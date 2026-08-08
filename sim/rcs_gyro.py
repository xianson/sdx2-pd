"""Line-faithful port of the RCS Gyros mod torque model.

Source: 3580535545/Data/Scripts/RCSGyros/RCSController.cs

  L121 UpdateMoments():
        for each working RCS thruster:
            direction = thruster.Orientation.Forward
            offset    = thruster.Position - centerOfMassLocal      (BLOCK units)
            moment    = per-axis lever decomposition by facing (L138-164)
            moment   *= GridScale * MaxThrust                      (L167)
            _momentBias += moment
            _totalMoment += Abs(moment)                            (L172)

  L178 UpdateGyros():
        power = _totalMoment.Length() / 2 / _workingGyros          (L181)
        gyro.GyroStrengthMultiplier = power / 3.36e7               (L184)

  L83  if no RCS thrusters at all -> GyroStrengthMultiplier = 0
  L364 only subtype 'sdg_rcsGyroComputer' is collected into _gyros

Note the total applied torque is `_totalMoment.Length()/2` REGARDLESS of computer
count — extra computers divide the same figure, so they add nothing but redundancy.
Note also UpdateMoments uses MaxThrust and only checks IsWorking, never
CurrentStrength: thrusters translating still pay full value into rotation.
"""
import math
from vec import V

BASE_GYRO_FORCE = 3.36e7
GRID_SCALE_LARGE = 2.5
RCS_THRUST = 1.5e6
RCS_MASS = 1420.0

FWD, BACK, LEFT, RIGHT, UP, DOWN = 'Forward', 'Backward', 'Left', 'Right', 'Up', 'Down'


def moment_for(direction, offset):
    """L138-164 verbatim. offset is in BLOCK units relative to CoM."""
    m = [0.0, 0.0, 0.0]        # x, y, z
    ox, oy, oz = offset
    if direction == FWD:
        m[0] = oy
        m[1] = -ox
    elif direction == BACK:
        m[0] = -oy
        m[1] = ox
    elif direction == LEFT:
        m[2] = -oy
        m[1] = oz
    elif direction == RIGHT:
        m[2] = oy
        m[1] = -oz
    elif direction == DOWN:
        m[2] = ox
        m[0] = -oz
    elif direction == UP:
        m[2] = -ox
        m[0] = oz
    return m


def total_moment(thrusters, grid_scale=GRID_SCALE_LARGE, thrust=RCS_THRUST):
    """thrusters: list of (direction, (ox,oy,oz)) in block units. Returns (V total, V bias)."""
    tot = [0.0, 0.0, 0.0]
    bias = [0.0, 0.0, 0.0]
    for direction, offset in thrusters:
        m = moment_for(direction, offset)
        m = [c * grid_scale * thrust for c in m]
        for i in range(3):
            bias[i] += m[i]
            tot[i] += abs(m[i])
    return V(*tot), V(*bias)


def applied_torque(thrusters, n_computers=1, **kw):
    """L181 — the torque the grid actually gets, independent of computer count."""
    if not thrusters or n_computers < 1:
        return 0.0
    tot, _ = total_moment(thrusters, **kw)
    return tot.length() / 2.0


def gyro_multiplier(thrusters, n_computers=1, **kw):
    """L184 — what each computer's GyroStrengthMultiplier is set to."""
    if not thrusters:
        return 0.0
    return applied_torque(thrusters, n_computers, **kw) / n_computers / BASE_GYRO_FORCE


# ------------------------------------------------------------------ hull layout
def ring_layout(n_per_ring, lever_blocks, rings=('fore', 'aft')):
    """Lateral-facing RCS in rings fore and aft of the CoM.

    SE grid axes: +X right, +Y up, +Z backward (forward = -Z). So the fore/aft
    lever arm is along Z, NOT X. Checking moment_for():
      LEFT/RIGHT at (0,0,oz) -> moment.Y = +/-oz   (yaw)
      UP/DOWN    at (0,0,oz) -> moment.X = +/-oz   (pitch)
    A Left-facing thruster displaced along X produces NO moment, which is why the
    lever axis matters.
    """
    th = []
    for sign, name in ((+1, 'aft'), (-1, 'fore')):
        if name not in rings:
            continue
        for i in range(n_per_ring):
            oz = sign * lever_blocks
            d = (LEFT, RIGHT, UP, DOWN)[i % 4]
            th.append((d, (0.0, 0.0, oz)))
    return th


def inertia_box(mass_kg, length_m, beam_m):
    return mass_kg * (length_m ** 2 + beam_m ** 2) / 12.0


def alpha_deg(thrusters, mass_kg, length_m, beam_m, n_computers=1):
    tau = applied_torque(thrusters, n_computers)
    return math.degrees(tau / inertia_box(mass_kg, length_m, beam_m))
