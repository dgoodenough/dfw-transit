using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;

public class DemandEngine
{
    // ---- tunables ----
    const double SpeedMetro = 32.0, SpeedBrt = 22.0, SpeedCommuter = 50.0; // km/h avg incl stops
    const double WalkKmh = 4.8, BoardMin = 6.0, XferWalkMin = 6.0;
    const double WalkAccessKm = 1.5, PnrKm = 8.0, PnrKmh = 40.0, PnrPenaltyMin = 5.0;
    // drive baseline = PEAK door-to-door (DFW peak avg ~38 km/h incl. signals) + parking/terminal time
    const double DriveFactor = 1.35, DriveKmh = 38.0, DriveTerminalMin = 8.0;
    const double CompetRatio = 1.3, CompetSlackMin = 5.0, MaxTransitMin = 90.0;

    static double Hav(double la1, double lo1, double la2, double lo2)
    {
        double R = 6371.0, p = Math.PI / 180.0;
        double dla = (la2 - la1) * p, dlo = (lo2 - lo1) * p;
        double a = Math.Sin(dla / 2) * Math.Sin(dla / 2) + Math.Cos(la1 * p) * Math.Cos(la2 * p) * Math.Sin(dlo / 2) * Math.Sin(dlo / 2);
        return R * 2 * Math.Atan2(Math.Sqrt(a), Math.Sqrt(1 - a));
    }

    // stations
    List<string> stId = new List<string>(); List<double> stLat = new List<double>(); List<double> stLon = new List<double>();
    List<bool> stPnr = new List<bool>(); Dictionary<string, int> stIdx = new Dictionary<string, int>();
    // graph nodes: 0..S-1 street nodes; line-nodes appended
    int S;
    Dictionary<string, int> lineNode = new Dictionary<string, int>(); // "stIdx|line" -> node
    List<List<int>> adjN = new List<List<int>>(); List<List<double>> adjW = new List<List<double>>();
    List<string> nodeLine = new List<string>(); // node -> line name ("" for street)
    public Dictionary<string, double> lineLenKm = new Dictionary<string, double>();
    public Dictionary<string, string> lineMode = new Dictionary<string, string>();

    void AddEdge(int a, int b, double w) { adjN[a].Add(b); adjW[a].Add(w); }
    int GetLineNode(int st, string line)
    {
        string key = st.ToString() + "|" + line;
        int n;
        if (lineNode.TryGetValue(key, out n)) return n;
        n = adjN.Count; lineNode[key] = n;
        adjN.Add(new List<int>()); adjW.Add(new List<double>()); nodeLine.Add(line);
        AddEdge(S0(st), n, BoardMin); // board
        AddEdge(n, S0(st), 0.0);      // alight
        return n;
    }
    int S0(int st) { return st; }

