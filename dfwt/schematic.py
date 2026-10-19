"""Schematic ("diagram") layout of the network, in the style of the Washington
Metro map: octilinear lines, uniform strokes, bundled shared corridors.

The layout is computed once, at build time, over the *union* of every station
and stop-to-stop edge in every scenario, so the diagram does not move when the
page switches plan or year; the page only shows, hides or fades parts of it.
It is deterministic (no randomness, everything iterated in sorted order).

Method
------
1. **Union graph.** Nodes are stations; edges are consecutive stops of any line
   in any scenario, each carrying the set of lines that use it. Stations at the
   same place (within 40 m, or the same name within 400 m, and never on a common
   line) are merged into one node: on a diagram they are one interchange.
2. **Density-equalizing pre-warp.** Stress majorization (SMACOF, localized
   update) on all station pairs with target distance ``c * d**GAMMA`` (geographic
   km, GAMMA < 1) and weight ``target**-2``, floored at a minimum spacing. The
   power law expands the dense Fort Worth and Dallas cores and compresses the
   long commuter-rail reaches while keeping the overall geography (it starts
   from the true positions and is rotated back onto them with Procrustes).
3. **Octilinear directions.** Chains of degree-2 stations between junctions or
   termini are the units of the drawing. At each junction the incident chains
   get distinct ports (one of 8 directions) by exhaustive search over
   cyclic-order-preserving assignments, so the cyclic order of neighbours is
   kept. Along each chain a small dynamic program picks one direction per edge,
   trading angular deviation from the current geometry against a penalty per
   bend (45° bends cheap, 90° expensive, sharper ones forbidden). A change of
   direction is moved off the station into the longer adjacent edge, which
   then has exactly one bend.
4. **Least-squares relaxation.** Positions (plus the two leg lengths of each
   bent edge) solve a sparse linear least-squares problem: every straight edge
   lies along its direction (perpendicular residual, weight ramped up),
   has a target length (chain-smoothed, so stations are evenly spaced), and
   every node is weakly anchored to its pre-warped position. Transfer pairs are
   pulled together. Violated minimum distances (node–node and node–edge) are
   linearized into separation terms on the next iteration (active set).
   Steps 3–4 alternate a few times, then directions are frozen and the
   relaxation continues until all spacing constraints hold.
5. **Exact octilinearity.** A final least-norm projection makes every straight
   edge exactly octilinear; any edge that still cannot be straight is drawn as
   two octilinear legs (one bend).
6. **Line ordering.** In each corridor the lines get one order per chain;
   permutations are improved by local search that minimizes crossings at the
   junctions, measured geometrically from the port positions of each line.
7. **Waterways.** Rivers and lakes are carried along with a moving-least-squares
   affine warp fitted to the station displacements (geographic -> layout),
   then simplified and smoothed (rivers snapped towards octilinear runs).

Units: 1.0 = the minimum distance between station centres. y grows north here;
the JSON for the page flips it (SVG y grows down).
"""
import collections
import itertools
import json
import math
import os
import re

import numpy as np

from . import config, geo

MIN_SP = 1.0          # minimum distance between station centres
PITCH = 0.30          # offset between parallel lines in a corridor
MERGE_KM = 0.04       # always merge stations closer than this
MERGE_NAME_KM = 0.40  # merge same-named stations closer than this
MERGE_LINKED_KM = 0.15  # merge transfer-linked stations closer than this
PASS_KM = 0.12        # a line passing this close to another station is drawn through it
SIGMA_KM = 0.8        # station density smoothing for the cartogram
BACKGROUND = 0.10     # uniform density added (relative to the mean); smaller = stronger equalization
INK = 1.0             # cartogram mass per km of line (stations weigh 1)
EDGE_MED = 2.6        # target median stop-to-stop length after the pre-warp
L_MIN, L_MAX = 1.3, 8.0
B45, B90 = 0.35, 1.6
N_ASSIGN, N_RELAX = 10, 14
W_REP = 12.0
W_LEN = 1.5
W_ANC = 0.3
SHRINK = 0.45         # a straight edge shrunk below this fraction of its target gets a bend
SEG_GAP = 0.45        # clear space between the outer strokes of two corridors  # bend penalties (squared radians of deviation they must save)
DIRS = np.array([(math.cos(k * math.pi / 4), math.sin(k * math.pi / 4)) for k in range(8)])
CITIES = [("Fort Worth", 32.7555, -97.3308), ("Dallas", 32.7810, -96.7990), ("Denton", 33.2148, -97.1331),
          ("Arlington", 32.7357, -97.1081), ("DFW Airport", 32.8998, -97.0403), ("Plano", 33.0198, -96.6989)]


def _norm_name(s):
    s = s.lower().replace("square", "sq")
    return re.sub(r"[^a-z0-9]", "", s)


