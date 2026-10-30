"""The map page (dfwt/webmap.py, dfwt/templates/map.html): what it exports beyond the model's
numbers, and that the page's drive-alone minutes follow the model's formula."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, webmap  # noqa: E402
from dfwt.network import Network  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dfwt", "templates", "map.html")


def drive_minutes(d, km, cong):
    """config.drive: road km = km x circuity; the first local_km at local_kmh, the rest at
    freeway_kmh; the moving part x congestion, plus terminal minutes."""
    road = km * d["circuity"]
    local = min(road, d["local_km"])
    return (local / d["local_kmh"] * 60 + (road - local) / d["freeway_kmh"] * 60) * cong + d["terminal_min"]


class StationGradeTests(unittest.TestCase):
    def test_grades_follow_adjacent_segments(self):
        net = Network.load(None, config.load())
        grades = webmap.station_grades(net)
        near = {}   # (station, mode) -> grades of the segments beside it, over that mode's lines
        for ln in net.lines.values():
            for i, sid in enumerate(ln.stop_ids):
                near.setdefault((sid, ln.mode), set()).update(ln.segments[k].grade for k in (i - 1, i) if 0 <= k < len(ln.segments))
        seen_tunnel = False
        for (sid, mode), gs in near.items():
            if "tunnel" in gs:
                seen_tunnel = True
                self.assertEqual(grades[sid][mode], "tunnel", sid)
            elif gs <= {"surface"}:
                self.assertNotIn(mode, grades.get(sid, {}), sid)
        self.assertTrue(seen_tunnel)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PageDriveTests(unittest.TestCase):
    def run_drive(self, export, km):
        """driveMin from the page, for two points `km` apart on the projection plane."""
        src = open(TEMPLATE, encoding="utf-8").read()
        fn = re.search(r"function driveMin\(T, A, B, Y\) \{.*?\n\}", src, re.S).group(0)
        proj = re.search(r"const projXY = .*?;", src).group(0)
        T = {"proj": [32.8, -97.0, 1.0, 1.0], "cong": {"2050": 1.12}, "drive": export}
        js = f"{proj}\n{fn}\nconsole.log(driveMin({json.dumps(T)}, {{lat: 32.8, lon: -97.0}}, {{lat: 32.8, lon: {-97.0 + km}}}, 2050));"
        return float(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)

    def test_local_then_freeway(self):
        d = {"circuity": 1.35, "local_km": 5, "local_kmh": 30, "freeway_kmh": 72, "terminal_min": 5}
        export = {"circuity": 1.35, "localKm": 5, "localKmh": 30, "freewayKmh": 72, "terminal": 5}
        for km in (1.0, 3.7, 12.5, 50.0):
            self.assertAlmostEqual(self.run_drive(export, km), drive_minutes(d, km, 1.12), places=6)

    def test_old_export_still_works(self):
        export = {"perKm": 1.35 / 38 * 60, "terminal": 8}
        self.assertAlmostEqual(self.run_drive(export, 10.0), 10 * 1.35 / 38 * 60 * 1.12 + 8, places=6)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PageLineDiagramTests(unittest.TestCase):
    def align(self, B, F):
        """alignStops from the page: the line diagram lines up the shown year's stops with the last year's."""
        src = open(TEMPLATE, encoding="utf-8").read()
        fn = re.search(r"function alignStops\(B, F\) \{.*?\n\}", src, re.S).group(0)
        js = f"{fn}\nconsole.log(JSON.stringify(alignStops({json.dumps(B)}, {json.dumps(F)})));"
        return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)

    def test_reroute_is_a_gap_between_shared_stops(self):
        ops, n = self.align(list("ABCDEF"), list("ABXYEFG"))
        self.assertEqual(n, 4)
        self.assertEqual([o for o, _ in ops], ["=", "=", "b", "b", "f", "f", "=", "=", "f"])

    def test_infill_and_extension(self):
        ops, n = self.align(list("ACD"), list("ABCDE"))
        self.assertEqual(ops, [["=", "A"], ["f", "B"], ["=", "C"], ["=", "D"], ["f", "E"]])


if __name__ == "__main__":
    unittest.main()
