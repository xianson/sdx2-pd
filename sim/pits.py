"""Recessed-pit PDC arcs: do artificially constrained firing arcs help?

MECHANISM. A pit is modelled as an ARC restriction, not lattice geometry: each
mount keeps its stock position, normal and own-hull occlusion, and gets an extra
"visible cone" predicate intersected with the stock `bears()` -- axis + half-angle.
The override is a per-instance attribute (`m.bears = closure`), which shadows the
class method at the ONLY call site that gates eligibility (targeting.valid:109).
Nothing in weapons.py / targeting.py / fleet_efficiency.py is modified.

Physics reading: the pit axis is the direction the recess is dug toward (a canted
pit points its cone off the surface normal); the half-angle is set by pit depth --
deeper pit = narrower cone. `occluded()` still runs with the stock normal, so a
pit can never see through the hull; the cone can only SUBTRACT sky.

`run_arcs` is a verbatim mirror of fleet_efficiency.run plus an `arcs(fleet)` hook
applied after build+reset and before the first wave. verify() asserts it reproduces
fleet_efficiency.run bit-for-bit when arcs=None, and that a pit override actually
changes bears() behaviour.
"""
import math, random, sys, time
import weapons
from vec import V
from ship import Ship
from shipyard import build_ship
from hull2 import GRID
from weapons import PdcMount, PDC_ALIAS
from torpedo2 import Torpedo2
import fleet_efficiency
from fleet_efficiency import wave, class_speed_mps
import ladder

SEEDS = list(range(701, 725))
THREAT = V(1.0, 0.0, 0.0)          # hull-local threat axis (ships never rotate)


# ------------------------------------------------------------------ run + hook
def run_arcs(n_ships=1, mounts_per=8, kind='PdcMcrn', salvo=16, waves=1,
             torp_kind='Plasma220mmTorp', spacing=500.0, seed=1, engage_all=True,
             cls='Corvette', perfect=False, wave_gap=0.0, launcher_speed=0.0,
             policy=None, assign=None, launch_delays=None, arcs=None):
    """fleet_efficiency.run with an `arcs(fleet)` hook. Verbatim otherwise."""
    weapons.reset_part_ids()
    Torpedo2.reset_ids()
    weapons.Torpedo.reset_ids()
    rnd = random.Random(seed)
    fleet = []
    for s in range(n_ships):
        hull, man, mounts = build_ship(cls, pdc_mix={PDC_ALIAS[kind]: mounts_per},
                                       n_rcs=200, seed=seed + s)
        sh = Ship(hull, V(0, s * spacing, 0), V(0, 0, 0), class_speed_mps(cls),
                  drive_thrust=292e6 * 2)
        for m in mounts:
            m.reset()
        fleet.append((sh, hull, mounts))

    if arcs is not None:
        arcs(fleet)

    total_mounts = sum(len(f[2]) for f in fleet)
    tot_leak = tot_kill = tot_eng = tot_ticks = 0
    waste = {}
    per_wave = []
    for w in range(waves):
        lk, kl, eng, tk, wst = wave(fleet, salvo, torp_kind, rnd, spacing,
                                    policy=policy, assign=assign,
                                    launch_delays=launch_delays,
                                    engage_all=engage_all, perfect=perfect,
                                    launcher_speed=launcher_speed)
        if wave_gap:
            for f in fleet:
                for m in f[2]:
                    for _ in range(int(wave_gap * 60)):
                        m.step(1.0 / 60.0, False)
        tot_leak += lk; tot_kill += kl; tot_eng += eng; tot_ticks += tk
        for k in ('fired', 'wasted', 'missed', 'inflight', 'dup', 'total',
                  'hits', 'useful', 'overkill', 'off_ticks',
                  'dup_assign', 'engaged', 'multi_engaged', 'engager_mounts'):
            waste[k] = waste.get(k, 0.0) + wst[k]
        hot = max((m.heat / m.max_heat for f in fleet for m in f[2]), default=0)
        per_wave.append((lk, kl, hot))
    W = waste.get
    fired = max(1, W('fired', 0))
    return dict(leakers=tot_leak, kills=tot_kill,
                fired_rounds=W('fired', 0),
                dead_pct=100.0 * W('wasted', 0) / fired,
                miss_pct=100.0 * W('missed', 0) / fired,
                mounts=total_mounts, per_wave=per_wave)