def _angdiff(a, b):
    d = (a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


class Layout:
    """Result: nodes (station groups) with positions, edges with optional bends,
    line orders per edge, transfer connectors and schematized water."""

    def __init__(self):
        self.nodes = []        # dicts: sids, name, geo (km), x, y
        self.node_of = {}      # sid -> node index
        self.edges = []        # dicts: a, b (a < b), lines (ordered), bend (x, y) or None
        self.eidx = {}         # (a, b) -> edge index
        self.transfers = []    # (a, b) node pairs drawn as connectors
        self.water = {"rivers": [], "lakes": []}
        self.labels = []       # (text, x, y, kind)


# ---------------------------------------------------------------- graph
def _polyline_dist(p, pts):
    """Distance from p to a polyline and the arc-length position of the closest point."""
    best, pos, acc = 1e18, 0.0, 0.0
    for q0, q1 in zip(pts, pts[1:]):
        ab = q1 - q0
        L2 = ab @ ab
        t = float(np.clip((p - q0) @ ab / L2, 0, 1)) if L2 > 1e-12 else 0.0
        d = np.linalg.norm(p - q0 - t * ab)
        if d < best:
            best, pos = d, acc + t * math.sqrt(L2)
        acc += math.sqrt(L2)
    return best, pos


def _union(nets):
    proj = geo.Projector()
    stations, seqs, modes = {}, [], {}
    for key in sorted(nets):
        net = nets[key]
        stations.update(net.stations)
        for ln in sorted(net.lines.values(), key=lambda l: l.id):
            seqs.append((key, ln.id, list(ln.stop_ids), [s.pts for s in ln.segments]))
            modes.setdefault(ln.id, ln.mode)
    used = sorted({s for _, _, ss, _ in seqs for s in ss})
    xy = {s: np.array(proj.xy(stations[s].lat, stations[s].lon)) for s in used}
    line_sets = collections.defaultdict(set)
    nbrs = collections.defaultdict(set)
    for _, lid, ss, _ in seqs:
        for s in ss:
            line_sets[s].add(lid)
        for a, b in zip(ss, ss[1:]):
            nbrs[a].add(b)
            nbrs[b].add(a)
    transfers = set()
    radius = next(iter(nets.values())).cfg["transfer"]["walk_radius_m"] / 1000
    for net in nets.values():
        for a, b, _, _ in net.transfers:
            if a in xy and b in xy:
                transfers.add(frozenset((a, b)))
    # merge co-located stations (union-find), never two stops of one line, max degree 8
    parent = {s: s for s in used}

    def find(s):
        while parent[s] != s:
            parent[s] = parent[parent[s]]
            s = parent[s]
        return s
    P = np.array([xy[s] for s in used])
    D = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1))
    close = sorted(zip(*np.nonzero(np.triu(D < MERGE_NAME_KM, 1))), key=lambda ij: (D[ij], ij))
    for i, j in close:
        a, b = used[i], used[j]
        if D[i, j] < radius and not (line_sets[a] & line_sets[b]):
            transfers.add(frozenset((a, b)))
        same = _norm_name(stations[a].name) == _norm_name(stations[b].name)
        linked = D[i, j] < MERGE_LINKED_KM and frozenset((a, b)) in transfers
        if not (D[i, j] < MERGE_KM or same or linked) or b in nbrs[a]:
            continue
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        members = [s for s in used if find(s) in (ra, rb)]
        if any(x & y for x, y in itertools.combinations([line_sets[s] for s in members], 2)):
            continue
        ext = {find(t) for s in members for t in nbrs[s]} - {ra, rb}
        if len(ext) > 8:
            continue
        parent[max(ra, rb)] = min(ra, rb)
    groups = collections.defaultdict(list)
    for s in used:
        groups[find(s)].append(s)
    lay = Layout()
    for root in sorted(groups):
        sids = sorted(groups[root], key=lambda s: (-len(line_sets[s]), s))
        k = len(lay.nodes)
        for s in sids:
            lay.node_of[s] = k
        lay.nodes.append({"sids": sids, "name": stations[sids[0]].name,
                          "geo": np.mean([xy[s] for s in sids], axis=0)})
    G = np.array([nd["geo"] for nd in lay.nodes])
    # stop-to-stop node adjacency (before pass-through routing)
    direct = set()
    for _, _, ss, _ in seqs:
        ns = [lay.node_of[s] for s in ss]
        direct |= {(min(a, b), max(a, b)) for a, b in zip(ns, ns[1:]) if a != b}
    # each segment's node path: a line whose track runs through another station's
    # spot (within PASS_KM) is drawn through it, so it joins that corridor
    lay.paths = {}
    for key, lid, ss, segs in seqs:
        ns = [lay.node_of[s] for s in ss]
        path, stop_at = [ns[0]], [0]
        for k in range(len(ns) - 1):
            a, b = ns[k], ns[k + 1]
            pts = np.array([proj.xy(lat, lon) for lon, lat in segs[k]]) if k < len(segs) else np.array([G[a], G[b]])
            lo, hi = pts.min(0) - PASS_KM, pts.max(0) + PASS_KM
            hits = []
            for u in np.nonzero(np.all((G > lo) & (G < hi), 1))[0]:
                u = int(u)
                if u in ns or np.linalg.norm(G[u] - G[a]) < 0.2 or np.linalg.norm(G[u] - G[b]) < 0.2:
                    continue
                d, pos = _polyline_dist(G[u], pts)
                if d < PASS_KM:
                    hits.append((pos, u))
            via = [u for _, u in sorted(hits)]
            if via and not ((min(a, via[0]), max(a, via[0])) in direct or (min(b, via[-1]), max(b, via[-1])) in direct):
                via = []
            path += via + [b]
            stop_at.append(len(path) - 1)
        lay.paths[(key, lid)] = (path, stop_at)
    elines = collections.defaultdict(set)
    for (key, lid), (path, _) in lay.paths.items():
        for a, b in zip(path, path[1:]):
            if a != b:
                elines[(min(a, b), max(a, b))].add(lid)
    for (a, b) in sorted(elines):
        lay.eidx[(a, b)] = len(lay.edges)
        lay.edges.append({"a": a, "b": b, "lines": sorted(elines[(a, b)]), "bend": None})
    tr = set()
    for t in transfers:
        a, b = sorted(lay.node_of[s] for s in t)
        if a != b and (a, b) not in lay.eidx:
            tr.add((a, b))
    lay.transfers = sorted(tr)
    lay.modes = modes
    lay.seqs = [(k, lid, path) for (k, lid), (path, _) in sorted(lay.paths.items())]
    lay.termini = {path[i] for _, _, path in lay.seqs for i in (0, -1)}
    return lay


