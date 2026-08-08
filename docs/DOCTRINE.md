# SDX2 point defence — what to do and why

Everything below is measured in a simulator whose interception path is verified
**against compiled WeaponCore source** — 747 differential tests covering the RNG, the
acquisition deck, the aim predictor, the quartic solver, the projectile-vs-projectile
collision test, and the full firing model (heat, RoF truncation, reload).

**Firing-model verification, and its five known divergences.** Proven correct: both
integer truncations (`TicksPerShot = (uint)(3600f/RateOfFire)` exact for RoF 1..3600);
the heat state machine (engage 0.8, clear 0.4, overheat checked immediately after the
per-shot add, resume at 0.822, `HsRate = HeatSinkRate/3`); the **one-way door** — in a
120 s sustained run the mount overheats three times, resumes twice, and degrade NEVER
clears, exactly as claimed; **`ProhibitCoolingWhenOff` gates on `Comp.Cube.IsWorking`**,
so `ToggleWeaponFire` cools while disabling the block freezes heat (this claim was
load-bearing for several policies and it holds); and the reload chain, matching within
3 ticks and -0.13% on a pure-reload duty cycle. A 2.4 s window is 72 vs 72 rounds, exact.

Divergences, all small and all in the same direction: **cooling actually runs every 19
ticks, not 20** (`FutureEvents.Tick` commits `_offset` after running callbacks), so real
cooling is ~5.26% stronger and the sim UNDER-cools; there is a **15-tick overheat grace
window** the sim omits; a float32-vs-float64 truncation differs by 1 rpm at 4 of 147 grid
heats for rof=80 (only sub-100-rpm mounts can straddle a boundary); above MaxHeat the
real Lerp extrapolates below 0.25x where the sim clamps; and the sim assumes infinite
magazine restock. Net: sustained-fire output is **~2-3% pessimistic**, which shifts
absolute numbers slightly but not the orderings these mechanics drive. Numbers are leakers unless stated, with paired
t-statistics. Damage/armour modelling is deliberately excluded — it is not verified and
is not what this study is about.

---

## 0. READ THIS FIRST — the study was calibrated against the wrong threat

Every defensive result below was measured against **`Plasma220mmTorp`**. At the SAME price
(24x TorpedoGuidanceComputer per shot), **`Torpedo220mmHekp` walks through everything**:

| payload, 48 fired at 3 hulls | no PB | burst-only b14 | full ladder |
|---|---|---|---|
| Plasma220 (the study standard) | 17.25 | **5.92** | 6.75 |
| **Hekp 220** | 36.62 | **35.71** (t=+47.6) | **39.04** |
| BlastFrag 160 | 36.54 | 36.42 | ~38.9 |
| Belter 220 | 4.88 | 3.33 | 8.75 |

Note the ladder is **WORSE than no script at all** against Hekp. The policy actively hurts.

**Mechanism, verified in our own bit-exact ports rather than conjectured.** Hekp and
BlastFrag fly a *scripted terminal S-weave* — staged `DesiredElevation` rungs of
+-300/+250/-150/+100 m switching at 2500/2000/1500/1000/500/200 m from target, with
2652 m/s^2 of authority. That is INSIDE the PDC envelope, precisely where the OffsetRatio
weave this whole study modelled is gated OFF (`OffsetMinRange` 2000-2500 m).

And the defence cannot lead it: for PROJECTILE targets the accel-tracking
`AdvancedProjectile` solver is gated behind **`UseLimitlessPDSolver`, which no SDX2 weapon
sets**. Every SDX2 PDC therefore fires **pure linear lead**, which is unleadable against a
2.6 km/s^2 S-weave. Per-round miss rate doubles (21.8% -> 43.6%). Health 5 vs 4 compounds it.

**Consequences:**
1. **Re-tune everything against Hekp, not Plasma.** The ladder/EDD/respread edifice is
   optimised for the most stoppable expensive torpedo in the mod.
2. **Nothing in the legal PB actuator set answers the S-weave** — nor does a full-battery
   PdcMcrnAdv refit (36.2 leakers). The counter has to be geometric (escort placement,
   closing speed), not scripted.
3. The one PD mechanism that might still work is the **anti-torpedo torpedo** (section 1),
   because HHM 11 one-shots and does not need to lead a weave four times.

