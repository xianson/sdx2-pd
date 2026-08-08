"""Line-faithful port of WeaponCore 3.0 aim prediction.

Source: 3154371364/Data/Scripts/CoreSystems/EntityComp/Parts/Weapon/WeaponTracking.cs
  - TrajectoryPredictionShootingFrame.Calculate            (L671)
  - TrajectoryPredictionShootingFrame.CalculateCrudeTti    (L696)
  - TrajectoryPredictionTargetDescription.DecidePredictionAlgorithm (L836)
  - QuarticSolver                                          (L619)
  - TrajectoryEstimation                                   (L874)
  - CalculateAdvancedGridAimPrediction                     (L1115)
  - CalculateAdvancedPdAimPrediction                       (L1289)

Every branch and constant below is transcribed from that file. Where the C# uses
`Vector3D.Transform(v, QuaternionD.CreateFromAxisAngle(...))` we use Rodrigues,
which is mathematically identical.

WHAT ACTUALLY RUNS FOR SDX2 (audit 2026-08-07) -- read this before using the module:

  * `AmmoSkipAccel = AccelPerSec <= 0`  (AmmoConstants.cs:497).  Every SDX2 PDC
    round and every railgun sabot has `AccelPerSec = 0f`, so AmmoSkipAccel is
    TRUE for all of them.  Line 902 is `useSimple = AmmoSkipAccel || accelSqr <
    2.5`, therefore **useSimple is unconditionally true and the QuarticSolver
    fallback is dead code for every SDX2 kinetic weapon**.  It is still ported
    below, faithfully, because energy/accelerating ammo would reach it.

  * Same flag zeroes `projectileAccelTime`, so the `timePenalty` fudge at L974
    and L1014-1020 is always 0 for SDX2.  Ported anyway.

  * `allowAdvancedProjectileAlgorithm = Prediction > 1 && UseLimitlessPDSolver`
    (L944).  **No SDX2 weapon sets UseLimitlessPDSolver**, so the anti-twist PD
    solver never runs.  A PDC shooting a torpedo therefore falls all the way
    through to `TargetPos + crudeTti * Dv` -- a plain constant-velocity
    intercept with zero acceleration compensation.  `advanced_pd_prediction`
    below is provided for completeness but `trajectory_estimation` will not
    reach it unless you pass `use_limitless_pd_solver=True`.

  * The grid path is live: railguns and PDCs shooting grids do run
    CalculateAdvancedGridAimPrediction whenever the L859 gate passes.
"""
import math
from vec import V, rotate_axis_angle

DT = 1.0 / 60.0


# ------------------------------------------------------- shooting frame (L671)
class Frame:
    def __init__(self, target_pos, target_vel, shooter_pos, shooter_vel):
        self.TargetPos, self.TargetVel = target_pos, target_vel
        self.ShooterPos, self.ShooterVel = shooter_pos, shooter_vel
        self.Dr = target_pos - shooter_pos
        self.Dv = target_vel - shooter_vel
        self.Distance = self.Dr.length()
        self.Los = self.Dr / self.Distance

    def crude_tti(self, muzzle_speed):
        """L696. Returns (ok, tti)."""
        closing_speed = self.Dv.dot(self.Los)
        tti = muzzle_speed * muzzle_speed - (self.Dv - self.Los * closing_speed).length_sq()
        if tti <= 0.0:
            return False, math.inf
        closing_distance = self.Dr.dot(self.Los)
        tti = closing_distance / (math.sqrt(tti) - closing_speed)
        if tti <= 0.0:
            return False, math.inf
        return True, tti


