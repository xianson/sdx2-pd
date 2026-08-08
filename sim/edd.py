"""Legal EDD gates + spatially-resolved commitment accounting.

Chasing the oracle ablation's two load-bearing pieces with legal observables only:

THREAD 1 — a better legal EDD.
  `window_nearest` is an accidental EDD (uniform speed => deadline order = range
  order) but it clamps every mount to a FLEET-WIDE scalar `nearest + 500`, which
  blinds laterally-offset consorts at close range: at lead-nearest 500 m a 1000 m
  consort is 1118 m from the edge torpedo and its gate is 1000 m. Fix: give each
  HULL a gate reflecting its own geometry.
    edge point   P  = c0 + u * N        u = mean own-bearing direction (hull 0)
    per-hull edge e_s = |P - c_s|       c_s = running mean of own muzzle positions
  N can be the dead-reckoned ctx['nearest'] (same legality as window_nearest) or,
  MORE legally, a cross-hull bearing triangulation (mode='tri'): min range over
  converging cross-ship bearing pairs, dead-reckoned between fixes with a learned
  closing speed. Nothing in 'tri' mode reads ctx['nearest'] at all.

  Depth is then a LADDER OF OFFSETS ABOVE THE MOVING EDGE (edge_ladder) instead of
  fractions of base range: rung gates are e_s + off, burst-and-descend as in
  ladder.py. Offsets may be negative (rung sits below the current edge and idles
  until the salvo closes onto it -- time staggering relative to the edge).

THREAD 2 — commitment accounting without per-target attribution.
  TargetId = -1 kills per-target accounting, but rounds fired at the same torpedo
  CONVERGE geometrically: a round flies at the predicted intercept, a tracking
  mount's bearing points at the same torpedo's current position, and in this
  near-head-on geometry the two rays pass within tens of metres. So for each
  tracking mount count OWN in-flight rounds (ctx['own_rounds'], legal:
  MonitorProjectile + GetProjectileState) whose extrapolated ray converges with
  that mount's bearing ray: that is the fleet's ordnance already committed to the
  REGION this mount is engaging -- per-region, no identity. When it exceeds a
  kill-sized threshold the mount re-aims (never ceases fire):
    commit_act='demote'  step down a rung (tighter gate, closer target)
    commit_act='reroll'  one-tick gate pulse below the engaged region, then jump
                         to the widest rung -- the deliberate re-roll primitive.

LEGALITY: reads ctx['t'], ctx['nearest'] (mode 'ctx' only), ctx['tracking'],
ctx['bearings'], ctx['own_rounds'], n_ships/n_mounts, and own mount state
(shots_fired, heat, _base_range, _idx, _ship, _in_flight). Never touches
ctx['_torps'] / _ship_of / _hull_of, torpedo objects, or round targets.
"""
import math
from ladder import _ray_gap

#: expected rounds to kill a live Health-4 torpedo at P_LIVE ~ 0.41
KILL_ROUNDS = 10.0


def _unit(v):
    n = v.length()
    return v / n if n > 1e-12 else None


# --------------------------------------------------------------- fleet state
def _new_state():
    return {'last_t': None, 'csum': {}, 'cnt': {}, 'u': None,
            'closing': 1100.0, 'tri': None, 'prev_N': None}


def _centers(st):
    return {s: st['csum'][s] / st['cnt'][s] for s in st['csum']}


