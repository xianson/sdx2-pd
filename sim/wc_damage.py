"""Line-faithful port of WeaponCore ``DamageGrid()``.

Source of truth
---------------
``3154371364/Data/Scripts/CoreSystems/Session/SessionDamageMgr.cs``  L369-L1010
(the per-block loop), plus ``RadiantAoe`` L1294-L1385.
Derived ammo constants:  ``Definitions/SerializedConfigs/AmmoConstants.cs``.
Armour classification:   ``Session/SessionSupport.cs`` L118-L126.
ArmorCore registration:  ``Session/SessionModHandlers.cs`` L267-L311.
Server defaults:         ``Definitions/SerializedConfigs/CoreSettings.cs`` L189-L209.

Transcribed control flow (outer i-loop over root blocks, j-loop over AoE range
rings, k-loop over the blocks in a ring):

  L436  basePool     = t.BaseDamagePool
  L461  cutoff       = AmmoDef.BaseDamageCutoff ;  useBaseCutoff = cutoff > 0
  L424  fallOff      = Const.FallOffScaling && distTraveled > Const.FallOffDistance
  L427  fallOffMult  = clamp(1-(dist-fd)/(maxTraj-fd), FallOff.MinMultipler, 1)
  L468  exit when (basePool <= 0.5 || objectsHit >= maxObjects) && !detRequested
  L488  gridSizeBuff = Enforcement.{Large,Small}GridDamageMultiplier
  L490  smallVsLargeBuff = 0.25 when a LARGE-grid shooter hits a SMALL grid and
        both Grids.Large and Grids.Small are disabled (sticky for the whole call)
  L594  DamageBlockCache[0].Add(rootBlock)   <- root is queued BEFORE RadiantAoe,
        which queues it AGAIN at hitdist 0, so the root eats primary + AoE damage
  L664  blockHp   = Integrity - AccumulatedDamage
  L665  blockDmgModifier = cubeBlockDef.GeneralDamageMultiplier
  L666  damageScale      = hits              (>1 only for VirtualBeams)
  L667  directDamageScale = Enforcement.DirectDamageModifer * hitEnt.DamageMulti
  L668  areaDamageScale   = Enforcement.AreaDamageModifer   * hitEnt.DamageMulti
  L672  EVERYTHING below is gated on
        Const.DamageScaling || blockDmgModifier != 1 || gridDamageModifier != 1
  L674  blockDmgModifier or gridDamageModifier < 1e-9  ->  blockHp = MaxValue (immune)
  L677  blockHp   = blockHp / blockDmgModifier / gridDamageModifier
  L679  if MaxIntegrity > 0 && blockHp > MaxIntegrity: basePool = 0; continue
  L687  GridScaling  -> damageScale *= LargeGridDmgScale (large) ELSE IF SmallGridDmgScale
  L698  ArmorScaling -> isArmor ? *= armor.Armor : *= armor.NonArmor
  L702                  isArmor && (Light>=0||Heavy>=0) -> *= armor.Heavy / armor.Light
  L717  CustomDamageScales -> *= modifier   (NoSkip / Exclusive / Inclusive)
  L736  GlobalDamageModifed -> direct/area/det *= BlockDamageMap modifiers
  L748  ArmorCoreActive -> direct /= (EnergyBaseDmg ? Energetic : Kinetic)Resistance
  L749                     area   /= (EnergyAreaDmg ? ...)
  L750                     det    /= (EnergyDetDmg  ? ...)
  L755  fallOff -> damageScale *= fallOffMultipler
  L761  baseScale    = damageScale * directDamageScale * smallVsLargeBuff * gridSizeBuff
  L762  scaledDamage = (useBaseCutoff ? cutoff : basePool) * baseScale
  L763  aoeScaledDmg = aoeDamageFall * (detActive?det:area)Scale * damageScale * gridSizeBuff
  L766  primary && scaledDamage <= blockHp : basePool -= scaledDamage (cutoff) else 0
  L776  primary && scaledDamage >  blockHp : deadBlock, basePool -= blockHp / baseScale
  L784  countBlocks && (primary || !SkipBlocksForAOE) -> objectsHit++
  L790  non-root blocks take AoE damage (pooled branch at L792)
  L863  !deadBlock || gridBlockCount < 2500 ? DoDamage now : DEFER ~10 ticks
  L925  applied integrity loss = scaledDamage * gridDamageModifier * blockDmgModifier
  L937  endCycle -> start detonation (--i) / earlyExit / zero the reported pool

Negative multipliers mean "disabled" and are skipped (L687-L708 guard on >= 0).

Things the source does that this port deliberately does NOT model, because they
need live game state: Defense Shields / NerdShield pool absorption (L385-L411,
L521-L560), the ``IsClient`` predicted-health cache (L664, L925-L935), deformation
(L869-L885), the projectile impulse (L857), and EWAR.  ``partial_shield`` is
exposed as a callback so the L653 early-exit can at least be exercised.
"""
import math

# ---------------------------------------------------------------- server settings
class Enforcement:
    """CoreSettings.cs L189-L209 defaults.  All 1.0 / off out of the box."""
    def __init__(self):
        self.DirectDamageModifer = 1.0          # L189 (Keen's typo preserved)
        self.AreaDamageModifer = 1.0            # L190
        self.LargeGridDamageMultiplier = 1.0    # L208
        self.SmallGridDamageMultiplier = 1.0    # L209
        self.DisableSmallVsLargeBuff = False    # L206


SETTINGS = Enforcement()

