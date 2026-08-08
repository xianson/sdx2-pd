"""Generate catalogue.json from the shipped game data. Nothing here is hand-entered.

Sources, in override order (later wins):
  1. vanilla  SpaceEngineers/Content/Data/Components.sbc          — item MaxIntegrity/Mass
     SDX2 Core 2815514917/Data/Items/*.sbc                        — SDX2 overrides those
     (SDX2 re-defines vanilla `Thrust` 30->120 and `Detector` 4->500, so order matters)
  2. vanilla  Content/Data/CubeBlocks/*.sbc                       — block defs
     2815514917 (Core), 3580645761 (Weapons), 3580535545 (RCS Gyros)  Data/**/*.sbc
     2815514917/Data/ModAdjuster/…                                — SDX2's vanilla-block edits
  3. ../sdx2_blocks.csv                                           — resolved recipe per block
  4. 2815514917/Data/ShipCoreConfig_Groups.xml + Data/Cores/**    — the SCF ruleset
  5. the world's SCF storage ShipCoreConfig_World.xml             — the live speed cap

Derived per block:
    integrity = sum(count * item MaxIntegrity)      — exactly how SE builds BlockIntegrity
    mass      = sum(count * item Mass)              — likewise MyCubeBlockDefinition.Mass
    gdm       = <GeneralDamageMultiplier> or 1.0
    power_mw  = <MaxPowerOutput>       (Reactor/BatteryBlock, already MW)
    thrust_n  = <ForceMagnitude>       (Thrust)
    gyro_n    = <ForceMagnitude>       (Gyro)

THE RULESET NO LONGER COMES FROM ../sdx2.json. That file is a rip of lomdar's planner
and it has drifted from the mod actually installed: it omits every sdx_*Pgen* block and
sdx_torpedoLauncherMediumContinuous from the groups, omits the Battleship/Dreadnought
cores, renames the 7x7 cargo containers, invents a `sdx_shipConnectors` group and eight
torchDrives entries, and carries stale Storage budgets (Picket 24/Corvette 40/Frigate 75
where the shipped cores say 20/35/70). Groups and cores are read from the mod; sdx2.json
is kept only as a cross-check and every disagreement is emitted as a warning.

SPEED IS A MODIFIER, NOT A NUMBER. A core's <MaxSpeed> is a fraction of the world cap:
the Corvette's 0.55 means 0.55 * MaxPossibleSpeedMetersPerSecond, consumed exactly that
way at ShipCoreFramework Server/Enforcement/SpeedEnforcement.cs:541. SCF writes the cap
straight into MyEnvironmentDefinition.LargeShipMaxSpeed (Session.Definitions.cs:21-25).
`speed` stays the modifier; `speed_mps` is the number.

The CAP ITSELF is a server setting and cannot be inferred from local files. The local
single-player save's stored config (Storage/3552595651.sbm_ShipCoreFramework/
ShipCoreConfig_World.xml) says 300, but that is this machine's SP world, NOT the server
the project is about. SERVER_WORLD_SPEED below is the authoritative value and overrides
the file scan; `world_speed_source` records which one won.

Subsystem tags: `subsystem` is the sim's coarse grouping (what the hull model counts as
power/thrust/etc.). `wc_subsystem` is WeaponCore's real classification from
ValidSubSystemTarget(), which is NOT the same thing — see WC_SUBSYSTEM_NOTE.

Run:  python gen_catalogue.py     (writes catalogue.json next to this file)
"""
import csv, glob, json, os, re, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
VANILLA = r"C:\Program Files (x86)\Steam\steamapps\common\SpaceEngineers\Content\Data"
WORKSHOP = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\244850"
MODS = ['2815514917', '3580645761', '3580535545']       # Core, Weapons, RCS Gyros
SDX2 = '2815514917'
WORLD_SAVE = (r"C:\Users\slob\AppData\Roaming\SpaceEngineers\Saves\76561198083962964"
              r"\Sigma Draconis Expanse 2 Creative World 2026-08-01 1243")

#: MaxPossibleSpeedMetersPerSecond on the SERVER the project actually plays on.
#: Set to None to fall back to whatever the local save's SCF storage says.
#:
#: This is a server config value. It lives either in the server's own
#: ShipCoreConfig_World.xml or in an admin `/core setworldspeed`, and NEITHER is
#: readable from this machine. The local SP save says 300; the server is 1000. Stated
#: directly by the user, which outranks the local file scan. If the server is ever
#: re-tuned this constant is the single place to change.
#:
#: What this does NOT change: <MaxSpeed> is still a modifier, so every class scales
#: with it (Corvette 0.55 -> 550 m/s at 1000, 165 at 300).
SERVER_WORLD_SPEED = 1000.0

POWER, UTILITY, OFFENSE, THRUST, PRODUCTION, ANY = (
    'Power', 'Utility', 'Offense', 'Thrust', 'Production', 'Any')