# ------------------------------------------------ algorithm gate (L836)
def decide_algorithm(targ_accel_sqr, targ_vel_sqr, angular_vel_sqr,
                     allow_advanced_grid):
    """Grid branch of DecidePredictionAlgorithm (L852-866).

    Returns 'AdvancedGrid' or 'Crude'.  Note the real gate additionally requires
    `GridTarget?.Physics != null && !GridTarget.Closed` (L856-857), which has no
    analogue here.
    """
    attempt = (allow_advanced_grid and
               (angular_vel_sqr > 0.0003 or (targ_accel_sqr > 100 and targ_vel_sqr > 100)))
    return 'AdvancedGrid' if attempt else 'Crude'


def decide_algorithm_projectile(prev_vel1_sqr, prev_vel0_sqr, allow_advanced_pd):
    """Projectile branch of DecidePredictionAlgorithm (L840-851).

    `allow_advanced_pd` is `Prediction > 1 && UseLimitlessPDSolver` (L944) -- and
    no SDX2 weapon sets UseLimitlessPDSolver, so in practice this returns 'Crude'
    for every PDC-vs-torpedo engagement in this project.
    """
    attempt = (allow_advanced_pd and prev_vel1_sqr > 100.0 and prev_vel0_sqr > 100.0)
    return 'AdvancedProjectile' if attempt else 'Crude'


def accel_used_by_predictor(accel_vec, prediction_level):
    """AiTargeting.cs:1257 -- `targetAccel` is zeroed unless AimLeadingPrediction > 1.

    CORRECTION (audit): that line lives in `AcquireBlock`, i.e. it gates the
    ACQUISITION-time lead used to pick a subsystem block.  The firing solution in
    TargetAligned (WeaponTracking.cs:279) and TrackingTarget (:368) reads
    `topMostEnt.Physics.LinearAcceleration` raw, with NO prediction-level gate,
    and CalculateAdvancedGridAimPrediction re-reads `targetGrid.Physics.
    LinearAcceleration` for itself at L1138-1140.  So this function must NOT be
    applied to the firing solution; it is kept only for modelling acquisition.
    """
    return accel_vec if prediction_level > 1 else V(0, 0, 0)


# -------------------------------------- CalculateAdvancedGridAimPrediction (L1115)
def advanced_grid_prediction(target_com, target_offset_world, target_vel,
                             target_drive_accel_world, angular_vel,
                             weapon_pos, weapon_vel, crude_tti, muzzle_speed,
                             max_speed, apply_max_speed_after_step=True):
    """Returns (found, intercept_point, tti, point_vel). Faithful transcription.

    `point_vel` is L1233's `(currentX.Translation - previousX.Translation) / dt`,
    which the caller feeds into the intercept frame.
    """
    max_speed_sqr = max_speed * max_speed

    previous_target_offset_world = target_offset_world.copy()
    target_offset_world = target_offset_world.copy()
    target_drive_accel_world = target_drive_accel_world.copy()

    w_norm = angular_vel.length()
    rot_axis = angular_vel / w_norm if w_norm >= 1e-8 else V(0, 0, 1)
    rot_angle = w_norm * DT if w_norm >= 1e-8 else 0.0

    cur_pos, cur_vel = target_com.copy(), target_vel.copy()
    prev_pos = V(0, 0, 0)

    start = max(int(crude_tti * 60 * 0.8), 1)
    budget = max(int(crude_tti * 60 * 1.2), 5)

    for step in range(budget + 1):
        if step >= start:
            a = prev_pos + previous_target_offset_world
            t0 = step * DT - DT
            d = cur_pos + target_offset_world - a
            u = weapon_vel - d / DT
            w1 = weapon_pos - a + d * (t0 / DT)

            A = u.dot(u) - muzzle_speed * muzzle_speed
            B = 2.0 * u.dot(w1)
            C = w1.dot(w1)
            delta = B * B - 4.0 * A * C

            if delta < 0.0:
                has_root = False
            else:
                t1_frame = t0 + DT
                f0 = A * t0 * t0 + B * t0 + C
                f1 = A * t1_frame * t1_frame + B * t1_frame + C
                has_root = (f0 <= 0.0 and f1 >= 0.0) or (f0 >= 0.0 and f1 <= 0.0)
                if not has_root and A != 0.0:
                    t_vertex = -B / (2.0 * A)
                    if t0 < t_vertex < t1_frame:
                        f_vertex = -delta / (4.0 * A)
                        has_root = (f0 <= 0.0 and f_vertex >= 0.0) or (f0 >= 0.0 and f_vertex <= 0.0)

            if has_root:
                sd = math.sqrt(delta)
                t1 = (-B - sd) / (2.0 * A)
                t2 = (-B + sd) / (2.0 * A)
                t = math.inf
                if t0 < t1 <= t0 + DT:
                    t = min(t, t1)
                if t0 < t2 <= t0 + DT:
                    t = min(t, t2)
                if not math.isinf(t):
                    direction_estimate = -(u * t + w1) / (muzzle_speed * t)
                    intercept = weapon_pos + direction_estimate * (muzzle_speed * t)
                    return True, intercept, t, (cur_pos - prev_pos) / DT

        prev_pos = cur_pos.copy()
        previous_target_offset_world = target_offset_world.copy()

        v_dot = target_drive_accel_world

        if not apply_max_speed_after_step and cur_vel.length_sq() > max_speed_sqr:
            cur_vel = cur_vel.normalized() * max_speed
        cur_vel = cur_vel + v_dot * DT
        cur_pos = cur_pos + cur_vel * DT
        if apply_max_speed_after_step and cur_vel.length_sq() > max_speed_sqr:
            cur_vel = cur_vel.normalized() * max_speed

        target_offset_world = rotate_axis_angle(target_offset_world, rot_axis, rot_angle)
        target_drive_accel_world = rotate_axis_angle(target_drive_accel_world, rot_axis, rot_angle)

    return False, target_com + target_offset_world, math.inf, target_vel


