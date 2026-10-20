"""Shared-track pieces for the web map, so lines on the same track can be drawn side by side.

Lines that share a corridor rarely share exact coordinates: each was routed or fitted
on its own, so two lines on one track sit a few metres to a few tens of metres apart.
Every line is sampled every STEP m, in priority order (existing first, then metro,
commuter rail, BRT, by opening year), and each sample snaps to an earlier line's track
point when one lies within TOL m running the same way (either direction); otherwise
it starts new track. Track used by the same lines (and opening years) end to end is
merged into one piece, oriented the way its first line runs, with its lines in
priority order; the page offsets them side by side when zoomed in. Display only: the
model and the network tables are untouched.
"""
import collections
import math

from . import osmroute

STEP = 20.0      # sample spacing, m
TOL = 30.0       # a sample this close to earlier track, running parallel, is on it
CELL = TOL
PARALLEL = 0.9   # |cos| of the heading difference
SIMPLIFY = 3.0   # Douglas-Peucker tolerance for the drawn pieces, m
MODE_RANK = {"metro": 0, "commuter": 1, "brt": 2}


def _dp(P, tol):
    if len(P) < 3:
        return P
    keep = [False] * len(P)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        (ax, ay), (bx, by) = P[i], P[j]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        best, k = 0.0, None
        for m in range(i + 1, j):
            d = abs((P[m][0] - ax) * dy - (P[m][1] - ay) * dx) / L
            if d > best:
                best, k = d, m
        if k is not None and best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, f in zip(P, keep) if f]


def pieces(lines):
    """lines: [(line_index, mode, status, first_year, [(year, [(lon, lat), ...]), ...])].
    Returns [([(lon, lat), ...], [(line_index, year), ...]), ...]."""
    order = sorted(lines, key=lambda l: (l[2] != "existing", MODE_RANK.get(l[1], 3), l[3], l[0]))
    rank = {l[0]: k for k, l in enumerate(order)}
    xy, head, owner = [], [], []          # track points: position, heading, (line, index on that line)
    grid = collections.defaultdict(list)
    chain = {}                            # (line, index) -> track point
    use = collections.defaultdict(dict)   # (u, v) with u < v -> {line: year}
    walk = {}                             # (u, v) -> (line rank, line runs u->v)

    for li, _, _, _, segs in order:
        n_own = 0
        prev = None
        for year, pts in segs:
            P = []
            for q in (osmroute.xy(*p) for p in pts):   # repeated vertices give 0-length steps with no heading
                if not P or math.dist(P[-1], q) > 0.5:
                    P.append(q)
            S = []
            for a, b in zip(P, P[1:]):
                d = math.dist(a, b)
                k = max(1, int(d // STEP))
                h = math.atan2(b[1] - a[1], b[0] - a[0])
                S += [((a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k), h) for t in range(k)]
            if P:
                S.append((P[-1], S[-1][1] if S else 0.0))
            for p, h in S:
                cx, cy = int(p[0] // CELL), int(p[1] // CELL)
                best = None
                for gx in (cx - 1, cx, cx + 1):
                    for gy in (cy - 1, cy, cy + 1):
                        for t in grid[(gx, gy)]:
                            if owner[t][0] == li or abs(math.cos(head[t] - h)) < PARALLEL:
                                continue
                            d = math.dist(xy[t], p)
                            if d < TOL and (best is None or d < best[0]):
                                best = (d, t)
                if best:
                    node = best[1]
                else:
                    node = len(xy)
                    xy.append(p)
                    head.append(h)
                    owner.append((li, n_own))
                    chain[(li, n_own)] = node
                    n_own += 1
                    grid[(cx, cy)].append(node)
                if prev is not None and node != prev:
                    path = [prev, node]
                    (la, ia), (lb, ib) = owner[prev], owner[node]
                    if la == lb and la != li and 1 < abs(ib - ia) <= 12:   # skipped points on the track joined
                        step = 1 if ib > ia else -1
                        mid = [chain.get((la, i)) for i in range(ia + step, ib, step)]
                        if None not in mid:
                            path = [prev] + mid + [node]
                    for u, v in zip(path, path[1:]):
                        e = (min(u, v), max(u, v))
                        use[e][li] = min(use[e].get(li, year), year)
                        if e not in walk or rank[li] < walk[e][0]:
                            walk[e] = (rank[li], u < v)
                prev = node

    # merge runs of edges with the same users into pieces
    adj = collections.defaultdict(list)
    for (u, v) in use:
        adj[u].append(v)
        adj[v].append(u)
    sig = {e: tuple(sorted(us.items())) for e, us in use.items()}

    def key(u, v):
        return (min(u, v), max(u, v))

    def through(n, e):
        """The other edge at node n continuing piece edge e, or None at a junction or change."""
        if len(adj[n]) != 2:
            return None
        o = [m for m in adj[n] if key(n, m) != e]
        if len(o) != 1:
            return None
        f = key(n, o[0])
        return f if sig[f] == sig[e] else None

    seen, out = set(), []
    for e0 in use:
        if e0 in seen:
            continue
        seen.add(e0)
        u, v = e0
        nodes = [u, v]
        e = e0
        while True:   # extend forward from v
            f = through(nodes[-1], e)
            if f is None or f in seen:
                break
            seen.add(f)
            nodes.append(f[0] if f[1] == nodes[-1] else f[1])
            e = f
        e = e0
        while True:   # and backward from u
            f = through(nodes[0], e)
            if f is None or f in seen:
                break
            seen.add(f)
            nodes.insert(0, f[0] if f[1] == nodes[0] else f[1])
            e = f
        # orient along the piece's first line
        a, b = nodes[0], nodes[1]
        _, fwd = walk[key(a, b)]
        if fwd != (a < b):
            nodes.reverse()
        pts = _dp([xy[n] for n in nodes], SIMPLIFY)
        users = sorted(use[e0].items(), key=lambda t: rank[t[0]])
        out.append(([osmroute.ll(p) for p in pts], users))
    return out
