"""Route a line's stations along real right-of-way (Overture/OSM rail or roads).

Graph: Overture transportation segments split at their connectors. Search state is
a *directed edge*, so the turn angle at every junction is known and limited:
trains can't cross a diamond onto another line or reverse at a wye, buses can't
U-turn. Routing is station-constrained Viterbi: at each station every possible
arrival state is kept with its cost and the next leg is one multi-source
Dijkstra from all of them, so no early greedy choice locks in a detour.

Requires pyarrow (requirements-geometry.txt) and data/osm/*.parquet (tools/fetch_osm.py).
"""
import collections
import heapq
import math
import re
import struct

from . import config

LAT0, LON0 = 32.8, -97.0
KX = math.radians(1) * 6371008.8 * math.cos(math.radians(LAT0))
KY = math.radians(1) * 6371008.8


def set_origin(lat0, lon0):
    """Re-centre the local projection (default: DFW). A metro elsewhere (metro/) calls this
    before building a Graph so metres stay metres; it affects every later xy()/ll() call."""
    global LAT0, LON0, KX
    LAT0, LON0 = lat0, lon0
    KX = math.radians(1) * 6371008.8 * math.cos(math.radians(LAT0))


def xy(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def ll(p):
    return (p[0] / KX + LON0, p[1] / KY + LAT0)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def wkb_linestring(buf):
    """Decode a 2D WKB LineString (the only geometry Overture segments use)."""
    bo = "<" if buf[0] == 1 else ">"
    gtype = struct.unpack_from(bo + "I", buf, 1)[0] & 0xFFFF
    if gtype % 1000 != 2:
        raise ValueError(f"not a LineString (type {gtype})")
    dims = 3 if gtype in (1002, 3002) else 4 if gtype == 3002 else 2
    n = struct.unpack_from(bo + "I", buf, 5)[0]
    vals = struct.unpack_from(bo + "d" * (n * dims), buf, 9)
    return [(vals[i * dims], vals[i * dims + 1]) for i in range(n)]


def _heading(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _angdiff(h1, h2):
    return abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi))


def _along(P, s):
    acc = 0.0
    for a, b in zip(P, P[1:]):
        L = dist(a, b)
        if acc + L >= s:
            t = (s - acc) / L if L else 0
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        acc += L
    return P[-1]


def _cut(P, f0, f1, total):
    s0, s1 = f0 * total, f1 * total
    out, acc = [], 0.0
    for a, b in zip(P, P[1:]):
        L = dist(a, b)
        if acc + L >= s0 and not out:
            t = (s0 - acc) / L if L else 0
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        if out and acc + L < s1:
            out.append(b)
        if acc + L >= s1:
            t = (s1 - acc) / L if L else 0
            q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            if not out:
                out.append(q)
            if dist(out[-1], q) > 0.01:
                out.append(q)
            break
        acc += L
    return out if len(out) >= 2 else [P[0], P[-1]]


