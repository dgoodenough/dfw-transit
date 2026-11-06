"""Non-commute trips (config ridership.nonwork): trip tables, the off-peak network, and the
calibration that keeps today's totals."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, demand, evaluate, geo  # noqa: E402
from dfwt.graph import YearGraph  # noqa: E402
from dfwt.network import Network  # noqa: E402


def toy_zones(cfg):
    """Four zones on an east-west line through the DFW Airport generator."""
    pj = geo.Projector()
    x0, y0 = pj.xy(32.8998, -97.0403)

    class Z:
        n = 4
        ids = ["z0", "z1", "z2", "z3"]     # not in the sector file: the regional job mix
        pop = np.array([1000.0, 0, 3000, 2000])
        jobs = np.array([5000.0, 800, 100, 400])
        x = x0 + np.array([0.0, 4, 10, 25])
        y = np.full(4, y0)
        cong = 1.0

        def dist_rows(self, i0, i1):
            return np.abs(self.x[i0:i1, None] - self.x[None, :]).astype(np.float32)

        def drive_min(self, d):
            return demand.drive_minutes(self.cfg["drive"], d, self.cong)
    z = Z()
    z.cfg = cfg
    return z


class NonworkTripTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(config.load()["ridership"]["nonwork"]["enabled"])

    def test_trip_table_totals(self):
        cfg = config.load()
        nc = cfg["ridership"]["nonwork"]
        airport = next(g for g in nc["generators"] if g["name"] == "DFW Airport")
        nc["generators"] = [airport]
        z = toy_zones(cfg)
        od = demand.nonwork_od(z, cfg)
        rate = nc["trips_per_person"]
        self.assertAlmostEqual(od.sum() / (z.pop.sum() * (rate["hbo"] + rate["nhb"]) + airport["daily_trips"]), 1.0, places=3)
        # every trip from home: HBO + NHB productions + the generator's visitors, who come from homes
        hbo_nhb = od.sum() - airport["daily_trips"]
        self.assertGreater(hbo_nhb, 0)
        # the airport's trips land on its zone (the nearest, z0) and come from where people live
        nc["generators"] = []
        no_gen = demand.nonwork_od(z, cfg)
        extra = od - no_gen
        self.assertAlmostEqual(extra[:, 0].sum() / airport["daily_trips"], 1.0, places=3)
        self.assertAlmostEqual(float(extra[1].sum()), 0.0, places=3)   # nobody lives in z1

    def test_attractions_weigh_retail_more_than_basic_jobs(self):
        cfg = config.load()
        r = cfg["ridership"]["nonwork"]["attraction_rates"]
        for p in ("hbo", "nhb"):
            self.assertGreater(r[p]["retail"], r[p]["service"])
            self.assertGreater(r[p]["service"], r[p]["basic"])

    def test_nonwork_config_is_offpeak_and_leaves_the_commute_config_alone(self):
        cfg = config.load(scenario="two_million")
        c = demand.nonwork_cfg(cfg)
        nc = cfg["ridership"]["nonwork"]
        self.assertEqual(c["ridership"]["asc"], nc["asc"])
        self.assertEqual(c["ridership"]["telework"], 1.0)
        vr = nc["value_of_time_ratio"]   # time against money: in-vehicle and out-of-vehicle alike
        self.assertAlmostEqual(c["ridership"]["b_ivt_per_min"], cfg["ridership"]["b_ivt_per_min"] * vr)
        self.assertAlmostEqual(c["ridership"]["b_ovt_extra_per_min"] / c["ridership"]["b_ivt_per_min"],
                               cfg["ridership"]["b_ovt_extra_per_min"] / cfg["ridership"]["b_ivt_per_min"])
        nc["value_of_time_on"] = "cost"   # the other reading: money weighs more, time as for commutes
        c2 = demand.nonwork_cfg(cfg)
        self.assertAlmostEqual(c2["ridership"]["b_ivt_per_min"], cfg["ridership"]["b_ivt_per_min"])
        self.assertAlmostEqual(c2["ridership"]["b_per_dollar"], cfg["ridership"]["b_per_dollar"] / vr)
        nc["value_of_time_on"] = "time"
        self.assertIsNone(c["ridership"]["parking_policy"]["cashout"])
        hf = nc["offpeak_headway_factor"]["feeder"]
        self.assertAlmostEqual(demand.feeder_headway(c, 2040), demand.feeder_headway(cfg, 2040) * hf)
        self.assertNotEqual(cfg["ridership"]["asc"], nc["asc"])   # cfg untouched
        self.assertEqual(cfg["ridership"]["telework"], config.load()["ridership"]["telework"])
        # venues charge their own parking, at a price the parking policy doesn't raise
        dfw = c["ridership"]["paid_parking"]["generator: DFW Airport"]
        self.assertTrue(dfw["fixed"])
        self.assertNotIn("generator: DFW Airport", cfg["ridership"]["paid_parking"])
        z = demand.nonwork_zones(demand.Zones(cfg), cfg)
        z.year, z.tod_key = 2060, "test-2060"   # the 2M plan's parking prices have doubled by then
        i = demand.generator_zones(z, next(g for g in nc["generators"] if g["name"] == "DFW Airport"))[0][0]
        self.assertAlmostEqual(float(z.parking_usd()[0][i]), dfw["usd_per_day"])

    def test_offpeak_headways_lengthen_waits(self):
        net = Network.load()
        peak, off = YearGraph(net, 2025), YearGraph(net, 2025, headway_factor={"metro": 1.5, "commuter": 2.0})
        same = YearGraph(net, 2025, headway_factor=1.0)
        for g in (peak, off, same):
            g.skim()
        ok = np.isfinite(peak.T)
        self.assertTrue(np.all(off.T[ok] >= peak.T[ok] - 1e-4))
        self.assertGreater(float(off.T[ok].mean()), float(peak.T[ok].mean()))
        np.testing.assert_allclose(same.T[ok], peak.T[ok])

    def test_pinned_generator_moves_its_zone_for_nonwork_only(self):
        cfg = config.load()
        z = demand.Zones(cfg)
        zo = demand.nonwork_zones(z, cfg)
        g = next(g for g in cfg["ridership"]["nonwork"]["generators"] if g.get("pin"))
        i = demand.generator_zones(z, g)[0][0]
        x, y = geo.Projector().xy(g["lat"], g["lon"])
        self.assertAlmostEqual(float(zo.x[i]), float(x), places=6)
        self.assertNotAlmostEqual(float(z.x[i]), float(x), places=3)


class NonworkCalibrationTests(unittest.TestCase):
    def test_today_keeps_its_total_and_work_share(self):
        """With the switch on, the calibrated constants give today's rail boardings and the
        surveyed work share (re-run evaluate.calibrate_nonwork after changing the component)."""
        net = Network.load()
        cfg = config.load()
        cfg["ridership"]["nonwork"]["enabled"] = True
        cal = cfg["ridership"]["calibration"]
        r = evaluate.run_year(evaluate.Context(cfg), net, cal["year"])
        self.assertAlmostEqual(r["daily_trips"], r["work_trips"] + r["nonwork_trips"], places=3)
        self.assertLess(abs(r["daily_boardings"] / cal["rail_boardings"] - 1), 0.03)
        self.assertLess(abs(r["work_share"] - cfg["ridership"]["nonwork"]["calibration"]["work_share"]), 0.02)


if __name__ == "__main__":
    unittest.main()
