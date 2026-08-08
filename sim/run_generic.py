"""Does `descend_inflight` transfer across PDC types, or is it a PdcMcrn special?

The robustness pass covered the SHOT-COUNTING trigger (burst=14) and found it
transfers to PdcUnn/UnnAdv/PgenAdv but INVERTS on PdcMcrnAdv (80 rpm, HHM 5),
where baseline beats every range policy. The in-flight trigger has only ever been
tested on PdcMcrn.

Specific reason to expect trouble: K=4 is one kill's worth of committed ordnance
for HHM 1 (torpedo Health 4). PdcMcrnAdv is HHM 5 and flak HHM 11 — one hit kills,
so their kill-sized commitment is K=1. A fixed K=4 makes them over-commit 4x
before reacting. So K should scale as ceil(health / hhm).

SCF legality: 8 points. Weight-1 mounts (Unn, Mcrn) -> 8 of them; weight-2
(UnnAdv, McrnAdv, OpaAdv, PgenAdv) -> 4. PgenAdv is included as a data point only;
Protogen gear is not available to us.
"""
import sys, io, math, statistics as st
import ladder as L
import reroll as R
from fleet_efficiency import run
from weapons import PDC_STATS, PDC_ALIAS
from shipyard import CLASSES, weight_of

SEEDS = list(range(701, 719))
TORP_HEALTH = 4


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def pol_baseline(m, ctx):
    return True, None


KINDS = ['PdcMcrn', 'PdcUnn', 'PdcUnnAdv', 'PdcPgenAdv', 'PdcMcrnAdv', 'PdcOpaAdv']
groups = CLASSES['Corvette'].get('pdc_groups')

print("=" * 118)
print("GENERICITY — does descend_inflight transfer across PDC types?".center(118))
print("=" * 118)
print(f"  {'mount':<13}{'hhm':>4}{'rof':>6}{'n':>3}{'K*':>4}"
      f"{'no PB':>8}{'burst14':>9}{'DI k=4':>9}{'DI k=K*':>9}"
      f"{'t(DI4-bo)':>11}{'t(DIK-bo)':>11}", flush=True)
print("  " + "-" * 114)

for kind in KINDS:
    s = PDC_STATS[kind]
    hhm = s['hhm']
    rof = s['rof']
    w = weight_of(PDC_ALIAS[kind], groups)
    n = max(1, int(8 // w))
    kstar = max(1, math.ceil(TORP_HEALTH / max(1, hhm)))

    rows = {}
    for label, pol in (('nopb', lambda: pol_baseline),
                       ('bo', lambda: L.with_infl_index(L.burst_ladder_only(burst=14))),
                       ('di4', lambda: R.descend_inflight(k=4)),
                       ('dik', lambda: R.descend_inflight(k=kstar))):
        rows[label] = [run(3, n, kind=kind, salvo=48, waves=1, seed=sd,
                           engage_all=True, policy=pol())['leakers'] for sd in SEEDS]
    print(f"  {kind:<13}{hhm:>4}{rof:>6}{n:>3}{kstar:>4}"
          f"{st.mean(rows['nopb']):>8.2f}{st.mean(rows['bo']):>9.2f}"
          f"{st.mean(rows['di4']):>9.2f}{st.mean(rows['dik']):>9.2f}"
          f"{paired_t(rows['di4'], rows['bo']):>11.2f}"
          f"{paired_t(rows['dik'], rows['bo']):>11.2f}", flush=True)

print()
print("  K* = ceil(torpedo Health 4 / HealthHitModifier).  n = mounts legal at 8 SCF points.")
print("  negative t = the in-flight trigger beats the shot counter for that mount.")
