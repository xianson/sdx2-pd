"""Optimal picket design: how far out, and how should mounts be distributed?

The formation result everyone has been quoting (an axial picket line leaking 0.00 under
every policy) was measured with THREE CORVETTES, all carrying the stock 8-mount ring. The
Picket CLASS never appeared in it, and the distribution of mounts across the line was never
varied. So "optimal picket design" was an open question, not a finding.

Geometry, from frontier.picket(): the lead is fleet[0] at x=0 and is what torpedoes home
on; screens sit UP-THREAT at positive x, so the salvo must fly past them to reach the lead.
Lateral offset alternates +/-lat to keep pass-by angular rate under the 0.1309 rad/tick
slew cap.

Two questions, both at EQUAL TOTAL PDC POINTS so the comparison is a real build choice:

  1. SPACING. How far up-threat do screens want to be? Too close and their envelope
     overlaps the lead's, adding nothing; too far and the salvo has re-converged or the
     screens are out of mutual support.
  2. DISTRIBUTION. Given 24 points, is 8/8/8 right? A heavy screen sees the salvo first
     and longest, so it may deserve more; but the lead is what actually gets hit, so
     stripping it is a gamble. Includes the extreme case of screens with NO PD at all,
     which tests whether the formation works because screens SHOOT or merely because
     they are in the way.

Mount counts stand in for class: the Picket core has 5 PDC points, Corvette 8, Frigate 12.
build_placed always constructs a Corvette hull, so this varies battery size rather than
hull size -- a real limitation, noted rather than papered over.
"""
import io
import math
import statistics as st
import sys

from vec import V
import frontier as F
import reroll as R

SEEDS = list(range(701, 715))


def ring(n, alias='pdcMcrn'):
    """n mounts spread evenly on the hull ring, mirroring shipyard's angle math."""
    if n <= 0:
        return []
    return [(alias, 360.0 * i / n, +1 if i % 2 == 0 else -1) for i in range(n)]


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def specs(counts, xs, lat=250.0):
    out = []
    for i, (n, x) in enumerate(zip(counts, xs)):
        y = 0.0 if i == 0 else (lat if i % 2 else -lat)
        out.append((ring(n), V(x, y, 0)))
    return out


def measure(counts, xs, salvo, pol):
    lk = []
    fired = []
    for s in SEEDS:
        r = F.run_placed(specs(counts, xs), salvo=salvo, seed=s, policy=pol())
        lk.append(r['leakers'])
        fired.append(r['fired_rounds'])
    return lk, st.mean(fired)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                 line_buffering=True)
    POL = lambda: R.descend_inflight(k=4)
    SALVO = 96   # above the ~50 saturation cliff, so rows can actually differ

    print('=' * 112)
    print(('SPACING — 8/8/8 mounts, salvo %d, 14 seeds' % SALVO).center(112))
    print('=' * 112)
    print('  %-34s%9s%10s%9s' % ('layout', 'leakers', 'sd', 'fired'))
    print('  ' + '-' * 108)
    base = None
    for xs, label in [((0, 0, 0), 'abreast (all at x=0)'),
                      ((0, 500, 1000), 'line 0/500/1000'),
                      ((0, 1000, 2000), 'line 0/1000/2000'),
                      ((0, 2000, 4000), 'line 0/2000/4000  (the quoted one)'),
                      ((0, 3000, 6000), 'line 0/3000/6000'),
                      ((0, 4000, 8000), 'line 0/4000/8000')]:
        lk, fired = measure((8, 8, 8), xs, SALVO, POL)
        if base is None:
            base = lk
        print('  %-34s%9.2f%10.2f%9.0f' % (label, st.mean(lk), st.stdev(lk), fired))
    print('  (first row is the reference for the t-stats below)')

    print()
    print('=' * 112)
    print(('DISTRIBUTION — 24 PDC points total, salvo %d' % SALVO).center(112))
    print('=' * 112)
    print('  %-34s%9s%10s%9s%12s' % ('lead/screen/screen', 'leakers', 'sd', 'fired', 't vs 8/8/8'))
    print('  ' + '-' * 108)
    XS = (0, 2000, 4000)
    ref = None
    rows = [(8, 8, 8), (12, 6, 6), (16, 4, 4), (4, 10, 10), (2, 11, 11),
            (0, 12, 12), (24, 0, 0), (12, 12, 0), (5, 5, 5)]
    for counts in rows:
        lk, fired = measure(counts, XS, SALVO, POL)
        if ref is None:
            ref = lk
        tag = '/'.join(str(c) for c in counts)
        if sum(counts) != 24:
            tag += '  (%d pts)' % sum(counts)
        print('  %-34s%9.2f%10.2f%9.0f%12.2f'
              % (tag, st.mean(lk), st.stdev(lk), fired, paired_t(lk, ref)))
    print()
    print('  0/12/12 tests whether screens work by SHOOTING or merely by being in the way.')
    print('  24/0/0 is a single hull carrying everything, i.e. no picket line at all.')
    print('  5/5/5 is three Picket-class batteries (15 pts) rather than 24, for scale.')
