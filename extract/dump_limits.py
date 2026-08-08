"""Dump lomdar's sdx2.json planner dataset into readable tables."""
import json, io, sys, csv, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(D, 'sdx2.json'), encoding='utf-8'))
out = io.StringIO()
W = out.write

W(f"# SDX2 limits — ripped from lomdar.com core planner\n\n")
W(f"Source: `https://www.lomdar.com/games/se1/data/sdx2.json` "
  f"(the planner at `/games/se1/sdx2/planner/` fetches this).\n\n")
W(f"- modset: **{d['modset']}**\n- gameBuild: **{d['gameBuild']}**\n"
  f"- generated: **{d['generated']}**\n- schema: {d['schema']}\n\n")

sc = d['shipCores']
W(f"## World speed\n\n**`worldSpeed = {sc['worldSpeed']}` m/s** — the SCF "
  f"`MaxPossibleSpeedMetersPerSecond`. Per-class caps below are absolute m/s, not modifiers.\n\n")

# ---------------------------------------------------------------- core summary
W("## Ship classes\n\n")
W("| core | subtype | class | max speed | backup cores | grid |\n|---|---|---|---|---|---|\n")
for c in sc['cores']:
    bc = 'unlimited' if c['maxBackupCores'] == -1 else c['maxBackupCores']
    W(f"| **{c['name']}** | `{c['subtype']}` | {c['class']} | **{c['speed']}** | {bc} | {c['grid'] or '—'} |\n")
W("\n")

# ------------------------------------------------------- category budget matrix
cats = []
for c in sc['cores']:
    for cat in c['categories']:
        if cat['name'] not in cats:
            cats.append(cat['name'])
names = [c['name'] for c in sc['cores']]
W("## Category budgets by class\n\n")
W("`—` = category absent for that core. `0` = present but banned. "
  "`*` suffix = critical (losing it triggers the punishment).\n\n")
W("| category | " + " | ".join(names) + " |\n")
W("|---" * (len(names) + 1) + "|\n")
for cn in cats:
    row = [cn]
    for c in sc['cores']:
        m = next((x for x in c['categories'] if x['name'] == cn), None)
        row.append('—' if m is None else f"{m['budget']}{'*' if m['critical'] else ''}")
    W("| " + " | ".join(row) + " |\n")
W("\n")

# ------------------------------------------------------------ category details
W("## Category detail (groups, directions, punishment)\n\n")
for c in sc['cores']:
    W(f"### {c['name']}  ({c['class']}, {c['speed']} m/s)\n\n")
    W("| category | budget | critical | punishment | directions | groups |\n|---|---|---|---|---|---|\n")
    for cat in c['categories']:
        W(f"| {cat['name']} | {cat['budget']} | {'yes' if cat['critical'] else ''} | "
          f"{cat['punishment']} | {', '.join(cat['directions']) or '—'} | "
          f"{', '.join('`'+g+'`' for g in cat['groups'])} |\n")
    W("\n")

# -------------------------------------------------------------------- groups
W("## Groups — block weights\n\n")
W("A category's budget is spent by each block's `weight`.\n\n")
for g in sorted(sc['groups'], key=lambda x: x['name']):
    W(f"### `{g['name']}`  ({len(g['blocks'])} blocks)\n\n")
    W("| block | subtype | type | size | weight | capacity | thrust |\n|---|---|---|---|---|---|---|\n")
    for b in g['blocks']:
        W(f"| {b['name']} | `{b['subtype']}` | {b['type']} | {b['size']} | **{b['weight']}** | "
          f"{b['capacity'] if b['capacity'] is not None else '—'} | "
          f"{b['thrust'] if b['thrust'] is not None else '—'} |\n")
    W("\n")

# ------------------------------------------------------------------ thrusters
W("## Thrusters\n\n")
W("| thruster | subtype | grid | group | force N | mass kg | inf min/max | eff min/max | fuel | draw lo/hi |\n")
W("|---|---|---|---|---|---|---|---|---|---|\n")
for t in sorted(d['thrust']['thrusters'], key=lambda x: -x['force']):
    dr = t['draw'] or {}
    W(f"| {t['name']} | `{t['subtype']}` | {t['grid']} | {t['group']} | {t['force']:,.0f} | "
      f"{t['mass']:,.0f} | {t['infMin']}/{t['infMax']} | {t['effMin']}/{t['effMax']} | "
      f"{dr.get('fuel','—')} | {dr.get('lo',0):,.0f}/{dr.get('hi',0):,.0f} |\n")
