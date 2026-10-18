import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, demand, validate  # noqa: E402
from dfwt.graph import YearGraph  # noqa: E402
from dfwt.network import Network  # noqa: E402


class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = Network.load()

    def test_every_line_has_one_segment_per_stop_gap(self):
        for ln in self.net.lines.values():
            self.assertEqual(len(ln.segments), len(ln.stop_ids) - 1, ln.name)

    def test_only_existing_lines_run_today(self):
        running = {r.line.id for r in self.net.runs(2025)}
        existing = {l.id for l in self.net.lines.values() if l.status == "existing"}
        self.assertEqual(running, existing)

    def test_service_upgrade_applies_from_its_year(self):
        tre = next(l for l in self.net.lines.values() if l.name == "TRE")
        self.assertEqual(tre.headway_at(2025), 30)
        self.assertEqual(tre.headway_at(2030), 15)

    def test_shared_track_is_charged_once(self):
        owner = self.net.track_owner()
        total = sum(self.net.line_cost_musd(l, owner=owner) for l in self.net.lines.values())
        naive = 0.0
        cfg = self.net.cfg
        for l in self.net.lines.values():
            if l.status == "existing":
                continue
            per = cfg["cost_musd_per_km"][l.mode]
            naive += sum(s.km * per.get(s.grade, per["surface"]) for s in l.segments if s.year > cfg["existing_year"])
            naive += sum(1 for y in l.stop_years if y > cfg["existing_year"]) * cfg["station_cost_musd"][l.mode]
        self.assertLess(total, naive)

    def test_shifting_a_line_moves_all_of_it(self):
        net = Network.load()
        ln = net.lines["E28"]
        before = ln.first_year
        net.apply_edits([{"op": "shift_line_years", "target": "E28", "field": "", "value": "10"}])
        self.assertEqual(ln.first_year, before + 10)


class ValidationTests(unittest.TestCase):
    def test_plan_has_no_errors_or_islands(self):
        findings = validate.run(Network.load())
        bad = [f for f in findings if f[0] == "error" or f[1] == "ISLAND"]
        self.assertEqual(bad, [])

    def test_v1_baseline_still_shows_its_known_defects(self):
        codes = {f[1] for f in validate.run(Network.load("v1_baseline"))}
        self.assertIn("DUP_NAME", codes)
        self.assertIn("ISLAND", codes)


class ScenarioTests(unittest.TestCase):
    def test_right_sized_changes_modes(self):
        net = Network.load("right_sized")
        self.assertEqual(net.lines["E23"].mode, "brt")

    def test_v1_baseline_has_no_v2_lines(self):
        net = Network.load("v1_baseline")
        self.assertNotIn("E38", net.lines)
        self.assertEqual(net.transfers, [])


class GraphTests(unittest.TestCase):
    def test_midlothian_reaches_downtown_dallas_in_2050(self):
        net = Network.load()
        g = YearGraph(net, 2050)
        legs, total = g.itinerary(g.sidx["X595"] if "X595" in g.sidx else
                                  g.sidx[next(s for s in g.station_ids if net.stations[s].name == "Midlothian")],
                                  g.sidx["X187"])
        self.assertLess(total, 120)
        self.assertTrue(any(kind == "ride" for kind, *_ in legs))

    def test_skim_is_zero_on_diagonal_and_finite(self):
        g = YearGraph(Network.load(), 2025)
        T = g.skim()
        self.assertTrue(np.all(np.diag(T) == 0))
        self.assertTrue(np.isfinite(T).all())


class DemandTests(unittest.TestCase):
    def test_gravity_matches_productions_and_attractions(self):
        cfg = config.load()

        class Z:  # four zones on a line
            n = 4
            pop = np.array([100.0, 0, 50, 50])
            jobs = np.array([0.0, 120, 30, 50])
            x = np.array([0.0, 5, 10, 20])
            y = np.zeros(4)
            cfg_ = cfg

            def dist_rows(self, i0, i1):
                return np.abs(self.x[i0:i1, None] - self.x[None, :]).astype(np.float32)

            def drive_min(self, d):
                return demand.Zones.drive_min(self, d)

        z = Z()
        z.cfg = cfg
        od = demand.gravity(z, cfg)
        total = cfg["demand"]["total_commutes"]
        np.testing.assert_allclose(od.sum(axis=1), z.pop / z.pop.sum() * total, rtol=1e-3)
        np.testing.assert_allclose(od.sum(axis=0), z.jobs / z.jobs.sum() * total, rtol=1e-3)


if __name__ == "__main__":
    unittest.main()
