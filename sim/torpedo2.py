"""WeaponCore Smart-torpedo flight model, ported line-for-line from CoreSystems.

Source of truth (workshop 3154371364):
    Data/Scripts/CoreSystems/Projectiles/Projectile.cs
    Data/Scripts/CoreSystems/Definitions/SerializedConfigs/AmmoConstants.cs
    Data/Scripts/CoreSystems/Session/SessionDamageMgr.cs
Ammo defs: workshop 3580645761 .../CoreParts/TorpedoAmmo/, parsed into
../coreparts.json and reduced to ../torpedo_profiles.json by gen_torp_profiles.py.

WHAT THE TWO EARLIER MODELS GOT WRONG
-------------------------------------
v1 modelled a flat 260 m/s cruise.  Wrong: DesiredSpeed 260 is only the
per-tick launch impulse; the speed ceiling is `speedCapMulti * MaxSpeed`
(Projectile.cs:846, clamped :855) and the cruise stage sets speedCapMulti to
3.7-5.

v2 (this file's predecessor) fixed the cap but then asserted that turning
authority is AccelPerSec (15600 m/s^2) and that AccelMulti is "a navigation
gain, not a thrust limit".  That is flatly contradicted by Projectile.cs:1273:

    accelMpsMulti = aConst.AccelInMetersPerSec * approach.AccelMulti;

AccelMulti is a *thrust* multiplier and the cruise stages set it to 0.017-0.023,
i.e. 265-359 m/s^2, not 15600.  The stage-0 value is a literal 0 (there is no
"0 means 1" fallback for AccelMulti, unlike DeAccelMulti / TotalAccelMulti at
AmmoConstants.cs:2208-2209), so the boost stage has *no* thrust and *no*
steering at all -- Projectile.cs:794 gates the entire navigation block on
`accelMpsMulti > 0`, and Direction is only rewritten inside it (:833).

v2 also used pure pursuit.  The real law (Projectile.cs:717-720) is true
proportional navigation with N = Smarts.Aggressiveness.

WHAT IS MODELLED EXACTLY
------------------------
* ProcessApproach stage machine: start/end conditions, StartAnd/EndAnd
  operators, CanExpireOnceStarted, RestartCondition, stage advance/restart
  (Projectile.cs:915-1401, 1682-1775).
* CheckApproachCondition for every condition these rounds actually use
  (Projectile.cs:1489-1620).
* accelMpsMulti / speedCapMulti / totalAccelSq / deAccelMulti binding
  (Projectile.cs:1273-1276).
* Proportional-navigation guidance and the renormalisation to accelMpsMulti
  (Projectile.cs:705-739), including the ZeroEffortNav variant (:722-729).
* The weave (Projectile.cs:763-792) with its OffsetMinRange gate.
* ProNavControl steering-limit clamp (Projectile.cs:798-808, 1885-1905).
* The MaxLateralThrust thrust de-rate (Projectile.cs:811-825) -- dead for every
  SDX2 torpedo because all of them set SteeringLimit > 0, which selects the
  AdvancedSmartSteering branch instead.
* Speed cap + drag (Projectile.cs:842-858) and the TotalAcceleration budget
  (:860-865, :703).
* Termination: MaxLifeTime vs MaxTrajectory (Projectiles.cs:312-323).
* Projectile-vs-projectile damage (SessionDamageMgr.cs:1091-1152).

DELIBERATELY NOT MODELLED (no-ops for a deep-space torpedo engagement)
----------------------------------------------------------------------
Planet Surface positions and gravity (GravityMultiplier is 0 on every torpedo),
water, model rotation / AV, obstacle avoidance (CheckFutureIntersection is off),
ApproachOrbits (Orbit is false on every stage), retargeting / zombie logic,
TimedSpawns.  Each is asserted-off at load where the def makes that checkable.
"""
import json, math, os, random

from vec import V

_P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'torpedo_profiles.json')
PROFILES = json.load(open(_P, encoding='utf-8'))

DT = 1.0 / 60.0                 # MyEngineConstants.PHYSICS_STEP_SIZE_IN_SECONDS
DELTA_TIME_RATIO = 1.0          # SessionSupport.cs:54 -- 1 on the server
DELTA_STEP = DELTA_TIME_RATIO * DT   # SessionSupport.cs:55 DeltaStepConst

# Condition value units, so a caller never has to guess whether 2500 is ticks or
# metres.  Mirrors COND_UNITS in gen_torp_profiles.py.
UNIT_TICKS = 'ticks'
UNIT_METRES = 'metres'


