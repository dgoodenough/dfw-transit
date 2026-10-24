"""Schematic ("diagram") layout of the network, in the style of the Washington
Metro map: octilinear lines, uniform strokes, bundled shared corridors.

The diagram has versions (VERSIONS: Rail, BRT, All), each laid out on its own
over the modes it shows (a layout for rail alone is not bent by the bus grid).
Each layout is computed once, at build time, over the *union* of every station
and stop-to-stop edge of those modes in every scenario, so the diagram does not
move when the page switches plan or year; the page only shows, hides or fades
parts of it. Everything is read from the loaded networks (stations, stop
sequences, segment geometry, transfers); nothing is hard-coded. It is
deterministic (no randomness, everything iterated in sorted order); a version
takes ~15-40 s per variant (layout_json caches it in the temp folder).

Method
------
1. **Union graph.** Nodes are stations; stations at the same place (within
   40 m, the same name within 400 m, transfer-linked within 150 m, or a walk
   transfer within MERGE_WALK_KM, 300 m, as long as the group spans no more)
   merge into one interchange node ("Akard · Metro Center"), never two stops of
   one routing (a line may stop at one in one plan and the other in another)
   and never above degree 8.
   A line whose track (segment geometry) passes within 120 m of another station
   is drawn *through* that node when that joins an existing corridor, so
   express hops bundle with the local line instead of fanning out separately.
2. **Density-equalizing pre-warp.** A diffusion cartogram (Gastner & Newman
   2004; FFT on a grid) driven by "ink" density: stations plus samples along
   every edge weighted by its number of lines. The flow is continuous, so it
   cannot fold; it expands the Fort Worth and Dallas cores and compresses the
   long commuter-rail reaches. The scale is set so the median hop is EDGE_MED.
3. **Straightness rules** (looser geography, before any direction is chosen).
   *Strokes*: at every station the two edge ends that the most lines run
   straight through are joined (the default plan's routings first; not across
   a turn sharper than STROKE_TURN, and not where every line ends), so a trunk
   is one stroke through its junctions (_strokes). Stations are pulled into
   line along their strokes, and every stroke that runs along one of the four
   axes in the real geography (a north-south trunk, an east-west line) is laid
   exactly along it, heaviest first, edge by edge, as long as that agrees with
   those laid already; the lighter branch takes the bend (_smooth). A *firm*
   stroke, very straight over many stations (AXIS_FIRM, AXIS_FIRM_N: the Fort
   Worth Main / Terminal - La Gran Plaza trunk), is laid even where the warp
   left other lines in its way (they give way), keeps its axis AXIS_FIRM_DP
   times as hard below and never gets a bend. These positions anchor
   everything after.
4. **Octilinear directions.** Chains of degree-2 stations between junctions or
   termini are the units of the drawing. At each junction the incident chains
   get distinct ports (8 directions) by exhaustive search over assignments that
   keep the cyclic order of neighbours, each aimed along its chain's general
   direction (its next few stations), ends that lines run straight through kept
   opposite (T_THROUGH), no line turned back on itself (T_SHARP) and axis edges
   on their axis (AXIS_DP); termini get no
   port, so a line's last stretch is free to run straight on. Along each chain
   a dynamic program (_turn_dp) picks one direction per edge, trading squared
   angular deviation (from the edge and from the chain's course) against a
   cost per turn (B_TURN: 45° cheap, 90° dear, sharper forbidden) and a further
   cost for a turn back within ZZ_HOPS edges (a zig-zag). A change of direction
   is moved off the station into the longer adjacent edge, which gets one bend.
5. **Least-squares relaxation.** Positions (plus the two leg lengths of each
   bent edge) solve a linear least-squares problem: each straight edge lies
   along its direction (perpendicular residual, weight ramped up), has a
   chain-smoothed target length (even station spacing), and every node is
   weakly anchored to its pre-warped position; walk-linked stations that
   couldn't merge (transfer pairs: within the walk radius, or linked in
   transfers.csv) are pulled to sit side by side, hard (W_XFER, and already
   in step 3's smoothing, W_XFER_S), a long explicit link only gently. Node pairs and drawn pieces of different corridors that are too
   close become linearized separation rows on the next solve (active set).
   Directions are re-assigned for N_ASSIGN rounds, then frozen; edges that
   still collapse or sit far off their direction, or that hold two stations
   under the minimum spacing, get one bend. Then the geography gives way to
   straight lines where there is room: a bend whose chain runs straight on in
   one of its leg directions, a jog (a line running on 45° off for a few edges
   and back), a V or a 135° turn along a line, across junctions too (_kinks;
   only where that lowers the turn cost of every line on those edges), and a
   short stub at a terminus turning 45° off its line, are
   tried straight; those the relaxation can't hold, that crowd a station or
   that turn an edge round (two stations swapping places), keep their kink
   (kinks near trouble are put off and retried a few at a time).
   Last, with the stations fixed, an edge where a line turns back on itself at
   a station (135 degrees or more) is redrawn another octilinear way if that
   eases it without crowding anything (_unsharp).
   Steps 4-5 are chaotic (a small change can tip a junction elsewhere), so they
   run once per VARIANT (in parallel processes) and the drawing with the best
   quality() is kept: fewest bends, zig-zags, sharp turns, crossings beyond
   the geography's, edges drawn backwards and walk-linked pairs left apart.
6. **Exact octilinearity and spacing.** A least-norm projection makes every
   straight edge exactly octilinear; each bent edge is drawn as two octilinear
   legs. If any two stations were still under MIN_SP, the whole layout is
   scaled uniformly (angles unchanged) so the minimum spacing always holds.
7. **Line ordering.** In each chain the lines get one order; permutations are
   improved by local search minimizing crossings at the junctions, measured
   geometrically from each line's port position.
8. **Waterways**, stylized, not traced. Rivers ride the same cartogram flow
   plus the smoothed displacement of nearby stations, are clipped to the
   network's surroundings, simplified hard (Douglas-Peucker, RIVER_DP), snapped
   to octilinear runs and given rounded corners (Chaikin): ribbons, not outlines.
   A lake is placed by a local affine fit (geographic -> layout) at its centroid
   and drawn as a soft ellipse with its area and principal axes (long axis on
   one of the eight directions), shrunk to clear every station.

Units: 1.0 = the minimum distance between station centres. y grows north here;
the JSON for the page flips it (SVG y grows down).
"""
import collections
import copy
import hashlib
import itertools
import json
import math
import os
import re
import tempfile

import numpy as np

from . import config, geo

PRE = "#pre"          # paths key suffix: a rerouted line's routing before its reroute opens
MIN_SP = 1.0          # minimum distance between station centres
PITCH = 0.30          # offset between parallel lines in a corridor
MERGE_KM = 0.04       # always merge stations closer than this
MERGE_NAME_KM = 0.40  # merge same-named stations closer than this
MERGE_LINKED_KM = 0.15  # merge transfer-linked stations closer than this,
MERGE_WALK_KM = 0.30  # and walk-linked ones (within the walk radius) this close: one interchange, not two
                      # markers and a connector (a group so merged spans no more than this)
CONNECTOR_MAX = 1.6   # a walk link this short (centre to centre) is drawn as a connector; a longer one only
                      # faintly, around the station selected (it would cross the core: the page)
W_XFER_S = 25.0       # walk-linked stations (transfers) are pulled this hard to sit side by side in _smooth,
W_XFER = 4.0          # ... and in the least-squares relaxation (a stop-to-stop edge's length weighs W_LEN)
LABEL_GROUP = 8.0     # same-named stations (ignoring a compass suffix) this close share one label when zoomed out
LAKE_SCALE = 0.8      # lakes are drawn a little smaller than their local scale
LAKE_ASPECT = 3.0     # a lake's blob is at most this elongated
LAKE_CLEAR = 0.55     # and clears every station centre by this much
LAKE_MIN = 0.3        # a blob narrower than this (half-width) is left out
RIVER_DP = 1.6        # rivers are simplified this hard (layout units) before the octilinear snap
PASS_KM = 0.12        # a line passing this close to another station is drawn through it
SIGMA_KM = 0.8        # station density smoothing for the cartogram
BACKGROUND = 0.10     # uniform density added (relative to the mean); smaller = stronger equalization
INK = 1.0             # cartogram mass per km of line (stations weigh 1)
EDGE_MED = 2.6        # target median stop-to-stop length after the pre-warp
L_MIN, L_MAX = 1.3, 8.0
PORT_LOOK = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)  # weights of a chain's next stations when aiming its port
N_ASSIGN, N_RELAX, N_STRAIGHTEN = 10, 14, 30
# compute() lays out each of these and keeps the best: how strongly stations keep to their
# pre-warped places (w_anc, W_ANC) and the cap on hop length when ranking axis strokes
# (hop_km, AXIS_HOP_KM: short-hop multi-line trunks first, or long lines first), and whether
# two axis edges may leave a station the same way (unique: no), each with the walk-link pulls
# (W_XFER_S, W_XFER) at full strength and weaker (xfer)
VARIANTS = tuple(dict(v, xfer=x) for x in (1.0, 0.6, 0.35) for v in
                 ({"w_anc": 0.05, "hop_km": 1.5, "unique": True}, {"w_anc": 0.15, "hop_km": 99.0, "unique": False}))
