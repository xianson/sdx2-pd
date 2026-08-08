# Audit — damage resolution and armour (`wc_damage.py`)

Scope: `wc_damage.py` only. Everything else is reported, not touched.

Sources of truth used (all paths under `C:\Program Files (x86)\Steam\steamapps\`):

| ref | file |
|---|---|
| **WC** | `workshop\content\244850\3154371364\Data\Scripts\CoreSystems\` |
| **SDX2-code** | `workshop\content\244850\3580645761\Data\Scripts\Mod\CoreParts\` |
| **SDX2-blocks** | `workshop\content\244850\2815514917\Data\` |
| **vanilla** | `common\SpaceEngineers\Content\Data\` |

Test status after the fixes: **`test_hifi.py` 38 pass / 1 fail / 1 below floor** (was 39/0/1).
The single failure is a wrong tabletop constant, not a regression — see
[Broken assertion](#broken-assertion) below. I did not touch `test_hifi.py`.

---

## Verdicts on the stated claims

### 1. Damage is a penetration POOL — **CONFIRMED, with one important exception**

`SessionDamageMgr.cs:461-462, 762, 766-782`

```
cutoff        = t.AmmoDef.BaseDamageCutoff ;  useBaseCutoff = cutoff > 0     // L461-462
scaledDamage  = (float)((useBaseCutoff ? cutoff : basePool) * baseScale)     // L762
survive: if (useBaseCutoff) basePool -= scaledDamage; else basePool = 0;     // L769-772
kill   : basePool -= (float)(blockHp / (baseScale==0 ? 1e-7 : baseScale));   // L780-781
```

The `perHit` formula and the kill cost are exactly as claimed. **The "surviving costs
`perHit`" half is only true on the cutoff branch.** With `BaseDamageCutoff == 0`
(every SDX2 PDC round) a block that survives sets `basePool = 0` outright — the round
is entirely consumed regardless of how much of it the block "used". Verified: a
`PDC50mmHeavy` (6800, no cutoff) into 1000 hp internals kills 6 and is fully consumed
by the 7th, which takes only 800.

A non-obvious consequence worth writing down: because `basePool -= scaledDamage`
subtracts the **post-scale** figure, a large anti-material multiplier drains the pool
proportionally faster. The airburst fragment's ×210 net vs ceramic means one fragment
(24,000 pool, 1,000 cutoff) spends 210,000 of pool on a single ceramic block and stops.
It cannot strip a second one. Higher multiplier ⇒ *fewer* blocks penetrated.

### 2. `blockHp = (Integrity - Accumulated) / GeneralDamageMultiplier / gridDamageModifier` — **CONFIRMED**

`SessionDamageMgr.cs:664, 665, 677`. Two guards the port was missing:

* `L672` — the division, the `MaxIntegrity` check, and **all** scaling are gated on
  `aConst.DamageScaling || blockDmgModifier != 1 || gridDamageModifier != 1`.
* `L674-675` — if either modifier is `< 1e-9`, `blockHp = float.MaxValue`, i.e. the
  block is **immune**, not a divide-by-zero. The old port would have raised
  `ZeroDivisionError`.

In practice `DamageScaling` is `true` for every ammo in this world because
`AmmoConstants.cs:1269` ORs in `ArmorCoreActive`, and SDX2's ceramic ArmorDefinition
sets it. The gate is therefore a no-op here — but it is now modelled, and
`ARMORCORE_ACTIVE` is an explicit module constant so it can be flipped.

### 3. ArmorCore resistance DIVIDES — **CONFIRMED**

`SessionDamageMgr.cs:742-752`

```
directDamageScale /= t.AmmoDef.Const.EnergyBaseDmg ? resistances.EnergeticResistance : resistances.KineticResistance;
areaDamageScale   /= t.AmmoDef.Const.EnergyAreaDmg ? ... ;
detDamageScale    /= t.AmmoDef.Const.EnergyDetDmg  ? ... ;
```

`KineticResistance = 0.1` ⇒ ×10 damage taken. `AmmoConstants.cs:1439`:
`energyBaseDmg = ammoDef.DamageScales.DamageType.Base != Kinetic`.

The port only modelled the **direct** division. It now models all three, which is what
makes claim 8 (torpedoes) resolvable at all. `SessionModHandlers.cs:1772-1779` clamps
each resistance to `> 0.0001 ? value : 1` and only registers a subtype at all when the
pair is not `(1,1)` and not `(0,0)`, so `kin_res == ene_res == 1.0` in the port is
exactly equivalent to being absent from `ArmorCoreBlockMap`.

### 4. Vanilla armour gets no ArmorCore resistance; classified by subtype substring — **CONFIRMED**

`SessionSupport.cs:118-126` (the claim's line 118 is exact):

```csharp
if (name.Contains("Armor")) {
    var normalArmor = name.Contains("ArmorBlock") || name.Contains("HeavyArmor")
                   || name.StartsWith("LargeRoundArmor") || name.Contains("BlockArmor");
    var blast = !normalArmor && (name == "ArmorCenter" || ... || name.StartsWith("SmallArmor"));
    if (normalArmor || blast) {
        AllArmorBaseDefinitions.Add(t);
        if (blast || name.Contains("Heavy")) HeavyArmorBaseDefinitions.Add(t);
    }
}
```

`SessionDamageMgr.cs:697` unions that with `CustomArmorSubtypes`, which is fed only by
`ArmorDefinition`s (`SessionModHandlers.cs:291-307`). SDX2's ten armour definitions
(`SDX2-code/Armors/*.cs`) name no vanilla armour subtype, so vanilla armour has no
entry in `ArmorCoreBlockMap`.

Two things the classifier implies that are easy to trip over:

* `name.Contains("Armor")` is **ordinal, case-sensitive**. `sdx_armorCeramic` has a
  lower-case `a` and is therefore *not* picked up by the vanilla path at all — it is
  armour purely because `sdx_armors_Ceramic.cs` declares `Kind = Heavy`.
* SDX2 registers `Kind = NonArmor` resistances on **non-armour** blocks, and those
  are big: cockpits `EnergeticResistance 43.5`, small cargo `200`, beacons and ship
  cores `50`, hydrogen tanks `12.5–15.15`, armoured conveyors `KineticResistance 0.2`.
  Those blocks take `1/43.5` etc. of energy damage. This is a real, large effect that
  no `sdx_blocks()` fixture represents. **Reported, not modelled** — the fixture set is
  four blocks and expanding it is `components.py`/`catalogue.json` territory (another
  agent's file; `catalogue.json` already carries `kin_res`/`ene_res` per subtype).

### 5. Heavy armour gdm 0.5 is commented out; effective HP is 16,520 — **CONFIRMED, and the port was wrong**

* vanilla `Data\CubeBlocks\CubeBlocks_Armor.sbc:858`, inside the
  `LargeHeavyBlockArmorBlock` definition (L703-862):
  `<!-- <GeneralDamageMultiplier>0.5</GeneralDamageMultiplier> -->`.
  It is the **only** occurrence of the tag in the whole file — no heavy armour shape
  has it live.
* SDX2 `Data\ModAdjuster\CubeBlocks\KeenSoftwareHouse\CubeBlocks_Armor.xml:31` — the
  override carries the same line, also commented out.

So `gdm == 1.0`. The 16,520 figure comes from SDX2 **replacing the recipe**, which the
claim did not mention (`CubeBlocks_Armor.xml:15-19`):

```
15 SteelPlate (MaxIntegrity 100) + 50 MetalGrid (30) + 104 sdx_componentTitaniumPlate (130)
= 1500 + 1500 + 13520 = 16,520
```

`sdx_componentTitaniumPlate` `MaxIntegrity 130 / Mass 20` at
`SDX2-blocks\Items\sdx_itemsComponentsTech.sbc:37+`. Vanilla's own recipe is
150 SteelPlate + 50 MetalGrid = **16,500**, so 16,520 is specifically the SDX2 number.
`catalogue.json` independently derives 16,520 / gdm 1.0 / mass 2,680 — the two
pipelines now agree.

**Fixed**: `sdx_blocks()['heavy']` is now `Block(..., 16520, 1.0, ...)` with mass 2,680.
Effective HP against a sabot drops from 33,000 to 16,520 — heavy steel is half as
tough as previously modelled. `components.py:16-21`'s note that "the two disagree by
design" is now stale and should be updated by whoever owns that file.

### 6. Every sabot carries an anti-ceramic `CustomScalesDef` of ×35–70 — **CONFIRMED**

I initially read this as REFUTED because a naïve regex captured only the numerator.
The modifiers are written as **expressions**:

| ammo | literal `Modifier` | value | × `Armor` 0.3 = net |
|---|---|---|---|
| `sabot100mmMcrn` | `11.6f/.3f` | 38.667 | 11.6 |
| `sabot100mmOpa` | `11f/.3f` | 36.667 | 11.0 |
| `sabot100mmUnn` | `10.5f/.3f` | 35.0 | 10.5 |
| `sabot80mm{Unn,Opa,Pgen,Improvised}` | `21f/.3f` | 70.0 | 21.0 |
| `airbust100mm{Unn,Opa}_Fragment` | `210f/.3f` | 700.0 | 210.0 |

The mod author pre-divided by `DamageScales.Armor.Armor` because `L698` and `L722`
both multiply (`sdx_armorCeramic` **is** armour via `Kind = Heavy`). The port's stored
values (`11.6/0.3`, `35.0`, `70.0`, `700.0`) are the literal modifiers and are
**correct**. I have rewritten them as explicit `x / 0.3` expressions matching the mod
source so this cannot be misread again, and added the missing `sabot100mmOpa` /
`sabot80mmImprovised`.

"ONE ceramic block absorbs one whole sabot" — confirmed for the MCRN round:
perHit `18000 × 11.6 = 208,800 ≤ 220,000`, so the block survives and the 180,000 pool
is over-drawn by 208,800 on the first block. Also true for the 80 mm rounds
(`10000 × 21 = 210,000`).

### 7. Airburst fragments ×700 vs ceramic, 220,000 → 10,000 in one fragment — **CONFIRMED**

Literal modifier 700, net ×210, cutoff 1,000 ⇒ 210,000 damage, residual 10,000 (4.55 %).
One fragment, one block — the 210,000 pool cost means it cannot reach a second ceramic
(see claim 1). The follow-up sabot then breaches the stripped block for only
`10,000 / 11.6 = 862` of pool. `test_hifi.py` 1c/1d assert all of this and still pass.

### 8. Steel does not stop a sabot at any thickness — **CONFIRMED**

perHit `5,400 < 16,520`, so no heavy block ever dies and the round is purely
pool-limited: `ceil(180,000 / 5,400) = 34` blocks touched, **0 kills**. That is
34 × 2.5 m = 85 m of heavy armour perforated, and it is *unchanged* by the gdm fix —
the fix halves the HP but the round was never HP-limited. The claim's "~33 blocks" is
the exact quotient; the loop touches the 34th before the pool clears.

### 9. Torpedo warheads deal energy AoE, so ceramic's kinetic weakness does not apply — **CONFIRMED**

`SDX2-code/TorpedoAmmo/*.cs`: every warhead has `BaseDamage = 1f` and all the payload
in `AreaOfDamage.ByBlockHit` (50,000–75,000, radius 6–11 m, depth 3–4 m,
`Falloff = Exponential`, `Shape = Round`, `MaxAbsorb = 0`). `DamageType.AreaEffect` and
`.Detonation` are `Energy` on all of them (`.Base` is `Kinetic` on most, `Energy` on
HEKP — irrelevant at 1 damage).

`L749` therefore divides the *area* scale by `EnergeticResistance`, which is `1f` for
ceramic. Modelled result, 11³ brick, 220 mm plasma torpedo:

```
11^3 heavy   (16,520 hp): 74 destroyed, 2,062,479 aoe damage
11^3 ceramic (220,000 hp): 0 destroyed, 2,702,500 aoe damage
```

Ceramic eats the whole warhead. Note the corollary: ceramic is the *wrong* armour
against torpedoes and the *right* armour against sabots, which is presumably the design
intent and is only visible once the area/det resistance split is modelled.

### 10. AoE falloff types, `Depth`, `MaxObjectsHit`, `CountBlocks`, `aoeIsPool` are modelled correctly — **REFUTED (they were absent entirely)**

The old `fire()` was a 30-line primary-damage-only loop. There was no `j` loop, no
`k` loop, no `DamageBlockCache`, no `RadiantAoe`, no falloff switch, no `aoeIsPool`,
no detonation staging; `CountBlocks` and `MaxObjectsHit` were mis-modelled (see
"Mechanics absent" #4). All of it is now ported. Behaviour I verified against the
source line by line while doing so, and which is worth knowing because it is
counter-intuitive:

* **The root block is queued twice.** `L594` adds it to `DamageBlockCache[0]` *before*
  `RadiantAoe`, which adds it again at `hitdist 0` (`L1373`). So the root takes primary
  damage at `k=0` **and** ring-0 AoE damage at `k=1`. Verified: root accumulates
  `1000 + 50000`.
* **`Depth <= 0` defaults to `Radius`** (`AmmoConstants.cs:1198-1201`), and when
  `depth < radius` the hit axis is clamped to `root ± (ceil(depth·GridSizeR) − 1)`
  (`L1310-1334`), turning the sphere into a slab. Verified footprints for radius 10 m:
  `Depth 0 → 229` cells, `Depth 2.5 → 69`, `Depth 25 → 229`.
* **Shape**: `Diamond` = Manhattan distance, `Round` = rounded Euclidean (`L1345-1348`).
  radius 10 m ⇒ 85 vs 229 cells.
* **`MaxAbsorb` does not terminate the loop.** The `endCycle` test at `L937` only
  *does* anything if a detonation is pending or active (`L942-958`); otherwise it falls
  through. For a `ByBlockHit`-only round `MaxAbsorb` matters solely inside the pooled
  branch (`L810-812`), where it caps per-block damage. Verified: `Pooled` 100,000 pool
  into 50,000 hp blocks kills 2 with `MaxAbsorb 0` and **0** with `MaxAbsorb 20,000`
  (5 blocks × 20,000).
* **`Falloff.Pooled` is the only value that sets `aoeIsPool`** (`L509`, `L519`). No SDX2
  ammo uses it — every one is `Exponential` or `NoFalloff` — so the pooled branch is
  dead code in this world. Modelled anyway.
* **DamageGrid's detonation path rarely fires.** `detRequested` is set on every primary
  hit (`L774`), but `detActive` is only set when `endCycle` is true *while*
  `detRequested` (`L944-951`). Once `RadiantAoe` has run for any reason
  `foundAoeBlocks` is true, which kills `endCycle`'s first term. For HEKP fragment 1
  (`MaxObjectsHit 0` ⇒ unlimited) the EndOfLife AoE therefore never resolves inside
  `DamageGrid` at all — it must come from `DetonateProjectile` (`L1164`). It *does*
  fire when `MaxObjectsHit` is reached; verified with `MaxObjectsHit = 4` (detonation
  deals 15,520 to the already-damaged root and kills it). **This is a source
  fragility, not a port bug** — flagging it because any conclusion drawn about
  detonation damage from `DamageGrid` alone will be wrong.

---

## Mechanics present in the source but absent from the port

Ranked by how much they change results. Items 1-9 are now **implemented**; 10-13 are
**still absent** and documented in the module docstring.

| # | mechanic | source | effect if ignored | status |
|---|---|---|---|---|
| 1 | Whole AoE path: `j`/`k` loops, `RadiantAoe`, 7 falloff kinds, `Depth`, `Shape`, `MaxAbsorb`, `aoeIsPool`, detonation staging | `L590-967`, `L1294-1385` | **Total.** Every torpedo in SDX2 puts 100 % of its damage here. The old port scored a 75,000-damage warhead as 1 damage. | fixed |
| 2 | Heavy-armour fixture (gdm 0.5 → 1.0, integrity 16,500 → 16,520) | `CubeBlocks_Armor.sbc:858`, `ModAdjuster/…/CubeBlocks_Armor.xml:31` | 2× error on the most common block in the game. Halves survivability everywhere it is HP-limited. | fixed |
| 3 | `areaDamageScale` / `detDamageScale` and their ArmorCore divisions | `L668-669`, `L749-750` | Ceramic looked 10× weak to torpedoes when it is exactly neutral. Sign-of-the-answer error. | fixed |
| 4 | `ObjectsHit.CountBlocks` semantics + `MaxObjectsHit` const | `L443`, `L487`, `L784-787`, `L1000-1003` | The old port counted every block as an object. With `CountBlocks = false` (all SDX2 PDCs and sabots) `objectsHit` increments **once per grid** (`L1001`), so `MaxObjectsHit = 1` means "one grid", not "one block". Verified: `MaxObjectsHit=3, CountBlocks=false` still penetrates 20 blocks. | fixed |
| 5 | `baseScale == 0` is not a skip | `L762`, `L766-772`, `L780` | Old port `continue`d when `bscale <= 0`. Source deals 0 damage and, on a non-cutoff round, **zeroes the pool**. An `Armor = 0f` ammo would look like it passed through instead of dying on contact. | fixed |
| 6 | `smallVsLargeBuff` 0.25 and `gridSizeBuff` | `L460`, `L488`, `L490-491`, `L761` | 4× over-estimate of large-grid guns shooting small grids (and the buff is *sticky* for the whole call once set). Verified 10,000 → 2,500. | fixed |
| 7 | `FallOffScaling` / `FallOffDistance` / `FallOff.MinMultipler` | `L424-427`, `L754-755`, `AmmoConstants.cs:1274` | Up to `1/MinMultipler` over-estimate at range. No SDX2 round sets `MinMultipler != 1`, so currently inert — but the flag now exists and is derived, not assumed. | fixed |
| 8 | `MaxIntegrity` immunity and the `blockDmgModifier < 1e-9` immunity | `L674-675`, `L679-683` | The zero-modifier case was a `ZeroDivisionError`; `MaxIntegrity` mis-modelled as `break` instead of `basePool = 0; continue`. | fixed |
| 9 | `Settings.Enforcement.DirectDamageModifer` / `AreaDamageModifer` / grid multipliers / `DisableSmallVsLargeBuff`, and `hitEnt.DamageMulti`, and `hits` (VirtualBeams) | `L667-668`, `L438-440`, `CoreSettings.cs:189-209` | All default to 1, so inert on a default server — but they were not even expressible. Now a `SETTINGS` object plus `damage_multi`/`hits` parameters. | fixed |
| 10 | Deferred block destruction on grids ≥ 2500 blocks | `L863`, `L891-903`, `L136-176` | Kills on big grids are applied ~10 ticks late and *batched*, so a second projectile in the same tick still sees the block alive. Now surfaced as a `deferred` list in the result and as `grid_block_count`; the tick delay itself is not simulated (there is no clock here). | partial |
| 11 | Shields: `ShieldType.Heal` early return, NerdShield pool absorption, Defense Shields `partialShield` early-exit | `L385-411`, `L489`, `L521-560`, `L653-657` | Against a shielded target the pool is reduced *before* any block is touched, or the loop aborts on the first protected block. Order-of-magnitude when shields are up. Needs live shield state; `partial_shield` is exposed as a callback so the `L653` abort is at least testable. | partial |
| 12 | `GlobalDamageModifed` / `BlockDamageMap` per-subtype direct+area modifiers | `L727-740` | Server-config only. Now expressible via `block_damage_map={subtype: (direct, area)}`. | fixed (as a hook) |
| 13 | Client-side predicted health (`_slimHealthClient`), deformation, projectile impulse, EWAR, `SelfDamage`/same-logical-group suppression (`L379-383`) | `L664`, `L857`, `L869-885`, `L925-935` | Cosmetic or non-damage. `SelfDamage` matters only for friendly fire. | not modelled, documented |

---

## Broken assertion

`test_hifi.py:46`

```python
check("  blockHp = 16500 / 0.5", 33000, B['heavy']().integrity / B['heavy']().gdm)
```

Now reports `tabletop=33,000  hifi=16,520  d=49.9%`. **The tabletop side is the wrong
one.** Both its inputs are refuted by the shipped data: the integrity is 16,520 (SDX2
titanium recipe) and the gdm is 1.0 (the 0.5 is commented out in both the vanilla
definition and SDX2's override). I did not weaken the test.

The correct replacement is `check("  blockHp = 16520 / 1.0", 16520, ...)`. Note that the
two neighbouring checks that *look* like they depend on this — `penetration depth` and
`hits to kill = 33000/600` — do not: the first is pool-limited (34 blocks either way)
and the second hardcodes 33,000 on both sides, so it is self-consistent arithmetic that
happens to no longer describe any real block. That second check is not *failing*, but
it is now asserting a fictional number and should be re-baselined to `16520/600 = 27.5`.

---

## Problems found outside my file (not touched)

1. **`components.py:14-21`** — the docstring says `wc_damage.sdx_blocks()` "still
   hardcodes 0.5 … so the two disagree by design". That is now stale; they agree.
   Same file's claim that the disagreement is intentional should be deleted.
2. **Latent duplicate-key hazard in `Custom.Types`** — `AmmoConstants.cs:1264` builds the
   map with `customBlockDef.Add(def, customDef.Modifier)`, a `Dictionary.Add` that
   throws `ArgumentException` on a duplicate key, inside a loop over *all* game
   definitions × *all* declared `Types`. Any ammo that lists the same `SubTypeId` twice
   will throw during `AmmoConstants` construction. I checked every SDX2 ammo and none
   does — `sdx_ammo_sabot80mmImprovised.cs` has two `sdx_armorCeramic` entries but they
   are in two separate `AmmoDef`s (`sabot80mmImprovisedTurreted` L80-90 and
   `sabot80mmImprovisedFixed` L282-292), one each. No live bug; noted only so nobody
   "tidies up" by merging modifier lists.
3. **`WC SessionModHandlers.cs:284`** — `if (ArmorCorePriorityMap.TryGetValue(type, out prevPrio));`
   has a stray semicolon, so `prevPrio = int.MinValue;` on the next line runs
   unconditionally. `DefinitionPriority` is therefore inert and every armour definition
   is treated as "first seen": later definitions always win, and the `Remove` branches
   for re-classification never execute. Upstream WC bug; only matters if two mods claim
   the same armour subtype.
4. **`catalogue.json` carries `kin_res`/`ene_res` for all 204 subtypes** but nothing in
   the damage path outside `wc_damage.py` uses the *energy* side. SDX2's `NonArmor`
   ArmorDefinitions put `EnergeticResistance` 12.5–200 on cockpits, cargo, tanks,
   beacons and ship cores. Any energy-damage model that ignores those is wrong by up to
   200×. Whoever owns the ship/subsystem sims should check they are being read.

---

## What I changed in `wc_damage.py`

* Docstring rewritten as a full line-by-line transcription map with the real line
  numbers, plus an explicit list of what is *not* modelled and why.
* New: `Enforcement`/`SETTINGS`, `ARMORCORE_ACTIVE`, `Falloff`, `AoeShape`, `SkipMode`,
  `AoeDef` (with the `AmmoConstants` radius/depth derivations), `Scales`, `BlockGrid`
  (port of `RadiantAoe` incl. the multi-cell inflate at `L1359-1372`), `damage_grid`
  (the full `i`/`j`/`k` loop), `uniform_grid` helper, and a `__main__` self-check.
* `Ammo` gained `grid_small`, `count_blocks`, `skip_blocks_for_aoe`,
  `no_grid_or_armor_scaling`, `energy_area`, `energy_det`, falloff fields, `aoe`, `det`,
  and the derived `AmmoConstants` flags as properties (`damage_scaling`,
  `armor_scaling`, `grid_scaling`, `custom_damage_scales`, `falloff_scaling`,
  `max_objects_const`). Negative `custom` modifiers are dropped at construction, per
  `AmmoConstants.cs:1261`.
* `base_scale` kept its signature and return shape; `fire` kept its signature and all
  four original result keys (`log`, `kills`, `touched`, `pool_left`) and gained
  `objects_hit`, `destroyed`, `deferred`, `aoe_log`, `damage_primary`, `damage_aoe`.
  `subsystem_demo.py`, `layout.py`, `engage.py`, `pareto.py` and `defense_sim.py` all
  still run.
* Fixtures: heavy armour corrected; anti-ceramic modifiers rewritten as the mod's own
  `x/0.3` expressions; added `sabot100mmOpa`, `sabot80mmImprovised`, `PDC50mmLight`,
  three torpedoes and the HEKP warhead so the AoE path has real ammo to drive it.
