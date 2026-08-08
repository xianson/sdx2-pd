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
//    rescan   force a weapon re-scan.
//    igc      force an IGC poll and print the net table now.
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
// Diagnostics are OPT-IN: run the PB with the argument 'debug' to toggle them.
// Default is the optimal net with no panel, no CustomData writes, and no block
// re-count, so the normal path costs only what fighting requires.
const int    LOG_WAVES      = 24;     // waves retained in the log ring
const double DAMAGE_POLL_S  = 1.0;    // how often to re-count blocks (damage sensor)
const double LEAK_RANGE_M   = 250.0;  // target seen closer than this => scored a leak
const double BAND_STALE_S   = 1.5;    // ignore a band report older than this
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
class Wave {
    public int    N, PeakIn, Ended, Kills, Leaks, BlocksLost, Fired, Descents;
    public double Start, Dur, PeakHeat;
    public bool   Vanilla;
    public int    LeakByRange, LeakByDamage;
    public double ClosestM = -1.0;
}
Wave Cur;
readonly List<Wave> Log = new List<Wave>();
int    PrevInbound;
int    PendingDrops;
int    BlockCount = -1;
double DamagePollDue;
int    TotKills, TotLeaks, TotBlocks, TotFired;
int    _waveFiredAt, _waveDescAt;
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
        if (m.InFlight <= 0 && m.Band < 0) continue;   // not engaging anything
        double r = m.AppliedRange > 0 ? m.AppliedRange * frac : 0.0;
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
    // targetId == -1 is the sentinel for a PROJECTILE target (Target.SetTargetId).
    // Every anti-torpedo round reports the same -1, so rounds cannot be
    // attributed to individual torpedoes — but a COUNT is all this needs, and
    // filtering on -1 keeps anti-grid fire from polluting it.
    if (targetId != -1) return;
    if (start) { m.InFlight++; m.Spawns++; TotalSpawns++; }
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
    if (arg == "vanilla" || arg == "active" || arg == "toggle") {
        Vanilla = arg == "toggle" ? !Vanilla : arg == "vanilla";
        SaveFlags();
        // Close any wave in progress so its stats are not split across two modes.
        if (Cur != null) CloseWave();
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            m.Rung = 0;
            SetRange(m, m.BaseRange);
        }
        Echo("mode -> " + (Vanilla ? "VANILLA (passive control)" : "ACTIVE"));
        return;
    }
    if (arg == "debug") {
        Debug = !Debug;
        SaveFlags();
        if (!Debug) Me.CustomData = "";
        Echo("debug -> " + (Debug ? "ON (panel + CustomData wave log)" : "OFF"));
        return;
    }
    if (arg == "rescan") { Discover(); }
    if (arg == "igc") {          // force a fresh poll and print, for spot checks
        Gossip();
        Inbound = FleetInbound();
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
    if (Inbound < PrevInbound) PendingDrops += PrevInbound - Inbound;
    PrevInbound = Inbound;

    if (Cur != null) {
        if (Inbound > Cur.PeakIn) Cur.PeakIn = Inbound;

        // RANGE-INFERRED LEAKS. Works with damage disabled, which the block sensor
        // cannot. If something was seen inside LEAK_RANGE_M in the last moment, endings
        // recorded now are scored leaks.
        double near = ClosestSeen();
        if (PendingDrops > 0 && near >= 0.0 && near <= LEAK_RANGE_M) {
            Cur.Leaks += PendingDrops;
            Cur.LeakByRange += PendingDrops;
            PendingDrops = 0;
        }
        if (near >= 0.0 && (Cur.ClosestM < 0.0 || near < Cur.ClosestM)) Cur.ClosestM = near;

        if (lostNow > 0) {
            Cur.BlocksLost += lostNow;
            int leak = PendingDrops < lostNow ? PendingDrops : lostNow;
            if (leak > 0) { Cur.Leaks += leak; Cur.LeakByDamage += leak; PendingDrops -= leak; }
        }
        double hot = 0.0;
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            float h = Wc.GetWeaponHeatLevel(m.Blk, m.Parts.Count > 0 ? m.Parts[0] : 0);
            if (h > hot) hot = h;
        }
        if (hot > Cur.PeakHeat) Cur.PeakHeat = hot;
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
        if (Cur != null && ZeroRuns >= WAVE_GAP_TICKS) CloseWave();
        if (Debug) Report(); else Status();
        return;                       // nothing else to do until a threat appears
    }
    if (ZeroRuns >= WAVE_GAP_TICKS) {                       // new engagement begins
        Respread();
        WaveCount++;
        Cur = new Wave();
        Cur.N = WaveCount;
        Cur.Start = Now;
        Cur.PeakIn = Inbound;
        Cur.Vanilla = Vanilla;
        _waveFiredAt = TotalSpawns;
        _waveDescAt = TotalDescents();
        PendingDrops = 0;
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
        double want = m.BaseRange * RUNGS[m.Rung];
        if (want < MIN_RANGE_M) want = MIN_RANGE_M;
        SetRange(m, want);
        // Fire is NEVER toggled. Every withholding policy tested lost.
    }

    if (Debug) Report(); else Status();
}

