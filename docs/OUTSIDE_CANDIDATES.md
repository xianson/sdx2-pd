# Outside survey — premises, threat model, and the levers nobody scored

Role: second contrarian pass, deliberately outside the six prescribed angles
(re-roll/deck-phase, sustained waves, legal EDD, arc constraints, offensive
torpedo doctrine, sorting/WTA/tuning/triangulation) and outside
`FRONTIER_CANDIDATES.md` (actuator audit, placement, mixed batteries, pgen,
formation pickets). All C# claims verified against
`workshop/content/244850/3154371364` (CoreSystems) and `3580645761` (SDX2).

Implementations: `outside_policies.py`, `outside_probe.py`. Driver:
`outside_eval.py`, results in `outside_eval_out.txt`. SEEDS 701–724.

---

## The candidate list, with kill/keep reasoning

### 1. KEEP — "A kill is not a kill": fragment-on-death torpedoes (headline)

The harness treats every shot-down torpedo as a clean removal. The game does
not. `ProjectileClose()` (Projectile.cs:429-438) runs on EVERY projectile
death — shot down included — and spawns fragments when
`FragOnEnd && age >= MinArmingTime`. `FragOnEnd` (AmmoConstants.cs:1019) is
true whenever the fragment ammo resolves, TimedSpawns is off, and the
EndOfLife AoE is not arm-on-hit. Checked per SDX2 torpedo against the
launcher `Ammos` lists (fragments only resolve if listed, AmmoConstants.cs:391-419):

| torpedo | fragment | resolves? | on shoot-down spawns |
|---|---|---|---|
| Plasma220mmTorp, TrailerTorp, 160mmPlasma, 190mmImprovised | "Fragment220mm" | **NO — never defined in the mod** | nothing (clean death) |
| Torpedo220mmBelter / 160mmBelter | FragmentBelter | YES | 5 × (800 + 200 AoE) dmg, inherit full parent velocity + 30 m/s radial kick, unguided, 1800 m / 3 s |
| Torpedo220mmHekp | HEKPWARHEAD | YES | 1 × (30 000 + 40 000 EoL AoE) dmg, 1° cone on parent direction, accel 1200 → cap, **MaxLifeTime 30 ticks = 0.5 s** |
| Torpedo160mmBlastFrag | Cluster 160mm Explosion | YES | 15 × (2000 + 5000 EoL) dmg, 45° cone, 5000 m/s, 500 m reach |

And the fragments are **unkillable**: all four fragment ammos have
`Health = 0`, and WeaponCore only adds projectiles with `Health > 0` to the
target lists (Projectile.cs:3482). Arming (MinArmingTime 90 ticks = 1.5 s) is
long past by the time anything is inside the PDC envelope.

Two consequences:

* **The harness's leaker score is exactly right for the study's default threat
  (Plasma220mmTorp) — by accident.** SDX2 references a fragment ammo that does
  not exist ("Must list all primary, shrapnel, and pattern ammos" — they
  didn't). If the mod author ever fixes that def, every Plasma kill inside
  ~1–2 km starts delivering 9 fragments and the whole leaker-minimisation
  programme needs re-scoring.
* **Against Belter/Hekp/BlastFrag salvos the objective is wrong today.** A
  Hekp killed inside ~700 m on a converged trajectory still delivers its
  70 000-damage warhead — a "kill" that mitigates nothing, and the warhead
  cannot be engaged. Worse, the weave gates OFF inside OffsetMinRange
  (2000–2500 m), so inside the PDC envelope the parent is flying a converged
  PN course: fragments inherit a hitting trajectory. Kill RANGE, which no
  policy ever scored, decides whether a kill is real.

Measured (instrumented oracle-side kill log + ballistic continuation of the
per-type fragment model, `outside_probe.py`): see results section. This
re-scores existing policies; the actuatable consequence is threat-dependent
doctrine — against Hekp/Belter, prefer policies whose kill-distance
distribution sits beyond the fragment envelope, and count a close kill as a
partial leak when comparing candidates.

### 2. KEEP — hull-visibility ladder (implemented policy)

The stock ladder hands rung `_idx % 6` to every mount regardless of which hull
it stands on. But a rung is a range about the MOUNT, and consorts stand 500 s
metres off the threat axis: ship 2's mounts at rung 0.28 (798 m) can NEVER
acquire a torpedo on the lead's track (min possible distance 1000 m), and rung
0.38 (1083 m) sees only a ±417 m sliver. The incumbent parks consort mounts in
guaranteed-blind states for the cool+dwell cycle every descent — structural
fire-withholding that nobody classified as withholding because it is worn by
the winning policy. Fix: filter each hull's band list to rungs that can
geometrically reach the track (own-formation knowledge, PB-trivial via IGC +
the same launch-bearing dead-reckoning ctx['nearest'] already assumes).
Zero effect at 1 hull by construction; tested at 3 hulls.

### 3. KEEP (feasibility) — the anti-torpedo torpedo nobody loaded

`BaseTorpedoLauncherDefinition.cs:33` — torpedo tubes declare
`Threats = { Grids, **Projectiles** }`. The Goliath light tube
(`sdx_weapon_torpedoLauncherLightSingle.cs`) carries `Torpedo160mmPlasma` AND
`Torpedo160mmPlasmaAtt` as selectable ammos — ATT is an anti-torpedo
interceptor, and `SetActiveAmmo` is PB-registered. Torpedo HHM = 11 → any
interceptor hit one-shots a health-4/5 torpedo, immune to the 4-hits problem
and to dead-round waste (its round count IS its kill count, modulo misses).
The def is broken as shipped (stage 1 all-Ignore end conditions → caps at
260 m/s, audit item 2a) — but the failure mode leaves it with FULL unstaged
steering authority (15 600 m/s² at 260 m/s = 4 m turn radius), which is a
fine profile for a head-on intercept where the target supplies 1040 m/s of
closure. Feasibility simulated with the audited Torpedo2 machinery
(`outside_att.py`). In-game unknowns flagged there: whether a fixed launcher
auto-acquires projectile targets, and tube count per hull.

### 4. KEEP (rescoring, costs nothing) — survival threshold, not leaker count

2–3 leakers kill a hull and every leaker in this harness lands on the SAME
hull (all torpedoes target `fleet[0][0]`). So the deployable objective is
P(leakers ≤ 2), which weighs the distribution's tail, not its mean. Computed
per-seed for every policy in the eval — checks whether burst-only vs
full-ladder (means 5.92 vs 6.75 at 3h s48, but different mechanisms) or
window vs ladder rank differently on survival than on mean leakers.

### 5. KILLED — subsystem-protection objective (the unused LEAK_COST table)

`wave()` scores a leaker the tick it crosses `detonate_at` and never computes
an impact point, an aspect angle, or a subsystem map on the victim. WHAT a
leaker hits is not modelled anywhere in the rig, so a LEAK_COST-weighted
objective is unmeasurable without modifying the shared harness — and the
policy actuators (range/on-off on defending PDCs) have no influence over
where a surviving torpedo strikes anyway. The one measurable economic axis,
ammo, cannot reorder anything: policies differ by ≲700 PDC40mm rounds per
engagement while one leaker is 60–75k armour damage plus LEAK_COST-class
component losses; the exchange rate is off by orders of magnitude. Dead twice
over: not measurable, and could not flip a ranking if it were.

### 6. KILLED — main guns as backup PD

`BaseRailgunDefinition.cs:28-30`: `Threats = { Grids }` only. WeaponCore's
`SetTurretTargetTypes` can only toggle categories already in the definition's
threat list (prior finding), so no PB call can make a railgun engage
projectiles. Dead at the definition level. (PDCs: Projectiles/Grids/
Characters/Meteors; the lidar tracks Projectiles but is a sensor.)

### 7. KILLED — decoys against torpedoes

No decoy code path exists in `Projectile.cs` smart navigation — decoys divert
turret AIM (WeaponTracking), not projectile HOMING. A torpedo that has locked
a grid flies PN at that grid. Scattering decoy blocks does nothing to a salvo
already locked on. Dead.

### 8. KILLED — steering which hull eats the leakers

Under the threshold objective the fleet would rather split 6 leakers 2/2/2
than eat 6 on one hull. But target choice belongs to the attacker's guidance;
projectile targets carry no identity a defender could bias; and no actuator
reaches enemy guidance (no phantoms from PB, no decoys per #7). The defence
cannot redistribute hits, only prevent them. Dead unless the FORMATION agent
ever gets manoeuvre — that lever belongs to the attacker.

### 9. KILLED (mostly) — reload phasing

PdcMcrn in the harness never reloads inside a wave at these salvo sizes
(reloading counter exists; `run()` reports it; waves cool between). Heat never
binds (27% peak). There is no magazine timing to exploit on the shipped
hardware. Inert, like heat-cycling — reported so nobody retries it.

### 10. Context probe — threat-model perturbation (staggered launch)

`run(launch_delays=...)` models stagger as extra start distance. One cheap
table: does the incumbent ranking survive a 0/1/2 s staggered salvo, i.e.
does simultaneous-launch tuning overfit? Context only — the doctrine agent
owns attack design; this is defensive robustness. (See results.)

---

## Results (SEEDS 701–724 unless noted; full output in outside_eval_out.txt / outside_dirty_out.txt)

### A. Required tables — Plasma220 (the clean-death default)

t1 = paired t vs burst_ladder_only(14), t2 = vs ladder_deconflict(40,14).
P(surv) = P(leakers ≤ 2 on the targeted hull) — the survival-threshold objective (#4).

1 hull salvo 24:

| policy | leak | sd | fired | P(surv) | t1-leak | t1-fired | t2-leak | t2-fired |
|---|---|---|---|---|---|---|---|---|
| baseline (no PB) | 6.33 | 2.24 | 588 | 0.00 | +9.29 | +26.59 | +8.30 | +23.05 |
| static band | 4.04 | 1.83 | 339 | 0.17 | +6.46 | −28.60 | +5.89 | −20.63 |
| window +500 | 2.21 | 2.00 | 556 | 0.62 | +2.35 | +15.86 | +2.03 | +14.79 |
| burst-only b14 | 1.33 | 1.27 | 456 | **0.88** | +0.00 | +0.00 | −0.16 | +1.68 |
| full ladder | 1.38 | 1.44 | 450 | 0.83 | +0.16 | −1.68 | +0.00 | +0.00 |
| vis burst-only | 1.33 | 1.27 | 456 | 0.88 | +0.00 | +0.00 | −0.16 | +1.68 |
| vis ladder | 1.38 | 1.44 | 450 | 0.83 | +0.16 | −1.68 | +0.00 | +0.00 |

3 hulls salvo 48:

| policy | leak | sd | fired | P(surv) | t1-leak | t1-fired | t2-leak | t2-fired |
|---|---|---|---|---|---|---|---|---|
| baseline (no PB) | 17.25 | 4.09 | 1512 | 0.00 | +12.62 | +28.01 | +13.05 | +31.08 |
| static band | 11.54 | 2.54 | 886 | 0.00 | +7.39 | −29.44 | +8.37 | −31.56 |
| window +500 | 9.08 | 2.78 | 1253 | 0.00 | +5.97 | +7.79 | +5.05 | +9.50 |
| burst-only b14 | 5.92 | 2.24 | 1178 | 0.08 | +0.00 | +0.00 | −0.15 | +3.91 |
| full ladder | 6.00 | 2.47 | 1144 | 0.08 | +0.15 | −3.91 | +0.00 | +0.00 |
| vis burst-only | 5.67 | 2.65 | 1210 | 0.17 | −0.51 | +4.71 | −0.62 | +8.06 |
| vis ladder | 6.04 | 2.10 | 1182 | 0.08 | +0.24 | +0.52 | +0.09 | +4.61 |

**vis_ladder verdict (candidate #2): honest null.** The blind-rung fix does what
it says mechanically — consorts convert blind time into fire (+32 rounds,
t=+4.71) — but the extra fire buys no significant leaker reduction (−0.25,
t=−0.51 for burst-only; tie for the full ladder). Blind-rung dwell is short
(cool+dwell then re-cycle) and torpedo-free anyway for most of the wave. At
1 hull it is bit-identical to the incumbent by construction. Not worth
deploying; do not iterate on it.

**Survival objective (candidate #4): no rank flips.** P(leak≤2) orders policies
exactly as mean leakers at both loads (burst-only 0.88 survival vs ladder 0.83
at 1h s24 — within noise). The tail and the mean move together here because
leaker distributions are unimodal with similar shape across policies. The
threshold framing changes which SCENARIO matters (3h s48 is unsurvivable for
every policy: P≈0.08 — a defence evaluated at that load is already dead and
should be evaluated at lower salvos or more hulls), but not which policy to
pick. Negative result, settled with data nobody had logged.

**Thin-stream robustness** (coordinator request; trickle 8@1s + mass, 12 seeds):
vis variants are the same state machine and inherit the ladder's density
sensitivity — bit-identical at 1 hull, t=−0.55 at 3 hulls. No robustness
advantage. Side finding worth having: the trickle attack is far MORE effective
against `window_nearest` (19.92 leak at 3h s48, 23.08 at 1h s48 — vs ladder
7.92/17.58): the early trickle drags `nearest` down and the window cap blinds
every mount to the massed wave behind it. The offence agents should know the
trickle's best victim is the window, not the ladder.

### B. Dirty-death rescoring (candidate #1) — Belter/Hekp threats, oracle-side

eff-leak = leakers + fragment-damage/leak-damage. med-kr = median kill range.

1 hull s24, Torpedo220mmBelter (leak worth 60 000):

| policy | leak | kills | frag dmg | eff-leak | Δeff | med-kr |
|---|---|---|---|---|---|---|
| baseline | 1.08 | 22.9 | 75 374 | 2.34 | +1.26 | 919 |
| burst-only b14 | 1.08 | 22.9 | 79 684 | 2.41 | +1.33 | 782 |
| full ladder | 1.17 | 22.8 | 79 326 | 2.49 | +1.32 | 790 |

3 hulls s48 Belter: burst-only 3.33 leak → 5.81 eff-leak (+2.48); ordering
across policies unchanged (static band stays worst, t=+18.6 on eff-leak).

1 hull s24, Torpedo220mmHekp: leakers 15.1–17.5 for EVERY policy (hp 5,
1196 m/s, terminal S-weave — see below); fragment tax small in relative terms
(Δeff 0.00–0.13) because there are few kills to tax. 3h s48: Δeff 0.25–0.66,
ordering unchanged.

Findings:

1. **Vs Belter the scoreboard undercounts true delivered damage ~2.2–2.5×.**
   About half of all kills happen inside the 1 100 m fragment envelope
   (kill-range CDFs: 0.46–0.51 below 800 m) and each such kill still delivers
   ~5 000 damage of unkillable fragments on a converged course. The tax is
   +1.3 effective leakers at 1h s24 and +2.5 at 3h s48.
2. **The tax is policy-INSENSITIVE.** Kill-range distributions are nearly
   identical across baseline/window/ladder/vis (the range gate changes which
   MOUNT fires, not where torpedoes die — kills cluster where density ×
   accuracy peaks, and even static band only moves the median from ~790 m to
   ~510–630 m by killing less overall). So there is no fire-control counter to
   the fragment tax: rankings on eff-leak match rankings on leakers everywhere.
   The premise attack finds a real hidden cost but NOT a new policy lever;
   the counters are upstream (interceptors #3, or hardware that kills farther).
3. **The harness's clean-kill assumption is correct for the default threat only
   by a mod bug** — Plasma220's fragment ammo is undefined. If SDX2 ever fixes
   "Fragment220mm", every Plasma kill inside ~1–2 km gains a 9-fragment tax and
   these tables become the default scoring.
4. **Torpedo-type asymmetry dwarfs salvo shaping.** Same hardware, same salvo
   24, 1 hull: Plasma220 leaks 1.33 under the ladder; **Hekp leaks 15.9**
   (hp 5 = 5 PDC40 hits, 1196 m/s in the envelope, terminal S-weave, and its
   warhead survives a shoot-down inside 700 m). Belter leaks 1.08 even with NO
   script. For the offence: switching ammo from Belter/Plasma to Hekp is worth
   ~+14 leakers per 24 — an order of magnitude more than any launch-timing
   shape measured (+1.6 to +2.7). For the defence: Hekp salvos at these loads
   are simply not stoppable by PDC fire control; the answer is interceptors
   (which one-shot the hp-5 Hekp, P(kill)=1.00 launched ≤4 km) or formation.

### C. The interceptor lever (candidate #3) — outside_att_out numbers

Duels with the audited Torpedo2 model, 24 seeds, ATT launched from the
defended hull when the inbound crosses launch range:

| incoming | launch 5 km | 4 km | 3 km | 2 km |
|---|---|---|---|---|
| Plasma220mmTorp | 0.04 | 0.17 | 0.79 | **1.00** |
| Torpedo220mmBelter | **1.00** | 1.00 | 1.00 | 1.00 |
| Torpedo160mmBelter | **1.00** | 1.00 | 1.00 | 1.00 |
| Torpedo220mmHekp | 0.62 | **1.00** | 1.00 | 1.00 |

P(kill) per interceptor. The long-launch failures vs Plasma are intercepts
that happen beyond OffsetMinRange where the target still weaves at ratio 0.7;
launched 2–3 km the intercept occurs in the no-weave zone and is certain. The
broken def is an ADVANTAGE here: with the approach machine collapsed it keeps
the un-staged 15 600 m/s² steering authority (4.3 m turn radius at 260 m/s),
and head-on the TARGET supplies 1040–1300 m/s of closure.

Caveats measured/flagged:
* vs Belter, an intercept at any range ≤1.8 km is still a dirty death (5
  fragments continue) — vs Hekp, intercepts at ≥800 m are CLEAN (warhead
  lifetime 0.5 s ≈ 670 m reach), which makes the ATT the only hard counter to
  the worst torpedo in the set.
* Rate-limited: ReloadTime 720 = 12 s per tube; ~1–2 interceptors per tube per
  approach. This thins a salvo by the tube count; it is a layer, not a defence.
* Economics: 24× TorpedoGuidanceComputer per interceptor, PDC rounds free.
  One guaranteed kill per 24 TGC vs ~14+ PDC rounds per kill that only arrive
  when the deck cooperates.
* Density-robust by construction: no rung state, no saturation dynamics — a
  trickled stream feeds interceptors one target at a time with reloads free
  between, so the trickle-8 attack that costs the ladder +2.67 does not touch
  this layer. (Not simulated fleet-scale; per-duel P(kill) is the evidence.)
* IN-GAME UNKNOWNS, honestly: (1) does a FIXED launcher (Scope="camera")
  auto-acquire projectile targets and fire without player input? (2) does the
  Goliath light tube fit the user's hulls? (3) `SetActiveAmmo` on tubes is
  PB-registered but untested in anger. A 20-minute in-game test settles all
  three and is the single highest-value experiment this survey proposes.

### Verdict

No new PDC fire-control policy survives contact (vis: null; threshold: no
flips) — consistent with DOCTRINE.md's "fire control is close to its ceiling".
The two things that matter are OUTSIDE the PDC loop:
1. **Threat truth**: kills are not clean vs Belter/Hekp (source-verified,
   +130% hidden damage vs Belter), Hekp is ~10× the attack value of any salvo
   shape, and no range policy can dodge the fragment tax.
2. **The idle tubes**: a PB-actuatable interceptor layer with per-round
   P(kill)≈1 inside 4 km, the only counter found for Hekp, density-robust,
   awaiting one in-game verification.
