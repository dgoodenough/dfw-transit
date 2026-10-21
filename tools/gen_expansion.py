"""Build a network-expansion scenario from a corridor spec.

    python tools/gen_expansion.py lever_expand_jobs        # reads scenarios/<name>/corridors.json

The spec lists new lines as waypoints; this script writes the scenario's full
lines / stations / line_stops / line_segments / stages / transfers tables (the
base plan's rows plus the new ones), so the scenario is an ordinary folder that
`python -m dfwt validate --scenario <name>` and `ridership` read.

Spec (JSON):

    {"include": ["other_scenario"],            # merge another spec's lines first (optional)
     "stage_overrides": [{"line_id": "E35", "stage": "1", "year_opens": 2080}],   # base stages (optional)
     "lines": [
       {"id": "XP01", "name": "SH-114 Line", "mode": "metro", "color": "#e65100",
        "grade": "elevated",                   # default grade; a stop's "grade" applies from it onward
        "spacing_km": 1.3,                     # intermediate stops are added on longer gaps
        "follow_roads": true,                  # metro: run in freeway/arterial corridors (default: straight)
        "notes": "...",
        "stops": ["X129",                      # an existing station id ...
                  {"name": "Valwood", "lat": 32.921, "lon": -96.919},     # ... or a new stop
                  {"via": true, "lat": 32.91, "lon": -96.95},             # shape point, no stop
                  ...],
        "stages": [["X129", "Valwood", 2075], ["Valwood", "X318", 2080]]}]}

Geometry is straight station-to-station (through any via points), which is
enough for a proposal's length and cost. New stops within `snap_m` of an
existing station reuse it. Proposed metro inside a downtown core
(config "cores") is costed as tunnel.
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config, geo  # noqa: E402

TABLES = {
    "lines.csv": ["line_id", "name", "mode", "status", "color", "headway_min", "notes"],
    "stations.csv": ["station_id", "name", "lat", "lon"],
    "line_stops.csv": ["line_id", "seq", "station_id", "year_opens"],
    "line_segments.csv": ["line_id", "seq", "year_opens", "grade", "geometry_source", "locked", "geometry_wkt"],
    "stages.csv": ["line_id", "stage", "kind", "from_stop", "to_stop", "year_opens", "until_year", "via_line",
                   "headway_min", "locked", "note"],
    "transfers.csv": ["station_a", "station_b", "walk_min", "note"],
}
SNAP_M = 250
TRANSFER_M = 650   # explicit walk links up to this distance (the model links <= 400 m by itself)


def read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(folder, name, rows):
    with open(os.path.join(folder, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TABLES[name], lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_spec(name, seen=None):
    """(lines, stage_overrides, infill) of a spec and the specs it includes."""
    seen = seen if seen is not None else set()
    if name in seen:
        return [], [], []
    seen.add(name)
    with open(config.path("scenarios", name, "corridors.json"), encoding="utf-8") as f:
        spec = json.load(f)
    lines, overrides, infill = [], [], []
    for inc in spec.get("include", []):
        l2, o2, i2 = load_spec(inc, seen)
        lines += l2
        overrides += o2
        infill += i2
    ids = {ln["id"] for ln in spec.get("lines", [])}
    lines = [ln for ln in lines if ln["id"] not in ids] + spec.get("lines", [])
    names = {i["name"] for i in spec.get("infill", [])}
    infill = [i for i in infill if i["name"] not in names] + spec.get("infill", [])
    shift = int(spec.get("year_shift", 0))     # move every new line / infill of this spec (and its includes)
    if shift:
        lines = [dict(ln, year=ln["year"] + shift) if "year" in ln else
                 dict(ln, stages=[[a, b, y + shift] for a, b, y in ln["stages"]]) for ln in lines]
        infill = [dict(i, year=int(i["year"]) + shift) for i in infill]
    return lines, overrides + spec.get("stage_overrides", []), infill


def add_infill(t, st, item, new_id):
    """Insert an infill stop on an existing line (and on every same-mode line sharing that
    track) at the track point nearest item's lat/lon. The track keeps its year; the stop opens
    in item["year"]. Returns the station id used."""
    lat, lon = item["lat"], item["lon"]
    mode = {r["line_id"]: r["mode"] for r in t["lines.csv"]}
    segs = sorted((r for r in t["line_segments.csv"] if r["line_id"] == item["line"]), key=lambda r: int(r["seq"]))
    stops = sorted((r for r in t["line_stops.csv"] if r["line_id"] == item["line"]), key=lambda r: int(r["seq"]))
    best = None
    for r in segs:
        pts = geo.parse_wkt(r["geometry_wkt"])
        for k in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            kx = math.cos(math.radians(lat))
            dx, dy = (x1 - x0) * kx, y1 - y0
            f = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((lon - x0) * kx * dx + (lat - y0) * dy) / (dx * dx + dy * dy)))
            p = (x0 + f * (x1 - x0), y0 + f * (y1 - y0))
            d = geo.hav_km(lat, lon, p[1], p[0])
            if best is None or d < best[0]:
                best = (d, int(r["seq"]), k, p)
    d, seq, k, p = best
    a, b = stops[seq - 1]["station_id"], stops[seq]["station_id"]
    sid = new_id
    st[sid] = {"station_id": sid, "name": item["name"], "lat": f"{p[1]:.6f}", "lon": f"{p[0]:.6f}"}
    t["stations.csv"].append(st[sid])
    # every same-mode line running a <-> b gets the stop
    for lid in sorted({r["line_id"] for r in t["line_stops.csv"]}):
        if mode[lid] != mode[item["line"]]:
            continue
        ls = sorted((r for r in t["line_stops.csv"] if r["line_id"] == lid), key=lambda r: int(r["seq"]))
        ids = [r["station_id"] for r in ls]
        for i in range(len(ids) - 1):
            if {ids[i], ids[i + 1]} != {a, b}:
                continue
            seg = next(r for r in t["line_segments.csv"] if r["line_id"] == lid and int(r["seq"]) == i + 1)
            pts = geo.parse_wkt(seg["geometry_wkt"])       # in this line's direction
            # split inside the vertex pair the stop sits on (smallest detour via the stop)
            dk = lambda u, v: geo.hav_km(u[1], u[0], v[1], v[0])
            kk = min(range(len(pts) - 1), key=lambda q: dk(pts[q], p) + dk(p, pts[q + 1]) - dk(pts[q], pts[q + 1]))
            first = pts[:kk + 1] + [p]
            second = [p] + pts[kk + 1:]
            for r in t["line_stops.csv"]:
                if r["line_id"] == lid and int(r["seq"]) > i + 1:
                    r["seq"] = str(int(r["seq"]) + 1)
            for r in t["line_segments.csv"]:
                if r["line_id"] == lid and int(r["seq"]) > i + 1:
                    r["seq"] = str(int(r["seq"]) + 1)
            wkt = lambda q: "LINESTRING (" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in q) + ")"
            seg["geometry_wkt"] = wkt(first)
            t["line_segments.csv"].append(dict(seg, seq=str(i + 2), geometry_wkt=wkt(second)))
            yr = max(int(item["year"]), int(seg["year_opens"]))
            t["line_stops.csv"].append({"line_id": lid, "seq": str(i + 2), "station_id": sid, "year_opens": str(yr)})
            for r in t["stages.csv"]:
                if r["line_id"] == lid:
                    for c in ("from_stop", "to_stop"):
                        if r[c].startswith("#") and int(r[c][1:]) > i + 1:
                            r[c] = f"#{int(r[c][1:]) + 1}"
            break
    return sid, d


def places():
    out = []
    for fn in ("dfw_gazetteer.json", "dfw_hoods.json"):
        p = config.path("data", fn)
        if os.path.exists(p):
            for e in json.load(open(p, encoding="utf-8"))["elements"]:
                t = e.get("tags", {})
                if t.get("name") and "lat" in e and t.get("place") in (
                        "neighbourhood", "quarter", "suburb", "town", "village", "city", "hamlet"):
                    out.append((e["lat"], e["lon"], t["name"]))
    return out


def compass(lat0, lon0, lat1, lon1):
    b = math.degrees(math.atan2((lon1 - lon0) * math.cos(math.radians(lat0)), lat1 - lat0)) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((b + 22.5) // 45) % 8]


def place_name(lat, lon, gaz, namer=None, taken=None):
    """A new stop's name: cross streets / neighbourhood / landmark (dfwt/naming.py)
    when the road extract is there, else the nearest place (plus a compass point
    if it is over 800 m away, which tools/rename_stations.py --propose fixes)."""
    best = min(gaz, key=lambda p: geo.hav_km(lat, lon, p[0], p[1]))
    d = geo.hav_km(lat, lon, best[0], best[1])
    fallback = best[2] if d < 0.8 else f"{best[2]} {compass(best[0], best[1], lat, lon)}"
    if namer is None or not namer.segs:
        return fallback
    return namer.name(lat, lon, taken, fallback)[0]


def in_core(lat, lon, cfg):
    return any(isinstance(c, dict) and geo.hav_km(lat, lon, c["lat"], c["lon"]) <= c["radius_km"]
               for c in cfg["cores"].values())


def auto_stages(ln, legs, cfg):
    """No explicit stages: open from the first stop in pieces no longer than the mode's
    stage limit, as many per five-year interval as the interval limit allows, from ln["year"]."""
    rules = cfg["staging"]
    per_stage, per_int = rules["max_km_per_stage"][ln["mode"]], rules["max_km_per_interval"][ln["mode"]]
    km = [sum(geo.hav_km(*leg[j], *leg[j + 1]) for j in range(len(leg) - 1)) for leg in legs]
    out, start, acc, year, in_int = [], 0, 0.0, ln["year"], 0.0
    for i, k in enumerate(km):
        if acc + k > per_stage and i > start:
            if in_int + acc > per_int:
                year, in_int = year + 5, 0.0
            out.append((start, i, year))
            in_int += acc
            start, acc = i, 0.0
        acc += k
    if in_int + acc > per_int:
        year += 5
    out.append((start, len(km), year))
    return out


def fix_infill_years(t, want):
    """Stages re-time a staged line's stops, keeping an infill stop's delay relative to the
    stored segment year. Shift each infill stop's stored year so that, after the stages are
    applied, it opens in the year asked for."""
    import copy
    from dfwt import staging
    st_name = {r["station_id"]: r["name"] for r in t["stations.csv"]}
    tabs = {k: copy.deepcopy(v) for k, v in t.items() if k != "stages.csv"}
    compiled, _, _ = staging.compile_stages(tabs, copy.deepcopy(t["stages.csv"]))
    got = {(r["line_id"], r["seq"]): int(r["year_opens"]) for r in compiled["line_stops.csv"]}
    for r in t["line_stops.csv"]:
        y = want.get(st_name.get(r["station_id"]))
        if y is not None and got.get((r["line_id"], r["seq"]), y) != y:
            r["year_opens"] = str(int(r["year_opens"]) + y - got[(r["line_id"], r["seq"])])


_ROADS = None
_DENS = None
BRT_SPACING_KM = {"urban": 1.2, "suburban": 1.6}   # stop spacing for new BRT, by how dense the street is


def _density_at(lat, lon):
    """People + jobs per km2 within 800 m of the nearest zone (base data)."""
    global _DENS
    import numpy as np
    from dfwt import demand
    if _DENS is None:
        z = demand.Zones(config.load())
        _DENS = (z, demand.activity_density(z))
    z, dens = _DENS
    from dfwt.geo import Projector
    x, y = Projector().xy(lat, lon)
    return float(dens[int(np.argmin((z.x - x) ** 2 + (z.y - y) ** 2))])


ANCHOR_KM = 0.3   # a station this close to a new BRT street becomes one of its stops


def brt_anchors(pts, L, stations, ends):
    """Stations (id -> (lat, lon)) within ANCHOR_KM of a BRT leg, as [(km along, id)]: the bus
    stops there, so new lines meet the rail and BRT they pass instead of missing them by a
    few hundred metres. Leg ends and stations near them are left out."""
    lat0 = pts[0][0]
    kx = 111.32 * math.cos(math.radians(lat0))
    P = [((p[1] - pts[0][1]) * kx, (p[0] - lat0) * 110.57) for p in pts]
    lo_lat, hi_lat = min(p[0] for p in pts) - 0.004, max(p[0] for p in pts) + 0.004
    lo_lon, hi_lon = min(p[1] for p in pts) - 0.005, max(p[1] for p in pts) + 0.005
    out = {}
    for sid, (la, lo) in stations.items():
        if sid in ends or not (lo_lat <= la <= hi_lat and lo_lon <= lo <= hi_lon):
            continue
        q = ((lo - pts[0][1]) * kx, (la - lat0) * 110.57)
        acc, best = 0.0, None
        for a, b in zip(P, P[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            seg = math.hypot(dx, dy)
            t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (seg * seg))) if seg else 0.0
            d = math.hypot(a[0] + t * dx - q[0], a[1] + t * dy - q[1])
            if best is None or d < best[0]:
                best = (d, acc + t * seg)
            acc += seg
        if best and best[0] <= ANCHOR_KM and 0.4 < best[1] * L / (acc or 1) < L - 0.4:
            out[sid] = best[1] * L / acc
    picked = []
    for sid, d in sorted(out.items(), key=lambda kv: kv[1]):
        if not picked or d - picked[-1][0] > 0.4:   # two stations a few steps apart: stop at the first
            picked.append((d, sid))
    return picked


def brt_cuts(pts, L, start=0.0):
    """Distances along a BRT leg (km) for its intermediate stops between `start` and `L`:
    about every 1.2 km where the street is urban (config growth.tod.setting_density_per_km2),
    1.6 km elsewhere, evened out so the last gap isn't a stub."""
    urban = config.load()["growth"]["tod"]["setting_density_per_km2"]["urban"]

    def point_at(d):
        acc = 0.0
        for a, b in zip(pts, pts[1:]):
            dl = geo.hav_km(*a, *b)
            if acc + dl >= d:
                f = (d - acc) / dl if dl else 0
                return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
            acc += dl
        return pts[-1]

    def gap(d):
        lat, lon = point_at(d)
        return BRT_SPACING_KM["urban" if _density_at(lat, lon) >= urban else "suburban"]

    cuts, pos = [], start
    while pos + gap(pos) < L - 0.5 * gap(pos):
        pos += gap(pos)
        cuts.append(pos)
    if cuts:   # stretch so the last stop isn't crowded against the end
        k = (L - start) / (cuts[-1] + gap(cuts[-1]) - start)
        cuts = [start + (c - start) * k for c in cuts]
    return cuts
