"""The map's data layers (dfwt/layers.py): area shapes and the per-plan files."""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import layers  # noqa: E402


def inside(poly, x, y):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[-1:] + poly[:-1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


class Zones:
    """A few points in km, as demand.Zones has them."""
    def __init__(self, n=60, seed=1):
        r = np.random.default_rng(seed)
        self.x, self.y = r.uniform(-10, 10, n), r.uniform(-10, 10, n)
        self.n = n


class CellTests(unittest.TestCase):
    def test_a_point_lies_in_the_cell_of_its_nearest_centre(self):
        z = Zones()
        polys, areas = layers.cells(z.x, z.y)
        r = np.random.default_rng(2)
        for px, py in r.uniform(-8, 8, (300, 2)):
            near = int(np.argmin((z.x - px) ** 2 + (z.y - py) ** 2))
            hits = [i for i, p in enumerate(polys) if inside(p, px, py)]
            self.assertEqual(hits, [near])
        self.assertTrue((areas > 0).all())

    def test_a_lone_point_gets_the_capped_disc(self):
        polys, areas = layers.cells(np.array([0.0, 100.0]), np.array([0.0, 0.0]))
        disc = 0.5 * layers.CIRCLE * layers.MAX_R_KM ** 2 * np.sin(2 * np.pi / layers.CIRCLE)
        self.assertAlmostEqual(areas[0], disc, places=6)


class WriteTests(unittest.TestCase):
    def test_values_round_trip_through_the_plan_file(self):
        z = Zones(12)
        rng = np.random.default_rng(3)
        res = {}
        for y in (2025, 2030, 2035):
            res[y] = {"zone": {"pop": rng.uniform(0, 5000, z.n), "jobs": rng.uniform(0, 3000, z.n),
                               "reach": rng.uniform(0, 4e5, z.n), "beats": rng.uniform(0, .6, z.n)}}
        res[2026] = {}   # a year the layers don't keep
        with tempfile.TemporaryDirectory() as d:
            meta = layers.write(z, {"plan": {"results": res}}, d)
            src = open(os.path.join(d, "plan.js"), encoding="utf-8").read()
            self.assertTrue(os.path.exists(os.path.join(d, "zones.js")))
        self.assertEqual(meta["years"], [2025, 2030, 2035])
        self.assertEqual(meta["plans"], ["plan"])
        obj = json.loads(src[src.index("] = ") + 4:src.rindex(";")])
        pop = np.cumsum(np.array(obj["pop"]), axis=0) * 10   # changes from the year before, in tens
        self.assertTrue(np.allclose(pop[2], res[2035]["zone"]["pop"], atol=5))
        beats = np.cumsum(np.array(obj["beats"]), axis=0)
        self.assertTrue(np.allclose(beats[1], res[2030]["zone"]["beats"] * 100, atol=0.5))

    def test_kept_years(self):
        cfg = {"years": list(range(2025, 2101))}
        kept = [y for y in cfg["years"] if layers.keep(cfg, y)]
        self.assertEqual(kept[:3], [2025, 2030, 2035])
        self.assertEqual(kept[-1], 2100)


if __name__ == "__main__":
    unittest.main()
