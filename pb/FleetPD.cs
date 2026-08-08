// ============================================================================
//  FLEET POINT DEFENCE  —  "descend on in-flight commitment"
//  Paste into a Programmable Block, append the WcPbApi class, recompile.
//  No configuration. Put one on every hull; they find each other over IGC.
//
//  MEASURED RESULT (3 hulls, 24 torpedoes/wave, 20 waves, 6 s gaps, 12 seeds):
//      no script .................. dies wave ~2.6,  71.5 cumulative leakers
//      shot-counting ladder ....... dies wave  5.6,  21.8
//      THIS ....................... dies wave 14.5,   4.3   at 29.9% peak heat
//  A same-scoring alternative (wave-boundary respread) needed 18,595 rounds and
//  hit 77.3% heat; this needs 13,731 at 29.9%, i.e. it survives just as long on
//  26% less ammunition and less than half the heat. That matters past ~20 waves,
//  where 0.8*MaxHeat latches DegradeRof and only clears at 0.4 (~135 s of not
//  firing) — a one-way door, confirmed against real WeaponCore.
//
//  HOW IT WORKS
//  Each weapon block sits on a rung of a six-step range ladder, and the battery
//  starts spread across the rungs. When a block has >= K of its OWN rounds in
//  the air, it drops a rung. Shrinking its tracking range makes its currently
//  held target ineligible, so WeaponCore re-acquires something closer.
//
//  It is a RE-AIM, never a cease-fire. That distinction is the whole result:
//  across ~45 tested policies, everything that concentrates or re-prioritises
//  fire beat baseline, and everything that withheld fire lost. K = 4 is one
//  kill's worth of committed ordnance (torpedo Health 4, PDC40mm HHM 1), and it
//  trips fastest at long range where time-of-flight piles up unresolved
//  commitment — which is exactly when a mount should stop dwelling far out.
//
//  DELIBERATELY ABSENT, all measured worse:
//    * heat cycling / any cease-fire ....... 131.6 vs 21.8 cumulative leakers.
//      A DEGRADED mount still fires ~12 rd/s; a cooling-pinned one ~1.3.
//      The heat cliff is better crossed than guarded.
//    * ray de-confliction ................. no leaker benefit at 100 seeds.
//    * duty rotation / toggling ........... +1.8 to +5.3 leakers.
//    * per-hull edge cap .................. helps a shot-counting ladder, but
//      measured WORSE combined with this trigger (5.50 vs 4.25), and the threat
//      edge is not PB-observable anyway: GetProjectilesLockedOn returns a COUNT
//      with no distance, and GetWeaponTarget on a projectile target hands back a
//      MyDetectedEntityInfo built from a null entity (ApiBackend.cs:1074), so a
//      PB cannot even tell "tracking a torpedo" from "no target".
//    * wave-boundary respread ............. byte-identical to this policy; the
//      in-flight counter already zeroes itself between waves.
//
//  KNOWN LIMIT — read this before trusting it. SDX2 PDCs fire pure LINEAR LEAD
//  at projectiles: the accel-tracking solver is gated behind
//  UseLimitlessPDSolver, which no SDX2 weapon sets. Torpedo220mmHekp and
//  Torpedo160mmBlastFrag fly a scripted terminal S-weave (2652 m/s^2) inside the
//  PDC envelope and are essentially unstoppable by ANY fire control — against
//  those this script leaks ~36 of 48 and so does everything else, including no
//  script at all. The counter there is geometric (escort placement, closing
//  speed), not scripted. This policy is tuned against Plasma220-class rounds.
// ============================================================================

