"""Polyline and catchment helpers in the metro's local km projection."""
import collections
import math

import numpy as np


class ZoneIndex:
    """Grid index of zone centroids for radius queries."""

    def __init__(self, m, cell_km=1.0):
        self.m, self.c = m, cell_km
        self.grid = collections.defaultdict(list)
        for i, (x, y) in enumerate(zip(m.x, m.y)):
            self.grid[(int(x // cell_km), int(y // cell_km))].append(i)
        self.grid = {k: np.array(v) for k, v in self.grid.items()}

    def near(self, x, y, r_km):
        """Zone indices within r_km of (x, y)."""
        k = int(math.ceil(r_km / self.c))
        cx, cy = int(x // self.c), int(y // self.c)
        parts = [self.grid[(i, j)] for i in range(cx - k, cx + k + 1) for j in range(cy - k, cy + k + 1)
                 if (i, j) in self.grid]
        if not parts:
            return np.zeros(0, dtype=int)
        idx = np.concatenate(parts)
        d2 = (self.m.x[idx] - x) ** 2 + (self.m.y[idx] - y) ** 2
        return idx[d2 <= r_km * r_km]

    def near_points(self, P, r_km):
        """Zone indices within r_km of any of the points P [(x, y)]."""
        out = set()
        for x, y in P:
            out.update(self.near(x, y, r_km).tolist())
        return np.array(sorted(out), dtype=int)


def to_xy(m, pts):
    """[(lat, lon)] -> [(x, y)] km."""
    if not pts:
        return []
    lat = np.array([p[0] for p in pts])
    lon = np.array([p[1] for p in pts])
    x, y = m.xy(lat, lon)
    return list(zip(x.tolist(), y.tolist()))


def to_ll(m, P):
    if not P:
        return []
    x = np.array([p[0] for p in P])
    y = np.array([p[1] for p in P])
    lat, lon = m.ll(x, y)
    return list(zip(lat.tolist(), lon.tolist()))


def length(P):
    return sum(math.dist(a, b) for a, b in zip(P, P[1:]))


def cumlen(P):
    out = [0.0]
    for a, b in zip(P, P[1:]):
        out.append(out[-1] + math.dist(a, b))
    return out


def point_at(P, cum, s):
    s = max(0.0, min(s, cum[-1]))
    k = int(np.searchsorted(cum, s, side="right")) - 1
    k = max(0, min(k, len(P) - 2))
    L = cum[k + 1] - cum[k]
    f = (s - cum[k]) / L if L else 0.0
    return (P[k][0] + f * (P[k + 1][0] - P[k][0]), P[k][1] + f * (P[k + 1][1] - P[k][1]))


def resample(P, step_km):
    """Points every step_km along P (both ends included)."""
    cum = cumlen(P)
    n = max(1, int(math.ceil(cum[-1] / step_km)))
    return [point_at(P, cum, cum[-1] * i / n) for i in range(n + 1)]


def project(P, cum, q):
    """(distance along P, distance from P) of point q."""
    best = (1e18, 0.0)
    for k, (a, b) in enumerate(zip(P, P[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        d = math.hypot(a[0] + t * vx - q[0], a[1] + t * vy - q[1])
        if d < best[0]:
            best = (d, cum[k] + t * math.sqrt(L2))
    return best[1], best[0]


def cut(P, cum, s0, s1):
    """The part of P between distances s0 < s1 along it."""
    out = [point_at(P, cum, s0)]
    for k in range(len(P)):
        if s0 < cum[k] < s1:
            out.append(P[k])
    out.append(point_at(P, cum, s1))
    return out


def share_near(P, Q_list, r_km, step_km=0.2):
    """Share of P's length within r_km of any polyline in Q_list (a duplicate test)."""
    if not Q_list:
        return 0.0
    S = resample(P, step_km)
    grid = collections.defaultdict(list)
    for Q in Q_list:
        for q in resample(Q, step_km):
            grid[(int(q[0] // r_km), int(q[1] // r_km))].append(q)
    hit = 0
    for p in S:
        cx, cy = int(p[0] // r_km), int(p[1] // r_km)
        if any(math.dist(p, q) <= r_km for i in (cx - 1, cx, cx + 1) for j in (cy - 1, cy, cy + 1)
               for q in grid.get((i, j), ())):
            hit += 1
    return hit / len(S)


def turn_deg(a, b, c):
    h1 = math.atan2(b[1] - a[1], b[0] - a[0])
    h2 = math.atan2(c[1] - b[1], c[0] - b[0])
    return abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi))
