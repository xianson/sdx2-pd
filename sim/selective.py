"""Selective-targeting PD policies built ONLY on levers the WeaponCore PB API has.

API surface, verified against wcbuild/src/Api/ApiBackend.cs (PbApiMethods dict)
and corrected against the coordinator's ground truth:

  AVAILABLE about INCOMING torpedoes:
    * GetProjectilesLockedOn(grid) -> (bool, count, age). Aggregate count only.
    * GetWeaponTarget(block, id): for a projectile target returns
      (true, true, false, null) (ApiBackend.cs:1074) — a per-mount "tracking a
      projectile" BOOLEAN. The entity is hard-coded null and TargetId is the -1
      sentinel for EVERY projectile (MiscTypes.cs:318), so per-torpedo
      attribution is impossible. Read here as `mount._has_tgt` /
      `ctx['tracking']`.
    * RegisterProjectileAdded(cb(pos, health)) — one launch fix per projectile,
      nothing after. Justifies the dead-reckoned `ctx['nearest']` estimate.

  AVAILABLE about OWN rounds:
    * MonitorProjectile registers only at the FIRING weapon's component
      (Projectile.cs:344), so it covers own rounds only; with
      GetProjectileState(id) it yields real position+velocity per own round
      (`ctx['own_rounds']`) and an exact per-mount in-flight count.

  NOT AVAILABLE:
    * GetProjectilesLockedOnPos (inbound positions) — mod-API only.
    * Assigning a projectile to a weapon — PbSetWeaponTarget resolves a long
      entityId via MyEntities.GetEntityById; internal Projectiles are not
      MyEntities.

So the design space is: shape WeaponCore's own acquisition indirectly.
Acquisition mechanics exploited below (targeting.py / wc_acquire.py):
  * a mount HOLDS its target while valid; validity re-checks
    dist <= mount.range every tick, so LOWERING range below the held target's
    distance force-drops it and opens an immediate re-seek window;
  * a target-less mount draws from a shuffled 4-wide deck window, so mounts
    frequently pile onto the same torpedo (-> dead-round waste, ~60% of all
    rounds at salvo 24);
  * ToggleWeaponFire stops SHOTS but not tracking or cooling.

Deliberately NOT here (already covered by demand.py, seeds 601-612):
commitment budgets / caps, demand- and arrival-banding, demand_max mount
gating, usage rebracketing, escalate-on-saturation. The incumbent to beat is
static band 1.0/.75/.5/.25, not baseline.

Policy interface: pol(mount, ctx) -> (fire: bool, tracking_range: float|None),
called at PB cadence (Update10). ctx fields documented in
fleet_efficiency.wave; each maps to a named API call.
"""
import math
from ship import DT

PB_DT = 10 * DT              # Update10 = one PB decision per 10 ticks


def _pbtick(ctx):
    """Integer PB-update counter, from accumulated Runtime.TimeSinceLastRun."""
    return int(round(ctx['t'] / PB_DT))


# --------------------------------------------------------------- controls
def pol_baseline(m, ctx):
    """Control: WeaponCore left alone. No PB calls."""
    return True, None


def range_band(bands):
    """INCUMBENT reference: static eligibility shells by mount index.

    One SetBlockTrackingRange per mount to bands[i]*base. The best previously
    measured policy (1.0/.75/.5/.25); every new idea reports against it.
    """
    def pol(m, ctx):
        return True, m._base_range * bands[m._idx % len(bands)]
    pol.__name__ = 'range_band'
    return pol


# --------------------------------------------------- 1. rolling window gate
def rolling_window(width):
    """Collapse every mount's eligibility onto the HEAD of the torpedo stream.

    Mechanism: SetBlockTrackingRange(block, nearest + width) every Update10,
    where `nearest` is dead-reckoned (RegisterProjectileAdded launch fix +
    known torpedo speed profile — the only way a PB can range inbounds).
    Torpedoes beyond the window are invisible to acquisition, so no mount
    wastes low-P(hit) long shots on the tail of the salvo while the front is
    live; shrinking range also force-drops held far targets, re-rolling the
    mount onto the near slice.

    Expected trade: miss-waste down (all shots short-range), pile-on and
    dead-round waste up (fewer eligible targets per deck draw).
    """
    def pol(m, ctx):
        return True, min(m._base_range, ctx['nearest'] + width)
    pol.__name__ = 'rolling_window_%d' % width
    return pol