STREET_WORDS = ("lane", "boulevard", "blvd", "road", "parkway", "tap", "avenue", "drive", "freeway", "highway", "street",
                "loop", "trail", "pike", "expressway")


def street_hint(name):
    """'Josey Lane BRT' -> 'Josey', 'Denton Tap BRT' -> 'Denton Tap': the street a BRT line
    is named after, if its name says so (place-named lines get None)."""
    words = [w for w in name.replace("BRT", "").split() if w]
    for i, w in enumerate(words):
        if w.lower().strip(",") in STREET_WORDS and i:
            return " ".join(words[:i + (1 if w.lower() == "tap" else 0)])
    return None


def _cut_loops(P, near=80.0):
    """Remove detours where the route comes back within `near` m of where it already
    was (circling a block to touch a waypoint)."""
    import math
    out = list(P)
    i = 0
    while i < len(out):
        cut = None
        run = 0.0
        for j in range(i + 1, len(out)):
            run += math.dist(out[j - 1], out[j])
            if run > 2500:   # only small loops (around a block or two), never a line that circles back
                break
            if run > 3 * near + 150 and math.dist(out[i], out[j]) < near:
                cut = j
        if cut is not None:
            out = out[:i + 1] + out[cut:]
        i += 1
    return out


def road_path(pts, name):
    """Route a BRT corridor through its waypoints ((lat, lon) list) on the road network,
    favoring arterials and the street it is named after. Returns (lat, lon) points, or
    None if no route is found (the caller keeps the straight lines)."""
    global _ROADS
    from dfwt import osmroute
    if _ROADS is None:
        _ROADS = osmroute.Graph("road", classes={"primary", "secondary", "tertiary", "trunk", "motorway"})
    w_cls = {"primary": 1.0, "secondary": 1.0, "trunk": 1.15, "tertiary": 1.35, "motorway": 1.6}
    hint = street_hint(name)
    xy = [osmroute.xy(lon, lat) for lat, lon in pts]
    if len(xy) > 2:
        # the waypoints are rough guesses: if the street route between the ends alone passes
        # near every one of them and is no longer, the bus just stays on that street
        import math
        P2, _ = osmroute.route(_ROADS, [xy[0], xy[-1]], max_turn=100, snap_r=900, w_cls=w_cls, turn_pen=700.0,
                               detour=2.5, snap_w=1.0, prefer=hint)
        if P2 and all(min(math.dist(w, q) for q in P2) < 1200 for w in xy[1:-1]):
            P1, _ = osmroute.route(_ROADS, xy, max_turn=100, snap_r=900, w_cls=w_cls, turn_pen=700.0, detour=2.5,
                                   snap_w=1.0, prefer=hint)
            L = lambda P: sum(math.dist(a, b) for a, b in zip(P, P[1:]))
            if not P1 or L(P2) <= 1.1 * L(P1):
                return [(lat, lon) for lon, lat in (osmroute.ll(p) for p in _cut_loops(P2))]
    for snap, turn in ((900, 100), (1500, 135)):
        # waypoints are loose guides (snap_w 1): a bus stays on its street rather than
        # zigzagging to touch each one; turns cost extra so it changes street rarely
        P, _ = osmroute.route(_ROADS, xy, max_turn=turn, snap_r=snap, w_cls=w_cls, turn_pen=700.0, detour=2.5,
                              snap_w=1.0, prefer=hint)
        if P:
            P = _cut_loops(P)
            out = [(lat, lon) for lon, lat in (osmroute.ll(p) for p in P)]
            return out   # the station ends are joined later (a detour only if a station is off the street)
    return None


