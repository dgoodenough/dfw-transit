"""metro/ input parsers on tiny hand-written fixtures (no network)."""
import csv
import datetime as dt
import gzip
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import geo  # noqa: E402
from metro import census, fetch, gtfs, lodes, mobilitydb, net  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.strip() + "\n")
    return path


def dbf_bytes(fields, rows):
    """A dBASE III file: fields [(name, length)], all character fields."""
    hlen = 32 + 32 * len(fields) + 1
    rlen = 1 + sum(n for _, n in fields)
    out = bytearray(struct.pack("<BBBBIHH20x", 3, 26, 1, 1, len(rows), hlen, rlen))
    for name, n in fields:
        out += name.encode().ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([n, 0]) + b"\0" * 14
    out += b"\r"
    for r in rows:
        out += b" " + b"".join(str(r[name]).encode().ljust(n)[:n] for name, n in fields)
    out += b"\x1a"
    return bytes(out)


class CensusTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_cenpop_filters_counties_and_builds_geoids(self):
        p = write(os.path.join(self.d, "cp.txt"), """
﻿STATEFP,COUNTYFP,TRACTCE,BLKGRPCE,POPULATION,LATITUDE,LONGITUDE
48,201,100000,1,1500,+29.760000,-095.370000
48,201,100000,2,0,+29.761000,-095.371000
48,113,000100,1,900,+32.780000,-096.800000
""")
        z = census.parse_cenpop(p, {"48201"})
        self.assertEqual(sorted(z), ["482011000001", "482011000002"])
        self.assertEqual(z["482011000001"]["pop"], 1500)
        self.assertAlmostEqual(z["482011000001"]["lon"], -95.37)
        self.assertEqual(z["482011000002"]["county_fips"], "48201")
        self.assertEqual(len(census.parse_cenpop(p)), 3)

    def test_tiger_dbf_land_area(self):
        fields = [("GEOID", 12), ("ALAND", 14), ("AWATER", 14), ("INTPTLAT", 11), ("INTPTLON", 12)]
        rows = [{"GEOID": "482011000001", "ALAND": 2500000, "AWATER": 0, "INTPTLAT": "+29.7600000", "INTPTLON": "-095.3700000"},
                {"GEOID": "481130001001", "ALAND": 100, "AWATER": 5, "INTPTLAT": "+32.7800000", "INTPTLON": "-096.8000000"}]
        zp = os.path.join(self.d, "tl_2020_48_bg.zip")
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("tl_2020_48_bg.dbf", dbf_bytes(fields, rows))
            z.writestr("tl_2020_48_bg.shp", b"not read")
        a = census.parse_tiger_bg(zp, {"48201"})
        self.assertEqual(list(a), ["482011000001"])
        self.assertEqual(a["482011000001"]["aland_m2"], 2500000.0)
        self.assertAlmostEqual(a["482011000001"]["intpt_lon"], -95.37)

    def test_cbsa_delineation_xlsx(self):
        header = ["CBSA Code", "Metropolitan Division Code", "CSA Code", "CBSA Title", "County/County Equivalent",
                  "FIPS State Code", "FIPS County Code"]
        data = [["List 1. CORE BASED STATISTICAL AREAS"], [], header,
                ["26420", "", "288", "Houston-Pasadena-The Woodlands, TX", "Harris County", "48", "201"],
                ["26420", "", "288", "Houston-Pasadena-The Woodlands, TX", "Austin County", "48", "015"],
                ["19100", "", "206", "Dallas-Fort Worth-Arlington, TX", "Dallas County", "48", "113"]]
        strings, rows_xml = [], []
        for i, row in enumerate(data, 1):
            cells = []
            for j, v in enumerate(row):
                strings.append(v)
                cells.append(f'<c r="{chr(65 + j)}{i}" t="s"><v>{len(strings) - 1}</v></c>')
            rows_xml.append(f'<row r="{i}">{"".join(cells)}</row>')
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        p = os.path.join(self.d, "list1.xlsx")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
            z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(rows_xml)}</sheetData></worksheet>")
        got = census.cbsa_counties(p, "26420")
        self.assertEqual(got["cbsa_title"], "Houston-Pasadena-The Woodlands, TX")
        self.assertEqual(got["counties"], {"48201": "Harris County", "48015": "Austin County"})


class LodesTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def gz(self, name, text):
        p = os.path.join(self.d, name)
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
        return p

    def test_wac_to_block_groups(self):
        p = self.gz("tx_wac.csv.gz", """
w_geocode,C000,CA01,createdate
482011000001001,10,1,20240101
482011000001002,5,0,20240101
482011000002000,7,2,20240101
481130001001000,99,0,20240101
""")
        self.assertEqual(lodes.aggregate_wac(p, {"48201"}), {"482011000001": 15, "482011000002": 7})

    def test_od_to_tract_pairs_and_dfwt_columns(self):
        main = self.gz("tx_od_main.csv.gz", """
w_geocode,h_geocode,S000,SA01
482011000001001,482013000001001,3,1
482011000002000,482013000002005,2,0
482011000001001,481130001001000,4,0
""")
        aux = self.gz("tx_od_aux.csv.gz", """
w_geocode,h_geocode,S000,SA01
482011000001001,220010001001000,8,0
""")
        od = lodes.aggregate_od([main, aux], {"48201"})
        self.assertEqual(od, {("48201300000", "48201100000"): 5})
        out = os.path.join(self.d, "od_tracts.csv")
        self.assertEqual(lodes.write_od(od, out), 1)
        with open(out) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows, [{"h_tract": "48201300000", "w_tract": "48201100000", "jobs": "5"}])

    def test_urls(self):
        self.assertTrue(lodes.wac_url("tx", 2022).endswith("LODES8/tx/wac/tx_wac_S000_JT00_2022.csv.gz"))
        self.assertTrue(lodes.od_url("tx", "aux", 2022).endswith("LODES8/tx/od/tx_od_aux_JT00_2022.csv.gz"))


class CatalogTests(unittest.TestCase):
    def row(self, sid, lat=(29.5, 30.3), lon=(-95.8, -95.0), **kw):
        r = {"mdb_source_id": sid, "data_type": "gtfs", "status": "", "redirect.id": "",
             "location.bounding_box.minimum_latitude": lat[0], "location.bounding_box.maximum_latitude": lat[1],
             "location.bounding_box.minimum_longitude": lon[0], "location.bounding_box.maximum_longitude": lon[1],
             "urls.latest": f"https://storage.example/{sid}.zip", "urls.direct_download": f"https://agency.example/{sid}.zip",
             "urls.authentication_type": "0"}
        r.update(kw)
        return r

    def test_select_feeds(self):
        bbox = (-96.6, 28.8, -94.3, 30.6)
        rows = [self.row("1"),
                self.row("2", lat=(25, 49), lon=(-124, -70)),            # national (Amtrak-like)
                self.row("3", status="deprecated"),
                self.row("4", **{"redirect.id": "1"}),
                self.row("5", data_type="gbfs"),
                self.row("6", lat=(32.5, 33.0), lon=(-97.5, -96.5)),     # another metro
                self.row("7", lat=(0, 30.3), lon=(-95.8, 0))]            # broken bbox
        self.assertEqual([r["mdb_source_id"] for r in mobilitydb.select_feeds(rows, bbox)], ["1"])
        self.assertEqual([r["mdb_source_id"] for r in mobilitydb.select_feeds(rows, bbox, exclude=["1"])], [])
        self.assertEqual([r["mdb_source_id"] for r in mobilitydb.select_feeds(rows, bbox, include=["2", "6"])], ["2", "6"])
        self.assertEqual(mobilitydb.feed_urls(rows[0]), ["https://storage.example/1.zip", "https://agency.example/1.zip"])
        self.assertEqual(mobilitydb.feed_urls(self.row("8", **{"urls.authentication_type": "1"})), ["https://storage.example/8.zip"])


