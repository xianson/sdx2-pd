"""True cost of a design, resolved recursively to unobtainable roots, and the
survivability-weighted exchange ratio that actually matters.

Two separate ideas:

1. BUILD COST is not what a block's component list says. `sdx_componentMcrn` looks
   craftable, but its only recipe is 1x `sdx_ingotMcrnScrap`, which no blueprint
   produces. So costs must be resolved RECURSIVELY down to items that nothing can
   make, then filtered against what you can mine. Checking one level deep understates
   MCRN/UNN/OPA gear badly.

2. COST ALONE IS THE WRONG OBJECTIVE. A hull that costs half as much but dies twice
   as often is not cheaper. What matters in an attrition war over scarce NPC
   components is:

        E[engagements survived]  = 1 / (1 - p_survive)
        lifetime spend           = build + E * ammo_per_engagement
        lifetime kills           = E * kills_per_engagement
        COST PER KILL            = lifetime spend / lifetime kills

   This is the metric that correctly prices a railgun ship (high build, ~zero
   marginal) against a torpedo ship (moderate build, real marginal cost) against an
   improvised ship (cheap, fragile).

THREE THINGS THIS MODULE USED TO GET WRONG (all fixed, all changed the answer):

  * RESULT AMOUNTS WERE IGNORED. `sdx_ammoBlueprintTorpedo160mm` consumes 120x
    sdx_componentTorpedoGuidanceComputer and yields `<Result Amount="5" .../>`. The
    old scan recorded the whole 120 against ONE magazine, so torpedoes were priced
    at 5x their real cost. A 160mm torpedo costs 24x TGC per shot, not 120x.
  * THE LEAF SET WAS A HAND-WRITTEN GUESS. It listed `sdx_ingotTitanium` (no such
    item) and omitted Copper and Tungsten (both real, both mineable). The leaf set is
    now DERIVED: an item is free iff it is TypeId Ore, or TypeId Ingot produced by a
    blueprint whose every input is itself ore/ingot — i.e. a refinery step. SDX2's
    refinery recipes are self-referential (`1x Iron -> 0.7x Iron`, same SubtypeId),
    so they have to be cut here or the graph diverges instead of terminating.
  * RECIPE CHOICE WAS NONDETERMINISTIC. Files were walked in `set` order and the
    first blueprint seen won via `setdefault`, so ~21 components with both a vanilla
    and an SDX2 recipe resolved differently run to run. SDX2 now wins explicitly.

ModAdjuster (mod 3017795356) rewrites block recipes at runtime — heavy armour becomes
15 SteelPlate + 50 MetalGrid + 104 sdx_componentTitaniumPlate, not the vanilla 150+50.
It only applies files named in each mod's Data/ModAdjuster/ModAdjusterFiles.txt, so
that manifest is honoured rather than globbing the directory.
"""
import re, os, glob, json, math
from collections import defaultdict

CACHE_VERSION = 3
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recipe_cache.json')
BASE = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\244850"
VANILLA = r"C:\Program Files (x86)\Steam\steamapps\common\SpaceEngineers\Content\Data"
WORLD = (r"C:\Users\slob\AppData\Roaming\SpaceEngineers\Saves\76561198083962964"
         r"\Sigma Draconis Expanse 2 Creative World 2026-08-01 1243\Sandbox_config.sbc")

SDX2 = '2815514917'          # SDX2 Core: its recipes override the vanilla ones
_ITEM = re.compile(r'Amount="([\d.]+)"[^>]*TypeId="([\w./]+)"[^>]*SubtypeId="([^"]*)"')


def world_mod_ids():
    return re.findall(r'<PublishedFileId>(\d+)</PublishedFileId>',
                      open(WORLD, encoding='utf-8-sig', errors='replace').read())


def _modadjuster_files(mod_id):
    """Only the XMLs listed in the mod's manifest are applied by ModAdjuster."""
    root = os.path.join(BASE, mod_id, 'Data', 'ModAdjuster')
    man = os.path.join(root, 'ModAdjusterFiles.txt')
    if not os.path.exists(man):
        return []
    out = []
    for line in open(man, encoding='utf-8-sig', errors='replace'):
        rel = line.strip()
        if not rel:
            continue
        f = os.path.join(root, rel.replace(chr(92), os.sep))
        if os.path.exists(f):
            out.append(f)
    return out


