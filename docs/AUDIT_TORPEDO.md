# AUDIT — projectile flight, torpedo guidance, staging

Domain: `torpedo2.py`, `../torpedo_profiles.json`. Nothing else was modified.

Sources of truth, all line numbers verified against the installed files:

- `…/244850/3154371364/Data/Scripts/CoreSystems/Projectiles/Projectile.cs` (187 689 bytes)
- `…/CoreSystems/Projectiles/Projectiles.cs`
- `…/CoreSystems/Definitions/SerializedConfigs/AmmoConstants.cs` (2 444 lines)
- `…/CoreSystems/Definitions/CoreDefinitions.cs`
- `…/CoreSystems/Session/SessionDamageMgr.cs`
- `…/244850/3580645761/Data/Scripts/Mod/CoreParts/TorpedoAmmo/*.cs`, parsed into `../coreparts.json`

**Line-number correction up front.** Two of the pointers in the brief are wrong for this
build of the mod. Smart navigation is at `Projectile.cs:522-880`, not ~2479-2630
(2479-2630 is drone/mine orbit code). Projectile-on-projectile damage is
`SessionDamageMgr.cs:1091-1162`, not ~336-355. `ProcessApproach` at `:915` and the speed
cap at `:846/:855` were correct.

---

## Verdicts on the five stated claims

### 1. "terminal speed is 1040 m/s (Plasma220/220Belter), 1300 (160Belter), 962 (190Improvised)" — **CONFIRMED**, with two caveats

`speedCap = speedCapMulti * MaxSpeed` (`Projectile.cs:846`), clamped at `:855`.
`speedCapMulti` comes from `approach.SpeedCapMulti` (`:1274`).

| torpedo | cruise `SpeedCapMulti` | cap at a stationary launcher |
|---|---|---|
| Plasma220mmTorp | 4 | **1040** ✔ |
| Torpedo220mmBelter | 4 | **1040** ✔ |
| Torpedo160mmBelter | 5 | **1300** ✔ |
| Torpedo190mmImprovised | 3.7 | **962** ✔ |

**Caveat A — `MaxSpeed` is not `DesiredSpeed`.** `Projectile.cs:295-297`:

```csharp
var desiredSpeed = (Direction * DesiredSpeed);
var relativeSpeedCap = Info.ShooterVel + desiredSpeed;
MaxSpeed = relativeSpeedCap.Length();
```

Every cap scales with launcher velocity. Measured peak speeds from a launcher closing at
100/200/400 m/s: Plasma220mmTorp 1040 → 1440 → 1786 → 1833; Torpedo160mmPlasma
1300 → 1800 → 2300 → 2920. The "1040 m/s torpedo" is a 2.9 km/s torpedo off a fast hull.
`:843-844` only re-latches `MaxSpeed` downward while the round is *slower* than
`DesiredSpeed`, so the launch-time value persists for the whole flight.

**Caveat B — two rounds beat the numbers above.** BlastFrag and Hekp switch to
`SpeedCapMulti = 4.6` (**1196 m/s**) inside 2500 m, i.e. exactly in the PDC envelope.

### 2. "no SDX2 hull (max 650 m/s) can outrun a torpedo" — **REFUTED** (twice)

**a) `Torpedo160mmPlasmaAtt` never exceeds 260 m/s.** Its stage 1 sets `AccelMulti = 1`
and `SpeedCapMulti = 5`, but all five of its end conditions are `Ignore`
(`sdx_ammo_torpedo160mmPlasmaAtt.cs`, `EndCondition1/2/3 = Ignore`, and 4/5 default to
`Ignore` because that is enum value 0 — `CoreDefinitions.cs:1522-1524`). With
`Operators = StartEnd_And`, `endAnd == true`, and `Ignore` returns `conditionAnd`
(`Projectile.cs:1497-1499`) — so all five are true and the stage ends on the first tick it
runs. `ApproachEnd` takes the `!hasNextStep` branch (`:1769-1774`), approaches deactivate
(`:696`), and `speedCapMulti` falls back to 1 → cap 260 m/s. Measured peak in the sim: 520
m/s for exactly one tick, then 260 for the rest of the flight. **This def is broken.** It
is outrun by a 650 m/s hull by 390 m/s, and it dies at `MaxLifeTime` after ~10 km having
never reached a 15 km target.

