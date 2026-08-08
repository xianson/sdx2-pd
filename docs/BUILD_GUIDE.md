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

**The launcher fixes the warhead, and that decides everything.** Raw throughput is a trap:
LightTriple has the best rate but fires Belter, the round PD stops easily.

| launcher | pts | tubes | torp/min | warhead | leakers of 48 | eff. hits/pt/min |
|---|---|---|---|---|---|---|
| **MediumDouble** | 7 | 2 | 12.0 | **Torpedo220mmHekp** | **35.7** | **1.27** |
| **LightDouble** | 7 | 2 | 12.0 | **Torpedo160mmBlastFrag** | **36.4** | **1.30** |
| LightTriple | 10 | 3 | 28.8 | Torpedo160mmBelter | 3.3 | 0.20 |
| MediumTriple | 10 | 3 | 12.0 | Torpedo220mmBelter | ~3 | 0.08 |
| ImprovisedDouble | 7 | 2 | 14.4 | Torpedo190mmImprovised (free) | 2.2 | 0.16 |
| LightSingle | 4 | 1 | 5.0 | Plasma + PlasmaAtt (interceptor) | -- | -- |

**Buy Double launchers.** MediumDouble and LightDouble are ~6x more effective per point
than LightTriple, because Hekp and BlastFrag fly the terminal S-weave that no point defence
can lead. Use LightTriple/ImprovisedDouble only when you want cheap volume to saturate.

| core | PDC pts → mounts | torpedo loadout | tubes | alpha | torp/min | TGC/min if sustained |
|---|---|---|---|---|---|---|
| Picket | 5 | 2× MediumDouble | 4 | 4 | 24 | 576 |
| Corvette | 8 | 4× MediumDouble | 8 | 8 | 48 | 1,152 |
| Frigate | 12 | 8× MediumDouble | 16 | 16 | 96 | 2,304 |
| Cruiser | 26 | 10× MediumDouble | 20 | 20 | 120 | 2,880 |
| Carrier | 20 | 10× MediumDouble | 20 | 20 | 120 | 2,880 |

(Swap in LightTriple/ImprovisedDouble if you need volume over penetration.)

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

**Three hulls on the threat axis at 0 / 2000 / 4000 m, ±250 m lateral.** The spacing is a
real optimum, not a plateau — measured at salvo 96, above the saturation cliff:

| layout | leakers |
|---|---|
| abreast | 23.57 |
| 0/500/1000 | 9.57 |
| 0/1000/2000 | 4.71 |
| **0/2000/4000** | **2.21** |
| 0/3000/6000 | 5.64 |
| 0/4000/8000 | **26.86 — worse than abreast** |

Spread too far and the line is worse than no formation at all. A screen's envelope
intersects the torpedo track ~3x longer than a hull abreast and catches the boost phase;
past ~3000 m separation that stops holding. Keep the +/-250 m lateral offset so pass-by
angular rate stays under the 0.1309 rad/tick slew cap.

**Distribution matters, and every station needs a real battery.** At 24 total PDC points:

| lead/screen/screen | leakers |
|---|---|
| **4/10/10** | **1.79** |
| 2/11/11 | 2.07 |
| 8/8/8 | 2.21 |
| 16/4/4 | 7.07 |
| 12/6/6 | 16.00 |
| 0/12/12 | 16.79 |
| 24/0/0 (no line) | 32.71 |
| 5/5/5 (15 pts) | 38.43 |

Heavy screens and a light lead is right — but the lead still needs a few mounts (0/12/12
collapses), and thin screens are the worst failure (12/6/6 is 7x worse than 8/8/8 at the
same cost). **Rule: give every station at least ~8 mounts, then put surplus on the
screens.**

**Points beat hull count under saturation.** 5/5/5 across three hulls (15 points) scores
38.43 -- WORSE than one hull carrying 24 (32.71). A pack of cheap lightly-armed hulls
cannot defend itself against a real salvo, however good the geometry.

**Lead with the cheap hull.** If the attacker targets the *front* picket instead of the
hull behind it, the advantage inverts -- 9.5 versus 4.0 abreast. The doctrine depends on the
enemy shooting the valuable ship, which a good opponent will not reliably do.

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
