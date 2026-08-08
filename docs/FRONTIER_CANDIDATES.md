# Frontier survey — what the fire-control framing missed

Role: contrarian pass. Everything below either questions a premise of the
per-mount-policy programme or exploits a lever outside it. Implementations in
`frontier.py`; drivers `frontier_explore*.py`, finals `frontier_final.py`
(SEEDS 701-714, reference rows included). All C# claims verified against the
CoreSystems source at
`workshop/content/244850/3154371364/Data/Scripts/CoreSystems/Api/ApiBackend.cs`
and the SDX2 source at `3580645761/Data/Scripts/Mod/CoreParts`.

## A. The "unexplored actuators" — all five are dead ends

1. **SetAiFocus / ReleaseAiFocus / GetAiFocus** — PB-registered
   (`PbApiMethods`, ApiBackend.cs:188-190) but `PbSetAiFocus(block, long
   entityId, priority)` resolves the target by **entity id**. Torpedoes are
   `Projectile` objects, not entities; projectile targets carry the -1
   sentinel. There is nothing to focus on. Useful only against grids.
2. **SetWeaponTarget** — same shape (`long` entity id), same conclusion.
3. **SetTurretTargetTypes / GetTurretTargetTypes** — PB-registered, but the
   implementation (ApiBackend.cs:1151-1165) only toggles members of the
   weapon definition's threat-**category** list. Every threat in this
   scenario is one category (projectiles); there is nothing to discriminate.
   Inert here.
4. **FireWeaponOnce** — PB-registered (`PbFireWeaponBurst`). It is a
   fire-pacing lever, i.e. structured withholding, and withholding is the
   study's strongest confirmed negative. No non-withholding use found.
5. **SetActiveAmmo** — PB-registered, but every SDX2 PDC declares exactly one
   selectable primary ammo (BasePDCDefinition.cs:184 = PDC40mm; McrnAdv =
   PDC50mmHeavy only; OpaAdv's extra `Ammos` entries are spawn stages
   `Flak50mmStage2`/`FlakFragment50mm`, not magazine-backed alternates).
   Nothing to switch to. The interaction-radius lever exists only at
   ship-fitting time, not at runtime.
6. **Phantoms** (`SpawnPhantom` etc., CoreSystemsApiPhantoms.cs) — present
   only in the mod-API dict (`ApiMethods`, :153-161), **absent from
   `PbApiMethods`**. Same trap as `GetAllSmartProjectiles`. Discarded.

Conclusion: the PB actuator surface really is just `SetBlockTrackingRange` +
`ToggleWeaponFire`. The room to move is **before the fight**: ship fitting
and fleet geometry.

## B. Premises examined

* **"Leakers" as objective** — the harness scores a leaker at `detonate_at`
  and never models the impact point, so LEAK_COST-weighted objectives are not
  measurable in this rig; and the winning configurations below drive leakers
  to ~0, which makes the leaker-cost distinction moot. Kept leakers + rounds.
* **Hull manoeuvre to stretch the window** — `wave()` never integrates ship
  motion, so untestable without touching shared files. Also dominated:
  drives move a hull hundreds of metres over the 8.6 s flight; formation
  placement moves it kilometres for free. Pursued formation instead.
* **Steering the deck walk** — `AcquireRandom` seeds from `UniquePartId`
  (Misc.cs:76-85), unreadable from a PB, and the deck order depends on the
  projectile-cache order, invisible to a PB. Range-gating (the ladder) is the
  only real handle on acquisition. Rejected.

## C. The finding nobody was looking for: **placement**

Per-mount probe (`frontier_explore` diagnostics): on the stock 8-ring,
mounts at ring angles **180 and 225 never fire** at the threat axis (own-hull
occlusion) and 135 fires at half duty. The reference fleet fights with ~5.8
of its 8 mounts, and the whole ~40-policy study inherited that silently.
Worse, `build_ship` assigns ring angles by mix-dict order, so the first
mixed-battery test I ran was dominated by WHERE the kinds landed, not what
they were — mixed-loadout comparisons are meaningless without placement
control (`build_placed` in frontier.py mirrors the shipyard cell math
bit-exactly; fidelity-checked against `run()`).

* **RING_BROADSIDE** — relocate the two dead mounts to bearing-side cells.
  Same 8 points, same 8 x PdcMcrn. This is pure ship design; no PB involved.
* In-game caveat: threat-axis specific. A ring is omnidirectional; a
  broadside battery needs the hull oriented at the launch bearing (which
  `RegisterProjectileAdded` supplies, and the fleet AI can hold).

## D. Mixed batteries under the 8-point budget (placement-controlled)

