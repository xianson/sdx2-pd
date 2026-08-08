"""Fleet tests at salvo sizes that actually LOAD the fleet.

Every fleet result so far was easier per mount than the single-hull result:
    1 hull  =  8 mounts vs salvo 24  -> 3.00 torpedoes/mount
    3 hulls = 24 mounts vs salvo 40  -> 1.67 torpedoes/mount
which is why 3-hull salvo 24 saturates at ~0.1 leakers and discriminates nothing.
Matching single-hull loading needs salvo 72 for three hulls.

This matters because the fleet is where the waste lives: measured 92.0% waste and
3.2-4.2 mounts/target on 3 hulls vs 87.0% and 1.7 on one. Redundant commitment is a
fleet phenomenon, so policies aimed at it must be judged under fleet load.
"""
import sys, io, math, statistics as st
from fleet_efficiency import run
import ladder as L

SEEDS = list(range(701, 729))            # 28 seeds
Wd = 116


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
POLICIES = [
    ('baseline (no PB)',        pol_baseline),
    ('static band .75/.5/.25',  L.static_band()),
    ('window nearest+500',      L.window_nearest(500.0)),
    ('burst-only b14',          W(L.burst_ladder_only(burst=14))),
    ('full ladder tol40 b14',   W(L.ladder_deconflict(tol=40, burst=14))),
]


def table(n_ships, salvo):
    per_mount = salvo / (n_ships * 8.0)
    print("\n" + "=" * Wd)
    print(f"{n_ships} HULL(S), salvo {salvo}  —  {per_mount:.2f} torpedoes/mount".center(Wd))
    print("=" * Wd)
    print(f"  {'policy':<26}{'leak':>7}{'sd':>6}{'leak/ship':>10}{'kills':>7}{'fired':>8}"
          f"{'waste%':>8}{'dead%':>7}{'mnt/tgt':>9}", flush=True)
    print("  " + "-" * (Wd - 4))
    keep = {}
    for name, pol in POLICIES:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=1, seed=s,
                  engage_all=True, policy=pol) for s in SEEDS]
        keep[name] = rs
        lk = [r['leakers'] for r in rs]
        print(f"  {name:<26}{st.mean(lk):>7.2f}{st.stdev(lk):>6.2f}"
              f"{st.mean(lk)/n_ships:>10.2f}{agg(rs,'kills'):>7.2f}{agg(rs,'fired_rounds'):>8.0f}"
              f"{agg(rs,'waste_pct'):>8.1f}{agg(rs,'dead_pct'):>7.1f}"
              f"{agg(rs,'mounts_per_target'):>9.2f}", flush=True)
    ref = 'burst-only b14'
    rl = [r['leakers'] for r in keep[ref]]
    rf = [r['fired_rounds'] for r in keep[ref]]
    print(f"  paired vs {ref}:")
    for name in keep:
        if name == ref:
            continue
        l2 = [r['leakers'] for r in keep[name]]
        f2 = [r['fired_rounds'] for r in keep[name]]
        print(f"    {name:<26} leak d={st.mean([x-y for x,y in zip(l2,rl)]):+6.2f} "
              f"t={paired_t(l2,rl):+7.2f} | fired d={st.mean([x-y for x,y in zip(f2,rf)]):+7.0f} "
              f"t={paired_t(f2,rf):+7.2f}", flush=True)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    table(1, 24)          # 3.00/mount — the reference difficulty
    table(3, 48)          # 2.00/mount
    table(3, 72)          # 3.00/mount — matches the single-hull load
    table(3, 96)          # 4.00/mount — fleet overload
