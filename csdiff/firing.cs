// VERBATIM extraction of WeaponCore's firing model: heat, rate-of-fire degradation,
// the overheat state machine, the shot cadence, and magazine reload.
//
// Sources, copied without algebraic change:
//   EntityComp/Parts/Weapon/WeaponController.cs:260-363  UpdateWeaponHeat
//   EntityComp/Parts/Weapon/WeaponController.cs:365-380  UpdateRof
//   EntityComp/Parts/Weapon/WeaponShoot.cs:17-375        Shoot (cadence/ammo/heat core)
//   EntityComp/Parts/Weapon/WeaponShoot.cs:377-435       FinishMode, GiveUpTarget, OverHeat
//   EntityComp/Parts/Weapon/WeaponShoot.cs:437-460       SetPreFire / UnSetPreFire
//   EntityComp/Parts/Weapon/WeaponState.cs:119-164       StartShooting / StopShooting / ResetShotState
//   EntityComp/Parts/Weapon/WeaponReload.cs:125-158      HasAmmo
//   EntityComp/Parts/Weapon/WeaponReload.cs:210-343      ComputeServerStorage / ServerReload / StartReload
//   EntityComp/Parts/Weapon/WeaponReload.cs:345-448      Reloaded / CancelReload
//   EntityComp/Parts/Weapon/WeaponFields.cs:327          HsRate = system.WConst.HeatSinkRate / 3
//   Session/SessionFutureEvents.cs:27-99                 FutureEvents (Schedule + Tick, VERBATIM —
//                                                        its _offset-after-callbacks quirk makes the
//                                                        self-rescheduling heat loop run every 19 ticks)
//   Session/SessionUpdate.cs:615-633,656,786-815,962-978 per-tick reload check, shoot gate,
//                                                        quickSkip (reproduced in RunTick)
//   Session/SessionSupport.cs:36,54-56                   Tick++ / RelativeTime advance
//   Session/SessionRun.cs:76,142,183,198                 frame order: Timings -> FutureEvents.Tick
//                                                        -> AiLoop -> ShootWeapons
//
// The Weapon/Comp/System/Session object graph is replaced by plain data holders that keep the
// ORIGINAL member paths (Comp.Cube.IsWorking, System.WConst.RateOfFire, PartState.Heat, ...) so
// nearly every extracted line is character-identical to the source. Every substitution:
//   SUB(1)  Session -> stub with Tick/RelativeTime/flags. Run as single-player listen server:
//           IsServer=true, IsClient=false, MpActive=false, DedicatedServer=false, IsCreative=false.
//           FutureEvents itself is NOT stubbed - it is the verbatim class (DeSchedule/Purge, which
//           nothing here calls, dropped; Log.Line in Purge was the only external dependency).
//   SUB(2)  Comp -> holder: Cube.{Closed,IsWorking}, CurrentHeat, HeatLoss, MaxHeat, HasInventory,
//           IsWorking, TypeSpecific, Data.Repo.Values.Set.{RofModifier,Overload},
//           CoreInventory -> a mag counter (see SUB 9).
//   SUB(3)  System (WeaponSystem) -> holder of definition constants, incl. WConst. Values read:
//           ProhibitCoolingWhenOff, HeatSinkRateOverheatMult, MaxHeat, DegRof, HeatThresholdStart,
//           HeatThresholdEnd, WepCoolDown, RofAt0Heat, RofAt100Heat, BarrelSpinRate,
//           HasBarrelRotation, DelayToFire, AlwaysFireFull, DesignatorWeapon, GoHomeToReload,
//           DropTargetUntilLoaded, MaxReloads, HasAmmoSelection, ShotsPerBurst, HasEjector,
//           DelayCeaseFire, WConst.{RateOfFire,ReloadTime,DelayAfterBurst,DisableOverheat,
//           HeatSinkRate,GiveUpAfter}, Values.HardPoint.Loading.{BarrelsPerShot,TrajectilesPerBarrel,
//           SkipBarrels,DelayAfterBurst,GiveUpAfter,ShotsInBurst}.
//   SUB(4)  PartState / ProtoWeaponAmmo / Reload -> holders with the same field names and TYPES
//           (Heat float, CurrentAmmo int, StartId/EndId ushort, MagsLoaded/CurrentMags int).
//   SUB(5)  ActiveAmmoDef.AmmoDef(.Const) -> holder: Reloadable, EnergyAmmo, MustCharge, IsHybrid,
//           BurstMode, HasShotReloadDelay, MagazineSize, MagsToLoad, WeaponPatternCount,
//           HeatNeededToFire, AllowNegativeHeatModifier. BurstMode/HasShotReloadDelay are computed
//           by the VERBATIM AmmoConstants.cs:531/540 (Energy()) expressions in the constructor.
//   SUB(6)  AV: emissives, sounds, animations, EventTriggerStateChanged -> no-op stubs. The
//           HeatEmissives indexing arithmetic in UpdateWeaponHeat is preserved (Color[101] dummy).
//   SUB(7)  Network sends (SendState, SendWeaponReload, ammo syncs) -> no-op stubs; all such
//           call sites are also dead because MpActive=false.
//   SUB(8)  Projectile creation (WeaponShoot.cs:152-303: muzzle dummies, deviation RNG, ammo
//           patterns, NewProjectile queue) -> counters. RoundsFired += 1 per barrel iteration that
//           reaches the generation region; ProjectilesEmitted += TrajectilesPerBarrel *
//           patternIndex with WeaponPattern=false so patternIndex == WeaponPatternCount (== 1 for
//           every SDX2 PDC round). No RNG state feeds back into cadence/heat/reload, so dropping
//           the draws cannot change the extracted behaviour. Back-kick, ejection and the
//           DecayPerShot self-damage block (:343-358) are likewise dropped (DecayPerShot=0).
//   SUB(9)  MyInventory -> an integer magazine count `Comp.CoreInventory.MagsInInventory`.
//           GetItemAmount().ToIntSafe() returns it, ItemsCanBeRemoved(n) is `>= n`, RemoveItems
//           subtracts. The conveyor-pull block in ComputeServerStorage (WeaponReload.cs:221-241,
//           volume math + s.PartToPullConsumable) is reduced to its one state-relevant line, the
//           Reload.CurrentMags refresh - the harness models a pre-stocked inventory instead of
//           the pull system. This is the extraction boundary for inventory.
//   SUB(10) Target / ShootManager side effects: GiveUpTarget's Target.Reset, EndShootMode,
//           UpdateShootSync, ScheduleWeaponHome -> no-ops. EndShootMode only clears manual-shoot
//           bookkeeping (WeaponTypes.cs:562-595) and Trigger (already Off on the AiShoot path
//           modelled here), so it cannot gate the AI auto-fire this harness drives.
//   SUB(11) Barrel rotation: HasBarrelRotation=false, so SpinBarrel/UpdateBarrelRotation are
//           never entered (stubs kept so the verbatim guards compile). UpdatePivotPos dropped.
//   SUB(12) RunTick reproduces the per-frame ordering and the SERVER shoot gate with the AiShoot
//           auto-fire path collapsed to an injected wantFire: autoShot <- (w.AiShooting &&
//           Trigger==Off), sequenceReady/ai.CanShoot/target terms <- true, delayedFire
//           (DelayCeaseFire aim-wander) <- false. The reloadingGuard/overHeat/needsHeat/quickSkip
//           lines are verbatim from SessionUpdate.cs:792-798,969. Aim/track gating is OUT OF
//           SCOPE - wantFire asserts the weapon is on target.
//   SUB(13) Charging/energy weapons: MustCharge=false for every PDC, so ChargeReload and the
//           charge branches of Reloaded are unreachable (kept verbatim where cheap, else noted
//           inline). Phantom/Rifle/creative special cases kept but dead (TypeSpecific=Block).
//
// BOUNDARY (cannot be extracted without a live Session, documented per the harness rules):
//   * the conveyor/inventory pull system (SUB 9) - reload correctness vs the BLOCK inventory is
//     covered; hangar-to-block ammo logistics is not.
//   * aim/tracking/turret slew and target acquisition (SUB 12) - wantFire is injected.
//   * client/MP reload handshakes (ClientReload, WaitForClient paths) - single-player server only.
//   * SessionUpdate.cs:483-485 (reload timer freeze while the block is OFF) is noted but not
//     driven: RunTick asserts Comp.IsWorking for firing scenarios; the cooling-gate scenarios
//     never reload.
using System;
using System.Collections.Generic;
using VRage.Utils;
using VRageMath;

