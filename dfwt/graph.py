"""Line-aware routing graph for one year, station-to-station skims, and trip planning.

Nodes: one platform node per open station plus one node per (run, stop).
Edges: board (platform -> line, cost = expected wait + transfer penalty),
       alight (line -> platform, free), ride (line stop -> next line stop),
       transfer walk (platform <-> platform within config.transfer.walk_radius_m).
Every trip boards at least once, so one transfer penalty is subtracted from all
station-to-station times: the first boarding costs only the wait.
"""
import collections
import heapq

import numpy as np

from . import geo


class YearGraph:
    def __init__(self, net, year):
        self.net, self.year, cfg = net, year, net.cfg
        self.runs = net.runs(year)
        self.station_ids = sorted({s for r in self.runs for s in r.stops})
        self.sidx = {s: i for i, s in enumerate(self.station_ids)}
        n_st = len(self.station_ids)
        self.node_info = [("P", s, None) for s in self.station_ids]
        adj = [[] for _ in range(n_st)]
        tcfg = cfg["transfer"]
        self.board_pen = tcfg["penalty_min"]
        wcap = cfg["wait"]["max_wait_min"]
        for ri, run in enumerate(self.runs):
            wait = min(run.line.headway_at(year) * cfg["wait"]["fraction_of_headway"], wcap)
            wait *= cfg["wait"].get("weight", 1.0)   # perceived wait (sensitivity; 1 = as before)
            prev = None
            for k, sid in enumerate(run.stops):
                node = len(self.node_info)
                self.node_info.append(("L", sid, ri))
                adj.append([])
                p = self.sidx[sid]
                adj[p].append((node, wait + self.board_pen, "board"))
                adj[node].append((p, 0.0, "alight"))
                if prev is not None:
                    t = run.hop_min[k - 1]
                    adj[prev].append((node, t, "ride"))
                    adj[node].append((prev, t, "ride"))
                prev = node
        # transfer walks between nearby platforms
        r_km = tcfg["walk_radius_m"] / 1000
        pts = [(net.stations[s].lat, net.stations[s].lon) for s in self.station_ids]
        for i in range(n_st):
            for j in range(i + 1, n_st):
                if abs(pts[i][0] - pts[j][0]) > 0.005:
                    continue
                d = geo.hav_km(*pts[i], *pts[j])
                if d <= r_km:
                    t = d * 1.2 / tcfg["walk_speed_kmh"] * 60
                    adj[i].append((j, t, "walk"))
                    adj[j].append((i, t, "walk"))
        # explicit transfer links (same-place stations further apart than the auto radius)
        for a, b, walk_min, _ in net.transfers:
            if a in self.sidx and b in self.sidx:
                i, j = self.sidx[a], self.sidx[b]
                if walk_min is None:
                    sa, sb = net.stations[a], net.stations[b]
                    walk_min = geo.hav_km(sa.lat, sa.lon, sb.lat, sb.lon) * 1.25 / tcfg["walk_speed_kmh"] * 60
                adj[i].append((j, walk_min, "walk"))
                adj[j].append((i, walk_min, "walk"))
        self.adj = adj
        self.n_st = n_st

    def dijkstra(self, src):
        n = len(self.adj)
        dist = [float("inf")] * n
        pred = [-1] * n
        dist[src] = 0.0
        pq = [(0.0, src)]
        adj = self.adj
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, w, _ in adj[u]:
                nd = d + w
                if nd < dist[v]:
                    dist[v] = nd
                    pred[v] = u
                    heapq.heappush(pq, (nd, v))
        return dist, pred

    def skim(self):
        """Station x station door-free travel minutes (inf if unreachable) and predecessor trees."""
        n = self.n_st
        T = np.full((n, n), np.inf, dtype=np.float32)
        preds = []
        # stations joined by walking links: the only pairs a path can connect without riding
        group = list(range(n))

        def find(i):
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i
        for i in range(n):
            for j, _, kind in self.adj[i]:
                if kind == "walk" and j < n:
                    group[find(i)] = find(j)
        members = collections.defaultdict(list)
        for i in range(n):
            members[find(i)].append(i)
        for a in range(n):
            dist, pred = self.dijkstra(a)
            row = np.array(dist[:n], dtype=np.float32) - self.board_pen
            for b in members[find(a)]:   # a walk between platforms is not a transit trip
                u = pred[b]
                while u != -1 and u != a and u < n:
                    u = pred[u]
                if u == a or u == -1:
                    row[b] = np.inf
            row[a] = 0.0
            T[a] = row
            preds.append(np.array(pred, dtype=np.int32))
        self.T, self.preds = T, preds
        return T

    def path_nodes(self, a, b):
        pred = self.preds[a]
        out, u = [], b
        while u != -1:
            out.append(u)
            if u == a:
                break
            u = pred[u]
        return out[::-1]

    def itinerary(self, a, b):
        """Readable legs between station indices a and b (requires skim or a fresh dijkstra)."""
        dist, pred = self.dijkstra(a)
        nodes, u = [], b
        while u != -1:
            nodes.append(u)
            u = pred[u]
        nodes.reverse()
        legs = []
        for u, v in zip(nodes, nodes[1:]):
            ku, kv = self.node_info[u], self.node_info[v]
            if ku[0] == "P" and kv[0] == "P":
                legs.append(("walk", ku[1], kv[1], None, dist[v] - dist[u]))
            elif ku[0] == "L" and kv[0] == "L":
                run = self.runs[kv[2]]
                if legs and legs[-1][0] == "ride" and legs[-1][3] is run:
                    _, s0, _, _, t = legs[-1]
                    legs[-1] = ("ride", s0, kv[1], run, t + dist[v] - dist[u])
                else:
                    legs.append(("ride", ku[1], kv[1], run, dist[v] - dist[u]))
            elif ku[0] == "P" and kv[0] == "L":
                legs.append(("wait", ku[1], ku[1], self.runs[kv[2]], dist[v] - dist[u] - self.board_pen))
        return legs, dist[b] - self.board_pen
