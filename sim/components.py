"""SDX2 component catalogue with subsystem tags and functional contributions.

Integrity/mass are computed from the real <Component> recipes; outputs are the real
<MaxPowerOutput>/<ForceMagnitude>.

SUBSYSTEM_ORDER is the order the SDX2 guns walk when picking an aimpoint. It is not a
guess: every railgun, PDC and torpedo launcher in mod 3580645761 declares

    SubSystems = new[] { Power, Utility, Offense, Thrust, Production, Any }

(Railguns/BaseRailgunDefinition.cs:31, PDC/BasePDCDefinition.cs:33,
Torpedolaunchers/BaseTorpedoLauncherDefinition.cs:37). Only sdx_lidar differs — it
leads with Thrust.

THREE TAGS, THREE JOBS. Do not substitute one for another.

  `subsystem`     the sim's coarse bucket. Legacy; kept only for readouts and for
                  callers that predate the split. Never use it for target selection.
  `wc_subsystem`  WeaponCore's own classification (CoreSystems AiTargeting.cs
                  AcquireBlock :1254-1288 via GridToBlockTypeMap). This is what a gun
                  actually walks. `CATALOGUE_JSON['wc_subsystem_note']` has the full
                  derivation; the three that bite:
                    - GYROS are Steering, and Steering is ABSENT from the SubSystems
                      array above, so a gyro is only ever reached in the final
                      all-blocks pass, i.e. LAST. `subsystem` calls them Utility, which
                      would have a sim shoot them SECOND.
                    - GAS TANKS match no branch of either classifier -> `Any`.
                    - a DECOY is in exactly one acquisition bucket (default Utility),
                      even though it satisfies every branch of the *validation*
                      predicate. Acquisition is the path that matters here.
  `role`          explicit functional role: 'gyro', 'rcs_computer', 'rcs', 'drive',
                  'reactor', 'weapon', 'armour', 'decoy', 'filler', 'other'. This
                  exists because hull2 used to locate torque-producing blocks with
                  `subsystem == UTILITY`; correcting a targeting tag would then have
                  silently zeroed every hull's torque. Capability lookups read `role`.

`wc_targetable` is False for armour. WeaponCore builds both its aimpoint pools from
lists filtered by `as IMyTerminalBlock` (SessionEvents.cs:341-344, SessionJobs.cs:381),
and an armour cube is not one — armour is eaten on the way in, never aimed at.

NOTHING IN THIS FILE IS HAND-ENTERED. Every number is read out of catalogue.json,
which `gen_catalogue.py` derives from the shipped .sbc/.xml game data — see that
module's docstring for the exact sources and the integrity = sum(count * MaxIntegrity)
derivation. Regenerate with:  python gen_catalogue.py

Values the generated table moved away from the previous hand-entered ones:

  * LargeHeavyBlockArmorBlock gdm is 1.0, not 0.5. <GeneralDamageMultiplier>0.5 is
    COMMENTED OUT in both vanilla CubeBlocks/CubeBlocks_Armor.sbc L858 and SDX2's
    ModAdjuster/CubeBlocks/KeenSoftwareHouse/CubeBlocks_Armor.xml, so the block ships
    with the 1.0 default and heavy steel is half as tough as previously modelled.
    Its 16,520 integrity likewise comes from the ModAdjuster recipe (15 SteelPlate +
    50 MetalGrid + 104 sdx_componentTitaniumPlate), not the vanilla 150+50.
    `wc_damage.sdx_blocks()['heavy']` now carries the same 16,520 / gdm 1.0, so the two
    pipelines AGREE. (They used to disagree, and a stale note here claimed that was by
    design. It was not; both are now correct.)
  * the Epstein drives carry a live <GeneralDamageMultiplier>0.25, so they are 4x
    harder to kill than the old flat 1.0.

WORLD_SPEED is the live cap, in m/s, and it is 1000 — the SERVER's setting.
ShipCoreFramework writes `Config.MaxPossibleSpeedMetersPerSecond` straight into
MyEnvironmentDefinition.LargeShipMaxSpeed (Session.Definitions.cs:21-25), and class
`<MaxSpeed>` values are consumed as FRACTIONS of it (SpeedEnforcement.cs:541
`baseMaxSpeed = MaxPossibleSpeedMetersPerSecond * speedModifiers.MaxSpeed`).

The MODIFIER mechanism is read out of the shipped mod XML and is not in doubt. The CAP
is a server config value and is NOT inferable from this machine: the local SP save's
stored SCF config says 300, which is evidence about that save and nothing else. 1000 is
the server figure; it lives in `gen_catalogue.SERVER_WORLD_SPEED`, which is the single
place to change it. `speed_mps` is the resulting m/s figure per class:

    Picket 650, Corvette 550, Frigate 500, Cruiser 450,
    Carrier/Barge/Hauler 300, Skiff 400, Outpost/Installation 50
"""
import json, os

