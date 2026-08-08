"""Strip the wave state machine; keep plain running counters. Merge the arguments.

Wave framing was the wrong model for a real fight: inbound rises and falls continuously,
so "the wave" never closed and every dip fed the drop accumulator, producing 167 kills
from a peak of 21. Running totals with a periodic snapshot have no such state to corrupt.

Arguments collapse to two. `debug` now does everything diagnostic -- toggles the panel and
the CustomData log, forces a weapon rescan, and refreshes the IGC poll immediately -- so
there is nothing to remember. `vanilla` / `active` stay separate because they change what
the script DOES, not what it reports.
"""
import io
import re

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()

# ---------------------------------------------------------------- running counters
s = re.sub(r'class Wave \{.*?\n\}\nWave Cur;\nreadonly List<Wave> Log = new List<Wave>\(\);\n',
           '', s, count=1, flags=re.S)
s = s.replace("int    TotKills, TotLeaks, TotBlocks, TotFired;",
              "int    TotKills, TotLeaks, TotBlocks, TotFired;\n"
              "int    LeakRng, LeakDmg, PeakInbound;\n"
              "double ClosestEver = -1.0;\n"
              "double LogDue;")

# ---------------------------------------------------------------- Main body
s = s.replace("""    if (Cur != null) {
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
            // returns -1 when unavailable; and it is a 0..1 fraction, not a percent
            float h = Wc.GetWeaponHeatLevel(m.Blk, m.Parts.Count > 0 ? m.Parts[0] : 0);
            if (h > 0f && h <= 1f && h > hot) hot = h;
        }
        if (hot > Cur.PeakHeat) Cur.PeakHeat = hot;
    }
""",
"""    if (Inbound > PeakInbound) PeakInbound = Inbound;

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
""")

s = s.replace("""    if (Inbound < PrevInbound) {
        int died = PrevInbound - Inbound;
        PendingDrops += died;""",
"""    if (Inbound < PrevInbound) {
        int died = PrevInbound - Inbound;
        PendingDrops += died;
        LastDropAt = Now;""")
s = s.replace("double ClosestEver = -1.0;", "double ClosestEver = -1.0;\ndouble LastDropAt;")

# wave open / close sites
s = s.replace("""        if (Cur != null && ZeroRuns >= WAVE_GAP_TICKS) CloseWave();
""", "")
s = s.replace("""    if (ZeroRuns >= WAVE_GAP_TICKS) {                       // new engagement begins
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
    }""",
"""    if (ZeroRuns >= WAVE_GAP_TICKS) {   // a fresh engagement: reset the opening spread
        Respread();
        WaveCount++;
    }""")

s = re.sub(r'// Whatever is still pending when the wave closes.*?\n\}\n\n', '', s, count=1, flags=re.S)
s = s.replace("        if (Cur != null) CloseWave();\n", "")
s = re.sub(r'\s*int TotalDescents\(\) \{.*?\n\}\n', '\n', s, count=1, flags=re.S)
s = s.replace("int    _waveFiredAt, _waveDescAt;\n", "")

# per-round classification writes straight to the running counters
s = s.replace("""    ShotFlightSum += dt;
    if (Cur != null) Cur.FlightSum += dt;""", "    ShotFlightSum += dt;")
s = s.replace("""        ShotHits++;
        if (Cur != null) Cur.Hits++;
    } else {
        ShotFlyouts++;
        if (Cur != null) Cur.Flyouts++;
    }""",
"""        ShotHits++;
    } else {
        ShotFlyouts++;
    }""")
s = s.replace("""            OrphanEst += orph;
            if (Cur != null) Cur.Orphan += orph;""", "            OrphanEst += orph;")
s = s.replace("""        if (Cur != null) sb.Append("  [wave ").Append(Cur.N).Append(" live]");\n""", "")

# ---------------------------------------------------------------- periodic write
s = s.replace("    if (Debug) Report(); else Status();",
              "    if (Debug && Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }\n"
              "    if (Debug) Report(); else Status();")
s = s.replace("    if (Debug) WriteLog();\n", "")

# ---------------------------------------------------------------- merge arguments
s = re.sub(r'    if \(arg == "debug"\) \{.*?\n    \}\n    if \(arg == "rescan"\) \{ Discover\(\); \}\n',
'''    if (arg == "debug") {
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
''', s, count=1, flags=re.S)
s = re.sub(r'    if \(arg == "igc"\) \{.*?\n        return;\n    \}\n', '', s, count=1, flags=re.S)

s = s.replace("""//    rescan   force a weapon re-scan.
//    igc      force an IGC poll and print the net table now.""",
"""//             Toggling it on also forces a weapon rescan and an immediate IGC poll,
//             so it is the only diagnostic argument there is.""")

io.open(P, 'w', encoding='utf-8').write(s)
print('wave stripped=%s  periodic=%s  args_merged=%s'
      % ('class Wave' not in s, 'LogDue' in s, '"igc"' not in s))