namespace WcReal
{
    // ------------------------------------------------------------------ SUB(1) Session stub
    public class Session
    {
        public static Session I;
        internal const double StepConst = 1.0 / 60.0;        // SessionFields.cs:42 = PHYSICS_STEP_SIZE_IN_SECONDS

        public uint Tick;
        public double RelativeTime;
        public bool DedicatedServer;                          // false: exercise the client emissive branch too
        public bool IsServer = true;
        public bool IsClient;
        public bool MpActive;
        public bool IsCreative;
        public FutureEvents FutureEvents = new FutureEvents();
        public Color[] HeatEmissives = new Color[101];        // SUB(6): dummy palette, indexing preserved

        public void SendState(object o) { }                   // SUB(7)
        public void SendWeaponHeatSyncLoop(object o) { }      // SUB(7)
        public void SendWeaponReload(object o, bool b = false) { } // SUB(7)
        public void SendWeaponAmmoData(object o, bool isSyncStep = false) { } // SUB(7)
    }

    // --------------------------------------------- SessionFutureEvents.cs:27-99, VERBATIM
    // (DeSchedule/Purge dropped; unused here.) NOTE the load-bearing quirk: Tick() runs the
    // due callbacks BEFORE writing `_offset = tick`, so a callback that reschedules itself
    // with delay 20 lands 19 ticks after the tick it ran on. UpdateWeaponHeat is exactly such
    // a callback: the heat loop is 20 ticks after a shot, then every 19 ticks.
    public class FutureEvents
    {
        internal struct FutureAction
        {
            internal Action<object> Callback;
            internal object Arg1;

            internal FutureAction(Action<object> callBack, object arg1)
            {
                Callback = callBack;
                Arg1 = arg1;
            }
        }

        internal FutureEvents()
        {
            for (int i = 0; i <= _maxDelay; i++) _callbacks[i] = new List<FutureAction>();
        }

        private volatile bool Active = true;
        private const int _maxDelay = 14400;
        private List<FutureAction>[] _callbacks = new List<FutureAction>[_maxDelay + 1]; // and fill with list instances
        private uint _offset;
        private uint _lastTick;
        internal void Schedule(Action<object> callback, object arg1, uint delay)
        {
            lock (_callbacks)
            {
                delay = delay <= 0 ? 1 : delay;
                _callbacks[(_offset + delay) % _maxDelay].Add(new FutureAction(callback, arg1));
            }
        }

        internal void Tick(uint tick, bool purge = false)
        {
            if (_callbacks.Length > 0 && Active)
            {
                lock (_callbacks)
                {
                    if (_lastTick == tick - 1 || purge)
                    {
                        var index = tick % _maxDelay;
                        for (int i = 0; i < _callbacks[index].Count; i++)
                            _callbacks[index][i].Callback(_callbacks[index][i].Arg1);

                        _callbacks[index].Clear();
                        _offset = tick;
                    }
                    else
                    {
                        var replayLen = tick - _lastTick;
                        var idx = replayLen;
                        for (int i = 0; i < tick - _lastTick; i++)
                        {
                            var pastIdx = (tick - --idx) % _maxDelay;
                            for (int j = 0; j < _callbacks[pastIdx].Count; j++)
                                _callbacks[pastIdx][j].Callback(_callbacks[pastIdx][j].Arg1);

                            _callbacks[pastIdx].Clear();
                            _offset = tick;
                        }
                    }

                    _lastTick = tick;
                }
            }
        }
    }

