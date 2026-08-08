# AUDIT — SCF ruleset, block catalogue, NPC-component economy

Scope: `economics.py`, `gen_catalogue.py`, `shipyard.py`, `components.py`.
Everything below was re-derived from the shipped data for the mod list in
`…/Sigma Draconis Expanse 2 Creative World 2026-08-01 1243/Sandbox_config.sbc`
(52 mods, 1541 `.sbc` files) plus the ModAdjuster XML patches that are actually applied.
`../sdx2.json` was used **only** as a thing to check against, never as a source.

Headline: **6 claims REFUTED, 14 CONFIRMED, 2 confirmed-with-correction.** The two that
change conclusions most are the world speed cap (every class is 30% of the modelled
speed) and torpedo ammo (5× cheaper than reported).

---

## 1. RULESET

### 1.1 World speed cap — **REFUTED (both the premise and the number)**

The world loads **3552595651** (canonical ShipCoreFramework). The fork **3582505859 is
not in the mod list at all** — `Sandbox_config.sbc:307-308` lists `3552595651.sbm`, and
`grep 3582505859 Sandbox_config.sbc` returns nothing. Both have a `Storage/` folder in
this save because the save was opened with each at some point, but storage folders are
not load evidence.

So the live config is `Storage/3552595651.sbm_ShipCoreFramework/ShipCoreConfig_World.xml`
→ `<MaxPossibleSpeedMetersPerSecond>300</MaxPossibleSpeedMetersPerSecond>`.
That value is not advisory — SCF writes it straight into the environment definition:

```
Session/Session.Definitions.cs:21-25
    MyDefinitionManager.Static.EnvironmentDefinition.LargeShipMaxSpeed =
        Config.MaxPossibleSpeedMetersPerSecond;
    …SmallShipMaxSpeed = Config.MaxPossibleSpeedMetersPerSecond;
```

**Live cap = 300 m/s.** `Config/ModConfig.XmlModels.cs:49` and
`Config/ModConfig.WorldSettings.cs:32-40` confirm 300 is also the hard default and the
fallback on validation failure. `sdx2.json` `shipCores.worldSpeed = 1000` is the fork's
number and is wrong for this world.

### 1.2 Per-class speed caps — **REFUTED. These are MODIFIERS, not m/s.**

`<MaxSpeed>` in each `*_Core.xml` is a fraction, consumed as a fraction:

```
Server/Enforcement/SpeedEnforcement.cs:541
    baseMaxSpeed = Session.Config.MaxPossibleSpeedMetersPerSecond * speedModifiers.MaxSpeed;
```

`2815514917/Data/Cores/Combat Grids/Corvette_Core.xml` → `<MaxSpeed>0.55</MaxSpeed>`.
The claimed figures are exactly modifier × **1000**; the live figures are × **300**:

| class | `<MaxSpeed>` | claimed (rip, ×1000) | **live (×300)** | limit type | friction band m/s |
|---|---|---|---|---|---|
| Picket | 0.65 | 650 | **195** | Friction | 90–195 |
| Corvette | 0.55 | 550 | **165** | Friction | 90–165 |
| Frigate | 0.50 | 500 | **150** | Friction | 90–150 |
| Cruiser | 0.45 | 450 | **135** | Friction | 90–135 |
| Carrier / Barge / Hauler | 0.30 | 300 | **90** | Normal | 90–240 |
| Skiff (No-Core) | 0.40 | 400 | **120** | Friction | 90–120 |
| Outpost / Installation | 0.05 | 50 | **15** | Normal | 9–12 |

The *ratios* in the claim are all correct; the absolute speeds are 3.33× too high. Note
`<SpeedBoostEnabled>false</SpeedBoostEnabled>` on the Corvette, so its `MaxBoost` 0.65
(195 m/s) is dead — boost is off for the combat classes.

### 1.3 Category budgets are POINTS spent by per-block weight — **CONFIRMED**

`Server/Components/GridComponent.Limits.cs:31,53-65,82-88`:

```
var weight = matchedBlockType.CountWeight;
…
if (currentWeight + weight > effectiveMaxCount)   // MaxCount is a POINT budget
…
groupBucket.TotalWeight += weight;
```

