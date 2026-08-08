"""Resolve SDX2 WeaponDefinition property-getter inheritance chains.

Pattern:
    public WeaponDefinition PdcUnnAdv { get {
        var b = PdcUnn;                    // or BasePdcDefinition()
        b.HardPoint.Loading.RateOfFire = 1200;
        b.Ammos = new[] { PDC40mm, };
        return b;
    } }
"""
import re, os, json, copy, sys
from parse_coreparts import strip_comments, match_brace, parse_init, coerce, split_top, ROOT

# ---- pass 1: base definitions built by methods -------------------------------
BASES = {}
GETTERS = {}   # name -> (parentExpr, [(path, valuetext)])

GETTER_RE = re.compile(
    r'public\s+WeaponDefinition\s+([A-Za-z_]\w*)\s*\{\s*get\s*\{', re.S)
METHOD_RE = re.compile(
    r'private\s+WeaponDefinition\s+([A-Za-z_]\w*)\s*\(\s*\)\s*\{', re.S)


def scan(path):
    src = strip_comments(open(path, encoding='utf-8-sig', errors='replace').read())
    for m in METHOD_RE.finditer(src):
        name = m.group(1)
        b = src.index('{', m.end() - 1)
        e = match_brace(src, b)
        body = src[b + 1:e]
        rm = re.search(r'return\s+new\s+WeaponDefinition\s*\{', body)
        if rm:
            bb = body.index('{', rm.end() - 1)
            ee = match_brace(body, bb)
            BASES[name] = parse_init(body[bb + 1:ee])
    for m in GETTER_RE.finditer(src):
        name = m.group(1)
        b = src.index('{', m.end() - 1)
        e = match_brace(src, b)
        body = src[b + 1:e]
        pm = re.search(r'var\s+(\w+)\s*=\s*([A-Za-z_]\w*)\s*(\(\s*\))?\s*;', body)
        if not pm:
            continue
        var, parent = pm.group(1), pm.group(2)
        overrides = []
        # statement-level split on ';' at depth 0
        depth, cur, stmts = 0, [], []
        instr = False
        i = 0
        while i < len(body):
            c = body[i]
            if instr:
                cur.append(c)
                if c == '\\':
                    cur.append(body[i + 1]); i += 2; continue
                if c == '"':
                    instr = False
                i += 1; continue
            if c == '"':
                instr = True; cur.append(c); i += 1; continue
            if c in '{[(':
                depth += 1
            elif c in '}])':
                depth -= 1
            if c == ';' and depth == 0:
                stmts.append(''.join(cur)); cur = []; i += 1; continue
            cur.append(c); i += 1
        for s in stmts:
            s = s.strip()
            am = re.match(r'^' + var + r'\.([\w\.]+)\s*=\s*(.*)$', s, re.S)
            if am:
                overrides.append((am.group(1), am.group(2).strip()))
                continue
            sm = re.match(r'^' + var + r'\.AddSuffix\((.*)\)$', s, re.S)
            if sm:
                overrides.append(('_AddSuffix', sm.group(1)))
        GETTERS[name] = (parent, overrides)


for dp, _, fs in os.walk(ROOT):
    for f in fs:
        if f.endswith('.cs'):
            scan(os.path.join(dp, f))


# ---- pass 2: resolve ---------------------------------------------------------
def setpath(d, path, val):
    keys = path.split('.')
    for k in keys[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    d[keys[-1]] = val


def parse_val(v):
    v = v.strip()
    m = re.match(r'^new\s*(?:[A-Za-z_][\w\.]*)?\s*(?:\[\s*\])?\s*\{', v, re.S)
    if m:
        b = v.index('{'); e = match_brace(v, b)
        return parse_init(v[b + 1:e])
    m = re.match(r'^Builders\.TurretMountPoint\((.*)\)$', v, re.S)
    if m:
        args = [coerce(a.strip()) for a in split_top(m.group(1))]
        return {"_mount": args}
    return coerce(v)


RESOLVED = {}
_stack = set()


def resolve(name):
    if name in RESOLVED:
        return RESOLVED[name]
    if name in BASES:
        RESOLVED[name] = copy.deepcopy(BASES[name]); return RESOLVED[name]
    if name not in GETTERS:
        return None
    if name in _stack:
        return None
    _stack.add(name)
    parent, overs = GETTERS[name]
    base = resolve(parent)
    d = copy.deepcopy(base) if base else {}
    for path, val in overs:
        if path == '_AddSuffix':
            continue
        setpath(d, path, parse_val(val))
    _stack.discard(name)
    RESOLVED[name] = d
    return d


for n in list(GETTERS) + list(BASES):
    resolve(n)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weapons.json')
json.dump(RESOLVED, open(out, 'w'), indent=1, default=str)
print(f"bases={len(BASES)} getters={len(GETTERS)} resolved={len(RESOLVED)}")
print("wrote", out)