MAX_PROCS = 2         # variants laid out in parallel at most (each holds a few dense n x n matrices)
STRAIGHT_FEW = 3      # kinks put off in phase 3 are tried this many at a time
W_REP = 12.0
W_LEN = 1.5
W_ANC = 0.15
DEV_BEND = 25.0       # a straight edge still this far (degrees) off its direction gets a bend
STRAIGHT_SP = 0.8      # phase 3 keeps a straightened edge only if no station ends up closer than this
SP_AIM = 1.2          # the relaxation aims this much above MIN_SP (the final scale guarantees MIN_SP)
SHRINK = 0.45         # a straight edge shrunk below this fraction of its target gets a bend
SEG_GAP = 0.45        # clear space between the outer strokes of two corridors
# straightness rules (_strokes, _smooth, _ports, _chain_dirs)
STROKE_TURN = 70.0    # two edge ends join into one stroke only if they turn less than this (degrees)
DEFAULT_W = 4.0       # a line of the default plan counts this many times in a stroke
SMOOTH = 40.0         # how hard stations are pulled into line along their stroke (_smooth)
AXIS_TOL = 0.12       # a stroke that strays less than this from an axis (RMS offset / length)
AXIS_MIN = 4          # ... and has at least this many edges keeps to that axis:
AXIS = 1000.0         # its edges are laid along the axis this stiffly (_smooth),
AXIS_LEN = 5.0        # and pulled to their pre-warped length this hard,
AXIS_EDGE = 35.0      # those within this many degrees of the axis in the real geography,
AXIS_JOG, AXIS_JOG_KM = 65.0, 0.8   # (a hop shorter than AXIS_JOG_KM: AXIS_JOG degrees; small jogs stay on the axis)
AXIS_MISS = 0.2       # unless that misses by more than this fraction of the edge's length
AXIS_HOP_KM = 1.5     # strokes are laid heaviest first: lines squared x hop length (capped at this)
AXIS_CROSS = True     # ... and an edge whose laying pushes one line across another stays free
AXIS_FIRM, AXIS_FIRM_N = 0.08, 12   # ... except a firm stroke, a very straight one of many stations: the others give way to it,
AXIS_FIRM_DP = 40.0   # and its edges keep to the axis this many times as hard (AXIS_DP), and are never bent
AXIS_KEEP = 0.6      # a stroke that can lay less than this share of its edges is left free
AXIS_DP = 1.0         # directions of axis edges pay this per 45 degrees off the axis (VARIANTS)
SMOOTH_W = 4.0        # a chain's course: its direction over +-this much (layout units)
W_RAW = 0.3           # weight of an edge's own direction against the chain's course
B_TURN = (0.0, 1.2, 3.5, 30.0)          # cost of a turn by 0, 45, 90, 135 degrees
Z_ZIG = 2.5           # extra for a turn back within ZZ_HOPS edges of the last turn (a zig-zag)
ZZ_HOPS = 3
ZZ_LEN = 4.0          # quality(): two opposite turns this close (layout units) make a zig-zag
T_THROUGH = 0.5       # per line running straight through a junction, per 45 degrees its ports turn
T_SHARP = 4.0         # per line turning back on itself (135 degrees or more) at a junction's ports
UNSHARP_LEG, UNSHARP_GAP = 0.25, 0.45   # _unsharp: shortest leg of a redrawn edge; clearance it keeps
DIRS = np.array([(math.cos(k * math.pi / 4), math.sin(k * math.pi / 4)) for k in range(8)])
CITY_KM = 1.2         # an area name stands beside the busiest station this close to its centre
CITIES = [("Fort Worth", 32.7555, -97.3308), ("Dallas", 32.7810, -96.7990), ("Denton", 33.2148, -97.1331),
          ("Arlington", 32.7357, -97.1081), ("DFW Airport", 32.8998, -97.0403), ("Plano", 33.0198, -96.6989)]


def _norm_name(s):
    s = s.lower().replace("square", "sq")
    return re.sub(r"[^a-z0-9]", "", s)


_SUFFIX = re.compile(r"\s+(?:N|S|E|W|NE|NW|SE|SW)\d*$")


def base_name(s):
    """A station name without a trailing compass suffix ("Irving W3" -> "Irving")."""
    return _SUFFIX.sub("", s).strip()


def label_groups(lay):
    """Leader node per node: stations with the same base name that are close on
    the diagram ("Uptown", "Uptown", "Design District W" ...) form one group, so
    the page can label the group once when zoomed out. The leader is the member
    without a suffix if there is one, then the one with the most lines."""
    n = len(lay.nodes)
    deg = collections.Counter()
    for ed in lay.edges:
        deg[ed["a"]] += len(ed["lines"])
        deg[ed["b"]] += len(ed["lines"])
    parent = list(range(n))

    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    by = collections.defaultdict(list)
    for v, nd in enumerate(lay.nodes):
        by[base_name(nd["name"]).lower()].append(v)
    for vs in by.values():
        for a, b in itertools.combinations(vs, 2):
            A, B = lay.nodes[a], lay.nodes[b]
            if math.hypot(A["x"] - B["x"], A["y"] - B["y"]) <= LABEL_GROUP:
                parent[find(b)] = find(a)
    groups = collections.defaultdict(list)
    for v in range(n):
        groups[find(v)].append(v)
    lead = list(range(n))
    for vs in groups.values():
        k = min(vs, key=lambda v: (base_name(lay.nodes[v]["name"]) != lay.nodes[v]["name"], -deg[v],
                                   len(lay.nodes[v]["name"]), v))
        for v in vs:
            lead[v] = k
    return lead