### 1.4 Which PDC group each class uses — **CONFIRMED, and stronger than claimed**

**Every one of the 11 shipped cores uses `pdcsHeavyAdvWeights`** for its Point Defense
Cannons limit. `pdcsAdv` and `pdcsEvenAdvWeights` are defined in
`ShipCoreConfig_Groups.xml` but **referenced by no shipped core** — they are dead groups.

In `pdcsHeavyAdvWeights`: all six `*Adv` PDC families weigh **2**, all six basic/
improvised families weigh **1**. So the Corvette's budget of 8 buys **4× sdx_pdcUnnAdv**
or **8× sdx_pdcMcrn**. Confirmed exactly as stated.

### 1.5 Ceramic caps — **CONFIRMED**

Picket 20 / Corvette 40 / Frigate 60 / Cruiser 120 / Carrier 240, group `ceramics`, where
`sdx_armorCeramic` weighs 1 and `sdx_cargocontainerReinforced1x1` weighs 2. (Battleship
240, Dreadnought has no Ceramics limit — both admin-only, see 1.7.)

### 1.6 Offensive Weapons is a shared pool — **CONFIRMED, with two things the claim missed**

Weights in group `weapons`:

| weight | blocks |
|---|---|
| 102 | `sdx_torpedoLauncherMediumContinuous` ← **no such block exists** (see 4.4) |
| 42 | 4 turreted railguns, **`sdx_detectorPassiveOpticalFocused`, `sdx_detectorPassiveRadioFocused`** |
| 34 | 5 fixed railguns (incl. `sdx_railgunPgenLightFixed`) |
| 10 | Light/Medium **Triple** torpedo launchers |
| 7 | Improvised/Light/Medium **Double** launchers, `sdx_detectorActiveRadioOmnidirectional_2x2` |
| 4 | Light/Medium **Single** launchers (+ HalfSlope variants) |
| 0 | **all 24 PDC variants** |

Two additions to the claim: a **focused passive sensor costs 42 offensive points — the
same as a turreted railgun**, and an active 2×2 radar costs 7 (a double torpedo tube).
That is a real design trade the sims do not currently model at all: fitting the good
sensor costs you a main gun.

### 1.7 `sdx_pdcPgenAdv` is in no SCF group — **REFUTED (premise). Conclusion still holds.**

It *is* grouped, with normal weights, in the shipped `ShipCoreConfig_Groups.xml`:
`pdcsAdv` 1, `pdcsEvenAdvWeights` 1, `pdcsHeavyAdvWeights` **2**, `weapons` 0 — identical
to every other advanced PDC. What makes it unbuildable is the **recipe**: 1×
`sdx_componentAdminKit`, an item with `MaxIntegrity 999999999` and no blueprint
(`2815514917/Data/Items/sdx_itemsComponentsAdmin.sbc`). Its derived block integrity is
**1,000,032,699** — effectively invulnerable, which is the giveaway.

The "in no group" belief came from `sdx2.json`, which silently drops every `*Pgen*`
block. `shipyard.weight_of()` was therefore falling back to `default=1` for it instead of
the real 2 — fixed.

Also admin-gated and *not* previously flagged: **`sdx_railgunPgenLightFixed`** (weight 34
in `weapons`, 1 in `railgunsFixed`, recipe 1× AdminKit).

Full AdminKit-gated list, after ModAdjuster: `sdx_pdcPgenAdv` (+5 variants),
`sdx_railgunPgenLightFixed` (+1), `sdx_shipcoreBattleship`, `sdx_shipcoreDreadnought`,
`sdx_shipcoreStationAdmin`, `LargeBlockSmallThrust`, and — via ModAdjuster —
`LargeRailgun`, `AutoCannonTurret`, `StaticDrill`, `BasicStaticDrill`,
`AdvancedStaticDrill`.

### 1.8 Battleship / Dreadnought / StationAdmin cores need AdminKit — **CONFIRMED**

