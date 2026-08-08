// Emits ground-truth vectors from the VERBATIM WeaponCore code in extracted.cs
// and predict.cs. No game, no session — the extracted functions are driven with
// fed inputs and their outputs dumped as JSON for the Python port to be diffed against.
using System;
using System.Text;
using WcReal;
using VRageMath;

class Program
{
    static StringBuilder sb = new StringBuilder();
    static string D(double v) { return double.IsInfinity(v) || double.IsNaN(v) ? "null" : v.ToString("R"); }

    static void Main()
    {
        sb.Append("{\n");
        Rng();
        Deck();
        DeckPersistent();
        PredictVectors();
        Quartic();
        CollideVectors();
        FiringVectors();
        sb.Append("\"end\": true\n}\n");
        Console.Write(sb.ToString());
    }

    // ---------------------------------------------------- XorShiftRandomStruct
    static void Rng()
    {
        sb.Append("\"rng\": {\n");
        ulong[] seeds = { 1UL, 2UL, 42UL, 12345UL, 999983UL };
        for (int s = 0; s < seeds.Length; s++)
        {
            var r = new XorShiftRandomStruct(seeds[s]);
            sb.Append("  \"" + seeds[s] + "\": {\"u64\": [");
            for (int i = 0; i < 8; i++) { if (i > 0) sb.Append(","); sb.Append(r.NextUInt64()); }
            var r2 = new XorShiftRandomStruct(seeds[s]);
            sb.Append("], \"dbl\": [");
            for (int i = 0; i < 8; i++) { if (i > 0) sb.Append(","); sb.Append(D(r2.NextDouble())); }
            var r3 = new XorShiftRandomStruct(seeds[s]);
            sb.Append("], \"range_i_1_5\": [");
            for (int i = 0; i < 40; i++) { if (i > 0) sb.Append(","); sb.Append(r3.Range(1, 5)); }
            var r4 = new XorShiftRandomStruct(seeds[s]);
            sb.Append("], \"range_i_0_16\": [");
            for (int i = 0; i < 40; i++) { if (i > 0) sb.Append(","); sb.Append(r4.Range(0, 16)); }
            var r5 = new XorShiftRandomStruct(seeds[s]);
            sb.Append("], \"fair_16\": [");
            for (int i = 0; i < 20; i++) { if (i > 0) sb.Append(","); sb.Append(r5.FairRange(16UL)); }
            sb.Append("]}" + (s < seeds.Length - 1 ? "," : "") + "\n");
        }
        sb.Append("},\n");
    }

    // ------------------------------------------------------------ GetDeck
    static void Deck()
    {
        sb.Append("\"deck\": [\n");
        int[][] cases = {
            new[]{0,4,16}, new[]{4,4,16}, new[]{8,4,16}, new[]{12,4,16},
            new[]{0,4,8},  new[]{0,3,3},  new[]{0,1,3},  new[]{0,8,8},
            new[]{0,12,12},new[]{2,4,12}, new[]{0,4,0},  new[]{0,16,4}
        };
        for (int c = 0; c < cases.Length; c++)
        {
            int fc = cases[c][0], cs = cases[c][1], sh = cases[c][2];
            var rng = new XorShiftRandomStruct(777UL);
            int[] deck = new int[0];
            var o = AiDeck.GetDeck(ref deck, fc, cs, sh, ref rng);
            sb.Append("  {\"firstCard\":" + fc + ",\"cardsToSort\":" + cs
                      + ",\"cardsToShuffle\":" + sh + ",\"deck\":[");
            for (int i = 0; i < cs; i++) { if (i > 0) sb.Append(","); sb.Append(o[i]); }
            sb.Append("]}" + (c < cases.Length - 1 ? "," : "") + "\n");
        }
        sb.Append("],\n");
    }

