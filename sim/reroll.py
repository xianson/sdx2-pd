"""Forced re-acquisition (the "re-roll") as an explicit, directly-controlled primitive.

MOTIVATION
  The burst-and-descend ladder wins, yet it changes rungs LESS often (0.347 per
  tracking call) than a rate-matched random rung cycler that loses (0.448). So the
  value is not "change range often" — it is WHEN the held target gets invalidated.
  What a rung change mechanically does is make the held target invalid, which fires
  Target.Reset(..., LostTracking) (SessionUpdate.cs:883); TargetChanged then opens the
  projectile-seek window immediately, so the mount re-draws from the WeaponCore deck
  on that same tick. The ladder may be nothing but a crude re-roll scheduler that
  happens to also pay a range price.

THE PRIMITIVE
  A "re-roll pulse" = for ONE PB tick (10 sim ticks) return a dipped tracking range,
  then restore. Dropping range below the held target's distance invalidates it and
  forces re-acquisition. Because the PB runs at Update10 the dip cannot be shorter
  than 10 ticks. Three dip depths, three different costs:

    dip='zero'     range=0 for one PB window. GUARANTEED drop, and the re-draw
                   happens only after restore (nothing is eligible during the dip),
                   so each pulse costs ~10 ticks of dip + up to 15 ticks waiting for
                   the next 1-in-15 seek window. This is the theoretically clean
                   re-roll: the new target is drawn from the FULL range set with no
                   range preference — but it withholds ~0.2-0.4 s of fire per pulse.
    dip='nearest'  range=nearest+margin for one PB window. Drops the target only if
                   it is beyond the leading edge; re-acquisition can succeed on the
                   SAME tick (TargetChanged window) among leading-edge torpedoes, so
                   fire is essentially not interrupted. A pulsed window_nearest.
    dip=<float>    range=frac*rung for one PB window. A transient rung visit —
                   drops only targets beyond frac, re-acquires below it. This is
                   what a ladder demotion does, minus the persistence.

  `bands` optionally pins each mount to a STATIC rung (idx % len(bands)) so range
  diversity can be tested separately from re-roll timing:
      static_band(LADDER)                = diversity only
      make_reroll(..., bands=LADDER)     = diversity + re-roll timing
      burst_ladder_only(14)              = diversity + re-roll timing + descend
  If the middle row matches the bottom row, descending is incidental and forced
  re-acquisition is the real primitive.

PHASE SIDE-EFFECT (see phase_probe.py)
  Every re-roll also bumps the mount's AcquireAttempts by >=1 (failed and successful
  attempts both count, AiTargeting.cs:98), which advances its deck window by
  check_size=4. Mounts with equal attempt counts examine the SAME 4-candidate chunk
  (chunk = 4*attempts % N). Staggered re-roll schedules therefore double as a deck
  DESYNC actuator — the only one a PB has, since pre-contact every target-less mount
  bumps at the same cadence-driven rate and cannot be differentiated.

LEGALITY: reads only ctx fields and own-mount state; the actuator is
SetBlockTrackingRange. Same footing as ladder.py.
"""
import math
import ladder as L

LADDER = L.LADDER


def _gid(m, ctx):
    return m._ship * ctx['per_hull'] + m._idx


# --------------------------------------------------------------------- triggers
# A trigger is trig(m, ctx, st) -> bool, consulted only when no pulse is active.
# st carries: shots0 (rounds at last re-roll), last_roll (t of last re-roll),
# held_since (first PB tick the tracking boolean was observed True), rolls.

def trig_rounds(burst=14):
    """The incumbent's own trigger, isolated: N of my rounds since the last re-roll.
    Round count is PB-known exactly (own shots via MonitorProjectile / ammo API)."""
    def t(m, ctx, st):
        return m.shots_fired - st['shots0'] >= burst
    return t


