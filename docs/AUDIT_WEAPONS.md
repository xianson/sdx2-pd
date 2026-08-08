# Weapons audit — heat, reload, dispersion, arcs, LOS, aim prediction

Scope: `weapons.py`, `wc_predict.py`. Sources of truth:

- **WC** = `.../244850/3154371364/Data/Scripts/CoreSystems/` (WeaponCore 3.0)
- **SDX** = `.../244850/3580645761/Data/Scripts/Mod/CoreParts/` + `Data/Ammo/*.sbc`

`test_hifi.py` after these changes: **38 passed, 1 failed, 1 below floor**. The one
failure is `blockHp = 16500 / 0.5` (tabletop 33,000 vs hifi 16,520) in section 1a,
which is entirely `wc_damage.py` (`B['heavy']().integrity / B['heavy']().gdm`) — the
other agent's file, mid-edit. **No assertion was weakened.** All 10 chatter checks in
section 3 still pass unchanged, and the grid solver they exercise was not modified.

---

## 1. Verdicts

### HEAT

| Claim | Verdict | Evidence |
|---|---|---|
| overheat at `Heat >= MaxHeat` | **CONFIRMED** | `WeaponShoot.cs:315`. Checked per barrel, immediately after `Heat += HeatPShot` (:313), and it `break`s the barrel loop (:318) so the rest of that shot event does not fire. |
| resume at `Heat <= MaxHeat*Cooldown` (0.822) | **CONFIRMED** | `WeaponController.cs:326`. Also: `Cooldown` is hard-clamped to `[0, 0.95]` at `CoreSystems.cs:521-522`, which is what caps `PdcPgenAdv`'s `.95f`. |
| DegradeRof engages 0.8, clears 0.4 | **CONFIRMED, with a caveat** | `WeaponController.cs:310` / `:317`; the 0.8/0.4 defaults are applied at `CoreSystems.cs:531-532` because no SDX2 def sets `DegradeRofSettings` (grep: zero usages tree-wide). **Caveat:** `:310` requires `System.DegRof`, and `sdx_weapon_pdcPgenAdv.cs:62` sets `DegradeRof = false` — that gun never degrades. The port applied degradation unconditionally. |
| `rate *= Lerp(1.0, 0.25, Heat/MaxHeat)` while degraded | **CONFIRMED, incomplete** | `WeaponController.cs:369-371`. The port stopped there; the real code then does `RateOfFire = (int)systemRate` (:376) **and** `TicksPerShot = (uint)(3600f/RateOfFire)` (:378) — two integer truncations, so the degraded rate is quantised. |
| an overheated PDC never returns to full rate | **CONFIRMED and quantified** | Resume (0.822) sits above the clear threshold (0.40), so heat oscillates in `[0.82, 1.0]` and `CurrentlyDegrading` never clears. Simulated on a held trigger for 120 s with unlimited ammo: **PdcUnn settles at 14.3 % of nominal rate** (60 → 8.6-15 shots/s, cycling OK→DEG at 7.3 s→OH at 20.6 s→DEG at 40.7 s→…); **PdcMcrn 24.7 %**; **PdcPgenAdv 100 % forever** (sink 45,000/s vs 3,529/s heat, and `DegradeRof=false`). |
| `ProhibitCoolingWhenOff` gates on `Comp.Cube.IsWorking` (`WeaponController.cs:268`) so a ceased-fire but powered mount still cools | **CONFIRMED** | Exact line. `IsWorking` is power/functional state, not firing state. `BasePDCDefinition.cs:128` sets it true for all PDCs; `sdx_weapon_pdcPgenAdv.cs:71` sets it false; no railgun sets it at all. |
| `HeatSinkRateOverheatMult` | **CONFIRMED to exist, INERT in SDX2** | `WeaponController.cs:270`: `HsRate * (Overheated && HeatSinkRateOverheatMult != 0 ? mult : 1f)`. Note the `!= 0` guard — an unset value means multiplier 1, not 0. Grep over the whole SDX2 tree: **zero usages**, only the schema declaration at `script/Structure.cs:523`. So it is 1.0 for every weapon in this project. |

**New finding the port missed entirely — cooling is not continuous.**
`HsRate = HeatSinkRate / 3` (`WeaponFields.cs:327`) and `UpdateWeaponHeat` reschedules
itself every **20 ticks** (`WeaponController.cs:345`, and `WeaponShoot.cs:307-311` starts
the loop). So cooling arrives in 3 lumps per second, and the *degrade/resume state
transitions themselves* (`:310-341`) only get evaluated on that 20-tick beat — a weapon
can sit overheated for up to 19 extra ticks after crossing the release threshold. Now
modelled (`PdcMount._cool`, `_cool_accum`).

Minor WC bug worth knowing: `var set = Heat - LastHeat > 0.001 || Heat - LastHeat < 0.001`
(`:276`) is a tautology (they meant `< -0.001`), so `set` is always true and the
transition checks always run. Also `LastHeat` is only updated inside the
`!DedicatedServer` block (`:307`), so on a DS it stays 0 forever. Neither changes
behaviour, but do not "fix" a port to match the apparent intent.

### RELOAD / AMMO