All three recipes contain `sdx_componentAdminKit` ×1
(`2815514917/Data/Cores/Combat Grids/sdx_shipcoreCombat.sbc`). Not player-reachable.
Dropping exactly these three from the 12 manifest cores + No-Core leaves the same **10
classes** lomdar's planner ships, which is a decent independent check on the filter.

### 1.9 NEW — `sdx2.json` has drifted from the installed mod (54 discrepancies)

Not in the brief, but it invalidated the ruleset source. `sdx2.json` vs the shipped XML:

- omits all 6 `*Pgen*` weapon entries and `sdx_railgunPgenLightFixed`
- omits `sdx_torpedoLauncherMediumContinuous` (weights 102/70)
- omits `sdx_shipcoreBattleship` / `sdx_shipcoreDreadnought` from `sdx_shipcores`
- renames `sdx_cargoIndustrial7x7x7/9`, `sdx_cargoIndustrial2x2x6` → `sdx_cargocontainer7x7x7/9`
- **invents** a `sdx_shipConnectors` group (11 blocks) and 8 extra `torchDrives` entries
- stale Storage budgets: Picket 24→**20**, Corvette 40→**35**, Frigate 75→**70**, Skiff 104→**100**
- `worldSpeed` 1000 vs live 300

`gen_catalogue.py` now reads the ruleset from the mod and emits every one of these as a
warning.

---

## 2. ECONOMY (recursive to raw ore)

Method: an item is producible iff it appears in some blueprint's `<Result>`/`<Results>`;
`<Prerequisites>` never make anything. Leaves are derived, not listed: an item is free iff
it has an `Ore` definition (a voxel deposit), or some blueprint makes it from inputs that
are *all* mineable. 189 blueprints total across the whole loaded mod set
(vanilla 125, SDX2 Core 63, AQD 1) — verified by counting `</Blueprint>` in every `.sbc`
and `.xml` under every loaded mod.

### 2.1 "21 of 34 mod-added components producible by NO blueprint" — **CONFIRMED (21), denominator is 33**

There are **33** SDX2-namespaced `<Component>` definitions (27 with `TypeId Component`, 6
with `TypeId Ingot` — the faction scraps are declared as Components but typed as Ingots).
**21 have no blueprint result**, **12 do**. 21 is exactly right.

The 21: `AdminKit`, `DetectorAdvanced`, `DetectorExperimental`, `Electromagnet`,
`Fabrication`, `Industrial`, `IndustrialAdvanced`, `Processing`,
`ReactorLaserExperimental`, `TargetingComputer`, `TargetingComputerAdvanced`,
`ThrusterHeavy`, `TorpedoArming`, `TorpedoGuidanceComputer`, `TurretGimbal`, and the six
`sdx_ingot{Mcrn,Unn,Opa}{,Advanced}Scrap`.

(If you count *every* `<Component>` element the mod set touches it is 43 — that adds the
7 vanilla Prototech components, vanilla `Detector` and `Thrust` which SDX2 re-defines, and
one from AQD. None of those are "mod-added" in the sense that matters.)

### 2.2 `sdx_componentMcrn/Unn/Opa` craftable only from non-craftable scrap — **CONFIRMED**

`2815514917/Data/Blueprints/sdx_itemsBlueprintsTechScrap.sbc` — six 1:1 recipes,
e.g. `sdx_itemsBlueprintMcrnScrap: 1x sdx_ingotMcrnScrap → 1x sdx_componentMcrn`. No
blueprint anywhere produces any `sdx_ingot*Scrap`. Salvage-gated, as stated.

### 2.3 Drive costs — **CONFIRMED exactly**

| drive | unobtainable roots |
|---|---|
| `sdx_drive{Mcrn,Unn,Opa}Military3x3` | **free** |
| `sdx_drive{Mcrn,Unn,Opa}Military5x5` | **free** |
| `sdx_drive{Mcrn,Unn,Opa}Military7x7` | **50× `sdx_ingot{Mcrn,Unn,Opa}Scrap`** |
| `sdx_driveCivilian3x3 / 3x3_small / 5x5 / 7x7` | **free** |
| `sdx_driveIndustrial7x7` | **50× `sdx_componentIndustrial`** |
| `sdx_driveIndustrial9x9` | **50× `sdx_componentIndustrialAdvanced`** |
| `sdx_driveTorch3x3_small`, vanilla H2 thrusters | **free** |