# ---------------------------------------------------------------- pit builders
def set_pit(m, axis, half_deg):
    """Recess `m` into a pit whose visible cone is `half_deg` about `axis`.
    Intersected with the stock mechanical arc; occlusion untouched."""
    ax = axis.normalized()
    cos_h = math.cos(math.radians(half_deg))
    stock = PdcMount.bears

    def bears(dir_local, _m=m, _ax=ax, _c=cos_h, _stock=stock):
        d = dir_local.normalized()
        if _ax.dot(d) < _c:
            return False
        return _stock(_m, d)
    m.bears = bears
    m._pit = (ax, half_deg)


def set_blind(m):
    """Delete a mount for the honest fewer-mounts control (arcs untouched
    elsewhere; the block still exists so hull/occlusion stay identical)."""
    m.bears = lambda dir_local: False
    m._pit = None


def transverse(j, n, phase=0.0):
    """j-th of n unit vectors tiling the plane transverse to THREAT (+X)."""
    b = 2.0 * math.pi * j / n + phase
    return V(0.0, math.cos(b), math.sin(b))


def cant(delta_deg, j, n, phase=0.0):
    """Pit axis canted `delta_deg` off the threat axis toward transverse slot j."""
    d = math.radians(delta_deg)
    t = transverse(j, n, phase)
    return (THREAT * math.cos(d) + t * math.sin(d)).normalized()


# Ring geometry: mount idx i has normal at 45*i deg in the X-Y plane. Mounts 4
# (180 deg) and 5 (225 deg) never fire on the stock hull (own-hull occlusion).
EFFECTIVE = (0, 1, 2, 3, 6, 7)


def arcs_stock(fleet):
    pass


def arcs_iris(psi):
    """All pits dug toward the threat axis, half-angle psi (pit-depth sweep)."""
    def f(fleet):
        for sh, hull, ms in fleet:
            for m in ms:
                set_pit(m, THREAT, psi)
    return f


def arcs_radial(psi):
    """Each mount recessed straight down where it sits: cone about own normal."""
    def f(fleet):
        for sh, hull, ms in fleet:
            for m in ms:
                set_pit(m, m.normal, psi)
    return f


def arcs_fan(delta, psi, phase=0.0, mounts=EFFECTIVE):
    """Six pits tiling the transverse azimuth about the threat axis, each canted
    `delta` off-axis with half-angle `psi`. Sector width/overlap sweep:
    adjacent axes are 2*asin(sin(delta)*sin(pi/6)) apart, so psi below ~half of
    that is disjoint, psi ~ delta is heavy overlap (all cover the axis)."""
    def f(fleet):
        for sh, hull, ms in fleet:
            for j, i in enumerate(mounts):
                set_pit(ms[i], cant(delta, j, len(mounts), phase), psi)
    return f


def arcs_sweepers(n_sweep, delta, psi):
    """`n_sweep` wide-open sweepers + the rest narrow fan specialists."""
    def f(fleet):
        for sh, hull, ms in fleet:
            spec = [i for i in EFFECTIVE[n_sweep:]]
            for j, i in enumerate(spec):
                set_pit(ms[i], cant(delta, j, len(spec)), psi)
    return f


def arcs_kmount(k):
    """Honest control: k open mounts, the rest deleted. Deletion order takes
    effective mounts first so the comparison is against mounts that matter."""
    keep = list(EFFECTIVE[:k]) + [4, 5][:max(0, k - len(EFFECTIVE))]

    def f(fleet):
        for sh, hull, ms in fleet:
            for i, m in enumerate(ms):
                if i not in keep:
                    set_blind(m)
    return f


def arcs_consort_aim(psi, up_threat=1500.0):
    """Per-hull iris: each hull's pits point at a spot `up_threat` m up the
    threat axis from the LEAD, so consorts cover the lead's terminal volume."""
    def f(fleet):
        lead = fleet[0][0]
        aim_world = lead.pos + V(up_threat, 0.0, 0.0)
        for sh, hull, ms in fleet:
            ax = sh.dir_to_local((aim_world - sh.pos).normalized())
            for m in ms:
                set_pit(m, ax, psi)
    return f


# ------------------------------------------------------------------ statistics
def paired_t(xs, ys):
    """t-stat of paired differences xs - ys (positive = xs worse/larger)."""
    n = len(xs)
    d = [x - y for x, y in zip(xs, ys)]
    md = sum(d) / n
    var = sum((x - md) ** 2 for x in d) / max(1, n - 1)
    sd = math.sqrt(var)
    if sd < 1e-12:
        return 0.0 if abs(md) < 1e-12 else math.copysign(99.0, md)
    return md / (sd / math.sqrt(n))


