"""Hi-fi chatter experiment: does lateral chatter actually defeat SDX2 railguns?

Fidelity notes:
  * target integrated at the engine's 60 Hz with the LargeShipMaxSpeed clamp
  * the accel the shooter reads is MyPhysicsBody.LinearAcceleration, which in SE is a
    ONE-TICK finite difference  (v - v_prev) * 60  — so it is instantaneous and noisy,
    exactly what a square-wave chatter poisons
  * aim solution comes from the ported CalculateAdvancedGridAimPrediction
  * the shot flies straight from the muzzle to the returned intercept point at
    muzzle speed

MISS IS MEASURED PERPENDICULAR TO THE LINE OF FIRE, not as a raw distance.

`one_shot` used to return `|target_pos_at_impact - aimpoint|`, which counts ALONG-TRACK
error as a miss. It is not one. A sabot is not a proximity-fused round: it flies along
its line and continues past the aimpoint, so if the target is displaced up or down that
same line the round still passes through it -- it just arrives a little early or late
relative to the nominal intercept. Only the component of the displacement PERPENDICULAR
to the line of fire can cause the round to pass by.

For the perpendicular-crossing geometry used in the tables below (target crossing in
+z, shot fired along +x) the two definitions nearly coincide, which is why this went
unnoticed; the along-track term is a second-order O(miss^2/R) contamination. In any
geometry with a radial component -- a closing or receding target, a stern chase, a
tail-on pursuit -- the old form silently overstates the miss, and it does so worst
exactly where the closing speed is highest. `WORLD_SPEED` and the sabot muzzle speed
are now sourced rather than hardcoded.
"""
import math, sys, io
from vec import V
from wc_predict import trajectory_estimation, DT
from components import WORLD_SPEED

#: sabot DesiredSpeed, SDX RailAmmo/sdx_ammo_sabot*.cs:100
SABOT_MUZZLE = 10000.0


class Target:
    """A grid flying a lateral-accel programme, stepped like SE physics."""

    def __init__(self, pos, vel, max_speed):
        self.pos = pos.copy()
        self.vel = vel.copy()
        self.prev_vel = vel.copy()
        self.max_speed = max_speed

    def step(self, accel):
        self.prev_vel = self.vel.copy()
        self.vel = self.vel + accel * DT
        if self.vel.length_sq() > self.max_speed ** 2:
            self.vel = self.vel.normalized() * self.max_speed
        self.pos = self.pos + self.vel * DT

    @property
    def measured_accel(self):
        """What MyPhysicsBody.LinearAcceleration reports: one-tick difference."""
        return (self.vel - self.prev_vel) * 60.0


def programme(kind, amp, period):
    if kind == 'none':
        return lambda t: V(0, 0, 0)
    if kind == 'constant':
        return lambda t: V(0, amp, 0)
    if kind == 'square':
        return lambda t: V(0, amp if (t % period) < period / 2 else -amp, 0)
    if kind == 'sine':
        return lambda t: V(0, amp * math.sin(2 * math.pi * t / period), 0)
    if kind == 'circle':
        return lambda t: V(0, amp * math.cos(2 * math.pi * t / period),
                           amp * math.sin(2 * math.pi * t / period))
    raise ValueError(kind)


def one_shot(R, kind, amp, period, fire_at, cruise=200.0, muzzle=SABOT_MUZZLE,
             max_speed=WORLD_SPEED, warmup=3.0, total_error=False, closing=0.0):
    """Fire one round at time `fire_at`; return (cross_track_miss, algorithm).

    The returned miss is the component of (true position - aimpoint) PERPENDICULAR to
    the line of fire, which is the only component that can make the round pass by.
    Set `total_error=True` for the old raw-distance figure, which is a diagnostic (it
    tells you how far off the intercept was in all axes) and not a miss.
    """
    shooter_pos, shooter_vel = V(0, 0, 0), V(0, 0, 0)
    # crossing in +z; `closing` adds a RADIAL component (-x = closing on the shooter).
    # Radial motion is what separates the two miss definitions: it is along the line of
    # fire, so it is entirely absent from a real miss and entirely present in a raw
    # distance. With the world cap at 1000 m/s a Picket closes at 650, so this is the
    # normal case, not a corner.
    tgt = Target(V(R, 0, 0), V(-closing, 0, cruise), max_speed)
    fn = programme(kind, amp, period)

    t = 0.0
    while t < warmup + fire_at - 1e-9:
        tgt.step(fn(t))
        t += DT

    aim_pos = tgt.pos.copy()           # aimpoint = CoM (offset zero, isolates the effect)
    aim, tti, algo = trajectory_estimation(
        target_pos=aim_pos, target_vel=tgt.vel, target_accel=tgt.measured_accel,
        target_angular_vel=V(0, 0, 0), target_com=tgt.pos,
        shooter_pos=shooter_pos, shooter_vel=shooter_vel,
        muzzle_speed=muzzle, max_speed=max_speed, prediction_level=3)
    if math.isinf(tti):
        return None, algo

    steps = int(round(tti / DT))
    for i in range(steps):
        tgt.step(fn(t))
        t += DT

    err = tgt.pos - aim
    if total_error:
        return err.length(), algo
    # line of fire = muzzle -> aimpoint. Project the error onto it and discard that
    # component; what is left is the only part that can make the round miss.
    los = aim - shooter_pos
    n = los.length()
    if n < 1e-9:
        return err.length(), algo
    los = los / n
    return (err - los * err.dot(los)).length(), algo


def sweep(R, kind, amp, period, samples=40, **kw):
    misses, algo = [], None
    for i in range(samples):
        m, a = one_shot(R, kind, amp, period, fire_at=period * i / samples, **kw)
        algo = a
        if m is not None:
            misses.append(m)
    return (sum(misses) / len(misses) if misses else float('nan')), algo


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    TGT_R = 15.0
    print("=" * 118)
    print("HI-FI: ported CalculateAdvancedGridAimPrediction vs chatter".center(118))
    print("=" * 118)
    print(f"  target crossing at 200 m/s, muzzle {SABOT_MUZZLE/1000:g} km/s, "
          f"LargeShipMaxSpeed {WORLD_SPEED:g}, hull radius {TGT_R:g} m")
    print("  miss = CROSS-TRACK component only; means over 40 firing phases\n")
    RANGES = [10000, 8000, 6000, 4000, 2000]
    print(f"{'programme':<26}{'algo':<16}" + ''.join(f"{f'{r//1000}km':>17}" for r in RANGES))
    print(f"{'':<42}" + ''.join(f"{'miss    hit?':>17}" for _ in RANGES))
    print("-" * 118)
    CASES = [('none', 0, 1.0), ('constant 30', 30, 1.0), ('constant 100', 100, 1.0),
             ('square 30 @0.5s', 30, 0.5), ('square 60 @0.5s', 60, 0.5),
             ('square 100 @0.5s', 100, 0.5), ('square 100 @0.25s', 100, 0.25),
             ('square 200 @0.25s', 200, 0.25), ('sine 100 @0.5s', 100, 0.5),
             ('circle 100 @0.5s', 100, 0.5)]
    for label, amp, per in CASES:
        kind = label.split()[0]
        kind = 'none' if kind == 'none' else kind
        line = f"{label:<26}"
        algo_seen = ''
        cells = []
        for R in RANGES:
            m, algo = sweep(R, kind, amp, per)
            algo_seen = algo
            cells.append(f"{m:>11.1f}m{'HIT' if m <= TGT_R else 'miss':>6}")
        print(line + f"{algo_seen:<16}" + "".join(cells))
