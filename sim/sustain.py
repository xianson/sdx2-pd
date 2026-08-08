"""Sustained-battle policies + instrumentation.

Everything before this file optimised one 2.4 s salvo. Here the objective is
SURVIVAL over many waves: waves_to_death (cumulative leakers on the targeted hull
reaching KILL_HITS) and cumulative leakers, not per-wave leakers.

`run_x` replicates fleet_efficiency.run()'s loop exactly (validated bit-identical
when attrition=0) so that between-wave hooks exist WITHOUT touching shared files:
  * per-wave fired/wasted counts, mount snapshots (rounds, reloading, heat, rung)
  * optional attrition: leakers permanently destroy mounts. OWN MODEL ASSUMPTION,
    not verified game behaviour -- the real mod damages the hull generically and
    never kills a PDC.

Reload model recap (weapons.py, PdcMcrn): 5 mags x 120 = 600 rounds, then a 5.0 s
reload that only STARTS at rounds==0 and keeps counting down while idle -- so a
reload that begins in (or shortly before) a 6 s wave gap is free, and one that
begins mid-wave costs the rest of that wave. There is no way to trigger a reload
early: the only ammo lever a policy has is which mounts do the firing.
"""
import math, random, statistics as st
import weapons
from vec import V
from ship import Ship, DT
from shipyard import build_ship
from torpedo2 import Torpedo2
from weapons import PDC_ALIAS
from fleet_efficiency import wave, class_speed_mps
import ladder as L

KILL_HITS = 3


# ------------------------------------------------------------------ driver
def run_x(n_ships=3, mounts_per=8, kind='PdcMcrn', salvo=16, waves=20, seed=1,
          wave_gap=6.0, policy=None, torp_kind='Plasma220mmTorp', spacing=500.0,
          cls='Corvette', engage_all=True, attrition=0.0, snapshots=False):
    """fleet_efficiency.run() with between-wave hooks. Same RNG discipline, so
    attrition=0 reproduces run() leak-for-leak (see validate() in run_sustain)."""
    weapons.reset_part_ids()
    Torpedo2.reset_ids()
    weapons.Torpedo.reset_ids()
    rnd = random.Random(seed)
    fleet = []
    for s in range(n_ships):
        hull, man, mounts = build_ship(cls, pdc_mix={PDC_ALIAS[kind]: mounts_per},
                                       n_rcs=200, seed=seed + s)
        sh = Ship(hull, V(0, s * spacing, 0), V(0, 0, 0), class_speed_mps(cls),
                  drive_thrust=292e6 * 2)
        for m in mounts:
            m.reset()
        fleet.append([sh, hull, list(mounts)])
    kill_rnd = random.Random(seed * 7919 + 13)  # own stream: never perturbs wave RNG
    per_wave, fired_w, wasted_w, snaps, lost_w, hot_w = [], [], [], [], [], []
    for w in range(waves):
        flt = [tuple(f) for f in fleet]
        lk, kl, _eng, _tk, wst = wave(flt, salvo, torp_kind, rnd, spacing,
                                      policy=policy, engage_all=engage_all)
        per_wave.append((lk, kl))
        fired_w.append(wst['fired'])
        wasted_w.append(wst['wasted'])
        hot_w.append(max((m.heat / m.max_heat for f in fleet for m in f[2]),
                         default=0.0))          # end-of-wave, pre-gap
        if snapshots:
            snap = []
            for si, f in enumerate(fleet):
                for i, m in enumerate(f[2]):
                    lb = getattr(m, '_lb', None)
                    snap.append((si, i, m.shots_fired, m.rounds, m.reloading,
                                 m.heat / m.max_heat, lb['rung'] if lb else -1))
            snaps.append(snap)
        lost = 0
        if attrition > 0.0:
            tgt = fleet[0][2]
            for _ in range(lk):
                if tgt and kill_rnd.random() < attrition:
                    tgt.pop(kill_rnd.randrange(len(tgt)))
                    lost += 1
        lost_w.append(lost)
        if wave_gap:
            for f in fleet:
                for m in f[2]:
                    for _ in range(int(wave_gap * 60)):
                        m.step(DT, False)
    cum, died = 0, None
    for i, (lk, _kl) in enumerate(per_wave, 1):
        cum += lk
        if cum >= KILL_HITS and died is None:
            died = i
    return dict(leakers=sum(p[0] for p in per_wave),
                kills=sum(p[1] for p in per_wave),
                waves_to_death=died if died is not None else waves + 1,
                fired_rounds=sum(fired_w), per_wave=per_wave, fired_w=fired_w,
                wasted_w=wasted_w, snaps=snaps, mounts_lost=sum(lost_w),
                peak_heat=100.0 * max(hot_w) if hot_w else 0.0,
                end_heat=100.0 * hot_w[-1] if hot_w else 0.0)