### 2.4 Weapon costs — **CONFIRMED, with one refinement**

| block | unobtainable roots |
|---|---|
| `sdx_pdcMcrn` (Unn/Opa identical) | 20× `TargetingComputer`, 5× `{Mcrn,Unn,Opa}Scrap` |
| `sdx_pdcMcrnAdv` (Unn/Opa) | 20× `TargetingComputerAdvanced`, 5× `*AdvancedScrap` |
| `sdx_pdcImprovised` | 20× `Industrial` |
| `sdx_railgunMcrnMediumFixed` (Unn/Opa) | 40× `Electromagnet`, 100× `*Scrap` |
| `sdx_railgunImprovisedLightFixed` | 50× `Industrial` |
| `sdx_railgunMcrnMediumTurreted` (Unn/Opa) | 300× `Electromagnet`, 1× `TurretGimbal`, 50× **`*AdvancedScrap`** |
| `sdx_railgunImprovisedLightTurreted` | 50× `IndustrialAdvanced`, 50× `Electromagnet`, 1× `TurretGimbal` |
| torpedo launcher Light single/double/triple | 10 / 25 / **50**× `TorpedoArming` |
| torpedo launcher Medium single/double/triple | 15 / 45 / **90**× `TorpedoArming` |
| `sdx_torpedoLauncherImprovisedDouble` | 30× `Industrial` |

Refinement: the turreted railgun's 50× scrap is the **Advanced** grade, not the basic
grade the fixed gun uses — a separate and scarcer input.

### 2.5 Torpedo ammo — **REFUTED. 24× per shot, not 120×.**

`2815514917/Data/Blueprints/sdx_ammoBlueprintsTorpedos.sbc:12-22`:

```xml
<DisplayName>5x 160mm Torpedo</DisplayName>
<Prerequisites>
  … <Item Amount="120" TypeId="Component" SubtypeId="sdx_componentTorpedoGuidanceComputer" />
</Prerequisites>
<Result Amount="5" TypeId="AmmoMagazine" SubtypeId="sdx_ammomagazineTorpedo160mm" />
```

`<Result Amount="5">`. Magazine `<Capacity>1</Capacity>` is confirmed
(`Data/Ammos/sdx_ammomagazineTorpedosStub.sbc:20`), so one magazine is one shot — but one
*craft* yields five magazines. **120 / 5 = 24× `TorpedoGuidanceComputer` per shot.** Same
for the 220mm. The 120 figure came from `economics.py` ignoring `Result Amount` entirely;
it made torpedoes look 5× more ruinous than they are and it dominated every cost-per-kill
ranking in `exchange_demo.py`.

### 2.6 PDC / sabot / improvised-torpedo ammo free — **CONFIRMED**

All ore-only. Worth recording alongside: PDC magazines hold **120 rounds**
(`<Capacity>120</Capacity>`), sabot and torpedo magazines hold **1**. So "PDC ammo is
free" and "sabot ammo is free" are true but the per-magazine logistics differ 120×.

### 2.7 Ceramic, reactors, gyros, RCS free to raw ore — **CONFIRMED**

- `sdx_armorCeramic` = 22× `sdx_componentCeramicPlate`; plate = 11× `sdx_ingotBoron` + 3
  Magnesium; boron = `1 Stone → 0.003 boron`. Free, but **≈80,700 Stone per block** —
  a Cruiser's 120-block allowance is ~9.7M Stone. Free ≠ cheap.
- `sdx_reactorFusion1x1/3x3/5x5` — via `ReactorLaser` / `ReactorLaserAdvanced` /
  `ReactorShielding`, all three craftable from Iron/Platinum/Titanium/Boron/Lead. Free.
- `sdx_gyroscopeBraced_large`, `sdg_rcsGyroComputer`, `sdx_thrusterRCSBareLG` — free.
- Also free: `LargeHeavyBlockArmorBlock`, `LargeBlockArmorBlock`,
  `sdx_cargocontainerReinforced1x1`, and the Picket/Corvette/Frigate/Barge/Hauler/
  Outpost/Installation ship cores.

