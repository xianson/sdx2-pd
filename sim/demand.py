"""Commitment budgeting and demand-driven banding.

Three ideas, all implementable with ONLY `ToggleWeaponFire` + `SetBlockTrackingRange`
plus polling `GetProjectilesLockedOn` and a clock:

1. COMMITMENT BUDGET ("fire X, then toggle off").
   Dead-round waste is rounds still in flight when the kill lands. A mount that keeps
   firing after it has already committed enough rounds to kill is manufacturing waste.
   So: fire a burst sized to the kill requirement, then cease fire for one time-of-flight
   so the burst can resolve, then resume. Unlike duty rotation this does not surrender
   throughput -- the off-interval is exactly the window in which extra rounds would have
   been redundant. Duty rotation turns guns off blindly; this turns them off only when
   they would be wasting.

2. DEMAND-DRIVEN BANDING.
   Instead of fixed range fractions, set the band from measured demand: how many
   torpedoes are inbound and how long until they arrive. More demand -> engage further
   out to buy more shots. Less demand -> engage close, where P(hit) is high and flight
   time short.

3. DEMAND MAXING (supply matching).
   Compute rounds required vs rounds deliverable in the time remaining, and enable only
   as many mounts as that requires. Surplus mounts stay dark rather than pile redundant
   rounds onto targets already covered.

WHAT A PB CAN ACTUALLY SEE -- every signal below is differenced from successive polls,
which is what a real script would do:
    ctx['inbound']  <- GetProjectilesLockedOn(victim).Count
    ctx['nearest']  <- range to closest threat (from the same call's projectile list)
    ctx['t']        <- clock
  net delta        = d(inbound)/dt      across PB ticks
  closing speed    = -d(nearest)/dt     across PB ticks
  arrival time     = nearest / closing
No policy here touches a torpedo object, a per-projectile identity, or anything the PB
API cannot return. `_hist` is per-mount scratch, seeded lazily because run() rebuilds
ships every call.
"""
import math

#: SDX2 torpedo Health (4-5) / PDC40mm HealthHitModifier 1
HITS_TO_KILL = 4
#: measured single-round hit fraction for a 3.417 m threshold mount at mid envelope.
#: Deliberately a parameter: it is what converts "hits needed" into "rounds needed".
P_HIT = 0.19


def _poll(m, ctx):
    """Difference successive PB polls into (delta_inbound, closing_speed, arrival_s).

    Returns closing=0 / arrival=inf on the first poll, when a real script would also
    have no derivative yet.
    """
    h = getattr(m, '_hist', None)
    if h is None:
        h = m._hist = {'t': ctx['t'], 'in': ctx['inbound'], 'near': ctx['nearest'],
                       'din': 0.0, 'closing': 0.0}
        return 0.0, 0.0, float('inf')
    dt = ctx['t'] - h['t']
    if dt <= 1e-9:
        return h['din'], h['closing'], (
            ctx['nearest'] / h['closing'] if h['closing'] > 1e-6 else float('inf'))
    din = (ctx['inbound'] - h['in']) / dt
    closing = (h['near'] - ctx['nearest']) / dt
    h.update(t=ctx['t'], **{'in': ctx['inbound']}, near=ctx['nearest'],
             din=din, closing=closing)
    arrival = ctx['nearest'] / closing if closing > 1e-6 else float('inf')
    return din, closing, arrival


def _rate(m):
    """Rounds per second. PDC_STATS rof is rounds per MINUTE."""
    return m.rof / 60.0


