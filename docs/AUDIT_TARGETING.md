# AUDIT — WeaponCore target acquisition

Sources of truth
- WC 3.0: `C:\Program Files (x86)\Steam\steamapps\workshop\content\244850\3154371364\Data\Scripts\CoreSystems\`
- SDX2 defs: `...\244850\3580645761\Data\Scripts\Mod\CoreParts\`

Deliverables
- `wc_acquire.py` — line-faithful port, every function annotated with `file:line`.
- `targeting.py` — now delegates to it.
- Scratch A/B (does not touch `fleet_efficiency.py`): `../ab_stats.py`, `../ab_targeting.py`.

---

## 1. Headline: how the real thing actually picks

The mental model in the old `targeting.py` docstring — *"shuffle the WHOLE cache and
take the first valid entry"* — is **wrong**. `AiTargeting.cs:607-641` with the SDX2
PDC definition does this:

```
numOfTargets   = collection.Count                            // :602
numToRandomize = targetClosest ? TopTargets : numOfTargets   // :609  (=numOfTargets)
checkSize      = CycleTargets                                // :618  (=4)
chunk          = checkSize * w.AcquireAttempts % numOfTargets// :620
if (chunk + checkSize >= numOfTargets)                       // :622
    checkSize  = numOfTargets - chunk