    // ------------------------------------------------------------------ SUB(2-5) data holders
    public class CubeStub { public bool Closed; public bool IsWorking = true; }
    public class FixedPointStub { public int V; public int ToIntSafe() { return V; } }
    // SUB(9): MyInventory replaced by a mag counter.
    public class InventoryStub
    {
        public int MagsInInventory;
        public object FindItem(object id) { return AmmoItemStub; }
        public static readonly ItemStub AmmoItemStub = new ItemStub();
        public FixedPointStub GetItemAmount(object id) { return new FixedPointStub { V = MagsInInventory }; }
        public bool ItemsCanBeRemoved(int amount, object item) { return MagsInInventory >= amount; }
        public void RemoveItems(uint itemId, int amount) { MagsInInventory -= amount; }
        public int ItemCount { get { return MagsInInventory > 0 ? 1 : 0; } }
        public bool ContainItems(int amount, object content) { return MagsInInventory >= amount; }
        public void Remove(object item, int amount) { MagsInInventory -= amount; }
    }
    public class ItemStub { public uint ItemId; public object Content; }
    public enum CompTypeSpecific { VanillaTurret, Phantom, Rifle }
    public class SetStub { public float RofModifier = 1f; public int Overload = 1; }
    public class ValuesStub { public SetStub Set = new SetStub(); }
    public class RepoStub { public ValuesStub Values = new ValuesStub(); }
    public class DataStub { public RepoStub Repo = new RepoStub(); }
    public class CompStub
    {
        public CubeStub Cube = new CubeStub();
        public float CurrentHeat;
        public double HeatLoss;
        public int MaxHeat;
        public bool HasInventory = true;
        public bool IsWorking = true;
        public CompTypeSpecific TypeSpecific = CompTypeSpecific.VanillaTurret;
        public DataStub Data = new DataStub();
        public InventoryStub CoreInventory = new InventoryStub();
        public ShootManagerStub ShootManager = new ShootManagerStub();
        public float CurrentInventoryVolume;
    }
    public class ShootManagerStub
    {
        public enum EndReason { Overheat, Reload }
        public uint LastShootTick;
        public uint LastCycle = uint.MaxValue;
        public void EndShootMode(EndReason reason, bool skipNetwork = false) { } // SUB(10)
        public void UpdateShootSync(object w) { }                                // SUB(10)
    }
    public class WConstStub
    {
        public int RateOfFire;
        public int ReloadTime;          // CoreSystems.cs:850, clamped >= 0
        public int DelayAfterBurst;
        public bool DisableOverheat;
        public float HeatSinkRate;
        public bool GiveUpAfter;
    }
    public class LoadingStub
    {
        public int BarrelsPerShot = 1;
        public int TrajectilesPerBarrel = 1;
        public int SkipBarrels;
        public int DelayAfterBurst;
        public bool GiveUpAfter;
        public int ShotsInBurst;
    }
    public class HardPointStub { public LoadingStub Loading = new LoadingStub(); }
    public class ValuesDefStub { public HardPointStub HardPoint = new HardPointStub(); }
    public class SystemStub
    {
        public WConstStub WConst = new WConstStub();
        public ValuesDefStub Values = new ValuesDefStub();
        public bool ProhibitCoolingWhenOff;
        public float HeatSinkRateOverheatMult;
        public int MaxHeat;
        public bool DegRof;
        // CoreSystems.cs:526-543 defaults: 0.8 / 0.4 / 1.0 / 0.25; WepCoolDown clamped to [0,.95]
        public float HeatThresholdStart = 0.8f;
        public float HeatThresholdEnd = 0.4f;
        public float RofAt0Heat = 1f;
        public float RofAt100Heat = 0.25f;
        public float WepCoolDown;
        public int BarrelSpinRate;
        public bool HasBarrelRotation;
        public uint DelayToFire;
        public bool AlwaysFireFull;
        public bool DesignatorWeapon;
        public bool GoHomeToReload;
        public bool DropTargetUntilLoaded;
        public int MaxReloads;
        public bool HasAmmoSelection;
        public int ShotsPerBurst;       // CoreSystems.cs:386 BarrelValues <- Loading.ShotsInBurst
        public bool HasEjector;
        public bool DelayCeaseFire;
    }
    public class AmmoConstStub
    {
        public bool Reloadable = true;
        public bool EnergyAmmo;
        public bool MustCharge;
        public bool IsHybrid;
        public bool BurstMode;
        public bool HasShotReloadDelay;
        public int MagazineSize;
        public int MagsToLoad;          // AmmoConstants.cs:546: def > 0 ? def : 1
        public int WeaponPatternCount = 1;
        public bool WeaponPattern;
        public bool HasEjectEffect;
        public bool SlowFireFixedWeapon;
    }
    public class AmmoDefStub
    {
        public AmmoConstStub Const = new AmmoConstStub();
        public float HeatNeededToFire;
        public bool AllowNegativeHeatModifier;
    }
    public class ActiveAmmoDefStub { public AmmoDefStub AmmoDef = new AmmoDefStub(); public object AmmoDefinitionId; }
    public class PartStateStub { public float Heat; public bool Overheated; }
    public class ProtoWeaponAmmoStub { public int CurrentAmmo; public float CurrentCharge; }
    public class ReloadStub
    {
        public ushort StartId;
        public ushort EndId;
        public int MagsLoaded = 1;
        public bool WaitForClient;
        public int AmmoTypeId;
        public int CurrentMags;
        public int LifetimeLoads;
    }
    public class TargetStub { public bool HasTarget; }
    public class WeaponRandomStub { public XorShiftRandomStruct TurretRandom; public int CurrentSeed; }
    public class TargetDataStub { public WeaponRandomStub WeaponRandom = new WeaponRandomStub(); }
    public class HeatingPartStub { public void SetEmissiveParts(string s, Color c, float f) { } } // SUB(6)
    public enum EventTriggers { Homing, Overheated, Reloading, Firing, StopFiring, PreFire, BurstReload, NoMagsToLoad }
    public enum ReloadedState { Default = 0, Callback = 1, EarlyExit = 2, Hybrid = 3, ChargedOnly = 4, Other5 = 5, Other6 = 6 }

    public class FiringWeapon
    {
        // -------- holders standing in for the live object graph (see SUB table)
        public SystemStub System = new SystemStub();
        public CompStub Comp = new CompStub();
        public PartStateStub PartState = new PartStateStub();
        public ProtoWeaponAmmoStub ProtoWeaponAmmo = new ProtoWeaponAmmoStub();
        public ReloadStub Reload = new ReloadStub();
        public ActiveAmmoDefStub ActiveAmmoDef = new ActiveAmmoDefStub();
        public TargetStub Target = new TargetStub();
        public TargetDataStub TargetData = new TargetDataStub();
        public List<HeatingPartStub> HeatingParts = new List<HeatingPartStub>();