#: SessionModHandlers.AssembleArmorDefinitions sets this when any ArmorDefinition
#: declares a non-unity resistance.  SDX2's sdx_armors_Ceramic.cs does, so it is
#: True for this world -- which in turn forces AmmoConstants L1269 damageScaling
#: True for EVERY ammo, making the L672 gate a no-op here.
ARMORCORE_ACTIVE = True

GRID_SIZE_LARGE = 2.5
GRID_SIZE_SMALL = 0.5
DEFERRED_DESTROY_BLOCK_COUNT = 2500     # L863


class Falloff:                                   # AreaOfDamage falloff kinds, L622-L647
    NoFalloff = 'NoFalloff'
    Linear = 'Linear'
    Curve = 'Curve'
    InvCurve = 'InvCurve'
    Squeeze = 'Squeeze'
    Pooled = 'Pooled'
    Exponential = 'Exponential'


class AoeShape:
    Diamond = 'Diamond'
    Round = 'Round'


class SkipMode:
    NoSkip = 'NoSkip'
    Exclusive = 'Exclusive'
    Inclusive = 'Inclusive'


# ---------------------------------------------------------------- definitions
class AoeDef:
    """AreaOfDamage.ByBlockHit / .EndOfLife plus the AmmoConstants derivations.

    AmmoConstants.cs L1168/L1178: radius is forced to 0 when the section is
    disabled.  L1198-L1201: depth defaults to radius when <= 0.
    """

    def __init__(self, enable=False, damage=0.0, radius=0.0, depth=0.0,
                 falloff=Falloff.NoFalloff, shape=AoeShape.Diamond,
                 max_absorb=0.0, min_arming_time=0):
        self.enable = bool(enable)
        self.damage = float(damage)
        self.radius = float(radius) if self.enable else 0.0
        self.depth = (float(radius) if depth <= 0 else float(depth)) if self.enable else 0.0
        self.falloff = falloff
        self.shape = shape
        self.max_absorb = float(max_absorb) if max_absorb > 0 else 0.0
        self.min_arming_time = int(min_arming_time)


NO_AOE = AoeDef()


class Ammo:
    def __init__(self, name, base_damage, cutoff=0.0, energy_base=False,
                 grid_large=-1.0, grid_small=-1.0, armor=-1.0, light=-1.0, heavy=-1.0,
                 non_armor=-1.0, custom=None, skip_mode=SkipMode.NoSkip,
                 max_objects=0, max_integrity=0.0,
                 count_blocks=False, skip_blocks_for_aoe=False,
                 no_grid_or_armor_scaling=False,
                 energy_area=None, energy_det=None,
                 falloff_distance=0.0, falloff_min=1.0, max_trajectory=0.0,
                 aoe=None, det=None):
        self.name = name
        self.base_damage = float(base_damage)
        self.cutoff = float(cutoff)
        # AmmoConstants.cs L1439: energyBaseDmg = DamageType.Base != Kinetic.
        # AreaEffect / Detonation default to the Base type when not stated.
        self.energy_base = bool(energy_base)
        self.energy_area = bool(energy_base if energy_area is None else energy_area)
        self.energy_det = bool(energy_base if energy_det is None else energy_det)
        self.grid_large, self.grid_small = grid_large, grid_small
        self.armor, self.light, self.heavy, self.non_armor = armor, light, heavy, non_armor
        # CustomBlockDefinitionBasesToScales; AmmoConstants L1261 drops Modifier < 0
        self.custom = {k: v for k, v in (custom or {}).items() if v >= 0}
        self.skip_mode = skip_mode
        self.max_objects = max_objects      # 0 = unlimited
        self.max_integrity = max_integrity
        self.count_blocks = bool(count_blocks)              # ObjectsHit.CountBlocks
        self.skip_blocks_for_aoe = bool(skip_blocks_for_aoe)
        self.no_grid_or_armor_scaling = bool(no_grid_or_armor_scaling)
        self.falloff_distance = float(falloff_distance)
        self.falloff_min = float(falloff_min)
        self.max_trajectory = float(max_trajectory)
        self.aoe = aoe or NO_AOE            # AreaOfDamage.ByBlockHit
        self.det = det or NO_AOE            # AreaOfDamage.EndOfLife

    # --- AmmoConstants.cs L487 / L1269-L1277 derived flags --------------------
    @property
    def max_objects_const(self):
        """L487: MaxObjectsHit > 0 ? value : int.MaxValue."""
        return self.max_objects if self.max_objects > 0 else float('inf')

    @property
    def custom_damage_scales(self):
        """L1266: only true once at least one Modifier >= 0 was registered."""
        return len(self.custom) > 0

    @property
    def falloff_scaling(self):
        """L1274: MinMultipler > 0 && MinMultipler != 1."""
        return self.falloff_min > 0 and abs(self.falloff_min - 1.0) > 1e-6

    @property
    def armor_scaling(self):
        """L1273."""
        return (not self.no_grid_or_armor_scaling
                and (self.armor >= 0 or self.non_armor >= 0
                     or self.heavy >= 0 or self.light >= 0))

    @property
    def grid_scaling(self):
        """L1275."""
        return (not self.no_grid_or_armor_scaling
                and (self.grid_large >= 0 or self.grid_small >= 0))

    @property
    def damage_scaling(self):
        """L1269.  ArmorCoreActive alone makes this true for every ammo in SDX2."""
        return (self.falloff_scaling or self.max_integrity > 0
                or self.armor >= 0 or self.non_armor >= 0
                or self.heavy >= 0 or self.light >= 0
                or self.grid_large >= 0 or self.grid_small >= 0
                or self.custom_damage_scales or ARMORCORE_ACTIVE)