| Claim | Verdict | Evidence |
|---|---|---|
| `ReloadTime`, `MagsToLoad`, magazine `<Capacity>` | **CONFIRMED** | `CoreSystems.cs:431` `targetAmmoSize = MagsToLoad * MagazineSize`; `AmmoConstants.cs:541` `MagazineSize = MagazineDef.Capacity`. |
| PDC 40 mm = 120, so 5 mags = 600 rounds | **CONFIRMED for the 40 mm guns** | `Data/Ammo/Pdc/sdx_ammomagazinePdc.sbc:45` `<Capacity>120</Capacity>`. |
| …and therefore every PDC has 600 rounds | **REFUTED** | `sdx_ammomagazinePdc50mm` is **600** (same file, `:70`). `PdcPgenAdv` fires `PDC50mmLight` → 50 mm magazine, and it does **not** override `MagsToLoad` (still 5), so its load is **3,000 rounds, not 600** — the port was 5× low. `PdcMcrnAdv` (PDC50mmHeavy, `MagsToLoad=1`) and `PdcOpaAdv` (PDC50mmFlak, `MagsToLoad=1`) are 600 ✓. |
| `ShotsInBurst`, `DelayAfterBurst` | **CONFIRMED, and the port had neither** | Two distinct paths. `AmmoConstants.cs:1293`: `burstMode = ShotsInBurst > 0 && (energyAmmo \|\| Capacity >= ShotsInBurst)`; `:1297`: `shotReload = !burstMode && ShotsInBurst > 0 && DelayAfterBurst > 0`. `PdcPgenAdv` has ShotsInBurst 20 / DelayAfterBurst 15 and Capacity 600 ≥ 20 → **burstMode**, so it takes `WeaponShoot.cs:369→379-395`, not the `:360` shot-reload path. Either way `ShootTime = max(DelayAfterBurst, TicksPerShot)` ticks after the last shot of the burst (`:364`, `:392`). |
| `BarrelsPerShot` | **CONFIRMED** | The barrel loop `WeaponShoot.cs:80` consumes one round per barrel (`:100`) and adds `HeatPShot` per barrel (`:313`). So it multiplies **both** ammo and heat, which the port had right. |
| `TrajectilesPerBarrel` | **CONFIRMED, was missing** | `WeaponShoot.cs:195` — an inner loop that emits projectiles *without* consuming extra ammo or heat. It is 1 on every SDX2 PDC so there is no numeric impact, but the port conflated "shots" with "projectiles". Now exposed as `projectiles_per_s`. |
| `shots_per_s = RateOfFire/60 * BarrelsPerShot` | **REFUTED — this is the second-largest error in the port** | `RateOfFire` is rounds per **minute** and the engine turns it into an **integer tick period**: `TicksPerShot = (uint)(3600f / RateOfFire)` (`WeaponController.cs:378`, `:416`), consumed as `ShootTime = TicksPerShot * StepConst + RelativeTime` with `StepConst = PHYSICS_STEP_SIZE_IN_SECONDS` (`SessionFields.cs:42`) and gated by `RelativeTime < ShootTime` (`WeaponShoot.cs:42, 50`). The truncation is severe for fast guns. |

Measured cadence impact (`shots_per_s`, i.e. rounds/s):

| kind | RoF | TicksPerShot | events/s | rounds/s | old `RoF/60·brl` | error | magazine | heat/s | sink/s | t→overheat |
|---|---|---|---|---|---|---|---|---|---|---|
| PdcUnn | 2000 | 1 | 60.0 | **60.0** | 33.3 | **×1.80** | 600 | 5400 | 400 | 9.0 s |
| PdcUnnAdv | 1200 | 3 | 20.0 | 40.0 | 40.0 | ×1.00 | 600 | 3600 | 400 | 28.1 s |
| PdcMcrn | 1800 | 2 | 30.0 | 30.0 | 30.0 | ×1.00 | 600 | 3000 | 400 | 17.3 s |
| PdcMcrnAdv | 80 | 45 | 1.3 | 1.3 | 1.3 | ×1.00 | 600 | 1600 | 400 | 37.5 s |
| PdcOpa | 1200 | 3 | 20.0 | 20.0 | 20.0 | ×1.00 | 600 | 2000 | 320 | 21.4 s |
| PdcOpaAdv | 30 | 120 | 0.5 | 0.5 | 0.5 | ×1.00 | 600 | 50 | 160 | never |
| PdcPgenAdv | 3000 | 1 | 35.3 | **35.3** | 50.0 | **×0.71** | **3000** | 3529 | 45000 | never |
| PdcImprovised | 900 | 4 | 15.0 | 15.0 | — | new | 600 | 1500 | 160 | 13.4 s |

`PdcUnn` fires 80 % faster *and heats 80 % faster* than the port thought — its time to
first overheat drops from 16.2 s to 9.0 s. `PdcPgenAdv` is 29 % slower than the port
thought (the 20-shot / 15-tick burst duty cycle) but carries 5× the ammo.

### DISPERSION — **REFUTED. This is the largest error in the port.**

`WeaponShoot.cs:198-219`:

```csharp
var deviatePlus  = DeviateShotAngleRads + DeviateShotAngleRads;   // :202  = 2*dev
var deviateMinus = DeviateShotAngleRads;                          // :203  =   dev
var randomFloat1 = (float)(rnd1 * deviatePlus - deviateMinus);    // :214  ~ U[-dev,+dev]
var randomFloat2 = (float)(rnd2 * MathHelper.TwoPi);              // :215  ~ U[0,2pi)
var r1Sin = Math.Sin(randomFloat1);
muzzle.DeviatedDir = Vector3.TransformNormal(
    -new Vector3D(r1Sin*Math.Cos(randomFloat2), r1Sin*Math.Sin(randomFloat2),
                  Math.Cos(randomFloat1)), dirMatrix);            // :217
```

`randomFloat1` is the **polar** angle and it is uniform on `[-dev, +dev]`. The off-axis
angle is therefore `|randomFloat1|`, **uniform in ANGLE**, not uniform over the disc.
There is no `sqrt(rnd)` anywhere. Consequently at range `R` against a target of
radius `r`:

```
P(hit) = min(1, atan(r/R) / dev)        # LINEAR in r
```

The port used `(r / (R·tan dev))²`. The ratio of truth to port is `R·tan(dev)/r`, i.e.
the error grows *linearly with range*. Measured, vs a 1.1 m torpedo, non-weaving:

