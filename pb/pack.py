"""Build the single-paste and minified FleetPD artifacts.

Minification strips comments and collapses whitespace only. It does NOT rename
identifiers — that buys little and risks breaking a script nobody can debug in the
in-game editor. What it does buy is the thing actually worth protecting: the reasoning.
The constants stay, but why K=4 rather than 14, why in-flight beats a shot counter, and
why fire is never withheld all live in the comments.

String and char literals are extracted before any regex runs, so a `//` or `/*` inside a
literal cannot truncate the file.
"""
import io
import os
import re
import sys

API = (r"C:\Users\slob\AppData\Local\Temp\claude\D--SE-Common-main"
       r"\4d2e7beb-1ce3-4782-9446-c3b1b83a0edb\scratchpad\wcbuild\src\Api"
       r"\CoreSystemsPbApi.cs")
PB = r"D:\sdx2-pd\pb"

BANNER = """// FleetPD — SDX2 fleet point defence, single-paste build.
// https://github.com/xianson/sdx2-pd    (docs/DOCTRINE.md for the reasoning)
//
// Paste the WHOLE file into a Programmable Block and recompile. Nothing to configure.
// Requires WeaponCore (CoreSystems) in the world.
//
// The WcPbApi class at the bottom is WeaponCore's own published PB API shim by
// Ash-LikeSnow, included verbatim so this is a single paste:
// https://github.com/Ash-LikeSnow/WeaponCore
"""

MIN_BANNER = """// FleetPD (minified) — https://github.com/xianson/sdx2-pd
// Readable source, with the measurements and reasoning, is pb/FleetPD.cs in that repo.
// Includes WeaponCore's published WcPbApi shim (Ash-LikeSnow), verbatim.
"""


def extract_class(src, decl):
    """Return the full text of a class declaration plus its balanced brace body."""
    i = src.index(decl)
    j = src.index('{', i)
    depth = 0
    k = j
    while True:
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                break
        k += 1
    return src[i:k + 1]


def minify(src):
    """Strip comments and blank lines in ONE pass over the source.

    The obvious two-pass version (mask literals, then regex out comments) is WRONG: an
    apostrophe inside a comment — "doesn't", "hull's" — opens a phantom char literal that
    swallows everything to the next quote, braces included, and yields a file that does
    not compile. Comments and literals have to be recognised by the same scanner.
    """
    BS = chr(92)
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ''
        if c == '/' and nxt == '/':
            while i < n and src[i] != chr(10):
                i += 1
            continue
        if c == '/' and nxt == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            continue
        if c == '@' and nxt == '"':                 # verbatim string: "" escapes
            j = i + 2
            while j < n:
                if src[j] == '"':
                    if j + 1 < n and src[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
            continue
        if c == '"' or c == "'":
            j = i + 1
            while j < n:
                if src[j] == BS:
                    j += 2
                    continue
                if src[j] == c:
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
            continue
        out.append(c)
        i += 1
    s = ''.join(out)
    s = chr(10).join(line.strip() for line in s.split(chr(10)))
    s = chr(10).join(line for line in s.split(chr(10)) if line)
    return s


def main():
    api = io.open(API, encoding='utf-8-sig').read()
    wcapi = extract_class(api, 'public class WcPbApi')
    script = io.open(os.path.join(PB, 'FleetPD.cs'), encoding='utf-8').read()

    unified = BANNER + '\n' + script + '\n\n' + wcapi + '\n'
    io.open(os.path.join(PB, 'FleetPD.unified.cs'), 'w', encoding='utf-8').write(unified)

    mini = MIN_BANNER + minify(script) + '\n' + minify(wcapi) + '\n'
    io.open(os.path.join(PB, 'FleetPD.min.cs'), 'w', encoding='utf-8').write(mini)

    print('unified : %5d lines %7d chars' % (unified.count('\n'), len(unified)))
    print('minified: %5d lines %7d chars  (%.0f%% of unified)'
          % (mini.count('\n'), len(mini), 100.0 * len(mini) / len(unified)))
    # PB source limit is 100k characters; warn well before it.
    if len(mini) > 90000:
        print('WARNING: minified build is close to the PB 100k character limit')
    return 0


if __name__ == '__main__':
    sys.exit(main())
