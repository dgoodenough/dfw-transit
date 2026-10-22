"""The map's door-to-door trip planner reads the model's access rules from dfwt/tripplan.py.
These tests check the export reproduces demand.Access, so the page can't drift from the model."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, demand, growth, tripplan  # noqa: E402
from dfwt.graph import YearGraph  # noqa: E402
from dfwt.network import Network  # noqa: E402

SC = "two_million"   # feeder buses, bike and drop-off levers, walk-distance year tables


class TripPlanExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.load(scenario=SC)
        cls.net = Network.load(SC, cls.cfg)
        cls.zones = demand.Zones(cls.cfg)
        cls.years = (2025, 2050)
        cls.graphs = {y: YearGraph(cls.net, y) for y in cls.years}
        cls.out = tripplan.export(cls.zones, cls.net, cls.graphs)

    def test_rules_follow_year_tables_and_levers(self):
        r25, r50 = (tripplan.rules(self.cfg, y) for y in self.years)
        ac = self.cfg["access"]
        self.assertAlmostEqual(r25["walkKm"], demand.in_effect(ac["walk_max_m"], 2025) / 1000)
        self.assertAlmostEqual(r50["walkKm"], demand.in_effect(ac["walk_max_m"], 2050) / 1000)
        self.assertEqual(r50["feeder"]["headway"], demand.feeder_headway(self.cfg, 2050))
        self.assertNotIn("bike", r25)   # micromobility starts in from_year (2030)
        self.assertIn("bike", r50)
        self.assertIn("kiss", r50)
        base = tripplan.rules(config.load(), 2050)
        self.assertNotIn("bike", base)

    def test_garages_match_access(self):
        for y, g in self.graphs.items():
            gz = growth.grown_zones(self.zones, self.net, y, self.cfg)
            is_pnr, _ = demand.garages(gz, self.net, g, self.cfg)
            acc = demand.Access(gz, self.net, g, self.cfg)
            np.testing.assert_array_equal(is_pnr, acc.pnr_cap > 0)
            exported = {s for s, ts in self.out["garages"].items() if sum(t <= y for t in ts) % 2}
            self.assertEqual(exported, {s for s, p in zip(g.station_ids, is_pnr) if p})

    def test_exported_rules_reproduce_access_minutes(self):
        """Recompute the model's access minutes for a sample of zones from the export, as the page does."""
        k = self.out
        for y, g in self.graphs.items():
            gz = growth.grown_zones(self.zones, self.net, y, self.cfg)
            acc = demand.Access(gz, self.net, g, self.cfg)
            r, c = k["rules"][k["yearRules"][y]], k["cong"][y]
            self.assertAlmostEqual(c, gz.cong, places=4)
            st = self.net.stations
            for i in range(0, self.zones.n, 97):
                for j in range(acc.acc_st.shape[1]):
                    t = acc.acc_t[i, j]
                    if not np.isfinite(t):
                        continue
                    s = st[g.station_ids[acc.acc_st[i, j]]]
                    sx, sy = (s.lon - k["proj"][1]) * k["proj"][2], (s.lat - k["proj"][0]) * k["proj"][3]
                    zx, zy = (self.zones.lon[i] - k["proj"][1]) * k["proj"][2], (self.zones.lat[i] - k["proj"][0]) * k["proj"][3]
                    d = np.hypot(sx - zx, sy - zy)
                    mode = demand.ACCESS_MODES[acc.acc_mode[i, j]]
                    page = {"walk": lambda: d * r["walkPerKm"],
                            "pnr": lambda: d * r["pnr"]["perKm"] * c + r["pnr"]["pen"],
                            "feeder": lambda: r["feeder"]["ovt"] + d * r["feeder"]["perKm"] * c}[mode]()
                    self.assertAlmostEqual(page, float(t), delta=0.02, msg=f"zone {i} {mode} {y}")

    def test_feeder_zones_match_density(self):
        y = 2050
        gz = growth.grown_zones(self.zones, self.net, y, self.cfg)
        ok = demand.activity_density(gz) >= self.cfg["access"]["feeder"]["min_density_per_km2"]
        feed = self.out["feed"]
        page = np.array([sum(t <= y for t in v) % 2 == 1 if isinstance(v, list) else (v > 0 and y >= v) for v in feed])
        np.testing.assert_array_equal(page, ok)
        self.assertGreater(ok.sum(), 0)

    def test_drive_matches_the_model(self):
        d = self.out["drive"]
        gz = growth.grown_zones(self.zones, self.net, 2050, self.cfg)
        for km in (1.0, 12.5, 50.0):   # the page's driveMin: local streets, then freeway
            road = km * d["circuity"]
            local = min(road, d["localKm"])
            moving = local / d["localKmh"] * 60 + (road - local) / d["freewayKmh"] * 60
            self.assertAlmostEqual(moving * self.out["cong"][2050] + d["terminal"], gz.drive_min(km), places=2)
        self.assertLess(gz.drive_min(40.0) / gz.drive_min(4.0), 10 * 0.6)   # long trips average a higher speed

    def test_zone_points_round_trip(self):
        pts = tripplan.zone_points(self.zones)
        self.assertEqual(len(pts), 2 * self.zones.n)
        self.assertAlmostEqual(pts[0] / 1e4, self.zones.lat[0], places=4)
        self.assertAlmostEqual(pts[1] / 1e4, self.zones.lon[0], places=4)


if __name__ == "__main__":
    unittest.main()