# --------------------------------------------------------- instrumentation
def instrument(pol, acc):
    """Sample per-PB-tick (1/6 s) reload state through the policy interface.
    acc['reload_pbt'][wave] counts battery mount-PB-ticks spent with reloading>0
    while a wave is live -- i.e. mount-time out of action WHEN IT MATTERED. A real
    PB has this natively (IsWeaponReadyToFire / inventory)."""
    def wrapped(m, ctx):
        if '_iw' not in ctx:                 # once per PB tick
            ctx['_iw'] = True
            if ctx['t'] < acc.get('last_t', -1.0):
                acc['wave'] = acc.get('wave', 0) + 1
            acc['last_t'] = ctx['t']
        if m.reloading > 0:
            w = acc.get('wave', 0)
            rp = acc.setdefault('reload_pbt', {})
            rp[w] = rp.get(w, 0) + 1
        return pol(m, ctx)
    return wrapped


# --------------------------------------------------------------- policies
def respread(inner, n_bands=len(L.LADDER)):
    """CROSS-WAVE PRE-POSITIONING. At each wave boundary (PB clock reset; in game,
    GetProjectilesLockedOn going 0 -> N) reset every mount's ladder state to the
    opening spread. Costs nothing during the fight; wave N+1 opens from the
    designed configuration instead of wherever wave N collapsed to."""
    def pol(m, ctx):
        lt = getattr(m, '_rs_t', None)
        if lt is not None and ctx['t'] < lt:
            lb = getattr(m, '_lb', None)
            if lb is not None:
                lb['rung'] = m._idx % n_bands
                lb['base'] = m.shots_fired
                lb['since'] = ctx['t']
                lb['bottom_at'] = None
        m._rs_t = ctx['t']
        return inner(m, ctx)
    return pol


def bottomfix(inner):
    """Isolate ONE mechanism of respread: ladder_deconflict keys its bottom-rung
    recycle timer to the within-wave PB clock ('bottom_at'), which RESETS each
    wave. A mount that bottomed at t=8 of wave N cannot satisfy
    t - bottom_at >= dwell until t=8.35 of wave N+1, so it sits at 0.28x range
    for most of the next wave. This wrapper only re-zeroes that timer at the
    boundary; rungs keep whatever spread wave N produced."""
    def pol(m, ctx):
        lt = getattr(m, '_bf_t', None)
        if lt is not None and ctx['t'] < lt:
            lb = getattr(m, '_lb', None)
            if lb is not None and lb.get('bottom_at') is not None:
                lb['bottom_at'] = ctx['t']       # restart dwell, don't strand it
        m._bf_t = ctx['t']
        return inner(m, ctx)
    return pol


