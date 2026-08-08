"""THE ORACLE — unconstrained upper bound on point defence.

This CHEATS BY CONSTRUCTION and must never be presented as a deployable policy. It
reads true torpedo positions, velocities and health, and it knows every round in flight
and which target each was fired at. It also bypasses the range gate entirely, handing
each mount a target directly. None of that is available to a Programmable Block:
Target.SetTargetId writes -1 for every projectile target, there is no API returning
enemy positions, and the only real actuators are per-mount max range and on/off.

Its purpose is to bound the problem. Every legal policy sits somewhere between the
no-PB baseline and this. If the oracle is close to the best legal policy, the remaining
loss is physics and further control work is wasted. If it is far below, the API
constraints are what is costing us and it is worth engineering hard around them.

WHAT IT STILL CANNOT DO — these are physical, not informational, so the oracle respects
them and the bound stays honest:
  * a mount cannot fire through its own hull, or outside its arc, or beyond its range
    (targeting.valid enforces all three)
  * rounds still fly with real time-of-flight, real dispersion, real speed variance
  * a round can still only hit the ONE target it was fired at (ProjectileHits.cs:601)
  * turret slew is still rate-limited (PdcMount.acquire)
So even the oracle suffers dead-round waste when a target dies mid-flight; it simply
never CHOOSES to over-commit.

THE ALGORITHM — three classical pieces, which the WTA analysis identified as the parts
of this problem that actually cash out:
  1. EDD / least-laxity ordering: service targets by time-to-impact. With near-uniform
     torpedo speeds this is also range order, which is why `window_nearest` worked.
  2. Commitment accounting (shoot-look-shoot): subtract the expected damage of rounds
     ALREADY IN FLIGHT before assigning more. This is the piece no legal policy can do,
     because it needs per-target attribution of your own rounds.
  3. Moore-Hodgson drop-the-tail: a torpedo that cannot be killed before it arrives gets
     nothing. Rounds spent on it are pure loss, and under saturation dropping the
     unsaveable tail is provably optimal for count-of-late-jobs.
"""
import math
import targeting

#: live-target hit probability, measured from the incumbent's per-kill miss count.
#: NOT the 0.19 overall figure -- that folds dead-round waste into p and double-counts
#: exactly what commitment accounting removes.
P_LIVE = 0.41


def _time_to_impact(tgt, ship, detonate_at=150.0):
    d = (tgt.pos - ship.pos).length() - detonate_at
    v = tgt.vel.length()
    return d / v if v > 1e-6 else float('inf')


def oracle_assign(p_hit=P_LIVE, recompute_every=3, use_commitment=True,
                  drop_hopeless=True, overkill_factor=1.0):
    """Return an assignment callback for fleet_efficiency.wave(assign=...).

    `use_commitment` and `drop_hopeless` exist so the oracle's powers can be ABLATED
    separately -- that tells us which piece of perfect knowledge is worth most, and
    therefore what a real PB should spend effort approximating.
    """
    state = {'tick': -1, 'map': {}}

    def assign(fleet, torps, in_flight, t):
        state['tick'] += 1
        if state['tick'] % recompute_every and state['map']:
            # reuse, but drop entries whose target has died
            return {k: v for k, v in state['map'].items() if v is not None and v.alive}

        lead = fleet[0][0]

        # --- rounds already committed, per target (impossible for a real PB) ---
        committed = {}
        if use_commitment:
            for r in in_flight:
                tg = r.target
                if tg is not None and tg.alive:
                    committed[id(tg)] = committed.get(id(tg), 0.0) + p_hit * r.hhm

        # --- candidate mounts, with the physical constraints still enforced ---
        free = []
        for si, (sh, hull, mounts) in enumerate(fleet):
            for m in mounts:
                if m.alive and m.rounds > 0 and not m.overheated:
                    free.append((m, sh, hull))

        # --- EDD: earliest deadline first ---
        order = sorted(torps, key=lambda x: _time_to_impact(x, lead))

        out = {}
        taken = set()
        for tgt in order:
            if not tgt.alive:
                continue
            deficit = tgt.health - committed.get(id(tgt), 0.0)
            if deficit <= 0:
                continue                      # already lethally committed
            tti = _time_to_impact(tgt, lead)

            # mounts that can physically engage it, cheapest (shortest flight) first
            cands = []
            for m, sh, hull in free:
                if id(m) in taken:
                    continue
                ok, dist = targeting.valid(m, tgt, sh, hull)
                if not ok:
                    continue
                tof = dist / max(1.0, m.muzzle)
                if drop_hopeless and tof >= tti:
                    continue                  # round cannot arrive before impact
                cands.append((tof, dist, m))
            if not cands:
                continue
            cands.sort(key=lambda c: c[0])

            # Moore-Hodgson: if even the whole battery cannot kill it in time, spend
            # nothing on it and let it through -- those rounds save a later target.
            if drop_hopeless:
                best_tof = cands[0][0]
                usable = max(0.0, tti - best_tof)
                reachable = sum(m.rof / 60.0 * usable * p_hit * m.hhm
                                for _tof, _d, m in cands)
                if reachable < deficit:
                    continue

            need = deficit * overkill_factor
            for tof, dist, m in cands:
                if need <= 0:
                    break
                out[id(m)] = tgt
                taken.add(id(m))
                # expected damage this mount lands before impact
                need -= (m.rof / 60.0) * max(0.0, tti - tof) * p_hit * m.hhm

        state['map'] = out
        return out

    return assign


def greedy_nearest_assign(recompute_every=3):
    """Control: perfect assignment power, NO deadline reasoning and NO commitment
    accounting -- just put every mount on the closest target it can engage.

    Isolates how much of the oracle's advantage is 'direct assignment' versus
    'knowing what is already committed and what is worth saving'.
    """
    state = {'tick': -1, 'map': {}}

    def assign(fleet, torps, in_flight, t):
        state['tick'] += 1
        if state['tick'] % recompute_every and state['map']:
            return {k: v for k, v in state['map'].items() if v is not None and v.alive}
        out = {}
        for si, (sh, hull, mounts) in enumerate(fleet):
            for m in mounts:
                if not m.alive:
                    continue
                best, bd = None, 1e18
                for tgt in torps:
                    if not tgt.alive:
                        continue
                    ok, dist = targeting.valid(m, tgt, sh, hull)
                    if ok and dist < bd:
                        best, bd = tgt, dist
                if best is not None:
                    out[id(m)] = best
        state['map'] = out
        return out

    return assign