# ---------------------------------------------------------------- vector helpers
def _cross(a, b):
    return V(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


def _perp(v):
    """Vector3D.CalculatePerpendicularVector."""
    a = V(0, 0, 1) if abs(v.z) < 0.9 else V(1, 0, 0)
    c = _cross(v, a)
    n = c.length()
    if n < 1e-12:
        c = _cross(v, V(0, 1, 0))
        n = c.length()
    return c / n if n > 1e-12 else V(1, 0, 0)


def _point_line_distance(a, b, p):
    """MyUtils.GetPointLineDistance(from, to, point) -- distance to the infinite line."""
    d = b - a
    dl = d.length()
    if dl < 1e-9:
        return (p - a).length()
    return _cross(p - a, d).length() / dl


class _Store:
    __slots__ = ('pos',)

    def __init__(self):
        self.pos = V(0, 0, 0)


# ============================================================== the torpedo ====
class Torpedo2:
    """One WeaponCore Smart projectile.

    `target_ref` needs a `.pos` (V); `.vel` is used if present, else zero.
    `shooter_vel` matters: MaxSpeed is |ShooterVel + dir*DesiredSpeed|
    (Projectile.cs:295-297), so every speed cap scales with launcher velocity.
    """

    #: FALLBACK ONLY. This used to be the sole source of a torpedo's RNG stream, via
    #: `seed * 7919 + self.id`, and because it is a PROCESS-GLOBAL counter that nothing
    #: reset, two back-to-back runs of the same scenario at the same seed produced
    #: different answers -- measured 1, 2, 3, 3 leakers on four identical repeats. Any
    #: A/B that ran its arms sequentially in one process was confounded by it, which
    #: means every sequential comparison in this project predating this fix is void.
    #:
    #: The stream is now seeded from (scenario seed, index within salvo), so it depends
    #: only on the scenario. `index` should always be passed; `_ids` survives for
    #: callers that construct a lone probe torpedo, and reset_ids() exists so even they
    #: can be made repeatable.
    _ids = 0

    @classmethod
    def reset_ids(cls):
        cls._ids = 0

    def __init__(self, kind, pos, vel, target_ref, seed=0, shooter_vel=None,
                 stage_mode=None, index=None):
        if index is None:
            Torpedo2._ids += 1
            index = Torpedo2._ids
        self.index = index
        self.id = index
        self.kind = kind
        p = PROFILES[kind]
        self.p = p
        self.stages = p['stages']
        sm = p['smarts']

        self.pos = pos.copy()
        # LastPosition, needed by the projectile-vs-projectile CCD
        # (ProjectileHits.cs:653) which brackets both segments over the same tick.
        self.last_pos = pos.copy()
        self.origin = pos.copy()
        self.target = target_ref
        # (scenario seed, index within salvo) -- NOT a process-global counter
        self.rnd = random.Random((int(seed) * 7919 + int(index) * 104729) & 0xFFFFFFFF)

        # ---- AmmoConstants -------------------------------------------------
        self.desired_speed = p['desired']                    # Trajectory.DesiredSpeed
        self.accel_per_sec = p['accel_per_sec']              # :482 AccelInMetersPerSec
        self.delta_v_per_tick = p['delta_velocity_per_tick'] # :483
        self.max_life = p['life_ticks']                      # :480
        self.max_traj = p['max_traj']
        ta = p.get('total_acceleration')
        self.total_accel_sq_base = (ta * ta) if ta else float('inf')  # :484-485

        self.aggressiveness = sm['aggressiveness']
        self.nav_acceleration = sm['nav_acceleration']       # :830-831
        self.zero_effort_nav_base = sm['zero_effort_nav']
        self.min_turn_speed_sq = sm['min_turn_speed'] ** 2   # :833
        self.advanced_steering = sm['advanced_smart_steering']   # :819
        self.steering_cos = sm['steering_cos']               # :2429
        mlt = sm['max_lateral_thrust']
        self.max_lateral_thrust = float('inf') if mlt is None else mlt   # :507
        self.no_steering = sm['no_steering']
        # PreComputedMath.ComputeSteering (:2425-2441)
        rad = math.radians(sm['steering_limit_deg'])
        self.steering_sign = 1
        m = rad
        if m > math.pi / 2:
            m = math.pi - m
            self.steering_sign = -1
        self.steering_norm_len = math.sin(m)
        self.steering_parallel_len = math.sqrt(max(0.0, 1.0 - self.steering_norm_len ** 2))

        self.offset_time = sm['offset_time']
        self.offset_ratio = sm['offset_ratio']
        self.offset_min_range_sq = sm['offset_min_range'] ** 2
        self.collision_size = p['collision_size']

        # ---- launch state (Projectile.cs:295-308) --------------------------
        self.shooter_vel = (shooter_vel or V(0, 0, 0)).copy()
        d0 = vel.normalized() if vel.length() > 1e-9 else (target_ref.pos - pos).normalized()
        self.direction = d0
        relative_speed_cap = self.shooter_vel + d0 * self.desired_speed
        self.max_speed = relative_speed_cap.length()         # :297
        if p['ammo_skip_accel']:
            self.vel = relative_speed_cap
        else:
            self.vel = self.shooter_vel + d0 * (self.delta_v_per_tick * DELTA_TIME_RATIO)
        self.vel_len_sq = self.vel.length_sq()
        self.prev_vel0 = self.vel.copy()
        self.prev_vel1 = self.vel.copy()

        # ---- ProInfo / ApproachInfo ----------------------------------------
        self.health = p['health']                            # BaseHealthPool, :159
        self.age = -1.0                                      # RelativeAge, Projectiles.cs:130
        self.prev_age = -1.0
        self.travelled = 0.0                                 # DistanceTraveled
        self.dist_to_travel_sq = self.max_traj ** 2          # :251
        self.total_acceleration = 0.0                        # Info.TotalAcceleration
        self.frags = 0

        self.requested_stage = -1                            # :927-931
        self.last_activated_stage = -1
        self.approach_active = True
        self.a_start_health = self.health
        self.a_start_travel = 0.0
        self.a_age_start = 0.0
        self.a_spawns_start = 0
        self.a_pos_b = V(0, 0, 0)
        self.a_pos_c = V(0, 0, 0)
        self.a_fwd = d0.copy()
        self.a_up = _perp(d0)
        self.a_angle_variance = 0.0
        self.a_store = [_Store() for _ in range(2 * len(self.stages))]
        self.target_position = target_ref.pos.copy()
        self.prev_target_vel = getattr(target_ref, 'vel', None)
        self.prev_target_vel = self.prev_target_vel.copy() if self.prev_target_vel else V(0, 0, 0)
        self.last_target_vel = None

        self.rand_offset_dir = V(0, 0, 0)
        self.alive = True
        self.expired = False
        self.end_reason = None

        # telemetry
        self.stage_log = []          # (tick, stage_index)
        self.speed_cap = self.max_speed
        self.accel_mps = 0.0

    # ------------------------------------------------------------- properties
    @property
    def stage(self):
        i = self.requested_stage
        return self.stages[i] if 0 <= i < len(self.stages) else None

    @property
    def weaving(self):
        """True when the OffsetMinRange gate (Projectile.cs:787) is open."""
        if self.offset_time <= 0 or self.offset_ratio <= 0:
            return False
        return (self.target_position - self.pos).length_sq() >= self.offset_min_range_sq

    @property
    def speed(self):
        return self.vel.length()

    # ------------------------------------------- CheckApproachCondition port
    def _check(self, cond, val, cond_and, line_c, pos_c, line_b, pos_b):
        """Projectile.cs:1489-1620."""
        cs = self.collision_size
        tp = self.target.pos
        if cond == 'Spawn':
            return True
        if cond == 'Ignore':
            # :1497-1499 -- with AND return true so it cannot block; with OR
            # return false so it cannot false-positive.
            return cond_and
        if cond == 'DistanceFromPositionC':
            if (line_c - pos_c).length_sq() > 1e-12:
                return _point_line_distance(line_c, pos_c, self.pos) - cs <= val
            return (pos_c - self.pos).length() - cs <= val
        if cond == 'DistanceToPositionC':
            if (line_c - pos_c).length_sq() > 1e-12:
                return _point_line_distance(line_c, pos_c, self.pos) - cs >= val
            return (pos_c - self.pos).length() - cs >= val
        if cond == 'DistanceFromPositionB':
            if (line_b - pos_b).length_sq() > 1e-12:
                return _point_line_distance(line_b, pos_b, self.pos) - cs <= val
            return (pos_b - self.pos).length() - cs <= val
        if cond == 'DistanceToPositionB':
            if (line_b - pos_b).length_sq() > 1e-12:
                return _point_line_distance(line_b, pos_b, self.pos) - cs >= val
            return (pos_b - self.pos).length() - cs >= val
        if cond == 'DistanceFromTarget':
            return (tp - self.pos).length() - cs <= val
        if cond == 'DistanceToTarget':
            return (tp - self.pos).length() - cs >= val
        if cond == 'DistanceFromEndTrajectory':
            return (self.target_position - self.pos).length() - cs <= val
        if cond == 'DistanceToEndTrajectory':
            return (self.target_position - self.pos).length() - cs >= val
        if cond == 'Lifetime':
            return self.age >= val                       # absolute RelativeAge, :1546
        if cond == 'Deadtime':
            return self.age <= val
        if cond == 'RelativeLifetime':
            return self.age - self.a_age_start >= val
        if cond == 'RelativeDeadtime':
            return self.age - self.a_age_start <= val
        if cond == 'MinTravelRequired':
            return self.travelled - self.a_start_travel >= val
        if cond == 'MaxTravelRequired':
            return self.travelled - self.a_start_travel <= val
        if cond == 'RelativeHealthLost':
            return self.a_start_health - self.health >= val
        if cond == 'HealthRemaining':
            return self.health <= val
        if cond == 'RelativeSpawns':
            return self.frags - self.a_spawns_start >= val
        if cond in ('EnemySeekersLessThanEqualTo', 'ReaquiredTarget'):
            return True          # no seekers / never loses target in this harness
        if cond in ('EnemySeekersGreaterThanEqualTo', 'EnemyTargetLoss'):
            return False
        if cond == 'DesiredElevation':
            return False         # planet-only, GravityMultiplier == 0 on all torpedoes
        raise NotImplementedError('condition %r not ported' % cond)

    # -------------------------------------------------- ProcessApproach port
    def _resolve(self, kind, stored_id, end_side):
        """RelativeTo -> world position (Projectile.cs:1122-1239)."""
        if kind == 'Origin':
            return self.origin.copy()
        if kind == 'Shooter':
            return self.origin.copy()          # no separate shooter entity here
        if kind == 'Target':
            return self.target_position.copy()
        if kind == 'Surface':
            return self.origin.copy()          # :1140-1141, no planet
        if kind == 'MidPoint':
            return (self.target_position + self.pos) * 0.5
        if kind == 'PositionA':
            return self.pos.copy()
        if kind in ('StoredStartDontUse', 'StoredStartPosition', 'StoredStartLocalPosition'):
            s = self.a_store[stored_id].pos
            return s.copy() if s.length_sq() > 0 else self.target_position.copy()
        if kind in ('StoredEndDontUse', 'StoredEndPosition', 'StoredEndLocalPosition'):
            s = self.a_store[len(self.stages) + stored_id].pos
            return s.copy() if s.length_sq() > 0 else self.target_position.copy()
        if kind == 'Nothing':
            # PositionC :1236-1238 falls back to the target; PositionB has no
            # `Nothing` case at all, so the previous value is retained.
            return self.target.pos.copy() if end_side == 'C' else None
        return self.origin.copy()

    def _dir_relative_to(self, kind, stored_id, default):
        """FwdRelativeTo / UpRelativeTo (Projectile.cs:985-1087)."""
        if kind in ('ForwardRelativeToBlock', 'UpRelativeToBlock',
                    'ForwardRelativeToShooter', 'UpRelativeToShooter',
                    'ForwardOriginDirection', 'UpOriginDirection',
                    'ForwardRelativeToGravity', 'UpRelativeToGravity'):
            return default
        if kind in ('ForwardTargetDirection', 'UpTargetDirection'):
            return (self.target_position - self.pos).normalized()
        if kind in ('ForwardTargetVelocity', 'UpTargetVelocity'):
            tv = self.prev_target_vel
            return tv.normalized() if tv.length_sq() > 1e-12 else default
        if 'StoredStart' in kind:
            d = self._resolve('StoredStartPosition', stored_id, 'S') - self.pos
            return d.normalized() if d.length_sq() > 1e-12 else default
        if 'StoredEnd' in kind:
            d = self._resolve('StoredEndPosition', stored_id, 'E') - self.pos
            return d.normalized() if d.length_sq() > 1e-12 else default
        return default            # ForwardElevationDirection handled by the caller

    def _plane_offset(self, plane_point, normal, to_point):
        """PlaneD(point, normal).DistanceToPoint(to) * normal (Projectile.cs:1300-1339)."""
        n = normal.normalized()
        return n * (to_point - plane_point).dot(n)

    def _process_approach(self):
        """Projectile.cs:915-1401.  Returns (accel_mps, cap_multi, total_accel_sq,
        deaccel_multi, zero_effort_nav)."""
        accel_mps = self.accel_per_sec        # :689 speedLimitPerTick
        cap_multi = 1.0
        total_accel_sq = self.total_accel_sq_base
        deaccel = 1.0
        zen = self.zero_effort_nav_base

        if not self.approach_active and self.requested_stage != -1:
            return accel_mps, cap_multi, total_accel_sq, deaccel, zen

        last_active = self.last_activated_stage
        if self.requested_stage == -1:                       # :927-931
            self.last_activated_stage = -1
            self.requested_stage = 0
            last_active = -1

        stage_change = self.requested_stage != last_active
        if stage_change:                                     # :935-941
            self.a_start_health = self.health
            self.a_start_travel = self.travelled
            self.a_age_start = self.age
            self.a_spawns_start = self.frags

        ap = self.stages[self.requested_stage]
        if ap['swap_navigation_type']:                       # :947-948
            zen = not zen

        # ---- vantage points (:983-1110) ---------------------------------
        if ap['adjust_forward'] or stage_change:
            self.a_fwd = self._dir_relative_to(ap['forward'], ap['stored_start_id']
                                               if 'Start' in ap['forward'] else ap['stored_end_id'],
                                               self.direction)
        if ap['adjust_up'] or stage_change:
            self.a_up = self._dir_relative_to(ap['up'], ap['stored_start_id']
                                              if 'Start' in ap['up'] else ap['stored_end_id'],
                                              _perp(self.direction))
        if ap['angle_offset'] != 0.0:                        # :1089-1110
            angle = (ap['angle_offset'] + self.a_angle_variance) * math.pi
            sn, cs_ = math.sin(angle), math.cos(angle)
            up_fwd = _perp(self.a_up)
            up_right = _cross(self.a_up, up_fwd)
            fwd_fwd = _perp(self.a_fwd)
            fwd_right = _cross(self.a_fwd, up_fwd)
            self.a_up = up_fwd * sn + up_right * cs_
            self.a_fwd = fwd_fwd * sn + fwd_right * cs_

        height_offset = self.a_up * ap['desired_elevation']  # :1112-1113
        rel_dist = self.travelled - self.a_start_travel
        travel_lead = rel_dist if rel_dist >= ap['tracking_distance'] else 0.0
        desired_lead = (travel_lead if ap['push_lead_by_travel'] else 0.0) + ap['lead_distance']
        clamped_lead = max(desired_lead, ap['mod_future_step'])   # :1117

        if stage_change or ap['adjust_position_b']:          # :1120-1180
            pb = self._resolve(ap['position_b'], ap['stored_start_id'], 'B')
            if pb is not None:
                self.a_pos_b = pb
            if ap['lead_rotate_elevate_b']:
                self.a_pos_b = self.a_pos_b + height_offset + self.a_fwd * clamped_lead
        if stage_change or ap['adjust_position_c']:          # :1182-1246
            pc = self._resolve(ap['position_c'], ap['stored_start_id'], 'C')
            if pc is not None:
                self.a_pos_c = pc
            if ap['lead_rotate_elevate_c']:
                self.a_pos_c = self.a_pos_c + height_offset + self.a_fwd * clamped_lead

        position_b = self.a_pos_b.copy()
        position_c = self.a_pos_c.copy()

        # ---- start conditions (:1260-1271) ------------------------------
        el_line_c = position_c + height_offset
        el_line_b = position_b + height_offset
        sa = ap['start_and']
        s1 = self._check(ap['start_conditions'][0][0], ap['start_conditions'][0][1], sa,
                         el_line_c, position_c, el_line_b, position_b)
        s2 = self._check(ap['start_conditions'][1][0], ap['start_conditions'][1][1], sa,
                         el_line_c, position_c, el_line_b, position_b)

        started = ((sa and s1 and s2) or (not sa and (s1 or s2))
                   # THE latch: once any stage has activated, every later stage
                   # auto-starts unless it opted into CanExpireOnceStarted.
                   or (self.last_activated_stage >= 0 and not ap['can_expire_once_started']))

        if started:                                          # :1272-1382
            accel_mps = self.accel_per_sec * ap['accel_multi']    # :1273
            cap_multi = ap['speed_cap_multi']                     # :1274
            total_accel_sq *= ap['total_accel_multi_sq']          # :1275
            deaccel = ap['deaccel_multi']                         # :1276

            fwd_dest = ap['forward'] == 'ForwardElevationDirection'
            up_dest = ap['up'] == 'UpElevationDirection'
            if fwd_dest:
                d = (position_c - position_b) if not ap['elevation_relative_to_c'] \
                    else (position_b - position_c)
                fwd_dir = d.normalized() if d.length_sq() > 1e-12 else self.direction
            else:
                fwd_dir = self.a_fwd
            if up_dest:
                up_dir = fwd_dir if fwd_dest else fwd_dir
            else:
                up_dir = self.a_up
            surface_ref = position_b if not ap['elevation_relative_to_c'] else position_c

            el = ap['elevation']                             # :1286-1371
            if el == 'Surface':
                el_offset = height_offset
            elif el == 'Origin':
                el_offset = self._plane_offset(self.origin - height_offset, up_dir, surface_ref)
            elif el == 'MidPoint':
                proj = (position_c + position_b) * 0.5
                el_offset = self._plane_offset(proj - height_offset, up_dir, surface_ref)
            elif el == 'Shooter':
                el_offset = self._plane_offset(self.origin - height_offset, up_dir, surface_ref)
            elif el == 'Target':
                pp = position_c if not ap['elevation_relative_to_c'] else position_b
                tpp = position_b if not ap['elevation_relative_to_c'] else position_c
                el_offset = self._plane_offset(pp - height_offset, up_dir, tpp)
            elif el == 'PositionA':
                el_offset = self._plane_offset(self.pos - height_offset, up_dir, surface_ref)
            else:
                el_offset = V(0, 0, 0)

            desired_pos = (position_c if not ap['trajectory_relative_to_b'] else position_b) + el_offset
            if (desired_pos - self.pos).length_sq() < 1e-12:
                desired_pos = desired_pos + self.a_fwd * 10000.0
            self.target_position = desired_pos               # :1377 (Orbit is false everywhere)

            if self.last_activated_stage != self.requested_stage:   # :1379-1380
                self._start_event(ap, position_b, position_c)

        # ---- end conditions (:1385-1396) --------------------------------
        end_line_c = position_c + height_offset
        end_line_b = position_b + height_offset
        ea = ap['end_and']
        ends = [self._check(c[0], c[1], ea, end_line_c, position_c, end_line_b, position_b)
                for c in ap['end_conditions']]
        if (ea and all(ends)) or (not ea and any(ends)):
            self._approach_end(ap, ends, position_b, position_c)

        return accel_mps, cap_multi, total_accel_sq, deaccel, zen

    def _start_event(self, ap, position_b, position_c):
        """ApproachStartEvent (Projectile.cs:1622-1680) -- Store* and EndProjectile only."""
        self.last_activated_stage = self.requested_stage
        ev = ap['start_event']
        if ev == 'EndProjectile':
            self._end('StartEvent.EndProjectile')
            return
        if not ev.startswith('Store'):
            return
        t = ap['stored_start_type']
        slot = self.a_store[self.requested_stage]
        if t == 'Target':
            slot.pos = self.target_position.copy()
        elif t == 'PositionA':
            slot.pos = self.pos.copy()
        elif t == 'Shooter':
            slot.pos = self.origin.copy()
        elif t == 'MidPoint':
            slot.pos = (position_c + position_b) * 0.5
        elif t == 'Nothing':
            store_c = ev in ('StoreDontUse', 'StorePositionDontUse', 'StorePositionC')
            slot.pos = (position_c if store_c
                        else (self.pos if ev == 'StorePositionA' else position_b)).copy()
        elif t == 'StoredStartLocalPosition':
            store_b = ev in ('StoreDontUse', 'StorePositionDontUse', 'StorePositionB')
            slot.pos = (position_b if store_b
                        else (self.pos if ev == 'StorePositionA' else position_c)).copy()
        else:
            slot.pos = self.target.pos.copy()

    def _approach_end(self, ap, ends, position_b, position_c):
        """ApproachEnd (Projectile.cs:1682-1775)."""
        n = len(self.stages)
        has_next = self.requested_stage + 1 < n
        is_active = self.last_activated_stage >= 0
        rc = ap['restart_condition']
        force = ap['force_restart']
        # NOTE MoveToPrevious behaves as MoveToNext whenever the stage actually
        # activated -- activeNext includes it (:1690).
        active_next = is_active and not force and rc in ('Wait', 'MoveToPrevious', 'MoveToNext')
        inactive_next = (not is_active) and (not force) and rc == 'MoveToNext'
        move_forward = has_next and (active_next or inactive_next)
        restart = (rc == 'MoveToPrevious' and not is_active) or rc == 'ForceRestart'

        ev = ap['end_event']
        if ev == 'EndProjectile' or (ev == 'EndProjectileOnRestart'
                                     and (restart or (not move_forward and has_next))):
            self._end('EndEvent.EndProjectile')
            return
        if ev.startswith('Store'):
            t = ap['stored_end_type']
            slot = self.a_store[n + self.requested_stage]
            if t == 'Target':
                slot.pos = self.target_position.copy()
            elif t == 'PositionA':
                slot.pos = self.pos.copy()
            elif t == 'Shooter':
                slot.pos = self.origin.copy()
            elif t == 'MidPoint':
                slot.pos = (position_c + position_b) * 0.5
            elif t == 'Nothing':
                store_c = ev in ('StoreDontUse', 'StorePositionDontUse', 'StorePositionC')
                slot.pos = (position_c if store_c
                            else (self.pos if ev == 'StorePositionA' else position_b)).copy()
            else:
                slot.pos = self.target.pos.copy()

        if move_forward:                                     # :1756-1761
            self.last_activated_stage = self.requested_stage
            self.requested_stage += 1
        elif restart or force:                               # :1762-1768
            self.last_activated_stage = self.requested_stage
            prev = self.requested_stage
            if rc == 'MoveToPrevious':
                self.requested_stage = prev
            else:
                ids = [e['approach_id'] for e in ap['restart_list']] or [-1]
                self.requested_stage = max(0, ids[0]) if ids[0] >= 0 else max(0, prev - 1)
        elif not has_next:                                   # :1769-1774
            self.last_activated_stage = n
            self.requested_stage = n
        self.stage_log.append((int(self.age), self.requested_stage))

    # ---------------------------------------------------------- RunSmart port
    def _end(self, reason):
        self.dist_to_travel_sq = self.travelled ** 2
        self.alive = False
        self.expired = True
        self.end_reason = self.end_reason or reason

    def step(self, dt=DT):
        """One 60 Hz tick.  Returns the current range to the target.

        Ordering follows Projectiles.cs:129-323 -> Projectile.RunSmart (:522-880).
        """
        if not self.alive:
            return (self.target.pos - self.pos).length()

        self.prev_age = self.age
        self.last_pos = self.pos.copy()
        self.age += DELTA_TIME_RATIO                          # Projectiles.cs:129-130

        # ---- target bookkeeping (:598-653) ---------------------------------
        tvel = getattr(self.target, 'vel', None)
        tvel = tvel.copy() if tvel else V(0, 0, 0)
        self.target_position = self.target.pos.copy()
        self.prev_target_vel = tvel

        proposed = self.vel.copy()

        # ---- approaches (:693-697) -----------------------------------------
        if self.stages and (self.approach_active or self.requested_stage == -1):
            accel_mps, cap_multi, total_accel_sq, deaccel, zen = self._process_approach()
            self.approach_active = 0 <= self.requested_stage < len(self.stages)
            if not self.alive:
                return (self.target.pos - self.pos).length()
        else:
            accel_mps = self.accel_per_sec
            cap_multi, total_accel_sq, deaccel = 1.0, self.total_accel_sq_base, 1.0
            zen = self.zero_effort_nav_base
        self.accel_mps = accel_mps

        # ---- navigation (:699-834) ------------------------------------------
        fast_enough = self.vel_len_sq >= self.min_turn_speed_sq
        commanded = None
        m2t_norm = V(0, 0, 0)
        if (not self.no_steering) and fast_enough and self.total_acceleration <= total_accel_sq:
            target_accel = V(0, 0, 0)
            if self.last_target_vel is not None:
                target_accel = (self.prev_target_vel - self.last_target_vel) * 60.0
            self.last_target_vel = self.prev_target_vel.copy()

            m2t = self.target_position - self.pos
            m2t_norm = m2t.normalized()
            rel_vel = self.prev_target_vel - self.vel
            lat_target_accel = target_accel - m2t_norm * target_accel.dot(m2t_norm)

            if not zen:
                # TRUE PROPORTIONAL NAVIGATION (:719-720).  N == Aggressiveness.
                omega = _cross(m2t, rel_vel) / max(m2t.length_sq(), 1.0)
                lat = (_cross(omega, m2t_norm) * (self.aggressiveness * rel_vel.length())
                       + lat_target_accel * self.nav_acceleration)
            else:
                # zero-effort-miss (:724-728)
                dist_to_target = m2t.dot(m2t_norm)
                closing = rel_vel.dot(m2t_norm)
                tau = dist_to_target / max(1.0, abs(closing))
                z = m2t + rel_vel * tau
                lat = z * (self.aggressiveness / (tau * tau)) + lat_target_accel * self.nav_acceleration

            if lat.length_sq() < 1e-24:                       # :731-734
                commanded = m2t_norm * accel_mps
            else:
                diff = accel_mps * accel_mps - lat.length_sq()
                if diff < 0:
                    commanded = lat.normalized() * accel_mps
                else:
                    commanded = lat + m2t_norm * math.sqrt(diff)
            # gravity compensation (:740-756) skipped: GravityMultiplier == 0
        else:
            commanded = self.direction * accel_mps            # :758-759

        # ---- weave (:764-792) ------------------------------------------------
        offset = False
        if self.offset_time > 0:
            prev_c = self.prev_age % self.offset_time
            cur_c = self.age % self.offset_time
            if prev_c < 0 or prev_c > cur_c:
                up = _perp(self.direction)
                right = _cross(self.direction, up)
                a = self.rnd.random() * 2.0 * math.pi
                self.rand_offset_dir = (up * math.sin(a) + right * math.cos(a)) * self.offset_ratio
            if (self.target_position - self.pos).length_sq() >= self.offset_min_range_sq:
                # NB this is ADDED to an already-renormalised commandedAccel, so
                # |commandedAccel| becomes accel_mps * sqrt(1 + offsetRatio^2).
                commanded = commanded + self.rand_offset_dir * accel_mps
                offset = True

        # ---- thrust integration (:794-834) -----------------------------------
        if accel_mps > 0:
            if self.advanced_steering:                        # :798-808
                if fast_enough:
                    heading, normalised = self._pro_nav_control(commanded)
                    if normalised:
                        proposed = self.vel + heading * (accel_mps * DELTA_STEP)
                    else:
                        proposed = self.vel + commanded * DELTA_STEP
                else:
                    proposed = self.vel + commanded * DELTA_STEP
            else:                                             # :810-827 (dead for SDX2)
                if self.max_lateral_thrust < 1 and fast_enough:
                    cn = commanded.normalized()
                    dot = self.direction.dot(cn)
                    if offset or dot < 0.98:
                        rad = math.acos(max(-1.0, min(1.0, dot))) or 1e-300
                        if rad > self.max_lateral_thrust and dot > 0:
                            commanded = cn * (accel_mps * abs(rad / math.pi - 1.0))
                proposed = self.vel + commanded * DELTA_STEP
            self.direction = proposed.normalized()            # :833
        # else: no thrust, no steering, Direction frozen -- the boost stage.

        # ---- speed cap (:842-867) --------------------------------------------
        self.vel_len_sq = proposed.length_sq()
        if self.vel_len_sq <= self.desired_speed ** 2:        # :843-844
            self.max_speed = self.desired_speed
        cap = cap_multi * self.max_speed                      # :846
        # AmmoUseDrag is false on every SDX2 torpedo (no DragPerSecond), so the
        # :847-854 drag term is skipped; deaccel_multi is therefore inert.
        self.speed_cap = cap
        if self.vel_len_sq > cap * cap:                       # :855-858
            proposed = self.direction * cap
        else:
            self.total_acceleration += (proposed - self.prev_vel1).length_sq()   # :860

        self.prev_vel0 = self.prev_vel1
        self.prev_vel1 = self.vel
        if self.total_acceleration > total_accel_sq:          # :864-865
            proposed = self.vel
        self.vel = proposed

        # ---- move + terminate (Projectiles.cs:289-323) ------------------------
        travel = self.vel * DELTA_STEP
        self.pos = self.pos + travel
        self.travelled += abs(self.direction.dot(travel))     # :311-312 (path length)

        if self.age > self.max_life:                          # :314-317
            self._end('MaxLifeTime')
        elif self.travelled ** 2 >= self.dist_to_travel_sq:   # :320
            self._end('MaxTrajectory')
        return (self.target.pos - self.pos).length()

    def _pro_nav_control(self, command_accel):
        """Projectile.cs:1885-1905.  Returns (heading, isNormalized)."""
        if self.vel.length_sq() < 1e-10 or command_accel.length_sq() < 1e-10:
            return command_accel, False
        if self.direction.dot(command_accel.normalized()) < self.steering_cos:
            normal = _cross(_cross(self.direction, command_accel), self.direction)
            if normal.length_sq() < 1e-10:
                normal = _perp(self.direction)
            else:
                normal = normal.normalized()
            return (self.direction * (self.steering_sign * self.steering_parallel_len)
                    + normal * self.steering_norm_len), True
        return command_accel, False

    # ------------------------------------------------------------------ damage
    def hits_to_kill(self, hhm):
        """SessionDamageMgr.cs:1101-1152.

        scaledDamage = 1 * HealthHitModifier (:1110), subtracted from the target's
        BaseHealthPool (:1151).  So ceil(Health / HHM) hits, and HHM may be < 1.
        """
        hhm = float(hhm)
        if hhm <= 0:
            return float('inf')
        return max(1, math.ceil(self.health / hhm))


# ================================================================ weave =======
_WEAVE_CACHE = {}


def weave_rms(torp_kind, tof, samples=400, seed=12345, speed=None):
    """RMS lateral displacement a torpedo accumulates over `tof` seconds.

    Measured, not guessed: integrates the real weave (Projectile.cs:764-792) at
    60 Hz -- a perpendicular acceleration of accel_mps * OffsetRatio, re-rolled
    every OffsetTime ticks, with the resulting velocity renormalised to the speed
    cap each tick.  That renormalisation is why the displacement is bounded by
    v*tof and not by 0.5*a*tof^2: the weave rotates the velocity vector, it does
    not lengthen it.

    Returns 0 when the round is inside OffsetMinRange, where the weave is gated
    off entirely (:787).
    """
    p = PROFILES[torp_kind]
    sm = p['smarts']
    ratio, period = sm['offset_ratio'], sm['offset_time']
    if ratio <= 0 or period <= 0 or tof <= 0:
        return 0.0
    # Pick the stage that is actually running while the weave is enabled.  The
    # weave gate is `range >= OffsetMinRange` (:787) and stages are ordered by
    # decreasing range, so that is the FIRST powered stage -- not the terminal
    # one.  BlastFrag/Hekp only reach their 2652 m/s^2 stages inside 2500 m,
    # where the weave is already switched off.
    live = [s for s in p['stages'] if s['accel_multi'] > 0 and not s.get('ends_immediately')]
    if not live:
        return 0.0
    a = live[0]['accel_mps2']
    v = speed if speed is not None else live[0]['speed_cap_mps']
    key = (torp_kind, round(tof, 4), samples, seed, round(v, 3))
    if key in _WEAVE_CACHE:
        return _WEAVE_CACHE[key]

    rnd = random.Random(seed)
    n = max(1, int(round(tof * 60.0)))
    acc = 0.0
    for _ in range(samples):
        # 2-D is sufficient: the weave plane is perpendicular to the heading.
        vx, vy = v, 0.0
        px = py = 0.0
        ox = oy = 0.0
        for k in range(n):
            if k % period == 0:
                th = rnd.random() * 2.0 * math.pi
                ox, oy = math.cos(th) * ratio * a, math.sin(th) * ratio * a
            # commandedAccel = a along heading + the perpendicular offset
            hx, hy = (vx, vy) if (vx or vy) else (1.0, 0.0)
            hl = math.hypot(hx, hy) or 1.0
            hx, hy = hx / hl, hy / hl
            vx += (hx * a + ox) * DT
            vy += (hy * a + oy) * DT
            sp = math.hypot(vx, vy)
            if sp > v:                       # the :855-857 clamp
                vx, vy = vx / sp * v, vy / sp * v
            px += vx * DT
            py += vy * DT
        acc += py * py                       # cross-track component
    out = math.sqrt(acc / samples)
    _WEAVE_CACHE[key] = out
    return out


def weave_sigma(torp_kind, tof):
    """Backward-compatible name.  Now a simulated value, not a closed form."""
    return weave_rms(torp_kind, tof)


def weave_bound(torp_kind, tof):
    """Hard physical ceiling: the round cannot displace further than it can fly."""
    return PROFILES[torp_kind]['terminal_speed'] * tof


# ================================================================= harness ====
class _Fixed:
    def __init__(self, pos=None, vel=None):
        self.pos = pos or V(0, 0, 0)
        self.vel = vel or V(0, 0, 0)

    def advance(self, dt=DT):
        self.pos = self.pos + self.vel * dt


def _patch_pure(t):
    """Degrade a Torpedo2 to v2's pure pursuit, so the two laws can be measured
    rather than argued about.  With both gains zero, `lat` is exactly zero and
    Projectile.cs:731-733 reduces commandedAccel to `LOS * accelMpsMulti`."""
    t.aggressiveness = 0.0
    t.nav_acceleration = 0.0
    return t


def fly(kind, start_range=15000.0, target_vel=None, shooter_vel=None, seed=1,
        marks=(3000.0, 1000.0), max_ticks=20000, pure_pursuit=False):
    """Fire one round head-on from `start_range`; report mark crossings and CPA.

    Impact is closest point of approach, not a radius test: at 1040 m/s a tick is
    17 m, so a literal `range <= CollisionSize` test can never fire.  WeaponCore
    itself sweeps a line segment per tick (ProjectileHits), so CPA is the right
    analogue.
    """
    tgt = _Fixed(V(0, 0, 0), target_vel)
    t = Torpedo2(kind, V(start_range, 0, 0), V(-1, 0, 0), tgt, seed=seed,
                 shooter_vel=shooter_vel)
    if pure_pursuit:
        _patch_pure(t)
    hit = {m: None for m in marks}
    peak = 0.0
    best, best_t = start_range, None
    n = 0
    while t.alive and n < max_ticks:
        n += 1
        tgt.advance()
        d = t.step()
        peak = max(peak, t.speed)
        for m in marks:
            if hit[m] is None and d <= m:
                hit[m] = t.age / 60.0
        if d < best:
            best, best_t = d, t.age / 60.0
        elif best < 500.0:
            break                              # past CPA, it has flown through
    return {
        'kind': kind, 'peak': peak, 'impact': best_t if best < 500.0 else None,
        'cpa': best, 'marks': hit, 'age': t.age / 60.0, 'travelled': t.travelled,
        'end': t.end_reason, 'stage_log': t.stage_log, 'start_range': start_range,
    }


def validate(start_range=15000.0, tol=0.05):
    """Cross-check the tick sim against a piecewise closed-form straight-line flight.

    Boost coast at DesiredSpeed for `boost_ticks`, then each powered stage in
    turn: accelerate at accel_mps2 to that stage's cap and cruise until the
    stage's DistanceFromPositionC threshold.  Weave off (it only lengthens the
    path).  Returns [(kind, closed_form_s, sim_s, delta_s, ok)].
    """
    out = []
    for k, p in PROFILES.items():
        live = [s for s in p['stages'] if s['accel_multi'] > 0 and not s['ends_immediately']]
        if not live:
            out.append((k, None, None, None, None))
            continue
        boost = p['stages'][0]['end_conditions'][0][1] / 60.0
        v = p['desired']
        rng = start_range - v * boost          # range left after the coast
        closed = boost
        for i, s in enumerate(live):
            a, cap = s['accel_mps2'], s['speed_cap_mps']
            # this stage runs until its DistanceFromPositionC end value, or to 0
            # if it is the last powered stage
            stop = 0.0
            for c in s['end_conditions']:
                if c[0] == 'DistanceFromPositionC':
                    stop = c[1]
            if i == len(live) - 1:
                stop = 0.0
            span = rng - stop
            if span <= 0:
                continue
            if v < cap:
                ta = (cap - v) / a
                da = v * ta + 0.5 * a * ta * ta
                if da >= span:                 # still accelerating when the stage ends
                    ta = (-v + math.sqrt(v * v + 2 * a * span)) / a
                    v += a * ta
                    closed += ta
                    rng = stop
                    continue
                closed += ta
                span -= da
                v = cap
            closed += span / v
            rng = stop
        keep = p['smarts']['offset_ratio']
        p['smarts']['offset_ratio'] = 0.0
        try:
            sim = fly(k, start_range)['impact']
        finally:
            p['smarts']['offset_ratio'] = keep
        d = (sim - closed) if sim else None
        # rounds whose terminal stages carry a DesiredElevation fly an S-weave the
        # straight-line closed form cannot represent, so they run slightly long.
        wiggle = any(s['desired_elevation'] for s in live)
        lim = tol * 3 if wiggle else tol
        out.append((k, closed, sim, d, (d is not None and abs(d) <= lim)))
    return out


def _main():
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    order = ['Torpedo160mmBelter', 'Torpedo160mmBlastFrag', 'Torpedo160mmPlasma',
             'Torpedo160mmPlasmaAtt', 'Torpedo190mmImprovised', 'Torpedo220mmBelter',
             'Torpedo220mmHekp', 'Plasma220mmTorp', 'TrailerTorp']

    print('=' * 108)
    print('STAGE TABLE  (accel = AccelPerSec * AccelMulti; cap = SpeedCapMulti * MaxSpeed)'.center(108))
    print('=' * 108)
    print('%-24s %-3s %-9s %-8s %-34s %s' % ('torpedo', '#', 'accel', 'cap', 'ends when', 'note'))
    print('-' * 108)
    for k in order:
        p = PROFILES[k]
        for s in p['stages']:
            e = [c for c in s['end_conditions'] if c[0] != 'Ignore']
            desc = ' & '.join('%s %g %s' % (c[0], c[1], c[2]) for c in e) or '(unconditional)'
            note = 'IMMEDIATE - values never apply' if s['ends_immediately'] else \
                   ('coast, no thrust/steering' if s['accel_multi'] == 0 else '')
            print('%-24s %-3d %-9.1f %-8.0f %-34s %s' % (
                k if s['index'] == 0 else '', s['index'], s['accel_mps2'],
                s['speed_cap_mps'], desc[:34], note))
        print('-' * 108)

    print()
    print('=' * 108)
    print('FLIGHT — fired head-on from 15 km, stationary target, stationary launcher'.center(108))
    print('=' * 108)
    print('%-24s %6s %8s %8s %8s %9s %9s %s' % (
        'torpedo', 'peak', 't@3km', 't@1km', 'impact', '3km->hit', '1km->hit', 'ends'))
    print('-' * 108)
    nan = float('nan')
    for k in order:
        r = fly(k, 15000.0)
        t3, t1, ti = r['marks'][3000.0], r['marks'][1000.0], r['impact']
        e3 = (ti - t3) if (ti and t3) else nan
        e1 = (ti - t1) if (ti and t1) else nan
        print('%-24s %6.0f %7.2fs %7.2fs %7.2fs %8.2fs %8.2fs %s' % (
            k, r['peak'], t3 or nan, t1 or nan, ti or nan, e3, e1,
            r['end'] or 'impact'))
    print()
    print('  3km->hit is the PDC exposure window over a 3 km engagement envelope.')
    print('  Old flat-260 model gave (3000-150)/260 = %.1f s.' % ((3000 - 150) / 260.0))

    print()
    print('=' * 108)
    print('LAUNCH RANGE SWEEP — does it arrive at all?  (CPA, m)'.center(108))
    print('=' * 108)
    ranges = (5000, 10000, 15000, 20000, 23000, 24000)
    print('%-24s' % 'torpedo' + ''.join('%10s' % ('%dkm' % (r // 1000)) for r in ranges))
    print('-' * 108)
    for k in order:
        row = '%-24s' % k
        for R in ranges:
            r = fly(k, float(R))
            row += '%10s' % (('%.0f' % r['cpa']) if r['cpa'] < 500 else 'MISS')
        print(row)
    print('  MaxTrajectory counts PATH length (Projectiles.cs:311-312), so a weaving')
    print('  round fired at its nominal 24 km reach dies short of the target.')

    print()
    print('=' * 108)
    print('REACH — what actually terminates the round'.center(108))
    print('=' * 108)
    print('%-24s %10s %10s %12s %12s %s' % (
        'torpedo', 'life(t)', 'life(s)', 'reach@life', 'MaxTraj', 'binds'))
    print('-' * 108)
    for k in order:
        p = PROFILES[k]
        v = p['terminal_speed']
        ls = p['life_ticks'] / 60.0
        reach = v * ls
        binds = 'MaxTrajectory' if p['max_traj'] <= reach else 'MaxLifeTime'
        print('%-24s %10d %9.1fs %11.0fm %11.0fm %s' % (
            k, p['life_ticks'], ls, reach, p['max_traj'], binds))

    print()
    print('=' * 108)
    print('GUIDANCE LAW — real PN (N=Aggressiveness=3) vs v2\'s pure pursuit'.center(108))
    print('=' * 108)
    print('  Target crossing at 90 deg, 15 km launch.  CPA in metres; MISS = never closed.')
    print('%-24s' % 'torpedo' + ''.join('%18s' % ('tgt %d m/s' % v) for v in (0, 200, 400, 650)))
    print('%-24s' % '' + ''.join('%9s%9s' % ('PN', 'pursuit') for _ in range(4)))
    print('-' * 108)
    for k in ('Torpedo160mmPlasma', 'Plasma220mmTorp', 'Torpedo190mmImprovised',
              'Torpedo220mmHekp'):
        row = '%-24s' % k
        for tv in (0, 200, 400, 650):
            for pp_ in (False, True):
                r = fly(k, 15000.0, target_vel=V(0, float(tv), 0), pure_pursuit=pp_)
                row += '%9s' % (('%.0f' % r['cpa']) if r['cpa'] < 500 else 'MISS')
        print(row)
    print('  Pure pursuit lags a crossing target; PN leads it.  Against a stationary')
    print('  target the two agree, which is why the error hid in the head-on case.')

    print()
    print('=' * 108)
    print('WEAVE — simulated displacement vs the old closed form'.center(108))
    print('=' * 108)
    print('%8s %9s %14s %14s %12s %12s' % (
        'range', 'tof', 'OLD .5*r*a*t^2', 'OLD w/ 15600', 'simulated', 'v*tof bound'))
    print('-' * 108)
    kk = 'Plasma220mmTorp'
    p = PROFILES[kk]
    a_true = [s for s in p['stages'] if s['accel_multi'] > 0][-1]['accel_mps2']
    ratio = p['smarts']['offset_ratio']
    v = p['terminal_speed']
    for R in (500, 1000, 2000, 3000, 4000, 6000):
        tof = R / 3000.0                       # 3 km/s PDC muzzle
        old_true = 0.5 * ratio * a_true * tof * tof
        old_full = 0.5 * ratio * p['accel_per_sec'] * tof * tof
        sim = weave_rms(kk, tof)
        bound = weave_bound(kk, tof)
        flag = ' <-- exceeds bound' if old_full > bound else ''
        print('%7dm %8.2fs %13.0fm %13.0fm %11.0fm %11.0fm%s' % (
            R, tof, old_true, old_full, sim, bound, flag))
    # crossover of 0.5*ratio*A*t^2 with v*t
    for label, A in (('AccelPerSec 15600', p['accel_per_sec']), ('staged accel', a_true)):
        tc = 2.0 * v / (ratio * A)
        print('  %s: exceeds v*tof past tof=%.3fs (= %.0f m at a 3 km/s muzzle)'
              % (label, tc, tc * 3000.0))
    print('  OffsetMinRange for %s is %.0f m — inside that the weave is OFF entirely.'
          % (kk, p['smarts']['offset_min_range']))
    print('  Per-torpedo simulated RMS weave at tof=1.0 s:')
    for k in order:
        pp = PROFILES[k]
        print('    %-24s ratio=%-5.2g period=%3dt minRange=%5.0fm  rms=%6.1f m'
              % (k, pp['smarts']['offset_ratio'], pp['smarts']['offset_time'],
                 pp['smarts']['offset_min_range'], weave_rms(k, 1.0)))

    print()
    print('=' * 108)
    print('CAN A HULL OUTRUN IT?  (SDX2 top speed 650 m/s)'.center(108))
    print('=' * 108)
    print('%-24s %10s %12s %s' % ('torpedo', 'terminal', 'closing', 'verdict'))
    print('-' * 108)
    for k in order:
        v = PROFILES[k]['terminal_speed']
        print('%-24s %9.0f %11.0f %s' % (
            k, v, v - 650, 'catches' if v > 650 else 'OUTRUN by a 650 m/s hull'))

    print()
    print('=' * 108)
    print('HITS TO KILL  (ceil(Health / HealthHitModifier), SessionDamageMgr.cs:1110/1151)'.center(108))
    print('=' * 108)
    print('%-24s %8s' % ('torpedo', 'Health') +
          ''.join('%12s' % ('HHM %g' % h) for h in (0.5, 1.0, 2.0, 5.0)))
    print('-' * 108)
    for k in order:
        p = PROFILES[k]
        print('%-24s %8g' % (k, p['health']) +
              ''.join('%12d' % max(1, math.ceil(p['health'] / h))
                      for h in (0.5, 1.0, 2.0, 5.0)))
    print('  Torpedo-on-target HHM is %g (what a torpedo does to another projectile).'
          % PROFILES['Plasma220mmTorp']['hhm'])

    print()
    print('=' * 108)
    print('LAUNCHER VELOCITY SCALES EVERY CAP  (MaxSpeed = |ShooterVel + dir*260|)'.center(108))
    print('=' * 108)
    print('%-24s' % 'torpedo' + ''.join('%14s' % ('shooter %d' % s)
                                        for s in (0, 100, 200, 400)))
    print('-' * 108)
    for k in ('Plasma220mmTorp', 'Torpedo160mmPlasma', 'Torpedo190mmImprovised'):
        row = '%-24s' % k
        for sv in (0, 100, 200, 400):
            r = fly(k, 15000.0, shooter_vel=V(-float(sv), 0, 0))
            row += '%12.0f  ' % r['peak']
        print(row)
    print('  A 400 m/s launcher firing forward turns a "1040 m/s" torpedo into 2600 m/s.')

    print()
    print('=' * 108)
    print('VALIDATION — tick sim vs closed-form two-phase flight (weave off)'.center(108))
    print('=' * 108)
    print('%-24s %12s %12s %10s %s' % ('torpedo', 'closed form', 'sim', 'delta', ''))
    print('-' * 108)
    for k, c, s, d, ok in validate():
        if c is None:
            print('%-24s %12s %12s %10s %s' % (k, '-', '-', '-', 'no powered stage'))
        else:
            print('%-24s %11.2fs %11.2fs %9.3fs %s' % (k, c, s, d, 'OK' if ok else 'MISMATCH'))

    print()
    print('=' * 108)
    print('AGILITY — turn radius v^2/a and max turn rate a/v per powered stage'.center(108))
    print('=' * 108)
    print('%-24s %5s %8s %9s %10s %10s' % ('torpedo', 'stage', 'v m/s', 'a m/s^2', 'radius m', 'deg/s'))
    print('-' * 108)
    for k in order:
        for s in PROFILES[k]['stages']:
            if s['accel_multi'] <= 0 or s['ends_immediately']:
                continue
            v, a = s['speed_cap_mps'], s['accel_mps2']
            print('%-24s %5d %8.0f %9.1f %10.0f %10.1f' % (
                k, s['index'], v, a, v * v / a, math.degrees(a / v)))
    print('  v2 assumed turning authority 15600 m/s^2 -> 840 deg/s.  The real cruise')
    print('  figure is 16-21 deg/s, a 40x overestimate.')


if __name__ == '__main__':
    _main()