class Block:
    """One IMySlimBlock.

    ``kin_res`` / ``ene_res`` are ArmorCore ResistanceValues and only exist for
    subtypes registered by an ArmorDefinition (SessionModHandlers L309).  They
    DIVIDE the damage scale, so 0.1 means the block takes 10x damage.
    """

    def __init__(self, subtype, integrity, gdm=1.0, is_armor=False, is_heavy=False,
                 kin_res=1.0, ene_res=1.0, mass=0.0, size=(1, 1, 1)):
        self.subtype = subtype
        self.integrity = float(integrity)
        self.gdm = float(gdm)
        self.is_armor, self.is_heavy = is_armor, is_heavy
        self.kin_res, self.ene_res = float(kin_res), float(ene_res)
        self.mass = mass
        self.size = tuple(size)
        self.accumulated = 0.0

    @property
    def alive(self):
        return self.accumulated < self.integrity

    def reset(self):
        self.accumulated = 0.0

    def __repr__(self):
        return (f"<{self.subtype} {'alive' if self.alive else 'DEAD'} "
                f"{self.accumulated:,.0f}/{self.integrity:,.0f}>")


# ---------------------------------------------------------------- scale block
class Scales:
    """The L666-L761 scalar set for one (ammo, block) pair."""
    __slots__ = ('damage', 'direct', 'area', 'det', 'base', 'skip', 'immune')

    def __init__(self, damage, direct, area, det, base, skip, immune):
        self.damage, self.direct, self.area, self.det = damage, direct, area, det
        self.base, self.skip, self.immune = base, skip, immune

    def __iter__(self):                       # so `s, skip = ...` still unpacks
        return iter((self.base, self.skip))


def _scales(ammo, blk, grid_damage_modifier=1.0, large_grid=True, hits=1,
            damage_multi=1.0, small_vs_large_buff=1.0, grid_size_buff=None,
            fall_off=False, fall_off_multipler=1.0, settings=SETTINGS,
            block_damage_map=None):
    """L666-L761.  Returns a Scales; `skip` reproduces the L724 `continue`."""
    if grid_size_buff is None:
        grid_size_buff = (settings.LargeGridDamageMultiplier if large_grid
                          else settings.SmallGridDamageMultiplier)         # L488

    damage_scale = float(hits)                                             # L666
    direct = settings.DirectDamageModifer * damage_multi                   # L667
    area = settings.AreaDamageModifer * damage_multi                       # L668
    det = area                                                             # L669

    gated = (ammo.damage_scaling
             or abs(blk.gdm - 1.0) > 1e-9
             or abs(grid_damage_modifier - 1.0) > 1e-9)                    # L672

    if gated:
        if ammo.grid_scaling:                                              # L685
            if ammo.grid_large >= 0 and large_grid:                        # L687
                damage_scale *= ammo.grid_large
            elif ammo.grid_small >= 0 and not large_grid:                  # L689
                damage_scale *= ammo.grid_small

        if ammo.armor_scaling:                                             # L694
            if blk.is_armor and ammo.armor >= 0:                           # L698
                damage_scale *= ammo.armor
            elif not blk.is_armor and ammo.non_armor >= 0:                 # L700
                damage_scale *= ammo.non_armor
            if blk.is_armor and (ammo.light >= 0 or ammo.heavy >= 0):      # L702
                if blk.is_heavy and ammo.heavy >= 0:                       # L705
                    damage_scale *= ammo.heavy
                elif not blk.is_heavy and ammo.light >= 0:                 # L707
                    damage_scale *= ammo.light

        if ammo.custom_damage_scales:                                      # L712
            found = ammo.custom.get(blk.subtype)
            inclusive = ammo.skip_mode == SkipMode.Inclusive               # L718
            exclusive = ammo.skip_mode == SkipMode.Exclusive               # L719
            if (ammo.skip_mode == SkipMode.NoSkip or exclusive) and found is not None:
                damage_scale *= found                                      # L722
            elif (exclusive and found is None) or (inclusive and found is not None):
                return Scales(0.0, 0.0, 0.0, 0.0, 0.0, True, False)        # L724

        if block_damage_map:                                               # L727
            mod = block_damage_map.get(blk.subtype)
            if mod is not None:
                direct *= mod[0]                                           # L736
                area *= mod[1]                                             # L737
                det *= mod[1]                                              # L738

        if ARMORCORE_ACTIVE:                                               # L742
            # L745: only registered subtypes are in ArmorCoreBlockMap.  A block
            # with both resistances at 1.0 is never registered, so leaving them
            # at 1.0 is exactly equivalent to being absent from the map.
            if blk.kin_res != 1.0 or blk.ene_res != 1.0:
                direct /= blk.ene_res if ammo.energy_base else blk.kin_res  # L748
                area /= blk.ene_res if ammo.energy_area else blk.kin_res    # L749
                det /= blk.ene_res if ammo.energy_det else blk.kin_res      # L750

        if fall_off:                                                       # L754
            damage_scale *= fall_off_multipler

    base = damage_scale * direct * small_vs_large_buff * grid_size_buff    # L761
    return Scales(damage_scale, direct, area, det, base, False, False)


def base_scale(ammo, blk, grid_damage_modifier=1.0, direct_damage_modifier=None,
               large_grid=True, **kw):
    """Backwards-compatible wrapper: returns (baseScale, skip) for L672-L761.

    ``direct_damage_modifier`` overrides Settings.Enforcement.DirectDamageModifer.
    """
    settings = kw.pop('settings', SETTINGS)
    if direct_damage_modifier is not None:
        settings = Enforcement()
        settings.DirectDamageModifer = direct_damage_modifier
    s = _scales(ammo, blk, grid_damage_modifier=grid_damage_modifier,
                large_grid=large_grid, settings=settings, **kw)
    return s.base, s.skip