# ------------------------------------------------ 2. occupancy-map surge
def occupancy_surge(bands=(1.0, 0.75, 0.5, 0.25)):
    """Range-bracketed occupancy map: sentinel mounts AS the sensor, the rest
    surge to wherever the map says the fight is.

    Mechanism: mounts 0..3 are pinned to staggered brackets (one
    SetBlockTrackingRange each); their GetWeaponTarget projectile-flag
    booleans (`ctx['tracking']`) then say which shells contain torpedoes —
    spatial resolution the single GetProjectilesLockedOn scalar cannot give,
    and with no dead reckoning. Every remaining mount is retasked each
    Update10 to the INNERMOST occupied bracket, concentrating fire at the head
    of the stream where P(hit) is highest and round flight time shortest.

    This is rolling_window rebuilt from a MEASURED signal instead of an
    estimated one; its lag is the sentinels' acquisition cadence.
    """
    def pol(m, ctx):
        if m._idx < len(bands):
            return True, m._base_range * bands[m._idx]      # sentinel layer
        tr = ctx['tracking'][m._ship]
        inner = None
        for k in range(len(bands) - 1, -1, -1):             # innermost first
            if k < len(tr) and tr[k]:
                inner = k
                break
        if inner is None:
            return True, None            # map empty: free-range until contact
        return True, m._base_range * bands[inner]
    pol.__name__ = 'occupancy_surge'
    return pol


# ------------------------------------------------ 3. convergence deconflict
def _converge_map(ctx, horizon=1.0, thresh=40.0):
    """Geometric same-target grouping from OWN rounds' pos+vel only.

    A real PB extrapolates its monitored rounds (GetProjectileState) as
    constant-velocity lines; rounds from different mounts whose trajectories
    pass within `thresh` metres inside the next `horizon` seconds are almost
    certainly converging on the same torpedo. Returns {mount_key: senior_key}
    for every mount whose newest round converges with a LOWER-ordered mount's
    newest round. No torpedo object, no round.target — geometry only.
    """
    cm = ctx.get('_conv')
    if cm is not None:
        return cm
    latest = {}
    for ship, idx, pos, vel in ctx['own_rounds']:
        latest[(ship, idx)] = (pos, vel)     # list is in firing order
    keys = sorted(latest)
    cm = {}
    for i in range(len(keys)):
        p1, v1 = latest[keys[i]]
        for j in range(i + 1, len(keys)):
            if keys[j] in cm:
                continue
            p2, v2 = latest[keys[j]]
            dp = p2 - p1
            dv = v2 - v1
            dvdv = dv.dot(dv)
            s = 0.0 if dvdv < 1e-9 else -dp.dot(dv) / dvdv
            if s <= 0.02 or s > horizon:
                continue
            if (dp + dv * s).length() <= thresh:
                cm[keys[j]] = keys[i]
    ctx['_conv'] = cm
    return cm


def converge_mute():
    """Deconflict by SILENCE: a mount whose fire provably converges with a
    senior mount's fire stops pouring into the shared target.

    Mechanism: _converge_map (own-round geometry, above) + ToggleWeaponFire.
    The junior mount keeps its track (toggle does not drop targets) and keeps
    its rounds already in flight; it simply stops adding to a torpedo that
    already has a full kill stream inbound. It resumes the moment convergence
    clears — which is exactly when the shared torpedo dies, because its own
    newest round then ceases to exist. Directly attacks
    committed-rounds-per-target, the driver of dead-round waste.
    """
    def pol(m, ctx):
        return (m._ship, m._idx) not in _converge_map(ctx), None
    pol.__name__ = 'converge_mute'
    return pol