*Caveat:* this rests on two verified facts (the bit-exact staged-Approach port, and the
linear-lead-only projectile fire control) but has **not been flown in-game**.

---

## 1. What to actually do

Ordered by size of effect. The first two need no scripting at all.

### Formation — the largest lever, and free
An axial **picket line** (hulls at +1200 / +2400 m up-threat, ±250 m lateral) instead of
abreast: **0.00 leakers on 14/14 seeds under every policy, including no PB at all**. At
salvo 96, where every fire-control policy collapses to ~38 leakers, pickets hold at 1.25.
A picket's envelope intersects the torpedo track roughly 3× longer and catches the boost
phase.

*Doctrine:* lead with the cheap or tanky hull. If the attacker targets the **front**
picket instead, the advantage inverts (9.5 vs 4.0 stock).
*Confidence:* one agent, 14 seeds. **Wants independent replication** — it currently makes
most of the rest of this document nearly irrelevant, which is reason enough to check it.

### Mount placement — free, ~35%
On the stock ring, mounts at **180° and 225° never fire** — own-hull occlusion. A stock
8-mount hull fights with about **5.8 mounts**. A broadside refit at the same 8 SCF points:
2.64 → 1.71 leakers (t=−2.88).

Also: `build_ship` assigns ring angles by mix-dict order, so any mixed-battery comparison
that is not explicitly placement-controlled is confounded by *where* kinds land rather
than what they are.

### The PB script — descend on IN-FLIGHT COMMITMENT (`reroll.descend_inflight`)
Six rungs at 1.0 / 0.8 / 0.65 / 0.5 / 0.38 / 0.28 of base tracking range, mounts started
spread across them. **A mount descends one rung when >= 4 of its OWN rounds are
airborne** (kill-sized: torpedo Health 4, PDC40mm HHM 1), with a ~0.35 s refractory.
Legal via `MonitorProjectile` spawn/despawn counts on your own weapons.

This replaces the shot-counting burst trigger and is the strongest policy found:

| scenario | infl4 | burst-only b14 | t | full ladder | t |
|---|---|---|---|---|---|
| **sustained 3h s24 x 20 waves, cum leak** | **4.25** | 21.75 | **-16.81** | 16.17 | **-6.89** |
| **sustained waves-to-death** | **14.50** | 5.58 | +5.21 | 7.92 | +3.96 |
| 3h s48 leakers | 5.21 | 5.43 | -0.27 n.s. | 7.71 | **-3.11** |
| 1h s24 leakers | 1.14 | 1.36 | -0.49 n.s. | 1.57 | -1.15 n.s. |

*Read it honestly:* the single-wave gain over burst-only is NOT significant. **The
sustained result is the significant one** — 4x fewer cumulative leakers and 2.6x the
waves survived — and sustained survival is the real objective.

*It is not fire reduction.* In the sustained fight it fires MORE than both incumbents
(+1726 rounds, t=+5.67, peak heat 29.9%). Single-wave it fires ~14% fewer, via fewer
eligible targets at low rungs, never by ceasing fire.

*Mechanism:* in-flight >= k trips fastest at LONG range, because a long time-of-flight
piles up unresolved commitment. So mounts stop dwelling on far rungs — which is precisely
the over-commitment failure the oracle study identified as the dominant loss.

*Controls:* it is the signal, not a faster clock. burst-only at b6/b8/b10 and a
wall-clock `descend_stale(0.35)` are all worse. Adding ray-conflict demotion does not
help (6.60 vs 5.80).

*Implementation trap — this is the single most important line in this document for
anyone writing the script:* **time-keyed policy state must survive the wave clock
resetting.** `fleet_efficiency.wave` sets `t = 0.0` per wave while `ladder.py:134`
compares `ctx['t'] - st['bottom_at'] >= dwell`; across a boundary that goes NEGATIVE and
strands the mount at 0.28x range (798 m) for most of the next wave. Two agents found this
independently from opposite directions. Measured cost of getting it wrong: 40.9 vs 4.25
cumulative leakers, and it is why the shipped ladder degrades every wave after its first.

**MANAGE CROSS-WAVE STATE — this is worth more than any trigger choice.** Reset each
mount's rung to the designed opening spread at every wave boundary (detected legally from
the PB clock plus inbound going 0 -> N). Two independent agents converged on nearly the
same number by different routes:

| 3 hulls, s24, g6, 20 waves | waves-to-death | cum leak |
|---|---|---|
| burst-only b14 | 5.58 | 21.75 |
| full ladder t40 b14 | 7.92 | 16.17 |
| **respread(burst-only)** | **14.58** | **4.33** |
| **descend_inflight(k=4)** | **14.50** | **4.25** |

respread vs full ladder: wtd +6.67 (t=+4.48), cum -11.83 (t=-6.78). Single-wave at s24
both incumbents leak ~0, so **essentially ALL sustained leakage was state rot**, not
combat. `descend_inflight` wins for the same underlying reason — in-flight count
naturally zeroes between waves, so it is immune to the stranding by construction.

*Trade-off:* respread fires ~55% more rounds and at 6 s gaps ratchets heat to the
DegradeRof cliff by wave ~20 (peak 82%). The advantage survives to 40 waves anyway
(20.50 vs 41.67 cum). If you fight long at short gaps, add `heat_floor` — let heat DEMOTE
a mount down the ladder (a redirect, never a withhold) — which caps heat near 51%. At
15 s gaps heat never binds (~21%).

The older burst-and-descend ladder, kept for reference: same rungs, but each mount
descends after ~14 of its own rounds.

* **It never ceases fire.** The burst counter triggers a *re-aim* (range change), not a
  cease-fire. This is the whole reason it works.
* For the shot-counting variant, `burst = 12-16` is a plateau; **b=10 does not transfer**
  across scenarios, b>=18 degrades.
* The bottom-to-top cycle **never fires** in practice and can be deleted.
* **Do NOT add ray de-confliction. RETRACTED.** I previously recommended it for long
  battles. That was wrong: its apparent sustained advantage was differential exposure to
  a CROSS-WAVE STATE BUG in `ladder.py` (below), not to the ray test. Once the state is
  managed, de-confliction adds nothing and costs at long wave gaps.
* **Never heat-cycle.** 131.58 cumulative leakers against 21.75. Actively harmful, not
  merely inert.
* **Add the per-hull edge cap** (`bo + hullcap 650`) — the only policy found that beats
  burst-only. Each hull caps its mounts' range at (its OWN nearest threat + 650 m) rather
  than a fleet-wide scalar. Pooled over 42 pairs: d=-0.62 leakers, t=-1.92, 20 better /
  17 tied / 5 worse (sign test p~0.002), ammo-neutral, and it never hurt at any load.
  Small but directionally solid; recommended as a free bolt-on.
  *Why it works:* a fleet-wide window blinds consorts. At lead-nearest 500 m a consort
  1000 m away is 1118 m from the edge torpedo but gated at 1000 m — it sees nothing.
  That is the precise reason `window_nearest` collapses from 9.14 to 28.18 at fleet load.
* Exempt sub-100-rpm mounts (e.g. PdcMcrnAdv) from the ladder entirely — with ~5 rounds
  per engagement they lose more to range narrowing than de-confliction can recover.

### Recessed PDC pits — free, but only pays without a script
**Why partitioning fails:** the sky is not a hemisphere to be tiled. From the lead hull
the entire threat lives inside **18 deg of the +X axis at 3 km**, widening to only ~32 deg
terminally. There is nothing to partition. A disjoint sector spends most of the 2.4 s
window blind, which is why `fan d20 p10` scores 36.50 against stock's 5.92.

* **With the ladder: neutral.** Good pits (heavy overlap, half-angle ~1.5-2x the pit
  spacing, e.g. `d20 p36`) tie the ladder while firing **8-9% fewer rounds** (t=-6 to -13).
* **Without a script: a genuine ~23% win.** 4.88-5.04 vs 6.33 at 1 hull (t=-3.3). The pit
  crudely emulates the ladder by forcing re-acquisition at the cone edge — dead-round %
  barely moves (59.6 -> 57.8), so it is re-prioritisation, not efficiency.
* **CORRECTION to an earlier reading:** a good pit is NOT equivalent to deleting a mount.
  `kmount 5` (9.71) is significantly worse than a heavy-overlap pit design (5.92), so the
  partition retains essentially full battery value while removing sky. The
  "iris-25 ~ kmount-4" equivalence I cited holds only for the aggressive configurations.
* `kmount 6` is bit-identical to stock, independently confirming the stock hull really
  does fight with <=6 of its 8 mounts.