        // -------- WeaponFields.cs state, same names/types
        public float HsRate;                       // WeaponFields.cs:159
        public float HeatPShot;                    // WeaponController.cs:412 (HeatPerShot * ammo HeatModifier)
        public float LastHeat;
        public uint LastHeatUpdateTick;
        public uint ServerHeatSyncTimer;
        public float HeatPerc;
        public bool CurrentlyDegrading;
        public bool HeatLoopRunning;
        public uint OverHeatCountDown;
        public int RateOfFire;
        public int BarrelSpinRate;
        public uint TicksPerShot;
        public double ShootTime;
        public uint LastShootTick;
        public uint LastLoadedTick;
        public uint LastMagSeenTick;
        public uint LastInventoryTick;
        public int ShotsFired;
        public long FireCounter;
        public bool PreFired;
        public bool IsShooting;
        public bool FinishShots;
        public bool Loading;
        public bool NoMagsToLoad;
        public bool CheckInventorySystem = true;
        public bool ClientReloadWaitingForServer;
        public bool ClientReloading;
        public bool ServerQueuedAmmo;
        public uint ReloadEndTick = uint.MaxValue;
        public int ClientMakeUpShots;
        public ushort ClientStartId;
        public ushort ClientEndId;
        public ushort ClientLastShotId;
        public int DelayedCycleId = -1;
        public int ProposedAmmoId = -1;
        public bool ScheduleAmmoChange;
        public int NextMuzzle;
        public int ProjectileCounter;
        public bool PauseShoot;
        public bool ReturingHome;
        public bool IsHome = true;
        public float CurrentAmmoVolume;
        public float EstimatedCharge;
        public float MaxCharge;
        public uint CeaseFireDelayTick = uint.MaxValue / 2;
        private uint _ticksUntilShoot;
        private int _nextVirtual;
        private int _numOfMuzzles = 1;
        private readonly List<int> _muzzlesToFire = new List<int>();
        private readonly int[] MuzzleIdToName = new int[64];

        // -------- harness counters (SUB 8) + heat-pass probe
        public long RoundsFired;
        public long ProjectilesEmitted;
        public int HeatPasses;
        public uint LastHeatPassTick;
        public int HeatPassGapMin = int.MaxValue, HeatPassGapMax;

        public FiringWeapon()
        {
            // WeaponFields.cs:327
            HsRate = System.WConst.HeatSinkRate / 3;
        }

        public void InitFromSystem()
        {
            HsRate = System.WConst.HeatSinkRate / 3;                       // WeaponFields.cs:327
            // AmmoConstants.cs:531 (Energy): burstMode; :540: shotReload — VERBATIM expressions
            ActiveAmmoDef.AmmoDef.Const.BurstMode = System.Values.HardPoint.Loading.ShotsInBurst > 0 && (ActiveAmmoDef.AmmoDef.Const.EnergyAmmo || ActiveAmmoDef.AmmoDef.Const.MagazineSize >= System.Values.HardPoint.Loading.ShotsInBurst);
            ActiveAmmoDef.AmmoDef.Const.HasShotReloadDelay = !ActiveAmmoDef.AmmoDef.Const.BurstMode && System.Values.HardPoint.Loading.ShotsInBurst > 0 && System.Values.HardPoint.Loading.DelayAfterBurst > 0;
            System.ShotsPerBurst = System.Values.HardPoint.Loading.ShotsInBurst; // CoreSystems.cs:386
            // CoreSystems.cs:521-522
            if (System.WepCoolDown < 0) System.WepCoolDown = 0;
            if (System.WepCoolDown > .95f) System.WepCoolDown = .95f;
            UpdateRof();
        }

        // ==================================================== WeaponController.cs:260-363
        internal void UpdateWeaponHeat(object o = null)
        {
            if (Comp.Cube.Closed)
            {
                return;
            }


            if (!System.ProhibitCoolingWhenOff || System.ProhibitCoolingWhenOff && Comp.Cube.IsWorking)
            {
                var hsRateMod = HsRate * (PartState.Overheated && System.HeatSinkRateOverheatMult != 0 ? System.HeatSinkRateOverheatMult : 1f) + (float)Comp.HeatLoss;
                Comp.CurrentHeat = Comp.CurrentHeat >= hsRateMod ? Comp.CurrentHeat - hsRateMod : 0;
                PartState.Heat = PartState.Heat >= hsRateMod ? PartState.Heat - hsRateMod : 0;
                Comp.HeatLoss = 0;
            }

            var set = PartState.Heat - LastHeat > 0.001 || PartState.Heat - LastHeat < 0.001;

            LastHeatUpdateTick = Session.I.Tick;

            if (!Session.I.DedicatedServer)
            {
                var heatOffset = HeatPerc = PartState.Heat / System.MaxHeat;

                if (set && heatOffset > .33)
                {
                    if (heatOffset > 1) heatOffset = 1;

                    heatOffset -= .33f;

                    var intensity = .7f * heatOffset;

                    var color = Session.I.HeatEmissives[(int)(heatOffset * 100)];

                    for (var i = 0; i < HeatingParts.Count; i++)
                    {
                        HeatingParts[i]?.SetEmissiveParts("Heating", color, intensity);
                    }
                }
                else if (set)
                {
                    for (var i = 0; i < HeatingParts.Count; i++)
                    {
                        HeatingParts[i]?.SetEmissiveParts("Heating", Color.Transparent, 0);
                    }
                }

                LastHeat = PartState.Heat;
            }

            if (set && System.DegRof && PartState.Heat >= (System.MaxHeat * System.HeatThresholdStart))
            {
                CurrentlyDegrading = true;
                UpdateRof();
            }
            else if (set && CurrentlyDegrading)
            {
                if (PartState.Heat <= System.MaxHeat * System.HeatThresholdEnd)
                {
                    CurrentlyDegrading = false;
                }

                UpdateRof();
            }

            // If we send the full state, we also reset the timer so we don't send a heat update.
            if (PartState.Overheated && PartState.Heat <= System.MaxHeat * System.WepCoolDown)
            {
                EventTriggerStateChanged(EventTriggers.Overheated, false);
                if (Session.I.IsServer)
                {
                    PartState.Overheated = false;
                    OverHeatCountDown = 0;

                    if (Session.I.MpActive)
                    {
                        Session.I.SendState(Comp);

                        ServerHeatSyncTimer = 0;
                    }
                }
            }

            if (PartState.Heat > 0)
            {
                Session.I.FutureEvents.Schedule(UpdateWeaponHeat, null, 20);
            }
            else
            {
                HeatLoopRunning = false;
                LastHeatUpdateTick = 0;
            }

            // This will not send an update when the code above sends the full state.
            if (Session.I.IsServer && Session.I.MpActive && (!PartState.Overheated || OverHeatCountDown == 0))
            {
                if (++ServerHeatSyncTimer == 6)
                {
                    Session.I.SendWeaponHeatSyncLoop(this);

                    ServerHeatSyncTimer = 0;
                }
            }

            // harness probe (not WC code): record the real pass cadence
            HeatPasses++;
            if (LastHeatPassTick > 0)
            {
                var gap = (int)(Session.I.Tick - LastHeatPassTick);
                if (gap < HeatPassGapMin) HeatPassGapMin = gap;
                if (gap > HeatPassGapMax) HeatPassGapMax = gap;
            }
            LastHeatPassTick = Session.I.Tick;
        }