# ---------------------------------------------------------------- pre-warp


class Cartogram:
    """Density-equalizing map (Gastner & Newman 2004, diffusion method).

    Station density is smoothed onto a grid, mixed with a uniform background
    (which sets how strong the equalization is), and diffused with FFTs; points
    are advected along the diffusion velocity v = -grad(rho)/rho. The flow is
    continuous, so the warp cannot fold, and any other geometry (waterways,
    labels) is carried through exactly the same flow."""

    def __init__(self, P, grid=384, sigma=None, background=None, mass=None):
        sigma = SIGMA_KM if sigma is None else sigma
        background = BACKGROUND if background is None else background
        lo, hi = P.min(0), P.max(0)
        span = (hi - lo).max() * 1.6
        self.origin = (lo + hi) / 2 - span / 2
        self.h = span / grid
        self.n = grid
        g = (P - self.origin) / self.h
        rho = np.zeros((grid, grid))
        ij = np.clip(np.round(g).astype(int), 0, grid - 1)
        np.add.at(rho, (ij[:, 1], ij[:, 0]), 1.0 if mass is None else mass)
        k = np.fft.fftfreq(grid) * 2 * np.pi
        self.kx, self.ky = np.meshgrid(k, k)
        k2 = self.kx ** 2 + self.ky ** 2
        s = sigma / self.h
        rho = np.real(np.fft.ifft2(np.fft.fft2(rho) * np.exp(-k2 * s * s / 2)))
        inside = rho > rho.max() * 1e-3
        rho = np.maximum(rho, 0) + background * rho[inside].mean()
        self.rho_k = np.fft.fft2(rho)
        self.k2 = k2

    def _vel(self, t):
        f = self.rho_k * np.exp(-self.k2 * t)
        r = np.real(np.fft.ifft2(f))
        gx = np.real(np.fft.ifft2(1j * self.kx * f))
        gy = np.real(np.fft.ifft2(1j * self.ky * f))
        return -gx / r, -gy / r

    @staticmethod
    def _interp(F, g):
        n = F.shape[0]
        x = np.clip(g[:, 0], 0, n - 1.001)
        y = np.clip(g[:, 1], 0, n - 1.001)
        x0, y0 = x.astype(int), y.astype(int)
        fx, fy = x - x0, y - y0
        return (F[y0, x0] * (1 - fx) * (1 - fy) + F[y0, x0 + 1] * fx * (1 - fy) +
                F[y0 + 1, x0] * (1 - fx) * fy + F[y0 + 1, x0 + 1] * fx * fy)

    def warp(self, Qs, steps=400):
        """Advect several point arrays (same flow); returns warped copies in km-like units."""
        sizes = [len(q) for q in Qs]
        g = (np.vstack(Qs) - self.origin) / self.h
        t, dt = 0.0, 0.05
        for _ in range(steps):
            vx, vy = self._vel(t)
            v = np.stack([self._interp(vx, g), self._interp(vy, g)], 1)
            vmax = max(np.abs(vx).max(), np.abs(vy).max())     # grid-wide: independent of the points
            step = min(dt, 0.4 / max(vmax, 1e-9))
            # midpoint (RK2)
            gm = g + 0.5 * step * v
            vx2, vy2 = self._vel(t + 0.5 * step)
            v2 = np.stack([self._interp(vx2, gm), self._interp(vy2, gm)], 1)
            g = g + step * v2
            t += step
            dt *= 1.08
            if vmax < 1e-3:
                break
        out = g * self.h + self.origin
        res, i = [], 0
        for s in sizes:
            res.append(out[i:i + s])
            i += s
        return res


def _prewarp(P, edges, nlines=None, extra=()):
    """Cartogram warp, then scale so the median stop-to-stop hop is EDGE_MED.

    The density is "ink": each station counts once, and every edge is sampled
    every 250 m with a weight proportional to its number of lines, so corridors
    where many lines converge get more room than a station count alone gives.
    `extra` point arrays (waterways, labels) ride along the same flow."""
    pts, mass = [P], [np.full(len(P), 1.0)]
    for k, (a, b) in enumerate(edges):
        ln = np.linalg.norm(P[b] - P[a])
        m = max(int(ln / 0.25), 1)
        t = (np.arange(m) + 0.5) / m
        pts.append(P[a] + t[:, None] * (P[b] - P[a]))
        mass.append(np.full(m, INK * (nlines[k] if nlines is not None else 1) * ln / m))
    cart = Cartogram(np.vstack(pts), mass=np.concatenate(mass))
    out = cart.warp([P] + list(extra))
    A = out[0]
    el = [np.linalg.norm(A[a] - A[b]) for a, b in edges]
    s = EDGE_MED / np.median(el)
    c = A.mean(0)
    return [(Y - c) * s for Y in out]


# ---------------------------------------------------------------- chains / directions
def _chains(lay):
    n = len(lay.nodes)
    inc = [[] for _ in range(n)]
    for i, e in enumerate(lay.edges):
        inc[e["a"]].append(i)
        inc[e["b"]].append(i)
    key = [len(inc[v]) != 2 or v in lay.termini for v in range(n)]
    chains, seen = [], set()

    def walk(v, e):
        nodes, es = [v], []
        while True:
            seen.add(e)
            ed = lay.edges[e]
            w = ed["b"] if ed["a"] == v else ed["a"]
            nodes.append(w)
            es.append(e)
            if key[w]:
                return nodes, es
            nxt = [x for x in inc[w] if x != e]
            v, e = w, nxt[0]
            if e in seen:
                return nodes, es

    for v in range(n):
        if key[v]:
            for e in inc[v]:
                if e not in seen:
                    chains.append(walk(v, e))
    for e in range(len(lay.edges)):          # pure cycles without a junction
        if e not in seen:
            v = lay.edges[e]["a"]
            key[v] = True
            chains.append(walk(v, e))
    return inc, key, chains


