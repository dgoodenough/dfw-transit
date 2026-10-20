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

    def test_through_route_joins_two_lines_at_their_shared_terminus(self):
        net = Network.load()
        a, b = net.lines["F02"], net.lines["E22"]
        n_stops = len(a.stop_ids) + len(b.stop_ids) - 1
        km = a.km + b.km
        net.apply_edits([{"op": "through_route", "target": "F02", "field": "E22", "value": "Blue / I-30"}])
        ln = net.lines["F02"]
        self.assertNotIn("E22", net.lines)
        self.assertEqual(len(ln.stop_ids), n_stops)
        self.assertEqual(len(ln.segments), len(ln.stop_ids) - 1)
        self.assertAlmostEqual(ln.km, km, places=6)
        self.assertEqual(net.stations[ln.stop_ids[0]].name, "Ridgmar Mall / BRT Transfer")
        self.assertIn("Handley", [net.stations[s].name for s in ln.pnr_stops])
        # one continuous run once both halves are open
        self.assertEqual(len([r for r in net.runs(2070) if r.line is ln]), 1)

    def test_through_route_keeps_the_better_headway(self):
        net = Network.load()
        net.apply_edits([{"op": "through_route", "target": "E10", "field": "E30", "value": ""}])
        tre = net.lines["E10"]
        self.assertEqual(tre.headway_at(2025), 30)   # Alvarado not open yet: TRE as today
        self.assertEqual(tre.headway_at(2040), 15)   # TRE's 15 beats Alvarado's default 20

    def test_add_express_skips_stops_but_runs_the_same_track(self):
        net = Network.load()
        net.apply_edits([{"op": "add_express", "target": "E17", "field": "E17X", "value": "#10;#20"},
                         {"op": "set_headway", "target": "E17X", "field": "2030", "value": "10"}])
        loc = next(r for r in net.runs(2070) if r.line.id == "E17")
        ex = next(r for r in net.runs(2070) if r.line.id == "E17X")
        self.assertEqual(len(ex.stops), 4)
        self.assertAlmostEqual(sum(ex.hop_km), sum(loc.hop_km), places=6)
        self.assertLess(sum(ex.hop_min), sum(loc.hop_min))
        self.assertEqual(net.lines["E17X"].headway_at(2070), 10)


class CostAndRerouteTests(unittest.TestCase):
    def test_cost_factor_falls_as_the_program_matures(self):
        from dfwt.network import cost_factor
        cfg = {"cost_efficiency": {"2025": 1.0, "2040": 0.85, "2055": 0.75}, "staging": {"construction_years": {"metro": 0}}}
        self.assertAlmostEqual(cost_factor(cfg, 2025, "metro"), 1.0)
        self.assertAlmostEqual(cost_factor(cfg, 2032.5, "metro"), 0.925)
        self.assertAlmostEqual(cost_factor(cfg, 2090, "metro"), 0.75)
        self.assertEqual(cost_factor({"staging": {"construction_years": {}}}, 2050, "metro"), 1.0)

    def test_reroute_keeps_the_old_routing_until_the_new_track_opens(self):
        net = Network.load()
        before = net.line_cost_musd(net.lines["E13"])
        net.apply_edits([{"op": "reroute", "target": "E13", "field": "2035", "value": "tunnel|X137;@32.784,-96.80;X141"}])
        ln = net.lines["E13"]
        self.assertNotIn("X138", ln.stop_ids)          # West End is off the new routing
        self.assertIn("X138", net.line_at("E13", 2030).stop_ids)
        self.assertEqual(net.line_at("E13", 2035), ln)
        self.assertGreater(net.line_cost_musd(ln), before + 500)   # a tunnel is built
        served = lambda y: {s for r in net.runs(y) if r.line.id == "E13" for s in r.stops}
        self.assertIn("X138", served(2030))
        self.assertNotIn("X138", served(2040))


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
        # every pair is reachable by riding, except stations a short walk apart (a walk
        # between platforms isn't a transit trip), which are left out
        walk = {(i, j) for i in range(g.n_st) for j, _, kind in g.adj[i] if kind == "walk" and j < g.n_st}
        bad = [(i, j) for i, j in zip(*np.nonzero(~np.isfinite(T))) if (i, j) not in walk]
        self.assertLess(len(bad), 0.001 * T.size)
        self.assertTrue((T[np.isfinite(T)] >= 0).all())


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