def _section(body, name):
    m = re.search(r'<%s>(.*?)</%s>' % (name, name), body, re.S)
    if not m:
        return []
    return [(float(a), t, u) for a, t, u in _ITEM.findall(m.group(1))]


def _scan():
    """Returns (item_recipes, block_recipes, item_types).

    item_recipes: subtype -> [[amount_per_unit, input_subtype], ...]
    block_recipes: subtype -> {component: count}
    item_types:   subtype -> TypeId
    """
    ids = world_mod_ids()
    sbc = [(f, 'vanilla') for f in
           sorted(glob.glob(os.path.join(VANILLA, '**', '*.sbc'), recursive=True))]
    patch = []
    for i in ids:
        sbc += [(f, i) for f in
                sorted(glob.glob(os.path.join(BASE, i, 'Data', '**', '*.sbc'), recursive=True))]
        patch += [(f, i) for f in _modadjuster_files(i)]

    item_types, blueprints, block_recipes = {}, [], {}
    for path, tag in sbc + patch:                   # ModAdjuster patches apply last
        try:
            s = open(path, encoding='utf-8-sig', errors='replace').read()
        except Exception:
            continue
        for m in re.finditer(r'<(Component|PhysicalItem)>(.*?)</\1>', s, re.S):
            b = m.group(2)
            st = re.search(r'<SubtypeId>(.*?)</SubtypeId>', b)
            ty = re.search(r'<TypeId>(.*?)</TypeId>', b)
            if st and ty:
                # Ore/Iron and Ingot/Iron share a SubtypeId, so keep the UNION of
                # TypeIds — collapsing to last-wins loses the fact that Iron is
                # mineable while e.g. PrototechScrap is only ever salvaged.
                item_types.setdefault(st.group(1), []).append(ty.group(1))
        for m in re.finditer(r'<Blueprint\b[^>]*>(.*?)</Blueprint>', s, re.S):
            b = m.group(1)
            pre = _section(b, 'Prerequisites')
            res = _section(b, 'Results')
            one = re.search(r'<Result\b([^>]*)/>', b)
            if one:
                a = re.search(r'Amount="([\d.]+)"', one.group(1))
                u = re.search(r'SubtypeId="([^"]*)"', one.group(1))
                if u:
                    res.append((float(a.group(1)) if a else 1.0, '', u.group(1)))
            if res:
                bid = re.search(r'<SubtypeId>(.*?)</SubtypeId>', b)
                blueprints.append((bid.group(1) if bid else '', tag, pre, res))
        for m in re.finditer(r'<Definition[\s>].*?</Definition>', s, re.S):
            b = m.group(0)
            st = re.search(r'<SubtypeId>(.*?)</SubtypeId>', b)
            if not st or not st.group(1).strip():
                continue
            cs = re.findall(r'<Component\s+Subtype="([^"]+)"\s+Count="([\d.]+)"', b)
            if cs:
                agg = defaultdict(float)
                for c, k in cs:
                    agg[c] += float(k)
                block_recipes[st.group(1)] = dict(agg)   # later file wins, as in SE

    # --- FREE leaves: what comes out of the ground, and what a refinery makes of it.
    # MINEABLE = a subtype that has an `Ore` definition, i.e. it exists as a voxel
    # deposit. INGOT_LIKE = everything Ore- or Ingot-typed.
    # An ingot is FREE iff some blueprint makes it purely out of MINEABLE inputs.
    # The `pre <= mineable` test is what separates the two kinds of self-referential
    # recipe SDX2 ships: `1x Iron -> 0.7x Iron` is Ore/Iron -> Ingot/Iron and Iron IS
    # mineable, so Iron is free; `1x PrototechScrap -> 1x PrototechScrap` has no
    # PrototechScrap ore behind it, so prototech stays an unobtainable salvage root.
    mineable = {k for k, ts in item_types.items() if 'Ore' in ts}
    ingot_like = {k for k, ts in item_types.items() if {'Ore', 'Ingot'} & set(ts)}
    free = set(mineable)
    for bid, tag, pre, res in blueprints:
        srcs = {u for _, _, u in pre}
        if not srcs or not (srcs <= mineable):
            continue
        for amt, ty, sub in res:
            if sub in ingot_like:
                free.add(sub)

    # --- item recipes, SDX2 first then blueprint-id order, so the pick is stable
    item_recipes = {}
    for bid, tag, pre, res in sorted(blueprints, key=lambda b: (0 if b[1] == SDX2 else 1, b[0])):
        for amt, ty, sub in res:
            if sub in free or amt <= 0 or sub in item_recipes:
                continue
            item_recipes[sub] = [[a / amt, u] for a, t, u in pre]
    return item_recipes, block_recipes, item_types, sorted(free)


