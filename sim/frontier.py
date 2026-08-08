"""Frontier probes: the levers OUTSIDE per-mount fire control.

Everything prior optimised per-mount range/toggle policy on a FIXED ship
(8x PdcMcrn) in a FIXED formation (lateral 500 m). This file varies the two
things a fleet commander actually controls before the shooting starts —
battery composition and formation geometry — plus the one policy that only
exists once the battery is mixed.

A. MIXED BATTERY (hardware lever, 8-point SCF budget respected)
   PdcMcrnAdv: 2 points, 80 rpm, dev 0, muzzle 4000, HHM 5 vs torpedo Health 4
   -> ONE ROUND = ONE KILL, with a 160 m interaction radius (PDC50mmHeavy
   tracer-length quirk, wc_collide.threshold_for). This weapon is immune to
   the two mechanics that destroy the 40mm battery: it does not need 4 hits
   accumulated on one torpedo (scatter cannot "wound everything, kill
   nothing") and its dead-round channel is only duplication. Legal builds:
   k x pdcMcrnAdv + (8-2k) x pdcMcrn, k = 0..4.

B. FORMATION (geometry lever, zero cost)
   wave() flies the salvo down the -X axis at the lead hull: 260 m/s for the
   first ~2.5 s, then ~300 m/s^2 up to 1040. The stock lateral line gives
   every hull the same terminal 2.9 s window. Staggering hulls ALONG the
   threat axis ("picket line") lets up-threat hulls engage the boost/mid
   phase — a picket at +2000 m sees the salvo for ~5.5 s, at +4000 m for the
   entire flight — and boost-phase torpedoes are slow, unweaving targets.
   Lateral offset +/-250 m keeps peak angular rates under the turret slew cap.
   In-game caveat: axis-specific (needs the fleet to orient on the launch
   bearing, which RegisterProjectileAdded provides) and pickets stand closer
   to the launcher.

C. ROLE POLICY FOR MIXED HARDWARE ("sniper calls, herd yields")
   The incumbent full ladder demotes the LESS-committed mount on a ray
   conflict. On a mixed battery that is exactly backwards: the Adv mount has
   ~0 rounds in flight (slow rof) so the ladder makes the guaranteed-kill
   sniper yield to a 40mm spray whose 12 in-flight rounds will mostly waste
   anyway. Here: Adv mounts keep full reach and de-conflict only among
   themselves (+ optional shoot-and-scoot re-aim pulse after every round);
   40mm mounts run window+ladder and additionally demote whenever their ray
   converges with a sniper ray.

Legality: policies read only ctx and own-mount state. The kind of each own
mount and each hull's formation offset are own-fleet constants a PB knows
(IGC). Per-ship leading-edge range is derived from ctx['nearest'] plus the
known threat axis — the same dead-reckoning that justifies 'nearest' itself.
"""
import math, random, statistics as stats
import weapons
from vec import V
from ship import Ship
from shipyard import build_ship
from torpedo2 import Torpedo2
from fleet_efficiency import wave, class_speed_mps, run
import ladder as L

SEEDS = list(range(701, 715))

MCRN8 = {'pdcMcrn': 8}


# ------------------------------------------------------------------ custom runner
def run_custom(specs, salvo=40, seed=1, policy=None, torp_kind='Plasma220mmTorp',
               waves=1):
    """Mirror of fleet_efficiency.run() with per-hull pdc_mix and position.

    specs: list of (pdc_mix_dict, position_V). Reproduces run() exactly when
    given [(MCRN8, V(0,0,0)), (MCRN8, V(0,500,0)), (MCRN8, V(0,1000,0))]
    (verified by check_fidelity below). Shared wave() does all the physics.
    """
    weapons.reset_part_ids()
    Torpedo2.reset_ids()
    weapons.Torpedo.reset_ids()
    rnd = random.Random(seed)
    fleet = []
    for s, (mix, pos) in enumerate(specs):
        hull, man, mounts = build_ship('Corvette', pdc_mix=dict(mix), n_rcs=200,
                                       seed=seed + s)
        assert len(mounts) == sum(mix.values()), \
            f"build dropped a mount: {mix} -> {len(mounts)}"
        sh = Ship(hull, pos, V(0, 0, 0), class_speed_mps('Corvette'),
                  drive_thrust=292e6 * 2)
        for m in mounts:
            m.reset()
        fleet.append((sh, hull, mounts))
    tot_leak = tot_kill = fired = 0
    for _ in range(waves):
        lk, kl, _eng, _tk, wst = wave(fleet, salvo, torp_kind, rnd, 500.0,
                                      policy=policy, engage_all=True)
        tot_leak += lk
        tot_kill += kl
        fired += wst['fired']
    return dict(leakers=tot_leak, kills=tot_kill, fired_rounds=fired)


