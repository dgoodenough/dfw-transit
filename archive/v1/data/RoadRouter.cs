using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Text.RegularExpressions;

public class RoadRouter
{
    const double MLAT = 110540.0;
    static double MLON = 111320.0 * Math.Cos(32.8 * Math.PI / 180.0);
    static double Dm(double alon, double alat, double blon, double blat)
    { double dx = (alon - blon) * MLON, dy = (alat - blat) * MLAT; return Math.Sqrt(dx * dx + dy * dy); }

    Dictionary<long, int> nodeIdx = new Dictionary<long, int>();
    List<double> nLon = new List<double>(); List<double> nLat = new List<double>();
    List<List<int>> adj = new List<List<int>>(); List<List<double>> adjW = new List<List<double>>();
    Dictionary<long, List<int>> grid = new Dictionary<long, List<int>>();
    const double CELL = 0.01;

    long Key(double lon, double lat) { return ((long)Math.Round(lon * 100000.0)) * 10000000L + (long)Math.Round((lat + 90) * 100000.0); }
    long GKey(double lon, double lat) { return ((long)Math.Floor(lon / CELL)) * 1000000L + (long)Math.Floor((lat + 90) / CELL); }

    int GetNode(double lon, double lat)
    {
        long k = Key(lon, lat); int i;
        if (nodeIdx.TryGetValue(k, out i)) return i;
        i = nLon.Count; nodeIdx[k] = i; nLon.Add(lon); nLat.Add(lat);
        adj.Add(new List<int>()); adjW.Add(new List<double>());
        long gk = GKey(lon, lat);
        if (!grid.ContainsKey(gk)) grid[gk] = new List<int>();
        grid[gk].Add(i);
        return i;
    }

    public string Load(string[] paths)
    {
        var rxGeom = new Regex("\"geometry\"\\s*:\\s*\\[([^\\]]*)\\]", RegexOptions.Compiled);
        var rxPt = new Regex("\"lat\"\\s*:\\s*(-?\\d+\\.\\d+)\\s*,\\s*\"lon\"\\s*:\\s*(-?\\d+\\.\\d+)", RegexOptions.Compiled);
        int nWays = 0, nEdges = 0;
        foreach (var p in paths)
        {
            string raw = File.ReadAllText(p);
            foreach (Match gm in rxGeom.Matches(raw))
            {
                nWays++;
                int prev = -1;
                foreach (Match pm in rxPt.Matches(gm.Groups[1].Value))
                {
                    double la = double.Parse(pm.Groups[1].Value, CultureInfo.InvariantCulture);
                    double lo = double.Parse(pm.Groups[2].Value, CultureInfo.InvariantCulture);
                    int cur = GetNode(lo, la);
                    if (prev >= 0 && prev != cur)
                    {
                        double w = Dm(nLon[prev], nLat[prev], lo, la);
                        adj[prev].Add(cur); adjW[prev].Add(w);
                        adj[cur].Add(prev); adjW[cur].Add(w);
                        nEdges += 2;
                    }
                    prev = cur;
                }
            }
        }
        return string.Format("ways={0} nodes={1} edges={2}", nWays, nLon.Count, nEdges);
    }

    public int Nearest(double lon, double lat)
    {
        int best = -1; double bd = double.MaxValue;
        long cx = (long)Math.Floor(lon / CELL), cy = (long)Math.Floor((lat + 90) / CELL);
        for (int r = 0; r <= 4 && best < 0; r++)  // expand search ring until hit
        {
            for (long dx = -r; dx <= r; dx++) for (long dy = -r; dy <= r; dy++)
            {
                if (Math.Abs(dx) != r && Math.Abs(dy) != r) continue;
                List<int> cellList;
                if (!grid.TryGetValue((cx + dx) * 1000000L + (cy + dy), out cellList)) continue;
                foreach (int i in cellList)
                { double d = Dm(nLon[i], nLat[i], lon, lat); if (d < bd) { bd = d; best = i; } }
            }
            if (best >= 0 && r >= 1) break;  // one extra ring after first hit
        }
        return best;
    }

    double[] dist; int[] pred;
    bool Dijkstra(int src, int dst, double maxKm)
    {
        int N = nLon.Count;
        if (dist == null) { dist = new double[N]; pred = new int[N]; }
        var touched = new List<int>();
        var heap = new SortedSet<long>();
        // lazy init via version trick: just reset all (N up to ~500k, fast enough per leg? 500k*8B clear ~ ok)
        for (int i = 0; i < N; i++) { dist[i] = double.MaxValue; pred[i] = -1; }
        dist[src] = 0; heap.Add(src);
        double lim = maxKm * 1000.0;
        while (heap.Count > 0)
        {
            long top = heap.Min; heap.Remove(top);
            int u = (int)(top % 1000000L);
            double du = (top / 1000000L) / 10.0;
            if (du > dist[u] + 0.05) continue;
            if (u == dst) return true;
            if (dist[u] > lim) return false;
            var an = adj[u]; var aw = adjW[u];
            for (int e = 0; e < an.Count; e++)
            {
                int v = an[e]; double nd = dist[u] + aw[e];
                if (nd < dist[v] - 0.05)
                { dist[v] = nd; pred[v] = u; heap.Add(((long)Math.Round(nd * 10)) * 1000000L + v); }
            }
        }
        return false;
    }

    // route through anchor sequence; returns "lon lat;lon lat;..." + stats line at index 0
    public string Route(double[] anchorsLonLat)
    {
        int nA = anchorsLonLat.Length / 2;
        var pts = new List<double[]>();
        double railKm = 0; int failed = 0;
        int prevNode = -1;
        for (int a = 0; a < nA; a++)
        {
            double lo = anchorsLonLat[a * 2], la = anchorsLonLat[a * 2 + 1];
            int node = Nearest(lo, la);
            if (a == 0) { prevNode = node; pts.Add(new double[] { nLon[node], nLat[node] }); continue; }
            bool ok = node >= 0 && prevNode >= 0 && Dijkstra(prevNode, node, 40);
            if (ok)
            {
                var leg = new List<double[]>();
                int cur = node;
                while (cur != prevNode && cur >= 0) { leg.Add(new double[] { nLon[cur], nLat[cur] }); cur = pred[cur]; }
                leg.Reverse();
                foreach (var p in leg) pts.Add(p);
                railKm += dist[node] / 1000.0;
            }
            else { failed++; pts.Add(new double[] { lo, la }); }
            prevNode = node;
        }
        var sb = new System.Text.StringBuilder();
        sb.Append(string.Format(CultureInfo.InvariantCulture, "STATS|{0:F1}|{1}", railKm, failed));
        foreach (var p in pts) sb.Append(string.Format(CultureInfo.InvariantCulture, ";{0:F6} {1:F6}", p[0], p[1]));
        return sb.ToString();
    }
}