**b) Even the working rounds lose the stern chase, via range not speed.** `MaxTrajectory`
counts *path* length, so a fleeing hull drains the budget. Bisected max launch range at
which a hull fleeing at 650 m/s is still caught (CPA < 500 m):

| torpedo | vs 650 m/s flee | vs 400 m/s flee | head-on |
|---|---|---|---|
| Torpedo160mmBelter | 11 217 m | 16 321 m | 24 000 m |
| Torpedo160mmPlasma | 10 891 m | 16 185 m | 24 000 m |
| Torpedo220mmHekp | 8 094 m | 14 318 m | 24 000 m |
| Torpedo160mmBlastFrag | 8 776 m | 14 702 m | 24 000 m |
| Torpedo220mmBelter | 7 783 m | 14 209 m | 24 000 m |
| Torpedo190mmImprovised | 7 321 m | 13 917 m | 24 000 m |
| Plasma220mmTorp | 7 233 m | 13 119 m | 24 000 m |
| TrailerTorp | 7 188 m | 13 590 m | 24 000 m |
| Torpedo160mmPlasmaAtt | ~500 m | ~500 m | 14 000 m |

A 650 m/s hull running from a Plasma220 launched beyond ~7.2 km escapes. Every one of
those runs ends `MaxTrajectory`, not `MaxLifeTime`.

### 3. "PDC exposure over a 3 km envelope is ~2.2-3.0 s, not 11 s" — **CONFIRMED**, band is 2.30-3.11 s

Mean of 12 seeds, head-on from 15 km, stationary target and launcher. The old flat-260
model gave (3000-150)/260 = **11.0 s**.

| torpedo | 3 km → impact | 1 km → impact |
|---|---|---|
| Torpedo160mmBelter | 2.30 s | 0.76 s |
| Torpedo160mmPlasma | 2.31 s | 0.76 s |
| Torpedo160mmBlastFrag | 2.64 s | 0.90 s |
| Torpedo220mmHekp | 2.64 s | 0.90 s |
| Torpedo220mmBelter | 2.88 s | 0.95 s |
| TrailerTorp | 2.98 s | 0.95 s |
| Plasma220mmTorp | 2.99 s | 0.96 s |
| **Torpedo190mmImprovised** | **3.11 s** | 1.03 s |
| Torpedo160mmPlasmaAtt | *never arrives* (11.5 s if it did) | — |

190Improvised is 3.11 s, marginally over the claimed 3.0 ceiling. Against a *closing*
650 m/s target the window shrinks to 1.53-2.17 s. Off a 400 m/s launcher it drops below
1.2 s.

### 4. "effective reach is MaxTrajectory 24 km, not lifetime × 260" — **CONFIRMED** (one exception)

Both are checked, independently, each tick (`Projectiles.cs:311-323`):

```csharp
info.DistanceTraveled += Math.Abs(distChanged);        // :312
if (info.RelativeAge > aConst.MaxLifeTime) { … }       // :314
if (info.DistanceTraveled * info.DistanceTraveled >= p.DistanceToTravelSqr) { … }  // :320
```

`DistanceToTravelSqr` is seeded to `MaxTrajectory²` at `Projectile.cs:251`.
`distChanged = Dot(Direction, TravelMagnitude)` and `TravelMagnitude = Velocity *
DeltaStepConst` (`Projectiles.cs:271`), so **`DistanceTraveled` is path length**, not
displacement. Neither is "authoritative" — whichever trips first wins. Which one that is:

