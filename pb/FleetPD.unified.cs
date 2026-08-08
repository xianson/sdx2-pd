// FleetPD — SDX2 fleet point defence, single-paste build.
// https://github.com/xianson/sdx2-pd    (docs/DOCTRINE.md for the reasoning)
//
// Paste the WHOLE file into a Programmable Block and recompile. Nothing to configure.
// Requires WeaponCore (CoreSystems) in the world.
//
// The WcPbApi class at the bottom is WeaponCore's own published PB API shim by
// Ash-LikeSnow, included verbatim so this is a single paste:
// https://github.com/Ash-LikeSnow/WeaponCore

// ============================================================================
//  FLEET POINT DEFENCE  —  "descend on in-flight commitment"
//  Paste into a Programmable Block, append the WcPbApi class, recompile.
//  No configuration. Put one on every hull; they find each other over IGC.
//
//  ARGUMENTS (default behaviour needs none -- it just runs the optimal net):
//    debug    toggle diagnostics: per-mount Echo panel + a per-wave CustomData log.
//             OFF by default, because the panel and the block re-count that powers
//             leak estimation both cost work the fight does not need.
//    vanilla  passive control: full range, no ladder, stats still recorded to their own
//             totals. 'active' resumes, 'toggle' flips. The in-game control for the
//             simulator's `no PB` baseline.
//             Toggling it on also forces a weapon rescan and an immediate IGC poll,
//             so it is the only diagnostic argument there is.
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
// Floor the ladder sits ON, not merely clamps to. Raise it if your mounts have a
// large MinTargetDistance -- WeaponCore enforces one per weapon and it is not
// readable from a PB. SDX2's flak is 1000 m, but flak is exempted by the RPM check
// long before this matters.
const double RANGE_FLOOR_M  = 400.0;
const double MIN_RPM        = 100.0;  // below this, leave the mount ALONE
const double RPM_SAMPLE_S   = 8.0;    // observation window for measured rate
const double RESCAN_S       = 30.0;   // pick up built/repaired/destroyed mounts
// Diagnostics are OPT-IN: run the PB with the argument 'debug' to toggle them.
// Default is the optimal net with no panel, no CustomData writes, and no block
// re-count, so the normal path costs only what fighting requires.
const double LOG_EVERY_S    = 10.0;   // CustomData refresh interval
const double DAMAGE_POLL_S  = 1.0;    // how often to re-count blocks (damage sensor)
const double LEAK_RANGE_M   = 250.0;  // target seen closer than this => scored a leak
const double BAND_STALE_S   = 1.5;    // ignore a band report older than this
const double HIT_FRAC       = 0.92;   // ended inside this fraction of reach => hit
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
readonly Dictionary<long, int> Peers = new Dictionary<long, int>();      // gridId -> age in runs
readonly Dictionary<long, int> PeerInbound = new Dictionary<long, int>(); // gridId -> its inbound
readonly Dictionary<long, bool> PeerQueryable = new Dictionary<long, bool>(); // API said Item1
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
    public double AppliedRange = -1.0;   // last value actually pushed
    public int    Descents;              // diagnostics
    public int    _idx;                  // stable display index
    public int    Band = -1;             // last TargetRanged* seen (17..20)
    public double BandAt = -1.0;         // when it was reported
    public double BandRangeM = -1.0;     // upper bound in metres implied by it
}

readonly List<Mount> Mounts = new List<Mount>();
// Learned per-block state, keyed by EntityId and preserved across rescans. Without this
// a rescan builds fresh Mounts and WIPES the measured rate of fire, so a slow mount is
// un-exempted and harmfully laddered for the next sample window every single rescan.
class Learned { public double Rpm; public bool Exempt; public double BaseRange; }
readonly Dictionary<long, Learned> Memory = new Dictionary<long, Learned>();
readonly Dictionary<long, Mount> ById = new Dictionary<long, Mount>();
readonly List<IMyTerminalBlock> _blocks = new List<IMyTerminalBlock>();
readonly List<IMyTerminalBlock> _allBlocks = new List<IMyTerminalBlock>();
readonly Dictionary<string, int> _map = new Dictionary<string, int>();

double Now;
double RescanDue;
int    RangeWrites;
int    WaveCount;
int    TotalSpawns;
// ---- wave statistics.
// LEAK DETECTION IS AN ESTIMATE, and the log says so. No API reports "a torpedo hit us":
// WeaponCore's event monitor exposes only weapon-state triggers (Firing, Reloading,
// Overheated, TargetRanged*), and GetProjectilesLockedOn returns a bare count. So the
// script correlates two signals:
//     inbound count FALLS      -> that many torpedoes ended, by kill or by arrival
//     grid block count FALLS   -> we took damage
// Endings that coincide with damage are attributed to leaks; the rest are counted kills.
// A leaker that destroys nothing is undercounted; splash that kills a block without a
// full arrival is overcounted. A good signal, not ground truth.
int    PrevInbound;
int    PendingDrops;
int    BlockCount = -1;
double DamagePollDue;
int    TotKills, TotLeaks, TotBlocks, TotFired;
int    LeakRng, LeakDmg, PeakInbound;
double ClosestEver = -1.0;
double LastDropAt;
double LogDue;
// Round-level efficiency. Keyed by projectile id; entries are removed on the end
// callback, so the dictionary is bounded by rounds currently in the air.
struct Shot { public Vector3D P; public double T; public double Reach; }
readonly Dictionary<ulong, Shot> Airborne = new Dictionary<ulong, Shot>();
int    ShotHits, ShotFlyouts;
double ShotFlightSum;
double OrphanEst;
// VANILLA MODE. Passive: mounts stay at full range and never descend, but every
// statistic is still recorded. Toggle with the 'vanilla' / 'active' argument. Totals are
// kept per mode so the log compares the two directly -- the in-game control for the
// simulator's `no PB` row.
bool Vanilla;
bool Debug;
int  VKills, VLeaks, VBlocks, VFired, VWaves;
readonly List<IMyTerminalBlock> _dmgScan = new List<IMyTerminalBlock>();

int    IgcSent;
int    IgcRecv;
int    IgcBadPayload;
int    PeersEverSeen;
double LastPeerHeard = -1.0;
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
    Vanilla = Storage != null && Storage.Contains("vanilla");
    Debug = Storage != null && Storage.Contains("debug");
    if (Ready) Discover();
}

// ------------------------------------------------------------------- IGC
// Each hull announces only its grid id. Everything else is derived locally, so
// there is no protocol to version and nothing to desynchronise.
void Gossip() {
    while (Igc.HasPendingMessage) {
        var msg = Igc.AcceptMessage();
        IgcRecv++;
        if (!(msg.Data is long)) { IgcBadPayload++; continue; }
        long id = (long)msg.Data;
        if (id == Me.CubeGrid.EntityId) continue;      // our own broadcast echoing back
        if (!Peers.ContainsKey(id)) PeersEverSeen++;
        Peers[id] = 0;
        LastPeerHeard = Now;
    }
    IGC.SendBroadcastMessage(IGC_TAG, Me.CubeGrid.EntityId);
    IgcSent++;

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
    PeerInbound.Clear();
    PeerQueryable.Clear();
    for (int i = 0; i < PeerIds.Count; i++) {
        long id = PeerIds[i];
        var t = Wc.GetProjectilesLockedOn(id);
        PeerQueryable[id] = t.Item1;
        PeerInbound[id] = t.Item1 ? t.Item2 : -1;
        if (t.Item1 && t.Item2 > best) best = t.Item2;
    }
    return best;
}

// ---------------------------------------------------------------- discovery
int _rejNotReady, _rejShortRange, _rejNoMap, _rejNotCore, _seenBlocks;

