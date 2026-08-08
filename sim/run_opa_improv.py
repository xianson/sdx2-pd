"""The two PDC kinds the genericity sweep missed: PdcOpa and PdcImprovised.

PdcOpa was simply omitted — it is in the catalogue and buildable at weight 1.0.

PdcImprovised is a HARNESS GAP, not just a test gap: `sdx_pdcImprovised.sbc` sits
alongside every other PDC as a normal player-buildable block, and it IS in the SCF
weight tables at 1.0 (pdcsEvenAdvWeights / pdcsHeavyAdvWeights), but the catalogue
builder dropped it — `catalogue.json` contains no pdc keys at all, they come from
elsewhere. Injected here at runtime by cloning pdcOpa (identical 1x2x1 footprint);
integrity/mass differ slightly but neither affects leaker counts, since a leaker
never destroys a mount in this model.

Both are HHM 1 and reasonably fast, so the in-flight policy SHOULD transfer. The
interesting one is PdcImprovised: dev 0.5 is the worst dispersion in the mod (worse
than PdcUnn's 0.4) against a 3.417 m interaction threshold, and prediction level 1.
"""
import sys, io, math, statistics as st
import copy
import components as C
import weapons as W

# ---- inject the missing block, before anything reads the tables
if 'pdcImprovised' not in C.CATALOGUE:
    e = copy.deepcopy(C.CATALOGUE['pdcOpa'])
    e['subtype'] = 'sdx_pdcImprovised'
    e['name'] = 'Improvised PDC'
    C.CATALOGUE['pdcImprovised'] = e
    if hasattr(C, 'BY_SUBTYPE'):
        C.BY_SUBTYPE['sdx_pdcImprovised'] = e
W.PDC_ALIAS.setdefault('PdcImprovised', 'pdcImprovised')
# PDC_KIND (block subtype -> PDC_STATS key) is built at weapons.py IMPORT time from
# PDC_ALIAS x CATALOGUE, so patching the alias afterwards is not enough: build_ship
# places the block but never turns it into a mount. Without this line the run silently
# builds ZERO mounts, charges the full 8 SCF points, and reports 48/48 leakers — which
# looks like a devastating result and is actually an empty ship.
W.PDC_KIND['sdx_pdcImprovised'] = 'PdcImprovised'

import ladder as L
import reroll as R
from fleet_efficiency import run
from weapons import PDC_STATS
from shipyard import CLASSES, weight_of

SEEDS = list(range(701, 719))


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def pol_baseline(m, ctx):
    return True, None


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    groups = CLASSES['Corvette'].get('pdc_groups')
    print("=" * 108)
    print("THE TWO MISSED KINDS — PdcOpa and PdcImprovised".center(108))
    print("=" * 108)
    print(f"  {'mount':<15}{'rof':>6}{'dev':>7}{'pred':>6}{'wt':>5}{'n':>3}"
          f"{'no PB':>9}{'burst14':>9}{'DI k=4':>9}{'t(DI-bo)':>10}{'t(DI-nopb)':>12}",
          flush=True)
    print("  " + "-" * 104)
    for kind in ('PdcMcrn', 'PdcOpa', 'PdcImprovised'):
        s = PDC_STATS[kind]
        try:
            w = weight_of(W.PDC_ALIAS[kind], groups)
        except Exception:
            w = 1.0
        n = max(1, int(8 // w))
        out = {}
        for lab, pol in (('nopb', lambda: pol_baseline),
                         ('bo', lambda: L.with_infl_index(L.burst_ladder_only(burst=14))),
                         ('di', lambda: R.descend_inflight(k=4))):
            out[lab] = [run(3, n, kind=kind, salvo=48, waves=1, seed=sd,
                            engage_all=True, policy=pol())['leakers'] for sd in SEEDS]
        print(f"  {kind:<15}{s['rof']:>6}{s['dev']:>7}{s.get('prediction',3):>6}"
              f"{w:>5.1f}{n:>3}{st.mean(out['nopb']):>9.2f}{st.mean(out['bo']):>9.2f}"
              f"{st.mean(out['di']):>9.2f}{paired_t(out['di'],out['bo']):>10.2f}"
              f"{paired_t(out['di'],out['nopb']):>12.2f}", flush=True)
    print()
    print("  negative t(DI-bo)   = in-flight trigger beats the shot counter")
    print("  negative t(DI-nopb) = the policy is worth running at all for that mount")
