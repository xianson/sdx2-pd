"""The range ladder as a SORTING NETWORK.

The full ladder's conflict pass is an unstructured set of compare-exchanges:
"if these two rays converge, demote one rung". Taking that literally, the
mount->rung assignment is a sequence being sorted, and the questions become
the classical ones: what is the SORT KEY, what is the COMPARATOR SCHEDULE,
and how many passes does the network need against a ~14-PB-tick engagement?

Three families here:

1. rank_ladder(source='direct')  — "sort by omniscient comparison": every PB
   tick compute each mount's key, argsort, assign rung = rank. This is the
   fixed point every incremental network approximates; it bounds them above.
2. rank_ladder(source='net')     — the same assignment maintained INCREMENTALLY
   by a comparator network: odd-even transposition (pairs (0,1),(2,3).. on even
   PB ticks, (1,2),(3,4).. on odd — O(n) work per tick, neighbour-only, the
   classic linear-array network) or Batcher merge-exchange (one stage per tick,
   15 stages for n=24, non-local but converges in log^2 n stages).
3. sorted_ladder — keeps the FULL ladder semantics (demote-on-conflict, burst,
   bottom-cycle) but uses the sort as a conflict-detection ACCELERATOR: sort
   tracking mounts by a sky-projection key, ray-test only ADJACENT pairs.
   Same-target mounts have nearly identical bearings, so they land adjacent in
   the sorted order and the O(n^2) pairwise pass collapses to O(n).

KEYS (all legal: derived from own bearings / own rounds only):
  sky_u / sky_theta  project every tracking ray onto a plane normal to the mean
                     bearing at the dead-reckoned nearest-threat depth; key is
                     one plane coordinate (u) or the polar angle around the
                     projected centroid (theta). Spatially coherent: adjacent
                     keys = adjacent sky.
  range              triangulated distance to own target: min-gap ray-ray
                     intersection with the best-converging peer (the same
                     computation ladder._ray_gap already does). Untracked ->
                     +inf (widest band), tracking-but-untriangulated -> below
                     that.
  infl               committed rounds in flight (MonitorProjectile counts).
                     Most committed -> widest band, so commitment keeps its far
                     target and the uncommitted are squeezed onto near threats.

RUNG COUNT: bands='perm' gives n distinct bands geometrically interpolated
1.0 -> 0.28 (a true permutation, rung count == mounts); passing a tuple (e.g.
ladder.LADDER) maps ranks many-to-one onto 6 rungs.

State: the network's slot array is fleet-wide. A ctx entry carries it within a
PB tick; a per-mount attribute carries it across ticks (mounts are rebuilt per
run, so nothing leaks between runs/seeds).
"""
import math
from vec import V
from ladder import LADDER, _ray_gap

SENT_UNTRACKED = 1e18    # no projectile track: sort to the wide end
SENT_NOTRI = 1e17        # tracking but no converging peer to triangulate with

_PERM_CACHE = {}
_BATCHER_CACHE = {}


def perm_bands(n, top=1.0, bot=0.28):
    """n distinct range bands, geometric from top to bot (matches LADDER's ends)."""
    got = _PERM_CACHE.get((n, top, bot))
    if got is None:
        if n == 1:
            got = [top]
        else:
            r = (bot / top) ** (1.0 / (n - 1))
            got = [top * (r ** i) for i in range(n)]
        _PERM_CACHE[(n, top, bot)] = got
    return got


