"""Shared-track pieces for the web map (dfwt/bundle.py)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import bundle, osmroute  # noqa: E402
from dfwt.network import Network  # noqa: E402


def km(pts):
    return sum(math.dist(osmroute.xy(*a), osmroute.xy(*b)) for a, b in zip(pts, pts[1:])) / 1000


class BundleTests(unittest.TestCase):
    def test_parallel_lines_share_one_piece(self):
        # two 3 km lines 12 m apart, drawn in opposite directions, then one turns away
        a = [(-97.0, 32.80), (-97.0, 32.827)]
        b = [(-96.99987, 32.827), (-96.99987, 32.80), (-96.98, 32.79)]
        P = bundle.pieces([(0, "metro", "proposed", 2030, [(2030, a)]),
                           (1, "metro", "proposed", 2040, [(2040, b)])])
        shared = [(pts, u) for pts, u in P if len(u) == 2]
        self.assertEqual(sum(len(u) == 2 for _, u in P), len(shared))
        self.assertAlmostEqual(sum(km(p) for p, _ in shared), 3.0, delta=0.1)
        self.assertEqual([li for li, _ in shared[0][1]], [0, 1])          # priority order
        self.assertEqual({y for _, u in shared for _, y in u}, {2030, 2040})
        self.assertAlmostEqual(sum(km(p) for p, u in P if [li for li, _ in u] == [1]), 2.3, delta=0.2)

    def test_every_line_is_drawn_in_full(self):
        net = Network.load()
        lines = list(net.lines.values())
        P = bundle.pieces([(i, ln.mode, ln.status, ln.first_year, [(s.year, s.pts) for s in ln.segments])
                           for i, ln in enumerate(lines)])
        drawn = [0.0] * len(lines)
        for pts, users in P:
            for li, _ in users:
                drawn[li] += km(pts)
        for i, ln in enumerate(lines):
            self.assertGreater(drawn[i], 0.9 * ln.km - 0.3, ln.name)


if __name__ == "__main__":
    unittest.main()