STEERING, JUMPING = 'Steering', 'Jumping'

# TypeId -> the sim's coarse subsystem bucket. ConveyorSorter is deliberately absent:
# SDX2 uses it both for real sorters and for every WeaponCore gun, so it is resolved by
# group membership. Gyro stays UTILITY here because that is the tag hull2 uses to find
# the blocks that make torque — it is NOT what WeaponCore calls a gyro (see below).
TYPE_SUBSYSTEM = {
    'Reactor': POWER, 'BatteryBlock': POWER, 'SolarPanel': POWER,
    'WindTurbine': POWER, 'HydrogenEngine': POWER,
    'Gyro': UTILITY, 'Decoy': UTILITY,
    'LargeMissileTurret': OFFENSE, 'LargeGatlingTurret': OFFENSE,
    'SmallMissileLauncher': OFFENSE, 'SmallMissileLauncherReload': OFFENSE,
    'SmallGatlingGun': OFFENSE, 'InteriorTurret': OFFENSE, 'Warhead': OFFENSE,
    'Thrust': THRUST,
    'Refinery': PRODUCTION, 'Assembler': PRODUCTION, 'OxygenGenerator': PRODUCTION,
    'SurvivalKit': PRODUCTION,
}

# ---------------------------------------------------------------- WeaponCore truth
WC_SUBSYSTEM_NOTE = """\
There are TWO different WeaponCore classifiers and they do not agree. Getting this
wrong is why `subsystem` and `wc_subsystem` are separate fields.

(1) ACQUISITION -- how a gun picks an aimpoint. AiTargeting.cs AcquireBlock :1254-1288
    walks `system.Values.Targeting.SubSystems` in declaration order and, for each
    entry, draws from `Session.GridToBlockTypeMap[grid][bt]`. That map is built at
    SessionJobs.cs:381-451 as an EXCLUSIVE if/else-if chain -- one bucket per block:
        Production -> Power -> Offense -> Utility -> Thrust -> Steering -> Jumping
    `bt == Any` is SKIPPED inside the loop (:1265 `if (bt != Any && ...)`), and because
    the SDX2 array contains Any, `OnlySubSystems` is false (CoreSystems.cs:649-662) so
    the walk falls through to :1288 -- a uniform draw over `topMap.MyCubeBocks`.

(2) VALIDATION -- WeaponTracking.cs ValidSubSystemTarget() :1659-1690, used only by the
    FocusSubSystem terminal override (:509, :1614) and AiConstruct.cs:1175.

Four consequences the sim's `subsystem` tag does NOT capture:
  * a GYRO is Steering, not Utility. SDX2's weapons declare
    SubSystems = {Power, Utility, Offense, Thrust, Production, Any} and Steering is
    NOT in that list, so gyros are never sought deliberately - they are only ever hit
    in the final all-blocks pass, i.e. LAST. Tagging them Utility makes a sim shoot
    them SECOND.
  * a hydrogen/water TANK is IMyGasTank. It matches no branch of either classifier, so
    it lands in no bucket at all and is likewise only reachable in the final pass.
    `wc_subsystem` records that as `Any`. Tanks used to be tagged Production here.
  * ARMOUR IS NEVER AN AIMPOINT. Both `MyCubeBocks` (SessionEvents.cs:341-344) and
    GridToBlockTypeMap are built from blocks that pass `as IMyTerminalBlock`, and an
    armour cube is not one. `wc_targetable` carries this; a model that lets a gun aim
    at armour is picking a target the engine cannot pick.
  * a DECOY is the one place the two classifiers genuinely disagree. In (2) it
    satisfies EVERY BlockTypes case. In (1) it goes into exactly ONE bucket --
    `DecoyMap[fat]`, defaulting to Utility (SessionJobs.cs:404-416) and settable per
    decoy at the terminal. So a decoy is NOT a first hit for every subsystem-seeker on
    the acquisition path, which is the path that matters for target selection.
    `wc_subsystem` says 'Decoy'; consumers modelling ACQUISITION should treat it as
    Utility-by-default, and only treat it as matching-anything when modelling a
    FocusSubSystem override."""

