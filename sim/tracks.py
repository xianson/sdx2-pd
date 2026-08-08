"""Triangulated torpedo TRACK LIST + explicit distributed assignment.

Stage 1 (tracker): cluster the per-mount bearing rays (ctx['bearings']) by
pairwise closest approach, least-squares triangulate each cluster, and keep
the estimates across PB ticks as tracks (alpha-beta, dead-reckoned velocity).
Stage 2 (assignment): mount x track benefit matrix -> Bertsekas forward
auction (or greedy, for the cost ablation) over per-track demand slots, then
realise the assignment through the only actuator that exists: each mount's
tracking-range gate, set just above its assigned track's range so every
farther track is ineligible. A gate cannot exclude CLOSER tracks, so the
benefit charges a contamination penalty per closer track.

LEGALITY LINE — this module reads ONLY:
  * ctx['bearings']   GetWeaponAzimuthMatrix x GetWeaponElevationMatrix plus
                      own block world positions. DIRECTION ONLY.
  * ctx['tracking'], ctx['own_rounds'], ctx['nearest'], ctx['t'],
    n_ships/per_hull/n_mounts (own fleet config over IGC)
  * its own mounts' attributes (rof, _base_range, _ship, _idx)
It never imports torpedo2, never touches a torpedo object, and nothing that
carries target identity exists in any input. Truth-based scoring lives in
run_tracks.py and feeds NOTHING back into this module.

Geometry note that dominates the 1-hull case: the sim computes every mount's
aim direction from the SHIP CENTRE, so same-hull same-target rays are exactly
parallel — range is unobservable from a single hull (the brief's ~20 m
baseline, fully degenerate here). Same-hull rays are clustered by a parallel
test and ranged from track history or the legal `nearest` dead-reckoning;
only cross-hull pairs (500–1000 m baseline) genuinely triangulate.
"""
import math
from vec import V


def _unit(v):
    n = v.length()
    return v / n if n > 1e-12 else V(0.0, 0.0, 1.0)


def _closest(p1, d1, p2, d2):
    """Closest approach of two rays with UNIT dirs.
    Returns (gap, midpoint, s, u) or None if parallel."""
    b = d1.dot(d2)
    den = 1.0 - b * b
    if den < 1e-12:
        return None
    w0 = p1 - p2
    d = d1.dot(w0)
    e = d2.dot(w0)
    s = (b * e - d) / den
    u = (e - b * d) / den
    q1 = p1 + d1 * s
    q2 = p2 + d2 * u
    return (q1 - q2).length(), (q1 + q2) * 0.5, s, u


def _lsq_point(lines):
    """Point minimising sum of squared distances to lines [(anchor, unit dir)].
    Solves  sum(I - d d^T) p = sum(I - d d^T) a  by Cramer. None if singular."""
    m00 = m01 = m02 = m11 = m12 = m22 = 0.0
    bx = by = bz = 0.0
    for a, d in lines:
        xx = 1.0 - d.x * d.x
        yy = 1.0 - d.y * d.y
        zz = 1.0 - d.z * d.z
        xy = -d.x * d.y
        xz = -d.x * d.z
        yz = -d.y * d.z
        m00 += xx; m01 += xy; m02 += xz
        m11 += yy; m12 += yz; m22 += zz
        bx += xx * a.x + xy * a.y + xz * a.z
        by += xy * a.x + yy * a.y + yz * a.z
        bz += xz * a.x + yz * a.y + zz * a.z
    det = (m00 * (m11 * m22 - m12 * m12)
           - m01 * (m01 * m22 - m12 * m02)
           + m02 * (m01 * m12 - m11 * m02))
    if abs(det) < 1e-7:
        return None
    px = (bx * (m11 * m22 - m12 * m12)
          - m01 * (by * m22 - m12 * bz)
          + m02 * (by * m12 - m11 * bz)) / det
    py = (m00 * (by * m22 - bz * m12)
          - bx * (m01 * m22 - m12 * m02)
          + m02 * (m01 * bz - by * m02)) / det
    pz = (m00 * (m11 * bz - by * m12)
          - m01 * (m01 * bz - by * m02)
          + bx * (m01 * m12 - m11 * m02)) / det
    return V(px, py, pz)