class AccessTests(unittest.TestCase):
    """Feeder bus and other optional access modes (config.access)."""

    @classmethod
    def setUpClass(cls):
        cls.net = Network.load()
        cls.g = YearGraph(cls.net, 2025)
        from dfwt import geo
        pj = geo.Projector()
        st = cls.net.stations[cls.g.station_ids[0]]
        sx, sy = pj.xy(np.array([s_.lat for s_ in map(cls.net.stations.get, cls.g.station_ids)]),
                       np.array([s_.lon for s_ in map(cls.net.stations.get, cls.g.station_ids)]))
        x0, y0 = pj.xy(st.lat, st.lon)
        # a zone on a station, and one 1.5-5 km from the nearest station
        far = None
        for ang in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            for r in (2.5, 3.0, 3.5, 4.0):
                x, y = x0 + r * np.cos(ang), y0 + r * np.sin(ang)
                dmin = float(np.sqrt((sx - x) ** 2 + (sy - y) ** 2).min())
                if 1.5 < dmin < 4.5:
                    far = (x, y, dmin)
                    break
            if far:
                break
        assert far, "no test point found"
        cls.dmin = far[2]

        class Z:
            n = 2
            x = np.array([x0, far[0]])
            y = np.array([y0, far[1]])
            pop = np.array([5000.0, 5000.0])
            jobs = np.array([1000.0, 1000.0])
            cong = 1.0
        cls.Z = Z

    def cfg(self, **feeder):
        cfg = config.load()
        cfg["access"]["feeder"].update({"enabled": True, "min_density_per_km2": 0, **feeder})
        return cfg

    def test_feeders_can_be_switched_off(self):
        cfg = config.load()
        cfg["access"]["feeder"]["enabled"] = False   # on by default: today's buses are the 2025 feeder grid
        acc = demand.Access(self.Z(), self.net, self.g, cfg)
        self.assertFalse((acc.acc_mode == demand.FEEDER).any())
        self.assertFalse((acc.egr_mode == demand.FEEDER).any())

    def test_feeder_reaches_a_zone_beyond_walking_distance(self):
        cfg = self.cfg(headway_min={"2025": 10})
        fd = cfg["access"]["feeder"]
        acc = demand.Access(self.Z(), self.net, self.g, cfg, pnr=False)
        # the zone on a station walks; the far zone rides the bus to its nearest station
        self.assertEqual(acc.acc_mode[0, 0], demand.WALK)
        self.assertEqual(acc.acc_mode[1, 0], demand.FEEDER)
        self.assertEqual(acc.egr_mode[1, 0], demand.FEEDER)
        ovt = fd["stop_walk_min"] + 10 * cfg["wait"]["fraction_of_headway"] + fd["transfer_penalty_min"]
        t = ovt + self.dmin * fd["circuity"] / fd["speed_kmh"] * 60
        self.assertAlmostEqual(float(acc.acc_t[1, 0]), t, places=3)
        self.assertAlmostEqual(float(acc.acc_o[1, 0]), ovt, places=3)   # bus riding is in-vehicle time

    def test_feeder_only_from_its_first_year_and_where_dense_enough(self):
        acc = demand.Access(self.Z(), self.net, self.g, self.cfg(headway_min={"2030": 10}), pnr=False)
        self.assertFalse((acc.acc_mode == demand.FEEDER).any())
        acc = demand.Access(self.Z(), self.net, self.g,
                            self.cfg(headway_min={"2025": 10}, min_density_per_km2=1e9), pnr=False)
        self.assertFalse((acc.acc_mode == demand.FEEDER).any())

    def test_suburban_garages_are_spaced_and_kept_out_of_downtowns(self):
        from dfwt import geo
        cfg = config.load()
        sub = cfg["access"]["pnr_suburban"]
        sub.update(enabled=True, from_year=2025, modes=["metro", "brt", "commuter"])
        g = YearGraph(self.net, 2070)
        before = demand.Access(self.Z(), self.net, g, config.load()).pnr_cap > 0
        cap = demand.Access(self.Z(), self.net, g, cfg).pnr_cap
        new = np.nonzero((cap > 0) & ~before)[0]
        self.assertGreater(len(new), 0)
        pts = [self.net.stations[g.station_ids[i]] for i in new]
        for c in cfg["cores"].values():
            if isinstance(c, dict):
                for s in pts:
                    self.assertGreaterEqual(geo.hav_km(s.lat, s.lon, c["lat"], c["lon"]), sub["min_core_km"] - 0.1)
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                self.assertGreaterEqual(geo.hav_km(pts[a].lat, pts[a].lon, pts[b].lat, pts[b].lon),
                                        sub["min_spacing_km"] - 0.1)
        np.testing.assert_allclose(cap[new], sub["spaces"] * cfg["access"]["pnr_people_per_space"])

    def test_year_tables_and_segments(self):
        self.assertIsNone(demand.in_effect({"2030": 15}, 2025))
        self.assertEqual(demand.in_effect({"2025": 30, "2030": 15}, 2027), 30)
        self.assertEqual(demand.in_effect({"2025": 30, "2030": 15}, 2100), 15)
        cfg = config.load()
        self.assertEqual(demand.access_segments(cfg, 2050), [(1.0, ())])
        cfg["access"]["micromobility"]["enabled"] = True
        cfg["access"]["kiss_ride"]["enabled"] = True
        segs = demand.access_segments(cfg, 2050)
        self.assertAlmostEqual(sum(w for w, _ in segs), 1.0)
        self.assertEqual(len(segs), 3)
        self.assertEqual(demand.access_segments(cfg, 2025), [(1.0, ())])  # before from_year


