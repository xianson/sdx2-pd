"""PDC mounts, torpedoes and flak with WeaponCore-faithful mechanics.

Sources
  WC  = 3154371364/Data/Scripts/CoreSystems/...
  SDX = 3580645761/Data/Scripts/Mod/CoreParts/...

FIRING CADENCE  (WC WeaponController.cs:378, WeaponShoot.cs:42-50)
    RateOfFire is shots per MINUTE and the engine converts it to an INTEGER tick
    period:  TicksPerShot = (uint)(3600f / RateOfFire).  Shot events therefore
    happen at 60 / TicksPerShot Hz, NOT RateOfFire/60 Hz.  The truncation is
    real and it is large for fast guns:
        RoF 2000 -> 3600/2000 = 1.8 -> 1 tick  -> 60.0 events/s  (not 33.3)
        RoF 3000 -> 3600/3000 = 1.2 -> 1 tick  -> 60.0 events/s  (not 50.0)
        RoF 1800 -> 2.0 -> 2 ticks -> 30.0/s   (exact)
    Each shot event consumes BarrelsPerShot rounds and BarrelsPerShot *
    HeatPerShot heat (WeaponShoot.cs:80,100,313), and emits BarrelsPerShot *
    TrajectilesPerBarrel projectiles (:195).

HEAT  (WC WeaponController.cs:260-380, WeaponShoot.cs:305-328)
    overheat when Heat >= MaxHeat                                  (Shoot L315)
    resume    when Heat <= MaxHeat * Cooldown                      (Ctrl L326)
        Cooldown is clamped to [0, 0.95] at CoreSystems.cs:521-522.
    DegradeRof engages at Heat >= MaxHeat*HeatThresholdStart (0.8) (Ctrl L310)
               clears  at Heat <= MaxHeat*HeatThresholdEnd  (0.4)  (Ctrl L317)
        ...but ONLY when the def sets DegradeRof=true (Ctrl L310).  PdcPgenAdv
        sets it FALSE, so that gun never degrades.
    while degraded:
        systemRate = (int)(RateOfFire * Lerp(RofAt0Heat 1.0, RofAt100Heat 0.25,
                                             Heat/MaxHeat))          (Ctrl L369-376)
        TicksPerShot = (uint)(3600 / systemRate)                     (Ctrl L378)
        -- two integer truncations, so the degraded rate is quantised too.
    -> because resume (0.822) sits ABOVE the degrade-clear threshold (0.40), an
       overheated PDC comes back at Lerp(1,0.25,0.822) = 0.3835 of nominal and
       only recovers full rate if cooling outruns heating.  CONFIRMED.
    Cooling is NOT continuous: UpdateWeaponHeat reschedules itself every 20
    ticks (Ctrl L345) and subtracts HsRate = HeatSinkRate/3 (WeaponFields L327)
    each time -- HeatSinkRate per second in the mean, in 3 lumps.
    HeatSinkRateOverheatMult multiplies HsRate while overheated *if nonzero*
    (Ctrl L270); no SDX2 def sets it, so it is 1.0 everywhere here.
    ProhibitCoolingWhenOff gates on Comp.Cube.IsWorking (Ctrl L268), i.e. on
    POWER, not on firing -- a ceased-fire but powered mount still cools.
    CONFIRMED.  (PdcPgenAdv sets it false outright.)

DISPERSION  (WC WeaponShoot.cs:198-219)  -- the port used to get this wrong.
        randomFloat1 = rnd1 * (2*dev) - dev      -> POLAR angle ~ U[-dev, +dev]
        randomFloat2 = rnd2 * 2*pi               -> azimuth   ~ U[0, 2pi)
        dir = (sin(t1)cos(t2), sin(t1)sin(t2), cos(t1)) in the muzzle frame
    The off-axis angle is |randomFloat1|, which is UNIFORM IN ANGLE, not uniform
    over the disc.  So at range R against a target of radius r:
        P(hit) = min(1, atan(r/R) / dev)          -- LINEAR in r
    The old port used (r / (R tan dev))^2, which understates every PDC hit
    probability by roughly a factor of r/(R tan dev).  At 1.5 km with the 0.1
    deg PDC and a 1.1 m torpedo that is 0.18 vs 0.42 -- a 2.4x error.
    `sample_deviation()` is the ONE place this is implemented.  Anything that
    needs a deviated shot direction calls it; there is no second copy.  (There
    used to be one in engage.py, with the OPPOSITE error -- sqrt(rnd), a uniform
    DISC -- so the two files disagreed about the same line of C#.)

MUZZLE SPEED VARIANCE  (WC Projectile.cs:257-264, AmmoConstants.cs:474)
        SpeedVariance = ammo.Trajectory.SpeedVariance.Start > 0 || .End > 0
        speedVariance = NextDouble() * (max - min) + min
        DesiredSpeed  = targetSpeed + speedVariance
    Every SDX2 PDC round carries SpeedVariance = Random(-150, +150) except the
    flak parent, which is Random(-20, +20) (sdx_ammo_PDC40mm.cs:102,
    PDC50mmHeavy.cs:101, PDC50mmLight.cs:101, PDC50mmFlak.cs:140).  The `> 0`
    test on End means the flag IS active for a symmetric range.
    The predictor does NOT know: the firing solution is built from the nominal
    DesiredSpeed, so the round arrives early or late by
        dt = d/v_actual - d/v_nominal ~= -tof * (dv / v_nominal)
    and the target has moved `v_perp * dt` off the aimpoint in that time.  So
    the miss is a 1-D displacement ALONG the target's cross-track direction of
        s = (dv / v_nominal) * v_perp * tof ,      dv ~ U[-150, +150]
    i.e. up to 5% of the lead distance, and it is ZERO for a target closing
    straight down the line of fire (a timing error then just moves the meeting
    point along that same line).  At 2 km against a 260 m/s crosser this is
    ~9 m, comparable to the whole dispersion cone -- which is why AUDIT_WEAPONS
    called it the largest unmodelled PDC-accuracy term.

ARCS  (WC MathFuncs.cs:128-296, WeaponTracking.cs:1711-1745)
    WeaponLookAt builds its frame from Up = MyPivotUp = azimuthMatrix.Up
    (WeaponController.cs:204), which for a surface-mounted turret IS the mount's
    outward normal.  Elevation is the angle between the target vector and its
    projection onto the plane perpendicular to Up (MathFuncs L165-181), so a
    target at angle theta off the normal sits at elevation 90-theta and the
    mount bears iff  90-MaxElev <= theta <= 90-MinElev.  MaxElevation < 90
    therefore does create a BLIND CONE of (90-MaxElev) along the normal.
    CONFIRMED.
    Azimuth limits are only enforced when MaxAz < 180 or MinAz > -180
    (MathFuncs L245-256); every SDX2 PDC is +/-180 so azimuth is free, but the
    fixed railguns are +/-5 az AND +/-5 el and PdcMount supports that.
    AimingTolerance is a SEPARATE firing gate on the dot product of the actual
    barrel direction against the target (WeaponTracking.cs:433), with
    AimingTolerance = cos(radians) (WeaponFields.cs:331) and <= 0 meaning 180
    deg (CoreSystems.cs:853).  It widens the mechanical arc only when the turret
    is Azimuth-only / Elevation-only or AddToleranceToTracking is set
    (WeaponTracking.cs:1725-1734) -- false for every SDX2 PDC.

LOS  (WC WeaponTracking.cs:458, 1514-1520)
    The ray runs from the SCOPE dummy, not the muzzle, and the whole check is
    throttled to once per 30 ticks per block (`Tick - Comp.LastRayCastTick > 29`).
    MuzzleCheck is false and DisableLosCheck is false on every SDX2 PDC.

TORPEDO WEAVE  (WC Projectiles/Projectile.cs:764-792, 810-826, 852-856)
    every OffsetTime ticks: RandOffsetDir = random unit perpendicular to
    Direction, scaled by OffsetRatio; beyond OffsetMinRange the command becomes
    accel*(pursuit + OffsetRatio*RandOffsetDir).
    CRITICAL CORRECTION: AccelPerSec = 260*60 = 15600 m/s^2 and DesiredSpeed =
    260, so accel*dt = 260 m/s = the whole cruise speed in ONE TICK, and L856
    re-caps the speed every tick.  The weave is therefore a bounded HEADING
    OFFSET of atan(OffsetRatio) at constant speed, re-drawn every OffsetTime
    ticks -- NOT a sustained 10,920 m/s^2 lateral acceleration.  The old port
    modelled the latter and overstated weave-induced PDC miss by ~10x.
    OffsetRatio is also per-round: 0.2 (160mm Belter), 0.32 (220mm HEKP),
    0.7 (160mm Plasma).  The port used 0.7, the worst case, for everything.

FLAK  (SDX PDCAmmo/sdx_ammo_PDC50mmFlak.cs)
    PDC50mmFlak (MaxLifeTime 1 tick, Fragments=1, ArmWhenHit)
      -> Flak50mmStage2 (SphereShape d=25, Guidance Smart but AccelPerSec=5 so
         it cannot actually steer at 3000 m/s; TimedSpawns Proximity=100,
         ParentDies, MaxSpawns 1)
      -> 45 x FlakFragment50mm (MaxTrajectory 45 m, AoE r=4 dmg=300,
         HealthHitModifier 11 vs torpedo Health 4-5, so one fragment kills).
    Net: an effectively unguided round with a 100 m proximity fuse.
"""
import functools, math, random
from vec import V
from hull2 import GRID
from components import CATALOGUE
import wc_acquire

