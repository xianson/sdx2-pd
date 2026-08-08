"""Fix the logging: counters that never counted, and a table that never lined up.

Reported symptoms and their causes, from a real run:

  fired = 0
      OnProjectile filtered on `targetId != -1`, intending to keep anti-grid fire out of
      the anti-torpedo counters. The filter rejected everything, so no round was ever
      counted. It cascades: InFlight stays 0 -> OnWeaponEvent skipped every mount because
      it gated on InFlight > 0 -> no range band recorded -> ClosestSeen() always -1 ->
      LEAK DETECTION COULD NEVER FIRE. One bad predicate, three dead features.
      Fix: count every round this block fires, no filter.

  columns off by one, heat = -1809326%
      The header lost its `ended` column but the row still appended it, so every field
      printed one column to the left. Fixed by removing the wave table entirely.

  kill~ = 167 from peakIn 21 over a 136 s "wave"
      Inbound rises and falls continuously in a real fight, and every dip added to the
      drop accumulator while the wave never closed. Wave framing was the wrong model.

So: no more wave records. The log is now a periodic snapshot of running counts, written
every LOG_EVERY_S seconds, which is what was actually wanted and has no state machine to
get wrong.
"""
import io
import re

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()
PCT = chr(37)

# ------------------------------------------------------------------ 1. counters
s = s.replace("""    if (start) {
        m.InFlight++;
        m.Spawns++;
        TotalSpawns++;""",
"""    // NO targetId FILTER. It used to skip anything whose Target.TargetId was not the
    // -1 projectile sentinel, which rejected every round and silently zeroed the stats.
    if (start) {
        m.InFlight++;
        m.Spawns++;
        TotalSpawns++;""")
s = s.replace("""    // targetId == -1 is the sentinel for a PROJECTILE target (Target.SetTargetId).
    // Every anti-torpedo round reports the same -1, so rounds cannot be attributed to
    // individual torpedoes — but a COUNT is all this needs, and filtering on -1 keeps
    // anti-grid fire from polluting it.
    if (targetId != -1) return;
""", "")

# ------------------------------------------------------------------ 2. band gate
s = s.replace("        if (m.InFlight <= 0 && m.Band < 0) continue;   // not engaging anything",
              "        if (!Alive(m.Blk)) continue;")

# ------------------------------------------------------------------ 3. heat guard
s = s.replace("            float h = Wc.GetWeaponHeatLevel(m.Blk, m.Parts.Count > 0 ? m.Parts[0] : 0);\n"
              "            if (h > hot) hot = h;",
              "            // returns -1 when unavailable; and it is a 0..1 fraction, not a percent\n"
              "            float h = Wc.GetWeaponHeatLevel(m.Blk, m.Parts.Count > 0 ? m.Parts[0] : 0);\n"
              "            if (h > 0f && h <= 1f && h > hot) hot = h;")

# ------------------------------------------------------------------ 4. periodic log
s = s.replace("const int    LOG_WAVES      = 24;     // waves retained in the log ring",
              "const double LOG_EVERY_S    = 10.0;   // CustomData refresh interval")

body = s
m = re.search(r'void WriteLog\(\) \{', body)
end = body.index('void AppendTotals(', m.start())
newlog = '''void WriteLog() {
    var sb = new StringBuilder();
    sb.Append("FleetPD   grid=").Append(Me.CubeGrid.EntityId PCTOP 1000000L)
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
          .Append((100.0 * (TotKills + VKills) / tot).ToString("0.0")).Append(PCTCH).AppendLine();
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

'''.replace('PCTOP', PCT).replace('PCTCH', "'" + PCT + "'")
s = body[:m.start()] + newlog + body[end:]

# AppendTotals loses the waves/blocks columns
s = re.sub(r'void AppendTotals\(StringBuilder sb.*?\n\}', '''void AppendTotals(StringBuilder sb, string label, int k, int l, int f) {
    sb.Append(label.PadRight(9))
      .Append(k.ToString().PadLeft(7))
      .Append(l.ToString().PadLeft(7))
      .Append(f.ToString().PadLeft(8))
      .Append((k > 0 ? ((double)f / k).ToString("0.0") : "-").PadLeft(9))
      .Append((k + l > 0 ? (100.0 * k / (k + l)).ToString("0.0") + PCTS : "-").PadLeft(11))
      .AppendLine();
}'''.replace('PCTS', '"' + PCT + '"'), s, count=1, flags=re.S)

io.open(P, 'w', encoding='utf-8').write(s)
print('log rewritten: filter_gone=%s periodic=%s'
      % ('targetId != -1' not in s, 'LOG_EVERY_S' in s))