def _ports(X, chains, key, inc_count):
    """Port (direction index 0..7) for each chain end at a junction: ends[(chain, 0|1)]."""
    at = collections.defaultdict(list)       # node -> [(chain idx, end)]
    for ci, (nodes, _) in enumerate(chains):
        at[nodes[0]].append((ci, 0))
        at[nodes[-1]].append((ci, 1))
    ports = {}
    order = sorted(at, key=lambda v: (-len(at[v]), v))
    for v in order:
        ends = at[v]
        angs = []
        for ci, end in ends:
            nodes = chains[ci][0] if end == 0 else chains[ci][0][::-1]
            r1 = X[nodes[1]] - X[v]
            r2 = X[nodes[min(2, len(nodes) - 1)]] - X[v]
            r = r1 / (np.linalg.norm(r1) + 1e-9) + 0.5 * r2 / (np.linalg.norm(r2) + 1e-9)
            angs.append(math.atan2(r[1], r[0]))
        # preferred ports from already-assigned single-edge neighbours
        pref = []
        for ci, end in ends:
            nodes = chains[ci][0]
            other = (ci, 1 - end)
            pref.append((ports[other] + 4) % 8 if len(nodes) == 2 and other in ports else None)
        k = len(ends)
        idx = sorted(range(k), key=lambda i: angs[i])
        best, bestc = None, 1e18
        for combo in itertools.combinations(range(8), min(k, 8)):
            for s in range(len(combo)):
                cost = 0.0
                for r, i in enumerate(idx):
                    dk = combo[(r + s) % len(combo)] if r < len(combo) else combo[0]
                    cost += _angdiff(angs[i], dk * math.pi / 4) ** 2
                    if pref[i] is not None and pref[i] != dk:
                        cost += 0.6
                if cost < bestc - 1e-12:
                    bestc, best = cost, (combo, s)
        combo, s = best
        for r, i in enumerate(idx):
            ports[ends[i]] = combo[(r + s) % len(combo)] if r < len(combo) else combo[0]
    return ports


def _chain_dirs(X, nodes, p0, p1):
    """DP: one direction per edge of the chain (in chain orientation)."""
    m = len(nodes) - 1
    INF = 1e18
    un = np.zeros((m, 8))
    for k in range(m):
        v = X[nodes[k + 1]] - X[nodes[k]]
        th = math.atan2(v[1], v[0])
        for d in range(8):
            un[k, d] = _angdiff(th, d * math.pi / 4) ** 2
    if p0 is not None:
        un[0] += [0 if d == p0 else 50 for d in range(8)]
    if p1 is not None:
        last = (p1 + 4) % 8
        un[m - 1] += [0 if d == last else 50 for d in range(8)]

    def trans(a, b):
        t = min((a - b) % 8, (b - a) % 8)
        return (0, B45, B90, 25, 50)[t]
    cost = un[0].copy()
    back = np.zeros((m, 8), dtype=int)
    for k in range(1, m):
        new = np.full(8, INF)
        for d in range(8):
            cands = [cost[p] + trans(p, d) for p in range(8)]
            p = int(np.argmin(cands))
            new[d], back[k, d] = cands[p] + un[k, d], p
        cost = new
    d = int(np.argmin(cost))
    out = [d]
    for k in range(m - 1, 0, -1):
        d = back[k, d]
        out.append(d)
    return out[::-1]


def _assign(lay, X, chains, key, L):
    """Edge directions (canonical a->b) and bent edges {e: (d1 from a, d2 into b)}."""
    ports = _ports(X, chains, key, None)
    dirs, bent = {}, {}
    for ci, (nodes, es) in enumerate(chains):
        cd = _chain_dirs(X, nodes, ports.get((ci, 0)), ports.get((ci, 1)))
        if len(es) == 1:
            # a single edge between two junctions: the ports may disagree -> one bend
            d0, d1 = ports[(ci, 0)], (ports[(ci, 1)] + 4) % 8
            if d0 != d1 and min((d0 - d1) % 8, (d1 - d0) % 8) <= 2:
                cd = None
                ed = lay.edges[es[0]]
                fwd = ed["a"] == nodes[0]
                bent[es[0]] = (d0, d1) if fwd else ((d1 + 4) % 8, (d0 + 4) % 8)
                continue
        # move bends off stations into the longer adjacent edge
        legs = [[d] for d in cd]
        for k in range(1, len(cd)):
            if cd[k] != cd[k - 1]:
                cands = [j for j in (k - 1, k) if len(legs[j]) == 1]
                if not cands:
                    continue
                j = max(cands, key=lambda j: (L[es[j]], j))
                legs[j] = [cd[k - 1], cd[k]]
        for k, e in enumerate(es):
            fwd = lay.edges[e]["a"] == nodes[k]
            lg = legs[k] if fwd else [(d + 4) % 8 for d in legs[k][::-1]]
            if len(lg) == 1:
                dirs[e] = lg[0]
            else:
                bent[e] = tuple(lg)
    return dirs, bent


# ---------------------------------------------------------------- least squares
def _radius(lay):
    """Half-width of the bundle at each node (for spacing)."""
    r = np.zeros(len(lay.nodes))
    for e in lay.edges:
        h = (len(e["lines"]) - 1) / 2 * PITCH
        r[e["a"]] = max(r[e["a"]], h)
        r[e["b"]] = max(r[e["b"]], h)
    return r


def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(p - (a + t * ab)), t