DT = 1.0 / 60.0

# ----------------------------------------------------------- torpedo constants
# SDX TorpedoAmmo/sdx_ammo_torpedo160mmPlasma.cs:182-207 (the 0.7-ratio variant)
TORP_ACCEL = 260.0 * 60.0        # AccelPerSec  = 15600 m/s^2
TORP_CRUISE = 260.0              # DesiredSpeed
TORP_OFFSET_RATIO = 0.7          # Smarts.OffsetRatio  (0.2 / 0.32 on other rounds)
TORP_OFFSET_TIME = 30            # Smarts.OffsetTime, ticks
TORP_OFFSET_MIN_RANGE = 2500.0   # Smarts.OffsetMinRange
TORP_RADIUS = 1.1                # Shape.Diameter 2.2 / 2

FLAK_PROXIMITY = 100.0           # Flak50mmStage2 TimedSpawns.Proximity
FLAK_FRAGMENTS = 45              # Flak50mmStage2 Fragment.Fragments


# ---------------------------------------------------------------- real SDX2 stats
# Every field is transcribed from SDX CoreParts/PDC/*.cs on top of
# BasePDCDefinition.cs.  Magazine capacities come from Data/Ammo/Pdc/
# sdx_ammomagazinePdc.sbc: 40mm = 120, 50mm = 600.
_BASE = dict(
    rof=1800, barrels=1, trajectiles=1, heat_per_shot=100, max_heat=45000,
    heat_sink=400, cooldown=0.822, degrade_rof=True, prohibit_cool_off=True,
    reload_ticks=300, mags=5, mag_cap=120, shots_in_burst=0, delay_after_burst=0,
    delay_until_fire=0, delay_cease_fire=30, dev=0.1, aim_tol=60.0,
    rotate_rate=0.1309, elevate_rate=0.1309, min_az=-180, max_az=180,
    min_el=-40, max_el=90, add_tol_to_track=False,
    max_dist=3000.0, min_dist=0.0, muzzle=3000.0, hhm=1, prediction=3,
    heat_sink_overheat_mult=0.0,
    # Trajectory.SpeedVariance half-width in m/s. -150..+150 on every 40/50 mm
    # round (sdx_ammo_PDC40mm.cs:102, PDC50mmHeavy.cs:101, PDC50mmLight.cs:101);
    # the flak parent is -20..+20 (PDC50mmFlak.cs:140).
    speed_var=150.0,
)


