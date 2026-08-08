"""Build ships to the real SCF class budgets, with every subsystem in the lattice.

CLASSES is not a hand-written table: it is derived (via catalogue.json) from the ship
cores SDX2 Core actually ships — mod 2815514917 `Data/ShipCoreConfig_Manifest.xml` ->
`Data/Cores/**/*_Core.xml` — not from `../sdx2.json`, which has drifted from the
installed mod. Each core carries a `<MaxSpeed>` and a list of `<BlockLimits>`, each with
a `<MaxCount>` and the `<BlockGroups>` it may be spent in; the cost of one block is its
`<CountWeight>` inside that group.

Two things this used to get wrong:

  * SPEED. `S['speed']` is now m/s. A core's `<MaxSpeed>` is a MODIFIER of the world
    cap (SpeedEnforcement.cs: `MaxPossibleSpeedMetersPerSecond * speedModifiers.MaxSpeed`)
    and this world's cap is 300, so the Corvette's 0.55 is 165 m/s. sdx2.json's `speed`
    field had already multiplied by a worldSpeed of 1000, giving 550 — 3.33x too fast.
    `S['speed_modifier']` keeps the raw fraction.
  * WEIGHTS. The Corvette's Point Defense Cannons budget is 8 POINTS, not 8 mounts: in
    group pdcsHeavyAdvWeights an sdx_pdcUnnAdv weighs 2, so 8 points buys FOUR of them
    (an sdx_pdcMcrn weighs 1, so eight of those). Every core in the mod uses
    pdcsHeavyAdvWeights for that limit — pdcsAdv and pdcsEvenAdvWeights are defined but
    referenced by no shipped core.

The only thing still assumed rather than read is the hull ENVELOPE — how many blocks
long and wide a class is. SCF does not constrain that, so it stays a harness choice.
"""
import math, random
from hull2 import Hull, GRID
from components import CATALOGUE, SHIP_CORES, GROUP_WEIGHTS, WORLD_SPEED

# harness assumption, NOT ruleset data: block envelope per class. Classes with no entry
# are scaled off the Corvette by the cube root of their total combat budget.
ENVELOPE = {
    'Picket':   (7, 7, 24),
    'Corvette': (8, 8, 30),
    'Frigate':  (10, 10, 36),
}
_REF = 'Corvette'

CATEGORY = dict(               # our shorthand -> the ruleset's category name
    ceramic='Ceramics', offensive='Offensive Weapons', pdc='Point Defense Cannons',
    torpedo='Torpedo Launchers', fixed_rg='Fixed Railguns', turret_rg='Turreted Railguns',
    epstein='Epstein Drives', power='Power Blocks', utilities='Utilities',
    production='Production', storage='Storage', cores='Ship Cores')


def weight_of(alias, groups, default=1):
    """Cost of one `alias` inside any of `groups`.

    A weight of 0 is MEANINGFUL, not missing: every PDC has CountWeight 0 in the
    `weapons` group, which is how SCF lets the PDC budget be the only thing that caps
    them. So this distinguishes absent (fall back to `default`) from zero.

    `sdx_pdcPgenAdv` is NOT weightless and NOT ungrouped — the shipped groups file gives
    it 1 in pdcsAdv, 1 in pdcsEvenAdvWeights, 2 in pdcsHeavyAdvWeights and 0 in weapons,
    exactly like the other advanced PDCs. What makes it unbuildable is its recipe: 1x
    sdx_componentAdminKit, an item with MaxIntegrity 999,999,999 that no blueprint
    produces. lomdar's ../sdx2.json omits the block entirely, which is where the "in no
    group at all" idea came from.
    """
    st = CATALOGUE[alias]['subtype']
    for g in groups:
        w = GROUP_WEIGHTS.get(g, {}).get(st)
        if w is not None:
            return w
    return default


def _budgets(core):
    cats = core['categories']
    out = {}
    for short, name in CATEGORY.items():
        c = cats.get(name)
        out[short] = c['budget'] if c else 0
        out[short + '_groups'] = c['groups'] if c else []
    # `speed` is m/s; the ruleset stores a fraction of the world cap, not a speed
    out['speed_modifier'] = core['speed']
    out['speed'] = core.get('speed_mps', core['speed'] * WORLD_SPEED)
    out['speed_limit_type'] = core.get('speed_limit_type')
    out['friction_band'] = (core.get('friction_min_mps'), core.get('friction_max_mps'))
    out['categories'] = cats
    return out