def row(label, res, ref=None):
    lk = [r['leakers'] for r in res]
    fr = [r['fired_rounds'] for r in res]
    n = len(res)
    s = f"  {label:<34}{sum(lk)/n:>8.2f}{sum(fr)/n:>9.0f}"
    if ref is not None:
        s += f"{paired_t(lk, [r['leakers'] for r in ref]):>9.2f}" \
             f"{paired_t(fr, [r['fired_rounds'] for r in ref]):>9.2f}"
    return s


def sweep(configs, scenarios, seeds, ref_key=None, dump=None):
    """configs: list of (label, arcs, policy_factory). policy_factory() -> pol
    or None. Fresh policy per run (policies keep per-mount state).

    t-stats are paired against the STOCK row under the SAME policy (labels are
    '<arc> / <pol>'), so an arc change is always measured at fixed policy."""
    out = {}
    for sc_label, kw in scenarios:
        print(f"\n== {sc_label} | seeds {seeds[0]}..{seeds[-1]} (n={len(seeds)}) ==",
              flush=True)
        print(f"  {'config':<34}{'leakers':>8}{'fired':>9}{'t_leak':>9}{'t_fired':>9}"
              f"   (t vs stock, same policy)", flush=True)
        results = {}
        for label, arcs, polf in configs:
            res = []
            for s in seeds:
                res.append(run_arcs(seed=s, arcs=arcs,
                                    policy=(polf() if polf else None), **kw))
            results[label] = res
        for label, _, _ in configs:
            pol = label.split(' / ')[-1]
            ref = results.get(f'stock / {pol}')
            print(row(label, results[label],
                      ref if not label.startswith('stock /') else None), flush=True)
        out[sc_label] = results
    if dump:
        import json
        slim = {sc: {lab: [(r['leakers'], r['fired_rounds']) for r in res]
                     for lab, res in rs.items()} for sc, rs in out.items()}
        with open(dump, 'w') as f:
            json.dump(slim, f)
        print(f"[raw per-seed results -> {dump}]", flush=True)
    return out


# ---------------------------------------------------------------- verification
def verify():
    # 1. exact reproduction of the shared run() at stock arcs
    for polf, tag in ((None, 'no PB'),
                      (lambda: ladder.burst_ladder_only(burst=14), 'burst14')):
        for seed in (701, 702):
            a = fleet_efficiency.run(1, 8, kind='PdcMcrn', salvo=24, waves=1,
                                     seed=seed, engage_all=True,
                                     policy=(polf() if polf else None))
            b = run_arcs(1, 8, kind='PdcMcrn', salvo=24, waves=1, seed=seed,
                         engage_all=True, policy=(polf() if polf else None))
            assert a['leakers'] == b['leakers'] and \
                a['fired_rounds'] == b['fired_rounds'], \
                (tag, seed, a['leakers'], b['leakers'],
                 a['fired_rounds'], b['fired_rounds'])
    print("verify: run_arcs == fleet_efficiency.run at stock arcs "
          "(2 seeds x {no PB, burst14}, leakers AND fired identical)", flush=True)

    # 2. the override actually changes bears()
    weapons.reset_part_ids()
    hull, man, mounts = build_ship('Corvette', pdc_mix={PDC_ALIAS['PdcMcrn']: 8},
                                   n_rcs=200, seed=701)
    m = mounts[0]                              # normal +X
    on_axis = V(1, 0, 0)
    off_axis = V(math.cos(math.radians(30)), math.sin(math.radians(30)), 0)
    assert m.bears(on_axis) and m.bears(off_axis)
    set_pit(m, THREAT, 20.0)
    assert m.bears(on_axis) and not m.bears(off_axis)
    # pit cannot ADD sky: point outside the stock arc stays out
    m2 = mounts[2]                             # normal +Y, stock arc theta<=130
    set_pit(m2, V(0, -1, 0), 60.0)             # cone dips past the stock horizon
    below = V(0.0, -math.cos(math.radians(35)), math.sin(math.radians(35)))
    th = math.degrees(math.acos(max(-1, min(1, m2.normal.dot(below.normalized())))))
    assert th > 130 and not m2.bears(below)
    set_blind(m2)
    assert not m2.bears(on_axis)
    print("verify: set_pit narrows bears(), intersects with stock arc, "
          "set_blind deletes", flush=True)


