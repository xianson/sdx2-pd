"""Physics-driven duel: two 6-DOF ships, real armour facing, ported WeaponCore.

What is actually simulated per 1/60 s tick:
  * both ships as rigid bodies with mass/inertia from their real block layout
  * shooter slews its FIXED railgun by rotating the hull (bang-bang min-time law)
  * fires only when the boresight is inside AimingTolerance = 1.0 deg AND reloaded
  * aim solution from the ported CalculateAdvancedGridAimPrediction, fed the
    one-tick finite-difference acceleration the engine would report
  * shot flies at muzzle speed; on arrival the impact ray is transformed into the
    target's hull frame and DDA-marched through real blocks (oblique = more armour)
  * damage resolved by the ported DamageGrid pool/cutoff logic
"""
import math, sys, io, random
from vec import V
from ship import Ship, DT
from hull2 import Hull, GRID
from shipyard import build_ship
from wc_damage import fire, sdx_ammo
from wc_predict import trajectory_estimation
from weapons import deviated_dir
from components import class_speed

AIM_TOLERANCE_DEG = 1.0
MUZZLE = 10000.0
#: LargeShipMaxSpeed, i.e. the world cap SCF writes into the environment definition.
#: A per-CLASS cap is that number times the core's <MaxSpeed> modifier; use
#: components.class_speed(cls) for a hull, not this.
from components import WORLD_SPEED as MAX_SPEED


class Railgun:
    def __init__(self, ammo_name, reload_s, dev_deg):
        self.ammo = sdx_ammo()[ammo_name]
        self.name = ammo_name
        self.reload_s = reload_s
        self.dev = math.radians(dev_deg)
        self.cool = 0.0

    def ready(self):
        return self.cool <= 0.0

    def tick(self):
        if self.cool > 0:
            self.cool -= DT

    def discharge(self):
        self.cool = self.reload_s


def pick_aimpoint(target: Ship, rnd):
    """WeaponCore aims at a random block from a reshuffled deck, walking SubSystems in
    priority order (Power -> Utility -> Offense -> Thrust -> Production -> Any).

    This now defers to hull2.pick_target_block, the port of AiTargeting.cs L1263-1279.
    hull.py had no subsystem tags, so the old version drew from generic internals and
    only fell back to "anything" — i.e. it never modelled the priority walk at all.
    Returns (component, world position of its centre)."""
    c = target.hull.pick_target_block(rnd)
    if c is None:
        return None, None
    p = c.centre()
    return c, target.to_world(V(p[0] * GRID, p[1] * GRID, p[2] * GRID))


def resolve_hit(shooter: Ship, target: Ship, impact_world, direction_world, ammo):
    """Transform the shot into hull space and march it through real blocks."""
    # entry point: back the impact up outside the hull along -direction
    span = max(target.hull.dims) * 1.5
    origin_world = impact_world - direction_world * span
    o = target.to_local(origin_world)
    d = target.dir_to_local(direction_world)
    column = target.hull.march(o, d)         # deduped: one entry per component
    if not column:
        return None
    r = fire(ammo, column)
    target.hull.mark_dirty()                 # blocks died: capability must be recomputed
    return r


