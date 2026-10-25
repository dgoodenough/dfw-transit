"""GTFS -> today's fixed-route rail and frequent bus, in dfwt's network table format.

For each feed:
  1. pick a typical weekday: among the Tue-Thu dates the calendar covers, the most
     common trip count (holidays and overlapping service periods fall out), earliest such date;
  2. for every route (by route_type: rail, subway/metro, tram/light rail, bus), count trips
     leaving their first stop in the AM peak window (07:00-09:00 by default) in each
     direction; the busier direction's count gives the peak headway;
  3. keep all rail, subway and tram routes, BRT-named bus routes, and bus routes at or
     under the frequent-headway threshold (15 min by default);
  4. the busier direction's most common stop pattern becomes the line: stops (collapsed to
     their parent station) and, between consecutive stops, the trip's shape cut at the
     stops (by shape_dist_traveled when the feed has it, else by projection).

Output tables follow network/README.md: lines.csv, stations.csv, line_stops.csv,
line_segments.csv, all with status "existing". Plus routes.csv: every route considered,
its peak headway and why it was kept or dropped.
"""
import collections
import csv
import datetime as dt
import io
import math
import os
import re
import zipfile

from dfwt import geo

RAIL, SUBWAY, TRAM, BUS = "rail", "subway", "tram", "bus"
MIDDAY = (10 * 3600, 14 * 3600)   # base-service window, reported alongside the peak headway
DEFAULT_COLOR = {"commuter": "#4A5D7E", "metro": "#0071BC", "streetcar": "#e57373", "brt": "#7b1fa2", "bus": "#607d8b"}


def route_class(route_type):
    """GTFS route_type (basic or extended) -> rail / subway / tram / bus / None (ferry, aerial, coach...)."""
    try:
        t = int(route_type)
    except (TypeError, ValueError):
        return None
    if t == 2 or 100 <= t <= 117:
        return RAIL
    if t in (1, 12) or 400 <= t <= 404 or t == 405:
        return SUBWAY
    if t in (0, 5) or 900 <= t <= 906:
        return TRAM
    if t in (3, 11) or 700 <= t <= 716 or t == 800:
        return BUS
    return None


def parse_time(s):
    """'HH:MM:SS' (hours may pass 24) -> seconds, or None if blank."""
    s = (s or "").strip()
    if not s:
        return None
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + int(sec)


def _hhmm(secs):
    return f"{int(secs) // 3600:02d}:{int(secs) % 3600 // 60:02d}"


# ---------- reading ----------
class Feed:
    """A GTFS feed in a .zip or a directory. table(name) yields dict rows ([] if absent)."""

    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
        if self.zip:
            self.names = {os.path.basename(n): n for n in self.zip.namelist() if n.endswith(".txt")}
        else:
            self.names = {n: os.path.join(path, n) for n in os.listdir(path) if n.endswith(".txt")}

    def has(self, name):
        return name in self.names

    def table(self, name):
        if name not in self.names:
            return
        if self.zip:
            with self.zip.open(self.names[name]) as raw:
                yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        else:
            with open(self.names[name], encoding="utf-8-sig", newline="") as f:
                yield from csv.DictReader(f)