* **2 x PdcMcrnAdv + 4 x Mcrn ("sniper")** — HHM 5 one-shots a Health-4
  torpedo with a 160 m interaction radius; immune to scatter-wounding. But
  80 rpm is ~2.6 rounds per terminal window: measured ~1.6 kills per sniper
  per wave, and each sniper costs two 30 rps stream mounts. **Loses** (6.75
  vs 4.00 ladder-vs-ladder at 4 seeds). Throughput really is the binding
  constraint — now confirmed for hardware, not just policy.
* **2 x PdcOpaAdv flak + 4 x Mcrn** — the only true annulus (hardware
  MinTargetDistance 1000, reach 4000) and a 50 m radius, but 30 rpm with
  `delay_until_fire=12` delivers ~1 round per acquisition. **Loses badly**
  (9.75). The outer-shell idea dies on rate-of-fire.
* **2 x PdcUnnAdv + 4 x Mcrn** — 2-barrel 40 rps. Ties/marginally better
  (2.50 +/- 2.38), not significant.
* **k x PdcPgenAdv + Mcrn ("pgen")** — PDC50mmLight: same 3.417 m radius but
  muzzle 3600, dev 0.075, 20-round bursts at 50 rps (30.8 rps effective), no
  rof degrade. **Wins**: pgen2b/pgen3 hit 0.0-1.5 leakers at salvo 40
  (4-seed explore) vs 4.00 for the stock ladder. Faster rounds = shorter
  time-of-flight = fewer dead rounds and less weave displacement per flight.