| kind | 500 m | 1000 m | 1500 m | 2500 m |
|---|---|---|---|---|
| PdcUnn (dev 0.4°) | ×3.2 | ×6.3 | ×9.5 | ×15.9 |
| PdcMcrn (dev 0.1°) | ×1.0 (sat) | ×1.6 | ×2.4 | ×4.0 |
| PdcPgenAdv (dev 0.075°) | ×1.0 (sat) | ×1.2 | ×1.8 | ×3.0 |

Note `deviateMinus` is *overwritten* rather than added when `targSGMod` is set (`:212`
vs `:207`) — a WC inconsistency, irrelevant here since `DeviateShotAngleSGModifier` is
unset in SDX2. Also, the deviation is drawn fresh per barrel *and* per trajectile
(`:195` loop encloses `:198`).

### ARCS / LOS

| Claim | Verdict | Evidence |
|---|---|---|
| full-azimuth turret with outward normal `n` covers elevations `[min,max]`; a target `theta` off `n` sits at elevation `90-theta`; bears iff `90-MaxElev <= theta <= 90-MinElev`; blind cone of `(90-MaxElev)` along `n` | **CONFIRMED** | `MyPivotUp = azimuthMatrix.Up` (`WeaponController.cs:204`) is the turret's spin axis = the mount normal. `WeaponLookAt` builds `constraintMatrix` with `Up = MyPivotUp` (`MathFuncs.cs:140-146`), flattens the target vector by dropping the Up component (`:165`), and computes `desiredElevation = angle(localTargetVector, flattenedTargetVector) * sign(Y)` (`:180`) — i.e. elevation is measured **off the plane perpendicular to the normal, toward the normal**. Straight up the normal gives `flattened == 0` → elevation `±90` (`:175-176`). So elevation `= 90 − theta` and `MaxElevation < 90` leaves a genuine blind cone. PdcUnn / PdcUnnAdv (`MaxElevation = 80`) have a 10° blind cone; every other SDX2 PDC is 90 → none. |
| `AimingTolerance` | **CONFIRMED as a separate gate; does NOT widen the arc for SDX2 PDCs** | `AimingTolerance = Math.Cos(AimingToleranceRads)` (`WeaponFields.cs:331`) and `AimingToleranceRads = ToRadians(value <= 0 ? 180 : value)` (`CoreSystems.cs:853`) — **zero means 180°, not zero**. It is tested against the *actual barrel direction*: `IsDotProductWithinTolerance(ref MyPivotFwd, ref targetDir, AimingTolerance)` (`WeaponTracking.cs:433`, `:296`), which reduces to `cos(angle) > tol`. Values: 60° base, 1° on PdcMcrnAdv, 15° on PdcPgenAdv, and **0 → 180°** on `railgunPgenLightFixed` (`:27`). |
| `AddToleranceToTracking` | **CONFIRMED, and it is false everywhere that matters** | `WeaponTracking.cs:1725-1734` widens the *mechanical* limits by `toleranceRads` only if `TurretMovement` is `AzimuthOnly`/`ElevationOnly` **or** `AddToleranceToTracking`. Both PDC and railgun bases set it false; the single `true` in the whole mod is `sdx_weapon_torpedoLauncherImprovisedDouble.cs:36`. Note the WC bug: the `else if (… \|\| AddToleranceToTracking)` at `:1730` is unreachable when the flag is true because `:1725` already caught it, so the flag can only ever widen **elevation**, never azimuth. |
| a "fixed" railgun has ±5 azimuth, not zero | **CONFIRMED — and it is stronger than claimed** | All five fixed railguns set ±5 in **both** axes: `MaxAzimuth=5 / MinAzimuth=-5 / MaxElevation=5 / MinElevation=-5` at `railgunImprovisedLightFixed.cs:33-36`, `railgunMcrnMediumFixed.cs:33-36`, `railgunOpaMediumFixed.cs:28-31`, `railgunPgenLightFixed.cs:36-39`, `railgunUnnLightFixed.cs:40-43`. So it is a 10°×10° box, not a full elevation range — and the `90−theta` mapping does **not** apply to them (the normal is the boresight, not a spin axis). Genuine zeroes do exist in this codebase (`BaseTorpedoLauncherDefinition.cs:84-85`, `Misc/sdx_lidar.cs:134-135`), so ±5 was a deliberate choice. They also keep `TurretAttached = true` / `TurretController = true` — the lines that would disable them are commented out (`railgunMcrnMediumFixed.cs:29-30`, `railgunUnnLightFixed.cs:34-35`) — so they are narrow-arc *turrets*. Turreted railguns never touch azimuth and inherit ±180 (`BaseRailgunDefinition.cs:79-80`). |
| `RotateRate`/`ElevateRate` slew limits | **CONFIRMED** | `MathFuncs.cs:218-222`: `simAzStep = AzStep * DeltaTimeRatio`, then `Clamp(azToTraverse, ±simAzStep)`; `AzStep = RotateRate` in **rad per tick** (`CoreSystems.cs` `TurretMovements`). PDCs are 0.0785-0.1309 rad/tick (270-450 °/s); railguns are 0.01-0.1 (34-344 °/s). Crucially `isTracking = !azHitLimit && !elHitLimit` (`:274`) — a mount pinned at an arc limit reports **not tracking** even if the target is barely outside. |
| scope LOS / `MuzzleCheck` / `DisableLosCheck` | **CONFIRMED, and the port was missing the throttle** | The ray runs from `GetScope.Info.Position`, optionally pulled back by `ScopeDistToCheckPos` (`WeaponTracking.cs:1519-1520`) — **the scope dummy, not the muzzle**. `MuzzleCheck` adds a per-muzzle self-hit test (`:1553-1563`); it is `false` on every SDX2 weapon (zero `= true` hits tree-wide). `DisableLosCheck` is `false` on all PDCs but **`true` on three railguns** (`railgunOpaLightTurreted.cs:51`, `railgunOpaMediumFixed.cs:52`, `railgunUnnLightFixed.cs:50`) and on the torpedo-launcher base (`:112`). **The whole check is throttled**: `session.Tick - w.Comp.LastRayCastTick > 29` (`:458`), so LOS is re-tested at most every 30 ticks *per block*, and a mount whose LOS just became blocked keeps firing into its own hull for up to half a second. |