def _update(ctx, st, mode='ctx', tri_tol=70.0):
    """Once-per-PB-tick fleet computation, cached on ctx. Returns dict with
    per-hull edge distances e[s] (None = unknown, caller keeps base range)."""
    key = '_edd_%d' % id(st)
    got = ctx.get(key)
    if got is not None:
        return got
    t = ctx['t']
    if st['last_t'] is not None and t < st['last_t']:
        fresh = _new_state()
        st.clear()
        st.update(fresh)
    dt = (t - st['last_t']) if st['last_t'] is not None else 0.0
    st['last_t'] = t

    bs = ctx.get('bearings') or []
    for si, ii, mw, dw in bs:
        if si in st['csum']:
            st['csum'][si] = st['csum'][si] + mw
            st['cnt'][si] += 1
        else:
            st['csum'][si] = mw.copy()
            st['cnt'][si] = 1
    cs = _centers(st)
    c0 = cs.get(0)
    if c0 is None and cs:
        c0 = next(iter(cs.values()))

    # threat direction: mean of hull-0 bearing dirs (fallback: all hulls)
    acc = None
    for si, ii, mw, dw in bs:
        if si != 0:
            continue
        u = _unit(dw)
        if u is not None:
            acc = u if acc is None else acc + u
    if acc is None:
        for si, ii, mw, dw in bs:
            u = _unit(dw)
            if u is not None:
                acc = u if acc is None else acc + u
    if acc is not None:
        u_now = _unit(acc)
        if u_now is not None:
            st['u'] = u_now if st['u'] is None else _unit(st['u'] * 0.6 + u_now * 0.4)

    # ---- N: range to the salvo's leading edge, from hull 0 -----------------
    if mode == 'ctx':
        N = ctx['nearest']
    else:
        # cross-hull bearing triangulation only; no ctx['nearest'] anywhere
        rmin = None
        if c0 is not None:
            for i in range(len(bs)):
                si, ii, pi, di = bs[i]
                for j in range(i + 1, len(bs)):
                    sj, ij, pj, dj = bs[j]
                    if si == sj:
                        continue
                    r = _ray_gap(pi, di, pj, dj)
                    if r is not None and r[0] <= tri_tol:
                        rr = (r[1] - c0).length()
                        if rmin is None or rr < rmin:
                            rmin = rr
        coast = None
        if st['tri'] is not None:
            coast = st['tri'] - st['closing'] * dt
        if rmin is not None and coast is not None:
            N = min(rmin, coast)
        elif rmin is not None:
            N = rmin
        else:
            N = coast
        if N is not None:
            N = max(100.0, N)
        st['tri'] = N

    # learned closing speed (for tri coasting), from d(N)/dt
    if N is not None and st['prev_N'] is not None and dt > 1e-6:
        c = (st['prev_N'] - N) / dt
        if 200.0 < c < 2200.0:
            st['closing'] += 0.3 * (c - st['closing'])
    st['prev_N'] = N

    # ---- per-hull edge distance --------------------------------------------
    e = {}
    n_ships = ctx['n_ships']
    if N is None:
        for s in range(n_ships):
            e[s] = None
    elif c0 is not None and st['u'] is not None:
        P = c0 + st['u'] * N
        for s in range(n_ships):
            c_s = cs.get(s)
            e[s] = (P - c_s).length() if c_s is not None else N
    else:
        for s in range(n_ships):
            e[s] = N

    out = {'e': e, 'N': N, 'closing': st['closing']}
    ctx[key] = out
    return out


