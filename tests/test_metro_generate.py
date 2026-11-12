"""The network generator (metro/generate.py) on small synthetic inputs.

Two dense clusters 20 km apart on one arterial, a thin string of homes between them: the
generator should find two centers, route one corridor between them on the road, call it
metro by its density, put stations at both centers, and write tables dfwt loads without
errors. Without jobs data it must still run, flagged as population-only.
"""
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LAT0, LON0 = 30.0, -90.0
KX = 111.32 * math.cos(math.radians(LAT0))


def ll(x_km, y_km):
    return LAT0 + y_km / 110.57, LON0 + x_km / KX


def wkb(points):
    return b"\x01" + struct.pack("<II", 2, len(points)) + b"".join(struct.pack("<dd", lon, lat) for lon, lat in points)


def write_roads(path, x0=-3, x1=23):
    """An east-west arterial along y = 0, one Overture-style segment per km."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    rows = []
    for k, x in enumerate(range(x0, x1)):
        a, b = ll(x, 0), ll(x + 1, 0)
        rows.append({"id": f"s{k}", "geometry": wkb([(a[1], a[0]), (b[1], b[0])]), "class": "primary",
                     "connectors": [{"connector_id": f"c{k}", "at": 0.0}, {"connector_id": f"c{k + 1}", "at": 1.0}],
                     "access_restrictions": [], "names": {"primary": "Main Street"}})
    for k, y in enumerate((-2, 2)):   # two cross streets, for station names
        for cx in (0, 20):
            a, b = ll(cx, y), ll(cx, 0)
            rows.append({"id": f"x{k}{cx}", "geometry": wkb([(a[1], a[0]), (b[1], b[0])]), "class": "secondary",
                         "connectors": [{"connector_id": f"y{k}{cx}", "at": 0.0},
                                        {"connector_id": f"c{cx - x0}", "at": 1.0}],
                         "access_restrictions": [], "names": {"primary": f"Cross {k}{cx} Road"}})
    restr = pa.list_(pa.struct([("access_type", pa.string()),
                                ("when", pa.struct([("heading", pa.string()), ("mode", pa.list_(pa.string()))])),
                                ("between", pa.list_(pa.float64()))]))
    schema = pa.schema([("id", pa.string()), ("geometry", pa.binary()), ("class", pa.string()),
                        ("connectors", pa.list_(pa.struct([("connector_id", pa.string()), ("at", pa.float64())]))),
                        ("access_restrictions", restr), ("names", pa.struct([("primary", pa.string())]))])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def zones(with_jobs=True):
    """Two clusters (x = 0 and x = 20 km) of dense block groups, homes every km between."""
    out = []
    k = 0
    for cx, scale in ((0, 1.0), (20, 0.8)):
        for i in range(-2, 3):
            for j in range(-2, 3):
                k += 1
                out.append((cx + i * 0.4, j * 0.4, 2500 * scale, 4000 * scale, k))
    for x in range(3, 18):
        for y in (-0.5, 0.5):
            k += 1
            out.append((x, y, 900, 150, k))
    for x in range(-10, 30, 4):          # thin countryside
        for y in (-8, 8):
            k += 1
            out.append((x, y, 300, 30, k))
    rows = []
    for x, y, pop, jobs, k in out:
        lat, lon = ll(x, y)
        rows.append({"geoid": f"{k:012d}", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "pop": str(int(pop)),
                     "jobs": str(int(jobs)) if with_jobs else "", "area_km2": "", "county_fips": "99001"})
    return rows


def synthetic_metro(tmp, with_jobs=True):
    from metro import inputs
    write_roads(os.path.join(tmp, "roads.parquet"))
    return inputs.Metro("synthetic", tmp, zones(with_jobs), {"name": "Synthetic"}, None,
                        {"roads": os.path.join(tmp, "roads.parquet"), "rail": None})


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pyarrow not installed")
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        from dfwt import osmroute
        osmroute.set_origin(32.8, -97.0)   # other tests use the DFW projection

    def test_two_clusters_give_two_centers(self):
        from metro import centers, generate
        m = synthetic_metro(self.tmp)
        p = generate.params()["centers"]
        surf = centers.Surface(m, p["grid_km"], p["kernel_km"])
        cs = centers.find(m, surf, p)
        centers.classify(m, cs, p)
        self.assertEqual(len(cs), 2)
        xs = sorted(round(c.x - float(m.xy(LAT0, LON0)[0])) for c in cs)
        self.assertEqual(xs, [0, 20])
        self.assertEqual(max(cs, key=lambda c: c.activity).kind, "downtown")

    def test_one_corridor_between_them(self):
        from dfwt import config, validate
        from metro import generate, output
        m = synthetic_metro(self.tmp)
        out = os.path.join(self.tmp, "out")
        r = generate.generate("synthetic", out=out, run_model=False, metro=m, log=lambda *a: None)
        self.assertEqual(len(r["chosen"]), 1)
        line = r["chosen"][0]
        self.assertEqual(line.mode, "metro")              # ~13,000 people + jobs per route-km
        self.assertAlmostEqual(line.km, 20, delta=2.5)     # routed along the arterial
        self.assertGreaterEqual(len(line.stops), 4)
        for name in ("lines.csv", "stations.csv", "line_stops.csv", "line_segments.csv", "transfers.csv",
                     "stages.csv", "report.md", "candidates.csv", "centers.csv"):
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        net = output.load_net(r["tables"], config.load(), "synthetic")
        self.assertEqual([f for f in validate.run(net) if f[0] == "error"], [])
        ends = {net.stations[s].lon for s in (net.lines["G01"].stop_ids[0], net.lines["G01"].stop_ids[-1])}
        self.assertEqual(sorted(round((lon - LON0) * KX) for lon in ends), [0, 20])

    def test_population_only_is_flagged(self):
        from metro import generate
        m = synthetic_metro(self.tmp, with_jobs=False)
        self.assertFalse(m.jobs_ok)
        out = os.path.join(self.tmp, "out_pop")
        r = generate.generate("synthetic", out=out, run_model=False, metro=m, log=lambda *a: None)
        self.assertTrue(r["chosen"])
        with open(os.path.join(out, "report.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("population-only", text)

    def test_mode_thresholds(self):
        from metro import candidates, generate
        gp = generate.params()
        self.assertEqual(candidates.choose_mode("road", 20, 9000, 0, gp)[0], "metro")
        self.assertEqual(candidates.choose_mode("road", 20, 4000, 0, gp)[0], "brt")
        self.assertEqual(candidates.choose_mode("road", 4, 15000, 0, gp)[0], "streetcar")
        self.assertIsNone(candidates.choose_mode("road", 20, 1000, 0, gp)[0])
        self.assertEqual(candidates.choose_mode("rail", 40, 0, 3000, gp)[0], "commuter")


if __name__ == "__main__":
    unittest.main()


class BuildoutParamsTests(unittest.TestCase):
    def test_buildout_block_merges_only_when_asked(self):
        from metro import generate
        base, bo = generate.params(), generate.params(buildout=True)
        self.assertNotIn("buildout", base)
        self.assertFalse(base["buildout_mode"])
        self.assertTrue(bo["buildout_mode"])
        self.assertLess(bo["centers"]["min_activity"], base["centers"]["min_activity"])
        self.assertLess(bo["modes"]["brt"], base["modes"]["brt"])
        self.assertLess(bo["selection"]["min_trips_per_musd"], base["selection"]["min_trips_per_musd"])
        self.assertEqual(bo["modes"]["metro"], base["modes"]["metro"])   # untouched keys stay


class MetroGrowthTests(unittest.TestCase):
    """A metro's own growth (registry `growth`) replaces DFW's forecast, and future years run."""

    @classmethod
    def setUpClass(cls):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pyarrow not installed")
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        from dfwt import osmroute
        osmroute.set_origin(32.8, -97.0)

    def test_registry_growth_replaces_dfw_forecast(self):
        from dfwt import config, growth
        from metro import model
        m, base = synthetic_metro(self.tmp), config.load()
        own = {"regional_pop": {"2020": 1.0, "2050": 1.3, "_doc": "x"}, "regional_jobs": {"2023": 1.0, "2050": 1.25}}
        cfg = model.metro_cfg(m, [], base, growth=own)
        self.assertAlmostEqual(growth.regional(cfg, "pop", 2050), 1.3)
        self.assertAlmostEqual(growth.regional(cfg, "jobs", 2050), 1.25)
        self.assertEqual(cfg["growth"]["capture"]["job_centers"]["jobs_share"], 0.0)
        cfg0 = model.metro_cfg(m, [], base)   # no registry growth: DFW's, as before
        self.assertEqual(cfg0["growth"]["regional_pop"], base["growth"]["regional_pop"])

    def test_future_years_run(self):
        from metro import generate
        out = os.path.join(self.tmp, "o")
        r = generate.generate("synthetic", out=out, metro=synthetic_metro(self.tmp), log=lambda *a: None,
                              future_years=[2050])
        f = r["model"]["future"][2050]["generated"]
        self.assertGreater(f["daily_trips"], r["model"]["generated"]["daily_trips"])   # the region grows
        with open(os.path.join(out, "report.md"), encoding="utf-8") as fh:
            self.assertIn("2050, every line open", fh.read())


class FullModelSelectionTests(unittest.TestCase):
    """metro/modelselect.py: the full model prunes the sketch's pool."""

    def test_prune_drops_lines_below_the_floor_and_orders_by_value(self):
        from metro import modelselect

        class C:
            def __init__(self, uid, capital):
                self.uid, self.capital, self.opex, self.status, self.reason, self.order = uid, capital, 0.0, "chosen", "", 0
        a, b, c = C("A", 1000), C("B", 1000), C("C", 1000)
        trips = {"A": 5000, "B": 2000, "C": 500}   # per $M: 5, 2, 0.5

        def fake_values(ctx, net, ids, year, procs=None, inputs=None, alone=None):
            for l in ids:
                alone[l] = trips[l]
            alone[None] = 0.0
            return {l: (trips[l], trips[l]) for l in ids}, 0.0, 0.0
        old, old_lu = modelselect.values, modelselect.land_use
        modelselect.values, modelselect.land_use = fake_values, lambda *a: None
        try:
            gp = {"selection": {"model": {"min_trips_per_musd": 1.0}}}
            cfg = {"staging": {"value_opex_years": 20}}
            kept, rounds = modelselect.prune([c, b, a], lambda cs: (None, {x.uid: x.uid for x in cs}), None, 1e9,
                                             gp, cfg, 2050, log=lambda *x: None)
            self.assertEqual([x.uid for x in kept], ["A", "B"])
            self.assertEqual((c.status, a.order, b.order), ("rejected", 1, 2))
            kept, _ = modelselect.prune([a, b], lambda cs: (None, {x.uid: x.uid for x in cs}), None, 1500,
                                        gp, cfg, 2050, log=lambda *x: None)
            self.assertEqual([x.uid for x in kept], ["A"])   # over budget: the lower value goes
        finally:
            modelselect.values, modelselect.land_use = old, old_lu

    def test_generate_with_full_model(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pyarrow not installed")
        from metro import generate
        tmp = tempfile.mkdtemp()
        try:
            r = generate.generate("synthetic", out=os.path.join(tmp, "o"), metro=synthetic_metro(tmp),
                                  log=lambda *a: None, future_years=[2050], full_model=True)
            self.assertEqual(r["model_select"]["year"], 2050)
            self.assertGreater(r["chosen"][0].model_trips, 0)
            with open(os.path.join(tmp, "o", "report.md"), encoding="utf-8") as f:
                self.assertIn("Chosen by the full model", f.read())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            from dfwt import osmroute
            osmroute.set_origin(32.8, -97.0)


class BranchRuleTests(unittest.TestCase):
    """metro/select.py: a candidate sharing a trunk is a branch if it runs branch_min_km on its own."""

    def test_branch_allowed_parallel_copy_rejected(self):
        from metro import select

        class Sk:   # the trunk carries the most
            def line(self, mode, st, *a, **k):
                return {"new_trips": 20000.0 if st[-1] == (20, 0) else 10000.0}

        class C:
            def __init__(self, uid, P, seq):
                self.uid, self.P, self.seq, self.kind, self.mode = uid, P, seq, "road", "brt"
                self.km = sum(math.dist(a, b) for a, b in zip(P, P[1:]))
                self.capital, self.opex, self.status, self.ratio = 1000.0, 0.0, "pool", 10.0
                self.station_xy = [P[0], P[-1]]
                self.along, self.pnr, self.pnr_cap, self.name, self.order = [], [], [], uid, None
        trunk = C("A", [(0, 0), (20, 0)], ("a", "b"))
        branch = C("B", [(0, 0), (12, 0), (12, 8)], ("a", "c"))          # 12 km on the trunk, 8 of its own
        copy_ = C("D", [(0, 0.3), (20, 0.3)], ("d", "e"))                 # 300 m beside the trunk all the way
        trunk.ratio, branch.ratio, copy_.ratio = 12.0, 11.0, 10.0
        gp = {"selection": {"min_trips_per_musd": 0.5, "max_lines": 10, "duplicate_m": 400, "duplicate_share": 0.5,
                            "branch_min_km": 5, "branch_share_m": 250}, "stations": {"transfer_m": 800}}
        chosen, spent = select.run([trunk, branch, copy_], Sk(), 1e9, gp, {"staging": {"value_opex_years": 20}}, [], [],
                                   log=lambda *a: None)
        self.assertEqual([c.uid for c in chosen], ["A", "B"])
        self.assertIn("a branch", branch.reason)
        self.assertTrue(copy_.reason.startswith("duplicate"))
        self.assertAlmostEqual(branch.cost_charged, 1000 * 8 / 20, delta=80)   # its own 8 of 20 km


class RouterTests(unittest.TestCase):
    """Phase 3: anchors, through-running, winding."""

    def test_winding_sees_a_staircase(self):
        from metro import through
        straight = [(0, 0), (10, 0)]
        stairs = []
        for k in range(10):
            stairs += [(k, k % 2 * 0.0 + (k // 1) * 0.0), (k, 1.0 if k % 2 else 0.0)]
        stairs = [(x * 0.5, y * 1.5) for x, y in [(i // 2, (i % 4 in (1, 2)) * 1) for i in range(40)]]
        self.assertLess(through.max_winding(straight), 1.01)
        self.assertGreater(through.max_winding(stairs), 1.5)

    def test_a_street_holds_two_brt_lines(self):
        from metro import select
        trunk = [(0, 0), (10, 0)]
        on_it = [[(0, 0.1), (6, 0.1)], [(2, -0.1), (10, -0.1)]]
        self.assertAlmostEqual(select.stacked_km(trunk, on_it, 0.25, 2), 4.0, delta=0.3)   # both share x 2..6
        self.assertEqual(select.stacked_km(trunk, on_it[:1], 0.25, 2), 0.0)               # one line: room for another
        apart = [[(0, 3), (10, 3)], [(0, -3), (10, -3)]]
        self.assertEqual(select.stacked_km(trunk, apart, 0.25, 2), 0.0)

    def test_angle_at_a_downtown(self):
        from metro import through

        class C:
            def __init__(self, x, y):
                self.x, self.y = x, y
        by = {"D": C(0, 0), "A": C(-5, 0), "B": C(5, 0.5), "N": C(0, 5)}
        self.assertGreater(through.angle_at(by, "D", "A", "B"), 170)
        self.assertAlmostEqual(through.angle_at(by, "D", "A", "N"), 90, delta=0.1)

    def test_turns_are_searched_not_filtered(self):
        """A to T: the shortest path turns 90 degrees at B; a longer one through C bends gently. The plain
        search finds only the sharp one (which the turn filter then drops); the edge-based one finds C's."""
        from metro import candidates

        class C:
            def __init__(self, x, y):
                self.x, self.y = x, y
        by = {"A": C(0, 0), "B": C(4, 0), "T": C(4, 4), "C": C(2.5, 1.0)}
        adj = {k: [] for k in by}
        for u, v, km in (("A", "B", 4.0), ("B", "T", 4.0), ("A", "C", 5.0), ("C", "T", 5.0)):
            adj[u].append((v, km, (u, v)))
            adj[v].append((u, km, (u, v)))
        plain = candidates._search("A", adj, 100)
        self.assertEqual(plain["T"][1], ["A", "B", "T"])
        turns = candidates._search_turns("A", adj, by, 100, 75, 1.5)
        self.assertEqual(turns["T"][1], ["A", "C", "T"])
        self.assertAlmostEqual(turns["T"][0], 10.0)          # route km, without the penalty
        gentle = candidates._search_turns("A", adj, by, 100, 120, 1.5)   # the 90-degree turn allowed: its penalty
        self.assertEqual(gentle["T"][1], ["A", "B", "T"])                # (1.5 km) is less than the 2 km detour

    def test_a_downtown_anchor_moves_the_downtown(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pyarrow not installed")
        from metro import anchors, centers, generate
        tmp = tempfile.mkdtemp()
        try:
            m = synthetic_metro(tmp)
            p = generate.params()["centers"]
            cs = centers.find(m, centers.Surface(m, p["grid_km"], p["kernel_km"]), p)
            centers.classify(m, cs, p)
            lat, lon = ll(20, 0)   # the smaller cluster
            anchors.apply(m, cs, [{"name": "City Hall", "lat": lat, "lon": lon, "kind": "downtown"}], p, log=None)
            down = [c for c in cs if c.kind == "downtown"]
            self.assertEqual(len(down), 1)
            self.assertAlmostEqual(down[0].x - float(m.xy(LAT0, LON0)[0]), 20, delta=1.5)
            lat, lon = ll(10, 6)   # nowhere near a center: a new one
            n = len(cs)
            anchors.apply(m, cs, [{"name": "Airport", "lat": lat, "lon": lon, "kind": "airport", "weight": 20000}], p, log=None)
            self.assertEqual(len(cs), n + 1)
            self.assertEqual(cs[-1].anchor, "airport")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            from dfwt import osmroute
            osmroute.set_origin(32.8, -97.0)


class LinePlanTests(unittest.TestCase):
    """metro/lineplan.py on a stand-in for the demand model: trips are a function of the line set."""

    def setUp(self):
        from metro import lineplan
        self._eval = lineplan._evaluate

    def tearDown(self):
        from metro import lineplan
        lineplan._evaluate = self._eval

    def _planner(self, trips_of, budget=1000.0, anchors=(), rounds=3, exact=0):
        from metro import lineplan

        class C:
            def __init__(self, uid, P, capital, ratio=1.0, mode="brt"):
                self.uid, self.P, self.capital, self.ratio, self.mode = uid, P, capital, ratio, mode
                self.kind, self.seq, self.routes, self.reason, self.status = "road", ("A", uid), {}, "", "pool"
                self.stops = [(0, P[0], None), (1, P[-1], None)]
                self.station_xy = [P[0], P[-1]]
                self.opex, self.peak_hour_load, self.order, self.headway = 0.0, 0.0, None, None

            @property
            def km(self):
                return 10.0
        cs = {u: C(u, P, cap) for u, P, cap in [("A1", [(0, 0), (10, 0)], 300), ("A2", [(0, 0.1), (10, 0.1)], 300),
                                                  ("B1", [(0, 5), (10, 5)], 300), ("X1", [(20, 20), (30, 20)], 300)]}
        cfg = {"staging": {"value_opex_years": 20}, "modes": {"brt": {"default_headway_min": 8, "vehicle_capacity": 100}}}
        gp = {"selection": {"model": {"min_trips_per_musd": 1.0}, "plan": {"rounds": rounds, "anchor_trips": 1000, "procs": 1,
                                                                        "exact_max_evals": exact}}}
        p = lineplan.Planner(list(cs.values()), None, None, cfg, gp, budget, 2050, None, {}, [], [],
                             anchors, [], None, log=lambda *a: None)
        lineplan._evaluate = lambda jobs, procs: {k: (trips_of(set(u)), 300.0 * len(u)) for k, u, _ in jobs}
        p.merges = lambda S, H: []
        return p, cs

    def test_drops_a_duplicate_and_adds_a_better_line(self):
        def trips(S):   # A1 and A2 run the same street: together worth one; B1 is worth 900 on its own
            return 1000 * bool(S & {"A1", "A2"}) + 900 * ("B1" in S)
        p, cs = self._planner(trips)
        out = {c.uid for c in p.run([cs["A1"], cs["A2"]])}
        self.assertIn("B1", out)
        self.assertEqual(len(out & {"A1", "A2"}), 1)   # one of the two, not both

    def test_budget_holds(self):
        p, cs = self._planner(lambda S: 1000 * len(S), budget=600.0)
        out = p.run([cs["A1"], cs["B1"]])
        self.assertLessEqual(len(out), 2)

    def test_the_exact_program_finds_what_one_move_at_a_time_cannot(self):
        def trips(S):   # B1 and X1 are worth nothing alone and 2,000 together (riders who change between them)
            return 700 * ("A1" in S) + 2000 * ({"B1", "X1"} <= S)
        p, cs = self._planner(trips)
        self.assertEqual({c.uid for c in p.run([cs["A1"]])}, {"A1"})           # adding either one alone loses J
        p, cs = self._planner(trips, exact=4096)
        self.assertEqual({c.uid for c in p.run([cs["A1"]])}, {"A1", "B1", "X1"})
        self.assertEqual(p.exact_result["subsets"], 16)   # every set of the 4 lines, the empty one too: all within 1.5 x the money
        self.assertFalse(p.exact_result["local_was_optimal"])

    def test_an_unserved_anchor_costs_enough_to_add_a_line(self):
        def trips(S):   # X1 carries little, but it is the only line to the airport
            return 1000 * ("A1" in S) + 100 * ("X1" in S)
        p, cs = self._planner(trips, anchors=[("Airport", "airport", 30.0, 20.0)])
        out = p.run([cs["A1"]])
        self.assertIn("X1", {c.uid for c in out})
        self.assertEqual(p.end["unserved"], [])


class AirportSpurTests(unittest.TestCase):
    """metro/spurs.py: a line ending near an airport terminal off the road graph gets a variant running on to it."""

    def test_a_spur_to_the_terminal(self):
        from metro import spurs

        class M:
            def ll(self, x, y):
                return 30.0 + y / 111.0, -97.0 + x / 96.0

        class C:
            def __init__(self, uid, seq, P, ratio):
                self.uid, self.seq, self.P, self.ratio = uid, seq, P, ratio
                self.mode, self.kind, self.status, self.mode_reason = "brt", "road", "pool", ""
                self.capital, self.opex, self.new_trips = 100.0, 1.0, 500.0

        class A:   # the center the airport anchor marks, 2.5 km from the terminal
            x, y = 0.0, 0.0
            anchor_list = [("Airport", "airport", 2.5, 0.0)]
        by = {}
        cands = [C("R1", ("C1", "C2"), [(-10.0, 0.0), (0.0, 0.0)], 2.0),     # ends at the airport's center
                 C("R2", ("C3", "C4"), [(0.0, 20.0), (0.0, 10.0)], 3.0)]      # nowhere near it
        made = []

        def make(seq):
            c = C(f"S{len(made) + 1}", seq, None, 0.0)
            made.append(c)
            return c

        def setup(c, mode, P):
            c.P, c.mode, c.capital, c.opex, c.new_trips = P, mode, 100.0, 1.0, 600.0
        gp = {"lines": {"airport_spur": {"enabled": True, "max_km": 4.0, "per_airport": 6}}}
        cfg = {"staging": {"value_opex_years": 20}, "cost_musd_per_km": {"brt": {"surface": 30, "elevated": 80}}}
        out = spurs.add(M(), cands, by, [A()], gp, cfg, make, setup, log=None)
        self.assertEqual(len(out), 1)
        v = out[0]
        self.assertEqual(v.seq[:2], ("C1", "C2"))
        self.assertEqual(by[v.seq[-1]].name, "Airport")
        self.assertAlmostEqual(v.P[-1][0], 2.5)
        self.assertAlmostEqual(v.capital, 100.0 + 2.5 * 50)   # the spur at the elevated premium


class BorderTests(unittest.TestCase):
    """metro/model.py add_border: crossers from Mexico join the commutes at their bridge, car-free."""

    def test_crossers_at_the_bridge(self):
        import numpy as np
        from dfwt import config, geo
        from metro import model

        class Z:
            pass
        z = Z()
        lat, lon = np.array([31.75, 31.80, 31.70]), np.array([-106.49, -106.40, -106.30])
        z.x, z.y = geo.Projector().xy(lat, lon)
        z.n, z.pop, z.jobs = 3, np.array([1000.0, 5000.0, 4000.0]), np.array([3000.0, 2000.0, 5000.0])

        class Ctx:
            pass
        ctx = Ctx()
        ctx.zones, ctx.od = z, np.array([[10.0, 20.0, 10.0], [50.0, 100.0, 50.0], [40.0, 40.0, 80.0]], dtype=np.float32)
        cfg = config.load()
        cfg["demand"]["total_commutes"] = 400.0
        cfg["demand"]["border"] = [{"port": "El Paso", "lat": 31.7486, "lon": -106.4869, "pedestrians_day": 1000,
                                    "bus_day": 100}]
        out = model.add_border(ctx, cfg)
        rc = cfg["ridership"]
        n = 1100 * 2 / (rc["round_trip"] / rc["work_share_of_transit_trips"] * rc["telework"])
        self.assertEqual(out[0][1], 0)                                   # the zone at the bridge
        self.assertAlmostEqual(float(ctx.od[0].sum()), 40.0 + n, places=2)   # spread like the zone's own commutes
        self.assertAlmostEqual(float(ctx.od[0, 1] / ctx.od[0, 0]), 2.0, places=3)
        self.assertAlmostEqual(cfg["demand"]["total_commutes"], 400.0 + n, places=3)
        self.assertGreater(z.carless_floor[0], 0.5)                      # mostly crossers, none with a car here
        self.assertEqual(float(z.carless_floor[1]), 0.0)
        model.add_border(ctx, cfg)                                       # a second call on the same cfg
        self.assertAlmostEqual(cfg["demand"]["total_commutes_residents"], 400.0)


class TerminalCostTests(unittest.TestCase):
    """candidates.terminal_cost: a line ending downtown pays for its terminal; a through line doesn't."""

    def test_downtown_ends_pay(self):
        from metro import candidates
        cfg = {"cost_musd_per_km": {"metro": {"surface": 140, "tunnel": 600}}}
        tc = {"enabled": True, "tail_km": 0.4, "turnback_musd": {"metro": {"tunnel": 50, "surface": 15}}}
        down, r = [(0.0, 0.0)], 1.5
        stub = [(0, (0.5, 0.0), None), (5, (5.5, 0.0), None)]               # ends downtown, in tunnel there
        through = [(0, (-5.0, 0.0), None), (5, (0.0, 0.0), None), (10, (5.0, 0.0), None)]
        self.assertAlmostEqual(candidates.terminal_cost(tc, cfg, "metro", stub, ["tunnel"], down, r), 0.4 * 600 + 50)
        self.assertEqual(candidates.terminal_cost(tc, cfg, "metro", through, ["surface", "surface"], down, r), 0.0)
        self.assertEqual(candidates.terminal_cost({"enabled": False}, cfg, "metro", stub, ["tunnel"], down, r), 0.0)