def _envelope(name, S):
    if name in ENVELOPE:
        return ENVELOPE[name]
    ref = _budgets(SHIP_CORES[_REF])
    def tot(x):
        return max(1, x['offensive'] + x['pdc'] * 4 + x['power'] * 4 + x['ceramic'])
    k = (tot(S) / tot(ref)) ** (1 / 3.0)
    nx, ny, nz = ENVELOPE[_REF]
    return (max(5, int(round(nx * k))), max(5, int(round(ny * k))),
            max(12, int(round(nz * k))))


CLASSES = {}
for _name, _core in SHIP_CORES.items():
    _S = _budgets(_core)
    _S['nx'], _S['ny'], _S['nz'] = _envelope(_name, _S)
    CLASSES[_name] = _S


def build_ship(cls='Corvette', reactor_style='dispersed', pdc_kind='pdcUnnAdv',
               pdc_mix=None, n_rcs=200, rcs_lever_frac=0.75, rcs_lever=None,
               seed=1, internals=0.30, ceramic=None, ceramic_frac=1.0,
               armour='steel+ceramic', dims=None, name=None, with_mounts=True,
               turret_rg=False, max_turret_rg=99, max_fixed_rg=1):
    """Returns (hull, manifest, mounts). Budgets are enforced, not assumed.

    ceramic       absolute block count; None -> class budget * ceramic_frac
    pdc_mix       {alias: count}; None -> spend the PDC budget on `pdc_kind`
    rcs_lever     absolute lever in blocks; None -> rcs_lever_frac * half-length
    armour        'steel+ceramic' | 'steel' (no ceramic allowance at all)
    turret_rg     buy Turreted Railguns first (Cruiser/Carrier allow 1). Off by
                  default: it spends 42 offensive points and reshapes the whole fit, so
                  turning it on silently would rebase every existing comparison.
    max_fixed_rg  cap on fixed guns. 1 by default because that is what this function
                  used to hard-code; the Frigate/Cruiser/Carrier sub-cap is 2.
    """
    S = CLASSES[cls]
    nx, ny, nz = dims or (S['nx'], S['ny'], S['nz'])
    h = Hull(name or cls, nx, ny, nz)
    rnd = random.Random(seed)
    man = {'class': cls, 'speed': S['speed'], 'spent': {}, 'unspent': {}}
    hx, hy, hz = nx // 2, ny // 2, nz // 2

    # ---- armour shell -------------------------------------------------------
    h.shell('heavy', depth=1)

    # ---- ceramic allowance, centre-out on the bow, behind the steel ---------
    n_cer = 0 if armour == 'steel' else (
        ceramic if ceramic is not None else int(S['ceramic'] * ceramic_frac))
    n_cer = max(0, min(n_cer, S['ceramic']))            # SCF caps it hard
    cand = sorted(((i, j) for j in range(-hy + 1, hy) for i in range(-hx + 1, hx)),
                  key=lambda c: c[0] ** 2 + c[1] ** 2)
    for i, j in cand[:n_cer]:
        h.install_if_free('ceramic', (i, j, -hz + 1))
    man['spent']['ceramic'] = n_cer * weight_of('ceramic', S['ceramic_groups'])

    # ---- power --------------------------------------------------------------
    grp = S['power_groups']
    order = (['reactor5', 'reactor3', 'reactor1'] if reactor_style == 'clustered'
             else ['reactor1'])
    reactors, pts = [], S['power']
    while True:
        for k in order:
            w = weight_of(k, grp)
            if w > 0 and w <= pts:      # w == 0 would never exhaust the budget
                reactors.append(k)
                pts -= w
                break
        else:
            break
    n = len(reactors)
    for idx, k in enumerate(reactors):
        sz = CATALOGUE[k]['size']
        if reactor_style == 'clustered':
            z = -sz[2] // 2 + idx * (sz[2] + 1)
            x = -sz[0] // 2
        else:
            span = hz - 4
            z = int(-span + 2 * span * (idx + 0.5) / max(1, n))
            x = (-1 if idx % 2 else 1) * (hx // 2) - sz[0] // 2
        h.install_if_free(k, (x, -sz[1] // 2, z), name=f"{k}#{idx}")
    man['spent']['power'] = S['power'] - pts
    man['unspent']['power'] = pts
    man['reactors'] = reactors

    # ---- epstein drives (aft) ----------------------------------------------
    grp = S['epstein_groups']
    drives, pts = [], S['epstein']
    while True:
        w = weight_of('drive5', grp)
        if w <= 0 or w > pts:
            break
        drives.append('drive5')
        pts -= w
    for idx, k in enumerate(drives):
        sz = CATALOGUE[k]['size']
        h.install_if_free(k, (-sz[0] // 2, -sz[1] // 2, hz - sz[2] - 1), name=f"{k}#{idx}")
    man['spent']['epstein'] = S['epstein'] - pts
    man['drives'] = drives

    # ---- utilities: exactly ONE RCS computer (extras add no torque) ---------
    h.install_if_free('rcscomp', (0, 0, 0), name='rcscomp')
    man['spent']['utilities'] = weight_of('rcscomp', S['utilities_groups'])
    man['unspent']['utilities'] = S['utilities'] - man['spent']['utilities']

    # ---- RCS on the skin, in rings working inwards from the extremities -----
    # They REPLACE skin armour (a hull thruster occupies an armour slot), and the
    # lever arm is along Z, which is what generates yaw/pitch moment. RCS thrusters
    # appear in no SCF group, so they cost nothing and are skin-limited only.
    lox, loy, _ = h.lo
    hix, hiy, hiz = h.hi
    skin = []
    for i in range(lox, hix + 1):
        for j in range(loy, hiy + 1):
            if i in (lox, hix) or j in (loy, hiy):    # circumference only
                skin.append((i, j))
    lever = int(rcs_lever if rcs_lever is not None else hz * rcs_lever_frac)
    lever = max(1, min(lever, hiz))
    zs = []
    for step in range(hz):                            # furthest-out rings first
        for sign in (+1, -1):
            z = sign * (lever - step)
            if abs(z) >= 1 and z not in zs:
                zs.append(z)
    placed = 0
    for z in zs:
        if placed >= n_rcs:
            break
        for (i, j) in skin:
            if placed >= n_rcs:
                break
            cur = h.cells.get((i, j, z))
            if cur is not None and sum(1 for _ in cur.cells()) != 1:
                continue                              # don't break multi-cell blocks
            if h.replace_cell('rcs', (i, j, z)) is not None:
                placed += 1
    man['n_rcs'] = placed

    # ---- offence ------------------------------------------------------------
    # Offensive Weapons is the master budget; Torpedo Launchers / Fixed Railguns /
    # Turreted Railguns are sub-caps that also have to hold.
    off = S['offensive']
    ogrp = S['offensive_groups']

    # TURRETED RAILGUNS. Cruiser and Carrier each allow one, and this never built any:
    # S['turret_rg'] was read into CLASSES and then ignored, so the class with the
    # single most expensive weapon decision in the ruleset was being modelled as if the
    # option did not exist. It costs 42 offensive points against a fixed gun's 34, and
    # 42 + 2*34 = 110 > 102, so taking the turret CROWDS OUT both fixed guns on a
    # Cruiser -- turret-vs-2x-fixed is a genuine either/or, not an addition.
    # `turret_rg=True` spends the sub-cap; the default False keeps the previous fit so
    # existing comparisons are not silently rebased.
    trg_w = weight_of('railgun_t', ogrp)
    trg_cap = weight_of('railgun_t', S['turret_rg_groups'])
    man['turret_railgun'] = 0
    turrets, tr_pts = 0, S['turret_rg']
    if turret_rg:
        while (trg_cap > 0 and tr_pts >= trg_cap and off >= trg_w
               and turrets < max_turret_rg):
            # A 3x5x3 turret needs real room; put it dorsally amidships where it has
            # sky on both beams rather than buried in the bow with the fixed gun.
            c = h.install_if_free('railgun_t', (-1, hy - 5, -1 + turrets * 4),
                                  name=f'railgun_t{turrets}')
            if c is None:
                break
            off -= trg_w
            tr_pts -= trg_cap
            turrets += 1
        man['turret_railgun'] = turrets
    man['spent']['turret_rg'] = S['turret_rg'] - tr_pts

    rg_w = weight_of('railgun', ogrp)
    man['railgun'] = 0
    fixed, f_pts = 0, S['fixed_rg']
    fixed_cap = weight_of('railgun', S['fixed_rg_groups'])
    while (fixed_cap > 0 and f_pts >= fixed_cap and off >= rg_w
           and fixed < max_fixed_rg):
        c = h.install_if_free('railgun', (fixed * 2 - 1, -1, -hz + 2),
                              name=f'railgun{fixed}')
        if c is None:
            break
        off -= rg_w
        f_pts -= fixed_cap
        fixed += 1
    man['railgun'] = fixed
    man['spent']['fixed_rg'] = S['fixed_rg'] - f_pts

    tube_w = weight_of('torptube', ogrp)
    tube_cap = weight_of('torptube', S['torpedo_groups'])
    tubes, tpts = 0, S['torpedo']
    while tube_w > 0 and tube_cap > 0 and off >= tube_w and tpts >= tube_cap:
        h.install_if_free('torptube', (-3 + (tubes % 3) * 3, 1, -hz + 4), name=f"tube{tubes}")
        off -= tube_w
        tpts -= tube_cap
        tubes += 1
    man['torpedo_tubes'] = tubes
    man['spent']['offensive'] = S['offensive'] - off
    man['unspent']['offensive'] = off
    man['spent']['torpedo'] = S['torpedo'] - tpts

    # ---- PDC mounts on the skin --------------------------------------------
    pgrp = S['pdc_groups']
    if pdc_mix is None:
        w = weight_of(pdc_kind, pgrp)
        pdc_mix = {pdc_kind: int(S['pdc'] // w)} if w else {pdc_kind: 0}
    order = [k for k in pdc_mix for _ in range(pdc_mix[k])]
    total = len(order) or 1
    mounts, spent = [], 0
    for idx, kind in enumerate(order):
        ang = 2 * math.pi * idx / total
        zc = int((-1 if idx % 2 else 1) * hiz * 0.55)
        # clamp onto the lattice: round(cos*hx) lands on +nx//2, which for an even nx
        # is one cell OUTSIDE the hull, and a mount out there has no armour under it
        cell = h.clamp((int(round(math.cos(ang) * hx)), int(round(math.sin(ang) * hy)), zc))
        comp = h.install_replacing(kind, cell, name=f"pdc{idx}")
        if comp is None:                       # landed on a reactor/drive: shuffle off
            comp = h.install_if_free(kind, cell, name=f"pdc{idx}")
        spent += weight_of(kind, pgrp)
        mounts.append((comp, cell, (math.cos(ang), math.sin(ang), 0.0)))
    man['spent']['pdc'] = spent
    man['unspent']['pdc'] = S['pdc'] - spent
    man['pdc'] = len(order)
    man['pdc_kind'] = pdc_kind
    man['pdc_mix'] = dict(pdc_mix)

    # ---- filler -------------------------------------------------------------
    h.fill('internal', density=internals, seed=seed)
    h.baseline()

    if with_mounts:
        mounts = make_mounts(mounts)
    return h, man, mounts


def make_mounts(raw):
    """Turn (component, cell, normal) triples into live PdcMount objects.

    Imported lazily: weapons.py reads GRID out of hull2 and knows nothing about the
    shipyard, and keeping it that way avoids a cycle.
    """
    from vec import V
    from weapons import PdcMount, PDC_KIND
    out = []
    for comp, cell, nrm in raw:
        if comp is None:
            continue
        kind = PDC_KIND.get(comp.spec['subtype'])
        if kind is None:
            continue
        m = PdcMount(kind, cell, V(*nrm), component=comp)
        out.append(m)
    return out


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print(f"SCF ship cores from SDX2 Core's Data/Cores/**, world cap {WORLD_SPEED:g} m/s")
    print(f"{'class':<14}{'mod':>6}{'m/s':>6}{'envelope':>12}{'cer':>6}{'off':>6}{'pdc':>6}"
          f"{'torp':>6}{'rg':>4}{'eps':>5}{'pwr':>5}{'util':>6}")
    print("-" * 86)
    for k, S in CLASSES.items():
        env = f"{S['nx']}x{S['ny']}x{S['nz']}"
        print(f"{k:<14}{S['speed_modifier']:>6.2f}{S['speed']:>6.0f}{env:>12}"
              f"{S['ceramic']:>6g}{S['offensive']:>6g}{S['pdc']:>6g}{S['torpedo']:>6g}"
              f"{S['fixed_rg']:>4g}{S['epstein']:>5g}{S['power']:>5g}{S['utilities']:>6g}")
    print()
    h, man, mounts = build_ship('Corvette')
    print("Corvette build:", {k: v for k, v in man.items() if k != 'spent'})
    print("  points spent:", man['spent'])