# ---------------------------------------- CalculateAdvancedPdAimPrediction (L1289)
def advanced_pd_prediction(target_pos, target_vel, prev_vel1, prev_vel0,
                           weapon_pos, weapon_vel, crude_tti, muzzle_speed,
                           target_max_speed):
    """The anti-twist PD solver.  Returns (found, intercept, tti, point_vel).

    UNREACHABLE FOR SDX2: gated behind `UseLimitlessPDSolver`, which no SDX2
    weapon sets (L944).  Ported so the gap is visible rather than silent.

    Differences from the grid solver that matter: the accel is a TWO-frame
    finite difference (L1293-1294), the propagation ROTATES the accel vector by
    the measured twist quaternion every step (the target's own turn rate) rather
    than by the target's angular velocity, it bails when either accel sample is
    under 1 m/s^2 (L1299) or the twist is under 1e-6 rad (L1313), and the search
    starts at `step > start` rather than `step >= start` (L1338).
    """
    target_accel0 = (prev_vel1 - prev_vel0) / DT
    target_accel1 = (target_vel - prev_vel1) / DT

    n0, n1 = target_accel0.length(), target_accel1.length()
    if n0 < 1.0 or n1 < 1.0:
        return False, target_pos, math.inf, target_vel

    e0, e1 = target_accel0 / n0, target_accel1 / n1
    w = V(e0.y * e1.z - e0.z * e1.y, e0.z * e1.x - e0.x * e1.z, e0.x * e1.y - e0.y * e1.x)
    sin_theta = max(0.0, min(1.0, w.length()))
    if sin_theta < 1e-6:
        return False, target_pos, math.inf, target_vel
    w = w / sin_theta
    cos_theta = max(-1.0, min(1.0, e0.dot(e1)))
    twist = math.atan2(sin_theta, cos_theta)

    max_speed_sqr = target_max_speed * target_max_speed
    accel_world = target_accel1.copy()
    cur_pos, cur_vel = target_pos.copy(), target_vel.copy()
    prev_pos = V(0, 0, 0)

    start = max(int(crude_tti * 60 * 0.8), 1)
    budget = max(int(crude_tti * 60 * 1.2), 5)

    for step in range(budget + 1):
        if step > start:                          # L1338: strict, unlike the grid solver
            a = prev_pos
            t0 = step * DT - DT
            d = cur_pos - a
            u = weapon_vel - d / DT
            w1 = weapon_pos - a + d * (t0 / DT)
            A = u.dot(u) - muzzle_speed * muzzle_speed
            B = 2.0 * u.dot(w1)
            C = w1.dot(w1)
            delta = B * B - 4.0 * A * C
            if delta >= 0.0:
                t1_frame = t0 + DT
                f0 = A * t0 * t0 + B * t0 + C
                f1 = A * t1_frame * t1_frame + B * t1_frame + C
                has_root = (f0 <= 0.0 and f1 >= 0.0) or (f0 >= 0.0 and f1 <= 0.0)
                if not has_root and A != 0.0:
                    tv = -B / (2.0 * A)
                    if t0 < tv < t1_frame:
                        fv = -delta / (4.0 * A)
                        has_root = (f0 <= 0.0 and fv >= 0.0) or (f0 >= 0.0 and fv <= 0.0)
                if has_root:
                    sd = math.sqrt(delta)
                    t1 = (-B - sd) / (2.0 * A)
                    t2 = (-B + sd) / (2.0 * A)
                    t = math.inf
                    if t0 < t1 <= t0 + DT:
                        t = min(t, t1)
                    if t0 < t2 <= t0 + DT:
                        t = min(t, t2)
                    if not math.isinf(t):
                        de = -(u * t + w1) / (muzzle_speed * t)
                        return (True, weapon_pos + de * (muzzle_speed * t), t,
                                (cur_pos - prev_pos) / DT)

        prev_pos = cur_pos.copy()
        cur_vel = cur_vel + accel_world * DT
        cur_pos = cur_pos + cur_vel * DT
        if cur_vel.length_sq() > max_speed_sqr:
            cur_vel = cur_vel.normalized() * target_max_speed
        accel_world = rotate_axis_angle(accel_world, w, twist)

    return False, target_pos, math.inf, target_vel