        // ==================================================== WeaponController.cs:365-380
        internal void UpdateRof()
        {
            var systemRate = System.WConst.RateOfFire * Comp.Data.Repo.Values.Set.RofModifier;
            var barrelRate = System.BarrelSpinRate * Comp.Data.Repo.Values.Set.RofModifier;
            var heatModifier = MathHelper.Lerp(System.RofAt0Heat, System.RofAt100Heat, PartState.Heat / System.MaxHeat);

            systemRate *= CurrentlyDegrading ? heatModifier : 1;

            if (systemRate < 1)
                systemRate = 1;

            RateOfFire = (int)systemRate;
            BarrelSpinRate = (int)barrelRate;
            TicksPerShot = (uint)(3600f / RateOfFire);
            if (System.HasBarrelRotation) UpdateBarrelRotation();
        }

        private void UpdateBarrelRotation() { } // SUB(11): never entered, HasBarrelRotation=false
        internal bool SpinBarrel(bool spinDown = false) { return true; } // SUB(11): never entered

        // ==================================================== WeaponShoot.cs:17-375 (core)
        internal void Shoot() // Inlined due to keens mod profiler
        {
            var s = Session.I;
            var tick = s.Tick;
            #region Prefire
            var aConst = ActiveAmmoDef.AmmoDef.Const;
            if (_ticksUntilShoot++ < System.DelayToFire) {

                // SUB(6): WeaponShoot.cs:27-28 prefire sound dropped

                if (aConst.MustCharge && aConst.Reloadable || System.AlwaysFireFull)
                    FinishShots = true;

                if (!PreFired)
                    SetPreFire();
                return;
            }

            if (PreFired)
                UnSetPreFire();
            #endregion

            var notReadyToShoot = Session.I.RelativeTime < ShootTime && !MyUtils.IsZero(Session.I.RelativeTime - ShootTime, 1E-04F);
            #region Weapon timing
            if (System.HasBarrelRotation && !SpinBarrel() || notReadyToShoot)
                return;

            // SUB(11): WeaponShoot.cs:47-48 UpdatePivotPos dropped

            ShootTime = TicksPerShot * Session.StepConst + Session.I.RelativeTime;

            LastShootTick = tick;
            if (!IsShooting) StartShooting();

            // SUB(8): WeaponShoot.cs:55-60 Ai velocity cache dropped
            #endregion

            #region Projectile Creation

            // SUB(8): WeaponShoot.cs:66-73 wValues/rnd/pattern/deviation lookups dropped
            var loading = System.Values.HardPoint.Loading;
            FireCounter++;
            var selfDamage = 0f;
            LastShootTick = Session.I.Tick;
            Comp.ShootManager.LastShootTick = Session.I.Tick;

            for (var i = 0; i < loading.BarrelsPerShot; i++)
            {
                #region Update ProtoWeaponAmmo state
                if (aConst.Reloadable)
                {
                    if (ProtoWeaponAmmo.CurrentAmmo == 0)
                    {
                        if (ClientMakeUpShots == 0)
                        {
                            if (s.MpActive && s.IsServer) // What?
                            {
                                s.SendWeaponReload(this);
                            }

                            break;
                        }
                    }

                    if (ProtoWeaponAmmo.CurrentAmmo > 0)
                    {
                        --ProtoWeaponAmmo.CurrentAmmo;

                        // SUB(7): WeaponShoot.cs:102-109 MP ammo sync dropped (MpActive=false)

                        // SUB(10): WeaponShoot.cs:111-114 ShootCount/UpdateShootSync dropped (AiShoot)

                        if (ProtoWeaponAmmo.CurrentAmmo == 0)
                        {
                            ClientLastShotId = Reload.StartId;
                            // SUB(7): WeaponShoot.cs:119-124 client reload request dropped (IsClient=false)
                        }
                    }
                    else if (ClientMakeUpShots > 0)
                    {
                        --ClientMakeUpShots;
                    }

                    // SUB(8): WeaponShoot.cs:137-143 ejection dropped (HasEjector=false)
                }

                #endregion

                // SUB(8): WeaponShoot.cs:152-303 muzzle update, back-kick, AV, deviation,
                // ammo pattern and NewProjectile queueing replaced by counters. With
                // WeaponPattern=false, patternIndex == aConst.WeaponPatternCount (:223) and the
                // generation loops are :195 (TrajectilesPerBarrel) x :252 (patternIndex).
                {
                    var patternIndex = aConst.WeaponPatternCount;
                    for (int j = 0; j < loading.TrajectilesPerBarrel; j++)
                        for (int k = 0; k < patternIndex; k++)
                            ProjectilesEmitted++;
                    RoundsFired++;
                }

                _muzzlesToFire.Add(MuzzleIdToName[NextMuzzle]);

                if (HeatPShot > 0 || ActiveAmmoDef.AmmoDef.AllowNegativeHeatModifier) {

                    if (!HeatLoopRunning)
                    {
                        s.FutureEvents.Schedule(UpdateWeaponHeat, null, 20);
                        HeatLoopRunning = true;
                    }

                    PartState.Heat += HeatPShot;
                    Comp.CurrentHeat += HeatPShot;
                    if ((PartState.Heat >= System.MaxHeat || PartState.Overheated) && !System.WConst.DisableOverheat)
                    {
                        OverHeat();
                        break;
                    }
                    else if (System.WConst.DisableOverheat)
                    {
                        if (PartState.Heat >= System.MaxHeat)
                            PartState.Heat = System.MaxHeat;

                        if (Comp.CurrentHeat >= Comp.MaxHeat)
                            Comp.CurrentHeat = Comp.MaxHeat;
                    }
                }

                if (i == System.Values.HardPoint.Loading.BarrelsPerShot) NextMuzzle++;

                NextMuzzle = (NextMuzzle + (System.Values.HardPoint.Loading.SkipBarrels + 1)) % _numOfMuzzles;
            }

            #endregion

            #region Reload and Animation
            EventTriggerStateChanged(state: EventTriggers.Firing, active: true, muzzles: _muzzlesToFire);

            _muzzlesToFire.Clear();
            _nextVirtual = _nextVirtual + 1 < System.Values.HardPoint.Loading.BarrelsPerShot ? _nextVirtual + 1 : 0;

            // SUB(8): WeaponShoot.cs:343-358 DecayPerShot self-damage dropped (selfDamage == 0)
            if (selfDamage > 0) { }

            if (ActiveAmmoDef.AmmoDef.Const.HasShotReloadDelay && System.ShotsPerBurst > 0 && ++ShotsFired == System.ShotsPerBurst)
            {
                var burstDelay = (uint)System.Values.HardPoint.Loading.DelayAfterBurst;
                ShotsFired = 0;
                ShootTime = burstDelay > TicksPerShot ? burstDelay * Session.StepConst + Session.I.RelativeTime : TicksPerShot * Session.StepConst + Session.I.RelativeTime;
                if (System.Values.HardPoint.Loading.GiveUpAfter)
                    GiveUpTarget();
            }

            if (System.AlwaysFireFull || ActiveAmmoDef.AmmoDef.Const.BurstMode)
                FinishMode();

            #endregion
        }