void Discover() {
    _rejNotReady = _rejShortRange = _rejNoMap = _rejNotCore = _seenBlocks = 0;
    foreach (var m in Mounts) {
        if (!Alive(m.Blk)) continue;          // never touch a closed block
        foreach (var pid in m.Parts)
            Wc.UnMonitorProjectileCallback(m.Blk, pid, OnProjectile);
    }
    Mounts.Clear();
    ById.Clear();
    _blocks.Clear();
    // NOTE SDX2 PDCs are ConveyorSorter subtypes, so the scan must be over
    // IMyTerminalBlock generally rather than any turret interface.
    _allBlocks.Clear();
    GridTerminalSystem.GetBlocksOfType(_allBlocks, b => Alive(b) && b.IsSameConstructAs(Me));
    foreach (var b in _allBlocks) {
        if (Wc.HasCoreWeapon(b)) _blocks.Add(b); else _rejNotCore++;
    }

    int spread = 0;
    foreach (var b in _blocks) {
        _map.Clear();
        _seenBlocks++;
        if (!Wc.GetBlockWeaponMap(b, _map) || _map.Count == 0) { _rejNoMap++; continue; }

        // ---- BASE RANGE. This needs care, and getting it wrong was a real bug.
        //
        // GetMaxWeaponRange does NOT return the hardpoint maximum. It returns
        // Weapon.MaxTargetDistance, which WeaponState.cs:179 computes as
        //     Math.Min(Set.Range, Math.Min(hardPointMax, ammoMax))
        // i.e. it TRACKS THE CURRENT TRACKING-RANGE SETTING. Re-reading it after this
        // script has narrowed a gate returns our own narrowed value, so each rescan
        // ratcheted the base down: 3000 -> 840 -> 235 -> floor. Once it fell under the
        // 500 m sanity filter the weapon was rejected outright and the script reported
        // "no weapons found".
        //
        // Fix: PROBE for the true maximum. SetBlockTrackingRange clamps the request to
        // min(hardPointMax, ammoMax) at ApiBackend.cs:1201, so asking for an absurd
        // value and reading it back yields the real ceiling. Done once per block and
        // remembered, so it also survives a player having lowered the slider by hand.
        double baseRange = 0.0;
        Learned known;
        if (Memory.TryGetValue(b.EntityId, out known) && known.BaseRange > 0.0) {
            baseRange = known.BaseRange;
        } else {
            Wc.SetBlockTrackingRange(b, 1e9f);          // clamped by WC to the true max
            foreach (var kv in _map) {
                float r = Wc.GetMaxWeaponRange(b, kv.Value);
                if (r > baseRange) baseRange = r;
            }
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
        Learned mem;
        if (!Memory.TryGetValue(b.EntityId, out mem)) { mem = new Learned(); Memory[b.EntityId] = mem; }
        mem.BaseRange = baseRange;
        mt.Rpm = mem.Rpm;
        mt.Exempt = mem.Exempt;
        mt._idx = Mounts.Count;
        Mounts.Add(mt);
        ById[b.EntityId] = mt;

        // Exact in-flight accounting. The callback fires with start=true at
        // spawn (Projectile.cs:352) and start=false at end of life
        // (ProjectileTypes.cs:120), so a running count is exact rather than
        // estimated. Register on every part of the block.
        foreach (var kv in _map) {
            mt.Parts.Add(kv.Value);
            Wc.MonitorProjectileCallback(b, kv.Value, OnProjectile);
            Wc.MonitorEvents(b, kv.Value, OnWeaponEvent);
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

// TargetRanged* band report. The callback carries no block identity, so the band is
// applied to whichever mounts are currently engaging -- coarse, but the aggregate
// minimum is what the leak rule uses and that is dominated by the closest mount anyway.
void OnWeaponEvent(int state, bool active) {
    if (!active || state < 17 || state > 20) return;
    // 17 -> <=100%, 18 -> <=75%, 19 -> <=50%, 20 -> <=25% of that mount's current gate
    double frac = state == 17 ? 1.00 : state == 18 ? 0.75 : state == 19 ? 0.50 : 0.25;
    for (int i = 0; i < Mounts.Count; i++) {
        var m = Mounts[i];
        if (!Alive(m.Blk)) continue;
        double r = m.AppliedRange > 0 ? m.AppliedRange * frac : 0.0;  // bands are of the CURRENT gate
        if (r <= 0) continue;
        m.Band = state;
        m.BandAt = Now;
        m.BandRangeM = r;
    }
}

// Closest target range implied by any fresh band report, or -1 if nothing recent.
double ClosestSeen() {
    double best = -1.0;
    for (int i = 0; i < Mounts.Count; i++) {
        var m = Mounts[i];
        if (m.BandAt < 0 || Now - m.BandAt > BAND_STALE_S) continue;
        if (best < 0 || m.BandRangeM < best) best = m.BandRangeM;
    }
    return best;
}

void OnProjectile(long coreEnt, int partId, ulong projId, long targetId,
                  Vector3D pos, bool start) {
    Mount m;
    if (!ById.TryGetValue(coreEnt, out m)) return;
    // NO targetId FILTER. It used to skip anything whose Target.TargetId was not the
    // -1 projectile sentinel, which rejected every round and silently zeroed the stats.
    if (start) {
        m.InFlight++;
        m.Spawns++;
        TotalSpawns++;
        if (Debug) {
            var sh = new Shot();
            sh.P = pos;
            sh.T = Now;
            sh.Reach = m.BaseRange;
            Airborne[projId] = sh;
        }
        return;
    }
    if (m.InFlight > 0) m.InFlight--;
    if (!Debug) return;
    Shot rec;
    if (!Airborne.TryGetValue(projId, out rec)) return;
    Airborne.Remove(projId);
    double flew = Vector3D.Distance(rec.P, pos);
    double dt = Now - rec.T;
    ShotFlightSum += dt;
    // Short flight => it ran into its target. Full reach => it hit nothing.
    if (rec.Reach > 0 && flew < rec.Reach * HIT_FRAC) {
        ShotHits++;
    } else {
        ShotFlyouts++;
    }
}

// ------------------------------------------------------------------- main
public void Main(string arg, UpdateType src) {
    if (!Ready) {
        Wc = new WcPbApi();
        try { Ready = Wc.Activate(Me); } catch { Ready = false; }
        if (!Ready) { Echo("WeaponCore PB API unavailable."); return; }
        Discover();
    }
    if (arg == "vanilla" || arg == "active" || arg == "toggle") {
        Vanilla = arg == "toggle" ? !Vanilla : arg == "vanilla";
        SaveFlags();
        // Close any wave in progress so its stats are not split across two modes.
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            m.Rung = 0;
            SetRange(m, m.BaseRange);
        }
        Echo("mode -> " + (Vanilla ? "VANILLA (passive control)" : "ACTIVE"));
        return;
    }
    if (arg == "debug") {
        // One diagnostic argument. Toggling it on also forces a weapon rescan and an
        // immediate IGC poll and write, so there is nothing else to remember.
        Debug = !Debug;
        SaveFlags();
        if (!Debug) { Me.CustomData = ""; Echo("debug -> OFF"); return; }
        Discover();
        Gossip();
        Inbound = FleetInbound();
        LogDue = 0.0;
        WriteLog();
        Report();
        return;
    }
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
    // ---- damage sensor. Counting blocks is O(n), so it is sampled rather than polled.
    int lostNow = 0;
    if (Debug && Now >= DamagePollDue) {
        DamagePollDue = Now + DAMAGE_POLL_S;
        _dmgScan.Clear();
        GridTerminalSystem.GetBlocks(_dmgScan);
        int n = _dmgScan.Count;
        if (BlockCount >= 0 && n < BlockCount) lostNow = BlockCount - n;
        BlockCount = n;
    }

    // ---- inbound delta: a fall means that many torpedoes ended, somehow.
    if (Inbound < PrevInbound) {
        int died = PrevInbound - Inbound;
        PendingDrops += died;
        LastDropAt = Now;
        // Orphaned-round estimate: of everything airborne right now, the share committed
        // to the torpedoes that just died is about died / (live before they died).
        if (Debug && PrevInbound > 0) {
            int air = 0;
            for (int i = 0; i < Mounts.Count; i++) air += Mounts[i].InFlight;
            double orph = air * ((double)died / PrevInbound);
            OrphanEst += orph;
        }
    }
    PrevInbound = Inbound;

    if (Inbound > PeakInbound) PeakInbound = Inbound;

    // RANGE-INFERRED LEAKS. Works with damage disabled, which the block sensor cannot.
    // If a mount reported its target inside LEAK_RANGE_M in the last moment, endings
    // recorded now are scored leaks rather than kills.
    double near = ClosestSeen();
    if (near >= 0.0 && (ClosestEver < 0.0 || near < ClosestEver)) ClosestEver = near;
    if (PendingDrops > 0 && near >= 0.0 && near <= LEAK_RANGE_M) {
        if (Vanilla) VLeaks += PendingDrops; else TotLeaks += PendingDrops;
        LeakRng += PendingDrops;
        PendingDrops = 0;
    }
    if (lostNow > 0) {
        TotBlocks += lostNow;
        int leak = PendingDrops < lostNow ? PendingDrops : lostNow;
        if (leak > 0) {
            if (Vanilla) VLeaks += leak; else TotLeaks += leak;
            LeakDmg += leak;
            PendingDrops -= leak;
        }
    }
    // Endings with nothing close and no damage are kills. Resolved on a short delay so a
    // band report has a chance to arrive first.
    if (PendingDrops > 0 && Now - LastDropAt > 0.75) {
        if (Vanilla) VKills += PendingDrops; else TotKills += PendingDrops;
        PendingDrops = 0;
    }

    // IDLE HANDLING — this is load-bearing and its absence is a real defect.
    // The ladder only has a job while torpedoes are inbound. Holding the spread while
    // idle leaves some mounts gated to 0.28x of their range (a few hundred metres), so
    // they will not engage distant fighters, grids or anything else. That looks exactly
    // like "the PDCs are broken". While nothing is inbound every mount goes to FULL
    // range; the opening spread is applied on the 0 -> N transition instead, which is
    // also where the measured policy applies it.
    if (Inbound <= 0) {
        ZeroRuns++;
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            if (m.Rung != 0) { m.Rung = 0; m.LastDescend = -99.0; }
            SetRange(m, m.BaseRange);
        }
        if (Debug && Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }
    if (Debug) Report(); else Status();
        return;                       // nothing else to do until a threat appears
    }
    if (ZeroRuns >= WAVE_GAP_TICKS) {   // a fresh engagement: reset the opening spread
        Respread();
        WaveCount++;
    }
    ZeroRuns = 0;

    // Drop dead mounts and rescan if any went away. Cheap: reference checks only.
    bool lost = false;
    for (int i = Mounts.Count - 1; i >= 0; i--) {
        if (!Alive(Mounts[i].Blk)) { ById.Remove(Mounts[i].Id); Mounts.RemoveAt(i); lost = true; }
    }
    if (lost) RescanDue = 0.0;
    // Periodic rescan also picks up newly built or repaired mounts.
    if (Now >= RescanDue) { RescanDue = Now + RESCAN_S; Discover(); }

    if (Vanilla) {
        // Passive control: full range on everything, no ladder, but keep logging.
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            if (m.Rung != 0) m.Rung = 0;
            SetRange(m, m.BaseRange);
        }
        if (Debug && Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }
    if (Debug) Report(); else Status();
        return;
    }

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
            if (m.Rpm > 0.0) {
                m.Exempt = m.Rpm < MIN_RPM;
                Learned mem;
                if (!Memory.TryGetValue(m.Id, out mem)) { mem = new Learned(); Memory[m.Id] = mem; }
                mem.Rpm = m.Rpm; mem.Exempt = m.Exempt;
            }
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
            m.Descents++;
        }
        SetRange(m, RungRange(m, m.Rung));
        // Fire is NEVER toggled. Every withholding policy tested lost.
    }

    if (Debug && Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }
    if (Debug) Report(); else Status();
}

