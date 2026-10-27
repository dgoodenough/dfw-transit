"""Activity centers from zone density (step 2a of the generator).

Method (DENCLUE-style density clustering, numpy only):

1. Activity = people + jobs per block group, deposited at its centroid on a grid of
   `grid_km` cells. Smoothed density = activity within `kernel_km` of each cell / disc
   area (people + jobs per km2), the same measure dfwt.demand.activity_density uses.
2. Every cell at or above `min_density` climbs to its densest neighbour until it reaches
   a local peak; the cells that reach the same peak form one cluster (its basin).
   Peaks closer than `merge_km` to a denser peak are merged into it.
3. A cluster is a center if its activity (people + jobs in its cells) is at least
   `min_activity`. Its point is the activity-weighted centroid of the zones within
   `kernel_km` of the peak.
4. Tiers, by jobs (people + jobs if the metro has no jobs data, flagged):
   downtown  jobs within `downtown_radius_km` >= `downtown_jobs` and peak job density
             >= `downtown_job_density` (the region's top one always qualifies)
   major     activity >= `major_activity`
   minor     the rest
   Town centers for regional rail are found the same way with the lower `town_*`
   thresholds (smaller places at the edge of the region).
"""
import math

import numpy as np


class Center:
    def __init__(self, cid, x, y, lat, lon, activity, pop, jobs, peak_density, peak_jobs_density, kind, cells):
        self.id, self.x, self.y, self.lat, self.lon = cid, x, y, lat, lon
        self.activity, self.pop, self.jobs = activity, pop, jobs
        self.peak_density, self.peak_jobs_density = peak_density, peak_jobs_density
        self.kind, self.cells = kind, cells
        self.name = cid
        self.near_jobs = jobs

    def as_row(self):
        return {"center_id": self.id, "name": self.name, "kind": self.kind, "lat": round(self.lat, 6),
                "lon": round(self.lon, 6), "activity": round(self.activity), "pop": round(self.pop),
                "jobs": round(self.jobs), "peak_density_per_km2": round(self.peak_density),
                "peak_job_density_per_km2": round(self.peak_jobs_density)}


class Surface:
    """Gridded activity and its kernel-smoothed density."""

    def __init__(self, m, grid_km=0.5, kernel_km=1.0):
        self.g, self.r = grid_km, kernel_km
        pad = kernel_km + 2 * grid_km
        self.x0, self.y0 = float(m.x.min()) - pad, float(m.y.min()) - pad
        self.nx = int((m.x.max() + pad - self.x0) / grid_km) + 1
        self.ny = int((m.y.max() + pad - self.y0) / grid_km) + 1
        self.ix = ((m.x - self.x0) / grid_km).astype(int)
        self.iy = ((m.y - self.y0) / grid_km).astype(int)
        self.act = self._deposit(m.activity)
        self.jobs = self._deposit(m.jobs)
        self.dens = self.smooth(self.act)
        self.jdens = self.smooth(self.jobs)

    def _deposit(self, v):
        a = np.zeros((self.nx, self.ny))
        np.add.at(a, (self.ix, self.iy), v)
        return a

    def smooth(self, a, r=None):
        r = r or self.r
        k = int(math.ceil(r / self.g))
        out = np.zeros_like(a)
        n = 0
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                if (dx * self.g) ** 2 + (dy * self.g) ** 2 <= r * r + 1e-9:
                    out += np.roll(np.roll(a, dx, 0), dy, 1)
                    n += 1
        return out / (n * self.g * self.g)   # per km2 of the discrete disc

    def cell_xy(self, i, j):
        return self.x0 + (i + 0.5) * self.g, self.y0 + (j + 0.5) * self.g

    def density_at(self, x, y, jobs=False):
        i = np.clip(((np.asarray(x) - self.x0) / self.g).astype(int), 0, self.nx - 1)
        j = np.clip(((np.asarray(y) - self.y0) / self.g).astype(int), 0, self.ny - 1)
        return (self.jdens if jobs else self.dens)[i, j]


def climb(dens, mask):
    """For every cell in mask: index of the peak reached by steepest ascent (-1 outside)."""
    nx, ny = dens.shape
    idx = np.arange(nx * ny).reshape(nx, ny)
    best_v, best_i = dens.copy(), idx.copy()
    padv = np.pad(dens, 1, constant_values=-1)
    padi = np.pad(idx, 1, constant_values=-1)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0:
                continue
            v = padv[1 + dx:1 + dx + nx, 1 + dy:1 + dy + ny]
            i = padi[1 + dx:1 + dx + nx, 1 + dy:1 + dy + ny]
            better = v > best_v
            best_v = np.where(better, v, best_v)
            best_i = np.where(better, i, best_i)
    ptr = best_i.ravel()
    for _ in range(64):
        nxt = ptr[ptr]
        if np.array_equal(nxt, ptr):
            break
        ptr = nxt
    out = np.where(mask.ravel(), ptr, -1)
    return out.reshape(nx, ny)