| torpedo | MaxLifeTime | reach at terminal speed | MaxTrajectory | binds |
|---|---|---|---|---|
| Torpedo160mmBelter | 2504 t (41.7 s) | 54 253 m | 24 000 m | MaxTrajectory |
| Torpedo160mmBlastFrag | 2400 t (40.0 s) | 47 840 m | 24 000 m | MaxTrajectory |
| Torpedo160mmPlasma | 2304 t (38.4 s) | 49 920 m | 24 000 m | MaxTrajectory |
| Torpedo190mmImprovised | 2504 t | 40 147 m | 24 000 m | MaxTrajectory |
| Torpedo220mmBelter | 2504 t | 43 403 m | 24 000 m | MaxTrajectory |
| Torpedo220mmHekp | 2400 t | 47 840 m | 24 000 m | MaxTrajectory |
| Plasma220mmTorp / TrailerTorp | 2304 t | 39 936 m | 24 000 m | MaxTrajectory |
| **Torpedo160mmPlasmaAtt** | 2304 t | 9 984 m | 14 000 m | **MaxLifeTime** |

Extra finding the claim does not cover: because the budget is *path* length and the weave
lengthens the path, a weaving round fired at exactly its nominal 24 km reach dies short.
Measured CPA at a 24 km launch: Plasma220mmTorp and TrailerTorp **MISS**;
Torpedo160mmPlasma 152 m; BlastFrag 111 m. At 23 km and below everything connects.

### 5. "the old weave term `0.5*offsetRatio*accel*tof²` exceeded the physical `v*tof` bound past ~1 km" — **CONFIRMED**, and it is worse than ~1 km for half the rounds

Crossover is `tof = 2v / (ratio · A)`, at a 3 km/s PDC muzzle:

| torpedo | ratio | crossover range |
|---|---|---|
| Plasma220mmTorp / TrailerTorp | 0.7 | **571 m** |
| Torpedo160mmPlasma | 0.7 | 714 m |
| Torpedo160mmBlastFrag / 220mmHekp | 0.32 | 1 438 m |
| Torpedo190mmImprovised | 0.2 | 1 850 m |
| Torpedo220mmBelter | 0.2 | 2 000 m |
| Torpedo160mmBelter | 0.2 | 2 500 m |

At 3 km the old term claimed **5 460 m** of lateral throw against a 1 040 m hard bound —
5.3× unphysical. Simulated RMS at the same point: **67 m**.

---

## Port notes, item by item

### 1. `ProcessApproach` (`Projectile.cs:915-1401`, `1489-1620`, `1622-1775`) — ported

Three things the previous extraction got wrong, in order of impact:

**(a) `Start2Value` is not a trigger.** It is bound to `StartCondition2`
(`Projectile.cs:1266`), and in every SDX2 def `StartCondition2 = Ignore`. Verified against
raw source: `sdx_ammo_torpedo160mmBlastFrag.cs:386` is `StartCondition2 = Ignore` while
`:392` is `Start2Value = 60`. The 60 is inert. The parse in `../coreparts.json` was
*correct*; the interpretation was not.

**(b) Start conditions are irrelevant after stage 0.** `Projectile.cs:1271`:

```csharp
if (approach.StartAnd && start1 && start2 || !approach.StartAnd && (start1 || start2)
    || storage.LastActivatedStage >= 0 && !approach.CanExpireOnceStarted)
```

Every SDX2 stage sets `CanExpireOnceStarted = false`, so the third disjunct is true from
the moment stage 0 activates (`ApproachStartEvent` sets `LastActivatedStage`, `:1625`).
**The machine is driven entirely by END conditions.** This is why the 8-stage rounds look
like they trigger on distance: their end conditions are `DistanceFromPositionC` at
2500/2000/1500/1000/500/200/0 m.

**(c) `MoveToPrevious` does not move to previous.** `:1690` folds it into `activeNext`
alongside `Wait` and `MoveToNext`, so whenever the stage actually activated it advances
forward. BlastFrag stage 3 declares `MoveToPrevious` and behaves as `MoveToNext`.

`RestartCondition`, `ForceRestart`, `GetRestartId`, `StoredStart/End` slots,
`StageEvents.EndProjectile/Store*/Refund/ForceRetarget`, and the `StartAnd`/`EndAnd`
operator table (`AmmoConstants.cs:2212-2237`) are all ported. `Conditions.Ignore` returning
`conditionAnd` (`:1497-1499`) is ported — it is the mechanism behind the PlasmaAtt bug.

