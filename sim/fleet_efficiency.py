"""Fleet PD efficiency with the CORRECTED torpedo model.

Two changes from every earlier torpedo result:
  1. Torpedo2 — staged Approaches, so terminal speed is 1040-1300 m/s, not 260.
     PDC exposure over a 3 km envelope drops from ~11 s to ~2.2-3.0 s.
  2. weave_sigma() — lateral dispersion bounded by v*tof instead of 0.5*a*tof^2,
     which used to exceed the physically achievable displacement past ~1 km.

Scored on two axes, not leakers alone:
  * CAPACITY CONSUMED  mount-seconds actually engaged / mount-seconds available.
    What fraction of the fleet's point defence the wave cost you.
  * LEAK COST          priced by WHAT the leaker hits, using the subsystem model.
    Armour damage is repairable from raw ore (free); a dead PDC is 20x
    TargetingComputer + 5x faction scrap; a dead railgun is 40x Electromagnet +
    100x scrap. Counting leakers treats those as equal. They are not.

Multi-wave, because conserving capacity only has value if a wave 2 exists.
"""
import math, sys, io, random
import weapons
from vec import V
from ship import Ship, DT
from shipyard import build_ship
from hull2 import GRID
from weapons import PdcMount, PDC_ALIAS, FLAK_PROXIMITY, TORP_RADIUS
from torpedo2 import Torpedo2, PROFILES
import targeting
from targeting import select
from rounds import fire, HIT, WASTED, EXPIRED

# NPC-component cost of replacing what a leaker destroys (economics.py roots)
LEAK_COST = {'pdc': 25.0, 'railgun': 140.0, 'torptube': 50.0, 'armour': 0.0,
             'reactor': 0.0, 'rcs': 0.0, 'other': 0.0}

# There is NO local p_kill in this file any more.
#
# It used to inline its own copy:
#     spread = dist*tan(dev); if weaving: hypot(spread, weave_sigma(kind, tof))
#     return 1.0 if spread <= eff else (eff / spread) ** 2
# and that copy carried BOTH of the errors AUDIT_WEAPONS found and fixed in
# PdcMount.p_kill_per_shot -- the squared-disc hit law (the real dispersion is uniform
# in POLAR ANGLE, WeaponShoot.cs:214, so the law is LINEAR in target radius) and the
# 10,920 m/s^2 weave. So every number this file printed was a pre-audit number
# regardless of what weapons.py said. The shared method is now the only implementation.


def class_speed_mps(cls):
    """Class speed cap in m/s = world cap * <MaxSpeed> modifier."""
    from components import class_speed
    return class_speed(cls)[0]


def torp_weave_params(torp_kind):
    """(cruise, OffsetRatio, OffsetTime) for the ACTUAL round, from its profile.

    p_kill_per_shot used to be handed the 0.7-ratio worst case for everything; the real
    values are per-round (0.2 Belter / 0.32 HEKP / 0.7 Plasma) and the cruise speed is
    the staged terminal figure, not 260.
    """
    p = PROFILES[torp_kind]
    sm = p['smarts']
    return p['desired'], sm['offset_ratio'], sm['offset_time']


