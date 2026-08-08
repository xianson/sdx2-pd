"""Classical-problem imports for the PD policy search.

WHAT THIS PROBLEM ACTUALLY IS
  Weapon-Target Assignment with three twists: (a) assignment is made by an
  adversarial randomiser (WeaponCore's deck walk) that we can only BIAS through
  per-mount range prefixes; (b) rounds are commitment-delayed (a dead target
  wastes the whole pipeline, ~f*tof rounds per kill); (c) a hard common deadline
  (~2.4 s envelope crossing). Decomposed, three classical sub-problems survive
  contact with the range-gate-only actuator:

  1. SHOOT-LOOK-SHOOT SALVO SIZING (commitment doctrine). We cannot "look"
     (no per-torpedo state), but the renewal-theory version needs no look:
     commit the salvo N* that maximises expected kills per unit time,
         N* = argmax P(Bin(N, p) >= H) / (N/f + s)
     with H = 4 hits to kill, f = 30 rounds/s, s ~ 0.15 s re-aim dead time.
     Two consistent readings, one per hit-probability level:
       * p_live ~ 0.41 (hit prob given the target is still alive; weapon
         physics only, measured 4/(4+5.8) from the incumbent's per-kill miss
         count) -> N* = 12-16 across the plausible band. THE TUNED BURST 14
         IS THIS OPTIMUM -- the incumbent's magic number is a computable
         constant, not a free parameter.
       * p_agg = 0.19 (hits / all rounds, waste folded in) -> N* = 27, a
         PER-TARGET commitment: 14 * k at the observed concurrency k ~ 2.
         `pooled_sls` actuates this reading -- budget N*/k per mount, k from
         the ray-conflict cluster size -- making the division adaptive.

  2. MAXIMAL INDEPENDENT SET on the conflict graph (distributed colouring).
     The ladder resolves conflicts pairwise, one rung per PB tick, by a blind
     fixed-fraction demotion that may not even exclude the shared target.
     A Luby-style single-round resolution: per conflict CLUSTER (connected
     component), one winner (max rounds in flight) keeps the target, every
     loser gets a SURGICAL range cut to just below the triangulated range of
     the shared torpedo -- the ray-gap midpoint hands us that range for free.
     The cut force-drops exactly the shared target while keeping every nearer
     torpedo eligible, which is the least-destructive edge-removal the
     actuator can express.

  3. EARLIEST-DUE-DATE / MOORE-HODGSON (deadline scheduling). All torpedoes
     share speed, so due-date order = range order, and minimising late jobs
     under saturation means serving the head and abandoning the tail --
     window_nearest IS the index policy already. Kept as a cap.

  Framings that do NOT cash out (evaluated, discarded):
  * Restless-bandit / Whittle index: the deadline index reduces to least
    laxity = nearest-first here (uniform speeds, unobservable per-target
    damage), i.e. it re-derives window_nearest and adds nothing new.
  * Coupon-collector closed forms: predict baseline scatter (24 mounts on 40
    targets covers n(1-(1-1/n)^m) ~ 18 targets, max load ~3 -- matches the
    measured mnt/tgt 2.7 and "everything wounded, nothing dead") but yield a
    diagnosis, not an actuator. See report_analysis() in run_wta.py.

LEGALITY: identical basis to ladder.py -- ctx['bearings'] (direction only),
ctx['own_rounds'] (own rounds' pos/vel), ctx['nearest'] (dead-reckoned),
own mount scratch state, and offline weapon/torpedo constants. The in-flight
map is rebuilt from ctx['own_rounds'] (a real PB owns every MonitorProjectile
callback). No torpedo object, no target identity is read anywhere.
"""
import math
from math import comb
import ladder as L
from ladder import _ray_gap

# ---- constants from the brief / weapon spec (offline knowledge, not tuning) --
H_HITS = 4        # torpedo Health 4, PDC40mm HealthHitModifier 1
P_HIT = 0.19      # measured per-round hit probability
ROF_S = 30.0      # PdcMcrn 1800 rpm
SWITCH_S = 0.15   # re-aim dead time: force-drop reopens the seek window at once
TERM_MPS = 1040.0     # staged terminal speed (lower bound)
PB_S = 10.0 / 60.0    # Update10
# closure per PB tick: a cut must undercut the shared target by at least this
# much or the torpedo walks back inside the gate before the next decision
CLOSURE_M = TERM_MPS * PB_S


def sls_salvo_size(p=P_HIT, h=H_HITS, f=ROF_S, s=SWITCH_S, nmax=60):
    """Renewal-optimal salvo: argmax_N P(kill | N rounds) / (N/f + s)."""
    best_n, best_r = h, 0.0
    for n in range(h, nmax):
        pk = sum(comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(h, n + 1))
        r = pk / (n / f + s)
        if r > best_r:
            best_n, best_r = n, r
    return best_n


NSTAR = sls_salvo_size()          # 27 at the nominal constants


# --------------------------------------------------------------- shared maps
def _infl_map(ctx):
    """(ship,idx) -> own rounds in flight, complete at tick start.

    Built from ctx['own_rounds'] so every mount sees the SAME finished map
    (ladder's progressive _infl_by_key gives early mounts an empty view).
    """
    got = ctx.get('_wta_infl')
    if got is not None:
        return got
    inf = {}
    for ship, idx, _p, _v in ctx.get('own_rounds') or []:
        k = (ship, idx)
        inf[k] = inf.get(k, 0) + 1
    ctx['_wta_infl'] = inf
    return inf


