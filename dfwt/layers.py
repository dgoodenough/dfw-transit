"""Map data layers: the model's numbers for each area, year by year, for the map's Data layers
toggle (docs/map.html): residents, jobs, jobs reachable by transit in 45 minutes, and the
share of residents' commutes where transit beats driving.

The areas are the 2020 block groups the model runs on (demand.Zones). Their boundaries aren't
in the repository, only their centroids, so each is drawn as its Voronoi cell (the land nearer
its centroid than any other), clipped to MAX_R_KM from the centroid; densities are per km2 of
that cell. Values are kept every STEP years (and the last year); the map interpolates between.

The layers are written as scripts beside the map (docs/layers/), one shared file of shapes and
one per plan, loaded when a layer is first switched on: a script tag loads from file:// too,
where fetch() doesn't, and the map page stays its size for readers who never open a layer."""
import json
import math
import os

import numpy as np

from . import geo

STEP = 5            # model years kept for the layers
MAX_R_KM = 8.0      # a cell reaches at most this far from its centroid (rural and edge areas)
NEIGHBOURS = 40     # nearest centroids tried when cutting a cell
CIRCLE = 32         # sides of the starting polygon
REACH_MIN = 45      # the jobs-reachable layer's threshold


def keep(cfg, year):
    """Whether a model year's per-area numbers are kept for the layers."""
    ys = cfg["years"]
    return (year - ys[0]) % STEP == 0 or year == max(ys)


def zone_values(z, od, res):
    """This year's per-area numbers (float32 arrays): residents, jobs, jobs reachable by transit
    within REACH_MIN clock minutes, and the share of commutes from the area where transit beats
    driving (the model's competitive commutes)."""
    reach = res["jobs_reach"]
    t = REACH_MIN if REACH_MIN in reach else max(reach)
    out = od.sum(axis=1)
    beats = np.divide(res["comp_from"], out, out=np.zeros_like(out, dtype=float), where=out > 0)
    return {"pop": z.pop.astype(np.float32), "jobs": z.jobs.astype(np.float32),
            "reach": reach[t].astype(np.float32), "beats": beats.astype(np.float32)}


def _clip(poly, nx, ny, c):
    """Keep the part of polygon `poly` (list of (x, y)) where nx*x + ny*y <= c."""
    out = []
    for k in range(len(poly)):
        p, q = poly[k - 1], poly[k]
        dp, dq = nx * p[0] + ny * p[1] - c, nx * q[0] + ny * q[1] - c
        if dq <= 0:
            if dp > 0:
                t = dp / (dp - dq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
            out.append(q)
        elif dp <= 0:
            t = dp / (dp - dq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def cells(x, y):
    """Voronoi cells of the points (km), each clipped to MAX_R_KM: (polygons as lists of (x, y),
    areas in km2). Points sharing a location share a cell, and each counts its full area."""
    n = len(x)
    ring = [(MAX_R_KM * math.cos(2 * math.pi * k / CIRCLE), MAX_R_KM * math.sin(2 * math.pi * k / CIRCLE)) for k in range(CIRCLE)]
    polys, areas = [], np.zeros(n)
    k = min(NEIGHBOURS, n - 1)
    for i0 in range(0, n, 512):
        i1 = min(n, i0 + 512)
        d2 = (x[i0:i1, None] - x[None, :]) ** 2 + (y[i0:i1, None] - y[None, :]) ** 2
        near = np.argsort(d2, axis=1)[:, :k + 1]
        for r, i in enumerate(range(i0, i1)):
            px, py = x[i], y[i]
            poly = [(px + a, py + b) for a, b in ring]
            for j in near[r]:
                dx, dy = x[j] - px, y[j] - py
                dd = dx * dx + dy * dy
                if dd < 1e-12:
                    continue
                if dd / 4 > max((u - px) ** 2 + (v - py) ** 2 for u, v in poly):
                    break   # neighbours are sorted: none further away can cut the cell
                # the half-plane nearer i than j: (p - mid) . (j - i) <= 0
                poly = _clip(poly, dx, dy, dx * (px + dx / 2) + dy * (py + dy / 2))
            polys.append(poly)
            areas[i] = 0.5 * abs(sum(poly[m - 1][0] * poly[m][1] - poly[m][0] * poly[m - 1][1] for m in range(len(poly))))
    return polys, areas


def _encode(poly, pj):
    """A polygon as integers: lat, lon x 1e4 for the first point, then differences."""
    pts = [(round((v / pj.ky + pj.lat0) * 1e4), round((u / pj.kx + pj.lon0) * 1e4)) for u, v in poly]
    out = [pts[0][0], pts[0][1]]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if (a, b) != (c, d):
            out += [c - a, d - b]
    return out


def _script(key, obj):
    body = json.dumps(obj, separators=(",", ":"))
    return f"(window.DFWT_LAYERS = window.DFWT_LAYERS || {{}})[{json.dumps(key)}] = {body};\n"


def write(zones, evals, out_dir):
    """Write docs/layers/zones.js (shapes) and one script per plan with kept years; returns what
    the map needs to find them: {"years": [...], "plans": [keys], "reachMin": REACH_MIN}."""
    os.makedirs(out_dir, exist_ok=True)
    pj = geo.Projector()
    polys, areas = cells(zones.x, zones.y)
    with open(os.path.join(out_dir, "zones.js"), "w", encoding="utf-8") as f:
        f.write(_script("_zones", {"area": [round(float(a), 3) for a in areas],
                                    "poly": [_encode(p, pj) for p in polys]}))
    plans, years = [], None
    for key, ev in evals.items():
        kept = sorted(y for y, r in ev["results"].items() if "zone" in r)
        if not kept:
            continue
        years = years or kept
        rs = [ev["results"][y]["zone"] for y in kept]
        # residents and jobs to the nearest 10 (as tens), jobs reached in hundreds, shares in %;
        # each year after the first as the change from the one before
        q = {"pop": lambda a: np.rint(a / 10), "jobs": lambda a: np.rint(a / 10),
             "reach": lambda a: np.rint(a / 100), "beats": lambda a: np.rint(a * 100)}
        obj = {"years": kept}
        for k, fq in q.items():
            m = np.array([fq(r[k]) for r in rs], dtype=np.int64)
            m[1:] = np.diff(m, axis=0)
            obj[k] = m.tolist()
        with open(os.path.join(out_dir, f"{key}.js"), "w", encoding="utf-8") as f:
            f.write(_script(key, obj))
        plans.append(key)
    for name in os.listdir(out_dir):   # a plan dropped from the build leaves no stale file
        if name.endswith(".js") and name != "zones.js" and name[:-3] not in plans:
            os.remove(os.path.join(out_dir, name))
    return {"years": years or [], "plans": plans, "reachMin": REACH_MIN}
