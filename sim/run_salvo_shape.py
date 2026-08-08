"""OFFENSIVE doctrine: does SHAPING the salvo in time beat firing it all at once?

The defensive study measured a structural weakness worth exploiting: a PDC round is bound
to ONE torpedo (ProjectileHits.cs:601), so when a torpedo dies every round already in
flight toward it is wasted -- 55-70% of all rounds fired. Rounds are in the air for
0.5-1.0 s, and the whole engagement window is only ~2.4 s.

So an attacker who arrives WHILE the defender is mid-commitment should get through
disproportionately. The candidate shapes:
  * trickle-then-mass  a few singles to induce commitment, then the bulk arriving during it
  * two pulses         half, then half after a delay
  * even stagger       spread uniformly (the anti-shape: gives PDCs a clean queue)
  * mass-then-trickle  the reverse, as a control

TORPEDO BUDGET IS FIXED across all shapes, because that is the honest comparison: torpedo
ammo is the expensive thing in the NPC economy (24x TorpedoGuidanceComputer per shot,
magazine Capacity = 1) while PDC ammo is free. The attacker's real metric is therefore
LEAKERS PER TORPEDO SPENT, not leakers.

Delays are modelled as extra start distance (delay * 260 m/s), which preserves every
round's own staged-Approach kinematics, boost phase and weave.
"""
import sys, io, math, statistics as st
from fleet_efficiency import run
import ladder as L

SEEDS = list(range(701, 725))
N = 48                      # fixed torpedo budget
Wd = 112


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def shape_all_at_once():
    return [0.0] * N


def shape_trickle_then_mass(k, spacing, gap):
    """k singles spaced `spacing` apart, then the remaining N-k together `gap` after
    the last trickle round. Trickle goes FIRST, so it launches EARLIEST = smallest delay."""
    d = [i * spacing for i in range(k)]
    mass_at = (k - 1) * spacing + gap if k else 0.0
    return d + [mass_at] * (N - k)


def shape_two_pulse(gap):
    return [0.0] * (N // 2) + [gap] * (N - N // 2)


def shape_even(total):
    return [i * total / (N - 1) for i in range(N)]


def shape_mass_then_trickle(k, spacing, gap):
    d = [0.0] * (N - k)
    return d + [gap + i * spacing for i in range(k)]


SHAPES = [
    ('all at once (baseline)',      shape_all_at_once()),
    ('trickle 4 @0.5s, gap 1.0',    shape_trickle_then_mass(4, 0.5, 1.0)),
    ('trickle 4 @1.0s, gap 2.0',    shape_trickle_then_mass(4, 1.0, 2.0)),
    ('trickle 8 @0.5s, gap 1.0',    shape_trickle_then_mass(8, 0.5, 1.0)),
    ('trickle 8 @1.0s, gap 1.5',    shape_trickle_then_mass(8, 1.0, 1.5)),
    ('trickle 12 @0.8s, gap 1.5',   shape_trickle_then_mass(12, 0.8, 1.5)),
    ('two pulse gap 1.5',           shape_two_pulse(1.5)),
    ('two pulse gap 3.0',           shape_two_pulse(3.0)),
    ('two pulse gap 6.0',           shape_two_pulse(6.0)),
    ('even stagger over 6s',        shape_even(6.0)),
    ('even stagger over 15s',       shape_even(15.0)),
    ('mass then trickle 8',         shape_mass_then_trickle(8, 0.5, 1.5)),
]


def table(n_ships, polname, pol):
    print("\n" + "=" * Wd)
    print(f"{n_ships} hull(s), {N} torpedoes total, defender = {polname}".center(Wd))
    print("=" * Wd)
    print(f"  {'salvo shape':<28}{'leak':>7}{'sd':>6}{'leak/torp':>11}{'kills':>7}"
          f"{'PDC fired':>11}{'dead%':>7}", flush=True)
    print("  " + "-" * (Wd - 4))
    keep = {}
    for name, delays in SHAPES:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=N, waves=1, seed=s,
                  engage_all=True, policy=pol, launch_delays=delays) for s in SEEDS]
        keep[name] = [r['leakers'] for r in rs]
        lk = keep[name]
        print(f"  {name:<28}{st.mean(lk):>7.2f}{st.stdev(lk):>6.2f}"
              f"{st.mean(lk)/N:>11.3f}{st.mean([r['kills'] for r in rs]):>7.2f}"
              f"{st.mean([r['fired_rounds'] for r in rs]):>11.0f}"
              f"{st.mean([r['dead_pct'] for r in rs]):>7.1f}", flush=True)
    ref = 'all at once (baseline)'
    rl = keep[ref]
    print(f"  paired vs {ref} (POSITIVE = better for the ATTACKER):")
    for name in keep:
        if name == ref:
            continue
        print(f"    {name:<28} d={st.mean([x-y for x,y in zip(keep[name],rl)]):+6.2f} "
              f"t={paired_t(keep[name],rl):+7.2f}", flush=True)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    BURST = L.with_infl_index(L.burst_ladder_only(burst=14))
    table(3, 'burst-only b14 (best legal)', BURST)
    table(3, 'no PB (baseline defence)', lambda m, ctx: (True, None))
    table(1, 'burst-only b14 (best legal)', BURST)