def _clusters(ctx, tol):
    """Connected components of the ray-conflict graph, once per PB tick.

    Returns (comp, size, est) where comp maps mount key -> component root,
    size maps root -> member count, and est maps mount key -> distance from
    its muzzle to the nearest triangulated shared-target midpoint. est is the
    range recovered from two bearings -- the only ranging the API allows.
    """
    key = '_wta_clu_%g' % tol
    got = ctx.get(key)
    if got is not None:
        return got
    bs = ctx.get('bearings') or []
    parent = {}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    est = {}
    for i in range(len(bs)):
        si, ii, pi, di = bs[i]
        ki = (si, ii)
        for j in range(i + 1, len(bs)):
            sj, ij, pj, dj = bs[j]
            kj = (sj, ij)
            r = _ray_gap(pi, di, pj, dj)
            if r is None or r[0] > tol:
                continue
            gap, mid = r
            parent.setdefault(ki, ki)
            parent.setdefault(kj, kj)
            union(ki, kj)
            dei = (mid - pi).length()
            dej = (mid - pj).length()
            if dei < est.get(ki, 1e18):
                est[ki] = dei
            if dej < est.get(kj, 1e18):
                est[kj] = dej
    comp = {k: find(k) for k in parent}
    size = {}
    for k, r in comp.items():
        size[r] = size.get(r, 0) + 1
    out = (comp, size, est)
    ctx[key] = out
    return out


# ------------------------------------------------------------------ policies
def wta_policy(bands=L.LADDER, tol=40.0, nstar=NSTAR, pooled=True,
               surgical=True, guard=200.0, burst=14, cool_frac=0.20,
               dwell=0.35, window=None, demote_junior=False):
    """Configurable stack. pooled/surgical/window switch the three imports.

    pooled    burst budget = nstar / k (k = conflict-cluster size incl. self)
              instead of the fixed per-mount `burst`.
    surgical  conflict resolution: cluster losers (everyone but the max-in-
              flight member) cut range to just below the triangulated shared-
              target range for one PB tick, instead of a rung demotion.
              Skipped when the shared target IS the leading edge
              (est <= nearest + guard): deadline dominates, pile-on stands.
    demote_junior  ladder-style resolution instead: cluster losers demote one
              rung immediately (mutually exclusive with surgical in spirit;
              lets pooled budgets be A/B'd against the incumbent demotion).
    window    EDD cap: range never exceeds nearest + window.
    """
    def pol(m, ctx):
        st = getattr(m, '_wta', None)
        if st is None:
            st = m._wta = {'rung': m._idx % len(bands), 'base': m.shots_fired,
                           'bottom_at': None}
        rung = st['rung']
        me = (m._ship, m._idx)
        comp, size, est = _clusters(ctx, tol)
        k = size.get(comp.get(me), 1) if me in comp else 1
        cut = None
        reaimed = False

        # ---- MIS de-confliction: one-shot cluster resolution ---------------
        if (surgical or demote_junior) and me in comp:
            infl = _infl_map(ctx)
            root = comp[me]
            # winner = most committed member; deterministic tie-break on key
            best_key, best_score = None, None
            for kk, rr in comp.items():
                if rr != root:
                    continue
                sc = (infl.get(kk, 0), -(kk[0] * 1000 + kk[1]))
                if best_score is None or sc > best_score:
                    best_key, best_score = kk, sc
            i_win = best_key == me
            d_est = est.get(me)
            if not i_win and demote_junior:
                if rung < len(bands) - 1:
                    rung += 1
                reaimed = True
            elif not i_win and d_est is not None and \
                    d_est > ctx['nearest'] + guard:
                # exclude the shared torpedo, keep everything nearer eligible;
                # undercut by one PB tick of closure so it stays excluded
                cut = min(0.97 * d_est, d_est - CLOSURE_M)
                reaimed = True

        # ---- SLS burst budget ----------------------------------------------
        budget = max(2, int(round(nstar / float(k)))) if pooled else burst
        if not reaimed and m.shots_fired - st['base'] >= budget:
            if rung < len(bands) - 1:
                rung += 1
            reaimed = True

        if reaimed:
            st['base'] = m.shots_fired
            st['bottom_at'] = ctx['t'] if rung == len(bands) - 1 else None

        # ---- bottom-of-ladder recycle (identical to ladder.py) -------------
        if rung == len(bands) - 1:
            if st['bottom_at'] is None:
                st['bottom_at'] = ctx['t']
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and ctx['t'] - st['bottom_at'] >= dwell:
                rung = 0
                st['base'] = m.shots_fired
                st['bottom_at'] = None

        st['rung'] = rung
        r = m._base_range * bands[rung]
        if window is not None:
            r = min(r, ctx['nearest'] + window)
        if cut is not None:
            r = min(r, cut)
        return True, r
    return pol


# named variants ---------------------------------------------------------------
def pooled_sls(tol=40.0, nstar=NSTAR):
    """SLS only: adaptive burst N*/k, conflicts resolved by budget exhaustion."""
    return wta_policy(tol=tol, nstar=nstar, pooled=True, surgical=False)


def surgical_mis(tol=40.0, guard=200.0, burst=14):
    """MIS only: fixed burst 14, one-tick surgical cluster resolution."""
    return wta_policy(tol=tol, guard=guard, burst=burst,
                      pooled=False, surgical=True)


def sls_mis(tol=40.0, guard=200.0, nstar=NSTAR):
    """SLS budget + MIS surgical de-confliction."""
    return wta_policy(tol=tol, guard=guard, nstar=nstar,
                      pooled=True, surgical=True)


def sls_mis_edd(tol=40.0, guard=200.0, nstar=NSTAR, window=500.0):
    """All three imports: SLS budget + MIS resolution + EDD window cap."""
    return wta_policy(tol=tol, guard=guard, nstar=nstar, window=window,
                      pooled=True, surgical=True)