**Condition value binding.** `Start1Value→StartCon1`, `Start2Value→StartCon2`,
`End1..5Value→EndCon1..5`. Units are now typed per condition in the profile JSON
(`ticks` / `metres` / `hp` / `count` / `none`). Note `Lifetime` uses **absolute**
`Info.RelativeAge` (`:1546`), not stage-relative — `RelativeLifetime` (`:1558`) is the
stage-relative one.

**`DistanceFromPositionC` is not always range-to-target.** `:1509-1513` uses
`MyUtils.GetPointLineDistance` — perpendicular distance to the line
`positionC + heightOffset → positionC` — whenever `DesiredElevation != 0`. BlastFrag/Hekp
stages 2-6 carry `DesiredElevation` of ±300/±250/±150/+100, so those gates measure
cross-track offset from the elevation line, not slant range. Ported, and it is the reason
those two rounds show a 42-45 m CPA (a terminal S-weave) instead of the 4-8 m the
2-stage rounds achieve.

### 2. `AccelMulti` / `SpeedCapMulti` / `TotalAccelMulti` / `DeAccelMulti` / `ModFutureStep` — ported; **this is where v2 was most wrong**

`Projectile.cs:1273-1276`:

```csharp
accelMpsMulti = aConst.AccelInMetersPerSec * approach.AccelMulti;
speedCapMulti = approach.SpeedCapMulti;
totalAccelSq *= approach.TotalAccelMultiSq;
deAccelMulti = approach.DeAccelMulti;
```