### PREDICTION (`wc_predict.py`)

| Claim | Verdict | Evidence |
|---|---|---|
| `TrajectoryEstimation` line-faithful | **CONFIRMED** for the structure at `WeaponTracking.cs:874-1099` | |
| `CalculateCrudeTti` | **CONFIRMED, exact** | `:696-720`. Every line matches. |
| `DecidePredictionAlgorithm` gate `angularVel² > 0.0003 \|\| (accel² > 100 && vel² > 100)` | **CONFIRMED, exact** | `:859-860`. The real gate also requires `GridTarget?.Physics != null && !GridTarget.Closed` (`:856-857`). `allowAdvancedGridAlgorithm = (int)Prediction > 1` (`:943`), and the enum is `Off, Basic, Accurate, Advanced` = 0..3 (`CoreDefinitions.cs:507-513`) — so **Accurate also enables it**, not just Advanced. |
| `CalculateAdvancedGridAimPrediction` incl. the per-step quadratic and the `LargeShipMaxSpeed` clamp | **CONFIRMED, faithful** | `:1115-1287`. Verified line by line: the `start`/`budget` bounds (`:1158-1159`), the vertex-sign fallback for a double root inside one frame (`:1192-1202`), the root window `t > t0 && t <= t0+dt` (`:1213-1221`), `applyMaxSpeedAfterStep` ordering (`:1266-1277`), and the offset/accel rotation by the angular-velocity quaternion (`:1279-1280`). Two things the port dropped and I restored: the returned point velocity `(currentX.Translation − previousX.Translation)/dt` (`:1233`), and the fact that `targetDriveAccelWorld` is **re-read from `targetGrid.Physics.LinearAcceleration` inside the function** (`:1138-1140`) rather than taken from the caller. |
| `useSimple` when `targAccelSqr < 2.5` | **CONFIRMED but INCOMPLETE — and the omission is decisive** | `:902` is `useSimple = ammoDef.Const.AmmoSkipAccel \|\| targAccelSqr < 2.5`. `AmmoSkipAccel = AccelPerSec <= 0` (`AmmoConstants.cs:497`). **Every SDX2 PDC round and every railgun sabot has `AccelPerSec = 0f`**, so `useSimple` is unconditionally true and **the QuarticSolver fallback is dead code for every SDX2 kinetic weapon**. The same flag zeroes `projectileAccelTime`, so the `timePenalty` fudge (`:974-981`, `:1014-1020`) is always 0. |
| QuarticSolver stand-in | **PARTIALLY REFUTED** | The coefficients are algebraically equivalent: `WeaponTracking.cs:622-626` is exactly `\|dr + dv·t + ½a·t²\|²/v² − t²`, i.e. the port's `f(t)` scaled by `1/v²`, so the Newton root is the same. But four real behaviours were missing: (a) it **returns a convergence flag** and the caller keeps the crude tti on failure — `QuarticSolver(...) ? advTti : tti` (`:1012`); (b) 10 iterations, not 6 (`:628`); (c) an absolute tolerance `1e-3` on the *scaled* residual (`:639`); (d) **no positivity clamp** — the real solver can return a negative `t`, which is precisely why (a) exists. All four are now ported. |
| — | **REFUTED: the port added an acceleration term to the quartic aimpoint that does not exist** | `:1022` is `aimPoint = frame0.TargetPos + (finalTti + timePenalty) * frame0.Dv` — **`Dv` only**. The quartic refines the *time*; the aim point is then a pure linear extrapolation. The port returned `TargetPos + Dv·t + accel·(0.5t²)`. Dead code in practice (see `AmmoSkipAccel`), but wrong. |
| `accel_used_by_predictor` cites `AiTargeting.cs:1257` | **MISATTRIBUTED** | The line is real — `var targetAccel = (int)AimLeadingPrediction > 1 ? Physics?.LinearAcceleration : Vector3.Zero;` — but it lives inside **`AcquireBlock`**, gating the acquisition-time lead used to pick a subsystem block. The firing solution reads accel raw with no prediction gate (`WeaponTracking.cs:279` in `TargetAligned`, `:368` in `TrackingTarget`). Docstring corrected; the function is no longer applied to the firing path. |

**Gap the port hid: PDC-vs-torpedo never runs advanced prediction at all.**
A torpedo is a `Projectile` target, so `DecidePredictionAlgorithm` takes the
`TargetType.Projectile` branch (`:840-851`) → `CalculateAdvancedPdAimPrediction`. That
branch is gated on `allowAdvancedProjectileAlgorithm = Prediction > 1 && UseLimitlessPDSolver`
(`:944`), and **`UseLimitlessPDSolver` is never set anywhere in SDX2** (only the schema
declaration at `script/Structure.cs:565`). Combined with `AmmoSkipAccel`, every SDX2
PDC firing at a torpedo lands on `TargetPos + crudeTti * Dv` — a **plain
constant-velocity intercept with zero acceleration compensation**. That is the single
most important fact for point defence and the port did not represent it.
`advanced_pd_prediction` is now ported behind `use_limitless_pd_solver=True` so the gap
is visible rather than silent.

---

## 2. CLAIM TO TEST HARDEST — "chatter defeats railguns"

> "a target oscillating faster than projectile flight time makes the predictor over-lead
> by `0.5*a*tf²`, needing `a > 2*r/tf²`"

### The mechanism and the formula: **CONFIRMED**