def _pdc(**kw):
    d = dict(_BASE)
    d.update(kw)
    return d


PDC_STATS = {
    # AUDIT NOTE: this used to be a positional tuple.  Both importers
    # (defense_sim.py, pareto.py) imported it without using it, so widening it
    # to a dict of named fields breaks nothing.
    'PdcUnn': _pdc(rof=2000, heat_per_shot=90, dev=0.4, min_el=-20, max_el=80),
    'PdcUnnAdv': _pdc(rof=1200, barrels=2, heat_per_shot=90, max_heat=90000,
                      dev=0.1, min_el=-20, max_el=80),
    'PdcMcrn': _pdc(rof=1800, dev=0.1, min_el=-40, max_el=90),
    'PdcMcrnAdv': _pdc(rof=80, heat_per_shot=1200, mags=1, mag_cap=600,
                       dev=0.0, aim_tol=1.0, min_el=-20, max_el=90,
                       muzzle=4000.0, hhm=5),                 # PDC50mmHeavy
    'PdcOpa': _pdc(rof=1200, max_heat=36000, heat_sink=320, dev=0.16,
                   rotate_rate=0.1047, elevate_rate=0.1047,
                   min_el=-20, max_el=90, prediction=2),      # AimLeading Accurate
    'PdcOpaAdv': _pdc(rof=30, max_heat=18000, heat_sink=160, mags=1, mag_cap=600,
                      dev=0.0, rotate_rate=0.0785, elevate_rate=0.0785,
                      min_el=-15, max_el=90, max_dist=4000.0, min_dist=1000.0,
                      delay_until_fire=12, muzzle=3000.0, hhm=11, prediction=1,
                      speed_var=20.0),                       # PDC50mmFlak parent
    'PdcPgenAdv': _pdc(rof=3000, max_heat=70000, heat_sink=45000, cooldown=0.95,
                       degrade_rof=False, prohibit_cool_off=False,
                       reload_ticks=30, mags=5, mag_cap=600,
                       shots_in_burst=20, delay_after_burst=15,
                       delay_cease_fire=0, dev=0.075, aim_tol=15.0,
                       rotate_rate=0.13, elevate_rate=0.13,
                       min_el=-14, max_el=90, muzzle=3600.0),  # PDC50mmLight
    'PdcImprovised': _pdc(rof=900, max_heat=18000, heat_sink=160, dev=0.5,
                          rotate_rate=0.0785, elevate_rate=0.0785,
                          min_el=-30, max_el=90, prediction=1),
}
FLAK_MOUNTS = {'PdcOpaAdv'}

#: PDC_STATS key <-> the components.py catalogue handle for the same block
PDC_ALIAS = {'PdcUnn': 'pdcUnn', 'PdcUnnAdv': 'pdcUnnAdv', 'PdcMcrn': 'pdcMcrn',
             'PdcMcrnAdv': 'pdcMcrnAdv', 'PdcOpa': 'pdcOpa', 'PdcOpaAdv': 'pdcOpaAdv',
             'PdcPgenAdv': 'pdcPgenAdv'}
PDC_KIND = {}                       # block SubtypeId -> PDC_STATS key
for _k, _a in PDC_ALIAS.items():
    _s = CATALOGUE.get(_a)
    if _s:
        PDC_KIND[_s['subtype']] = _k

#: kept for callers that only wanted the muzzle speed table
PDC_MUZZLE = {k: v['muzzle'] for k, v in PDC_STATS.items()}


# ------------------------------------------------------------- shared mechanics
def ticks_per_shot(rate_of_fire):
    """WeaponController.cs:378.  `TicksPerShot = (uint)(3600f / RateOfFire)`."""
    if rate_of_fire < 1:
        rate_of_fire = 1                       # Ctrl L373-374
    return max(1, int(3600.0 / rate_of_fire))


# ---------------------------------------------------------------- part registry
# WC assigns UniquePartId sequentially in part-registration order
# (SessionTypes.cs:723-726) and derives every per-weapon RNG from it:
#   Misc.cs:76-85  CurrentSeed = int.MaxValue - w.UniquePartId
#                  AcquireRandom = new XorShiftRandomStruct((ulong)CurrentSeed)
#
# THE OLD SEEDING WAS NOT REPRODUCIBLE.  PdcMount.reset() used
#   random.Random(hash((self.kind, self.cell)) & 0xFFFFFFFF)
# and `hash()` of a tuple containing a str is SALTED PER PROCESS (PEP 456), so the
# same scenario measured 4 leakers in one process and 7 in another with no code
# change.  Every comparative number in this project that predates this line was
# produced under an unrecorded per-process seed.
#
# Because the id is a registration counter it must be RESET at the start of each
# scenario, or repeat N of a scenario inside one process gets different mounts from
# repeat 1 -- the same class of bug as torpedo2._ids.  reset_part_ids() is that
# reset and every scenario entry point calls it.  targeting.py deliberately has no
# counter of its own; it reads m.unique_part_id, so there is exactly one to reset.
_next_part_id = 0


def reset_part_ids():
    """Call once at the start of a scenario, before building any mounts."""
    global _next_part_id
    _next_part_id = 0