    static void DeckPersistent()
    {
        sb.Append("\"deck_persistent\": [\n");
        var rng = new XorShiftRandomStruct(4242UL);
        int[] deck = new int[0];
        for (int call = 0; call < 6; call++)
        {
            int chunk = (4 * call) % 16;
            var o = AiDeck.GetDeck(ref deck, chunk, 4, 16, ref rng);
            sb.Append("  {\"call\":" + call + ",\"chunk\":" + chunk + ",\"deck\":[");
            for (int i = 0; i < 4; i++) { if (i > 0) sb.Append(","); sb.Append(o[i]); }
            sb.Append("]}" + (call < 5 ? "," : "") + "\n");
        }
        sb.Append("],\n");
    }

    // ------------------------- CrudeTti + CalculateAdvancedGridAimPrediction
    // Shooter at origin. Target at (R,0,0), crossing in +Z, lateral accel in +Y.
    // aim.Y is precisely the over-lead the chatter claim depends on.
    static void PredictVectors()
    {
        sb.Append("\"predict\": [\n");
        double[] ranges = { 10000, 8000, 6000, 4000, 2000 };
        double[] accels = { 0, 30, 60, 100, 200 };
        double[] cruises = { 0, 200, 550 };
        bool first = true;
        foreach (var R in ranges)
            foreach (var a in accels)
                foreach (var cr in cruises)
                {
                    var tPos = new Vector3D(R, 0, 0);
                    var tVel = new Vector3D(0, 0, cr);
                    var sPos = Vector3D.Zero;
                    var sVel = Vector3D.Zero;
                    var frame = TrajectoryPredictionShootingFrame.Calculate(ref tPos, ref tVel, ref sPos, ref sVel);
                    double crude;
                    bool okCrude = frame.CalculateCrudeTti(10000.0, out crude);
                    KineticState st; double t;
                    var tp = tPos; var tv = tVel; var sp = sPos; var sv = sVel;
                    bool found = Predict.CalculateAdvancedGridAimPrediction(
                        1000.0, new Vector3D(0, a, 0), tPos, Vector3D.Zero,
                        ref tp, ref tv, ref sp, ref sv, crude, 10000.0, false, out st, out t);
                    if (!first) sb.Append(",\n");
                    first = false;
                    sb.Append("  {\"R\":" + R + ",\"a\":" + a + ",\"cruise\":" + cr
                        + ",\"okCrude\":" + (okCrude ? "true" : "false")
                        + ",\"crudeTti\":" + D(crude)
                        + ",\"found\":" + (found ? "true" : "false")
                        + ",\"tti\":" + D(t)
                        + ",\"aim\":[" + D(st.Translation.X) + "," + D(st.Translation.Y)
                        + "," + D(st.Translation.Z) + "]}");
                }
        sb.Append("\n],\n");
    }

    // ------------------------------------------------------------ QuarticSolver
    static void Quartic()
    {
        sb.Append("\"quartic\": [\n");
        double[] ranges = { 10000, 8000, 6000, 4000, 2000 };
        double[] accels = { 0, 30, 60, 100, 200 };
        bool first = true;
        foreach (var R in ranges)
            foreach (var a in accels)
            {
                var dr = new Vector3D(R, 0, 0);
                var dv = new Vector3D(0, 0, 200);
                var ac = new Vector3D(0, a, 0);
                double tti = R / 10000.0;
                var coeff = new double[5];
                bool ok = Predict.QuarticSolver(ref tti, dr, dv, ac, 10000.0, coeff);
                if (!first) sb.Append(",\n");
                first = false;
                sb.Append("  {\"R\":" + R + ",\"a\":" + a + ",\"ok\":" + (ok ? "true" : "false")
                    + ",\"tti\":" + D(tti) + "}");
            }
        sb.Append("\n],\n");
    }

    // ------------------------------------------------ projectile-vs-projectile CCD
    static AmmoConst AC(bool line, double diam, double byBlock, float eol)
    {
        bool cl; double cs;
        Collide.CollisionShape(line, diam, out cl, out cs);
        var a = new AmmoConst();
        a.CollisionIsLine = cl; a.CollisionSize = cs;
        a.ByBlockHitRadius = byBlock; a.EndOfLifeRadius = eol;
        return a;
    }