POWER, UTILITY, OFFENSE, THRUST, PRODUCTION, ANY = (
    'Power', 'Utility', 'Offense', 'Thrust', 'Production', 'Any')
#: WeaponCore has two more BlockTypes that the SDX2 guns never ask for
STEERING, JUMPING = 'Steering', 'Jumping'

SUBSYSTEM_ORDER = [POWER, UTILITY, OFFENSE, THRUST, PRODUCTION, ANY]

#: The SubSystems array every shipped SDX2 gun declares, verbatim and in order.
#: AiTargeting.cs:1259 walks exactly this; :1265 SKIPS the ANY entry inside the loop,
#: and because ANY is present `OnlySubSystems` is false (CoreSystems.cs:649-662) so the
#: walk falls through to :1288, a uniform draw over EVERY terminal block on the grid.
#: So ANY here means "the unfiltered fallback pass", not "a bucket".
WC_SUBSYSTEM_ORDER = [POWER, UTILITY, OFFENSE, THRUST, PRODUCTION, ANY]
#: Steering and Jumping are absent from that array, so blocks tagged with them are
#: never sought deliberately — they are only ever reached by the ANY fallback, LAST.
WC_UNSOUGHT = (STEERING, JUMPING)
#: On the ACQUISITION path a decoy sits in one bucket, defaulting to Utility
#: (SessionJobs.cs:404-416). It matches everything only on the FocusSubSystem
#: validation path (WeaponTracking.cs:1659-1690).
DECOY = 'Decoy'
DECOY_ACQUISITION_BUCKET = UTILITY

#: `role` values, for capability lookups that must not depend on a targeting tag.
ROLE_GYRO, ROLE_RCS_COMPUTER, ROLE_RCS = 'gyro', 'rcs_computer', 'rcs'
ROLE_DRIVE, ROLE_REACTOR, ROLE_WEAPON = 'drive', 'reactor', 'weapon'
ROLE_ARMOUR, ROLE_DECOY, ROLE_FILLER = 'armour', 'decoy', 'filler'

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'catalogue.json')

_FIELDS = ('subtype', 'integrity', 'mass', 'subsystem', 'wc_subsystem', 'role',
           'wc_targetable', 'power_mw', 'thrust_n', 'gyro_n', 'is_armor', 'is_heavy',
           'kin_res', 'ene_res', 'gdm', 'scf_weight')


def _load(path=_PATH):
    if not os.path.exists(path):
        raise SystemExit(f"{path} missing — run `python gen_catalogue.py` first")
    return json.load(open(path, encoding='utf-8'))


CATALOGUE_JSON = _load()

#: subtype -> spec, for every block the SCF ruleset can budget (204 of them)
BY_SUBTYPE = {}
for _st, _b in CATALOGUE_JSON['blocks'].items():
    _d = {k: _b[k] for k in _FIELDS}
    _d['size'] = tuple(_b['size'])
    _d['type'] = _b['type']
    _d['name'] = _b['name']
    _d['scf_groups'] = _b['scf_groups']
    BY_SUBTYPE[_st] = _d

#: short handle -> spec. The handles the sims build ships out of.
CATALOGUE = {a: BY_SUBTYPE[st] for a, st in CATALOGUE_JSON['aliases'].items()}

#: SCF ship-core rulesets, straight out of SDX2 Core's shipped Data/Cores/**
SHIP_CORES = {c['name']: c for c in CATALOGUE_JSON['classes']}
GROUP_WEIGHTS = CATALOGUE_JSON['group_weights']
#: live world cap in m/s (300 here). Class `speed` values are fractions of this.
WORLD_SPEED = CATALOGUE_JSON['world_speed']


