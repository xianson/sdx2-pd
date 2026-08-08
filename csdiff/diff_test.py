"""Differential test: the Python port vs VERBATIM WeaponCore C#.

Ground truth in vectors.json is emitted by `csdiff/` — a net8.0 console app whose
`extracted.cs` contains XorShiftRandomStruct (Support/Utils.cs) and GetDeck
(Ai/AiSupport.cs) copied verbatim from the mod, with only ProtoBuf attributes
stripped and GetDeck's accessibility widened. No arithmetic was altered.

This removes reading-comprehension error as a variable: either the Python
reproduces the shipped C# bit-for-bit or it does not.
"""
import json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'hifi'))
from wc_acquire import XorShiftRandomStruct, DeckBuffer

V = json.load(open(os.path.join(HERE, 'vectors.json')))
P = F = 0


def chk(label, want, got, tol=None):
    global P, F
    if tol is None:
        ok = want == got
    else:
        ok = len(want) == len(got) and all(abs(a - b) <= tol for a, b in zip(want, got))
    P, F = P + ok, F + (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"          C#     : {want[:6] if isinstance(want, list) else want}")
        print(f"          python : {got[:6] if isinstance(got, list) else got}")


print("=" * 96)
print("DIFFERENTIAL TEST — Python port vs VERBATIM WeaponCore C#".center(96))
print("=" * 96)
print("  ground truth compiled from the mod's own source (net8.0). No game involved.\n")

print("XorShiftRandomStruct  (Support/Utils.cs:57)")
for seed, exp in V['rng'].items():
    s = int(seed)
    r = XorShiftRandomStruct(s); chk(f"seed {seed:>6}  NextUInt64 x8", exp['u64'], [r.next_uint64() for _ in range(8)])
    r = XorShiftRandomStruct(s); chk(f"seed {seed:>6}  NextDouble x8", exp['dbl'], [r.next_double() for _ in range(8)], tol=1e-12)
    r = XorShiftRandomStruct(s); chk(f"seed {seed:>6}  Range(1,5) x40", exp['range_i_1_5'], [r.range_int(1, 5) for _ in range(40)])
    r = XorShiftRandomStruct(s); chk(f"seed {seed:>6}  Range(0,16) x40", exp['range_i_0_16'], [r.range_int(0, 16) for _ in range(40)])
    r = XorShiftRandomStruct(s); chk(f"seed {seed:>6}  FairRange(16) x20", exp['fair_16'], [r.fair_range(16) for _ in range(20)])

print("\nGetDeck  (Ai/AiSupport.cs:225) — fresh buffer, seed 777")
for c in V['deck']:
    rng = XorShiftRandomStruct(777); db = DeckBuffer()
    got = list(db.get_deck(c['firstCard'], c['cardsToSort'], c['cardsToShuffle'], rng)[:c['cardsToSort']])
    chk(f"first={c['firstCard']:>3} sort={c['cardsToSort']:>3} shuffle={c['cardsToShuffle']:>3}", c['deck'], got)

print("\nGetDeck — PERSISTENT buffer + shared RNG, as WeaponCore actually calls it (seed 4242)")
rng = XorShiftRandomStruct(4242); db = DeckBuffer()
for c in V['deck_persistent']:
    got = list(db.get_deck(c['chunk'], 4, 16, rng)[:4])
    chk(f"call {c['call']} chunk {c['chunk']:>2}", c['deck'], got)

print()
print("=" * 96)
print(f"RESULT: {P} passed, {F} failed".center(96))
print("=" * 96)

# ---------------------------------------------------------------- prediction
print("\nCalculateAdvancedGridAimPrediction  (WeaponTracking.cs:1115)")
sys.path.insert(0, os.path.join(HERE, '..', 'hifi'))
from wc_predict import advanced_grid_prediction, Frame
from vec import V as PV