`CalculateAdvancedGridAimPrediction` propagates the target with the *instantaneous*
`Physics.LinearAcceleration` held constant for the whole flight (`:1138-1140`, `:1255`,
`:1271`). If the true acceleration reverses inside the flight window, the assumed
displacement `½a·tf²` is spurious. Verified as an **over-lead**, consistently in the
direction of the instantaneous accel — 6 firing phases at 10 km, a = 100 m/s²,
period 0.5 s gave `aim.y − truth.y` of −62.0, +45.4, +53.7, +62.1, −45.3, −53.7 m
against the predicted 50 m. The threshold `a > 2r/tf²` is then a trivial rearrangement
of `½a·tf² > r`. The existing 10 test-suite checks (10 km/8/6/4/2 km × a = 60/100)
match the closed form to 0.3-7.8 %.

### "faster than projectile flight time": **CONFIRMED, and the claim is conservative**

Period sweep at a = 100 m/s², muzzle 10 km/s:

| R | tf | period 0.1 | 0.25 | 0.5 | 1.0 | 2.0 | 8.0 | constant | `½a·tf²` |
|---|---|---|---|---|---|---|---|---|---|
| 10 km | 1.00 s | 52.0 | 52.2 | 53.3 | **56.3** | 46.5 | 26.6 | **3.3** | 50.0 |
| 4 km | 0.40 s | 9.0 | 8.9 | **9.4** | 7.1 | 5.4 | 6.1 | **1.5** | 8.0 |

The miss is flat at `½a·tf²` for `period ≲ 2·tf` and actually *peaks* near
`period ≈ tf`, so the requirement is looser than "faster than tf". Constant
acceleration produces only 3.3 m at 10 km, which is the positive control: the advanced
solver compensates constant accel almost perfectly. **The vulnerability is to the
*change* in acceleration, not to acceleration.**

### As a tactical claim: **MATERIALLY REFUTED**

**(a) Most hulls cannot generate the required acceleration.** Sabot muzzle speed is
10,000 m/s (`RailAmmo/sdx_ammo_sabot*.cs:100`) and railgun `MaxTargetDistance` is
10,000 m (`BaseRailgunDefinition.cs:39`), so **`tf` cannot exceed 1.0 s** — which caps
the achievable over-lead at `0.5·a·1.0² = a/2` metres. Chatter is lateral, so it must
come from the RCS ring; main-drive acceleration is along the hull axis and cannot be
reversed on a sub-second period. Using this project's own `shipyard.build_ship` masses
and RCS counts, and `r` = beam half-width (chatter displaces across the beam):

| class | mass | nRCS | a (⅙ facing) | a (¼ facing) | beam r | need @10 km | need @6 km | verdict @10 km |
|---|---|---|---|---|---|---|---|---|
| Skiff | 680 t | 188 | 69.1 | 103.6 | 6.2 m | 12.5 | 34.7 | **YES** |
| Barge | 1313 t | 194 | 36.9 | 55.4 | 7.5 m | 15.0 | 41.7 | **YES** |
| Picket | 1845 t | 196 | 26.6 | 39.8 | 8.8 m | 17.5 | 48.6 | **YES** |
| Hauler | 2263 t | 192 | 21.2 | 31.8 | 8.8 m | 17.5 | 48.6 | **YES** |
| Outpost | 2332 t | 195 | 20.9 | 31.4 | 8.8 m | 17.5 | 48.6 | **YES** |
| Corvette | 3055 t | 200 | 16.4 | 24.5 | 10.0 m | 20.0 | 55.6 | marginal |
| Installation | 3914 t | 200 | 12.8 | 19.2 | 11.2 m | 22.5 | 62.5 | marginal |
| Frigate | 5043 t | 200 | 9.9 | 14.9 | 12.5 m | 25.0 | 69.4 | **NO** |
| Cruiser | 6785 t | 200 | 7.4 | 11.1 | 13.8 m | 27.5 | 76.4 | **NO** |
| Carrier | 8665 t | 200 | 5.8 | 8.7 | 15.0 m | 30.0 | 83.3 | **NO** |

Requirement scales as `1/tf²` = `1/R²` while capability is fixed, so **nobody can
chatter through a railgun at 6 km or closer.** Chatter is a small-ship, max-range-only
tactic, and it is useless for exactly the capitals the claim would matter most for.
The railgun's counter is simply to close.

**(b) The vulnerability is a definition setting, not a physics fact — and the fix is
*less* prediction, not more.** `allowAdvancedGridAlgorithm` requires
`Prediction > 1` (`:943`). Dropping a railgun to `AimLeadingPrediction = Basic` makes
the shot fall through to `TargetPos + crudeTti·Dv`, whose error is bounded by the
target's *velocity* oscillation `(a·T/4)·tf` rather than by `½a·tf²` — and for
`T < 2·tf` the former is strictly smaller:

| R | a | period | Advanced (3) | Basic (1) | Advanced/Basic |
|---|---|---|---|---|---|
| 10 km | 60 | 0.25 s | 31.0 m | **2.5 m** | ×12.2 |
| 10 km | 60 | 0.50 s | 31.2 m | **3.8 m** | ×8.2 |
| 10 km | 100 | 0.25 s | 51.6 m | **4.1 m** | ×12.7 |
| 10 km | 100 | 1.00 s | 53.8 m | **12.6 m** | ×4.3 |
| 6 km | 100 | 0.25 s | 18.8 m | **2.3 m** | ×8.1 |
| 10 km | 30 | constant | **1.0 m** | 14.8 m | ×0.07 |
| 10 km | 100 | constant | **3.3 m** | 51.9 m | ×0.06 |

So the advanced predictor is 4-13× **worse** against chatter and 5-15× **better**
against sustained acceleration. All SDX2 railguns ship `AimLeadingPrediction = Advanced`
(`BaseRailgunDefinition.cs:51`), which is what creates the exploit. This is a live
rock-paper-scissors between predictor setting and target behaviour, not a one-way
counter.