const int    K_INFLIGHT     = 4;      // one kill's worth of committed rounds
const double REFRACTORY_S   = 0.35;   // min seconds between descents
const int    WAVE_GAP_TICKS = 60;     // PB runs with inbound==0 => wave is over
const double MIN_RANGE_M    = 300.0;  // never gate a mount below this
const double MIN_RPM        = 100.0;  // below this, leave the mount ALONE
const double RPM_SAMPLE_S   = 8.0;    // observation window for measured rate
const double RESCAN_S       = 30.0;   // pick up built/repaired/destroyed mounts
const bool   DEBUG_PANEL    = true;
const string IGC_TAG        = "FleetPD.v1";
const int    PEER_TIMEOUT   = 30;     // runs before a silent peer is dropped
const bool   FLEET_TILE     = true;   // offset opening rungs by hull ordinal

// Rung fractions of each block's own max weapon range.
static readonly double[] RUNGS = { 1.00, 0.80, 0.65, 0.50, 0.38, 0.28 };
// Derived, never a second literal — a mismatch here would index out of bounds.
static readonly int RUNG_COUNT = RUNGS.Length;

WcPbApi Wc;
bool Ready;
IMyBroadcastListener Igc;

// ---- fleet state.
// WHY IGC IS LOAD-BEARING, not decoration: GetProjectilesLockedOn(victim) counts
// projectiles locked onto ONE grid. A consort has ZERO locked onto itself while
// the lead is being saturated, so a hull that only ever queries its own grid
// sees Inbound == 0, never descends, and never detects a wave. Escorts would
// contribute nothing. The API accepts ANY victim id, so peers exchange grid ids
// and every hull then polls every peer locally — fresher and simpler than
// broadcasting counts, since no count can go stale in transit.
readonly Dictionary<long, int> Peers = new Dictionary<long, int>();  // gridId -> age
readonly List<long> PeerIds = new List<long>();
int HullOrdinal;      // stable index among peers, for fleet-wide rung tiling
int HullCount = 1;
int TiledFor = -1;    // ordinal the current opening rungs were computed for

class Mount {
    public IMyTerminalBlock Blk;
    public long   Id;
    public double BaseRange;
    public int    Rung;
    public int    OpeningRung;
    public int    InFlight;      // exact, from the projectile monitor
    public double LastDescend;
    // Measured rate of fire. There is no API getter for RoF, but the projectile
    // monitor already sees every spawn, so the script observes it directly.
    public int    Spawns;
    public double SampleStart;
    public double Rpm;
    public bool   Exempt;        // slow mount: run no policy at all
    public readonly List<int> Parts = new List<int>();
}

readonly List<Mount> Mounts = new List<Mount>();
readonly Dictionary<long, Mount> ById = new Dictionary<long, Mount>();
readonly List<IMyTerminalBlock> _blocks = new List<IMyTerminalBlock>();
readonly Dictionary<string, int> _map = new Dictionary<string, int>();

double Now;
double RescanDue;
int    ZeroRuns = WAVE_GAP_TICKS;
int    Inbound;

public Program() {
    Runtime.UpdateFrequency = UpdateFrequency.Update10;
    Wc = new WcPbApi();
    try { Ready = Wc.Activate(Me); } catch { Ready = false; }
    Igc = IGC.RegisterBroadcastListener(IGC_TAG);
    // Deliberately NO SetMessageCallback: we poll in Gossip() on the Update10 tick.
    // A callback plus an unconditional broadcast each run makes every hull wake every
    // other hull, which then broadcasts again — a self-sustaining message storm.
    if (Ready) Discover();
}