def _angdiff(a, b):
    d = (a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


XFER_KEEP = 0.5       # (a pair the warp spread apart keeps this share of that, see _xfer_pairs)
XFER_LONG = 0.1      # (an explicit transfers.csv link beyond the walk radius: this fraction of the pull)
XFER_FAR, W_APART = 1.6, 4.0    # quality(): a walk-linked pair drawn this many times its pull distance apart costs this


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
        self.scale = 1.0       # the uniform rescale the minimum spacing needed
        self.w_xfer = (W_XFER_S, W_XFER)
        self.xfer_t = None     # _xfer_pairs, set by _place
        self.firm = set()      # edges of firm axis strokes, set by _smooth


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
            # a rerouted line's old routing (it runs until the new track opens) is laid out
            # too, under the scenario key + PRE, so the page can draw it in the early years
            for _, until, old, it in net.variants.get(ln.id, []):
                if it.get("reroute"):
                    seqs.append((key + PRE, ln.id, list(old.stop_ids), [s.pts for s in old.segments]))
    used = sorted({s for _, _, ss, _ in seqs for s in ss})
    xy = {s: np.array(proj.xy(stations[s].lat, stations[s].lon)) for s in used}
    line_sets = collections.defaultdict(set)
    seq_sets = collections.defaultdict(set)       # the stop sequences (scenario routings) through each station
    nbrs = collections.defaultdict(set)
    for q, (_, lid, ss, _) in enumerate(seqs):
        for s in ss:
            line_sets[s].add(lid)
            seq_sets[s].add(q)
        for a, b in zip(ss, ss[1:]):
            nbrs[a].add(b)
            nbrs[b].add(a)
    transfers = set()
    radius = next(iter(nets.values())).cfg["transfer"]["walk_radius_m"] / 1000
    for net in nets.values():
        for a, b, _, _ in net.transfers:
            if a in xy and b in xy:
                transfers.add(frozenset((a, b)))
    # merge co-located stations (union-find), never two stops of one routing, max degree 8
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
        walk = D[i, j] < min(MERGE_WALK_KM, radius) and frozenset((a, b)) in transfers
        if not (D[i, j] < MERGE_KM or same or linked or walk) or b in nbrs[a]:
            continue
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        members = [s for s in used if find(s) in (ra, rb)]
        # never two stops of one routing (a line may stop at one in one plan and at the other
        # in another: a stop moved down the street is still the same interchange)
        if any(x & y for x, y in itertools.combinations([seq_sets[s] for s in members], 2)):
            continue
        idx = [used.index(s) for s in members]
        if walk and not (D[i, j] < MERGE_KM or same or linked) and D[np.ix_(idx, idx)].max() > MERGE_WALK_KM:
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
    lay.walk_km = radius
    lay.modes = modes
    lay.seqs = [(k, lid, path) for (k, lid), (path, _) in sorted(lay.paths.items())]
    # a ring (its stop list ends where it starts, e.g. the Beltline) has no terminus
    lay.termini = {path[i] for _, _, path in lay.seqs for i in (0, -1) if path[0] != path[-1]}
    # the default plan's edges: the straightness rules follow its routings (the others'
    # alternatives are laid out too, but don't bend its trunks)
    default = next(iter(nets.values())).cfg.get("default_scenario")
    default = default if default in nets else ("plan" if "plan" in nets else None)
    lay.default = default
    lay.prime = {lay.eidx[(min(a, b), max(a, b))] for k, _, path in lay.seqs if k == default or default is None
                 for a, b in zip(path, path[1:])}
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


TURN_COST = (0.0, 1.0, 3.0, 8.0, 50.0)     # _turn_cost: a turn by 0, 45, 90, 135, 180 degrees


def _line_dirs(lay, path, dirs, bent, override=None):
    """A line's drawn directions along a node path, from the assigned directions (a bent edge
    gives its two legs; override {edge: direction} replaces some): [(direction, edge, from node)]."""
    out = []
    for u, w in zip(path, path[1:]):
        e = lay.eidx[(min(u, w), max(u, w))]
        fwd = lay.edges[e]["a"] == u
        if override and e in override:
            ds = [override[e]]
        elif e in dirs:
            ds = [dirs[e]]
        elif e in bent:
            ds = list(bent[e])
        else:
            return None
        out += [((d if fwd else (d + 4) % 8), e, u) for d in (ds if fwd else ds[::-1])]
    return out


def _turn_cost(lay, dirs, bent, edges, override):
    """Turn cost (TURN_COST per turn, plus one more for a turn straight back within ZZ_HOPS
    pieces) of the default plan's lines that use any of `edges`, with `override` applied."""
    edges, total = set(edges), 0.0
    for key, _, path in lay.seqs:
        if (lay.default is not None and key != lay.default) or not edges & set(_path_edges(lay, path)):
            continue
        ds = _line_dirs(lay, path, dirs, bent, override)
        if not ds:
            continue
        last = None
        for k in range(1, len(ds)):
            t = (ds[k][0] - ds[k - 1][0]) % 8
            t = t - 8 if t > 4 else t
            if t:
                total += TURN_COST[abs(t)]
                if last and last[0] * t < 0 and k - last[1] <= ZZ_HOPS:
                    total += 1.0
                last = (t, k)
    return total


def _path_edges(lay, path):
    return [lay.eidx[(min(u, w), max(u, w))] for u, w in zip(path, path[1:])]


def _kinks(lay, dirs, bent=None):
    """Kinks along the default plan's lines, as (run [(edge, from node)], new direction): the
    middle run of a V or a 45-degree jog (at most ZZ_HOPS straight edges between a turn and
    one back), turned towards the line's course, and the shorter run (at most ZZ_HOPS edges) at
    a 135-degree turn, turned 45 degrees to ease it."""
    out = []
    for key, _, path in lay.seqs:
        if lay.default is not None and key != lay.default:
            continue
        runs = []          # [direction or None, [(straight edge, from node)], all straight]
        for d, e, u in _line_dirs(lay, path, dirs, bent or {}) or []:
            if runs and runs[-1][0] == d and (e in dirs) == runs[-1][2] and (e in dirs):
                runs[-1][1].append((e, u))
            elif runs and runs[-1][0] == d and runs[-1][1][-1][0] == e:
                continue          # the second leg of a bent edge running on
            else:
                runs.append([d, [(e, u)], e in dirs])
        turn = lambda a, b: ((b - a) % 8) - 8 if (b - a) % 8 > 4 else (b - a) % 8  # noqa: E731
        for i in range(1, len(runs)):
            A, B = runs[i - 1], runs[i]
            if A[0] is None or B[0] is None:
                continue
            t = turn(A[0], B[0])
            sg = 1 if t > 0 else -1
            if abs(t) == 3:
                for r, nd in sorted(((A, (A[0] + sg) % 8), (B, (B[0] - sg) % 8)), key=lambda c: len(c[0][1])):
                    if r[2] and len(r[1]) <= ZZ_HOPS:
                        out.append((r[1], nd))
                        break
            elif abs(t) in (1, 2) and i + 1 < len(runs) and B[2] and len(B[1]) <= ZZ_HOPS:
                if turn(B[0], runs[i + 1][0]) == -t:
                    out.append((B[1], (B[0] - sg) % 8))
    return out


def _passes(lay):
    """{node: {(e1, e2): how many lines run e1 -> node -> e2}} (e1 < e2): each line counts
    once per scenario that runs it so (the default scenario DEFAULT_W times), so the
    routings most plans share, and the default plan's, weigh most."""
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for key, lid, ns in lay.seqs:
        if key.endswith(PRE):
            continue
        w = DEFAULT_W if key == lay.default else 1.0
        ring = len(ns) > 3 and ns[0] == ns[-1]
        for k in range(1, len(ns) - 1 + ring):        # a ring runs on through where it closes
            nxt = ns[k + 1] if k + 1 < len(ns) else ns[1]
            e1 = lay.eidx[(min(ns[k - 1], ns[k]), max(ns[k - 1], ns[k]))]
            e2 = lay.eidx[(min(ns[k], nxt), max(ns[k], nxt))]
            if e1 != e2:
                out[ns[k]][(min(e1, e2), max(e1, e2))] += w
    return out


def _strokes(lay, inc, X):
    """Strokes: the long runs the drawing keeps straight. At every station the two edge ends
    that the most lines run straight through are joined (not across a turn sharper than
    STROKE_TURN degrees; at a plain station of degree 2 always; two edges of the default
    plan before others), so a trunk is one stroke through its junctions and branches peel
    off it.
    Returns (strokes, mate): strokes [(nodes, edges)] (a walk v0 e0 v1 e1 ... vm) and
    mate {(node, edge): the edge the stroke continues into at that node: lines through}."""
    passes = _passes(lay)
    other = lambda e, v: lay.edges[e]["b"] if lay.edges[e]["a"] == v else lay.edges[e]["a"]  # noqa: E731
    mate = {}
    for v in range(len(lay.nodes)):
        cand = []
        for e1, e2 in itertools.combinations(sorted(inc[v]), 2):
            u1, u2 = X[other(e1, v)] - X[v], X[other(e2, v)] - X[v]
            ang = math.degrees(_angdiff(math.atan2(u1[1], u1[0]), math.atan2(u2[1], u2[0])))
            n = passes[v].get((e1, e2), 0)
            if (ang < 180 - STROKE_TURN or n == 0) and len(inc[v]) > 2:
                continue
            if n == 0 and v in lay.termini:     # every line there ends there: nothing runs straight on
                continue
            cand.append((-((e1 in lay.prime) + (e2 in lay.prime)), -n, -ang, e1, e2))
        for _, n, _, e1, e2 in sorted(cand):
            if (v, e1) not in mate and (v, e2) not in mate:
                mate[(v, e1)], mate[(v, e2)] = (e2, -n), (e1, -n)
    seen, strokes = set(), []

    def walk(v, e):
        nodes, es = [v], []
        while e is not None and e not in seen:
            seen.add(e)
            es.append(e)
            v = other(e, v)
            nodes.append(v)
            e = mate.get((v, e), (None,))[0]
        return nodes, es
    for v in range(len(lay.nodes)):           # from every free end
        for e in sorted(inc[v]):
            if e not in seen and (v, e) not in mate:
                strokes.append(walk(v, e))
    for e in range(len(lay.edges)):           # closed loops
        if e not in seen:
            strokes.append(walk(lay.edges[e]["a"], e))
    return strokes, mate


def stroke_axis(P):
    """The octilinear axis (0..3: E-W, NE-SW, N-S, NW-SE) a run of points P follows, and
    how far it strays from it: RMS distance off the axis line / extent along it."""
    c = P.mean(0)
    _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    k = int(round(math.atan2(Vt[0, 1], Vt[0, 0]) / (math.pi / 4))) % 4
    u, nr = DIRS[k], DIRS[(k + 2) % 8]
    along, off = (P - c) @ u, (P - c) @ nr
    ext = along.max() - along.min()
    return k, float(np.sqrt((off ** 2).mean()) / ext) if ext > 1e-9 else 1e9


def _axis_strokes(lay, G, strokes, hop_km=AXIS_HOP_KM):
    """Strokes that run roughly along one of the four axes in the real geography G
    (stroke_axis strays less than AXIS_TOL; at least AXIS_MIN edges), heaviest first (lines
    x length): [(axis 0..3, [edges], firm)], leaving out stretches that cross the axis (more
    than AXIS_EDGE degrees off it) and edges the default plan doesn't use. firm: a very
    straight stroke of many stations (AXIS_FIRM_N edges, straying less than AXIS_FIRM)."""
    out = []
    for nodes, es in strokes:
        if len(es) >= AXIS_MIN and len(set(nodes)) == len(nodes):
            k, stray = stroke_axis(G[nodes])
            if stray < AXIS_TOL:
                keep = []
                for a, b, e in zip(nodes, nodes[1:], es):
                    v = G[b] - G[a]
                    off = _angdiff(math.atan2(v[1], v[0]) % math.pi, k * math.pi / 4)
                    lim = AXIS_EDGE if np.linalg.norm(v) > AXIS_JOG_KM else AXIS_JOG
                    if min(off, math.pi - off) < math.radians(lim) and e in lay.prime:
                        keep.append(e)
                wt = sum(len(lay.edges[e]["lines"]) ** 2 * min(np.linalg.norm(G[lay.edges[e]["a"]] - G[lay.edges[e]["b"]]), hop_km) for e in es)
                if keep:
                    out.append((-wt, es[0], k, keep, stray < AXIS_FIRM and len(es) >= AXIS_FIRM_N))
    return [(k, keep, firm) for _, _, k, keep, firm in sorted(out)]


def _axis_off(d, k):
    """45-degree steps between direction d (0..7) and axis k (0..3, either way along it)."""
    return min((d - k) % 4, (k - d) % 4)


def _smooth(lay, A, G, strokes, hop_km=AXIS_HOP_KM, unique=True):
    """Looser geography, before any direction is chosen: positions smoothed along every
    stroke and laid along the axes that hold, against a unit pull of each station to its
    pre-warped place A. Linear least squares in (x, y) of every station.
    - Each station inside a stroke is pulled onto the segment between its stroke
      neighbours (at its own fraction of the way, so spacing ratios stay), weighted by
      SMOOTH and the lines it carries (a fifth of that off the default plan's routings):
      wiggles a few stations long go.
    - Axis strokes (_axis_strokes), heaviest first, are then laid along their axis edge by
      edge: stiffly across the axis (AXIS), softly in length (AXIS_LEN, towards the
      pre-warped length). An edge that can't take its axis given those already laid (it,
      or one laid before, would miss by more than AXIS_MISS of its length, or shrink below
      a quarter of it) is left free. So a north-south trunk is drawn north-south through
      its junctions, and of two branches leaving one station along the same axis the
      lighter one takes the bend; the two never meet halfway.
    Each edge is a rank-one update of the inverse (Sherman-Morrison), so trying one costs
    O(n^2). Returns (positions, {edge: axis} of the edges laid along an axis)."""
    n = len(A)
    M = np.eye(2 * n)
    for nodes, es in strokes:
        for k in range(1, len(nodes) - 1):
            u, v, w = nodes[k - 1], nodes[k], nodes[k + 1]
            if len({u, v, w}) < 3:
                continue
            l1, l2 = np.linalg.norm(A[v] - A[u]), np.linalg.norm(A[w] - A[v])
            t = l1 / (l1 + l2 + 1e-9)
            nl = len(lay.edges[es[k - 1]]["lines"]) + len(lay.edges[es[k]]["lines"])
            wt = SMOOTH * (1.0 if es[k - 1] in lay.prime and es[k] in lay.prime else 0.2) * min(nl / 2, 3) ** 0.5
            c = np.array([1.0, -(1 - t), -t])
            for d in range(2):
                ix = [2 * v + d, 2 * u + d, 2 * w + d]
                M[np.ix_(ix, ix)] += wt * np.outer(c, c)
    rhs = A.reshape(-1).copy()
    for a, b, t, f in _xfer_pairs(lay, _radius(lay)):
        g = A[b] - A[a]
        g = g / (np.linalg.norm(g) + 1e-9) * t
        w = lay.w_xfer[0] * f
        for d in range(2):
            ia, ib = 2 * a + d, 2 * b + d
            M[ia, ia] += w
            M[ib, ib] += w
            M[ia, ib] -= w
            M[ib, ia] -= w
            rhs[ib] += w * g[d]
            rhs[ia] -= w * g[d]
    Minv = np.linalg.inv(M)
    st = {"M": M, "rhs": rhs, "Minv": Minv, "x": Minv @ rhs, "acc": np.zeros((0, 6)),   # acc: a, b, u, length, scale
          "axes": {}, "taken": set(), "firm": set()}     # taken: (station, direction) of the laid edges
    ea = np.array([ed["a"] for ed in lay.edges], int)
    eb = np.array([ed["b"] for ed in lay.edges], int)

    def lay_edge(e, k, check):
        """Lay edge e along axis k if it holds; check: only if that adds no crossing."""
        a, b = lay.edges[e]["a"], lay.edges[e]["b"]
        d = k if (G[b] - G[a]) @ DIRS[k] >= 0 else k + 4
        if unique and ((a, d) in st["taken"] or (b, (d + 4) % 8) in st["taken"]):
            return False          # another edge already leaves that station that way
        u = DIRS[d]
        nr, ln = np.array([-u[1], u[0]]), float(np.linalg.norm(A[b] - A[a]))
        ix = [2 * b, 2 * b + 1, 2 * a, 2 * a + 1]
        cn = np.array([nr[0], nr[1], -nr[0], -nr[1]])     # across the axis
        cu = np.array([u[0], u[1], -u[0], -u[1]])         # along it
        # the two rows as rank-one updates of the inverse (Sherman-Morrison): a trial
        # costs O(n); only an edge that is laid updates the whole inverse
        Minv, x = st["Minv"], st["x"]
        m1 = Minv[:, ix] @ cn
        f1 = AXIS / (1 + AXIS * (cn @ m1[ix]))
        x1 = x + m1 * (f1 * (0.0 - cn @ x[ix]))
        m2 = Minv[:, ix] @ cu - m1 * (f1 * (m1[ix] @ cu))
        f2 = AXIS_LEN / (1 + AXIS_LEN * (cu @ m2[ix]))
        x1 = x1 + m2 * (f2 * (ln - cu @ x1[ix]))
        cand = np.vstack([st["acc"], [a, b, u[0], u[1], ln, max(ln, 1.0)]])
        ia, ib = cand[:, 0].astype(int), cand[:, 1].astype(int)
        dv = x1.reshape(n, 2)[ib] - x1.reshape(n, 2)[ia]
        across = np.abs(dv[:, 0] * -cand[:, 3] + dv[:, 1] * cand[:, 2])
        along = dv[:, 0] * cand[:, 2] + dv[:, 1] * cand[:, 3]
        if (across > AXIS_MISS * cand[:, 5]).any() or (along < 0.25 * cand[:, 4]).any():
            return False          # it can't take the axis given those laid already: left free
        if check and _n_crossings(x1.reshape(n, 2), ea, eb) > _n_crossings(x.reshape(n, 2), ea, eb):
            return False          # it would push a line across another
        st["Minv"] = Minv - np.outer(m1, m1 * f1) - np.outer(m2, m2 * f2)
        st["M"][np.ix_(ix, ix)] += AXIS * np.outer(cn, cn) + AXIS_LEN * np.outer(cu, cu)
        st["rhs"][ix] += AXIS_LEN * ln * cu
        st["x"], st["acc"] = x1, cand
        st["axes"][e] = k
        st["taken"] |= {(a, d), (b, (d + 4) % 8)}
        return True

    def snapshot():
        return {k: (v.copy() if hasattr(v, "copy") else v) for k, v in st.items()}
    for k, es, firm in _axis_strokes(lay, G, strokes, hop_km):
        es = [e for e in es if e not in st["axes"]]
        before, n0 = snapshot(), _n_crossings(st["x"].reshape(n, 2), ea, eb)
        laid = sum(lay_edge(e, k, False) for e in es)
        if AXIS_CROSS and not firm and _n_crossings(st["x"].reshape(n, 2), ea, eb) > n0:
            # the stroke pushed lines across others: lay it again edge by edge, leaving
            # out the edges that do
            st.update(before)
            before = snapshot()
            laid = sum(lay_edge(e, k, True) for e in es)
        if laid < AXIS_KEEP * len(es):     # only bits of it: that would make a staircase
            st.update(before)
        elif firm:
            st["firm"] |= {e for e in es if e in st["axes"]}
    M, rhs, axes = st["M"], st["rhs"], st["axes"]
    lay.firm = st["firm"]
    return np.linalg.solve(M, rhs).reshape(n, 2), axes


def _n_crossings(P, ea, eb):
    """Proper crossings among the straight station-to-station segments (ea[i], eb[i]) at
    positions P, of segments that share no station."""
    p, q = P[ea], P[eb]
    lo, hi = np.minimum(p, q), np.maximum(p, q)
    i, j = np.nonzero(np.triu(np.all((lo[:, None] <= hi[None]) & (lo[None] <= hi[:, None]), axis=2), 1))
    keep = (ea[i] != ea[j]) & (ea[i] != eb[j]) & (eb[i] != ea[j]) & (eb[i] != eb[j])
    i, j = i[keep], j[keep]

    def orient(a, b, c):
        return (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    d1, d2 = orient(p[j], q[j], p[i]), orient(p[j], q[j], q[i])
    d3, d4 = orient(p[i], q[i], p[j]), orient(p[i], q[i], q[j])
    return int(((d1 * d2 < -1e-12) & (d3 * d4 < -1e-12)).sum())


def _ports(X, chains, through=None, axes=None, axis_dp=AXIS_DP, firm=(), turning=None):
    """Port (direction index 0..7) for each chain end at a junction: ends[(chain, 0|1)].
    Each end aims along its chain's general direction (its first few stations, nearest
    weighted most); a terminus gets no port, so its chain is free to run straight.
    `through` {(chain end), (chain end): lines} pairs ends at one junction that lines run
    straight through: their ports should be opposite (T_THROUGH per line and 45 degrees off);
    an end on an axis stroke (`axes` {edge: axis}) pays axis_dp per 45 degrees off the axis
    (AXIS_FIRM_DP times that on a firm stroke's edge, `firm`). `turning` {(chain end), (chain
    end): lines} pairs the ends that any line runs between: a port pair that would turn those
    lines back on themselves (by 135 degrees or more) pays T_SHARP per line."""
    at = collections.defaultdict(list)       # node -> [(chain idx, end)]
    for ci, (nodes, _) in enumerate(chains):
        at[nodes[0]].append((ci, 0))
        at[nodes[-1]].append((ci, 1))
    through = through or {}
    ports = {}
    order = sorted(at, key=lambda v: (-len(at[v]), v))
    for v in order:
        ends = at[v]
        if len(ends) == 1:     # a terminus: nothing to fit around, its chain finds its own way
            continue
        angs = []
        for ci, end in ends:
            nodes = chains[ci][0] if end == 0 else chains[ci][0][::-1]
            r = np.zeros(2)
            for j, wt in zip(range(1, len(nodes)), PORT_LOOK):
                d = X[nodes[j]] - X[v]
                r += wt * d / (np.linalg.norm(d) + 1e-9)
            angs.append(math.atan2(r[1], r[0]))
        # preferred ports from already-assigned single-edge neighbours
        pref = []
        for ci, end in ends:
            nodes = chains[ci][0]
            other = (ci, 1 - end)
            pref.append((ports[other] + 4) % 8 if len(nodes) == 2 and other in ports else None)
        k = len(ends)
        pairs = [(i, j, through[(ends[i], ends[j])]) for i in range(k) for j in range(i + 1, k)
                 if (ends[i], ends[j]) in through]
        turns = [(i, j, (turning or {})[(ends[i], ends[j])]) for i in range(k) for j in range(i + 1, k)
                 if (ends[i], ends[j]) in (turning or {})]
        ax = [(axes or {}).get(chains[ci][1][0 if end == 0 else -1]) for ci, end in ends]
        aw = [axis_dp * (AXIS_FIRM_DP if chains[ci][1][0 if end == 0 else -1] in firm else 1.0) for ci, end in ends]
        idx = sorted(range(k), key=lambda i: angs[i])
        best, bestc = None, 1e18
        for combo in itertools.combinations(range(8), min(k, 8)):
            for s in range(len(combo)):
                cost = 0.0
                pk = [0] * k
                for r, i in enumerate(idx):
                    dk = pk[i] = combo[(r + s) % len(combo)] if r < len(combo) else combo[0]
                    cost += _angdiff(angs[i], dk * math.pi / 4) ** 2
                    if ax[i] is not None:
                        cost += aw[i] * _axis_off(dk, ax[i])
                    if pref[i] is not None and pref[i] != dk:
                        cost += 0.6
                for i, j, nl in pairs:
                    off = abs(4 - (pk[i] - pk[j]) % 8)
                    cost += T_THROUGH * min(nl / 2, 3) * off
                for i, j, nl in turns:
                    if abs(4 - (pk[i] - pk[j]) % 8) >= 3:
                        cost += T_SHARP * min(nl, 3)
                if cost < bestc - 1e-12:
                    bestc, best = cost, (combo, s)
        combo, s = best
        for r, i in enumerate(idx):
            ports[ends[i]] = combo[(r + s) % len(combo)] if r < len(combo) else combo[0]
    return ports


def _smooth_dirs(P, W):
    """Direction of a polyline P at each piece's midpoint, taken over +-W of arc length."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    out = []
    for k in range(len(seg)):
        m = (s[k] + s[k + 1]) / 2
        lo, hi = max(m - W, 0.0), min(m + W, s[-1])
        if hi - lo < 1e-9:
            lo, hi = s[k], s[k + 1]
        v = np.array([np.interp(hi, s, P[:, 0]) - np.interp(lo, s, P[:, 0]),
                      np.interp(hi, s, P[:, 1]) - np.interp(lo, s, P[:, 1])])
        out.append(math.atan2(v[1], v[0]))
    return out


def _turn_dp(un):
    """Directions (0..7) for a sequence of edges with unary costs un[k, d]: each turn pays
    B_TURN by its size (a U-turn is not allowed), and a turn back the other way within
    ZZ_HOPS edges of the last one (a zig-zag) pays Z_ZIG on top. DP over states
    (direction, side of the last turn, edges since it)."""
    m = len(un)
    H = ZZ_HOPS
    NZ = 1 + 2 * H                     # z = 0: no recent turn; 1..H left turn h ago; H+1..2H right
    INF = 1e18
    cost = np.full((8, NZ), INF)
    cost[:, 0] = un[0]
    back = []
    tcost = [B_TURN[min(t, 8 - t)] if t != 4 else INF for t in range(8)]
    for k in range(1, m):
        new = np.full((8, NZ), INF)
        bk = np.zeros((8, NZ, 2), dtype=int)
        for z in range(NZ):
            sg = 0 if z == 0 else (1 if z <= H else -1)
            h = 0 if z == 0 else (z if z <= H else z - H)
            for dp in range(8):
                c0 = cost[dp, z]
                if c0 >= INF:
                    continue
                for d in range(8):
                    t = (d - dp) % 8
                    if t == 4:
                        continue
                    if t == 0:
                        nz, c = (0 if not sg or h + 1 > H else (h + 1 if sg > 0 else H + h + 1)), c0
                    else:
                        s = 1 if t < 4 else -1
                        c = c0 + tcost[t] + (Z_ZIG if sg and s != sg else 0.0)
                        nz = 1 if s > 0 else H + 1
                    c += un[k, d]
                    if c < new[d, nz] - 1e-12:
                        new[d, nz] = c
                        bk[d, nz] = (dp, z)
        cost = new
        back.append(bk)
    d, z = np.unravel_index(int(np.argmin(cost)), cost.shape)
    out = [int(d)]
    for k in range(m - 1, 0, -1):
        d, z = back[k - 1][d, z]
        out.append(int(d))
    return out[::-1]


def _chain_dirs(X, nodes, p0, p1, axes=None, axis_dp=AXIS_DP, aw=None):
    """One direction per edge of the chain (in chain orientation): each edge pays its squared
    angular deviation from its own course and from the chain's course over +-SMOOTH_W,
    weighted by its length, and axis_dp per 45 degrees off its stroke's axis (axes[k], or
    None; times aw[k] if given); turns and zig-zags pay as in _turn_dp; ports are kept."""
    m = len(nodes) - 1
    P = X[nodes]
    raw, sm = _smooth_dirs(P, 0.0), _smooth_dirs(P, SMOOTH_W)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    un = np.zeros((m, 8))
    for k in range(m):
        w = float(np.clip(seg[k] / EDGE_MED, 0.5, 2.0))
        for d in range(8):
            th = d * math.pi / 4
            un[k, d] = w * (W_RAW * _angdiff(raw[k], th) ** 2 + (1 - W_RAW) * _angdiff(sm[k], th) ** 2)
            if axes and axes[k] is not None:
                un[k, d] += axis_dp * (aw[k] if aw else 1.0) * _axis_off(d, axes[k])
    if p0 is not None:
        un[0] += [0 if d == p0 else 50 for d in range(8)]
    if p1 is not None:
        last = (p1 + 4) % 8
        un[m - 1] += [0 if d == last else 50 for d in range(8)]
    return _turn_dp(un)


def _through(lay, chains, mate):
    """{(end, end): lines} for chain ends meeting at a junction that a stroke runs straight through."""
    endof = {}
    for ci, (nodes, es) in enumerate(chains):
        endof[(nodes[0], es[0])] = (ci, 0)
        endof[(nodes[-1], es[-1])] = (ci, 1)
    out = {}
    for (v, e), (f, n) in mate.items():
        if (v, e) in endof and (v, f) in endof and n > 0:
            out[(endof[(v, e)], endof[(v, f)])] = n
    return out


def _turning(lay, chains):
    """{(end, end): lines} for every pair of chain ends at a junction that some line runs
    between (_passes; both orders)."""
    endof = {}
    for ci, (nodes, es) in enumerate(chains):
        endof[(nodes[0], es[0])] = (ci, 0)
        endof[(nodes[-1], es[-1])] = (ci, 1)
    out = {}
    for v, pp in _passes(lay).items():
        for (e1, e2), n in pp.items():
            if (v, e1) in endof and (v, e2) in endof:
                a, b = endof[(v, e1)], endof[(v, e2)]
                out[(a, b)] = out[(b, a)] = n
    return out


def _assign(lay, X, chains, key, L, through=None, axes=None, axis_dp=AXIS_DP):
    """Edge directions (canonical a->b) and bent edges {e: (d1 from a, d2 into b)}. The edges
    of firm axis strokes (lay.firm) keep to their axis AXIS_FIRM_DP times as hard."""
    axes = axes or {}
    firm = getattr(lay, "firm", set())
    ports = _ports(X, chains, through, axes, axis_dp, firm, getattr(lay, "turning", None))
    dirs, bent = {}, {}
    for ci, (nodes, es) in enumerate(chains):
        cd = _chain_dirs(X, nodes, ports.get((ci, 0)), ports.get((ci, 1)), [axes.get(e) for e in es], axis_dp,
                         [AXIS_FIRM_DP if e in firm else 1.0 for e in es])
        if len(es) == 1 and (ci, 0) in ports and (ci, 1) in ports:
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


def _xfer_pairs(lay, rad, P=None):
    """[(a, b, target distance, weight factor)] for the transfer pairs (walk-linked stations
    drawn as separate nodes), set once per layout from the pre-warped positions P
    (lay.xfer_t). A pair within the walk radius is pulled to sit side by side, just clear of
    each other's bundles (or XFER_KEEP of its pre-warped distance, up to twice that, where the
    warp spread a dense core: pulling every pair there tight would crush it), the closer
    the harder; a longer explicit link (transfers.csv) only gently, to a distance growing
    with the walk."""
    if P is None and getattr(lay, "xfer_t", None) is not None:
        return lay.xfer_t
    out = []
    walk = getattr(lay, "walk_km", 0.4) or 0.4
    partners = collections.Counter(v for t in lay.transfers for v in t)
    for a, b in lay.transfers:
        d = float(np.linalg.norm(lay.nodes[a]["geo"] - lay.nodes[b]["geo"]))
        # a station walk-linked to several others (a downtown web of links) is pulled by each
        # less, so the web doesn't crush the core
        share = 1 / math.sqrt(max(partners[a], partners[b]))
        need = max(MIN_SP * SP_AIM, rad[a] + rad[b] + 0.6)
        t = need * max(1.0, d / walk)
        if P is not None:
            t = max(t, min(XFER_KEEP * float(np.linalg.norm(P[a] - P[b])), 2 * t))
        out.append((a, b, t, float(np.clip(0.25 / max(d, 1e-3), 0.5, 2.5)) * share if d <= walk * 1.01 else XFER_LONG * share))
    return out


def _walk_pair(lay, a, b):
    """Are nodes a and b within the walk radius (not just linked in transfers.csv)?"""
    return float(np.linalg.norm(lay.nodes[a]["geo"] - lay.nodes[b]["geo"])) <= (getattr(lay, "walk_km", 0.4) or 0.4) * 1.01


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
    for a, b, t, f in _xfer_pairs(lay, _radius(lay)):
        g = X[b] - X[a]
        g = g / (np.linalg.norm(g) + 1e-9)
        w = lay.w_xfer[1] * f
        for c in range(2):
            row({2 * b + c: w, 2 * a + c: -w}, w * g[c] * t)
    for coefs, b in rep:
        row(coefs, b)
    N = np.zeros((nv, nv))
    rvec = np.zeros(nv)
    by_len = collections.defaultdict(list)     # normal equations, rows of one length at a time
    for coefs, b in zip(rows, rhs):
        by_len[len(coefs)].append((list(coefs.keys()), list(coefs.values()), b))
    for group in by_len.values():
        C = np.array([c for c, _, _ in group], int)
        V = np.array([v for _, v, _ in group], float)
        B = np.array([b for _, _, b in group], float)
        np.add.at(N, (C[:, :, None], C[:, None, :]), V[:, :, None] * V[:, None, :])
        np.add.at(rvec, C, V * B[:, None])
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
    rows, close = [], []
    diff = X[None, :, :] - X[:, None, :]
    dist = np.sqrt((diff ** 2).sum(-1))
    need = np.maximum(MIN_SP * SP_AIM, rad[:, None] + rad[None, :] + 0.6)
    bad = 0
    for i, k in zip(*np.nonzero(np.triu(dist < need * margin, 1))):
        g = diff[i, k] / dist[i, k] if dist[i, k] > 1e-6 else np.array([1.0, 0.0])
        coefs = {}
        for c in range(2):
            coefs[2 * k + c] = W_REP * g[c]
            coefs[2 * i + c] = -W_REP * g[c]
        rows.append((coefs, W_REP * need[i, k] * 1.05))
        if dist[i, k] < 0.9 * need[i, k] / SP_AIM:
            close.append((int(i), int(k)))
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
    return rows, bad, close


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
        t = u if ed["a"] == v else -u          # the leg touching v, in canonical a->b orientation
        nr = np.array([-t[1], t[0]])           # offsets are to the left of a->b
        lines = order[chain_of[e]]
        off = (lines.index(lid) - (len(lines) - 1) / 2) * PITCH
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
                    R = _dp(np.array(r), RIVER_DP)
                    if np.linalg.norm(np.diff(R, axis=0), axis=1).sum() < 1.5:   # a stub: leave it out
                        continue
                    lay.water["rivers"].append({"name": name, "pts": _chaikin(_octi_path(R), 2)})
            else:
                c = ring.mean(0)
                Yc = _carry(A, X, warped[k - 1].mean(0, keepdims=True))[0]
                if np.sqrt(((X - Yc) ** 2).sum(1)).min() > 6:
                    continue
                Z = _local_affine(G, X, c)(ring)
                Z = (Z - Z.mean(0)) * LAKE_SCALE + Yc
                pts = _lake_blob(Z, X)
                if pts is not None:
                    lay.water["lakes"].append({"name": name, "area": area, "pts": pts})


def _lake_blob(Z, X):
    """A lake outline generalized to a soft ellipse: the outline's area and principal axes
    (aspect at most LAKE_ASPECT), its long axis on the nearest of the eight directions,
    shrunk until it clears every station by LAKE_CLEAR; None when that leaves too little."""
    P = np.vstack([Z, Z[:1]])
    cross = P[:-1, 0] * P[1:, 1] - P[1:, 0] * P[:-1, 1]
    area = abs(cross.sum()) / 2
    if area < 1e-6:
        return None
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)          # second moments of the outline,
    mid = (P[:-1] + P[1:]) / 2                                # sampled evenly along it
    c = (mid * seg[:, None]).sum(0) / seg.sum()
    C = ((mid - c).T * seg) @ (mid - c) / seg.sum()
    w, V = np.linalg.eigh(C)
    ratio = min(LAKE_ASPECT, math.sqrt(max(w[1], 1e-12) / max(w[0], 1e-12)))
    th = round(math.atan2(V[1, 1], V[0, 1]) / (math.pi / 4)) * math.pi / 4
    a, b = math.sqrt(area / math.pi * ratio), math.sqrt(area / math.pi / ratio)
    u, n = np.array([math.cos(th), math.sin(th)]), np.array([-math.sin(th), math.cos(th)])
    L = np.stack([(X - c) @ u, (X - c) @ n], 1)
    s = 1.0
    while s * b >= LAKE_MIN and (((L[:, 0] / (s * a + LAKE_CLEAR)) ** 2 + (L[:, 1] / (s * b + LAKE_CLEAR)) ** 2) < 1).any():
        s *= 0.92
    if s * b < LAKE_MIN:
        return None
    t = np.linspace(0, 2 * math.pi, 40, endpoint=False)
    return c + np.outer(s * a * np.cos(t), u) + np.outer(s * b * np.sin(t), n)


# ---------------------------------------------------------------- driver
def compute(nets, log=None):
    """The layout (see the module docstring). Steps 3-5 are chaotic -- a small change in
    one place can tip a junction elsewhere into a different, worse drawing -- so they run
    once for each of VARIANTS (deterministic) and the drawing with the best quality()
    score is kept."""
    restore = _blas_one_thread()
    try:
        return _compute(nets, log)
    finally:
        restore()


def _compute(nets, log=None):
    lay = _union(nets)
    G = np.array([nd["geo"] for nd in lay.nodes])
    water = _load_water()
    extra = [r for _, _, _, rings in water for r in rings]
    A, *warped = _prewarp(G, [(e["a"], e["b"]) for e in lay.edges], [len(e["lines"]) for e in lay.edges], extra)
    args = [(copy.deepcopy(lay), G, A, warped, water, None, var) for var in VARIANTS]
    outs = _run_variants(args)
    best = None
    for i, (var, out) in enumerate(zip(VARIANTS, outs)):
        q = quality(out)
        if log:
            log(f"variant {i} {var}: {q}")
        if best is None or q["score"] < best[0] - 1e-9:
            best = (q["score"], out)
    return best[1]


def _place_args(a):
    lay, G, A, warped, water, log, var = a
    return _place(lay, G, A, warped, water, log, **var)


def _run_variants(args):
    """_place for each variant, in parallel processes where the platform allows (each is
    deterministic on its own, so the result doesn't depend on how they are run)."""
    n = min(len(args), os.cpu_count() or 1, MAX_PROCS)
    if n > 1:
        try:
            import concurrent.futures
            import multiprocessing
            ctx = multiprocessing.get_context("fork")
            with concurrent.futures.ProcessPoolExecutor(n, mp_context=ctx, initializer=_blas_one_thread) as ex:
                return list(ex.map(_place_args, args))
        except (ValueError, OSError, AssertionError, RuntimeError, ImportError,
                concurrent.futures.process.BrokenProcessPool):
            pass          # no fork (Windows), or already inside a worker process: one after another
    return [_place_args(a) for a in args]


def _place(lay, G, A, warped, water, log=None, w_anc=W_ANC, hop_km=AXIS_HOP_KM, unique=True, axis_dp=AXIS_DP, xfer=1.0):
    n = len(lay.nodes)
    lay.w_xfer = (W_XFER_S * xfer, W_XFER * xfer)
    lay.xfer_t = _xfer_pairs(lay, _radius(lay), A)
    inc, key, chains = _chains(lay)
    strokes, mate = _strokes(lay, inc, A)
    through = _through(lay, chains, mate)
    lay.turning = _turning(lay, chains)
    AS, axes = _smooth(lay, A, G, strokes, hop_km, unique)       # the anchors: pre-warped, then smoothed along strokes
    L = _targets(lay, AS, chains)
    rad = _radius(lay)
    wanc = np.array([w_anc * (1.5 if key[v] else 1.0) for v in range(n)])
    X = AS.copy()
    rep = []
    dirs = bent = None
    legs = {}

    close = []

    def step(wp, margin=1.1):
        nonlocal X, legs, rep, close
        X, legs = _solve(lay, X, AS, dirs, bent, L, wp, rep, wanc)
        # active set: separation terms only for pairs that are (nearly) too close now
        rep, bad, close = _violations(lay, X, dirs, bent, legs, rad, margin=margin)
        return bad
    # phase 1: directions re-assigned from the current geometry, moderate weight
    for it in range(N_ASSIGN):
        dirs, bent = _assign(lay, X, chains, key, L, through, axes, axis_dp)
        bad = step(min(1.5 * 1.35 ** it, 6.0))
        if log:
            log(f"assign {it}: {len(dirs)} straight, {len(bent)} bent, {bad} spacing violations")
    # phase 2: frozen directions; edges that still deviate or collapse get one bend
    for it in range(N_RELAX):
        conv = []
        for e, d in list(dirs.items()):
            if e in lay.firm:
                continue          # a firm axis stroke stays straight: the others give way
            ed = lay.edges[e]
            v = X[ed["b"]] - X[ed["a"]]
            ln = np.linalg.norm(v)
            dev = math.degrees(_angdiff(math.atan2(v[1], v[0]), d * math.pi / 4))
            if dev > DEV_BEND or v @ DIRS[d] < SHRINK * L[e]:
                (i, al), (j, be) = _decompose(v if ln > 1e-6 else DIRS[d])
                off = lambda x: min((x - d) % 8, (d - x) % 8)  # noqa: E731
                if dev <= DEV_BEND or i == j or max(off(i), off(j)) > 1:
                    # legs on either side of its direction (never doubling back on the line),
                    # on the side the edge has drifted to
                    side = 1 if (v @ DIRS[(d + 2) % 8]) >= 0 else -1
                    i, j, al, be = d, (d + side) % 8, 1.0, 0.0
                bent[e] = (i, j) if al >= be else (j, i)
                del dirs[e]
                conv.append(e)
        if it >= 4:      # stations still well under the minimum spacing: free one straight edge
            for pair in close:
                es = [e for v in pair for e in inc[v] if e in dirs and e not in lay.firm]
                if es:
                    e = max(es, key=lambda e: (L[e], -e))
                    d = dirs.pop(e)
                    bent[e] = (d, (d + 1) % 8)
                    conv.append(e)
        bad = step(min(6.0 * 1.6 ** it, 80.0))
        if log:
            log(f"relax {it}: {len(conv)} -> bent, {len(dirs)} straight, {len(bent)} bent, {bad} spacing violations")
        if it >= 4 and bad == 0 and not conv:
            break
    # phase 3: straighten, where the relaxed layout leaves room. Two kinds of kink are tried
    # away: a bent edge whose neighbour in its chain runs straight on in one of its two leg
    # directions is made straight that way, and a short stub at a terminus (up to two edges)
    # that turns 45° off its line is lined up with it. Edges the relaxation can't hold that
    # way, or that crowd a station, keep their kink; a round that crowds the map is undone.
    def deviates(e, d):
        ed = lay.edges[e]
        v = X[ed["b"]] - X[ed["a"]]
        dev = math.degrees(_angdiff(math.atan2(v[1], v[0]), d * math.pi / 4))
        return dev > DEV_BEND or v @ DIRS[d] < SHRINK * L[e]

    def nearest():      # each station's distance to its nearest neighbour once made exact
        Xe = _exact(lay, X, dirs)
        D = np.sqrt(((Xe[:, None, :] - Xe[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(D, np.inf)
        return D.min(1)

    def going(f, v):    # straight edge f's direction, leaving node v
        return dirs[f] if lay.edges[f]["a"] == v else (dirs[f] + 4) % 8

    def restore(e, was):
        dirs.pop(e, None)
        bent.pop(e, None)
        (dirs if was[0] == "d" else bent)[e] = was[1]

    def candidates():
        out, nk = {}, [0]
        for e, legs2 in sorted(bent.items()):
            ed = lay.edges[e]
            cont = collections.Counter()
            for v, w in ((ed["a"], ed["b"]), (ed["b"], ed["a"])):
                if key[v]:
                    continue
                for f in inc[v]:
                    if f != e and f in dirs:      # straight on through v, towards w
                        g = (going(f, v) + 4) % 8
                        cont[g if w == ed["b"] else (g + 4) % 8] += 1
            v = X[ed["b"]] - X[ed["a"]]
            cands = [d for d in legs2 if cont[d] and v @ DIRS[d] > 0]    # never against the edge
            if cands:
                d = max(cands, key=lambda d: (cont[d], -d))
                if not deviates(e, d) or len(cands) == 1:
                    out[e] = (("b", legs2), d)
        other = lambda f, v: lay.edges[f]["b"] if lay.edges[f]["a"] == v else lay.edges[f]["a"]  # noqa: E731
        for t in range(len(lay.nodes)):           # stubs at termini
            if len(inc[t]) != 1 or inc[t][0] not in dirs:
                continue
            stub = [inc[t][0]]
            d, u = going(stub[0], t), other(stub[0], t)   # the stub leaves the terminus going d
            if not key[u] and len(inc[u]) == 2:
                f = inc[u][0] if inc[u][1] == stub[0] else inc[u][1]
                if f in dirs and going(f, u) == d:
                    stub.append(f)
                    u = other(f, u)
            if key[u] or len(inc[u]) != 2:
                continue
            f = inc[u][0] if inc[u][1] == stub[-1] else inc[u][1]
            if f not in dirs:
                continue
            line, out_d = (going(f, u) + 4) % 8, (d + 4) % 8   # arriving at u; on into the stub
            if min((line - out_d) % 8, (out_d - line) % 8) != 1:
                continue
            node = u                              # the stub runs on in the line's direction
            for s in reversed(stub):
                out[s] = (("d", dirs[s]), line if lay.edges[s]["a"] == node else (line + 4) % 8)
                node = other(s, node)
        for nodes, es in chains:                  # jogs: a line running d, 45° off, d again
            seq = [going(e, v) if e in dirs else None for v, e in zip(nodes, es)]
            k = 1
            while k < len(es) - 1:
                if seq[k] is None or seq[k - 1] is None or min((seq[k] - seq[k - 1]) % 8, (seq[k - 1] - seq[k]) % 8) != 1:
                    k += 1
                    continue
                j = k
                while j < len(es) and seq[j] == seq[k] and j - k < ZZ_HOPS:
                    j += 1
                if j < len(es) and seq[j] == seq[k - 1]:
                    d = seq[k - 1]
                    for i in range(k, j):
                        out.setdefault(es[i], (("d", dirs[es[i]]), d if lay.edges[es[i]]["a"] == nodes[i] else (d + 4) % 8))
                k = j
        # along each line of the default plan, across junctions too: a V or a jog (a short run
        # turned 90 or 45 degrees off and back) is turned halfway back (straight back for 45),
        # and a sharp turn (135 degrees) is eased by turning the shorter run 45 degrees; only
        # where that lowers the turn cost (TURN_COST) of every line using those edges
        for run, nd in _kinks(lay, dirs, bent):
            es = [e for e, _ in run]
            if any(e in out for e in es):
                continue
            new = {e: (nd if lay.edges[e]["a"] == u else (nd + 4) % 8) for e, u in run}
            if any((X[lay.edges[e]["b"]] - X[lay.edges[e]["a"]]) @ DIRS[d] <= 0 for e, d in new.items()):
                continue          # never against the edge
            if _turn_cost(lay, dirs, bent, es, new) < _turn_cost(lay, dirs, bent, es, {}) - 1e-9:
                for e, d in new.items():
                    out[e] = (("d", dirs[e]), d)
                nk[0] += 1
        if log:
            log(f"kinks: {nk[0]} candidates")
        return out

    ea, eb = [ed["a"] for ed in lay.edges], [ed["b"] for ed in lay.edges]

    def trouble(X0):       # stations crowded, or at either end of an edge that turned round
        V0, V1 = X0[eb] - X0[ea], X[eb] - X[ea]
        n0 = np.linalg.norm(V0, axis=1)
        flip = np.nonzero((n0 > 0.2) & ((V0 * V1).sum(1) < -0.1 * n0 * n0))[0]
        # crowded: under the floor and closer than before the round (a spot already squeezed
        # would otherwise undo every round)
        near_now = nearest()
        crowd = np.nonzero((near_now < floor) & (near_now < near0 - 1e-3))[0]
        return np.union1d(crowd, np.array([[ea[f], eb[f]] for f in flip], int).reshape(-1))

    floor = min(STRAIGHT_SP, nearest().min())     # never more crowded than before (or STRAIGHT_SP)
    # all kinks are tried at once; those near trouble are put off and then tried a few
    # at a time (west to east); a few that still cause trouble are given up
    failed, later = set(), set()
    for it in range(N_STRAIGHTEN):
        allc = {e: c for e, c in candidates().items() if e not in failed}
        cand = {e: c for e, c in allc.items() if e not in later}
        few = not cand
        cand = cand or allc
        if not cand:
            break
        mid = lambda e: X[lay.edges[e]["a"], 0] + X[lay.edges[e]["b"], 0]  # noqa: E731
        order = sorted(cand, key=lambda e: (mid(e), e))
        near0 = nearest()       # spacing before the round
        tried = {}
        for e in order[:STRAIGHT_FEW] if few else order:
            tried[e] = cand[e][0]
            bent.pop(e, None)
            dirs[e] = cand[e][1]
        X0, legs0, rep0, close0 = X, legs, rep, close
        for _ in range(3):      # let the separation terms (active set) catch up
            step(80.0)
        back = {e for e in tried if deviates(e, dirs[e]) or any(e in inc[v] for pair in close for v in pair)}
        for e in back:
            restore(e, tried[e])
        if back:
            step(80.0)
        # the exact projection must not crowd stations either (it would shrink the whole map),
        # nor may an edge turn round (two stations swap places along a line): give the kinks
        # back near any such station, widening
        for reach in (1.5, 3.0, 6.0):
            crowd = trouble(X0)
            if not len(crowd):
                break
            near = {e for e in tried if e not in back and
                    min(np.linalg.norm(X[crowd] - X[lay.edges[e][s]], axis=1).min() for s in ("a", "b")) < reach}
            for e in near:
                restore(e, tried[e])
            back |= near
            for _ in range(2):
                step(80.0)
        # still in trouble: undo this round altogether
        crowd = trouble(X0)
        if len(crowd):
            # the kinks near the trouble are left alone from now on (they'd only cause it
            # again); the round is undone and the rest are tried again
            near = {e for e in tried if min(np.linalg.norm(X[crowd] - X[lay.edges[e][s]], axis=1).min() for s in ("a", "b")) < 6.0}
            if log:
                log(f"straighten {it}: undone ({len(tried)} of {len(cand)} tried; {len(crowd)} stations in trouble, "
                    f"{len(near)} kinks near them kept)")
            for e in tried:
                restore(e, tried[e])
            X, legs, rep, close = X0, legs0, rep0, close0
            if few:
                failed |= set(tried)
            else:
                later |= near or set(tried)
            continue
        failed |= back
        if log:
            log(f"straighten {it}: {len(tried) - len(back)} of {len(tried)} kinks removed ({len(cand)} candidates)")
    X = _exact(lay, X, dirs)
    # hard guarantee of the minimum spacing: a uniform scale keeps every angle
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(D, np.inf)
    if D.min() < MIN_SP:
        f = MIN_SP / D.min() * 1.0001
        c = X.mean(0)
        X = (X - c) * f + c
        A = (A - c) * f + c
        legs = {e: (a * f, b * f) for e, (a, b) in legs.items()}
        lay.scale = f
        if log:
            log(f"scaled by {f:.3f} to keep the minimum spacing")
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
    _unsharp(lay, X, log)
    _order_lines(lay, X, chains, key)
    _water(lay, A, X, water, warped)
    for name, v in _city_cores(lay):
        lay.labels.append((name, float(X[v, 0]), float(X[v, 1]), "city"))
    lay.X = X
    lay.chains = chains
    return lay


def _edge_shapes(v):
    """The octilinear ways to draw vector v: straight if it is octilinear, and every two-leg
    shape (d1 then d2, 45 or 90 degrees apart, both legs at least UNSHARP_LEG long), as
    [(directions, bend point offset or None)]."""
    out = []
    L = float(np.linalg.norm(v))
    if L < 1e-9:
        return out
    th = math.atan2(v[1], v[0]) / (math.pi / 4)
    if abs(th - round(th)) < 1e-3:
        out.append(((round(th) % 8,), None))
    for d1 in range(8):
        for step in (1, 2, -1, -2):
            d2 = (d1 + step) % 8
            M = np.array([DIRS[d1], DIRS[d2]]).T
            al, be = np.linalg.solve(M, v)
            if al > UNSHARP_LEG and be > UNSHARP_LEG:
                out.append(((d1, d2), DIRS[d1] * al))
    return out


def _unsharp(lay, X, log=None):
    """Last touch, stations fixed: a line that turns back on itself at a station (135 degrees
    or more) is eased by drawing one of the two edges there another octilinear way (straight,
    or two legs either way round), the way that costs the lines through that edge least in
    turns (TURN_COST, over every plan's routing) and passes no closer to other edges and
    stations than the old drawing or UNSHARP_GAP. So a short edge the relaxation left at an odd
    angle doesn't make the line double back."""
    def pieces(e, frm):
        ed = lay.edges[e]
        pts = [X[ed["a"]]] + ([np.array(ed["bend"])] if ed["bend"] is not None else []) + [X[ed["b"]]]
        if frm != ed["a"]:
            pts = pts[::-1]
        return [round(math.atan2(q[1] - p[1], q[0] - p[0]) / (math.pi / 4)) % 8 for p, q in zip(pts, pts[1:])]
    uses = collections.defaultdict(list)          # edge -> [(path, i)]: path[i] -> path[i + 1] runs on it
    for key, _, path in lay.seqs:
        for i, (u, w) in enumerate(zip(path, path[1:])):
            uses[lay.eidx[(min(u, w), max(u, w))]].append((path, i))

    def tc(d0, d1):
        t = (d1 - d0) % 8
        return TURN_COST[min(t, 8 - t)]

    def cost(e):
        c = 0.0
        for path, i in uses[e]:
            ds = pieces(e, path[i])
            c += sum(tc(a, b) for a, b in zip(ds, ds[1:]))
            if i > 0:
                c += tc(pieces(lay.eidx[(min(path[i - 1], path[i]), max(path[i - 1], path[i]))], path[i - 1])[-1], ds[0])
            if i + 2 < len(path):
                c += tc(ds[-1], pieces(lay.eidx[(min(path[i + 1], path[i + 2]), max(path[i + 1], path[i + 2]))], path[i + 1])[0])
        return c

    def clearance(e, pts):
        ed = lay.edges[e]
        ends = {ed["a"], ed["b"]}
        segs = list(zip(pts, pts[1:]))
        lo = np.min(pts, axis=0) - 2.0
        hi = np.max(pts, axis=0) + 2.0
        dmin, nx = 1e9, 0
        for f, fd in enumerate(lay.edges):
            if f == e or {fd["a"], fd["b"]} & ends:
                continue
            q = [X[fd["a"]]] + ([np.array(fd["bend"])] if fd["bend"] is not None else []) + [X[fd["b"]]]
            if (np.max(q, axis=0) < lo).any() or (np.min(q, axis=0) > hi).any():
                continue
            for p1, q1 in segs:
                for p2, q2 in zip(q, q[1:]):
                    if _intersect(p1, q1, p2, q2):
                        nx += 1
                    else:
                        dmin = min(dmin, _seg_seg(p1, q1, p2, q2)[0])
        for v in range(len(lay.nodes)):
            if v not in ends and (X[v] >= lo).all() and (X[v] <= hi).all():
                for p1, q1 in segs:
                    dmin = min(dmin, _seg_dist(X[v], p1, q1)[0])
        return nx, dmin
    fixed = 0
    for _ in range(3):
        sharp = set()
        for key, _, path in lay.seqs:
            for i in range(1, len(path) - 1):
                e1 = lay.eidx[(min(path[i - 1], path[i]), max(path[i - 1], path[i]))]
                e2 = lay.eidx[(min(path[i], path[i + 1]), max(path[i], path[i + 1]))]
                if e1 != e2 and tc(pieces(e1, path[i - 1])[-1], pieces(e2, path[i])[0]) >= TURN_COST[3]:
                    sharp |= {e1, e2}
        if not sharp:
            break
        changed = False
        for e in sorted(sharp):
            ed = lay.edges[e]
            a, b = ed["a"], ed["b"]
            old = ed["bend"]
            pts_old = [X[a]] + ([np.array(old)] if old is not None else []) + [X[b]]
            c_old, (x_old, g_old) = cost(e), clearance(e, pts_old)
            best = None
            for ds, off in _edge_shapes(X[b] - X[a]):
                ed["bend"] = None if off is None else tuple(X[a] + off)
                c = cost(e)
                if c < c_old - 1e-9 and (best is None or c < best[0] - 1e-9):
                    pts = [X[a]] + ([X[a] + off] if off is not None else []) + [X[b]]
                    nx, g = clearance(e, pts)
                    if nx <= x_old and g >= min(g_old, UNSHARP_GAP):
                        best = (c, ed["bend"])
            ed["bend"] = old if best is None else best[1]
            if best is not None:
                fixed += 1
                changed = True
        if not changed:
            break
    if log:
        log(f"unsharp: {fixed} edges redrawn")


def _city_cores(lay):
    """[(area name, node)]: each of CITIES is named beside its core station, the one with the
    most lines within CITY_KM of its centre (else the nearest station), so the name sits on
    its downtown and not wherever the warp carried the centre's point."""
    proj = geo.Projector()
    G = np.array([nd["geo"] for nd in lay.nodes])
    nl = collections.Counter()
    for ed in lay.edges:
        for v in (ed["a"], ed["b"]):
            nl[v] += len(ed["lines"])
    out = []
    for name, lat, lon in CITIES:
        c = np.array(proj.xy(lat, lon))
        d = np.linalg.norm(G - c, axis=1)
        near = np.nonzero(d < CITY_KM)[0]
        v = int(min(near, key=lambda v: (-nl[v], d[v]))) if len(near) else int(d.argmin())
        if d[v] < 5 * CITY_KM:     # an area this version doesn't serve gets no name
            out.append((name, v))
    return out


def drawn_dirs(lay, path):
    """A line's drawn course along a node path: [(direction 0..7, length)] per straight piece."""
    out = []
    for a, b in zip(path, path[1:]):
        e = lay.eidx[(min(a, b), max(a, b))]
        pts = edge_polyline(lay, e)
        if lay.edges[e]["a"] != a:
            pts = pts[::-1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            out.append((round(math.atan2(y1 - y0, x1 - x0) / (math.pi / 4)) % 8, math.hypot(x1 - x0, y1 - y0)))
    return out


def line_turns(lay, path):
    """Turns along a line: (bends, zig-zags, sharp turns). A zig-zag is a turn followed by one
    the other way within ZZ_LEN (a jog or a V that undoes itself); a sharp turn is 135
    degrees or more."""
    ds = drawn_dirs(lay, path)
    turns = []
    for k in range(1, len(ds)):
        t = (ds[k][0] - ds[k - 1][0]) % 8
        if t:
            turns.append((k, t if t <= 4 else t - 8))
    zz = sum(1 for (k1, t1), (k2, t2) in zip(turns, turns[1:])
             if t1 * t2 < 0 and sum(ds[k][1] for k in range(k1, k2)) <= ZZ_LEN)
    return len(turns), zz, sum(1 for _, t in turns if abs(t) >= 3)


def _crossings(segs):
    """Proper crossings among [(edge, p, q, its end nodes)] of edges that share no station."""
    P, Q = np.array([s[1] for s in segs]), np.array([s[2] for s in segs])
    lo, hi = np.minimum(P, Q), np.maximum(P, Q)
    ov = np.all((lo[:, None] <= hi[None]) & (lo[None] <= hi[:, None]), axis=2)
    out = set()
    for i, j in zip(*np.nonzero(np.triu(ov, 1))):
        if segs[i][0] != segs[j][0] and not segs[i][3] & segs[j][3] and _intersect(P[i], Q[i], P[j], Q[j]):
            out.add((min(segs[i][0], segs[j][0]), max(segs[i][0], segs[j][0])))
    return len(out)


def sharp_turns(lay, keys=None):
    """Where lines turn back on themselves at a station: [(scenario, line, station node, turn in
    degrees)] for every turn of 135 degrees or more between the piece a line arrives on and the
    piece it leaves on (the routings of `keys`, default: every scenario's)."""
    out = []
    for (key, lid), (path, _) in sorted(lay.paths.items()):
        if keys is not None and key not in keys:
            continue
        for i in range(1, len(path) - 1):
            ds = []
            for u, w in ((path[i - 1], path[i]), (path[i], path[i + 1])):
                pts = edge_polyline(lay, lay.eidx[(min(u, w), max(u, w))])
                if lay.edges[lay.eidx[(min(u, w), max(u, w))]]["a"] != u:
                    pts = pts[::-1]
                (x0, y0), (x1, y1) = (pts[-2], pts[-1]) if u == path[i - 1] else (pts[0], pts[1])
                ds.append(round(math.atan2(y1 - y0, x1 - x0) / (math.pi / 4)) % 8)
            t = (ds[1] - ds[0]) % 8
            if min(t, 8 - t) >= 3:
                out.append((key, lid, path[i], 45 * min(t, 8 - t)))
    return out


def quality(lay):
    """How clean the drawing is, over the lines of the default plan and of the plan: bends,
    zig-zags and sharp turns along the lines, edge crossings drawn against those in the real
    geography (straight station-to-station segments), edges drawn backwards (more than 90
    degrees off the real direction), walk-linked interchanges drawn apart (more than XFER_FAR
    times the distance they are pulled to), and score = bends + 2 zig-zags + 5 sharp turns +
    3 crossings beyond the geography's + 5 backwards + 20 x (uniform rescale - 1) + W_APART apart."""
    keys = {k for k in (lay.default, "plan") if k}
    bends = zz = sharp = 0
    for (key, _), (path, _) in sorted(lay.paths.items()):
        if key in keys:
            b, z, s = line_turns(lay, path)
            bends, zz, sharp = bends + b, zz + z, sharp + s
    drawn, geog = [], []
    for e, ed in enumerate(lay.edges):
        ends = {ed["a"], ed["b"]}
        pts = edge_polyline(lay, e)
        drawn += [(e, np.array(p), np.array(q), ends) for p, q in zip(pts, pts[1:])]
        geog.append((e, lay.nodes[ed["a"]]["geo"], lay.nodes[ed["b"]]["geo"], ends))
    xd, xg = _crossings(drawn), _crossings(geog)
    # stations out of order: an edge of the default plan drawn pointing away (by more than
    # 90 degrees) from where its far end really is
    back = sum(1 for e in lay.prime if (np.array([lay.nodes[lay.edges[e]["b"]][c] - lay.nodes[lay.edges[e]["a"]][c] for c in "xy"]) @
                                       (lay.nodes[lay.edges[e]["b"]]["geo"] - lay.nodes[lay.edges[e]["a"]]["geo"])) < 0)
    # interchanges pulled apart: walk-linked pairs (within the walk radius) drawn further apart
    # than XFER_FAR times the distance they are pulled to
    apart = 0
    for a, b, t, f in _xfer_pairs(lay, _radius(lay)):
        A, B = lay.nodes[a], lay.nodes[b]
        apart += _walk_pair(lay, a, b) and math.hypot(A["x"] - B["x"], A["y"] - B["y"]) > XFER_FAR * t * getattr(lay, "scale", 1.0)
    score = (bends + 2 * zz + 5 * sharp + 3 * max(0, xd - xg) + 5 * back + 20 * (getattr(lay, "scale", 1.0) - 1) +
             W_APART * apart)
    return {"bends": bends, "zigzags": zz, "sharp": sharp, "crossings": xd, "geo_crossings": xg, "backwards": back,
            "apart": apart, "score": round(float(score), 1)}


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
    paths = collections.defaultdict(dict)
    for (key, lid), (path, stop_at) in sorted(lay.paths.items()):
        paths[key][lid] = [path, stop_at]
    # every walk link the model uses that the layout keeps as two nodes: [a, b, 1 if it is long
    # on the diagram (not drawn but around the station selected), 1 if it is a longer walk than
    # the walk radius (a transfers.csv link)]
    conn = [[a, b, int(math.hypot(lay.nodes[a]["x"] - lay.nodes[b]["x"], lay.nodes[a]["y"] - lay.nodes[b]["y"]) > CONNECTOR_MAX),
             int(not _walk_pair(lay, a, b))] for a, b in lay.transfers]
    return {"nodes": nodes, "edges": edges, "paths": paths, "transfers": conn,
            "rivers": rivers, "lakes": lakes, "labels": labels, "pitch": PITCH, "lead": label_groups(lay)}


def diagram_nets(nets):
    """The networks the diagram lays out: every scenario minus BRT lines it adds on top
    of the plan (the 2M arterial grid lives on the map view only)."""
    plan_lines = set(nets["plan"].lines) if "plan" in nets else set()
    out = {}
    for k, n in nets.items():
        for lid in [l for l, ln in n.lines.items() if ln.mode == "brt" and l not in plan_lines and k != "plan"]:
            n = n.without(lid)
        out[k] = n
    return out


# The diagram's versions, each laid out on its own (a layout for the modes it shows, not the
# all-modes layout with strokes hidden: the bus lines are what force most bends):
# (key, label, modes; None = rail and the plan's BRT corridors, as diagram_nets).
VERSIONS = (("rail", "Rail", ("metro", "commuter", "streetcar")),
            ("brt", "BRT", ("brt",)),
            ("all", "Rail + BRT corridors", None))
DEFAULT_VERSION = "rail"


def version_nets(nets, modes):
    """The networks one diagram version lays out: only lines of `modes` (every BRT line,
    the 2M arterial grid too, when BRT is among them), or diagram_nets for None."""
    if modes is None:
        return diagram_nets(nets)
    out = {}
    for k, n in nets.items():
        for lid in [l for l, ln in n.lines.items() if ln.mode not in modes]:
            n = n.without(lid)
        out[k] = n
    return out


def _blas_one_thread():
    """Run numpy's OpenBLAS on one thread; returns a function that restores it. The layout's
    dense solves are small (~1,000-2,500 unknowns): extra BLAS threads gain little on an
    idle machine and cost up to 10x on a busy one (the build evaluates scenarios in parallel).
    A no-op where the library or its symbols can't be found."""
    try:
        import ctypes
        import glob
        base = os.path.dirname(np.__file__)
        for lib in sorted(glob.glob(base + ".libs/*openblas*") + glob.glob(os.path.join(base, ".dylibs", "*openblas*"))):
            dll = ctypes.CDLL(lib)
            for pre in ("scipy_openblas", "openblas"):
                for suf in ("64_", "_64_", ""):
                    get, put = (getattr(dll, f"{pre}_{f}_num_threads{suf}", None) for f in ("get", "set"))
                    if get and put:
                        old = get()
                        put(1)
                        return lambda: put(old)
    except Exception:          # noqa: BLE001 -- an optimization only
        pass
    return lambda: None


def _cache_key(nets):
    """A digest of everything a layout depends on: the code, the waterways and every
    scenario's stations, stop sequences, segment geometry and transfers."""
    h = hashlib.sha256()
    for path in (__file__, config.path("data", "waterways.geojson")):
        if os.path.exists(path):
            with open(path, "rb") as f:
                h.update(f.read())
    for key in sorted(nets):
        net = nets[key]
        h.update(repr((key, net.cfg.get("default_scenario"), net.cfg["transfer"]["walk_radius_m"])).encode())
        for ln in sorted(net.lines.values(), key=lambda l: l.id):
            h.update(repr((ln.id, ln.mode, ln.stop_ids, [s.pts for s in ln.segments],
                           [(until, old.stop_ids, [s.pts for s in old.segments], it.get("reroute"))
                            for _, until, old, it in net.variants.get(ln.id, [])])).encode())
            h.update(repr([(s, net.stations[s].name, net.stations[s].lat, net.stations[s].lon) for s in ln.stop_ids]).encode())
        h.update(repr(sorted((a, b) for a, b, *_ in net.transfers)).encode())
    return h.hexdigest()[:32]


def layout_json(nets, log=None, cache=True):
    """to_json(compute(nets)), reused from a cache in the temp folder when nothing it depends
    on changed (a layout takes ~15-60 s; quick builds and re-runs skip it)."""
    path = os.path.join(tempfile.gettempdir(), "dfwt-schematic", _cache_key(nets) + ".json") if cache else None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    out = to_json(compute(nets, log=log))
    if path:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(out, f, separators=(",", ":"))
            os.replace(path + ".tmp", path)
        except OSError:
            pass
    return out


def build(nets, log=None, cache=True):
    """Every diagram version's layout + page JSON, and the geographic waterways layer, for
    webmap: {"sets": {key: layout}, "versions": [[key, label, modes]], "default", "geoWater"}."""
    out = {"sets": {}, "versions": [], "default": DEFAULT_VERSION, "geoWater": waterways_geo()}
    for key, label, modes in VERSIONS:
        out["sets"][key] = layout_json(version_nets(nets, modes), log=log, cache=cache)
        out["versions"].append([key, label, list(modes) if modes else None])
    return out


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
            out["rivers"] += [[[round(lat, 4), round(lon, 4)] for lon, lat in line] for line in g]
        else:
            out["lakes"] += [[[round(lat, 4), round(lon, 4)] for lon, lat in poly[0]] for poly in g]
    return out