def load_recipes(refresh=False):
    if not refresh and os.path.exists(CACHE):
        d = json.load(open(CACHE))
        if isinstance(d, dict) and d.get('version') == CACHE_VERSION:
            return d
    ir, br, it, free = _scan()
    d = dict(version=CACHE_VERSION, items=ir, blocks=br, types=it, free=free)
    json.dump(d, open(CACHE, 'w'))
    return d


_D = None


def _data():
    global _D
    if _D is None:
        _D = load_recipes()
    return _D


def roots(item, depth=0, seen=frozenset()):
    """{unobtainable root: qty} for ONE unit of `item`. Free leaves contribute nothing."""
    d = _data()
    if item in d['free']:
        return {}
    rec = d['items'].get(item)
    if rec is None:
        rec = ([[v, k] for k, v in d['blocks'][item].items()]
               if item in d['blocks'] else None)
    if rec is None or item in seen or depth > 24:
        return {item: 1.0}
    out = defaultdict(float)
    for amt, sub in rec:
        for k, v in roots(sub, depth + 1, seen | {item}).items():
            out[k] += v * amt
    return dict(out)


def npc_cost(item, qty=1.0):
    """Unobtainable roots needed for `qty` of `item`."""
    return {k: v * qty for k, v in roots(item).items()}


def total_cost(bill):
    """bill: {subtype: qty} -> merged NPC root cost."""
    out = defaultdict(float)
    for k, q in bill.items():
        for r, v in npc_cost(k, q).items():
            out[r] += v
    return dict(out)


# ------------------------------------------------------- survivability weighting
def exchange(build_bill, ammo_bill_per_engagement, p_survive, kills_per_engagement,
             scarcity=None):
    """Survivability-weighted cost.

    p_survive           : probability the hull survives one engagement
    kills_per_engagement: enemy hulls killed per engagement
    scarcity            : optional {root: weight} if some NPC comps are rarer than
                          others; defaults to 1.0 each (pure component count)
    """
    build = total_cost(build_bill)
    ammo = total_cost(ammo_bill_per_engagement)
    w = scarcity or {}

    def val(d):
        return sum(v * w.get(k, 1.0) for k, v in d.items())

    if p_survive >= 1.0:
        E = float('inf')
    else:
        E = 1.0 / (1.0 - p_survive)

    b, a = val(build), val(ammo)
    if math.isinf(E):
        lifetime_spend = float('inf') if a > 0 else b
        cost_per_kill = (a / kills_per_engagement) if kills_per_engagement and a > 0 else \
                        (0.0 if kills_per_engagement else float('inf'))
    else:
        lifetime_spend = b + E * a
        lk = E * kills_per_engagement
        cost_per_kill = lifetime_spend / lk if lk > 0 else float('inf')

    return dict(build=b, ammo_per_engagement=a, expected_engagements=E,
                lifetime_spend=lifetime_spend, cost_per_kill=cost_per_kill,
                build_detail=build, ammo_detail=ammo)


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    d = load_recipes(refresh='--refresh' in sys.argv)
    print(f"{len(d['items'])} item recipes, {len(d['blocks'])} block recipes, "
          f"{len(d['free'])} free leaves")
    print("free:", ' '.join(d['free']))
    print()
    for st in ('sdx_ammomagazineTorpedo160mm', 'sdx_ammomagazineTorpedo190mmImprovised',
               'sdx_pdcUnnAdv', 'sdx_railgunMcrnMediumFixed', 'sdx_railgunMcrnMediumTurreted',
               'sdx_driveMcrnMilitary5x5', 'sdx_driveMcrnMilitary7x7', 'sdx_armorCeramic',
               'sdx_reactorFusion1x1', 'sdx_thrusterRCSBareLG', 'LargeHeavyBlockArmorBlock'):
        r = npc_cost(st)
        print(f"  {st:<40}" + (', '.join(f'{v:g}x {k}' for k, v in sorted(r.items())) or 'FREE'))