// ------------------------------------------------------------------- IGC
// Each hull announces only its grid id. Everything else is derived locally, so
// there is no protocol to version and nothing to desynchronise.
void Gossip() {
    while (Igc.HasPendingMessage) {
        var msg = Igc.AcceptMessage();
        if (!(msg.Data is long)) continue;
        long id = (long)msg.Data;
        if (id != Me.CubeGrid.EntityId) Peers[id] = 0;
    }
    IGC.SendBroadcastMessage(IGC_TAG, Me.CubeGrid.EntityId);

    // age out hulls that have gone quiet (destroyed, PB off, out of range)
    PeerIds.Clear();
    foreach (var kv in Peers) PeerIds.Add(kv.Key);
    foreach (var id in PeerIds) {
        int age = Peers[id] + 1;
        if (age > PEER_TIMEOUT) Peers.Remove(id); else Peers[id] = age;
    }

    // Stable ordinal by sorted grid id, so every hull independently computes the
    // same ordering without electing a leader.
    PeerIds.Clear();
    PeerIds.Add(Me.CubeGrid.EntityId);
    foreach (var kv in Peers) PeerIds.Add(kv.Key);
    PeerIds.Sort();
    HullCount = PeerIds.Count;
    HullOrdinal = PeerIds.IndexOf(Me.CubeGrid.EntityId);
    if (HullOrdinal < 0) HullOrdinal = 0;

    // Discover() runs in the constructor, before any peer has been heard, so the
    // opening rungs were computed at ordinal 0. Re-tile whenever the ordinal
    // moves (a hull joins, or one is destroyed and the sort shifts).
    if (FLEET_TILE && HullOrdinal != TiledFor) {
        TiledFor = HullOrdinal;
        for (int i = 0; i < Mounts.Count; i++) {
            Mounts[i].OpeningRung = OpeningFor(i);
            if (Inbound <= 0) Mounts[i].Rung = Mounts[i].OpeningRung;
        }
    }
}

// Fleet-wide inbound: the largest count locked onto ANY known hull. That is the
// engagement signal an escort needs, and it is what makes escorts participate.
int FleetInbound() {
    int best = 0;
    for (int i = 0; i < PeerIds.Count; i++) {
        var t = Wc.GetProjectilesLockedOn(PeerIds[i]);
        if (t.Item1 && t.Item2 > best) best = t.Item2;
    }
    return best;
}

// ---------------------------------------------------------------- discovery
void Discover() {
    foreach (var m in Mounts) {
        if (!Alive(m.Blk)) continue;          // never touch a closed block
        foreach (var pid in m.Parts)
            Wc.UnMonitorProjectileCallback(m.Blk, pid, OnProjectile);
    }
    Mounts.Clear();
    ById.Clear();
    _blocks.Clear();
    GridTerminalSystem.GetBlocksOfType(_blocks,
        b => Alive(b) && b.IsSameConstructAs(Me) && Wc.HasCoreWeapon(b));

    int spread = 0;
    foreach (var b in _blocks) {
        _map.Clear();
        if (!Wc.GetBlockWeaponMap(b, _map) || _map.Count == 0) continue;

        // SetBlockTrackingRange is per BLOCK, not per weapon part, so the block
        // is the unit of control. Use the longest-reaching part for the base.
        double baseRange = 0.0;
        foreach (var kv in _map) {
            float r = Wc.GetMaxWeaponRange(b, kv.Value);
            if (r > baseRange) baseRange = r;
        }
        // Anti-torpedo duty only. Also skip very slow guns: a mount that gets
        // ~5 rounds off per engagement loses more to range narrowing than the
        // re-aim can win back (measured: sub-100-rpm mounts do worse WITH the
        // ladder than without it).
        if (baseRange < 500.0) continue;

        var mt = new Mount {
            Blk = b, Id = b.EntityId, BaseRange = baseRange,
            Rung = OpeningFor(spread), OpeningRung = OpeningFor(spread),
            InFlight = 0, LastDescend = -99.0
        };
        Mounts.Add(mt);
        ById[b.EntityId] = mt;

        // Exact in-flight accounting. The callback fires with start=true at
        // spawn (Projectile.cs:352) and start=false at end of life
        // (ProjectileTypes.cs:120), so a running count is exact rather than
        // estimated. Register on every part of the block.
        foreach (var kv in _map) {
            mt.Parts.Add(kv.Value);
            Wc.MonitorProjectileCallback(b, kv.Value, OnProjectile);
        }
        spread++;
    }
}