Ship cores that are **not** free: `sdx_shipcoreCruiser` 1× `Electromagnet`,
`sdx_shipcoreCarrier` 1× `TurretGimbal`.

### 2.8 `ReactorLaserExperimental` and `ThrusterHeavy` are orphans — **CONFIRMED**

Both are consumed by **0** blocks and **0** blueprints, and produced by **0** blueprints.
Dead definitions. (`sdx_componentDetectorExperimental` by contrast is consumed by 8 blocks
but produced by nothing — that one is a live salvage gate, not an orphan.)

### 2.9 NEW — there is no loot table

Exhaustive scan of every `.sbc`/`.xml`/`.cs` in all 52 loaded mods: the 21 unobtainable
components appear **only** in their own item definitions, in `GameCoreIcons.sbc`, and in
the block recipes that consume them. **No SpawnGroup, container drop table, or research
recipe produces any of them.** The entire supply is grinding down NPC hulls that were
spawned already containing those blocks. Any attrition model that assumes a resupply rate
needs that rate measured in-world; it is not in the data.

---

## 3. CATALOGUE

### 3.1 `integrity = Σ count × MaxIntegrity`, `mass` likewise — **CONFIRMED (16/16 spot checks)**

Re-derived independently from a second pass over the same `.sbc` set. 16 blocks checked
(both armour grades, ceramic, all three reactors, 5×5 and 7×7 drives, RCS thruster, both
gyros, `pdcUnnAdv`, `pdcMcrn`, fixed railgun, triple torpedo tube, Corvette core) — all
match `catalogue.json` exactly. A full sweep of all 188 catalogued blocks found **zero**
disagreements once ModAdjuster was applied.

The one apparent mismatch, `LargeHeavyBlockArmorBlock` 16,500/3,300 vs the catalogue's
16,520/2,680, was **my** first pass being wrong, not the catalogue: I had globbed only
`.sbc` and missed the ModAdjuster `.xml` patches. See 3.2.

### 3.2 Heavy armour gdm and HP — **CONFIRMED, and the recipe matters as much as the gdm**

`GeneralDamageMultiplier` 0.5 is commented out in **both** places:

- vanilla `Content/Data/CubeBlocks/CubeBlocks_Armor.sbc`
- `2815514917/Data/ModAdjuster/CubeBlocks/KeenSoftwareHouse/CubeBlocks_Armor.xml`:
  `<!-- <GeneralDamageMultiplier>0.5</GeneralDamageMultiplier> -->`

⇒ **gdm 1.0**. And the *live* recipe is the ModAdjuster one:

```xml
<Component Subtype="SteelPlate" Count="15" />
<Component Subtype="MetalGrid" Count="50" />
<Component Subtype="sdx_componentTitaniumPlate" Count="104" />
```

= 15×100 + 50×30 + 104×130 = **16,520**, not the vanilla 150+50 = 16,500. So the
claimed effective HP of 16,520 is right, and it is right for two reasons that had to be
checked separately.

ModAdjuster is live: mod **3017795356** is in the world's mod list
(`Sandbox_config.sbc:357-358`) and it patches whatever each mod's
`Data/ModAdjuster/ModAdjusterFiles.txt` lists.

**Epstein drives carry a live `<GeneralDamageMultiplier>0.25`** — CONFIRMED for all 14
drive subtypes (military 3x3/5x5/7x7 in all three factions, civilian, industrial, torch).
No other block in the catalogue has a non-1.0 gdm.

`test_hifi.py` has one failure, `blockHp = 16500 / 0.5` expecting 33,000 against the
catalogue's 16,520. **The catalogue is right and the tabletop fixture is wrong on both
terms.** That file is not mine to edit — flagging it for whoever owns `wc_damage.py`.

### 3.3 Subsystem tagging matches WeaponCore's BlockTypes — **REFUTED in three places**