# TypeId -> WeaponCore BlockTypes, transcribed from ValidSubSystemTarget()
WC_SUBSYSTEM = {
    'Reactor': POWER, 'BatteryBlock': POWER, 'SolarPanel': POWER,
    'WindTurbine': POWER, 'HydrogenEngine': POWER,
    'Thrust': THRUST,
    'Gyro': STEERING, 'Cockpit': STEERING, 'ShipController': STEERING,
    'JumpDrive': JUMPING,
    'Decoy': 'Decoy',                       # matches every subsystem
    'Refinery': PRODUCTION, 'Assembler': PRODUCTION, 'OxygenGenerator': PRODUCTION,
    'SurvivalKit': PRODUCTION,
    'RadioAntenna': UTILITY, 'LaserAntenna': UTILITY, 'RemoteControl': UTILITY,
    'ShipWelder': UTILITY, 'ShipGrinder': UTILITY, 'Drill': UTILITY,
    'MedicalRoom': UTILITY, 'CameraBlock': UTILITY, 'UpgradeModule': UTILITY,
    'LargeMissileTurret': OFFENSE, 'LargeGatlingTurret': OFFENSE,
    'SmallMissileLauncher': OFFENSE, 'SmallMissileLauncherReload': OFFENSE,
    'SmallGatlingGun': OFFENSE, 'InteriorTurret': OFFENSE, 'Warhead': OFFENSE,
}
WEAPON_GROUPS = {'weapons', 'pdcsAdv', 'pdcsEvenAdvWeights', 'pdcsHeavyAdvWeights',
                 'railgunsFixed', 'railgunsTurreted', 'torpedoLaunchers'}
WEAPON_NAME = re.compile(r'pdc|railgun|torpedo|missile|gatling', re.I)

# The short handles the sims use. Only the SELECTION is curated here; every number
# attached to them is read out of the game files below.
ALIASES = {
    'light':      'LargeBlockArmorBlock',
    'heavy':      'LargeHeavyBlockArmorBlock',
    'ceramic':    'sdx_armorCeramic',
    'reactor1':   'sdx_reactorFusion1x1',
    'reactor3':   'sdx_reactorFusion3x3',
    'reactor5':   'sdx_reactorFusion5x5',
    'drive5':     'sdx_driveMcrnMilitary5x5',
    'drive7':     'sdx_driveMcrnMilitary7x7',
    'rcs':        'sdx_thrusterRCSBareLG',
    'rcscomp':    'sdg_rcsGyroComputer',
    'gyro':       'sdx_gyroscopeBraced_large',
    'pdcUnn':     'sdx_pdcUnn',
    'pdcUnnAdv':  'sdx_pdcUnnAdv',
    'pdcMcrn':    'sdx_pdcMcrn',
    'pdcMcrnAdv': 'sdx_pdcMcrnAdv',
    'pdcOpa':     'sdx_pdcOpa',
    'pdcOpaAdv':  'sdx_pdcOpaAdv',
    'pdcPgenAdv': 'sdx_pdcPgenAdv',
    'railgun':    'sdx_railgunMcrnMediumFixed',
    # Cruiser and Carrier each allow ONE Turreted Railgun (42 offensive points vs the
    # fixed gun's 34); shipyard.build_ship could not build one at all until now.
    'railgun_t':  'sdx_railgunMcrnMediumTurreted',
    'torptube':   'sdx_torpedoLauncherLightTriple',
}

# ---------------------------------------------------------------------------
# `role` — an explicit functional role for the SIM, independent of both `subsystem`
# and `wc_subsystem`. It exists because hull2 used to find the torque-producing blocks
# with `subsystem == UTILITY`, which silently breaks the moment a tag is corrected.
# Keyed on TypeId, with subtype special-cases below.
# ---------------------------------------------------------------------------
TYPE_ROLE = {
    'Reactor': 'reactor', 'BatteryBlock': 'reactor', 'SolarPanel': 'reactor',
    'WindTurbine': 'reactor', 'HydrogenEngine': 'reactor',
    'Gyro': 'gyro',
    'Thrust': 'drive',
    'CubeBlock': 'armour',
    'Decoy': 'decoy',
}
#: subtype -> role, overriding TYPE_ROLE
SUBTYPE_ROLE = {
    'sdg_rcsGyroComputer': 'rcs_computer',   # a Gyro block that ONLY multiplies RCS moment
    'sdx_thrusterRCSBareLG': 'rcs',          # a Thrust block used for attitude, not drive
}

#: WeaponCore only ever picks an aimpoint from a list of IMyTerminalBlock.
#: `MyCubeBocks` (SessionEvents.cs:340-345, ToGridMap :421-427) filters
#: `myCubeBlock as IMyTerminalBlock`, and GridToBlockTypeMap (SessionJobs.cs:381-451)
#: is built by walking that same list. So ARMOUR IS NEVER AIMED AT -- it is only ever
#: eaten on the way to a functional block. TypeIds that are not terminal blocks:
NON_TERMINAL_TYPES = {'CubeBlock'}

# Blocks with kinetic/energetic resistance set by WeaponCore's damage-modifier tables
# rather than by a CubeBlock field. SDX2 ceramic is the only one that matters and its
# value is asserted by test_hifi (PDC40mm vs ceramic baseScale = 0.5/0.1).
RESISTANCE = {'sdx_armorCeramic': dict(kin_res=0.1, ene_res=1.0)}
ARMOUR = {'LargeBlockArmorBlock': dict(is_armor=True, is_heavy=False),
          'LargeHeavyBlockArmorBlock': dict(is_armor=True, is_heavy=True),
          'sdx_armorCeramic': dict(is_armor=True, is_heavy=True)}