deck = GetDeck(ref s.TargetDeck, chunk, checkSize, numToRandomize, AcquireRandom) // :625
for (x = 0; x < checkSize; x++) { lp = collection[deck[x]]; ... }                 // :628
```

`numToRandomize` is `GetDeck`'s **cardsToShuffle**, not **cardsToSort**. `cardsToSort`
is `checkSize` = 4. So `GetDeck` only ever builds **four cards**. It is a
**cycling four-wide window** over the projectile cache whose start advances by four
on every acquisition attempt, randomised only *within* the window:

```
attempt 0: chunk=0  deck=[0, 2, 3, 1]
attempt 1: chunk=4  deck=[6, 4, 7, 5]
attempt 2: chunk=8  deck=[9, 11, 10, 8]
attempt 3: chunk=12 deck=[13, 15, 14, 12]
attempt 4: chunk=0  deck=[0, 2, 1, 3]     <- wraps
```

Two quirks in that arithmetic are load-bearing and are reproduced verbatim:

**(a) `CycleTargets > numOfTargets` SUBTRACTS, it does not clamp** (`AiTargeting.cs:615-616`,
`checkSize = w.System.CycleTargets - numOfTargets`). Measured `checkSize` by cache size
for `CycleTargets = 4`:

| cache size N | 0 | 1 | 2 | **3** | 4 | 5 | 6 | 7 | 8 | 16 |
|---|---|---|---|---|---|---|---|---|---|---|
| candidates examined | 0 | 1 | 2 | **1** | 4 | 1-4 | 2 or 4 | 1-4 | 4 | 4 |

With exactly three torpedoes in the cache a PDC examines **one** of them per attempt.
That is a WeaponCore bug, not my port; it is in the shipped code.

**(b) `Range(1, n)` can return 0 and is heavily biased** (`Support/Utils.cs:207-215`).
`(int)NextUInt64()` keeps the low 32 bits *signed*, so `rndInt % (aMax-aMin)` is
negative half the time; the guard then negates, but `0 * -1 == 0` is still below
`aMin=1` and is returned anyway. Measured `Range(1,5)` over 20 000 draws:
`{0: 12.7%, 1: 37.7%, 2: 24.8%, 3: 12.2%, 4: 12.5%}`. `GetDeck`'s `startChunk`
(`AiSupport.cs:233`) depends on this — a returned 0 silently relocates the shuffled
sub-window to the front of the deck. `Range(0, i+1)` (the Fisher-Yates index,
`AiSupport.cs:242`) *is* uniform, because negatives fold cleanly.

RNG correctness: the state update is canonical xorshift128+ (Vigna); my port matches an
independently written reference for the constructor state and the output sequence.

On the buffer-reuse semantics of `GetDeck`: I modelled `Session.TargetDeck` /
`Session.BlockDeck` as a persistent `DeckBuffer` that only reallocates (zero-filled,
discarding old contents) when `deck.Length < cardsToSort`. **Adversarial note on my own
port:** buffer reuse turns out to be *observationally inert*. Every `deck[i] = deck[j]`
has `j <= i`, and `deck[j]` for `j < i` was written earlier in the same pass, so no
stale value from a previous call can ever survive into `deck[0..cardsToSort)`. The
reuse is a GC optimisation only. It is still modelled, because the array being
session-global (not per-weapon) *is* observable — it means the deck must be consumed
before any other weapon calls `GetDeck`, and it means `GetDeck` is not thread-safe.

---

## 2. SDX2 settings — read, not assumed

`PDC/BasePDCDefinition.cs:27-48`:

| field | base PDC | per-weapon overrides |
|---|---|---|
| `ClosestFirst` | `false` (:37) | none |
| `IgnoreDumbProjectiles` | `false` (:38) | none |
| `LockedSmartOnly` | `false` (:39) | none |
| `MaxTargetDistance` | `3000` (:42) | `pdcOpaAdv.cs:29` → 4000 (one variant; `:84` → 3000) |
| `TopTargets` | `32` (:44) | **→ 12** on every shipped PDC except pdcPgenAdv |
| `CycleTargets` | `4` (:45) | `pdcPgenAdv.cs:29` → 0 |
| `TopBlocks` | `16` (:46) | **→ 12** (pdcPgenAdv → 4) |
| `CycleBlocks` | `4` (:47) | `pdcPgenAdv.cs:30` → 0 |
| `SubSystems` | `Power, Utility, Offense, Thrust, Production, Any` (:33-36) | none |
| `Threats` | `Projectiles, Grids, Characters, Meteors` (:29-32) | none |

Overrides at `pdcMcrn.cs:47-48`, `pdcUnn.cs:47-48`, `pdcOpa.cs:49-50`,
`pdcImprovised.cs:27-28,67-68`, `pdcMcrnAdv.cs:61-62`, `pdcUnnAdv.cs:60-61`,
`pdcOpaAdv.cs:31-32`, `pdcPgenAdv.cs:27-30`.

**`TopTargets` is 12, not the base 32.** It is nearly irrelevant here though: with
`ClosestFirst=false` it is not used at all on the projectile path (`AiTargeting.cs:609`
substitutes `numOfTargets`). It only bites on the block path, where it *is* the
`cardsToShuffle` (`AiTargeting.cs:1345`).

**pdcPgenAdv is a genuine outlier** — `CycleTargets = CycleBlocks = 0` means it scans
the *entire* cache on every acquisition attempt instead of a 4-wide window. If any
result compares PDC types, that difference is real and is now modelled
(`wc_acquire.sdx2_pdc`).

`Railguns/BaseRailgunDefinition.cs:26-45`: `TopTargets 12`, `CycleTargets 0`,
`TopBlocks 24`, `CycleBlocks 0`, `ClosestFirst false`, `IgnoreDumbProjectiles false`,
`LockedSmartOnly false`, `MaxTargetDistance 10000`, `Threats = { Grids }` only.
`railgunUnnLightFixed.cs:25-26` sets `TopTargets = TopBlocks = 0`, which makes
`GetDeck`'s `shuffle` flag false — that weapon does **no** randomisation, it walks the
internal list in order.

Because `CycleTargets = 0`, railguns take the `checkSize = numOfTargets` branch and
build a deck as long as the whole cache — but only a `TopTargets`-wide sub-window of it
is shuffled. Verified against a 30-entry cache: cards 0-11 permuted, cards 12-29 left
in list order.

The sim's `weapons.PDC_STATS` ranges (3000 / 4000) already agree with
`MaxTargetDistance`. No discrepancy.

---

## 3. Your claims

### CLAIM 1 — "SDX2 PDCs have ClosestFirst=false, so each mount shuffles the whole projectile cache and picks randomly"
**PARTLY CONFIRMED, MECHANISM REFUTED.**
`ClosestFirst = false` is right (`BasePDCDefinition.cs:37`, never overridden). The
runtime read at `AiTargeting.cs:579-581` can be overridden at the terminal, but only if
`AllowSwitchTargetPriority` is set; that field defaults false
(`CoreDefinitions.cs:328`, no `DefaultValue`) and `grep` over the whole SDX2 mod returns
zero hits, so the definition value is what is used. But it does **not**
shuffle the whole cache. `cardsToSort = checkSize = CycleTargets = 4`
(`AiTargeting.cs:618`, `:625`). It shuffles a **four-card window** whose position
`chunk = 4 * AcquireAttempts % numOfTargets` (`:620`) is **deterministic, not random**.
See §1.

### CLAIM 2 — "`CycleTargets = 4` means a mount only examines four candidates per acquisition attempt"
**REFUTED as stated** (true only when `numOfTargets >= 4`).
`AiTargeting.cs:615-616` subtracts rather than clamps when `CycleTargets > numOfTargets`,
and `:622-623` shrinks the last window. With 3 candidates a mount examines **1**; with
1 candidate it examines 1; with 5 it examines 1-4 depending on the attempt counter.
Table in §1.

### CLAIM 3 — "AllowFireDistribution defaults false and SDX2 never sets it, so FireDistributionSystem never runs"
**CONFIRMED.**
- `Definitions/CoreDefinitions.cs:329` `[ProtoMember(25)] internal bool AllowFireDistribution;`
  — no `DefaultValue`, so C# `false`. Copied verbatim to `CoreSystems.cs:307`.
- `grep -rn AllowFireDistribution` over the entire SDX2 mod: **zero hits**.
- `Support/FireDistribution/FireDistributionSupport.cs:101` gates registration on
  `system.AllowFireDistribution && mOverrides.EnableFireDistribution`.
- The terminal toggle that would set `EnableFireDistribution` is itself gated on
  `AllowFireDistribution` (`TerminalHelpers.cs:558-563`), so a player cannot turn it on
  either.
- **Sharp edge worth knowing:** `AiTargeting.cs:571` checks only
  `mOverrides.EnableFireDistribution`, *not* `AllowFireDistribution`. If anything ever
  sets that override through the API path it would create an accessor regardless of the
  definition. `EnableFireDistribution` also defaults false (`ProtoWeapon.cs:626`, no
  `DefaultValue`), so the conclusion still holds — but the guard at :571 is weaker than
  the one at FireDistributionSupport:101.

### CLAIM 4 — "SupportingPD defaults true, so PDCs engage projectiles not locked onto their own grid"
**CONFIRMED.**
- `Definitions/SerializedConfigs/Weapon/ProtoWeapon.cs:623`
  `[ProtoMember(35), DefaultValue(true)] public bool SupportingPD = true;`
- `AiTargeting.cs:545` `var collection = ai.GetProCache(w, mOverrides.SupportingPD);`
- `AiSupport.cs:255-263`: `supportingPd ? ProjectileCache : ProjectileLockedCache`.
- `AiSupport.cs:272-279`: `ProjectileCache` = all of `LiveProjectile.Keys`;
  `ProjectileLockedCache` = only entries whose value is `true`, and
  `ProjectileGen.cs:338` sets that value to `condition1 || condition2 || condition4 ||
  condition6` — the "aimed at this grid" conditions. So `SupportingPD = true` genuinely
  widens the cache to projectiles targeting neighbours.
- Only counter-lever is `DisableSupportingPD` in the weapon definition
  (`ProtoWeapon.cs:44-45` forces the override false). SDX2 sets it only on the torpedo
  launcher (`Torpedolaunchers/BaseTorpedoLauncherDefinition.cs:67`) and there it is
  `false`. PDCs never set it.

### CLAIM 5 — "FireDistributionManager is per-Ai/per-construct, so separate ships never coordinate"
**CONCLUSION CONFIRMED, FRAMING IMPRECISE.**
`AiFields.cs:214-235`: `_fireDistributionManager` is an instance field on `Ai`, created
lazily as `new FireDistributionManager(this)` and only when `IsGrid && GridEntity != null`.
Reached via `w.Comp.MasterAi` (`AiTargeting.cs:574`).
It is **per-`Ai`**, and `Ai` is *not* the same thing as `Construct` — a Construct
aggregates several `Ai`s under `Construct.RootAi` (see `AiSupport.cs:284`
`Construct.RootAi.Construct.GetExportedCollection`). So "per-Ai/per-construct" conflates
two different scopes. `MasterAi` is also not always the weapon's own `Ai`:
`WeaponComp.cs:1338-1346` redirects it to the *controlling* block's `Ai` when a control
component exists. Two separate ships never share one either way, so the operative
conclusion holds. It is moot regardless — per CLAIM 3 the manager is never constructed.

### CLAIM 6 — "a mount holds its target until it dies or becomes invalid, it does not re-roll every tick"
**CONFIRMED.**
`SessionUpdate.cs:755`: `weaponReady = ... && (!w.Target.HasTarget || rootConstruct.HadFocus && constructResetTick)`
— a weapon that has a target is not queued into `AcquireTargets` at all. `:757` gates
`seek` on `weaponReady`. `CheckAcquire` (`:947-951`) removes it from the queue the
moment `w.Target.HasTarget`. Invalidation is the *other* path:
`SessionUpdate.cs:882-883` runs `Weapon.TrackingTarget` every tick and calls
`w.Target.Reset(Tick, States.LostTracking)` when it fails, which re-opens the queue.

**Additional finding you did not claim, and it matters:** re-acquisition after a loss is
also *rate limited*. `SessionUpdate.cs:748` `myTimeSlot` fires once per
`AwakeBuckets = 60` ticks (`SessionFields.cs:51`), and the projectile fast path
`w.ProjectilesNear` (`SessionUpdate.cs:736`) requires `w.Target.TargetChanged || QCount
== w.ShortLoadId`, where `QCount` cycles 0..14 (`SessionSupport.cs:70`) and
`ShortLoadId` is assigned 0..14 (`SessionSupport.cs:414-419`) — one window per 15 ticks
(0.25 s). The `TargetChanged` term means the tick right after a kill is free, so the
0.25 s penalty only lands on *failed* attempts. Modelled in
`wc_acquire.weapon_may_seek` and switchable via `targeting.MODEL_ACQUIRE_CADENCE`.

---

## 4. Does any of it change the numbers?

`fleet_efficiency` monkeypatched (never edited) by `../ab_stats.py`.
`PYTHONHASHSEED=0`, torpedo2.py sha1 `b63d69d71826`, `Torpedo2._ids` reset per run
(see §5.2 — without that reset the four arms do not see the same torpedo RNG streams
and the comparison is confounded; my first pass had that bug and I redid it).

`run(1, 8, salvo=16, waves=1, seed=11)`:

| variant | leakers | kills | rounds | capacity | peak heat |
|---|---|---|---|---|---|
| old approx (uniform random) | 3 | 13 | 307.0 | 14.51% | 10.41% |
| old approx, ClosestFirst=True | 9 | 7 | 194.0 | 8.83% | 9.10% |
| **EXACT port + WC cadence** | **1** | **15** | **256.0** | **12.38%** | **10.65%** |
| EXACT port, attempt every tick | 4 | 12 | 297.0 | 13.88% | 9.36% |

A single seed spans 1-4 leakers between arms that are statistically identical, so
**do not read anything off that table**. 24 seeds, same scenario:

| variant | leakers | sd | kills | rounds | cap% |
|---|---|---|---|---|---|
| old approx (uniform random) | 3.38 | 1.47 | 12.62 | 310.1 | 14.59 |
| old approx, ClosestFirst=True | 7.42 | 1.98 | 8.58 | 216.6 | 9.62 |
| **EXACT port + WC cadence** | **3.08** | **1.47** | **12.92** | **289.1** | **13.64** |
| EXACT port, attempt every tick | 3.71 | 1.23 | 12.29 | 293.6 | 13.87 |

Paired over the same 24 seeds:
- `old_uniform - exact` = **+0.29 leakers, t = +0.66** → indistinguishable.
- `closest_first - exact` = **+4.33 leakers, t = +8.69** → enormous.

(The pre-correction run, 32 seeds, gave +0.09/t=0.29 and +3.94/t=11.05 — same verdict.)

Salvo sweep (8 seeds, mean leakers):

| variant | s8 | s16 | s24 | s32 |
|---|---|---|---|---|
| old approx (uniform) | 0.25 | 4.12 | 9.88 | 15.50 |
| old approx ClosestFirst | 0.38 | 7.12 | 15.50 | 25.12 |
| EXACT port + WC cadence | 0.12 | 3.50 | 8.88 | 16.38 |
| EXACT port every tick | 0.50 | 3.62 | 8.75 | 16.38 |

**Verdict on the premise of this audit.** Your instinct that nearest-target selection
was the bug is *correct and large* — forcing ClosestFirst adds **+4.3 leakers, t = 8.7**,
roughly doubling them. But the replacement you reached for by guesswork — a uniform
random draw from the valid pool — reproduces the exact WeaponCore deck to **within
noise** (+0.29, t = 0.66). The headline "10 leakers → 4" therefore **survives** the
exact port; it was not an artefact of the approximation. The right conclusion is that
you were lucky, not that you were rigorous: the approximation had the wrong mechanism
(§1) and happened to land on the right distribution.

Why the deck ≈ uniform here: the cache has no distance ordering, mounts drift apart in
`AcquireAttempts` (they fail at different rates), the window is shuffled internally,
and — the dominant term — **~72-76% of all mount-ticks find nothing at all**, because
bearing and own-hull occlusion reject far more candidates than the deck ever offers.
Concentration probe, 8 mounts, salvo 16, seed 11:

| variant | idle | duplicate assignments/tick (of 8) |
|---|---|---|
| old approx (uniform) | 71.6% | 0.96 |
| old approx ClosestFirst | 70.1% | 1.65 |
| EXACT port + WC cadence | 75.9% | 0.43 |
| EXACT port every tick | 71.8% | 1.10 |

The exact port with the WC cadence *spreads fire better* than the uniform draw
(0.43 vs 0.96 duplicates/tick): the cycling window is mildly anti-correlated across
mounts, and the slot gate desynchronises them further. ClosestFirst is the outlier at
1.65, which is the whole mechanism of the original bug — mounts pile onto the same
nearest torpedo. Note that removing the cadence raises duplicates to 1.10, *above* the
uniform draw, which says the anti-correlation comes mostly from the slot gate rather
than from the deck.

### One thing that did change, and is worth keeping
The old `select` drew from `m.rnd`, seeded in `PdcMount.reset()` (`weapons.py:103`) as
`random.Random(hash((self.kind, self.cell)) & 0xFFFFFFFF)`. **`hash()` of a tuple
containing a `str` is salted per process**, so every `fleet_efficiency` number produced
by the old code was **irreproducible across runs** — I measured the same headline case
at 4 and then 7 leakers in two processes with no code change. The exact port is seeded
from `UniquePartId` through the xorshift, exactly as
`Definitions/SerializedConfigs/Misc.cs:76-85` does (including the single
`AcquireRandom.NextBoolean()` burn-in at `:85`), and is now **bit-deterministic**.
`weapons.py` is not my file, so I did not touch that seeding — but every result in the
repo that predates this change carries an unrecorded per-process seed.

---

## 5. Problems found outside my domain (reported, not touched)

1. **`weapons.py:103`** — `random.Random(hash((self.kind, self.cell)) & 0xFFFFFFFF)`.
   Per-process hash salt; any consumer of `m.rnd` is irreproducible. Should be
   `zlib.crc32(repr((kind, cell)).encode())` or similar. Now only affects the shot-roll
   paths, not selection.
2. **`torpedo2.Torpedo2._ids` is a process-global counter** (`torpedo2.py:119-124`) and
   each torpedo seeds its RNG from `seed * 7919 + self.id` (`:134`). Two back-to-back
   `fleet_efficiency.run()` calls with the *same* `seed` therefore give different
   answers — measured 1, 2, 3, 3 leakers on four identical repeats. Any A/B that runs
   variants sequentially in one process is confounded unless `_ids` is reset. **This
   invalidates any sequential comparison anyone in this codebase has run so far**, mine
   included until I found it. Fix: seed from `(seed, index_within_salvo)`, not from a
   global counter.
3. **`torpedo2.py` was broken mid-audit** — `PROFILES[...]['stages']` was changed to
   full Approach dicts while `Torpedo2.__init__:56` still did
   `sorted(st, key=lambda s: s[0])`, raising `KeyError: 0` for every scenario. Repaired
   by its owner since. Its sha1 also changed three times during this audit
   (`3f0a79f8436a` → `b63d69d71826` → ...), so absolute leaker counts in this document
   are only comparable *within* the tables above, not against earlier sessions.
4. **`fleet_efficiency.wave` calls `select` once per mount per tick** and treats a
   returned target as immediately actionable. WeaponCore does not: acquisition is queued
   and slot-throttled (`SessionUpdate.cs:746-757`). I model this inside `targeting.py`
   behind `MODEL_ACQUIRE_CADENCE`, but it properly belongs in the engagement loop.
5. **`PdcMount.RETARGET_S = 0.35`** (`weapons.py:97`) is a hand-tuned stand-in for
   "acquisition runs on a cadence". That is now double-counted against
   `MODEL_ACQUIRE_CADENCE`. Whoever owns `weapons.py` should decide which one survives;
   the WC-sourced one is the 1-in-15/1-in-60 slot gate, not a fixed 0.35 s.

## 6. Not ported (out of scope, flagged)

- `AiTargeting.cs:1359-1610` raycast/LOS body of `FindRandomBlock` — reduced to an
  `accept(block) -> (ok, checked, sighted)` callback. The deck, the `lastBlocks` budget
  and the loop bounds *are* ported.
- `GetClosestHitableBlockOfType` (`:1612+`) is ported as a nearest-with-`accept` scan.
  Its five-way running minimum and `Top5` carry-forward are structurally reproduced;
  the tie-breaking between `newEntity0..3` is not, because nothing downstream reads it.
  Note it has **no `CycleBlocks` budget** — turning `ClosestFirst` on removes the
  per-attempt work cap on the block path entirely.
- `AiTargeting.cs:2087` drone deck and `:181` / `:434` / `:957` decks share the same
  `GetDeck` and `cycle_window`, so they are covered by the port but have no caller here.