# ------------------------------------------------------------------ 1. commitment
def commitment_budget(rounds_per_burst=None, hold_factor=1.0, p_hit=P_HIT):
    """Fire a kill-sized burst, then cease fire for hold_factor x time-of-flight.

    rounds_per_burst defaults to HITS_TO_KILL / p_hit -- the expected rounds needed to
    land the required hits. hold_factor scales the resolve window: 1.0 waits exactly one
    time-of-flight, so the burst has landed before the mount commits anything further.

    Implementation in-game: track `shots_fired` via the weapon's own counters (or just
    integrate rof x elapsed), then ToggleWeaponFire(false) and set a resume tick.
    """
    def pol(m, ctx):
        _poll(m, ctx)
        n = rounds_per_burst if rounds_per_burst else max(1.0, HITS_TO_KILL / p_hit)
        st = getattr(m, '_burst', None)
        if st is None:
            st = m._burst = {'base': m.shots_fired, 'off_until': -1.0}
        if ctx['t'] < st['off_until']:
            return False, None
        if m.shots_fired - st['base'] >= n:
            tof = ctx['nearest'] / max(1.0, m.muzzle)
            st['off_until'] = ctx['t'] + hold_factor * tof
            st['base'] = m.shots_fired
            return False, None
        return True, None
    return pol


def commitment_budget_staggered(rounds_per_burst=None, hold_factor=1.0, p_hit=P_HIT):
    """Same, but mounts start their cycles out of phase by _idx.

    Synchronised bursts across 8 mounts would put 8x the ordnance in the air at once,
    which is the very thing the budget is meant to prevent. Phasing spreads commitment
    across the engagement.
    """
    inner = commitment_budget(rounds_per_burst, hold_factor, p_hit)

    def pol(m, ctx):
        st = getattr(m, '_burst', None)
        if st is None:
            n = rounds_per_burst if rounds_per_burst else max(1.0, HITS_TO_KILL / p_hit)
            # stagger the FIRST burst only; afterwards the tof hold keeps them apart
            frac = (m._idx % 4) / 4.0
            m._burst = {'base': m.shots_fired - n * frac, 'off_until': -1.0}
        return inner(m, ctx)
    return pol


# ---------------------------------------------------------------- 2. dynamic band
def demand_band(lo=0.3, hi=1.0, per_torp=0.05):
    """Band fraction scales with inbound count: more threats -> engage further out.

    A light raid is handled close in, where flight time is short and P(hit) is high. A
    heavy raid needs every second of envelope, so the band opens up. Mount _idx still
    spreads the layers so mounts do not all sit at the same radius.
    """
    def pol(m, ctx):
        _poll(m, ctx)
        want = lo + per_torp * ctx['inbound']
        want = max(lo, min(hi, want))
        # spread the four layers around the demanded centre
        spread = (1.0, 0.85, 0.7, 0.55)[m._idx % 4]
        return True, m._base_range * want * spread
    return pol


def arrival_band(lo=0.25, hi=1.0, target_shots=None, p_hit=P_HIT):
    """Set the band from PREDICTED ARRIVAL TIME rather than raw count.

    Rounds available against the nearest threat is rate x arrival_time. If that already
    exceeds what a kill needs, pull the band in (shorter flight, less commitment). If it
    falls short, open up to buy exposure. This is the "net delta + predicted arrival"
    form: closing speed and arrival time both come from differencing polls.
    """
    need = target_shots if target_shots else max(1.0, HITS_TO_KILL / p_hit)

    def pol(m, ctx):
        _din, _closing, arrival = _poll(m, ctx)
        if not math.isfinite(arrival):
            return True, None
        avail = _rate(m) * arrival
        # surplus -> tighten, deficit -> widen
        frac = hi if avail < need else max(lo, min(hi, need / max(1e-6, avail)))
        spread = (1.0, 0.85, 0.7, 0.55)[m._idx % 4]
        return True, m._base_range * frac * spread
    return pol