    static void CollideVectors()
    {
        const double DS = 1.0 / 60.0;

        // ---- CollisionShape
        sb.Append("\"shape\": [\n");
        double[] diams = { 0.5, 2.2, 25, 80, 0, -1 };
        bool first = true;
        foreach (var isLine in new[] { true, false })
            foreach (var d in diams)
            {
                bool cl; double cs;
                Collide.CollisionShape(isLine, d, out cl, out cs);
                if (!first) sb.Append(",\n");
                first = false;
                sb.Append("  {\"shapeIsLine\":" + (isLine ? "true" : "false") + ",\"diameter\":" + D(d)
                    + ",\"isLine\":" + (cl ? "true" : "false") + ",\"size\":" + D(cs) + "}");
            }
        sb.Append("\n],\n");

        // ---- BulletRadius
        sb.Append("\"bullet_radius\": [\n");
        first = true;
        foreach (var isLine in new[] { true, false })
            foreach (var d in new double[] { 0.5, 25, 80 })
                foreach (var bb in new double[] { 0, 10, 200 })
                    foreach (var det in new[] { false, true })
                    {
                        var a = AC(isLine, d, bb, 33f);
                        if (!first) sb.Append(",\n");
                        first = false;
                        sb.Append("  {\"shapeIsLine\":" + (isLine ? "true" : "false") + ",\"diameter\":" + D(d)
                            + ",\"byBlock\":" + D(bb) + ",\"eol\":33,\"detonate\":" + (det ? "true" : "false")
                            + ",\"r\":" + D(Collide.BulletRadius(a, det)) + "}");
                    }
        sb.Append("\n],\n");

        // ---- IncludeRadius (isolates VRage's BoundingSphereD.Include)
        sb.Append("\"include\": [\n");
        first = true;
        double[][] inc = {
            new double[]{0,0,0, 0.5,  4.33,0,0, 1},
            new double[]{0,0,0, 80,   4.33,0,0, 1},
            new double[]{0,0,0, 25,   4.33,0,0, 1},
            new double[]{0,0,0, 0.5,  0,0,0, 1},
            new double[]{0,0,0, 2,    1,0,0, 0.25},
            new double[]{0,0,0, 0.1,  100,0,0, 1},
            new double[]{5,-3,2, 3,   5,-3,2, 3},
        };
        foreach (var v in inc)
        {
            var r = Collide.IncludeRadius(new Vector3D(v[0], v[1], v[2]), v[3],
                                          new Vector3D(v[4], v[5], v[6]), v[7]);
            if (!first) sb.Append(",\n");
            first = false;
            sb.Append("  {\"c0\":[" + D(v[0]) + "," + D(v[1]) + "," + D(v[2]) + "],\"r0\":" + D(v[3])
                + ",\"c1\":[" + D(v[4]) + "," + D(v[5]) + "," + D(v[6]) + "],\"r1\":" + D(v[7])
                + ",\"r\":" + D(r) + "}");
        }
        sb.Append("\n],\n");

        // ---- TargetRadius: bullet CollisionSize vs torpedo per-tick travel
        sb.Append("\"target_radius\": [\n");
        first = true;
        foreach (var bd in new double[] { 0.5, 25, 80 })
            foreach (var tline in new[] { true, false })
                foreach (var travel in new double[] { 0, 4.333333333333333, 21.666666666666668 })
                {
                    var bullet = AC(true, bd, 0, 0f);
                    var tgt = AC(tline, 2.2, 0, 0f);
                    var tp = new Vector3D(1000, 0, 0);
                    var tl = new Vector3D(1000 + travel, 0, 0);
                    if (!first) sb.Append(",\n");
                    first = false;
                    sb.Append("  {\"bulletDiam\":" + D(bd) + ",\"targetIsLine\":" + (tline ? "true" : "false")
                        + ",\"travel\":" + D(travel)
                        + ",\"r\":" + D(Collide.TargetRadius(bullet, tgt, tp, tl)) + "}");
                }
        sb.Append("\n],\n");

        // ---- Hits: a round crossing a torpedo at a range of miss distances.
        // Round flies +X at `vb`; torpedo flies -X at 260 offset `miss` in +Y.
        sb.Append("\"hits\": [\n");
        first = true;
        foreach (var bd in new double[] { 0.5, 25, 80 })
            foreach (var vb in new double[] { 3000, 4000 })
                foreach (var miss in new double[] { 0, 1, 3, 5, 20, 60, 100, 160, 200 })
                    foreach (var drift in new double[] { 0, 100 })
                    {
                        var bullet = AC(true, bd, 0, 0f);
                        var tgt = AC(true, 2.2, 0, 0f);
                        var pLast = new Vector3D(0, 0, 0);
                        var pPos = new Vector3D(vb * DS, 0, 0);
                        var tLast = new Vector3D(vb * DS * 0.5, miss, 0);
                        var tPos = tLast + new Vector3D(-260.0 * DS, 0, 0);
                        var br = Collide.BulletRadius(bullet, false);
                        var tr = Collide.TargetRadius(bullet, tgt, tPos, tLast);
                        double cad;
                        var hit = Collide.Hits(pLast, pPos, tLast, tPos,
                            new Vector3D(0, drift, 0), DS, br, tr, out cad);
                        if (!first) sb.Append(",\n");
                        first = false;
                        sb.Append("  {\"bulletDiam\":" + D(bd) + ",\"vb\":" + D(vb) + ",\"miss\":" + D(miss)
                            + ",\"drift\":" + D(drift) + ",\"br\":" + D(br) + ",\"tr\":" + D(tr)
                            + ",\"cad\":" + D(cad) + ",\"hit\":" + (hit ? "true" : "false") + "}");
                    }
        sb.Append("\n],\n");

        // ---- speed-matched degenerate branch (|dvdv| < 1e-6)
        sb.Append("\"hits_matched\": [\n");
        first = true;
        foreach (var miss in new double[] { 0, 1, 5, 100 })
        {
            var bullet = AC(true, 0.5, 0, 0f);
            var tgt = AC(true, 2.2, 0, 0f);
            var pLast = new Vector3D(0, 0, 0);
            var pPos = new Vector3D(50, 0, 0);
            var tLast = new Vector3D(0, miss, 0);
            var tPos = new Vector3D(50, miss, 0);
            var br = Collide.BulletRadius(bullet, false);
            var tr = Collide.TargetRadius(bullet, tgt, tPos, tLast);
            double cad;
            var hit = Collide.Hits(pLast, pPos, tLast, tPos, Vector3D.Zero, DS, br, tr, out cad);
            if (!first) sb.Append(",\n");
            first = false;
            sb.Append("  {\"miss\":" + D(miss) + ",\"br\":" + D(br) + ",\"tr\":" + D(tr)
                + ",\"cad\":" + D(cad) + ",\"hit\":" + (hit ? "true" : "false") + "}");
        }
        sb.Append("\n],\n");
    }

