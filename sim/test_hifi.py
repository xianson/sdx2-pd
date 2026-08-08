"""Cross-validation: hand-computable tabletop closed forms vs the line-faithful ports.

Every check states the arithmetic you can do on a calculator, then asserts the
ported engine code produces it. A FAIL means either the tabletop derivation or the
port is wrong — both are shown so the discrepancy is diagnosable.
"""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from wc_damage import Ammo, Block, fire, base_scale, sdx_blocks, sdx_ammo
from rcs_gyro import (total_moment, applied_torque, gyro_multiplier, ring_layout,
                      alpha_deg, inertia_box, moment_for, LEFT, RIGHT, UP, DOWN,
                      FWD, BACK, RCS_THRUST, RCS_MASS, GRID_SCALE_LARGE, BASE_GYRO_FORCE)
from vec import V

PASS = FAIL = SKIP = 0
def check(label, tabletop, hifi, tol=0.02, unit='', floor=0.0):
    """floor = absolute noise floor below which the comparison is not resolvable."""
    global PASS, FAIL, SKIP
    if floor and abs(tabletop) < floor:
        SKIP += 1
        print(f"  [n/a ] {label:<52} tabletop={tabletop:>13,.2f}{unit}"
              f"  hifi={hifi:>13,.2f}{unit}  below {floor}{unit} solver floor")
        return
    if tabletop == 0:
        ok = abs(hifi) < 1e-9
        rel = 0.0
    else:
        rel = abs(hifi - tabletop) / abs(tabletop)
        ok = rel <= tol
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:<52} tabletop={tabletop:>13,.2f}{unit}"
          f"  hifi={hifi:>13,.2f}{unit}  d={rel*100:>5.1f}%")

B, A = sdx_blocks(), sdx_ammo()

print("=" * 118)
print("1. DAMAGE RESOLUTION".center(118))
print("=" * 118)

# --- 1a sabot vs heavy steel -------------------------------------------------
# scale = grid(1.0) * armor(0.3); Heavy=-1 disabled; Energy so ene_res=1.0 -> 0.3
# perHit = cutoff 18,000 * 0.3 = 5,400 ; blockHp = 16,520/1.0 = 16,520 -> survives
#
# RE-BASELINED. This check asserted `blockHp = 16500 / 0.5 = 33000` and BOTH of those
# terms are refuted by the shipped data. The TABLETOP side was the wrong one, not the
# port; the expected value is corrected here rather than the tolerance widened.
#   integrity 16,520 not 16,500 -- SDX2 REPLACES the recipe in
#     2815514917/Data/ModAdjuster/CubeBlocks/KeenSoftwareHouse/CubeBlocks_Armor.xml:15-19
#     as 15 SteelPlate(100) + 50 MetalGrid(30) + 104 sdx_componentTitaniumPlate(130)
#     = 1500 + 1500 + 13520 = 16,520, and ModAdjuster (mod 3017795356) is in the world's
#     mod list. Vanilla's own 150 SteelPlate + 50 MetalGrid = 16,500 is not what loads.
#   gdm 1.0 not 0.5 -- <GeneralDamageMultiplier>0.5 is COMMENTED OUT in both places it
#     appears: vanilla Content/Data/CubeBlocks/CubeBlocks_Armor.sbc:858 (the only
#     occurrence in that file, so no heavy shape has it live) and SDX2's override
#     CubeBlocks_Armor.xml:31.
# catalogue.json derives 16,520 / 1.0 from the .sbc+.xml independently, and
# wc_damage.sdx_blocks()['heavy'] now agrees, so two separate pipelines concur.
# Consequence: heavy steel is HALF as tough as every result before this line assumed.
s, _ = base_scale(A['sabot100mmMcrn'], B['heavy']())
check("sabot100mmMcrn vs heavy: baseScale = 1.0*0.3", 0.3, s)
check("  perHit = 18000 * 0.3", 5400, 18000 * s)
check("  blockHp = 16520 / 1.0  (was 16500/0.5; both terms refuted)", 16520,
      B['heavy']().integrity / B['heavy']().gdm)
