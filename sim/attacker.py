"""ATTACKER-side salvo composer: mixed torpedo types, per-torpedo approach axis,
arrival offsets and scatter.

This is fleet_efficiency.wave copied VERBATIM in structure and RNG draw order (the
shared file must not be modified), with exactly one generalisation: instead of one
(torp_kind, launch_delays) pair, each torpedo i is built from a spec

    (kind, back_m, axis, scatter)

    kind     torpedo2.PROFILES key
    back_m   extra start distance in metres (arrival stagger, same mechanism as
             launch_delays * 260 in the shared wave)
    axis     unit V, the DIRECTION OF FLIGHT (shared wave uses V(-1,0,0));
             spawn is lead.pos - axis * (start_range + back) + off
    scatter  half-width of the uniform spawn offset cube (shared wave: 80 m)

RNG parity: per torpedo the draws are 3x rnd.uniform(-scatter, scatter) then
rnd.randrange(10**6), identical to the shared wave, so a spec list equivalent to
the stock arguments reproduces fleet_efficiency.run bit for bit
(parity_check() below asserts this).

Scoring adds per-kind leaker/kill attribution, because the economic metric is
EXPENSIVE leakers per expensive torpedo: guided 160/220 mm ammo costs
24x TorpedoGuidanceComputer each, Torpedo190mmImprovised is free
(AUDIT_ECONOMY.md 2.5/2.6).
"""
import random
import weapons
from vec import V
from ship import Ship, DT
from shipyard import build_ship
from hull2 import GRID
from weapons import PDC_ALIAS
from torpedo2 import Torpedo2
import targeting
from targeting import select
from rounds import fire, HIT, WASTED, EXPIRED
from fleet_efficiency import class_speed_mps

FREE_KINDS = {'Torpedo190mmImprovised'}


def stock_specs(salvo, kind='Plasma220mmTorp', delays=None, axis=None, scatter=80.0):
    """Spec list equivalent to the shared wave's (torp_kind, launch_delays)."""
    ax = axis or V(-1, 0, 0)
    out = []
    for i in range(salvo):
        back = (delays[i % len(delays)] * 260.0) if delays else 0.0
        out.append((kind, back, ax, scatter))
    return out


