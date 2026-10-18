"""One-time converter: archive/v1/db (the v1 source of truth) -> network/ (v2 model).

What changes in the data model, and why:

* v1 stored derived values next to source values (station `act`, `lines`,
  `n_lines`, `color`, `year_opens`), so a hand edit in one place silently
  disagreed with another. v2 keeps only source facts; everything else is
  derived at build time.
* v1 had two segment conventions (FW: one row per shared track listing
  `;`-separated lines and years; extra: one row per line). v2 has exactly one:
  a line is an ordered list of stops (`line_stops`) plus one geometry per
  consecutive stop pair (`line_segments`). Shared track is detected, not encoded.
* v1 station years and per-line track years disagreed on 238 of 642 links
  (e.g. Red reached Waterside in 2070 but the station said 2035 because Orange
  got there first). v2 stores the year a *line* serves a *stop*:
  max(station year, first year that line's track reaches it). A stop that opens
  later than the track around it is an infill station; trains run through it
  until then.

Run once: python tools/migrate_v1.py
"""
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config, geo  # noqa: E402

V1 = config.path("archive", "v1", "db")
OUT = config.path("network")

# Real-world 2025 peak headways for the lines that exist today.
EXISTING_HEADWAY = {"TRE": 30, "Texrail": 30, "A Train": 30, "Cotton Belt": 30,
                    "Orange Line": 15, "Green Line": 15, "Red Line": 15, "Blue Line": 15}
# The extra "Silver" is too light on a light basemap.
COLOR_FIX = {"#BDBDBD": "#6b7785"}


def read(name):
    with open(os.path.join(V1, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(name, fields, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    cfg = config.load()
    stations = {r["station_id"]: r for r in read("stations.csv")}
    lines = read("lines.csv")
    sl = read("station_lines.csv")
    segs = read("segments.csv")

    # per (line name, unordered station pair) -> (year, geometry, from_id)
    seg_by = {}
    for g in segs:
        names, years = g["line"].split(";"), g["year_opens"].split(";")
        for i, n in enumerate(names):
            y = int(years[i] if i < len(years) else years[-1])
            seg_by[(n, frozenset((g["from_id"], g["to_id"])))] = (y, g["geometry_wkt"], g["from_id"])

    by_line = collections.defaultdict(list)
    for r in sl:
        by_line[r["line_id"]].append(r)

    out_lines, out_stops, out_segs = [], [], []
    for ln in lines:
        lid, name = ln["line_id"], ln["name"]
        stops = sorted(by_line[lid], key=lambda r: int(r["seq"]))
        seg_years = []
        for i, (a, b) in enumerate(zip(stops, stops[1:])):
            y, wkt, from_id = seg_by[(name, frozenset((a["station_id"], b["station_id"])))]
            pts = geo.parse_wkt(wkt)
            if from_id != a["station_id"]:
                pts = pts[::-1]
            seg_years.append(y)
            out_segs.append({"line_id": lid, "seq": i + 1, "year_opens": y,
                             "grade": grade_for(cfg, ln["mode"], y, pts),
                             "geometry_wkt": geo.to_wkt(pts)})
        for i, s in enumerate(stops):
            adj = [seg_years[j] for j in (i - 1, i) if 0 <= j < len(seg_years)]
            st_year = int(stations[s["station_id"]]["year_opens"])
            out_stops.append({"line_id": lid, "seq": i + 1, "station_id": s["station_id"],
                              "year_opens": max(st_year, min(adj)) if adj else st_year})
        status = "existing" if all(y <= cfg["existing_year"] for y in seg_years) else "proposed"
        out_lines.append({"line_id": lid, "name": name, "mode": ln["mode"], "status": status,
                          "color": COLOR_FIX.get(ln["color"], ln["color"]),
                          "headway_min": EXISTING_HEADWAY.get(name, "") if status == "existing" else "",
                          "notes": ""})

    out_stations = [{"station_id": s["station_id"], "name": s["name"],
                     "lat": f"{float(s['lat']):.6f}", "lon": f"{float(s['lon']):.6f}"}
                    for s in stations.values()]

    os.makedirs(OUT, exist_ok=True)
    write("lines.csv", ["line_id", "name", "mode", "status", "color", "headway_min", "notes"], out_lines)
    write("stations.csv", ["station_id", "name", "lat", "lon"], out_stations)
    write("line_stops.csv", ["line_id", "seq", "station_id", "year_opens"], out_stops)
    write("line_segments.csv", ["line_id", "seq", "year_opens", "grade", "geometry_wkt"], out_segs)
    print(f"migrated {len(out_lines)} lines, {len(out_stations)} stations, "
          f"{len(out_stops)} line stops, {len(out_segs)} segments -> network/")


def grade_for(cfg, mode, year, pts):
    """Proposed metro through a downtown core is costed as tunnel; everything else surface."""
    if mode != "metro" or year <= cfg["existing_year"]:
        return "surface"
    for core in cfg["cores"].values():
        if not isinstance(core, dict):
            continue
        mid = pts[len(pts) // 2]
        if geo.hav_km(mid[1], mid[0], core["lat"], core["lon"]) <= core["radius_km"]:
            return "tunnel"
    return "surface"


if __name__ == "__main__":
    main()
