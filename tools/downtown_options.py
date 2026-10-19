"""Build the downtown Fort Worth alignment options as scenarios.

    python tools/downtown_options.py

Today every north-south line zigzags through downtown (Courthouse -> Sundance
Square -> east to Central Station -> back west to Convention Center -> south to
T&P), with 67-84 degree turns between stations ~430 m apart. No train can do that.
Each option below re-sequences the downtown stops so the trunks run straight,
then the curve fitter (dfwt/align.py) checks that the result is buildable.

  downtown_main   One north-south trunk straight down Main St (Courthouse, Sundance
                  Square, Convention Center, T&P). Blue becomes an east-west line
                  through Central Station and Sundance Square. Teal turns west at
                  Courthouse. Sundance Square is the big interchange.
  downtown_jones  The north-south trunk swings east under Jones St through Central
                  Station (Courthouse, Central Station, T&P), so the TRE/TEXRail
                  hub is on every line. Blue runs east-west through Central and
                  Sundance Square. Convention Center is dropped (430 m from Central).
  downtown_split  Two parallel north-south trunks: Orange/Pink straight down Main
                  St, Purple from Central Station down Jones St to T&P. Blue
                  east-west through Central and Sundance Square.

Each writes scenarios/<name>/ (line_stops, line_segments, stages) with only the
affected lines changed; new downtown links are drawn station to station in tunnel
and then fitted.
"""
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import align, config, geo, staging  # noqa: E402
from dfwt.network import Network  # noqa: E402

ST = {"PIS": "S007", "TB": "S008", "CH": "S009", "SS": "S010", "TCC": "S016", "CS": "S011",
      "BP": "S036", "CC": "S013", "TP": "S012", "SM": "S014"}

OPTIONS = {
    "downtown_main": {
        "F03": ("PIS", "SM", ["PIS", "CH", "SS", "CC", "TP", "SM"]),
        "F04": ("PIS", "SM", ["PIS", "CH", "SS", "CC", "TP", "SM"]),
        "F07": ("CS", "TP", ["SS", "CC", "TP"]),
        "F02": ("BP", "CC", ["BP", "CS", "SS", "TCC"]),
        "F01": ("TB", "TCC", ["TB", "CH", "TCC"]),
    },
    "downtown_jones": {
        "F03": ("PIS", "SM", ["PIS", "CH", "CS", "TP", "SM"]),
        "F04": ("PIS", "SM", ["PIS", "CH", "CS", "TP", "SM"]),
        "F07": ("CS", "TP", ["CS", "TP"]),
        "F02": ("BP", "CC", ["BP", "CS", "SS", "TCC"]),
        "F01": ("TB", "TCC", ["TB", "CH", "TCC"]),
    },
    "downtown_split": {
        "F03": ("PIS", "SM", ["PIS", "CH", "SS", "CC", "TP", "SM"]),
        "F04": ("PIS", "SM", ["PIS", "CH", "SS", "CC", "TP", "SM"]),
        "F07": ("CS", "TP", ["CS", "TP"]),
        "F02": ("BP", "CC", ["BP", "CS", "SS", "TCC"]),
        "F01": ("TB", "TCC", ["TB", "CH", "TCC"]),
    },
}
# split: Purple gets its own Jones St tunnel (a distinct track key from Orange's Main St pair)
OWN_TUNNEL = {"downtown_split": {"F07"}}


