// VERBATIM extracts from WeaponCore WeaponTracking.cs. Substitutions are numbered
// SUB(n) inline; every one replaces an external STATE READ with an injected value.
// No arithmetic altered.
using System; using VRage.Game.Entity; using VRageMath; using VRage.Utils;
using MyCubeGrid = VRage.Game.Entity.MyEntity;

namespace WcReal {
  public static class Predict {
    public static bool QuarticSolver(ref double timeToIntercept, Vector3D relativePosition, Vector3D relativeVelocity, Vector3D acceleration, double projectileSpeed, double[] coefficients, double tolerance = 1e-3, int maxIterations = 10)
            {
                var oneOverSpeedSq = projectileSpeed > 0 ? 1.0 / (projectileSpeed * projectileSpeed) : 0;
                coefficients[4] = acceleration.LengthSquared() * 0.25 * oneOverSpeedSq;
                coefficients[3] = Vector3D.Dot(relativeVelocity, acceleration) * oneOverSpeedSq;
                coefficients[2] = (Vector3D.Dot(relativePosition, acceleration) + relativeVelocity.LengthSquared()) * oneOverSpeedSq - 1.0;
                coefficients[1] = 2.0 * Vector3D.Dot(relativePosition, relativeVelocity) * oneOverSpeedSq;
                coefficients[0] = relativePosition.LengthSquared() * oneOverSpeedSq;
    
                for (int ii = 0; ii < maxIterations; ++ii)
                {
                    // Evaluate
                    double value = 0;
                    double xn = 1;
                    for (int n = 0; n <= 4; ++n)
                    {
                        value += coefficients[n] * xn;
                        xn *= timeToIntercept;
                    }
    
                    if (Math.Abs(value) < tolerance)
                        return true;
    
                    // Derivative
                    double deriv = 0;
                    double xn1 = 1;
                    for (int n = 1; n <= 4; ++n)
                    {
                        deriv += n * coefficients[n] * xn1;
                        xn1 *= timeToIntercept;
                    }
    
                    if (MyUtils.IsZero(deriv, 1e-10f)) 
                        break;
    
                    timeToIntercept -= value / deriv;
                }
                return false;
            }

    public static bool CalculateAdvancedGridAimPrediction(double injMaxSpeed, Vector3D injTargetAccel, Vector3D injTargetCom, Vector3D injTargetAngularVel, ref Vector3D targetPos, ref Vector3D targetVel, ref Vector3D weaponPos, ref Vector3D weaponVel, double crudeTti, double muzzleSpeed, bool debug, out KineticState targetPointState, out double t)
            {
                const double dt = 1.0 / 60.0;
                
                double maxSpeed;
                bool applyMaxSpeedAfterStep;
                // SUB(1): no registered velocity-constraint hook in SDX2, so the else
                // branch is what runs. maxSpeed injected instead of read from
                // MyDefinitionManager.EnvironmentDefinition.LargeShipMaxSpeed.
                maxSpeed = injMaxSpeed;
                applyMaxSpeedAfterStep = true;
    
                var maxSpeedSqr = maxSpeed * maxSpeed;
                
                // SUB(2): no accel-estimator hook registered, so this is
                // (Vector3D)targetGrid.Physics.LinearAcceleration, injected.
                var targetDriveAccelWorld = injTargetAccel;
                
                var targetFixedPoint = injTargetCom;   // SUB(3)
                var targetOffsetWorld = targetPos - targetFixedPoint;
                var previousTargetOffsetWorld = targetOffsetWorld;
                
                var w = injTargetAngularVel;           // SUB(4)
                var wNorm = w.Length();
    
                var rotIncr = wNorm < 1e-8
                    ? QuaternionD.Identity 
                    : QuaternionD.CreateFromAxisAngle(w / wNorm, wNorm * dt);
                
                var currentX = new KineticState(targetFixedPoint, targetVel);
                var previousX = new KineticState();
                Func<MyCubeGrid, Vector3D, Vector3D, Vector3D> externalForceFunction = null; // SUB(5): unregistered
    
                // Reasonable bounds for the solution:
                var start = Math.Max((int)(crudeTti * 60 * 0.8), 1);
                var budget = Math.Max((int)(crudeTti * 60 * 1.2), 5);
    
                for (var step = 0; step <= budget; step++) // Budget + 1 steps
                {
                    if (step >= start)
                    {
                        var a = previousX.Translation + previousTargetOffsetWorld;
                        var t0 = step * dt - dt;
                        var d = currentX.Translation + targetOffsetWorld - a;
                        var u = weaponVel - d / dt;
                        var w1 = weaponPos - a + d * t0 / dt;
                        // ReSharper disable InconsistentNaming
                        // Honestly it would be best if we made a linear solver if A ~= 0. Maybe later
                        var A = Vector3D.Dot(u, u) - muzzleSpeed * muzzleSpeed;
                        var B = 2 * Vector3D.Dot(u, w1);
                        var C = Vector3D.Dot(w1, w1);
                        // ReSharper restore InconsistentNaming
                        var delta = B * B - 4.0 * A * C;
    
                        bool hasRoot;
                        if (delta < 0.0)
                        {
                            hasRoot = false;
                        }
                        else
                        {
                            var t1Frame = t0 + dt;
                            var f0 = A * t0 * t0 + B * t0 + C;
                            var f1 = A * t1Frame * t1Frame + B * t1Frame + C;
    
                            // If the sign changed over this interval, the interval contains the root:
                            hasRoot = (f0 <= 0.0 && f1 >= 0.0) || (f0 >= 0.0 && f1 <= 0.0);
    
                            if (!hasRoot)
                            {
                                // If the sign didn't change, it's still possible for the function to have both roots inside this interval.
                                // To check this, we verify the signs of the function at the two ends against the sign of the function at the vertex:
                                var tVertex = -B / (2.0 * A);
                                if (tVertex > t0 && tVertex < t1Frame)
                                {
                                    var fVertex = -delta / (4.0 * A);
                                    hasRoot = (f0 <= 0.0 && fVertex >= 0.0) || (f0 >= 0.0 && fVertex <= 0.0);
                                }
                            }
                        }
    
                        if (hasRoot)
                        {
                            delta = Math.Sqrt(delta);
                            var t1 = (-B - delta) / (2.0 * A);
                            var t2 = (-B + delta) / (2.0 * A);
    
                            t = double.PositiveInfinity;
    
                            if (t1 > t0 && t1 <= t0 + dt)
                            {
                                t = Math.Min(t, t1);
                            }
    
                            if (t2 > t0 && t2 <= t0 + dt)
                            {
                                t = Math.Min(t, t2);
                            }
    
                            if (!double.IsPositiveInfinity(t))
                            {
                                // Target GRID position:
                                //var positionEstimate = a + d * (t - t0) / dt;
    
                                // The actual launch direction:
                                var directionEstimate = -(u * t + w1) / (muzzleSpeed * t);
    
                                targetPointState = new KineticState(
                                    weaponPos + directionEstimate * (muzzleSpeed * t),
                                    (currentX.Translation - previousX.Translation) / dt
                                );
                                
                                //MyAPIGateway.Utilities.ShowMessage("A", $"Found in {start}/{step}/{budget} used {step-start}");
    
                                return true;
                            }
                        }
                    }
    
                                    
                    previousX = currentX;
                    previousTargetOffsetWorld = targetOffsetWorld;
    
                    var vDot = targetDriveAccelWorld;
    
                    if (externalForceFunction != null)
                    {
                        vDot += externalForceFunction.Invoke(
                            null,                       // SUB(5b): dead branch, hook is null
                            currentX.Translation,
                            currentX.LinearVelocity
                        );
                    }
    
                    if (!applyMaxSpeedAfterStep && currentX.LinearVelocity.LengthSquared() > maxSpeedSqr)
                    {
                        currentX.LinearVelocity = currentX.LinearVelocity.Normalized() * maxSpeed;
                    }
                    
                    currentX.LinearVelocity += vDot * dt;
                    currentX.Translation += currentX.LinearVelocity * dt;
    
                    if (applyMaxSpeedAfterStep && currentX.LinearVelocity.LengthSquared() > maxSpeedSqr)
                    {
                        currentX.LinearVelocity = currentX.LinearVelocity.Normalized() * maxSpeed;
                    }
                    
                    targetOffsetWorld = Vector3D.Transform(targetOffsetWorld, rotIncr);
                    targetDriveAccelWorld = Vector3D.Transform(targetDriveAccelWorld, rotIncr);
                }
    
                targetPointState = new KineticState(targetPos, targetVel);
                t = double.PositiveInfinity;
                
                return false;
            }
  }