The **ordering** is right and is now sourced rather than asserted: every SDX2 railgun, PDC
and torpedo launcher declares
`SubSystems = { Power, Utility, Offense, Thrust, Production, Any }` —
`3580645761/Data/Scripts/Mod/CoreParts/Railguns/BaseRailgunDefinition.cs:31`,
`PDC/BasePDCDefinition.cs:33`, `Torpedolaunchers/BaseTorpedoLauncherDefinition.cs:37`.
(`Misc/sdx_lidar.cs:52` differs — it leads with Thrust.)

The **per-block mapping** was wrong. Ground truth is
`3154371364/…/CoreSystems/EntityComp/Parts/Weapon/WeaponTracking.cs:1658-1690`
(`ValidSubSystemTarget`), and the enum has **eight** members, not six —
`Any, Offense, Utility, Power, Production, Thrust, Jumping, Steering`
(`Definitions/CoreDefinitions.cs:285-293`).

| block | tagged | WeaponCore truth | consequence |
|---|---|---|---|
| all 4 Gyro blocks incl. `sdg_rcsGyroComputer` | `Utility` | **`Steering`** (`cube is MyGyro`) | Steering is **not in the SubSystems array**, so in game a gyro is only ever hit as `Any` — i.e. **LAST**. Tagged Utility, a sim shoots it **second**. |
| 11 hydrogen/water tanks | `Production` | **`Any`** (`IMyGasTank` is not `IMyProductionBlock`) | tanks were a priority target; they are not |
| 5 Decoy blocks | `Utility` | **every case** (`\|\| cube is IMyDecoy` appears in all 7 branches) | one tag cannot express this; decoys should be the first hit for *any* subsystem-seeker |

`Power`, `Thrust`, `Offense` and the Refinery/Assembler/OxygenGenerator/SurvivalKit part of
`Production` were all correct. The real `Utility` set is much wider than modelled —
`IMyUpgradeModule` (non-production), `IMyRadioAntenna`, `IMyLaserAntenna`,
`MyRemoteControl`, `IMyShipToolBase`, `IMyMedicalRoom`, `IMyCameraBlock`.

`ConveyorSorter → Offense` is correct only for registered WeaponCore platforms
(`cube is MyConveyorSorter && Session.I.PartPlatforms.ContainsKey(...)`); resolving it by
SCF group membership is a sound proxy but will misjudge a WC weapon that is in no SCF
group, or a genuine sorter whose name matches `/pdc|railgun|torpedo|missile|gatling/i`.

### 3.4 NEW — `gen_catalogue.py` was applying an override the game does not

ModAdjuster loads only what `ModAdjusterFiles.txt` names. `gen_catalogue.py` globbed
`ModAdjuster/**/*.xml`, so it applied
`CubeBlocks/KeenSoftwareHouse/CubeBlocks_Tools.xml`, which is **on disk but not in the
manifest** — corrupting `LargeShipGrinder`, `LargeShipWelder`, `SmallBlockDrill`,
`SmallShipGrinder`, `SmallShipWelder`, `LargeOreDetector`. (The manifest also names
`Block_Rcs.xml`, which is not on disk and is silently skipped by the real loader.)
Fixed — the manifest is now honoured.

### 3.5 NEW — blocks in SCF groups that do not exist

`sdx_torpedoLauncherMediumContinuous` (weights **102** in `weapons`, **70** in
`torpedoLaunchers`) has **no block definition in any loaded mod**. Likewise
`sdx_cargoIndustrial2x2x6`, `sdx_cargoIndustrial7x7x7`, `sdx_cargoIndustrial7x7x9`, and
two empty `<SubtypeId/>` entries in `production` / `productionWater`. Dead ruleset
entries — now reported as warnings rather than silently dropped.

---

## 4. FIXES APPLIED

### `economics.py` — rewritten scan; three defects, all of which changed numbers

1. **`<Result Amount>` was ignored.** `recipe.setdefault(res[0], pre)` recorded the whole
   prerequisite list against one unit of the first result. Torpedoes were priced 5× too
   high. Now divides by the result amount.
2. **Nondeterministic recipe choice.** `for f in set(files)` + `setdefault` meant the
   winning blueprint for the ~21 components that have both a vanilla and an SDX2 recipe
   depended on set iteration order. SDX2 now wins explicitly, tie-broken on blueprint id.