# ---------------------------------------------------------------- grid geometry
class BlockGrid:
    """A cube map for the AoE path.  Port of RadiantAoe, L1294-L1385.

    ``cubes`` maps every occupied cell to its Block; a multi-cell block appears
    under each of its cells, exactly as MyCubeGrid.TryGetCube behaves.
    """

    def __init__(self, cubes, grid_size=GRID_SIZE_LARGE, general_damage_modifier=1.0):
        self.cubes = dict(cubes)
        self.grid_size = float(grid_size)
        self.grid_size_r = 1.0 / float(grid_size)
        self.general_damage_modifier = float(general_damage_modifier)
        self.large = abs(grid_size - GRID_SIZE_LARGE) < 1e-9
        xs = [c[0] for c in self.cubes] or [0]
        ys = [c[1] for c in self.cubes] or [0]
        zs = [c[2] for c in self.cubes] or [0]
        self.min = (min(xs), min(ys), min(zs))
        self.max = (max(xs), max(ys), max(zs))
        self._extent = {}
        for cell, blk in self.cubes.items():
            lo, hi = self._extent.get(id(blk), (cell, cell))
            self._extent[id(blk)] = (tuple(map(min, lo, cell)),
                                     tuple(map(max, hi, cell)))

    def radiant_aoe(self, root_pos, radius, depth, shape, dbc, hit_axis=2,
                    destroyed=None):
        """L1294-L1385.  Fills `dbc` (list of lists indexed by hitdist).

        Returns (maxDbc, foundSomething).  `hit_axis` replaces the L1310-L1334
        ray/face solve: 0=x, 1=y, 2=z is the axis the shot came in along.
        """
        destroyed = destroyed if destroyed is not None else set()
        if depth <= 0 or radius <= 0:                                      # L1299
            return 0, False

        radius *= self.grid_size_r                                         # L1302
        depth *= self.grid_size_r                                          # L1303
        maxradius = int(math.floor(radius))                                # L1304
        maxdepth = int(math.ceil(depth))                                   # L1305
        mn = [max(root_pos[a] - maxradius, self.min[a]) for a in range(3)]  # L1306
        mx = [min(root_pos[a] + maxradius, self.max[a]) for a in range(3)]  # L1307

        if depth < radius:                                                 # L1310
            mn[hit_axis] = root_pos[hit_axis] - maxdepth + 1               # L1322
            mx[hit_axis] = root_pos[hit_axis] + maxdepth - 1               # L1323

        max_dbc, found = 0, False
        for i in range(mn[0], mx[0] + 1):
            for j in range(mn[1], mx[1] + 1):
                for k in range(mn[2], mx[2] + 1):
                    cell = (i, j, k)
                    if shape == AoeShape.Diamond:                          # L1345
                        hitdist = sum(abs(cell[a] - root_pos[a]) for a in range(3))
                    else:                                                  # L1348
                        hitdist = int(_round_half_away(math.sqrt(
                            sum((root_pos[a] - cell[a]) ** 2 for a in range(3)))))
                    if hitdist > maxradius:                                # L1350
                        continue
                    blk = self.cubes.get(cell)
                    if blk is None:
                        continue
                    if not blk.alive or blk in destroyed:                  # L1357
                        continue
                    lo, hi = self._extent[id(blk)]
                    if lo != hi:                                           # L1359 multi-cell
                        if not _multicell_reach(lo, hi, root_pos, cell):
                            continue
                    while len(dbc) <= hitdist:
                        dbc.append([])
                    dbc[hitdist].append(blk)                               # L1373
                    found = True
                    if hitdist > max_dbc:
                        max_dbc = hitdist                                  # L1377
        return max_dbc, found


def _round_half_away(x):
    """C# Math.Round default is banker's rounding; Math.Round(double) on a
    non-negative distance ties are vanishingly rare, but match MidpointRounding
    .ToEven to be safe."""
    f = math.floor(x)
    d = x - f
    if d > 0.5:
        return f + 1
    if d < 0.5:
        return f
    return f if int(f) % 2 == 0 else f + 1


def _multicell_reach(lo, hi, root_pos, cell):
    """L1359-L1372: inflate a 1-cell box at the root until it touches the block's
    bounds, inflate once more, and require the candidate cell to sit inside."""
    rlo, rhi = list(root_pos), list(root_pos)

    def disjoint():
        return any(rhi[a] < lo[a] or rlo[a] > hi[a] for a in range(3))

    if all(lo[a] <= root_pos[a] <= hi[a] for a in range(3)):               # L1364
        rlo = [max(rlo[a], lo[a]) for a in range(3)]
        rhi = [min(rhi[a], hi[a]) for a in range(3)]
    else:
        guard = 0
        while disjoint() and guard < 512:                                  # L1367
            rlo = [v - 1 for v in rlo]
            rhi = [v + 1 for v in rhi]
            guard += 1
    rlo = [v - 1 for v in rlo]                                             # L1370
    rhi = [v + 1 for v in rhi]
    return all(rlo[a] <= cell[a] <= rhi[a] for a in range(3))              # L1371