class Graph:
    def __init__(self, kind, classes=None, oneway=True, path=None):
        """`path`: the parquet to read (default data/osm/rail.parquet or roads.parquet)."""
        import pyarrow.parquet as pq
        path = path or config.path("data", "osm", "rail.parquet" if kind == "rail" else "roads.parquet")
        cols = ["geometry", "class", "connectors", "access_restrictions", "names"]
        rows = pq.read_table(path, columns=cols).to_pylist()
        self.node_xy, self.edges = {}, []      # edge: (u, v, pts, cls, fwd, bwd, length, name)
        self.out = collections.defaultdict(list)
        for r in rows:
            if classes and r["class"] not in classes:
                continue
            P = [xy(*c) for c in wkb_linestring(r["geometry"])]
            total = sum(dist(a, b) for a, b in zip(P, P[1:]))
            if total < 0.5:
                continue
            fwd = bwd = True
            if kind != "rail" and oneway:
                for a in r["access_restrictions"] or []:
                    w = a.get("when") or {}
                    if a["access_type"] == "denied" and w.get("heading") and not w.get("mode") and not a.get("between"):
                        bwd = bwd and w["heading"] != "backward"
                        fwd = fwd and w["heading"] != "forward"
            name = ((r["names"] or {}).get("primary") or "")
            cons = sorted(r["connectors"] or [], key=lambda c: c["at"])
            for c0, c1 in zip(cons, cons[1:]):
                if c1["at"] - c0["at"] <= 0:
                    continue
                pts = _cut(P, c0["at"], c1["at"], total)
                u, v = c0["connector_id"], c1["connector_id"]
                self.node_xy.setdefault(u, pts[0])
                self.node_xy.setdefault(v, pts[-1])
                self._add(u, v, pts, r["class"], fwd, bwd, name)
        self.egrid = collections.defaultdict(set)
        for i, e in enumerate(self.edges):
            self._index(i, e[2])
        self.dead, self.vn = set(), 0

    def _add(self, u, v, pts, cls, fwd, bwd, name):
        i = len(self.edges)
        self.edges.append((u, v, pts, cls, fwd, bwd, sum(dist(a, b) for a, b in zip(pts, pts[1:])), name))
        if fwd:
            self.out[u].append((i, 1))
        if bwd:
            self.out[v].append((i, -1))
        return i

    def _index(self, i, P):
        for a, b in zip(P, P[1:]):
            n = int(dist(a, b) // 200) + 1
            for t in range(n + 1):
                q = (a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n)
                self.egrid[(int(q[0] // 250), int(q[1] // 250))].add(i)

    def pts(self, e, dr):
        P = self.edges[e][2]
        return P if dr == 1 else P[::-1]

    def h_out(self, e, dr):
        P = self.pts(e, dr)
        return _heading(P[0], _along(P, min(40, self.edges[e][6])))

    def h_in(self, e, dr):
        P = self.pts(e, dr)[::-1]
        return _heading(_along(P, min(40, self.edges[e][6])), P[0])

    def head(self, e, dr):
        return self.edges[e][1] if dr == 1 else self.edges[e][0]

    def project(self, p, r, k=16):
        """Split up to k nearest edges at the projection of p; [(distance, node)]."""
        cx, cy, m = int(p[0] // 250), int(p[1] // 250), int(r // 250) + 1
        cand = set()
        for i in range(cx - m, cx + m + 1):
            for j in range(cy - m, cy + m + 1):
                cand |= self.egrid.get((i, j), set())
        hits = []
        for ei in cand:
            if ei in self.dead:
                continue
            P = self.edges[ei][2]
            best = (1e18, 0, None)
            for s_, (a, b) in enumerate(zip(P, P[1:])):
                vx, vy = b[0] - a[0], b[1] - a[1]
                L2 = vx * vx + vy * vy
                t = 0 if L2 == 0 else max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
                q = (a[0] + t * vx, a[1] + t * vy)
                if dist(p, q) < best[0]:
                    best = (dist(p, q), s_, q)
            if best[0] <= r:
                hits.append((best[0], ei, best[1], best[2]))
        hits.sort()
        out = []
        for dd, ei, s_, q in hits[:k]:
            u, v, P, cls, fwd, bwd, L, name = self.edges[ei]
            A, B = P[:s_ + 1] + [q], [q] + P[s_ + 1:]
            if dist(A[0], q) < 1:
                out.append((dd, u))
                continue
            if dist(B[-1], q) < 1:
                out.append((dd, v))
                continue
            self.vn += 1
            n = f"v{self.vn}"
            self.node_xy[n] = q
            self.dead.add(ei)
            for a_, b_, pts in ((u, n, A), (n, v, B)):
                self._index(self._add(a_, b_, pts, cls, fwd, bwd, name), pts)
            out.append((dd, n))
        return out


def route(G, stops_xy, max_turn, snap_r=400, w_cls=None, turn_pen=0.0, detour=3.0, snap_w=3.0, prefer=None):
    """Polyline through the stations in order, or (None, reason)."""
    w_cls = w_cls or {}
    rx = re.compile(prefer) if prefer else None

    def W(e):
        ed = G.edges[e]
        return ed[6] * w_cls.get(ed[3], 1.0) * (0.6 if rx and rx.search(ed[7]) else 1.0)

    legs, cur = [], None
    for k in range(len(stops_xy) - 1):
        A, B = stops_xy[k], stops_xy[k + 1]
        dsts = {n: dd for dd, n in G.project(B, snap_r)}
        if not dsts:
            return None, f"no track/road within {snap_r} m of stop {k + 2}"
        best, prev, pq_ = {}, {}, []

        def push(s, c, p):
            if c < best.get(s, 1e18):
                best[s], prev[s] = c, p
                heapq.heappush(pq_, (c, s[0], s[1]))

        if cur is None:
            srcs = G.project(A, snap_r)
            if not srcs:
                return None, f"no track/road within {snap_r} m of stop 1"
            for dd, n in srcs:
                for e, dr in G.out[n]:
                    if e not in G.dead:
                        push((e, dr), dd * snap_w + W(e), None)
        else:
            for s0, c0 in cur.items():
                n, hin = G.head(*s0), G.h_in(*s0)
                for e, dr in G.out[n]:
                    if e in G.dead or e == s0[0] or _angdiff(hin, G.h_out(e, dr)) > max_turn:
                        continue
                    push((e, dr), c0 + W(e), ("SEED", s0))
        lim = dist(A, B) * detour + 5000 + min(best.values(), default=0)
        arr = {}
        while pq_:
            c, e, dr = heapq.heappop(pq_)
            if c > best.get((e, dr), 1e18):
                continue
            if c > lim:
                break
            v = G.head(e, dr)
            if v in dsts:
                arr[(e, dr)] = c + dsts[v] * snap_w
            hin = G.h_in(e, dr)
            for e2, dr2 in G.out[v]:
                if e2 == e or e2 in G.dead:
                    continue
                t = _angdiff(hin, G.h_out(e2, dr2))
                if t <= max_turn:
                    push((e2, dr2), c + W(e2) + turn_pen * (t / 90.0) ** 2, (e, dr))
        if not arr:
            return None, f"no route between stops {k + 1} and {k + 2} within the turn limit"
        legs.append(prev)
        cur = arr
    s, seq = min(cur, key=cur.get), []
    for prev in reversed(legs):
        while True:
            seq.append(s)
            p = prev[s]
            if p is None:
                s = None
                break
            if p[0] == "SEED":
                s = p[1]
                break
            s = p
        if s is None:
            break
    seq.reverse()
    P = []
    for e, dr in seq:
        Q = G.pts(e, dr)
        P.extend(Q if not P else Q[1:])
    return P, "ok"