def trig_inflight(k=6, refractory=0.35):
    """Re-roll when my own in-flight count says a kill's worth is already committed.
    Torpedo health 4, PDC40mm hhm 1 -> 4 useful hits kill; with realistic hit rates
    k~5-8 rounds airborne means the target is dead-or-nearly if they connect.
    Refractory because in-flight rounds persist ~TOF after the pulse."""
    def t(m, ctx, st):
        return (m._has_tgt and m._in_flight >= k
                and ctx['t'] - st['last_roll'] >= refractory)
    return t


def trig_time(period=0.5, stagger=True):
    """Re-roll on a wall clock. With stagger, mount g's deadlines are offset by
    g*period/n_mounts, so at most one mount re-rolls per PB tick — the deliberate
    deck-phase spreader."""
    def t(m, ctx, st):
        if not m._has_tgt:
            return False
        if 'off' not in st:
            st['off'] = (float(_gid(m, ctx) % ctx['n_mounts']) / ctx['n_mounts']
                         * period if stagger else 0.0)
            st['last_roll'] = ctx['t'] - period + st['off']  # first roll at off
        return ctx['t'] - st['last_roll'] >= period
    return t


def trig_stale(hold=0.7):
    """Re-roll when the per-mount tracking boolean has been continuously True for
    `hold` seconds — the mount is welded to something that is either dying under
    someone else's fire or unkillable in time."""
    def t(m, ctx, st):
        return (st['held_since'] is not None
                and ctx['t'] - st['held_since'] >= hold)
    return t


def trig_conflict(tol=40.0, refractory=0.25):
    """Bearing convergence with another tracking mount as a RE-ROLL trigger.
    Plain conflict detection demoting a rung is inert on leakers (t=-1.15 @100
    seeds); this instead forces the less-committed mount of the pair to re-draw.
    Requires ladder.with_infl_index wrapping for the tie-break."""
    def t(m, ctx, st):
        if not m._has_tgt or ctx['t'] - st['last_roll'] < refractory:
            return False
        me = (m._ship, m._idx)
        for A, B in L._conflicts(ctx, tol):
            if A != me and B != me:
                continue
            other = B if A == me else A
            mine = m._in_flight
            theirs = ctx.get('_infl_by_key', {}).get(other, 0)
            if mine < theirs or (mine == theirs and me > other):
                return True
        return False
    return t


def trig_bearing_rate(eps_deg=0.4, need=2, refractory=0.3):
    """Re-roll when my aim direction has stopped moving for `need` consecutive PB
    samples — a frozen bearing means a dead-ahead closer already saturated, or a
    corpse-in-waiting. Caveat: torpedoes aimed at MY OWN hull are near-zero bearing
    rate by geometry, so this trigger is expected to misfire on the most dangerous
    targets; it is here because nobody had measured it."""
    ce = math.cos(math.radians(eps_deg))

    def t(m, ctx, st):
        key = '_bear_map'
        bm = ctx.get(key)
        if bm is None:
            bm = ctx[key] = {(s, i): d for s, i, _p, d in ctx.get('bearings', [])}
        d = bm.get((m._ship, m._idx))
        prev = st.get('prev_dir')
        st['prev_dir'] = d
        if d is None or prev is None:
            st['still'] = 0
            return False
        dn, pn = d.length(), prev.length()
        if dn < 1e-9 or pn < 1e-9:
            st['still'] = 0
            return False
        c = d.dot(prev) / (dn * pn)
        st['still'] = st.get('still', 0) + 1 if c >= ce else 0
        return (st['still'] >= need
                and ctx['t'] - st['last_roll'] >= refractory)
    return t


