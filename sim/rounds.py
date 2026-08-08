"""Real PDC rounds in flight, on the verified WeaponCore collision path.

Replaces `PdcMount.p_kill_per_shot`. That closed form collapsed the entire flight
into a probability applied AT THE INSTANT OF FIRING, which made three things
structurally unobservable:

  1. A round could not be IN FLIGHT, so it could never be wasted on a torpedo that
     something else killed while it was travelling. At 3000 m/s over 2500 m that is
     a 0.83 s / 50-tick exposure per round, and the old model scored it as 0.0%.
  2. Shape.Diameter never entered the calculation. It is the dominant term: see
     wc_collide.threshold_for. PDC50mmHeavy gets a 160 m interaction radius and
     PDC40mm gets 3.417 m — a 47x linear difference the dispersion model could
     not express, because it assumed a ~1.1 m physical torpedo.
  3. The weave had to be modelled analytically instead of just displacing the target.

Collision is `wc_collide`, a bit-exact port of ProjectileHits.cs:601-682 verified
against the compiled mod source (csdiff: 731/731).

THE CONSTRAINT THAT MATTERS: a round can only hit the ONE projectile it was fired
at. ProjectileHits.cs:601 reads `target.TargetObject as Projectile` — one object, no
proximity loop. The only code that iterates `ai.LiveProjectile` is the end-of-life
branch (Projectiles.cs:473), which explicitly skips the assigned target. So rounds
cannot opportunistically hit a neighbouring torpedo, and a dead target means every
round already committed to it is lost.
"""
import math
from vec import V
from ship import DT
from weapons import deviated_dir, cross
from wc_predict import trajectory_estimation
from wc_collide import (AmmoConst, bullet_radius, target_radius, hits,
                        PDC_AMMO, TORPEDO_AMMO)

#: outcome tags
HIT, WASTED, EXPIRED = 'hit', 'wasted', 'expired'

#: PDC_STATS key -> the ammo its Ammos array actually lists.
#: Read from CoreParts/PDC/sdx_weapon_*.cs; pdcMcrn and pdcUnn declare no Ammos of
#: their own and inherit PDC40mm from BasePDCDefinition.cs:184.
MOUNT_AMMO = {
    'PdcUnn': 'PDC40mm',
    'PdcUnnAdv': 'PDC40mm',
    'PdcMcrn': 'PDC40mm',
    'PdcOpa': 'PDC40mm',
    'PdcMcrnAdv': 'PDC50mmHeavy',
    'PdcOpaAdv': 'PDC50mmFlak',
    'PdcPgenAdv': 'PDC50mmLight',
    'PdcImprovised': 'PDC40mmImprovised',
}

_TORP_CONST = AmmoConst(**TORPEDO_AMMO)
_BULLET_CONST = {}


def bullet_const(kind):
    """AmmoConst for a mount kind, cached."""
    c = _BULLET_CONST.get(kind)
    if c is None:
        a = PDC_AMMO[MOUNT_AMMO[kind]]
        c = AmmoConst(shape_is_line=a['shape_is_line'], diameter=a['diameter'])
        _BULLET_CONST[kind] = c
    return c


def _perp_frame(fwd):
    """Two unit vectors perpendicular to `fwd`, for the deviation cone."""
    a = V(0.0, 0.0, 1.0) if abs(fwd.z) < 0.9 else V(1.0, 0.0, 0.0)
    right = cross(fwd, a)
    n = right.length()
    right = V(1.0, 0.0, 0.0) if n < 1e-12 else right / n
    return right, cross(fwd, right).normalized()


class Round:
    """One PDC round. Straight-line, unguided, bound to a single target."""
    __slots__ = ('last_pos', 'pos', 'vel', 'life', 'target', 'mount',
                 'bconst', 'br', 'hhm', 'drift')

    def __init__(self, pos, vel, life_ticks, target, mount, bconst, br, hhm,
                 drift=None):
        self.last_pos = pos
        self.pos = pos
        self.vel = vel
        self.life = life_ticks
        self.target = target
        self.mount = mount
        self.bconst = bconst
        self.br = br
        self.hhm = hhm
        self.drift = drift if drift is not None else V(0.0, 0.0, 0.0)

    def advance(self, dt=DT):
        self.last_pos = self.pos
        self.pos = self.pos + self.vel * dt
        self.life -= 1

    def resolve(self, dt=DT):
        """Test this tick's segment against the assigned target.

        Call AFTER both this round and the torpedoes have advanced, so last_pos and
        pos bracket the same interval on both sides — that is the pairing
        ProjectileHits.cs works with.

        Returns HIT / WASTED / EXPIRED / None.
        """
        t = self.target
        if t is None or not t.alive:
            return WASTED
        tr = target_radius(self.bconst, _TORP_CONST,
                           (t.pos.x, t.pos.y, t.pos.z),
                           (t.last_pos.x, t.last_pos.y, t.last_pos.z))
        hit, _cad = hits((self.last_pos.x, self.last_pos.y, self.last_pos.z),
                         (self.pos.x, self.pos.y, self.pos.z),
                         (t.last_pos.x, t.last_pos.y, t.last_pos.z),
                         (t.pos.x, t.pos.y, t.pos.z),
                         (self.drift.x, self.drift.y, self.drift.z),
                         self.br, tr, dt)
        if hit:
            return HIT
        if self.life <= 0:
            return EXPIRED
        return None


def fire(mount, target, ship, rnd, shooter_vel=None):
    """Build one Round, or None if no firing solution exists.

    The lead is solved from the target's state at THIS instant and never revised,
    which is precisely what a weaving torpedo exploits.
    """
    local = V(mount.cell[0], mount.cell[1], mount.cell[2])
    from hull2 import GRID
    muzzle_pos = ship.to_world(local * GRID + mount.normal * (GRID * 1.01))

    accel = getattr(target, 'measured_accel', None) or V(0.0, 0.0, 0.0)
    aim, tti, _algo = trajectory_estimation(
        target_pos=target.pos, target_vel=target.vel, target_accel=accel,
        target_angular_vel=V(0.0, 0.0, 0.0), target_com=target.pos,
        shooter_pos=muzzle_pos, shooter_vel=shooter_vel or V(0.0, 0.0, 0.0),
        muzzle_speed=mount.muzzle, max_speed=mount.muzzle,
        prediction_level=getattr(mount, 'prediction', 3))
    if aim is None or math.isinf(tti):
        return None

    fwd = aim - muzzle_pos
    n = fwd.length()
    if n < 1e-9:
        return None
    fwd = fwd / n
    right, up = _perp_frame(fwd)
    dir_ = deviated_dir(rnd, mount.dev, fwd, right, up)

    # DesiredSpeed + SpeedVariance, Projectile.cs:257-264
    sv = getattr(mount, 'speed_var', 0.0)
    speed = mount.muzzle + (rnd.random() * 2.0 * sv - sv) if sv else mount.muzzle
    bc = bullet_const(mount.kind)
    life = max(1, int(mount.range / max(1.0, speed) / DT) + 1)
    return Round(muzzle_pos, dir_ * speed, life, target, mount, bc,
                 bullet_radius(bc), mount.hhm)