def find(m, surf, p, kind_prefix="C", min_density=None, min_activity=None, merge_km=None):
    """Clusters on `surf` with the thresholds in p (the generator's "centers" block)."""
    min_density = p["min_density"] if min_density is None else min_density
    min_activity = p["min_activity"] if min_activity is None else min_activity
    merge_km = p["merge_km"] if merge_km is None else merge_km
    mask = surf.dens >= min_density
    peak_of = climb(surf.dens, mask)
    peaks = np.unique(peak_of[peak_of >= 0])
    nxny = surf.ny
    pk = sorted(peaks, key=lambda q: -surf.dens.ravel()[q])
    head = {}
    kept = []
    for q in pk:
        i, j = divmod(int(q), nxny)
        x, y = surf.cell_xy(i, j)
        tgt = None
        for h in kept:
            hi, hj = divmod(int(h), nxny)
            hx, hy = surf.cell_xy(hi, hj)
            if math.hypot(hx - x, hy - y) < merge_km:
                tgt = h
                break
        if tgt is None:
            kept.append(q)
            head[q] = q
        else:
            head[q] = tgt
    lab = np.full(peak_of.shape, -1)
    for q in peaks:
        lab[peak_of == q] = head[q]
    zone_lab = lab[surf.ix, surf.iy]
    out = []
    for h in kept:
        zs = zone_lab == h
        act = float(m.activity[zs].sum())
        if act < min_activity:
            continue
        i, j = divmod(int(h), nxny)
        px, py = surf.cell_xy(i, j)
        near = (m.x - px) ** 2 + (m.y - py) ** 2 <= surf.r ** 2
        w = m.activity[near]
        if w.sum() > 0:
            cx, cy = float(np.average(m.x[near], weights=w)), float(np.average(m.y[near], weights=w))
        else:
            cx, cy = px, py
        lat, lon = m.ll(cx, cy)
        out.append(Center("", cx, cy, float(lat), float(lon), act, float(m.pop[zs].sum()), float(m.jobs[zs].sum()),
                          float(surf.dens[i, j]), float(surf.jdens[i, j]), "minor", int((lab == h).sum())))
    out.sort(key=lambda c: -c.activity)
    for k, c in enumerate(out):
        c.id = f"{kind_prefix}{k + 1:02d}"
    return out


def classify(m, centers, p):
    """Set each center's kind: downtown / major / minor (see module doc)."""
    if not centers:
        return
    r2 = p["downtown_radius_km"] ** 2
    metric = m.jobs if m.jobs_ok else m.activity
    for c in centers:
        near = (m.x - c.x) ** 2 + (m.y - c.y) ** 2 <= r2
        c.near_jobs = float(metric[near].sum())
    top = max(centers, key=lambda c: c.near_jobs)
    sep = p["downtown_sep_km"]
    for c in centers:
        dens = c.peak_jobs_density if m.jobs_ok else c.peak_density
        lim_j = p["downtown_jobs"] if m.jobs_ok else p["downtown_jobs"] * p["pop_only_factor"]
        lim_d = p["downtown_job_density"] if m.jobs_ok else p["downtown_job_density"] * p["pop_only_factor"]
        # the biggest job center within downtown_sep_km: a second downtown is a separate city
        # (Fort Worth beside Dallas), not a big office park on the first one's freeways
        biggest = all(o.near_jobs <= c.near_jobs for o in centers if math.hypot(o.x - c.x, o.y - c.y) <= sep)
        if c is top or (c.near_jobs >= lim_j and dens >= lim_d and biggest):
            c.kind = "downtown"
        elif c.activity >= p["major_activity"]:
            c.kind = "major"
        else:
            c.kind = "minor"


def towns(m, surf, p, centers):
    """Smaller town centers (regional rail ends): clusters at the lower town thresholds that
    are at least `town_min_sep_km` from every urban center."""
    out = []
    for t in find(m, surf, p, "T", p["town_min_density"], p["town_min_activity"], p["merge_km"]):
        if all(math.hypot(t.x - c.x, t.y - c.y) >= p["town_min_sep_km"] for c in centers + out):
            t.kind = "town"
            out.append(t)
    for k, t in enumerate(out):
        t.id = f"T{k + 1:02d}"
    return out
