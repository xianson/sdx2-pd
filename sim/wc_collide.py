"""Port of WeaponCore's projectile-vs-projectile impact detection.

Ground truth: csdiff/collide.cs, a verbatim extraction of
  ProjectileHits.cs:601-682  (guard, bulletRadius, targetRadius, sphere-sphere CCD)
  AmmoConstants.cs:1227-1244 (CollisionShape)
compiled against the real VRage.Math.dll. Verified bit-exact by csdiff/diff_test.py.

THE TWO THINGS THIS SETTLES

1. A round can only ever hit the ONE projectile it was fired at.
   ProjectileHits.cs:601 reads `target.TargetObject as Projectile` — a single object,
   not a list. There is no proximity loop for a normal round; the only place that
   iterates `ai.LiveProjectile` is the end-of-life branch (Projectiles.cs:473), and it
   explicitly skips `info.Target.TargetObject`. So a round whose torpedo dies while it
   is still in flight hits nothing. It is unconditionally wasted, and at a 3000 m/s
   muzzle over 2500 m that is a 0.83 s / 50-tick window per round.

2. The interaction radius is enormous and comes from Shape.Diameter, which SDX2 sets
   as a TRACER LENGTH. `bulletRadius` for a LineShape is the raw Diameter (no halving,
   ProjectileHits.cs:614), and `targetRadius` in the line branch is built from the
   SHOOTER's CollisionSize, not the target's — the in-source comment calls this
   "really fucking random". Measured thresholds against a 260 m/s torpedo:
       PDC40mm / PDC50mmLight  Diameter  0.5  ->   0.5 +  2.917 =   3.417 m
       PDC50mmFlak             Diameter   25  ->    25 + 25     =  50.0   m
       PDC50mmHeavy            Diameter   80  ->    80 + 80     = 160.0   m
   A dispersion-only hit model — which is what p_kill_per_shot was — cannot see any
   of this, and it is a 47x linear difference between the two ends of the range.
"""
import math

#: Session.I.DeltaStepConst
DELTA_STEP = 1.0 / 60.0


def collision_shape(shape_is_line, diameter):
    """AmmoConstants.cs:1227-1244 -> (collision_is_line, collision_size).

    A LineShape keeps the raw Diameter; a SphereShape is halved here and then halved
    AGAIN in bullet_radius. Both are faithful to the source.
    """
    is_line = shape_is_line
    size = diameter
    if size <= 0:
        if not is_line:
            is_line = True
        size = 1.0
    elif not is_line:
        size *= 0.5
    return is_line, size


class AmmoConst:
    """The four AmmoDef.Const fields the collision path reads."""
    __slots__ = ('collision_is_line', 'collision_size', 'by_block_hit_radius',
                 'end_of_life_radius')

    def __init__(self, shape_is_line, diameter, by_block_hit_radius=0.0,
                 end_of_life_radius=0.0):
        self.collision_is_line, self.collision_size = collision_shape(
            shape_is_line, diameter)
        self.by_block_hit_radius = by_block_hit_radius
        self.end_of_life_radius = end_of_life_radius


def bullet_radius(a, is_detonate=False):
    """ProjectileHits.cs:605-624."""
    if a.collision_is_line:
        # NOTE: no 0.5 factor on this branch. That is the source, not an omission.
        return (a.end_of_life_radius if is_detonate else
                (a.by_block_hit_radius if a.by_block_hit_radius > a.collision_size
                 else a.collision_size))
    return (a.end_of_life_radius if is_detonate else
            (a.by_block_hit_radius if a.by_block_hit_radius > 0.5 * a.collision_size
             else 0.5 * a.collision_size))


def include_radius(c0, r0, c1, r1):
    """VRageMath.BoundingSphereD.Include, verified against the shipped DLL."""
    dx, dy, dz = c1[0] - c0[0], c1[1] - c0[1], c1[2] - c0[2]
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist + r1 <= r0:
        return r0
    if dist + r0 <= r1:
        return r1
    return (dist + r0 + r1) * 0.5


