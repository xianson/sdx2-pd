"""Make diagnostics opt-in. Default = the optimal net, running lean.

Everything expensive is now gated behind a runtime `debug` flag: the per-mount Echo panel,
the CustomData log, and the O(n) block re-count that powers leak estimation. With debug
off the script does only what it needs to fight -- poll inbound, gossip, set ranges.
"""
import io

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()

# ---- compile-time switches become runtime state, default OFF
s = s.replace(
    "const bool   DEBUG_PANEL    = true;\n"
    "const bool   CUSTOMDATA_LOG = true;   // write a per-wave log to this PB's CustomData\n",
    "// Diagnostics are OPT-IN: run the PB with the argument 'debug' to toggle them.\n"
    "// Default is the optimal net with no panel, no CustomData writes, and no block\n"
    "// re-count, so the normal path costs only what fighting requires.\n")

s = s.replace("bool Vanilla;", "bool Vanilla;\nbool Debug;")

# persist both flags
s = s.replace('    Vanilla = Storage != null && Storage.Contains("vanilla");',
              '    Vanilla = Storage != null && Storage.Contains("vanilla");\n'
              '    Debug = Storage != null && Storage.Contains("debug");')
s = s.replace('        Storage = Vanilla ? "vanilla" : "";',
              '        SaveFlags();')

# ---- the debug argument
s = s.replace('    if (arg == "rescan") { Discover(); }',
              '''    if (arg == "debug") {
        Debug = !Debug;
        SaveFlags();
        if (!Debug) Me.CustomData = "";
        Echo("debug -> " + (Debug ? "ON (panel + CustomData wave log)" : "OFF"));
        return;
    }
    if (arg == "rescan") { Discover(); }''')

# ---- gate the expensive block re-count
s = s.replace("    int lostNow = 0;\n    if (Now >= DamagePollDue) {",
              "    int lostNow = 0;\n    if (Debug && Now >= DamagePollDue) {")

# ---- gate every panel call
s = s.replace("if (DEBUG_PANEL) Report();", "if (Debug) Report(); else Status();")
s = s.replace("    if (CUSTOMDATA_LOG) WriteLog();", "    if (Debug) WriteLog();")

# ---- a one-line status for the non-debug path. A PB echoing nothing reads as crashed.
s = s.replace("void Report() {", '''// Non-debug output: one line, so the block is visibly alive without doing any work.
void Status() {
    Echo("FleetPD " + (Vanilla ? "[VANILLA] " : "") + Mounts.Count + " mounts, "
         + Inbound + " inbound, hull " + (HullOrdinal + 1) + "/" + HullCount
         + (Mounts.Count == 0 ? "  -- no weapons, run 'debug'" : "")
         + "\\n'debug' for diagnostics");
}

void SaveFlags() {
    Storage = (Vanilla ? "vanilla " : "") + (Debug ? "debug" : "");
}

void Report() {''')

# the idle path also needs a status line
s = s.replace("""        if (Cur != null && ZeroRuns >= WAVE_GAP_TICKS) CloseWave();
        if (Debug) Report(); else Status();""",
"""        if (Cur != null && ZeroRuns >= WAVE_GAP_TICKS) CloseWave();
        if (Debug) Report(); else Status();""")

# ---- stats are only meaningful with the sensor running; say so in the log header
s = s.replace('sb.AppendLine("A leaker that destroys nothing is missed; splash may be overcounted.");',
              'sb.AppendLine("A leaker that destroys nothing is missed; splash may be overcounted.");\n'
              '    sb.AppendLine("Only waves fought with debug ON are recorded.");')

io.open(P, 'w', encoding='utf-8').write(s)
print('debug gating: flag=%s status=%s gated_scan=%s'
      % ('bool Debug;' in s, 'void Status()' in s, 'if (Debug && Now >= DamagePollDue)' in s))
