"""Station names: real, unique, and the rename mapping fully applied (tools/rename_stations.py)."""
import csv
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("rename_stations", os.path.join(ROOT, "tools", "rename_stations.py"))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

from dfwt import config  # noqa: E402
from dfwt.naming import clean_street, keys  # noqa: E402


class StationNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stations = rs.survey()
        cls.mapping = rs.load_map()

    def test_no_generated_duplicate_or_misspelt_names(self):
        bad = rs.problems(self.stations)
        self.assertEqual(bad[:5], [], f"{len(bad)} name problems; run python tools/rename_stations.py --propose")

    def test_mapping_is_fully_applied(self):
        maps = {}
        for m in self.mapping:
            maps.setdefault(m["old_name"], []).append(m)
        left = [(f, r["station_id"], r["name"]) for p in self.stations for f, r in p["rows"]
                if rs.lookup(maps, r["name"], r["lat"], r["lon"])]
        self.assertEqual(left, [], "run python tools/rename_stations.py")

    def test_mapping_rows_are_complete_and_unambiguous(self):
        for m in self.mapping:
            self.assertTrue(m["new_name"].strip() and m["old_name"] != m["new_name"], m)
            self.assertFalse(rs.bad_name(m["new_name"]), m)
            float(m["lat"]), float(m["lon"])

    def test_stations_on_existing_lines_keep_their_names(self):
        def rows(name):
            with open(config.path("network", name), encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        status = {r["line_id"]: r["status"] for r in rows("lines.csv")}
        st = {r["station_id"]: r for r in rows("stations.csv")}
        ex = config.load()["existing_year"]   # stations open today (an infill stop on today's line is new)
        existing = {r["station_id"] for r in rows("line_stops.csv")
                    if status[r["line_id"]] == "existing" and int(r["year_opens"]) <= ex}
        for m in self.mapping:
            for sid in existing:
                s = st[sid]
                if s["name"] in (m["old_name"], m["new_name"]):
                    self.assertGreater(rs.km(s["lat"], s["lon"], m["lat"], m["lon"]), rs.MATCH_KM,
                                       f"{s['name']} ({sid}) is on a line that exists today")

    def test_street_names_are_shortened_like_dart_names(self):
        self.assertEqual(clean_street("North Belt Line Road"), "Belt Line")
        self.assertEqual(clean_street("Interstate 30 Frontage Road"), "I-30")
        self.assertEqual(clean_street("Lyndon B Johnson Freeway"), "LBJ")
        self.assertEqual(clean_street("Avenue E"), "Avenue E")
        self.assertEqual(clean_street("Plano Parkway", places={"plano"}), "Plano Parkway")
        self.assertEqual(keys("Long / Deen"), keys("Deen / Long"))


if __name__ == "__main__":
    unittest.main()


class StationIdTests(unittest.TestCase):
    def test_generated_ids_are_registered_where_they_stand(self):
        # tools/gen_expansion.py keeps an id per place (scenarios/station_ids.csv), so regenerating
        # a scenario doesn't renumber its stations
        from dfwt import geo
        with open(config.path("scenarios", "station_ids.csv"), encoding="utf-8") as f:
            reg = {r["station_id"]: r for r in csv.DictReader(f)}
        for sc in ("lever_expand_package", "lever_expand_max"):
            with open(config.path("scenarios", sc, "stations.csv"), encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["station_id"].startswith("XS"):
                        g = reg[r["station_id"]]
                        d = geo.hav_km(float(r["lat"]), float(r["lon"]), float(g["lat"]), float(g["lon"]))
                        self.assertLess(d, 0.4, (sc, r["station_id"]))