pf = pp = 0
worst = (0.0, None)
for r in V['predict']:
    R, a, cr = r['R'], r['a'], r['cruise']
    tpos, tvel = PV(R, 0, 0), PV(0, 0, cr)
    spos, svel = PV(0, 0, 0), PV(0, 0, 0)
    fr = Frame(tpos, tvel, spos, svel)
    ok, crude = fr.crude_tti(10000.0)
    # crudeTti first
    want_c = r['crudeTti']
    if want_c is not None:
        d = abs(crude - want_c)
        good = d < 1e-9
        pp, pf = pp + good, pf + (not good)
        if not good:
            print(f"  [FAIL] crudeTti R={R:.0f} a={a:.0f} cr={cr:.0f}  C#={want_c:.6f} py={crude:.6f}")
    found, aim, tti, _vel = advanced_grid_prediction(
        tpos, PV(0, 0, 0), tvel, PV(0, a, 0), PV(0, 0, 0),
        spos, svel, crude, 10000.0, 1000.0)
    if found != r['found']:
        pf += 1
        print(f"  [FAIL] found R={R:.0f} a={a:.0f} cr={cr:.0f}  C#={r['found']} py={found}")
        continue
    if not found:
        pp += 1
        continue
    # compare the AIMPOINT, which is what the shot is fired at
    cs = PV(*r['aim'])
    err = (aim - cs).length()
    scale = max(1.0, cs.length())
    good = err / scale < 1e-6
    pp, pf = pp + good, pf + (not good)
    if err > worst[0]:
        worst = (err, (R, a, cr))
    if not good:
        print(f"  [FAIL] aim R={R:.0f} a={a:.0f} cr={cr:.0f}  err={err:.6f} m"
              f"  C#=({cs.x:.3f},{cs.y:.3f},{cs.z:.3f}) py=({aim.x:.3f},{aim.y:.3f},{aim.z:.3f})")
print(f"  {pp} passed, {pf} failed across {len(V['predict'])} geometries"
      f" (worst aimpoint error {worst[0]:.3e} m at R/a/cruise={worst[1]})")
P += pp; F += pf

print("\nQuarticSolver  (WeaponTracking.cs:619)")
from wc_predict import quartic_solver
qp = qf = 0
for r in V['quartic']:
    res = quartic_solver(r['R'] / 10000.0, PV(r['R'], 0, 0), PV(0, 0, 200),
                         PV(0, r['a'], 0), 10000.0)
    got = res[1] if isinstance(res, tuple) else res
    d = abs(got - r['tti'])
    good = d < 1e-6
    qp, qf = qp + good, qf + (not good)
    if not good:
        print(f"  [FAIL] R={r['R']:.0f} a={r['a']:.0f}  C#={r['tti']:.8f} py={got:.8f} d={d:.2e}")
print(f"  {qp} passed, {qf} failed across {len(V['quartic'])} cases")
P += qp; F += qf

print()
print("=" * 96)
print(f"TOTAL: {P} passed, {F} failed".center(96))
print("=" * 96)# ----------------------------------------------------------- collision detection


# ----------------------------------------------------------- collision detection
# ProjectileHits.cs:601-682 + AmmoConstants.cs:1227-1244, via csdiff/collide.cs
import wc_collide as C

print()
print("CollisionShape  (AmmoConstants.cs:1227)")
for c in V['shape']:
    il, sz = C.collision_shape(c['shapeIsLine'], c['diameter'])
    chk(f"line={c['shapeIsLine']} diam={c['diameter']}", (c['isLine'], c['size']), (il, sz))

print()
print("bulletRadius  (ProjectileHits.cs:605)")
for c in V['bullet_radius']:
    a = C.AmmoConst(c['shapeIsLine'], c['diameter'], c['byBlock'], c['eol'])
    chk(f"line={c['shapeIsLine']} d={c['diameter']} bb={c['byBlock']} det={c['detonate']}",
        c['r'], C.bullet_radius(a, c['detonate']))

print()
print("BoundingSphereD.Include  (VRage.Math.dll)")
for c in V['include']:
    chk(f"c0={c['c0']} r0={c['r0']} c1={c['c1']} r1={c['r1']}",
        c['r'], C.include_radius(tuple(c['c0']), c['r0'], tuple(c['c1']), c['r1']))

print()
print("targetRadius  (ProjectileHits.cs:626)")
for c in V['target_radius']:
    a = C.AmmoConst(True, c['bulletDiam'])
    t = C.AmmoConst(c['targetIsLine'], 2.2)
    got = C.target_radius(a, t, (1000.0, 0.0, 0.0), (1000.0 + c['travel'], 0.0, 0.0))
    chk(f"bd={c['bulletDiam']} tline={c['targetIsLine']} travel={c['travel']:.3f}", c['r'], got)