# ------------------------------------------------------------------ the machine
def make_reroll(trigger, dip='zero', bands=None, margin=400.0):
    """Generic re-roll controller: hold rung range r0 (static per mount if `bands`,
    else full base range); when `trigger` fires, emit a one-PB-tick dip, then
    restore r0 and reset the trigger's book-keeping."""
    nb = len(bands) if bands else 0

    def pol(m, ctx):
        st = getattr(m, '_rr', None)
        if st is None:
            st = m._rr = {'shots0': m.shots_fired, 'last_roll': ctx['t'],
                          'held_since': None, 'dip': False, 'rolls': 0}
        if st['last_roll'] > ctx['t']:
            st['last_roll'] = ctx['t']     # wave rollover, see descend_inflight
        if st['held_since'] is not None and st['held_since'] > ctx['t']:
            st['held_since'] = ctx['t']
        # observe the tracking boolean (real PB: GetWeaponTarget Item2 each Update10)
        if m._has_tgt:
            if st['held_since'] is None:
                st['held_since'] = ctx['t']
        else:
            st['held_since'] = None

        r0 = m._base_range * (bands[m._idx % nb] if nb else 1.0)

        if st['dip']:                       # restore leg of the pulse
            st['dip'] = False
            st['shots0'] = m.shots_fired
            st['last_roll'] = ctx['t']
            st['held_since'] = None
            st['rolls'] += 1
            return True, r0

        if trigger(m, ctx, st):             # dip leg
            st['dip'] = True
            if dip == 'zero':
                return True, 0.0
            if dip == 'nearest':
                return True, min(r0, ctx['nearest'] + margin)
            return True, r0 * float(dip)

        return True, r0
    return pol


# ------------------------------------------- descend variants (my own, not ladder.py)
def descend_inflight(k=6, bands=LADDER, cool_frac=0.20, dwell=0.35,
                     refractory=0.35):
    """The full burst-ladder structure but with the burst counter REPLACED by the
    in-flight commitment trigger: descend a rung when >=k of my rounds are airborne.
    Tests whether a better re-roll TRIGGER improves the incumbent ladder itself."""
    def pol(m, ctx):
        st = getattr(m, '_di', None)
        if st is None:
            st = m._di = {'rung': m._idx % len(bands), 'last': ctx['t'],
                          'bottom_at': None}
        # wave rollover: the harness resets t per wave (a real PB clock is
        # monotonic). Stale timestamps in the future would block the refractory
        # and the bottom-rung dwell for the entire next wave.
        if st['last'] > ctx['t']:
            st['last'] = ctx['t']
        if st['bottom_at'] is not None and st['bottom_at'] > ctx['t']:
            st['bottom_at'] = ctx['t']
        rung = st['rung']
        if (m._has_tgt and m._in_flight >= k
                and ctx['t'] - st['last'] >= refractory):
            if rung < len(bands) - 1:
                rung += 1
            st['last'] = ctx['t']
            st['bottom_at'] = ctx['t'] if rung == len(bands) - 1 else None
        if rung == len(bands) - 1:
            if st['bottom_at'] is None:
                st['bottom_at'] = ctx['t']
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and ctx['t'] - st['bottom_at'] >= dwell:
                rung = 0
                st['last'] = ctx['t']
                st['bottom_at'] = None
        st['rung'] = rung
        return True, m._base_range * bands[rung]
    return pol


def descend_stale(hold=0.6, bands=LADDER, cool_frac=0.20, dwell=0.35):
    """Ladder descend triggered by continuous-track time instead of round count."""
    def pol(m, ctx):
        st = getattr(m, '_ds', None)
        if st is None:
            st = m._ds = {'rung': m._idx % len(bands), 'held': None,
                          'bottom_at': None}
        if st['held'] is not None and st['held'] > ctx['t']:
            st['held'] = ctx['t']          # wave rollover, see descend_inflight
        if st['bottom_at'] is not None and st['bottom_at'] > ctx['t']:
            st['bottom_at'] = ctx['t']
        if m._has_tgt:
            if st['held'] is None:
                st['held'] = ctx['t']
        else:
            st['held'] = None
        rung = st['rung']
        if st['held'] is not None and ctx['t'] - st['held'] >= hold:
            if rung < len(bands) - 1:
                rung += 1
            st['held'] = ctx['t']       # re-arm
            st['bottom_at'] = ctx['t'] if rung == len(bands) - 1 else None
        if rung == len(bands) - 1:
            if st['bottom_at'] is None:
                st['bottom_at'] = ctx['t']
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and ctx['t'] - st['bottom_at'] >= dwell:
                rung = 0
                st['held'] = None
                st['bottom_at'] = None
        st['rung'] = rung
        return True, m._base_range * bands[rung]
    return pol
