// VERBATIM extraction of WeaponCore's projectile-vs-projectile impact detection.
//
// Sources, copied without algebraic change:
//   ProjectileHits.cs:601-682   guard, bulletRadius, targetRadius, sphere-sphere CCD
//   AmmoConstants.cs:1227-1244  CollisionShape (isLine / size derivation)
//
// Only the surrounding Projectile/AmmoDef object graph is replaced by plain fields,
// because reproducing it would require a live Session. Every arithmetic line and every
// branch is the original. Substitutions are numbered SUB(n) and listed here:
//   SUB(1) p.State == ProjectileState.Detonate      -> bool isDetonate
//   SUB(2) aConst.{CollisionIsLine,CollisionSize,ByBlockHitRadius,EndOfLifeRadius}
//                                                   -> fields on AmmoConst bullet
//   SUB(3) targetAmmo.{CollisionIsLine,CollisionSize} -> fields on AmmoConst target
//   SUB(4) Session.I.DeltaStepConst                 -> double deltaStep
//   SUB(5) p.{LastPosition,Position} / targetProjectile.{LastPosition,Position}
//                                                   -> passed Vector3D values
//   SUB(6) driftCompensationVelocity                -> passed Vector3D value
using System;
using VRageMath;

namespace WcReal
{
    public struct AmmoConst
    {
        public bool CollisionIsLine;
        public double CollisionSize;
        public double ByBlockHitRadius;
        public float EndOfLifeRadius;
    }

    public static class Collide
    {
        // ---------------------------------------- AmmoConstants.cs:1227-1244
        // NOTE the asymmetry that survives into the radii below: a LineShape keeps the
        // raw Diameter, a SphereShape gets it halved here and then halved AGAIN at
        // ProjectileHits.cs:623. Both are reproduced as written.
        public static void CollisionShape(bool shapeIsLine, double diameter,
            out bool collisionIsLine, out double collisionSize)
        {
            var isLine = shapeIsLine;
            var size = diameter;

            if (size <= 0)
            {
                if (!isLine) isLine = true;
                size = 1;
            }
            else if (!isLine) size *= 0.5;
            collisionIsLine = isLine;
            collisionSize = size;
        }

        // ---------------------------------------- ProjectileHits.cs:605-624
        public static double BulletRadius(AmmoConst aConst, bool isDetonate)
        {
            double bulletRadius;

            // LineShape is deprecated, and we use some fallback calculations to reproduce the old behavior:
            if (aConst.CollisionIsLine)
            {
                bulletRadius = isDetonate
                    ? aConst.EndOfLifeRadius
                    : aConst.ByBlockHitRadius > aConst.CollisionSize
                        ? aConst.ByBlockHitRadius
                        : aConst.CollisionSize;
            }
            else
            {
                // CollisionSize is diameter. This is the correct expression:
                bulletRadius = isDetonate
                    ? aConst.EndOfLifeRadius
                    : aConst.ByBlockHitRadius > 0.5 * aConst.CollisionSize
                        ? aConst.ByBlockHitRadius
                        : 0.5 * aConst.CollisionSize;
            }
            return bulletRadius;
        }

        // ---------------------------------------- ProjectileHits.cs:626-641
        // The `aConst.CollisionSize` inside the line branch is the SHOOTER's ammo, not
        // the target's. That is what the source reads; the in-source comment calls it
        // "really fucking random". Preserved deliberately.
        public static double TargetRadius(AmmoConst aConst, AmmoConst targetAmmo,
            Vector3D targetPosition, Vector3D targetLastPosition)
        {
            double targetRadius;

            // The previous implementation completely ignored the actual size of the target and did this nonsense:
            if (targetAmmo.CollisionIsLine)
            {
                // This calculation is really fucking random...
                var sphere = new BoundingSphereD(targetPosition, aConst.CollisionSize);
                sphere.Include(new BoundingSphereD(targetLastPosition, 1));
                targetRadius = sphere.Radius;
            }
            else
            {
                // CollisionSize is diameter:
                targetRadius = 0.5 * targetAmmo.CollisionSize;
            }
            return targetRadius;
        }

        // ---------------------------------------- ProjectileHits.cs:643-682
        public static bool Hits(Vector3D pLastPosition, Vector3D pPosition,
            Vector3D tLastPosition, Vector3D tPosition,
            Vector3D driftCompensationVelocity, double deltaStep,
            double bulletRadius, double targetRadius,
            out double closestApproachDistanceSqr)
        {
            var dp = pLastPosition + driftCompensationVelocity * deltaStep - tLastPosition;
            var dv = (pPosition - pLastPosition - tPosition + tLastPosition) / deltaStep;

            var dvdv = Vector3D.Dot(dv, dv);

            if (Math.Abs(dvdv) < 1e-6)
            {
                // Very weird case where projectiles are speed-matched.
                // We will treat it as the collision tick.
                closestApproachDistanceSqr = Vector3D.Dot(dp, dp);
            }
            else
            {
                var dpdv = Vector3D.Dot(dp, dv);

                // We clamp t to the interval between this tick and the next tick.
                // if t is negative, the collision has already passed and the closest approach is at t=0.
                var timeOfClosestApproach = MathHelperD.Clamp(-dpdv / dvdv, 0.0, deltaStep);
                closestApproachDistanceSqr = Vector3D.Dot(dp, dp) + dvdv * (timeOfClosestApproach * timeOfClosestApproach) + 2.0 * dpdv * timeOfClosestApproach;
            }

            // The two things are interacting if their bounding spheres overlap:
            var interactionThreshold = bulletRadius + targetRadius;

            return closestApproachDistanceSqr < interactionThreshold * interactionThreshold;
        }

        // Exposed so the port can be diffed against VRage's real Include(), rather
        // than against my guess at the merge formula.
        public static double IncludeRadius(Vector3D c0, double r0, Vector3D c1, double r1)
        {
            var s = new BoundingSphereD(c0, r0);
            s.Include(new BoundingSphereD(c1, r1));
            return s.Radius;
        }
    }
}