**(c) Unverified premises.** Two things cannot be settled from these sources:
whether SE thrusters can reverse a 25 m/s² lateral command on a 0.25-0.5 s period with
no meaningful ramp, and whether `MyPhysicsBody.LinearAcceleration` really reports a
clean one-tick finite difference (Havok internals). Both are assumptions baked into
`chatter_experiment.py`. **UNVERIFIABLE from source — needs the in-game measurement
that has never been done.** They matter: a thruster ramp comparable to the chatter
period would flatten the effective amplitude and, per (a), most classes have no margin
to spare.

**Verdict: the physics is right, the arithmetic is right, the tactical conclusion is
wrong for anything Frigate-sized or larger, wrong at any range under ~8 km, and
avoidable by the defender at the cost of a definition edit.**

---

## 3. Torpedo weave — the other big correction

The port's docstring claimed `0.7 * 15600 = 10,920 m/s²` of sustained lateral
acceleration beyond 2500 m, and `p_kill_per_shot` used
`hypot(dispersion, 0.5*10920*tof²*0.35)`.

The `10920` is arithmetically right and physically meaningless. From
`Projectile.cs:787` the command is `accel*(pursuit + OffsetRatio·RandOffsetDir)`, but
`AccelPerSec = 260*60 = 15600` while `DesiredSpeed = 260`
(`sdx_ammo_torpedo160mmPlasma.cs:182-183`), so **`accel·dt` = 260 m/s = the entire
cruise speed in one tick**, and `:852-856` re-caps the speed to `DesiredSpeed` every
tick. The weave is therefore a **bounded heading offset of `atan(OffsetRatio)` at
constant speed**, re-drawn every `OffsetTime` ticks — not an unbounded acceleration.
Two further things the port missed: `MaxLateralThrust` is unset on every SDX2 torpedo
and `Clamp(0 → 0.0001)` (`AmmoConstants.cs:507`) makes the `:823` magnitude scaling
`|δ/π − 1|` permanently active; and `OffsetRatio` is per-round — **0.2** (160 mm
Belter), **0.32** (220 mm HEKP), **0.7** (160 mm Plasma). The port applied the worst
case to everything.

Replacement model, derived not fitted:
`v_lat = cruise·ratio/√(1+ratio²)`; a re-draw changes the lateral velocity by
`(4/π)·v_lat` on average (`E|û₁−û₂| = 4/π`); the predictor's error is that jump times
the flight time remaining after the **last** re-draw. Validated against 900-sample
runs of the corrected `Torpedo` (phase swept over all 30 weave phases — an earlier
measurement that fixed the phase gave nonsense):

| tof | 0.1 s | 0.2 | 0.3 | 0.5 | 0.7 | 1.0 | 1.33 | 2.0 |
|---|---|---|---|---|---|---|---|---|
| sim mean cross-track error | 2.2 m | 7.8 | 17.3 | 47.0 | 78.2 | 118.8 | 169.4 | 265.0 |
| model | 1.9 | 7.6 | 17.1 | 47.5 | 85.4 | 142.4 | 205.0 | 332.2 |
| model/sim | 0.87 | 0.98 | 0.99 | 1.01 | 1.09 | **1.20** | 1.21 | 1.25 |
| old port model | 76.4 | — | — | **477.7** | — | **1911.0** | — | — |

Exact to 1-3 % over the 0.2-0.5 s band, +20 % at the longest flight a 3 km / 3000 m/s
PDC can have; it over-predicts at long flights because it ignores the pursuit term
pulling earlier legs' drift back out. The old model was **10× high at tof 0.5 s and
16× high at 1.0 s**.

**One subtlety that bit me and is worth recording.** Averaging the *offset* over weave
phase and then computing one hit probability drives every weaving shot to exactly 0,
because a hit needs the dispersion radius to nearly cancel a ~47 m offset and that
never happens. The physically correct structure is to average the **hit probability**
over phase: the phases where no re-draw falls inside the flight window are shots that
flew within a single straight weave leg, and the constant-velocity lead is *exact* for
those. Those are the shots that connect. `p_kill_per_shot` now phase-averages the
probability (`_weave_residuals`, 64 phases).

Net effect on `p(kill)` per round vs a 1.1 m torpedo:

| kind | 500 m | 1000 m | 1500 m | 2500 m |
|---|---|---|---|---|
| PdcUnn, weaving | 0.0004 → **0.215** | 0.0000 → **0.056** | 0.0000 → 0.0026 | 0 → 0 |
| PdcMcrn, weaving | 0.0004 → **0.676** | 0.0000 → **0.219** | 0.0000 → 0.0070 | 0 → 0 |
| PdcPgenAdv, weaving | 0.0009 → **0.734** | 0.0001 → **0.383** | 0.0000 → **0.101** | 0 → 0 |
| PdcOpaAdv (flak), weaving | 1.0 → **0** (min range) | 0.222 → **1.0** | 0.044 → **1.0** | 0.006 → **0.391** |

`defense_sim.py` conclusions invert as a result: PDC batteries now stop essentially
every salvo tested, where before the weave made them near-useless. **Any prior
project conclusion that "torpedoes are nearly unstoppable" was an artifact of these
two bugs (the squared dispersion law and the 10× weave), not a finding.**

