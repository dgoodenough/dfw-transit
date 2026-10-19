"""Land-use and parking policy levers: run each alone and in combination.

    OMP_NUM_THREADS=1 python tools/landuse_levers.py [--years 2050,2070,2100] [--out FILE] [lever ...]

Each lever is a set of config changes (growth.case, growth.tod, growth.capture,
ridership.parking_policy, access.pnr_spaces). Results are daily boardings (rail +
BRT; local buses are not modeled), population and jobs within 800 m of a station,
and how much growth the capture policy placed. Appends one JSON line per lever-year
to --out and prints a table.
"""
import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config  # noqa: E402
from dfwt.evaluate import Context, run_year  # noqa: E402
from dfwt.network import Network  # noqa: E402


def growth_low(c):
    c["growth"]["case"] = "low"


def growth_high(c):
    c["growth"]["case"] = "high"


def upzone(c):
    """Station-area upzoning toward Rosslyn-Ballston: 5x the default TOD response,
    and today's DART/TRE/TEXRail stations upzoned from 2030 (they get none by default)."""
    t = c["growth"]["tod"]
    t["pop_uplift"] = {"downtown": 1.5, "urban": 1.0, "suburban": 0.5}
    t["jobs_uplift"] = {"downtown": 0.75, "urban": 0.75, "suburban": 0.25}
    t["upzone_existing_year"] = 2030


def capture(c, share=0.4):
    """Steer growth to station areas: `share` of the population and job growth that
    would land outside them goes to station areas, up to MTSA / R-B densities."""
    k = c["growth"]["capture"]
    k["pop_share"] = share
    k["jobs_share"] = share


def capture25(c):
    capture(c, 0.25)


def capture60(c):
    capture(c, 0.6)


def cores(c):
    """15% of regional job growth to the five rail-served cores (Dallas CBD, Uptown,
    Dallas & Fort Worth Medical Districts, Fort Worth CBD)."""
    c["growth"]["capture"]["job_centers"]["jobs_share"] = 0.15


def pricing(c):
    """Parking prices double in real terms by 2050 in today's districts (fewer free and
    cheap spaces downtown); $8/day parking spreads to every place with >= 10,000 jobs
    per km2 within 800 m."""
    p = c["ridership"]["parking_policy"]
    p["price_growth"] = 1.0
    p["priced_centers"] = {"min_jobs_per_km2": 10000, "usd_per_day": 8}


def cashout(c):
    """Parking cash-out: $5/day in lieu of free parking, offered to half the commuters
    to job sites with >= 2,000 jobs per km2 (by 2050)."""
    c["ridership"]["parking_policy"]["cashout"] = {"min_jobs_per_km2": 2000, "usd_per_day": 5, "coverage": 0.5}


def garages(c):
    """Bigger park & ride garages: 4,000 spaces at line termini, 1,200 at commuter stations."""
    c["access"]["pnr_spaces"] = {"terminus": 4000, "commuter_station": 1200}


def garages_moderate(c):
    """Moderately bigger garages: 2,500 spaces at line termini, 600 at commuter stations."""
    c["access"]["pnr_spaces"] = {"terminus": 2500, "commuter_station": 600}


def capture_metro(c):
    """Growth capture (40%) focused on metro stations: commuter and BRT station areas
    get a much lower target density, so growth concentrates on the metro, Arlington-style."""
    capture(c, 0.4)
    c["growth"]["capture"]["mode_factor"] = {"metro": 1.0, "commuter": 0.3, "brt": 0.3}


LEVERS = {f.__name__: f for f in (growth_low, growth_high, upzone, capture, capture25, capture60,
                                  capture_metro, cores, pricing, cashout, garages, garages_moderate)}
LAND = ["upzone", "capture", "cores", "pricing", "cashout"]
COMBOS = {
    "package": LAND + ["garages"],
    "package_high": ["growth_high"] + LAND + ["garages"],
    "package_nogarage": LAND,
    "package_moderate": LAND + ["garages_moderate"],
    "package_moderate_high": ["growth_high"] + LAND + ["garages_moderate"],
}


def build_cfg(name):
    cfg = config.load()
    if name == "baseline":
        return cfg
    for part in COMBOS.get(name, name.split("+")):
        LEVERS[part](cfg)
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("levers", nargs="*", default=["baseline"])
    ap.add_argument("--years", default="2050,2070,2100")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    years = [int(y) for y in a.years.split(",")]
    for name in a.levers:
        cfg = build_cfg(name)
        ctx = Context(cfg)
        net = Network.load(None, cfg)
        for y in years:
            t0 = time.time()
            r = run_year(ctx, net, y)
            row = {"lever": name, "year": y, "boardings": round(r["daily_boardings"]),
                   "pop": round(r["pop"]), "jobs": round(r["jobs"]),
                   "pop_800m": round(r["pop_800m"]), "jobs_800m": round(r["jobs_800m"]),
                   "commuters": round(r["transit_commuters"]), "pnr": round(r["pnr_riders"]),
                   "full_garages": r["pnr_full_garages"], "per_trip": round(r["boardings_per_trip"], 2),
                   **{k: round(v) for k, v in r["capture"].items()}}
            print(json.dumps(row), f"({time.time() - t0:.0f}s)", flush=True)
            if a.out:
                with open(a.out, "a") as f:
                    f.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