# ---------- service calendar ----------
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _date(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


class Calendar:
    def __init__(self, cal_rows, cd_rows):
        self.base = []
        for r in cal_rows:
            self.base.append((r["service_id"], _date(r["start_date"]), _date(r["end_date"]),
                              tuple(r.get(d, "0").strip() == "1" for d in DAYS)))
        self.exc = collections.defaultdict(dict)
        for r in cd_rows:
            self.exc[_date(r["date"])][r["service_id"]] = r["exception_type"].strip()

    def active(self, day):
        s = {sid for sid, a, b, wd in self.base if a <= day <= b and wd[day.weekday()]}
        for sid, t in self.exc.get(day, {}).items():
            if t == "1":
                s.add(sid)
            elif t == "2":
                s.discard(sid)
        return s

    def span(self):
        ds = [a for _, a, _, _ in self.base] + [b for _, _, b, _ in self.base] + list(self.exc)
        return (min(ds), max(ds)) if ds else (None, None)


def pick_weekday(cal, trips_per_service, max_days=400, window=None):
    """Typical Tue-Thu: the most common nonzero trip count, earliest date with it.
    `window` (start, end) narrows the search, e.g. to feed_info's validity dates.
    Returns (date, active service ids, trip count) or (None, set(), 0)."""
    a, b = cal.span()
    if a is None:
        return None, set(), 0
    if window and window[0] <= b and window[1] >= a:
        a, b = max(a, window[0]), min(b, window[1])
    counts = []
    d = a
    while d <= b and (d - a).days <= max_days:
        if d.weekday() in (1, 2, 3):
            act = cal.active(d)
            n = sum(trips_per_service.get(s, 0) for s in act)
            if n:
                counts.append((d, n, act))
        d += dt.timedelta(days=1)
    if not counts:
        return None, set(), 0
    freq = collections.Counter(n for _, n, _ in counts)
    best = max(freq.items(), key=lambda kv: (kv[1], kv[0]))[0]
    d, n, act = next(c for c in counts if c[1] == best)
    return d, act, n


# ---------- geometry ----------
def _xy(lon, lat, lat0):
    return (lon * 111.320 * math.cos(math.radians(lat0)), lat * 110.574)


def cumulative(pts):
    """[(lon, lat)] -> cumulative km along the polyline."""
    m = [0.0]
    for p, q in zip(pts, pts[1:]):
        m.append(m[-1] + geo.hav_km(p[1], p[0], q[1], q[0]))
    return m


def project_stops(shape, stops):
    """Measure (km along `shape`) of each stop, kept non-decreasing so a loop or a
    route that doubles back cuts in order. shape, stops: [(lon, lat)]."""
    lat0 = shape[0][1]
    S = [_xy(x, y, lat0) for x, y in shape]
    M = cumulative(shape)
    out, k0 = [], 0
    for lon, lat in stops:
        px, py = _xy(lon, lat, lat0)
        best = (float("inf"), k0, 0.0)
        for k in range(k0, len(S) - 1):
            (ax, ay), (bx, by) = S[k], S[k + 1]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            d2 = (ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2
            if d2 < best[0] - 1e-12:
                best = (d2, k, t)
        _, k, t = best
        k0 = k
        out.append(M[k] + t * (M[k + 1] - M[k]) if len(M) > 1 else 0.0)
    return out


def cut(shape, M, m0, m1):
    """Part of `shape` (cumulative measures M) between measures m0 <= m1, endpoints interpolated."""
    def at(m):
        for k in range(len(M) - 1):
            if M[k] <= m <= M[k + 1]:
                f = 0.0 if M[k + 1] == M[k] else (m - M[k]) / (M[k + 1] - M[k])
                (ax, ay), (bx, by) = shape[k], shape[k + 1]
                return (ax + f * (bx - ax), ay + f * (by - ay))
        return shape[0] if m <= M[0] else shape[-1]
    pts = [at(m0)] + [p for p, m in zip(shape, M) if m0 < m < m1] + [at(m1)]
    return pts


# ---------- the analysis ----------
def analyze(feed, tag, *, am=(7 * 3600, 9 * 3600), frequent_max=15.0, brt_pattern=None,
            existing_year=2025, label=""):
    """One feed -> dict of table rows {lines, stations, line_stops, line_segments, routes} and info."""
    routes = {r["route_id"]: r for r in feed.table("routes.txt")}
    rclass = {rid: route_class(r.get("route_type")) for rid, r in routes.items()}
    trips = {}
    per_service = collections.Counter()
    for r in feed.table("trips.txt"):
        if rclass.get(r["route_id"]) is None:
            continue
        trips[r["trip_id"]] = r
        per_service[r["service_id"]] += 1
    cal = Calendar(feed.table("calendar.txt"), feed.table("calendar_dates.txt"))
    fi = next(feed.table("feed_info.txt"), None) or {}
    window = None
    if all(re.fullmatch(r"[0-9]{8}", fi.get(k) or "") for k in ("feed_start_date", "feed_end_date")):
        window = (_date(fi["feed_start_date"]), _date(fi["feed_end_date"]))
    day, active, n_day = pick_weekday(cal, per_service, window=window)
    info = {"tag": tag, "label": label, "service_date": day.isoformat() if day else None,
            "trips_on_date": n_day, "am_window": [am[0] / 3600, am[1] / 3600], "frequent_headway_min": frequent_max}
    empty = {k: [] for k in ("lines", "stations", "line_stops", "line_segments", "routes")}
    if not day:
        info["error"] = "no weekday service found in calendar"
        return empty, info
    trips = {t: r for t, r in trips.items() if r["service_id"] in active}

    # headway-based trips (frequencies.txt): departures per trip
    freq = collections.defaultdict(list)
    for r in feed.table("frequencies.txt"):
        if r["trip_id"] in trips:
            freq[r["trip_id"]].append((parse_time(r["start_time"]), parse_time(r["end_time"]), int(r["headway_secs"])))

    st = collections.defaultdict(list)
    for r in feed.table("stop_times.txt"):
        if r["trip_id"] in trips:
            d = r.get("shape_dist_traveled", "")
            st[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"],
                                     parse_time(r.get("departure_time")) or parse_time(r.get("arrival_time")),
                                     float(d) if d not in ("", None) else None))
    # per route & direction: [(first departure, stops tuple, trip_id)]
    by_rd = collections.defaultdict(list)
    for tid, rows in st.items():
        rows.sort()
        t = trips[tid]
        stops = tuple(x[1] for x in rows)
        first = next((x[2] for x in rows if x[2] is not None), None)
        deps = [first]
        if tid in freq:
            deps = []
            for a, b, h in freq[tid]:
                deps.extend(range(a, b, max(h, 60)))
        for dep in deps:
            by_rd[(t["route_id"], t.get("direction_id", "") or "")].append((dep, stops, tid))

    stops_tbl = {r["stop_id"]: r for r in feed.table("stops.txt")}

    def station_of(sid):
        r = stops_tbl.get(sid, {})
        p = (r.get("parent_station") or "").strip()
        return p if p and p in stops_tbl else sid

    shapes = None   # loaded lazily: only if some route is kept
    brt_re = re.compile(brt_pattern, re.I) if brt_pattern else None
    out = {k: [] for k in empty}
    used_ids, used_names, stations = set(), set(), {}
    for rid, r in sorted(routes.items(), key=lambda kv: (kv[1].get("route_sort_order") or "", kv[0])):
        cls = rclass.get(rid)
        dirs = {d: v for (ri, d), v in by_rd.items() if ri == rid}
        short, long_ = (r.get("route_short_name") or "").strip(), (r.get("route_long_name") or "").strip()
        summary = {"feed": tag, "route_id": rid, "short_name": short, "long_name": long_,
                   "route_type": r.get("route_type"), "class": cls or "", "trips_on_date": sum(len(v) for v in dirs.values()),
                   "am_trips_busier_dir": 0, "headway_min": "", "headway_basis": "", "midday_headway_min": "",
                   "mode": "", "kept": 0, "reason": ""}
        out["routes"].append(summary)
        if cls is None:
            summary["reason"] = "route_type not rail/metro/tram/bus"
            continue
        if not dirs:
            summary["reason"] = "no trips on service date"
            continue
        am_counts = {d: sum(1 for dep, _, _ in v if dep is not None and am[0] <= dep < am[1]) for d, v in dirs.items()}
        main = max(dirs, key=lambda d: (am_counts[d], len(dirs[d])))
        n_am = am_counts[main]
        win = (am[1] - am[0]) / 60
        if n_am >= 2:
            hw, basis = win / n_am, "am_peak"
        elif len(dirs[main]) >= 2:
            deps = sorted(dep for dep, _, _ in dirs[main] if dep is not None)
            hw, basis = (deps[-1] - deps[0]) / 60 / (len(deps) - 1), "all_day_mean"
        else:
            hw, basis = None, "single_trip"
        n_mid = sum(1 for dep, _, _ in dirs[main] if dep is not None and MIDDAY[0] <= dep < MIDDAY[1])
        summary.update(am_trips_busier_dir=n_am, headway_min=round(hw, 1) if hw else "", headway_basis=basis,
                       midday_headway_min=round((MIDDAY[1] - MIDDAY[0]) / 60 / n_mid, 1) if n_mid else "")
        name_text = f"{short} {long_} {r.get('route_desc', '')}"
        if cls == RAIL:
            mode = "commuter"
        elif cls == SUBWAY:
            mode = "metro"
        elif cls == TRAM:
            mode = None   # decided from the pattern's length and stop spacing below
        else:
            mode = "brt" if brt_re and brt_re.search(name_text) else "bus"
        if mode == "bus" and not (basis == "am_peak" and hw <= frequent_max + 1e-9):
            summary.update(mode=mode, reason=f"bus not frequent (peak headway {summary['headway_min'] or 'n/a'} > {frequent_max:g} min)")
            continue

        pool = [x for x in dirs[main] if x[0] is not None and am[0] <= x[0] < am[1]] or dirs[main]
        pats = collections.Counter(x[1] for x in pool)
        pattern = max(pats, key=lambda p: (pats[p], len(p)))
        rep = next(x[2] for x in pool if x[1] == pattern)
        rows = st[rep]
        # collapse to stations, dropping consecutive repeats
        seq = []
        for (_, sid, _, dist) in rows:
            k = station_of(sid)
            if seq and seq[-1][0] == k:
                continue
            seq.append((k, sid, dist))
        if len(seq) < 2:
            summary.update(mode=mode or "", reason="pattern has fewer than 2 stations")
            continue
        pts = [(float(stops_tbl[s]["stop_lon"]), float(stops_tbl[s]["stop_lat"])) for _, s, _ in seq]

        # geometry
        shape_id = (trips[rep].get("shape_id") or "").strip()
        if shape_id and shapes is None:
            shapes = collections.defaultdict(list)
            for p in feed.table("shapes.txt"):
                d = p.get("shape_dist_traveled", "")
                shapes[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]), float(p["shape_pt_lat"]),
                                              float(d) if d not in ("", None) else None))
            for v in shapes.values():
                v.sort()
        shp = shapes.get(shape_id) if shapes and shape_id else None
        segs = []
        if shp and len(shp) >= 2:
            S = [(x, y) for _, x, y, _ in shp]
            M = cumulative(S)
            sd = [d for *_, d in shp]
            stop_d = [d for *_, d in seq]
            if all(d is not None for d in sd) and all(d is not None for d in stop_d) and sd[-1] > sd[0]:
                # feed distances (any unit) -> km measures by linear interpolation over the shape's own points
                def to_km(d):
                    for k in range(len(sd) - 1):
                        if sd[k] <= d <= sd[k + 1]:
                            f = 0.0 if sd[k + 1] == sd[k] else (d - sd[k]) / (sd[k + 1] - sd[k])
                            return M[k] + f * (M[k + 1] - M[k])
                    return M[0] if d < sd[0] else M[-1]
                meas = [to_km(d) for d in stop_d]
                src = "gtfs_shape_dist"
            else:
                meas = project_stops(S, pts)
                src = "gtfs_shape"
            for i in range(len(seq) - 1):
                a, b = meas[i], max(meas[i], meas[i + 1])
                g = cut(S, M, a, b) if b - a > 1e-6 else [pts[i], pts[i + 1]]
                segs.append((g, src))
        else:
            segs = [([pts[i], pts[i + 1]], "straight") for i in range(len(seq) - 1)]

        km = sum(geo.polyline_km(g) for g, _ in segs)
        if mode is None:
            spacing = km / (len(seq) - 1)
            mode = "metro" if km >= 5 and spacing >= 0.5 else "streetcar"
        summary["mode"] = mode

        lid = re.sub(r"[^A-Za-z0-9_-]+", "-", short or rid).strip("-") or rid
        lid = f"{tag}_{lid}"
        if lid in used_ids:
            lid = f"{lid}_{re.sub(r'[^A-Za-z0-9_-]+', '-', rid)}"
        used_ids.add(lid)
        name = long_ or short or rid
        if short and long_ and short not in long_:
            name = f"{short} {long_}"
        if name in used_names:
            name = f"{name} ({label or tag})"
        used_names.add(name)
        color = (r.get("route_color") or "").strip()
        color = f"#{color}" if re.fullmatch(r"[0-9A-Fa-f]{6}", color) else DEFAULT_COLOR[mode]
        note = (f"GTFS {label or tag} route {rid}; {n_am} AM-peak trips ({_hhmm(am[0])}-{_hhmm(am[1])}, busier direction) "
                f"on {day.isoformat()}; headway basis {basis}; "
                + (f"midday headway {summary['midday_headway_min']} min" if n_mid else "PEAK-ONLY (no 10:00-14:00 trips)"))
        out["lines"].append({"line_id": lid, "name": name, "mode": mode, "status": "existing", "color": color,
                             "headway_min": summary["headway_min"], "notes": note})
        for i, (k, _, _) in enumerate(seq, 1):
            sid = f"{tag}_{k}"
            if sid not in stations:
                s = stops_tbl[k]
                stations[sid] = {"station_id": sid, "name": (s.get("stop_name") or k).strip(),
                                 "lat": f"{float(s['stop_lat']):.6f}", "lon": f"{float(s['stop_lon']):.6f}"}
            out["line_stops"].append({"line_id": lid, "seq": i, "station_id": sid, "year_opens": existing_year})
        for i, (g, src) in enumerate(segs, 1):
            out["line_segments"].append({"line_id": lid, "seq": i, "year_opens": existing_year, "grade": "surface",
                                         "geometry_source": src, "locked": 1, "geometry_wkt": geo.to_wkt(g)})
        summary.update(kept=1, reason="rail" if cls != BUS else ("brt" if mode == "brt" else "frequent bus"))
    out["stations"] = sorted(stations.values(), key=lambda s: s["station_id"])
    info.update(lines=len(out["lines"]), stations=len(out["stations"]), routes_considered=len(out["routes"]))
    return out, info


COLUMNS = {
    "lines": ["line_id", "name", "mode", "status", "color", "headway_min", "notes"],
    "stations": ["station_id", "name", "lat", "lon"],
    "line_stops": ["line_id", "seq", "station_id", "year_opens"],
    "line_segments": ["line_id", "seq", "year_opens", "grade", "geometry_source", "locked", "geometry_wkt"],
    "routes": ["feed", "route_id", "short_name", "long_name", "route_type", "class", "trips_on_date",
               "am_trips_busier_dir", "headway_min", "headway_basis", "midday_headway_min", "mode", "kept", "reason"],
}


def merge(results):
    """Combine per-feed outputs (station ids are already prefixed by feed tag)."""
    out = {k: [] for k in COLUMNS}
    seen = set()
    for tables in results:
        for k in COLUMNS:
            for r in tables[k]:
                if k == "stations":
                    if r["station_id"] in seen:
                        continue
                    seen.add(r["station_id"])
                out[k].append(r)
    return out


def write_tables(tables, folder):
    os.makedirs(folder, exist_ok=True)
    counts = {}
    for k, cols in COLUMNS.items():
        with open(os.path.join(folder, f"{k}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(tables[k])
        counts[f"{k}.csv"] = len(tables[k])
    return counts