// Single choke point for range changes, so the diagnostics can count them and we never
// spam an unchanged value.
void SetRange(Mount m, double r) {
    if (Math.Abs(r - m.AppliedRange) < 0.5) return;
    m.AppliedRange = r;
    RangeWrites++;
    Wc.SetBlockTrackingRange(m.Blk, (float)r);
}

int TotalDescents() {
    int d = 0;
    foreach (var m in Mounts) d += m.Descents;
    return d;
}

// Whatever is still pending when the wave closes had no damage correlated with it, so it
// is counted as a kill.
void CloseWave() {
    Cur.Dur = Now - Cur.Start;
    Cur.Fired = TotalSpawns - _waveFiredAt;
    Cur.Descents = TotalDescents() - _waveDescAt;
    Cur.Kills += PendingDrops;
    PendingDrops = 0;
    Cur.Ended = Cur.Kills + Cur.Leaks;
    if (Cur.Vanilla) {
        VKills += Cur.Kills; VLeaks += Cur.Leaks;
        VBlocks += Cur.BlocksLost; VFired += Cur.Fired; VWaves++;
    } else {
        TotKills += Cur.Kills; TotLeaks += Cur.Leaks;
        TotBlocks += Cur.BlocksLost; TotFired += Cur.Fired;
    }
    Log.Add(Cur);
    while (Log.Count > LOG_WAVES) Log.RemoveAt(0);
    Cur = null;
    if (Debug) WriteLog();
}

void WriteLog() {
    var sb = new StringBuilder();
    sb.Append("FleetPD log   grid=").Append(Me.CubeGrid.EntityId % 1000000L)
      .Append("   hull ").Append(HullOrdinal + 1).Append('/').Append(HullCount)
      .Append("   mounts=").Append(Mounts.Count).AppendLine();
    sb.AppendLine("kill~ and leak~ are ESTIMATES. Nothing reports being hit, so the script");
    sb.AppendLine("A fall in inbound count is scored a LEAK if any mount reported its target");
    sb.AppendLine("inside " + LEAK_RANGE_M.ToString("0") + " m just beforehand (WeaponCore TargetRanged bands),");
    sb.AppendLine("or if grid blocks were lost at the same moment. Otherwise it is a kill.");
    sb.AppendLine("byRng works with damage disabled; byDmg does not.");
    sb.AppendLine("Only waves fought with debug ON are recorded.");
    sb.AppendLine();
    sb.AppendLine("wave  mode    dur  peakIn  ended  kill~  leak~  byRng  byDmg  closest  fired  r/kill~  heat");
    for (int i = 0; i < Log.Count; i++) {
        var w = Log[i];
        sb.Append(w.N.ToString().PadLeft(4))
          .Append(w.Vanilla ? "  VAN" : "  act")
          .Append((w.Dur.ToString("0.0") + "s").PadLeft(7))
          .Append(w.PeakIn.ToString().PadLeft(8))
          .Append(w.Ended.ToString().PadLeft(7))
          .Append(w.Kills.ToString().PadLeft(7))
          .Append(w.Leaks.ToString().PadLeft(7))
          .Append(w.LeakByRange.ToString().PadLeft(7))
          .Append(w.LeakByDamage.ToString().PadLeft(7))
          .Append((w.ClosestM >= 0 ? ((int)w.ClosestM).ToString() + "m" : "-").PadLeft(9))
          .Append(w.Fired.ToString().PadLeft(7))
          .Append((w.Kills > 0 ? ((double)w.Fired / w.Kills).ToString("0.0") : "-").PadLeft(9))
          .Append(((int)(w.PeakHeat * 100)).ToString().PadLeft(5)).Append('%')
          .AppendLine();
    }
    sb.AppendLine();
    sb.AppendLine("mode      waves  kill~  leak~  blocks   fired  r/kill~  intercept");
    AppendTotals(sb, "ACTIVE", WaveCount - VWaves, TotKills, TotLeaks, TotBlocks, TotFired);
    AppendTotals(sb, "VANILLA", VWaves, VKills, VLeaks, VBlocks, VFired);
    sb.AppendLine();
    sb.AppendLine("Run the PB with argument 'vanilla' to collect the passive control, then");
    sb.AppendLine("'active' to resume. Compare the two intercept rates above.");
    Me.CustomData = sb.ToString();
}

void AppendTotals(StringBuilder sb, string label, int waves, int k, int l, int b, int f) {
    sb.Append(label.PadRight(9))
      .Append(waves.ToString().PadLeft(5))
      .Append(k.ToString().PadLeft(7))
      .Append(l.ToString().PadLeft(7))
      .Append(b.ToString().PadLeft(8))
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
    if (WaveCount > 0 || Cur != null) {
        sb.Append("-- stats --  kill~=").Append(TotKills).Append(" leak~=").Append(TotLeaks);
        if (TotKills + TotLeaks > 0)
            sb.Append(" intercept=")
              .Append((100.0 * TotKills / (TotKills + TotLeaks)).ToString("0")).Append('%');
        sb.Append(" blocksLost=").Append(TotBlocks);
        if (Cur != null) sb.Append("  [wave ").Append(Cur.N).Append(" live]");
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
