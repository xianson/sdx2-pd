// FleetPD (minified) — https://github.com/xianson/sdx2-pd
// Readable source, with the measurements and reasoning, is pb/FleetPD.cs in that repo.
// Includes WeaponCore's published WcPbApi shim (Ash-LikeSnow), verbatim.
const int    K_INFLIGHT     = 4;
const double REFRACTORY_S   = 0.35;
const int    WAVE_GAP_TICKS = 60;
const double RANGE_FLOOR_M  = 400.0;
const double MIN_RPM        = 100.0;
const double RPM_SAMPLE_S   = 8.0;
const double RESCAN_S       = 30.0;
const double LOG_EVERY_S    = 10.0;
const double DAMAGE_POLL_S  = 1.0;
const double LEAK_RANGE_M   = 250.0;
const double BAND_STALE_S   = 1.5;
const double HIT_FRAC       = 0.92;
const string IGC_TAG        = "FleetPD.v1";
const int    PEER_TIMEOUT   = 30;
const bool   FLEET_TILE     = true;
static readonly double[] RUNGS = { 1.00, 0.80, 0.65, 0.50, 0.38, 0.28 };
static readonly int RUNG_COUNT = RUNGS.Length;
WcPbApi Wc;
bool Ready;
IMyBroadcastListener Igc;
readonly Dictionary<long, int> Peers = new Dictionary<long, int>();
readonly Dictionary<long, int> PeerInbound = new Dictionary<long, int>();
readonly Dictionary<long, bool> PeerQueryable = new Dictionary<long, bool>();
readonly List<long> PeerIds = new List<long>();
int HullOrdinal;
int HullCount = 1;
int TiledFor = -1;
class Mount {
public IMyTerminalBlock Blk;
public long   Id;
public double BaseRange;
public int    Rung;
public int    OpeningRung;
public int    InFlight;
public double LastDescend;
public int    Spawns;
public double SampleStart;
public double Rpm;
public bool   Exempt;
public readonly List<int> Parts = new List<int>();
public double AppliedRange = -1.0;
public int    Descents;
public int    _idx;
public int    Band = -1;
public double BandAt = -1.0;
public double BandRangeM = -1.0;
}
readonly List<Mount> Mounts = new List<Mount>();
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
int    PrevInbound;
int    PendingDrops;
int    BlockCount = -1;
double DamagePollDue;
int    TotKills, TotLeaks, TotBlocks, TotFired;
int    LeakRng, LeakDmg, PeakInbound;
double ClosestEver = -1.0;
double LastDropAt;
double LogDue;
struct Shot { public Vector3D P; public double T; public double Reach; }
readonly Dictionary<ulong, Shot> Airborne = new Dictionary<ulong, Shot>();
int    ShotHits, ShotFlyouts;
double ShotFlightSum;
double OrphanEst;
bool Vanilla;
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
if (Ready) Discover();
}
void Gossip() {
while (Igc.HasPendingMessage) {
var msg = Igc.AcceptMessage();
IgcRecv++;
if (!(msg.Data is long)) { IgcBadPayload++; continue; }
long id = (long)msg.Data;
if (id == Me.CubeGrid.EntityId) continue;
if (!Peers.ContainsKey(id)) PeersEverSeen++;
Peers[id] = 0;
LastPeerHeard = Now;
}
IGC.SendBroadcastMessage(IGC_TAG, Me.CubeGrid.EntityId);
IgcSent++;
PeerIds.Clear();
foreach (var kv in Peers) PeerIds.Add(kv.Key);
foreach (var id in PeerIds) {
int age = Peers[id] + 1;
if (age > PEER_TIMEOUT) Peers.Remove(id); else Peers[id] = age;
}
PeerIds.Clear();
PeerIds.Add(Me.CubeGrid.EntityId);
foreach (var kv in Peers) PeerIds.Add(kv.Key);
PeerIds.Sort();
HullCount = PeerIds.Count;
HullOrdinal = PeerIds.IndexOf(Me.CubeGrid.EntityId);
if (HullOrdinal < 0) HullOrdinal = 0;
if (FLEET_TILE && HullOrdinal != TiledFor) {
TiledFor = HullOrdinal;
for (int i = 0; i < Mounts.Count; i++) {
Mounts[i].OpeningRung = OpeningFor(i);
if (Inbound <= 0) Mounts[i].Rung = Mounts[i].OpeningRung;
}
}
}
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
int _rejNotReady, _rejShortRange, _rejNoMap, _rejNotCore, _seenBlocks;
void Discover() {
_rejNotReady = _rejShortRange = _rejNoMap = _rejNotCore = _seenBlocks = 0;
foreach (var m in Mounts) {
if (!Alive(m.Blk)) continue;
foreach (var pid in m.Parts)
Wc.UnMonitorProjectileCallback(m.Blk, pid, OnProjectile);
}
Mounts.Clear();
ById.Clear();
_blocks.Clear();
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
double baseRange = 0.0;
Learned known;
if (Memory.TryGetValue(b.EntityId, out known) && known.BaseRange > 0.0) {
baseRange = known.BaseRange;
} else {
Wc.SetBlockTrackingRange(b, 1e9f);
foreach (var kv in _map) {
float r = Wc.GetMaxWeaponRange(b, kv.Value);
if (r > baseRange) baseRange = r;
}
}
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
foreach (var kv in _map) {
mt.Parts.Add(kv.Value);
Wc.MonitorProjectileCallback(b, kv.Value, OnProjectile);
Wc.MonitorEvents(b, kv.Value, OnWeaponEvent);
}
spread++;
}
}
int OpeningFor(int n) {
int off = FLEET_TILE ? HullOrdinal : 0;
return ((n + off) % RUNG_COUNT + RUNG_COUNT) % RUNG_COUNT;
}
static bool Alive(IMyTerminalBlock b) {
return b != null && !b.Closed && b.CubeGrid != null;
}
void OnWeaponEvent(int state, bool active) {
if (!active || state < 17 || state > 20) return;
double frac = state == 17 ? 1.00 : state == 18 ? 0.75 : state == 19 ? 0.50 : 0.25;
for (int i = 0; i < Mounts.Count; i++) {
var m = Mounts[i];
if (!Alive(m.Blk)) continue;
double r = m.AppliedRange > 0 ? m.AppliedRange * frac : 0.0;
if (r <= 0) continue;
m.Band = state;
m.BandAt = Now;
m.BandRangeM = r;
}
}
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
if (start) {
m.InFlight++;
m.Spawns++;
TotalSpawns++;
{
var sh = new Shot();
sh.P = pos;
sh.T = Now;
sh.Reach = m.BaseRange;
Airborne[projId] = sh;
}
return;
}
if (m.InFlight > 0) m.InFlight--;
Shot rec;
if (!Airborne.TryGetValue(projId, out rec)) return;
Airborne.Remove(projId);
double flew = Vector3D.Distance(rec.P, pos);
double dt = Now - rec.T;
ShotFlightSum += dt;
if (rec.Reach > 0 && flew < rec.Reach * HIT_FRAC) {
ShotHits++;
} else {
ShotFlyouts++;
}
}
public void Main(string arg, UpdateType src) {
if (!Ready) {
Wc = new WcPbApi();
try { Ready = Wc.Activate(Me); } catch { Ready = false; }
if (!Ready) { Echo("WeaponCore PB API unavailable."); return; }
Discover();
}
if (arg == "vanilla" || arg == "active" || arg == "toggle") {
Vanilla = arg == "toggle" ? !Vanilla : arg == "vanilla";
foreach (var m in Mounts) {
if (!Alive(m.Blk)) continue;
m.Rung = 0;
SetRange(m, m.BaseRange);
}
Echo("mode -> " + (Vanilla ? "VANILLA (passive control)" : "ACTIVE"));
return;
}
if (Mounts.Count == 0) { Discover(); if (Mounts.Count == 0) { Echo("No CoreSystems weapons found."); return; } }
Now += Runtime.TimeSinceLastRun.TotalSeconds;
Gossip();
Inbound = FleetInbound();
int lostNow = 0;
if (Now >= DamagePollDue) {
DamagePollDue = Now + DAMAGE_POLL_S;
_dmgScan.Clear();
GridTerminalSystem.GetBlocks(_dmgScan);
int n = _dmgScan.Count;
if (BlockCount >= 0 && n < BlockCount) lostNow = BlockCount - n;
BlockCount = n;
}
if (Inbound < PrevInbound) {
int died = PrevInbound - Inbound;
PendingDrops += died;
LastDropAt = Now;
if (PrevInbound > 0) {
int air = 0;
for (int i = 0; i < Mounts.Count; i++) air += Mounts[i].InFlight;
double orph = air * ((double)died / PrevInbound);
OrphanEst += orph;
}
}
PrevInbound = Inbound;
if (Inbound > PeakInbound) PeakInbound = Inbound;
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
if (PendingDrops > 0 && Now - LastDropAt > 0.75) {
if (Vanilla) VKills += PendingDrops; else TotKills += PendingDrops;
PendingDrops = 0;
}
if (Inbound <= 0) {
ZeroRuns++;
foreach (var m in Mounts) {
if (!Alive(m.Blk)) continue;
if (m.Rung != 0) { m.Rung = 0; m.LastDescend = -99.0; }
SetRange(m, m.BaseRange);
}
if (Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }
Report();
return;
}
if (ZeroRuns >= WAVE_GAP_TICKS) {
Respread();
WaveCount++;
}
ZeroRuns = 0;
bool lost = false;
for (int i = Mounts.Count - 1; i >= 0; i--) {
if (!Alive(Mounts[i].Blk)) { ById.Remove(Mounts[i].Id); Mounts.RemoveAt(i); lost = true; }
}
if (lost) RescanDue = 0.0;
if (Now >= RescanDue) { RescanDue = Now + RESCAN_S; Discover(); }
if (Vanilla) {
foreach (var m in Mounts) {
if (!Alive(m.Blk)) continue;
if (m.Rung != 0) m.Rung = 0;
SetRange(m, m.BaseRange);
}
if (Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }
Report();
return;
}
foreach (var m in Mounts) {
if (!Alive(m.Blk)) continue;
if (m.SampleStart <= 0.0) m.SampleStart = Now;
double span = Now - m.SampleStart;
if (span >= RPM_SAMPLE_S) {
double rpm = m.Spawns * 60.0 / span;
m.Rpm = (m.Rpm <= 0.0) ? rpm : (m.Rpm * 0.5 + rpm * 0.5);
m.Spawns = 0;
m.SampleStart = Now;
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
}
if (Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }
Report();
}
double RungRange(Mount m, int rung) {
double span = m.BaseRange - RANGE_FLOOR_M;
if (span <= 0.0) return m.BaseRange;
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
}
}
void Report() {
var sb = new StringBuilder();
sb.Append(Vanilla ? "== FleetPD [VANILLA CONTROL] ==  t=" : "== FleetPD ==  t=").Append(Now.ToString("0")).Append("s  hull ")
.Append(HullOrdinal + 1).Append('/').Append(HullCount).AppendLine();
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
public bool Activate(Sandbox.ModAPI.Ingame.IMyTerminalBlock pbBlock)
{
var dict = pbBlock.GetProperty("WcPbAPI")?.As<IReadOnlyDictionary<string, Delegate>>().GetValue(pbBlock);
if (dict == null) throw new Exception("WcPbAPI failed to activate");
return ApiAssign(dict);
}
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
public void GetAllCoreWeapons(ICollection<MyDefinitionId> collection) => _getCoreWeapons?.Invoke(collection);
public void GetAllCoreStaticLaunchers(ICollection<MyDefinitionId> collection) =>
_getCoreStaticLaunchers?.Invoke(collection);
public void GetAllCoreTurrets(ICollection<MyDefinitionId> collection) => _getCoreTurrets?.Invoke(collection);
public bool GetBlockWeaponMap(Sandbox.ModAPI.Ingame.IMyTerminalBlock weaponBlock, IDictionary<string, int> collection) =>
_getBlockWeaponMap?.Invoke(weaponBlock, collection) ?? false;
public MyTuple<bool, int, int> GetProjectilesLockedOn(long victim) =>
_getProjectilesLockedOn?.Invoke(victim) ?? new MyTuple<bool, int, int>();
public void GetSortedThreats(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, IDictionary<MyDetectedEntityInfo, float> collection) =>
_getSortedThreats?.Invoke(pBlock, collection);
public void GetSortedThreatsByID(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, IDictionary<long, MyDetectedEntityInfo> collection) =>
_getSortedThreatsByID?.Invoke(pBlock, collection);
public void GetObstructions(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, ICollection<Sandbox.ModAPI.Ingame.MyDetectedEntityInfo> collection) =>
_getObstructions?.Invoke(pBlock, collection);
public MyDetectedEntityInfo? GetAiFocus(long shooter, int priority = 0) => _getAiFocus?.Invoke(shooter, priority);
public bool SetAiFocus(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, long target, int priority = 0) =>
_setAiFocus?.Invoke(pBlock, target, priority) ?? false;
public bool ReleaseAiFocus(Sandbox.ModAPI.Ingame.IMyTerminalBlock pBlock, long playerId) =>
_releaseAiFocus?.Invoke(pBlock, playerId) ?? false;
public MyDetectedEntityInfo? GetWeaponTarget(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId = 0) =>
_getWeaponTarget?.Invoke(weapon, weaponId);
public void SetWeaponTarget(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long target, int weaponId = 0) =>
_setWeaponTarget?.Invoke(weapon, target, weaponId);
public void FireWeaponOnce(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, bool allWeapons = true, int weaponId = 0) =>
_fireWeaponOnce?.Invoke(weapon, allWeapons, weaponId);
public void ToggleWeaponFire(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, bool on, bool allWeapons, int weaponId = 0) =>
_toggleWeaponFire?.Invoke(weapon, on, allWeapons, weaponId);
public bool IsWeaponReadyToFire(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId = 0, bool anyWeaponReady = true,
bool shootReady = false) =>
_isWeaponReadyToFire?.Invoke(weapon, weaponId, anyWeaponReady, shootReady) ?? false;
public float GetMaxWeaponRange(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
_getMaxWeaponRange?.Invoke(weapon, weaponId) ?? 0f;
public bool GetTurretTargetTypes(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, IList<string> collection, int weaponId = 0) =>
_getTurretTargetTypes?.Invoke(weapon, collection, weaponId) ?? false;
public void SetTurretTargetTypes(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, IList<string> collection, int weaponId = 0) =>
_setTurretTargetTypes?.Invoke(weapon, collection, weaponId);
public void SetBlockTrackingRange(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, float range) =>
_setBlockTrackingRange?.Invoke(weapon, range);
public bool IsTargetAligned(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
_isTargetAligned?.Invoke(weapon, targetEnt, weaponId) ?? false;
public MyTuple<bool, Vector3D?> IsTargetAlignedExtended(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
_isTargetAlignedExtended?.Invoke(weapon, targetEnt, weaponId) ?? new MyTuple<bool, Vector3D?>();
public bool CanShootTarget(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
_canShootTarget?.Invoke(weapon, targetEnt, weaponId) ?? false;
public Vector3D? GetPredictedTargetPosition(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetEnt, int weaponId) =>
_getPredictedTargetPos?.Invoke(weapon, targetEnt, weaponId) ?? null;
public float GetHeatLevel(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _getHeatLevel?.Invoke(weapon) ?? 0f;
public float GetWeaponHeatLevel(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) => _getWeaponHeatLevel?.Invoke(weapon, weaponId) ?? -1f;
public int GetMaxWeaponHeatLevel(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) => _getMaxWeaponHeatLevel?.Invoke(weapon, weaponId) ?? -1;
public float GetCurrentPower(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _currentPowerConsumption?.Invoke(weapon) ?? 0f;
public float GetMaxPower(MyDefinitionId weaponDef) => _getMaxPower?.Invoke(weaponDef) ?? 0f;
public bool HasGridAi(long entity) => _hasGridAi?.Invoke(entity) ?? false;
public bool HasCoreWeapon(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _hasCoreWeapon?.Invoke(weapon) ?? false;
public float GetOptimalDps(long entity) => _getOptimalDps?.Invoke(entity) ?? 0f;
public string GetActiveAmmo(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
_getActiveAmmo?.Invoke(weapon, weaponId) ?? null;
public int GetAmmoCount(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
_getAmmoCount?.Invoke(weapon, weaponId) ?? -1;
public void SetActiveAmmo(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId, string ammoType) =>
_setActiveAmmo?.Invoke(weapon, weaponId, ammoType);
public void MonitorProjectileCallback(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId, Action<long, int, ulong, long, Vector3D, bool> action) =>
_monitorProjectile?.Invoke(weapon, weaponId, action);
public void UnMonitorProjectileCallback(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId, Action<long, int, ulong, long, Vector3D, bool> action) =>
_unMonitorProjectile?.Invoke(weapon, weaponId, action);
public MyTuple<Vector3D, Vector3D, float, float, long, string> GetProjectileState(ulong projectileId) =>
_getProjectileState?.Invoke(projectileId) ?? new MyTuple<Vector3D, Vector3D, float, float, long, string>();
public float GetConstructEffectiveDps(long entity) => _getConstructEffectiveDps?.Invoke(entity) ?? 0f;
public long GetPlayerController(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon) => _getPlayerController?.Invoke(weapon) ?? -1;
public Matrix GetWeaponAzimuthMatrix(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
_getWeaponAzimuthMatrix?.Invoke(weapon, weaponId) ?? Matrix.Zero;
public Matrix GetWeaponElevationMatrix(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
_getWeaponElevationMatrix?.Invoke(weapon, weaponId) ?? Matrix.Zero;
public bool IsTargetValid(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, long targetId, bool onlyThreats, bool checkRelations) =>
_isTargetValid?.Invoke(weapon, targetId, onlyThreats, checkRelations) ?? false;
public MyTuple<Vector3D, Vector3D> GetWeaponScope(Sandbox.ModAPI.Ingame.IMyTerminalBlock weapon, int weaponId) =>
_getWeaponScope?.Invoke(weapon, weaponId) ?? new MyTuple<Vector3D, Vector3D>();
public MyTuple<bool, bool> IsInRange(Sandbox.ModAPI.Ingame.IMyTerminalBlock block) =>
_isInRange?.Invoke(block) ?? new MyTuple<bool, bool>();
public void MonitorEvents(Sandbox.ModAPI.Ingame.IMyTerminalBlock entity, int partId, Action<int, bool> action) =>
_monitorEvents?.Invoke(entity, partId, action);
public void UnMonitorEvents(Sandbox.ModAPI.Ingame.IMyTerminalBlock entity, int partId, Action<int, bool> action) =>
_unmonitorEvents?.Invoke(entity, partId, action);
}