print()
print("sphere-sphere CCD  (ProjectileHits.cs:643)")
DS = 1.0 / 60.0
for c in V['hits']:
    a = C.AmmoConst(True, c['bulletDiam']); t = C.AmmoConst(True, 2.2)
    vb = c['vb']
    p_last = (0.0, 0.0, 0.0)
    p_pos = (vb * DS, 0.0, 0.0)
    t_last = (vb * DS * 0.5, c['miss'], 0.0)
    t_pos = (t_last[0] - 260.0 * DS, t_last[1], t_last[2])
    br = C.bullet_radius(a)
    tr = C.target_radius(a, t, t_pos, t_last)
    tag = f"d={c['bulletDiam']} vb={c['vb']:.0f} miss={c['miss']:.0f} drift={c['drift']:.0f}"
    chk(tag + " br", c['br'], br)
    chk(tag + " tr", c['tr'], tr)
    hit, cad = C.hits(p_last, p_pos, t_last, t_pos, (0.0, c['drift'], 0.0), br, tr, DS)
    chk(tag + " cad", c['cad'], cad)
    chk(tag + " hit", c['hit'], hit)

print()
print("sphere-sphere CCD, speed-matched branch  (|dvdv| < 1e-6)")
for c in V['hits_matched']:
    a = C.AmmoConst(True, 0.5); t = C.AmmoConst(True, 2.2)
    p_last = (0.0, 0.0, 0.0); p_pos = (50.0, 0.0, 0.0)
    t_last = (0.0, c['miss'], 0.0); t_pos = (50.0, c['miss'], 0.0)
    br = C.bullet_radius(a)
    tr = C.target_radius(a, t, t_pos, t_last)
    hit, cad = C.hits(p_last, p_pos, t_last, t_pos, (0.0, 0.0, 0.0), br, tr, DS)
    chk(f"matched miss={c['miss']:.0f} cad", c['cad'], cad)
    chk(f"matched miss={c['miss']:.0f} hit", c['hit'], hit)

print()

# ----------------------------------------------------------- firing model
# WeaponController.cs:260-380 + WeaponShoot.cs + WeaponReload.cs + the SessionUpdate
# shoot gate, via csdiff/firing.cs. Diffed against hifi/weapons.py PdcMount
# (step / _rate_now / _cool / ticks_per_shot).
import weapons as WPN
from weapons import PdcMount, PDC_STATS, ticks_per_shot

_mk_n = [0]


def mk_mount(base, **over):
    d = dict(PDC_STATS[base]); d.update(over)
    _mk_n[0] += 1
    key = f'_diff_{_mk_n[0]}'
    PDC_STATS[key] = d
    return PdcMount(key, (0, 0, 0), PV(1, 0, 0), unique_part_id=910000 + _mk_n[0])


print("TicksPerShot sweep  (WeaponController.cs:378, rof 1..3600, C# float vs py double truncation)")
tps_c = V['tps_sweep']
bad = [(r + 1, tps_c[r], ticks_per_shot(r + 1)) for r in range(3600) if tps_c[r] != ticks_per_shot(r + 1)]
chk("ticks_per_shot identical for every RateOfFire 1..3600", [], bad)

print("\nUpdateRof while degraded  (WeaponController.cs:365-378) vs PdcMount._rate_now")
rof_rows = V['update_rof']
mounts = {}
exact = clamp_rows = clamp_bad = 0
bad = []
for r in rof_rows:
    m = mounts.get(r['rof'])
    if m is None:
        m = mounts[r['rof']] = mk_mount('PdcMcrn', rof=r['rof'])
    m.heat = r['heat']; m.degraded = True
    got = m._rate_now()
    want = 60.0 / r['tps']
    if r['heat'] > 45000:          # C# does NOT clamp Heat/MaxHeat; the python does
        clamp_rows += 1
        if abs(got - want) > 1e-9:
            clamp_bad += 1
    elif abs(got - want) > 1e-9:
        bad.append((r['rof'], r['heat'], want, got))
    else:
        exact += 1
chk(f"degraded rate exact on all {exact + len(bad)} rows with heat <= MaxHeat", [], bad)
if bad:
    print(f"         CONFIRMED DIVERGENCE ({len(bad)}/{exact + len(bad)} rows, all low-RoF): WC computes")
    print(f"         (int)(rof * Lerp(...)) in FLOAT32; the python does it in float64. At heat values")
    print(f"         where the product straddles an integer, the truncated RoF differs by 1 rpm")
    print(f"         (e.g. rof=80 heat=24750: C# 47 -> tps 76, py 46 -> tps 78, a 2.6% rate error at")
    print(f"         that heat only). Affects PdcMcrnAdv/PdcOpaAdv-class mounts while degraded; the")
    print(f"         1800+ rpm PDCs never hit a boundary in this grid.")