def budget_cost(mix):
    from shipyard import CLASSES, weight_of
    pg = CLASSES['Corvette']['pdc_groups']
    return sum(weight_of(k, pg) * n for k, n in mix.items())


# ------------------------------------------------------------ placement control
#: alias -> PDC_STATS key
ALIAS_KIND = {v: k for k, v in weapons.PDC_ALIAS.items()}

#: the stock 8-ring as (alias, angle_deg, z_sign) triples — mirrors the
#: shipyard loop exactly (angle = 2*pi*idx/total, zc alternates +/- by parity)
STOCK_RING = [('pdcMcrn', 45.0 * i, +1 if i % 2 == 0 else -1) for i in range(8)]


def build_placed(slots, seed):
    """Build a Corvette with an explicitly placed PDC battery.

    slots: list of (alias, angle_deg, z_sign). Reproduces build_ship's ring
    cell math (shipyard.py:292-302) so a slots list equal to STOCK_RING gives
    a bit-identical ship to build_ship(pdc_mix={'pdcMcrn': 8}) — verified in
    check_fidelity. Placement is a real in-game freedom (you weld the turret
    where you want it); this just exposes it to the harness.
    """
    # internals=0.0: the stock flow fills AFTER mounting PDCs, so to reproduce
    # its lattice bit-exactly we defer the filler until our ring is installed.
    hull, man, _ = build_ship('Corvette', pdc_mix={}, n_rcs=200, seed=seed,
                              internals=0.0)
    from shipyard import CLASSES
    S = CLASSES['Corvette']
    hx, hy = S['nx'] // 2, S['ny'] // 2
    hiz = hull.hi[2]
    mounts = []
    for idx, (alias, ang_deg, zs) in enumerate(slots):
        ang = math.radians(ang_deg)
        zc = int(zs * hiz * 0.55)
        cell = hull.clamp((int(round(math.cos(ang) * hx)),
                           int(round(math.sin(ang) * hy)), zc))
        comp = hull.install_replacing(alias, cell, name=f"pdc{idx}")
        if comp is None:
            comp = hull.install_if_free(alias, cell, name=f"pdc{idx}")
        assert comp is not None, f"no room for {alias} at {cell}"
        m = weapons.PdcMount(ALIAS_KIND[alias], cell,
                             V(math.cos(ang), math.sin(ang), 0.0), component=comp)
        mounts.append(m)
    hull.fill('internal', density=0.30, seed=seed)
    hull.baseline()
    return hull, man, mounts


def run_placed(specs, salvo=40, seed=1, policy=None, torp_kind='Plasma220mmTorp'):
    """run_custom but each spec is (slots_list, position_V)."""
    weapons.reset_part_ids()
    Torpedo2.reset_ids()
    weapons.Torpedo.reset_ids()
    rnd = random.Random(seed)
    fleet = []
    for s, (slots, pos) in enumerate(specs):
        hull, man, mounts = build_placed(slots, seed + s)
        sh = Ship(hull, pos, V(0, 0, 0), class_speed_mps('Corvette'),
                  drive_thrust=292e6 * 2)
        for m in mounts:
            m.reset()
        fleet.append((sh, hull, mounts))
    lk, kl, _eng, _tk, wst = wave(fleet, salvo, torp_kind, rnd, 500.0,
                                  policy=policy, engage_all=True)
    return dict(leakers=lk, kills=kl, fired_rounds=wst['fired'])