        // ==================================================== WeaponShoot.cs:377-401
        private void FinishMode()
        {
            if (ActiveAmmoDef.AmmoDef.Const.BurstMode && ++ShotsFired > System.ShotsPerBurst) { // detect when the "first" burst cycle has ended and reset it to shot == 1 so that it can repeat multiple times within a reload window
                ShotsFired = 1;
                EventTriggerStateChanged(EventTriggers.BurstReload, false);
            }

            var outOfShots = ProtoWeaponAmmo.CurrentAmmo == 0 && ClientMakeUpShots == 0;
            var burstReset = ActiveAmmoDef.AmmoDef.Const.BurstMode && ShotsFired == System.ShotsPerBurst;
            var genericReset = !ActiveAmmoDef.AmmoDef.Const.BurstMode && outOfShots;

            if (burstReset) {

                EventTriggerStateChanged(EventTriggers.BurstReload, true);
                var burstDelay =  (uint)System.WConst.DelayAfterBurst;
                ShootTime = burstDelay > TicksPerShot ? burstDelay * Session.StepConst + Session.I.RelativeTime : TicksPerShot * Session.StepConst + Session.I.RelativeTime;
                if (System.WConst.GiveUpAfter)
                     GiveUpTarget();
            }
            else if (System.AlwaysFireFull)
                FinishShots = true;

            if (burstReset || genericReset)
                StopShooting(burstReset && !outOfShots);
        }

        // ==================================================== WeaponShoot.cs:403-410
        private void GiveUpTarget()
        {
            if (Session.I.IsServer)
            {
                // SUB(10): Target.Reset / FastTargetResetTick dropped (target system out of scope)
            }
        }

        // ==================================================== WeaponShoot.cs:412-435
        private void OverHeat()
        {
            if (Session.I.IsServer && Comp.Data.Repo.Values.Set.Overload > 1)
            {
                // SUB(10): overload self-damage dropped (Overload == 1 in every scenario)
            }

            EventTriggerStateChanged(EventTriggers.Overheated, true);
            Comp.ShootManager.EndShootMode(ShootManagerStub.EndReason.Overheat, true);


            if (Session.I.IsServer)
            {
                var wasOver = PartState.Overheated;
                if (!wasOver)
                    OverHeatCountDown = 15;

                PartState.Overheated = true;
                if (Session.I.MpActive && !wasOver)
                    Session.I.SendState(Comp);
            }

        }

        // ==================================================== WeaponShoot.cs:437-460
        private void UnSetPreFire()
        {
            EventTriggerStateChanged(EventTriggers.PreFire, false);
            _muzzlesToFire.Clear();
            PreFired = false;
            // SUB(6): prefire sound stop dropped
        }

        private void SetPreFire()
        {
            var nxtMuzzle = NextMuzzle;
            for (int i = 0; i < System.Values.HardPoint.Loading.BarrelsPerShot; i++)
            {
                _muzzlesToFire.Clear();
                _muzzlesToFire.Add(MuzzleIdToName[NextMuzzle]);
                if (i == System.Values.HardPoint.Loading.BarrelsPerShot) NextMuzzle++;
                nxtMuzzle = (nxtMuzzle + (System.Values.HardPoint.Loading.SkipBarrels + 1)) % _numOfMuzzles;
            }

            EventTriggerStateChanged(EventTriggers.PreFire, true, _muzzlesToFire);

            PreFired = true;
        }

        // ==================================================== WeaponState.cs:119-164
        public void StartShooting()
        {
            // SUB(6): firing sound dropped
            if (!IsShooting)
            {
                EventTriggerStateChanged(EventTriggers.StopFiring, false);
                // SUB(13): !Reloadable ChargeReload branch dead (Reloadable=true for all PDCs)
            }
            IsShooting = true;
        }

        public void StopShooting(bool burst = false)
        {
            if (IsShooting || PreFired)
            {
                EventTriggerStateChanged(EventTriggers.Firing, false);
                EventTriggerStateChanged(EventTriggers.StopFiring, true, _muzzlesToFire);
            }

            // SUB(6): HandlesInput AV dropped

            if (IsShooting && Session.I.IsServer && Session.I.MpActive)
            {
                // Send the burst shot end on state change:
                Session.I.SendWeaponAmmoData(this, true);
            }

            ResetShotState();
        }

        private void ResetShotState()
        {
            FireCounter = 0;
            CeaseFireDelayTick = uint.MaxValue / 2;
            _ticksUntilShoot = 0;
            FinishShots = false;

            if (PreFired)
                UnSetPreFire();

            IsShooting = false;
        }

        // ==================================================== WeaponReload.cs:125-158
        internal bool HasAmmo()
        {
            if (Session.I.IsCreative || !ActiveAmmoDef.AmmoDef.Const.Reloadable || Comp_InfiniteResource) {
                NoMagsToLoad = false;
                return true;
            }

            Reload.CurrentMags = Comp.TypeSpecific != CompTypeSpecific.Phantom ? Comp.CoreInventory.GetItemAmount(ActiveAmmoDef.AmmoDefinitionId).ToIntSafe() : Reload.CurrentMags;

            var energyDrainable = ActiveAmmoDef.AmmoDef.Const.EnergyAmmo && Comp_Ai_HasPower;
            var nothingToLoad = Reload.CurrentMags <= 0 && !energyDrainable;

            if (NoMagsToLoad) {
                if (nothingToLoad)
                    return false;

                EventTriggerStateChanged(EventTriggers.NoMagsToLoad, false);
                // SUB(10): construct OutOfAmmoWeapons set dropped
                NoMagsToLoad = false;
                LastMagSeenTick = Session.I.Tick;
            }
            else if (nothingToLoad)
            {
                EventTriggerStateChanged(EventTriggers.NoMagsToLoad, true);
                // SUB(10): construct OutOfAmmoWeapons set dropped

                if (!NoMagsToLoad)
                    CheckInventorySystem = true;

                NoMagsToLoad = true;
            }

            return !NoMagsToLoad;
        }
        public bool Comp_InfiniteResource;   // Comp.InfiniteResource
        public bool Comp_Ai_HasPower = true; // Comp.Ai.HasPower