# ------------------------------------------------- Thread 2: commitment map
def _commit_counts(ctx, tol=80.0):
    """(ship, idx) -> (rounds_converging, est_range) for every TRACKING mount.

    rounds_converging = own in-flight rounds (whole fleet's own weapons -- a PB
    monitors all of them) whose forward ray passes within `tol` of this mount's
    bearing ray: ordnance already committed to the region this mount engages.
    est_range = distance from the mount to the convergence region (median of
    per-round closest-approach distances along the bearing ray).
    """
    key = '_edd_commit_%g' % tol
    got = ctx.get(key)
    if got is not None:
        return got
    out = {}
    rounds = []
    for _s, _i, pos, vel in ctx.get('own_rounds') or []:
        u = _unit(vel)
        if u is not None:
            rounds.append((pos, u))
    for si, ii, mw, dw in ctx.get('bearings') or []:
        u = _unit(dw)
        if u is None:
            continue
        cnt = 0
        ss = []
        for pos, dv in rounds:
            r = _ray_gap(mw, u, pos, dv)
            if r is not None and r[0] <= tol:
                cnt += 1
                ss.append((r[1] - mw).length())
        ss.sort()
        est = ss[len(ss) // 2] if ss else None
        out[(si, ii)] = (cnt, est)
    ctx[key] = out
    return out


# ------------------------------------------------------------------ policies
def hull_window(margin=500.0, mode='ctx'):
    """Thread 1 minimal: per-hull leading-edge window instead of a fleet scalar."""
    st = _new_state()

    def pol(m, ctx):
        fl = _update(ctx, st, mode=mode)
        e = fl['e'].get(m._ship)
        if e is None:
            return True, None
        return True, min(m._base_range, e + margin)
    return pol


#: rung offsets above the moving edge, widest first (metres)
OFFSETS = (1100.0, 800.0, 560.0, 380.0, 230.0, 120.0)


def edge_ladder(offsets=OFFSETS, burst=14, cool_frac=0.20, dwell=0.35,
                mode='ctx', commit_K=None, commit_tol=80.0,
                commit_act='demote', commit_cd=0.5, lo=300.0):
    """Burst-and-descend ladder anchored to the per-hull moving edge.

    Rungs are e_s + offsets[rung] (clamped to [lo, base]); the burst counter
    demotes to a tighter offset, the bottom rung cycles back to the top when
    cool. With commit_K set, a mount whose engaged region already has >= K own
    rounds converging on it re-aims: 'demote' steps a rung, 'reroll' pulses the
    gate below the region for one PB tick then restarts at the widest rung.
    NEVER ceases fire; every trigger is a re-aim.
    """
    st = _new_state()
    nr = len(offsets)

    def pol(m, ctx):
        fl = _update(ctx, st, mode=mode)
        e = fl['e'].get(m._ship)
        s = getattr(m, '_el', None)
        if s is None:
            s = m._el = {'rung': m._idx % nr, 'base': m.shots_fired,
                         'bottom_at': None, 'cd': -1.0, 'pulse': False}
        rung = s['rung']
        t = ctx['t']

        # returning from a re-roll pulse: restart at the widest rung
        if s['pulse']:
            s['pulse'] = False
            rung = 0
            s['base'] = m.shots_fired
            s['bottom_at'] = None

        demoted = False
        # ---- commitment trigger (Thread 2) --------------------------------
        if commit_K is not None and t >= s['cd']:
            got = _commit_counts(ctx, commit_tol).get((m._ship, m._idx))
            if got is not None and got[0] >= commit_K:
                s['cd'] = t + commit_cd
                if commit_act == 'reroll':
                    # full re-roll: gate below EVERYTHING for one PB tick so the
                    # held target is dropped and nothing closer is re-held, then
                    # restart at the widest rung for a fresh deck walk
                    s['pulse'] = True
                    s['base'] = m.shots_fired
                    s['rung'] = rung
                    return True, lo
                if rung < nr - 1:
                    rung += 1
                    demoted = True

        # ---- burst budget ---------------------------------------------------
        if not demoted and m.shots_fired - s['base'] >= burst:
            if rung < nr - 1:
                rung += 1
                demoted = True
            s['base'] = m.shots_fired
        if demoted:
            s['base'] = m.shots_fired
            s['bottom_at'] = t if rung == nr - 1 else None

        # ---- bottom of the ladder: cycle back up when cool ------------------
        if rung == nr - 1:
            if s['bottom_at'] is None:
                s['bottom_at'] = t
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and t - s['bottom_at'] >= dwell:
                rung = 0
                s['base'] = m.shots_fired
                s['bottom_at'] = None

        s['rung'] = rung
        if e is None:
            return True, None
        return True, min(m._base_range, max(lo, e + offsets[rung]))
    return pol


def frac_ladder_commit(bands=(1.0, 0.8, 0.65, 0.5, 0.38, 0.28), burst=14,
                       cool_frac=0.20, dwell=0.35, commit_K=12,
                       commit_tol=80.0, commit_act='demote', commit_cd=0.5,
                       lo=300.0):
    """The incumbent fraction-of-base ladder chassis + the commitment trigger.

    Isolates Thread 2 on the proven chassis: identical to burst_ladder_only
    except a mount also re-aims when its engaged region already has >= K own
    rounds converging on it.
    """
    nr = len(bands)

    def pol(m, ctx):
        s = getattr(m, '_fl', None)
        if s is None:
            s = m._fl = {'rung': m._idx % nr, 'base': m.shots_fired,
                         'bottom_at': None, 'cd': -1.0, 'pulse': False}
        rung = s['rung']
        t = ctx['t']
        if s['pulse']:
            s['pulse'] = False
            rung = 0
            s['base'] = m.shots_fired
            s['bottom_at'] = None

        demoted = False
        if commit_K is not None and t >= s['cd']:
            got = _commit_counts(ctx, commit_tol).get((m._ship, m._idx))
            if got is not None and got[0] >= commit_K:
                s['cd'] = t + commit_cd
                if commit_act == 'reroll':
                    # gate below everything for one PB tick (drop, re-hold
                    # nothing closer), then restart at the widest rung
                    s['pulse'] = True
                    s['base'] = m.shots_fired
                    s['rung'] = rung
                    return True, lo
                if rung < nr - 1:
                    rung += 1
                    demoted = True

        if not demoted and m.shots_fired - s['base'] >= burst:
            if rung < nr - 1:
                rung += 1
                demoted = True
            s['base'] = m.shots_fired
        if demoted:
            s['base'] = m.shots_fired
            s['bottom_at'] = t if rung == nr - 1 else None

        if rung == nr - 1:
            if s['bottom_at'] is None:
                s['bottom_at'] = t
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and t - s['bottom_at'] >= dwell:
                rung = 0
                s['base'] = m.shots_fired
                s['bottom_at'] = None

        s['rung'] = rung
        return True, m._base_range * bands[rung]
    return pol


def hull_cap(inner_factory, margin=600.0, mode='ctx'):
    """Combinator: any policy, capped per hull at (own edge distance + margin).

    The EDD window as a CAP on another policy's gate rather than the gate
    itself -- e.g. the incumbent frac ladder inside a formation-corrected
    window. Never touches the fire decision."""
    st = _new_state()
    inner = inner_factory()

    def pol(m, ctx):
        f, r = inner(m, ctx)
        fl = _update(ctx, st, mode=mode)
        e = fl['e'].get(m._ship)
        if e is None:
            return f, r
        cap = min(m._base_range, e + margin)
        return f, min(r if r is not None else m._base_range, cap)
    return pol


def battery_servo_ladder(offsets=(60.0, 140.0, 260.0, 420.0, 650.0, 950.0),
                         n_probe=2, dn=260.0, up=420.0, lo=150.0,
                         burst=None, cool_frac=0.20, dwell=0.35):
    """Per-HULL edge estimate from the battery's own tracking booleans; NO
    ctx['nearest'], no triangulation.

    Each hull keeps an edge estimate ê. Its bearing-capable mounts (those that
    have ever tracked) are ranked and given static offsets above ê; the
    `n_probe` lowest-offset mounts are the measurement: if every probe tracks,
    ê is above the true edge -> lower it (dn per PB tick, > closing rate); if
    no probe tracks, ê has cut below the edge -> raise it (up); mixed -> hold
    (hysteresis). The rest of the battery rides ê + larger offsets, so depth
    coverage survives while the probes pin the leading edge.

    With `burst` set, non-probe mounts also burst-and-descend through the
    offset list (re-aim, never cease fire), cycling to the widest when cool.
    """
    st = {'last_t': None, 'e': {}, 'seen': {}, 'rank': {}}
    nr = len(offsets)

    def _tick(ctx):
        key = '_bsl_%d' % id(st)
        if ctx.get(key):
            return
        ctx[key] = True
        t = ctx['t']
        if st['last_t'] is not None and t < st['last_t']:
            st['e'].clear()
            st['seen'].clear()
            st['rank'].clear()
        st['last_t'] = t
        tr = ctx['tracking']
        for s in range(ctx['n_ships']):
            seen = st['seen'].setdefault(s, set())
            for i, b in enumerate(tr[s]):
                if b:
                    seen.add(i)
            ranks = {idx: k for k, idx in enumerate(sorted(seen))}
            st['rank'][s] = ranks
            if not ranks:
                continue
            probes = [idx for idx in sorted(seen)][:n_probe]
            e = st['e'].get(s)
            if e is None:
                if any(tr[s][i] for i in probes):
                    st['e'][s] = 3000.0
                continue
            hits = sum(1 for i in probes if tr[s][i])
            if hits == len(probes):
                e -= dn
            elif hits == 0:
                e += up
            st['e'][s] = min(3000.0, max(lo, e))

    def pol(m, ctx):
        _tick(ctx)
        e = st['e'].get(m._ship)
        ranks = st['rank'].get(m._ship) or {}
        rk = ranks.get(m._idx)
        if e is None or rk is None:
            return True, None
        rk = min(rk, nr - 1)
        if burst is not None and rk >= n_probe:
            s = getattr(m, '_bs', None)
            if s is None:
                s = m._bs = {'rung': rk, 'base': m.shots_fired, 'bottom_at': None}
            rung = s['rung']
            if m.shots_fired - s['base'] >= burst:
                if rung > n_probe:
                    rung -= 1          # descend toward the edge
                s['base'] = m.shots_fired
                s['bottom_at'] = ctx['t'] if rung == n_probe else None
            if rung == n_probe:
                if s['bottom_at'] is None:
                    s['bottom_at'] = ctx['t']
                hot = (m.heat / m.max_heat) if m.max_heat else 0.0
                if hot <= cool_frac and ctx['t'] - s['bottom_at'] >= dwell:
                    rung = nr - 1
                    s['base'] = m.shots_fired
                    s['bottom_at'] = None
            s['rung'] = rung
            rk = rung
        return True, min(m._base_range, max(lo, e + offsets[rk]))
    return pol


def frac_ladder_dynburst(base_burst=16, floor=4, scale=0.5, commit_tol=80.0,
                         cool_frac=0.20, dwell=0.35):
    """Commitment-SCALED burst: rung budget shrinks with the ordnance already
    converging on the mount's engaged region. burst_i = base - scale*C_ray,
    clamped to [floor, base]. Heavily-committed regions rotate off fast;
    untouched regions get the full burst. Smooth version of the K-trigger."""
    from ladder import LADDER as bands
    nr = len(bands)

    def pol(m, ctx):
        s = getattr(m, '_db', None)
        if s is None:
            s = m._db = {'rung': m._idx % nr, 'base': m.shots_fired,
                         'bottom_at': None}
        rung = s['rung']
        t = ctx['t']
        got = _commit_counts(ctx, commit_tol).get((m._ship, m._idx))
        c = got[0] if got is not None else 0
        burst = max(floor, base_burst - scale * c)
        if m.shots_fired - s['base'] >= burst:
            if rung < nr - 1:
                rung += 1
            s['base'] = m.shots_fired
            s['bottom_at'] = t if rung == nr - 1 else None
        if rung == nr - 1:
            if s['bottom_at'] is None:
                s['bottom_at'] = t
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and t - s['bottom_at'] >= dwell:
                rung = 0
                s['base'] = m.shots_fired
                s['bottom_at'] = None
        s['rung'] = rung
        return True, m._base_range * bands[rung]
    return pol


def ladder_deconflict_inv(bands=(1.0, 0.8, 0.65, 0.5, 0.38, 0.28), tol=40.0,
                          burst=14, cool_frac=0.20, dwell=0.35):
    """Full ladder with the conflict tie-break INVERTED: the MORE-committed
    mount of a conflicting pair yields (its investment is sunk -- the shared
    target is already dying, so its future rounds are the wasted ones).
    Requires with_infl_index-style publication, done inline."""
    from ladder import _conflicts
    nr = len(bands)

    def pol(m, ctx):
        if '_infl_by_key' not in ctx:
            ctx['_infl_by_key'] = {}
        ctx['_infl_by_key'][(m._ship, m._idx)] = m._in_flight
        s = getattr(m, '_li', None)
        if s is None:
            s = m._li = {'rung': m._idx % nr, 'base': m.shots_fired,
                         'bottom_at': None}
        rung = s['rung']
        demoted = False
        me = (m._ship, m._idx)
        for A, B in _conflicts(ctx, tol):
            if A != me and B != me:
                continue
            other = B if A == me else A
            mine = m._in_flight
            theirs = ctx['_infl_by_key'].get(other, 0)
            # MORE rounds committed -> this one yields (inverted)
            if mine > theirs or (mine == theirs and me > other):
                if rung < nr - 1:
                    rung += 1
                    demoted = True
                break
        if not demoted and m.shots_fired - s['base'] >= burst:
            if rung < nr - 1:
                rung += 1
                demoted = True
            s['base'] = m.shots_fired
        if demoted:
            s['base'] = m.shots_fired
            s['bottom_at'] = ctx['t'] if rung == nr - 1 else None
        if rung == nr - 1:
            if s['bottom_at'] is None:
                s['bottom_at'] = ctx['t']
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and ctx['t'] - s['bottom_at'] >= dwell:
                rung = 0
                s['base'] = m.shots_fired
                s['bottom_at'] = None
        s['rung'] = rung
        return True, m._base_range * bands[rung]
    return pol


def servo_edge(dn=350.0, up=260.0, up_spread=90.0, lo=400.0):
    """Fully-observable per-mount edge servo. NO ctx['nearest'] anywhere.

    Gate shrinks by `dn` per PB tick while the mount reports a projectile track
    (GetWeaponTarget Item2 boolean) and grows by `up` (+ per-mount stagger)
    while it does not. Equilibrium hovers just above the mount's own nearest
    in-arc torpedo -- a per-mount leading-edge tracker built from one boolean.
    The shrink phase repeatedly cuts the held target loose, forcing the
    re-acquisition to take the closest eligible: synthesised ClosestFirst.
    """
    def pol(m, ctx):
        g = getattr(m, '_sv', None)
        if g is None:
            g = m._base_range
        if ctx['tracking'][m._ship][m._idx]:
            g -= dn
        else:
            g += up + up_spread * (m._idx % 4)
        g = min(m._base_range, max(lo, g))
        m._sv = g
        return True, g
    return pol