3. **Hand-written leaf set.** `RAW` listed `sdx_ingotTitanium` (no such item) and omitted
   **Copper** and **Tungsten**, both real and both mineable. Leaves are now derived from
   the `Ore`/`Ingot` type system. This had to distinguish two shapes of self-referential
   recipe: `1x Iron → 0.7x Iron` is `Ore/Iron → Ingot/Iron` and Iron *is* mineable, so
   Iron is free; `1x PrototechScrap → 1x PrototechScrap` has no PrototechScrap ore behind
   it, so prototech is correctly an unobtainable salvage root. Collapsing TypeIds to
   last-wins per subtype loses that distinction, so the union is kept.
4. ModAdjuster patches now applied (manifest-driven), so block recipes match the game.
5. Cache is versioned (`CACHE_VERSION = 3`) so the stale `recipe_cache.json` cannot be
   silently reused.

`total_cost` / `npc_cost` / `exchange` signatures unchanged; `exchange_demo.py` runs.

### `gen_catalogue.py`

- Ruleset now read from `2815514917/Data/ShipCoreConfig_Groups.xml` +
  `ShipCoreConfig_Manifest.xml` → `Data/Cores/**` + `ShipCoreConfig_No_Core.xml`.
  `../sdx2.json` is retained purely as a cross-check and every disagreement is a warning
  (54 of them fire).
- `world_speed` read from the live SCF world config of the mod the world actually loads,
  with a warning if a non-loaded SCF mod has leftover storage. Added `speed_is_modifier`,
  and per class `speed_mps`, `boost_mps`, `speed_limit_type`, `friction_{min,max}_mps`.
- Admin-gated cores dropped with an explicit warning.
- ModAdjuster manifest honoured instead of globbing.
- `GasTank`/`OxygenTank` removed from `Production`.
- New per-block `wc_subsystem` field carrying WeaponCore's real classification, plus
  `wc_subsystem_note` in the JSON. `subsystem` deliberately left alone — `hull2.py:191`
  finds gyros by `subsystem == UTILITY` and retagging them would silently zero the hull's
  torque. **This needs a cross-file follow-up: `hull2.pick_target_block` should select on
  `wc_subsystem`, and `hull2` should find gyros by `gyro_n > 0` alone.** That file is not
  mine.

### `shipyard.py`

- `S['speed']` is now **m/s** (modifier × world cap); `S['speed_modifier']` keeps the
  fraction; added `speed_limit_type` and `friction_band`.
- `weight_of()` distinguished absent from **zero** — every PDC has weight 0 in `weapons`,
  which is meaningful, and the old `if w:` fell through to `default=1`. Guarded the three
  budget loops against a 0 weight so they cannot spin.
- Docstring corrected on `sdx_pdcPgenAdv` (it is grouped; it is AdminKit-gated).

### `components.py`

- Documented that `WORLD_SPEED` is 300 and that class `speed` is a fraction; added
  `class_speed(name) -> (m/s, modifier)`.
- Exposed `wc_subsystem` on every spec, added `STEERING`/`JUMPING`, `WC_SUBSYSTEM_ORDER`
  and `WC_UNSOUGHT`, and documented the three divergences with the file:line source for
  the `SubSystems` ordering.

Regenerated `catalogue.json`: **188 blocks** (was 204 — the 16 lost are the phantom
`sdx_shipConnectors` group and the misnamed cargo containers that only `sdx2.json`
believed in), 21 aliases, 10 cores, world speed 300.

Verified: all 17 modules still import; `test_hifi.py` 38 pass / 1 fail (the pre-existing,
documented heavy-armour fixture disagreement of 3.2); `layout.py`, `subsystem_demo.py`,
`exchange_demo.py`, `shipyard.py`, `components.py`, `economics.py` all run.

---

## 5. CORRECTED COST TABLES

Resolved recursively to unobtainable roots. Free-to-mine inputs are omitted; every root
listed below can *only* be obtained by grinding NPC hardware.

### 5.1 Reference fit as `shipyard.build_ship()` builds it

Fixed railgun (MCRN) + triple light tubes + `pdcUnnAdv` + 1×1 reactors + 5×5 drives.