    // ==================================================================== firing model
    // Ground truth for heat / RoF degradation / overheat / reload / shot cadence, via the
    // verbatim extraction in firing.cs. Weapon parameters mirror hifi/weapons.py PDC_STATS.
    static FiringWeapon Mk(int rof, float heatPShot, int maxHeat, float sinkRate, float cooldown,
        bool degRof, bool prohibit, int reloadTicks, int magSize, int magsToLoad,
        int shotsInBurst, int delayAfterBurst, uint delayToFire, int barrels, int invMags,
        bool preload = true)
    {
        WcReal.Session.I = new WcReal.Session();
        var w = new FiringWeapon();
        w.System.WConst.RateOfFire = rof;
        w.System.WConst.HeatSinkRate = sinkRate;
        w.System.WConst.ReloadTime = reloadTicks;
        w.System.WConst.DelayAfterBurst = delayAfterBurst;
        w.System.Values.HardPoint.Loading.DelayAfterBurst = delayAfterBurst;
        w.System.Values.HardPoint.Loading.ShotsInBurst = shotsInBurst;
        w.System.Values.HardPoint.Loading.BarrelsPerShot = barrels;
        w.System.MaxHeat = maxHeat;
        w.Comp.MaxHeat = maxHeat;
        w.System.WepCoolDown = cooldown;
        w.System.DegRof = degRof;
        w.System.ProhibitCoolingWhenOff = prohibit;
        w.System.DelayToFire = delayToFire;
        w.HeatPShot = heatPShot;
        w.ActiveAmmoDef.AmmoDef.Const.MagazineSize = magSize;
        w.ActiveAmmoDef.AmmoDef.Const.MagsToLoad = magsToLoad;
        w.Comp.CoreInventory.MagsInInventory = invMags;
        w.CheckInventorySystem = false;
        w.InitFromSystem();
        if (preload)
        {
            // stand in for the first completed load of a battle-ready mount
            var loaded = magsToLoad <= invMags ? magsToLoad : invMags;
            w.Reload.MagsLoaded = loaded;
            w.ProtoWeaponAmmo.CurrentAmmo = loaded * magSize;
            w.Comp.CoreInventory.MagsInInventory -= loaded;
            w.Reload.CurrentMags = w.Comp.CoreInventory.MagsInInventory;
        }
        return w;
    }