# -------------------------------------------------------------------- geometry
def probe():
    """Bearing spread of the threat, as seen from the lead and a consort."""
    weapons.reset_part_ids()
    Torpedo2.reset_ids()
    rnd = random.Random(701)

    class P:                                   # static stand-in for the lead
        pos = V(0, 0, 0)
    lead = P()
    axis = V(-1, 0, 0)
    torps = [Torpedo2('Plasma220mmTorp',
                      lead.pos - axis * 6000.0 + V(rnd.uniform(-80, 80),
                                                   rnd.uniform(-80, 80),
                                                   rnd.uniform(-80, 80)),
                      axis * 260.0, lead, seed=rnd.randrange(10 ** 6), index=i)
             for i in range(24)]
    consort = V(0, 500, 0)
    bands = {}                                  # range band -> (max off-axis lead, consort)
    while any(t.alive for t in torps):
        for t in torps:
            if not t.alive:
                continue
            if t.step() <= 150.0:
                t.alive = False
                continue
            d = t.pos - lead.pos
            r = d.length()
            if r > 3000:
                continue
            a = math.degrees(math.acos(max(-1, min(1, d.normalized().dot(THREAT)))))
            dc = t.pos - consort
            ac = math.degrees(math.acos(max(-1, min(1, dc.normalized().dot(THREAT)))))
            key = int(r // 500)
            cur = bands.get(key, (0.0, 0.0))
            bands[key] = (max(cur[0], a), max(cur[1], ac))
    print("range band  max off-axis (lead)  max off-axis (consort@y=500)", flush=True)
    for k in sorted(bands, reverse=True):
        print(f"  {k*500:>4}-{k*500+500:<4} m {bands[k][0]:>12.1f} deg"
              f" {bands[k][1]:>16.1f} deg", flush=True)


# -------------------------------------------------------------------- drivers
SC1 = ('1 hull, salvo 24 (3.0/mount)',
       dict(n_ships=1, mounts_per=8, kind='PdcMcrn', salvo=24, waves=1,
            engage_all=True))
SC3 = ('3 hulls, salvo 48 (2.0/mount)',
       dict(n_ships=3, mounts_per=8, kind='PdcMcrn', salvo=48, waves=1,
            engage_all=True))
SC3H = ('3 hulls, salvo 72 (3.0/mount)',
        dict(n_ships=3, mounts_per=8, kind='PdcMcrn', salvo=72, waves=1,
             engage_all=True))

POLS = {'no PB': None,
        'burst14': lambda: ladder.burst_ladder_only(burst=14),
        'ladder t40b14': lambda: ladder.ladder_deconflict(tol=40, burst=14)}


def _cfg(arc_label, arcs, pol_names):
    return [(f"{arc_label} / {p}", arcs, POLS[p]) for p in pol_names]


def explore(scenario, seeds, pol_names=('no PB', 'burst14')):
    arcs_list = [
        ('stock', None),
        ('kmount 6', arcs_kmount(6)),
        ('kmount 5', arcs_kmount(5)),
        ('kmount 4', arcs_kmount(4)),
        ('iris 35', arcs_iris(35)),
        ('iris 25', arcs_iris(25)),
        ('iris 18', arcs_iris(18)),
        ('iris 12', arcs_iris(12)),
        ('radial 90', arcs_radial(90)),
        ('radial 60', arcs_radial(60)),
        ('radial 45', arcs_radial(45)),
        ('radial 30', arcs_radial(30)),
        ('fan d10 p8', arcs_fan(10, 8)),
        ('fan d10 p14', arcs_fan(10, 14)),
        ('fan d10 p22', arcs_fan(10, 22)),
        ('fan d20 p10', arcs_fan(20, 10)),
        ('fan d20 p16', arcs_fan(20, 16)),
        ('fan d20 p24', arcs_fan(20, 24)),
        ('fan d20 p35', arcs_fan(20, 35)),
        ('fan d30 p15', arcs_fan(30, 15)),
        ('fan d30 p24', arcs_fan(30, 24)),
        ('fan d30 p40', arcs_fan(30, 40)),
        ('sweep2 d25 p16', arcs_sweepers(2, 25, 16)),
    ]
    if scenario is SC3:
        arcs_list += [('consort-aim 25', arcs_consort_aim(25)),
                      ('consort-aim 35', arcs_consort_aim(35)),
                      ('consort-aim 50', arcs_consort_aim(50))]
    configs = []
    for al, a in arcs_list:
        configs += _cfg(al, a, pol_names)
    sweep(configs, [scenario], seeds)


def fine(scenario, seeds, pol_names=('no PB', 'burst14')):
    """Fine sweep around the one promising region: HEAVY-OVERLAP fans, where
    each pit still covers the threat axis (psi > delta) but truncates the far
    side of the approach cone -- a transverse partial-partition."""
    arcs_list = [('stock', None)]
    for d in (10, 15, 20, 25):
        for p in (28, 32, 36, 40, 45):
            if p <= d:
                continue
            arcs_list.append((f'fan d{d} p{p}', arcs_fan(d, p)))
    configs = []
    for al, a in arcs_list:
        configs += _cfg(al, a, pol_names)
    sweep(configs, [scenario], seeds)


def final(scenario, seeds, arcs_list, dump=None):
    configs = []
    for al, a in arcs_list:
        configs += _cfg(al, a, ('no PB', 'burst14', 'ladder t40b14'))
    sweep(configs, [scenario], seeds, dump=dump)


# Finalists chosen from the 8/12-seed sweeps (outpits_explore*.txt, outpits_fine1.txt).
FINALISTS_1 = [
    ('stock', None),
    ('kmount 5', arcs_kmount(5)),            # honest fewer-mounts control
    ('fan d20 p36', arcs_fan(20, 36)),       # best heavy-overlap fan
    ('fan d15 p32', arcs_fan(15, 32)),
    ('fan d25 p40', arcs_fan(25, 40)),
    ('iris 25', arcs_iris(25)),              # representative pit-depth loser
]
FINALISTS_3 = [
    ('stock', None),
    ('kmount 5', arcs_kmount(5)),
    ('fan d20 p35', arcs_fan(20, 35)),
    ('consort-aim 35', arcs_consort_aim(35)),
    ('consort-aim 50', arcs_consort_aim(50)),
]
FINALISTS_72 = [
    ('stock', None),
    ('consort-aim 50', arcs_consort_aim(50)),
]

# Coordinator scenario: thin stream where the ladder is known to degrade
# (1 hull, salvo 48: 8 torps trickling at 1 s intervals, then 40 at once).
SCTHIN = ('1 hull, salvo 48 trickle-then-mass',
          dict(n_ships=1, mounts_per=8, kind='PdcMcrn', salvo=48, waves=1,
               engage_all=True,
               launch_delays=[i * 1.0 for i in range(8)] + [8.5] * 40))
FINALISTS_THIN = [
    ('stock', None),
    ('fan d20 p36', arcs_fan(20, 36)),
    ('fan d15 p32', arcs_fan(15, 32)),
]


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'verify'
    t0 = time.time()
    if mode == 'verify':
        verify()
    elif mode == 'probe':
        probe()
    elif mode == 'time':
        r = run_arcs(1, 8, salvo=24, waves=1, seed=701)
        print(f"1 hull s24 no-PB: {time.time()-t0:.1f}s leak={r['leakers']}", flush=True)
        t1 = time.time()
        r = run_arcs(3, 8, salvo=48, waves=1, seed=701,
                     policy=ladder.burst_ladder_only(burst=14))
        print(f"3 hull s48 burst: {time.time()-t1:.1f}s leak={r['leakers']}", flush=True)
    elif mode == 'explore1':
        explore(SC1, SEEDS[:8])
    elif mode == 'explore3':
        explore(SC3, SEEDS[:8])
    elif mode == 'fine1':
        fine(SC1, SEEDS[:12])
    elif mode == 'fine3':
        fine(SC3, SEEDS[:12])
    elif mode == 'final1':
        final(SC1, SEEDS, FINALISTS_1, dump='final1_raw.json')
    elif mode == 'final3':
        final(SC3, SEEDS, FINALISTS_3, dump='final3_raw.json')
    elif mode == 'final72':
        final(SC3H, SEEDS, FINALISTS_72, dump='final72_raw.json')
    elif mode == 'finalthin':
        final(SCTHIN, SEEDS, FINALISTS_THIN, dump='finalthin_raw.json')
    print(f"[{mode} done in {time.time()-t0:.1f}s]", flush=True)