# ------------------------------------------------------ TrajectoryEstimation (L874)
def trajectory_estimation(target_pos, target_vel, target_accel, target_angular_vel,
                          target_com, shooter_pos, shooter_vel, muzzle_speed,
                          max_speed, prediction_level=3,
                          ammo_skip_accel=True, projectile_accel=0.0,
                          use_limitless_pd_solver=False,
                          target_is_projectile=False,
                          prev_vel1=None, prev_vel0=None,
                          target_max_speed=None):
    """Top-level entry. Returns (aimpoint, tti, algorithm_used).

    `ammo_skip_accel` defaults TRUE because every SDX2 kinetic round has
    AccelPerSec = 0 (AmmoConstants.cs:497).  With it true, `useSimple` is
    unconditionally true (L902) and the quartic branch is unreachable -- which
    is the real in-game behaviour, not a shortcut.
    """
    targ_accel_sqr = target_accel.length_sq()
    targ_vel_sqr = target_vel.length_sq()
    use_simple = ammo_skip_accel or targ_accel_sqr < 2.5          # L902

    frame0 = Frame(target_pos, target_vel, shooter_pos, shooter_vel)
    ok, crude_tti = frame0.crude_tti(muzzle_speed)
    if not ok:
        return target_pos, math.inf, 'None'

    if target_is_projectile:
        algo = decide_algorithm_projectile(
            prev_vel1.length_sq() if prev_vel1 is not None else 0.0,
            prev_vel0.length_sq() if prev_vel0 is not None else 0.0,
            prediction_level > 1 and use_limitless_pd_solver)
    else:
        algo = decide_algorithm(targ_accel_sqr, targ_vel_sqr,
                                target_angular_vel.length_sq(), prediction_level > 1)

    found, intercept, tti, point_vel = False, target_pos, math.inf, target_vel
    if algo == 'AdvancedGrid':
        found, intercept, tti, point_vel = advanced_grid_prediction(
            target_com, target_pos - target_com, target_vel, target_accel,
            target_angular_vel, shooter_pos, shooter_vel, crude_tti,
            muzzle_speed, max_speed)
    elif algo == 'AdvancedProjectile':
        found, intercept, tti, point_vel = advanced_pd_prediction(
            target_pos, target_vel, prev_vel1, prev_vel0, shooter_pos,
            shooter_vel, crude_tti, muzzle_speed,
            target_max_speed if target_max_speed is not None else max_speed)

    if found:
        # L972-982: accelerating-projectile fudge. Dead when ammo_skip_accel.
        if not ammo_skip_accel and tti > 0.0 and projectile_accel > 0.0:
            time_penalty = (muzzle_speed / projectile_accel) / tti
            tti += time_penalty
            intercept = intercept + (point_vel - shooter_vel) * time_penalty
        return intercept, tti, algo

    # Fallback (L991-1028): crude tti, then simple-linear or quartic.
    tti = crude_tti
    if use_simple:
        # L996 -- this is the branch every SDX2 kinetic weapon actually takes.
        return frame0.TargetPos + frame0.Dv * tti, tti, 'Crude/simple-linear'

    # L1005-1022. NOTE: the quartic only refines the TIME. The aim point is a
    # pure LINEAR extrapolation on Dv -- there is no 0.5*a*t^2 term in the real
    # code. The port used to add one; that was wrong.
    adv_tti = tti
    converged, adv_tti = quartic_solver(adv_tti, frame0.Dr, frame0.Dv,
                                        target_accel, muzzle_speed)
    final_tti = adv_tti if converged else tti
    projectile_accel_time = 0.0 if ammo_skip_accel or projectile_accel <= 0 \
        else muzzle_speed / projectile_accel
    time_penalty = projectile_accel_time / final_tti if projectile_accel_time > 0 else 0.0
    return (frame0.TargetPos + frame0.Dv * (final_tti + time_penalty),
            final_tti, 'Crude/quartic')