def duel(range_m=10000, chatter_amp=0.0, chatter_period=0.5, cross_speed=200.0,
         fire_discipline_deg=0.03,
         duration=120.0, ceramic=40, seed=1, shooter_ammo='sabot100mmMcrn',
         airburst_first=False, max_speed=None, cls='Corvette', verbose=False):
    import weapons
    weapons.reset_part_ids()
    rnd = random.Random(seed)
    # max_speed is LargeShipMaxSpeed as the PREDICTOR sees it (it clamps the propagated
    # target speed there, WeaponTracking.cs:1266-1277). The hull's own cap is the
    # class modifier times the world cap, which is lower; the predictor uses the world
    # figure because that is what MyEnvironmentDefinition carries.
    if max_speed is None:
        max_speed = MAX_SPEED
    hull_speed = class_speed(cls)[0]

    # 20 RCS on a 14-block lever reproduces hull.py's add_rcs_rings(10, nz//2-1),
    # except the thrusters are now real blocks in the lattice rather than a side list.
    sh_hull, _, _ = build_ship(cls, ceramic=ceramic, n_rcs=20, rcs_lever=14,
                               seed=seed, name='shooter', with_mounts=False)
    tg_hull, _, _ = build_ship(cls, ceramic=ceramic, n_rcs=20, rcs_lever=14,
                               seed=seed + 7, name='target', with_mounts=False)

    shooter = Ship(sh_hull, V(0, 0, 0), V(0, 0, 0), hull_speed,
                   drive_thrust=292e6 * 2, name='shooter')
    target = Ship(tg_hull, V(range_m, 0, 0), V(0, 0, cross_speed), hull_speed,
                  drive_thrust=292e6 * 2, name='target')

    gun = Railgun(shooter_ammo, reload_s=7.0, dev_deg=0.0)
    ab = sdx_ammo()['airburstFragment']

    t = 0.0
    shots = hits = 0
    misses = []
    internals_killed = 0
    ceramic_killed = 0
    fired_airburst = 0

    while t < duration:
        target.apply_chatter(t, chatter_amp, chatter_period)
        aim_cell, aim_block = pick_aimpoint(target, rnd)
        if aim_block is None:
            break

        pred, tti, algo = trajectory_estimation(
            target_pos=aim_block, target_vel=target.vel,
            target_accel=target.measured_accel, target_angular_vel=target.omega,
            target_com=target.pos, shooter_pos=shooter.pos, shooter_vel=shooter.vel,
            muzzle_speed=MUZZLE, max_speed=max_speed, prediction_level=3)

        off = shooter.point_at(pred) if not math.isinf(tti) else 180.0

        gun.tick()
        # WeaponCore ALLOWS firing anywhere inside AimingTolerance, but 1.0 deg is
        # 175 m of error at 10 km. A competent pilot/autopilot waits for the boresight
        # to settle; `fire_discipline_deg` is that settling threshold.
        settled = off <= fire_discipline_deg and shooter.omega.length() < 0.02
        if gun.ready() and settled and not math.isinf(tti):
            # Fire along the boresight, deviation applied about it by the ONE shared
            # port of WeaponShoot.cs:198-217.
            #
            # This used to be a second, local implementation:
            #     ang = gun.dev * math.sqrt(rnd.random())
            # which samples a uniform DISC. The source has no sqrt -- randomFloat1 is
            # the polar angle and is uniform on [-dev, +dev] (:214) -- so the local
            # copy was biased AWAY from the boresight, the exact opposite error to the
            # one AUDIT_WEAPONS fixed in weapons.py. Two files, one line of C#, two
            # different wrong answers; hence the shared helper.
            aim_dir = deviated_dir(rnd, gun.dev, shooter.fwd,
                                   shooter.right, shooter.up)

            flight = tti
            impact_point = shooter.pos + aim_dir * (MUZZLE * flight)

            # advance the world by the flight time
            steps = max(1, int(round(flight / DT)))
            for _ in range(steps):
                target.apply_chatter(t, chatter_amp, chatter_period)
                target.step()
                shooter.step()
                t += DT

            shots += 1
            # miss measured against where the TARGETED BLOCK actually ended up
            ac = aim_cell.centre()
            true_block = target.to_world(V(ac[0] * GRID, ac[1] * GRID, ac[2] * GRID))
            misses.append((impact_point - true_block).length())

            # no artificial radius test: march the ray and see whether it finds blocks
            ammo = ab if (airburst_first and fired_airburst < 1) else gun.ammo
            if ammo is ab:
                fired_airburst += 1
            r = resolve_hit(shooter, target, impact_point, aim_dir, ammo)
            if r and r['touched'] > 0:
                hits += 1
                ceramic_killed = target.hull.dead_count('sdx_armorCeramic')
                internals_killed = target.hull.dead_count('Generic')
            gun.discharge()
            continue

        target.step()
        shooter.step()
        t += DT

    return dict(shots=shots, hits=hits, miss_mean=(sum(misses) / len(misses)) if misses else 0.0,
                ceramic_killed=ceramic_killed, internals_killed=internals_killed,
                integrity=target.hull.integrity_frac(), algo=algo,
                alpha=math.degrees(shooter.alpha_max), mass=shooter.mass)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=" * 120)
    print("PHYSICS-DRIVEN DUEL — fixed railgun vs a chattering target".center(120))
    print("=" * 120)
    probe = duel(duration=1.0)
    print(f"  shooter hull: {probe['mass']/1e6:.2f} kt, alpha_max {probe['alpha']:.1f} deg/s^2")
    print(f"  fixed railgun, AimingTolerance {AIM_TOLERANCE_DEG} deg, 7 s reload, "
          f"muzzle {MUZZLE/1000:.0f} km/s\n")
    print(f"{'range':>7}{'chatter':>10}{'shots':>7}{'hits':>6}{'hit%':>7}"
          f"{'mean miss':>11}{'ceramic lost':>14}{'internals lost':>16}{'target integ':>14}")
    print("-" * 120)
    for R in (10000, 6000, 3000):
        for amp in (0, 30, 60, 120):
            r = duel(range_m=R, chatter_amp=amp, duration=90.0)
            hp = 100.0 * r['hits'] / r['shots'] if r['shots'] else 0.0
            print(f"{R:>7}{amp:>9}{'':>1}{r['shots']:>7}{r['hits']:>6}{hp:>6.0f}%"
                  f"{r['miss_mean']:>10.1f}m{r['ceramic_killed']:>14}"
                  f"{r['internals_killed']:>16}{r['integrity']*100:>13.1f}%")