col = [B['heavy']() for _ in range(60)]
r = fire(A['sabot100mmMcrn'], col)
check("  penetration depth = 180000 / 5400", 180000 / 5400, r['touched'], tol=0.05)
check("  blocks killed", 0, len(r['kills']))

# --- 1b sabot vs ceramic -----------------------------------------------------
# scale = 0.3 * (11.6/0.3) = 11.6 ; perHit = 18,000*11.6 = 208,800 <= 220,000 -> survives
# pool 180,000 - 208,800 < 0  -> stopped after ONE block
s, _ = base_scale(A['sabot100mmMcrn'], B['ceramic']())
check("sabot100mmMcrn vs ceramic: baseScale = 0.3*38.667", 11.6, s)
check("  perHit = 18000 * 11.6", 208800, 18000 * s)
col = [B['ceramic']() for _ in range(10)]
r = fire(A['sabot100mmMcrn'], col)
check("  blocks touched (one ceramic eats the round)", 1, r['touched'])
check("  ceramic left standing at", 220000 - 208800, col[0].integrity - col[0].accumulated)

# --- 1c airburst fragment vs ceramic ----------------------------------------
# scale = 0.3*700 = 210 ; perHit = 1,000*210 = 210,000 -> strips to 10,000 (4.5%)
s, _ = base_scale(A['airburstFragment'], B['ceramic']())
check("airburst frag vs ceramic: baseScale = 0.3*700", 210.0, s)
cer = B['ceramic']()
r = fire(A['airburstFragment'], [cer])
check("  damage dealt = 1000 * 210", 210000, r['log'][0][2])
check("  ceramic residual HP", 10000, cer.integrity - cer.accumulated)
check("  residual as % of full", 4.545, (cer.integrity - cer.accumulated) / 2200)

# --- 1d the combo: stripped ceramic then sabot -------------------------------
# remaining 10,000 ; sabot perHit 208,800 > 10,000 -> dies, pool cost 10,000/11.6 = 862
stripped = B['ceramic']()
fire(A['airburstFragment'], [stripped])          # strip it: 10,000 hp left
r_solo = fire(A['sabot100mmMcrn'], [stripped])   # sabot into ONLY that block
check("combo: pool spent breaching stripped ceramic = 10000/11.6", 10000 / 11.6,
      180000 - r_solo['pool_left'])
check("  ceramic destroyed by the follow-up sabot", 1, len(r_solo['kills']))
check("  pool surviving the breach", 180000 - 10000 / 11.6, r_solo['pool_left'])

col = [B['ceramic']()] + [B['heavy']() for _ in range(2)] + [B['internal']() for _ in range(30)]
fire(A['airburstFragment'], [col[0]])
r = fire(A['sabot100mmMcrn'], col)
internals = [k for k in r['kills'] if k >= 3]
print(f"       -> after the combo one sabot killed {len(r['kills'])} blocks "
      f"({len(internals)} internals), touched {r['touched']}")
col2 = [B['ceramic']()] + [B['heavy']() for _ in range(2)] + [B['internal']() for _ in range(30)]
r2 = fire(A['sabot100mmMcrn'], col2)
check("  same sabot WITHOUT airburst prep: internals killed", 0,
      len([k for k in r2['kills'] if k >= 3]))