# Synthetic stand-in for "generic ship internals". Not a game block, so it carries no
# provenance; it exists so a hull has something between the armour and the machinery.
SYNTHETIC = {
    # Stands in for the mixed bag of terminal internals (cargo, tanks, conveyors,
    # cockpits...). wc_targetable=True: those ARE IMyTerminalBlocks, so they are what a
    # gun's final all-blocks pass actually draws from.
    'internal': dict(subtype='Generic', size=[1, 1, 1], integrity=5000, mass=500,
                     subsystem=PRODUCTION, wc_subsystem=ANY,
                     role='filler', wc_targetable=True,
                     power_mw=0.0, thrust_n=0.0, gyro_n=0.0,
                     gdm=1.0, is_armor=False, is_heavy=False, kin_res=1.0, ene_res=1.0,
                     scf_weight=0, type='Synthetic', source='synthetic'),
}


# ------------------------------------------------------------------ item table
def load_items():
    """{subtype: (max_integrity, mass)}; SDX2 overrides vanilla."""
    out, prov = {}, {}
    files = [(os.path.join(VANILLA, 'Components.sbc'), 'vanilla')]
    files += [(f, '2815514917') for f in
              sorted(glob.glob(os.path.join(WORKSHOP, '2815514917', 'Data', 'Items', '*.sbc')))]
    for path, tag in files:
        if not os.path.exists(path):
            continue
        s = open(path, encoding='utf-8-sig', errors='replace').read()
        for m in re.finditer(r'<(Component|PhysicalItem)>(.*?)</\1>', s, re.S):
            b = m.group(2)
            st = re.search(r'<SubtypeId>(.*?)</SubtypeId>', b)
            mi = re.search(r'<MaxIntegrity>([\d.eE+-]+)</MaxIntegrity>', b)
            ms = re.search(r'<Mass>([\d.eE+-]+)</Mass>', b)
            if not st or not mi:
                continue
            out[st.group(1)] = (float(mi.group(1)), float(ms.group(1)) if ms else 0.0)
            prov[st.group(1)] = tag
    return out, prov


# ----------------------------------------------------------------- block table
def _defs(path):
    s = open(path, encoding='utf-8-sig', errors='replace').read()
    for m in re.finditer(r'<Definition[\s>].*?</Definition>', s, re.S):
        yield m.group(0)


def modadjuster_files(mod):
    """The XMLs ModAdjuster (mod 3017795356) actually applies for `mod`.

    It reads Data\\ModAdjuster\\ModAdjusterFiles.txt and loads only what is listed
    there, so globbing the directory is wrong in both directions: SDX2 ships
    CubeBlocks/KeenSoftwareHouse/CubeBlocks_Tools.xml which is NOT in its manifest
    (and so never applied to LargeShipGrinder/Welder/SmallBlockDrill/LargeOreDetector),
    and its manifest lists Block_Rcs.xml which is not on disk.
    """
    root = os.path.join(WORKSHOP, mod, 'Data', 'ModAdjuster')
    man = os.path.join(root, 'ModAdjusterFiles.txt')
    if not os.path.exists(man):
        return [], []
    out, missing = [], []
    for line in open(man, encoding='utf-8-sig', errors='replace'):
        rel = line.strip()
        if not rel:
            continue
        f = os.path.join(root, rel.replace(chr(92), os.sep))
        (out if os.path.exists(f) else missing).append(f if os.path.exists(f) else rel)
    return out, missing


