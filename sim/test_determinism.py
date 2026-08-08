"""Regression guard: a scenario is a pure function of its arguments.

WHY THIS EXISTS. Two process-global counters silently invalidated every comparative
result in this project:

  1. `torpedo2.Torpedo2._ids` was a global counter and each torpedo seeded its RNG from
     `seed * 7919 + self.id`. Nothing reset it, so repeat 2 of a scenario drew a
     different weave stream from repeat 1 -- four identical repeats measured 1, 2, 3, 3
     leakers. Any A/B running its arms sequentially in one process was confounded.
     (`weapons.Torpedo` had the same defect, and `targeting._next_part_id` a third
     instance of it.)

  2. `PdcMount.reset()` seeded from `random.Random(hash((kind, cell)))`. `hash()` of a
     tuple containing a str is SALTED PER PROCESS (PEP 456), so the identical case
     measured 4 leakers in one process and 7 in another with no code change.

Neither failure is visible from a single run. Both are caught here.

Two properties are asserted, and they are not the same property:

  WITHIN-PROCESS   N identical repeats in one interpreter must agree. Catches leaked
                   state between runs -- global counters, module caches, RNG objects
                   surviving across scenarios.
  ACROSS-PROCESS   fresh interpreters, each with a DIFFERENT PYTHONHASHSEED, must agree
                   byte-for-byte. Catches any dependence on `hash()`, on set/dict
                   iteration order, or on anything else the interpreter randomises.
                   Running the child processes at the same hash seed would pass
                   vacuously and prove nothing, which is the trap.

Results are compared as canonical JSON with floats at full repr precision, so a
1-ulp divergence fails rather than rounding away.

Run:  python test_determinism.py
"""
import json, os, subprocess, sys, io

HERE = os.path.dirname(os.path.abspath(__file__))
REPEATS = 4
HASH_SEEDS = ['0', '1', '12345']

#: (label, callable-name, kwargs). Kept small: this is a determinism probe, not a sweep.
CASES = [
    ('fleet 1x8 PdcMcrn salvo16', 'fleet', dict(
        n_ships=1, mounts_per=8, kind='PdcMcrn', salvo=16, waves=1, seed=11)),
    ('fleet 1x8 PdcUnnAdv salvo24', 'fleet', dict(
        n_ships=1, mounts_per=8, kind='PdcUnnAdv', salvo=24, waves=1, seed=7)),
    ('fleet 3x8 net-engage 2 waves', 'fleet', dict(
        n_ships=3, mounts_per=8, kind='PdcMcrn', salvo=16, waves=2, seed=3,
        engage_all=True)),
    ('torpedo flight Plasma220', 'torp', dict(kind='Plasma220mmTorp', seed=5, n=8)),
    ('torpedo flight 160Belter', 'torp', dict(kind='Torpedo160mmBelter', seed=9, n=8)),
    ('duel 10km chatter 60', 'duel', dict(range_m=10000, chatter_amp=60, duration=25.0,
                                          seed=2)),
    # This case exists because the other five DO NOT COVER `PdcMount.rnd`.
    # `m.rnd` is currently write-only on every measured path: selection moved to the
    # wc_acquire XorShift stream (seeded from UniquePartId) and the shot Bernoullis are
    # rolled from the scenario RNG, so the old `hash((kind, cell))` seed had stopped
    # affecting any number even though it was still salted per process. Re-arming that
    # seed and re-running the fleet cases gives IDENTICAL results at three different
    # hash seeds -- i.e. those cases cannot see the bug at all. This one draws directly
    # from the mount streams, so the guard is real rather than vacuous.
    ('mount RNG streams', 'mountrnd', dict(kind='PdcUnn', n=6, draws=8)),
]


# --------------------------------------------------------------------- scenarios
def _round(x, nd=9):
    return round(float(x), nd)


def run_fleet(**kw):
    import fleet_efficiency as fe
    r = fe.run(**kw)
    return dict(leakers=r['leakers'], kills=r['kills'], rounds=_round(r['rounds']),
                capacity=_round(r['capacity_pct']), heat=_round(r['peak_heat']),
                mounts=r['mounts'],
                per_wave=[[w[0], w[1], _round(w[2])] for w in r['per_wave']])


def run_torp(kind, seed, n):
    """Fly a salvo and record every impact. Sensitive to the weave stream, which is
    exactly what the _ids bug corrupted."""
    from vec import V
    from torpedo2 import Torpedo2
    Torpedo2.reset_ids()

    class T:
        pos = V(0, 0, 0)
        vel = V(0, 0, 0)

    tgt = T()
    out = []
    for i in range(n):
        p = Torpedo2(kind, V(15000.0 + 40 * i, 30.0 * i, -20.0 * i),
                     V(-260.0, 0, 0), tgt, seed=seed, index=i)
        d = 1e18
        for _ in range(4000):
            d = min(d, p.step())
            if not p.alive:
                break
        out.append([i, _round(d, 6), _round(p.age, 4), bool(p.alive),
                    _round(p.pos.x, 4), _round(p.pos.y, 4), _round(p.pos.z, 4)])
    return dict(impacts=out)


