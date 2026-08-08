"""SUSTAINED BATTLE — the objective is survival over many waves, not one salvo.

Everything up to here was waves=1, which is why heat looked inert (peak ~27%) and why
'rounds fired' read as a free side-note. Over a long engagement neither holds:

  PdcMcrn: 30 rounds/s x 100 heat = 3000 heat/s against heat_sink/3 = 133/s of cooling.
  Net +2867/s, so ~15.7 s of cumulative FIRING reaches MaxHeat 45000. One wave is ~2.4 s
  of firing (~7200 heat, 16%), and shedding that takes 54 SECONDS. Any wave gap shorter
  than that ratchets heat upward across waves.

  The thresholds are a trap: DegradeRof engages at 0.8*MaxHeat and only clears at 0.4,
  while overheat recovery sits at 0.822 -- above the clear point. Clearing a degrade
  needs ~135 s of not firing. In a long battle that is a one-way door.

So rounds fired IS the longevity axis, and heat-management policies must be re-tested
here: the earlier "heat cycling is inert (t=+0.00)" result was a single-wave artifact.

Scoring: 2-3 torpedo hits kill a grid, so leakers are scored against a survival
threshold rather than linearly. `waves_to_death` is the wave at which cumulative leakers
on the targeted hull reach KILL_HITS.
"""
import sys, io, math, statistics as st
from fleet_efficiency import run
import ladder as L

SEEDS = list(range(801, 813))
KILL_HITS = 3
Wd = 132


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


def pol_baseline(m, ctx):
    return True, None


def heat_cycle(cut=0.75, resume=0.35):
    """Re-tested here. ToggleWeaponFire leaves the block working, so heat still bleeds
    off while ceased (WeaponController.cs:268) -- disabling the block would freeze it."""
    def pol(m, ctx):
        f = m.heat / m.max_heat if m.max_heat else 0.0
        if m._pol_off:
            if f <= resume:
                m._pol_off = False
        elif f >= cut:
            m._pol_off = True
        return (not m._pol_off), None
    return pol


def combine(*pols):
    def pol(m, ctx):
        fire, rng = True, None
        for p in pols:
            f, r = p(m, ctx)
            fire = fire and f
            if r is not None:
                rng = r
        return fire, rng
    return pol


W = L.with_infl_index
POLICIES = [
    ('baseline (no PB)',          pol_baseline),
    ('static band .75/.5/.25',    L.static_band()),
    ('window nearest+500',        L.window_nearest(500.0)),
    ('burst-only b14',            W(L.burst_ladder_only(burst=14))),
    ('full ladder tol40 b14',     W(L.ladder_deconflict(tol=40, burst=14))),
    ('heat cycle 75/35',          heat_cycle()),
    ('burst-only + heat cycle',   combine(W(L.burst_ladder_only(burst=14)), heat_cycle())),
    ('ladder + heat cycle',       combine(W(L.ladder_deconflict(tol=40, burst=14)),
                                          heat_cycle())),
]


def table(n_ships, salvo, waves, gap):
    per_mount = salvo / (n_ships * 8.0)
    print("\n" + "=" * Wd)
    print(f"{n_ships} hull(s), salvo {salvo} ({per_mount:.2f}/mount) x {waves} waves, "
          f"{gap:.0f}s gap".center(Wd))
    print("=" * Wd)
    print(f"  {'policy':<26}{'leak/wave':>10}{'cum leak':>9}{'waves_to_death':>15}"
          f"{'fired':>8}{'peak heat%':>11}{'end heat%':>10}{'kills':>7}", flush=True)
    print("  " + "-" * (Wd - 4))
    keep = {}
    for name, pol in POLICIES:
        rs = [run(n_ships, 8, kind='PdcMcrn', salvo=salvo, waves=waves, seed=s,
                  engage_all=True, policy=pol, wave_gap=gap) for s in SEEDS]
        keep[name] = rs
        # wave at which cumulative leakers reach the grid-kill threshold
        deaths = []
        for r in rs:
            cum, died = 0, None
            for i, (lk, _kl, _hot) in enumerate(r['per_wave'], 1):
                cum += lk
                if cum >= KILL_HITS and died is None:
                    died = i
            deaths.append(died if died is not None else waves + 1)
        lk_tot = [r['leakers'] for r in rs]
        print(f"  {name:<26}{st.mean(lk_tot)/waves:>10.2f}{st.mean(lk_tot):>9.2f}"
              f"{st.mean(deaths):>15.2f}"
              f"{st.mean([r['fired_rounds'] for r in rs]):>8.0f}"
              f"{st.mean([r['peak_heat'] for r in rs]):>11.1f}"
              f"{st.mean([r['per_wave'][-1][2] * 100 for r in rs]):>10.1f}"
              f"{st.mean([r['kills'] for r in rs]):>7.1f}", flush=True)
    ref = 'burst-only b14'
    rl = [r['leakers'] for r in keep[ref]]
    rh = [r['peak_heat'] for r in keep[ref]]
    print(f"  paired vs {ref}:")
    for name in keep:
        if name == ref:
            continue
        l2 = [r['leakers'] for r in keep[name]]
        h2 = [r['peak_heat'] for r in keep[name]]
        print(f"    {name:<26} cumleak d={st.mean([x-y for x,y in zip(l2,rl)]):+6.2f} "
              f"t={paired_t(l2,rl):+7.2f} | peakheat d={st.mean([x-y for x,y in zip(h2,rh)]):+6.1f} "
              f"t={paired_t(h2,rh):+7.2f}", flush=True)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    # SURVIVABLE waves only. At salvo 48+ every hull dies in wave 1 (8-14 leakers,
    # threshold 3), so waves_to_death saturates and measures nothing. A long-battle
    # test needs waves the fleet can actually absorb, so that HEAT is what eventually
    # ends it rather than the opening salvo. 3 hulls at salvo 16-24 leak ~0-1/wave.
    table(3, 16, 20, 6.0)
    table(3, 24, 20, 6.0)
    table(3, 24, 20, 15.0)
    table(3, 32, 16, 6.0)
