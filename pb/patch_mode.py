"""Add a VANILLA control mode: run passive, keep logging, tally separately.

This is the in-game equivalent of the simulator's `no PB` baseline row. Run some waves
active and some vanilla and the CustomData log shows both intercept rates side by side,
which is the only way to check the sim's prediction against the actual game.
"""
import io

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()
PCT = chr(37)
Q = "'" + PCT + "'"

# ---- state
s = s.replace("int    _waveFiredAt, _waveDescAt;", """int    _waveFiredAt, _waveDescAt;
// VANILLA MODE. Passive: mounts stay at full range and never descend, but every
// statistic is still recorded. Toggle with the 'vanilla' / 'active' argument. Totals are
// kept per mode so the log compares the two directly -- the in-game control for the
// simulator's `no PB` row.
bool Vanilla;
int  VKills, VLeaks, VBlocks, VFired, VWaves;""")

# ---- persist mode across recompiles
s = s.replace("    if (Ready) Discover();\n}",
              "    Vanilla = Storage != null && Storage.Contains(\"vanilla\");\n"
              "    if (Ready) Discover();\n}")

# ---- argument handling
s = s.replace('    if (arg == "rescan") { Discover(); }',
              '''    if (arg == "vanilla" || arg == "active" || arg == "toggle") {
        Vanilla = arg == "toggle" ? !Vanilla : arg == "vanilla";
        Storage = Vanilla ? "vanilla" : "";
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
    if (arg == "rescan") { Discover(); }''')

# ---- the actual behavioural gate: in vanilla, hold full range and never descend
s = s.replace("""    foreach (var m in Mounts) {
        if (!Alive(m.Blk)) continue;
        // ---- measured rate of fire, and the slow-mount exemption.""",
"""    if (Vanilla) {
        // Passive control: full range on everything, no ladder, but keep logging.
        foreach (var m in Mounts) {
            if (!Alive(m.Blk)) continue;
            if (m.Rung != 0) m.Rung = 0;
            SetRange(m, m.BaseRange);
        }
        if (DEBUG_PANEL) Report();
        return;
    }

    foreach (var m in Mounts) {
        if (!Alive(m.Blk)) continue;
        // ---- measured rate of fire, and the slow-mount exemption.""")

# ---- tag waves with their mode and tally separately
s = s.replace("public double Start, Dur, PeakHeat;",
              "public double Start, Dur, PeakHeat;\n    public bool   Vanilla;")
s = s.replace("        Cur.PeakIn = Inbound;", "        Cur.PeakIn = Inbound;\n        Cur.Vanilla = Vanilla;")

s = s.replace("""    TotKills += Cur.Kills;
    TotLeaks += Cur.Leaks;
    TotBlocks += Cur.BlocksLost;
    TotFired += Cur.Fired;""",
"""    if (Cur.Vanilla) {
        VKills += Cur.Kills; VLeaks += Cur.Leaks;
        VBlocks += Cur.BlocksLost; VFired += Cur.Fired; VWaves++;
    } else {
        TotKills += Cur.Kills; TotLeaks += Cur.Leaks;
        TotBlocks += Cur.BlocksLost; TotFired += Cur.Fired;
    }""")

# ---- log: mode column + side-by-side comparison
s = s.replace('sb.AppendLine("wave    dur  peakIn  ended  kill~  leak~  blocks  fired  r/kill~  desc  heat");',
              'sb.AppendLine("wave  mode    dur  peakIn  ended  kill~  leak~  blocks  fired  r/kill~  desc  heat");')
s = s.replace("""        sb.Append(w.N.ToString().PadLeft(4))
          .Append((w.Dur.ToString("0.0") + "s").PadLeft(7))""",
"""        sb.Append(w.N.ToString().PadLeft(4))
          .Append(w.Vanilla ? "  VAN" : "  act")
          .Append((w.Dur.ToString("0.0") + "s").PadLeft(7))""")

OLD_TOT = '''    sb.AppendLine();
    sb.Append("totals  waves=").Append(WaveCount)
      .Append("  kill~=").Append(TotKills)
      .Append("  leak~=").Append(TotLeaks)
      .Append("  blocksLost=").Append(TotBlocks)
      .Append("  fired=").Append(TotFired);
    if (TotKills > 0)
        sb.Append("  r/kill~=").Append(((double)TotFired / TotKills).ToString("0.0"));
    if (TotKills + TotLeaks > 0)
        sb.Append("  intercept=")
          .Append((100.0 * TotKills / (TotKills + TotLeaks)).ToString("0.0")).Append(QQ);
    Me.CustomData = sb.ToString();'''.replace('QQ', Q)

NEW_TOT = '''    sb.AppendLine();
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
      .Append((k + l > 0 ? (100.0 * k / (k + l)).ToString("0.0") + QQS : "-").PadLeft(11))
      .AppendLine();'''.replace('QQS', '"' + PCT + '"')

s = s.replace(OLD_TOT, NEW_TOT)

# ---- echo shows the mode prominently
s = s.replace('sb.Append("== FleetPD ==  t=")',
              'sb.Append(Vanilla ? "== FleetPD [VANILLA CONTROL] ==  t=" : "== FleetPD ==  t=")')

io.open(P, 'w', encoding='utf-8').write(s)
print('vanilla mode: gate=%s tally=%s arg=%s'
      % ('if (Vanilla) {' in s, 'VKills' in s, '"vanilla"' in s))