Flak chain verified: `PDC50mmFlak` has `MaxLifeTime = 1` tick and `Fragments = 1,
ArmWhenHit` (`:59,:67,:135`) so it converts to `Flak50mmStage2` ~50 m off the muzzle;
Stage2 is `SphereShape` d=25 with `TimedSpawns { Proximity = 100, ParentDies = true,
MaxSpawns = 1 }` (`:298-304`) spawning `Fragments = 45` (`:287`); each fragment has
`HealthHitModifier = 11` (`:531`) vs torpedo `Health` 4-5, so one connects and kills.
`FLAK_PROXIMITY = 100` and `FLAK_FRAGMENTS = 45` are both correct. But Stage2's
`Guidance = Smart` is cosmetic: `AccelPerSec = 5` (`:374`) over its 100-tick life gives
8.3 m/s of Δv on a 3000 m/s round — a 0.16° course change. **Flak is effectively an
unguided round with a 100 m proximity fuse**, which is why `DeviateShotAngle = 0f` with
the comment "PDC uses a travel-to smart ammo, base accuracy doesn't affect" is
misleading, and why flak still has to beat the weave (it fails past ~3 km).

---

## 4. Mechanics in source but missing from the port, ranked by impact

**Fixed in this pass:**

1. **Dispersion is uniform in polar angle, not over the disc** (`WeaponShoot.cs:214`). Understated every PDC hit probability by ×1.0-16, growing with range.
2. **Torpedo weave is a bounded heading offset, not 10,920 m/s²** (`Projectile.cs:787, 823, 852-856`). Overstated weave-induced miss ~10-16×, which had zeroed PDC effectiveness against every weaving torpedo.
3. **`TicksPerShot = (uint)(3600/RateOfFire)`** (`WeaponController.cs:378`). PdcUnn ×1.80 rate and heat; PdcPgenAdv ×0.71.
4. **`PdcOpaAdv` has `MinTargetDistance = 1000`** (`sdx_weapon_pdcOpaAdv.cs:30`). The flak PDC is blind inside 1 km — precisely the terminal phase. The port had no minimum range at all. Biggest single tactical omission.
5. **`PdcPgenAdv` magazine is 3,000 rounds** (50 mm mag capacity 600 × `MagsToLoad` 5), not 600.
6. **`ShotsInBurst` / `DelayAfterBurst` duty cycle** and the `burstMode` vs `HasShotReloadDelay` distinction (`AmmoConstants.cs:1293,1297`, `WeaponShoot.cs:360-395`).
7. **`DegradeRof` is per-weapon** — false on `PdcPgenAdv` (`:62`). The port degraded everything.
8. **Degraded rate is doubly truncated** (`WeaponController.cs:376,378`), and **cooling runs in 20-tick lumps of `HeatSinkRate/3`** (`:345`, `WeaponFields.cs:327`) rather than continuously.
9. **The quartic branch is dead code** (`AmmoSkipAccel`, `AmmoConstants.cs:497`), and the port's quartic aim point wrongly added `0.5·a·t²` (`WeaponTracking.cs:1022` uses `Dv` only).
10. **`QuarticSolver` returns a convergence flag the caller acts on** (`:1012`); 10 iterations; no positivity clamp.
11. **`UseLimitlessPDSolver` is never set**, so PDC-vs-torpedo is a pure constant-velocity lead (`:944`). `advanced_pd_prediction` now ported behind the flag.
12. **`AimLeadingPrediction` is per-weapon** — Basic on `PdcOpaAdv`/`PdcImprovised`, Accurate on `PdcOpa`, Advanced elsewhere — and *Accurate already enables* `AdvancedGrid` (enum `CoreDefinitions.cs:507-513`).
13. **`AimingTolerance` (incl. `<= 0 → 180°`), `RotateRate`, `ElevateRate`** now drive acquisition instead of a magic `RETARGET_S = 0.35`. The dead time is derived per weapon (π/2 of traverse at `RotateRate` + `DelayUntilFire`); pass `dir_local` to `acquire()` for the real slew.
14. **`PdcImprovised` did not exist** in the port (RoF 900, MaxHeat 18000, sink 160, dev 0.5°, el −30..90).
15. **`TrajectilesPerBarrel`** (all 1 in SDX2, so no numeric impact) — exposed as `projectiles_per_s` so shots and projectiles stop being conflated.
16. **`MaxLateralThrust` magnitude scaling** on the torpedo (`Projectile.cs:823`, always active because `Clamp(0 → 0.0001)`).
17. **`Cooldown` clamped to `[0, 0.95]`** (`CoreSystems.cs:521-522`).
18. **Limited-azimuth mounts** (the ±5°/±5° fixed railguns) now use a boresight box instead of the turret `90 − theta` mapping, which does not apply to them.

**Still not modelled — documented, ranked:**

1. **`SpeedVariance = Random(-150, +150)`** on every PDC round (`sdx_ammo_PDC40mm.cs:102`). ±5 % muzzle speed against a predictor that assumes `DesiredSpeed`, i.e. an along-track lead error of up to 5 % of the lead distance. At 2 km with a 260 m/s crosser that is ~9 m of extra miss, comparable to the dispersion cone. Probably the largest remaining PDC-accuracy gap.
2. **`DelayCeaseFire`** (30 ticks on PDCs, 0 on `PdcPgenAdv`). Half a second of ammo and heat spent after the target dies or is lost, per re-target. A pure wastage term the sims currently get for free.
3. **LOS 30-tick throttle** (`WeaponTracking.cs:458`). The port treats occlusion as instantaneous; the real gun keeps firing into its own hull for up to 0.5 s. Conservative in the port's favour, so it understates friendly-fire and overstates effective mounts.
4. **`MaxTrajectory` (3500 m) exceeds `MaxTargetDistance` (3000 m)** for the 40/50 mm rounds. Rounds fired at max range keep flying 500 m past it and can still hit — the port hard-stops at `MaxTargetDistance`.
5. **Flak Stage2 pathologies**: `DesiredSpeed = 0` with a nonzero inherited velocity interacting with `MaxSpeed`/`speedCap` (`Projectile.cs:841-856`), `Inaccuracy = 10`, `Roam = true`, `MaxTargets = 60`, and a 60 m / 1 dmg end-of-life AoE. Any of these could change flak's real behaviour materially.
6. **`RofModifier` terminal slider.** `Ui.RateOfFire = true` with `RateOfFireMin` 0.6-0.72 on PdcUnn/PdcUnnAdv/PdcMcrn/PdcMcrnAdv (`sdx_weapon_pdcUnn.cs:24-25` etc.). A player can trade rate for thermal endurance, which given the 14 % sustained duty cycle above is probably a real optimisation the sims cannot express.
7. **`Comp.CurrentHeat` / `Comp.MaxHeat`** — a block-level heat aggregate maintained alongside per-part `PartState.Heat` (`WeaponShoot.cs:314`, `WeaponComp.cs:281`). Matters only for multi-weapon blocks.
8. **`Overload > 1` self-damage** on overheat: 2 % of max integrity per event (`WeaponShoot.cs:414-418`). `EnableOverload = false` on SDX2 PDCs so it is unreachable, but it is the mechanism by which a badly-run PDC destroys itself.
9. **`TopTargets`/`CycleTargets`/`TopBlocks`/`CycleBlocks`** and the `ClosestFirst = false` shuffled-deck acquisition. The port keeps a per-mount RNG and a comment about it but does not implement the candidate-deck cycling.
10. **`GravityMultiplier = 3`** and the whole gravity ballistics block (`WeaponTracking.cs:1033-1098`). Irrelevant in space; would matter for any planetary scenario.
11. **`Threats` ordering / `IgnoreDumbProjectiles` / `ValidSubSystemTarget`** — which is out of my domain but is what decides whether a PDC shoots the torpedo or the ship behind it.