`AccelInMetersPerSec = Trajectory.AccelPerSec` (`AmmoConstants.cs:482`) = 15600 for every
torpedo. **`AccelMulti` is a thrust multiplier, not a navigation gain.** v2's comment
("AccelMulti is a navigation gain, not a thrust limit … renormalises to speedLimitPerTick
= 15600") is contradicted by that single line. Real cruise thrust is 0.017-0.023 × 15600 =
**265-359 m/s²**, and the terminal stages of BlastFrag/Hekp are 0.17 × 15600 = 2652 m/s².

There is **no `0 means 1` fallback for `AccelMulti` or `SpeedCapMulti`** —
`AmmoConstants.cs:2177-2178` assign them raw. Only `DeAccelMulti` and `TotalAccelMulti`
get one (`:2208-2209`). Every torpedo's stage 0 has `AccelMulti = 0`, so `:794`
(`if (accelMpsMulti > 0)`) skips the whole navigation block: **the boost stage has no
thrust, no steering, and `Direction` is frozen** (it is only rewritten at `:833`, inside
that block). 1 s for the 160 mm rounds, 2 s for the 220 mm.

Consequences for agility, which nothing before this measured:

| torpedo | stage | v (m/s) | a (m/s²) | turn radius | max turn rate |
|---|---|---|---|---|---|
| Torpedo160mmPlasma / 160mmBelter | 1 | 1300 | 358.8 | 4 710 m | 15.8 °/s |
| Torpedo220mmBelter / Plasma220 / Trailer | 1 | 1040 | 265.2 | 4 078 m | 14.6 °/s |
| Torpedo160mmBlastFrag | 1 | 1040 | 358.8 | 3 014 m | 19.8 °/s |
| Torpedo190mmImprovised | 1 | 962 | 358.8 | 2 579 m | 21.4 °/s |
| BlastFrag / Hekp | 2-7 | 1196 | 2652 | **539 m** | **127 °/s** |

v2's 15600 m/s² implies 840 °/s — a **40× overestimate** of cruise agility. The real
cruise round is sluggish; the frag rounds buy a 7× agility jump for the last 2.5 km,
which is precisely the leaker-vs-PDC regime.

`SpeedCapMulti = 18.5` on BlastFrag/160Plasma stage 0 (the "implausible 4810 m/s" in the
brief) is **not a mis-parse**. The value really is 18.5. It is inert because
`AccelMulti = 0` on the same stage, so the round cannot accelerate toward it — it is a
permissive ceiling so a fast launcher's muzzle velocity is not clipped during the coast.

`ModFutureStep` (`AmmoConstants.cs:2196-2205`) ported verbatim; it is only used as the
lower clamp on `desiredLead` at `:1117`, and with `LeadDistance` 40-150 m it never binds.

`TotalAcceleration`: `MaxAcceleration = Trajectory.TotalAcceleration > 0 ? … :
double.MaxValue` (`:484`). **No SDX2 torpedo sets `TotalAcceleration`**, so the delta-v
budget at `:703`/`:860`/`:864` is infinite and inert. `TotalAccelMulti = 0` on every stage
→ `TotalAccelMultiSq = 1`. Ported anyway. Likewise `DeAccelMulti` only feeds the drag term
at `:849`, and `AmmoUseDrag` is false (no `DragPerSecond` on any torpedo) — also inert.

### 3. Smart navigation (`Projectile.cs:699-834`) — **pure pursuit REFUTED, it is proportional navigation**

`:717-720`, with `ZeroEffortNav` false (the default, and no torpedo overrides it):

```csharp
Vector3D omega = Vector3D.Cross(missileToTarget, relativeVelocity) / Math.Max(missileToTarget.LengthSquared(), 1);
lateralAcceleration = aConst.Aggressiveness * relativeVelocity.Length() * Vector3D.Cross(omega, missileToTargetNorm)
                    + aConst.NavAcceleration * lateralTargetAcceleration;
```

That is textbook true PN, `a_lat = N · V_c · (ω × r̂)`, with **N = `Smarts.Aggressiveness` = 3**
for every torpedo, plus a target-acceleration feedforward at
`NavAcceleration = Aggressiveness/2 = 1.5` (`AmmoConstants.cs:830-831` — the defs omit
`NavAcceleration`, and omitting it selects the half-aggressiveness default, not zero).

The renormalisation at `:737-738` is real and v2 read it correctly:

```csharp
var diff = accelMpsMulti * accelMpsMulti - lateralAcceleration.LengthSquared();
commandedAccel = diff < 0 ? Vector3D.Normalize(lateralAcceleration) * accelMpsMulti
                          : lateralAcceleration + Math.Sqrt(diff) * missileToTargetNorm;
```

`|commandedAccel| == accelMpsMulti` exactly. But `accelMpsMulti` is the **staged** value
(265-2652), not 15600. So the law is "always full thrust, direction chosen by PN".

**`MaxLateralThrust` is dead code for these rounds.** `AmmoConstants.cs:507` collapses an
absent value to 0.0001, which would make `:811` (`maxRotationsPerTickInRads < 1`) fire —
but `AdvancedSmartSteering = SteeringLimit > 0` (`:819`) is true for all nine (120-140°),
so `:798` takes the `ProNavControl` branch and `:810-827` never executes. Worth noting
that if it *did* execute, `:823` de-rates thrust magnitude by `|θ/π − 1|` rather than
limiting turn rate — it is a thrust penalty misnamed as a lateral-thrust limit.

**`SteeringLimit` almost never binds.** `ProNavControl` (`:1885-1905`) clamps the heading
only when `dot(Direction, ĉmd) < cos(SteeringLimit)`, i.e. below −0.5 (120°) or −0.766
(140°). A forward-flying missile does not command a near-reversal. Ported, measured
inactive in every run.

**Was the "torpedo overshoots and orbits" artefact real?** Yes — and it was caused by pure
pursuit, not by the staged accel. A/B in the same code path (`aggressiveness = 0`,
`nav_acceleration = 0` reduces `:731-733` to `commandedAccel = LOS · a`), 15 km launch,
CPA in metres:

| torpedo | target 0 m/s | | target 400 m/s | |
|---|---|---|---|---|
| | PN | pursuit | PN | pursuit |
| Torpedo160mmPlasma | 10 | 418 | 10 | 2 019 |
| Plasma220mmTorp | 6 | 3 237 | 7 | 1 312 |
| Torpedo220mmBelter | 6 | 64 | 6 | 1 162 |
| Torpedo190mmImprovised | 0 | 199 | 4 | 341 |

A 4 km turn radius plus pure pursuit cannot correct a terminal offset inside the last
2 km — that is the orbit artefact. PN nulls the LOS rate at long range where the radius is
affordable, and hits. **v2 masked a wrong guidance law by inflating thrust 40×; two errors
cancelling.** With PN restored the staged accel is fine and no orbiting occurs.

`ZeroEffortNav` (`:722-728`) is ported for completeness; no SDX2 torpedo enables it and no
stage sets `SwapNavigationType`.

### 4. The weave (`Projectile.cs:763-792`) — `weave_sigma()` replaced with simulation

```csharp
s.RandOffsetDir = Math.Sin(angle) * up + Math.Cos(angle) * right;   // :776
s.RandOffsetDir *= aConst.OffsetRatio;                              // :777
…
if (distSqr >= aConst.OffsetMinRangeSqr) { commandedAccel += accelMpsMulti * s.RandOffsetDir; }  // :787-789
```

Mechanics as ported:

- The offset is a **constant** perpendicular acceleration of `accelMpsMulti × OffsetRatio`,
  re-rolled every `OffsetTime` ticks (`:767-769`) — not a per-tick random walk.
- It is added **after** the `:737-738` renormalisation, so `|commandedAccel|` becomes
  `accelMpsMulti · √(1 + ratio²)` — the weave genuinely oversizes the command.
- **Displacement is bounded by the speed clamp — confirmed.** `:855-857` sets
  `proposedVel = Direction * speedCap`, preserving direction and truncating magnitude, so
  the weave rotates the velocity vector; it cannot lengthen it. Ceiling is `v·tof`.
- **The weave is gated OFF inside `OffsetMinRange`** (2000-2500 m) — i.e. across most of
  the PDC envelope. Any PD model that applies weave dispersion at 1-2 km is wrong.
- BlastFrag/Hekp never weave at their 2652 m/s² terminal thrust, because that stage only
  begins at 2500 m, exactly where the weave switches off. `weave_rms()` therefore uses the
  *first* powered stage, not the terminal one.

`weave_sigma(kind, tof)` keeps its signature but now calls `weave_rms()`, which integrates
the real mechanism at 60 Hz over 400 samples. Simulated RMS cross-track at tof = 1.0 s:

| torpedo | ratio | period | OffsetMinRange | RMS @ 1 s |
|---|---|---|---|---|
| Torpedo160mmPlasma | 0.7 | 30 t | 2500 m | 71.5 m |
| Plasma220mmTorp / TrailerTorp | 0.7 | 180 t | 2000 m | 67.2 m |
| Torpedo160mmBlastFrag / 220mmHekp | 0.32 | 30 t | 2500 m | 32.7 m |
| Torpedo160mmBelter / 190mmImprovised | 0.2 | 30 t | 2500 m | 20.4 m |
| Torpedo220mmBelter | 0.2 | 30 t | 2500 m | 15.1 m |
| Torpedo160mmPlasmaAtt | 0.0 | 180 t | 2500 m | 0 m — no weave at all |

### 5. Projectile-vs-projectile kill mechanics — **hits-to-kill = ceil(Health/HHM) CONFIRMED**, with a correction

`SessionDamageMgr.cs:1107-1110`:

```csharp
var damageScale = (float)attacker.AmmoDef.Const.HealthHitModifier;
if (attacker.AmmoDef.Const.VirtualBeams) damageScale *= attacker.Weapon.WeaponCache.Hits;
var scaledDamage = 1 * damageScale;
```

`:1151` subtracts `scaledDamage` from `pTarget.Info.BaseHealthPool`, seeded from
`aConst.Health` at `Projectile.cs:159`. So one hit removes exactly `HealthHitModifier`
health and **`ceil(Health / HealthHitModifier)` hits kill**. Confirmed.

Correction to `torpedo2.py`'s old `hits_to_kill`: it used `max(1, hhm)`, which silently
floors sub-1 modifiers. `HealthHitModifier` is a `double` and 0.5 is used in stock CoreParts
(`Coreparts/Definitions/AmmoTypes.cs:169,291`). Fixed.

Three mechanics the "ceil" formula hides, all ported:

- The attacker is consumed either way. On a non-killing hit `:1149` zeroes
  `attacker.BaseDamagePool`; on a killing hit `:1131-1139` deducts the target's full HP
  (not `scaledDamage`) from the attacker's health or damage pool. One PDC round per hit.
- `DamageScales.MaxIntegrity > 0` gives a hard immunity to any target with
  `BaseHealthPool` above it (`:1102-1104`). Not set on any SDX2 torpedo.
- A round with `EndOfLifeDamage > 0 && EndOfLifeAoe` past `MinArmingTime` detonates on the
  intercept and splashes every projectile in `EndOfLifeRadius` for the same
  `HealthHitModifier` each (`:1154-1155`, `DetonateProjectile` `:1164-1204`). Relevant for
  flak-vs-salvo.

Torpedo health is 4 (5 for BlastFrag/Hekp). Hits to kill: HHM 0.5 → 8/10, HHM 1 → 4/5,
HHM 2 → 2/3, HHM 5 → 1/1.

### 6. `MaxLifeTime` vs `MaxTrajectory` — see claim 4. Neither is authoritative; both are checked; `DistanceTraveled` is path length, and `RelativeAge` (`Projectiles.cs:130`, seeded −1 at `ProjectileTypes.cs:61`) is the age used, not `Info.Age`. `Info.Age` appears only in the drag term (`Projectile.cs:849`), which is inert here.

---

## UNVERIFIABLE

- **`MyUtils.GetPointLineDistance` semantics.** VRage source is not in the workshop tree.
  Ported as distance to the *infinite* line (the standard implementation). If it is
  actually a segment distance, BlastFrag/Hekp stage transitions 2→7 shift, but their accel
  and cap are identical across those six stages so flight time is unaffected; only the
  terminal S-weave amplitude and the 42-45 m CPA would change.
- **`RelativeTo.Surface` and `Elevation = Surface`** resolve to `Info.Origin` in the port
  (`Projectile.cs:1140-1141` does exactly that when `MyPlanet == null`). Correct in space,
  untested in atmosphere.
- **Multiplayer.** `DeltaTimeRatio` is 1 only on the server (`SessionSupport.cs:54`). On a
  lagging client every per-tick delta-v scales, and `AdvSyncClient && FullSync` suppresses
  the weave re-roll entirely (`Projectile.cs:771`). Model is server-side.
- **`Inaccuracy` / `OffsetTarget`.** `TargetOffSet` shifts the aim point by up to
  `Inaccuracy` metres (1-6 m here) every 300 ticks (`:621-631`). Not ported — it is
  smaller than the measured CPA for every round and would only add noise.
- **`MaxChaseTime`** (768-834 t) triggers a retarget attempt at `:559`, not a kill; if
  `NewTarget()` fails the `|| validTarget` at `:590` keeps the round alive. Not ported.
- **The 650 m/s SDX2 hull ceiling** is taken as given from the brief; hull performance is
  another agent's domain.

---

## Problems found outside my domain (reported, not fixed)

1. **`Torpedo160mmPlasmaAtt` is a broken ammo def** (`sdx_ammo_torpedo160mmPlasmaAtt.cs`,
   stage 1: `EndCondition1/2/3 = Ignore` with `Operators = StartEnd_And`). Its
   `AccelMulti = 1` / `SpeedCapMulti = 5` never take effect; it flies at 260 m/s and
   expires at ~10 km. Any balance or economics model that treats it as a peer of the other
   Plasma rounds is wrong. Fix would be `EndCondition1 = DistanceFromPositionC, End1Value = 0`
   to match `sdx_ammo_torpedo160mmPlasma.cs`.
2. **`../coreparts.json` drops `EndCondition4/5`** because the defs never write them. That
   is harmless (enum default is `Ignore`) but the generator now materialises them
   explicitly so downstream code cannot mistake "absent" for "unknown".
3. **Any consumer using a flat torpedo speed** should be re-checked. `weapons.py`,
   `pd_policy_sim.py`, `defense_sim.py`, `engage.py` and `../pdc_sim.py` were not read in
   detail (not my domain) but a 4-5× speed error propagates straight into PD sizing.
4. **`fleet_efficiency.py:38`** applies `weave_sigma` whenever `best.weaving` is true —
   which is now correct, since `Torpedo2.weaving` implements the `OffsetMinRange` gate.
   No change needed, but the semantics only became right with this rewrite.

---

## Corrected flight times

Head-on from 15 km, stationary target, stationary launcher, mean of 12 seeds.
`t→3 km` / `t→1 km` are absolute times from launch; the last two columns are the
range-independent exposure windows.

| torpedo | terminal | t→3 km | t→1 km | impact | 3 km→hit | 1 km→hit | CPA |
|---|---|---|---|---|---|---|---|
| Torpedo160mmBelter | 1300 | 11.19 s | 12.73 s | 13.49 s | **2.30 s** | 0.76 s | 6 m |
| Torpedo160mmPlasma | 1300 | 11.24 s | 12.78 s | 13.55 s | **2.31 s** | 0.76 s | 6 m |
| Torpedo160mmBlastFrag | 1196 | 13.14 s | 14.89 s | 15.78 s | **2.64 s** | 0.90 s | 45 m |
| Torpedo220mmHekp | 1196 | 14.16 s | 15.90 s | 16.80 s | **2.64 s** | 0.90 s | 42 m |
| Torpedo220mmBelter | 1040 | 14.15 s | 16.07 s | 17.02 s | **2.88 s** | 0.95 s | 4 m |
| TrailerTorp | 1040 | 14.41 s | 16.43 s | 17.39 s | **2.98 s** | 0.95 s | 3 m |
| Plasma220mmTorp | 1040 | 14.59 s | 16.62 s | 17.58 s | **2.99 s** | 0.96 s | 4 m |
| Torpedo190mmImprovised | 962 | 13.93 s | 16.01 s | 17.04 s | **3.11 s** | 1.03 s | 4 m |
| Torpedo160mmPlasmaAtt | 260 | — | — | — | — | — | MISS |

Old flat-260 model: 3 km→hit = 11.0 s for all of them. **PDCs get 3.5-4.8× less time than
every pre-correction result assumed.**

---

## Validation

`python torpedo2.py` cross-checks the 60 Hz tick sim against an independent piecewise
closed-form straight-line flight (boost coast → accelerate to each stage cap → cruise to
the stage's distance gate), weave disabled:

| torpedo | closed form | tick sim | delta |
|---|---|---|---|
| Torpedo160mmBelter | 13.50 s | 13.48 s | −0.015 s |
| Torpedo160mmPlasma | 13.50 s | 13.48 s | −0.015 s |
| Torpedo190mmImprovised | 17.04 s | 17.03 s | −0.003 s |
| Torpedo220mmBelter | 17.03 s | 17.02 s | −0.009 s |
| Plasma220mmTorp / TrailerTorp | 17.03 s | 17.02 s | −0.009 s |
| Torpedo160mmBlastFrag | 15.68 s | 15.75 s | +0.071 s |
| Torpedo220mmHekp | 16.72 s | 16.77 s | +0.050 s |

The two positive residuals are the 8-stage rounds' terminal S-weave
(`DesiredElevation ±300/±250/±150/+100`), which a straight-line closed form cannot
represent — the sim correctly flies slightly further.

`../torpedo_profiles.json` is regenerated by
`<scratchpad>/gen_torp_profiles.py` from `../coreparts.json`; rerun it if the ammo defs
change. It carries every stage field with typed condition units, plus the old flat keys so
existing callers keep working. `fleet_efficiency.py` was re-run against the new model and
still imports and executes.