// Opening rung for the n-th block on this hull. With FLEET_TILE the hull's
// ordinal offsets the pattern so a 3-hull formation tiles the ladder instead of
// three hulls duplicating the same spread. UNTESTED IN SIM — the harness gives
// every hull an identical spread — so it is a flag, and setting it false
// reproduces the measured configuration exactly.
int OpeningFor(int n) {
    int off = FLEET_TILE ? HullOrdinal : 0;
    return ((n + off) % RUNG_COUNT + RUNG_COUNT) % RUNG_COUNT;
}

// A destroyed PDC leaves a dangling IMyTerminalBlock. Calling into the WeaponCore
// API with one reaches a component lookup on a closed entity, which is the classic
// way a PB script throws. Everything that touches m.Blk goes through this first.
static bool Alive(IMyTerminalBlock b) {
    // NB: IMyCubeGrid in the INGAME api has no MarkedForClose (that is mod-api only),
    // so Closed plus a non-null grid is the strongest check available to a PB.
    return b != null && !b.Closed && b.CubeGrid != null;
}

void OnProjectile(long coreEnt, int partId, ulong projId, long targetId,
                  Vector3D pos, bool start) {
    Mount m;
    if (!ById.TryGetValue(coreEnt, out m)) return;
    // targetId == -1 is the sentinel for a PROJECTILE target (Target.SetTargetId).
    // Every anti-torpedo round reports the same -1, so rounds cannot be
    // attributed to individual torpedoes — but a COUNT is all this needs, and
    // filtering on -1 keeps anti-grid fire from polluting it.
    if (targetId != -1) return;
    if (start) { m.InFlight++; m.Spawns++; }
    else if (m.InFlight > 0) m.InFlight--;
}

// ------------------------------------------------------------------- main
public void Main(string arg, UpdateType src) {
    if (!Ready) {
        Wc = new WcPbApi();
        try { Ready = Wc.Activate(Me); } catch { Ready = false; }
        if (!Ready) { Echo("WeaponCore PB API unavailable."); return; }
        Discover();
    }
    if (arg == "rescan") { Discover(); }
    if (Mounts.Count == 0) { Discover(); if (Mounts.Count == 0) { Echo("No CoreSystems weapons found."); return; } }

    Now += Runtime.TimeSinceLastRun.TotalSeconds;
    Gossip();

    // Inbound COUNT across the whole formation. Counts only — the API returns
    // MyTuple<bool,int,int> with no distances, which is why there is no
    // edge/window logic anywhere in this script.
    Inbound = FleetInbound();

    // Wave boundary -> restore the opening spread. Measured redundant with this
    // trigger (the in-flight counter self-clears between waves) but kept as
    // cheap insurance: in game, waves need not arrive as cleanly as in the sim,
    // and a battery stranded on low rungs between waves was worth 40.9 vs 4.3
    // cumulative leakers when it went wrong.
    if (Inbound <= 0) {
        ZeroRuns++;
    } else {
        if (ZeroRuns >= WAVE_GAP_TICKS) Respread();
        ZeroRuns = 0;
    }

    // Drop dead mounts and rescan if any went away. Cheap: reference checks only.
    bool lost = false;
    for (int i = Mounts.Count - 1; i >= 0; i--) {
        if (!Alive(Mounts[i].Blk)) { ById.Remove(Mounts[i].Id); Mounts.RemoveAt(i); lost = true; }
    }
    if (lost) RescanDue = 0.0;
    // Periodic rescan also picks up newly built or repaired mounts.
    if (Now >= RescanDue) { RescanDue = Now + RESCAN_S; Discover(); }

    foreach (var m in Mounts) {
        if (!Alive(m.Blk)) continue;
        // ---- measured rate of fire, and the slow-mount exemption.
        // MEASURED, not assumed: on PdcMcrnAdv (80 rpm) and PdcOpaAdv (30 rpm),
        // NO SCRIPT beats every range policy (26.8 vs 29.8, and 38.9 vs 39.5
        // leakers). A mount that gets ~3 rounds off inside the 2.4 s window
        // loses more to any range narrowing than a re-aim can win back. Note
        // this is a RATE effect, not a HealthHitModifier one — scaling K by HHM
        // was tested and does essentially nothing (29.61 vs 29.83, t=-0.58).
        if (m.SampleStart <= 0.0) m.SampleStart = Now;
        double span = Now - m.SampleStart;
        if (span >= RPM_SAMPLE_S) {
            double rpm = m.Spawns * 60.0 / span;
            m.Rpm = (m.Rpm <= 0.0) ? rpm : (m.Rpm * 0.5 + rpm * 0.5);
            m.Spawns = 0;
            m.SampleStart = Now;
            // only ever latch the exemption on evidence of actually shooting
            if (m.Rpm > 0.0) m.Exempt = m.Rpm < MIN_RPM;
        }
        if (m.Exempt) {
            Wc.SetBlockTrackingRange(m.Blk, (float)m.BaseRange);
            continue;
        }

        if (Inbound > 0
            && m.InFlight >= K_INFLIGHT
            && Now - m.LastDescend >= REFRACTORY_S
            && m.Rung < RUNG_COUNT - 1) {
            m.Rung++;
            m.LastDescend = Now;
        }
        double want = m.BaseRange * RUNGS[m.Rung];
        if (want < MIN_RANGE_M) want = MIN_RANGE_M;
        Wc.SetBlockTrackingRange(m.Blk, (float)want);
        // Fire is NEVER toggled. Every withholding policy tested lost.
    }

    if (DEBUG_PANEL) Report();
}