class Track:
    __slots__ = ('tid', 'pos', 'vel', 'misses', 'quality', 'n_mounts', 'born')

    def __init__(self, tid, pos, vel, quality, t):
        self.tid = tid
        self.pos = pos
        self.vel = vel
        self.quality = quality        # '3d' | 'brg'
        self.misses = 0
        self.n_mounts = 0
        self.born = t


class Tracker:
    """Everything here is once-per-PB-tick, cached on ctx by the policy."""

    def __init__(self, tol=60.0, gate3d=300.0, gatebrg=130.0, margin=80.0,
                 margin_brg=220.0, need=22.0, duty=0.5, gamma=0.75, kmax=5,
                 hold_bonus=40.0, persist=20.0, pen_closer=8.0, dist_w=5.0,
                 fallback=500.0, floor_m=0.0, cap_w=0.0, front=0.0,
                 scouts=0, miss_max=3, done=0.0, mode='auction'):
        self.tol = tol
        self.gate3d = gate3d
        self.gatebrg = gatebrg
        self.margin = margin
        self.margin_brg = margin_brg
        self.need = need
        self.duty = duty
        self.gamma = gamma
        self.kmax = kmax
        self.hold_bonus = hold_bonus
        self.persist = persist
        self.pen_closer = pen_closer
        self.dist_w = dist_w
        self.fallback = fallback
        self.floor_m = floor_m         # gate >= nearest+floor: keep the deck
        self.cap_w = cap_w             # gate <= nearest+cap: window everything
        self.front = front             # assign only tracks within nearest+front
        self.scouts = scouts           # every Nth unassigned mount stays at
                                       # base range to keep feeding the tracker
        self.miss_max = miss_max
        self.done = done               # rounds in flight at which a track is
                                       # considered serviced: value decays with
                                       # commitment, slots stop at the threshold
                                       # (track-aware analogue of burst=14)
        self.mode = mode
        self.rof = 1800.0
        self.base_range = 3000.0
        self.reset()

    def reset(self):
        self.last_t = None
        self.tracks = []
        self.next_tid = 0
        self.closing = 1100.0          # m/s, refined from d(nearest)/dt
        self.prev_nearest = None
        self.centers = {}              # ship -> [sum V, n] running muzzle mean
        self.mount_obj = {}            # (ship, idx) -> mount; ONLY .bears() is
                                       # read (own turret arc = block WorldMatrix
                                       # + definition, a PB has both). Never
                                       # touch ._wc / .held through this.
        self.mount_track = {}          # (ship, idx) -> tid, from this tick's clusters
        self.prev_assign = {}          # (ship, idx) -> tid, from last assignment
        self.last_clusters = []        # [(members [(ship,idx)...], tid|None)] for measurement
        # legal-side realisation + cost counters
        self.real_ok = 0
        self.real_chk = 0
        self.cost = dict(ticks=0, pairs=0, lsq=0, assoc=0, ben=0, auction=0,
                         rounds_assoc=0)

    # ------------------------------------------------------------- helpers
    def center(self, si):
        rec = self.centers.get(si)
        return rec[0] / rec[1] if rec else None

    def center0(self):
        c = self.center(0)
        if c is not None:
            return c
        acc, n = V(0, 0, 0), 0
        for rec in self.centers.values():
            acc = acc + rec[0] / rec[1]
            n += 1
        return acc / n if n else V(0, 0, 0)

    # ------------------------------------------------------------ stage 1
    def update(self, ctx):
        t = ctx['t']
        if self.last_t is not None and t < self.last_t:
            self.reset()               # run/wave restarted (PB reboot detection)
        dt = (t - self.last_t) if self.last_t is not None else 0.0
        self.last_t = t
        self.cost['ticks'] += 1

        # closing-speed estimate from the legal nearest dead-reckoning
        if self.prev_nearest is not None and dt > 1e-6:
            c = (self.prev_nearest - ctx['nearest']) / dt
            if 200.0 < c < 2200.0:
                self.closing += 0.3 * (c - self.closing)
        self.prev_nearest = ctx['nearest']

        bs = ctx.get('bearings') or []
        for si, ii, mw, dw in bs:
            rec = self.centers.get(si)
            if rec is None:
                self.centers[si] = [mw.copy(), 1]
            else:
                rec[0] = rec[0] + mw
                rec[1] += 1

        # coast all tracks to now
        for tr in self.tracks:
            if dt > 0:
                tr.pos = tr.pos + tr.vel * dt
            tr.n_mounts = 0

        # legal-side realisation check on LAST tick's assignment: does the
        # mount's current bearing ray pass near its assigned track?
        by_tid = {tr.tid: tr for tr in self.tracks}
        if self.prev_assign:
            in_bear = {(si, ii): _unit(dw) for si, ii, _mw, dw in bs}
            for key, tid in self.prev_assign.items():
                tr = by_tid.get(tid)
                d = in_bear.get(key)
                if tr is None or d is None:
                    continue
                a = self.center(key[0])
                if a is None:
                    continue
                w = tr.pos - a
                along = w.dot(d)
                if along <= 0:
                    continue
                cross = (w - d * along).length()
                self.real_chk += 1
                if cross <= 100.0:
                    self.real_ok += 1

        # ---- rays anchored at estimated ship centres ----------------------
        rays = []
        for si, ii, _mw, dw in bs:
            a = self.center(si)
            rays.append((si, ii, a, _unit(dw)))

        # ---- pairwise clustering (union-find with per-ship line consistency)
        n = len(rays)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        edges = []
        PAR = 1.0 - 5e-7               # < ~1 mrad: same-hull identical bearing
        for i in range(n):
            si, _ii, ai, di = rays[i]
            for j in range(i + 1, n):
                sj, _ij, aj, dj = rays[j]
                self.cost['pairs'] += 1
                if si == sj:
                    if di.dot(dj) > PAR:
                        edges.append((0.0, i, j))
                    continue
                r = _closest(ai, di, aj, dj)
                if r is None:
                    continue
                gap, _mid, s, u = r
                if gap <= self.tol and 120.0 < s < 6000.0 and 120.0 < u < 6000.0:
                    edges.append((gap, i, j))
        edges.sort(key=lambda e: e[0])

        lines = [dict([(rays[i][0], (rays[i][2], rays[i][3]))]) for i in range(n)]
        for gap, i, j in edges:
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            # consistency: merged cluster must stay one line per ship, and all
            # cross-ship line pairs must still converge
            ok = True
            for sa, (aa, da) in lines[ri].items():
                for sb, (ab, db) in lines[rj].items():
                    if sa == sb:
                        if da.dot(db) <= PAR:
                            ok = False
                    else:
                        r = _closest(aa, da, ab, db)
                        if r is None or r[0] > self.tol * 1.6:
                            ok = False
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                continue
            parent[rj] = ri
            lines[ri].update(lines[rj])

        clusters = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(i)

        # ---- per-cluster estimate ------------------------------------------
        c0 = self.center0()
        nearest = ctx['nearest']
        obs = []                        # (kind, payload, members)
        for root, idxs in clusters.items():
            members = [(rays[i][0], rays[i][1]) for i in idxs]
            lns = list(lines[root].values())
            p = None
            if len(lns) >= 2:
                # angular spread gate: a 3D fix from near-parallel lines is
                # noise-amplified garbage, treat as bearing-only instead
                spread = 0.0
                for a in range(len(lns)):
                    for b in range(a + 1, len(lns)):
                        spread = max(spread, 1.0 - abs(lns[a][1].dot(lns[b][1])))
                if spread > 1.25e-3:
                    self.cost['lsq'] += 1
                    p = _lsq_point(lns)
                    if p is not None:
                        for a, d in lns:
                            w = p - a
                            s = w.dot(d)
                            if not (100.0 < s < 6000.0) or \
                               (w - d * s).length() > 150.0:
                                p = None
                                break
            if p is not None:
                obs.append(('3d', p, members))
            else:
                a, d = lns[0]
                obs.append(('brg', (a, d), members))

        # ---- association (greedy nearest, 3d first) ------------------------
        live = [tr for tr in self.tracks]
        used_tr = set()
        used_obs = set()
        cand = []
        for oi, (kind, payload, _mem) in enumerate(obs):
            if kind != '3d':
                continue
            for tr in live:
                self.cost['assoc'] += 1
                dd = (payload - tr.pos).length()
                if dd <= self.gate3d:
                    cand.append((dd, oi, tr))
        cand.sort(key=lambda x: x[0])
        matches = {}
        for dd, oi, tr in cand:
            if oi in used_obs or tr.tid in used_tr:
                continue
            used_obs.add(oi)
            used_tr.add(tr.tid)
            matches[oi] = tr
        cand = []
        for oi, (kind, payload, _mem) in enumerate(obs):
            if kind != 'brg' or oi in used_obs:
                continue
            a, d = payload
            for tr in live:
                if tr.tid in used_tr:
                    continue
                self.cost['assoc'] += 1
                w = tr.pos - a
                along = w.dot(d)
                if along <= 0:
                    continue
                cross = (w - d * along).length()
                if cross <= self.gatebrg:
                    cand.append((cross, oi, tr))
        cand.sort(key=lambda x: x[0])
        for dd, oi, tr in cand:
            if oi in used_obs or tr.tid in used_tr:
                continue
            used_obs.add(oi)
            used_tr.add(tr.tid)
            matches[oi] = tr

        # ---- update / birth -------------------------------------------------
        self.mount_track = {}
        self.last_clusters = []
        alpha, beta = 0.55, 0.22
        for oi, (kind, payload, mem) in enumerate(obs):
            tr = matches.get(oi)
            if tr is not None:
                if kind == '3d':
                    res = payload - tr.pos
                    tr.pos = tr.pos + res * alpha
                    if dt > 1e-6:
                        tr.vel = tr.vel + res * (beta / max(dt, 1e-3))
                    tr.quality = '3d'
                else:
                    a, d = payload
                    w = tr.pos - a
                    along = max(150.0, w.dot(d))
                    q = a + d * along          # nearest ray point at predicted range
                    res = q - tr.pos           # pure cross-track correction
                    tr.pos = tr.pos + res * 0.6
                    if dt > 1e-6:
                        tr.vel = tr.vel + res * (0.25 / max(dt, 1e-3))
                tr.misses = 0
            else:
                # birth
                if kind == '3d':
                    p = payload
                else:
                    a, d = payload
                    # range unobservable: put it on the ray at the legal
                    # salvo-front range (|p - c0| = nearest + 100)
                    r_est = self._range_on_ray(a, d, c0, nearest + 100.0)
                    p = a + d * r_est
                v0 = _unit(c0 - p) * self.closing
                tr = Track(self.next_tid, p, v0, kind, t)
                self.next_tid += 1
                self.tracks.append(tr)
            # clamp speed to torpedo kinematics
            sp = tr.vel.length()
            if sp > 2200.0:
                tr.vel = tr.vel * (2200.0 / sp)
            elif sp < 150.0:
                tr.vel = _unit(c0 - tr.pos) * self.closing
            tr.n_mounts = len(mem)
            for key in mem:
                self.mount_track[key] = tr.tid
            self.last_clusters.append((mem, tr.tid))

        # miss-out / cull / merge
        matched_tids = {tr.tid for tr in matches.values()} | \
                       {self.mount_track[k] for k in self.mount_track}
        keep = []
        for tr in self.tracks:
            if tr.tid not in matched_tids:
                tr.misses += 1
            if tr.misses < self.miss_max and (tr.pos - c0).length() > 60.0:
                keep.append(tr)
        keep.sort(key=lambda tr: tr.born)
        merged = []
        for tr in keep:
            dup = None
            for other in merged:
                if (tr.pos - other.pos).length() < 70.0:
                    dup = other
                    break
            if dup is None:
                merged.append(tr)
            else:
                dup.n_mounts += tr.n_mounts
                for key, tid in list(self.mount_track.items()):
                    if tid == tr.tid:
                        self.mount_track[key] = dup.tid
        self.tracks = merged[:64]

    @staticmethod
    def _range_on_ray(a, d, c0, R):
        """Smallest r>0 with |a + d*r - c0| = R, else fallback R."""
        w = a - c0
        b = 2.0 * d.dot(w)
        c = w.length_sq() - R * R
        disc = b * b - 4.0 * c
        if disc < 0.0:
            return max(300.0, R)
        r = (-b - math.sqrt(disc)) * 0.5
        if r < 200.0:
            r = (-b + math.sqrt(disc)) * 0.5
        return min(6000.0, max(300.0, r))

    # ------------------------------------------------------------ stage 2
    def assign(self, ctx):
        out = {}
        tracks = self.tracks
        if not tracks:
            self.prev_assign = {}
            return out
        c0 = self.center0()
        closing = max(self.closing, 200.0)

        # per-track state
        rng0 = [(tr.pos - c0).length() for tr in tracks]
        tti = [max(0.05, (r - 150.0) / closing) for r in rng0]

        # own committed rounds per track (round ray passes near the track)
        comm = [0] * len(tracks)
        for _s, _i, pos, vel in ctx.get('own_rounds') or []:
            dv = _unit(vel)
            best = None
            for k, tr in enumerate(tracks):
                self.cost['rounds_assoc'] += 1
                w = tr.pos - pos
                along = w.dot(dv)
                if along <= 0:
                    continue
                cross = (w - dv * along).length()
                if cross <= 80.0 and (best is None or cross < best[0]):
                    best = (cross, k)
            if best is not None:
                comm[best[1]] += 1

        # demand slots
        order = sorted(range(len(tracks)), key=lambda k: tti[k])
        if self.front:                 # assign only the leading edge; depth is
            lim = ctx['nearest'] + self.front   # someone else's problem
            order = [k for k in order if rng0[k] <= lim]
        slots = []                     # (track index, value)
        for k in order:
            if self.done and comm[k] >= self.done:
                continue               # enough ordnance en route; move on
            need = max(4.0, self.need - 0.7 * comm[k])
            usable = max(0.3, tti[k] - rng0[k] / 3000.0)
            per_mount = max(1.0, (self.rof / 60.0) * usable * self.duty)
            K = min(self.kmax, max(1, int(math.ceil(need / per_mount))))
            v = 100.0 / max(tti[k], 0.25)
            if self.done:
                v *= max(0.15, 1.0 - comm[k] / self.done)
            for c in range(K):
                slots.append((k, v * (self.gamma ** c)))
        nm_total = ctx['n_mounts']
        slots = slots[:2 * nm_total]

        # mounts + per-ship geometry
        mounts = []
        for s in range(ctx['n_ships']):
            row = ctx['tracking'][s]
            for i in range(len(row)):
                mounts.append((s, i))
        dists = {}                     # ship -> [dist to each track]
        closer = {}                    # ship -> [# tracks meaningfully closer]
        tdirs = {}                     # ship -> [unit dir to each track]
        for s in range(ctx['n_ships']):
            cs = self.center(s)
            if cs is None:
                continue
            dd = [(tr.pos - cs).length() for tr in tracks]
            dists[s] = dd
            closer[s] = [sum(1 for x in dd if x < dj - 120.0) for dj in dd]
            tdirs[s] = [_unit(tr.pos - cs) for tr in tracks]

        # benefit matrix. The range gate is a one-sided actuator: it can force
        # a mount INWARD (drop the held target, re-acquire closer) but never
        # OUTWARD (the hold path keeps any target inside the gate), so a slot
        # farther out than the mount's currently-held track is unrealisable
        # and gets None.
        tid_rng = {tracks[k].tid: rng0[k] for k in range(len(tracks))}
        ben = []
        for s, i in mounts:
            if s not in dists:
                ben.append(None)
                continue
            row = []
            held = self.mount_track.get((s, i))
            held_rng = tid_rng.get(held) if held is not None else None
            prev = self.prev_assign.get((s, i))
            mo = self.mount_obj.get((s, i))
            for k, val in slots:
                self.cost['ben'] += 1
                d = dists[s][k]
                if d > self.base_range:
                    row.append(None)
                    continue
                # turret-arc feasibility: own mount orientation only. Ships are
                # unrotated here so world==hull-local; in game this is the
                # block WorldMatrix transform.
                if mo is not None and not mo.bears(tdirs[s][k]):
                    row.append(None)
                    continue
                if held_rng is not None and held != tracks[k].tid \
                        and rng0[k] > held_rng + 150.0:
                    row.append(None)          # outward move: unrealisable
                    continue
                b = val - self.dist_w * d / 1000.0 \
                    - self.pen_closer * closer[s][k]
                if held is not None and held == tracks[k].tid:
                    b += self.hold_bonus
                if prev is not None and prev == tracks[k].tid:
                    b += self.persist
                row.append(b)
            ben.append(row)

        if self.mode == 'auction':
            asg = self._auction(ben, len(slots))
        else:
            asg = self._greedy(ben, slots)

        self.prev_assign = {}
        n_un = 0
        for mi, sj in enumerate(asg):
            s, i = mounts[mi]
            if sj < 0:
                # unassigned: never withhold; window to the salvo front so the
                # spare capacity concentrates instead of scattering. Every Nth
                # one stays a SCOUT at base range: gates near the front blind
                # the tracker to depth, someone has to keep observing it.
                n_un += 1
                if self.scouts and n_un % self.scouts == 0:
                    out[(s, i)] = None
                else:
                    out[(s, i)] = min(self.base_range,
                                      ctx['nearest'] + self.fallback)
                continue
            k, _v = slots[sj]
            tr = tracks[k]
            margin = self.margin if tr.quality == '3d' else self.margin_brg
            r = dists[s][k] + margin
            if self.floor_m:               # acquisition throughput floor
                r = max(r, ctx['nearest'] + self.floor_m)
            if self.cap_w:                 # leading-edge concentration cap
                r = min(r, ctx['nearest'] + self.cap_w)
            r = min(self.base_range, max(300.0, r))
            out[(s, i)] = r
            self.prev_assign[(s, i)] = tr.tid
        return out

    def _auction(self, ben, ns):
        nm = len(ben)
        asg = [-1] * nm
        if ns == 0:
            return asg
        vmax = 1.0
        for row in ben:
            if row:
                for b in row:
                    if b is not None and b > vmax:
                        vmax = b
        eps = 0.05 * vmax              # coarse eps: assignment within 5% of
        price = [0.0] * ns             # optimal is plenty against gate noise
        owner = [-1] * ns
        stack = [i for i in range(nm) if ben[i] is not None]
        guard = 0
        while stack and guard < 2000:
            guard += 1
            self.cost['auction'] += 1
            i = stack.pop()
            row = ben[i]
            bj, bv, sv = -1, -1e18, -1e18
            for j in range(ns):
                b = row[j]
                if b is None:
                    continue
                v = b - price[j]
                if v > bv:
                    sv, bv, bj = bv, v, j
                elif v > sv:
                    sv = v
            if bj < 0:
                continue
            price[bj] += (bv - sv if sv > -1e17 else 1.0) + eps
            if owner[bj] >= 0:
                asg[owner[bj]] = -1
                stack.append(owner[bj])
            owner[bj] = i
            asg[i] = bj
        return asg

    def _greedy(self, ben, slots):
        nm = len(ben)
        asg = [-1] * nm
        taken = [False] * nm
        order = sorted(range(len(slots)), key=lambda j: -slots[j][1])
        for j in order:
            bi, bv = -1, -1e18
            for i in range(nm):
                if taken[i] or ben[i] is None:
                    continue
                b = ben[i][j]
                self.cost['auction'] += 1
                if b is not None and b > bv:
                    bv, bi = b, i
            if bi >= 0:
                taken[bi] = True
                asg[bi] = j
        return asg


