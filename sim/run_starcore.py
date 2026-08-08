"""StarCore AMS_I vs SDX2 PDCs, head to head, on the verified engine.

Both mods define their weapons as WeaponCore CoreParts, so the same bit-exact mechanics
apply to both and this is a direct comparison rather than an analogy.

CROSS-MOD CAVEAT, stated up front: StarCore's AMS is presumably balanced against
StarCore's own missiles, not SDX2 torpedoes. Firing it at a Plasma220 tells you how it
would behave if you bolted it onto an SDX2 hull — which is the question asked — but it is
NOT a judgement about whether either mod is internally balanced.

StarCore AMS_I, read from Starcore_AMS_I.cs / Starcore_Ammo_AMS.cs:
    RateOfFire 1150   HeatPerShot 26   MaxHeat 6000   HeatSinkRate 130
    DeviateShotAngle 0.15   AimingTolerance 20   TopTargets 24   CycleTargets 4
    Threats = { Projectiles, Grids }   IgnoreDumbProjectiles = false
    ammo Bullet_AMS: LineShape Diameter 1, DesiredSpeed 1800, SpeedVariance 0,
                     HealthHitModifier 10, MaxTrajectory 2500, MaxLifeTime 150 ticks
"""
import io
import math
import statistics as st
import sys

import weapons as W
from wc_collide import AmmoConst, bullet_radius, target_radius, TORPEDO_AMMO

SEEDS = list(range(701, 719))

# ---- register StarCore AMS_I as a mount kind -------------------------------------
# Same shape of entry as PDC_STATS, sourced field-for-field from the definition.
W.PDC_STATS['StarcoreAMS'] = W._pdc(
    rof=1150, heat_per_shot=26, max_heat=6000, heat_sink=130,
    dev=0.15, aim_tol=20.0, muzzle=1800.0, hhm=10,
    max_dist=2500.0, min_dist=0.0, speed_var=0.0,
    min_el=-20, max_el=90, prediction=3,
)
# Registering PDC_STATS alone is NOT enough to make a mount buildable. The chain is
# PDC_ALIAS -> CATALOGUE -> PDC_KIND, and PDC_KIND is built at weapons.py IMPORT time,
# so a late alias leaves build_ship placing ZERO mounts while still charging SCF points.
# (Exactly the trap that made PdcImprovised read 48/48 leakers from an empty ship.)
import copy
import components as C
_e = copy.deepcopy(C.CATALOGUE['pdcMcrn'])
_e['subtype'] = 'sc_ams_i'
_e['name'] = 'StarCore AMS I'
C.CATALOGUE['starcoreAms'] = _e
if hasattr(C, 'BY_SUBTYPE'):
    C.BY_SUBTYPE['sc_ams_i'] = _e
W.PDC_ALIAS['StarcoreAMS'] = 'starcoreAms'
W.PDC_KIND['sc_ams_i'] = 'StarcoreAMS'

# The ammo's interaction radius comes from Shape.Diameter, so it must be registered too
# or the round would silently inherit PDC40mm's 0.5 m.
import rounds as R
R.MOUNT_AMMO['StarcoreAMS'] = 'Bullet_AMS'
from wc_collide import PDC_AMMO
PDC_AMMO['Bullet_AMS'] = dict(shape_is_line=True, diameter=1.0, speed=1800.0, var=0.0)
PDC_AMMO['Bullet_AMS_AOE'] = dict(shape_is_line=True, diameter=4.0, speed=1800.0, var=0.0)