class ModeChoiceTests(unittest.TestCase):
    def test_no_car_share_rises_with_density(self):
        cfg = config.load()

        class Z:
            n = 3
            pop = np.array([100.0, 20000, 80000])
            jobs = np.array([0.0, 0, 0])
            x = np.array([0.0, 50, 100])
            y = np.zeros(3)
        nc = demand.no_car_share(Z(), cfg)
        self.assertTrue(np.all(np.diff(nc) >= 0))
        self.assertGreaterEqual(nc.min(), cfg["ridership"]["no_car"]["share_by_density"][0][1])

    def test_calibration_constants_are_set(self):
        rc = config.load()["ridership"]
        self.assertLess(rc["pnr_asc_offset"], 0)      # drive-to-transit is less liked than walking in
        self.assertGreater(rc["b_ratio"], 0)
        self.assertLess(rc["active"]["asc"], 0)


class QuickBuildTests(unittest.TestCase):
    def test_quick_build_keeps_last_full_line_values(self):
        import csv as _csv
        import json
        import tempfile
        from dfwt import evaluate
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "lines.csv"), "w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=["line_id", "status", "marginal_at_opening", "marginal_final", "value_per_musd"])
            w.writeheader()
            w.writerow({"line_id": "A", "status": "proposed", "marginal_at_opening": "120", "marginal_final": "300",
                        "value_per_musd": "4.5"})
        with open(os.path.join(d, "line_values.json"), "w") as f:
            json.dump({"full_build": "2026-10-20"}, f)
        ev = {"lines": [{"line_id": "A", "status": "proposed"}, {"line_id": "B", "status": "proposed"}]}
        evaluate.carry_line_values(d, ev)
        self.assertEqual(ev["lines"][0]["marginal_final"], 300)
        self.assertEqual(ev["lines"][0]["value_per_musd"], 4.5)
        self.assertEqual(ev["lines"][1]["value_per_musd"], "")       # new since the full build
        self.assertEqual(ev["line_values_from"], "2026-10-20")


class LandUsePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.load()
        cls.zones = demand.Zones(cls.cfg)
        cls.net = Network.load(None, cls.cfg)

    def test_growth_capture_moves_growth_to_stations_without_changing_totals(self):
        import copy as cp
        cfg = cp.deepcopy(self.cfg)
        base = growth.grown_zones(self.zones, self.net, 2050, cfg)
        cfg["growth"]["capture"]["job_centers"]["jobs_share"] = 0.1
        cen = growth.grown_zones(self.zones, self.net, 2050, cfg)
        self.assertGreater(cen.capture["center_jobs"], 0)
        self.assertAlmostEqual(cen.jobs.sum(), base.jobs.sum(), delta=1.0)
        cfg["growth"]["capture"]["job_centers"]["jobs_share"] = 0.0
        cfg["growth"]["capture"].update(pop_share=0.5, jobs_share=0.5)
        pol = growth.grown_zones(self.zones, self.net, 2050, cfg)
        self.assertAlmostEqual(pol.pop.sum(), base.pop.sum(), delta=1.0)
        self.assertAlmostEqual(pol.jobs.sum(), base.jobs.sum(), delta=1.0)
        near = growth.near_stations(base, self.net, 2050)
        self.assertGreater(pol.pop[near].sum(), base.pop[near].sum() + 0.9 * pol.capture["captured_pop"])
        self.assertTrue((pol.pop >= 0).all() and (pol.jobs >= 0).all())
        # no station area is filled past its target density (unless it already was)
        c = cfg["growth"]["capture"]
        sa = growth.station_areas(self.zones, self.net, 2050, cfg, c["radius_m"])
        ins = sa["zone_st"] >= 0
        act = lambda z: np.bincount(sa["zone_st"][ins], weights=(z.pop + z.jobs)[ins], minlength=len(sa["sids"]))
        cap = np.array([c["target_density_per_km2"][s] * c["mode_factor"][m]
                        for s, m in zip(sa["setting"], sa["mode"])]) * sa["area"]
        before, after = act(base), act(pol)
        grew = after > before + 1
        self.assertTrue(grew.any())
        # (a station that opens next to an earlier one takes over land, and growth, placed
        # under the earlier one's headroom, so allow a few over)
        within = after[grew] <= np.maximum(cap[grew], before[grew]) * 1.15 + 1
        self.assertGreater(within.mean(), 0.95)

    def test_growth_cases_follow_the_alt_tables(self):
        import copy as cp
        cfg = cp.deepcopy(self.cfg)
        mid_j = growth.regional(cfg, "jobs", 2070)
        cfg["growth"]["case"] = "high"
        hi = cfg["growth"]["alt"]["high_pop"]
        self.assertAlmostEqual(growth.regional(cfg, "pop", 2070), hi["2070"])
        ratio = hi["2070"] / cfg["growth"]["regional_pop"]["2070"]
        self.assertAlmostEqual(growth.regional(cfg, "jobs", 2070), mid_j * ratio)

    def test_upzoning_gives_existing_stations_tod(self):
        import copy as cp
        cfg = cp.deepcopy(self.cfg)
        p0, _ = growth.tod_uplift(self.zones, self.net, 2025, cfg)
        cfg["growth"]["tod"]["upzone_existing_year"] = 2020
        p1, _ = growth.tod_uplift(self.zones, self.net, 2025, cfg)
        self.assertEqual(p0.max(), 0.0)
        self.assertGreater(p1.max(), 0.0)

    def test_parking_policy_phases_in(self):
        import copy as cp
        cfg = cp.deepcopy(self.cfg)
        pol = cfg["ridership"]["parking_policy"]
        pol.update(price_growth=1.0, priced_centers={"min_jobs_per_km2": 10000, "usd_per_day": 8},
                   cashout={"min_jobs_per_km2": 2000, "usd_per_day": 5, "coverage": 0.5})
        z = demand.Zones(cfg)
        z._dist = self.zones.dist_rows(0, self.zones.n)
        today = z.parking_usd()
        g = cp.copy(z)
        g.year, g.tod_key = 2050, ("test", 2050)
        usd, cash, cov = g.parking_usd()
        self.assertAlmostEqual(usd.max(), 2 * today[0].max())       # prices doubled by full_year
        self.assertGreater((usd > 0).sum(), (today[0] > 0).sum())    # more priced places
        self.assertEqual(today[2].max(), 0.0)
        self.assertAlmostEqual(cov.max(), 0.5)
        self.assertEqual(float(cov[usd > 0].max()), 0.0)             # no cash-out where parking is priced


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
            {"line_id": "E17", "stage": "2", "kind": "extension", "from_stop": "Frisco Main St",
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