def class_speed(name):
    """(m/s cap, modifier) for a class. Never read `speed` as if it were m/s."""
    c = SHIP_CORES[name]
    return c.get('speed_mps', c['speed'] * WORLD_SPEED), c['speed']


def alias_of(subtype):
    """Reverse the handle map; returns None for blocks the sims have no handle for."""
    for a, st in CATALOGUE_JSON['aliases'].items():
        if st == subtype:
            return a
    return None


def C(subtype, size, integrity, mass, subsystem, **kw):
    """Ad-hoc spec, for tests and for blocks with no catalogue entry.

    Kept so callers that predate catalogue.json still work; production specs come
    from the generated table, not from here.
    """
    d = dict(subtype=subtype, size=tuple(size), integrity=integrity, mass=mass,
             subsystem=subsystem, wc_subsystem=ANY, role='other', wc_targetable=True,
             power_mw=0.0, thrust_n=0.0, gyro_n=0.0,
             is_armor=False, is_heavy=False, kin_res=1.0, ene_res=1.0,
             gdm=1.0, scf_weight=0, type='Adhoc', name=subtype, scf_groups={})
    d.update(kw)
    return d


class Component:
    """One installed block. Multi-cell components are ONE object occupying many
    cells — matching SE, where a 3x3x3 reactor is a single IMySlimBlock."""

    __slots__ = ('spec', 'origin', 'accumulated', 'name')

    def __init__(self, kind, origin, name=None):
        self.spec = kind if isinstance(kind, dict) else CATALOGUE[kind]
        self.origin = tuple(origin)
        self.accumulated = 0.0
        self.name = name or (kind if isinstance(kind, str) else self.spec['subtype'])

    # --- interface the ported DamageGrid expects -----------------------------
    @property
    def subtype(self): return self.spec['subtype']
    @property
    def integrity(self): return self.spec['integrity']
    @property
    def gdm(self): return self.spec['gdm']
    @property
    def is_armor(self): return self.spec['is_armor']
    @property
    def is_heavy(self): return self.spec['is_heavy']
    @property
    def kin_res(self): return self.spec['kin_res']
    @property
    def ene_res(self): return self.spec['ene_res']
    @property
    def mass(self): return self.spec['mass']
    @property
    def subsystem(self): return self.spec['subsystem']
    @property
    def wc_subsystem(self): return self.spec['wc_subsystem']
    @property
    def role(self): return self.spec['role']
    @property
    def wc_targetable(self): return self.spec['wc_targetable']
    @property
    def alive(self): return self.accumulated < self.integrity

    def cells(self):
        ox, oy, oz = self.origin
        sx, sy, sz = self.spec['size']
        for i in range(sx):
            for j in range(sy):
                for k in range(sz):
                    yield (ox + i, oy + j, oz + k)

    def centre(self):
        ox, oy, oz = self.origin
        sx, sy, sz = self.spec['size']
        return (ox + (sx - 1) / 2.0, oy + (sy - 1) / 2.0, oz + (sz - 1) / 2.0)

    def reset(self):
        self.accumulated = 0.0

    def __repr__(self):
        return f"<{self.name} {'alive' if self.alive else 'DEAD'} " \
               f"{self.accumulated:,.0f}/{self.integrity:,.0f}>"


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print(f"world speed cap {WORLD_SPEED:g} m/s")
    print(f"{'alias':<12}{'subtype':<34}{'size':<9}{'integrity':>14}{'mass':>10}"
          f"{'gdm':>6}{'wt':>6}  subsystem -> wc_subsystem  role/aimable")
    print("-" * 128)
    for a, s in CATALOGUE.items():
        print(f"{a:<12}{s['subtype']:<34}{'x'.join(map(str,s['size'])):<9}"
              f"{s['integrity']:>14,}{s['mass']:>10,}{s['gdm']:>6.2f}"
              f"{s['scf_weight']:>6g}  {s['subsystem']:<11} -> {s['wc_subsystem']:<10} "
              f"{s['role']:<13}{'aimable' if s['wc_targetable'] else 'NOT aimable'}")
    print()
    for k, (mps, mod) in ((k, class_speed(k)) for k in SHIP_CORES):
        print(f"  {k:<14}{mod:>6.2f} x {WORLD_SPEED:g} = {mps:>6.0f} m/s")
