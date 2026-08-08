"""What can a fleet ACTUALLY launch? Torpedo output per core, and fleet-scale salvos.

Every salvo size used in this study so far (24, 48, 72, 96) was chosen to make the
defensive comparison discriminating, not because a fleet can produce it. This works out
what each SCF core can really put in the air, then feeds those numbers back through the
defence.

Launcher fire cycles are run through the WeaponCore rules verified in ../csdiff
(TicksPerShot = (uint)(3600/RateOfFire), ShotsInBurst, DelayAfterBurst, reload restoring
MagsToLoad x MagazineSize). Torpedo magazines have Capacity = 1, so MagsToLoad IS the
rounds per load.

Read from CoreParts/Torpedolaunchers/*.cs and the SCF weight tables:

  launcher            pts  tubes  rof  reload  mags  burst
  LightSingle           4    1    100   720      1     0 (= full magazine)
  LightDouble           7    2     60   540      2     2
  LightTriple          10    3     90   300      3     3
  MediumSingle          4    1     60   720      1     1
  MediumDouble          7    2     60   540      2     2
  MediumTriple         10    3     30   300      3     1
  ImprovisedDouble      7    2     30   380      2     2

`sdx_torpedoLauncherMediumContinuous` carries a 70-point weight but exists only in
Localization -- there is no CoreParts definition for it -- so it is excluded and flagged.

Cost note that shapes all of this: torpedo ammo is 24x TorpedoGuidanceComputer PER SHOT,
and those are NPC-hunted. PDC ammo is free. Sustained torpedo fire is an economic decision
long before it is a tactical one.
"""
import io
import math
import statistics as st
import sys

TICK = 1.0 / 60.0

LAUNCHERS = {
    # name              pts tubes rof reload mags burst
    'LightSingle':      (4,  1,   100, 720,  1,   0),
    'LightDouble':      (7,  2,    60, 540,  2,   2),
    'LightTriple':      (10, 3,    90, 300,  3,   3),
    'MediumSingle':     (4,  1,    60, 720,  1,   1),
    'MediumDouble':     (7,  2,    60, 540,  2,   2),
    'MediumTriple':     (10, 3,    30, 300,  3,   1),
    'ImprovisedDouble': (7,  2,    30, 380,  2,   2),
}

# SCF torpedo budgets, from shipyard.CLASSES
BUDGET = {'Picket': 14, 'Corvette': 28, 'Frigate': 56, 'Cruiser': 70, 'Carrier': 70}


def cycle(rof, reload_ticks, mags, burst, seconds=300.0):
    """Shots fired in `seconds`, on the verified firing cycle.

    Returns (total_shots, alpha) where alpha is the opening burst before the first
    reload -- the number that actually matters for saturating a point defence.
    """
    tps = int(3600.0 / rof) if rof > 0 else 1        # (uint) truncation, verified
    if tps < 1:
        tps = 1
    ammo = mags                                       # MagazineSize is 1 for torpedoes
    per_burst = mags if burst <= 0 else min(burst, mags)
    total = 0
    alpha = -1
    fired_in_burst = 0
    next_shot = 0
    reload_until = -1
    for t in range(int(seconds * 60)):
        if t < reload_until:
            continue
        if reload_until >= 0 and t >= reload_until:
            reload_until = -1
            ammo = mags
            fired_in_burst = 0
            next_shot = t
        if t < next_shot:
            continue
        if ammo <= 0:
            if alpha < 0:
                alpha = total
            reload_until = t + reload_ticks
            continue
        total += 1
        ammo -= 1
        fired_in_burst += 1
        next_shot = t + tps
        if fired_in_burst >= per_burst or ammo <= 0:
            if alpha < 0:
                alpha = total
            reload_until = t + reload_ticks
    return total, (alpha if alpha > 0 else total)


def best_loadout(points):
    """Maximise tubes within the point budget; break ties on sustained output."""
    names = list(LAUNCHERS)
    best = None
    # budgets are small, so brute force over counts is fine
    def rec(i, left, chosen):
        nonlocal best
        if i == len(names):
            tubes = sum(LAUNCHERS[n][1] * c for n, c in chosen.items())
            rate = sum(RATE[n] * c for n, c in chosen.items())
            alpha = sum(ALPHA[n] * c for n, c in chosen.items())
            key = (tubes, rate)
            if best is None or key > best[0]:
                best = (key, dict(chosen), tubes, rate, alpha, points - left)
            return
        n = names[i]
        pts = LAUNCHERS[n][0]
        for c in range(left // pts + 1):
            if c:
                chosen[n] = c
            rec(i + 1, left - c * pts, chosen)
            if c:
                del chosen[n]
    rec(0, points, {})
    return best


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)

    RATE, ALPHA = {}, {}
    print('=' * 104)
    print('LAUNCHER OUTPUT (verified firing cycle, 300 s)'.center(104))
    print('=' * 104)
    print('  %-18s%5s%7s%9s%10s%12s%14s' % ('launcher', 'pts', 'tubes', 'alpha',
                                            'torp/min', 'pts/tube', 'pts per t/min'))
    print('  ' + '-' * 100)
    for n, (pts, tubes, rof, rel, mags, burst) in LAUNCHERS.items():
        total, alpha = cycle(rof, rel, mags, burst)
        rate = total / 5.0                      # 300 s -> per minute
        RATE[n], ALPHA[n] = rate, alpha
        print('  %-18s%5d%7d%9d%10.1f%12.2f%14.2f'
              % (n, pts, tubes, alpha, rate, pts / tubes, pts / rate if rate else 0))

    print()
    print('=' * 104)
    print('PER-CORE TORPEDO OUTPUT at the SCF torpedo budget'.center(104))
    print('=' * 104)
    print('  %-11s%8s%8s%8s%11s%13s%14s' % ('core', 'budget', 'used', 'tubes',
                                            'alpha', 'torp/min', 'TGC/min'))
    print('  ' + '-' * 100)
    picks = {}
    for cls, pts in BUDGET.items():
        key, chosen, tubes, rate, alpha, used = best_loadout(pts)
        picks[cls] = (chosen, tubes, rate, alpha)
        print('  %-11s%8d%8d%8d%11d%13.1f%14.0f'
              % (cls, pts, used, tubes, alpha, rate, rate * 24))
        print('             %s' % ('  '.join('%dx %s' % (c, n) for n, c in chosen.items())))

    print()
    print('=' * 104)
    print('FLEET ALPHA STRIKE — every tube fired at once, before any reload'.center(104))
    print('=' * 104)
    print('  %-11s' % 'core' + ''.join(('%d ships' % n).rjust(11) for n in (1, 2, 3, 4, 6, 8)))
    print('  ' + '-' * 100)
    for cls in BUDGET:
        _c, _t, _r, alpha = picks[cls]
        print('  %-11s' % cls + ''.join(str(alpha * n).rjust(11) for n in (1, 2, 3, 4, 6, 8)))
    print()
    print('  sustained, torpedoes per minute:')
    print('  %-11s' % 'core' + ''.join(('%d ships' % n).rjust(11) for n in (1, 2, 3, 4, 6, 8)))
    for cls in BUDGET:
        _c, _t, rate, _a = picks[cls]
        print('  %-11s' % cls + ''.join(('%.0f' % (rate * n)).rjust(11) for n in (1, 2, 3, 4, 6, 8)))
