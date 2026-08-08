"""Per-round efficiency: hits, fly-outs, and an orphaned-round estimate.

This is measurable far more directly than leaks. MonitorProjectile fires twice for every
round we fire -- spawn (Projectile.cs:352) and end of life (ProjectileTypes.cs:120) -- and
BOTH callbacks carry a Vector3D position. So each round yields a flight distance and a
flight time, exactly:

    ended well short of its reach   -> it ran into something. A round can only hit the one
                                       target it was fired at (ProjectileHits.cs:601), so
                                       for anti-torpedo fire this is a HIT.
    ran out its full reach          -> it hit nothing: a fly-out.

The one thing distance cannot separate is WHY it hit nothing. A round whose torpedo died
mid-flight is orphaned and flies out looking identical to an honest miss. That split is
estimated instead: at the instant the inbound count falls by D of L live targets, roughly
D/L of everything currently airborne was committed to the dying ones.

Reported as: hit%, flyout%, orphan~ (share of fly-outs attributable to targets dying),
and mean flight time. Only runs with debug on -- it costs a dictionary insert and removal
per round.
"""
import io

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()

s = s.replace("const double BAND_STALE_S   = 1.5;    // ignore a band report older than this",
              "const double BAND_STALE_S   = 1.5;    // ignore a band report older than this\n"
              "const double HIT_FRAC       = 0.92;   // ended inside this fraction of reach => hit")

# ---- per-round tracking + counters
s = s.replace("int    _waveFiredAt, _waveDescAt;",
              """int    _waveFiredAt, _waveDescAt;
// Round-level efficiency. Keyed by projectile id; entries are removed on the end
// callback, so the dictionary is bounded by rounds currently in the air.
struct Shot { public Vector3D P; public double T; public double Reach; }
readonly Dictionary<ulong, Shot> Airborne = new Dictionary<ulong, Shot>();
int    ShotHits, ShotFlyouts;
double ShotFlightSum;
double OrphanEst;""")

s = s.replace("public int    LeakByRange, LeakByDamage;",
              "public int    LeakByRange, LeakByDamage;\n"
              "    public int    Hits, Flyouts;\n"
              "    public double Orphan, FlightSum;")

# ---- record spawn, resolve on end
s = s.replace("""    if (start) { m.InFlight++; m.Spawns++; TotalSpawns++; }
    else if (m.InFlight > 0) m.InFlight--;""",
"""    if (start) {
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
    if (Cur != null) Cur.FlightSum += dt;
    // Short flight => it ran into its target. Full reach => it hit nothing.
    if (rec.Reach > 0 && flew < rec.Reach * HIT_FRAC) {
        ShotHits++;
        if (Cur != null) Cur.Hits++;
    } else {
        ShotFlyouts++;
        if (Cur != null) Cur.Flyouts++;
    }""")

# ---- orphan estimate at the moment targets die
s = s.replace("""    // ---- inbound delta: a fall means that many torpedoes ended, somehow.
    if (Inbound < PrevInbound) PendingDrops += PrevInbound - Inbound;
    PrevInbound = Inbound;""",
"""    // ---- inbound delta: a fall means that many torpedoes ended, somehow.
    if (Inbound < PrevInbound) {
        int died = PrevInbound - Inbound;
        PendingDrops += died;
        // Orphaned-round estimate: of everything airborne right now, the share committed
        // to the torpedoes that just died is about died / (live before they died).
        if (Debug && PrevInbound > 0) {
            int air = 0;
            for (int i = 0; i < Mounts.Count; i++) air += Mounts[i].InFlight;
            double orph = air * ((double)died / PrevInbound);
            OrphanEst += orph;
            if (Cur != null) Cur.Orphan += orph;
        }
    }
    PrevInbound = Inbound;""")

# ---- log columns
s = s.replace('sb.AppendLine("wave  mode    dur  peakIn  ended  kill~  leak~  byRng  byDmg  closest  fired  r/kill~  heat");',
              'sb.AppendLine("wave  mode    dur  peakIn  kill~  leak~  closest  fired   hit%  flyout%  orphan~  tof  heat");')
s = s.replace("""          .Append(w.Leaks.ToString().PadLeft(7))
          .Append(w.LeakByRange.ToString().PadLeft(7))
          .Append(w.LeakByDamage.ToString().PadLeft(7))
          .Append((w.ClosestM >= 0 ? ((int)w.ClosestM).ToString() + "m" : "-").PadLeft(9))
          .Append(w.Fired.ToString().PadLeft(7))
          .Append((w.Kills > 0 ? ((double)w.Fired / w.Kills).ToString("0.0") : "-").PadLeft(9))
          .Append(((int)(w.PeakHeat * 100)).ToString().PadLeft(5)).Append(PCT)""".replace('PCT', "'" + chr(37) + "'"),
"""          .Append(w.Leaks.ToString().PadLeft(7))
          .Append((w.ClosestM >= 0 ? ((int)w.ClosestM).ToString() + "m" : "-").PadLeft(9))
          .Append(w.Fired.ToString().PadLeft(7))
          .Append(Pct(w.Hits, w.Hits + w.Flyouts).PadLeft(7))
          .Append(Pct(w.Flyouts, w.Hits + w.Flyouts).PadLeft(9))
          .Append(((int)w.Orphan).ToString().PadLeft(9))
          .Append((w.Hits + w.Flyouts > 0
                   ? (w.FlightSum / (w.Hits + w.Flyouts)).ToString("0.00") + "s" : "-").PadLeft(6))
          .Append(((int)(w.PeakHeat * 100)).ToString().PadLeft(5)).Append(PCT)""".replace('PCT', "'" + chr(37) + "'"))

s = s.replace("void AppendTotals(", """string Pct(int a, int b) {
    return b > 0 ? (100.0 * a / b).ToString("0") + PCTS : "-";
}

void AppendTotals(""".replace('PCTS', '"' + chr(37) + '"'))

# ---- efficiency block in the log footer
s = s.replace('    sb.AppendLine("Run the PB with argument \'vanilla\' to collect the passive control, then");',
              '''    sb.AppendLine();
    int res = ShotHits + ShotFlyouts;
    sb.Append("rounds resolved=").Append(res)
      .Append("  hit=").Append(Pct(ShotHits, res))
      .Append("  flyout=").Append(Pct(ShotFlyouts, res))
      .Append("  orphan~=").Append(((int)OrphanEst).ToString());
    if (res > 0) sb.Append("  meanToF=").Append((ShotFlightSum / res).ToString("0.00")).Append('s');
    sb.AppendLine();
    sb.AppendLine("hit = round ended short of its reach, so it ran into its target.");
    sb.AppendLine("flyout = ran out its full reach and hit nothing. orphan~ estimates how");
    sb.AppendLine("many of those were committed to a torpedo that died mid-flight.");
    sb.AppendLine();
    sb.AppendLine("Run the PB with argument \\'vanilla\\' to collect the passive control, then");''')

# ---- echo line
s = s.replace('        sb.Append(" blocksLost=").Append(TotBlocks);',
              '''        sb.Append(" blocksLost=").Append(TotBlocks);
        int res2 = ShotHits + ShotFlyouts;
        if (res2 > 0)
            sb.Append("  hit=").Append(Pct(ShotHits, res2))
              .Append(" flyout=").Append(Pct(ShotFlyouts, res2))
              .Append(" orphan~=").Append((int)OrphanEst);''')

io.open(P, 'w', encoding='utf-8').write(s)
print('efficiency: shots=%s orphan=%s pct=%s'
      % ('Airborne' in s, 'OrphanEst' in s, 'string Pct(' in s))
