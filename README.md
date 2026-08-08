# sdx2-pd

Point-defence analysis for **Sigma Draconis Expanse 2** (Space Engineers / WeaponCore),
plus the Programmable Block script that came out of it.

Everything here was derived by reading and compiling the actual mod source, not by
guessing from stat sheets. Where a claim is measured, the t-statistic is given. Where a
claim is unverified, it says so.

---

## Start here

* **[`docs/DOCTRINE.md`](docs/DOCTRINE.md)** — what to do and why. Read section 0 first;
  it explains why most of the rest is calibrated against the wrong threat.
* **[`pb/FleetPD.cs`](pb/FleetPD.cs)** — the PB script. Paste into a Programmable Block,
  append the `WcPbApi` class from WeaponCore, recompile.

## The short version

**Fire control is worth far less than geometry.** Formation dominates everything (an
axial picket line leaks 0.00 under *every* policy, including no script at all), mount
placement is worth ~35% for free (two mounts on a stock ring never fire — own-hull
occlusion), and the best script is a distant third.

**The best script is one mechanism, not a stack.** A six-rung range ladder where each
mount drops a rung when ≥4 of its own rounds are airborne. Sustained battle, 3 hulls,
20 waves: **4.25 cumulative leakers and 14.5 waves survived**, against 21.75 / 5.6 for a
shot-counting ladder and 71.5 / 2.6 for no script.

**The governing principle, from ~45 tested policies with no exceptions: redirect fire,
never withhold it.** Everything that concentrates or re-prioritises engagement beat
baseline; everything that reduced committed ordnance improved the waste *rate* and lost
more torpedoes. Heat cycling is not merely useless, it is actively harmful (131.6 vs 21.8
cumulative leakers) — a degraded mount still fires ~12 rd/s where a cooling-pinned one
fires ~1.3.

**And the whole edifice is calibrated against the wrong torpedo.** At identical cost,
`Torpedo220mmHekp` flies a scripted terminal S-weave inside the PDC envelope, and SDX2
PDCs can only fire linear lead at projectiles (the accel-tracking solver is gated behind
`UseLimitlessPDSolver`, which no SDX2 weapon sets). Against Hekp the best policy leaks
35.7 of 48 — and the ladder is *worse than no script*. No fire control answers it.

## Why you can believe the numbers

The interception path is verified **bit-exact against compiled WeaponCore source**:
**747 differential tests** covering the RNG, the acquisition deck walk, the aim predictor,
the quartic solver, projectile-vs-projectile collision, and the full firing model (heat,
rate-of-fire truncation, reload).

The method (`csdiff/`) is the point: extract WeaponCore functions *verbatim*, compile them
against the real Space Engineers assemblies, emit ground-truth vectors as JSON, and diff
the Python port against them. That removes reading-comprehension error as a failure mode —
which mattered, because it caught several things reasoning alone had got wrong, including
a 47× spread in projectile interaction radius that comes from `Shape.Diameter` being used
as a tracer length.

**Not verified:** `sim/wc_damage.py`. Armour and penetration numbers rest on a careful
reading, not a proof. Treat them accordingly.

## Layout

| path | contents |
|---|---|
| `sim/` | the simulator: verified WeaponCore ports, hull/subsystem model, torpedoes, and every policy tested |
| `csdiff/` | the differential harness — verbatim extracts + vector emitter + diff runner |
| `pb/` | the Programmable Block script |
| `docs/` | doctrine, five domain audits, extracted rulesets, and the candidate lists (including what failed and why) |
| `extract/` | parsers that turn mod source into the JSON the sim reads |

## Running it

```bash
cd sim
python test_hifi.py          # unit checks
python test_determinism.py   # same inputs must give same outputs, across processes
python run_final.py          # the headline policy comparison
python run_oracle.py         # the unconstrained upper bound and its ablation
```

The differential harness needs .NET Framework 4.8 and a Space Engineers install:

```bash
cd csdiff
MSBuild csdiff.csproj -t:Restore,Build -p:SEBIN="C:/.../SpaceEngineers/Bin64"
./bin/Debug/net48/vectors.exe > vectors.json
python diff_test.py
```

## Attribution

`csdiff/extracted.cs`, `predict.cs`, `collide.cs` and `firing.cs` contain **verbatim
extracts of WeaponCore source** by Ash-LikeSnow, reproduced for differential testing with
substitutions numbered and documented at the top of each file. Upstream:
<https://github.com/Ash-LikeSnow/WeaponCore>. The full mod tree is deliberately **not**
vendored here — fetch it from upstream if you want to rebuild the extracts.

Game data in `extract/*.json` is derived from the Sigma Draconis Expanse 2 mod
(workshop `3580645761`) and WeaponCore (`3154371364`), and belongs to their authors.

The analysis, simulator, harness and PB script are mine.

## Caveats worth knowing before you rely on any of this

* Defending hulls are **static** — no manoeuvre, which is exactly the variable that would
  break a picket line or a staggered salvo.
* A leaker damages the hull generically and **never destroys a mount**, so the compounding
  term where losing a PDC reduces throughput for every later wave is absent.
* **A kill is not always a kill.** Shot-down SDX2 torpedoes fragment on death and the
  fragments have `Health = 0`, so they are untargetable. Killing a Belter inside ~1,100 m
  still delivers 5×1,000 damage; killing a Hekp inside ~700 m mitigates nothing. The
  leaker metric understates delivered damage by ~2.2–2.5× against fragmenting rounds —
  though the tax is policy-insensitive, so rankings hold.
* The picket-formation result is from a single study at 14 seeds and **wants independent
  replication** — it currently makes most of the fire-control work moot.