// Single choke point for range changes, so the diagnostics can count them and we never
// spam an unchanged value.
// Rungs span FLOOR..base, so even the bottom rung keeps clear air above the weapon's
// minimum engagement range instead of crowding it.
double RungRange(Mount m, int rung) {
    double span = m.BaseRange - RANGE_FLOOR_M;
    if (span <= 0.0) return m.BaseRange;          // very short-ranged mount: leave it alone
    return RANGE_FLOOR_M + span * RUNGS[rung];
}

void SetRange(Mount m, double r) {
    if (Math.Abs(r - m.AppliedRange) < 0.5) return;
    m.AppliedRange = r;
    RangeWrites++;
    Wc.SetBlockTrackingRange(m.Blk, (float)r);
}

void WriteLog() {
    var sb = new StringBuilder();
    sb.Append("FleetPD   grid=").Append(Me.CubeGrid.EntityId % 1000000L)
      .Append("   hull ").Append(HullOrdinal + 1).Append('/').Append(HullCount)
      .Append("   mounts=").Append(Mounts.Count)
      .Append("   uptime=").Append(Now.ToString("0")).Append('s')
      .Append(Vanilla ? "   [VANILLA]" : "   [ACTIVE]").AppendLine();
    sb.Append("inbound now=").Append(Inbound)
      .Append("   peak=").Append(PeakInbound)
      .Append("   engagements=").Append(WaveCount).AppendLine();
    sb.AppendLine();

    int res = ShotHits + ShotFlyouts;
    sb.AppendLine("ROUNDS");
    sb.Append("  fired      ").Append(TotalSpawns).AppendLine();
    sb.Append("  resolved   ").Append(res).AppendLine();
    sb.Append("  hit        ").Append(ShotHits).Append("   ").Append(Pct(ShotHits, res)).AppendLine();
    sb.Append("  flyout     ").Append(ShotFlyouts).Append("   ").Append(Pct(ShotFlyouts, res)).AppendLine();
    sb.Append("  orphan~    ").Append((int)OrphanEst)
      .Append("   (of the flyouts: target died mid-flight)").AppendLine();
    if (res > 0)
        sb.Append("  meanToF    ").Append((ShotFlightSum / res).ToString("0.00")).Append('s').AppendLine();
    sb.AppendLine();

    sb.AppendLine("INTERCEPTS   (estimated - nothing reports being hit)");
    sb.Append("  kill~      ").Append(TotKills + VKills).AppendLine();
    sb.Append("  leak~      ").Append(TotLeaks + VLeaks)
      .Append("   byRange=").Append(LeakRng).Append(" byDamage=").Append(LeakDmg).AppendLine();
    int tot = TotKills + VKills + TotLeaks + VLeaks;
    if (tot > 0)
        sb.Append("  intercept  ")
          .Append((100.0 * (TotKills + VKills) / tot).ToString("0.0")).Append('%').AppendLine();
    if (ClosestEver >= 0)
        sb.Append("  closest    ").Append((int)ClosestEver).Append('m').AppendLine();
    sb.Append("  blocksLost ").Append(TotBlocks).AppendLine();
    sb.AppendLine();

    sb.AppendLine("mode      kill~  leak~   fired  r/kill~  intercept");
    AppendTotals(sb, "ACTIVE", TotKills, TotLeaks, TotFired);
    AppendTotals(sb, "VANILLA", VKills, VLeaks, VFired);
    sb.AppendLine();
    sb.AppendLine("A fall in the inbound count is scored a LEAK if a mount reported its");
    sb.AppendLine("target inside " + LEAK_RANGE_M.ToString("0") + "m just beforehand (WeaponCore TargetRanged");
    sb.AppendLine("bands), or if blocks were lost at that moment; otherwise a kill.");
    sb.AppendLine("hit = round ended short of its reach. flyout = ran its full reach.");
    sb.AppendLine("'vanilla' collects a passive control; 'active' resumes.");
    Me.CustomData = sb.ToString();
}

string Pct(int a, int b) {
    return b > 0 ? (100.0 * a / b).ToString("0") + "%" : "-";
}

void AppendTotals(StringBuilder sb, string label, int k, int l, int f) {
    sb.Append(label.PadRight(9))
      .Append(k.ToString().PadLeft(7))
      .Append(l.ToString().PadLeft(7))
      .Append(f.ToString().PadLeft(8))
      .Append((k > 0 ? ((double)f / k).ToString("0.0") : "-").PadLeft(9))
      .Append((k + l > 0 ? (100.0 * k / (k + l)).ToString("0.0") + "%" : "-").PadLeft(11))
      .AppendLine();
}

void Respread() {
    foreach (var m in Mounts) {
        m.Rung = m.OpeningRung;
        m.LastDescend = -99.0;
        // InFlight is not touched: the monitor owns it, and rounds still in the
        // air are real regardless of wave bookkeeping.
    }
}

// Non-debug output: one line, so the block is visibly alive without doing any work.
void Status() {
    Echo("FleetPD " + (Vanilla ? "[VANILLA] " : "") + Mounts.Count + " mounts, "
         + Inbound + " inbound, hull " + (HullOrdinal + 1) + "/" + HullCount
         + (Mounts.Count == 0 ? "  -- no weapons, run 'debug'" : "")
         + "\n'debug' for diagnostics");
}

void SaveFlags() {
    Storage = (Vanilla ? "vanilla " : "") + (Debug ? "debug" : "");
}

