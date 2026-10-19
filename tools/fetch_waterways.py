"""Fetch the DFW major waterways from Overture Maps and write data/waterways.geojson.

One-off data tool (not part of the build). Needs pyarrow, which the model itself
does not: `pip install pyarrow`, then

    python tools/fetch_waterways.py [--release 2026-09-23.1] [--raw /tmp/water.pkl]

Overture's base/water theme is OpenStreetMap water (© OpenStreetMap contributors,
ODbL). We read it anonymously from S3 with a bounding-box filter (row-group
statistics keep the download to a few MB), keep only the named features listed
below (the Trinity forks and main stem, and the major reservoirs), merge each
into one geometry, simplify hard with Douglas–Peucker, and round coordinates.
The output is small enough to commit.
"""
import argparse
import json
import math
import os
import pickle
import struct
import sys

BBOX = (-97.95, 32.25, -96.15, 33.75)          # lon/lat: the whole station extent plus margin
RIVERS = {                                     # name -> output id; all are OSM waterway=river lines
    "West Fork Trinity River": "West Fork Trinity River",
    "Clear Fork Trinity River": "Clear Fork Trinity River",
    "Elm Fork Trinity River": "Elm Fork Trinity River",
    "Trinity River": "Trinity River",
    "East Fork Trinity River": "East Fork Trinity River",
}
LAKES = ["Lake Worth", "Eagle Mountain Lake", "Benbrook Lake", "Lake Arlington", "Grapevine Lake",
         "Lewisville Lake", "White Rock Lake", "Lake Ray Hubbard", "Joe Pool Lake", "Mountain Creek Lake",
         "Lavon Lake", "Ray Roberts Lake", "North Lake", "Bachman Lake"]
RIVER_TOL_KM, LAKE_TOL_KM = 0.12, 0.10        # Douglas–Peucker tolerances
MIN_LAKE_KM2 = 0.5