* Uniform pits across a FLEET are badly negative — consorts need the ~77 deg off-axis view
  to defend the lead terminally. This is the fleet analogue of the stock ring's accidental
  occlusion problem.

**Verdict:** build them if you want the mounts physically protected — you give up nothing
measurable under a policy and save ammunition — but they cost ~1.8 leakers against thin
streams, so it is scenario-dependent rather than free.

### Hardware — a dead end
No legal 8-point mix beats pure **8× PdcMcrn**. PdcMcrnAdv loses despite its 160 m
interaction radius (80 rpm cannot replace two 30 rd/s streams); a flak annulus loses
badly. The one mix that won used Protogen gear, which is **not available to us**.

### The fourth lever — torpedo tubes are an unclaimed PD layer
`BaseTorpedoLauncherDefinition.cs:33` declares `Threats = { Grids, Projectiles }`, and the
Goliath light tube carries **`Torpedo160mmPlasmaAtt` — an anti-torpedo torpedo** — as a
selectable ammo. `SetActiveAmmo` and `ToggleWeaponFire` are both PB-registered.

Torpedo HHM = 11, so **one interceptor hit one-shots any torpedo**: no 4-hits problem, and
therefore no dead-round class at all — the failure mode that dominates PDC defence simply
does not exist here. The ATT definition is broken (it never stages, so it sits at 260 m/s)
but the break leaves it with un-staged 15,600 m/s^2 steering and a ~4.3 m turn radius.
Duelled against the audited torpedo model: **P(kill) = 1.00 vs Belter at every launch
range**, vs Hekp at <=4 km, vs Plasma220 at 2 km (0.79 at 3 km).

It is a layer, not a defence — ~1-2 shots per tube per approach (12 s reload) and 24
guidance computers per shot. But it is **density-robust (immune to the trickle attack)**
and it is the **only counter found for Hekp**.

**One in-game unknown gates it:** whether a fixed launcher auto-acquires projectile
targets. That cannot be settled offline and is the single highest-value experiment
remaining — roughly a 20-minute DS test.

### A kill is not a kill — a flaw in the leaker metric itself
Shot-down SDX2 torpedoes **fragment on death** (`ProjectileClose`, `FragOnEnd`) and the
fragments have **Health = 0, so they are untargetable**. Killing a torpedo close in does
not mean stopping it:
* Belter -> 5 x 1,000 damage on a converged course; "dirty" inside ~1,100 m
* Hekp -> its FULL 70,000 warhead; dirty inside ~700 m, so killing it there mitigates nothing
* BlastFrag -> 15 clusters inside 500 m
The harness's clean-kill scoring is accurate for Plasma220 only by accident — its fragment
ammo `Fragment220mm` is never defined in the mod.

Rescored at 24 seeds, true delivered damage vs Belter is **~2.2-2.5x the leaker score**.
Crucially the tax is **policy-insensitive** (kill-range CDFs are nearly identical across
policies), so it re-scores the THREAT, not the fire control: every ranking in this
document stands, but absolute effectiveness against fragmenting torpedoes is overstated.

**And torpedo TYPE dwarfs salvo shaping for the attacker: Hekp is ~10x the attack value
of any timing trick** — 15.9 leakers vs Plasma's 1.33, same ladder, same salvo.

---

## 2. The mechanics that explain all of it

**A round can only ever hit the ONE projectile it was fired at.**
`ProjectileHits.cs:601` reads `target.TargetObject as Projectile` — a single object, no
proximity loop. When a torpedo dies, every round already in flight toward it is lost and
cannot fall through to a neighbour. Measured: **55–70%** of all rounds fired by any
high-RoF mount.

**Interaction radius comes from `Shape.Diameter`, which SDX2 sets as a tracer length.**
For a LineShape, `bulletRadius` is the raw Diameter with no halving
(`ProjectileHits.cs:614`), and `targetRadius` is built from the *shooter's* CollisionSize
(the in-source comment calls it "really fucking random"). Against a torpedo:
PDC50mmHeavy 160 m, PDC50mmFlak 50 m, **PDC40mm / 50mmLight 3.417 m**. A 47× spread that
no dispersion-based reasoning can see.

**The engagement window is ~2.4 s.** Staged `Approaches` give torpedoes 1040–1300 m/s
terminal, so 2850 m of envelope is crossed almost instantly. **Throughput into that
window is the binding constraint on everything.**