def adaptive_burst(mk_inner, b0=14, b_min=8, b_max=26, step=4, target=None):
    """WAVE-TO-WAVE ADAPTATION of the burst budget, from a legal signal only:
    the battery's own rounds fired last wave (shots_fired is own state; a real
    PB owns every MonitorProjectile callback). Heuristic: rounds per wave well
    above the sustainable cooling budget -> shrink bursts (more re-aims, less
    spray); rounds well below -> grow bursts (fewer churn re-aims).
    `target` defaults to 24 mounts * a ~500 rounds/wave envelope scaled at call.
    Rebuilds the inner policy whenever the burst changes; mount rung state is
    carried by the mounts themselves, so this is seamless."""
    state = {'burst': b0, 'pol': None, 'last_t': -1.0, 'sf': {}, 'tot_prev': None}

    def pol(m, ctx):
        if state['pol'] is None:
            state['pol'] = mk_inner(state['burst'])
        if ctx['t'] < state['last_t']:           # wave boundary (once per tick)
            tot = sum(state['sf'].values())
            prev = state['tot_prev']
            if prev is not None:
                tgt = target if target is not None else 20 * ctx['n_mounts']
                dw = tot - prev                  # rounds fired in the last wave
                b = state['burst']
                if dw > tgt * 1.2:
                    b = max(b_min, b - step)
                elif dw < tgt * 0.8:
                    b = min(b_max, b + step)
                if b != state['burst']:
                    state['burst'] = b
                    state['pol'] = mk_inner(b)
            state['tot_prev'] = tot
        state['last_t'] = ctx['t']
        state['sf'][(m._ship, m._idx)] = m.shots_fired
        if state['tot_prev'] is None:
            state['tot_prev'] = 0.0
        return state['pol'](m, ctx)
    return pol


def cliff_guard(inner, cut=0.78, resume=0.74):
    """Exploit the POSITION of the DegradeRof cliff (0.8 engage / 0.4 clear /
    0.822 overheat-release: a one-way door). Tight hysteresis just below the
    cliff: hold fire only in [resume, cut], a few PB ticks at a time, so a mount
    never crosses 0.8 and never earns the 135 s degrade or 60 s overheat.
    NOT the dead 'heat cycling' (cut .75 / resume .35), which parked mounts for
    tens of seconds; this one shaves the top off. Distinct objective: keep the
    battery below the cliff for the WHOLE battle."""
    def pol(m, ctx):
        f, r = inner(m, ctx)
        frac = m.heat / m.max_heat if m.max_heat else 0.0
        hold = getattr(m, '_cg', False)
        if hold and frac <= resume:
            hold = False
        elif not hold and frac >= cut:
            hold = True
        m._cg = hold
        return (f and not hold), r
    return pol


def heat_floor(inner, knee=0.75, bands=L.LADDER):
    """Redirect-not-withhold heat response: heat forces a mount DOWN the ladder
    (shorter range) instead of off. A hot mount still kills close threats; it
    stops long-range spraying, which is where its rounds are least likely to
    matter per unit heat."""
    def pol(m, ctx):
        f, r = inner(m, ctx)
        frac = m.heat / m.max_heat if m.max_heat else 0.0
        j = min(len(bands) - 1, int(frac / knee * len(bands)))
        cap = m._base_range * bands[j]
        rr = m._base_range if r is None else r
        return f, min(rr, cap)
    return pol


def ammo_park(inner, thresh=60, frac=0.28):
    """RELOAD SHAPING with the only ammo lever that exists. A nearly-dry mount
    (< thresh rounds of a 600 mag) is pulled to the bottom rung: its remaining
    rounds go only to close, highest-certainty threats, and it runs dry as late
    as possible -- ideally into the wave gap, where the 5 s reload is free."""
    def pol(m, ctx):
        f, r = inner(m, ctx)
        if 0 < m.rounds < thresh and m.reloading <= 0:
            return f, m._base_range * frac
        return f, r
    return pol


def combine_fire(*pols):
    """AND the fire bits, last non-None range wins (leftmost = innermost)."""
    def pol(m, ctx):
        fire, rng = True, None
        for p in pols:
            f, r = p(m, ctx)
            fire = fire and f
            if r is not None:
                rng = r
        return fire, rng
    return pol


# ------------------------------------------------------------- scoring aid
def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))
