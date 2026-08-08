"""Projectile target selection, delegating to the exact WeaponCore port.

The previous version of this file picked uniformly at random from the whole
valid pool. That is NOT what WeaponCore does. AiTargeting.cs:607-641 with the
SDX2 PDC definition (CycleTargets = 4) makes each mount examine a WINDOW of
four consecutive entries in the projectile cache, shuffled among themselves,
where the window START advances by four on every acquisition attempt:

    chunk      = checkSize * w.AcquireAttempts % numOfTargets
    checkSize  = 4  (or numOfTargets - chunk near the end of the cache)
    deck       = GetDeck(chunk, checkSize, numOfTargets, w.AcquireRandom)
    for x in 0..checkSize:  first candidate that passes every filter wins

So it is a CYCLING SCAN with local randomisation, not a uniform draw. Two
mounts whose AcquireAttempts happen to agree examine the same four torpedoes.

See wc_acquire.py for the line-by-line port. This module only supplies the
filter chain (range / bearing / own-hull occlusion) that stands in for
AiTargeting.cs:661-758 + CanShootTarget.
"""
import wc_acquire as wc
from vec import V

# SessionUpdate.cs:746-757 acquisition cadence: a target-less weapon only gets
# to run AcquireTarget on its 1-in-60 awake slot or its 1-in-15 projectile
# window (SessionUpdate.cs:736, QCount 0..14). Set False to let every mount
# attempt every tick (the old behaviour).
MODEL_ACQUIRE_CADENCE = True

# WC assigns UniquePartId / Acquire.SlotId / ShortLoadId sequentially in part
# registration order (SessionTypes.cs:723-726, SessionSupport.cs:414-419).
#
# THIS MODULE NO LONGER KEEPS ITS OWN COUNTER. It used to, and because nothing reset
# it, repeat N of a scenario inside one process gave its mounts different part ids --
# and therefore different acquisition RNG streams and different cadence phases -- from
# repeat 1. That is the same defect as torpedo2._ids, in a second place. The id is now
# owned by weapons.PdcMount (`m.unique_part_id`), assigned from the one registry that
# `weapons.reset_part_ids()` clears, so there is exactly one thing to reset.
def _reset_registry():
    """Deprecated shim. The registry lives in weapons.reset_part_ids()."""
    import weapons
    weapons.reset_part_ids()


class _WcState:
    """Per-mount mirror of the Weapon fields the acquisition paths read."""

    def __init__(self, kind, pid, rnd_obj):
        self.p = wc.sdx2_pdc(kind, unique_part_id=pid)
        self.slot_id = pid % wc.AWAKE_BUCKETS            # SessionTypes.cs:723
        self.short_load_id = pid % wc.SHORT_LOAD_BUCKETS  # SessionSupport.cs:414
        self.rnd_obj = rnd_obj                            # reset() sentinel
        self.tick = 0
        self.held = None
        self.target_changed = False


def _state(m):
    st = getattr(m, '_wc', None)
    # PdcMount.reset() builds a fresh self.rnd; that is our "world reloaded"
    # signal, and WC likewise rebuilds AcquireRandom from CurrentSeed.
    if st is None or st.rnd_obj is not m.rnd:
        st = _WcState(m.kind, m.unique_part_id, m.rnd)
        m._wc = st
    return st


def bearing_local(m, x, ship):
    """Unit vector from the ship to the candidate, in HULL-LOCAL space.

    This is what the mount has to slew onto, and it is what a caller needs in order
    to run the real slew model (`PdcMount.acquire(tgt, dir_local=...)`) instead of the
    derived dead-time fallback. `select` caches the winner's on `m.aim_dir_local`.
    """
    d = x.pos - ship.pos
    n = d.length()
    if n < 1e-9:
        return ship.dir_to_local(V(0.0, 0.0, 1.0))
    return ship.dir_to_local(d / n)


def cross_speed(m, x, ship):
    """Component of the candidate's velocity PERPENDICULAR to this mount's line of
    fire, in m/s. Feeds PdcMount.p_kill_per_shot(cross_speed=...): the muzzle
    SpeedVariance lead error is purely cross-track, so a head-on closer sees none of
    it and a crosser sees all of it."""
    d = x.pos - ship.pos
    n = d.length()
    if n < 1e-9:
        return 0.0
    r = d / n
    v = getattr(x, 'vel', None)
    if v is None:
        return 0.0
    rel = v - getattr(ship, 'vel', V(0.0, 0.0, 0.0))
    return (rel - r * rel.dot(r)).length()


def valid(m, x, ship, hull, perfect=False):
    """Stands in for AiTargeting.cs:661-758 (state / speed / distance filters)
    plus Weapon.CanShootTarget (:769) and the own-grid Bresenham LOS check
    (:840). Returns (ok, distance)."""
    d = x.pos - ship.pos
    dist = d.length()
    if dist > m.range or not x.alive:      # w.MaxTargetDistanceSqr, :666-667
        return False, dist
    if not perfect:
        dl = ship.dir_to_local(d.normalized())
        if not m.bears(dl) or m.occluded(hull, dl):
            return False, dist
    return True, dist


def select(m, candidates, ship, hull, perfect=False, closest_first=None):
    """Returns (target, distance) or (None, None).

    Holds the current target while it stays valid (SessionUpdate.cs:755:
    weaponReady requires `!w.Target.HasTarget`), then runs one exact
    AcquireProjectile pass over the WeaponCore deck.
    """
    st = _state(m)
    w = st.p
    # Stands in for Session.Tick. Valid because fleet_efficiency calls select
    # once per mount per tick; a caller that skips mounts (engage_all=False)
    # will have their counters lag, which only shifts the cadence phase.
    st.tick += 1
    if closest_first is not None:
        w.closest_first = closest_first

    # ---- hold ------------------------------------------------------------
    cur = st.held
    if cur is not None:
        ok, dist = valid(m, cur, ship, hull, perfect)
        if ok:
            st.target_changed = False
            m.aim_dir_local = bearing_local(m, cur, ship)
            return cur, dist
        # Target.Reset(..., LostTracking) at SessionUpdate.cs:883 sets
        # TargetChanged, which opens the projectile-seek window immediately.
        st.held = None
        st.target_changed = True

    # ---- cadence gate ----------------------------------------------------
    if MODEL_ACQUIRE_CADENCE and not wc.weapon_may_seek(
            st.tick, st.slot_id, st.short_load_id, False, st.target_changed):
        st.target_changed = False
        return None, None
    st.target_changed = False

    # ---- one AcquireProjectile pass -------------------------------------
    hit = {}

    def accept(lp):
        ok, dist = valid(m, lp, ship, hull, perfect)
        if ok:
            hit['d'] = dist
        return ok

    # `candidates` plays the part of ai.GetProCache(w, SupportingPD) --
    # AiTargeting.cs:545. It is a live list; ClosestFirst would shellsort it
    # in place, exactly as WC mutates the shared cache.
    pick = wc.acquire_projectile(
        w, candidates, accept,
        weapon_pos=ship.pos,
        dist_sq=lambda p, wp: (p.pos - wp).length() ** 2)

    wc.bump_acquire_attempts(w)            # AiTargeting.cs:98, always

    if pick is None:
        m.aim_dir_local = None
        return None, None
    st.held = pick
    m.aim_dir_local = bearing_local(m, pick, ship)
    return pick, hit['d']
