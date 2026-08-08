"""Parse WeaponCore CoreParts C# definition files into nested dicts.

Handles the object-initializer subset used by SDX2:
    Field = value,
    Field = new SomeDef { ... },
    Field = new[] { a, b, c },
    Field = Random(start: -1, end: 1),
    Field = (int)((3000d/3000d)*60d - 1d),
"""
import re, os, json, sys

ROOT = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\244850\3580645761\Data\Scripts\Mod\CoreParts"


def strip_comments(src: str) -> str:
    out = []
    i, n = 0, len(src)
    in_str = False
    while i < n:
        c = src[i]
        if in_str:
            if c == '\\':
                out.append(src[i:i + 2]); i += 2; continue
            if c == '"':
                in_str = False
            out.append(c); i += 1; continue
        if c == '"':
            in_str = True; out.append(c); i += 1; continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = (j + 2) if j != -1 else n
            continue
        out.append(c); i += 1
    return ''.join(out)


def match_brace(s: str, start: int) -> int:
    """start = index of '{'. Returns index of matching '}'."""
    depth = 0
    i, n = start, len(s)
    in_str = False
    while i < n:
        c = s[i]
        if in_str:
            if c == '\\':
                i += 2; continue
            if c == '"':
                in_str = False
            i += 1; continue
        if c == '"':
            in_str = True; i += 1; continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_top(body: str):
    """Split an initializer body on top-level commas."""
    parts, depth, cur, in_str = [], 0, [], False
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if in_str:
            cur.append(c)
            if c == '\\':
                cur.append(body[i + 1]); i += 2; continue
            if c == '"':
                in_str = False
            i += 1; continue
        if c == '"':
            in_str = True; cur.append(c); i += 1; continue
        if c in '{[(':
            depth += 1
        elif c in '}])':
            depth -= 1
        if c == ',' and depth == 0:
            parts.append(''.join(cur)); cur = []; i += 1; continue
        cur.append(c); i += 1
    if ''.join(cur).strip():
        parts.append(''.join(cur))
    return [p.strip() for p in parts if p.strip()]


NUM_EXPR = re.compile(r'^[\s\d\.\+\-\*/\(\)dfDFeE]+$')


def coerce(v: str):
    v = v.strip()
    if v in ('true', 'false'):
        return v == 'true'
    # cast prefix e.g. (int)(...)
    m = re.match(r'^\((?:int|float|double|long)\)\s*(.*)$', v, re.S)
    if m:
        inner = coerce(m.group(1))
        if isinstance(inner, float):
            return int(inner) if v.startswith('(int)') or v.startswith('(long)') else inner
        return inner
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    # numeric literal or arithmetic expression with C# suffixes
    if NUM_EXPR.match(v):
        expr = re.sub(r'(?<=[\d\.])[dfDF]\b', '', v)
        expr = re.sub(r'(?<=[\d\.])[dfDF](?=[\s\)\*/\+\-]|$)', '', expr)
        try:
            r = eval(expr, {"__builtins__": {}}, {})
            if isinstance(r, (int, float)):
                return r
        except Exception:
            pass
    m = re.match(r'^Random\s*\(\s*start:\s*([^,]+),\s*end:\s*([^\)]+)\)$', v, re.S)
    if m:
        return {"_random": [coerce(m.group(1)), coerce(m.group(2))]}
    m = re.match(r'^Vector\s*\((.*)\)$', v, re.S)
    if m:
        vals = [coerce(re.sub(r'^\s*\w+:\s*', '', p)) for p in split_top(m.group(1))]
        return {"_vector": vals}
    m = re.match(r'^Color\s*\((.*)\)$', v, re.S)
    if m:
        return {"_color": [coerce(p) for p in split_top(m.group(1))]}
    return v  # bare identifier / enum


def _item(p: str):
    """An array element: either a nested object literal or a scalar."""
    p = p.strip()
    if re.match(r'^new\s*(?:[A-Za-z_][\w\.]*)?\s*(?:\[\s*\])?\s*\{', p, re.S):
        b = p.index('{')
        e = match_brace(p, b)
        return parse_init(p[b + 1:e])
    return coerce(p)


def parse_init(body: str):
    """Parse the inside of a { ... } initializer into a dict (or list)."""
    parts = split_top(body)
    if not parts:
        return {}
    # array-like if no top-level '=' assignments
    if not any(re.match(r'^\s*[A-Za-z_]\w*\s*=', p) for p in parts):
        return [_item(p) for p in parts]
    out = {}
    for p in parts:
        m = re.match(r'^\s*([A-Za-z_]\w*)\s*=\s*(.*)$', p, re.S)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        m2 = re.match(r'^new\s*(?:[A-Za-z_][\w\.]*)?\s*(?:\[\s*\])?\s*\{', val, re.S)
        if m2:
            b = val.index('{')
            e = match_brace(val, b)
            out[key] = parse_init(val[b + 1:e])
        else:
            out[key] = coerce(val)
    return out


DEF_RE = re.compile(
    r'(?:public|private|internal)?\s*(AmmoDef|WeaponDefinition|ArmorDefinition)\s+'
    r'([A-Za-z_]\w*)\s*(?:=>|=)\s*new\s+\1\s*\{', re.S)

METHOD_RE = re.compile(
    r'(?:private|public|internal)\s+(WeaponDefinition|AmmoDef)\s+([A-Za-z_]\w*)\s*\(\s*\)\s*\{', re.S)


def parse_file(path: str):
    src = strip_comments(open(path, encoding='utf-8-sig', errors='replace').read())
    found = {}
    for m in DEF_RE.finditer(src):
        kind, name = m.group(1), m.group(2)
        b = src.index('{', m.end() - 1)
        e = match_brace(src, b)
        if e == -1:
            continue
        found[name] = {"_kind": kind, "_file": os.path.relpath(path, ROOT), **_asdict(parse_init(src[b + 1:e]))}
    # methods returning `return new WeaponDefinition { ... };`
    for m in METHOD_RE.finditer(src):
        kind, name = m.group(1), m.group(2)
        tail = src[m.end():]
        rm = re.search(r'return\s+new\s+' + kind + r'\s*\{', tail)
        if not rm:
            continue
        b = m.end() + tail.index('{', rm.end() - 1)
        e = match_brace(src, b)
        if e == -1:
            continue
        found[name] = {"_kind": kind, "_file": os.path.relpath(path, ROOT), **_asdict(parse_init(src[b + 1:e]))}
    return found


def _asdict(x):
    return x if isinstance(x, dict) else {"_value": x}


def main():
    all_defs = {}
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if not f.endswith('.cs'):
                continue
            p = os.path.join(dirpath, f)
            try:
                all_defs.update(parse_file(p))
            except Exception as ex:
                print(f"ERR {f}: {ex}", file=sys.stderr)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coreparts.json')
    json.dump(all_defs, open(out, 'w'), indent=1, default=str)
    kinds = {}
    for k, v in all_defs.items():
        kinds.setdefault(v.get('_kind'), []).append(k)
    for k, v in sorted(kinds.items()):
        print(f"{k}: {len(v)}")
    print("wrote", out)


if __name__ == '__main__':
    main()
