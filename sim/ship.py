"""6-DOF rigid-body ship, stepped at the engine's 60 Hz.

Physics matched to Space Engineers where it matters:
  * linear: F = ma, then hard clamp |v| to LargeShipMaxSpeed (SCF-set)
  * angular: torque from the RCS Gyros model, capped; no angular speed limit in SE
  * thrusters apply force at the CoM (SE thrusters generate no torque themselves)
  * orientation carried as an orthonormal basis, re-orthonormalised each step
"""
import math
from vec import V, rotate_axis_angle

DT = 1.0 / 60.0


class Ship:
    def __init__(self, hull, pos, vel, max_speed, drive_thrust, n_computers=1,
                 name=None):
        self.hull = hull
        self.name = name or hull.name
        self.pos = pos.copy()
        self.vel = vel.copy()
        self.prev_vel = vel.copy()
        self.max_speed = max_speed
        self.drive_thrust = drive_thrust
        I, com, M = hull.inertia_principal()
        self.I = I
        self.mass = M
        self.tau = hull.torque(n_computers)
        # orientation basis: forward = -Z local, matching SE convention
        self.fwd = V(0, 0, -1)
        self.up = V(0, 1, 0)
        self.right = V(1, 0, 0)
        self.omega = V(0, 0, 0)
        self.throttle = 0.0            # 0..1 along fwd
        self.rcs_cmd = V(0, 0, 0)      # lateral accel command in world frame (m/s^2)
        self.torque_cmd = V(0, 0, 0)   # unit-ish axis, magnitude 0..1

    # ------------------------------------------------------------------ helpers
    @property
    def measured_accel(self):
        """MyPhysicsBody.LinearAcceleration = one-tick finite difference."""
        return (self.vel - self.prev_vel) * 60.0

    @property
    def alpha_max(self):
        """Roll axis — the cheapest axis, not the one that matters for pointing."""
        Imin = min(self.I.x, self.I.y, self.I.z)
        return self.tau / Imin if Imin > 0 else 0.0

    @property
    def alpha_point(self):
        """Pitch/yaw authority: what actually governs putting a fixed gun on target."""
        Ip = max(self.I.x, self.I.y)
        return self.tau / Ip if Ip > 0 else 0.0

    def rcs_accel_limit(self, n_facing):
        from rcs_gyro import RCS_THRUST
        return n_facing * RCS_THRUST / self.mass

    # -------------------------------------------------------------------- step
    def step(self):
        self.prev_vel = self.vel.copy()

        a = self.fwd * (self.drive_thrust * self.throttle / self.mass) + self.rcs_cmd
        self.vel = self.vel + a * DT
        if self.vel.length_sq() > self.max_speed ** 2:
            self.vel = self.vel.normalized() * self.max_speed
        self.pos = self.pos + self.vel * DT

        if self.torque_cmd.length_sq() > 1e-12:
            axis = self.torque_cmd.normalized()
            mag = min(1.0, self.torque_cmd.length())
            Iax = abs(axis.x) * self.I.x + abs(axis.y) * self.I.y + abs(axis.z) * self.I.z
            alpha = (self.tau * mag) / max(Iax, 1.0)
            self.omega = self.omega + axis * (alpha * DT)

        w = self.omega.length()
        if w > 1e-9:
            ax = self.omega / w
            ang = w * DT
            self.fwd = rotate_axis_angle(self.fwd, ax, ang).normalized()
            self.up = rotate_axis_angle(self.up, ax, ang).normalized()
            self.right = V(self.fwd.y * self.up.z - self.fwd.z * self.up.y,
                           self.fwd.z * self.up.x - self.fwd.x * self.up.z,
                           self.fwd.x * self.up.y - self.fwd.y * self.up.x).normalized()

    # ------------------------------------------------ attitude control (bang-bang)
    def point_at(self, target_world, deadband_deg=0.2):
        """Minimum-time-ish slew onto a target direction. Returns off-axis degrees."""
        des = (target_world - self.pos).normalized()
        cosang = max(-1.0, min(1.0, self.fwd.dot(des)))
        err = math.acos(cosang)
        axis = V(self.fwd.y * des.z - self.fwd.z * des.y,
                 self.fwd.z * des.x - self.fwd.x * des.z,
                 self.fwd.x * des.y - self.fwd.y * des.x)
        if axis.length() < 1e-9:
            self.torque_cmd = V(0, 0, 0)
            return math.degrees(err)
        axis = axis.normalized()
        # project current rate onto the slew axis
        w_along = self.omega.dot(axis)
        Iax = abs(axis.x) * self.I.x + abs(axis.y) * self.I.y + abs(axis.z) * self.I.z
        amax = self.tau / max(Iax, 1.0)
        # bang-bang switching curve: brake when w^2/(2*amax) >= remaining error
        if err < math.radians(deadband_deg) and abs(w_along) < 1e-3:
            self.torque_cmd = V(0, 0, 0)
        elif w_along > 0 and (w_along * w_along) / (2 * amax) >= err:
            self.torque_cmd = axis * -1.0
        else:
            self.torque_cmd = axis * 1.0
        # kill off-axis rate
        off = self.omega - axis * w_along
        if off.length() > 1e-4:
            self.torque_cmd = (self.torque_cmd - off.normalized() * 0.5)
        return math.degrees(err)

    # --------------------------------------------------------- world<->hull xform
    def to_local(self, world_point):
        d = world_point - self.pos
        return V(d.dot(self.right), d.dot(self.up), d.dot(self.fwd * -1.0))

    def dir_to_local(self, world_dir):
        return V(world_dir.dot(self.right), world_dir.dot(self.up),
                 world_dir.dot(self.fwd * -1.0))

    def to_world(self, local_point):
        return (self.pos + self.right * local_point.x + self.up * local_point.y
                + (self.fwd * -1.0) * local_point.z)

    # ------------------------------------------------------------------ chatter
    def apply_chatter(self, t, amp, period, axis=None):
        """Square-wave lateral accel, executed on RCS (no rotation cost)."""
        if amp <= 0:
            self.rcs_cmd = V(0, 0, 0)
            return
        ax = axis or self.right
        self.rcs_cmd = ax * (amp if (t % period) < period / 2 else -amp)