    static FiringWeapon Mcrn(int invMags = 1000000)
    {
        return Mk(1800, 100f, 45000, 400f, 0.822f, true, true, 300, 120, 5, 0, 0, 0u, 1, invMags);
    }

    static bool InRanges(int t, int[][] ranges)
    {
        foreach (var r in ranges) if (t >= r[0] && t <= r[1]) return true;
        return false;
    }

    static void RunScenario(string name, FiringWeapon w, int[][] fireRanges, int ticks, int sampleEvery, bool last)
    {
        var events = new StringBuilder();
        var samples = new StringBuilder();
        bool ohPrev = w.PartState.Overheated, dgPrev = w.CurrentlyDegrading, ldPrev = w.Loading;
        bool firstEv = true, firstSm = true;
        long roundsAtOverheat = -1;
        for (int t = 1; t <= ticks; t++)
        {
            w.RunTick(InRanges(t, fireRanges));
            if (w.PartState.Overheated != ohPrev)
            {
                events.Append((firstEv ? "" : ",") + "[" + t + ",\"oh\"," + (w.PartState.Overheated ? 1 : 0) + "]");
                firstEv = false;
                if (w.PartState.Overheated) roundsAtOverheat = w.RoundsFired;
                ohPrev = w.PartState.Overheated;
            }
            if (w.CurrentlyDegrading != dgPrev)
            {
                events.Append((firstEv ? "" : ",") + "[" + t + ",\"dg\"," + (w.CurrentlyDegrading ? 1 : 0) + "]");
                firstEv = false;
                dgPrev = w.CurrentlyDegrading;
            }
            if (w.Loading != ldPrev)
            {
                events.Append((firstEv ? "" : ",") + "[" + t + ",\"rl\"," + (w.Loading ? 1 : 0) + "]");
                firstEv = false;
                ldPrev = w.Loading;
            }
            if (t % sampleEvery == 0 || t == ticks)
            {
                int flags = (w.PartState.Overheated ? 1 : 0) | (w.CurrentlyDegrading ? 2 : 0) | (w.Loading ? 4 : 0);
                samples.Append((firstSm ? "" : ",") + "[" + t + "," + w.RoundsFired + "," + w.ProtoWeaponAmmo.CurrentAmmo
                    + "," + D(w.PartState.Heat) + "," + w.RateOfFire + "," + flags + "]");
                firstSm = false;
            }
        }
        sb.Append("  {\"name\":\"" + name + "\",\"fire\":" + Ranges(fireRanges) + ",\"ticks\":" + ticks
            + ",\"sampleEvery\":" + sampleEvery
            + ",\"samples\":[" + samples + "],\"events\":[" + events + "]"
            + ",\"totals\":{\"rounds\":" + w.RoundsFired + ",\"projectiles\":" + w.ProjectilesEmitted
            + ",\"roundsAtOverheat\":" + roundsAtOverheat
            + ",\"heatPasses\":" + w.HeatPasses
            + ",\"heatPassGapMin\":" + (w.HeatPassGapMin == int.MaxValue ? 0 : w.HeatPassGapMin)
            + ",\"heatPassGapMax\":" + w.HeatPassGapMax + "}}" + (last ? "" : ",") + "\n");
    }