# Budget-legal placement-controlled batteries. The probe (frontier_explore)
# showed ring angles 180/225 NEVER fire at the threat axis (own-hull
# occlusion), so the stock 8-point build fights with ~5.8 of its 8 mounts.
RING_BROADSIDE = ([('pdcMcrn', a, z) for a, z in
                   ((0, 1), (45, -1), (90, 1), (135, -1), (270, 1), (315, -1))]
                  + [('pdcMcrn', 0, -1), ('pdcMcrn', 90, -1)])   # 8 pts, all bear
RING_SNIPER = ([('pdcMcrnAdv', 0, 1), ('pdcMcrnAdv', 45, -1)]     # 2x2 pts
               + [('pdcMcrn', a, z) for a, z in
                  ((90, 1), (135, -1), (270, 1), (315, -1))])     # 4x1 pts
RING_PGEN = ([('pdcPgenAdv', 0, 1), ('pdcPgenAdv', 45, -1)]
             + [('pdcMcrn', a, z) for a, z in
                ((90, 1), (135, -1), (270, 1), (315, -1))])
RING_FLAK = ([('pdcOpaAdv', 0, 1), ('pdcOpaAdv', 45, -1)]
             + [('pdcMcrn', a, z) for a, z in
                ((90, 1), (135, -1), (270, 1), (315, -1))])


# ------------------------------------------------------------------ formations
def lateral(spacing=500.0, n=3):
    return [(dict(MCRN8), V(0, s * spacing, 0)) for s in range(n)]


def picket(xs=(0.0, 2000.0, 4000.0), lat=250.0, mixes=None):
    """Lead first (torpedoes home on fleet[0]); pickets staggered up-threat.

    Torpedoes spawn at lead+X*6000 and fly -X, so positive x is toward the
    threat. Alternating +/-lat keeps the pass-by angular rate below the
    0.1309 rad/tick slew cap."""
    mixes = mixes or [dict(MCRN8)] * len(xs)
    out = []
    for i, x in enumerate(xs):
        y = 0.0 if i == 0 else (lat if i % 2 else -lat)
        out.append((dict(mixes[i]), V(x, y, 0)))
    return out


# ------------------------------------------------------------------ policies
def formation_window(ship_x, margin=500.0):
    """window_nearest generalised to a formation: each hull windows on ITS OWN
    range to the leading edge. ctx['nearest'] is lead-relative; the torpedo
    stream runs down the threat axis, so a hull offset x_s up-threat sees the
    leading edge at |nearest - x_s|. Once the edge is past a picket, hold a
    tight window (the tail is passing through). Own formation offsets are
    fleet constants (IGC)."""
    def pol(m, ctx):
        edge = ctx['nearest'] - ship_x[m._ship]
        r = margin + max(0.0, edge)
        return True, min(m._base_range, r)
    return pol


def formation_window_ladder(ship_x, margin=500.0, tol=40.0, burst=14):
    """Formation window for prioritisation + ray ladder for de-confliction."""
    lad = L.ladder_deconflict(tol=tol, burst=burst)

    def pol(m, ctx):
        ctx.setdefault('_infl_by_key', {})[(m._ship, m._idx)] = m._in_flight
        _f, r = lad(m, ctx)
        edge = ctx['nearest'] - ship_x[m._ship]
        cap = min(m._base_range, margin + max(0.0, edge))
        return True, min(r if r is not None else m._base_range, cap)
    return pol