def load_blocks():
    """{subtype: dict}. Later files override earlier fields, matching SE's load order.

    ModAdjuster patches are applied after every .sbc, because ModAdjuster is a session
    component that rewrites definitions once the definition manager is up.
    """
    paths = [(f, 'vanilla') for f in
             sorted(glob.glob(os.path.join(VANILLA, 'CubeBlocks', '*.sbc')))]
    patches = []
    for mod in MODS:
        root = os.path.join(WORKSHOP, mod, 'Data')
        paths += [(f, mod) for f in sorted(glob.glob(os.path.join(root, '**', '*.sbc'),
                                                     recursive=True))]
        ok, _ = modadjuster_files(mod)
        patches += [(f, mod + '/ModAdjuster') for f in ok]
    paths += patches
    out = {}
    for path, tag in paths:
        try:
            blocks = list(_defs(path))
        except Exception:
            continue
        for b in blocks:
            st = re.search(r'<SubtypeId>(.*?)</SubtypeId>', b)
            # several vanilla defs carry an EMPTY SubtypeId (the unnamed variant of a
            # BlockPair). Bucketing them all under '' merges unrelated blocks.
            if not st or not st.group(1).strip():
                continue
            st = st.group(1)
            d = out.setdefault(st, dict(subtype=st, source=[]))
            d['source'].append(tag)
            ty = re.search(r'<TypeId>(.*?)</TypeId>', b)
            if ty:
                d['type'] = ty.group(1).replace('MyObjectBuilder_', '')
            sz = re.search(r'<Size\s+x="(\d+)"\s+y="(\d+)"\s+z="(\d+)"', b)
            if sz:
                d['size'] = [int(sz.group(1)), int(sz.group(2)), int(sz.group(3))]
            cs = re.search(r'<CubeSize>(\w+)</CubeSize>', b)
            if cs:
                d['cube_size'] = cs.group(1)
            comps = re.findall(r'<Component\s+Subtype="([^"]+)"\s+Count="(\d+)"', b)
            if comps:
                acc = {}
                for k, n in comps:
                    acc[k] = acc.get(k, 0) + int(n)
                d['recipe_sbc'] = acc
            # a commented-out tag is NOT a value: strip XML comments before reading
            live = re.sub(r'<!--.*?-->', '', b, flags=re.S)
            for tag_name, key, cast in (('GeneralDamageMultiplier', 'gdm', float),
                                        ('ForceMagnitude', 'force', float),
                                        ('MaxPowerOutput', 'power_mw', float)):
                mm = re.search(r'<%s>([\d.eE+-]+)</%s>' % (tag_name, tag_name), live)
                if mm:
                    d[key] = cast(mm.group(1))
    return out


# ---------------------------------------------------------------- csv recipes
def load_csv_recipes():
    path = os.path.join(PARENT, 'sdx2_blocks.csv')
    out = {}
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            acc = {}
            for part in (r['components'] or '').split(';'):
                if '=' not in part:
                    continue
                k, n = part.split('=', 1)
                acc[k] = acc.get(k, 0) + int(float(n))
            if acc:
                out[r['subtype']] = dict(recipe=acc, type=r['type'], size=r['size'],
                                         mod=r['mod'], name=r['name'].strip())
    return out


# ------------------------------------------------------------------- SCF ruleset
def world_mod_ids():
    cfg = os.path.join(WORLD_SAVE, 'Sandbox_config.sbc')
    return re.findall(r'<PublishedFileId>(\d+)</PublishedFileId>',
                      open(cfg, encoding='utf-8-sig', errors='replace').read())


def live_world_speed():
    """The world cap SCF pushes into MyEnvironmentDefinition.LargeShipMaxSpeed.

    SERVER_WORLD_SPEED wins if set. Otherwise fall back to scanning the LOCAL save,
    which is only ever evidence about this machine's single-player world: two
    ShipCoreFramework builds are installed - 3552595651 (canonical, config 300) and
    3582505859 (the fork, config 1000) - and BOTH have a storage folder here because
    the save was opened with each. Only the one in Sandbox_config.sbc is loaded.

    A stored SP config is NOT evidence about a server: the server has its own config
    file and an admin `/core setworldspeed`, neither visible from here.
    Returns (speed, scf_mod_id, notes).
    """
    ids = set(world_mod_ids())
    scf = [i for i in ids
           if os.path.isdir(os.path.join(WORKSHOP, i, 'Data', 'Scripts', 'ShipCoreFramework'))]
    notes = []
    installed = [d for d in os.listdir(os.path.join(WORLD_SAVE, 'Storage'))
                 if d.endswith('.sbm_ShipCoreFramework')] \
        if os.path.isdir(os.path.join(WORLD_SAVE, 'Storage')) else []
    for d in installed:
        mid = d.split('.')[0]
        if mid not in ids:
            notes.append(f"storage for ShipCoreFramework mod {mid} exists but that mod is "
                         f"NOT in the world's mod list - ignoring it")
    if len(scf) != 1:
        notes.append(f"expected exactly one ShipCoreFramework mod loaded, found {scf}")
    speed, mid = 300.0, (scf[0] if scf else None)      # SCF's own hard default
    if mid:
        p = os.path.join(WORLD_SAVE, 'Storage', mid + '.sbm_ShipCoreFramework',
                         'ShipCoreConfig_World.xml')
        if os.path.exists(p):
            m = re.search(r'<MaxPossibleSpeedMetersPerSecond>([\d.]+)<',
                          open(p, encoding='utf-8-sig', errors='replace').read())
            if m:
                speed = float(m.group(1))
        else:
            notes.append(f"no saved world config for SCF mod {mid}; using SCF default 300")
    if SERVER_WORLD_SPEED:
        if abs(speed - SERVER_WORLD_SPEED) > 0.5:
            notes.append(
                f"world speed: using SERVER_WORLD_SPEED={SERVER_WORLD_SPEED:g} m/s, NOT the "
                f"{speed:g} in this machine's local SP save (Storage/{mid}"
                f".sbm_ShipCoreFramework/ShipCoreConfig_World.xml). The server config is "
                f"not readable from here; the local file is not evidence about it.")
        speed = SERVER_WORLD_SPEED
    return speed, mid, notes


