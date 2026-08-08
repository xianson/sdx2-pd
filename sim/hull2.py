"""Subsystem-aware 3D hull with live capability degradation.

This is the only hull model. hull.py (a 3D block lattice with no subsystems and no
capability degradation) has been retired; every sim now builds through
shipyard.build_ship(), so they can no longer disagree with each other.

Differences from the retired hull.py:
  * every cell maps to a Component; multi-cell components are ONE object occupying
    many cells, matching SE (a 3x3x3 reactor is a single IMySlimBlock)
  * march() DEDUPES, so a ray crossing three cells of one reactor hits it ONCE —
    hull.py hit it three times, which over-killed large components
  * mass / CoM / inertia / torque / power / thrust are derived from SURVIVING
    components behind a dirty flag, so damage actually costs capability
  * targeting implements WeaponCore's SubSystems priority walk
"""
import math, random
from vec import V
from rcs_gyro import applied_torque, LEFT, RIGHT, UP, DOWN
from components import (CATALOGUE, Component, SUBSYSTEM_ORDER, WC_SUBSYSTEM_ORDER,
                        DECOY, DECOY_ACQUISITION_BUCKET,
                        ROLE_GYRO, ROLE_RCS_COMPUTER, ROLE_RCS, ROLE_DRIVE,
                        POWER, UTILITY, OFFENSE, THRUST, PRODUCTION, ANY)

GRID = 2.5


