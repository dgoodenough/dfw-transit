"""Access-lever experiments on the ridership model (config.access).

    OMP_NUM_THREADS=1 python tools/access_levers.py recal F F_feed15 F_garage_sel F_pkg ...
    OMP_NUM_THREADS=1 python tools/access_levers.py F_pnrmin:2070      (only some years)

Each variant edits a copy of config.access / ridership, runs 2050, 2070 and 2100,
and appends one JSON line to access_levers.jsonl in the current directory.

"F" is the corrected framework the levers are measured against: today's local buses
as 30-minute feeders where activity density >= 2,000/km2 (from 2025), riders a full
garage turns away fall back to walking or the bus (access.pnr_overflow_fallback),
and the asc recalibrated so 2025 still carries ~80k rail boardings. Run "recal"
first: it calibrates that asc and stores it for the F variants.
"""
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config  # noqa: E402
from dfwt.evaluate import Context, calibrate_asc, run_year  # noqa: E402
from dfwt.network import Network  # noqa: E402

OUT = "access_levers.jsonl"
YEARS = [2050, 2070, 2100]
UP15 = {"2025": 30, "2030": 15}


def feeder(a, table, dens=2000):
    a["feeder"].update({"enabled": True, "headway_min": table, "min_density_per_km2": dens})


def bigger_garages(a):
    a["pnr_spaces"] = {"terminus": 3000, "commuter_station": 800}


def suburban(a):
    a["pnr_suburban"]["enabled"] = True   # selected suburban metro stations (config defaults)


def bike(a, km=3, kmh=14):
    a["micromobility"].update(enabled=True, max_km=km, speed_kmh=kmh)


def kiss(a):
    a["kiss_ride"]["enabled"] = True


def walk(a):
    a["walk_max_m"] = 1600       # second entrances, through-block paths
    a["walk_circuity"] = 1.15    # connected street grid


def stored_asc(name="recal"):
    if os.path.exists(OUT):
        for line in open(OUT):
            r = json.loads(line)
            if r["variant"] == name:
                return r["asc"]
    raise SystemExit(f"run {name} first")


def F(a, r, table=None, dens=2000):
    feeder(a, table or {"2025": 30}, dens)
    a["pnr_overflow_fallback"] = True
    r["asc"] = stored_asc()


VARIANTS = {
    "base": lambda a, r: None,
    "fallback": lambda a, r: a.update(pnr_overflow_fallback=True),          # not recalibrated
    "F": lambda a, r: F(a, r),
    "F_feed15": lambda a, r: F(a, r, UP15),
    "F_feed10": lambda a, r: F(a, r, {"2025": 30, "2030": 10}),
    "F_garage_big": lambda a, r: (F(a, r), bigger_garages(a)),
    "F_garage_sel": lambda a, r: (F(a, r), suburban(a)),
    "F_bike": lambda a, r: (F(a, r), bike(a)),
    "F_bike5": lambda a, r: (F(a, r), bike(a, 5, 15)),
    "F_kiss": lambda a, r: (F(a, r), kiss(a)),
    "F_walk": lambda a, r: (F(a, r), walk(a)),
    "F_pnrmin": lambda a, r: (F(a, r), a.update(pnr_min_km=1.2)),           # not recalibrated
    "F_access_pkg": lambda a, r: (F(a, r, UP15), bike(a, 5, 15), walk(a), kiss(a)),
    "F_pkg": lambda a, r: (F(a, r, UP15), suburban(a), bike(a, 5, 15), walk(a), kiss(a)),
}


def main():
    base_cfg = config.load()
    ctx = Context(copy.deepcopy(base_cfg))
    for arg in sys.argv[1:]:
        name, _, ys = arg.partition(":")
        years = [int(y) for y in ys.split(",")] if ys else YEARS
        cfg = ctx.cfg
        for key in ("access", "ridership", "drive"):
            cfg[key] = copy.deepcopy(base_cfg[key])
        net = Network.load(None, cfg)
        rec = {"variant": name}
        t0 = time.time()
        if name in ("recal", "recal_fb"):      # recal: feeders from 2025 + fallback; recal_fb: fallback only
            if name == "recal":
                feeder(cfg["access"], {"2025": 30})
            cfg["access"]["pnr_overflow_fallback"] = True
            rec["asc"] = calibrate_asc(ctx, net, lo=-2.5, hi=-0.5, log=print)
            years = [2025]
        elif name.startswith("nocong"):          # nocong: base without congestion; nocong_F: F without
            cfg["drive"]["congestion"]["cap"] = 0.0
            if name == "nocong_F":
                F(cfg["access"], cfg["ridership"])
        else:
            VARIANTS[name](cfg["access"], cfg["ridership"])
            rec["asc"] = cfg["ridership"]["asc"]
        for y in years:
            r = run_year(ctx, net, y)
            row = {k: r[k] for k in ("daily_boardings", "daily_trips", "transit_commuters", "competitive_commutes",
                                      "boardings_per_trip", "pnr_riders", "pnr_demand", "pnr_full_garages",
                                      "pnr_spaces", "feeder_boardings", "riders_by_access")}
            row["stations"] = r["graph"].n_st
            rec[str(y)] = row
            print(f"{name} {y}: boardings {r['daily_boardings']:,.0f}  feeder bus {r['feeder_boardings']:,.0f}  "
                  f"P&R {r['pnr_riders']:,.0f}/{r['pnr_demand']:,.0f} full {r['pnr_full_garages']} "
                  f"spaces {r['pnr_spaces']:,.0f} access {({k: round(v) for k, v in r['riders_by_access'].items()})}",
                  flush=True)
        rec["secs"] = round(time.time() - t0)
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
