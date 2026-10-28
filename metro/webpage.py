"""A map page of the generated networks (docs/generated.html): each generated/<id>/ scenario on
one Leaflet map, with a picker, today's lines in grey and the report's summary.

    python -m metro webpage            # every generated/<id>/ with lines.csv
    python -m metro webpage houston dfw

Geometry is simplified for the web; the tables in generated/<id>/ stay the source."""
import csv
import json
import os
import re

from dfwt import config, geo

OUT = config.path("docs", "generated.html")
SIMPLIFY_DEG = 0.0002   # about 20 m
MODE_ORDER = {"commuter": 0, "metro": 1, "streetcar": 2, "brt": 3, "bus": 4}


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _simplify(pts, tol):
    """Ramer-Douglas-Peucker on (lon, lat) points (iterative)."""
    if len(pts) < 3:
        return pts
    keep, stack = {0, len(pts) - 1}, [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x0, y0), (x1, y1) = pts[a], pts[b]
        dx, dy = x1 - x0, y1 - y0
        n = (dx * dx + dy * dy) ** 0.5
        best, k = -1.0, None
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dx * (y - y0) - dy * (x - x0)) / n if n else ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
            if d > best:
                best, k = d, i
        if k is not None and best > tol:
            keep.add(k)
            stack += [(a, k), (k, b)]
    return [pts[i] for i in sorted(keep)]


def _lines(folder, only_status=None, skip_modes=()):
    """[{id, name, mode, status, color, headway, km, segs: [[[lat, lon], ...], ...], stops: [station ids]}]"""
    stops = {}
    for r in _rows(os.path.join(folder, "line_stops.csv")):
        stops.setdefault(r["line_id"], []).append((int(r["seq"]), r["station_id"]))
    segs = {}
    for r in _rows(os.path.join(folder, "line_segments.csv")):
        pts = geo.parse_wkt(r["geometry_wkt"])
        segs.setdefault(r["line_id"], []).append((int(r["seq"]), pts))
    out = []
    for r in _rows(os.path.join(folder, "lines.csv")):
        if only_status and r["status"] != only_status:
            continue
        if r["mode"] in skip_modes:
            continue
        lid = r["line_id"]
        parts = [p for _, p in sorted(segs.get(lid, []))]
        km = sum(geo.polyline_km(p) for p in parts)
        out.append({
            "id": lid, "name": r["name"], "mode": r["mode"], "status": r["status"],
            "color": r.get("color") or "#666666", "headway": r.get("headway_min") or "",
            "km": round(km, 1),
            "segs": [[[round(y, 5), round(x, 5)] for x, y in _simplify(p, SIMPLIFY_DEG)] for p in parts],
            "stops": [s for _, s in sorted(stops.get(lid, []))],
        })
    out.sort(key=lambda l: (l["status"] != "existing", MODE_ORDER.get(l["mode"], 9), l["name"]))
    return out


def _summary(folder):
    """The report's title, data warnings and Summary bullets, as plain text lines."""
    p = os.path.join(folder, "report.md")
    if not os.path.exists(p):
        return {"title": os.path.basename(folder), "warn": "", "bullets": []}
    text = open(p, encoding="utf-8").read()
    title = re.search(r"^# (.+)$", text, re.M)
    warn = re.search(r"^\*\*Data warnings:\*\*(.+)$", text, re.M)
    block = re.search(r"^## Summary\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    bullets = []
    if block:
        for ln in block.group(1).splitlines():
            if ln.startswith("- "):
                bullets.append(re.sub(r"`|\*\*", "", ln[2:]).strip())
    clean = lambda s: re.sub(r"`|\*\*", "", s).strip()
    return {"title": clean(title.group(1)) if title else os.path.basename(folder),
            "warn": clean(warn.group(1)) if warn else "", "bullets": bullets}


def networks(ids=None):
    root = config.path("generated")
    ids = ids or sorted((d for d in os.listdir(root) if os.path.exists(os.path.join(root, d, "lines.csv"))),
                        key=lambda d: (d.startswith("dfw"), d))   # the DFW cross-check last
    out = []
    for nid in ids:
        folder = os.path.join(root, nid)
        lines = _lines(folder)
        stations = {r["station_id"]: [r["name"], round(float(r["lat"]), 5), round(float(r["lon"]), 5)]
                    for r in _rows(os.path.join(folder, "stations.csv"))}
        used = {s for l in lines for s in l["stops"]}
        metro_id = nid.split("_")[0]
        # today's buses (not a model mode, so not in the generated tables): drawn faintly for context
        buses = _lines(config.path("data", "metros", metro_id, "existing"), only_status="existing",
                       skip_modes=("metro", "brt", "commuter", "streetcar"))
        for b in buses:
            b["stops"] = []
        out.append({"id": nid, **_summary(folder), "lines": lines, "buses": buses,
                    "stations": {k: v for k, v in stations.items() if k in used}})
    return out


def write(ids=None, out_path=OUT):
    data = networks(ids)
    with open(os.path.join(os.path.dirname(__file__), "webpage.html"), encoding="utf-8") as f:
        html = f.read()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html.replace("/*__DATA__*/null", blob))
    return out_path, data
