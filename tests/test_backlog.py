"""Small backlog pass (after v2.14): clock-time skims, shared-track notes, off-street bus stops,
co-located platforms."""
import copy
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import despur  # noqa: E402
from dfwt import validate, webmap  # noqa: E402
from dfwt.graph import YearGraph  # noqa: E402
from dfwt.network import Network  # noqa: E402


class BacklogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = Network.load("two_million")

    def test_clock_skim_drops_only_perceived_extras(self):
        g = YearGraph(self.net, 2050)
        g.skim()
        T, Tc = g.T, g.T_clock
        both = np.isfinite(T) & np.isfinite(Tc)
        self.assertTrue(both.any())
        self.assertTrue((Tc[both] <= T[both] + 1e-3).all())     # perceived >= clock
        self.assertTrue(np.isinf(np.diag(Tc)).all())             # a trip must ride

    def test_shared_track_note_for_fw_pink(self):
        names = {k: v.name for k, v in self.net.stations.items()}
        notes = {names[s]: v for s, v in webmap.shared_track(self.net).items()}
        self.assertIn(["FW Pink", "FW Orange", 2035], notes.get("Stockyards Main", []))

    def test_no_bus_doubles_back_to_a_stop_it_could_reach_on_its_street(self):
        tables, _ = Network.read_tables("two_million")
        t = {k: copy.deepcopy(tables[k]) for k in ("stations.csv", "lines.csv", "line_stops.csv", "line_segments.csv")}
        self.assertEqual(despur.fix_tables(t["stations.csv"], t["lines.csv"], t["line_stops.csv"],
                                           t["line_segments.csv"], log=None), 0)

    def test_detour_is_found_and_trimmed(self):
        # a bus runs east on a street, out 300 m north to a stop, back, and on east
        A = [(-97.0, 32.0), (-96.99, 32.0), (-96.99, 32.0027)]
        B = [(-96.99, 32.0027), (-96.99, 32.0), (-96.98, 32.0)]
        self.assertEqual(despur.detour(A, B), (1, 1))

    def test_co_located_platforms_are_flagged(self):
        net = copy.deepcopy(self.net)
        ln = next(l for l in net.lines.values() if l.mode == "brt" and len(l.stop_ids) > 3)
        sid = ln.stop_ids[1]
        s = net.stations[sid]
        twin = copy.copy(s)
        twin.id = sid + "_twin"
        twin.lat += 0.0002   # about 22 m
        net.stations[twin.id] = twin
        ln.stop_ids[2] = twin.id
        codes = {(f[1]) for f in validate.run(net)}
        self.assertIn("CO_LOCATED", codes)


if __name__ == "__main__":
    unittest.main()