# ---------------------------------------------------------------- damage loop
def damage_grid(ammo, block_list, grid=None, root_cells=None,
                grid_damage_modifier=1.0, large_grid=True, grid_block_count=0,
                objects_hit=0, dist_traveled=0.0, hits=1, damage_multi=1.0,
                relative_age=10 ** 9, attacker_grid_large=None,
                settings=SETTINGS, block_damage_map=None, partial_shield=None,
                hit_axis=2, do_damage=True):
    """Full port of DamageGrid's i/j/k loop, L436-L1006.

    ``block_list`` is the penetration column (one entry per root block, in the
    order the ray meets them).  Pass ``grid`` + ``root_cells`` to enable the AoE
    path; without them the loop degenerates to primary damage only, which is what
    every non-AoE round does anyway.
    """
    base_pool = ammo.base_damage                                           # L436
    cutoff = ammo.cutoff                                                   # L461
    use_cutoff = cutoff > 0                                                # L462
    max_objects = ammo.max_objects_const                                   # L419
    count_blocks = ammo.count_blocks                                       # L443
    skip_for_aoe = ammo.skip_blocks_for_aoe

    fall_off = ammo.falloff_scaling and dist_traveled > ammo.falloff_distance   # L424
    fall_off_mult = 1.0
    if fall_off and ammo.max_trajectory > ammo.falloff_distance:           # L427
        fall_off_mult = min(1.0, max(ammo.falloff_min,
                                     1.0 - (dist_traveled - ammo.falloff_distance)
                                     / (ammo.max_trajectory - ammo.falloff_distance)))

    has_aoe = ammo.aoe.enable                                              # L448
    has_det = ammo.det.enable and relative_age >= ammo.det.min_arming_time  # L449

    grid_size_buff = (settings.LargeGridDamageMultiplier if large_grid
                      else settings.SmallGridDamageMultiplier)             # L488
    small_vs_large = 1.0                                                   # L460

    det_requested = det_active = early_exit = False                        # L453-L455
    destroyed = 0                                                          # L456
    destroyed_slims = set()                                                # _destroyedSlims
    deferred = []                                                          # DeferredBlockDestroy
    log, kills, aoe_log = [], [], []
    dmg_pri = dmg_aoe_total = 0.0
    touched = 0

    def apply(blk, amount):
        """L865 block.DoDamage -> L925 realDmg = dmg * gridMod * blockMod."""
        if not do_damage:
            return
        blk.accumulated = min(blk.integrity,
                              blk.accumulated + amount * grid_damage_modifier * blk.gdm)

    i = 0
    spin = 0
    while i < len(block_list):
        spin += 1
        if spin > 1_000_000:
            break
        if early_exit or ((base_pool <= 0.5 or objects_hit >= max_objects)
                          and not det_requested):                          # L468
            base_pool = 0.0
            break
        elif has_det and objects_hit >= max_objects and skip_for_aoe:      # L473
            base_pool = 0.0

        root = block_list[i]                                               # L478
        if grid_damage_modifier <= 0:                                      # L482
            i += 1
            continue

        if (not settings.DisableSmallVsLargeBuff                           # L490
                and attacker_grid_large is not None
                and attacker_grid_large != large_grid
                and attacker_grid_large
                and ammo.grid_small < 0 and ammo.grid_large < 0):
            small_vs_large = 0.25                                          # L491

        aoe_absorb = aoe_depth = aoe_dmg_tally = aoe_radius = 0.0          # L493-L499
        aoe_damage = 0.0
        aoe_is_pool = False
        aoe_falloff, aoe_shape = Falloff.NoFalloff, AoeShape.Diamond

        if has_aoe and not det_requested:                                  # L501
            aoe_damage = ammo.aoe.damage
            aoe_radius = ammo.aoe.radius
            aoe_falloff = ammo.aoe.falloff
            aoe_absorb = ammo.aoe.max_absorb
            aoe_depth = ammo.aoe.depth
            aoe_shape = ammo.aoe.shape
            aoe_is_pool = aoe_falloff == Falloff.Pooled                    # L509
        elif has_det and det_requested:                                    # L511
            aoe_damage = ammo.det.damage
            aoe_radius = ammo.det.radius
            aoe_falloff = ammo.det.falloff
            aoe_absorb = ammo.det.max_absorb
            aoe_depth = ammo.det.depth
            aoe_shape = ammo.det.shape
            aoe_is_pool = aoe_falloff == Falloff.Pooled                    # L519

        if not det_requested:                                              # L562
            if root in destroyed_slims:                                    # L564
                i += 1
                continue
            if not root.alive:                                             # L567
                destroyed += 1
                destroyed_slims.add(root)
                i += 1
                continue

        max_aoe_distance = 0                                               # L590
        found_aoe = False
        dbc = [[]]
        if not det_requested:
            dbc[0].append(root)                                            # L594

        if ((has_aoe and aoe_damage > 0.5) and not det_requested) or (has_det and det_requested):  # L598
            det_requested = False                                          # L600
            if grid is not None and root_cells is not None:                # L601
                max_aoe_distance, found_aoe = grid.radiant_aoe(
                    root_cells[i], aoe_radius, aoe_depth, aoe_shape, dbc,
                    hit_axis=hit_axis, destroyed=destroyed_slims)

        block_stages = max_aoe_distance + 1                                # L609
        while len(dbc) < block_stages:
            dbc.append([])
        restart_same_root = False

        for j in range(block_stages):                                      # L610
            if early_exit or (det_active and det_requested):               # L613
                break

            aoe_damage_fall = 0.0                                          # L617
            if (has_aoe and aoe_damage > 0.5) or (has_det and det_active):  # L618
                gsr = grid.grid_size_r if grid is not None else (
                    1.0 / GRID_SIZE_LARGE if large_grid else 1.0 / GRID_SIZE_SMALL)
                maxfalldist = aoe_radius * gsr + 1                         # L621
                if aoe_falloff == Falloff.NoFalloff:                       # L625
                    aoe_damage_fall = aoe_damage
                elif aoe_falloff == Falloff.Linear:                        # L628
                    aoe_damage_fall = (maxfalldist - j) / maxfalldist * aoe_damage
                elif aoe_falloff == Falloff.Curve:                         # L631
                    aoe_damage_fall = aoe_damage - j / maxfalldist / (maxfalldist - j) * aoe_damage
                elif aoe_falloff == Falloff.InvCurve:                      # L634
                    aoe_damage_fall = ((maxfalldist - j) / maxfalldist
                                       * (maxfalldist - j) / maxfalldist * aoe_damage)
                elif aoe_falloff == Falloff.Squeeze:                       # L637
                    aoe_damage_fall = (j + 1) / maxfalldist / (maxfalldist - j) * aoe_damage
                elif aoe_falloff == Falloff.Pooled:                        # L640
                    aoe_damage_fall = aoe_damage
                elif aoe_falloff == Falloff.Exponential:                   # L643
                    aoe_damage_fall = 1.0 / (j + 1) * aoe_damage

            for k in range(len(dbc[j])):                                   # L649
                block = dbc[j][k]

                if partial_shield is not None and partial_shield(block):   # L653
                    early_exit = True
                if early_exit:
                    break
                if not block.alive or block in destroyed_slims:            # L659
                    continue

                block_hp = block.integrity - block.accumulated             # L664
                block_dmg_modifier = block.gdm                             # L665

                gated = (ammo.damage_scaling
                         or abs(block_dmg_modifier - 1.0) > 1e-9
                         or abs(grid_damage_modifier - 1.0) > 1e-9)        # L672
                if gated:
                    if block_dmg_modifier < 1e-9 or grid_damage_modifier < 1e-9:
                        block_hp = float('inf')                            # L675 immune
                    else:
                        block_hp = block_hp / block_dmg_modifier / grid_damage_modifier  # L677
                    if ammo.max_integrity > 0 and block_hp > ammo.max_integrity:  # L679
                        base_pool = 0.0                                    # L681
                        continue                                           # L682

                sc = _scales(ammo, block, grid_damage_modifier=grid_damage_modifier,
                             large_grid=large_grid, hits=hits, damage_multi=damage_multi,
                             small_vs_large_buff=small_vs_large,
                             grid_size_buff=grid_size_buff, fall_off=fall_off,
                             fall_off_multipler=fall_off_mult, settings=settings,
                             block_damage_map=block_damage_map)
                if sc.skip:                                                # L724
                    continue

                root_step = (k == 0 and j == 0 and not det_active)         # L758
                primary = root_step and block is root and not det_active   # L759

                base = sc.base                                             # L761
                scaled_damage = (cutoff if use_cutoff else base_pool) * base   # L762
                aoe_scaled = (aoe_damage_fall * (sc.det if det_active else sc.area)
                              * sc.damage * grid_size_buff)                # L763
                dead_block = False                                         # L764

                if primary and scaled_damage <= block_hp:                  # L766
                    dmg_pri += scaled_damage
                    if use_cutoff:
                        base_pool -= scaled_damage                         # L770
                    else:
                        base_pool = 0.0                                    # L772
                    det_requested = has_det                                # L774
                elif primary:                                              # L776
                    dmg_pri += scaled_damage
                    dead_block = True                                      # L779
                    scale = base if base != 0.0 else 0.0000001             # L780
                    base_pool -= block_hp / scale                          # L781

                if count_blocks and (primary or not skip_for_aoe):         # L784
                    objects_hit += 1
                if objects_hit >= max_objects and primary:                 # L786
                    det_requested = has_det

                if (not root_step and (has_aoe or has_det) and aoe_damage >= 0
                        and aoe_damage_fall >= 0 and not dead_block):      # L790
                    if aoe_is_pool:                                        # L792
                        scale = sc.damage if sc.damage != 0.0 else 0.0000001   # L794
                        if aoe_absorb > 0:                                 # L810
                            aoe_scaled = (aoe_absorb * (sc.det if det_active else sc.area)
                                          * sc.damage)                     # L812
                        if aoe_damage < aoe_scaled and block_hp >= aoe_damage:  # L798/L813
                            aoe_scaled = aoe_damage
                        elif block_hp <= aoe_scaled:                       # L802/L817
                            aoe_scaled = block_hp
                            dead_block = True
                        aoe_damage -= aoe_scaled / scale                   # L807/L822
                    aoe_dmg_tally += min(aoe_scaled, block_hp)             # L826
                    scaled_damage = aoe_scaled                             # L827
                    if not aoe_is_pool and scaled_damage > block_hp:       # L829
                        dead_block = True

                if dead_block:                                             # L834
                    destroyed += 1
                    destroyed_slims.add(block)

                if primary:
                    touched += 1
                    log.append((i, block.subtype,
                                min(scaled_damage, block_hp), dead_block))
                    if dead_block:
                        kills.append(i)
                elif scaled_damage > 0:
                    aoe_log.append((j, block.subtype,
                                    min(scaled_damage, block_hp), dead_block))

                if not dead_block or grid_block_count < DEFERRED_DESTROY_BLOCK_COUNT:  # L863
                    apply(block, scaled_damage)
                else:
                    deferred.append((block, scaled_damage))                # L902

                # L937
                end_cycle = ((not found_aoe and base_pool <= 0)
                             or (not root_step
                                 and ((aoe_dmg_tally >= aoe_absorb and aoe_absorb != 0
                                       and not aoe_is_pool)
                                      or aoe_damage <= 0.5))
                             or (not skip_for_aoe and objects_hit >= max_objects)
                             or (skip_for_aoe and root_step))
                if end_cycle:                                              # L942
                    if det_requested and not det_active:                   # L944
                        det_active = True                                  # L947
                        restart_same_root = True                           # L949 --i
                        break
                    if det_active:                                         # L953
                        early_exit = True                                  # L956
                        break

            if restart_same_root or early_exit:
                break

        if aoe_dmg_tally > 0:
            dmg_aoe_total += aoe_dmg_tally                                 # L976
        if not restart_same_root:
            i += 1

    if not count_blocks:                                                   # L1000
        objects_hit += 1

    return dict(log=log, kills=kills, touched=touched, objects_hit=objects_hit,
                pool_left=max(0.0, base_pool), destroyed=destroyed,
                deferred=deferred, aoe_log=aoe_log,
                damage_primary=dmg_pri, damage_aoe=dmg_aoe_total)