---

## 5. Problems found outside my domain (reported, not edited)

- **`wc_damage.py`** — `test_hifi.py` section 1a check `blockHp = 16500 / 0.5` now fails: tabletop 33,000 vs hifi 16,520. `B['heavy']().integrity / B['heavy']().gdm` is returning ~16,520, so either `integrity` moved to 8,260 or `gdm` moved to ~1.0. Present before any of my edits (verified against the pre-change baseline, which was 39/0). Whoever owns `wc_damage.py` should confirm this was intended.
- **`chatter_experiment.py`** — `one_shot` scores a miss as `|target_pos_at_impact − aimpoint|`, i.e. it counts along-track error as a miss. For a projectile that passes through, only cross-track error causes a miss. It happens not to matter for the perpendicular-crossing geometry used, but it will silently overstate misses in any geometry with a radial component. It also hardcodes `muzzle=10000` and `max_speed=1000`; the latter matches `catalogue.json` `world_speed = 1000`, the former matches sabot `DesiredSpeed`, so both are right today but neither is sourced.
- **`engage.py:124-125`** duplicates the dispersion model and has the *opposite* bug from the one I fixed: `ang = gun.dev * math.sqrt(rnd.random())` samples a uniform **disc**, whereas `WeaponShoot.cs:214` samples uniform in **angle** (no `sqrt`). It should be `ang = gun.dev * rnd.random()` with a random sign, or equivalently `gun.dev * (2*rnd.random() - 1)`.
- **`fleet_efficiency.py:34-38`** inlines its own copy of the old, wrong `p_kill` (squared law plus the `0.5*10920*tof²*0.35` weave term) instead of calling `PdcMount.p_kill_per_shot`. It will keep producing the pre-audit numbers until it is pointed at the shared method.

---

## 6. API changes in `weapons.py`

- `PDC_STATS` is now a dict of **named-field dicts** instead of positional tuples. Both importers (`defense_sim.py`, `pareto.py`) imported it without using it, so nothing breaks. `PDC_MUZZLE` is retained as a derived view.
- `PdcMount.__init__(kind, cell, normal, name=None, component=None)` unchanged. All previously used attributes are unchanged (`range`, `dev`, `muzzle`, `hhm`, `is_flak`, `shots_per_s`, `mag_rounds`, `reload_s`, `heat`, `max_heat`, `sink`, `elev_min/max`, `blind_cone_deg`, `bears`, `occluded`, `acquire`, `step`, `reset`, `p_kill_per_shot`).
- New: `min_range`, `aim_tol`, `rotate_rate`, `elevate_rate`, `az_min/az_max`, `full_azimuth`, `projectiles_per_s`, `tps`, `burst_mode`, `degrade_rof`, `prediction`, `retarget_s`, `spec`.
- `acquire(tgt, dir_local=None, dt=DT)` — passing `dir_local` runs the real slew model; omitting it keeps the old call signature with a per-weapon derived dead time.
- `p_kill_per_shot(dist, torp_radius, weaving, cruise=…, offset_ratio=…, offset_ticks=…)` — the three new keywords let callers use the actual torpedo variant's `OffsetRatio` (0.2 / 0.32 / 0.7) instead of always the worst case. It now also returns 0 outside `[MinTargetDistance, MaxTargetDistance]`.
- New module functions: `ticks_per_shot`, `weave_offset`, `_p_within`, `_weave_residuals`. New constants: `TORP_ACCEL`, `TORP_CRUISE`, `TORP_OFFSET_RATIO`, `TORP_OFFSET_TIME`, `TORP_OFFSET_MIN_RANGE`, `TORP_RADIUS`.
- `Torpedo(...)` gains `radius` and `max_lateral_thrust`; defaults now reference the named constants.

## 7. API changes in `wc_predict.py`

- `trajectory_estimation(...)` gains `ammo_skip_accel=True` (correct for all SDX2 kinetics), `projectile_accel`, `use_limitless_pd_solver`, `target_is_projectile`, `prev_vel1`, `prev_vel0`, `target_max_speed`. Existing positional/keyword calls in `chatter_experiment.py` and `engage.py` are unaffected.
- `advanced_grid_prediction` now returns a 4-tuple `(found, intercept, tti, point_vel)`.
- `quartic_solver` now returns `(converged, t)` and takes `tolerance`/`max_iterations`.
- New: `advanced_pd_prediction`, `decide_algorithm_projectile`.
