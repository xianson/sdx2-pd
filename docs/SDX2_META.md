# Sigma Draconis Expanse 2 — combat rules & meta analysis

Derived by reading the actual mod source (not wiki//lore), then re-implementing the
damage resolution offline and simulating it.

Sources:
- `3580645761` SDX2: Weapons — 33 ammo defs, 51 weapon defs (WeaponCore CoreParts)
- `2815514917` SDX2: Core — armour/drive/component `.sbc`
- `3154371364` WeaponCore 3.0 — `SessionDamageMgr.cs` is the authority on damage

Scripts (rerunnable): `parse_coreparts.py`, `parse_weapons.py`, `sdx_model.py`,
`slab_sim.py`, `pdc_sim.py`.

---

## 1. How damage actually resolves

This is the single most important thing, and it is *not* "damage vs HP".

```
blockHp_eff = (integrity - accumulated) / GeneralDamageMultiplier
scale       = gridMult * armorMult * (heavy|light)Mult      [-1 = disabled]
              * customSubtypeMult                            [per-block override]
              / armorCoreResistance[kinetic|energetic]
perHit      = (BaseDamageCutoff > 0 ? cutoff : pool) * scale

perHit <= blockHp : block survives, takes perHit,  pool -= perHit
perHit >  blockHp : block dies,                    pool -= blockHp / scale
```

Consequences that drive the whole meta:

1. **`BaseDamageCutoff` is the penetration mechanic.** A round with a cutoff walks
   successive blocks along its path, spending `cutoff*scale` per block, until its
   pool runs out. Sabots have cutoff 10k–20k. PDC rounds have none (pool dumps into
   one block).
2. **Resistance is a divisor.** `KineticResistance = 0.1` means **10× damage taken**,
   not 10× resistance. Easy to misread — the SDX2 comment even says so.
3. **Killing a block costs the projectile more pool than chipping it**
   (`blockHp/scale` vs `cutoff*scale`). Cheap blocks that die are a *more* expensive
   obstacle per block than tough blocks that survive.
4. **Per-subtype `CustomScalesDef` overrides everything else.** This is where the
   real balance lives and it is invisible unless you read the ammo files.

Vanilla armour is classified by *subtype-name substring* (`SessionSupport.cs:118`):
anything containing "Armor" + "ArmorBlock"/"HeavyArmor"/"BlockArmor" counts as armour;
"Heavy" in the name makes it heavy armour. Vanilla armour gets **no** ArmorCore
kinetic/energetic resistance — only the ammo's `Armor`/`Heavy` multipliers and its
`GeneralDamageMultiplier` (0.5 on heavy armour, which inflates effective HP 2×).

---

## 2. The armour blocks

| block | integrity | GDM | eff HP | mass | kin res | ene res |
|---|---|---|---|---|---|---|
| Light steel 1×1 | 2,500 | 1.0 | 2,500 | 500 kg | — | — |
| Heavy steel 1×1 | 16,500 | 0.5 | **33,000** | 3,300 kg | — | — |
| SDX2 Ceramic 1×1 | 220,000 | 1.0 | **220,000** | 7,700 kg | **0.1 (=10× dmg)** | 1.0 |

Ceramic = 22 × `sdx_componentCeramicPlate` (10,000 integrity, 350 kg each).
It is the mod's **only** custom armour block — everything else is vanilla steel.

---

## 3. The core triangle

**Every sabot carries an explicit anti-ceramic multiplier.** This is the designed
counter and it is decisive:

| ammo | armour mult | ×vs ceramic | net vs ceramic |
|---|---|---|---|
| sabot80mm (all) | 0.3 | 70.0 | **21.0** |
| sabot100mmUnn | 0.3 | 35.0 | 10.5 |
| sabot100mmOpa | 0.3 | 36.7 | 11.0 |
| sabot100mmMcrn | 0.3 | 38.7 | 11.6 |
| airburst100mm fragment | 0.3 | 700.0 | **210.0** |

Result, per single round fired at a solid stack:

| | light steel | heavy steel | ceramic |
|---|---|---|---|
| sabot100mmMcrn dmg/block | 5,400 | 5,400 | **208,800** |
| pool cost per block | 8,333 | 5,400 | 208,800 |
| **blocks penetrated** | 21.6 | **33.3** | **0.9** |

- **Steel does not stop railguns at any buildable thickness.** A 100mm sabot tunnels
  20–33 blocks. Twelve metres of heavy armour still leaks on round 1.
- **One ceramic block absorbs one entire sabot**, and survives with ~5% HP.
  N ceramic blocks ⇒ N+1 sabot hits on the same spot. Linear and predictable.
- Ceramic's 10× kinetic weakness is the balancing cost — and it applies to
  **PDC fire only**, because torpedo warheads deal *Energy* AoE damage
  (their `BaseDamage` of 1 is a dummy; all the damage is in `AreaOfDamage`).

So the triangle is:
- **Railgun sabots** → shut down by ceramic, devastating vs steel
- **PDC kinetic** → 5× effective vs ceramic, poor vs heavy steel
- **Torpedo AoE (Energy)** → ignores ceramic's weakness, craters steel

### Best armour schemes (rounds on the same spot to kill an internal)

| scheme | t/m² | sabot100 | PDC40mm hits | 160mm plasma torp |
|---|---|---|---|---|
| 3× heavy | 9.9 | **1** | 170 | 1 |
| 6× heavy | 19.8 | **1** | 335 | 2 |
| 1× ceramic | 7.7 | 2 | 41 | 3 |
| **1× heavy + 1× ceramic** | **11.0** | **2** | **96** | **4** |
| 2× heavy + 1× ceramic | 14.3 | 2 | 151 | 4 |
| 2× heavy + 2× ceramic | 22.0 | 3 | 188 | 6 |

**Recommendation: heavy steel outer, ceramic immediately behind it.** The steel
soaks PDC kinetic (where ceramic is 5× soft) and eats the largest torpedo AoE tick;
the ceramic is the sabot backstop. A sabot only loses 5,400 pool crossing the steel,
so it still arrives at the ceramic and is stopped there. 11 t/m² buys 2 sabots,
96 PDC hits and 4 torpedoes — roughly double the value of pure heavy at similar mass.

Pure heavy armour at *any* thickness is a trap: it is the best anti-PDC armour per
tonne (16.7 hits/tonne vs ceramic's 4.8) but it does literally nothing against the
railguns that dominate long range.

---

## 4. Weapons

### Railguns — the long-range decider
All fire at 1 rd/60 ticks with 2.8–7.7 s reloads, 10 km targeting, 9–10 km/s muzzle.

| weapon | ammo | pool | cutoff | dev° | mount |
|---|---|---|---|---|---|
| RailgunMcrnMediumFixed | sabot100mmMcrn | 180,000 | 18,000 | 0.000 | fixed ±5° |
| RailgunOpaMediumFixed | sabot100mmOpa | 140,000 | 19,000 | 0.022 | fixed ±5° |
| RailgunUnnMediumTurreted | sabot100mmUnn | 120,000 | 20,000 | 0.250 | −5/+40 |
| RailgunPgenMediumFixed | sabot80mmPgen | 80,000 | 10,000 | 0.023 | fixed, RoF 100 |
| RailgunUnnLightFixed | sabot80mmUnn | 80,000 | 10,000 | 0.000 | fixed ±5° |

Fixed mounts have **perfect accuracy (dev 0.00°)** and the highest pools. The MCRN
medium fixed is the single hardest-hitting gun in the mod. The UNN medium *turret*
pays for its traverse with 0.25° dispersion — at 10 km that is a 44 m spread, i.e.
it will miss a ship-sized target more often than not. **Fixed railguns + fly the
ship as the turret is strictly correct**, which is exactly the Expanse flip-and-burn
fighting style (and what your autopilot work already supports).

### PDCs — burst weapons, not sustained ones

| mount | ammo | cold rd/s | s to overheat | sustained | fade | HHM |
|---|---|---|---|---|---|---|
| PdcPgenAdv | 50mmLight | 50.0 | never | 50.0 | 100% | 1 |
| PdcUnnAdv | 40mm | 40.0 | 46.9 | 12.4 | 31% | 1 |
| PdcUnn | 40mm | 33.3 | 30.4 | 7.9 | 24% | 1 |
| PdcMcrn | 40mm | 30.0 | 30.4 | 7.1 | 24% | 1 |
| PdcOpa | 40mm | 20.0 | 40.6 | 6.1 | 31% | 1 |
| PdcMcrnAdv | 50mmHeavy | 1.3 | never | 0.6 | 48% | 5 |
| PdcOpaAdv | **50mmFlak** | 0.5 | never | 0.5 | 100% | 11 |

Heat model (from `WeaponController`/`WeaponShoot`): overheat at `MaxHeat`, resume at
`Cooldown × MaxHeat` (0.82), and RoF degrades from 80% heat, only clearing at 40%.
Because recovery (82%) is *above* the degrade-clear threshold (40%), an overheated
PDC never returns to full rate during a fight.

**PDCs deliver a strong ~30 s opening burst then fall to ~25% output.** Wave-2 and
wave-3 torpedo salvos face a far weaker screen than wave 1. This is the single
biggest exploitable timing in the mod.

`PdcPgenAdv` is an outlier: 50 rd/s, 45,000 heat-sink rate, **no overheat at all**,
and the tightest dispersion (0.075°). If it is available to you it is strictly the
best PDC in the mod by a wide margin.

### Anti-torpedo: hit-count is what matters
Torpedoes have `Health` 4–5. What kills them is `HealthHitModifier`:

- **40mm (HHM 1): needs 4 direct hits.** With 0.5 m projectiles and 0.1–0.4°
  dispersion, that is 4–19 s of fire per torpedo at 2 km.
- **50mmHeavy (HHM 5): one hit.**
- **50mmFlak (HHM 11): one hit** — and it is a proximity round. `PDC50mmFlak` →
  `Flak50mmStage2` (Smart, arms within **100 m** of the target) → **45 ×
  `FlakFragment50mm`** in a 45 m radius. Effectively a guaranteed kill in a bubble.

**`PdcOpaAdv` is the only flak mount in the mod.** At 0.5 rd/s it is slow, but every
round is a kill; four of them out-perform sixteen 40mm PDCs against massed torpedoes.

---

## 5. Torpedoes and saturation

All torpedoes: cruise **260 m/s**, `AccelPerSec` 15,600 (so they hit cruise in one
tick), 24 km max trajectory but **38–42 s lifetime ⇒ ~10 km real reach**.
Warheads are Energy AoE, exponential falloff, depth 4, armed after 90 ticks:

| torpedo | AoE dmg | radius |
|---|---|---|
| Plasma220mm / TrailerTorp | 75,000 | 11 m |
| Torpedo160mmBelter / 220mmBelter / 190mm | 60,000 | 5–10 m |
| Torpedo160mmPlasma | 50,000 | 6 m |
| Torpedo220mmHekp (fragment) | 40,000 det | 3 m |

At 260 m/s a torpedo spends ~11 s inside a 3 km PDC envelope — a long exposure.

### Leakers vs salvo size (simulated)

Realistic case: half the mounts bear on the threat axis, 0.5 s retarget dead-time.

| loadout | 8 | 12 | 16 | 24 | 32 | 48 |
|---|---|---|---|---|---|---|
| 4× PdcUnn | 4 | 8 | 12 | 20 | 28 | 44 |
| 8× PdcUnn | 0 | 4 | 8 | 16 | 24 | 40 |
| 16× PdcUnn | 0 | 0 | 0 | 8 | 16 | 32 |
| 8× PdcUnnAdv | 0 | 0 | 0 | 0 | 0 | 8 |
| 8× PdcPgenAdv | 0 | 0 | 0 | 0 | 0 | 0 |
| 8× PdcOpaAdv (flak) | 0 | 0 | 0 | 0 | 0 | 4 |
| 4× flak + 8× PdcUnn | 0 | 0 | 0 | 0 | 0 | 8 |

**Past the saturation threshold, every extra torpedo leaks 1:1.** There is no graceful
degradation — this is a hard cliff. Salvo sizing is therefore the whole game on
offence: a salvo of *threshold+1* is wasted, a salvo of *2× threshold* halves through.

Practical threshold for a well-defended ship (8–16 mixed PDCs): **~16–24 torpedoes
simultaneously on one bearing.**

Offensive corollaries:
- Split salvos across bearings — bearing_frac is the dominant term. Two 12-torpedo
  salvos from opposite arcs beat one 24-torpedo salvo from ahead.
- Time wave 2 for 30–60 s after wave 1, when PDC heat has collapsed output to 25%.
- `TorpedoLauncherLightTriple` (3 mags, 5 s reload) has by far the best salvo density.

---

## 6. PDC placement

Elevation limits are the binding constraint — every mount has a blind cone below it:

| mount | elevation | sphere coverage |
|---|---|---|
| PdcMcrn | −40 / +90 | 82.1% |
| PdcMcrnAdv | −20 / +90 | 67.1% |
| PdcUnn / PdcUnnAdv | −20 / +80 | 66.3% |
| PdcOpaAdv (flak) | −15 / +90 | 62.9% |
| PdcPgenAdv | −14 / +90 | 62.1% |

Rules that fall out:
1. **Minimum 2 mounts per axis** to cover the sphere, in practice 6+ for a convex hull.
2. `PdcMcrn` has by far the best sky coverage (−40°) — use it on hull positions where
   the depression angle matters (dorsal/ventral centreline).
3. `RestrictionRadius = 0.75` with `CheckForAnyWeapon = true` — **no two weapons of
   any type may be placed within 0.75 m of each other**. Plan mount spacing early.
4. Mount PDCs proud of the hull. LOS masking is not in my sim, but `MuzzleCheck` is
   false and `DisableLosCheck` is false, so the engine does check scope LOS — a PDC
   sunk into a recess loses arcs it nominally has.
5. Flak (`PdcOpaAdv`, 4 km) outranges every other PDC by 1 km. Put flak where it gets
   the earliest look down the likely torpedo bearing — i.e. bow and stern.

---

## 7. Mobility

Epstein drives, all water-fuelled, remarkably cheap on power (0.1–1.5 MW):

| drive | size | thrust |
|---|---|---|
| Industrial 9×9 | 9×9×6 | 703 MN |
| Industrial 7×7 | 7×7×5 | 350 MN |
| MCRN Military 7×7 | 7×7×6 | 292 MN |
| UNN Military 7×7 | 7×7×7 | 252 MN |
| OPA Military 7×7 | 7×7×8 | 226 MN |
| MCRN Military 5×5 | 5×5×4 | 133 MN |
| MCRN Military 3×3 | 3×3×3 | 60.5 MN |

MCRN leads thrust at every size class; OPA is the worst *and* the longest (7×7×8 eats
8 m of hull). Industrial drives out-thrust all military ones — if there is no
role-play restriction, `sdx_driveIndustrial9x9` at 703 MN is the mass-mover.

Reference: 703 MN on a 10,000 t hull = 70 m/s². The armour numbers above are 7.7–14.3
t/m² of frontal area, so armour mass is what actually caps your acceleration.

---

## 8. What this means — build guidance

**Offence**
- Fixed medium railguns (MCRN if available) are the primary killer. Turreted railguns
  are a dispersion trap at their 10 km design range.
- Fight nose-on and fly the ship as the gun mount.
- Torpedoes are a saturation weapon, not a chip weapon. Fire threshold+50% or don't
  fire. Split bearings, and exploit the 30 s PDC heat collapse for wave 2.

**Defence**
- Armour: heavy steel outer + ceramic backing, ~11 t/m². Never pure steel (railgun
  food), never pure ceramic on the skin (PDC food).
- Ceramic only needs to be one block thick to stop one sabot per block — spread it,
  don't stack it, unless you expect repeat hits on the same spot.
- PDCs: `PdcPgenAdv` if you can get it (no overheat), else `PdcUnnAdv`. Mix in
  4× `PdcOpaAdv` flak — it is the only real answer to massed torpedoes.
- Assume your PDC output falls to 25% after 30 s. Either overbuild mount count or
  accept that you win in the first wave or not at all.
- Internals: sabots that get through do ~18,000 per block to non-armour. Compartment-
  alise and duplicate critical blocks; a single sabot line can clear 20+ internals.

---

## 9. Caveats — what is NOT modelled

Stated plainly so the numbers aren't oversold:

- **LOS/hull masking of PDC arcs.** Approximated by the `bearing_frac` parameter.
- **Turret slew time and WeaponCore's real target-acquisition cadence.** Approximated
  by a flat retarget dead-time.
- **Torpedo evasion.** `OffsetRatio` is 0.2–0.7 on these torpedoes, meaning they weave.
  This should *reduce* PDC hit rates below my numbers, i.e. my saturation thresholds
  are optimistic for the defender.
- **My hit-probability model** is a uniform-disc dispersion approximation
  `P = (r_target / R·tan θ)²`, not WeaponCore's internal ballistics.
- **Shields.** Every ammo has a `Shields.Modifier` (PDC 3.75, torpedoes 1.0) but no
  shield mod is in this world's list, so I ignored them.
- **MES/NPC weapon variants** were parsed but excluded from the tables.
- `planet_*`-style environmental effects, gravity (`GravityMultiplier` 3 on PDC rounds)
  and atmospheric behaviour are not modelled — this is all vacuum analysis.

The highest-value next step is validating the PDC saturation threshold in-game
against the sim, since that is where the modelling assumptions are thinnest.

---

## 10. Railgun tracking, evasion, and PDC control

Scripts: `evasion_sim.py`, `run_evasion.py`, `tracking_sim.py`, `run_tracking.py`.

### 10.1 What the predictor actually does

`AiTargeting.cs:128` — `accelPrediction = (int)AimLeadingPrediction > 1`. Railguns and
PDCs both use `Advanced` (=3), so the lead solution **solves for target acceleration**.
`WeaponTracking.cs:902` — accel below `targAccelSqr < 2.5` (≈1.58 m/s²) is ignored.

Consequences:
- **Constant lateral acceleration is worth exactly nothing.** It is predicted out.
- **Gentle chatter is worth nothing** — under 1.58 m/s² the predictor drops the accel
  term entirely and reverts to linear lead, which a low-accel target doesn't beat.
- Sabots have `SpeedVariance = 0`, so flight time is deterministic. No free error.

### 10.2 The mechanism that does work: over-lead poisoning

The predictor samples *instantaneous* accel and extrapolates `0.5·a·tf²` of parabolic
drift. If you oscillate faster than the projectile's flight time you barely move — but
the shot is still thrown to where that parabola said you'd be.

```
miss  →  0.5 · a · tf²            (chatter period << flight time)
a_req >  2 · r_target / tf²       to guarantee a clean miss
```

Measured (MCRN medium fixed, dev 0.00°, 15 m hull radius, 40 m/s² lateral):

| pattern | 10 km | 8 km | 6 km | 4 km | 2 km |
|---|---|---|---|---|---|
| none / **constant lateral** | 100% | 100% | 100% | 100% | 100% |
| square flip 0.5 s | **3%** | 81% | 100% | 100% | 100% |
| square flip 1 s | 28% | 66% | 100% | 100% | 100% |
| square flip 2 s | 62% | 84% | 100% | 100% | 100% |
| square flip 4 s | 81% | 94% | 100% | 100% | 100% |
| barrel roll 2 s | **0%** | 100% | 100% | 100% | 100% |
| random re-aim 2 s | 86% | 95% | 100% | 100% | 100% |

**Faster chatter is strictly better**, down to your control-loop limit. Random re-aiming
is *worse* than a regular fast square wave — randomness lowers the mean |accel| that gets
extrapolated. Barrel roll is excellent when its period is tuned, brittle when it isn't.

Cost of entry, by range (10,000 t hull, 1.5 MN RCS blocks):

| range | flight time | a required | RCS blocks |
|---|---|---|---|
| 10 km | 1.00 s | 30 m/s² | 200 |
| 8 km | 0.80 s | 47 m/s² | 312 |
| 6 km | 0.60 s | 83 m/s² | 556 |
| 4 km | 0.40 s | 187 m/s² | 1,250 |
| 2 km | 0.20 s | 750 m/s² | 5,000 |

Requirement scales as **R⁻²**. Evasion is a long-range tool and dies completely inside
about 5 km. 200 RCS blocks to be effectively immune at 10 km is very buildable; 5,000 to
be immune at 2 km is not.

### 10.3 The trade you asked about

There are two separate costs to jinking, and only one of them is the obvious one:

1. **Mass/volume.** 200–560 RCS blocks is real tonnage and hull area competing with
   armour and PDCs.
2. **It does not cost you your own firing solution** — provided you jink on RCS. RCS
   translates the hull without rotating it, so a fixed railgun keeps pointing. If you
   instead jink by vectoring the main Epstein drive you must rotate ~90° and your fixed
   guns go off-target entirely. **Jink with RCS, never with the main drive.**

So the trade is mass, not mutual exclusivity — which makes evasion much more attractive
than it first looks, and makes RCS block count a primary design stat rather than an
afterthought.

### 10.4 The constraint that actually binds: hull slew

A fixed mount must hold the lead vector inside `AimingTolerance = 1.0°`. Required hull
rate is `v_perp / R`, and gyros (`sdx_gyroscopeBraced_large`, 3.36e7 N·m, same as vanilla)
cap how fast you get there.

| hull | gyros | α (°/s²) | spin-up to track a 300 m/s crosser @10 km / @3 km |
|---|---|---|---|
| corvette 2 kt, 60×18 m | 20 | 58.9 | 0.0 s / 0.1 s |
| frigate 6 kt, 90×24 m | 20 | 8.9 | 0.2 s / 0.6 s |
| cruiser 15 kt, 140×34 m | 20 | 1.5 | 1.2 s / 3.9 s |
| cruiser 15 kt, 140×34 m | 60 | 4.5 | 0.4 s / 1.3 s |
| capital 40 kt, 220×50 m | 20 | 0.23 | 7.6 s / 25.2 s |
| capital 40 kt, 220×50 m | 60 | 0.68 | 2.5 s / 8.4 s |

Required tracking rate (°/s):

| v_perp | 10 km | 6 km | 4 km | 2 km | 1 km |
|---|---|---|---|---|---|
| 300 m/s | 1.7 | 2.9 | 4.3 | 8.6 | 17.2 |
| 800 m/s | 4.6 | 7.6 | 11.5 | 22.9 | 45.8 |

**Fixed railguns are a small-hull weapon.** A corvette tracks anything. A 40 kt capital
with 20 gyros literally cannot bring a fixed gun to bear on a close crosser — and its
alternative, the UNN medium *turret*, hits only 12% at 10 km because of 0.25° dispersion.
That is the central capital-ship dilemma in this mod, and it is a genuine design hole
rather than something you can build around: gyro-spam the capital, or accept turret miss.

**Crossing velocity, not lateral accel, is what beats big ships.** Get inside 3 km with
high `v_perp` and a capital's fixed guns simply cannot follow.

### 10.5 PDC field of view — the blind cone

A full-azimuth turret whose mount normal points "outward" covers elevations
`[elev_min, elev_max]`. A target at angle θ off the normal sits at elevation `90 − θ`.
So `MaxElevation < 90` creates a **blind cone of `90 − MaxElevation` straight along the
mount's own normal.**

| mount | elevation | blind cone | usable arc off normal | of a ring of 8, bearing |
|---|---|---|---|---|
| PdcMcrn | −40..90 | 0° | 0°..130° | 5 |
| PdcMcrnAdv | −20..90 | 0° | 0°..110° | 5 |
| **PdcUnn / PdcUnnAdv** | −20..80 | **10°** | 10°..110° | 4 |
| PdcOpaAdv (flak) | −15..90 | 0° | 0°..105° | 5 |
| PdcPgenAdv | −14..90 | 0° | 0°..104° | 5 |

**A hull-face-mounted `PdcUnn` cannot engage a threat coming straight down its own
normal.** If your bow PDCs are UNN and the torpedoes come from dead ahead, those mounts
contribute nothing. Either use MCRN/Pgen/OpaAdv on the primary threat axis, or cant the
UNN mounts ~15–20° off the face so the threat axis falls inside their arc.

### 10.6 Rolling the hull to cycle fresh PDCs

Ring of 8 `PdcUnn`, beam threat, 90 s engagement, heat model live:

| roll period | total shots | vs static |
|---|---|---|
| static | 6,674 | — |
| 20 s | 6,915 | **+7%** |
| 30 s | 6,900 | +7% |
| 45 s | 6,805 | +4% |
| 90 s | 6,388 | −4% |
| 120 s | 6,075 | −9% |

Honest answer: **rolling is worth about +7% and is not a real tactic.** Mounts rotated
out of arc stop contributing entirely, which nearly cancels the heat relief. Rolling
*slower* than the heat cycle is actively harmful. Build more mounts instead.

### 10.7 Minimum PDC count to guarantee a kill

Smallest N that leaks zero, by salvo size and how many mounts can bear:

| mount | salvo 8 (100%/50%/33% bearing) | salvo 16 | salvo 32 |
|---|---|---|---|
| PdcUnn | 2 / 7 / 11 | 4 / 15 / 23 | 7 / 31 / 47 |
| PdcUnnAdv | 1 / 1 / 1 | 1 / 3 / 5 | 1 / 7 / 11 |
| PdcPgenAdv | 1 / 1 / 1 | 1 / 3 / 5 | 1 / 6 / 8 |
| PdcOpaAdv (flak) | 1 / 1 / 1 | 1 / 3 / 5 | 2 / 6 / 8 |

Control budget — torpedoes one mount can kill across a full 3 km→150 m approach:

| mount | torps killed per approach |
|---|---|
| PdcPgenAdv | 62.5 |
| PdcUnnAdv | 37.8 |
| PdcMcrn | 28.3 |
| PdcMcrnAdv | 18.3 |
| PdcOpaAdv (flak) | 15.1 |
| **PdcUnn** | **5.1** |

`PdcUnn`'s 0.4° dispersion is catastrophic against 2.2 m torpedoes — it is 7× worse than
`PdcUnnAdv`, which is the *same gun* at 0.1°. **Dispersion, not rate of fire, is the
dominant PDC stat for point defence.** Never use `PdcUnn` in an anti-torpedo role.

### 10.8 Range-band summary

| band | sabot ToF | fixed gun vs chatter | turret hit | hull rate @300 m/s | who wins |
|---|---|---|---|---|---|
| 10 km | 1.00 s | 62% (3% if fast chatter) | 12% | 1.7°/s | evasion viable |
| 8 km | 0.80 s | 84% | 18% | 2.1°/s | evasion marginal |
| 6 km | 0.60 s | 100% | 33% | 2.9°/s | fixed guns dominate |
| 4 km | 0.40 s | 100% | 74% | 4.3°/s | fixed guns dominate |
| 3 km | 0.30 s | 100% | 100% | 5.7°/s | PDC envelope opens |
| 2 km | 0.20 s | 100% | 100% | 8.6°/s | crossing beats jink |
| 1 km | 0.10 s | 100% | 100% | 17.2°/s | knife fight |

**There is no evasion answer inside 6 km. Armour is the only defence there.** That is
what makes the ceramic layer non-optional rather than a preference.

### 10.9 Suggested in-game tests

These are the assumptions worth checking, in priority order:

1. **Chatter vs a fixed railgun at 10 km.** Two ships, one running RCS square-wave at
   ~0.5 s period and ≥30 m/s², the other firing MCRN medium fixed. Predicted: hit rate
   collapses from 100% to <10%. This is the single biggest claim and the easiest to test.
2. **The 1.58 m/s² predictor floor.** Same setup at 1.0 m/s² — predicted: no benefit at
   all, hit rate stays 100%. Confirms the threshold is real.
3. **PdcUnn blind cone.** Park a torpedo run dead-on a face-mounted UNN PDC. Predicted:
   it never fires. Cant it 20° and it engages.
4. **PDC heat fade.** Sustained fire for 60 s, log rounds/s. Predicted: ~33 rd/s falling
   to ~8 rd/s, never recovering while the trigger is held.
5. **Saturation threshold.** 16 vs 24 torpedoes into a known PDC fit. Predicted: hard
   cliff, then 1:1 leakage.
6. **One ceramic block per sabot.** Single ceramic block, shoot it twice with a 100mm
   sabot. Predicted: survives the first at ~5% HP, dies to the second.

---

## 11. Airburst — the ceramic counter, and why aimpoint stability is a weapon

### 11.1 The round nobody talks about

`airburst100mmUnn` / `airburst100mmOpa`: a 10 km/s carrier that bursts **25 m short** of
the target and throws **24 fragments in a 45° cone**. Each fragment is pool 24,000,
cutoff 1,000, range 500 m — and carries a **×700 custom modifier vs `sdx_armorCeramic`**
(net ×210 after the 0.3 armour mult). That is the largest modifier in the mod.

| target | scale | dmg per block per fragment | effect |
|---|---|---|---|
| Light steel | 0.3 | 300 | chips 12% |
| Heavy steel | 0.3 | 300 | chips 1% — **useless** |
| **Ceramic** | **210** | **210,000** | **strips 95% of a 220,000 hp block** |

One fragment takes a ceramic block from full to **10,000 / 220,000 hp (4.5%)**. A round
carries 24 of them.

So the triangle closes:

```
ceramic   stops sabots      (1 block absorbs 1 whole round)
airburst  strips ceramic    (24 blocks to 4.5% per round, useless vs steel)
sabot     kills everything  through stripped ceramic — 21 blocks destroyed,
                            20 internals killed, in ONE round
```

Measured: a sabot into fresh ceramic destroys **0 blocks** and stops dead. The same sabot
into airburst-stripped ceramic destroys **21 blocks and kills 20 internals**, paying only
952 pool to breach.

### 11.2 Only two mounts can run the combo

| railgun | ammo |
|---|---|
| **RailgunOpaMediumFixed** | sabot100mmOpa + **airburst** |
| **RailgunUnnMediumTurreted** | sabot100mmUnn + **airburst** |
| MCRN medium fixed/turreted, Pgen, UNN light, all Improvised | sabot only |

This **reverses my earlier ranking**. I called MCRN Medium Fixed the best gun on raw pool
(180,000, 0.00° dispersion). Against an unarmoured or steel-armoured target it still is.
Against ceramic — i.e. against anyone who has read the same files — MCRN has *no answer*
except double-tapping, and **`RailgunOpaMediumFixed` is the better weapon** despite lower
pool and 0.0215° dispersion, because it is a fixed mount that can carry both ammo types.

### 11.3 Why you can't just double-tap instead

A ceramic block dies to 2 sabots. So why carry airburst? Because hitting the *same 2.5 m
block* twice is not something you get for free:

- `AiTargeting.cs:1335-1343` — WeaponCore builds a **randomised deck** of candidate
  blocks (`GetDeck(..., xRnd)`) and cycles it by `AcquireAttempts`. A turret re-aims at a
  different block essentially every acquisition. **Turreted railguns cannot deliberately
  double-tap.** The UNN medium turret is doubly cursed here: 0.25° dispersion is a 43.6 m
  spread at 10 km, giving ~0% chance of repeating a block.
- A **fixed** mount fires when the hull boresight is within `AimingTolerance = 1.0°` of
  the solution — 105 m at 6 km. The impact point is therefore set by *your pointing*, not
  by WeaponCore's block picker.

| railgun | dev° | P(2nd shot on same block) @10 km / 6 km / 4 km |
|---|---|---|
| MCRN med fixed | 0.0000 | 100% / 100% / 100% |
| OPA med fixed | 0.0215 | 11% / 31% / 69% |
| Pgen med fixed | 0.0230 | 10% / 27% / 61% |
| UNN med TURRET | 0.2500 | 0% / 0% / 1% |

(Dispersion only — target motion between shots makes all of these worse.)

**This makes pointing stability a damage stat.** A hull that can hold its boresight on one
block between reloads roughly doubles its effective railgun damage against ceramic,
because it converts "2 sabots strip 2 blocks" into "2 sabots kill 1 block and the second
tunnels 20 deep". That is a direct payoff for autopilot pointing quality, not just a
handling nicety.

### 11.4 The other fragmenting rounds

| round | chain | verdict |
|---|---|---|
| `Torpedo220mmHekp` | → HEKPWARHEAD → Fragment1 (30,000 pool, cutoff 1,000, **all armour mults 1.0**) + 40,000 det in r=3 | Ignores the 0.3 armour reduction entirely, but only 1,000/block. Drills ~30 blocks then detonates. Anti-internal, not anti-armour. |
| `Torpedo160mmBelter` | 60,000 Energy AoE r=6, plus 5 × `FragmentBelter` | `FragmentBelter` is 30 m/s, 1,800 m range, **HHM 5** — slow submunitions that also kill torpedoes (Health 4). A defensive minefield as much as an offensive round. |
| `Torpedo160mmBlastFrag` | → 15 × `Explosion160mmCluster` at **500 m standoff**, 2,000 dmg each, armour mult 1.0 | 30,000 spread over 15 pellets. Bypasses armour multipliers but far too weak to matter vs heavy steel (33,000/block). Skip. |
| `Torpedo160mmPlasmaAtt` | 4,000 direct + 10,000 AoE at **r=20** | Widest AoE in the mod but low damage, and `Grids.Large = 0.1` — it is an anti-*small*-grid round. |

### 11.5 Detection is not the constraint

| system | range |
|---|---|
| Lidar | 24,000 m |
| World ViewDistance / SyncDistance | 35,000 / 20,000 m |
| Torpedo targeting | 16,000 m (but ~10 km real reach) |
| **Railgun** | **10,000 m** |
| PDC / flak | 3,000 / 4,000 m |

Lidar sees 2.4× further than the longest-ranged weapon can shoot. **You will always see
them before you can hit them**, so there is no scouting/stealth game here — engagements
open at 10 km and close monotonically. That also means the evasion window (§10.2, viable
only beyond ~6 km) covers roughly the first 40% of the closing timeline and nothing after.

### 11.6 Revised offensive doctrine

1. Open at 10 km with **airburst** to strip ceramic across the target's engaged face.
2. Follow with **sabots** into the stripped cone — each one now tunnels ~20 blocks.
3. Carry `RailgunOpaMediumFixed` for this; MCRN fixed only if you know the target is
   steel-armoured or you trust your pointing to double-tap.
4. Torpedoes remain a pure saturation weapon — fire threshold+50%, split bearings, and
   time wave 2 into the 30 s PDC heat collapse.
5. Inside 6 km evasion is dead and it becomes an armour-and-PDC attrition fight, so decide
   before then whether you are committing or disengaging.