def fire(ammo, column, grid_damage_modifier=1.0, **kw):
    """Fire one projectile down `column` (front to back).  Mutates accumulated.

    Thin wrapper on damage_grid for the pure-penetration case; kept for the
    existing callers.
    """
    return damage_grid(ammo, column, grid_damage_modifier=grid_damage_modifier, **kw)


# ---------------------------------------------------------------- SDX2 fixtures
def sdx_blocks():
    """Verified against the shipped .sbc data (integrity = sum(count*MaxIntegrity)).

    LargeHeavyBlockArmorBlock: SDX2's ModAdjuster REPLACES the vanilla recipe with
      15 SteelPlate (100) + 50 MetalGrid (30) + 104 sdx_componentTitaniumPlate (130)
      = 16,520  -- 2815514917/Data/ModAdjuster/CubeBlocks/KeenSoftwareHouse/
      CubeBlocks_Armor.xml L15-L19, component MaxIntegrity from
      2815514917/Data/Items/sdx_itemsComponentsTech.sbc L37+.
      GeneralDamageMultiplier 0.5 is COMMENTED OUT in both vanilla
      CubeBlocks_Armor.sbc L858 and that override L31, so gdm is the 1.0 default
      and effective HP is 16,520 -- NOT 33,000.
    sdx_armorCeramic: 22 x sdx_componentCeramicPlate (10,000) = 220,000, an
      explicit <GeneralDamageMultiplier>1</GeneralDamageMultiplier>, and
      ArmorDefinition Kind=Heavy with KineticResistance 0.1 / EnergeticResistance 1
      (2815514917/Data/CubeBlocks/Armors/sdx_armorCeramic.sbc,
       3580645761/.../CoreParts/Armors/sdx_armors_Ceramic.cs).
    """
    return {
        'light':   lambda: Block('LargeBlockArmorBlock', 2500, 1.0, True, False, mass=500),
        'heavy':   lambda: Block('LargeHeavyBlockArmorBlock', 16520, 1.0, True, True,
                                 mass=2680),
        'ceramic': lambda: Block('sdx_armorCeramic', 220000, 1.0, True, True,
                                 kin_res=0.1, ene_res=1.0, mass=7700),
        'internal': lambda: Block('Generic', 5000, 1.0, False, False, mass=500),
    }