def wave(fleet, salvo, torp_kind, rnd, spacing, duration=90.0,
         detonate_at=150.0, start_range=6000.0, engage_all=True, perfect=False,
         launcher_speed=0.0, policy=None, pb_ticks=10, assign=None,
         launch_delays=None):
    """One salvo against the fleet. Returns (leakers, kills, mount_seconds_engaged).

    `launcher_speed` matters and used to be ignored: MaxSpeed is
    |ShooterVel + dir*DesiredSpeed| (Projectile.cs:295-297), so every speed cap on the
    round scales with how fast the launching hull was going.
    """
    lead = fleet[0][0]
    axis = V(-1, 0, 0)
    cruise, ratio, off_ticks = torp_weave_params(torp_kind)
    torps = []
    for i in range(salvo):
        off = V(rnd.uniform(-80, 80), rnd.uniform(-80, 80), rnd.uniform(-80, 80))
        # index=i: the round's RNG stream is a function of (seed, position in salvo),
        # never of a process-global counter. See Torpedo2.reset_ids.
        # A torpedo launched `d` seconds later starts `d * v` further back. Modelling
        # the stagger as extra START DISTANCE keeps every round's own kinematics
        # (staged Approaches, boost phase, weave) exactly as the verified profile.
        back = 0.0
        if launch_delays:
            back = launch_delays[i % len(launch_delays)] * 260.0
        torps.append(Torpedo2(torp_kind, lead.pos - axis * (start_range + back) + off,
                              axis * 260.0, lead, seed=rnd.randrange(10 ** 6), index=i,
                              shooter_vel=axis * launcher_speed))
    t = 0.0
    leakers = kills = 0
    engaged_ticks = 0
    ticks = 0
    # WASTE accounting, on the two categories that actually exist once rounds fly:
    #   wasted   the round's target died while the round was still in flight, so it
    #            flew past a corpse. A round can ONLY hit its assigned target
    #            (ProjectileHits.cs:601), so this is unrecoverable, and it is the
    #            waste that fleet coordination can actually reduce.
    #   missed   the round lived out its range without intersecting -> dispersion,
    #            speed variance and the weave. A weapon property, not a control one.
    # `overkill` is damage past the kill threshold on an otherwise useful hit.
    fired_rounds = wasted_rounds = missed_rounds = 0
    total_shots = 0.0
    hits = useful_hits = overkill_hits = 0.0
    dup_shots = 0.0
    dup_tick_assignments = 0
    engagers = {}                   # target id -> set of mounts that ever shot at it
    in_flight = []
    off_ticks_count = 0
    # PB control runs at Update10, not every tick. Base range is captured once so a
    # policy that narrows tracking range cannot ratchet it down cumulatively.
    for _sh, _hull, _ms in fleet:
        for _m in _ms:
            if not hasattr(_m, '_base_range'):
                _m._base_range = _m.range
            _m._pol_off = False
            _m._want = True
    while t < duration and any(x.alive for x in torps):
        alive = [x for x in torps if x.alive]
        if not alive:
            break
        ticks += 1
        if policy is not None and (ticks - 1) % pb_ticks == 0:
            nearest = min((x.pos - lead.pos).length() for x in alive)
            # Every ctx field maps to something a PB can really read:
            #   t        Runtime.TimeSinceLastRun accumulation
            #   inbound  WcPbApi.GetProjectilesLockedOn(grid).Item2
            #   nearest  dead-reckoned from RegisterProjectileAdded launch fix +
            #            known torpedo kinematics (no live positions exist for a
            #            PB: GetProjectilesLockedOnPos is mod-API only)
            #   n_ships/per_hull/n_mounts  own fleet config via IGC
            ctx = {'t': t, 'inbound': len(alive), 'nearest': nearest,
                   'n_ships': len(fleet),
                   'per_hull': max(len(_f[2]) for _f in fleet),
                   'n_mounts': sum(len(_f[2]) for _f in fleet)}
            # per-mount rounds in flight: PB-maintainable exactly, via the
            # MonitorProjectile spawn/despawn callback on own weapons.
            # Caveat: the sim retires dead-target rounds at the kill tick; in
            # game they persist to end-of-life, so real counts decay <=1 s slower.
            _infl = {}
            for _r in in_flight:
                _infl[id(_r.mount)] = _infl.get(id(_r.mount), 0) + 1
            # pre-pass: per-mount observables, before any policy runs, so a
            # policy may read the WHOLE battery's state (a real PB polls every
            # weapon each Update10 and shares across hulls over IGC).
            for _si, (_sh, _hull, _ms) in enumerate(fleet):
                for _i, _m in enumerate(_ms):
                    _m._idx = _i
                    _m._ship = _si
                    _m._in_flight = _infl.get(id(_m), 0)
                    # GetWeaponTarget: for a projectile target it returns
                    # (true, true, false, null) — Item2 is a per-mount
                    # "tracking a projectile" boolean, no identity/position
                    # (TargetId is the -1 sentinel for every projectile).
                    _w = getattr(_m, '_wc', None)
                    _m._has_tgt = bool(_w is not None and _w.held is not None
                                       and _w.held.alive)
            # tracking[ship][idx] -> that mount's projectile-track boolean.
            ctx['tracking'] = [[bool(_m._has_tgt) for _m in _f[2]] for _f in fleet]
            # own_rounds: (ship, idx, pos, vel) of every OWN round in flight —
            # exactly what MonitorProjectile + GetProjectileState expose.
            # Positions/velocities only; no target identity crosses this line.
            ctx['own_rounds'] = [(_r.mount._ship, _r.mount._idx, _r.pos, _r.vel)
                                 for _r in in_flight]
            # bearings: (ship, idx, muzzle_world, aim_dir_world) for every mount
            # currently tracking a projectile. This is GetWeaponAzimuthMatrix x
            # GetWeaponElevationMatrix (CoreSystemsPbApi.cs:138-139, PB-registered
            # at ApiBackend.cs:222) plus the block's own world position. Direction
            # only -- NO range and no identity, which is the whole point: range to
            # a torpedo has to be TRIANGULATED from two of these.
            # Fidelity caveat: this is the bearing to the target's current
            # position, whereas a real turret points at the PREDICTED INTERCEPT.
            # Two mounts at different ranges therefore aim at slightly different
            # points for the SAME torpedo, so in game the rays converge less
            # tightly than here and any tolerance must be correspondingly larger.
            _bearings = []
            for _si, (_sh, _hull, _ms) in enumerate(fleet):
                for _i, _m in enumerate(_ms):
                    _d = getattr(_m, 'aim_dir_local', None)
                    if not _m._has_tgt or _d is None:
                        continue
                    _mw = _sh.to_world(V(_m.cell[0], _m.cell[1], _m.cell[2]) * GRID
                                       + _m.normal * (GRID * 1.01))
                    _bearings.append((_si, _i, _mw, _sh.to_world(_d) - _sh.pos))
            ctx['bearings'] = _bearings
            # ---- ORACLE-SIDE ONLY. True torpedo objects and the mount->hull map,
            # for BOUNDING experiments (eligible-count gating). No PB can read these;
            # any policy touching them is measuring a ceiling, not a deployable rule.
            ctx['_torps'] = alive
            _so, _ho = {}, {}
            for _sh2, _hull2, _ms2 in fleet:
                for _m2 in _ms2:
                    _so[id(_m2)] = _sh2
                    _ho[id(_m2)] = _hull2
            ctx['_ship_of'] = _so
            ctx['_hull_of'] = _ho
            for _si, (_sh, _hull, _ms) in enumerate(fleet):
                for _i, _m in enumerate(_ms):
                    want, rng = policy(_m, ctx)
                    _m._want = want
                    _m.range = _m._base_range if rng is None else rng
        # ORACLE HOOK. `assign` bypasses the range-gate actuator entirely and hands
        # each mount a target directly, with full knowledge of torpedo state and of
        # every round in flight. It is CHEATING BY CONSTRUCTION and exists only to
        # measure the ceiling: how much the real API constraints (no target identity,
        # no enemy positions, range-gate-only actuation) actually cost us.
        forced = assign(fleet, alive, in_flight, t) if assign is not None else None
        assign_tick = {}                # target id -> mounts engaging it this tick
        for si, (sh, hull, mounts) in enumerate(fleet):
            if not engage_all and si != 0:
                continue                      # only the targeted hull defends
            for m in mounts:
                if forced is not None:
                    best = forced.get(id(m))
                    if best is not None and not best.alive:
                        best = None
                    bd = (best.pos - sh.pos).length() if best is not None else None
                    m.aim_dir_local = (targeting.bearing_local(m, best, sh)
                                       if best is not None else None)
                else:
                    best, bd = select(m, alive, sh, hull, perfect=perfect)
                # Real slew: pass the bearing so acquire() runs the RotateRate/
                # ElevateRate traverse and the AimingTolerance gate
                # (MathFuncs.cs:218-222, WeaponTracking.cs:433) instead of the derived
                # dead-time fallback. The invented RETARGET_S = 0.35 s that used to
                # stand in here is gone, and the acquisition cadence it double-counted
                # against lives in targeting.MODEL_ACQUIRE_CADENCE.
                on_t = (m.acquire(best, dir_local=getattr(m, 'aim_dir_local', None))
                        if best is not None else False)
                if not getattr(m, '_want', True):
                    off_ticks_count += 1
                    on_t = False        # ToggleWeaponFire: still cools, just no shots
                shots = m.step(DT, on_t)
                total_shots += shots
                if shots > 0:
                    engaged_ticks += 1
                    if best is not None:
                        engagers.setdefault(id(best), set()).add(id(m))
                        assign_tick[id(best)] = assign_tick.get(id(best), 0) + 1
                        if assign_tick[id(best)] > 1:
                            dup_shots += shots
                            dup_tick_assignments += 1
                # Fractional rate -> whole rounds. A PDC at 30 sh/s fires 0.5 rounds
                # per tick, so the remainder has to carry rather than be rounded, or
                # the throughput is wrong by up to a factor of two.
                m._acc = getattr(m, '_acc', 0.0) + shots
                while m._acc >= 1.0:
                    m._acc -= 1.0
                    if best is None:
                        break
                    r = fire(m, best, sh, rnd)
                    if r is not None:
                        in_flight.append(r)
                        fired_rounds += 1

        # torpedoes move first so their last_pos/pos bracket this same tick
        for x in alive:
            if x.step() <= detonate_at:
                x.alive = False; leakers += 1

        # then rounds move and resolve against the one target each was fired at
        survivors = []
        for r in in_flight:
            r.advance()
            out = r.resolve()
            if out is None:
                survivors.append(r)
            elif out == HIT:
                tgt = r.target
                need = max(1e-9, tgt.health)
                hits += 1
                useful_hits += 1
                if r.hhm > need:
                    overkill_hits += (r.hhm - need) / r.hhm
                tgt.health -= r.hhm
                if tgt.health <= 0:
                    tgt.alive = False; kills += 1
            elif out == WASTED:
                wasted_rounds += 1
            else:
                missed_rounds += 1
        in_flight = survivors
        t += DT
    return (leakers, kills, engaged_ticks, ticks,
            dict(fired=fired_rounds, wasted=wasted_rounds, missed=missed_rounds,
                 inflight=len(in_flight), dup=dup_shots, total=total_shots,
                 hits=hits, useful=useful_hits,
                 overkill=overkill_hits, dup_assign=dup_tick_assignments,
                 off_ticks=off_ticks_count,
                 engaged=len(engagers),
                 multi_engaged=sum(1 for v in engagers.values() if len(v) > 1),
                 engager_mounts=sum(len(v) for v in engagers.values())))