W("\n### Thruster groups\n\n| group | atmosphere behaviour |\n|---|---|\n")
for g in d['thrust']['thrusterGroups']:
    W(f"| {g['name']} | {g['atmo']} |\n")
W("\n")

# ------------------------------------------------------------------- spectrum
W("## Spectrum emitters / detectors\n\n")
W("| block | subtype | band | trigger | tag | directional | angle° | maxStrength | gain |\n")
W("|---|---|---|---|---|---|---|---|---|\n")
for b in d['spectrum']['blocks']:
    for e in b.get('emitters') or []:
        W(f"| {b['name']} | `{b['subtype']}` | {e.get('band')} | {e.get('trigger')} | {e.get('tag')} | "
          f"{e.get('directional')} | {e.get('angleDegrees','—')} | {e.get('maxStrength',0):,.0f} | "
          f"{e.get('gain','—')} |\n")
det = [(b, x) for b in d['spectrum']['blocks'] for x in (b.get('detectors') or [])]
if det:
    W("\n### Detectors\n\n| block | detector |\n|---|---|\n")
    for b, x in det:
        W(f"| {b['name']} | `{json.dumps(x)}` |\n")
W("\n")

# --------------------------------------------------------------------- tanks
W("## Gas tanks\n\n| tank | subtype | grid | capacity | gas |\n|---|---|---|---|---|\n")
for t in sorted(d['thrust']['tanks'], key=lambda x: -x['capacity']):
    W(f"| {t['name']} | `{t['subtype']}` | {t['grid']} | {t['capacity']:,.0f} | {t['storedGas']} |\n")
W("\n")

# ------------------------------------------------------------------ parachutes
W("## Parachutes\n\n| grid | reef | minAtmo | drag | radiusMult |\n|---|---|---|---|---|\n")
for p in d['thrust']['parachutes']:
    W(f"| {p['grid']} | {p['reef']} | {p['minAtmo']} | {p['drag']} | {p['radiusMult']} |\n")
W(f"\n(parachuteAlgoVer = {d['thrust']['parachuteAlgoVer']})\n\n")

# --------------------------------------------------------------------- planets
W("## Planets\n\n| planet | gravity | atmosphere |\n|---|---|---|\n")
for p in sorted(d['thrust']['planets'], key=lambda x: -x['gravity']):
    W(f"| {p['name']} | {p['gravity']} | {'yes' if p['atmosphere'] else 'no'} |\n")
W("\n")

W("## Bulk catalogues (exported to CSV alongside this file)\n\n")
W(f"- `sdx2_blocks.csv` — {len(d['gv']['blocks'])} blocks with component recipes\n")
W(f"- `sdx2_cargo.csv` — {len(d['thrust']['cargo'])} cargo containers\n")
W(f"- `sdx2_items.csv` — {len(d['thrust']['items'])} items (mass/volume)\n")
W(f"- `sdx2_components.csv` — {len(d['gv']['components'])} components with raw-material cost\n")
W(f"- `sdx2_materials.csv` — {len(d['gv']['materials'])} materials\n")

open(os.path.join(D, 'SDX2_LIMITS.md'), 'w', encoding='utf-8').write(out.getvalue())

# ------------------------------------------------------------------ CSV dumps
def wcsv(name, rows, cols):
    with open(os.path.join(D, name), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)

blocks = []
for b in d['gv']['blocks']:
    for sz in ('large', 'small'):
        v = b.get(sz)
        if not v:
            continue
        blocks.append({'name': b['name'], 'type': b['type'], 'mod': b['mod'], 'size': sz,
                       'subtype': v['subtype'],
                       'components': ';'.join(f"{k}={n}" for k, n in (v.get('components') or {}).items())})
wcsv('sdx2_blocks.csv', blocks, ['name', 'type', 'mod', 'size', 'subtype', 'components'])
wcsv('sdx2_cargo.csv', d['thrust']['cargo'], ['name', 'subtype', 'grid', 'volume', 'category', 'subcategory'])
wcsv('sdx2_items.csv', d['thrust']['items'], ['type', 'subtype', 'name', 'mass', 'volume'])
wcsv('sdx2_components.csv',
     [{**c, 'raw': ';'.join(f"{k}={v}" for k, v in (c.get('raw') or {}).items())} for c in d['gv']['components']],
     ['subtype', 'name', 'mass', 'volume', 'raw'])
wcsv('sdx2_materials.csv', d['gv']['materials'], ['subtype', 'name', 'kind'])

print("wrote SDX2_LIMITS.md and 5 CSVs")
print("markdown size:", len(out.getvalue()), "chars")