void Report() {
    var sb = new StringBuilder();
    sb.Append(Vanilla ? "== FleetPD [VANILLA CONTROL] ==  t=" : "== FleetPD ==  t=").Append(Now.ToString("0")).Append("s  hull ")
      .Append(HullOrdinal + 1).Append('/').Append(HullCount).AppendLine();

    // ---- discovery, with the reason for every rejection. Silent filters were what
    // made "no weapons found" impossible to diagnose in the first place.
    sb.Append("scan: ").Append(_seenBlocks).Append(" core blocks -> ")
      .Append(Mounts.Count).Append(" usable").AppendLine();
    if (_rejNotCore + _rejNoMap + _rejNotReady + _rejShortRange > 0) {
        sb.Append("  rejected: ");
        if (_rejNotCore > 0) sb.Append("notCoreWeapon=").Append(_rejNotCore).Append(' ');
        if (_rejNoMap > 0) sb.Append("noWeaponMap=").Append(_rejNoMap).Append(' ');
        if (_rejNotReady > 0) sb.Append("wcNotReady(retry)=").Append(_rejNotReady).Append(' ');
        if (_rejShortRange > 0) sb.Append("range<500=").Append(_rejShortRange);
        sb.AppendLine();
    }
    if (Mounts.Count == 0) {
        sb.AppendLine("NO USABLE WEAPONS.");
        sb.AppendLine("  wcNotReady is normal for a few seconds after load/recompile.");
        sb.AppendLine("  notCoreWeapon on everything => WeaponCore API not talking.");
        sb.Append("  run with argument 'rescan' to force a re-scan.");
        Echo(sb.ToString());
        return;
    }

    // ---- engagement state
    int air = 0, ex = 0, desc = 0;
    double minR = double.MaxValue, maxR = 0.0;
    var rungs = new int[RUNG_COUNT];
    foreach (var m in Mounts) {
        air += m.InFlight;
        desc += m.Descents;
        if (m.Exempt) ex++;
        rungs[m.Rung]++;
        if (m.AppliedRange < minR) minR = m.AppliedRange;
        if (m.AppliedRange > maxR) maxR = m.AppliedRange;
    }
    sb.Append(Inbound > 0 ? "ENGAGED" : "idle   ")
      .Append("  inbound(fleet)=").Append(Inbound)
      .Append("  waves=").Append(WaveCount)
      .Append("  quietRuns=").Append(ZeroRuns).AppendLine();
    sb.Append("own rounds airborne=").Append(air)
      .Append("  (descend at >=").Append(K_INFLIGHT).Append(")")
      .Append("  spawnsSeen=").Append(TotalSpawns).AppendLine();
    sb.Append("rungs far->near: ");
    for (int i = 0; i < RUNG_COUNT; i++) { sb.Append(rungs[i]); if (i < RUNG_COUNT - 1) sb.Append('/'); }
    sb.Append("   descents=").Append(desc).Append("  rangeWrites=").Append(RangeWrites).AppendLine();
    sb.Append("range applied ").Append(((int)minR).ToString()).Append("..")
      .Append(((int)maxR).ToString()).Append(" m");
    if (ex > 0) sb.Append("   exempt(<").Append((int)MIN_RPM).Append("rpm)=").Append(ex);
    sb.AppendLine();

    // ---- per-mount detail. Capped so a big battery cannot blow the 8k Echo limit.
    sb.AppendLine("  #  rung   range   air   rpm  st");
    int shown = 0;
    foreach (var m in Mounts) {
        if (shown++ >= 12) { sb.Append("  ... +").Append(Mounts.Count - 12).Append(" more"); break; }
        sb.Append("  ").Append(m._idx.ToString().PadLeft(2))
          .Append(m.Rung.ToString().PadLeft(6))
          .Append(((int)m.AppliedRange).ToString().PadLeft(8))
          .Append(m.InFlight.ToString().PadLeft(6))
          .Append(((int)m.Rpm).ToString().PadLeft(6))
          .Append("  ").Append(m.Exempt ? "EX" : (Alive(m.Blk) ? "ok" : "DEAD"))
          .AppendLine();
    }
    // ---- IGC / fleet net. `me` is this grid; every other row is a peer heard over
    // IGC. `inb` is what GetProjectilesLockedOn reports for THAT grid, which is the
    // whole point of the net: a consort has 0 locked onto itself while the lead is
    // saturated, so without peers an escort never sees an engagement at all.
    sb.Append("-- IGC net --  ordinal ").Append(HullOrdinal + 1).Append('/').Append(HullCount)
      .Append("  sent=").Append(IgcSent).Append(" recv=").Append(IgcRecv);
    if (IgcBadPayload > 0) sb.Append(" badPayload=").Append(IgcBadPayload);
    sb.AppendLine();
    sb.Append("  grid            age  inb").AppendLine();
    for (int i = 0; i < PeerIds.Count; i++) {
        long id = PeerIds[i];
        bool self = id == Me.CubeGrid.EntityId;
        int age;
        int inb;
        bool q;
        if (!Peers.TryGetValue(id, out age)) age = 0;
        if (!PeerInbound.TryGetValue(id, out inb)) inb = -1;
        if (!PeerQueryable.TryGetValue(id, out q)) q = false;
        sb.Append("  ").Append((id % 1000000L).ToString().PadLeft(7))
          .Append(self ? " (me)  " : "       ")
          .Append(self ? "  -" : age.ToString().PadLeft(3))
          .Append(q ? inb.ToString().PadLeft(5) : "  n/a")
          .AppendLine();
    }
    if (HullCount == 1) {
        sb.AppendLine("  SOLO: no peers heard. Escorts cannot see the lead's inbound");
        sb.AppendLine("  count without the net, so they will not engage.");
    } else if (LastPeerHeard >= 0.0 && Now - LastPeerHeard > 5.0) {
        sb.Append("  WARNING: no peer traffic for ")
          .Append((Now - LastPeerHeard).ToString("0")).Append("s (net dropping?)").AppendLine();
    }
    if (WaveCount > 0 || Inbound > 0) {
        sb.Append("-- stats --  kill~=").Append(TotKills).Append(" leak~=").Append(TotLeaks);
        if (TotKills + TotLeaks > 0)
            sb.Append(" intercept=")
              .Append((100.0 * TotKills / (TotKills + TotLeaks)).ToString("0")).Append('%');
        sb.Append(" blocksLost=").Append(TotBlocks);
        int res2 = ShotHits + ShotFlyouts;
        if (res2 > 0)
            sb.Append("  hit=").Append(Pct(ShotHits, res2))
              .Append(" flyout=").Append(Pct(ShotFlyouts, res2))
              .Append(" orphan~=").Append((int)OrphanEst);
        sb.AppendLine();
    }
    sb.Append("peersEver=").Append(PeersEverSeen)
      .Append("  runtime=").Append(Runtime.LastRunTimeMs.ToString("0.00")).Append("ms");
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


public class WcPbApi
    {
        private Action<ICollection<MyDefinitionId>> _getCoreWeapons;
        private Action<ICollection<MyDefinitionId>> _getCoreStaticLaunchers;
        private Action<ICollection<MyDefinitionId>> _getCoreTurrets;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, IDictionary<string, int>, bool> _getBlockWeaponMap;
        private Func<long, MyTuple<bool, int, int>> _getProjectilesLockedOn;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, IDictionary<MyDetectedEntityInfo, float>> _getSortedThreats;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, IDictionary<long, MyDetectedEntityInfo>> _getSortedThreatsByID;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, ICollection<Sandbox.ModAPI.Ingame.MyDetectedEntityInfo>> _getObstructions;
        private Func<long, int, MyDetectedEntityInfo> _getAiFocus;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, int, bool> _setAiFocus;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, bool> _releaseAiFocus;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, MyDetectedEntityInfo> _getWeaponTarget;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, int> _setWeaponTarget;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, bool, int> _fireWeaponOnce;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, bool, bool, int> _toggleWeaponFire;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, bool, bool, bool> _isWeaponReadyToFire;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, float> _getMaxWeaponRange;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, ICollection<string>, int, bool> _getTurretTargetTypes;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, ICollection<string>, int> _setTurretTargetTypes;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, float> _setBlockTrackingRange;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, int, bool> _isTargetAligned;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, int, MyTuple<bool, Vector3D?>> _isTargetAlignedExtended;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, int, bool> _canShootTarget;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, int, Vector3D?> _getPredictedTargetPos;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, float> _getHeatLevel;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, float> _getWeaponHeatLevel;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, int> _getMaxWeaponHeatLevel;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, float> _currentPowerConsumption;
        private Func<MyDefinitionId, float> _getMaxPower;
        private Func<long, bool> _hasGridAi;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, bool> _hasCoreWeapon;
        private Func<long, float> _getOptimalDps;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, string> _getActiveAmmo;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, int> _getAmmoCount;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, string> _setActiveAmmo;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, Action<long, int, ulong, long, Vector3D, bool>> _monitorProjectile;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, Action<long, int, ulong, long, Vector3D, bool>> _unMonitorProjectile;
        private Func<ulong, MyTuple<Vector3D, Vector3D, float, float, long, string>> _getProjectileState;
        private Func<long, float> _getConstructEffectiveDps;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long> _getPlayerController;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, Matrix> _getWeaponAzimuthMatrix;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, Matrix> _getWeaponElevationMatrix;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, long, bool, bool, bool> _isTargetValid;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, MyTuple<Vector3D, Vector3D>> _getWeaponScope;
        private Func<Sandbox.ModAPI.Ingame.IMyTerminalBlock, MyTuple<bool, bool>> _isInRange;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, Action<int, bool>> _monitorEvents;
        private Action<Sandbox.ModAPI.Ingame.IMyTerminalBlock, int, Action<int, bool>> _unmonitorEvents;

        // Descriptions made by Aristeas, with Sigmund Froid's https://steamcommunity.com/sharedfiles/filedetails/?id=2178802013 as a reference.
        // PR accepted after prolific begging by Aryx
        
        /// <summary>
        /// Activates the WcPbAPI using <see cref="IMyTerminalBlock"/> <paramref name="pbBlock"/>.
        /// </summary>
        /// <remarks>
        /// Recommended to use 'Me' in <paramref name="pbBlock"/> for simplicity.
        /// </remarks>
        /// <param name="pbBlock"></param>
        /// <returns><see cref="true"/>  if all methods assigned correctly, <see cref="false"/>  otherwise</returns>
        /// <exception cref="Exception">Throws exception if WeaponCore is not present</exception>
        public bool Activate(Sandbox.ModAPI.Ingame.IMyTerminalBlock pbBlock)
        {
            var dict = pbBlock.GetProperty("WcPbAPI")?.As<IReadOnlyDictionary<string, Delegate>>().GetValue(pbBlock);
            if (dict == null) throw new Exception("WcPbAPI failed to activate");
            return ApiAssign(dict);
        }

        /// <summary>
        /// Bulk calls <see cref="AssignMethod" /> for all WcPbAPI methods.
        /// </summary>
        /// <remarks>
        /// Not useful for most scripts, but is public nonetheless.
        /// </remarks>
        /// <param name="delegates"></param>
        /// <returns><see cref="true"/>  if all methods assigned correctly, <see cref="false"/>  otherwise</returns>
        public bool ApiAssign(IReadOnlyDictionary<string, Delegate> delegates)
        {
            if (delegates == null)
                return false;

            AssignMethod(delegates, "GetCoreWeapons", ref _getCoreWeapons);
            AssignMethod(delegates, "GetCoreStaticLaunchers", ref _getCoreStaticLaunchers);
            AssignMethod(delegates, "GetCoreTurrets", ref _getCoreTurrets);
            AssignMethod(delegates, "GetBlockWeaponMap", ref _getBlockWeaponMap);
            AssignMethod(delegates, "GetProjectilesLockedOn", ref _getProjectilesLockedOn);
            AssignMethod(delegates, "GetSortedThreats", ref _getSortedThreats);
            AssignMethod(delegates, "GetSortedThreatsByID", ref _getSortedThreatsByID);
            AssignMethod(delegates, "GetObstructions", ref _getObstructions);
            AssignMethod(delegates, "GetAiFocus", ref _getAiFocus);
            AssignMethod(delegates, "SetAiFocus", ref _setAiFocus);
            AssignMethod(delegates, "ReleaseAiFocus", ref _releaseAiFocus);
            AssignMethod(delegates, "GetWeaponTarget", ref _getWeaponTarget);
            AssignMethod(delegates, "SetWeaponTarget", ref _setWeaponTarget);
            AssignMethod(delegates, "FireWeaponOnce", ref _fireWeaponOnce);
            AssignMethod(delegates, "ToggleWeaponFire", ref _toggleWeaponFire);
            AssignMethod(delegates, "IsWeaponReadyToFire", ref _isWeaponReadyToFire);
            AssignMethod(delegates, "GetMaxWeaponRange", ref _getMaxWeaponRange);
            AssignMethod(delegates, "GetTurretTargetTypes", ref _getTurretTargetTypes);
            AssignMethod(delegates, "SetTurretTargetTypes", ref _setTurretTargetTypes);
            AssignMethod(delegates, "SetBlockTrackingRange", ref _setBlockTrackingRange);
            AssignMethod(delegates, "IsTargetAligned", ref _isTargetAligned);
            AssignMethod(delegates, "IsTargetAlignedExtended", ref _isTargetAlignedExtended);
            AssignMethod(delegates, "CanShootTarget", ref _canShootTarget);
            AssignMethod(delegates, "GetPredictedTargetPosition", ref _getPredictedTargetPos);
            AssignMethod(delegates, "GetHeatLevel", ref _getHeatLevel);
            AssignMethod(delegates, "GetWeaponHeatLevel", ref _getWeaponHeatLevel);
            AssignMethod(delegates, "GetMaxWeaponHeatLevel", ref _getMaxWeaponHeatLevel);
            AssignMethod(delegates, "GetCurrentPower", ref _currentPowerConsumption);
            AssignMethod(delegates, "GetMaxPower", ref _getMaxPower);
            AssignMethod(delegates, "HasGridAi", ref _hasGridAi);
            AssignMethod(delegates, "HasCoreWeapon", ref _hasCoreWeapon);
            AssignMethod(delegates, "GetOptimalDps", ref _getOptimalDps);
            AssignMethod(delegates, "GetAmmoCount", ref _getAmmoCount);
            AssignMethod(delegates, "GetActiveAmmo", ref _getActiveAmmo);
            AssignMethod(delegates, "SetActiveAmmo", ref _setActiveAmmo);
            AssignMethod(delegates, "MonitorProjectile", ref _monitorProjectile);
            AssignMethod(delegates, "UnMonitorProjectile", ref _unMonitorProjectile);
            AssignMethod(delegates, "GetProjectileState", ref _getProjectileState);
            AssignMethod(delegates, "GetConstructEffectiveDps", ref _getConstructEffectiveDps);
            AssignMethod(delegates, "GetPlayerController", ref _getPlayerController);
            AssignMethod(delegates, "GetWeaponAzimuthMatrix", ref _getWeaponAzimuthMatrix);
            AssignMethod(delegates, "GetWeaponElevationMatrix", ref _getWeaponElevationMatrix);
            AssignMethod(delegates, "IsTargetValid", ref _isTargetValid);
            AssignMethod(delegates, "GetWeaponScope", ref _getWeaponScope);
            AssignMethod(delegates, "IsInRange", ref _isInRange);
            AssignMethod(delegates, "RegisterEventMonitor", ref _monitorEvents);
            AssignMethod(delegates, "UnRegisterEventMonitor", ref _unmonitorEvents);
            return true;
        }

        /// <summary>
        /// Links method <paramref name="field"/> to internal API method of name <paramref name="name"/>
        /// </summary>
        /// <remarks>
        /// Not useful for most scripts, but is public nonetheless.
        /// </remarks>
        /// <typeparam name="T"></typeparam>
        /// <param name="delegates"></param>
        /// <param name="name"></param>
        /// <param name="field"></param>
        /// <exception cref="Exception"></exception>
        private void AssignMethod<T>(IReadOnlyDictionary<string, Delegate> delegates, string name, ref T field) where T : class
        {
            if (delegates == null)
            {
                field = null;
                return;
            }

            Delegate del;
            if (!delegates.TryGetValue(name, out del))
                throw new Exception($"{GetType().Name} :: Couldn't find {name} delegate of type {typeof(T)}");

            field = del as T;
            if (field == null)
                throw new Exception(
                    $"{GetType().Name} :: Delegate {name} is not type {typeof(T)}, instead it's: {del.GetType()}");
        }

        /// <summary>
        /// Populates <paramref name="collection"/> with <see cref="MyDefinitionId"/> of all loaded WeaponCore weapons.
        /// </summary>
        /// <param name="collection"></param>
        /// <seealso cref="GetAllCoreStaticLaunchers"/>
        /// <seealso cref="GetAllCoreTurrets"/>
        public void GetAllCoreWeapons(ICollection<MyDefinitionId> collection) => _getCoreWeapons?.Invoke(collection);

        /// <summary>
        /// Populates <paramref name="collection"/> with <see cref="MyDefinitionId"/> of all loaded WeaponCore fixed weapons.
        /// </summary>
        /// <param name="collection"></param>
        /// <seealso cref="GetAllCoreWeapons"/>
        /// <seealso cref="GetAllCoreTurrets"/>
        public void GetAllCoreStaticLaunchers(ICollection<MyDefinitionId> collection) =>
            _getCoreStaticLaunchers?.Invoke(collection);

        /// <summary>
        /// Populates <paramref name="collection"/> with <see cref="MyDefinitionId"/> of all loaded WeaponCore turret weapons.
        /// </summary>
        /// <param name="collection"></param>
        /// <seealso cref="GetAllCoreWeapons"/>
        /// <seealso cref="GetAllCoreStaticLaunchers"/>
        public void GetAllCoreTurrets(ICollection<MyDefinitionId> collection) => _getCoreTurrets?.Invoke(collection);

        /// <summary>
        /// Populates <paramref name="collection"/> with <see cref="IDictionary{String, Int32}"/> of contents:
        /// <list type="bullet">
        /// <item>Key: Name of weapon.</item>
        /// <item>Value: ID of weapon within <paramref name="weaponBlock"/>.</item>
        /// </list>
        /// </summary>
        /// <param name="weaponBlock"></param>
        /// <param name="collection"></param>
        /// <returns></returns>
        public bool GetBlockWeaponMap(Sandbox.ModAPI.Ingame.IMyTerminalBlock weaponBlock, IDictionary<string, int> collection) =>
            _getBlockWeaponMap?.Invoke(weaponBlock, collection) ?? false;

        /// <summary>
        /// Returns a <see cref="MyTuple{bool, int, int}"/> containing information about projectiles targeting <paramref name="victim"/>.
        /// </summary>
        /// <param name="victim"></param>
        /// <returns>
        /// <see cref="MyTuple{bool, int, int}"/> with contents:
        /// <list type="number">
        /// <item><see cref="bool"/> Is being locked?</item>
        /// <item><see cref="int"/> Number of locked projectiles.</item>
        /// <item><see cref="int"/> Time (in ticks) locked.</item>
        /// </list>
        /// </returns>
        public MyTuple<bool, int, int> GetProjectilesLockedOn(long victim) =>
            _getProjectilesLockedOn?.Invoke(victim) ?? new MyTuple<bool, int, int>();

        /// <summary>
        /// Populates <paramref name="collection"/> with contents:
        /// <list type="bullet">
        /// <item>Key: Hostile <see cref="MyDetectedEntityInfo"/> within targeting range of <paramref name="pBlock"/>'s grid</item>
        /// <item>Value: Threat level of Key</item>
        /// </list>
        /// </summary>
        /// <param name="pBlock"></param>
        /// <param name="collection"></param>
        public void GetSortedThreats(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, IDictionary<MyDetectedEntityInfo, float> collection) =>
            _getSortedThreats?.Invoke(pBlock, collection);

        /// <summary>
        /// Populates <paramref name="collection"/> with contents:
        /// <list type="bullet">
        /// <item>Key: Entity ID</item>
        /// <item>Value: Hostile <see cref="MyDetectedEntityInfo"/> within targeting range of <paramref name="pBlock"/>'s grid</item>
        /// </list>
        /// </summary>
        /// <param name="pBlock"></param>
        /// <param name="collection"></param>
        public void GetSortedThreatsByID(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, IDictionary<long, MyDetectedEntityInfo> collection) =>
            _getSortedThreatsByID?.Invoke(pBlock, collection);

        /// <summary>
        /// Populates <paramref name="collection"/> with contents:
        /// <list type="bullet">
        /// <item>Friendly <see cref="MyDetectedEntityInfo"/> within targeting range of <paramref name="pBlock"/>'s <see cref="IMyCubeGrid"/></item>
        /// </list>
        /// </summary>
        /// <param name="pBlock"></param>
        /// <param name="collection"></param>
        public void GetObstructions(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, ICollection<Sandbox.ModAPI.Ingame.MyDetectedEntityInfo> collection) =>
            _getObstructions?.Invoke(pBlock, collection);

        /// <summary>
        /// Returns the GridAi Target with priority <paramref name="priority"/> of <see cref="IMyCubeGrid"/> with EntityID <paramref name="shooter"/>.
        /// </summary>
        /// <remarks>
        /// If the grid is valid but does not have a target, an empty <see cref="MyDetectedEntityInfo"/> is returned.
        /// <para>
        /// Default <paramref name="priority"/> = 0 returns the player-selected target.
        /// </para>
        /// </remarks>
        /// <param name="shooter"></param>
        /// <param name="priority"></param>
        /// <returns>Nullable <see cref="MyDetectedEntityInfo"/>. Null if <paramref name="shooter"/> does not exist or lacks GridAi.</returns>
        public MyDetectedEntityInfo? GetAiFocus(long shooter, int priority = 0) => _getAiFocus?.Invoke(shooter, priority);

        /// <summary>
        /// Sets the GridAi Target of <paramref name="pBlock"/>'s <see cref="IMyCubeGrid"/> to EntityID <paramref name="target"/>.
        /// </summary>
        /// <remarks>
        /// Default <paramref name="priority"/> = 0 sets the player-visible target.
        /// </remarks>
        /// <param name="pBlock"></param>
        /// <param name="target"></param>
        /// <param name="priority"></param>
        /// <returns><see cref="true"/>  if successful, <see cref="false"/>  otherwise.</returns>
        public bool SetAiFocus(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, long target, int priority = 0) =>
            _setAiFocus?.Invoke(pBlock, target, priority) ?? false;

        /// <summary>
        /// Unsets the GridAi Target of <paramref name="pBlock"/>'s <see cref="IMyCubeGrid"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="playerId"/> may be set to 0.
        /// </remarks>
        /// <param name="pBlock"></param>
        /// <param name="playerId"></param>
        /// <returns><see cref="true"/>  if successful, <see cref="false"/>  otherwise.</returns>
        public bool ReleaseAiFocus(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, long playerId) =>
            _releaseAiFocus?.Invoke(pBlock, playerId) ?? false;

        /// <summary>
        /// Returns the WeaponAi target of <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <remarks>
        /// Seems to always return null for static weapons.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns>Nullable <see cref="MyDetectedEntityInfo"/>.</returns>
        public MyDetectedEntityInfo? GetWeaponTarget(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId = 0) =>
            _getWeaponTarget?.Invoke(weapon, weaponId);

        /// <summary>
        /// Sets the WeaponAi target of <paramref name="weaponId"/> on <paramref name="weapon"/> to EntityID <paramref name="target"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="target"></param>
        /// <param name="weaponId"></param>
        public void SetWeaponTarget(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long target, int weaponId = 0) =>
            _setWeaponTarget?.Invoke(weapon, target, weaponId);

        /// <summary>
        /// (DEPRECATED, use ToggleWeaponFire) Fires <paramref name="weaponId"/> on <paramref name="weapon"/> once.
        /// </summary>
        /// <remarks>
        /// <paramref name="allWeapons"/> uses all weapons on <paramref name="weapon"/>.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="allWeapons"></param>
        /// <param name="weaponId"></param>
        public void FireWeaponOnce(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, bool allWeapons = true, int weaponId = 0) =>
            _fireWeaponOnce?.Invoke(weapon, allWeapons, weaponId);

        /// <summary>
        /// Sets the Shoot On/Off toggle of <paramref name="weaponId"/> on <paramref name="weapon"/> to <see cref="bool"/> <paramref name="on"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="allWeapons"/> uses all weapons on <paramref name="weapon"/>.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="on"></param>
        /// <param name="allWeapons"></param>
        /// <param name="weaponId"></param>
        public void ToggleWeaponFire(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, bool on, bool allWeapons, int weaponId = 0) =>
            _toggleWeaponFire?.Invoke(weapon, on, allWeapons, weaponId);

        /// <summary>
        /// Returns whether or not <paramref name="weaponId"/> on <paramref name="weapon"/> is ready to fire.
        /// </summary>
        /// <remarks>
        /// <paramref name="anyWeaponReady"/> uses all weapons on <paramref name="weapon"/>.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <param name="anyWeaponReady"></param>
        /// <param name="shootReady"></param>
        /// <returns><see cref="true"/> if ready to fire, <see cref="false"/> otherwise.</returns>
        public bool IsWeaponReadyToFire(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId = 0, bool anyWeaponReady = true,
            bool shootReady = false) =>
            _isWeaponReadyToFire?.Invoke(weapon, weaponId, anyWeaponReady, shootReady) ?? false;

        /// <summary>
        /// Returns the current Aiming Radius of <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="float"/> range in meters.</returns>
        public float GetMaxWeaponRange(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
            _getMaxWeaponRange?.Invoke(weapon, weaponId) ?? 0f;

        /// <summary>
        /// Populates <paramref name="collection"/> with contents:
        /// <list type="bullet">
        /// <item><see cref="string"/> Allowed target type name for <paramref name="weaponId"/> on <paramref name="weapon"/>.</item>
        /// </list>
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="collection"></param>
        /// <param name="weaponId"></param>
        /// <returns>true if <paramref name="weaponId"/> and <paramref name="weapon"/> are valid, false otherwise.</returns>
        public bool GetTurretTargetTypes(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, IList<string> collection, int weaponId = 0) =>
            _getTurretTargetTypes?.Invoke(weapon, collection, weaponId) ?? false;

        /// <summary>
        /// Sets allowed target types for <paramref name="weaponId"/> on <paramref name="weapon"/> to <paramref name="collection"/>.
        /// </summary>
        /// <remarks>
        /// Invalid target types are ignored.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="collection"></param>
        /// <param name="weaponId"></param>
        public void SetTurretTargetTypes(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, IList<string> collection, int weaponId = 0) =>
            _setTurretTargetTypes?.Invoke(weapon, collection, weaponId);

        /// <summary>
        /// Sets the current Aiming Range of <paramref name="weapon"/> to <paramref name="range"/>.
        /// </summary>
        /// <remarks>
        /// Values over the maximum possible Aiming Range of <paramref name="weapon"/> will set it to the maximum possible.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="range"></param>
        public void SetBlockTrackingRange(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, float range) =>
            _setBlockTrackingRange?.Invoke(weapon, range);

        /// <summary>
        /// Returns whether or not <paramref name="weaponId"/> on <paramref name="weapon"/> is aligned with EntityID <paramref name="targetEnt"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="targetEnt"></param>
        /// <param name="weaponId"></param>
        /// <returns>true if aligned and valid, false otherwise.</returns>
        public bool IsTargetAligned(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
            _isTargetAligned?.Invoke(weapon, targetEnt, weaponId) ?? false;

        /// <summary>
        /// Returns whether or not <paramref name="weaponId"/> on <paramref name="weapon"/> is aligned with EntityID <paramref name="targetEnt"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="targetEnt"></param>
        /// <param name="weaponId"></param>
        /// <returns>
        /// <see cref="MyTuple{bool, Vector3D}"/> with contents:
        /// <list type="number">
        /// <item><see cref="bool"/> Is aligned? False if invalid.</item>
        /// <item><see cref="Vector3D"/> Position of target. Null if invalid.</item>
        /// </list>
        /// </returns>
        public MyTuple<bool, Vector3D?> IsTargetAlignedExtended(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
            _isTargetAlignedExtended?.Invoke(weapon, targetEnt, weaponId) ?? new MyTuple<bool, Vector3D?>();

        /// <summary>
        /// Returns whether or not <paramref name="weaponId"/> on <paramref name="weapon"/> is aligned with EntityID <paramref name="targetEnt"/>.
        /// </summary>
        /// <remarks>
        /// Like <see cref="IsTargetAligned"/>, but takes target velocity and acceleration into account.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="targetEnt"></param>
        /// <param name="weaponId"></param>
        /// <returns>true if aligned and valid, false otherwise</returns>
        public bool CanShootTarget(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
            _canShootTarget?.Invoke(weapon, targetEnt, weaponId) ?? false;

        /// <summary>
        /// Returns the lead position of <paramref name="weaponId"/> on <paramref name="weapon"/>, with target EntityId <paramref name="targetEnt"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="targetEnt"></param>
        /// <param name="weaponId"></param>
        /// <returns>Nullable <see cref="Vector3D"/> target lead position. Null if target or weapon invalid.</returns>
        public Vector3D? GetPredictedTargetPosition(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
            _getPredictedTargetPos?.Invoke(weapon, targetEnt, weaponId) ?? null;

        /// <summary>
        /// Returns the heat level of <paramref name="weapon"/>.
        /// </summary>
        /// <remarks>
        /// If <paramref name="weapon"/> is invalid or does not have heat, returns 0f.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <returns><see cref="float"/>Total heat of all combined weapons.</returns>
        public float GetHeatLevel(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _getHeatLevel?.Invoke(weapon) ?? 0f;

        /// <summary>
        /// Returns the heat level of the weapon on the block <paramref name="weapon"/> with id <paramref name="weaponId"/>.
        /// </summary>
        /// <remarks>
        /// If the given weapon is invalid or does not have heat, returns -1f.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="float"/>Total heat of the weapon with weapon id <paramref name="weaponId"/> on block <paramref name="weapon"/></returns>
        public float GetWeaponHeatLevel(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) => _getWeaponHeatLevel?.Invoke(weapon, weaponId) ?? -1f;

        /// <summary>
        /// Returns the maximum heat level of the weapon on the block <paramref name="weapon"/> with id <paramref name="weaponId"/>.
        /// </summary>
        /// <remarks>
        /// If the given weapon is invalid or does not have heat, returns -1.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="float"/>Maximum heat of the weapon with weapon id <paramref name="weaponId"/> on block <paramref name="weapon"/>.</returns>
        public int GetMaxWeaponHeatLevel(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) => _getMaxWeaponHeatLevel?.Invoke(weapon, weaponId) ?? -1;

        /// <summary>
        /// Returns current power consumption of <paramref name="weapon"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <returns><see cref="float"/> Power in MW</returns>
        public float GetCurrentPower(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _currentPowerConsumption?.Invoke(weapon) ?? 0f;

        /// <summary>
        /// Returns maximum power consumption of <paramref name="weapon"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <returns><see cref="float"/> Power in MW</returns>
        public float GetMaxPower(MyDefinitionId weaponDef) => _getMaxPower?.Invoke(weaponDef) ?? 0f;

        /// <summary>
        /// Returns whether or not EntityId <paramref name="entity"/> has a GridAi.
        /// </summary>
        /// <param name="entity"></param>
        /// <returns>true if GridAi present, false otherwise.</returns>
        public bool HasGridAi(long entity) => _hasGridAi?.Invoke(entity) ?? false;

        /// <summary>
        /// Returns whether or not <see cref="IMyTerminalBlock"/> <paramref name="weapon"/> has a WeaponCore weapon.
        /// </summary>
        /// <param name="entity"></param>
        /// <returns>true if weapon present, false otherwise.</returns>
        public bool HasCoreWeapon(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _hasCoreWeapon?.Invoke(weapon) ?? false;

        /// <summary>
        /// Returns the total optimal DPS of <see cref="IMyCubeGrid"/> with EntityId <paramref name="entity"/>.
        /// </summary>
        /// <param name="entity"></param>
        /// <returns><see cref="float"/> DPS.</returns>
        public float GetOptimalDps(long entity) => _getOptimalDps?.Invoke(entity) ?? 0f;

        /// <summary>
        /// Returns the active ammo name of <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="string"/> AmmoName</returns>
        public string GetActiveAmmo(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
            _getActiveAmmo?.Invoke(weapon, weaponId) ?? null;

        /// <summary>
        /// Returns the current amount of ammo the weapon has internally (loaded, not inventory) <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="int"/> Current ammo </returns>
        public int GetAmmoCount(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
            _getAmmoCount?.Invoke(weapon, weaponId) ?? -1;

        /// <summary>
        /// Sets the active ammo name of <paramref name="weaponId"/> on <paramref name="weapon"/> to <see cref="string"/> <paramref name="ammoType"/>.
        /// </summary>
        /// <remarks>
        /// Does nothing if <paramref name="ammoType"/> is invalid.
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        public void SetActiveAmmo(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId, string ammoType) =>
            _setActiveAmmo?.Invoke(weapon, weaponId, ammoType);

        /// <summary>
        /// Assigns projectile callback <paramref name="action"/> to <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="action"/> has parameters:
        /// <list type="number">
        /// <item><see cref="long"/> Parent weapon EntityId?</item>
        /// <item><see cref="int"/> Parent weapon partId</item>
        /// <item><see cref="ulong"/> Projectile EntityId</item>
        /// <item><see cref="long"/> Target EntityId</item>
        /// <item><see cref="Vector3D"/> ProjectilePosition if active, LastHit if destroyed</item>
        /// <item><see cref="bool"/> ProjectileExists?</item>
        /// </list>
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <param name="action"></param>
        public void MonitorProjectileCallback(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId, Action<long, int, ulong, long, Vector3D, bool> action) =>
            _monitorProjectile?.Invoke(weapon, weaponId, action);

        /// <summary>
        /// Unassigns projectile callback <paramref name="action"/> to <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="action"/> has parameters:
        /// <list type="number">
        /// <item><see cref="long"/> Parent weapon EntityId?</item>
        /// <item><see cref="int"/> Parent weapon partId</item>
        /// <item><see cref="ulong"/> Projectile EntityId</item>
        /// <item><see cref="long"/> Target EntityId</item>
        /// <item><see cref="Vector3D"/> ProjectilePosition if active, LastHit if destroyed</item>
        /// <item><see cref="bool"/> ProjectileExists?</item>
        /// </list>
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <param name="action"></param>
        public void UnMonitorProjectileCallback(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId, Action<long, int, ulong, long, Vector3D, bool> action) =>
            _unMonitorProjectile?.Invoke(weapon, weaponId, action);

        /// <summary>
        /// Returns ProjectileState of <paramref name="projectileId"/>.
        /// </summary>
        /// <param name="projectileId"></param>
        /// <returns>
        /// <see cref="MyTuple{Vector3D, Vector3D, float, float, long, string}"/> with contents:
        /// <list type="number">
        /// <item><see cref="Vector3D"/> Position</item>
        /// <item><see cref="Vector3D"/> Velocity</item>
        /// <item><see cref="float"/> BaseDamagePool</item>
        /// <item><see cref="float"/> BaseHealthPool</item>
        /// <item><see cref="long"/> Target EntityId</item>
        /// <item><see cref="string"/> AmmoRound Name</item>
        /// </list>
        /// </returns>
        public MyTuple<Vector3D, Vector3D, float, float, long, string> GetProjectileState(ulong projectileId) =>
            _getProjectileState?.Invoke(projectileId) ?? new MyTuple<Vector3D, Vector3D, float, float, long, string>();

        /// <summary>
        /// Returns the total effective DPS of <see cref="IMyCubeGrid"/> with EntityId <paramref name="entity"/>.
        /// </summary>
        /// <param name="entity"></param>
        /// <returns><see cref="float"/> DPS.</returns>
        public float GetConstructEffectiveDps(long entity) => _getConstructEffectiveDps?.Invoke(entity) ?? 0f;

        /// <summary>
        /// Returns the Id of <paramref name="weapon"/>'s controlling player.
        /// </summary>
        /// <param name="weapon"></param>
        /// <returns><see cref="long"/> PlayerId. -1 if invalid or uncontrolled.</returns>
        public long GetPlayerController(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _getPlayerController?.Invoke(weapon) ?? -1;

        /// <summary>
        /// Returns the rotation matrix of <paramref name="weaponId"/> on <paramref name="weapon"/>'s azimuth part.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="Matrix"/> AzimuthMatrix</returns>
        public Matrix GetWeaponAzimuthMatrix(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
            _getWeaponAzimuthMatrix?.Invoke(weapon, weaponId) ?? Matrix.Zero;

        /// <summary>
        /// Returns the rotation matrix of <paramref name="weaponId"/> on <paramref name="weapon"/>'s elevation part.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns><see cref="Matrix"/> ElevationMatrix</returns>
        public Matrix GetWeaponElevationMatrix(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
            _getWeaponElevationMatrix?.Invoke(weapon, weaponId) ?? Matrix.Zero;

        /// <summary>
        /// Returns whether or not <paramref name="targetId"/> is a valid target for <paramref name="weapon"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="onlyThreats"/> will return false if <paramref name="targetId"/>'s threat score is zero.
        /// <para><paramref name="checkRelations"/> will return false if <paramref name="targetId"/> is non-hostile.</para>
        /// </remarks>
        /// <param name="weapon"></param>
        /// <param name="targetId"></param>
        /// <param name="onlyThreats"></param>
        /// <param name="checkRelations"></param>
        /// <returns></returns>
        public bool IsTargetValid(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetId, bool onlyThreats, bool checkRelations) =>
            _isTargetValid?.Invoke(weapon, targetId, onlyThreats, checkRelations) ?? false;

        /// <summary>
        /// Returns scope information of <paramref name="weaponId"/> on <paramref name="weapon"/>.
        /// </summary>
        /// <param name="weapon"></param>
        /// <param name="weaponId"></param>
        /// <returns>
        /// <see cref="MyTuple{Vector3D, Vector3D}"/> with contents:
        /// <list type="number">
        /// <item><see cref="Vector3D"/> Position</item>
        /// <item><see cref="Vector3D"/> Direction</item>
        /// </list>
        /// </returns>
        public MyTuple<Vector3D, Vector3D> GetWeaponScope(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
            _getWeaponScope?.Invoke(weapon, weaponId) ?? new MyTuple<Vector3D, Vector3D>();

        // terminalBlock, Threat, Other, Something 
        /// <summary>
        /// Returns whether or not <paramref name="block"/>'s <see cref="IMyCubeGrid"/>'s GridAi's PrimaryTarget is in range.
        /// </summary>
        /// <remarks>
        /// The second value in the returned <see cref="MyTuple"/> might be legacy from when players could select two targets.
        /// </remarks>
        /// <param name="block"></param>
        /// <returns>
        /// <see cref="MyTuple{bool, bool}"/> with contents:
        /// <list type="number">
        /// <item><see cref="bool"/> PrimaryTarget In Range?</item>
        /// <item><see cref="bool"/> OtherTarget In Range?</item>
        /// </list>
        /// </returns>
        public MyTuple<bool, bool> IsInRange(Sandbox.ModAPI.Ingame.IMyTerminalBlock block) =>
            _isInRange?.Invoke(block) ?? new MyTuple<bool, bool>();

        /// <summary>
        /// Adds event monitor <paramref name="action"/> to weapon <paramref name="partId"/> on <paramref name="entity"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="action"/> has parameters:
        /// <list type="number">
        /// <item><see cref="int"/> State</item>
        /// <item><see cref="bool"/> Active</item>
        /// </list>
        /// 
        /// <para>
        /// List of event triggers:<br/>
        /// 0  Reloading<br/>
        /// 1  Firing<br/>
        /// 2  Tracking<br/>
        /// 3  Overheated<br/>
        /// 4  TurnOn<br/>
        /// 5  TurnOff<br/>
        /// 6  BurstReload<br/>
        /// 7  NoMagsToLoad<br/>
        /// 8  PreFire<br/>
        /// 9  EmptyOnGameLoad<br/>
        /// 10 StopFiring<br/>
        /// 11 StopTracking<br/>
        /// 12 LockDelay<br/>
        /// 13 Init<br/>
        /// 14 Homing<br/>
        /// 15 TargetAligned<br/>
        /// 16 WhileOn<br/>
        /// 17 TargetRanged100<br/>
        /// 18 TargetRanged75<br/>
        /// 19 TargetRanged50<br/>
        /// 20 TargetRanged25
        /// </para>
        /// </remarks>
        /// <param name="entity"></param>
        /// <param name="partId"></param>
        /// <param name="action"></param>
        public void MonitorEvents(Sandbox.ModAPI.Ingame.IMyTerminalBlock entity, int partId, Action<int, bool> action) =>
            _monitorEvents?.Invoke(entity, partId, action);

        /// <summary>
        /// Removes event monitor <paramref name="action"/> from weapon <paramref name="partId"/> on <paramref name="entity"/>.
        /// </summary>
        /// <remarks>
        /// <paramref name="action"/> has parameters:
        /// <list type="number">
        /// <item><see cref="int"/> State</item>
        /// <item><see cref="bool"/> Active</item>
        /// </list>
        /// </remarks>
        /// <param name="entity"></param>
        /// <param name="partId"></param>
        /// <param name="action"></param>
        public void UnMonitorEvents(Sandbox.ModAPI.Ingame.IMyTerminalBlock entity, int partId, Action<int, bool> action) =>
            _unmonitorEvents?.Invoke(entity, partId, action);

    }