def _claim_part_id():
    global _next_part_id
    pid = _next_part_id
    _next_part_id += 1
    return pid


def sample_deviation(rnd, dev_rads):
    """One draw of WeaponShoot.cs:198-217.  Returns (polar, azimuth) in radians.

        randomFloat1 = rnd1 * (dev + dev) - dev     -> U[-dev, +dev]   :202-203, :214
        randomFloat2 = rnd2 * TwoPi                 -> U[0, 2pi)       :215

    `polar` is SIGNED and uniform in ANGLE across the full [-dev, +dev]; the
    off-axis magnitude is |polar|.  There is no sqrt anywhere in the source, so a
    caller that writes `dev * sqrt(rnd.random())` is sampling a uniform disc and
    will understate the near-boresight density.

    `rnd` needs only `.random()`, so a stdlib Random and the ported
    XorShiftRandomStruct-backed stream are interchangeable here.
    """
    polar = rnd.random() * (dev_rads + dev_rads) - dev_rads
    return polar, rnd.random() * 2.0 * math.pi


def deviated_dir(rnd, dev_rads, fwd, right, up):
    """`muzzle.DeviatedDir` (WeaponShoot.cs:217) built in an explicit muzzle frame.

    The source composes (r1Sin*cos(t2), r1Sin*sin(t2), cos(t1)) and rotates it by
    Matrix.CreateFromDir(muzzle.Direction), whose Forward is that direction -- so
    the z component is along the boresight and the x/y components are the two
    perpendiculars.  Reproduced directly rather than via a tangent, so the result
    stays a unit vector at any deviation.
    """
    if dev_rads <= 0.0:
        return fwd.normalized()
    t1, t2 = sample_deviation(rnd, dev_rads)
    s = math.sin(t1)
    return (fwd * math.cos(t1) + right * (s * math.cos(t2))
            + up * (s * math.sin(t2))).normalized()


N_WEAVE_PHASE = 64


@functools.lru_cache(maxsize=8192)
def _weave_residuals(tof_q, period, n_phase=N_WEAVE_PHASE):
    """Residual flight time after the LAST weave re-draw, one entry per possible
    weave phase at the moment of firing.

    A phase that yields 0.0 means NO re-draw happened during the flight -- the
    torpedo flew a straight constant-velocity leg and the PDC's linear lead was
    exact.  Collapsing this list to its mean (which an earlier revision did)
    destroys exactly that case and drives every weaving shot to p=0, so callers
    must average the HIT PROBABILITY over these residuals, not average the
    offset first.
    """
    out = []
    for j in range(n_phase):
        p = period * (j + 0.5) / n_phase
        best, i = 0.0, 0
        while True:
            s = p + i * period
            if s > tof_q:
                break
            best = max(best, tof_q - s)
            i += 1
        out.append(best)
    return tuple(out)


@functools.lru_cache(maxsize=4096)
def _weave_phase_factor(tof_q, period, n_phase=N_WEAVE_PHASE):
    """Mean of `_weave_residuals` -- the expected-value form, for diagnostics."""
    r = _weave_residuals(tof_q, period, n_phase)
    return sum(r) / len(r)


def weave_offset(tof, cruise=TORP_CRUISE, ratio=TORP_OFFSET_RATIO,
                 offset_ticks=TORP_OFFSET_TIME):
    """Expected lateral position error a weaving torpedo accumulates over a shot
    flight of `tof` seconds, relative to the constant-velocity lead the PDC
    actually uses.

    Derivation from Projectile.cs:787 / :823 / :856 --
      accel*dt (15600/60 = 260 m/s) equals the whole cruise speed, so the heading
      snaps to the commanded direction inside one tick and L856 re-caps the
      speed.  The torpedo therefore flies at `cruise` on a heading atan(ratio)
      off pursuit, i.e. with a lateral velocity component
            v_lat = cruise * ratio / sqrt(1 + ratio^2).
      That vector's azimuth is re-drawn every OffsetTime ticks.  For two
      independent uniform directions E|u1 - u2| = 4/pi, so a re-draw changes the
      lateral velocity by (4/pi) * v_lat on average.  The predictor's error is
      that jump times the flight time remaining after the LAST re-draw, averaged
      over the (uniform) weave phase at the moment of firing.

    Validated against 900-sample runs of the ported `Torpedo` above: model/sim =
    0.87 at tof 0.1 s, 0.98-1.01 over 0.2-0.5 s, 1.09 at 0.7 s, 1.20 at 1.0 s
    (the longest flight a 3 km / 3000 m/s PDC can have) and 1.25 at 2.0 s.  It
    over-predicts at long flights because it ignores the pursuit term pulling
    earlier legs' drift back out.
    """
    if tof <= 0.0:
        return 0.0
    v_lat = cruise * ratio / math.sqrt(1.0 + ratio * ratio)
    period = offset_ticks / 60.0
    factor = _weave_phase_factor(round(tof, 4), round(period, 6))
    return (4.0 / math.pi) * v_lat * factor


def _p_within(r_eff, disp_radius, offset_radius, n=48):
    """P(|dispersion offset + weave offset| <= r_eff).

    `disp_radius` is the radius the shot would land at for a polar deviation of
    exactly `dev`; the actual polar angle is uniform on [0, dev] so the radius is
    swept uniformly in ANGLE (WeaponShoot.cs:214).  `offset_radius` is an
    independent offset of fixed magnitude and uniform azimuth.
    """
    if r_eff <= 0.0:
        return 0.0
    b = offset_radius
    if disp_radius <= 0.0:                      # DeviateShotAngle == 0
        return 1.0 if b <= r_eff else 0.0
    if b <= 0.0:
        return min(1.0, r_eff / disp_radius)    # linear, not squared
    tot = 0.0
    for i in range(n):
        # midpoint rule over the uniform polar-angle fraction
        a = disp_radius * (i + 0.5) / n
        x = (r_eff * r_eff - a * a - b * b) / (2.0 * a * b)
        if x >= 1.0:
            tot += 1.0
        elif x > -1.0:
            tot += 1.0 - math.acos(x) / math.pi
    return tot / n


