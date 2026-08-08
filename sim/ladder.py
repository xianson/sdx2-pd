"""Ray-intersection de-confliction on a range ladder.

The scheme:
  1. Mounts sit on a range LADDER (bands as fractions of base tracking range).
  2. Each PB tick, take the bearing of every mount that reports a projectile track
     and test the rays pairwise. Two rays whose closest approach is within
     `tol` metres, both in front of their muzzles, are engaging the SAME torpedo.
  3. On a conflict, DEMOTE one of the pair a rung. A tighter tracking range makes
     that (farther) torpedo ineligible, so the mount re-acquires something closer.
     That is genuine target de-confliction built out of nothing but a range gate.
  4. A mount that has fired `burst` rounds at its current rung also demotes, so
     commitment spreads down the ladder instead of piling up.
  5. At the bottom rung, once cooled, the mount cycles back to the top.

WHAT MAKES THIS LEGAL
  ctx['bearings']  = GetWeaponAzimuthMatrix x GetWeaponElevationMatrix per mount
                     (CoreSystemsPbApi.cs:138-139, PB-registered ApiBackend.cs:222)
                     plus the block's own position. DIRECTION ONLY.
  ctx['tracking']  = GetWeaponTarget(...).Item2, the per-mount "on a projectile"
                     boolean (ApiBackend.cs:1074). No identity, no position.
  m._in_flight     = own MonitorProjectile spawn/despawn callbacks.
Nothing here reads a torpedo object or a target identity. Identity does not exist:
Target.SetTargetId writes -1 for every projectile target.

FIDELITY CAVEAT that matters for `tol`: the sim's bearing points at the target's
CURRENT position, whereas a real turret points at the PREDICTED INTERCEPT. Two mounts
at different ranges therefore aim at slightly different points for the same torpedo,
so in game the rays converge less tightly than they do here and `tol` would need to be
larger. Treat any tol below ~50 m as optimistic relative to the real game.
"""
import math

LADDER = (1.0, 0.8, 0.65, 0.5, 0.38, 0.28)


def _ray_gap(p1, d1, p2, d2):
    """Closest approach between two rays, or None if parallel / behind a muzzle.

    Returns (gap_metres, midpoint) where midpoint is the triangulated target
    estimate -- the same computation that recovers RANGE from pure bearings.
    """
    a = d1.dot(d1)
    b = d1.dot(d2)
    c = d2.dot(d2)
    w0 = p1 - p2
    d = d1.dot(w0)
    e = d2.dot(w0)
    denom = a * c - b * b
    if abs(denom) < 1e-9:
        return None
    s = (b * e - c * d) / denom
    u = (a * e - b * d) / denom
    if s <= 0.0 or u <= 0.0:
        return None                       # convergence is behind one of them
    q1 = p1 + d1 * s
    q2 = p2 + d2 * u
    return (q1 - q2).length(), (q1 + q2) * 0.5


def _conflicts(ctx, tol):
    """Set of (ship, idx) pairs sharing a target, computed once per PB tick.

    Cached on ctx, which is rebuilt every PB tick, so the cache cannot go stale.
    O(n^2) in tracking mounts -- 24 mounts is 276 pairs, trivial for a PB.
    """
    key = '_conf_%g' % tol
    got = ctx.get(key)
    if got is not None:
        return got
    bs = ctx.get('bearings') or []
    pairs = []
    for i in range(len(bs)):
        si, ii, pi, di = bs[i]
        for j in range(i + 1, len(bs)):
            sj, ij, pj, dj = bs[j]
            r = _ray_gap(pi, di, pj, dj)
            if r is not None and r[0] <= tol:
                pairs.append(((si, ii), (sj, ij)))
    ctx[key] = pairs
    return pairs


def ladder_deconflict(bands=LADDER, tol=40.0, burst=14, cool_frac=0.20,
                      dwell=0.35, demote_on_conflict=True):
    """The full scheme. `burst` rounds per rung, `tol` metres for ray convergence.

    Tie-break on a conflict: demote whichever mount has FEWER rounds already in
    flight. The more-committed mount keeps the target -- its ordnance is already
    spent on it, so moving it would waste that investment, whereas the less
    committed one switches cheaply.
    """
    def pol(m, ctx):
        st = getattr(m, '_lb', None)
        if st is None:
            # start spread across the ladder rather than all at the top, or the
            # first conflict pass has to unwind an 8-way pile-up
            st = m._lb = {'rung': m._idx % len(bands), 'base': m.shots_fired,
                          'since': ctx['t'], 'bottom_at': None}
        rung = st['rung']

        demoted = False
        if demote_on_conflict:
            me = (m._ship, m._idx)
            for A, B in _conflicts(ctx, tol):
                if A != me and B != me:
                    continue
                other = B if A == me else A
                mine = m._in_flight
                theirs = ctx.get('_infl_by_key', {}).get(other, 0)
                # fewer rounds committed -> this one yields
                if mine < theirs or (mine == theirs and me > other):
                    if rung < len(bands) - 1:
                        rung += 1
                        demoted = True
                    break

        # burst budget at this rung
        if not demoted and m.shots_fired - st['base'] >= burst:
            if rung < len(bands) - 1:
                rung += 1
                demoted = True
            st['base'] = m.shots_fired

        if demoted:
            st['base'] = m.shots_fired
            st['since'] = ctx['t']
            st['bottom_at'] = ctx['t'] if rung == len(bands) - 1 else None

        # bottom of the ladder: cycle back to the top once cooled
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
    return pol


def with_infl_index(pol):
    """Publish an (ship,idx) -> in-flight map on ctx so the tie-break can see peers.

    A PB has this natively: it owns every MonitorProjectile callback, so it knows
    each of its own weapons' committed round counts.
    """
    def wrapped(m, ctx):
        if '_infl_by_key' not in ctx:
            ctx['_infl_by_key'] = {}
        ctx['_infl_by_key'][(m._ship, m._idx)] = m._in_flight
        return pol(m, ctx)
    return wrapped


# --------------------------------------------------------------- references
def static_band(bands=(1.0, 0.75, 0.5, 0.25)):
    def pol(m, ctx):
        return True, m._base_range * bands[m._idx % len(bands)]
    return pol


def window_nearest(margin=500.0):
    """The incumbent champion: clamp tracking range to nearest-threat + margin.

    Forces concentration on the leading edge of the salvo, synthesising the
    closest-first prioritisation SDX2 PDCs lack (ClosestFirst = false).
    """
    def pol(m, ctx):
        return True, min(m._base_range, ctx['nearest'] + margin)
    return pol


def window_plus_ladder(margin=500.0, **kw):
    """Windowing for prioritisation, ladder de-confliction inside the window."""
    lad = ladder_deconflict(**kw)

    def pol(m, ctx):
        _f, r = lad(m, ctx)
        cap = min(m._base_range, ctx['nearest'] + margin)
        return True, min(r if r is not None else m._base_range, cap)
    return pol


def deconflict_only(tol=40.0, bands=LADDER):
    """Ray de-confliction WITHOUT the burst/cycle machinery — isolates whether the
    intersection test itself is worth anything."""
    return ladder_deconflict(bands=bands, tol=tol, burst=10 ** 9,
                             demote_on_conflict=True)


def burst_ladder_only(bands=LADDER, burst=14):
    """Burst-and-descend WITHOUT ray de-confliction — the other half of the split."""
    return ladder_deconflict(bands=bands, burst=burst, demote_on_conflict=False)
