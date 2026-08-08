# SDX2 build guide

Prescriptive. Every number is measured; `docs/DOCTRINE.md` has the derivations and the
t-statistics. Where something is uncertain it says so rather than rounding to advice.

---

## 1. Point defence

**Buy weight-1 mounts, one per SCF point: `PdcMcrn`, `PdcUnn`, or `PdcOpa`.**
They are interchangeable in practice — at fleet load PdcUnn 3.39 / PdcMcrn 5.00 /
PdcOpa 9.89 leakers, and PdcUnn's advantage does not survive every scenario. Take whichever
you can supply.

**Never `PdcMcrnAdv` (80 rpm) or `PdcOpaAdv` flak (30 rpm).** Both are *worse than no fire
control at all*: 26.8 and 38.9 leakers against 29.8 and 39.5 with a policy. A mount that
fires ~3 rounds inside the 2.4 s engagement window cannot contribute, and PdcMcrnAdv's
160 m interaction radius does not rescue it. `PdcImprovised` is fine (weight 1, 900 rpm)
despite the worst dispersion in the mod.

**Move the dead mounts. This is the cheapest win available.**
On the stock 8-ring the mounts at **180° and 225° never fire** — own-hull occlusion. A
stock hull fights with **5.8 of its 8 mounts**. Relocating them broadside costs nothing and
takes 2.64 → 1.71 leakers.

**Recessed pits: fine at ~50° arc or wider, catastrophic below.**
Heavy overlap (half-angle ≈ 1.5–2× pit spacing) is leaker-neutral and saves 8–9% ammo, so
build them if you want the mounts armoured. A 20° fan scores **36.5 against 5.9**. The
threat lives inside 18° of the axis at 3 km, so there is no sky to partition — narrow arcs
only subtract.

Do not put uniform pits on a fleet: consorts need ~77° off-axis to defend the lead.

---

## 2. Torpedoes

**`LightTriple`, exclusively. 10 points, 3 tubes, 28.8 torpedoes/min.**
`MediumTriple` is the same points and the same tubes for **12.0/min** — it fires
`ShotsInBurst 1` at `rof 30`, where LightTriple empties its 3-round magazine in 1.3 s and
reloads in 5 s. Same cost, less than half the output, invisible on a stat sheet.

| core | PDC pts → mounts | torpedo loadout | tubes | alpha | torp/min | TGC/min if sustained |
|---|---|---|---|---|---|---|
| Picket | 5 | 1× LightTriple + 1× Single | 4 | 4 | 34 | 811 |
| Corvette | 8 | 2× LightTriple + 1× ImprovisedDouble | 8 | 8 | 72 | 1,728 |
| Frigate | 12 | 5× LightTriple + 1× Single | 16 | 16 | 149 | 3,576 |
| Cruiser | 26 | 7× LightTriple | 21 | 21 | 202 | 4,838 |
| Carrier | 20 | 7× LightTriple | 21 | 21 | 202 | 4,838 |

### Ammunition

| round | NPC cost per shot | note |
|---|---|---|
| **Torpedo190mmImprovised** | **free** (40 Fe, 20 Ni, 20 Pb, 25 U, 60 Mg, 20 Au, 20 Si, 2 Ag) | barely weaves; PDCs eat it one-on-one, but 96 at once leak 49.5–56.75 against *every* defence |
| Torpedo160mm (all) | 24× TorpedoGuidanceComputer | |
| Torpedo220mm (all) | 24× TorpedoGuidanceComputer | |
| **Torpedo220mmHekp** | 24× TGC | **effectively unstoppable — see below** |

**Hekp and BlastFrag beat all point defence.** They fly a scripted terminal S-weave
(±300/+250/−150/+100 m rungs switching at 2500/2000/1500/1000/500/200 m, 2652 m/s²) *inside*
the PDC envelope, where the OffsetRatio weave is gated off. And no SDX2 weapon sets
`UseLimitlessPDSolver`, so every PDC fires **pure linear lead** and cannot track it. Hekp
leaks **35.7 of 48** against the best policy, where Plasma leaks 5.9. If you can afford
Hekp, nothing defends against it; if you are defending, nothing you build helps.

### Firing doctrine

**Alpha strikes above ~50 torpedoes, or don't bother.** Defence saturates on *absolute*
salvo size, not torpedoes-per-mount: 3 Cruisers (78 mounts) leak 50.75 against 126, while
3 Corvettes (24 mounts) leak 5.92 against 48. Better ratio, nine times the leakage — the
`CycleTargets = 4` acquisition window means each mount examines at most 4 candidates, so
past ~50 targets fire scatters and nothing dies.