def wave_atk(fleet, specs, rnd, duration=90.0, detonate_at=150.0,
             start_range=6000.0, engage_all=True, perfect=False,
             launcher_speed=0.0, policy=None, pb_ticks=10):
    """One composed salvo against the fleet. Mirrors fleet_efficiency.wave."""
    lead = fleet[0][0]
    torps = []
    for i, (kind, back, axis, scatter) in enumerate(specs):
        off = V(rnd.uniform(-scatter, scatter), rnd.uniform(-scatter, scatter),
                rnd.uniform(-scatter, scatter))
        torps.append(Torpedo2(kind, lead.pos - axis * (start_range + back) + off,
                              axis * 260.0, lead, seed=rnd.randrange(10 ** 6),
                              index=i, shooter_vel=axis * launcher_speed))
    t = 0.0
    leakers = kills = 0
    leak_by_kind = {}
    kill_by_kind = {}
    engaged_ticks = 0
    ticks = 0
    fired_rounds = wasted_rounds = missed_rounds = 0
    in_flight = []
    for _sh, _hull, _ms in fleet:
        for _m in _ms:
            if not hasattr(_m, '_base_range'):
                _m._base_range = _m.range
            _m._pol_off = False
            _m._want = True
    while t < duration and any(x.alive for x in torps):
        alive = [x for x in torps if x.alive]
        if not alive:
            break
        ticks += 1
        if policy is not None and (ticks - 1) % pb_ticks == 0:
            nearest = min((x.pos - lead.pos).length() for x in alive)
            ctx = {'t': t, 'inbound': len(alive), 'nearest': nearest,
                   'n_ships': len(fleet),
                   'per_hull': max(len(_f[2]) for _f in fleet),
                   'n_mounts': sum(len(_f[2]) for _f in fleet)}
            _infl = {}
            for _r in in_flight:
                _infl[id(_r.mount)] = _infl.get(id(_r.mount), 0) + 1
            for _si, (_sh, _hull, _ms) in enumerate(fleet):
                for _i, _m in enumerate(_ms):
                    _m._idx = _i
                    _m._ship = _si
                    _m._in_flight = _infl.get(id(_m), 0)
                    _w = getattr(_m, '_wc', None)
                    _m._has_tgt = bool(_w is not None and _w.held is not None
                                       and _w.held.alive)
            ctx['tracking'] = [[bool(_m._has_tgt) for _m in _f[2]] for _f in fleet]
            ctx['own_rounds'] = [(_r.mount._ship, _r.mount._idx, _r.pos, _r.vel)
                                 for _r in in_flight]
            _bearings = []
            for _si, (_sh, _hull, _ms) in enumerate(fleet):
                for _i, _m in enumerate(_ms):
                    _d = getattr(_m, 'aim_dir_local', None)
                    if not _m._has_tgt or _d is None:
                        continue
                    _mw = _sh.to_world(V(_m.cell[0], _m.cell[1], _m.cell[2]) * GRID
                                       + _m.normal * (GRID * 1.01))
                    _bearings.append((_si, _i, _mw, _sh.to_world(_d) - _sh.pos))
            ctx['bearings'] = _bearings
            for _si, (_sh, _hull, _ms) in enumerate(fleet):
                for _i, _m in enumerate(_ms):
                    want, rng = policy(_m, ctx)
                    _m._want = want
                    _m.range = _m._base_range if rng is None else rng
        for si, (sh, hull, mounts) in enumerate(fleet):
            if not engage_all and si != 0:
                continue
            for m in mounts:
                best, bd = select(m, alive, sh, hull, perfect=perfect)
                on_t = (m.acquire(best, dir_local=getattr(m, 'aim_dir_local', None))
                        if best is not None else False)
                if not getattr(m, '_want', True):
                    on_t = False
                shots = m.step(DT, on_t)
                if shots > 0:
                    engaged_ticks += 1
                m._acc = getattr(m, '_acc', 0.0) + shots
                while m._acc >= 1.0:
                    m._acc -= 1.0
                    if best is None:
                        break
                    r = fire(m, best, sh, rnd)
                    if r is not None:
                        in_flight.append(r)
                        fired_rounds += 1

        for x in alive:
            if x.step() <= detonate_at:
                x.alive = False
                leakers += 1
                leak_by_kind[x.kind] = leak_by_kind.get(x.kind, 0) + 1

        survivors = []
        for r in in_flight:
            r.advance()
            out = r.resolve()
            if out is None:
                survivors.append(r)
            elif out == HIT:
                tgt = r.target
                tgt.health -= r.hhm
                if tgt.health <= 0:
                    tgt.alive = False
                    kills += 1
                    kill_by_kind[tgt.kind] = kill_by_kind.get(tgt.kind, 0) + 1
            elif out == WASTED:
                wasted_rounds += 1
            else:
                missed_rounds += 1
        in_flight = survivors
        t += DT
    return dict(leakers=leakers, kills=kills,
                leak_by_kind=leak_by_kind, kill_by_kind=kill_by_kind,
                fired_rounds=fired_rounds, wasted=wasted_rounds,
                missed=missed_rounds, ticks=ticks)


def run_atk(specs, n_ships=1, mounts_per=8, kind='PdcMcrn', spacing=500.0, seed=1,
            engage_all=True, cls='Corvette', perfect=False, launcher_speed=0.0,
            policy=None, start_range=6000.0):
    """Mirror of fleet_efficiency.run for one composed wave. Deterministic in args."""
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
        fleet.append((sh, hull, mounts))
    return wave_atk(fleet, specs, rnd, engage_all=engage_all, perfect=perfect,
                    launcher_speed=launcher_speed, policy=policy,
                    start_range=start_range)


def parity_check(seeds=(701, 702, 703), verbose=False):
    """run_atk(stock specs) must reproduce fleet_efficiency.run exactly."""
    from fleet_efficiency import run
    import ladder as L
    ok = True
    for s in seeds:
        pol_a = L.with_infl_index(L.burst_ladder_only(burst=14))
        pol_b = L.with_infl_index(L.burst_ladder_only(burst=14))
        a = run(3, 8, kind='PdcMcrn', salvo=48, waves=1, seed=s, engage_all=True,
                policy=pol_a, launch_delays=[0.0, 1.0] * 24)
        b = run_atk(stock_specs(48, delays=[0.0, 1.0] * 24), n_ships=3, seed=s,
                    policy=pol_b)
        same = (a['leakers'] == b['leakers'] and a['kills'] == b['kills']
                and a['fired_rounds'] == b['fired_rounds'])
        if verbose or not same:
            print(f"  seed {s}: shared leak={a['leakers']} kills={a['kills']} "
                  f"fired={a['fired_rounds']} | atk leak={b['leakers']} "
                  f"kills={b['kills']} fired={b['fired_rounds']} "
                  f"{'OK' if same else 'MISMATCH'}", flush=True)
        ok = ok and same
    return ok


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                                  errors='replace', line_buffering=True)
    print("parity:", parity_check(verbose=True), flush=True)