def _solve(lay, X, anchor, dirs, bent, L, wp, rep, wanc):
    n = len(lay.nodes)
    bl = sorted(bent)
    aux = {e: 2 * n + 2 * i for i, e in enumerate(bl)}
    nv = 2 * n + 2 * len(bl)
    rows, rhs = [], []

    def row(coefs, b):
        rows.append(coefs)
        rhs.append(b)
    for v in range(n):
        row({2 * v: wanc[v]}, wanc[v] * anchor[v, 0])
        row({2 * v + 1: wanc[v]}, wanc[v] * anchor[v, 1])
    for e, d in dirs.items():
        a, b = lay.edges[e]["a"], lay.edges[e]["b"]
        u, nr = DIRS[d], DIRS[(d + 2) % 8]
        row({2 * b: wp * nr[0], 2 * b + 1: wp * nr[1], 2 * a: -wp * nr[0], 2 * a + 1: -wp * nr[1]}, 0.0)
        row({2 * b: W_LEN * u[0], 2 * b + 1: W_LEN * u[1], 2 * a: -W_LEN * u[0], 2 * a + 1: -W_LEN * u[1]}, W_LEN * L[e])
    for e in bl:
        a, b = lay.edges[e]["a"], lay.edges[e]["b"]
        u1, u2 = DIRS[bent[e][0]], DIRS[bent[e][1]]
        ia = aux[e]
        for c in range(2):
            row({2 * b + c: wp, 2 * a + c: -wp, ia: -wp * u1[c], ia + 1: -wp * u2[c]}, 0.0)
        row({ia: W_LEN}, W_LEN * L[e] / 2)
        row({ia + 1: W_LEN}, W_LEN * L[e] / 2)
    for (a, b) in lay.transfers:
        g = X[b] - X[a]
        g = g / (np.linalg.norm(g) + 1e-9)
        for c in range(2):
            row({2 * b + c: 0.6, 2 * a + c: -0.6}, 0.6 * g[c] * MIN_SP * 1.3)
    for coefs, b in rep:
        row(coefs, b)
    N = np.zeros((nv, nv))
    rvec = np.zeros(nv)
    for coefs, b in zip(rows, rhs):
        cols = np.fromiter(coefs.keys(), int)
        vals = np.fromiter(coefs.values(), float)
        N[np.ix_(cols, cols)] += np.outer(vals, vals)
        rvec[cols] += vals * b
    sol = np.linalg.solve(N + 1e-9 * np.eye(nv), rvec)
    Xn = sol[:2 * n].reshape(n, 2)
    legs = {e: (sol[aux[e]], sol[aux[e] + 1]) for e in bl}
    return Xn, legs