# ----------------------------------------------------------------- policies
def track_policy(mode='auction', **kw):
    """pol(m, ctx) -> (fire, range). NEVER withholds fire; unassigned mounts
    run at base range (the governing principle: redirect, never withhold)."""
    trk = Tracker(mode=mode, **kw)

    def pol(m, ctx):
        trk.rof = m.rof
        trk.base_range = m._base_range
        asg = ctx.get('_trk_asg')
        if asg is None:
            trk.update(ctx)
            asg = trk.assign(ctx)
            ctx['_trk_asg'] = asg
        trk.mount_obj[(m._ship, m._idx)] = m   # own-arc registry (bears only)
        return True, asg.get((m._ship, m._idx))

    pol.tracker = trk
    return pol


def track_ladder_policy(mode='auction', ladder_kw=None, **kw):
    """Hybrid: burst-and-descend ladder as the base behaviour, auction
    assignment OVERRIDES the gate for mounts that hold a slot. Asks the
    decision question directly: does explicit assignment add anything on top
    of the reactive ladder?"""
    import ladder as _L
    trk = Tracker(mode=mode, **kw)
    lad = _L.with_infl_index(_L.ladder_deconflict(**(ladder_kw or {})))

    def pol(m, ctx):
        trk.rof = m.rof
        trk.base_range = m._base_range
        asg = ctx.get('_trk_asg')
        if asg is None:
            trk.update(ctx)
            asg = trk.assign(ctx)
            ctx['_trk_asg'] = asg
        trk.mount_obj[(m._ship, m._idx)] = m
        _f, lr = lad(m, ctx)           # keep ladder state ticking regardless
        key = (m._ship, m._idx)
        if key in trk.prev_assign:     # assigned: auction gate wins
            return True, asg.get(key)
        return True, lr

    pol.tracker = trk
    return pol
