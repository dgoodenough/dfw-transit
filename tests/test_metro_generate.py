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