def mix_roles(margin=500.0, tol=40.0, burst=14, scoot=True, snipe='PdcMcrnAdv',
              ship_x=None):
    """Sniper-calls / herd-yields for a mixed battery (see module docstring).

    Adv mounts: full reach; de-conflict only against OTHER snipers (tie-break
    by key; both have ~0 in flight so ladder's in-flight tie-break is noise);
    optional shoot-and-scoot: one PB tick after each round leaves, pulse the
    range down to force a re-acquire so consecutive rounds go to different
    torpedoes.
    40mm mounts: window+ladder as incumbent, PLUS demote-on-sniper-ray: a
    sniper round arriving means that torpedo is already dead, so any 40mm
    stream converging with a sniper bearing re-aims immediately.
    """
    kinds = {}                      # (ship, idx) -> kind; own-fleet constant
    lad = L.ladder_deconflict(tol=tol, burst=burst)

    def pol(m, ctx):
        me = (m._ship, m._idx)
        kinds[me] = m.kind
        ctx.setdefault('_infl_by_key', {})[me] = m._in_flight

        if m.kind == snipe:
            st = getattr(m, '_snipe', None)
            if st is None:
                st = m._snipe = {'shots': m.shots_fired}
            # sniper-vs-sniper dedup: higher key yields with a re-aim pulse
            for A, B in L._conflicts(ctx, tol):
                if me in (A, B):
                    other = B if A == me else A
                    if kinds.get(other) == snipe and me > other:
                        return True, m._base_range * 0.25
            if scoot and m.shots_fired > st['shots']:
                st['shots'] = m.shots_fired
                return True, m._base_range * 0.25      # re-aim pulse, one PB tick
            st['shots'] = m.shots_fired
            return True, None                          # full reach

        # ---- 40mm herd
        _f, r = lad(m, ctx)
        r = r if r is not None else m._base_range
        for A, B in L._conflicts(ctx, tol):
            if me in (A, B):
                other = B if A == me else A
                if kinds.get(other) == snipe:
                    r = min(r, m._base_range * 0.5)    # sniper called it: yield
                    break
        edge = ctx['nearest'] - (ship_x[m._ship] if ship_x else 0.0)
        cap = min(m._base_range, margin + max(0.0, edge))
        return True, min(r, cap)
    return pol


# ------------------------------------------------------------------ eval
def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or stats.stdev(d) == 0:
        return float('inf') if stats.mean(d) else 0.0
    return stats.mean(d) / (stats.stdev(d) / math.sqrt(len(d)))


def full_ladder():
    return L.with_infl_index(L.ladder_deconflict(tol=40, burst=14))


def row(name, fn, seeds):
    rs = [fn(s) for s in seeds]
    return name, [r['leakers'] for r in rs], [r['fired_rounds'] for r in rs], \
        [r['kills'] for r in rs]


def print_table(rows, ref_name='full ladder tol40 b14 (stock)'):
    ref = next(r for r in rows if r[0] == ref_name)
    print(f"  {'configuration + policy':<44}{'leak':>6}{'sd':>6}{'fired':>7}"
          f"{'kills':>7}{'t-leak':>8}{'t-fired':>8}", flush=True)
    print("  " + "-" * 86, flush=True)
    for name, lk, fr, kl in rows:
        tl = paired_t(lk, ref[1])
        tf = paired_t(fr, ref[2])
        sd = stats.stdev(lk) if len(lk) > 1 else 0.0
        print(f"  {name:<44}{stats.mean(lk):>6.2f}{sd:>6.2f}{stats.mean(fr):>7.0f}"
              f"{stats.mean(kl):>7.1f}{tl:>+8.2f}{tf:>+8.2f}", flush=True)


def check_fidelity(seed=701):
    """run_custom must reproduce run() bit-exactly on the stock config."""
    for pol_f in (lambda: None, full_ladder):
        a = run(3, 8, kind='PdcMcrn', salvo=40, waves=1, seed=seed,
                engage_all=True, policy=pol_f())
        b = run_custom(lateral(500.0), salvo=40, seed=seed, policy=pol_f())
        assert (a['leakers'], a['fired_rounds']) == \
               (b['leakers'], b['fired_rounds']), (a, b)
        c = run_placed([(STOCK_RING, V(0, 0, 0)), (STOCK_RING, V(0, 500, 0)),
                        (STOCK_RING, V(0, 1000, 0))], salvo=40, seed=seed,
                       policy=pol_f())
        assert (a['leakers'], a['fired_rounds']) == \
               (c['leakers'], c['fired_rounds']), (a, c)
    print("  fidelity: run_custom AND run_placed(STOCK_RING) == run(), "
          "baseline + ladder", flush=True)


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                                  errors='replace', line_buffering=True)
    check_fidelity()
