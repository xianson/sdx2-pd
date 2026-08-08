"""THE FINAL QUESTION: do the three winning ideas compose, or are they redundant?

Each was found by a different agent, against a different reference, and NONE has been
tested in combination:
  descend_inflight(k=4)  descend a rung when >=4 of my own rounds are airborne
                         (sustained 4.25 cum leak vs burst-only's 21.75)
  respread(inner)        reset rungs to the opening spread at each wave boundary
                         (sustained 4.33 cum leak)
  hull_cap(inner, 650)   cap each hull at ITS OWN nearest threat + 650 m
                         (d=-0.62, t=-1.92, sign test p~0.002)

descend_inflight and respread may well be redundant: both plausibly work by defeating the
same cross-wave state rot (in-flight count zeroes naturally between waves; respread zeroes
it explicitly). If so, stacking buys nothing and the simpler one wins.
"""
import sys, io, math, statistics as st
import ladder as L
import reroll as R
import sustain as S
import edd
from fleet_efficiency import run

SEEDS = list(range(801, 813))
W = L.with_infl_index


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


BO = lambda: W(L.burst_ladder_only(burst=14))
DI4 = lambda: R.descend_inflight(k=4)

ROWS = [
    ('burst-only b14 (ref)',        BO),
    ('full ladder t40 b14',         lambda: W(L.ladder_deconflict(tol=40, burst=14))),
    ('descend_inflight k4',         DI4),
    ('respread(burst-only)',        lambda: S.respread(BO())),
    ('respread(DI4)',               lambda: S.respread(DI4())),
    ('hullcap650(DI4)',             lambda: edd.hull_cap(DI4, 650.0)),
    ('respread(hullcap650(DI4))',   lambda: S.respread(edd.hull_cap(DI4, 650.0))),
    ('respread(hullcap650(BO))',    lambda: S.respread(edd.hull_cap(BO, 650.0))),
]


def sustained(n_ships, salvo, waves, gap):
    print("\n" + "=" * 104)
    print(f"SUSTAINED — {n_ships} hulls, salvo {salvo} x {waves} waves, {gap:.0f}s gap"
          .center(104))
    print("=" * 104)
    print(f"  {'policy':<28}{'waves_to_death':>15}{'cum leak':>10}{'fired':>9}"
          f"{'peak heat%':>11}", flush=True)
    print("  " + "-" * 100)
    keep = {}
    for name, fac in ROWS:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=waves, seed=s,
                  engage_all=True, policy=fac(), wave_gap=gap) for s in SEEDS]
        deaths = []
        for r in rs:
            cum, died = 0, None
            for i, (lk, _k, _h) in enumerate(r['per_wave'], 1):
                cum += lk
                if cum >= 3 and died is None:
                    died = i
            deaths.append(died if died is not None else waves + 1)
        keep[name] = ([r['leakers'] for r in rs], deaths)
        print(f"  {name:<28}{st.mean(deaths):>15.2f}"
              f"{st.mean(keep[name][0]):>10.2f}"
              f"{st.mean([r['fired_rounds'] for r in rs]):>9.0f}"
              f"{st.mean([r['peak_heat'] for r in rs]):>11.1f}", flush=True)
    for ref in ('burst-only b14 (ref)', 'descend_inflight k4', 'respread(burst-only)'):
        rl, rd = keep[ref]
        print(f"  paired vs {ref}:")
        for name in keep:
            if name == ref:
                continue
            l2, d2 = keep[name]
            print(f"    {name:<28} cumleak d={st.mean([x-y for x,y in zip(l2,rl)]):+7.2f} "
                  f"t={paired_t(l2,rl):+7.2f} | wtd d={st.mean([x-y for x,y in zip(d2,rd)]):+6.2f} "
                  f"t={paired_t(d2,rd):+6.2f}", flush=True)


def single(n_ships, salvo):
    print("\n" + "=" * 104)
    print(f"SINGLE WAVE — {n_ships} hulls, salvo {salvo}".center(104))
    print("=" * 104)
    print(f"  {'policy':<28}{'leak':>8}{'sd':>6}{'fired':>9}", flush=True)
    print("  " + "-" * 100)
    keep = {}
    for name, fac in ROWS:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=1, seed=s,
                  engage_all=True, policy=fac()) for s in SEEDS]
        keep[name] = [r['leakers'] for r in rs]
        print(f"  {name:<28}{st.mean(keep[name]):>8.2f}{st.stdev(keep[name]):>6.2f}"
              f"{st.mean([r['fired_rounds'] for r in rs]):>9.0f}", flush=True)
    rl = keep['burst-only b14 (ref)']
    print("  paired vs burst-only b14:")
    for name in keep:
        if name != 'burst-only b14 (ref)':
            print(f"    {name:<28} d={st.mean([x-y for x,y in zip(keep[name],rl)]):+6.2f} "
                  f"t={paired_t(keep[name],rl):+7.2f}", flush=True)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    sustained(3, 24, 20, 6.0)
    sustained(3, 24, 20, 15.0)
    single(3, 48)
    single(1, 24)