    public string Load(string stationsCsv, string segmentsCsv, string slCsv, bool existingOnly)
    {
        // stations
        var lines = File.ReadAllLines(stationsCsv);
        var hdr = lines[0].Split(','); int iId = Array.IndexOf(hdr, "\"station_id\""), iLat = Array.IndexOf(hdr, "\"lat\""), iLon = Array.IndexOf(hdr, "\"lon\""), iMode = Array.IndexOf(hdr, "\"mode\""), iYr = Array.IndexOf(hdr, "\"year_opens\"");
        for (int r = 1; r < lines.Length; r++)
        {
            var c = SplitCsv(lines[r]);
            if (existingOnly && int.Parse(c[iYr]) > 2025) continue;
            stIdx[c[iId]] = stId.Count; stId.Add(c[iId]);
            stLat.Add(double.Parse(c[iLat], CultureInfo.InvariantCulture)); stLon.Add(double.Parse(c[iLon], CultureInfo.InvariantCulture));
            stPnr.Add(c[iMode] == "commuter");
        }
        S = stId.Count;
        for (int i = 0; i < S; i++) { adjN.Add(new List<int>()); adjW.Add(new List<double>()); nodeLine.Add(""); }
        // termini -> P&R eligible
        var sl = File.ReadAllLines(slCsv); var sh = sl[0].Split(',');
        int iLid = Array.IndexOf(sh, "\"line_id\""), iSeq = Array.IndexOf(sh, "\"seq\""), iSid = Array.IndexOf(sh, "\"station_id\"");
        var bySeq = new Dictionary<string, List<KeyValuePair<int, string>>>();
        for (int r = 1; r < sl.Length; r++)
        {
            var c = SplitCsv(sl[r]);
            if (!bySeq.ContainsKey(c[iLid])) bySeq[c[iLid]] = new List<KeyValuePair<int, string>>();
            bySeq[c[iLid]].Add(new KeyValuePair<int, string>(int.Parse(c[iSeq]), c[iSid]));
        }
        foreach (var kv in bySeq)
        {
            kv.Value.Sort(delegate(KeyValuePair<int, string> a, KeyValuePair<int, string> b) { return a.Key.CompareTo(b.Key); });
            int t;
            if (stIdx.TryGetValue(kv.Value[0].Value, out t)) stPnr[t] = true;
            if (stIdx.TryGetValue(kv.Value[kv.Value.Count - 1].Value, out t)) stPnr[t] = true;
        }
        // segments -> ride edges
        var seg = File.ReadAllLines(segmentsCsv); var gh = seg[0].Split(',');
        int iLine = Array.IndexOf(gh, "\"line\""), iSm = Array.IndexOf(gh, "\"mode\""), iF = Array.IndexOf(gh, "\"from_id\""), iT = Array.IndexOf(gh, "\"to_id\""), iY = Array.IndexOf(gh, "\"year_opens\""), iW = Array.IndexOf(gh, "\"geometry_wkt\"");
        int iSegLid = Array.IndexOf(gh, "\"line_id\"");
        int nRide = 0;
        for (int r = 1; r < seg.Length; r++)
        {
            var c = SplitCsv(seg[r]);
            int fi, ti;
            if (!stIdx.TryGetValue(c[iF], out fi) || !stIdx.TryGetValue(c[iT], out ti)) continue;
            // length from WKT
            string wkt = c[iW].Replace("LINESTRING (", "").Replace(")", "");
            var pts = wkt.Split(','); double len = 0; double pla = 0, plo = 0; bool first = true;
            foreach (var p in pts)
            {
                var xy = p.Trim().Split(' ');
                double lo = double.Parse(xy[0], CultureInfo.InvariantCulture), la = double.Parse(xy[1], CultureInfo.InvariantCulture);
                if (!first) len += Hav(pla, plo, la, lo);
                pla = la; plo = lo; first = false;
            }
            var lns = c[iLine].Split(';'); var yrs = c[iY].Split(';');
            string mode = c[iSm];
            string lid = c[iSegLid];
            double speed = mode == "commuter" ? SpeedCommuter : (mode == "brt" ? SpeedBrt : SpeedMetro);
            for (int k = 0; k < lns.Length; k++)
            {
                int y = int.Parse(yrs[Math.Min(k, yrs.Length - 1)]);
                if (existingOnly && y > 2025) continue;
                string ln = lid.Length > 0 ? lid + ":" + lns[k] : lns[k];   // disambiguate name collisions (two 'Silver's)
                if (!lineLenKm.ContainsKey(ln)) { lineLenKm[ln] = 0; lineMode[ln] = mode; }
                lineLenKm[ln] += len;
                double t = len / speed * 60.0;
                int a = GetLineNode(fi, ln), b = GetLineNode(ti, ln);
                AddEdge(a, b, t); AddEdge(b, a, t); nRide += 2;
            }
        }
        // cross-station walk transfers (<=400m)
        int nXfer = 0;
        for (int i = 0; i < S; i++)
            for (int j = i + 1; j < S; j++)
            {
                if (Math.Abs(stLat[i] - stLat[j]) > 0.005 || Math.Abs(stLon[i] - stLon[j]) > 0.006) continue;
                if (Hav(stLat[i], stLon[i], stLat[j], stLon[j]) <= 0.4) { AddEdge(i, j, XferWalkMin); AddEdge(j, i, XferWalkMin); nXfer += 2; }
            }
        return string.Format("stations={0} nodes={1} rideEdges={2} xferEdges={3}", S, adjN.Count, nRide, nXfer);
    }

    static string[] SplitCsv(string line)
    {
        var outp = new List<string>(); bool q = false; var cur = new System.Text.StringBuilder();
        foreach (char ch in line)
        {
            if (ch == '"') q = !q;
            else if (ch == ',' && !q) { outp.Add(cur.ToString()); cur.Length = 0; }
            else cur.Append(ch);
        }
        outp.Add(cur.ToString());
        return outp.ToArray();
    }

    double[][] dist; int[][] pred;
    public void AllPairs()
    {
        int N = adjN.Count;
        dist = new double[S][]; pred = new int[S][];
        for (int src = 0; src < S; src++)
        {
            var d = new double[N]; var pr = new int[N]; var done = new bool[N];
            for (int i = 0; i < N; i++) { d[i] = double.MaxValue; pr[i] = -1; }
            d[src] = 0;
            var heap = new SortedSet<long>(); // encode dist(ms int)*1e6 + node
            heap.Add((long)0 * 1000000L + src);
            while (heap.Count > 0)
            {
                long top = heap.Min; heap.Remove(top);
                int u = (int)(top % 1000000L);
                if (done[u]) continue; done[u] = true;
                var an = adjN[u]; var aw = adjW[u];
                for (int e = 0; e < an.Count; e++)
                {
                    int v = an[e]; double nd = d[u] + aw[e];
                    if (nd < d[v] - 1e-9)
                    {
                        d[v] = nd; pr[v] = u;
                        heap.Add((long)Math.Round(nd * 100) * 1000000L + v);
                    }
                }
            }
            dist[src] = d; pred[src] = pr;
        }
    }