# A tiny GTFS feed: a commuter rail line (parent stations, shape with distances), a light
# rail line (shape without distances), a frequent bus, an infrequent bus and a ferry.
FEED = {
    "routes.txt": """
route_id,route_short_name,route_long_name,route_type,route_color
R1,,Northline,2,112233
LR,700,Red Line,0,EF0000
B1,82,Westheimer,3,
B2,99,Rare Route,3,
F1,,Ferry,4,
""",
    "calendar.txt": """
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
WK,1,1,1,1,1,0,0,20250106,20250131
""",
    "calendar_dates.txt": """
service_id,date,exception_type
WK,20250107,2
""",
    "stops.txt": """
stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station
PA,Alpha Station,30.000000,-95.000000,1,
PA1,Alpha Platform 1,30.000100,-95.000100,0,PA
PB,Bravo Station,30.100000,-95.000000,1,
PB1,Bravo Platform 1,30.100100,-95.000100,0,PB
L1,Main & 1st,29.700000,-95.400000,0,
L2,Main & 2nd,29.710000,-95.400000,0,
L3,Main & 3rd,29.720000,-95.400000,0,
L4,Main & 4th,29.730000,-95.400000,0,
L5,Main & 5th,29.740000,-95.400000,0,
L6,Main & 6th,29.750000,-95.400000,0,
L7,Main & 7th,29.760000,-95.400000,0,
B1a,West A,29.740000,-95.500000,0,
B1b,West B,29.740000,-95.490000,0,
""",
    "shapes.txt": """
shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled
SR,30.000000,-95.000000,1,0
SR,30.050000,-95.010000,2,5.7
SR,30.100000,-95.000000,3,11.4
SL,29.700000,-95.400000,1,
SL,29.730000,-95.401000,2,
SL,29.760000,-95.400000,3,
""",
}


def build_feed(folder):
    for name, text in FEED.items():
        write(os.path.join(folder, name), text)
    trips, st = ["route_id,service_id,trip_id,direction_id,shape_id"], ["trip_id,arrival_time,departure_time,stop_id,stop_sequence,shape_dist_traveled"]

    def add(route, tid, d, shape, stops, start, step=120, dists=None):
        trips.append(f"{route},WK,{tid},{d},{shape}")
        for i, s in enumerate(stops):
            t = start + i * step
            hhmmss = f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"
            st.append(f"{tid},{hhmmss},{hhmmss},{s},{i + 1},{dists[i] if dists else ''}")

    for k in range(4):        # commuter rail: 4 inbound AM trips 07:00..08:30 -> 30 min
        add("R1", f"r{k}", 0, "SR", ["PA1", "PB1"], 7 * 3600 + k * 1800, 600, dists=[0, 11.4])
    add("R1", "r9", 1, "SR", ["PB1", "PA1"], 17 * 3600, 600, dists=[0, 11.4])
    for k in range(10):       # light rail: every 12 min, 7 stops 1.1 km apart -> metro
        add("LR", f"l{k}", 0, "SL", ["L1", "L2", "L3", "L4", "L5", "L6", "L7"], 7 * 3600 + k * 720)
    for k in range(12):       # frequent bus: every 10 min
        add("B1", f"b{k}", 1, "", ["B1a", "B1b"], 7 * 3600 + k * 600)
    for k in range(3):        # midday too
        add("B1", f"bm{k}", 1, "", ["B1a", "B1b"], 11 * 3600 + k * 1200)
    for k in range(2):        # infrequent bus: 60 min
        add("B2", f"x{k}", 0, "", ["B1b", "B1a"], 7 * 3600 + k * 3600)
    write(os.path.join(folder, "trips.txt"), "\n".join(trips))
    write(os.path.join(folder, "stop_times.txt"), "\n".join(st))
    return folder


class GtfsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = build_feed(tempfile.mkdtemp())
        cls.tables, cls.info = gtfs.analyze(gtfs.Feed(d), "t", brt_pattern=r"\bBRT\b", existing_year=2025, label="Test")
        cls.lines = {r["line_id"]: r for r in cls.tables["lines"]}
        cls.routes = {r["route_id"]: r for r in cls.tables["routes"]}

    def test_zip_and_folder_read_the_same(self):
        d = build_feed(tempfile.mkdtemp())
        zp = os.path.join(tempfile.mkdtemp(), "feed.zip")
        with zipfile.ZipFile(zp, "w") as z:
            for n in os.listdir(d):
                z.write(os.path.join(d, n), "nested/" + n)
        t, _ = gtfs.analyze(gtfs.Feed(zp), "t", brt_pattern=r"\bBRT\b", existing_year=2025, label="Test")
        self.assertEqual(t["lines"], self.tables["lines"])

    def test_route_classes(self):
        self.assertEqual([gtfs.route_class(t) for t in ("2", "0", "1", "3", "4", "109", "900", "702", "x")],
                         ["rail", "tram", "subway", "bus", None, "rail", "tram", "bus", None])

    def test_typical_weekday_skips_holiday(self):
        # Tue 7 Jan 2025 is removed by calendar_dates; Wed 8 Jan is the first typical Tue-Thu
        self.assertEqual(self.info["service_date"], "2025-01-08")

    def test_kept_routes_modes_and_headways(self):
        self.assertEqual(sorted(self.lines), ["t_700", "t_82", "t_R1"])
        self.assertEqual(self.lines["t_R1"]["mode"], "commuter")
        self.assertEqual(self.lines["t_R1"]["headway_min"], 30.0)
        self.assertEqual(self.lines["t_R1"]["color"], "#112233")
        self.assertEqual(self.lines["t_700"]["mode"], "metro")
        self.assertEqual(self.lines["t_700"]["headway_min"], 12.0)
        self.assertEqual(self.lines["t_82"]["mode"], "bus")
        self.assertEqual(self.lines["t_82"]["headway_min"], 10.0)
        self.assertEqual(self.routes["B1"]["midday_headway_min"], 80.0)
        self.assertTrue(all(r["status"] == "existing" for r in self.tables["lines"]))
        self.assertEqual(self.routes["B2"]["kept"], 0)
        self.assertIn("not frequent", self.routes["B2"]["reason"])
        self.assertEqual(self.routes["F1"]["kept"], 0)

    def test_brt_pattern(self):
        d = build_feed(tempfile.mkdtemp())
        t, _ = gtfs.analyze(gtfs.Feed(d), "t", brt_pattern="Rare", existing_year=2025)
        modes = {r["line_id"]: r["mode"] for r in t["lines"]}
        self.assertEqual(modes["t_99"], "brt")

    def test_stations_collapse_to_parents(self):
        stops = [r for r in self.tables["line_stops"] if r["line_id"] == "t_R1"]
        self.assertEqual([r["station_id"] for r in stops], ["t_PA", "t_PB"])
        names = {r["station_id"]: r["name"] for r in self.tables["stations"]}
        self.assertEqual(names["t_PA"], "Alpha Station")
        self.assertTrue(all(r["year_opens"] == 2025 for r in stops))

    def test_segments_follow_shapes_and_meet_stations(self):
        st = {r["station_id"]: r for r in self.tables["stations"]}
        segs = [r for r in self.tables["line_segments"] if r["line_id"] == "t_700"]
        stops = [r["station_id"] for r in self.tables["line_stops"] if r["line_id"] == "t_700"]
        self.assertEqual(len(segs), len(stops) - 1)
        self.assertTrue(all(s["geometry_source"] == "gtfs_shape" and s["locked"] == 1 for s in segs))
        for s in segs:
            pts = geo.parse_wkt(s["geometry_wkt"])
            a, b = st[stops[s["seq"] - 1]], st[stops[s["seq"]]]
            self.assertLess(geo.hav_km(float(a["lat"]), float(a["lon"]), pts[0][1], pts[0][0]), 0.15)
            self.assertLess(geo.hav_km(float(b["lat"]), float(b["lon"]), pts[-1][1], pts[-1][0]), 0.15)
        # the 4th segment crosses the shape's bend at (29.73, -95.401)
        self.assertIn((-95.401, 29.73), geo.parse_wkt(segs[2]["geometry_wkt"]) + geo.parse_wkt(segs[3]["geometry_wkt"]))
        rail = [r for r in self.tables["line_segments"] if r["line_id"] == "t_R1"]
        self.assertEqual(rail[0]["geometry_source"], "gtfs_shape_dist")
        self.assertEqual(len(geo.parse_wkt(rail[0]["geometry_wkt"])), 3)
        bus = [r for r in self.tables["line_segments"] if r["line_id"] == "t_82"]
        self.assertEqual(bus[0]["geometry_source"], "straight")

    def test_write_tables_matches_dfwt_columns(self):
        out = tempfile.mkdtemp()
        counts = gtfs.write_tables(gtfs.merge([self.tables]), out)
        self.assertEqual(counts["lines.csv"], 3)
        from dfwt import network
        for t in network.TABLES:
            with open(os.path.join(out, t)) as f:
                self.assertIn("line_id" if t != "stations.csv" else "station_id", next(csv.reader(f)))

    def test_projection_and_cut(self):
        shape = [(0.0, 0.0), (0.01, 0.0), (0.01, 0.01)]
        m = gtfs.project_stops(shape, [(0.0, 0.0), (0.0101, 0.005), (0.01, 0.01)])
        M = gtfs.cumulative(shape)
        self.assertAlmostEqual(m[1], M[1] + (M[2] - M[1]) / 2, places=3)
        pts = gtfs.cut(shape, M, m[0], m[1])
        self.assertEqual(pts[1], (0.01, 0.0))
        self.assertAlmostEqual(pts[-1][1], 0.005, places=4)

    def test_parse_time_past_midnight(self):
        self.assertEqual(gtfs.parse_time("25:10:05"), 25 * 3600 + 605)
        self.assertIsNone(gtfs.parse_time(""))

    def test_pick_weekday_uses_most_common_count(self):
        cal = gtfs.Calendar([{"service_id": "A", "start_date": "20250106", "end_date": "20250131",
                              "tuesday": "1", "wednesday": "1", "thursday": "1"},
                             {"service_id": "X", "start_date": "20250107", "end_date": "20250107", "tuesday": "1"}], [])
        d, act, n = gtfs.pick_weekday(cal, {"A": 100, "X": 50})
        self.assertEqual((d, n), (dt.date(2025, 1, 8), 100))
        d, _, _ = gtfs.pick_weekday(cal, {"A": 100}, window=(dt.date(2025, 1, 20), dt.date(2025, 1, 31)))
        self.assertEqual(d, dt.date(2025, 1, 21))