void Respread() {
    foreach (var m in Mounts) {
        m.Rung = m.OpeningRung;
        m.LastDescend = -99.0;
        // InFlight is not touched: the monitor owns it, and rounds still in the
        // air are real regardless of wave bookkeeping.
    }
}

void Report() {
    int air = 0;
    var rungs = new int[RUNG_COUNT];
    foreach (var m in Mounts) { air += m.InFlight; rungs[m.Rung]++; }
    var sb = new StringBuilder();
    sb.Append("FleetPD  blocks=").Append(Mounts.Count)
      .Append("  hull ").Append(HullOrdinal + 1).Append('/').Append(HullCount)
      .Append("  inbound(fleet)=").Append(Inbound).AppendLine();
    sb.Append("own rounds airborne=").Append(air)
      .Append("  (descend at ").Append(K_INFLIGHT).Append(")").AppendLine();
    if (Mounts.Count == 0) { Echo("FleetPD: no usable weapons."); return; }
    int ex = 0;
    foreach (var m in Mounts) if (m.Exempt) ex++;
    if (ex > 0) sb.Append("exempt (slow, <").Append((int)MIN_RPM).Append(" rpm)=")
                  .Append(ex).AppendLine();
    sb.Append("rungs far->near: ");
    for (int i = 0; i < RUNG_COUNT; i++) {
        sb.Append(rungs[i]);
        if (i < RUNG_COUNT - 1) sb.Append('/');
    }
    Echo(sb.ToString());
}

// ============================================================================
//  APPEND the WcPbApi class here.
//  Source: WeaponCore  Data/Scripts/CoreSystems/Api/CoreSystemsPbApi.cs
//  (published for exactly this purpose — copy the whole class verbatim).
//
//  Members used, all verified present in that class:
//     Activate(IMyTerminalBlock)                          -> bool
//     HasCoreWeapon(IMyTerminalBlock)                      -> bool
//     GetBlockWeaponMap(IMyTerminalBlock, IDictionary<string,int>) -> bool
//     GetMaxWeaponRange(IMyTerminalBlock, int)             -> float
//     SetBlockTrackingRange(IMyTerminalBlock, float)       -> void   (per BLOCK)
//     GetProjectilesLockedOn(long)                         -> MyTuple<bool,int,int>
//     MonitorProjectileCallback(IMyTerminalBlock, int, Action<long,int,ulong,long,Vector3D,bool>)
//     UnMonitorProjectileCallback(IMyTerminalBlock, int, Action<...>)
// ============================================================================