class PdcMount:
    """One PDC on a hull cell with an outward normal (both in hull-local space).

    `component` is the Component the shipyard actually installed in the lattice. It is
    what the own-hull LOS check has to exclude, and it is what makes the mount die when
    the block dies -- a mount with no live component cannot shoot.
    """

    def __init__(self, kind, cell, normal, name=None, component=None,
                 unique_part_id=None):
        s = PDC_STATS[kind]
        self.kind = kind
        self.spec = s
        self.name = name or f"{kind}@{cell}"
        self.cell = cell
        self.component = component
        self.normal = normal.normalized()
        # UniquePartId in registration order (SessionTypes.cs:723-726). Every
        # per-weapon RNG hangs off it, so it is assigned here and never re-derived.
        self.unique_part_id = (_claim_part_id() if unique_part_id is None
                               else unique_part_id)

        # --- cadence, WeaponController.cs:378 / WeaponShoot.cs:80,313,360-370
        self.rof = s['rof']
        self.barrels = s['barrels']
        self.trajectiles = s['trajectiles']
        self.tps = ticks_per_shot(self.rof)
        self.shots_in_burst = s['shots_in_burst']
        self.delay_after_burst = s['delay_after_burst']
        # AmmoConstants.cs:1293 -- burstMode needs the magazine to cover the burst
        self.burst_mode = (self.shots_in_burst > 0
                           and s['mag_cap'] >= self.shots_in_burst)
        self.shots_per_s = self._events_per_s(self.tps) * self.barrels
        self.projectiles_per_s = self.shots_per_s * self.trajectiles

        # --- heat
        self.heat_per_shot = s['heat_per_shot']
        self.max_heat = s['max_heat']
        self.sink = s['heat_sink']
        self.cooldown_frac = min(0.95, max(0.0, s['cooldown']))   # CoreSystems L521-522
        self.degrade_rof = s['degrade_rof']
        self.overheat_sink_mult = s['heat_sink_overheat_mult']

        # --- ammo
        self.reload_s = s['reload_ticks'] / 60.0
        self.mag_rounds = s['mags'] * s['mag_cap']

        # --- geometry / gating
        self.dev = math.radians(s['dev'])
        self.aim_tol = math.radians(180.0 if s['aim_tol'] <= 0 else s['aim_tol'])
        self.rotate_rate = s['rotate_rate']       # rad/tick
        self.elevate_rate = s['elevate_rate']
        self.az_min, self.az_max = s['min_az'], s['max_az']
        self.elev_min, self.elev_max = s['min_el'], s['max_el']
        # WeaponTracking.cs:1725-1734 -- tolerance widens the arc only for
        # single-axis turrets or when AddToleranceToTracking is set.
        single_axis = (self.az_min == self.az_max) or (self.elev_min == self.elev_max)
        self.arc_tol_deg = math.degrees(self.aim_tol) if (
            single_axis or s['add_tol_to_track']) else 0.0

        self.range = s['max_dist']
        self.min_range = s['min_dist']
        self.hhm = s['hhm']
        self.muzzle = s['muzzle']
        self.speed_var = s['speed_var']            # Trajectory.SpeedVariance half-width
        self.prediction = s['prediction']
        self.is_flak = kind in FLAK_MOUNTS

        # Fallback dead time for acquire(tgt) with no bearing supplied: the mean
        # traverse of a uniformly-random new bearing on a full-azimuth turret is pi/2
        # at RotateRate rad/tick, plus DelayUntilFire. Derived from the definition, not
        # tuned -- but it is only a STAND-IN. Pass `dir_local` and the real slew
        # (MathFuncs.cs:218-222 + the AimingTolerance gate at WeaponTracking.cs:433)
        # runs instead, which is what any new caller should do.
        self.retarget_s = (math.pi / 2.0) / max(self.rotate_rate, 1e-6) / 60.0 \
            + s['delay_until_fire'] / 60.0
        self.reset()

    def _events_per_s(self, tps):
        """Shot events per second including the ShotsInBurst / DelayAfterBurst
        duty cycle (WeaponShoot.cs:360-370 shot-reload path, :379-395 burst path).
        Both set ShootTime to max(DelayAfterBurst, TicksPerShot) after the last
        shot of a burst, so the cycle is (n-1)*tps + max(delay, tps) ticks."""
        if self.shots_in_burst > 0 and self.delay_after_burst > 0:
            cycle = (self.shots_in_burst - 1) * tps + max(self.delay_after_burst, tps)
            return self.shots_in_burst * 60.0 / cycle
        return 60.0 / tps

    # ------------------------------------------------------------------- state
    # NOTE: `RETARGET_S = 0.35` used to live here. It was invented -- no such constant
    # exists in WeaponCore -- and it stood in for "acquisition runs on a cadence",
    # which by the time targeting.py ported the real 1-in-60 awake slot and 1-in-15
    # projectile window (SessionUpdate.cs:736-757) was being charged TWICE. It is gone.
    # The two mechanisms it was conflating are both modelled, separately and for real:
    #   * acquisition cadence  -> targeting.MODEL_ACQUIRE_CADENCE / wc_acquire
    #   * mechanical slew      -> acquire(dir_local=...) at RotateRate/ElevateRate
    # `retarget_s` remains as the derived fallback for acquire() with no bearing.

    def reset(self):
        # WeaponCore gives every weapon its own RNG, seeded from UniquePartId:
        #   Misc.cs:76-85  CurrentSeed = int.MaxValue - UniquePartId
        # Same derivation here, so the stream is a function of the part id alone and
        # nothing else. The previous seed was hash((kind, cell)), which Python salts
        # per process -- see the module note on the part registry.
        self.rnd = random.Random(2147483647 - self.unique_part_id)
        #: the exact WC stream, for anything that needs to match draw-for-draw
        self.acquire_random = wc_acquire.new_acquire_random(self.unique_part_id)
        self.heat = 0.0
        self.overheated = False
        self.degraded = False
        self.rounds = self.mag_rounds
        self.reloading = 0.0
        self.target = None
        self.retarget = 0.0
        self.aim = self.normal.copy()      # current barrel direction, hull-local
        self.shots_fired = 0
        self.shots_wasted = 0
        self.time_firing = 0.0
        self._cool_accum = 0.0

    def acquire(self, tgt, dir_local=None, dt=DT):
        """Returns True if the mount is on target and may fire this tick.

        With `dir_local` supplied this runs the real thing: slew the barrel
        toward the bearing at min(RotateRate, ElevateRate) rad/tick and report
        aligned once the residual angle is inside AimingTolerance
        (WeaponTracking.cs:411-433).  Without it, fall back to a per-weapon dead
        time derived from RotateRate (see `retarget_s`).
        """
        if tgt is not self.target:
            self.target = tgt
            self.retarget = self.retarget_s
        if dir_local is None:
            if self.retarget > 0:
                self.retarget -= dt
                return False
            return True

        want = dir_local.normalized()
        c = max(-1.0, min(1.0, self.aim.dot(want)))
        ang = math.acos(c)
        step = min(self.rotate_rate, self.elevate_rate) * (dt * 60.0)
        if ang <= step:
            self.aim = want
            ang = 0.0
        elif ang > 1e-9:
            # rotate `aim` toward `want` by `step` in their common plane
            perp = (want - self.aim * c)
            n = perp.length()
            if n > 1e-12:
                perp = perp / n
                self.aim = (self.aim * math.cos(step) + perp * math.sin(step)).normalized()
                ang -= step
        return ang <= self.aim_tol

    @property
    def blind_cone_deg(self):
        return 90.0 - self.elev_max

    @property
    def full_azimuth(self):
        """MathFuncs.cs:245-256 only clamps azimuth when MaxAz < 180 or
        MinAz > -180, so +/-180 means the azimuth ring is unconstrained."""
        return self.az_max >= 180 and self.az_min <= -180

    def bears(self, dir_local):
        """True if the mount can physically point at dir_local.

        FULL-AZIMUTH TURRET (every SDX2 PDC).  `self.normal` is the mount's
        outward normal, which is MyPivotUp = azimuthMatrix.Up
        (WeaponController.cs:204) -- the axis the turret spins about.
        MathFuncs.cs:174-181 measures elevation as the angle between the target
        vector and its projection onto the plane perpendicular to that axis, so a
        bearing theta off the normal is elevation 90-theta and the mount bears
        iff 90-MaxElev <= theta <= 90-MinElev.  MaxElevation < 90 leaves a blind
        cone of (90-MaxElev) around the normal.

        LIMITED-AZIMUTH MOUNT (the +/-5 az, +/-5 el fixed railguns -- SDX
        sdx_weapon_railgun*Fixed.cs:28-43).  Here the normal is the BORESIGHT,
        not a spin axis: the arc is a small az x el box about the barrel, and the
        90-theta mapping does not apply.  Decompose the bearing against a
        reference up-vector and test the two components separately.
        """
        d = dir_local.normalized()
        c = max(-1.0, min(1.0, self.normal.dot(d)))
        theta = math.degrees(math.acos(c))

        if self.full_azimuth:
            lo = 90.0 - self.elev_max - self.arc_tol_deg
            hi = 90.0 - self.elev_min + self.arc_tol_deg
            return lo <= theta <= hi

        # boresight box
        if c <= 0.0:
            return False                          # behind the mount
        up = V(0.0, 1.0, 0.0)
        if abs(self.normal.dot(up)) > 0.9:
            up = V(0.0, 0.0, 1.0)
        up = (up - self.normal * self.normal.dot(up)).normalized()
        right = cross(up, self.normal)
        el = math.degrees(math.asin(max(-1.0, min(1.0, d.dot(up)))))
        az = math.degrees(math.atan2(d.dot(right), c))
        t = self.arc_tol_deg
        return (self.az_min - t <= az <= self.az_max + t
                and self.elev_min - t <= el <= self.elev_max + t)

    @property
    def alive(self):
        return self.component is None or self.component.alive

    def occluded(self, hull, dir_local):
        """Own-hull LOS check.

        WC casts from the SCOPE dummy (WeaponTracking.cs:1519-1520), not the
        muzzle, and only re-tests every 30 ticks per block (:458).  We model the
        scope as sitting one grid proud of the armour along the mount's outward
        normal, and treat occlusion as instantaneous -- conservative, since the
        real gun keeps firing into its own hull for up to half a second after
        the geometry changes.

        The ray must NOT start along the line of fire: that put the origin
        inside the skin for any grazing shot, so whether a mount could fire down
        its own flank depended on which side of an even-width lattice it landed
        on (nx=8 spans -4..+3, so +4 floats clear and -4 does not).

        hull2.march() is deduped and returns Components, so the only thing left
        to exclude is the mount's OWN block.
        """
        origin = V(self.cell[0] * GRID, self.cell[1] * GRID, self.cell[2] * GRID)
        origin = origin + self.normal * (GRID * 1.01)
        for comp in hull.march(origin, dir_local, max_cells=60):
            if comp is not self.component and comp.alive:
                return True
        return False

    # -------------------------------------------------------------- heat/reload
    def _rate_now(self):
        """Shots per second right now, with both integer truncations of
        WeaponController.cs:373-378 applied."""
        rof = self.rof
        if self.degraded:
            frac = min(1.0, self.heat / self.max_heat)
            rof = int(rof * (1.0 + (0.25 - 1.0) * frac))    # (int)systemRate
            if rof < 1:
                rof = 1
        return self._events_per_s(ticks_per_shot(rof)) * self.barrels

    def _cool(self, lump):
        """One UpdateWeaponHeat pass (Ctrl L268-341), which fires every 20 ticks."""
        mult = self.overheat_sink_mult if (self.overheated
                                           and self.overheat_sink_mult != 0) else 1.0
        self.heat = max(0.0, self.heat - lump * mult)
        # degrade hysteresis, Ctrl L310-323
        if self.degrade_rof and self.heat >= self.max_heat * 0.8:
            self.degraded = True
        elif self.degraded and self.heat <= self.max_heat * 0.4:
            self.degraded = False
        # overheat release, Ctrl L326
        if self.overheated and self.heat <= self.max_heat * self.cooldown_frac:
            self.overheated = False

    def step(self, dt, want_fire):
        """Advance heat/reload one step. Returns rounds actually fired."""
        shots = 0.0
        if self.reloading > 0:
            self.reloading -= dt
            if self.reloading <= 0:
                self.rounds = self.mag_rounds
        elif want_fire and not self.overheated:
            shots = min(self._rate_now() * dt, self.rounds)
            self.rounds -= shots
            self.heat += shots * self.heat_per_shot
            self.shots_fired += shots
            self.time_firing += dt
            # WeaponShoot.cs:315 -- checked immediately after the heat is added
            if self.heat >= self.max_heat:
                self.overheated = True
            if self.rounds <= 0:
                self.reloading = self.reload_s

        # cooling runs on its own 20-tick schedule (Ctrl L345), HsRate = sink/3
        self._cool_accum += dt
        while self._cool_accum >= 20.0 / 60.0:
            self._cool_accum -= 20.0 / 60.0
            self._cool(self.sink / 3.0)
        return shots

    # ------------------------------------------------------------- effectiveness
    def speed_variance_sigma(self, dist, cross_speed):
        """RMS cross-track miss from Trajectory.SpeedVariance (Projectile.cs:257-264).

        The round's DesiredSpeed is `muzzle + U[-speed_var, +speed_var]` but the firing
        solution assumes `muzzle`, so the round is early/late by
            dt = d/v_actual - d/v_nominal
        and the target has moved `cross_speed * dt` off the aimpoint.  Only the
        CROSS-TRACK component counts: if the target closes straight down the line of
        fire, a timing error just slides the meeting point along that same line and
        still hits (this is the same distinction chatter_experiment.one_shot was
        getting wrong on the railgun side).

        `dt` is expanded to first order, dt ~= -tof * u/v, exact to O(u/v)^2 = 0.25%
        at u = 150, v = 3000.  E[u^2] = speed_var^2/3 for u ~ U[-a, +a], so
            sigma = (speed_var / sqrt(3) / muzzle) * cross_speed * tof.
        """
        if self.speed_var <= 0.0 or cross_speed <= 0.0:
            return 0.0
        tof = dist / self.muzzle
        return (self.speed_var / math.sqrt(3.0) / self.muzzle) * cross_speed * tof

    def p_kill_per_shot(self, dist, torp_radius, weaving,
                        cruise=TORP_CRUISE, offset_ratio=TORP_OFFSET_RATIO,
                        offset_ticks=TORP_OFFSET_TIME, cross_speed=0.0):
        """Probability one round removes the torpedo.

        Direct-fire: the round must land inside `torp_radius` against all three
        independent error sources --
          * the DeviateShotAngle cone, uniform in POLAR ANGLE (WeaponShoot.cs:214);
          * the target's weave displacement since the last re-draw;
          * the muzzle SpeedVariance lead error (Projectile.cs:257-264), which needs
            `cross_speed` -- the component of the target's velocity PERPENDICULAR to
            this mount's line of fire.  Left at 0 it contributes nothing, which is
            correct for a purely head-on closer and wrong for anything crossing, so
            callers with the geometry to hand should pass it.
        Flak: the proximity fuse only needs to pass within FLAK_PROXIMITY; the
        45 fragments at HealthHitModifier 11 then make the kill certain against
        Health 4-5.  Flak still has to cope with the weave -- Stage2's
        AccelPerSec of 5 m/s^2 cannot steer a 3000 m/s round.
        """
        if dist < self.min_range or dist > self.range:
            return 0.0
        eff_r = FLAK_PROXIMITY if self.is_flak else torp_radius
        disp = dist * math.tan(self.dev) if self.dev > 0 else 0.0
        sv = self.speed_variance_sigma(dist, cross_speed)
        if not weaving:
            return _p_within(eff_r, disp, sv)

        # Average the HIT PROBABILITY over the weave phase, not the offset.  The
        # phases with zero residual are shots that flew inside one straight weave
        # leg, and those are the ones that actually connect.
        tof = dist / self.muzzle
        v_lat = cruise * offset_ratio / math.sqrt(1.0 + offset_ratio * offset_ratio)
        k = (4.0 / math.pi) * v_lat
        res = _weave_residuals(round(tof, 4), round(offset_ticks / 60.0, 6))
        # the weave offset and the speed-variance offset are independent; combine in
        # quadrature rather than nesting another numeric integral inside the phase sum
        return sum(_p_within(eff_r, disp, math.hypot(k * r, sv)) for r in res) / len(res)