**The acquisition randomiser has no entropy.** `CurrentSeed = int.MaxValue − UniquePartId`.
Selection is a *cycling deck walk*, not a fresh draw:
`chunk = (check_size × AcquireAttempts) % num_of_targets`, and `AcquireAttempts`
increments on every attempt and is never reset. `cycle_window`
(`AiTargeting.cs:612-623`) **subtracts where it should clamp**, so with the base
`CycleTargets = 4` a weapon examines 1 / 2 / **1** / 4 / 4-of-N candidates at
1 / 2 / **3** / 4 / ≥5 eligible — and if the single card it examines fails `accept()` it
acquires nothing at all that attempt.

Forcing `CycleTargets = 0` is worth **5.92 → 1.96** on identical hardware (t=−7.52), but
only PgenAdv has it and it is unavailable. The advantage is **not recoverable** by fire
control (see failures below).

**Fleet PD is structurally worse than single-hull.** At matched torpedoes-per-mount a
3-hull net leaks **30%** where one hull leaks **6%**. Torpedoes target the lead, so
consorts at 500–1000 m fire across extra range: longer flight means more rounds orphaned
by a kill, and wider dispersion against a fixed 3.417 m threshold. *Always scale salvo by
torpedoes-per-mount* — otherwise fleet tests saturate and discriminate nothing.

---

## 3. The governing principle

**Redirect fire; never withhold it.** Across ~45 policies there are no exceptions.
Anything that concentrates or re-prioritises engagement beats baseline. Anything that
reduces committed ordnance improves the waste *rate* and loses more torpedoes.

**Waste and leakage are nearly independent.** The oracle's no-commitment variant runs 56%
dead-round waste and still stops essentially everything. Do not optimise waste as a proxy
for defence.

---

## 4. The ceiling

An oracle with true torpedo state, per-target attribution of rounds in flight, and direct
assignment — still obeying arcs, LOS, slew, time-of-flight and one-target-per-round:

| | 1 hull s24 | 3 hulls s48 | 3 hulls s72 |
|---|---|---|---|
| best legal (burst-only) | 1.33 | 5.42 | 21.42 |
| oracle, full | 0.08 | 0.33 | 3.08 |
| oracle, no commitment accounting | 0.00 | 0.17 | 11.75 |
| oracle, greedy-nearest (assignment power only) | 3.92 | 20.92 | 45.67 |

* **EDD (earliest-time-to-impact) ordering is the whole game** — the entire gap between
  greedy-nearest (worse than baseline) and any oracle variant. Raw assignment power
  without deadline reasoning is actively harmful.
* **Commitment accounting is load-dependent** — worthless at 1–2 torpedoes/mount, worth
  11.75 → 2.58 at 3.0/mount. Over-commitment is the saturation failure mode, and
  `TargetId = -1` makes it structurally impossible for a PB to address.
* `window_nearest` was an accidental crude EDD (uniform torpedo speed ⇒ deadline order =
  range order). That is why it worked at all.

**Fire control is close to its ceiling.** The remaining 8–16× sits almost entirely in
capability the API denies.

---

## 5. Offence

Torpedo ammo costs 24× TorpedoGuidanceComputer per shot; PDC ammo is free. The attacker's
metric is **leakers per torpedo spent** at a fixed budget.

**Salvo shaping beats good fire control and loses to bad.** Fixed 48-torpedo budget,
positive = better for attacker:

| shape | vs ladder, 3 hulls | vs ladder, 1 hull | vs no PB, 3 hulls |
|---|---|---|---|
| trickle 8 @1.0s, then mass 1.5s later | +1.62 (t=+2.65) | **+2.67 (t=+5.51)** | −0.29 |
| even stagger 15 s | +2.29 (t=+2.43) | +1.58 (t=+2.44) | **−2.50 (t=−2.42)** |
| mass then trickle 8 | +1.33 (t=+2.31) | +0.17 | **+3.46 (t=+3.95)** |

The ladder is **saturation-adapted**: it works by redistributing mounts across many
targets, so a thin stream leaves mounts at descended short-range rungs with little in
view. Against a naive defence a thin stream merely donates time to spare capacity.