def quartic_solver(t0, dr, dv, accel, muzzle_speed, tolerance=1e-3, max_iterations=10):
    """WeaponTracking.cs:619. Newton on the quartic

        c4 t^4 + c3 t^3 + c2 t^2 + c1 t + c0 = 0
        with  ci = coefficients of |dr + dv t + 0.5 a t^2|^2 / v^2  minus  t^2.

    Returns (converged, t).  Faithful: 10 iterations, absolute tolerance on the
    v^2-SCALED residual, break (not clamp) on a flat derivative, and NO
    positivity clamp -- the real solver can and does return a negative t, in
    which case the caller (L1012) keeps the crude tti instead.
    """
    one_over_v_sq = 1.0 / (muzzle_speed * muzzle_speed) if muzzle_speed > 0 else 0.0
    c = [0.0] * 5
    c[4] = accel.length_sq() * 0.25 * one_over_v_sq
    c[3] = dv.dot(accel) * one_over_v_sq
    c[2] = (dr.dot(accel) + dv.length_sq()) * one_over_v_sq - 1.0
    c[1] = 2.0 * dr.dot(dv) * one_over_v_sq
    c[0] = dr.length_sq() * one_over_v_sq

    t = t0
    for _ in range(max_iterations):
        value, xn = 0.0, 1.0
        for n in range(5):
            value += c[n] * xn
            xn *= t
        if abs(value) < tolerance:
            return True, t
        deriv, xn1 = 0.0, 1.0
        for n in range(1, 5):
            deriv += n * c[n] * xn1
            xn1 *= t
        if abs(deriv) < 1e-10:
            break
        t -= value / deriv
    return False, t