class Torpedo:
    """Smart torpedo with the real weave, speed cap and health.

    SEEDING: `index` is the round's position within its salvo and, with `seed`, fully
    determines its weave stream. It used to be a PROCESS-GLOBAL counter (`_ids`), which
    made two back-to-back runs of the same scenario at the same seed give different
    answers -- the same defect as torpedo2.Torpedo2._ids. `_ids` is retained only as a
    fallback for callers that pass no index, and it is resettable.
    """
    _ids = 0

    @classmethod
    def reset_ids(cls):
        cls._ids = 0

    def __init__(self, pos, vel, target_ref, health=4, cruise=TORP_CRUISE,
                 accel=TORP_ACCEL, offset_ratio=TORP_OFFSET_RATIO,
                 offset_time=TORP_OFFSET_TIME,
                 offset_min_range=TORP_OFFSET_MIN_RANGE, seed=0,
                 max_life_ticks=2304, radius=TORP_RADIUS,
                 max_lateral_thrust=0.0001, index=None):
        if index is None:
            Torpedo._ids += 1
            index = Torpedo._ids
        self.index = index
        self.id = index
        self.pos, self.vel = pos.copy(), vel.copy()
        # LastPosition. The projectile-vs-projectile CCD (ProjectileHits.cs:653)
        # needs the segment the target covered this tick, not just where it is.
        self.last_pos = pos.copy()
        self.target = target_ref
        self.health = float(health)
        self.cruise, self.accel = cruise, accel
        self.offset_ratio, self.offset_time = offset_ratio, offset_time
        self.offset_min_range = offset_min_range
        self.radius = radius
        # AmmoConstants.cs:507 -- Smarts.MaxLateralThrust is unset on every SDX2
        # torpedo, and Clamp(0 -> 0.0001) makes the L823 magnitude scaling
        # always active.
        self.max_lateral_thrust = max_lateral_thrust
        # seeded from (scenario seed, index within salvo) -- NOT from a global counter
        self.rnd = random.Random((int(seed) * 7919 + int(index) * 104729) & 0xFFFFFFFF)
        self.age_ticks = 0
        self.rand_offset = V(0, 0, 0)
        self.alive = True
        # Trajectory.MaxLifeTime -- a torpedo that outlives this is defeated, not a leaker
        self.max_life_ticks = max_life_ticks
        self.expired = False

    @property
    def weaving(self):
        return (self.pos - self.target.pos).length() >= self.offset_min_range

    def step(self, dt=DT):
        self.age_ticks += 1
        self.last_pos = self.pos.copy()
        if self.age_ticks >= self.max_life_ticks:
            self.alive = False
            self.expired = True
            return (self.target.pos - self.pos).length()
        to_t = self.target.pos - self.pos
        dist = to_t.length()
        direction = self.vel.normalized() if self.vel.length() > 1e-6 else to_t.normalized()

        # Projectile.cs:766-783 -- re-draw the offset every OffsetTime ticks
        if self.offset_time > 0 and self.age_ticks % self.offset_time == 0:
            up = perpendicular(direction)
            right = cross(direction, up)
            ang = self.rnd.random() * 2 * math.pi
            self.rand_offset = (up * math.sin(ang) + right * math.cos(ang)) * self.offset_ratio

        cmd = to_t.normalized() * self.accel
        offset = False
        if dist >= self.offset_min_range:
            cmd = cmd + self.rand_offset * self.accel       # L787
            offset = True

        # Projectile.cs:811-824 -- when MaxLateralThrust < 1 the command MAGNITUDE
        # is scaled by |delta/pi - 1|; the direction is deliberately not clamped.
        if self.max_lateral_thrust < 1.0 and cmd.length() > 1e-9:
            cn = cmd.normalized()
            dot = max(-1.0, min(1.0, direction.dot(cn)))
            if offset or dot < 0.98:
                delta = math.acos(dot) or 1e-300
                if delta > self.max_lateral_thrust and dot > 0:
                    cmd = cn * (self.accel * abs(delta / math.pi - 1.0))

        self.vel = self.vel + cmd * dt
        if self.vel.length() > self.cruise:                 # L852-856
            self.vel = self.vel.normalized() * self.cruise
        self.pos = self.pos + self.vel * dt
        return dist


