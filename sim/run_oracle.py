"""How much do the API constraints actually cost us?

The oracle cheats completely (true torpedo state, per-target attribution of every round
in flight, direct assignment) but still obeys physics: arcs, LOS, slew, time of flight,
dispersion, and one-target-per-round. It bounds what any control scheme could achieve.

The ablations matter more than the bound. Each removes ONE oracle power, so the gap
between them says which piece of impossible knowledge is actually load-bearing — and
therefore what a real PB should spend its effort approximating:
    greedy-nearest   perfect assignment, NO deadline logic, NO commitment accounting
    no-commitment    EDD + drop, but blind to rounds already in flight
    no-drop          EDD + commitment, but wastes rounds on unsaveable targets
    full             all three
"""
import sys, io, math, statistics as st
from fleet_efficiency import run
import ladder as L
import oracle as O

SEEDS = list(range(701, 713))
Wd = 118


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def agg(rs, k):
    return st.mean([r[k] for r in rs])


def pol_baseline(m, ctx):
    return True, None


W = L.with_infl_index
ROWS = [
    ('baseline (no PB)',        dict(policy=pol_baseline)),
    ('static band',             dict(policy=L.static_band())),
    ('window nearest+500',      dict(policy=L.window_nearest(500.0))),
    ('burst-only b14',          dict(policy=W(L.burst_ladder_only(burst=14)))),
    ('full ladder tol40 b14',   dict(policy=W(L.ladder_deconflict(tol=40, burst=14)))),
    ('~ORACLE greedy-nearest',  dict(assign=O.greedy_nearest_assign())),
    ('~ORACLE no-commitment',   dict(assign=O.oracle_assign(use_commitment=False))),
    ('~ORACLE no-drop',         dict(assign=O.oracle_assign(drop_hopeless=False))),
    ('~ORACLE full',            dict(assign=O.oracle_assign())),
]


def table(n_ships, salvo):
    per_mount = salvo / (n_ships * 8.0)
    print("\n" + "=" * Wd)
    print(f"{n_ships} hull(s), salvo {salvo}  —  {per_mount:.2f} torpedoes/mount".center(Wd))
    print("=" * Wd)
    print(f"  {'policy':<26}{'leak':>7}{'sd':>6}{'kills':>7}{'fired':>8}{'r/kill':>8}"
          f"{'waste%':>8}{'dead%':>7}{'miss%':>7}{'mnt/tgt':>9}", flush=True)
    print("  " + "-" * (Wd - 4))
    keep = {}
    for name, kw in ROWS:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=1, seed=s,
                  engage_all=True, **kw) for s in SEEDS]
        keep[name] = rs
        lk = [r['leakers'] for r in rs]
        print(f"  {name:<26}{st.mean(lk):>7.2f}{st.stdev(lk):>6.2f}{agg(rs,'kills'):>7.2f}"
              f"{agg(rs,'fired_rounds'):>8.0f}{agg(rs,'rounds_per_kill'):>8.1f}"
              f"{agg(rs,'waste_pct'):>8.1f}{agg(rs,'dead_pct'):>7.1f}{agg(rs,'miss_pct'):>7.1f}"
              f"{agg(rs,'mounts_per_target'):>9.2f}", flush=True)
    ref = 'burst-only b14'
    rl = [r['leakers'] for r in keep[ref]]
    print(f"  paired vs {ref} (negative = better):")
    for name in keep:
        if name == ref:
            continue
        l2 = [r['leakers'] for r in keep[name]]
        print(f"    {name:<26} leak d={st.mean([x-y for x,y in zip(l2,rl)]):+7.2f} "
              f"t={paired_t(l2,rl):+7.2f}", flush=True)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    table(1, 24)
    table(3, 48)
    table(3, 72)