def converge_retarget():
    """Deconflict by RESHUFFLE: the junior converging mount is forced to draw
    a new target instead of just shutting up.

    Mechanism: same convergence map, but the junior mount gets
    SetBlockTrackingRange(block, 1) for one Update10 — validity fails, the
    held target drops, and the re-seek (immediate on loss) lands on a fresh
    deck window with the shared torpedo now just 1 of ~4 candidates. Trades
    ~0.2-0.4 s of blindness for moving a redundant gun onto an unserviced
    torpedo, rather than idling it as converge_mute does.
    """
    def pol(m, ctx):
        if (m._ship, m._idx) in _converge_map(ctx):
            return True, 1.0
        return True, None
    pol.__name__ = 'converge_retarget'
    return pol


# ------------------------------------------------ 4. staggered release ladder
def ladder(r0, dr):
    """Temporal desync: mounts enter the fight one at a time, not all at once.

    Mechanism: ToggleWeaponFire — mount i holds fire until the dead-reckoned
    nearest threat is inside r0 - i*dr. Each newly released mount acquires at
    a different instant, after earlier kills have already reshuffled the deck,
    so commitments spread across the crossing instead of piling 8 mounts onto
    the first torpedoes the deck offers. Late rungs fire only at short range
    where P(hit) is high and the dead-round exposure window short. (Range-
    triggered, so distinct from demand.py's duty-triggered escalation.)
    """
    def pol(m, ctx):
        return ctx['nearest'] <= r0 - dr * (m._idx % ctx['per_hull']), None
    pol.__name__ = 'ladder_%d_%d' % (r0, dr)
    return pol


# ------------------------------------------------ 5. synchronized volley
def volley(on, off):
    """Global fire/assess duty cycle: the whole battery fires in pulses.

    Mechanism: ToggleWeaponFire on a shared clock (each hull derives the same
    phase from its own Runtime accumulation). A pulse of `on` PB ticks then
    `off` silent ticks lets each volley's kills LAND before the next volley
    acquires, so consecutive volleys do not stack rounds onto already-dead
    torpedoes. Pays with an (on)/(on+off) throughput cut inside a ~2.4 s
    window; the earlier toggle studies say throughput is binding, so this row
    is expected to LOSE — it is here as the synchronized-pulse control the
    per-mount rotation studies did not cover.
    """
    def pol(m, ctx):
        return _pbtick(ctx) % (on + off) < on, None
    pol.__name__ = 'volley_%don_%doff' % (on, off)
    return pol


# ------------------------------------------------ 6. retarget scramble
def scramble(period_pb=1):
    """Blind forced re-acquisition rotation: break up pile-ons open-loop.

    Mechanism: there is no "drop target" call, but validity re-checks
    dist <= range every tick — so SetBlockTrackingRange(block, 1) for one
    Update10 force-drops whatever the mount held and the loss opens an
    immediate re-seek on an advanced deck window. One mount per hull is pulsed
    each `period_pb` PB ticks, round-robin. Unlike converge_retarget this uses
    no evidence — it is the control that says whether the convergence map is
    worth its complexity, or whether random reshuffling does just as well.
    """
    def pol(m, ctx):
        slot = (_pbtick(ctx) // period_pb) % ctx['per_hull']
        if m._idx == slot:
            return True, 1.0
        return True, None
    pol.__name__ = 'scramble_%dpb' % period_pb
    return pol


# ------------------------------------------------ 7. goalkeeper reserve
def goalkeeper(k=2, r=1000.0):
    """Sacrifice sustained pressure for a guaranteed clean endgame.

    Mechanism: SetBlockTrackingRange once — k mounts per hull are pinned to a
    short radius r where dispersion is negligible and round flight time ~0.3 s,
    so nearly every round they commit resolves before the target can die to
    someone else. They are structurally incapable of joining the long-range
    pile-on; they exist to kill what the outer battery leaks. Distinct from
    demand.py's escalate_on_saturation: this reserve is always-armed and
    range-gated, not duty-triggered.
    """
    def pol(m, ctx):
        if (m._idx % ctx['per_hull']) < k:
            return True, r
        return True, None
    pol.__name__ = 'goalkeeper_%d_%d' % (k, int(r))
    return pol
