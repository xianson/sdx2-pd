"""Ray-intersection de-confliction on a range ladder, ablated.

Ablation matters here: the scheme has three separable parts (ray de-confliction,
burst-and-descend, window prioritisation) and the earlier ~30-policy sweep showed
that anything which WITHHOLDS fire loses while anything that REDIRECTS it wins. The
ladder is a redirect, the burst is a withhold, so they are measured apart as well as
together.
"""
import sys, io, math, statistics as st
from fleet_efficiency import run
import ladder as L

SEEDS = list(range(701, 715))
Wd = 128


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
    ('baseline (no PB)',            pol_baseline),
    ('static band .75/.5/.25',      L.static_band()),
    ('window nearest+500',          L.window_nearest(500.0)),
    ('deconflict only tol40',       W(L.deconflict_only(40.0))),
    ('deconflict only tol100',      W(L.deconflict_only(100.0))),
    ('burst ladder only b14',       W(L.burst_ladder_only(burst=14))),
    ('full ladder tol40 b14',       W(L.ladder_deconflict(tol=40, burst=14))),
    ('full ladder tol100 b14',      W(L.ladder_deconflict(tol=100, burst=14))),
    ('full ladder tol40 b30',       W(L.ladder_deconflict(tol=40, burst=30))),
    ('window + ladder tol40',       W(L.window_plus_ladder(500.0, tol=40, burst=14))),
    ('window + ladder tol100',      W(L.window_plus_ladder(500.0, tol=100, burst=30))),
]


def table(title, n_ships, salvo):
    print("\n" + "=" * Wd)
    print(title.center(Wd))
    print("=" * Wd)
    print(f"  {'policy':<26}{'leak':>7}{'sd':>6}{'kills':>7}{'fired':>8}{'r/kill':>8}"
          f"{'waste%':>8}{'dead%':>7}{'miss%':>7}{'use%':>7}{'mnt/tgt':>9}", flush=True)
    print("  " + "-" * (Wd - 4))
    keep = {}
    for name, pol in POLICIES:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=1, seed=s,
                  engage_all=True, policy=pol) for s in SEEDS]
        keep[name] = rs
        lk = [r['leakers'] for r in rs]
        print(f"  {name:<26}{st.mean(lk):>7.2f}{st.stdev(lk):>6.2f}{agg(rs,'kills'):>7.2f}"
              f"{agg(rs,'fired_rounds'):>8.0f}{agg(rs,'rounds_per_kill'):>8.1f}"
              f"{agg(rs,'waste_pct'):>8.1f}{agg(rs,'dead_pct'):>7.1f}{agg(rs,'miss_pct'):>7.1f}"
              f"{agg(rs,'useful_pct'):>7.1f}{agg(rs,'mounts_per_target'):>9.2f}", flush=True)
    for ref in ('static band .75/.5/.25', 'window nearest+500'):
        rl = [r['leakers'] for r in keep[ref]]
        rf = [r['fired_rounds'] for r in keep[ref]]
        print(f"  paired vs {ref}:")
        for name in keep:
            if name == ref:
                continue
            l2 = [r['leakers'] for r in keep[name]]
            f2 = [r['fired_rounds'] for r in keep[name]]
            print(f"    {name:<26} leak d={st.mean([x-y for x,y in zip(l2,rl)]):+6.2f} "
                  f"t={paired_t(l2,rl):+7.2f} | rounds d={st.mean([x-y for x,y in zip(f2,rf)]):+7.0f} "
                  f"t={paired_t(f2,rf):+7.2f}", flush=True)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    table("SINGLE CORVETTE, 8x PdcMcrn, salvo 24", 1, 24)
    table("3 CORVETTES NET-ENGAGING, 500 m, salvo 24", 3, 24)
    table("3 CORVETTES NET-ENGAGING, 500 m, salvo 40", 3, 40)