def _band_for(rank, n, bands):
    if bands == 'perm':
        return perm_bands(n)[rank]
    return bands[rank * len(bands) // n]


def _cross(a, b):
    return V(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


def _gid(s, i, per_hull):
    return s * per_hull + i


# ------------------------------------------------------------------ observables
def _infl_map(ctx):
    """(ship,idx) -> own rounds in flight, from ctx['own_rounds'] (MonitorProjectile)."""
    got = ctx.get('_sn_infl')
    if got is None:
        got = {}
        for s, i, _p, _v in ctx.get('own_rounds') or []:
            got[(s, i)] = got.get((s, i), 0) + 1
        ctx['_sn_infl'] = got
    return got


def _sky(ctx):
    """(ship,idx) -> (u, v, theta): each tracking ray projected onto the plane
    normal to the MEAN bearing at the nearest-threat depth. Removes most of the
    mount-position parallax, so two mounts on the same torpedo project to nearby
    points. Own bearings + dead-reckoned nearest only."""
    got = ctx.get('_sn_sky')
    if got is not None:
        return got
    got = {}
    bs = ctx.get('bearings') or []
    if len(bs) >= 1:
        n = V(0, 0, 0)
        c = V(0, 0, 0)
        for _s, _i, p, d in bs:
            n = n + d
            c = c + p
        c = c / len(bs)
        if n.length() > 1e-9:
            n = n.normalized()
            up = V(0, 0, 1) if abs(n.z) < 0.9 else V(0, 1, 0)
            e1 = _cross(n, up).normalized()
            e2 = _cross(n, e1)
            P = c + n * max(200.0, ctx.get('nearest', 1500.0))
            pts = []
            for s, i, p, d in bs:
                dn = d.dot(n)
                if dn <= 1e-6:
                    continue
                q = p + d * ((P - p).dot(n) / dn)
                pts.append((s, i, (q - P).dot(e1), (q - P).dot(e2)))
            if pts:
                cu = sum(x[2] for x in pts) / len(pts)
                cv = sum(x[3] for x in pts) / len(pts)
                for s, i, u, v in pts:
                    got[(s, i)] = (u, v, math.atan2(v - cv, u - cu))
    ctx['_sn_sky'] = got
    return got


def _tri(ctx, tol=60.0):
    """(ship,idx) -> (gap, range): triangulated distance to own target via the
    best-converging peer ray. O(n^2) — used by the 'range' key (i.e. by the
    omniscient rank policies; the O(n) claim belongs to the sky keys)."""
    ck = '_sn_tri_%g' % tol
    got = ctx.get(ck)
    if got is not None:
        return got
    got = {}
    bs = ctx.get('bearings') or []
    for i in range(len(bs)):
        si, ii, pi, di = bs[i]
        for j in range(i + 1, len(bs)):
            sj, ij, pj, dj = bs[j]
            r = _ray_gap(pi, di, pj, dj)
            if r is None or r[0] > tol:
                continue
            gap, mid = r
            for (s, x, p) in ((si, ii, pi), (sj, ij, pj)):
                cur = got.get((s, x))
                if cur is None or gap < cur[0]:
                    got[(s, x)] = (gap, (mid - p).length())
    ctx[ck] = got
    return got


def _keys(ctx, mode):
    """keys[gid] for every mount; LARGER key -> wider band (rank 0)."""
    ck = '_sn_keys_' + mode
    got = ctx.get(ck)
    if got is not None:
        return got
    n = ctx['n_mounts']
    ph = ctx['per_hull']
    if mode == 'infl':
        keys = [0.0] * n
        for (s, i), cnt in _infl_map(ctx).items():
            keys[_gid(s, i, ph)] = float(cnt)
    elif mode in ('sky_u', 'sky_theta'):
        keys = [SENT_UNTRACKED] * n
        for (s, i), (u, v, th) in _sky(ctx).items():
            keys[_gid(s, i, ph)] = u if mode == 'sky_u' else th
    elif mode == 'range':
        keys = [SENT_UNTRACKED] * n
        for s, row in enumerate(ctx['tracking']):
            for i, tr in enumerate(row):
                if tr:
                    keys[_gid(s, i, ph)] = SENT_NOTRI
        for (s, i), (gap, rng) in _tri(ctx).items():
            keys[_gid(s, i, ph)] = rng
    else:
        raise ValueError(mode)
    ctx[ck] = keys
    return keys


# ------------------------------------------------------------------ networks
def _batcher_stages(n):
    """Knuth merge-exchange (TAOCP Alg. M) as parallel stages; any n."""
    got = _BATCHER_CACHE.get(n)
    if got is not None:
        return got
    stages = []
    t = 1
    while (1 << t) < n:
        t += 1
    p = 1 << (t - 1)
    while p > 0:
        q = 1 << (t - 1)
        r = 0
        d = p
        while True:
            stage = [(i, i + d) for i in range(n - d) if (i & p) == r]
            if stage:
                seen = set()
                for a, b in stage:
                    assert a not in seen and b not in seen
                    seen.add(a)
                    seen.add(b)
                stages.append(stage)
            if q == p:
                break
            d = q - p
            r = p
            q >>= 1
        p >>= 1
    _BATCHER_CACHE[n] = stages
    return stages


def _advance_net(m, ctx, key, schedule, sink):
    """Advance the comparator network ONE scheduled stage this PB tick.
    Slot 0 = largest key = widest band. Swap only on strict key inversion, so
    sentinel ties stay put. Records (t, swaps, inversions, n_keyed) per tick."""
    tag = '_sn_net_%s_%s' % (key, schedule)
    st = ctx.get(tag)
    if st is None:
        st = getattr(m, '_sn_net', None)
        if st is None:
            n = ctx['n_mounts']
            st = {'order': list(range(n)), 'slot': list(range(n)), 'phase': 0,
                  'last': None, 'hist': [], 'n': n}
            if sink is not None:
                sink.append(st)
        ctx[tag] = st
    m._sn_net = st
    if st['last'] != ctx['t']:
        st['last'] = ctx['t']
        n = st['n']
        keys = _keys(ctx, key)
        order = st['order']
        if schedule == 'oe':
            pairs = [(i, i + 1) for i in range(st['phase'] & 1, n - 1, 2)]
        elif schedule == 'batcher':
            stages = _batcher_stages(n)
            pairs = stages[st['phase'] % len(stages)]
        else:
            raise ValueError(schedule)
        swaps = 0
        for a, b in pairs:
            if keys[order[a]] < keys[order[b]]:
                order[a], order[b] = order[b], order[a]
                swaps += 1
        st['phase'] += 1
        for pos, g in enumerate(order):
            st['slot'][g] = pos
        inv = sum(1 for x in range(n) for y in range(x + 1, n)
                  if keys[order[x]] < keys[order[y]])
        nk = sum(1 for k in keys if k < SENT_NOTRI)
        st['hist'].append((ctx['t'], swaps, inv, nk))
    return st


def _rank_of(m, ctx, key, source, schedule, sink):
    ph = ctx['per_hull']
    g = _gid(m._ship, m._idx, ph)
    if source == 'direct':
        ck = '_sn_rank_' + key
        got = ctx.get(ck)
        if got is None:
            keys = _keys(ctx, key)
            n = ctx['n_mounts']
            order = sorted(range(n), key=lambda x: (-keys[x], x))
            got = [0] * n
            for pos, gg in enumerate(order):
                got[gg] = pos
            ctx[ck] = got
        return got[g]
    st = _advance_net(m, ctx, key, schedule, sink)
    return st['slot'][g]


# ------------------------------------------------------------------ policies
def rank_ladder(key='sky_u', bands='perm', source='direct', schedule='oe'):
    """rung = rank in the key order. source='direct' is the omniscient sort;
    source='net' maintains the rank incrementally with `schedule`."""
    def pol(m, ctx):
        rank = _rank_of(m, ctx, key, source, schedule, pol.states)
        return True, m._base_range * _band_for(rank, ctx['n_mounts'], bands)
    pol.states = []
    return pol


def staggered_window(key='infl', lo=100.0, hi=900.0, source='direct',
                     schedule='oe'):
    """window_nearest with a rank-ordered STAGGER inside the window: everyone
    concentrates at the leading edge, but rank spreads the gates lo..hi past
    nearest so co-targeting mounts sit behind different gates."""
    def pol(m, ctx):
        n = ctx['n_mounts']
        rank = _rank_of(m, ctx, key, source, schedule, pol.states)
        frac = 1.0 - (rank / (n - 1) if n > 1 else 0.0)   # rank 0 -> hi
        return True, min(m._base_range, ctx['nearest'] + lo + (hi - lo) * frac)
    pol.states = []
    return pol


def sorted_ladder(tol=40.0, burst=14, bands=LADDER, cool_frac=0.20, dwell=0.35,
                  window=1, key='sky_u', source='sort', schedule='oe',
                  measure=False):
    """Full ladder semantics; conflicts found by ray-testing only pairs within
    `window` positions of each other in the key-sorted order (O(n*window) tests).
    source='sort' sorts fresh each tick; source='net' reads the comparator
    network's maintained order (fully O(n) per tick)."""
    def conflicts(m, ctx):
        got = ctx.get('_sn_adjconf')
        if got is not None:
            return got
        bs = ctx.get('bearings') or []
        ph = ctx['per_hull']
        ent = {(s, i): (p, d) for s, i, p, d in bs}
        if source == 'sort':
            keys = _keys(ctx, key)
            trk = sorted(ent.keys(),
                         key=lambda si: (keys[_gid(si[0], si[1], ph)], si))
        else:
            st = _advance_net(m, ctx, key, schedule, pol.states)
            trk = sorted(ent.keys(),
                         key=lambda si: st['slot'][_gid(si[0], si[1], ph)])
        pairs = []
        for k in range(1, window + 1):
            for x in range(len(trk) - k):
                A, B = trk[x], trk[x + k]
                r = _ray_gap(ent[A][0], ent[A][1], ent[B][0], ent[B][1])
                if r is not None and r[0] <= tol:
                    pairs.append((A, B))
        if measure:
            full = 0
            lst = list(ent.items())
            for i2 in range(len(lst)):
                for j2 in range(i2 + 1, len(lst)):
                    r = _ray_gap(lst[i2][1][0], lst[i2][1][1],
                                 lst[j2][1][0], lst[j2][1][1])
                    if r is not None and r[0] <= tol:
                        full += 1
            pol.stats.append((ctx['t'], len(pairs), full, len(trk)))
        ctx['_sn_adjconf'] = pairs
        return pairs

    def pol(m, ctx):
        st = getattr(m, '_sl', None)
        if st is None:
            st = m._sl = {'rung': m._idx % len(bands), 'base': m.shots_fired,
                          'since': ctx['t'], 'bottom_at': None}
        rung = st['rung']
        demoted = False
        me = (m._ship, m._idx)
        for A, B in conflicts(m, ctx):
            if A != me and B != me:
                continue
            other = B if A == me else A
            infl = _infl_map(ctx)
            mine = infl.get(me, 0)
            theirs = infl.get(other, 0)
            if mine < theirs or (mine == theirs and me > other):
                if rung < len(bands) - 1:
                    rung += 1
                    demoted = True
                break
        if not demoted and m.shots_fired - st['base'] >= burst:
            if rung < len(bands) - 1:
                rung += 1
                demoted = True
            st['base'] = m.shots_fired
        if demoted:
            st['base'] = m.shots_fired
            st['since'] = ctx['t']
            st['bottom_at'] = ctx['t'] if rung == len(bands) - 1 else None
        if rung == len(bands) - 1:
            if st['bottom_at'] is None:
                st['bottom_at'] = ctx['t']
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and ctx['t'] - st['bottom_at'] >= dwell:
                rung = 0
                st['base'] = m.shots_fired
                st['since'] = ctx['t']
                st['bottom_at'] = None
        st['rung'] = rung
        return True, m._base_range * bands[rung]

    pol.stats = []
    pol.states = []
    return pol
