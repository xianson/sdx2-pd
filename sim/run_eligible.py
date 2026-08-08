"""Can range gating emulate CycleTargets=0 by controlling the ELIGIBLE COUNT?

The A/B showed CycleTargets 4->0 is worth 5.92 -> 1.96 leakers at 3 hulls salvo 48
(t=-7.52) on identical hardware. We cannot change the field (PgenAdv, the only PDC with
CycleTargets=0, is not available). But cycle_window (AiTargeting.cs:612-623) examines
ALL eligible targets whenever the eligible count is 1, 2 or exactly 4 -- the starvation
notch is 3, and >=5 examines only a 4-wide walking window.

So: set each mount's tracking range so the count of torpedoes inside it lands on a good
number. `eligible_gate` does that by binary-searching the mount's own range, counting
targets with targeting.valid() -- which is CHEATING (it needs true positions) and exists
only to bound the idea. If the bound is small, the direction dies here; if it is large, a
legal estimator is worth building (per-mount engaged-boolean at staggered ranges gives a
coarse density profile).
"""
import sys, io, math, statistics as st
import targeting
from fleet_efficiency import run
import ladder as L

SEEDS = list(range(701, 725))


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def pol_baseline(m, ctx):
    return True, None


def eligible_gate(want=4, floor_frac=0.15, base_pol=None):
    """~ORACLE-ISH: pick the tracking range whose eligible count == `want`.

    Counts with true positions, so it bounds rather than deploys. Falls back to full
    range when no radius achieves the target count.
    """
    def pol(m, ctx):
        fire, rng = (True, None) if base_pol is None else base_pol(m, ctx)
        torps = ctx.get('_torps')
        sh = ctx.get('_ship_of', {}).get(id(m))
        hull = ctx.get('_hull_of', {}).get(id(m))
        if not torps or sh is None:
            return fire, rng
        base = m._base_range
        # distances to every torpedo this mount could physically engage at full range
        saved = m.range
        m.range = base
        ds = []
        for x in torps:
            if not x.alive:
                continue
            ok, dist = targeting.valid(m, x, sh, hull)
            if ok:
                ds.append(dist)
        m.range = saved
        if not ds:
            return fire, rng
        ds.sort()
        if len(ds) <= want:
            return fire, base
        # smallest radius containing exactly `want` targets, with a slack margin
        r = ds[want - 1] + 1.0
        return fire, max(base * floor_frac, min(base, r))
    return pol


def go(n_ships, salvo, rows):
    print("\n" + "=" * 100)
    print(f"{n_ships} hull(s) x 8 PdcMcrn, salvo {salvo} — eligible-count gating".center(100))
    print("=" * 100)
    print(f"  {'policy':<30}{'leak':>8}{'sd':>6}{'kills':>7}{'fired':>8}{'dead%':>7}"
          f"{'mnt/tgt':>9}", flush=True)
    print("  " + "-" * 96)
    keep = {}
    for name, pol in rows:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=1, seed=s,
                  engage_all=True, policy=pol) for s in SEEDS]
        keep[name] = [r['leakers'] for r in rs]
        lk = keep[name]
        print(f"  {name:<30}{st.mean(lk):>8.2f}{st.stdev(lk):>6.2f}"
              f"{st.mean([r['kills'] for r in rs]):>7.2f}"
              f"{st.mean([r['fired_rounds'] for r in rs]):>8.0f}"
              f"{st.mean([r['dead_pct'] for r in rs]):>7.1f}"
              f"{st.mean([r['mounts_per_target'] for r in rs]):>9.2f}", flush=True)
    ref = 'burst-only b14'
    rl = keep[ref]
    print(f"  paired vs {ref}:")
    for name in keep:
        if name == ref:
            continue
        print(f"    {name:<30} d={st.mean([x-y for x,y in zip(keep[name],rl)]):+6.2f} "
              f"t={paired_t(keep[name],rl):+7.2f}", flush=True)


BURST = L.with_infl_index(L.burst_ladder_only(burst=14))
ROWS = [
    ('baseline (no PB)',            pol_baseline),
    ('burst-only b14',              BURST),
    ('~gate eligible=1',            eligible_gate(1)),
    ('~gate eligible=2',            eligible_gate(2)),
    ('~gate eligible=4',            eligible_gate(4)),
    ('~gate eligible=3 (notch)',    eligible_gate(3)),
    ('~gate elig=4 + burst',        eligible_gate(4, base_pol=BURST)),
    ('~gate elig=2 + burst',        eligible_gate(2, base_pol=BURST)),
]

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    go(1, 24, ROWS)
    go(3, 48, ROWS)