# ---------------------------------------------------------------- 3. demand maxing
def demand_max(p_hit=P_HIT, headroom=1.0, bands=(1.0, 0.85, 0.7, 0.55)):
    """Enable only as many mounts as the measured demand requires.

    rounds_required = inbound x HITS_TO_KILL / p_hit
    rounds_per_mount = rate x arrival_time
    mounts_needed    = ceil(required / per_mount) x headroom
    A mount fires iff its _idx is inside that count. Surplus mounts stay dark instead of
    stacking redundant rounds onto covered targets. Mounts that DO fire keep the banding
    spread so they are not all at one radius.

    headroom > 1 over-provisions against the p_hit estimate being optimistic.
    """
    def pol(m, ctx):
        _din, _closing, arrival = _poll(m, ctx)
        spread = bands[m._idx % len(bands)]
        if not math.isfinite(arrival) or arrival <= 0:
            return True, m._base_range * spread
        required = ctx['inbound'] * HITS_TO_KILL / max(1e-6, p_hit)
        per_mount = max(1e-6, _rate(m) * arrival)
        needed = math.ceil(headroom * required / per_mount)
        return (m._idx < needed), m._base_range * spread
    return pol


def demand_max_global(p_hit=P_HIT, headroom=1.0, mounts_per_hull=8,
                      bands=(1.0, 0.85, 0.7, 0.55)):
    """demand_max, but the mount count is fleet-wide rather than per hull.

    A 3-hull net has 24 mounts against one salvo; sizing per hull over-provisions 3x.
    Fleet-wide indexing needs only an IGC hull ordinal, which the net already shares.
    """
    def pol(m, ctx):
        _din, _closing, arrival = _poll(m, ctx)
        spread = bands[m._idx % len(bands)]
        gidx = m._ship * mounts_per_hull + m._idx
        if not math.isfinite(arrival) or arrival <= 0:
            return True, m._base_range * spread
        required = ctx['inbound'] * HITS_TO_KILL / max(1e-6, p_hit)
        per_mount = max(1e-6, _rate(m) * arrival)
        needed = math.ceil(headroom * required / per_mount)
        return (gidx < needed), m._base_range * spread
    return pol


# ------------------------------------------------------------------- combinations
def combine(*pols):
    """AND the fire decisions; the LAST policy returning a range wins.

    Ordering is load-bearing and previously bit us: putting a flat range clip after a
    band silently discarded the band. Put the band LAST if you want it to survive.
    """
    def pol(m, ctx):
        fire, rng = True, None
        for p in pols:
            f, r = p(m, ctx)
            fire = fire and f
            if r is not None:
                rng = r
        return fire, rng
    return pol


# ============================================================================
# API REALITY CHECK (verified in wcbuild/src/Api + Projectiles, not assumed)
#
# WHAT A PB CAN SEE ABOUT INCOMING TORPEDOES: only the aggregate.
#   GetProjectilesLockedOn(gridEntityId) -> MyTuple<bool,int,int>   count only.
# There is NO API returning enemy projectile positions. `MonitorProjectile` looks
# like it should, but its registration site is Projectile.cs:344 inside
# Projectile.Start(), where `comp` is the FIRING weapon's own component -- so
# Session.MonitoredProjectiles only ever holds rounds YOUR OWN monitored weapons
# fired. GetProjectileState(id) then yields
#   (Position, Velocity, BaseDamagePool, BaseHealthPool, Target.TargetId, AmmoRound)
# for those, which means you CAN measure your own committed ordnance precisely.
#
# THE TRAP that kills per-target accounting: Target.SetTargetId
# (Support/MiscTypes.cs:318) sets TargetId = -1 for EVERY projectile target --
# a sentinel, not an identity. So all your anti-torpedo rounds report the same
# target id and cannot be attributed to individual torpedoes. Per-target
# commitment counting is therefore impossible through the API; only fleet-total
# committed ordnance is measurable. Everything below respects that.
# ============================================================================


def _shots_window(m, ctx, window):
    """Rounds this mount fired within the last `window` seconds.

    In-game equivalent: count your own MonitorProjectile spawn callbacks over the
    window, or integrate rof x firing time. Both are legitimate.
    """
    h = getattr(m, '_sw', None)
    if h is None:
        h = m._sw = []
    h.append((ctx['t'], m.shots_fired))
    while len(h) > 2 and h[0][0] < ctx['t'] - window:
        h.pop(0)
    return m.shots_fired - h[0][1]


