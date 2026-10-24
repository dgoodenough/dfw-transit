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
    from dfwt.__main__ import scenarios as built
    return built()


RAIL = dict((k, m) for k, _, m in schematic.VERSIONS)["rail"]


class SchematicLayoutTests(unittest.TestCase):
    """The default version of the diagram (Rail), laid out over every scenario."""
    @classmethod
    def setUpClass(cls):
        cls.raw = {sc or "plan": Network.load(sc) for sc in [None] + scenarios()}
        cls.nets = schematic.version_nets(cls.raw, RAIL)
        cls.lay = schematic.compute(cls.nets)
        cls.js = schematic.to_json(cls.lay)

    def test_versions_lay_out_only_their_modes(self):
        for key, _, modes in schematic.VERSIONS:
            nets = schematic.version_nets(self.raw, modes)
            for k, net in nets.items():
                if modes is None:      # All: rail and the plan's BRT (diagram_nets)
                    self.assertEqual(set(net.lines), set(schematic.diagram_nets(self.raw)[k].lines))
                else:
                    self.assertEqual(set(net.lines), {l for l, ln in self.raw[k].lines.items() if ln.mode in modes})
        self.assertIn(schematic.DEFAULT_VERSION, [k for k, _, _ in schematic.VERSIONS])

    def test_lines_are_straight(self):
        # the straightness rules: few bends and fewer zig-zags per line, no new crossings
        q = schematic.quality(self.lay)
        n = sum(1 for (k, _) in self.lay.paths if k in (self.lay.default, "plan"))
        self.assertLess(q["bends"] / n, 6.0, q)
        self.assertLess(q["zigzags"] / n, 2.0, q)
        # (edge against edge: a crossing that moves one station along in the drawing counts as a
        # new one; merged interchanges took a dozen of the geography's own away)
        self.assertLessEqual(q["crossings"], q["geo_crossings"] + 12, q)

    def test_every_walk_link_is_in_the_page_and_only_short_ones_are_drawn(self):
        # every transfer pair the model walks (within the walk radius, or in transfers.csv)
        # that the layout keeps as two nodes is in the page's data; one longer than
        # CONNECTOR_MAX on the diagram is flagged far, and the page draws only the others (a
        # far one just faintly around the station selected or hovered)
        self.assertEqual(sorted(tuple(t[:2]) for t in self.js["transfers"]), sorted(self.lay.transfers))
        for a, b, far, _ in self.js["transfers"]:
            d = math.hypot(self.lay.nodes[a]["x"] - self.lay.nodes[b]["x"], self.lay.nodes[a]["y"] - self.lay.nodes[b]["y"])
            self.assertEqual(far, int(d > schematic.CONNECTOR_MAX))
        with open(os.path.join(os.path.dirname(schematic.__file__), "templates", "schematic.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("if (!A || !B || far) continue;", js)                # draw(): connectors for short links only
        self.assertIn("if (!far || (a !== v && b !== v)) continue;", js)   # walks(): the far ones of one station

    def stations(self):
        st = {}
        for net in self.nets.values():
            st.update(net.stations)
        return st

    def test_same_place_interchanges_are_one_node(self):
        # walk transfers a short way apart are one interchange: Akard and Metro Center (the
        # Orange Line's stop moved a block in the 2-million plan) are one node, and a merged
        # group of different names spans no more than MERGE_WALK_KM
        from dfwt import geo
        st, proj = self.stations(), geo.Projector()
        sid = {s.name: k for k, s in st.items()}
        self.assertEqual(self.lay.node_of[sid["Akard"]], self.lay.node_of[sid["Metro Center"]])
        for nd in self.lay.nodes:
            if len({schematic._norm_name(st[s].name) for s in nd["sids"]}) > 1:
                pts = [np.array(proj.xy(st[s].lat, st[s].lon)) for s in nd["sids"]]
                self.assertLessEqual(max(np.linalg.norm(p - q) for p in pts for q in pts), schematic.MERGE_WALK_KM + 1e-9, nd["name"])
        # never two stops of one routing in one node
        for (key, lid), (path, stop_at) in self.lay.paths.items():
            stops = [path[i] for i in stop_at]
            self.assertTrue(all(u != w for u, w in zip(stops, stops[1:])), (key, lid))

    def test_fort_worth_main_terminal_to_la_gran_plaza_runs_straight_south(self):
        # the owner: "the line to La Gran Plaza should go straight north/south and not
        # deviate". FW Pink (F04) runs Main / Terminal (by Meacham airport) - downtown - La
        # Gran Plaza, almost due south in the real geography: every drawn piece points south,
        # all on one vertical
        path, stop_at = self.lay.paths[(self.lay.default, "F04")]
        names = [self.lay.nodes[path[i]]["name"] for i in stop_at]
        i, j = stop_at[names.index("Main / Terminal")], stop_at[names.index("La Gran Plaza")]
        ds = schematic.drawn_dirs(self.lay, path[i:j + 1])
        self.assertEqual({d for d, _ in ds}, {6}, ds)
        self.assertLess(np.ptp([self.lay.nodes[v]["x"] for v in path[i:j + 1]]), 1e-6)

    def test_no_line_doubles_back_at_a_station(self):
        # no line of the default plan or the plan is drawn turning straight back (180
        # degrees) at a station, hardly any by 135, and the SH-114 Line not at all (it used
        # to at John W Carpenter / Freeport and Parkridge)
        turns = schematic.sharp_turns(self.lay, {self.lay.default, "plan"})
        self.assertEqual([t for t in turns if t[3] == 180], [], turns)
        self.assertLessEqual(len(turns), 3, turns)
        self.assertEqual([t for t in turns if t[1] == "XP01"], [], turns)

    def test_airport_lines_keep_their_real_order(self):
        # DFW Airport North is drawn north of Terminal B (the Silver Line and TEXRail run up
        # from one to the other), and the SH-114 Line's stops from John W Carpenter / Freeport
        # through DFW Airport North to Grapevine run east to west as they really do
        self.assertGreater(self.node("DFW Airport North")["y"], self.node("DFW Airport Terminal B")["y"])
        path, stop_at = self.lay.paths[(self.lay.default, "XP01")]
        names = [self.lay.nodes[path[i]]["name"] for i in stop_at]
        xs = [self.lay.nodes[path[i]]["x"] for i in stop_at]
        a, b = names.index("John W Carpenter / Freeport"), names.index("Grapevine-Main Street")
        self.assertTrue(all(x0 > x1 for x0, x1 in zip(xs[a:b + 1], xs[a + 1:b + 1])), list(zip(names[a:b + 1], xs[a:b + 1])))

    def test_walk_linked_stations_are_pulled_together(self):
        # most walk transfers end up together: one interchange node (stations a short walk
        # apart are merged), or, for pairs within the walk radius kept as two nodes, near the
        # distance they are pulled to
        q = schematic.quality(self.lay)
        close = [t for t in self.lay.transfers if schematic._walk_pair(self.lay, *t)]
        st = {}
        for net in self.nets.values():
            st.update(net.stations)
        merged = [nd for nd in self.lay.nodes if len({schematic._norm_name(st[s].name) for s in nd["sids"]}) > 1]
        self.assertTrue(close and merged)
        self.assertLessEqual(q["apart"], (len(close) + len(merged)) / 4, q)

    def test_area_names_stand_beside_their_core_station(self):
        X = np.array([[n["x"], n["y"]] for n in self.lay.nodes])
        names = {t for t, _, _, _ in self.lay.labels}
        self.assertIn("Fort Worth", names)
        self.assertIn("Dallas", names)
        for t, x, y, kind in self.lay.labels:
            self.assertEqual(kind, "city")
            self.assertLess(np.linalg.norm(X - (x, y), axis=1).min(), 1e-9, t)

    def test_all_version_is_named_for_what_it_shows(self):
        label = dict((k, l) for k, l, _ in schematic.VERSIONS)["all"]
        self.assertNotEqual(label.lower(), "all")
        self.assertIn("BRT", label)

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
        # and grouping is complete: close stations with the same base name always share a label
        for a in range(len(nodes)):
            for b in range(a + 1, len(nodes)):
                A, B = nodes[a], nodes[b]
                if schematic.base_name(A["name"]).lower() == schematic.base_name(B["name"]).lower() and \
                        math.hypot(A["x"] - B["x"], A["y"] - B["y"]) <= schematic.LABEL_GROUP:
                    self.assertEqual(lead[a], lead[b], f"{A['name']} / {B['name']}")

    def test_waterways_extract_is_small_and_complete(self):
        path = config.path("data", "waterways.geojson")
        self.assertLess(os.path.getsize(path), 300 * 1024)
        with open(path, encoding="utf-8") as f:
            names = {ft["properties"]["name"] for ft in json.load(f)["features"]}
        for n in ("Trinity River", "West Fork Trinity River", "Elm Fork Trinity River", "Lewisville Lake", "White Rock Lake"):
            self.assertIn(n, names)
        self.assertTrue(self.lay.water["rivers"] and self.lay.water["lakes"])


def _toy(nodes, edges, paths, geo=None):
    """A Layout by hand: nodes [(x, y)] (also the geography unless geo is given), edges
    [(a, b)], paths {line: [nodes]} (all in the default plan)."""
    lay = schematic.Layout()
    for i, (x, y) in enumerate(nodes):
        g = np.array(geo[i] if geo else (x, y), float)
        lay.nodes.append({"sids": [str(i)], "name": str(i), "geo": g, "x": float(x), "y": float(y)})
    for a, b in edges:
        a, b = min(a, b), max(a, b)
        lay.eidx[(a, b)] = len(lay.edges)
        lay.edges.append({"a": a, "b": b, "lines": sorted(l for l, p in paths.items() if any({a, b} == {u, w} for u, w in zip(p, p[1:]))),
                          "bend": None})
    lay.paths = {("plan", l): (p, list(range(len(p)))) for l, p in paths.items()}
    lay.seqs = [("plan", l, p) for l, p in sorted(paths.items())]
    lay.default, lay.prime = "plan", set(range(len(lay.edges)))
    lay.termini = {p[i] for p in paths.values() for i in (0, -1)}
    return lay


class SchematicRuleTests(unittest.TestCase):
    """The straightness rules on small made-up networks."""

    def test_turn_dp_irons_out_a_wiggle_but_keeps_a_real_turn(self):
        # each edge leans a little off east, alternately north and south: one straight run
        un = np.array([[0.0 if d == (1 if k % 2 else 0) else 0.3 for d in range(8)] for k in range(8)])
        self.assertEqual(len(set(schematic._turn_dp(un))), 1)
        # five edges east, then five north: the line turns once, to north
        un = np.array([[0.0 if d == (0 if k < 5 else 2) else 2.0 for d in range(8)] for k in range(10)])
        dirs = schematic._turn_dp(un)
        self.assertEqual(dirs[:4], [0] * 4)
        self.assertEqual(dirs[-4:], [2] * 4)

    def test_turn_dp_pays_for_zigzags(self):
        # a jog that saves a little deviation is not worth two turns and the zig-zag
        un = np.zeros((7, 8)) + 1.0
        un[:, 0] = 0.0
        un[3, 0], un[3, 1] = 0.9, 0.0
        self.assertEqual(schematic._turn_dp(un), [0] * 7)

    def test_stroke_axis(self):
        t = np.linspace(0, 10, 11)
        k, stray = schematic.stroke_axis(np.stack([0.3 * np.sin(t), -t], 1))   # north-south, wiggling
        self.assertEqual(k, 2)
        self.assertLess(stray, schematic.AXIS_TOL)
        k, stray = schematic.stroke_axis(np.stack([t, t + 0.1 * np.cos(t)], 1))
        self.assertEqual(k, 1)

    def test_strokes_run_straight_through_junctions(self):
        # a trunk 0-1-2-3-4 (two lines) crossed at 2 by a branch line 5-2-6
        nodes = [(0, 4), (0, 3), (0, 2), (0, 1), (0, 0), (-1, 2), (1, 2)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (5, 2), (2, 6)]
        lay = _toy(nodes, edges, {"T1": [0, 1, 2, 3, 4], "T2": [0, 1, 2, 3, 4], "B": [5, 2, 6]})
        inc, _, _ = schematic._chains(lay)
        strokes, _ = schematic._strokes(lay, inc, np.array(nodes, float))
        self.assertIn(sorted([0, 1, 2, 3, 4]), [sorted(n) for n, _ in strokes])
        self.assertIn(sorted([5, 2, 6]), [sorted(n) for n, _ in strokes])

    def test_smooth_lays_a_trunk_on_its_axis(self):
        # a north-south trunk (two lines) that drifts east by 22 degrees in its middle, and
        # a branch leaving it at 2 to the west-north-west
        geo = [(0, 8), (0.2, 6), (1.0, 4), (1.8, 2), (2.0, 0), (2.1, -2), (-2, 3.4), (-5, 4.5)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (2, 6), (6, 7)]
        lay = _toy(geo, edges, {"T1": [0, 1, 2, 3, 4, 5], "T2": [0, 1, 2, 3, 4, 5], "B": [7, 6, 2]})
        A = np.array(geo, float)
        inc, _, _ = schematic._chains(lay)
        strokes, _ = schematic._strokes(lay, inc, A)
        X, axes = schematic._smooth(lay, A, A, strokes)
        for a, b in zip(range(5), range(1, 6)):        # every trunk edge is north-south now
            v = X[b] - X[a]
            self.assertLess(abs(v[0]), 0.1 * abs(v[1]), (a, b, v))
            self.assertLess(v[1], 0)                    # and still runs south (no station swapped)
            self.assertEqual(axes.get(lay.eidx[(a, b)]), 2)

    def test_crossing_count(self):
        # an X of two segments crosses once; segments sharing a station never count
        P = np.array([(0, 0), (2, 2), (0, 2), (2, 0), (1, 3)], float)
        self.assertEqual(schematic._n_crossings(P, np.array([0, 2]), np.array([1, 3])), 1)
        self.assertEqual(schematic._n_crossings(P, np.array([0, 0]), np.array([1, 4])), 0)

    def test_kinks_find_a_v_and_turn_it_halfway(self):
        # south-east, north-east for one edge, south-east again: a V whose middle edge is
        # turned to east; a 45-degree jog is turned straight back
        nodes = [(0, 2), (1, 1), (2, 2), (3, 1), (4, 0)]
        lay = _toy(nodes, [(0, 1), (1, 2), (2, 3), (3, 4)], {"L": [0, 1, 2, 3, 4]})
        dirs = {0: 7, 1: 1, 2: 7, 3: 7}
        self.assertEqual(schematic._kinks(lay, dirs), [([(1, 1)], 0)])
        self.assertLess(schematic._turn_cost(lay, dirs, {}, [1], {1: 0}), schematic._turn_cost(lay, dirs, {}, [1], {}))
        dirs = {0: 0, 1: 1, 2: 0, 3: 0}
        self.assertEqual(schematic._kinks(lay, dirs), [([(1, 1)], 0)])

    def test_a_ring_runs_on_through_where_it_closes(self):
        # a loop 0-1-2-3-0 (its stop list ends where it starts): one node per station, and the
        # line runs straight through station 0 like any other
        nodes = [(0, 0), (2, 0), (2, 2), (0, 2)]
        lay = _toy(nodes, [(0, 1), (1, 2), (2, 3), (3, 0)], {"R": [0, 1, 2, 3, 0]})
        self.assertEqual(len(lay.nodes), 4)
        passes = schematic._passes(lay)
        self.assertIn((lay.eidx[(0, 1)], lay.eidx[(0, 3)]), passes[0])
        for v in range(1, 4):
            self.assertEqual(len(passes[v]), 1)

    def test_line_turns_counts_bends_and_zigzags(self):
        # east, a 45 degree jog north-east, east again: two bends, one zig-zag
        nodes = [(0, 0), (2, 0), (3, 1), (5, 1), (7, 1)]
        lay = _toy(nodes, [(0, 1), (1, 2), (2, 3), (3, 4)], {"L": [0, 1, 2, 3, 4]})
        self.assertEqual(schematic.line_turns(lay, [0, 1, 2, 3, 4]), (2, 1, 0))
        # east then north (a real turn): one bend, no zig-zag
        nodes = [(0, 0), (2, 0), (4, 0), (4, 2), (4, 4)]
        lay = _toy(nodes, [(0, 1), (1, 2), (2, 3), (3, 4)], {"L": [0, 1, 2, 3, 4]})
        self.assertEqual(schematic.line_turns(lay, [0, 1, 2, 3, 4]), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