def resequence(tables, lid, a_key, b_key, new_keys, own_tunnel):
    """Replace the stops of line `lid` from a_key through the next b_key with new_keys."""
    stops = sorted([r for r in tables["line_stops.csv"] if r["line_id"] == lid], key=lambda r: int(r["seq"]))
    segs = sorted([r for r in tables["line_segments.csv"] if r["line_id"] == lid], key=lambda r: int(r["seq"]))
    ids = [r["station_id"] for r in stops]
    ia = ids.index(ST[a_key])
    ib = ids.index(ST[b_key], ia)
    new_ids = [ST[k] for k in new_keys]
    old_pairs = {}
    for i in range(ia, ib):
        old_pairs[frozenset((ids[i], ids[i + 1]))] = segs[i]
    stop_year = {r["station_id"]: r["year_opens"] for r in stops}
    region_year = min(int(segs[i]["year_opens"]) for i in range(max(ia - 1, 0), min(ib + 1, len(segs))))
    st = {r["station_id"]: r for r in tables["stations.csv"]}
    out_stops = stops[:ia] + [{"line_id": lid, "station_id": s, "year_opens": stop_year.get(s, str(region_year))}
                              for s in new_ids] + stops[ib + 1:]
    mid = []
    for a, b in zip(new_ids, new_ids[1:]):
        old = old_pairs.get(frozenset((a, b)))
        if old and not own_tunnel:
            pts = geo.parse_wkt(old["geometry_wkt"])
            if geo.hav_km(pts[0][1], pts[0][0], float(st[a]["lat"]), float(st[a]["lon"])) > \
                    geo.hav_km(pts[-1][1], pts[-1][0], float(st[a]["lat"]), float(st[a]["lon"])):
                pts = pts[::-1]
            mid.append({"line_id": lid, "year_opens": old["year_opens"], "grade": old["grade"],
                        "geometry_source": "downtown option", "locked": "", "geometry_wkt": geo.to_wkt(pts)})
        else:
            pa = (float(st[a]["lon"]), float(st[a]["lat"]))
            pb = (float(st[b]["lon"]), float(st[b]["lat"]))
            mid.append({"line_id": lid, "year_opens": str(region_year), "grade": "tunnel",
                        "geometry_source": "downtown option", "locked": "", "geometry_wkt": geo.to_wkt([pa, pb])})
    out_segs = segs[:ia] + mid + segs[ib:]
    for i, r in enumerate(out_stops):
        r["seq"] = str(i + 1)
    for i, r in enumerate(out_segs):
        r["seq"] = str(i + 1)
    tables["line_stops.csv"] = [r for r in tables["line_stops.csv"] if r["line_id"] != lid] + out_stops
    tables["line_segments.csv"] = [r for r in tables["line_segments.csv"] if r["line_id"] != lid] + out_segs


def fit_downtown(tables, lids, cfg):
    """Fit the changed lines and report radius/deviation flags inside the core."""
    net = Network.from_raw({k: v for k, v in tables.items()}, [], cfg, "option")
    m = align.params(cfg, "metro")
    report = {}
    for lid in lids:
        ln = net.lines[lid]
        pts, ends = [], [0]
        for s in ln.segments:
            pts += s.pts if not pts else s.pts[1:]
            ends.append(len(pts) - 1)
        st = [(net.stations[s].lon, net.stations[s].lat) for s in ln.stop_ids]
        segs, rep = align.fit_line(pts, ends, [s.grade for s in ln.segments], st, m)
        core = {ST[k] for k in ST}
        bad = [ln.stop_ids[k] for k in rep["flag_where"] if ln.stop_ids[k] in core]
        report[lid] = dict(min_radius=rep["min_radius_m"], core_flags=sorted({net.stations[s].name for s in bad}))
        for r, p in zip(sorted([r for r in tables["line_segments.csv"] if r["line_id"] == lid], key=lambda r: int(r["seq"])), segs):
            r["geometry_wkt"] = geo.to_wkt(p)
            r["geometry_source"] = "fitted"
    return report


def main():
    cfg = config.load()
    for name, spec in OPTIONS.items():
        tables, _ = Network.read_tables()
        tables = {k: [dict(r) for r in v] for k, v in tables.items()}
        for lid, (a, b, keys) in spec.items():
            resequence(tables, lid, a, b, keys, lid in OWN_TUNNEL.get(name, set()))
        # stages: re-derive the changed lines' stages from their (unchanged) years
        changed = set(spec)
        rows = [r for r in tables["stages.csv"] if r["line_id"] not in changed]
        sub = {k: [r for r in v if k in ("stations.csv",) or r.get("line_id") in changed] for k, v in tables.items()
               if k in ("stations.csv", "line_stops.csv", "line_segments.csv")}
        new_rows = staging.infer_stages(sub)
        for r in new_rows:
            if r["line_id"] == "F03" and r["stage"] == 1:
                r["locked"], r["note"] = "1", "Stockyards/Panther Island leg pinned to 2035 by the owner"
        tables["stages.csv"] = sorted(rows + new_rows, key=lambda r: (r["line_id"], int(r["stage"])))
        rep = fit_downtown(tables, sorted(changed), cfg)
        folder = config.path("scenarios", name)
        os.makedirs(folder, exist_ok=True)
        for t, fields in (("line_stops.csv", ["line_id", "seq", "station_id", "year_opens"]),
                          ("line_segments.csv", ["line_id", "seq", "year_opens", "grade", "geometry_source", "locked", "geometry_wkt"]),
                          ("stages.csv", staging.STAGE_COLS)):
            with open(os.path.join(folder, t), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
                w.writeheader()
                w.writerows(sorted(tables[t], key=lambda r: (r["line_id"], int(r.get("seq") or r.get("stage")))))
        print(name, {k: (round(v["min_radius"]), v["core_flags"]) for k, v in rep.items()})


if __name__ == "__main__":
    main()