class Hull:
    def __init__(self, name, nx, ny, nz):
        self.name = name
        self.nx, self.ny, self.nz = nx, ny, nz
        self.cells = {}                 # (i,j,k) -> Component
        self.components = []            # unique installed components
        self.dims = (nx * GRID, ny * GRID, nz * GRID)
        # INCLUSIVE cell range the lattice actually occupies. An even dimension is
        # asymmetric: nx=8 spans -4..+3, so +4 is OUTSIDE the hull. Placing a mount
        # at +nx//2 floats it in space next to the ship, where nothing occludes it.
        self.lo = (-(nx // 2), -(ny // 2), -(nz // 2))
        self.hi = (nx - 1 - nx // 2, ny - 1 - ny // 2, nz - 1 - nz // 2)
        self._dirty = True
        self._cap = None

    def clamp(self, cell):
        return tuple(max(self.lo[a], min(self.hi[a], cell[a])) for a in range(3))

    def on_skin(self, cell):
        return any(cell[a] in (self.lo[a], self.hi[a]) for a in range(3))

    # ---------------------------------------------------------------- building
    def install(self, kind, origin, name=None):
        c = Component(kind, origin, name)
        for cell in c.cells():
            self.cells[cell] = c
        self.components.append(c)
        self._dirty = True
        return c

    def shell(self, kind, depth=1):
        for i in range(self.nx):
            for j in range(self.ny):
                for k in range(self.nz):
                    d = min(i, self.nx - 1 - i, j, self.ny - 1 - j, k, self.nz - 1 - k)
                    cell = (i - self.nx // 2, j - self.ny // 2, k - self.nz // 2)
                    if d < depth and cell not in self.cells:
                        self.install(kind, cell)
        return self

    def fill(self, kind, density=1.0, seed=1):
        rnd = random.Random(seed)
        for i in range(self.nx):
            for j in range(self.ny):
                for k in range(self.nz):
                    cell = (i - self.nx // 2, j - self.ny // 2, k - self.nz // 2)
                    if cell in self.cells:
                        continue
                    if rnd.random() <= density:
                        self.install(kind, cell)
        return self

    def replace_cell(self, kind, cell, name=None):
        """Swap a single-cell component (e.g. skin armour) for another. A hull-mounted
        thruster genuinely occupies an armour slot, so this is the correct model."""
        old = self.cells.get(cell)
        if old is not None:
            if sum(1 for _ in old.cells()) != 1:
                return None                     # refuse to break a multi-cell block
            self.components.remove(old)
            del self.cells[cell]
        return self.install(kind, cell, name)

    def install_replacing(self, kind, origin, name=None):
        """Install at `origin`, displacing the single-cell blocks it lands on.

        A hull-mounted turret genuinely occupies armour slots, so this — not
        install_if_free — is the correct call for anything that belongs ON the skin.
        Refuses (returns None) rather than tear a hole in a multi-cell block.
        """
        size = CATALOGUE[kind]['size']
        ox, oy, oz = origin
        victims = []
        for i in range(size[0]):
            for j in range(size[1]):
                for k in range(size[2]):
                    old = self.cells.get((ox + i, oy + j, oz + k))
                    if old is None:
                        continue
                    if sum(1 for _ in old.cells()) != 1:
                        return None
                    victims.append(old)
        for v in victims:
            for c in v.cells():
                self.cells.pop(c, None)
            self.components.remove(v)
        return self.install(kind, origin, name)

    def free(self, origin, size):
        ox, oy, oz = origin
        sx, sy, sz = size
        for i in range(sx):
            for j in range(sy):
                for k in range(sz):
                    if (ox + i, oy + j, oz + k) in self.cells:
                        return False
        return True

    def install_if_free(self, kind, origin, name=None):
        """Install at `origin` if clear, else search outward for the nearest free
        spot. Never clobbers an existing component — silently destroying a reactor
        by placing a 1x1 on top of it corrupts every downstream number."""
        size = CATALOGUE[kind]['size']
        if self.free(origin, size):
            return self.install(kind, origin, name)
        hx, hy, hz = self.nx // 2, self.ny // 2, self.nz // 2
        ox, oy, oz = origin
        for r in range(1, max(self.nx, self.ny, self.nz)):
            for dz in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        if max(abs(dx), abs(dy), abs(dz)) != r:
                            continue
                        p = (ox + dx, oy + dy, oz + dz)
                        if (p[0] < -hx or p[1] < -hy or p[2] < -hz or
                                p[0] + size[0] > hx or p[1] + size[1] > hy
                                or p[2] + size[2] > hz):
                            continue
                        if self.free(p, size):
                            return self.install(kind, p, name)
        return None      # genuinely no room

    # ------------------------------------------------------------- capability
    def _rcs_thrusters(self, rcs, cx, cy, cz):
        """(direction, offset-in-blocks-from-CoM) for rcs_gyro.applied_torque().

        A hull thruster fires OUT of the face it is welded to, so the skin face it
        sits on is its Orientation.Forward — which is what decides whether its lever
        makes yaw or pitch.
        """
        out = []
        for c in rcs:
            p = c.centre()
            if p[0] <= self.lo[0]:
                d = LEFT
            elif p[0] >= self.hi[0]:
                d = RIGHT
            elif p[1] <= self.lo[1]:
                d = DOWN
            elif p[1] >= self.hi[1]:
                d = UP
            else:
                d = RIGHT if p[0] >= 0 else LEFT      # interior: keep it lateral
            out.append((d, (p[0] - cx / GRID, p[1] - cy / GRID, p[2] - cz / GRID)))
        return out

    def mark_dirty(self):
        self._dirty = True

    def capability(self):
        """Live capability from SURVIVING components. Cached behind a dirty flag."""
        if not self._dirty and self._cap is not None:
            return self._cap
        live = [c for c in self.components if c.alive]
        mass = sum(c.mass for c in live) or 1.0
        cx = sum(c.centre()[0] * GRID * c.mass for c in live) / mass
        cy = sum(c.centre()[1] * GRID * c.mass for c in live) / mass
        cz = sum(c.centre()[2] * GRID * c.mass for c in live) / mass
        Ix = Iy = Iz = 0.0
        for c in live:
            p = c.centre()
            dx, dy, dz = p[0] * GRID - cx, p[1] * GRID - cy, p[2] * GRID - cz
            Ix += c.mass * (dy * dy + dz * dz)
            Iy += c.mass * (dx * dx + dz * dz)
            Iz += c.mass * (dx * dx + dy * dy)
        # Capability is looked up by ROLE, never by a subsystem tag. WeaponCore calls a
        # gyro `Steering`, so the old `subsystem == UTILITY` test here would have
        # silently zeroed every hull's torque the moment the tag was corrected.
        rcs = [c for c in live if c.spec['role'] == ROLE_RCS]
        n_comp = sum(1 for c in live if c.spec['role'] == ROLE_RCS_COMPUTER)
        plain_gyro = sum(c.spec['gyro_n'] for c in live if c.spec['role'] == ROLE_GYRO)

        # RCS Gyros torque, straight through the line-faithful port. This used to be a
        # local approximation that fed every thruster's lever into BOTH the X and Y
        # sums; RCSController L138-164 gives a Left/Right thruster a yaw moment ONLY
        # and an Up/Down one a pitch moment ONLY, so the approximation overstated a
        # 20-RCS Corvette by 1.95x (8.66e8 vs 4.44e8 N.m).
        tau_rcs = 0.0
        if n_comp > 0 and rcs:
            tau_rcs = applied_torque(self._rcs_thrusters(rcs, cx, cy, cz))

        self._cap = dict(
            mass=mass,
            com=V(cx, cy, cz),
            I=V(Ix, Iy, Iz),
            torque=tau_rcs + plain_gyro,
            power_mw=sum(c.spec['power_mw'] for c in live),
            drive_n=sum(c.spec['thrust_n'] for c in live
                        if c.spec['role'] == ROLE_DRIVE),
            rcs_n=sum(c.spec['thrust_n'] for c in rcs),
            n_rcs=len(rcs),
            n_gyro_comp=n_comp,
            live=len(live),
        )
        self._dirty = False
        return self._cap

    def baseline(self):
        if not hasattr(self, '_base'):
            for c in self.components:
                c.reset()
            self._dirty = True
            self._base = dict(self.capability())
        return self._base

    def readout(self):
        """Per-subsystem damage readout as fractions of undamaged capability."""
        b, c = self.baseline(), self.capability()
        def frac(k):
            return (c[k] / b[k]) if b[k] else 1.0
        by_sys = {}
        for s in SUBSYSTEM_ORDER:
            tot = [x for x in self.components if x.subsystem == s]
            if not tot:
                continue
            alive = sum(1 for x in tot if x.alive)
            by_sys[s] = (alive, len(tot))
        return dict(power=frac('power_mw'), thrust=frac('drive_n'),
                    torque=frac('torque'), rcs=frac('n_rcs'),
                    mass_frac=frac('mass'), counts=by_sys,
                    integrity=self.integrity_frac())

    def integrity_frac(self):
        tot = sum(c.integrity for c in self.components) or 1
        rem = sum(max(0.0, c.integrity - c.accumulated) for c in self.components)
        return rem / tot

    # ------------------------------------------------------ ship.Ship interface
    def inertia_principal(self):
        """(I, com, mass) about the CoM, from SURVIVING components."""
        c = self.capability()
        return c['I'], c['com'], c['mass']

    def torque(self, n_computers=1):
        """Applied torque. `n_computers` is accepted and ignored on purpose:
        RCSController L181 divides the same _totalMoment/2 across every computer, so
        extra computers buy redundancy and nothing else."""
        return self.capability()['torque']

    def alive_blocks(self, subtype=None):
        return [c for c in self.components if c.alive
                and (subtype is None or c.subtype == subtype)]

    def count(self, subtype):
        return sum(1 for c in self.components if c.alive and c.subtype == subtype)

    def dead_count(self, subtype):
        return sum(1 for c in self.components if not c.alive and c.subtype == subtype)

    def reset_damage(self):
        for c in self.components:
            c.accumulated = 0.0
        self._dirty = True

    # ------------------------------------------------------------ ray marching
    def _aabb_entry(self, o, d):
        half = [(self.nx / 2 + 0.5) * GRID, (self.ny / 2 + 0.5) * GRID,
                (self.nz / 2 + 0.5) * GRID]
        t0, t1 = -math.inf, math.inf
        for a, (pc, dc) in enumerate(((o.x, d.x), (o.y, d.y), (o.z, d.z))):
            if abs(dc) < 1e-12:
                if pc < -half[a] or pc > half[a]:
                    return None
                continue
            ta, tb = (-half[a] - pc) / dc, (half[a] - pc) / dc
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return None
        return o + d * max(t0, 0.0)

    def march(self, origin_local, dir_local, max_cells=600):
        """DDA, DEDUPED: each distinct component appears once, in hit order."""
        d = dir_local.normalized()
        p = self._aabb_entry(origin_local, d)
        if p is None:
            return []
        cell = [math.floor(p.x / GRID + 0.5), math.floor(p.y / GRID + 0.5),
                math.floor(p.z / GRID + 0.5)]
        step, tmax, tdelta = [0, 0, 0], [math.inf] * 3, [math.inf] * 3
        for a, (pc, dc) in enumerate(((p.x, d.x), (p.y, d.y), (p.z, d.z))):
            if abs(dc) < 1e-12:
                continue
            step[a] = 1 if dc > 0 else -1
            tmax[a] = ((cell[a] + 0.5 * step[a]) * GRID - pc) / dc
            tdelta[a] = GRID / abs(dc)
        out, seen = [], set()
        for _ in range(max_cells):
            c = self.cells.get((cell[0], cell[1], cell[2]))
            if c is not None and c.alive and id(c) not in seen:
                seen.add(id(c))
                out.append(c)
            a = tmax.index(min(tmax))
            cell[a] += step[a]
            tmax[a] += tdelta[a]
            if (abs(cell[0]) > self.nx // 2 + 1 or abs(cell[1]) > self.ny // 2 + 1
                    or abs(cell[2]) > self.nz // 2 + 1):
                break
        return out

    # --------------------------------------------------------------- targeting
    def _acquisition_bucket(self, c):
        """Which GridToBlockTypeMap bucket a live block lands in.

        SessionJobs.cs:381-451 is an EXCLUSIVE if/else-if chain -- one bucket per block
        -- and a decoy is placed in DecoyMap[fat], which defaults to Utility (:404-416)
        rather than matching every type. Returns None for a block that matches no
        branch (gas tanks, cargo, armour); those are reachable only via the ANY pass.
        """
        s = c.spec['wc_subsystem']
        if s == DECOY:
            return DECOY_ACQUISITION_BUCKET
        return None if s == ANY else s

    def pick_target_block(self, rnd, subsystems=None, top_blocks=10):
        """WeaponCore's aimpoint walk, AiTargeting.cs AcquireBlock :1254-1288.

        Three things the previous version got wrong, all of which changed which block
        dies first:

        1. IT WALKED THE WRONG TAG. It selected on `subsystem`, the sim's coarse
           bucket, not on `wc_subsystem`. The tags differ on gyros -- WeaponCore calls
           a gyro `Steering`, and Steering is ABSENT from the SubSystems array every
           SDX2 gun declares -- so gyros were being shot SECOND (as Utility) when the
           real game only ever reaches them LAST, in the unfiltered fallback pass.

        2. IT TREATED `Any` AS A BUCKET. :1265 is `if (bt != Any && ...)`, so the ANY
           entry is SKIPPED inside the loop. Because ANY is nevertheless present in the
           array, `OnlySubSystems` is false (CoreSystems.cs:649-662) and the walk falls
           through to :1288 -- FindRandomBlock over `topMap.MyCubeBocks`, every terminal
           block on the grid. So ANY is the fallback pass, not a filter.

        3. IT LET GUNS AIM AT ARMOUR. Both aimpoint pools are built from lists filtered
           by `as IMyTerminalBlock` (SessionEvents.cs:341-344 for MyCubeBocks,
           SessionJobs.cs:381 for the type map). An armour cube is not a terminal
           block, so WeaponCore CANNOT aim at one -- armour is only ever eaten on the
           way in. On these hulls armour is most of the block count, so including it
           in the ANY pool diluted every fallback draw by roughly an order of
           magnitude and made the shot land on the skin instead of on machinery.
        """
        order = subsystems or WC_SUBSYSTEM_ORDER
        live = [c for c in self.components if c.alive and c.spec['wc_targetable']]
        for s in order:
            if s == ANY:
                pool = live                       # :1288 unfiltered fallback
            else:
                pool = [c for c in live if self._acquisition_bucket(c) == s]
            if pool:
                deck = pool[:]
                rnd.shuffle(deck)
                return rnd.choice(deck[:max(1, min(top_blocks, len(deck)))])
        return None