Crossing that cliff makes you roughly **15× more component-efficient per hit** (2,470 TGC
per hit in an even 3v3, versus 160 with six attackers).

**Sustained fire is economically impossible** — one Cruiser firing continuously burns 4,838
NPC components per minute. Alpha and then go quiet.

---

## 3. Internals

**One reactor powers everything.** Every power-consuming block in SDX2 sums to 406 MW; a
single `sdx_reactorFusion1x1` makes 440 MW. A combat Corvette draws ~10.5 MW.

**Carry 3–4 reactors anyway, and 3–4 gyro computers.** WeaponCore walks subsystems
Power → Utility → Offense → Thrust, so reactor mass is ablative shielding for the gyro
computer. Losing your single `sdg_rcsGyroComputer` sets rotation authority to **zero,
permanently**. Extra gyro computers add no torque; they are spares.

**Ceramic, not heavy armour.** One 1×1 ceramic block absorbs an entire sabot. Steel does
not stop sabots at *any* thickness — they tunnel 20–33 blocks. Ceramic is 0.1 kinetic /
1.0 energetic resistance, so it does nothing against torpedo warheads (Energy AoE) and
everything against PDC and railgun fire.

*Caveat: armour numbers rest on `wc_damage.py`, the one port never verified against
compiled source. Treat them as well-reasoned rather than proven.*

**Railguns: OPA medium fixed.** Only `RailgunOpaMediumFixed` and
`RailgunUnnMediumTurreted` carry both sabot and airburst, and airburst is the ceramic
counter (×700 vs ceramic, strips a 220,000 hp block to 4.5%). Turreted railguns cost 300×
Electromagnet against 40× for fixed — 7.5× for the convenience.

---

## 4. Formation

**Three or more hulls on the threat axis. Not abreast.**

| layout | leakers (salvo 48) |
|---|---|
| abreast | 1.14 |
| line, any spacing 500–3000 m | **0.00** |
| line, 4000/8000 m | 0.21 |
| one hull carrying everything | 3.07 |

Spacing is forgiving — anything from 500 m to 3000 m works. A screen's envelope intersects
the torpedo track ~3× longer than a hull abreast and catches the boost phase. Keep ±250 m
lateral offset so pass-by angular rate stays under the 0.1309 rad/tick slew cap.

**Hull count matters; gun distribution does not.** At 24 total PDC points every split from
16/4/4 to **0/12/12** leaks 0.00 — the hull being shot at needs *no* point defence if two
screens sit up-threat. Three 5-mount pickets (15 points) beat one 24-mount hull by 4×.

**Lead with the cheap hull.** If the attacker targets the *front* picket instead of the
hull behind it, the advantage inverts — 9.5 versus 4.0 abreast. This doctrine depends on
the enemy shooting the valuable ship, which a good opponent will not reliably do.

*Open: measured at salvo 48, below the saturation cliff, so several rows are pinned at
0.00. Hull count and spacing are solid; whether a heavy or light screen wins under real
saturation is unresolved.*

---

## 5. Script

**FleetPD v1.4.0+, default settings, one per hull.** Six-rung range ladder; a mount drops a
rung when ≥4 of its own rounds are airborne. Sustained battle: 4.25 cumulative leakers and
14.5 waves survived, against 21.75 / 5.6 for a shot-counting version.

- Fire is **never** withheld — across ~45 tested policies, redirecting fire always beat
  baseline and withholding it always lost.
- **Never heat-cycle**: 131.6 cumulative leakers against 21.8. A degraded mount still fires
  ~12 rd/s; a cooling-pinned one manages ~1.3. The heat cliff is better crossed than
  guarded.
- Ray de-confliction, duty rotation, demand-maxing and per-hull edge caps were all tested
  and are not worth running.

---

## 6. The short version

1. Move your 180° and 225° PDC mounts. Free, ~35%.
2. Fly three hulls in a line up the threat axis, cheapest in front.
3. LightTriple only. Alpha above 50 torpedoes or hold fire.
4. Improvised rounds are free and saturate perfectly well at scale.
5. Hekp is unstoppable — buy it if you can, and don't expect to defend against it.
6. One reactor works; carry four, plus four gyro computers.
7. Ceramic over steel.
8. Run the script, and never let it withhold fire.