def target_radius(a, target_ammo, target_position, target_last_position):
    """ProjectileHits.cs:626-641.

    `a` is the SHOOTER's ammo. Its collision_size seeding the sphere in the line
    branch is the documented quirk, preserved.
    """
    if target_ammo.collision_is_line:
        return include_radius(target_position, a.collision_size,
                              target_last_position, 1.0)
    return 0.5 * target_ammo.collision_size


def hits(p_last, p_pos, t_last, t_pos, drift_vel, br, tr, delta_step=DELTA_STEP):
    """ProjectileHits.cs:643-682 -> (hit, closest_approach_dist_sqr).

    Continuous closest approach over the tick, so a round covering 50-67 m per tick
    against a metre-scale target is still resolved. `drift_vel` is
    `driftCompensationVelocity` (ProjectileHits.cs:66-68): Vector3D.Zero for a
    fragment, a smart missile, or ammo without AmmoSkipAccel; otherwise ShooterVel.
    """
    dp = (p_last[0] + drift_vel[0] * delta_step - t_last[0],
          p_last[1] + drift_vel[1] * delta_step - t_last[1],
          p_last[2] + drift_vel[2] * delta_step - t_last[2])
    dv = ((p_pos[0] - p_last[0] - t_pos[0] + t_last[0]) / delta_step,
          (p_pos[1] - p_last[1] - t_pos[1] + t_last[1]) / delta_step,
          (p_pos[2] - p_last[2] - t_pos[2] + t_last[2]) / delta_step)

    dvdv = dv[0] * dv[0] + dv[1] * dv[1] + dv[2] * dv[2]
    dpdp = dp[0] * dp[0] + dp[1] * dp[1] + dp[2] * dp[2]

    if abs(dvdv) < 1e-6:
        # speed-matched: the source treats this as the collision tick
        cad = dpdp
    else:
        dpdv = dp[0] * dv[0] + dp[1] * dv[1] + dp[2] * dv[2]
        t = -dpdv / dvdv
        t = 0.0 if t < 0.0 else (delta_step if t > delta_step else t)
        cad = dpdp + dvdv * (t * t) + 2.0 * dpdv * t

    thr = br + tr
    return cad < thr * thr, cad


#: SDX2 ammo, read from
#: workshop/content/244850/3580645761/Data/Scripts/Mod/CoreParts/PDCAmmo/*.cs
PDC_AMMO = {
    'PDC40mm':          dict(shape_is_line=True, diameter=0.5, speed=3000.0, var=150.0),
    'PDC40mmImprovised': dict(shape_is_line=True, diameter=0.5, speed=3000.0, var=150.0),
    'PDC50mmLight':     dict(shape_is_line=True, diameter=0.5, speed=3600.0, var=150.0),
    'PDC50mmHeavy':     dict(shape_is_line=True, diameter=80.0, speed=4000.0, var=150.0),
    'PDC50mmFlak':      dict(shape_is_line=True, diameter=25.0, speed=3000.0, var=20.0),
    'Flak50mmStage2':   dict(shape_is_line=False, diameter=25.0, speed=3000.0, var=20.0),
}

#: every SDX2 torpedo is LineShape at Diameter 2.2
TORPEDO_AMMO = dict(shape_is_line=True, diameter=2.2)


def threshold_for(pdc_ammo_name, torp_travel_per_tick=260.0 / 60.0):
    """Interaction radius (m) for one PDC ammo against a torpedo.

    `torp_travel_per_tick` matters because target_radius grows with it in the line
    branch: a faster torpedo is a BIGGER target, which is backwards physically but is
    what the code computes.
    """
    a = AmmoConst(**{k: v for k, v in PDC_AMMO[pdc_ammo_name].items()
                     if k in ('shape_is_line', 'diameter')})
    t = AmmoConst(**TORPEDO_AMMO)
    br = bullet_radius(a)
    tr = target_radius(a, t, (0.0, 0.0, 0.0), (torp_travel_per_tick, 0.0, 0.0))
    return br + tr, br, tr