def sdx_ammo():
    """3580645761/Data/Scripts/Mod/CoreParts/{RailAmmo,PDCAmmo,TorpedoAmmo}/.

    Note the anti-ceramic Modifier is written in the mod as an EXPRESSION,
    e.g. `Modifier = 11.6f/.3f` -- pre-divided by Armor=0.3 so that the product
    DamageScales.Armor.Armor * Modifier lands back on the intended net figure
    (11.6 for the MCRN sabot, 210 for an airburst fragment).  Both factors are
    multiplied at L698 and L722; the values below are the literal Modifier.
    """
    return {
        # --- railgun sabots: BaseDamageCutoff pool rounds, Base DamageType Energy
        'sabot100mmMcrn': Ammo('sabot100mmMcrn', 180000, cutoff=18000, energy_base=True,
                               grid_large=1.0, grid_small=1.0, armor=0.3,
                               custom={'sdx_armorCeramic': 11.6 / 0.3},
                               max_trajectory=10500.0),
        'sabot100mmUnn': Ammo('sabot100mmUnn', 120000, cutoff=20000, energy_base=True,
                              grid_large=1.0, grid_small=1.0, armor=0.3,
                              custom={'sdx_armorCeramic': 10.5 / 0.3}),
        'sabot100mmOpa': Ammo('sabot100mmOpa', 140000, cutoff=19000, energy_base=True,
                              grid_large=1.0, grid_small=1.0, armor=0.3,
                              custom={'sdx_armorCeramic': 11.0 / 0.3}),
        'sabot80mmUnn': Ammo('sabot80mmUnn', 80000, cutoff=10000, energy_base=True,
                             grid_large=1.0, grid_small=1.0, armor=0.3,
                             custom={'sdx_armorCeramic': 21.0 / 0.3}),
        'sabot80mmImprovised': Ammo('sabot80mmImprovised', 60000, cutoff=10000,
                                    energy_base=True, grid_large=1.0, grid_small=1.0,
                                    armor=0.3, custom={'sdx_armorCeramic': 21.0 / 0.3}),
        'airburstFragment': Ammo('airburst100mmUnnFragment', 24000, cutoff=1000,
                                 energy_base=True, grid_large=1.0, grid_small=1.0,
                                 armor=0.3, custom={'sdx_armorCeramic': 210.0 / 0.3}),
        # --- PDC: Kinetic, no cutoff (one block per shot), CountBlocks=false
        'PDC40mm': Ammo('PDC40mm', 1200, cutoff=0, energy_base=False,
                        grid_large=1.0, grid_small=1.5, armor=0.5),
        'PDC50mmLight': Ammo('PDC50mmLight', 1200, cutoff=0, energy_base=False,
                             grid_large=1.0, grid_small=1.5, armor=0.5),
        'PDC50mmHeavy': Ammo('PDC50mmHeavy', 6800, cutoff=0, energy_base=False,
                             grid_large=1.0, grid_small=1.5, armor=0.5),
        # --- torpedoes: BaseDamage 1 is a dummy; all the damage is ByBlockHit AoE,
        #     whose DamageType.AreaEffect is Energy -- so ceramic's KINETIC 0.1
        #     never applies to a torpedo warhead.
        'torpedo220mmPlasma': Ammo('torpedo220mmPlasma', 1, cutoff=0,
                                   energy_base=False, energy_area=True, energy_det=True,
                                   grid_large=1.0, grid_small=1.0, count_blocks=True,
                                   aoe=AoeDef(True, 75000, 11, 4, Falloff.Exponential,
                                              AoeShape.Round),
                                   det=AoeDef(True, 1, 1, 1, Falloff.Exponential,
                                              AoeShape.Diamond, min_arming_time=90)),
        'torpedo160mmPlasma': Ammo('torpedo160mmPlasma', 1, cutoff=0,
                                   energy_base=False, energy_area=True, energy_det=True,
                                   grid_large=1.0, grid_small=1.0, count_blocks=True,
                                   aoe=AoeDef(True, 50000, 6, 4, Falloff.Exponential,
                                              AoeShape.Round),
                                   det=AoeDef(True, 1, 1, 1, Falloff.Exponential,
                                              AoeShape.Diamond, min_arming_time=90)),
        'torpedo220mmBelter': Ammo('torpedo220mmBelter', 1, cutoff=0,
                                   energy_base=False, energy_area=True, energy_det=True,
                                   grid_large=1.0, grid_small=1.0,
                                   aoe=AoeDef(True, 60000, 10, 3, Falloff.Exponential,
                                              AoeShape.Round),
                                   det=AoeDef(True, 1, 1, 1, Falloff.Exponential,
                                              AoeShape.Diamond, min_arming_time=90)),
        # HEKP stage-1 warhead: EndOfLife detonation with a MaxAbsorb cap
        'hekpWarhead': Ammo('hekpWarhead', 30000, cutoff=1000, energy_base=True,
                            grid_large=1.0, grid_small=1.0, armor=1.0, light=1.0,
                            heavy=1.0, non_armor=1.0, count_blocks=True,
                            det=AoeDef(True, 40000, 3, 4, Falloff.Exponential,
                                       AoeShape.Diamond, max_absorb=120000)),
    }


