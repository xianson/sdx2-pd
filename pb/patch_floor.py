"""Give the ladder headroom above the weapon's minimum engagement range.

Rungs were a raw fraction of base range, so the bottom rung sat at 0.28 x base with no
regard for how low the weapon can actually shoot. WeaponCore enforces a per-weapon
MinTargetDistance, and it is NOT zero everywhere: SDX2 sets 1000 m on pdcOpaAdv. At a
4000 m base that leaves a 0.28 rung sitting at 1120 m -- a 120 m usable annulus, i.e.
effectively blind.

Reparameterised so rungs span floor..base rather than 0..base:

    range(rung) = FLOOR + (base - FLOOR) * RUNGS[rung]

The bottom rung is then FLOOR + 0.28*(base - FLOOR), always clear of the floor, and the
top rung is still exactly base. Rung SPACING is unchanged in proportion, so the measured
behaviour is preserved wherever the floor is small relative to base -- which is every
fast mount, all of which have MinTargetDistance 0.

MinTargetDistance is not exposed to a PB (there is no getter in the API; the terminal's
GetMinRange is a UI-side read of WConst), so FLOOR is a script constant. In practice the
one SDX2 weapon with a large minimum is flak, which the measured-RPM check already exempts
from the ladder entirely at 30 rpm.
"""
import io

P = r"D:\sdx2-pd\pb\FleetPD.cs"
s = io.open(P, encoding='utf-8').read()

s = s.replace("const double MIN_RANGE_M    = 300.0;  // never gate a mount below this",
              "// Floor the ladder sits ON, not merely clamps to. Raise it if your mounts have a\n"
              "// large MinTargetDistance -- WeaponCore enforces one per weapon and it is not\n"
              "// readable from a PB. SDX2's flak is 1000 m, but flak is exempted by the RPM check\n"
              "// long before this matters.\n"
              "const double RANGE_FLOOR_M  = 400.0;")

# every rung computation goes through one helper
s = s.replace("""        double want = m.BaseRange * RUNGS[m.Rung];
        if (want < MIN_RANGE_M) want = MIN_RANGE_M;
        SetRange(m, want);""",
"""        SetRange(m, RungRange(m, m.Rung));""")

s = s.replace("void SetRange(Mount m, double r) {",
              """// Rungs span FLOOR..base, so even the bottom rung keeps clear air above the weapon's
// minimum engagement range instead of crowding it.
double RungRange(Mount m, int rung) {
    double span = m.BaseRange - RANGE_FLOOR_M;
    if (span <= 0.0) return m.BaseRange;          // very short-ranged mount: leave it alone
    return RANGE_FLOOR_M + span * RUNGS[rung];
}

void SetRange(Mount m, double r) {""")

# the band->metres conversion must use the same scale
s = s.replace("        double r = m.AppliedRange > 0 ? m.AppliedRange * frac : 0.0;",
              "        double r = m.AppliedRange > 0 ? m.AppliedRange * frac : 0.0;  // bands are of the CURRENT gate")

io.open(P, 'w', encoding='utf-8').write(s)
print('floor: helper=%s const=%s leftover_min=%s'
      % ('double RungRange(' in s, 'RANGE_FLOOR_M' in s, 'MIN_RANGE_M' in s))
