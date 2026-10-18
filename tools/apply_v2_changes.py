"""Apply the v2 plan changes (panel review steps A1-A9) to network/.

Run once, on the tables produced by tools/migrate_v1.py:
    python tools/apply_v2_changes.py
Every change is listed in network/CHANGELOG.md with the step it implements.
After this, network/ is hand-edited directly; this script is kept as the record
of how v2 was derived from v1.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config, geo  # noqa: E402

NET = config.path("network")
LOG = []


def read(name):
    p = os.path.join(NET, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(name, fields, rows):
    with open(os.path.join(NET, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def log(step, msg):
    LOG.append((step, msg))


def main():
    lines = {r["line_id"]: r for r in read("lines.csv")}
    stations = {r["station_id"]: r for r in read("stations.csv")}
    stops = read("line_stops.csv")
    segs = read("line_segments.csv")
    if "E38" in lines:
        sys.exit("v2 changes already applied (E38 exists); start from tools/migrate_v1.py")
    service, transfers = [], []

    def line_rows(lid, table):
        return sorted((r for r in table if r["line_id"] == lid), key=lambda r: int(r["seq"]))

    def set_years(lid, fn):
        for r in stops + segs:
            if r["line_id"] == lid:
                r["year_opens"] = str(fn(int(r["year_opens"]), r))

    def move_line(lid, first_year):
        ys = [int(r["year_opens"]) for r in stops + segs if r["line_id"] == lid]
        d = first_year - min(ys)
        set_years(lid, lambda y, r: y + d)
        return d

    def add_station(sid, name, lat, lon):
        stations[sid] = {"station_id": sid, "name": name, "lat": f"{lat:.6f}", "lon": f"{lon:.6f}"}

    def st_pt(sid):
        s = stations[sid]
        return (float(s["lon"]), float(s["lat"]))

    # ---------- A9: names riders recognize ----------
    renames = {
        "E20": "Silver Line",            # DART's own name for the Cotton Belt line (opened 2025)
        "F05": "Berry Line",             # FW core 'Silver' runs along Berry St
        "E19": "I-20 Crosstown",         # extra 'Silver': Fort Worth - Arlington - Duncanville
        "E18": "Las Colinas-Mesquite Line",
        "E22": "I-30 Line",              # was 'Blue Ctd'
        "E23": "SH-360 Line",            # was 'Purple line' (Mansfield - Arlington - Euless)
        "E01": "White Settlement BRT",
        "E02": "Riverside-Forest Hill BRT",
        "E04": "Jacksboro BRT",
        "E25": "McKinney Line",          # was 'Collin Commuter'
        "E09": "TEXRail", "E11": "A-train",
        "E16": "DNT West", "E17": "DNT East",
    }
    for lid, new in renames.items():
        log("A9", f"line {lid} '{lines[lid]['name']}' renamed '{new}'")
        lines[lid]["name"] = new
    for lid, ln in lines.items():
        if ln["name"].endswith(" (ROW)"):
            ln["name"] = ln["name"][:-6]
    log("A9", "dropped the '(ROW)' suffix from commuter line names")
    st_renames = {
        "X208": "Turtle Creek", "X234": "Turtle Creek", "X203": "Walnut Hill / Marsh",
        "X232": "Preston Center", "X249": "Irving West", "X221": "Tollway / Park Blvd",
        "X223": "Tollway / Frankford", "X215": "Frisco Main St", "X218": "Riders Field",
        "X504": "Riders Field", "X219": "Stonebriar", "X505": "Stonebriar",
        "X220": "Legacy West", "X506": "Legacy Town Center", "X507": "Preston / Legacy",
        "X508": "Coit / Legacy", "X509": "Independence / Legacy", "X510": "Custer / Legacy",
        "X044": "Hulen / Sycamore School", "X043": "Wedgwood", "X032": "Henderson St",
        "X002": "Jacksboro / Northside", "X006": "Ridgmar North", "X437": "North Arlington",
        "X428": "Mansfield North", "X298": "Camp Wisdom", "X297": "Red Bird",
        "X444": "DFW Airport South", "X410": "North Oak Cliff", "X411": "West Dallas",
        "X412": "Singleton / Sylvan",
    }
    for sid, new in st_renames.items():
        log("A9", f"station {sid} '{stations[sid]['name']}' renamed '{new}' (approximate cross-street/neighborhood)")
        stations[sid]["name"] = new

    # ---------- A1: run today's rail more often from 2030 ----------
    for lid, ln in lines.items():
        if ln["status"] == "existing":
            hw = 15 if ln["mode"] == "commuter" else 10
            service.append({"line_id": lid, "from_year": 2030, "headway_min": hw,
                            "note": "A1 frequency upgrade on existing track"})
            log("A1", f"{ln['name']}: every {ln['headway_min']} -> {hw} min from 2030")

    # ---------- A2: best BRT corridors by 2030 ----------
    for lid in ("E28", "E27", "E04", "E29"):
        d = move_line(lid, 2030)
        log("A2", f"{lines[lid]['name']}: opens 2030 ({d:+d} years)")

    # ---------- A3: Fort Worth Phase One staged around the Central-Medical District-TCU core ----------
    orange = line_rows("F03", stops)
    names = [stations[r["station_id"]]["name"] for r in orange]
    mi = names.index("Medical City - Baylor")
    for r in orange:
        if int(r["seq"]) - 1 > mi:
            r["year_opens"] = str(max(int(r["year_opens"]), 2045))
    for r in line_rows("F03", segs):
        if int(r["seq"]) - 1 >= mi:
            r["year_opens"] = str(max(int(r["year_opens"]), 2045))
    log("A3", "FW Orange: southwest tail Medical City -> Altamesa deferred to 2045 "
              "(saves $2.1B of 2035-40 spending for ~1.5 competitive commutes per $1M); "
              "the Stockyards/Panther Island north leg stays in 2035 for tourism and TOD demand LODES undercounts")

    # ---------- A4: keep every phase connected ----------
    # Midlothian -> Westmoreland (DART Red/Blue), ~1.1 km past Oak Cliff
    mid = line_rows("E37", stops)
    last = mid[-1]
    y = last["year_opens"]
    stops.append({"line_id": "E37", "seq": str(len(mid) + 1), "station_id": "X174", "year_opens": y})
    a, b = st_pt(last["station_id"]), st_pt("X174")
    segs.append({"line_id": "E37", "seq": str(len(mid)), "year_opens": y, "grade": "surface",
                 "geometry_wkt": geo.to_wkt([a, (a[0] + 0.001, (a[1] + b[1]) / 2), b])})
    log("A4", "Midlothian Line extended Oak Cliff -> Westmoreland (DART) so it is not an island from 2045 to 2065 "
              "(sketch geometry, ~1.1 km)")
    # McKinney Line south to Parker Road (DART Red/Orange) along the DART-owned corridor
    mck = line_rows("E25", stops)
    for r in stops + segs:
        if r["line_id"] == "E25":
            r["seq"] = str(int(r["seq"]) + 1)
    first = mck[0]
    stops.append({"line_id": "E25", "seq": "1", "station_id": "X125", "year_opens": first["year_opens"]})
    a, b = st_pt("X125"), st_pt(first["station_id"])
    segs.append({"line_id": "E25", "seq": "1", "year_opens": first["year_opens"], "grade": "surface",
                 "geometry_wkt": geo.to_wkt([a, (a[0] - 0.002, (a[1] + b[1]) / 2), b])})
    d = move_line("E25", 2035)
    log("A4", f"McKinney Line extended Watters Creek -> Parker Road (DART) and moved to 2035 ({d:+d} years); "
              "it connected to nothing until 2050 (sketch geometry on the DART-owned rail corridor)")

    # Jacksboro BRT: route via Fort Worth T&P so it meets TEXRail/TRE on opening day
    jb = line_rows("E04", stops)
    for r in stops + segs:
        if r["line_id"] == "E04" and int(r["seq"]) >= 2:
            r["seq"] = str(int(r["seq"]) + 1)
    stops.append({"line_id": "E04", "seq": "2", "station_id": "X072", "year_opens": "2030"})
    seg1 = next(r for r in segs if r["line_id"] == "E04" and r["seq"] == "1")
    seg1["geometry_wkt"] = geo.to_wkt([st_pt(jb[0]["station_id"]), st_pt("X072")])
    segs.append({"line_id": "E04", "seq": "2", "year_opens": "2030", "grade": "surface",
                 "geometry_wkt": geo.to_wkt([st_pt("X072"), st_pt(jb[1]["station_id"])])})
    log("A4", "Jacksboro BRT routed Magnolia W -> Fort Worth T&P -> Henderson St so it connects to TEXRail/TRE "
              "when it opens in 2030 (sketch geometry)")
    d = move_line("E02", 2045)
    log("A4", f"Riverside-Forest Hill BRT moved to 2045 ({d:+d} years): before then it touched no other open line")

    # ---------- A6: Collin County crosstown on SH-121 ----------
    new = [("X601", "McKinney South", 33.1600, -96.6550), ("X602", "Craig Ranch", 33.1330, -96.7100),
           ("X603", "Custer / SH-121", 33.1180, -96.7400), ("X604", "Coit / SH-121", 33.1110, -96.7700),
           ("X605", "Preston / SH-121", 33.1050, -96.7990)]
    for sid, n, la, lo in new:
        add_station(sid, n, la, lo)
    seq_ids = ["X500"] + [x[0] for x in new] + ["X218", "X219", "X220"]
    lines["E38"] = {"line_id": "E38", "name": "SH-121 BRT", "mode": "brt", "status": "proposed",
                    "color": "#00838f", "headway_min": "",
                    "notes": "A6: McKinney-Frisco-Legacy crosstown. Sketch alignment on SH-121 frontage roads; needs a real road-ROW routing pass."}
    for i, sid in enumerate(seq_ids):
        stops.append({"line_id": "E38", "seq": str(i + 1), "station_id": sid, "year_opens": "2040"})
        if i:
            segs.append({"line_id": "E38", "seq": str(i), "year_opens": "2040", "grade": "surface",
                         "geometry_wkt": geo.to_wkt([st_pt(seq_ids[i - 1]), st_pt(sid)])})
    log("A6", "new SH-121 BRT (E38) McKinney -> Craig Ranch -> Frisco/Riders Field -> Stonebriar -> Legacy West, 2040 "
              "(sketch alignment)")

    # ---------- A7: cut duplicates, hold the weakest outer legs ----------
    for lid, why in (("E06", "repeats the Alvarado line's Edgecliff-Crowley corridor (~0 marginal value)"),
                     ("E03", "Woodhaven direct adds no measurable value next to Teal and the Crosstown Loop")):
        log("A7", f"dropped {lines[lid]['name']} ({lid}): {why}")
        del lines[lid]
        stops[:] = [r for r in stops if r["line_id"] != lid]
        segs[:] = [r for r in segs if r["line_id"] != lid]
    for lid in ("E35", "E01"):
        d = move_line(lid, 2070)
        lines[lid]["notes"] = "A7: long-range reserve; lowest value per $ in the v1 plan"
        log("A7", f"{lines[lid]['name']} held as 2070 long-range reserve ({d:+d} years)")
    lines["E31"]["notes"] = "A7: long-range reserve (already 2070); consider intercity bus first"

    # ---------- A5: same-place stations become real transfers ----------
    by_station = {}
    for r in stops:
        by_station.setdefault(r["station_id"], set()).add(r["line_id"])
    ids = sorted(by_station)
    auto = config.load()["transfer"]["walk_radius_m"] / 1000
    n_tr = 0
    for i, a in enumerate(ids):
        A = stations[a]
        for b in ids[i + 1:]:
            B = stations[b]
            if abs(float(A["lat"]) - float(B["lat"])) > 0.008 or by_station[a] & by_station[b]:
                continue
            d = geo.hav_km(float(A["lat"]), float(A["lon"]), float(B["lat"]), float(B["lon"]))
            if auto < d <= 0.8:
                transfers.append({"station_a": a, "station_b": b, "walk_min": "",
                                  "note": f"A5: {A['name']} <-> {B['name']}, {d * 1000:.0f} m"})
                n_tr += 1
    log("A5", f"{n_tr} explicit transfer links between stations 400-800 m apart on different lines "
              "(walk time computed from distance; previously no transfer existed)")

    write("lines.csv", ["line_id", "name", "mode", "status", "color", "headway_min", "notes"], list(lines.values()))
    write("stations.csv", ["station_id", "name", "lat", "lon"], list(stations.values()))
    write("line_stops.csv", ["line_id", "seq", "station_id", "year_opens"],
          sorted(stops, key=lambda r: (r["line_id"], int(r["seq"]))))
    write("line_segments.csv", ["line_id", "seq", "year_opens", "grade", "geometry_wkt"],
          sorted(segs, key=lambda r: (r["line_id"], int(r["seq"]))))
    write("service.csv", ["line_id", "from_year", "headway_min", "note"], service)
    write("transfers.csv", ["station_a", "station_b", "walk_min", "note"], transfers)

    with open(os.path.join(NET, "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write("# Network changelog\n\n## v2 (from the panel review)\n\n"
                "Applied by `tools/apply_v2_changes.py` to the migrated v1 tables. "
                "Step IDs match `reports/panel/index.html`. The untouched v1 plan is "
                "kept as `scenarios/v1_baseline/` and in `archive/v1/`.\n\n")
        cur = None
        for step, msg in LOG:
            if step != cur:
                f.write(f"\n### {step}\n\n")
                cur = step
            f.write(f"- {msg}\n")
    print(f"applied {len(LOG)} changes; see network/CHANGELOG.md")


if __name__ == "__main__":
    main()