        // ==================================================== WeaponReload.cs:210-258
        internal bool ComputeServerStorage(bool calledFromReload = false)
        {
            var s = Session.I;
            var isPhantom = Comp.TypeSpecific == CompTypeSpecific.Phantom;

            if (!Comp.IsWorking || !ActiveAmmoDef.AmmoDef.Const.Reloadable || !Comp.HasInventory && !isPhantom) return false;

            if (!ActiveAmmoDef.AmmoDef.Const.EnergyAmmo && !isPhantom)
            {
                if (!s.IsCreative)
                {
                    // SUB(9): WeaponReload.cs:221-241 conveyor-pull block reduced to its one
                    // state-relevant line; the harness pre-stocks the block inventory.
                    Reload.CurrentMags = Comp.CoreInventory.GetItemAmount(ActiveAmmoDef.AmmoDefinitionId).ToIntSafe();
                }
            }

            var outOfAmmo = ProtoWeaponAmmo.CurrentAmmo == 0;
            var sendHome = System.GoHomeToReload && !IsHome;

            if (outOfAmmo) {
                if (sendHome && !ReturingHome)
                    ScheduleWeaponHome(true);

                if (System.DropTargetUntilLoaded && Target.HasTarget)
                { /* SUB(10): Target.Reset dropped */ }
            }

            var invalidStates = !outOfAmmo || sendHome || Loading || calledFromReload || Reload.WaitForClient || (System.MaxReloads > 0 && Reload.LifetimeLoads >= System.MaxReloads);
            return !invalidStates && ServerReload();
        }

        private void ScheduleWeaponHome(bool sendNow = false) { } // SUB(10)

        // ==================================================== WeaponReload.cs:260-305
        internal bool ServerReload()
        {
            if (DelayedCycleId >= 0)
                throw new InvalidOperationException("ammo cycling not modelled"); // SUB(13): ChangeAmmo — self-verifying boundary

            if (ScheduleAmmoChange)
                throw new InvalidOperationException("ammo cycling not modelled"); // SUB(13): ChangeActiveAmmoServer

            var hasAmmo = HasAmmo();

            if (!hasAmmo)
                return false;

            ++Reload.StartId;
            ++ClientStartId;
            ++Reload.LifetimeLoads;

            if (!ActiveAmmoDef.AmmoDef.Const.EnergyAmmo)
            {
                var isPhantom = Comp.TypeSpecific == CompTypeSpecific.Phantom;
                Reload.MagsLoaded = ActiveAmmoDef.AmmoDef.Const.MagsToLoad <= Reload.CurrentMags || Session.I.IsCreative ? ActiveAmmoDef.AmmoDef.Const.MagsToLoad : Reload.CurrentMags;

                if (!Session.I.IsCreative && !isPhantom)
                {
                    if (Comp.CoreInventory.ItemsCanBeRemoved(Reload.MagsLoaded, InventoryStub.AmmoItemStub))
                    {
                        // SUB(9): FindItem/magItem resolution collapses to the counter decrement
                        Comp.CoreInventory.RemoveItems(0, Reload.MagsLoaded);
                    }
                    else if (Comp.CoreInventory.ItemCount > 0 && Comp.CoreInventory.ContainItems(Reload.MagsLoaded, null))
                        Comp.CoreInventory.Remove(null, Reload.MagsLoaded);
                }
                Reload.CurrentMags = !isPhantom ? Comp.CoreInventory.GetItemAmount(ActiveAmmoDef.AmmoDefinitionId).ToIntSafe() : Reload.CurrentMags - Reload.MagsLoaded;
                if (Reload.CurrentMags == 0)
                    CheckInventorySystem = true;
            }
            else
                Reload.MagsLoaded = ActiveAmmoDef.AmmoDef.Const.MagsToLoad;

            StartReload();
            return true;
        }

        // ==================================================== WeaponReload.cs:307-343
        internal void StartReload()
        {
            Loading = true;
            // SUB(13): Rifle iron-sights branch dead (TypeSpecific=Block)

            if (!ActiveAmmoDef.AmmoDef.Const.BurstMode && !ActiveAmmoDef.AmmoDef.Const.HasShotReloadDelay && System.Values.HardPoint.Loading.GiveUpAfter)
                GiveUpTarget();

            EventTriggerStateChanged(EventTriggers.Reloading, true);

            if (ActiveAmmoDef.AmmoDef.Const.MustCharge)
                throw new InvalidOperationException("charge weapons not modelled"); // SUB(13): ChargeReload

            if (!ActiveAmmoDef.AmmoDef.Const.MustCharge || ActiveAmmoDef.AmmoDef.Const.IsHybrid) {

                var timeSinceShot = LastShootTick > 0 ? Session.I.Tick - LastShootTick : 0;
                var delayTime = timeSinceShot <= System.Values.HardPoint.Loading.DelayAfterBurst ? System.Values.HardPoint.Loading.DelayAfterBurst - timeSinceShot : 0;
                var delay = delayTime > 0 && ShotsFired == 0;
                if (System.WConst.ReloadTime > 0 || delay)
                {
                    ReloadEndTick = (uint)(Session.I.Tick + (!delay || System.WConst.ReloadTime > delayTime ? System.WConst.ReloadTime : delayTime));
                }
                else Reloaded(ReloadedState.Hybrid);
            }

            if (Session.I.MpActive && Session.I.IsServer)
            {
                if (ActiveAmmoDef.AmmoDef.Const.SlowFireFixedWeapon)
                    Reload.WaitForClient = false;

                Session.I.SendWeaponReload(this);
            }

            // SUB(6): reload sound dropped (ReloadEmitter == null path)
        }

