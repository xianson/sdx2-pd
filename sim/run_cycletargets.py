"""Is CycleTargets the hidden variable behind the PdcPgenAdv result?

REVERSE-ENGINEERED MECHANISM (AiTargeting.cs:612-623, ported bit-exact in
wc_acquire.cycle_window):

    if cycle <= 0:                check_size = num_of_targets     # examine EVERYTHING
    elif cycle > num_of_targets:  check_size = cycle - num_of_targets   # SUBTRACTS
    else:                         check_size = cycle

`check_size` is how many cards of the shuffled deck the weapon even LOOKS AT; it takes
the first that passes accept() and otherwise acquires nothing this attempt. So with the
base CycleTargets = 4:
    1 eligible  -> examines 1  (the only one: assignment is FORCED)
    2 eligible  -> examines 2
    3 eligible  -> examines 1  of 3   <-- starvation notch, worse than 4
    4 eligible  -> examines 4  (all)
   12 eligible  -> examines 4  of 12, window walking by AcquireAttempts

`sdx_weapon_pdcPgenAdv.cs:29` is the ONLY SDX2 PDC that sets CycleTargets = 0, so it
examines every eligible target every time and never starves. That is invisible in any
stat sheet, and it is a candidate explanation for PgenAdv beating PdcMcrn.

This isolates it: same PdcMcrn hardware, ONLY cycle_targets changed 4 -> 0.
The seed is fully determined (`CurrentSeed = int.MaxValue - UniquePartId`, Utils.cs),
so there is no hidden entropy anywhere in the selection.
"""
import sys, io, math, statistics as st
import wc_acquire as wc

_orig = wc.sdx2_pdc


def patched(name, unique_part_id=0):
    p = _orig(name, unique_part_id=unique_part_id)
    if getattr(patched, 'force_cycle', None) is not None:
        p.cycle_targets = patched.force_cycle
        p.reset_state()
    return p


wc.sdx2_pdc = patched
patched.force_cycle = None

import targeting                      # noqa: E402  (must import AFTER the patch)
from fleet_efficiency import run      # noqa: E402
import ladder as L                    # noqa: E402

SEEDS = list(range(701, 725))


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def pol_baseline(m, ctx):
    return True, None


def go(n_ships, salvo):
    print("\n" + "=" * 104)
    print(f"{n_ships} hull(s) x 8 PdcMcrn, salvo {salvo} — CycleTargets A/B".center(104))
    print("=" * 104)
    print(f"  {'policy':<22}{'CycleTargets':>13}{'leak':>8}{'sd':>6}{'kills':>7}"
          f"{'fired':>8}{'dead%':>7}{'mnt/tgt':>9}", flush=True)
    print("  " + "-" * 100)
    store = {}
    for pname, pol in (('baseline (no PB)', pol_baseline),
                       ('burst-only b14', L.with_infl_index(L.burst_ladder_only(burst=14)))):
        for cyc in (4, 0):
            patched.force_cycle = cyc
            rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=1, seed=s,
                      engage_all=True, policy=pol) for s in SEEDS]
            store[(pname, cyc)] = [r['leakers'] for r in rs]
            lk = store[(pname, cyc)]
            print(f"  {pname:<22}{cyc:>13}{st.mean(lk):>8.2f}{st.stdev(lk):>6.2f}"
                  f"{st.mean([r['kills'] for r in rs]):>7.2f}"
                  f"{st.mean([r['fired_rounds'] for r in rs]):>8.0f}"
                  f"{st.mean([r['dead_pct'] for r in rs]):>7.1f}"
                  f"{st.mean([r['mounts_per_target'] for r in rs]):>9.2f}", flush=True)
        a, b = store[(pname, 0)], store[(pname, 4)]
        print(f"    -> cycle 0 vs 4: d={st.mean([x-y for x,y in zip(a,b)]):+.2f} "
              f"t={paired_t(a,b):+.2f}", flush=True)
    patched.force_cycle = None


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    go(1, 24)
    go(3, 48)
    go(3, 72)