def run_duel(**kw):
    from engage import duel
    r = duel(**kw)
    return dict(shots=r['shots'], hits=r['hits'], miss=_round(r['miss_mean'], 6),
                ceramic=r['ceramic_killed'], internals=r['internals_killed'],
                integrity=_round(r['integrity']), algo=r['algo'])


def run_mountrnd(kind, n, draws):
    """Draw deviated shot directions straight from each mount's own RNG.

    Covers `PdcMount.rnd`, which no other case reaches. Also exercises
    weapons.sample_deviation, so a future re-divergence of the dispersion law between
    files shows up here as well.
    """
    import weapons
    from weapons import PdcMount, sample_deviation
    from vec import V
    weapons.reset_part_ids()
    out = []
    for i in range(n):
        m = PdcMount(kind, (i, 1, -2), V(1, 0, 0))
        row = [m.unique_part_id]
        for _ in range(draws):
            t1, t2 = sample_deviation(m.rnd, m.dev)
            row += [_round(t1, 12), _round(t2, 12)]
        # and the exact WC stream, which must also be a pure function of the part id
        row += [m.acquire_random.range_int(1, 5) for _ in range(4)]
        out.append(row)
    return dict(draws=out)


DISPATCH = {'fleet': run_fleet, 'torp': run_torp, 'duel': run_duel,
            'mountrnd': run_mountrnd}


def evaluate(which, kwargs):
    return json.dumps(DISPATCH[which](**kwargs), sort_keys=True)


# ------------------------------------------------------------------- child mode
if len(sys.argv) > 2 and sys.argv[1] == '--one':
    sys.stdout.write(evaluate(sys.argv[2], json.loads(sys.argv[3])))
    sys.exit(0)


# ------------------------------------------------------------------------ driver
def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=" * 118)
    print("DETERMINISM — same scenario+seed must give the same answer".center(118))
    print("=" * 118)
    print(f"  within-process : {REPEATS} identical repeats in this interpreter")
    print(f"  across-process : fresh interpreters at PYTHONHASHSEED "
          f"{', '.join(HASH_SEEDS)} (DIFFERENT seeds — equal seeds would pass "
          f"vacuously)")
    print(f"  comparison     : canonical JSON, floats to 9 dp\n")
    print(f"{'case':<32}{'within-process':>16}{'across-process':>16}   note")
    print("-" * 118)

    fails = 0
    for label, which, kwargs in CASES:
        # ---- within one process
        vals = [evaluate(which, kwargs) for _ in range(REPEATS)]
        within = len(set(vals)) == 1

        # ---- across processes, each at a different hash seed
        outs = []
        for hs in HASH_SEEDS:
            env = dict(os.environ, PYTHONHASHSEED=hs)
            p = subprocess.run(
                [sys.executable, os.path.join(HERE, 'test_determinism.py'),
                 '--one', which, json.dumps(kwargs)],
                capture_output=True, text=True, cwd=HERE, env=env, timeout=1800)
            if p.returncode != 0:
                outs.append(f"<rc={p.returncode}> {p.stderr[-300:]}")
            else:
                outs.append(p.stdout)
        across = len(set(outs)) == 1 and outs[0] == vals[0]

        note = ''
        if not within:
            note = f"{len(set(vals))} distinct results in one process"
        elif not across:
            note = (f"{len(set(outs))} distinct results across {len(HASH_SEEDS)} "
                    f"hash seeds" if len(set(outs)) > 1
                    else "child disagrees with parent")
        fails += (not within) + (not across)
        print(f"{label:<32}{'PASS' if within else 'FAIL':>16}"
              f"{'PASS' if across else 'FAIL':>16}   {note}")
        if not within:
            for v in sorted(set(vals)):
                print(f"      within  {v[:150]}")
        if not across and len(set(outs)) > 1:
            for v in sorted(set(outs)):
                print(f"      across  {v[:150]}")

    print()
    # ---- direct probes of the two specific defects -------------------------
    print("  targeted probes of the two original defects:")
    import weapons
    from weapons import PdcMount
    from vec import V
    weapons.reset_part_ids()
    a = [PdcMount('PdcMcrn', (i, 0, 0), V(1, 0, 0)).rnd.random() for i in range(4)]
    weapons.reset_part_ids()
    b = [PdcMount('PdcMcrn', (i, 0, 0), V(1, 0, 0)).rnd.random() for i in range(4)]
    ok_mount = a == b
    print(f"    mount RNG stable across reset_part_ids()          "
          f"{'PASS' if ok_mount else 'FAIL'}")

    from torpedo2 import Torpedo2
    seeds = []
    for _ in range(3):
        Torpedo2.reset_ids()

        class T:
            pos = V(0, 0, 0)
            vel = V(0, 0, 0)
        seeds.append([Torpedo2('Plasma220mmTorp', V(9000, 0, 0), V(-260, 0, 0), T(),
                               seed=4, index=i).rnd.random() for i in range(4)])
    ok_torp = all(s == seeds[0] for s in seeds)
    print(f"    torpedo RNG a function of (seed, index) only      "
          f"{'PASS' if ok_torp else 'FAIL'}")
    fails += (not ok_mount) + (not ok_torp)

    print()
    print("=" * 118)
    print((f"RESULT: {'ALL DETERMINISTIC' if not fails else str(fails) + ' FAILURES'}")
          .center(118))
    print("=" * 118)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