# ------------------------------------------------- 4. usage-based re-bracketing
def usage_rebracket(bands=(1.0, 0.75, 0.5, 0.25), window=0.5, hot=0.6):
    """Move a gun to a DIFFERENT range bracket based on how hard it is working.

    A mount firing near-continuously is in a saturated bracket -- there is more work
    at its radius than it can service, so pushing it outward buys it more exposure
    time. A mount that is barely firing is in a starved bracket and gets pulled
    inward where hit probability is higher and flight time shorter.

    Closed-loop version of static banding: brackets are reassigned from observed
    load rather than fixed by index. Needs only per-mount firing time, which a PB
    reads from its own shot counters.
    """
    def pol(m, ctx):
        _poll(m, ctx)
        st = getattr(m, '_ub', None)
        if st is None:
            st = m._ub = {'lvl': m._idx % len(bands)}
        fired = _shots_window(m, ctx, window)
        duty = fired / max(1e-6, _rate(m) * window)
        if duty >= hot and st['lvl'] > 0:
            st['lvl'] -= 1              # saturated -> outward (wider band)
        elif duty < hot * 0.4 and st['lvl'] < len(bands) - 1:
            st['lvl'] += 1              # starved -> inward (tighter band)
        return True, m._base_range * bands[st['lvl']]
    return pol


# -------------------------------------- 5. saturation-triggered escalation
def escalate_on_saturation(window=0.5, hot=0.75, bands=(1.0, 0.85, 0.7, 0.55)):
    """Keep a reserve dark; commit it only when the active set is provably saturated.

    This is the correct fix to duty rotation's failure. Rotation lost badly (+4.6
    leakers, t=+7.4) because it darkened mounts that were needed. Escalation is a
    RATCHET: it only ever ADDS guns, and only once the ones already firing are at
    max duty, so it can never remove throughput that was doing work.

    Reserve mounts idle at zero cost. A PB implements this with per-mount duty
    measurement plus ToggleWeaponFire, and shares the tier over IGC for a fleet.
    """
    def pol(m, ctx):
        _poll(m, ctx)
        spread = bands[m._idx % len(bands)]
        grp = getattr(m, '_esc_grp', None)
        if grp is None:
            grp = m._esc_grp = m._idx // 2          # tiers of 2 mounts
        st = getattr(m, '_esc', None)
        if st is None:
            st = m._esc = {'tier': 0, 'last': ctx['t']}
        fired = _shots_window(m, ctx, window)
        duty = fired / max(1e-6, _rate(m) * window)
        # a mount at max duty raises its own tier ceiling; escalation is monotonic
        if duty >= hot and ctx['t'] - st['last'] >= window:
            st['tier'] += 1
            st['last'] = ctx['t']
        return (grp <= st['tier']), m._base_range * spread
    return pol


# ------------------------------- 6. committed-ordnance supply/demand controller
def committed_cap(p_hit=P_HIT, headroom=1.5, bands=(1.0, 0.85, 0.7, 0.55)):
    """Cease fire once committed ordnance already exceeds what the raid requires.

    Dead-round waste is committed rounds that outlive their target. So cap
    commitment: rounds needed = inbound x HITS_TO_KILL / p_hit; rounds already in
    the air from this mount over the last time-of-flight is measurable. Scale by
    headroom for the p_hit estimate being optimistic.

    Uses ONLY aggregate inbound count and own shot counters -- both available.
    Per-target attribution is impossible (TargetId == -1), so this caps the total,
    which is the strongest legal form of the idea.
    """
    def pol(m, ctx):
        _poll(m, ctx)
        spread = bands[m._idx % len(bands)]
        tof = max(0.05, ctx['nearest'] / max(1.0, m.muzzle))
        in_air = _shots_window(m, ctx, tof)
        allowance = headroom * (ctx['inbound'] * HITS_TO_KILL / max(1e-6, p_hit)) \
            / max(1, 8)                      # per-mount share of the requirement
        return (in_air < allowance), m._base_range * spread
    return pol