  public struct TrajectoryPredictionShootingFrame
          {
              public Vector3D TargetPos, TargetVel;
              public Vector3D ShooterPos, ShooterVel;
  
              public Vector3D Dr, Dv;
              public double Distance;
              public Vector3D Los;
  
              public static TrajectoryPredictionShootingFrame Calculate(
                  ref Vector3D targetPos, ref Vector3D targetVel,
                  ref Vector3D shooterPos, ref Vector3D shooterVel)
              {
                  var dr = targetPos - shooterPos;
                  var dv = targetVel - shooterVel;
                  var distance = dr.Length();
                  var los = dr / distance;
  
                  return new TrajectoryPredictionShootingFrame
                  {
                      TargetPos = targetPos, TargetVel = targetVel,
                      ShooterPos = shooterPos, ShooterVel = shooterVel,
                      Dr = dr, Dv = dv,
                      Distance = distance,
                      Los = los
                  };
              }
              
              /// <summary>
              ///     Calculates a crude time-to-intercept using the first-order information.
              /// </summary>
              /// <param name="muzzleSpeed"></param>
              /// <param name="tti"></param>
              /// <returns></returns>
              public bool CalculateCrudeTti(double muzzleSpeed, out double tti)
              {
                  double closingSpeed;
                  Vector3D.Dot(ref Dv, ref Los, out closingSpeed);
                  
                  tti = muzzleSpeed * muzzleSpeed - (Dv - closingSpeed * Los).LengthSquared();
  
                  if (tti <= 0.0)
                  {
                      tti = double.PositiveInfinity;
                      return false;
                  }
  
                  double closingDistance;
                  Vector3D.Dot(ref Dr, ref Los, out closingDistance);
                  tti =  closingDistance / (Math.Sqrt(tti) - closingSpeed);
                  
                  if (tti <= 0.0)
                  {
                      tti = double.PositiveInfinity;
                      return false;                
                  }
  
                  return true;
              }
          }

  public struct KineticState
          {
              public Vector3D Translation;
              public Vector3D LinearVelocity;
  
              public KineticState(Vector3D translation, Vector3D linearVelocity)
              {
                  Translation = translation;
                  LinearVelocity = linearVelocity;
              }
          }
}