def uniform_grid(nx, ny, nz, factory, grid_size=GRID_SIZE_LARGE):
    """Solid nx*ny*nz brick of `factory()` blocks, for exercising the AoE path.
    Returns (BlockGrid, column_of_blocks_along_+z, cells_of_that_column)."""
    cubes = {}
    for x in range(nx):
        for y in range(ny):
            for z in range(nz):
                cubes[(x, y, z)] = factory()
    g = BlockGrid(cubes, grid_size=grid_size)
    cx, cy = nx // 2, ny // 2
    cells = [(cx, cy, z) for z in range(nz)]
    return g, [cubes[c] for c in cells], cells


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    A, B = sdx_ammo(), sdx_blocks()

    print("=" * 96)
    print("wc_damage self-check".center(96))
    print("=" * 96)

    for aname in ('sabot100mmMcrn', 'sabot80mmUnn', 'airburstFragment', 'PDC40mm'):
        a = A[aname]
        row = []
        for bname in ('light', 'heavy', 'ceramic', 'internal'):
            s, _ = base_scale(a, B[bname]())
            row.append(f"{bname}={s:g}")
        print(f"  baseScale  {aname:<18} " + "  ".join(row))

    print()
    for aname in ('sabot100mmMcrn', 'sabot80mmUnn'):
        for bname in ('heavy', 'ceramic'):
            col = [B[bname]() for _ in range(80)]
            r = fire(A[aname], col)
            print(f"  {aname:<18} vs 80x {bname:<8} pen={r['touched']:>3}  "
                  f"kills={len(r['kills']):>3}  poolLeft={r['pool_left']:>10,.0f}")

    print()
    # torpedo AoE into a 9x9x9 heavy-armour brick
    for aname in ('torpedo220mmPlasma', 'torpedo160mmPlasma'):
        g, col, cells = uniform_grid(11, 11, 11, B['heavy'])
        r = damage_grid(A[aname], col, grid=g, root_cells=cells,
                        grid_block_count=len(g.cubes))
        print(f"  {aname:<20} AoE into 11^3 heavy: destroyed={r['destroyed']:>3}  "
              f"aoeDmg={r['damage_aoe']:>12,.0f}  splashed={len(r['aoe_log'])}")
        g, col, cells = uniform_grid(11, 11, 11, B['ceramic'])
        r = damage_grid(A[aname], col, grid=g, root_cells=cells,
                        grid_block_count=len(g.cubes))
        print(f"  {'':<20} AoE into 11^3 ceramic: destroyed={r['destroyed']:>3}  "
              f"aoeDmg={r['damage_aoe']:>12,.0f}  splashed={len(r['aoe_log'])}")