*Robust choice:* trickle 8 then mass — the only shape significantly positive against good
defence at both fleet sizes without backfiring against a naive one. Even-stagger is
stronger against the ladder but reverses hard against baseline, so it is a read-dependent
gamble.

*But note the attack narrows the defender's edge rather than defeating it:* against the
trickle at 1 hull, no PB still leaks 24.08 versus the ladder's 17.38.

---

## 6. Confirmed dead — do not re-propose

| idea | result |
|---|---|
| blind on/off toggling, hull duty rotation | +1.75 to +5.33; rotation *period* is irrelevant |
| heat cycling | actively harmful, 131.58 vs 21.75 cumulative |
| commitment bursts that idle a gun one time-of-flight | biggest dead% drop measured (62→47%), still lost |
| usage-based re-bracketing | +3.75 |
| saturation-triggered escalation ratchet | +9.33, worst in study |
| demand-maxing / committed-ordnance caps / arrival banding | merely tie static banding |
| sort-as-assignment, incl. zero-inversion omniscient control | significantly worse (t=+4.2) |
| conflict detection on leakers (100 seeds) | inert (t=−1.15); real effect is ~13% fewer rounds |
| explicit track + auction assignment | loses under saturation; ~78k ops/tick vs ~50k PB budget |
| eligible-count gating (1/2/4) to emulate CycleTargets=0 | fails: 15.2–24.9 vs 5.92, even with true positions |
| density-gated ladder (counter to salvo shaping) | null at permissive threshold, worse at aggressive (t=+2.70, +4.70) |
| restricted PDC arcs / recessed pits (WITH a policy) | cannot beat, replace or reinforce the ladder. Disjoint sectors catastrophic (36.50 vs 5.92); only heavy overlap reaches parity. On a THIN STREAM pits+ladder are significantly WORSE than stock+ladder (19.12 vs 17.33, t=+3.7) — the hoped-for density robustness does not materialise |
| edge-anchored ladder rungs (`edge_ladder`) | worse at all loads — the low rungs act as a time-staggered reserve, and anchoring destroys it |
| commitment-driven demotion / re-roll / inverted tie-break | 0-7% of gap, or catastrophic (+11 to +14). The incumbent's "less-committed yields" rule is correct |
| PURE re-roll (dip range, restore, no descent) | +5.79 / +21.21 — the range-gate makes a guaranteed drop cost 0.25-0.4 s of fire, so it is withholding in disguise. **The rung DESCENT is load-bearing, not incidental** |
| reload staggering / `ammo_park` | reload downtime is only ~23 mount-s per 20-wave battle (0.2% of live mount-time) and the leak gap already exists in the first quartile where downtime is ZERO. My reload hypothesis was FALSIFIED |
| `cliff_guard` (hold just under the 0.8 heat cliff) | catastrophic, 87.50 cum vs 24.33. A DEGRADED mount still fires ~12 rd/s; a cooling-pinned one fires ~1.3. **The cliff is better crossed than guarded** |
| visibility-pruned rungs (drop rungs a consort can never see from) | converts blind time to fire (+32 rounds, t=+4.71) but no leaker gain (-0.25, t=-0.51) |
| survival-threshold scoring P(leak<=2) instead of mean leakers | no rank flips anywhere; changes which LOAD is meaningful, not which policy wins |
| subsystem-protection objective, railgun PD (`Threats={Grids}` only), decoys, steering which hull eats leakers, reload phasing | all killed with mechanism in `OUTSIDE_CANDIDATES.md` |
| deliberate deck-phase desync | +5.93 / +12.36 (t=+9.4/+13.3). Collision is real and constant (81% of same-tick pairs draw the identical 4-slot chunk at 3h s48) but the only way to desync costs fire |

---

## 7. Soft spots

* **The picket result needs replication.** One agent, 14 seeds, and it dominates everything.
* **The ladder's sustained-battle advantage is unexplained.** Heat is *not* the mechanism
  (21.4% vs 22.2%, t=−1.52). Reload downtime is the leading hypothesis and is under test.
* **`wc_damage.py` is unverified** — every armour conclusion rests on a reading, not a
  proof. Out of scope for this study but still true.
* **Mount loss is not modelled.** A leaker never destroys a PDC, so the compounding term
  where losing a mount reduces throughput for all later waves is absent.
* **Hulls are static.** No manoeuvre, which is exactly the variable that would break a
  picket line or a 15 s staggered salvo.
