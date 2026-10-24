"""Usage: PYTHONPATH=. python tools/diagram_preview.py OUT.html [--versions rail,brt,all] [--pickle DIR]

A quick preview of the map page after a change to the diagram (dfwt/schematic.py or its
templates), without the hour-long `python -m dfwt build`: the page is written by
webmap.write from the networks of the plan and every scenario in scenarios/ (as the build
loads them) and the evaluation tables already in results/<scenario>/ (no model run; the
trip planner's per-year results are left empty; stations the tables don't know, after a
rename or merge since they were written, get empty figures). Only the listed diagram versions are laid
out (default: rail, the one the page opens on); the page offers just those. --pickle DIR
also saves each version's Layout object (for analysis scripts) as DIR/<version>.pkl.

The page loads Leaflet from unpkg; offline, serve a local copy (route the request).
"""
import argparse
import csv
import os
import pickle
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, schematic, webmap  # noqa: E402
from dfwt.__main__ import scenarios  # noqa: E402
from dfwt.network import Network  # noqa: E402


def num(v):
    for f in (int, float):
        try:
            return f(v)
        except ValueError:
            pass
    return v


def rows(path):
    with open(path, encoding="utf-8") as f:
        return [{k: num(v) for k, v in r.items()} for r in csv.DictReader(f)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--versions", default="rail")
    ap.add_argument("--pickle")
    a = ap.parse_args()
    t = time.time()
    want = [v for v in a.versions.split(",") if v]
    schematic.VERSIONS = tuple(v for v in schematic.VERSIONS if v[0] in want)
    schematic.DEFAULT_VERSION = schematic.VERSIONS[0][0]
    if a.pickle:          # keep the Layout objects too
        os.makedirs(a.pickle, exist_ok=True)
        compute, keys = schematic.compute, iter([v[0] for v in schematic.VERSIONS])

        def keep(nets, log=None):
            lay = compute(nets, log=log)
            with open(os.path.join(a.pickle, next(keys) + ".pkl"), "wb") as f:
                pickle.dump(lay, f)
            print("  ", schematic.quality(lay), flush=True)
            return lay
        schematic.compute = keep
    nets, evals = {}, {}
    for key in ["plan"] + scenarios():
        nets[key] = Network.load(None if key == "plan" else key)
        d = config.path("results", key)
        yrs = rows(os.path.join(d, "years.csv"))
        # tables from an older build may name stations since merged or renamed: keep those the
        # network has, and give a station they lack empty figures
        st = [r for r in rows(os.path.join(d, "stations.csv")) if r["station_id"] in nets[key].stations]
        have = {r["station_id"] for r in st}
        st += [{**{k: 0 for k in st[0]}, "station_id": sid} for ln in nets[key].lines.values()
               for sid in dict.fromkeys(ln.stop_ids) if sid not in have and not have.add(sid)]
        evals[key] = {"years": yrs, "lines": rows(os.path.join(d, "lines.csv")), "stations": st,
                      "results": {r["year"]: {} for r in yrs}}
    webmap.write(nets, evals, a.out)
    print(f"wrote {a.out} in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