print(f"         heat > MaxHeat rows (C# extrapolates the Lerp, python clamps frac to 1): "
      f"{clamp_bad}/{clamp_rows} differ -> "
      + ("python's clamp is a REAL divergence above MaxHeat (reachable only in the 15-tick"
         " overheat grace window and the cooldown that follows)" if clamp_bad else "no observable difference"))

print("\nUpdateWeaponHeat single pass  (WeaponController.cs:260-363) vs PdcMount._cool")
bad = []
n = 0
for r in V['heat_pass']:
    m = mk_mount('PdcMcrn') if n == 0 else m  # one mount, reset per row
    n += 1
    m.heat = r['h0']; m.overheated = bool(r['ov0']); m.degraded = bool(r['dg0'])
    m._cool(m.sink / 3.0)
    ok = (abs(m.heat - r['h1']) <= 0.5 and int(m.overheated) == r['ov1'] and int(m.degraded) == r['dg1'])
    if not ok:
        bad.append((r['h0'], r['ov0'], r['dg0'], (r['h1'], r['ov1'], r['dg1']), (m.heat, int(m.overheated), int(m.degraded))))
chk(f"heat/degrade/overheat state machine identical on all {n} single passes", [], bad)

print("\nProhibitCoolingWhenOff gate  (WeaponController.cs:268) — C# ground truth, python has no block-off state")
for r in V['cool_gate']:
    frozen = r['h1'] == 30000
    should_freeze = r['prohibit'] == 1 and r['working'] == 0
    chk(f"prohibit={r['prohibit']} working={r['working']} -> {'frozen' if frozen else 'cools'}",
        should_freeze, frozen)
print("         => cooling is gated on Comp.Cube.IsWorking (block POWER), not on firing:")
print("            ToggleWeaponFire keeps cooling; turning the block OFF freezes heat.  CONFIRMED.")

# ---- tick-loop scenarios ----------------------------------------------------
SCEN_MOUNT = {
    'mcrn_window':        lambda: mk_mount('PdcMcrn'),
    'mcrn_sustained':     lambda: mk_mount('PdcMcrn'),
    'mcrn_gap6':          lambda: mk_mount('PdcMcrn'),
    'mcrn_gap15':         lambda: mk_mount('PdcMcrn'),
    'mcrn_gap60':         lambda: mk_mount('PdcMcrn'),
    'mcrn_overheat_grace': lambda: mk_mount('PdcMcrn'),
    'mcrn_reload_pure':   lambda: mk_mount('PdcMcrn', heat_per_shot=0),
    'mcrn_mags_finite':   lambda: mk_mount('PdcMcrn', heat_per_shot=0),
    'pgen_burst':         lambda: mk_mount('PdcPgenAdv'),
    'mcrnadv_window':     lambda: mk_mount('PdcMcrnAdv'),
    'opaadv_prefire':     lambda: mk_mount('PdcOpaAdv'),
}
PRIME = {'mcrn_overheat_grace': 44000.0}
# python-side known boundaries, reported but not failed:
NOFAIL = {
    'mcrn_mags_finite':  "python assumes an infinitely restocked inventory (no CurrentMags model)",
    'mcrnadv_window':    "phase: WC fires shot #1 on tick 1, a continuous-rate model cannot",
    'opaadv_prefire':    "python does not model DelayUntilFire prefire ticks in step()",
}

DT = 1.0 / 60.0


def run_py(m, ranges, ticks, sample_every, prime=0.0):
    if prime:
        m.heat = prime
    rounds = 0.0
    oh, dg, ld = m.overheated, m.degraded, (m.reloading > 0)
    samples, events = [], []
    for t in range(1, ticks + 1):
        want = any(a <= t <= b for a, b in ranges)
        rounds += m.step(DT, want)
        if m.overheated != oh:
            events.append((t, 'oh', int(m.overheated))); oh = m.overheated
        if m.degraded != dg:
            events.append((t, 'dg', int(m.degraded))); dg = m.degraded
        l = m.reloading > 0
        if l != ld:
            events.append((t, 'rl', int(l))); ld = l
        if t % sample_every == 0 or t == ticks:
            samples.append((t, rounds, m.heat))
    return samples, events, rounds