def _core_from_xml(path):
    r = ET.parse(path).getroot()
    sm = r.find('SpeedModifiers')
    def f(tag, default=0.0):
        t = sm.findtext(tag) if sm is not None else None
        return float(t) if t not in (None, '') else default
    cats = {}
    for bl in r.findall('BlockLimits'):
        cats[bl.findtext('Name')] = dict(
            budget=float(bl.findtext('MaxCount') or 0),
            groups=[g.text for g in bl.findall('BlockGroups')],
            critical=(bl.findtext('IsCriticalLimit') == 'true'),
            directions=[d.text for d in bl.findall('AllowedDirections')])
    return dict(name=r.findtext('UniqueName'), subtype=r.findtext('SubtypeId'),
                speed=f('MaxSpeed'), boost=f('MaxBoost'),
                boost_enabled=(r.findtext('SpeedBoostEnabled') == 'true'),
                speed_limit_type=r.findtext('SpeedLimitType'),
                friction_min=f('MinimumFrictionSpeedModifier'),
                friction_max=f('MaximumFrictionSpeedModifier'),
                max_blocks=r.findtext('MaxBlocks'), max_pcu=r.findtext('MaxPCU'),
                mobility=r.findtext('MobilityType'), categories=cats, file=path)


def load_scf(blocks):
    """The real ruleset: (group_weights, cores, world_speed, warnings).

    Cores whose block recipe needs sdx_componentAdminKit are dropped - Battleship,
    Dreadnought and the Trade Station core each take 1x AdminKit, an item with
    MaxIntegrity 999,999,999 that no blueprint produces and no NPC drops, so those
    classes are not buildable by a player at all. Dropping them leaves exactly the ten
    classes lomdar's planner ships, which is a decent independent check on the filter.
    """
    warn = []
    root = os.path.join(WORKSHOP, SDX2, 'Data')

    weights = {}
    gpath = os.path.join(root, 'ShipCoreConfig_Groups.xml')
    for g in ET.parse(gpath).getroot().findall('BlockGroup'):
        gn = g.findtext('Name')
        for bt in g.findall('BlockTypes'):
            st = bt.findtext('SubtypeId')
            weights.setdefault(st, {})[gn] = float(bt.findtext('CountWeight'))
            if st not in blocks:
                warn.append(f"group {gn} lists {st!r} but no loaded mod defines that block")

    files = [ET.parse(os.path.join(root, 'ShipCoreConfig_Manifest.xml')).getroot()]
    cores = []
    for sc in files[0].findall('ShipCore'):
        p = os.path.join(WORKSHOP, SDX2, sc.findtext('Filename').replace('/', os.sep))
        if not os.path.exists(p):
            warn.append(f"core manifest lists missing file {sc.findtext('Filename')}")
            continue
        cores.append(_core_from_xml(p))
    nc = os.path.join(root, 'ShipCoreConfig_No_Core.xml')
    if os.path.exists(nc):
        cores.append(_core_from_xml(nc))

    keep = []
    for c in cores:
        rec = (blocks.get(c['subtype']) or {}).get('recipe_sbc') or {}
        if 'sdx_componentAdminKit' in rec:
            warn.append(f"core {c['name']} ({c['subtype']}) needs AdminKit - admin only, dropped")
            continue
        keep.append(c)

    speed, scf_mod, notes = live_world_speed()
    warn += notes
    warn.append(f"world speed cap {speed:g} m/s from ShipCoreFramework mod {scf_mod}; "
                f"class <MaxSpeed> values are MODIFIERS of it")

    # cross-check the ripped planner data and shout about every disagreement
    try:
        rip = json.load(open(os.path.join(PARENT, 'sdx2.json'), encoding='utf-8'))['shipCores']
    except Exception as e:
        warn.append(f"sdx2.json cross-check skipped: {e}")
        return weights, keep, speed, warn
    if float(rip.get('worldSpeed', 0)) != speed:
        warn.append(f"sdx2.json worldSpeed={rip.get('worldSpeed')} but the live cap is {speed:g}")
    rg = {g['name']: {b['subtype']: float(b['weight']) for b in g['blocks']}
          for g in rip['groups']}
    mine = {}
    for st, d in weights.items():
        for gn, w in d.items():
            mine.setdefault(gn, {})[st] = w
    for gn in sorted(set(rg) | set(mine)):
        a, b = mine.get(gn, {}), rg.get(gn, {})
        for st in sorted(set(a) | set(b)):
            if a.get(st) != b.get(st):
                warn.append(f"sdx2.json drift: group {gn} {st} mod={a.get(st)} rip={b.get(st)}")
    rc = {c['name']: c for c in rip['cores']}
    for c in keep:
        r = rc.get(c['name'])
        if r is None:
            warn.append(f"sdx2.json drift: core {c['name']} absent from the rip")
            continue
        if abs(float(r['speed']) - c['speed'] * speed) > 0.5:
            warn.append(f"sdx2.json drift: {c['name']} speed rip={r['speed']} "
                        f"live={c['speed'] * speed:g}")
        rcat = {x['name']: x for x in r['categories']}
        for cn, cv in c['categories'].items():
            rv = rcat.get(cn)
            if rv is None:
                warn.append(f"sdx2.json drift: {c['name']}/{cn} absent from the rip")
            elif float(rv['budget']) != cv['budget'] or rv['groups'] != cv['groups']:
                warn.append(f"sdx2.json drift: {c['name']}/{cn} mod={cv['budget']:g}"
                            f"{cv['groups']} rip={rv['budget']}{rv['groups']}")
    return weights, keep, speed, warn


