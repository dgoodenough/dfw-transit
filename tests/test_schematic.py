"""Schematic (diagram view) layout: octilinear, spaced, deterministic, geographic."""
import json
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, schematic  # noqa: E402
from dfwt.network import Network  # noqa: E402


def scenarios():
    d = config.path("scenarios")
    return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))


class SchematicLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nets = {sc or "plan": Network.load(sc) for sc in [None] + scenarios()}
        cls.lay = schematic.compute(cls.nets)
        cls.js = schematic.to_json(cls.lay)

    def node(self, name):
        return next(n for n in self.lay.nodes if n["name"] == name)

    def test_every_drawn_edge_is_octilinear_with_at_most_one_bend(self):
        for e in range(len(self.lay.edges)):
            pts = schematic.edge_polyline(self.lay, e)
            self.assertLessEqual(len(pts), 3, "more than one bend")
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                self.assertGreater(math.hypot(x1 - x0, y1 - y0), 1e-6)
                a = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 45
                self.assertLess(min(a, 45 - a), 0.5, f"edge {e} is not octilinear")

    def test_no_two_stations_closer_than_min_spacing(self):
        X = np.array([[n["x"], n["y"]] for n in self.lay.nodes])
        d = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))
        np.fill_diagonal(d, np.inf)
        self.assertGreaterEqual(d.min(), schematic.MIN_SP - 1e-6)

    def test_layout_is_deterministic(self):
        again = schematic.to_json(schematic.compute(self.nets))
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.js, sort_keys=True))

    def test_every_station_of_every_scenario_is_placed(self):
        for net in self.nets.values():
            for ln in net.lines.values():
                for sid in ln.stop_ids:
                    self.assertIn(sid, self.lay.node_of)

    def test_line_paths_follow_drawn_edges(self):
        for key, net in self.nets.items():
            for ln in net.lines.values():
                path, stop_at = self.js["paths"][key][ln.id]
                self.assertEqual(len(stop_at), len(ln.stop_ids))
                self.assertEqual([path[i] for i in stop_at], [self.lay.node_of[s] for s in ln.stop_ids])
                for a, b in zip(path, path[1:]):
                    self.assertIn((min(a, b), max(a, b)), self.lay.eidx)

    def test_rough_geography_is_kept(self):
        fw, dal = self.node("Fort Worth Central"), self.node("Union Station")
        den = self.node("Downtown Denton Transit Center")
        self.assertLess(fw["x"], dal["x"])          # Fort Worth west of Dallas
        self.assertGreater(den["y"], dal["y"])      # Denton north (y grows north)
        self.assertGreater(den["y"], fw["y"])

    def test_corridor_line_order_is_a_permutation_of_its_lines(self):
        for ed in self.lay.edges:
            self.assertEqual(len(ed["lines"]), len(set(ed["lines"])))

    def test_base_name_strips_only_a_compass_suffix(self):
        self.assertEqual(schematic.base_name("Irving W3"), "Irving")
        self.assertEqual(schematic.base_name("Fair Park E10"), "Fair Park")
        self.assertEqual(schematic.base_name("UTA E"), "UTA")
        self.assertEqual(schematic.base_name("Frisco Main St"), "Frisco Main St")
        self.assertEqual(schematic.base_name("Northeast"), "Northeast")

    def test_label_groups_join_close_same_named_stations(self):
        lead = self.js["lead"]
        self.assertEqual(len(lead), len(self.lay.nodes))
        nodes = self.lay.nodes
        groups = {}
        for v, k in enumerate(lead):
            self.assertEqual(lead[k], k, "a group's leader leads itself")
            self.assertEqual(schematic.base_name(nodes[v]["name"]).lower(), schematic.base_name(nodes[k]["name"]).lower())
            groups.setdefault(k, []).append(v)
        for k, vs in groups.items():
            for v in vs:     # every member is within LABEL_GROUP of another member (groups are chains of close stations)
                if len(vs) > 1:
                    self.assertTrue(any(math.hypot(nodes[v]["x"] - nodes[u]["x"], nodes[v]["y"] - nodes[u]["y"]) <= schematic.LABEL_GROUP
                                        for u in vs if u != v))
            # the leader is the plain-named member when there is one
            if any(schematic.base_name(nodes[v]["name"]) == nodes[v]["name"] for v in vs):
                self.assertEqual(schematic.base_name(nodes[k]["name"]), nodes[k]["name"])
        uptown = [v for v, nd in enumerate(nodes) if nd["name"] == "Uptown"]
        self.assertGreater(len(uptown), 1)
        self.assertEqual(len({lead[v] for v in uptown}), 1, "the Uptown stations share one label")

    def test_waterways_extract_is_small_and_complete(self):
        path = config.path("data", "waterways.geojson")
        self.assertLess(os.path.getsize(path), 300 * 1024)
        with open(path, encoding="utf-8") as f:
            names = {ft["properties"]["name"] for ft in json.load(f)["features"]}
        for n in ("Trinity River", "West Fork Trinity River", "Elm Fork Trinity River", "Lewisville Lake", "White Rock Lake"):
            self.assertIn(n, names)
        self.assertTrue(self.lay.water["rivers"] and self.lay.water["lakes"])


if __name__ == "__main__":
    unittest.main()
