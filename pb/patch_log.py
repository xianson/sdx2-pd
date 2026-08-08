"""Add per-wave statistics and a CustomData log to FleetPD."""
import io

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()
PCT = chr(37)

s = s.replace(
    "const bool   DEBUG_PANEL    = true;",
    "const bool   DEBUG_PANEL    = true;\n"
    "const bool   CUSTOMDATA_LOG = true;   // write a per-wave log to this PB's CustomData\n"
    "const int    LOG_WAVES      = 24;     // waves retained in the log ring\n"
    "const double DAMAGE_POLL_S  = 1.0;    // how often to re-count blocks (damage sensor)")

s = s.replace("int    IgcSent;", '''// ---- wave statistics.
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
}
Wave Cur;
readonly List<Wave> Log = new List<Wave>();
int    PrevInbound;
int    PendingDrops;
int    BlockCount = -1;
double DamagePollDue;
int    TotKills, TotLeaks, TotBlocks, TotFired;
int    _waveFiredAt, _waveDescAt;
readonly List<IMyTerminalBlock> _dmgScan = new List<IMyTerminalBlock>();

int    IgcSent;''')

s = s.replace("    // IDLE HANDLING", '''    // ---- damage sensor. Counting blocks is O(n), so it is sampled rather than polled.
    int lostNow = 0;
    if (Now >= DamagePollDue) {
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
        if (lostNow > 0) {
            Cur.BlocksLost += lostNow;
            int leak = PendingDrops < lostNow ? PendingDrops : lostNow;
            if (leak > 0) { Cur.Leaks += leak; PendingDrops -= leak; }
        }
        double hot = 0.0;
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            float h = Wc.GetWeaponHeatLevel(m.Blk, m.Parts.Count > 0 ? m.Parts[0] : 0);
            if (h > hot) hot = h;
        }
        if (hot > Cur.PeakHeat) Cur.PeakHeat = hot;
    }

    // IDLE HANDLING''')

s = s.replace('''        if (DEBUG_PANEL) Report();
        return;                       // nothing else to do until a threat appears
    }
    if (ZeroRuns >= WAVE_GAP_TICKS) { Respread(); WaveCount++; }  // new engagement''',
'''        if (Cur != null && ZeroRuns >= WAVE_GAP_TICKS) CloseWave();
        if (DEBUG_PANEL) Report();
        return;                       // nothing else to do until a threat appears
    }
    if (ZeroRuns >= WAVE_GAP_TICKS) {                       // new engagement begins
        Respread();
        WaveCount++;
        Cur = new Wave();
        Cur.N = WaveCount;
        Cur.Start = Now;
        Cur.PeakIn = Inbound;
        _waveFiredAt = TotalSpawns;
        _waveDescAt = TotalDescents();
        PendingDrops = 0;
    }''')

LOG = '''int TotalDescents() {
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
    TotKills += Cur.Kills;
    TotLeaks += Cur.Leaks;
    TotBlocks += Cur.BlocksLost;
    TotFired += Cur.Fired;
    Log.Add(Cur);
    while (Log.Count > LOG_WAVES) Log.RemoveAt(0);
    Cur = null;
    if (CUSTOMDATA_LOG) WriteLog();
}

void WriteLog() {
    var sb = new StringBuilder();
    sb.Append("FleetPD log   grid=").Append(Me.CubeGrid.EntityId PCTOP 1000000L)
      .Append("   hull ").Append(HullOrdinal + 1).Append('/').Append(HullCount)
      .Append("   mounts=").Append(Mounts.Count).AppendLine();
    sb.AppendLine("kill~ and leak~ are ESTIMATES. Nothing reports being hit, so the script");
    sb.AppendLine("correlates a fall in inbound count with a fall in grid block count.");
    sb.AppendLine("A leaker that destroys nothing is missed; splash may be overcounted.");
    sb.AppendLine();
    sb.AppendLine("wave    dur  peakIn  ended  kill~  leak~  blocks  fired  r/kill~  desc  heat");
    for (int i = 0; i < Log.Count; i++) {
        var w = Log[i];
        sb.Append(w.N.ToString().PadLeft(4))
          .Append((w.Dur.ToString("0.0") + "s").PadLeft(7))
          .Append(w.PeakIn.ToString().PadLeft(8))
          .Append(w.Ended.ToString().PadLeft(7))
          .Append(w.Kills.ToString().PadLeft(7))
          .Append(w.Leaks.ToString().PadLeft(7))
          .Append(w.BlocksLost.ToString().PadLeft(8))
          .Append(w.Fired.ToString().PadLeft(7))
          .Append((w.Kills > 0 ? ((double)w.Fired / w.Kills).ToString("0.0") : "-").PadLeft(9))
          .Append(w.Descents.ToString().PadLeft(6))
          .Append(((int)(w.PeakHeat * 100)).ToString().PadLeft(5)).Append(PCTCH)
          .AppendLine();
    }
    sb.AppendLine();
    sb.Append("totals  waves=").Append(WaveCount)
      .Append("  kill~=").Append(TotKills)
      .Append("  leak~=").Append(TotLeaks)
      .Append("  blocksLost=").Append(TotBlocks)
      .Append("  fired=").Append(TotFired);
    if (TotKills > 0)
        sb.Append("  r/kill~=").Append(((double)TotFired / TotKills).ToString("0.0"));
    if (TotKills + TotLeaks > 0)
        sb.Append("  intercept=")
          .Append((100.0 * TotKills / (TotKills + TotLeaks)).ToString("0.0")).Append(PCTCH);
    Me.CustomData = sb.ToString();
}

void Respread() {'''
LOG = LOG.replace('PCTOP', PCT).replace('PCTCH', "'" + PCT + "'")
s = s.replace("void Respread() {", LOG)

s = s.replace('    sb.Append("peersEver=").Append(PeersEverSeen)',
              '''    if (WaveCount > 0 || Cur != null) {
        sb.Append("-- stats --  kill~=").Append(TotKills).Append(" leak~=").Append(TotLeaks);
        if (TotKills + TotLeaks > 0)
            sb.Append(" intercept=")
              .Append((100.0 * TotKills / (TotKills + TotLeaks)).ToString("0")).Append(PCTCH);
        sb.Append(" blocksLost=").Append(TotBlocks);
        if (Cur != null) sb.Append("  [wave ").Append(Cur.N).Append(" live]");
        sb.AppendLine();
    }
    sb.Append("peersEver=").Append(PeersEverSeen)'''.replace('PCTCH', "'" + PCT + "'"))

io.open(P, 'w', encoding='utf-8').write(s)
print('patched: log=%s  wave=%s  sensor=%s'
      % ('WriteLog' in s, 'class Wave' in s, 'DamagePollDue' in s))