    static string Ranges(int[][] r)
    {
        var b = new StringBuilder("[");
        for (int i = 0; i < r.Length; i++) b.Append((i > 0 ? "," : "") + "[" + r[i][0] + "," + r[i][1] + "]");
        return b.Append("]").ToString();
    }

    static void FiringVectors()
    {
        // ---- TicksPerShot for every definable RateOfFire (WeaponController.cs:376-378)
        sb.Append("\"tps_sweep\": [");
        {
            var w = Mcrn();
            for (int rof = 1; rof <= 3600; rof++)
            {
                w.System.WConst.RateOfFire = rof;
                w.UpdateRof();
                sb.Append((rof > 1 ? "," : "") + w.TicksPerShot);
            }
        }
        sb.Append("],\n");

        // ---- degraded RoF grid (WeaponController.cs:365-378), incl. heat above MaxHeat
        sb.Append("\"update_rof\": [\n");
        {
            int[] rofs = { 30, 80, 900, 1200, 1800, 2000, 3000 };
            bool first = true;
            foreach (var rof in rofs)
            {
                for (int i = 0; i <= 24; i++)
                {
                    float heat = 45000f * i / 20f;   // 0 .. 1.2 x MaxHeat
                    var w = Mcrn();
                    w.System.WConst.RateOfFire = rof;
                    w.PartState.Heat = heat;
                    w.CurrentlyDegrading = true;
                    w.UpdateRof();
                    if (!first) sb.Append(",\n");
                    first = false;
                    sb.Append("  {\"rof\":" + rof + ",\"heat\":" + D(heat) + ",\"rateOfFire\":" + w.RateOfFire
                        + ",\"tps\":" + w.TicksPerShot + "}");
                }
            }
        }
        sb.Append("\n],\n");

        // ---- single UpdateWeaponHeat pass (WeaponController.cs:260-363)
        sb.Append("\"heat_pass\": [\n");
        {
            float[] heats = { 0f, 50f, 133f, 133.34f, 17999f, 18000f, 18100f, 35999f, 36000f,
                              36989f, 36990f, 36991f, 37000f, 44999f, 45000f, 45800f, 50000f };
            bool first = true;
            foreach (var h in heats)
                foreach (var ov in new[] { false, true })
                    foreach (var dg in new[] { false, true })
                    {
                        var w = Mcrn();
                        w.PartState.Heat = h;
                        w.Comp.CurrentHeat = h;
                        w.PartState.Overheated = ov;
                        w.CurrentlyDegrading = dg;
                        w.UpdateWeaponHeat(null);
                        if (!first) sb.Append(",\n");
                        first = false;
                        sb.Append("  {\"h0\":" + D(h) + ",\"ov0\":" + (ov ? 1 : 0) + ",\"dg0\":" + (dg ? 1 : 0)
                            + ",\"h1\":" + D(w.PartState.Heat) + ",\"ov1\":" + (w.PartState.Overheated ? 1 : 0)
                            + ",\"dg1\":" + (w.CurrentlyDegrading ? 1 : 0) + ",\"rof1\":" + w.RateOfFire + "}");
                    }
        }
        sb.Append("\n],\n");

        // ---- ProhibitCoolingWhenOff x Cube.IsWorking gate (WeaponController.cs:268)
        sb.Append("\"cool_gate\": [\n");
        {
            bool first = true;
            foreach (var prohibit in new[] { false, true })
                foreach (var working in new[] { false, true })
                {
                    var w = Mcrn();
                    w.System.ProhibitCoolingWhenOff = prohibit;
                    w.Comp.Cube.IsWorking = working;
                    w.PartState.Heat = 30000f;
                    w.Comp.CurrentHeat = 30000f;
                    w.UpdateWeaponHeat(null);
                    if (!first) sb.Append(",\n");
                    first = false;
                    sb.Append("  {\"prohibit\":" + (prohibit ? 1 : 0) + ",\"working\":" + (working ? 1 : 0)
                        + ",\"h1\":" + D(w.PartState.Heat) + "}");
                }
        }
        sb.Append("\n],\n");

        // ---- tick-loop scenarios
        sb.Append("\"firing_scenarios\": [\n");

        RunScenario("mcrn_window", Mcrn(), new[] { new[] { 1, 144 } }, 150, 12, false);
        RunScenario("mcrn_sustained", Mcrn(), new[] { new[] { 1, 7200 } }, 7200, 60, false);
        RunScenario("mcrn_gap6", Mcrn(), new[] { new[] { 1, 180 }, new[] { 541, 720 } }, 720, 30, false);
        RunScenario("mcrn_gap15", Mcrn(), new[] { new[] { 1, 180 }, new[] { 1081, 1260 } }, 1260, 30, false);
        RunScenario("mcrn_gap60", Mcrn(), new[] { new[] { 1, 180 }, new[] { 3781, 3960 } }, 3960, 60, false);

        {   // overheat grace: primed just below MaxHeat, watch the shots that land after Overheated
            var w = Mcrn();
            w.PrimeHeat(44000f);
            RunScenario("mcrn_overheat_grace", w, new[] { new[] { 1, 600 } }, 600, 10, false);
        }
        {   // pure reload duty cycle: heat removed from the picture
            var w = Mk(1800, 0f, 45000, 400f, 0.822f, true, true, 300, 120, 5, 0, 0, 0u, 1, 1000000);
            RunScenario("mcrn_reload_pure", w, new[] { new[] { 1, 3600 } }, 3600, 30, false);
        }
        {   // finite inventory: 7 mags total, 5 preloaded, 2 left -> short second load, then dry
            var w = Mk(1800, 0f, 45000, 400f, 0.822f, true, true, 300, 120, 5, 0, 0, 0u, 1, 7);
            RunScenario("mcrn_mags_finite", w, new[] { new[] { 1, 2400 } }, 2400, 30, false);
        }
        // PdcPgenAdv (PDC50mmLight): burst 20 / delay 15, DegradeRof=false, no cooling prohibition
        RunScenario("pgen_burst",
            Mk(3000, 100f, 70000, 45000f, 0.95f, false, false, 30, 600, 5, 20, 15, 0u, 1, 1000000),
            new[] { new[] { 1, 1200 } }, 1200, 30, false);

        {   // cooling gate scenarios: primed, never firing
            var w = Mcrn(); w.PrimeHeat(30000f); w.Comp.Cube.IsWorking = false;
            RunScenario("cool_prohibit_off", w, new int[0][], 600, 60, false);
        }
        {
            var w = Mcrn(); w.PrimeHeat(30000f); w.Comp.Cube.IsWorking = true;
            RunScenario("cool_prohibit_on", w, new int[0][], 600, 60, false);
        }
        {
            var w = Mcrn(); w.System.ProhibitCoolingWhenOff = false; w.PrimeHeat(30000f); w.Comp.Cube.IsWorking = false;
            RunScenario("cool_noprohibit_off", w, new int[0][], 600, 60, false);
        }
        // PdcMcrnAdv (PDC50mmHeavy): rof 80 -> the integer cadence dominates a 2.4 s window
        RunScenario("mcrnadv_window",
            Mk(80, 1200f, 45000, 400f, 0.822f, true, true, 300, 600, 1, 0, 0, 0u, 1, 1000000),
            new[] { new[] { 1, 144 } }, 150, 12, false);
        // PdcOpaAdv (flak parent): DelayUntilFire 12 prefire ticks
        RunScenario("opaadv_prefire",
            Mk(30, 100f, 18000, 160f, 0.822f, true, true, 300, 600, 1, 0, 0, 12u, 1, 1000000),
            new[] { new[] { 1, 300 } }, 300, 30, true);

        sb.Append("],\n");
    }
}