class FetchPlumbingTests(unittest.TestCase):
    def test_registry_is_data(self):
        reg = fetch.registry()
        h = reg["houston"]
        self.assertEqual(h["cbsa"], "26420")
        self.assertEqual(len(h["county_fips"]), 9)
        self.assertTrue(all(len(c) == 5 and c[:2] in h["state_fips"] for c in h["county_fips"]))

    def test_cached_file_needs_no_network(self):
        d = tempfile.mkdtemp()
        p = write(os.path.join(d, "x_2022.csv.gz"), "cached")
        u, got = net.first_available(["https://blocked.invalid/x_2023.csv.gz", "https://blocked.invalid/x_2022.csv.gz"],
                                     lambda u: os.path.join(d, os.path.basename(u)))
        self.assertEqual(got, p)
        self.assertTrue(u.endswith("2022.csv.gz"))

    def test_fetch_error_meta(self):
        e = net.FetchError("https://lehd.ces.census.gov/data/x.gz", "blocked", "Tunnel connection failed: 403 Forbidden")
        m = e.as_meta()
        self.assertEqual((m["status"], m["host"]), ("blocked", "lehd.ces.census.gov"))

    def test_missing_report(self):
        meta = {"sources": {"lodes_wac": {"status": "blocked", "files": [{"host": "lehd.ces.census.gov"}]},
                            "lodes_od": {"status": "blocked", "files": [{"host": "lehd.ces.census.gov"}]},
                            "tiger2020_bg": {"status": "ok"},
                            "gtfs": {"status": "ok", "feeds": []},
                            "cbsa_delineation": {"registry_matches": True}},
                "outputs": {"zones.csv": {"empty_columns": ["jobs"]}, "osm/roads.parquet": {}, "osm/rail.parquet": {}}}
        items = {m["item"]: m["why"] for m in fetch.missing(meta)}
        self.assertEqual(set(items), {"zones.csv jobs", "od_tracts.csv"})
        self.assertIn("lehd.ces.census.gov", items["zones.csv jobs"])

    def test_bbox(self):
        self.assertEqual(fetch.bbox_of([{"lon": "-95", "lat": "29"}, {"lon": "-94", "lat": "30"}], 0.1),
                         [-95.1, 28.9, -93.9, 30.1])


if __name__ == "__main__":
    unittest.main()