def _seg_seg(p1, q1, p2, q2):
    """Closest points of two segments: (distance, t1, t2)."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    if a < 1e-12 and e < 1e-12:
        return np.linalg.norm(r), 0.0, 0.0
    if a < 1e-12:
        s, t = 0.0, np.clip(f / e, 0, 1)
    else:
        c = d1 @ r
        if e < 1e-12:
            s, t = np.clip(-c / a, 0, 1), 0.0
        else:
            b = d1 @ d2
            den = a * e - b * b
            s = np.clip((b * f - c * e) / den, 0, 1) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                s, t = np.clip(-c / a, 0, 1), 0.0
            elif t > 1:
                s, t = np.clip((b - c) / a, 0, 1), 1.0
    c1, c2 = p1 + d1 * s, p2 + d2 * t
    return np.linalg.norm(c2 - c1), s, t


def _segments(lay, X, dirs, bent, legs):
    """Drawn pieces: (edge, p, q, point(t) -> (coefs over node vars, constant))."""
    segs = []
    for e, ed in enumerate(lay.edges):
        a, b = ed["a"], ed["b"]
        if e in bent:
            m = X[a] + DIRS[bent[e][0]] * legs[e][0]
            segs.append((e, X[a].copy(), m, lambda t, a=a, o=m - X[a]: ({a: 1.0}, t * o)))
            segs.append((e, m, X[b].copy(), lambda t, b=b, o=m - X[b]: ({b: 1.0}, (1 - t) * o)))
        else:
            segs.append((e, X[a].copy(), X[b].copy(), lambda t, a=a, b=b: ({a: 1 - t, b: t}, np.zeros(2))))
    return segs


def _violations(lay, X, dirs, bent, legs, rad, margin=1.0):
    """Linearized separation rows (coefs, rhs) for node pairs closer than the
    minimum spacing, and for drawn pieces of different edges that come closer
    than their bundle widths allow (collinear overlaps included). Proper
    crossings are left alone: some lines do cross."""
    rows = []
    diff = X[None, :, :] - X[:, None, :]
    dist = np.sqrt((diff ** 2).sum(-1))
    need = np.maximum(MIN_SP, rad[:, None] + rad[None, :] + 0.6)
    bad = 0
    for i, k in zip(*np.nonzero(np.triu(dist < need * margin, 1))):
        g = diff[i, k] / dist[i, k] if dist[i, k] > 1e-6 else np.array([1.0, 0.0])
        coefs = {}
        for c in range(2):
            coefs[2 * k + c] = W_REP * g[c]
            coefs[2 * i + c] = -W_REP * g[c]
        rows.append((coefs, W_REP * need[i, k] * 1.05))
        bad += dist[i, k] < need[i, k] - 1e-6
    segs = _segments(lay, X, dirs, bent, legs)
    lo = np.array([np.minimum(p, q) for _, p, q, _ in segs])
    hi = np.array([np.maximum(p, q) for _, p, q, _ in segs])
    hw = np.array([(len(lay.edges[e]["lines"]) - 1) / 2 * PITCH for e, _, _, _ in segs])
    M = 1.0
    ov = np.all((lo[:, None] - M <= hi[None]) & (lo[None] - M <= hi[:, None]), axis=2)
    for i, j in zip(*np.nonzero(np.triu(ov, 1))):
        e1, p1, q1, f1 = segs[i]
        e2, p2, q2, f2 = segs[j]
        E1, E2 = lay.edges[e1], lay.edges[e2]
        if e1 == e2 or {E1["a"], E1["b"]} & {E2["a"], E2["b"]}:
            continue
        nd = hw[i] + hw[j] + SEG_GAP
        dd, t1, t2 = _seg_seg(p1, q1, p2, q2)
        if dd >= nd * margin or _intersect(p1, q1, p2, q2):
            continue
        c1, k1 = f1(t1)
        c2, k2 = f2(t2)
        g = (p2 + (q2 - p2) * t2) - (p1 + (q1 - p1) * t1)
        if np.linalg.norm(g) < 1e-6:          # collinear overlap: push apart sideways
            t = q1 - p1
            g = np.array([-t[1], t[0]])
            if g @ ((p2 + q2) / 2 - (p1 + q1) / 2) < 0:
                g = -g
        g = g / (np.linalg.norm(g) + 1e-12)
        coefs = collections.defaultdict(float)
        for v, w in c2.items():
            coefs[2 * v] += W_REP * w * g[0]
            coefs[2 * v + 1] += W_REP * w * g[1]
        for v, w in c1.items():
            coefs[2 * v] -= W_REP * w * g[0]
            coefs[2 * v + 1] -= W_REP * w * g[1]
        rows.append((dict(coefs), W_REP * (nd * 1.05 - g @ (k2 - k1))))
        bad += dd < nd - 1e-6
    return rows, bad


def _targets(lay, A, chains):
    L = np.zeros(len(lay.edges))
    rad = _radius(lay)
    for e, ed in enumerate(lay.edges):
        a, b = ed["a"], ed["b"]
        L[e] = np.clip(np.linalg.norm(A[a] - A[b]), max(L_MIN, rad[a] + rad[b] + 0.6), L_MAX)
    for nodes, es in chains:
        if len(es) > 1:
            mean = L[es].mean()
            L[es] = 0.45 * L[es] + 0.55 * mean
    return L


def _exact(lay, X, dirs):
    """Least-norm move that makes every straight edge exactly octilinear."""
    n = len(lay.nodes)
    es = sorted(dirs)
    C = np.zeros((len(es), 2 * n))
    for r, e in enumerate(es):
        a, b = lay.edges[e]["a"], lay.edges[e]["b"]
        nr = DIRS[(dirs[e] + 2) % 8]
        C[r, 2 * b:2 * b + 2] = nr
        C[r, 2 * a:2 * a + 2] = -nr
    x = X.reshape(-1)
    y = C @ x
    lam = np.linalg.lstsq(C @ C.T, y, rcond=None)[0]
    return (x - C.T @ lam).reshape(n, 2)


def _decompose(v, pref=None):
    """Write v as alpha*DIRS[i] + beta*DIRS[j] (alpha, beta >= 0, j = i+1)."""
    th = math.atan2(v[1], v[0]) % (2 * math.pi)
    i = int(th // (math.pi / 4)) % 8
    j = (i + 1) % 8
    M = np.array([DIRS[i], DIRS[j]]).T
    al, be = np.linalg.solve(M, v)
    return (i, max(al, 0.0)), (j, max(be, 0.0))


# ---------------------------------------------------------------- line ordering
def _order_lines(lay, X, chains, key):
    """One order per chain; local search on crossings at junctions."""
    chain_of = {}
    for ci, (nodes, es) in enumerate(chains):
        for k, e in enumerate(es):
            chain_of[e] = ci
    order = {ci: sorted(lay.edges[es[0]]["lines"], key=lambda l: (lay.modes.get(l) != "metro", l))
             for ci, (nodes, es) in enumerate(chains)}
    # passes: for each line, consecutive edge pairs at each node
    passes = collections.defaultdict(list)    # node -> [(line, e_in, e_out)]
    for _, lid, ns in lay.seqs:
        for k in range(1, len(ns) - 1):
            e1 = lay.eidx[(min(ns[k - 1], ns[k]), max(ns[k - 1], ns[k]))]
            e2 = lay.eidx[(min(ns[k], ns[k + 1]), max(ns[k], ns[k + 1]))]
            passes[ns[k]].append((lid, e1, e2))
    for v in passes:
        passes[v] = sorted(set(passes[v]))

    def port(v, e, lid):
        ed = lay.edges[e]
        other = ed["b"] if ed["a"] == v else ed["a"]
        if ed["bend"] is not None:
            tgt = np.array(ed["bend"])
        else:
            tgt = X[other]
        u = tgt - X[v]
        u = u / (np.linalg.norm(u) + 1e-9)
        ca = X[ed["b"]] - X[ed["a"]] if ed["bend"] is None else None
        # offset normal in canonical a->b orientation of the leg touching v
        if ed["a"] == v:
            t = u
        else:
            t = -u
        nr = np.array([-t[1], t[0]])
        lines = order[chain_of[e]]
        k = lines.index(lid)
        off = (k - (len(lines) - 1) / 2) * PITCH
        del ca
        return X[v] + 0.8 * u + off * nr

    def crossings(v):
        ps = passes.get(v, [])
        segs = [(port(v, e1, l), port(v, e2, l)) for l, e1, e2 in ps]
        c = 0
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                if ps[i][0] != ps[j][0] and _intersect(*segs[i], *segs[j]):
                    c += 1
        return c

    junctions = collections.defaultdict(set)
    for ci, (nodes, es) in enumerate(chains):
        junctions[ci] = {nodes[0], nodes[-1]}
    for _ in range(6):
        improved = False
        for ci in sorted(order):
            if len(order[ci]) < 2:
                continue
            vs = sorted(junctions[ci])
            cur = sum(crossings(v) for v in vs)
            best, bestc = order[ci], cur
            perms = itertools.permutations(order[ci]) if len(order[ci]) <= 5 else [order[ci], order[ci][::-1]]
            for p in perms:
                order[ci] = list(p)
                c = sum(crossings(v) for v in vs)
                if c < bestc:
                    best, bestc = list(p), c
            order[ci] = best
            improved |= bestc < cur
        if not improved:
            break
    for e in range(len(lay.edges)):
        lay.edges[e]["lines"] = order[chain_of[e]]


def _intersect(p1, p2, p3, p4):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return d1 * d2 < -1e-12 and d3 * d4 < -1e-12


# ---------------------------------------------------------------- waterways
def _dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [0, len(pts) - 1]
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        best, bi = -1, -1
        for i in range(a + 1, b):
            d, _ = _seg_dist(pts[i], pts[a], pts[b])
            if d > best:
                best, bi = d, i
        if best > tol:
            keep.append(bi)
            stack += [(a, bi), (bi, b)]
    return pts[sorted(keep)]


def _chaikin(pts, it=2, closed=False):
    for _ in range(it):
        P = np.vstack([pts, pts[:1]]) if closed else pts
        Q = 0.75 * P[:-1] + 0.25 * P[1:]
        R = 0.25 * P[:-1] + 0.75 * P[1:]
        mid = np.empty((2 * len(Q), 2))
        mid[0::2], mid[1::2] = Q, R
        pts = mid if closed else np.vstack([P[:1], mid, P[-1:]])
    return pts


def _octi_path(pts):
    """Snap a simplified polyline towards octilinear runs (each leg -> <= 2 octilinear legs)."""
    out = [pts[0]]
    for p in pts[1:]:
        v = p - out[-1]
        if np.linalg.norm(v) < 1e-9:
            continue
        (i, al), (j, be) = _decompose(v)
        if al > 1e-6 and be > 1e-6:
            out.append(out[-1] + DIRS[i] * al if al >= be else out[-1] + DIRS[j] * be)
        out.append(p)
    return np.array(out)


def _load_water():
    """[(name, kind, area_km2, [km point arrays])] from data/waterways.geojson."""
    path = config.path("data", "waterways.geojson")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    proj = geo.Projector()
    out = []
    for ft in gj["features"]:
        pr = ft["properties"]
        parts = ft["geometry"]["coordinates"]
        rings = parts if pr["kind"] == "river" else [poly[0] for poly in parts]
        out.append((pr["name"], pr["kind"], pr.get("area_km2", 0),
                    [np.array([proj.xy(lat, lon) for lon, lat in r]) for r in rings]))
    return out


def _carry(A, X, Q, sigma=2.5):
    """Move points Q (pre-warp coordinates) with the smoothed node displacements X - A."""
    if len(Q) == 0:
        return Q
    d2 = ((Q[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    w = np.exp(-d2 / (2 * sigma * sigma))
    return Q + (w @ (X - A)) / (w.sum(1, keepdims=True) + 0.05)


def _local_affine(G, X, q, sigma_km=8.0):
    """Weighted least-squares affine map geo -> layout around q."""
    w = np.exp(-((G - q) ** 2).sum(1) / (2 * sigma_km ** 2)) + 1e-9
    Gh = np.hstack([G - q, np.ones((len(G), 1))])
    M = Gh.T @ (w[:, None] * Gh) + 1e-6 * np.eye(3)
    T = np.linalg.solve(M, Gh.T @ (w[:, None] * X))
    return lambda P: np.hstack([P - q, np.ones((len(P), 1))]) @ T


def _water(lay, A, X, water, warped):
    """Rivers follow the warp (clipped to the network's neighbourhood);
    lakes keep their shape under a local affine fit, so they read as blobs of
    sensible size even where the warp squeezes empty country."""
    G = np.array([nd["geo"] for nd in lay.nodes])
    k = 0
    for name, kind, area, rings in water:
        for ring in rings:
            Y = _carry(A, X, warped[k])
            k += 1
            near = np.sqrt(((Y[:, None, :] - X[None, :, :]) ** 2).sum(-1)).min(1)
            if kind == "river":
                runs, cur = [], []
                for p, ok in zip(Y, near < 3.5):
                    if ok:
                        cur.append(p)
                    elif cur:
                        runs.append(cur)
                        cur = []
                if cur:
                    runs.append(cur)
                for r in runs:
                    if len(r) < 3:
                        continue
                    R = _dp(np.array(r), 0.8)
                    lay.water["rivers"].append({"name": name, "pts": _chaikin(_octi_path(R), 3)})
            else:
                c = ring.mean(0)
                Yc = _carry(A, X, warped[k - 1].mean(0, keepdims=True))[0]
                if np.sqrt(((X - Yc) ** 2).sum(1)).min() > 6:
                    continue
                Z = _local_affine(G, X, c)(ring)
                Z += Yc - Z.mean(0)
                R = _dp(Z, 0.25)
                if len(R) >= 4:
                    lay.water["lakes"].append({"name": name, "area": area,
                                               "pts": _chaikin(R[:-1], 3, closed=True)})


# ---------------------------------------------------------------- driver
def compute(nets, log=None):
    lay = _union(nets)
    n = len(lay.nodes)
    G = np.array([nd["geo"] for nd in lay.nodes])
    water = _load_water()
    proj = geo.Projector()
    cities = np.array([proj.xy(lat, lon) for _, lat, lon in CITIES])
    extra = [cities] + [r for _, _, _, rings in water for r in rings]
    A, *warped = _prewarp(G, [(e["a"], e["b"]) for e in lay.edges], [len(e["lines"]) for e in lay.edges], extra)
    inc, key, chains = _chains(lay)
    L = _targets(lay, A, chains)
    rad = _radius(lay)
    wanc = np.array([W_ANC * (1.5 if key[v] else 1.0) for v in range(n)])
    X = A.copy()
    rep = []
    dirs = bent = None
    legs = {}

    def step(wp, margin=1.1):
        nonlocal X, legs, rep
        X, legs = _solve(lay, X, A, dirs, bent, L, wp, rep, wanc)
        # active set: separation terms only for pairs that are (nearly) too close now
        rep, bad = _violations(lay, X, dirs, bent, legs, rad, margin=margin)
        return bad
    # phase 1: directions re-assigned from the current geometry, moderate weight
    for it in range(N_ASSIGN):
        dirs, bent = _assign(lay, X, chains, key, L)
        bad = step(min(1.5 * 1.35 ** it, 6.0))
        if log:
            log(f"assign {it}: {len(dirs)} straight, {len(bent)} bent, {bad} spacing violations")
    # phase 2: frozen directions; edges that still deviate or collapse get one bend
    for it in range(N_RELAX):
        conv = []
        for e, d in list(dirs.items()):
            ed = lay.edges[e]
            v = X[ed["b"]] - X[ed["a"]]
            ln = np.linalg.norm(v)
            dev = math.degrees(_angdiff(math.atan2(v[1], v[0]), d * math.pi / 4))
            if dev > 4.0 or v @ DIRS[d] < SHRINK * L[e]:
                (i, al), (j, be) = _decompose(v if ln > 1e-6 else DIRS[d])
                if dev <= 4.0 or i == j:
                    i, j = d, (d + 1) % 8
                bent[e] = (i, j) if al >= be else (j, i)
                del dirs[e]
                conv.append(e)
        bad = step(min(6.0 * 1.6 ** it, 80.0))
        if log:
            log(f"relax {it}: {len(conv)} -> bent, {len(dirs)} straight, {len(bent)} bent, {bad} spacing violations")
        if it >= 4 and bad == 0 and not conv:
            break
    lay.debug = (dirs, bent, legs, rad, L, A)
    lay.Xpre = X.copy()
    X = _exact(lay, X, dirs)
    for v, nd in enumerate(lay.nodes):
        nd["x"], nd["y"] = float(X[v, 0]), float(X[v, 1])
    for e, ed in enumerate(lay.edges):
        a, b = ed["a"], ed["b"]
        v = X[b] - X[a]
        if e in dirs:
            th = math.degrees(math.atan2(v[1], v[0]))
            if abs((th - dirs[e] * 45 + 180) % 360 - 180) < 0.3 and v @ DIRS[dirs[e]] > 0:
                continue
            (i, al), (j, be) = _decompose(v)
            ed["bend"] = tuple(X[a] + DIRS[i] * al) if al > 1e-6 and be > 1e-6 else None
        else:
            d1, d2 = bent[e]
            M = np.array([DIRS[d1], DIRS[d2]]).T
            try:
                al, be = np.linalg.solve(M, v)
            except np.linalg.LinAlgError:
                al = be = -1
            if al > 0.05 and be > 0.05:
                ed["bend"] = tuple(X[a] + DIRS[d1] * al)
            else:
                (i, al), (j, be) = _decompose(v)
                ed["bend"] = tuple(X[a] + DIRS[i] * al) if al > 1e-6 and be > 1e-6 else None
    _order_lines(lay, X, chains, key)
    _water(lay, A, X, water, warped[1:])
    for (name, _, _), p in zip(CITIES, _carry(A, X, warped[0])):
        lay.labels.append((name, float(p[0]), float(p[1]), "city"))
    lay.X = X
    lay.chains = chains
    return lay


def edge_polyline(lay, e):
    ed = lay.edges[e]
    a, b = lay.nodes[ed["a"]], lay.nodes[ed["b"]]
    pts = [(a["x"], a["y"])]
    if ed["bend"] is not None:
        pts.append(tuple(ed["bend"]))
    pts.append((b["x"], b["y"]))
    return pts


def to_json(lay):
    """Compact JSON for the page (y flipped so it grows downwards)."""
    r2 = lambda v: round(float(v), 2)  # noqa: E731
    nodes = [[r2(nd["x"]), r2(-nd["y"]), nd["sids"], nd["name"]] for nd in lay.nodes]
    edges = []
    for ed in lay.edges:
        bend = [r2(ed["bend"][0]), r2(-ed["bend"][1])] if ed["bend"] is not None else 0
        edges.append([ed["a"], ed["b"], bend, ed["lines"]])
    rivers = [{"n": r["name"], "p": [[r2(x), r2(-y)] for x, y in r["pts"]]} for r in lay.water["rivers"]]
    lakes = [{"n": r["name"], "a": r["area"], "p": [[r2(x), r2(-y)] for x, y in r["pts"]]} for r in lay.water["lakes"]]
    labels = [[t, r2(x), r2(-y), k] for t, x, y, k in lay.labels]
    return {"nodes": nodes, "edges": edges, "transfers": [list(t) for t in lay.transfers],
            "rivers": rivers, "lakes": lakes, "labels": labels, "pitch": PITCH}


def waterways_geo():
    """The waterways as [lat, lon] polylines/polygons for the geographic map layer."""
    path = config.path("data", "waterways.geojson")
    if not os.path.exists(path):
        return {"rivers": [], "lakes": []}
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    out = {"rivers": [], "lakes": []}
    for ft in gj["features"]:
        g = ft["geometry"]["coordinates"]
        if ft["properties"]["kind"] == "river":
            out["rivers"] += [[[lat, lon] for lon, lat in line] for line in g]
        else:
            out["lakes"] += [[[lat, lon] for lon, lat in poly[0]] for poly in g]
    return out
