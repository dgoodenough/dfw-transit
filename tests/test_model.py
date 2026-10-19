import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, demand, growth, validate  # noqa: E402
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
            cong = 1.0

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

    def test_growth_keeps_regional_totals_honest(self):
        cfg = config.load()
        base = np.array([100.0, 200, 300, 400])
        up = np.array([0.5, 0.0, 0.0, 0.0])
        g = growth._grow(base, 1.5, up, 0.2)
        # only 20% of the uplift is new to the region; the rest comes from elsewhere
        self.assertAlmostEqual(g.sum(), base.sum() * 1.5 + 0.2 * 100 * 1.5 * 0.5, places=6)
        self.assertGreater(g[0], base[0] * 1.5)
        self.assertLess(g[3], base[3] * 1.5)
        self.assertAlmostEqual(growth.congestion(cfg, cfg["drive"]["congestion"]["base_year"]), 1.0)
        self.assertLessEqual(growth.congestion(cfg, 2300), 1 + cfg["drive"]["congestion"]["cap"] + 1e-9)

    def test_balance_hits_row_and_column_totals(self):
        K = np.random.default_rng(1).random((5, 5)).astype(np.float32)
        O = np.array([1.0, 2, 3, 4, 5])
        D = np.array([3.0, 3, 3, 3, 3])
        out = demand.balance(K, O, D, 50)
        np.testing.assert_allclose(out.sum(axis=1), O, rtol=1e-3)
        np.testing.assert_allclose(out.sum(axis=0), D, rtol=1e-3)


if __name__ == "__main__":
    unittest.main()


class StagingTests(unittest.TestCase):
    def test_inferred_stages_round_trip(self):
        from dfwt import staging
        tables, _ = Network.read_tables()
        tables.pop("stages.csv")
        rows = staging.infer_stages(tables)
        t2, _, findings = staging.compile_stages(tables, rows)
        self.assertEqual([r["year_opens"] for r in tables["line_segments.csv"]],
                         [r["year_opens"] for r in t2["line_segments.csv"]])
        self.assertEqual([f for f in findings if f[0] == "error"], [])

    def test_a_staged_line_grows_per_interval(self):
        tables, _ = Network.read_tables()
        rows = [r for r in tables["stages.csv"] if r["line_id"] != "E17"]
        rows += [
            {"line_id": "E17", "stage": "1", "kind": "starter", "from_stop": "Galleria",
             "to_stop": "Pearl/Arts District", "year_opens": "2045"},
            {"line_id": "E17", "stage": "2", "kind": "extension", "from_stop": "Frisco",
             "to_stop": "Galleria", "year_opens": "2050"},
            {"line_id": "E17", "stage": "3", "kind": "extension", "from_stop": "Pearl/Arts District",
             "to_stop": "Rowlett", "year_opens": "2055"},
        ]
        net = Network.load(stage_rows=rows)
        km = {y: sum(sum(r.hop_km) for r in net.runs(y) if r.line.id == "E17") for y in (2045, 2050, 2055)}
        self.assertTrue(0 < km[2045] < km[2050] < km[2055])

    def test_spend_is_spread_before_opening(self):
        from dfwt import staging
        net = Network.load()
        spend = staging.spend_by_year(net)
        last_opening = max(y for l in net.lines.values() for y in l.stop_years + [s.year for s in l.segments])
        self.assertLess(max(spend), last_opening)
        self.assertAlmostEqual(sum(spend.values()),
                               sum(net.line_cost_musd(l) for l in net.lines.values()), delta=1.0)


class GeometryTests(unittest.TestCase):
    def test_fitted_corner_meets_minimum_radius(self):
        from dfwt import align
        cfg = config.load()
        m = align.params(cfg, "metro")
        # an L-shaped corridor with a sharp 90 degree corner between two far-apart stations
        a, corner, b = (-97.30, 32.75), (-97.30, 32.77), (-97.27, 32.77)
        segs, rep = align.fit_line([a, corner, b], [0, 2], ["surface"], [a, b], m)
        self.assertGreaterEqual(rep["min_radius_m"], m["Rmin"])
        self.assertEqual(segs[0][0], a)
        self.assertEqual(segs[-1][-1], b)

    def test_denoise_removes_spike(self):
        from dfwt import align
        pts = [(-97.30, 32.75), (-97.29, 32.75), (-97.2895, 32.75), (-97.2899, 32.75), (-97.28, 32.75)]
        out = align.denoise(pts)
        lons = [p[0] for p in out]
        self.assertEqual(lons, sorted(lons))

    def test_wkb_linestring(self):
        import struct
        from dfwt import osmroute
        buf = struct.pack("<BII4d", 1, 2, 2, -97.0, 32.0, -96.5, 32.5)
        self.assertEqual(osmroute.wkb_linestring(buf), [(-97.0, 32.0), (-96.5, 32.5)])