        // ==================================================== WeaponReload.cs:345-428
        internal void Reloaded(ReloadedState state) // why tf was this a nullable object where half the inputs weren't even used lol
        {
            var callBack = state == ReloadedState.Callback;
            var earlyExit = state == ReloadedState.EarlyExit;
            {
                // SUB(2): CoreEntity.Pin()/MarkedForClose guards dropped (entity always live here)

                if (state == ReloadedState.ChargedOnly) {
                    ProtoWeaponAmmo.CurrentCharge = MaxCharge;
                    EstimatedCharge = MaxCharge;
                    return;
                }

                if (ActiveAmmoDef.AmmoDef.Const.MustCharge && !callBack && !earlyExit) {

                    ProtoWeaponAmmo.CurrentCharge = MaxCharge;
                    EstimatedCharge = MaxCharge;

                    if (ActiveAmmoDef.AmmoDef.Const.IsHybrid && LoadingWait)
                        return;
                }
                else if (ActiveAmmoDef.AmmoDef.Const.IsHybrid && Charging && ReloadEndTick != uint.MaxValue)
                {
                    ReloadEndTick = uint.MaxValue - 1;
                    return;
                }

                ProtoWeaponAmmo.CurrentAmmo = Reload.MagsLoaded * ActiveAmmoDef.AmmoDef.Const.MagazineSize;
                if (Session.I.IsServer) {

                    ++Reload.EndId;
                    ClientEndId = Reload.EndId;

                    if (Comp.TypeSpecific == CompTypeSpecific.Phantom && ActiveAmmoDef.AmmoDef.Const.EnergyAmmo)
                        --Reload.CurrentMags;

                    if (Session.I.MpActive)
                    {
                        Session.I.SendWeaponReload(this);
                        if (Reload.EndId == 1)
                        {
                            Session.I.SendWeaponAmmoData(this);
                        }
                    }
                }
                // SUB(7): client-side else branch (WeaponReload.cs:394-411) dropped (IsClient=false)

                TargetData.WeaponRandom.TurretRandom = new XorShiftRandomStruct((ulong)(TargetData.WeaponRandom.CurrentSeed + (Reload.EndId + 1000000)));
                EventTriggerStateChanged(EventTriggers.Reloading, false);
                LastLoadedTick = Session.I.Tick;

                if (!ActiveAmmoDef.AmmoDef.Const.HasShotReloadDelay)
                    ShotsFired = 0;

                Loading = false;
                ReloadEndTick = uint.MaxValue;
                ProjectileCounter = 0;
                NextMuzzle = 0;

                if (Comp.ShootManager.LastCycle != uint.MaxValue)
                    Comp.ShootManager.EndShootMode(ShootManagerStub.EndReason.Reload);
            }
        }
        internal bool LoadingWait { get { return ReloadEndTick < uint.MaxValue - 1; } } // WeaponFields.cs:243
        public bool Charging;

        // ==================================================== WeaponReload.cs:438-448
        public void CancelReload()
        {
            if (ReloadEndTick == uint.MaxValue)
                return;
            NextMuzzle = 0;
            EventTriggerStateChanged(EventTriggers.Reloading, false);
            LastLoadedTick = Session.I.Tick;
            Loading = false;
            ReloadEndTick = uint.MaxValue;
            ProjectileCounter = 0;
        }

        // SUB(6): all EventTriggerStateChanged calls -> no-op (animation system)
        internal void EventTriggerStateChanged(EventTriggers state, bool active, List<int> muzzles = null) { }

        // ============================================================ per-tick driver, SUB(12)
        // Frame order per SessionRun.cs: Timings() [Tick++/RelativeTime, SessionSupport.cs:36,56]
        // -> FutureEvents.Tick(Tick) [SessionRun.cs:142, the heat loop] -> AiLoop [reload check
        // SessionUpdate.cs:615-633, shoot gate :656,:786-815] -> ShootWeapons [:962-978].
        public void RunTick(bool wantFire)
        {
            Session.I.Tick++;                                    // SessionSupport.cs:36
            Session.I.RelativeTime += Session.StepConst;         // SessionSupport.cs:54-56 (server: ratio 1)
            Session.I.FutureEvents.Tick(Session.I.Tick);         // SessionRun.cs:142

            // ---- SessionUpdate.cs:615-633 (server branch)
            var aConst = ActiveAmmoDef.AmmoDef.Const;
            if (aConst.Reloadable && !System.DesignatorWeapon && !Loading)
            { // does this need StayCharged?
                if (Session.I.IsServer)
                {
                    if (ProtoWeaponAmmo.CurrentAmmo == 0 || CheckInventorySystem)
                        ComputeServerStorage();
                }
            }
            else if (Loading && (Session.I.IsServer && Session.I.Tick >= ReloadEndTick))
                Reloaded(ReloadedState.Callback);

            // ---- SessionUpdate.cs:656 + 786-815, AiShoot auto-fire path
            var noAmmo = ProtoWeaponAmmo.CurrentAmmo == 0;                       // :656
            var reloadingGuard = aConst.Reloadable && ClientMakeUpShots == 0 && (Loading || noAmmo || Reload.WaitForClient || ClientReloadWaitingForServer); // :793
            var overHeat = PartState.Overheated && (OverHeatCountDown == 0 || OverHeatCountDown != 0 && OverHeatCountDown-- == 0); // :794
            var needsHeat = ActiveAmmoDef.AmmoDef.HeatNeededToFire > 0 && PartState.Heat < ActiveAmmoDef.AmmoDef.HeatNeededToFire; // :795
            var sequenceReady = true;                                            // SUB(12): :578, no weapon groups
            var canShoot = !overHeat && !reloadingGuard && !System.DesignatorWeapon && sequenceReady && !needsHeat; // :797
            var autoShot = wantFire;                                             // SUB(12): :800 AiShooting && Trigger==Off
            var anyShot = autoShot;                                              // SUB(12): :801, AiShoot mode only
            var delayedFire = false;                                             // SUB(12): :803 DelayCeaseFire aim path
            var finish = FinishShots || delayedFire;                             // :804
            var shootRequest = (anyShot || finish);                              // :805
            var shotReady = canShoot && shootRequest;                            // :807
            var shoot = shotReady;                                               // SUB(12): :809 ai.CanShoot/target terms true

            if (shoot)
            {
                // ---- ShootWeapons quickSkip, SessionUpdate.cs:966-973 (live-entity/LOS terms true)
                var quickSkip = PauseShoot || (ProtoWeaponAmmo.CurrentAmmo == 0 && ClientMakeUpShots == 0) && ActiveAmmoDef.AmmoDef.Const.Reloadable;
                if (quickSkip)
                    PauseShoot = false;
                else
                    Shoot();
            }
            else
            {
                if (IsShooting || PreFired)
                    StopShooting();
                // SUB(11): SpinBarrel spin-down dropped
            }
        }

        // Harness helper: seed pre-existing heat the way a prior burst would have left it
        // (heat present -> the 20-tick loop is running, WeaponShoot.cs:307-311).
        public void PrimeHeat(float heat)
        {
            PartState.Heat = heat;
            Comp.CurrentHeat = heat;
            if (heat > 0 && !HeatLoopRunning)
            {
                Session.I.FutureEvents.Schedule(UpdateWeaponHeat, null, 20);
                HeatLoopRunning = true;
            }
        }
    }
}