def threshold(ammo_name, torp_travel=260.0 / 60.0):
    a = PDC_AMMO[ammo_name]
    ac = AmmoConst(shape_is_line=a['shape_is_line'], diameter=a['diameter'])
    tc = AmmoConst(**TORPEDO_AMMO)
    br = bullet_radius(ac)
    tr = target_radius(ac, tc, (0.0, 0.0, 0.0), (torp_travel, 0.0, 0.0))
    return br + tr, br, tr


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 2 or st.stdev(d) == 0:
        return float('inf') if st.mean(d) else 0.0
    return st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                                  line_buffering=True)

    print('=' * 116)
    print('INTERACTION THRESHOLDS (ProjectileHits.cs:605-641, bit-exact)'.center(116))
    print('=' * 116)
    print('  %-22s%-18s%10s%10s%12s' % ('mount', 'ammo', 'bulletR', 'targetR', 'threshold'))
    for kind, ammo in (('SDX2 PdcMcrn/Unn/Opa', 'PDC40mm'),
                       ('SDX2 PdcOpaAdv', 'PDC50mmFlak'),
                       ('SDX2 PdcMcrnAdv', 'PDC50mmHeavy'),
                       ('StarCore AMS_I', 'Bullet_AMS'),
                       ('StarCore AMS AOE', 'Bullet_AMS_AOE')):
        thr, br, tr = threshold(ammo)
        print('  %-22s%-18s%10.1f%10.3f%11.3f m' % (kind, ammo, br, tr, thr))

    # ---- hits to kill and time of flight, the two things that actually bind
    print()
    print('=' * 116)
    print('KILL ECONOMY vs a Health-4 torpedo'.center(116))
    print('=' * 116)
    print('  %-22s%8s%8s%10s%14s%14s' % ('mount', 'rpm', 'HHM', 'hits/kill',
                                         'muzzle m/s', 'ToF @2000m'))
    for kind in ('PdcUnn', 'PdcMcrn', 'PdcOpa', 'PdcMcrnAdv', 'PdcOpaAdv', 'StarcoreAMS'):
        s = W.PDC_STATS[kind]
        hits = max(1, math.ceil(4.0 / max(1, s['hhm'])))
        print('  %-22s%8d%8d%10d%14.0f%13.2fs'
              % (kind, s['rof'], s['hhm'], hits, s['muzzle'], 2000.0 / s['muzzle']))

    # ---- head to head in the sim
    from fleet_efficiency import run
    import ladder as L
    import reroll as Rr

    print()
    print('=' * 116)
    print('HEAD TO HEAD — 3 hulls, 8 mounts each, salvo 48 Plasma220, 18 seeds'.center(116))
    print('=' * 116)
    print('  %-16s%10s%10s%10s%9s%9s%8s' % ('mount', 'no PB', 'burst14', 'DI k=4',
                                            'fired', 'dead%', 'kills'))
    print('  ' + '-' * 112)
    store = {}
    for kind in ('PdcMcrn', 'PdcUnn', 'StarcoreAMS'):
        row = {}
        for lab, pol in (('nopb', lambda: (lambda m, c: (True, None))),
                         ('bo', lambda: L.with_infl_index(L.burst_ladder_only(burst=14))),
                         ('di', lambda: Rr.descend_inflight(k=1 if W.PDC_STATS[kind]['hhm'] >= 4 else 4))):
            rs = [run(3, 8, kind=kind, salvo=48, waves=1, seed=s, engage_all=True,
                      policy=pol()) for s in SEEDS]
            row[lab] = [r['leakers'] for r in rs]
            row[lab + '_r'] = rs
        store[kind] = row
        rs = row['di_r']
        print('  %-16s%10.2f%10.2f%10.2f%9.0f%9.1f%8.1f'
              % (kind, st.mean(row['nopb']), st.mean(row['bo']), st.mean(row['di']),
                 st.mean([r['fired_rounds'] for r in rs]),
                 st.mean([r['dead_pct'] for r in rs]),
                 st.mean([r['kills'] for r in rs])))
    print()
    base = store['PdcMcrn']['di']
    for kind in ('PdcUnn', 'StarcoreAMS'):
        d = st.mean([x - y for x, y in zip(store[kind]['di'], base)])
        print('  %-16s vs PdcMcrn (best policy each): d=%+6.2f  t=%+6.2f'
              % (kind, d, paired_t(store[kind]['di'], base)))