TAIL_M, TAIL_TURN = 700.0, 60.0   # a BRT end that turns this sharply this close to the end stops at the turn


def trim_tail(pts):
    """(lat, lon) route ending at a new terminus: if it turns off its street (more than
    TAIL_TURN degrees) within the last TAIL_M, cut it at that turn so the line ends on the
    arterial instead of a block into a neighborhood. Returns the (possibly shorter) points."""
    from dfwt import osmroute
    P = [osmroute.xy(lon, lat) for lat, lon in pts]
    if len(P) < 3:
        return pts
    acc, cut = 0.0, None
    for i in range(len(P) - 2, 0, -1):   # walk back from the end
        acc += math.dist(P[i], P[i + 1])
        if acc > TAIL_M:
            break
        h1 = math.atan2(P[i][1] - P[i - 1][1], P[i][0] - P[i - 1][0])
        h2 = math.atan2(P[i + 1][1] - P[i][1], P[i + 1][0] - P[i][0])
        if abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi)) > TAIL_TURN and acc > 80:
            cut = i   # keep the farthest such turn: everything after the first sharp turn goes
    return pts[:cut + 1] if cut else pts


_FREEWAYS = None


def metro_road_path(pts):
    """Route a rail line through its stations ((lat, lon) list) along freeway and arterial
    corridors (light rail in a freeway or boulevard right-of-way rather than through
    neighborhoods): freeways and major arterials preferred, changing roads costs a lot.
    Returns (lat, lon) points or None."""
    global _FREEWAYS
    from dfwt import osmroute
    if _FREEWAYS is None:
        _FREEWAYS = osmroute.Graph("road", classes={"motorway", "trunk", "primary", "secondary"}, oneway=False)
    w_cls = {"motorway": 1.0, "trunk": 1.0, "primary": 1.1, "secondary": 1.3}
    xy = [osmroute.xy(lon, lat) for lat, lon in pts]
    for snap, turn in ((700, 100), (1200, 135)):
        P, _ = osmroute.route(_FREEWAYS, xy, max_turn=turn, snap_r=snap, w_cls=w_cls, turn_pen=1500.0, detour=1.8,
                              snap_w=3.0)
        if P:
            return [(lat, lon) for lon, lat in (osmroute.ll(p) for p in _cut_loops(P))]
    return None