def perpendicular(v):
    a = V(0, 0, 1) if abs(v.z) < 0.9 else V(1, 0, 0)
    return cross(v, a).normalized()


def cross(a, b):
    return V(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


# ----------------------------------------------------------------- mount layouts
def mount_ring(kind, hull, count, ring_z_frac=0.0):
    """Distribute `count` mounts around the hull circumference at a given z fraction.

    Layout helper only: it does NOT install blocks. Prefer shipyard.build_ship(), which
    installs the real Component and hands back mounts already bound to it.
    """
    nx, ny, nz = hull.nx, hull.ny, hull.nz
    z = int(ring_z_frac * (nz // 2))
    mounts = []
    for i in range(count):
        ang = 2 * math.pi * i / count
        n = V(math.cos(ang), math.sin(ang), 0.0)
        cx = int(round(math.cos(ang) * (nx // 2)))
        cy = int(round(math.sin(ang) * (ny // 2)))
        mounts.append(PdcMount(kind, (cx, cy, z), n))
    return mounts


def mount_face(kind, hull, count, face='bow'):
    """Mounts on the bow or stern cap, normals along -Z / +Z."""
    nz = hull.nz
    z = -(nz // 2) if face == 'bow' else (nz // 2)
    n = V(0, 0, -1) if face == 'bow' else V(0, 0, 1)
    out = []
    side = int(math.ceil(math.sqrt(count)))
    for i in range(count):
        cx = (i % side) - side // 2
        cy = (i // side) - side // 2
        out.append(PdcMount(kind, (cx, cy, z), n))
    return out