    // tract access
    List<double> trLat = new List<double>(); List<double> trLon = new List<double>(); Dictionary<string, int> trIdx = new Dictionary<string, int>();
    List<int[]> accSt = new List<int[]>(); List<double[]> accT = new List<double[]>();   // origin (walk+P&R)
    List<int[]> egrSt = new List<int[]>(); List<double[]> egrT = new List<double[]>();   // dest (walk only)
    public string LoadTracts(string tractsCsv)
    {
        var lines = File.ReadAllLines(tractsCsv);
        for (int r = 1; r < lines.Length; r++)
        {
            var c = lines[r].Split(',');
            trIdx[c[0]] = trLat.Count;
            double la = double.Parse(c[1], CultureInfo.InvariantCulture), lo = double.Parse(c[2], CultureInfo.InvariantCulture);
            trLat.Add(la); trLon.Add(lo);
            var aS = new List<int>(); var aT = new List<double>(); var eS = new List<int>(); var eT = new List<double>();
            for (int s = 0; s < S; s++)
            {
                if (Math.Abs(stLat[s] - la) > 0.09 || Math.Abs(stLon[s] - lo) > 0.11) continue;
                double dk = Hav(la, lo, stLat[s], stLon[s]);
                if (dk <= WalkAccessKm) { double t = dk / WalkKmh * 60; aS.Add(s); aT.Add(t); eS.Add(s); eT.Add(t); }
                else if (dk <= PnrKm && stPnr[s]) { aS.Add(s); aT.Add(dk * 1.3 / PnrKmh * 60 + PnrPenaltyMin); }
            }
            // keep best 5 by time
            Trim(aS, aT, 5); Trim(eS, eT, 5);
            accSt.Add(aS.ToArray()); accT.Add(aT.ToArray()); egrSt.Add(eS.ToArray()); egrT.Add(eT.ToArray());
        }
        return "tracts=" + trLat.Count;
    }
    static void Trim(List<int> s, List<double> t, int k)
    {
        while (s.Count > k)
        {
            int worst = 0; for (int i = 1; i < t.Count; i++) if (t[i] > t[worst]) worst = i;
            s.RemoveAt(worst); t.RemoveAt(worst);
        }
    }

    public Dictionary<string, double> lineFlow = new Dictionary<string, double>();
    public double totFlow = 0, compFlow = 0, evalFlow = 0;
    public Dictionary<string, double> missing = new Dictionary<string, double>();
    public string RunOD(string odCsv, bool attribute)
    {
        lineFlow.Clear(); totFlow = 0; compFlow = 0; evalFlow = 0; missing.Clear();
        var pathLines = new HashSet<string>();
        using (var sr = new StreamReader(odCsv))
        {
            sr.ReadLine();
            string line;
            while ((line = sr.ReadLine()) != null)
            {
                var c = line.Split(',');
                int o, dd;
                double f = double.Parse(c[2], CultureInfo.InvariantCulture);
                totFlow += f;
                if (!trIdx.TryGetValue(c[0], out o) || !trIdx.TryGetValue(c[1], out dd)) continue;
                if (o == dd) continue;
                double dk = Hav(trLat[o], trLon[o], trLat[dd], trLon[dd]);
                if (dk < 2.0) continue; // short trips: transit never the answer; excluded honestly
                evalFlow += f;
                double drive = dk * DriveFactor / DriveKmh * 60 + DriveTerminalMin;
                var aS = accSt[o]; var aT = accT[o]; var eS = egrSt[dd]; var eT = egrT[dd];
                double best = double.MaxValue; int bo = -1, bd = -1;
                for (int i = 0; i < aS.Length; i++)
                {
                    var drow = dist[aS[i]];
                    for (int j = 0; j < eS.Length; j++)
                    {
                        if (aS[i] == eS[j]) continue;
                        double t = aT[i] + drow[eS[j]] + eT[j];
                        if (t < best) { best = t; bo = aS[i]; bd = eS[j]; }
                    }
                }
                bool comp = best <= Math.Min(CompetRatio * drive + CompetSlackMin, MaxTransitMin);
                if (comp)
                {
                    compFlow += f;
                    if (attribute && bo >= 0)
                    {
                        pathLines.Clear();
                        int cur = bd; var pr = pred[bo]; int guard = 0;
                        while (cur != bo && cur >= 0 && guard++ < 5000) { if (nodeLine[cur].Length > 0) pathLines.Add(nodeLine[cur]); cur = pr[cur]; }
                        foreach (var ln in pathLines)
                        { double v; lineFlow.TryGetValue(ln, out v); lineFlow[ln] = v + f; }
                    }
                }
                else if (dk >= 8.0 && f >= 15)
                {
                    string key = string.Format(CultureInfo.InvariantCulture, "{0:F1},{1:F1}>{2:F1},{3:F1}",
                        Math.Round(trLat[o] * 10) / 10, Math.Round(trLon[o] * 10) / 10, Math.Round(trLat[dd] * 10) / 10, Math.Round(trLon[dd] * 10) / 10);
                    double v; missing.TryGetValue(key, out v); missing[key] = v + f;
                }
            }
        }
        return string.Format(CultureInfo.InvariantCulture, "total={0:F0} evaluated(>2km)={1:F0} competitive={2:F0} ({3:P1} of evaluated)", totFlow, evalFlow, compFlow, compFlow / evalFlow);
    }
}