def build(name):
    cfg = config.load()
    base = config.path("network")
    out = config.path("scenarios", name)
    t = {k: read(base, k) for k in TABLES}
    specs, overrides, infill = load_spec(name)
    for o in overrides:
        for r in t["stages.csv"]:
            if r["line_id"] == o["line_id"] and r["stage"] == str(o["stage"]):
                r["year_opens"] = str(o["year_opens"])
                r["note"] = o.get("note", "expansion lever: retimed")
    st = {r["station_id"]: r for r in t["stations.csv"]}
    used = {r["station_id"] for r in t["line_stops.csv"]}
    gaz = places()
    from dfwt.naming import Namer, keys
    namer = Namer()
    taken = set().union(*(keys(r["name"]) for r in t["stations.csv"]))
    counter = 1
    report = []

    def nearest_existing(lat, lon):
        best, bd = None, 1e9
        for sid in used:
            s = st[sid]
            if abs(float(s["lat"]) - lat) > 0.01:
                continue
            d = geo.hav_km(lat, lon, float(s["lat"]), float(s["lon"]))
            if d < bd:
                best, bd = sid, d
        return best, bd

    new_ids = []
    for item in infill:
        sid, d = add_infill(t, st, item, f"XS{counter:04d}")
        counter += 1
        used.add(sid)
        new_ids.append(sid)
        report.append(f"infill {item['name']} on {item['line']} ({d * 1000:.0f} m from the asked point), opens {item['year']}")
    # stops more than one corridor asks for (two new lines meeting): never trimmed away
    spec_pts = [(ln["id"], w["lat"], w["lon"]) for ln in specs for w in ln["stops"]
                if isinstance(w, dict) and "lat" in w and not w.get("via")]
    for ln in specs:
        lid = ln["id"]
        mode = ln["mode"]
        spacing = ln.get("spacing_km", {"metro": 1.2, "brt": 0.8, "commuter": 6}[mode])
        # waypoints -> [(lat, lon, sid or None, name, is_stop, grade_or_None)]
        wps = []
        express = set()   # waypoints reached without intermediate stops
        for w in ln["stops"]:
            if isinstance(w, str):
                if w not in st:     # a unique station name (e.g. a stop another new line created)
                    hits = [k for k, v in st.items() if v["name"] == w and k in used]
                    if len(hits) != 1:
                        raise SystemExit(f"{lid}: stop '{w}' is not a station id or a unique station name")
                    w = hits[0]
                s = st[w]
                wps.append((float(s["lat"]), float(s["lon"]), w, s["name"], True, None))
            elif "lat" not in w:   # {"id": existing station, "express": true}: no stops added on the way to it
                s = st[w["id"]]
                wps.append((float(s["lat"]), float(s["lon"]), w["id"], s["name"], True, w.get("grade")))
                express.add(len(wps) - 1)
            else:
                wps.append((w["lat"], w["lon"], w.get("id"), w.get("name"), not w.get("via"), w.get("grade")))
                if w.get("express"):
                    express.add(len(wps) - 1)
        # split into stop-to-stop legs (with via points), add intermediate stops on long legs
        stops = []          # (lat, lon, sid, name, explicit)
        legs = []           # list of point lists between consecutive stops, with grade
        grade = ln.get("grade", "surface")
        cur = [wps[0]]
        stops.append(wps[0])
        leg_grades = []
        g_now = wps[0][5] or grade
        for w in wps[1:]:
            cur.append(w)
            if not w[4]:
                continue
            pts = [(p[0], p[1]) for p in cur]
            if mode == "metro" and ln.get("follow_roads"):   # rail in a freeway/arterial corridor
                routed = metro_road_path(pts)
                if routed:
                    pts = routed
                else:
                    report.append(f"{lid} {ln['name']}: no road corridor for a leg; kept straight")
            if mode == "brt":   # BRT runs in the street: follow the roads, stops placed along them
                routed = road_path(pts, ln["name"])
                if routed:
                    pts = routed
                    # a new terminus a turn into a neighborhood: end on the arterial instead
                    def snaps(q):   # ends at a station, or where another new line stops: keep it
                        return nearest_existing(q[0], q[1])[1] * 1000 <= SNAP_M or any(
                            o != lid and geo.hav_km(q[0], q[1], a, b) * 1000 <= SNAP_M for o, a, b in spec_pts)
                    if w is wps[-1] and w[2] is None and not snaps(w):
                        pts = trim_tail(pts)
                        if pts[-1] != (w[0], w[1]):
                            w = (pts[-1][0], pts[-1][1], None, None, True, w[5])
                    if cur[0] is wps[0] and wps[0][2] is None and not snaps(wps[0]):
                        pts = trim_tail(pts[::-1])[::-1]
                        if pts[0] != (wps[0][0], wps[0][1]):
                            stops[0] = (pts[0][0], pts[0][1], None, None, True, wps[0][5])
                else:
                    report.append(f"{lid} {ln['name']}: no street route for a leg; kept straight")
            L = sum(geo.hav_km(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1))
            if mode == "brt":   # stations it passes are stops; regular stops fill the gaps between them
                served = {sid: (float(st[sid]["lat"]), float(st[sid]["lon"])) for sid in used}
                anchors = brt_anchors(pts, L, served, {cur[0][2], w[2]})
                bounds = [0.0] + [d for d, _ in anchors] + [L]
                cuts = []
                for k in range(len(bounds) - 1):
                    cuts += [(d, None) for d in brt_cuts(pts, bounds[k + 1], bounds[k])]
                    if k < len(anchors):
                        cuts.append(anchors[k])
            elif wps.index(w) in express:
                cuts = []
            else:
                n_extra = max(0, round(L / spacing) - 1) if L > 1.45 * spacing else 0
                cuts = [(L * (k + 1) / (n_extra + 1), None) for k in range(n_extra)]
            # walk the polyline, emitting intermediate stops
            sub, acc, ci = [pts[0]], 0.0, 0
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                dl = geo.hav_km(*a, *b)
                while ci < len(cuts) and acc + dl >= cuts[ci][0] - 1e-9:
                    f = (cuts[ci][0] - acc) / dl if dl else 0
                    p = (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
                    sub.append(p)
                    legs.append(sub)
                    leg_grades.append(g_now)
                    stops.append((p[0], p[1], cuts[ci][1], None, False))
                    sub = [p]
                    ci += 1
                acc += dl
                sub.append(b)
            legs.append(sub)
            leg_grades.append(g_now)
            stops.append(w)
            g_now = w[5] or g_now
            cur = [w]
        # resolve stop ids (snap, or new station)
        sids, names = [], []
        for s in stops:
            lat, lon, sid, nm = s[0], s[1], s[2], s[3]
            if sid is None:
                cand, d = nearest_existing(lat, lon)
                if cand and d * 1000 <= SNAP_M:
                    sid = cand
                    report.append(f"{lid}: snapped {nm or 'stop'} to {st[cand]['name']} ({d * 1000:.0f} m)")
                else:
                    sid = f"XS{counter:04d}"
                    counter += 1
                    nm = nm or place_name(lat, lon, gaz, namer, taken)
                    st[sid] = {"station_id": sid, "name": nm, "lat": f"{lat:.6f}", "lon": f"{lon:.6f}"}
                    t["stations.csv"].append(st[sid])
                    new_ids.append(sid)
            if sid in sids:
                if s[4]:    # an explicit stop the spec asked for twice
                    raise SystemExit(f"{lid}: stop {st[sid]['name']} appears twice")
                # an added stop that snapped to a station this line already serves (the street
                # passes it twice): drop it and join the legs on either side
                k = len(sids)
                legs[k - 1:k + 1] = [legs[k - 1] + legs[k][1:]]
                leg_grades[k - 1:k + 1] = [leg_grades[k - 1]]
                continue
            sids.append(sid)
            names.append(st[sid]["name"])
            used.add(sid)
        # snap leg ends onto the (possibly snapped) station coordinates
        for i, leg in enumerate(legs):
            a, b = st[sids[i]], st[sids[i + 1]]
            for end, s_ in ((0, a), (-1, b)):
                at = (float(s_["lat"]), float(s_["lon"]))
                if mode == "brt" and len(leg) > 2 and geo.hav_km(*leg[end], *at) <= 0.25:
                    continue    # a station beside the street: the bus stops on the street, no detour
                leg[end] = at
        # stage years per segment
        ref = {}
        for i, sid in enumerate(sids):
            ref[sid] = i
            ref[st[sid]["name"]] = ref.get(st[sid]["name"], i) if names.count(st[sid]["name"]) == 1 else None
        seg_year = [None] * len(legs)
        stage_rows = []
        stages = ln.get("stages") or auto_stages(ln, legs, cfg)
        for k, (a, b, y) in enumerate(stages):
            if isinstance(a, int):
                a, b = sids[a], sids[b]
            for x in (a, b):
                if ref.get(x) is None:
                    raise SystemExit(f"{lid}: stage stop '{x}' is not a unique stop on the line (use a station id)")
            ia, ib = sorted((ref[a], ref[b]))
            for i in range(ia, ib):
                seg_year[i] = y if seg_year[i] is None else min(seg_year[i], y)
            stage_rows.append({"line_id": lid, "stage": k + 1, "kind": "starter" if k == 0 else "extension",
                               "from_stop": sids[ia], "to_stop": sids[ib], "year_opens": y,
                               "note": "expansion lever (hand-staged)"})
        if None in seg_year:
            raise SystemExit(f"{lid}: segment {seg_year.index(None) + 1} is in no stage")
        t["lines.csv"].append({"line_id": lid, "name": ln["name"], "mode": mode, "status": "proposed",
                               "color": ln.get("color", "#e65100"), "headway_min": ln.get("headway_min", ""),
                               "notes": ln.get("notes", "expansion lever")})
        for i, sid in enumerate(sids):
            yrs = [seg_year[j] for j in (i - 1, i) if 0 <= j < len(legs)]
            t["line_stops.csv"].append({"line_id": lid, "seq": i + 1, "station_id": sid, "year_opens": min(yrs)})
        km = 0.0
        cost = 0.0
        for i, leg in enumerate(legs):
            g = leg_grades[i]
            if mode == "metro" and (in_core(*leg[0], cfg) or in_core(*leg[-1], cfg)):
                g = "tunnel"
            wkt = "LINESTRING (" + ", ".join(f"{p[1]:.6f} {p[0]:.6f}" for p in leg) + ")"
            t["line_segments.csv"].append({"line_id": lid, "seq": i + 1, "year_opens": seg_year[i], "grade": g,
                                           "geometry_source": "drawn", "locked": "", "geometry_wkt": wkt})
            k = sum(geo.hav_km(*leg[j], *leg[j + 1]) for j in range(len(leg) - 1))
            km += k
            cost += k * cfg["cost_musd_per_km"][mode].get(g, cfg["cost_musd_per_km"][mode]["surface"])
        t["stages.csv"] += stage_rows
        report.append(f"{lid} {ln['name']}: {len(sids)} stops, {km:.1f} km, track ~${cost / 1e3:.1f}B, "
                      f"opens {min(seg_year)}-{max(seg_year)}")
    # explicit walk links from new stations to other lines' stations 400-650 m away
    linked = {frozenset((r["station_a"], r["station_b"])) for r in t["transfers.csv"]}
    for sid in new_ids:
        a = st[sid]
        for oid in list(used):
            if oid == sid:
                continue
            b = st[oid]
            if abs(float(a["lat"]) - float(b["lat"])) > 0.007:
                continue
            d = geo.hav_km(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
            if 0.4 < d <= TRANSFER_M / 1000 and frozenset((sid, oid)) not in linked:
                t["transfers.csv"].append({"station_a": sid, "station_b": oid, "walk_min": "",
                                           "note": f"expansion lever: {a['name']} <-> {b['name']}, {d * 1000:.0f} m"})
                linked.add(frozenset((sid, oid)))
    t["stages.csv"].sort(key=lambda r: (r["line_id"], int(r["stage"])))
    fix_infill_years(t, {i["name"]: int(i["year"]) for i in infill})
    for k in TABLES:
        write(out, k, t[k])
    print("\n".join(report))


if __name__ == "__main__":
    for n in sys.argv[1:]:
        build(n)