def run(n_ships=1, mounts_per=8, kind='PdcMcrn', salvo=16, waves=3,
        torp_kind='Plasma220mmTorp', spacing=500.0, seed=1, engage_all=True,
        cls='Corvette', perfect=False, wave_gap=0.0, launcher_speed=0.0,
        policy=None, assign=None, launch_delays=None):
    """One scenario. FULLY DETERMINISTIC in (every argument) and nothing else.

    The three resets below are load-bearing, not hygiene. Each of these counters was a
    process-global that nothing cleared, so repeat N of a scenario saw different RNG
    streams from repeat 1 and separate processes disagreed outright:
      * weapons.reset_part_ids()  -> mount UniquePartId, hence every mount's shot RNG
                                     AND (via targeting._state) its acquisition deck
                                     and cadence phase
      * Torpedo2.reset_ids()      -> only a fallback now that index= is passed, but
                                     reset anyway so a stray construction cannot leak
      * weapons.Torpedo.reset_ids() -> same, for the legacy torpedo defense_sim uses
    test_determinism.py is the regression guard.
    """
    weapons.reset_part_ids()
    Torpedo2.reset_ids()
    weapons.Torpedo.reset_ids()
    rnd = random.Random(seed)
    fleet = []
    for s in range(n_ships):
        hull, man, mounts = build_ship(cls, pdc_mix={PDC_ALIAS[kind]: mounts_per},
                                       n_rcs=200, seed=seed + s)
        # class speed is a MODIFIER of the world cap (SpeedEnforcement.cs:541), and the
        # cap is a server setting -- both come from the catalogue, neither is a literal.
        sh = Ship(hull, V(0, s * spacing, 0), V(0, 0, 0), class_speed_mps(cls),
                  drive_thrust=292e6 * 2)
        for m in mounts:
            m.reset()
        fleet.append((sh, hull, mounts))

    total_mounts = sum(len(f[2]) for f in fleet)
    tot_leak = tot_kill = tot_eng = tot_ticks = 0
    waste = {}
    per_wave = []
    for w in range(waves):
        lk, kl, eng, tk, wst = wave(fleet, salvo, torp_kind, rnd, spacing, policy=policy,
                                    assign=assign, launch_delays=launch_delays,
                               engage_all=engage_all, perfect=perfect,
                               launcher_speed=launcher_speed)
        if wave_gap:                       # let mounts cool/reload between waves
            for f in fleet:
                for m in f[2]:
                    for _ in range(int(wave_gap * 60)):
                        m.step(DT, False)
        tot_leak += lk; tot_kill += kl; tot_eng += eng; tot_ticks += tk
        for k in ('fired', 'wasted', 'missed', 'inflight', 'dup', 'total',
                  'hits', 'useful', 'overkill', 'off_ticks',
                  'dup_assign', 'engaged', 'multi_engaged', 'engager_mounts'):
            waste[k] = waste.get(k, 0.0) + wst[k]
        hot = max((m.heat / m.max_heat for f in fleet for m in f[2]), default=0)
        per_wave.append((lk, kl, hot))
    cap = 100.0 * tot_eng / max(1, total_mounts * tot_ticks)
    W = waste.get
    rounds = W('fired', 0)
    # Denominator is rounds ACTUALLY SPAWNED, not the fractional rate integral.
    # Every spawned round ends as exactly one of: useful hit | wasted (target died
    # mid-flight) | missed (lived out its range) | still airborne at cutoff.
    fired = max(1, W('fired', 0))
    waste_pct = 100.0 * (W('wasted', 0) + W('missed', 0)) / fired
    n_eng = max(1, W('engaged', 0))
    reloads = sum(1 for f in fleet for m in f[2] if m.reloading > 0)
    return dict(rounds=rounds, reloading=reloads,
                waste_pct=waste_pct,
                fired_rounds=W('fired', 0),
                miss_pct=100.0 * W('missed', 0) / fired,
                dead_pct=100.0 * W('wasted', 0) / fired,
                overkill_pct=100.0 * W('overkill', 0.0) / fired,
                useful_pct=100.0 * W('useful', 0.0) / fired,
                hit_rate=100.0 * W('hits', 0.0) / fired,
                overkill_hits=W('overkill', 0.0),
                # fleet redundancy: how many mounts ever shot at the same torpedo
                multi_engaged_pct=100.0 * W('multi_engaged', 0) / n_eng,
                mounts_per_target=W('engager_mounts', 0) / n_eng,
                ceasefire_pct=100.0 * W('off_ticks', 0)
                              / max(1, total_mounts * tot_ticks),
                rounds_per_kill=(W('fired', 0) / tot_kill if tot_kill else float('nan')),
                leakers=tot_leak, kills=tot_kill, capacity_pct=cap,
                mounts=total_mounts, per_wave=per_wave,
                peak_heat=max(p[2] for p in per_wave) * 100)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=" * 118)
    print("SANITY CHECK — single hull, corrected torpedoes (1040 m/s, ~3 s exposure)".center(118))
    print("=" * 118)
    print(f"  {'salvo':>6}{'leakers':>10}{'kills':>8}{'capacity used':>16}{'peak heat':>12}")
    print("  " + "-" * 60)
    for salvo in (4, 8, 16, 24, 32):
        rs = [run(1, 8, salvo=salvo, waves=1, seed=s) for s in (11, 22, 33)]
        n = len(rs)
        print(f"  {salvo:>6}{sum(r['leakers'] for r in rs)/n:>10.1f}"
              f"{sum(r['kills'] for r in rs)/n:>8.1f}"
              f"{sum(r['capacity_pct'] for r in rs)/n:>15.1f}%"
              f"{sum(r['peak_heat'] for r in rs)/n:>11.1f}%")
    print("\n  compare: the OLD 260 m/s model had 8x PdcMcrn leaking 0 at salvo 16")

    print()
    print("=" * 118)
    print("FLEET EFFICIENCY — 3 waves of 16, does the net conserve capacity?".center(118))
    print("=" * 118)
    print(f"  {'fleet':<28}{'leakers':>9}{'kills':>7}{'capacity used':>16}"
          f"{'peak heat':>11}{'leak/ship':>11}")
    print("  " + "-" * 84)
    for n_ships, engage_all, label in [
            (1, True,  '1 ship'),
            (2, False, '2 ships, only target fires'),
            (2, True,  '2 ships, net engages'),
            (3, False, '3 ships, only target fires'),
            (3, True,  '3 ships, net engages')]:
        rs = [run(n_ships, 8, salvo=16, waves=3, seed=s, engage_all=engage_all)
              for s in (11, 22)]
        n = len(rs)
        lk = sum(r['leakers'] for r in rs) / n
        print(f"  {label:<28}{lk:>9.1f}{sum(r['kills'] for r in rs)/n:>7.1f}"
              f"{sum(r['capacity_pct'] for r in rs)/n:>15.1f}%"
              f"{sum(r['peak_heat'] for r in rs)/n:>10.1f}%{lk/n_ships:>11.2f}")
    print("\n  capacity used = mount-seconds engaged / mount-seconds available")
    print("  leak/ship     = leakers normalised by hulls committed")