# ---------------- WKB (2D) ----------------
def _wkb(buf, off=0):
    bo = "<" if buf[off] == 1 else ">"
    (t,) = struct.unpack_from(bo + "I", buf, off + 1)
    t &= 0xFFFF
    off += 5
    base = t % 1000
    dims = 3 if t >= 1000 else 2

    def pts(o):
        (n,) = struct.unpack_from(bo + "I", buf, o)
        o += 4
        vals = struct.unpack_from(bo + "%dd" % (n * dims), buf, o)
        return [(vals[i], vals[i + 1]) for i in range(0, n * dims, dims)], o + 8 * n * dims

    if base == 2:
        p, off = pts(off)
        return ("line", [p]), off
    if base == 3:
        (nr,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        rings = []
        for _ in range(nr):
            p, off = pts(off)
            rings.append(p)
        return ("poly", [rings]), off
    if base in (5, 6, 7):
        (n,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        lines, polys = [], []
        for _ in range(n):
            (kind, parts), off = _wkb(buf, off)
            (lines if kind == "line" else polys).extend(parts)
        return ("line", lines) if lines and not polys else ("poly", polys), off
    return ("other", []), off


# ---------------- geometry helpers ----------------
KX = math.radians(1) * 6371.0 * math.cos(math.radians(32.8))
KY = math.radians(1) * 6371.0


def _dp(pts, tol_km):
    """Douglas–Peucker on lon/lat points with a km tolerance."""
    if len(pts) < 3:
        return pts
    xy = [(x * KX, y * KY) for x, y in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = xy[i]
            if L2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > best:
                best, bi = d, i
        if best > tol_km:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def _area_km2(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += (x1 * KX) * (y2 * KY) - (x2 * KX) * (y1 * KY)
    return abs(s) / 2


def _chain(lines):
    """Join line pieces that share endpoints into as few polylines as possible."""
    pieces = [list(p) for p in lines if len(p) > 1]
    key = lambda p: (round(p[0], 5), round(p[1], 5))  # noqa: E731
    changed = True
    while changed:
        changed = False
        for i in range(len(pieces)):
            for j in range(len(pieces)):
                if i == j or not pieces[i] or not pieces[j]:
                    continue
                a, b = pieces[i], pieces[j]
                if key(a[-1]) == key(b[0]):
                    pieces[i] = a + b[1:]
                elif key(a[-1]) == key(b[-1]):
                    pieces[i] = a + b[::-1][1:]
                elif key(a[0]) == key(b[-1]):
                    pieces[i] = b + a[1:]
                elif key(a[0]) == key(b[0]):
                    pieces[i] = b[::-1] + a[1:]
                else:
                    continue
                pieces[j] = []
                changed = True
        pieces = [p for p in pieces if p]
    return pieces


def _clip(pts):
    """Drop vertices outside the bbox (river ways can run far beyond it)."""
    x0, y0, x1, y1 = BBOX
    return [p for p in pts if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]


def fetch(release):
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2", proxy_options=os.environ.get("HTTPS_PROXY") or None)
    path = f"overturemaps-us-west-2/release/{release}/theme=base/type=water/"
    d = ds.dataset(path, filesystem=s3, format="parquet")
    x0, y0, x1, y1 = BBOX
    f = ((ds.field("bbox", "xmax") >= x0) & (ds.field("bbox", "xmin") <= x1) &
         (ds.field("bbox", "ymax") >= y0) & (ds.field("bbox", "ymin") <= y1))
    t = d.to_table(columns=["id", "names", "subtype", "class", "geometry"], filter=f)
    rows = []
    for r in t.to_pylist():
        nm = (r.get("names") or {}).get("primary")
        if not nm:
            continue
        rows.append((nm, r["subtype"], r["class"], r["geometry"]))
    return rows


def build(rows):
    rivers, lakes = {}, {}
    for nm, sub, cls, wkb in rows:
        (kind, parts), _ = _wkb(wkb)
        if kind == "line" and nm in RIVERS and sub == "river":
            rivers.setdefault(RIVERS[nm], []).extend(_clip(p) for p in parts)
        elif kind == "poly" and nm in LAKES:
            lakes.setdefault(nm, []).extend(parts)
    feats = []
    for nm, parts in sorted(rivers.items()):
        lines = [_dp(p, RIVER_TOL_KM) for p in _chain(parts)]
        lines = [[[round(x, 4), round(y, 4)] for x, y in p] for p in lines if len(p) > 1]
        feats.append({"type": "Feature", "properties": {"name": nm, "kind": "river"},
                      "geometry": {"type": "MultiLineString", "coordinates": lines}})
    for nm, polys in sorted(lakes.items()):
        out = []
        for rings in polys:
            outer = rings[0]
            if _area_km2(outer) < MIN_LAKE_KM2:
                continue
            s = _dp(outer, LAKE_TOL_KM)
            if len(s) >= 4:
                out.append([[[round(x, 4), round(y, 4)] for x, y in s]])
        if out:
            area = sum(_area_km2([tuple(p) for p in poly[0]]) for poly in out)
            feats.append({"type": "Feature", "properties": {"name": nm, "kind": "lake", "area_km2": round(area, 1)},
                          "geometry": {"type": "MultiPolygon", "coordinates": out}})
    return {"type": "FeatureCollection",
            "attribution": "Overture Maps base/water (OpenStreetMap data, © OpenStreetMap contributors, ODbL)",
            "features": feats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default="2026-09-23.1")
    ap.add_argument("--raw", help="cache the raw bbox query here (pickle) and reuse it")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "waterways.geojson"))
    a = ap.parse_args()
    if a.raw and os.path.exists(a.raw):
        with open(a.raw, "rb") as f:
            rows = pickle.load(f)
    else:
        rows = fetch(a.release)
        if a.raw:
            with open(a.raw, "wb") as f:
                pickle.dump(rows, f)
    print(f"{len(rows)} named water features in the bbox", file=sys.stderr)
    gj = build(rows)
    gj["source"] = f"Overture Maps release {a.release}, theme=base/type=water, bbox {BBOX}"
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(gj, f, separators=(",", ":"))
    for ft in gj["features"]:
        print(ft["properties"]["kind"], ft["properties"]["name"], file=sys.stderr)
    print(f"wrote {a.out} ({os.path.getsize(a.out) / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
