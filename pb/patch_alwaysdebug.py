"""Diagnostics always on. Drop the debug flag. Never let VANILLA survive a reload.

Two changes.

1. Debug is gone as a concept -- the panel, the CustomData log, the block re-count and
   the per-round tracking all run unconditionally. One less thing to forget to switch on.

2. VANILLA is no longer persisted. It used to live in Storage, which survives a recompile
   AND a paste of a new script version, so a control run toggled once could silently
   continue into a later build with nothing on screen to say so. A passive control that
   outlives the session it was meant for is worse than no control. It now always starts
   ACTIVE and has to be asked for again.
"""
import io
import re

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()

# ---- 1. kill the flag and its persistence
s = s.replace("bool Vanilla;\nbool Debug;", """// VANILLA is deliberately NOT persisted: see the note in the header. Always starts
// ACTIVE so a control run cannot outlive the session it was collected for.
bool Vanilla;""")
s = s.replace("    Vanilla = Storage != null && Storage.Contains(\"vanilla\");\n"
              "    Debug = Storage != null && Storage.Contains(\"debug\");\n", "")
s = re.sub(r'\nvoid SaveFlags\(\) \{\n.*?\n\}\n', '\n', s, count=1, flags=re.S)
s = s.replace("        SaveFlags();\n", "")

# ---- 2. remove the debug argument entirely
s = re.sub(r'    if \(arg == "debug"\) \{.*?\n        return;\n    \}\n', '', s, count=1, flags=re.S)

# ---- 3. every gate becomes unconditional
s = s.replace("    if (Debug && Now >= DamagePollDue) {", "    if (Now >= DamagePollDue) {")
s = s.replace("    if (Debug && Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }\n"
              "    if (Debug) Report(); else Status();",
              "    if (Now >= LogDue) { LogDue = Now + LOG_EVERY_S; WriteLog(); }\n"
              "    Report();")
s = s.replace("        if (Debug) Report(); else Status();", "        Report();")
s = s.replace("        if (Debug && PrevInbound > 0) {", "        if (PrevInbound > 0) {")
s = s.replace("        if (Debug) {\n"
              "            var sh = new Shot();", "        {\n"
              "            var sh = new Shot();")
s = s.replace("    if (!Debug) return;\n    Shot rec;", "    Shot rec;")

# Status() is dead once Report always runs
s = re.sub(r'// Non-debug output: one line.*?\n\}\n\n', '', s, count=1, flags=re.S)

# ---- 4. header
s = s.replace("""//    debug    toggle diagnostics: per-mount Echo panel + a per-wave CustomData log.
//             OFF by default, because the panel and the block re-count that powers
//             leak estimation both cost work the fight does not need.
//             Toggling it on also forces a weapon rescan and an immediate IGC poll,
//             so it is the only diagnostic argument there is.""",
"""//    (diagnostics are ALWAYS ON: Echo panel, and a CustomData snapshot every 10 s)""")
s = s.replace("""//    vanilla  passive control: full range, no ladder, stats still recorded to their own
//             totals. 'active' resumes, 'toggle' flips. The in-game control for the
//             simulator's `no PB` baseline.""",
"""//    vanilla  passive control: full range, no ladder, stats still recorded to their own
//             totals. 'active' resumes, 'toggle' flips. The in-game control for the
//             simulator's `no PB` baseline. NOT persisted -- always starts ACTIVE, so a
//             control run can never silently outlive a recompile or a script update.""")

io.open(P, 'w', encoding='utf-8').write(s)
print('debug_gone=%s  status_gone=%s  storage_gone=%s'
      % ('Debug' not in s, 'void Status()' not in s, 'SaveFlags' not in s))