def subsystem_for(subtype, btype, groups):
    if WEAPON_GROUPS & set(groups) or WEAPON_NAME.search(subtype):
        return OFFENSE
    return TYPE_SUBSYSTEM.get(btype, ANY)


def wc_subsystem_for(subtype, btype, groups):
    """WeaponCore's own classification. A ConveyorSorter is Offense only when it is a
    registered weapon platform, which SCF group membership is a good proxy for."""
    if btype == 'Decoy':
        return 'Decoy'
    if WEAPON_GROUPS & set(groups) or WEAPON_NAME.search(subtype):
        return OFFENSE
    return WC_SUBSYSTEM.get(btype, ANY)


def role_for(subtype, btype, groups):
    """Explicit functional role for the sim. Never derived from a subsystem tag, so
    correcting a tag cannot silently zero a hull's torque or thrust."""
    if subtype in SUBTYPE_ROLE:
        return SUBTYPE_ROLE[subtype]
    if WEAPON_GROUPS & set(groups) or WEAPON_NAME.search(subtype):
        return 'weapon'
    return TYPE_ROLE.get(btype, 'other')


def wc_targetable_for(btype):
    """Can WeaponCore pick this block as an aimpoint at all? Only IMyTerminalBlock
    survives the MyCubeBocks filter (SessionEvents.cs:341-344), so armour cannot."""
    return btype not in NON_TERMINAL_TYPES