* Policy interaction: pgen-heavy rings prefer `window_nearest`; Mcrn-heavy
  rings prefer the full ladder. (Burst-fire guns concentrate naturally; the
  ladder's re-aim churn wastes their bursts.)

## E. Formation geometry (the big one)

The salvo flies one axis at 260 m/s for ~2.5 s (boost), then ~300 m/s^2 up to
1040 m/s. The stock lateral line gives every hull the same terminal ~2.9 s.
**Axial picket line** (lead at 0, hulls at +1200/+2400 toward the threat,
lateral +/-250 m to keep pass-by slew rates feasible):

* a picket's 3 km envelope intersects the torpedo track for most of the
  flight — engagement time roughly triples;
* pickets engage boost-phase torpedoes (260 m/s, weave displacement small
  over a round's flight) — near-free kills;
* as torpedoes pass a picket its "back-side" mounts get geometry, so the
  placement waste of C partially self-heals.

Measured: **0 leakers at salvo 40 under every policy including no-PB
baseline** (4-seed explore; finals on 14 seeds). At salvo 96 stock-ladder
leaks ~39 of 96; pickets leak ~1. The naive `window_nearest` mis-windows
pickets (nearest is lead-relative), fixed by `formation_window[_ladder]`
which windows each hull on `|nearest - ship_x|` — own-formation constants
plus the same dead-reckoning that justifies ctx['nearest'].

Caveats, honestly: direction-specific (needs fleet orientation on the launch
axis); pickets stand ~2.4 km closer to the launcher; torpedo-vs-picket hull
collision is not modelled (they home on the lead and pass within ~250 m of a
picket in the sim). **Adversarial hole, measured**: the defence does not
choose which hull the salvo homes on. Targeted = rear or middle hull: 0.00
leakers. Targeted = FRONT picket: 9.50 (4 seeds) — worse than stock 4.00,
because hulls behind the impact point cover almost none of the track.
Shallower pickets (0/800/1600, 0/1000/2000) do not fix it (8.0-8.5).
Attacker-uniform expectation ~3.2 still beats 4.00, and the defence controls
which HULL stands front — doctrine is to lead with the cheapest/tankiest hull
(leak-cost: armour is free ore), which also means a nearest-first attacker
wastes its salvo on the screen. But against an attacker who reliably targets
the up-threat hull, the picket line loses its advantage.

## F. Role policy for mixed hardware ("sniper calls, herd yields")

Implemented `mix_roles` (frontier.py): snipers keep full reach, de-conflict
among themselves, optional shoot-and-scoot re-aim pulse after each round;
40mm herd runs window+ladder and yields on ray-convergence with a sniper.
Rationale: the incumbent ladder's tie-break demotes the LESS-committed mount,
which on mixed hardware makes the guaranteed-kill sniper yield to a 40mm
spray. **Negative result**: mix_roles lost to the plain ladder even on the
sniper ring (10.75 vs 6.75). The yield clamp suppresses the herd more than
the dedup saves, and sniper hardware loses anyway (D). Not tuned further.

## Final numbers (SEEDS 701-714, full output in frontier_final_out.txt)

3 Corvettes net-engaging, salvo 40. t-stats paired against
`full ladder tol40 b14 (stock)` on leakers / rounds fired:

| configuration + policy | leak | sd | fired | t-leak | t-fired |
|---|---|---|---|---|---|
| baseline (no PB, stock) | 11.00 | 2.86 | 1450 | +10.99 | +36.05 |
| static band .75/.5/.25 (stock) | 6.36 | 1.34 | 828 | +10.48 | -3.39 |
| window nearest+500 (stock) | 5.29 | 2.97 | 1219 | +2.74 | +27.33 |
| full ladder tol40 b14 (stock) | 2.64 | 1.50 | 875 | +0.00 | +0.00 |
| broadside 8xM / full ladder | 1.71 | 1.38 | 1020 | -2.88 | +6.43 |
| broadside 8xM / window+500 | 2.57 | 1.83 | 1490 | -0.10 | +35.96 |
| pgen2b 2P+4M / window+500 | 0.43 | 0.65 | 1516 | -4.70 | +31.99 |
| pgen3 3P+2M / window+500 | 0.93 | 1.27 | 1319 | -3.12 | +28.55 |
| picket 0/1200/2400 / baseline (no PB) | 0.00 | 0.00 | 1581 | -6.60 | +30.47 |
| picket 0/1200/2400 / window+500 (naive) | 0.00 | 0.00 | 1559 | -6.60 | +25.20 |
| picket 0/1200/2400 / full ladder | 0.00 | 0.00 | 918 | -6.60 | +2.00 |
| picket 0/1200/2400 / form window+ladder | 0.00 | 0.00 | 867 | -6.60 | -0.57 |
| broadside+picket / full ladder | 0.00 | 0.00 | 982 | -6.60 | +4.51 |

Notes: reference rows reproduce the brief's table exactly. The picket line
zeroes the salvo on all 14 seeds under EVERY policy — including no PB — and
`formation_window+ladder` gets it at the ladder's ammunition cost (867 vs
875 rounds). pgen swaps prefer the window and pay for it in rounds fired
(+32 t on ammo); with the ladder they fire ~890 (explore) at ~1.5 leakers.

Saturation — 3 Corvettes, salvo 64 (t vs stock full ladder, same seeds):

| configuration + policy | leak | sd | fired | t-leak | t-fired |
|---|---|---|---|---|---|
| static band .75/.5/.25 (stock) | 23.50 | 3.32 | 913 | +7.16 | -2.40 |
| window nearest+500 (stock) | 23.00 | 4.74 | 1292 | +3.99 | +14.45 |
| full ladder tol40 b14 (stock) | 16.93 | 2.56 | 953 | +0.00 | +0.00 |
| broadside 8xM / full ladder | 12.21 | 2.29 | 1110 | -4.63 | +6.94 |
| pgen3 3P+2M / window+500 | 9.93 | 3.10 | 1374 | -7.66 | +25.21 |
| picket 0/1200/2400 / full ladder | 0.00 | 0.00 | 1243 | -24.78 | +24.18 |
| broadside+picket / full ladder | 0.00 | 0.00 | 1339 | -24.78 | +20.40 |
| pgen2b+picket / window+500 | 0.00 | 0.00 | 1937 | -24.78 | +50.52 |

At 1.6x the salvo the whole policy ladder has collapsed (17-23 leakers);
pickets still leak zero on every seed. Explore-grade salvo 96: stock ladder
38.75, pickets 1.25-2.00.

Single Corvette, salvo 24 (formation not applicable):

| configuration + policy | leak | sd | fired | t-leak | t-fired |
|---|---|---|---|---|---|
| baseline (no PB, stock) | 6.43 | 2.14 | 581 | +6.56 | +14.54 |
| static band .75/.5/.25 (stock) | 4.71 | 1.94 | 332 | +6.90 | -7.50 |
| window nearest+500 (stock) | 2.21 | 1.76 | 551 | +1.21 | +14.17 |
| full ladder tol40 b14 (stock) | 1.57 | 1.02 | 405 | +0.00 | +0.00 |
| broadside 8xM / full ladder | 0.79 | 0.97 | 495 | -1.92 | +11.61 |
| pgen2b 2P+4M / window+500 | 0.57 | 0.76 | 633 | -2.65 | +21.75 |
| pgen3 3P+2M / window+500 | 0.71 | 0.91 | 544 | -2.20 | +13.83 |

The refits halve the best policy's leakers on a lone hull too.

## Verdict

The fire-control programme was optimising the third-largest lever. Measured
order at equal budget: **formation geometry >> mount placement ~ Pgen swap >
any PB policy delta since window_nearest**. The PB policy result stands
(ladder still helps every configuration), but the next 10x was never in the
PB.