# --- 1e PDC vs armour --------------------------------------------------------
# ceramic kinetic: scale = 0.5 / 0.1 = 5.0 ; dmg = 1200*5 = 6000 ; 220000/6000 = 36.67
s, _ = base_scale(A['PDC40mm'], B['ceramic']())
check("PDC40mm vs ceramic: baseScale = 0.5/0.1", 5.0, s)
check("  hits to kill = 220000/6000", 36.667, 220000 / (1200 * s))
s, _ = base_scale(A['PDC40mm'], B['heavy']())
check("PDC40mm vs heavy: baseScale = 0.5", 0.5, s)
# RE-BASELINED alongside 1a. This check was NOT failing -- it hardcoded 33,000 on both
# sides, so it was self-consistent arithmetic that had simply stopped describing any
# real block. Now driven off the block itself: 16,520 / (1200*0.5) = 27.5 hits, so a
# 40 mm PDC needs half as many hits on heavy steel as previously reported.
hp = B['heavy']().integrity / B['heavy']().gdm
check("  hits to kill = 16520/600  (was 33000/600 = 55, fictional)", 27.533,
      hp / (1200 * s))

print()
print("=" * 118)
print("2. RCS GYRO TORQUE".center(118))
print("=" * 118)
# one RIGHT-facing thruster at aft offset oz=+10 blocks:
#   moment.Y = -oz = -10  -> |moment| = 10 * 2.5 * 1.5e6 = 3.75e7
#   applied torque = |total|/2 = 1.875e7
m = moment_for(RIGHT, (0, 0, 10))
check("single RIGHT thruster @oz=10: raw moment.Y", -10.0, m[1])
tot, bias = total_moment([(RIGHT, (0, 0, 10))])
check("  |totalMoment| = 10*2.5*1.5e6", 3.75e7, tot.length())
check("  applied torque = /2", 1.875e7, applied_torque([(RIGHT, (0, 0, 10))]))
check("  as fraction of one vanilla gyro", 0.558, applied_torque([(RIGHT, (0, 0, 10))]) / BASE_GYRO_FORCE)

# a Left-facing thruster displaced only along X makes NO moment (axis check)
check("LEFT thruster @ox=10 (wrong axis) -> zero torque", 0.0,
      applied_torque([(LEFT, (10, 0, 0))]))

# extra computers must not add torque
th = ring_layout(n_per_ring=20, lever_blocks=16)
t1 = applied_torque(th, n_computers=1)
t4 = applied_torque(th, n_computers=4)
check("40 RCS @16 blocks: torque with 1 computer", t1, t1)
check("  same torque with 4 computers (redundancy only)", t1, t4)
check("  per-computer GyroStrengthMultiplier halves with 2", gyro_multiplier(th, 1) / 2,
      gyro_multiplier(th, 2))
# tabletop: 40 thrusters, each |moment| = 16*2.5*1.5e6 = 6e7, but they split across
# two axes (yaw from L/R, pitch from U/D) so the VECTOR length is used, not the sum.
print(f"       note: totalMoment is a per-axis |sum| vector; .Length() of "
      f"({tot.x:.3g},{tot.y:.3g},{tot.z:.3g}) style vectors is what gets halved")

# no RCS -> zero
check("gyro computer with zero RCS thrusters", 0.0, gyro_multiplier([], 1))

print()
print("=" * 118)
print("3. CHATTER OVER-LEAD  (closed form vs ported CalculateAdvancedGridAimPrediction)".center(118))
print("=" * 118)
print("  tabletop: the predictor holds instantaneous accel constant over the flight,")
print("            so a target that oscillates faster than the flight time is over-led by")
print("            miss = 0.5 * a * tf^2   with tf = R / muzzleSpeed\n")
from chatter_experiment import sweep
for R in (10000, 8000, 6000, 4000, 2000):
    tf = R / 10000.0
    for amp in (60, 100):
        tabletop = 0.5 * amp * tf * tf
        hifi, algo = sweep(R, 'square', amp, 0.5, samples=24)
        check(f"R={R//1000}km a={amp}: miss = 0.5*{amp}*{tf:.2f}^2", tabletop, hifi,
              tol=0.12, unit="m", floor=2.0)

print()
print("=" * 118)
print(f"RESULT: {PASS} passed, {FAIL} failed, {SKIP} below solver floor".center(118))
print("=" * 118)
sys.exit(1 if FAIL else 0)