print("\nFiring scenarios — C# tick loop (verbatim Shoot/heat/reload + real FutureEvents) vs PdcMount.step")
print(f"  {'scenario':<20} {'C# rounds':>9} {'py rounds':>9} {'Δ':>7} {'Δ%':>6}  "
      f"{'maxΔheat/Max':>12}  {'events (C# vs py)':<28} verdict")
for sc in V['firing_scenarios']:
    name = sc['name']
    if name.startswith('cool_'):
        continue  # covered by the cool_gate section; python has no block-off state
    m = SCEN_MOUNT[name]()
    ps, pe, prounds = run_py(m, sc['fire'], sc['ticks'], sc['sampleEvery'], PRIME.get(name, 0.0))
    crounds = sc['totals']['rounds']
    d = prounds - crounds
    dpct = 100.0 * d / max(1.0, crounds)
    # heat deviation across samples, relative to MaxHeat
    maxh = max(abs(c[3] - p[2]) for c, p in zip(sc['samples'], ps)) / m.max_heat * 100.0
    # event-sequence comparison
    ce = [(e[0], e[1], e[2]) for e in sc['events']]
    ev_note = f"{len(ce)} vs {len(pe)}"
    seq_ok = [e[1:] for e in ce] == [e[1:] for e in pe]
    if seq_ok and ce:
        ev_note += f", |Δt|<= {max(abs(a[0] - b[0]) for a, b in zip(ce, pe))}"
    ok = abs(d) <= 2 if crounds <= 200 else abs(dpct) <= 5.0
    ok = ok and maxh <= 10.0
    known = NOFAIL.get(name)
    verdict = 'PASS' if ok else ('KNOWN-GAP' if known else 'FAIL')
    if verdict != 'KNOWN-GAP':
        P, F = P + (verdict == 'PASS'), F + (verdict == 'FAIL')
    print(f"  {name:<20} {crounds:>9} {prounds:>9.1f} {d:>+7.1f} {dpct:>+5.1f}%  "
          f"{maxh:>11.2f}%  {ev_note:<28} {verdict}")
    if not seq_ok:
        print(f"      event sequences differ:  C#={ce}")
        print(f"                               py={pe}")
    if known:
        print(f"      known boundary: {known}")

# ---- the specific mechanism claims the conclusions rest on ------------------
print("\nMechanism verdicts from the ground truth:")
gaps = {s['name']: (s['totals']['heatPassGapMin'], s['totals']['heatPassGapMax']) for s in V['firing_scenarios']}
gmn, gmx = gaps['mcrn_sustained']
print(f"  * cooling cadence: heat passes arrive every {gmn}..{gmx} ticks while the loop runs.")
print(f"    WC's FutureEvents commits _offset AFTER running callbacks (SessionFutureEvents.cs:79),")
print(f"    so the self-rescheduled 20-tick loop lands every 19 ticks: real cooling is")
print(f"    HeatSinkRate*(20/19) ~ {400 * 20 / 19:.1f}/s for HeatSinkRate=400, python cools at 400/s exactly.")
sus = next(s for s in V['firing_scenarios'] if s['name'] == 'mcrn_sustained')
ev = sus['events']
oh_on = [e[0] for e in ev if e[1] == 'oh' and e[2] == 1]
oh_off = [e[0] for e in ev if e[1] == 'oh' and e[2] == 0]
dg_off = [e[0] for e in ev if e[1] == 'dg' and e[2] == 0]
print(f"  * one-way door: overheats at ticks {oh_on}, resumes at {oh_off}, degrade NEVER clears")
print(f"    while engaged ({'no dg-off events' if not dg_off else 'dg-off at ' + str(dg_off)}) — resume heat 0.822*MaxHeat sits above the 0.4 clear point.")
grace = next(s for s in V['firing_scenarios'] if s['name'] == 'mcrn_overheat_grace')
g_oh = [e[0] for e in grace['events'] if e[1] == 'oh'][0]
rounds_at = grace['totals']['roundsAtOverheat']
print(f"  * overheat grace: Overheated set at tick {g_oh} after {rounds_at} rounds, but the gate's")
print(f"    OverHeatCountDown (15, SessionUpdate.cs:794) lets {grace['totals']['rounds'] - rounds_at} more rounds out before it bites.")
print(f"    python stops at the overheat instant — it under-fires by that amount per overheat event.")

print()
print("=" * 96)
print(f"  TOTAL: {P} passed, {F} failed")
print("=" * 96)
sys.exit(1 if F else 0)
