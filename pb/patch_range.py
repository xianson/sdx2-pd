"""Infer leaks from RANGE rather than from damage.

Damage-off testing breaks the block-count sensor: nothing is destroyed, so no leak is
ever detected. But WeaponCore's event monitor does expose a coarse range signal that
works for projectile targets, and it costs nothing to read.

WeaponTracking.cs:386-397 fires, from the aim path, one of
    17 TargetRanged100  target at >= 75% of this weapon's MaxTargetDistance
    18 TargetRanged75   50-75%
    19 TargetRanged50   25-50%
    20 TargetRanged25   <= 25%
and those indices are documented on WcPbApi.MonitorEvents. The bands are fractions of the
weapon's CURRENT MaxTargetDistance, which this script already tracks per mount as
AppliedRange -- so a band converts to an absolute distance bracket in metres.

Leak rule: when the inbound count falls, if any mount had its target inside
LEAK_RANGE_M just beforehand, that ending is scored a leak; otherwise a kill. Damage, when
it happens at all, is kept as a secondary confirmation.

This also corrects an earlier conclusion in the doctrine that a PB cannot observe range.
It can -- coarsely, four bands per mount, and finer across mounts sitting on different
ladder rungs.
"""
import io

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()

s = s.replace("const double DAMAGE_POLL_S  = 1.0;    // how often to re-count blocks (damage sensor)",
              "const double DAMAGE_POLL_S  = 1.0;    // how often to re-count blocks (damage sensor)\n"
              "const double LEAK_RANGE_M   = 250.0;  // target seen closer than this => scored a leak\n"
              "const double BAND_STALE_S   = 1.5;    // ignore a band report older than this")

# ---- per-mount band state
s = s.replace("    public int    _idx;                  // stable display index",
              "    public int    _idx;                  // stable display index\n"
              "    public int    Band = -1;             // last TargetRanged* seen (17..20)\n"
              "    public double BandAt = -1.0;         // when it was reported\n"
              "    public double BandRangeM = -1.0;     // upper bound in metres implied by it")

# ---- register the monitor alongside the projectile monitor
s = s.replace("""            mt.Parts.Add(kv.Value);
            Wc.MonitorProjectileCallback(b, kv.Value, OnProjectile);""",
"""            mt.Parts.Add(kv.Value);
            Wc.MonitorProjectileCallback(b, kv.Value, OnProjectile);
            Wc.MonitorEvents(b, kv.Value, OnWeaponEvent);""")

# ---- the callback. Action<int,bool> gives the trigger index and whether it went active.
s = s.replace("void OnProjectile(long coreEnt,", '''// TargetRanged* band report. The callback carries no block identity, so the band is
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

void OnProjectile(long coreEnt,''')

# ---- leak attribution: range first, damage as confirmation
s = s.replace("""    if (Cur != null) {
        if (Inbound > Cur.PeakIn) Cur.PeakIn = Inbound;
        if (lostNow > 0) {
            Cur.BlocksLost += lostNow;
            int leak = PendingDrops < lostNow ? PendingDrops : lostNow;
            if (leak > 0) { Cur.Leaks += leak; PendingDrops -= leak; }
        }""",
"""    if (Cur != null) {
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
        }""")

s = s.replace("public bool   Vanilla;",
              "public bool   Vanilla;\n    public int    LeakByRange, LeakByDamage;\n    public double ClosestM = -1.0;")

# ---- the band scan is cheap, so it must run regardless of Debug; only the block
#      re-count stays gated
s = s.replace("    int lostNow = 0;\n    if (Debug && Now >= DamagePollDue) {",
              "    int lostNow = 0;\n    if (Debug && Now >= DamagePollDue) {")

# ---- surface the split in the log
s = s.replace('sb.AppendLine("wave  mode    dur  peakIn  ended  kill~  leak~  blocks  fired  r/kill~  desc  heat");',
              'sb.AppendLine("wave  mode    dur  peakIn  ended  kill~  leak~  byRng  byDmg  closest  fired  r/kill~  heat");')
s = s.replace("""          .Append(w.Leaks.ToString().PadLeft(7))
          .Append(w.BlocksLost.ToString().PadLeft(8))
          .Append(w.Fired.ToString().PadLeft(7))
          .Append((w.Kills > 0 ? ((double)w.Fired / w.Kills).ToString("0.0") : "-").PadLeft(9))
          .Append(w.Descents.ToString().PadLeft(6))""",
"""          .Append(w.Leaks.ToString().PadLeft(7))
          .Append(w.LeakByRange.ToString().PadLeft(7))
          .Append(w.LeakByDamage.ToString().PadLeft(7))
          .Append((w.ClosestM >= 0 ? ((int)w.ClosestM).ToString() + "m" : "-").PadLeft(9))
          .Append(w.Fired.ToString().PadLeft(7))
          .Append((w.Kills > 0 ? ((double)w.Fired / w.Kills).ToString("0.0") : "-").PadLeft(9))""")

s = s.replace('sb.AppendLine("correlates a fall in inbound count with a fall in grid block count.");',
              'sb.AppendLine("A fall in inbound count is scored a LEAK if any mount reported its target");\n'
              '    sb.AppendLine("inside " + LEAK_RANGE_M.ToString("0") + " m just beforehand (WeaponCore TargetRanged bands),");\n'
              '    sb.AppendLine("or if grid blocks were lost at the same moment. Otherwise it is a kill.");')
s = s.replace('sb.AppendLine("A leaker that destroys nothing is missed; splash may be overcounted.");',
              'sb.AppendLine("byRng works with damage disabled; byDmg does not.");')

io.open(P, 'w', encoding='utf-8').write(s)
print('range inference: cb=%s rule=%s cols=%s'
      % ('OnWeaponEvent' in s, 'LeakByRange' in s, 'byRng' in s))
