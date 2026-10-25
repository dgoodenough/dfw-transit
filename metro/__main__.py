"""Command line.

  python -m metro list
  python -m metro fetch houston                       every default stage
  python -m metro fetch houston --only zones,gtfs     some stages
  python -m metro fetch houston --jobs-proxy places   also the (labelled) Overture places proxy
  python -m metro fetch houston --force               re-download cached raw files
"""
import argparse
import sys

from . import fetch


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m metro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="metros in the registry")
    f = sub.add_parser("fetch", help="gather a metro's inputs into data/metros/<id>/")
    f.add_argument("metro")
    f.add_argument("--only", help=f"comma-separated stages: {','.join(fetch.STAGES)}")
    f.add_argument("--force", action="store_true", help="re-download files already in raw/")
    f.add_argument("--lodes-year", type=int, help="LODES year (default: newest available)")
    f.add_argument("--overture-release", help=f"Overture release (default {fetch.overture.RELEASE}, as DFW)")
    f.add_argument("--jobs-proxy", choices=["places"],
                   help="also count Overture places per block group (zones_places_proxy.csv); off by default")
    f.add_argument("--am", default="7-9", help="AM peak window in hours for GTFS headways (default 7-9)")
    f.add_argument("--frequent", type=float, default=15.0, help="max peak headway (min) for a bus route to count as frequent")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for m in fetch.registry().values():
            print(f"{m['id']:12s} CBSA {m['cbsa']}  {m['name']}  ({len(m['county_fips'])} counties)")
        return 0
    stages = a.only.split(",") if a.only else list(fetch.DEFAULT_STAGES)
    bad = [s for s in stages if s not in fetch.STAGES]
    if bad:
        ap.error(f"unknown stage(s) {bad}")
    if a.jobs_proxy == "places" and "places" not in stages:
        stages.append("places")
    am = tuple(float(x) for x in a.am.split("-"))
    fetch.run(a.metro, stages, force=a.force, lodes_year=a.lodes_year, overture_release=a.overture_release,
              am=am, frequent=a.frequent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