| | Corvette | Frigate | Cruiser |
|---|---|---|---|
| speed | 165 m/s (0.55) | 150 m/s (0.50) | 135 m/s (0.45) |
| offensive spent | 54 / 62 | 84 / 90 | 94 / 102 |
| fixed railguns | 1 | 1 | 1 |
| triple tubes | 2 | 5 | 6 |
| PDCs (`pdcUnnAdv`, wt 2) | 4 | 6 | 13 |
| reactors / drives | 4 / 1 | 6 / 2 | 12 / 4 |
| `TorpedoArming` | 100 | 250 | 300 |
| `TargetingComputerAdvanced` | 80 | 120 | 260 |
| `McrnScrap` | 100 | 100 | 100 |
| `Electromagnet` | 40 | 40 | 41 |
| `UnnAdvancedScrap` | 20 | 30 | 65 |
| **total salvage-gated** | **340** | **540** | **766** |

Everything else on these hulls — armour, ceramic, reactors, gyros, RCS, cargo, the
Corvette/Frigate cores — is free to mined ore. The Cruiser core's extra `Electromagnet` is
the +1.

### 5.2 Most expensive legal fit (brute-forced against the shared pool and all sub-caps)

| | Picket | Corvette | Frigate | Cruiser | Carrier |
|---|---|---|---|---|---|
| offensive pool | 56 | 62 | 90 | 102 | 102 |
| spent | 14 | 61 | 88 | 102 | 102 |
| fixed / turreted railguns | 0 / 0 | 1 / 0 | 1 / 0 | 0 / **1** | 0 / **1** |
| torpedo tubes | 1 med-triple + 1 med-single | 2 med-triple + 1 med-double | 5 med-triple + 1 med-single | 6 med-triple | 6 med-triple |
| PDCs | 2 | 4 | 6 | 13 | 10 |
| `TorpedoArming` | 105 | 225 | 465 | 540 | 540 |
| `Electromagnet` | – | 40 | 40 | **301** | 300 |
| `TargetingComputerAdvanced` | 40 | 80 | 120 | 260 | 200 |
| `McrnScrap` | – | 100 | 100 | – | – |
| `McrnAdvancedScrap` | – | – | – | 50 | 50 |
| `UnnAdvancedScrap` | 10 | 20 | 30 | 65 | 50 |
| `TurretGimbal` | – | – | – | 1 | 2 |
| **total** | **155** | **465** | **755** | **1,217** | **1,142** |

Three things fall out of this that the sims currently miss:

1. **The Picket cannot spend its offensive budget.** Pool 56, but with Fixed Railguns 0
   and Turreted Railguns 0 its only spend is torpedo tubes, capped at 14. It leaves **42
   of 56 points stranded** — exactly the cost of one focused passive sensor (1.6). The
   Picket is a sensor picket by construction, and nothing in the harness models that.
2. **A Cruiser's single turreted railgun costs more than its entire torpedo battery in
   `Electromagnet` terms** (300 + gimbal + 50 advanced scrap). At 42 offensive points it
   also crowds out both fixed railguns (34 each, 110 > 102). Turret-vs-2×fixed is the
   Cruiser's central economic decision and `shipyard.build_ship` never builds a turret at
   all — `S['turret_rg']` is read into `CLASSES` and then ignored.
3. **`TorpedoArming` is the binding scarcity at every class**, 105→540 units, ahead of
   `Electromagnet` everywhere except the turret fits. Combined with 2.5 (24× TGC per
   shot, not 120×), the torpedo archetype is materially cheaper than
   `exchange_demo.py` reported: cost per kill at p=0.9 drops from **1,006 to 238**.

### 5.3 Ammo, per shot

| ammo | roots per shot | magazine capacity |
|---|---|---|
| `Torpedo160mm` / `Torpedo220mm` | **24× `TorpedoGuidanceComputer`** | 1 |
| `Torpedo190mmImprovised` | free | 1 |
| `Sabot80mm` / `100mm` / `80mmImprovised` | free | 1 |
| `Pdc40mm` / `50mm` / `40mmImprovised` | free | 120 |