# ------------------------------------------------------------------------ main
def build():
    items, item_src = load_items()
    blocks = load_blocks()
    csv_rec = load_csv_recipes()
    weights, cores, world_speed, scf_warn = load_scf(blocks)

    wanted = set(ALIASES.values())
    wanted |= set(weights)                       # everything the SCF ruleset can budget
    wanted |= set(ARMOUR)
    wanted.discard('')

    entries, warn, unknown_items = {}, list(scf_warn), set()
    for st in sorted(wanted):
        blk = blocks.get(st)
        rec = csv_rec.get(st, {}).get('recipe') or (blk or {}).get('recipe_sbc')
        if blk is None or not rec:
            warn.append(f"skip {st}: {'no block def' if blk is None else 'no recipe'}")
            continue
        integ = mass = 0.0
        for k, n in rec.items():
            if k not in items:
                unknown_items.add(k)
                continue
            mi, ms = items[k]
            integ += n * mi
            mass += n * ms
        btype = blk.get('type', '?')
        grp = weights.get(st, {})
        sub = subsystem_for(st, btype, grp)
        force = blk.get('force', 0.0)
        e = dict(
            subtype=st,
            name=csv_rec.get(st, {}).get('name', st),
            type=btype,
            size=blk.get('size', [1, 1, 1]),
            cube_size=blk.get('cube_size', 'Large'),
            integrity=int(round(integ)),
            mass=int(round(mass)),
            gdm=float(blk.get('gdm', 1.0)),
            power_mw=float(blk.get('power_mw', 0.0)) if sub == POWER else 0.0,
            thrust_n=force if btype == 'Thrust' else 0.0,
            gyro_n=force if btype == 'Gyro' else 0.0,
            subsystem=sub,
            wc_subsystem=wc_subsystem_for(st, btype, grp),
            role=role_for(st, btype, grp),
            wc_targetable=wc_targetable_for(btype),
            scf_weight=max(grp.values()) if grp else 0,
            scf_groups=grp,
            is_armor=ARMOUR.get(st, {}).get('is_armor', False),
            is_heavy=ARMOUR.get(st, {}).get('is_heavy', False),
            kin_res=RESISTANCE.get(st, {}).get('kin_res', 1.0),
            ene_res=RESISTANCE.get(st, {}).get('ene_res', 1.0),
            recipe=rec,
            recipe_source='sdx2_blocks.csv' if st in csv_rec else 'sbc',
            source=blk.get('source', []),
        )
        # cross-check the CSV against the sbc; a disagreement means one of them is stale
        if st in csv_rec and 'recipe_sbc' in blk and csv_rec[st]['recipe'] != blk['recipe_sbc']:
            e['recipe_disagrees_with_sbc'] = blk['recipe_sbc']
        entries[st] = e

    for k, v in SYNTHETIC.items():
        entries[v['subtype']] = dict(v, name=k, scf_groups={}, recipe={},
                                     recipe_source='synthetic', cube_size='Large')

    aliases = {}
    for a, st in ALIASES.items():
        if st in entries:
            aliases[a] = st
        else:
            warn.append(f"alias {a} -> {st} unresolved")
    for k, v in SYNTHETIC.items():
        aliases[k] = v['subtype']

    if unknown_items:
        warn.append("recipe items with no MaxIntegrity (counted as 0): "
                    + ', '.join(sorted(unknown_items)))

    gw = {}
    for st, d in weights.items():
        for gn, w in d.items():
            gw.setdefault(gn, {})[st] = w

    out = dict(
        generated_by='gen_catalogue.py',
        sources=dict(vanilla=VANILLA, workshop=WORKSHOP, mods=MODS,
                     csv='../sdx2_blocks.csv',
                     ruleset=f'{SDX2}/Data/ShipCoreConfig_Groups.xml + Data/Cores/**',
                     world=WORLD_SAVE,
                     cross_check='../sdx2.json (advisory only)'),
        world_speed=world_speed,
        world_speed_source=('SERVER_WORLD_SPEED constant (server config, not readable '
                           'from this machine)' if SERVER_WORLD_SPEED
                           else 'local save SCF ShipCoreConfig_World.xml'),
        speed_is_modifier=True,
        wc_subsystem_note=WC_SUBSYSTEM_NOTE,
        items={k: dict(integrity=v[0], mass=v[1], source=item_src[k])
               for k, v in sorted(items.items())},
        blocks=entries,
        aliases=aliases,
        classes=[dict(name=c['name'], subtype=c['subtype'],
                      speed=c['speed'], speed_mps=c['speed'] * world_speed,
                      boost=c['boost'], boost_enabled=c['boost_enabled'],
                      boost_mps=(c['boost'] * world_speed) if c['boost_enabled'] else None,
                      speed_limit_type=c['speed_limit_type'],
                      friction_min_mps=c['friction_min'] * world_speed,
                      friction_max_mps=c['friction_max'] * world_speed,
                      mobility=c['mobility'], max_blocks=c['max_blocks'],
                      max_pcu=c['max_pcu'], file=os.path.basename(c['file']),
                      categories={n: dict(budget=v['budget'], groups=v['groups'],
                                          critical=v['critical'],
                                          directions=v['directions'])
                                  for n, v in c['categories'].items()})
                 for c in cores],
        group_weights=gw,
        warnings=warn,
    )
    return out


if __name__ == '__main__':
    cat = build()
    path = os.path.join(HERE, 'catalogue.json')
    json.dump(cat, open(path, 'w', encoding='utf-8'), indent=1, sort_keys=False)
    print(f"wrote {path}")
    print(f"  {len(cat['items'])} items, {len(cat['blocks'])} blocks, "
          f"{len(cat['aliases'])} aliases, {len(cat['classes'])} ship cores, "
          f"world speed {cat['world_speed']:g} m/s")
    for w in cat['warnings']:
        print("  WARN", w)
    print()
    print(f"{'class':<14}{'mod':>6}{'m/s':>7}{'limit':>10}{'friction m/s':>15}")
    for c in cat['classes']:
        fr = '%.0f-%.0f' % (c['friction_min_mps'], c['friction_max_mps'])
        print(f"{c['name']:<14}{c['speed']:>6.2f}{c['speed_mps']:>7.0f}"
              f"{str(c['speed_limit_type']):>10}{fr:>15}")
    print()
    print(f"{'alias':<12}{'subtype':<34}{'size':<10}{'integrity':>12}{'mass':>10}"
          f"{'gdm':>6}{'out':>12}  subsystem / wc")
    for a, st in cat['aliases'].items():
        b = cat['blocks'][st]
        out = (f"{b['power_mw']:.0f} MW" if b['power_mw'] else
               f"{b['thrust_n']/1e6:.0f} MN" if b['thrust_n'] else
               f"{b['gyro_n']/1e6:.1f} MNm" if b['gyro_n'] else '')
        print(f"{a:<12}{st:<34}{'x'.join(map(str,b['size'])):<10}{b['integrity']:>12,}"
              f"{b['mass']:>10,}{b['gdm']:>6.2f}{out:>12}  {b['subsystem']}"
              f" / {b.get('wc_subsystem')}")
