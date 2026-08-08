"""Large fleet engagements at REAL torpedo output and REAL PDC budgets.

Salvo sizes in the rest of this study were chosen to make comparisons discriminating.
These come from the ships: each core's SCF torpedo budget buys a specific number of tubes,
and an alpha strike is every tube at once. From run_fleet_alpha.py:

    core       tubes  alpha  sustained     best loadout
    Picket       4      4     34/min       1x LightTriple + 1x MediumSingle
    Corvette     8      8     72/min       2x LightTriple + 1x ImprovisedDouble
    Frigate     16     16    149/min       5x LightTriple + 1x MediumSingle
    Cruiser     21     21    202/min       7x LightTriple
    Carrier     21     21    202/min       7x LightTriple

LightTriple dominates on every measure -- 0.35 points per torpedo/minute against 0.49-0.83
for everything else -- because it dumps its whole 3-round magazine in 1.3 s and reloads in
5 s, where MediumTriple trickles at ShotsInBurst 1 and rof 30 for the same points and the
same tube count.

Defenders use their own class PDC budget, which is the other half nobody has varied:
Picket 5, Corvette 8, Frigate 12, Carrier 20, Cruiser 26 points, all weight-1 PdcMcrn.

Wave cadence is the launcher's own cycle: LightTriple reloads in 5 s and empties in 1.3 s,
so a fleet firing continuously re-alphas about every 6.3 s.
"""
import io
import math
import statistics as st
import sys

from fleet_efficiency import run
import reroll as R
import ladder as L

SEEDS = list(range(901, 913))
ALPHA = {'Picket': 4, 'Corvette': 8, 'Frigate': 16, 'Cruiser': 21, 'Carrier': 21}
PDC_PTS = {'Picket': 5, 'Corvette': 8, 'Frigate': 12, 'Carrier': 20, 'Cruiser': 26}
RELOAD_GAP = 6.3          # LightTriple: 1.3 s to empty + 5 s reload


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def pol_baseline(m, ctx):
    return True, None


def go(def_cls, n_def, atk_cls, n_atk, waves, gap):
    salvo = ALPHA[atk_cls] * n_atk
    mounts = PDC_PTS[def_cls]
    out = {}
    for lab, pol in (('nopb', lambda: pol_baseline),
                     ('di', lambda: R.descend_inflight(k=4))):
        rs = [run(n_def, mounts, kind='PdcMcrn', salvo=salvo, waves=waves,
                  wave_gap=gap, seed=s, engage_all=True, cls=def_cls, policy=pol())
              for s in SEEDS]
        out[lab] = rs
    return salvo, mounts, out


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)

    print('=' * 118)
    print('SINGLE ALPHA STRIKE — attacker fleet empties every tube once'.center(118))
    print('=' * 118)
    print('  %-22s%-20s%7s%8s%9s%10s%10s%9s'
          % ('defender', 'attacker', 'salvo', 'mounts', 'torp/mnt', 'noPB', 'policy', 't'))
    print('  ' + '-' * 114)
    CASES = [
        ('Corvette', 3, 'Corvette', 3), ('Corvette', 3, 'Corvette', 6),
        ('Corvette', 3, 'Frigate', 3), ('Frigate', 3, 'Frigate', 3),
        ('Frigate', 3, 'Cruiser', 3), ('Cruiser', 2, 'Cruiser', 3),
        ('Cruiser', 3, 'Cruiser', 6), ('Carrier', 1, 'Corvette', 4),
    ]
    for dc, nd, ac, na in CASES:
        salvo, mounts, out = go(dc, nd, ac, na, 1, 0.0)
        a = [r['leakers'] for r in out['nopb']]
        b = [r['leakers'] for r in out['di']]
        print('  %-22s%-20s%7d%8d%9.2f%10.2f%10.2f%9.2f'
              % ('%dx %s' % (nd, dc), '%dx %s' % (na, ac), salvo, mounts,
                 salvo / float(mounts * nd), st.mean(a), st.mean(b), paired_t(b, a)))

    print()
    print('=' * 118)
    print('SUSTAINED — re-alpha every 6.3 s (LightTriple cycle), 12 waves'.center(118))
    print('=' * 118)
    print('  %-22s%-20s%7s%9s%12s%12s%11s'
          % ('defender', 'attacker', 'salvo', 'mounts', 'noPB cum', 'policy cum', 'TGC spent'))
    print('  ' + '-' * 114)
    for dc, nd, ac, na in CASES[:6]:
        salvo, mounts, out = go(dc, nd, ac, na, 12, RELOAD_GAP)
        a = st.mean([r['leakers'] for r in out['nopb']])
        b = st.mean([r['leakers'] for r in out['di']])
        print('  %-22s%-20s%7d%9d%12.1f%12.1f%11d'
              % ('%dx %s' % (nd, dc), '%dx %s' % (na, ac), salvo, mounts,
                 a, b, salvo * 12 * 24))
