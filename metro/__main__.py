"""Command line.

  python -m metro list
  python -m metro fetch houston                       every default stage
  python -m metro fetch houston --only zones,gtfs     some stages
  python -m metro fetch houston --jobs-proxy places   also the (labelled) Overture places proxy
  python -m metro fetch houston --force               re-download cached raw files

  python -m metro generate houston [--budget-musd N | --years N] [--no-model] [--out DIR]
                                                      build a potential network (generated/<id>/)
  python -m metro adapt-dfw                           write DFW's inputs in the contract shape
  python -m metro check-dfw [--no-model] [--reuse]     generate DFW, compare with the hand plan
                                                      (reports/generator_dfw_check.md)
"""
import argparse
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m metro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="metros in the registry")
    f = sub.add_parser("fetch", help="gather a metro's inputs into data/metros/<id>/")
    f.add_argument("metro")
    f.add_argument("--only", help="comma-separated stages (see metro/fetch.py STAGES)")
    f.add_argument("--force", action="store_true", help="re-download files already in raw/")
    f.add_argument("--lodes-year", type=int, help="LODES year (default: newest available)")
    f.add_argument("--overture-release", help="Overture release (default: the one DFW uses)")
    f.add_argument("--jobs-proxy", choices=["places"],
                   help="also count Overture places per block group (zones_places_proxy.csv); off by default")
    f.add_argument("--am", default="7-9", help="AM peak window in hours for GTFS headways (default 7-9)")
    f.add_argument("--frequent", type=float, default=15.0, help="max peak headway (min) for a bus route to count as frequent")
    g = sub.add_parser("generate", help="build a potential network from data/metros/<id>/ into generated/<id>/")
    g.add_argument("metro")
    g.add_argument("--budget-musd", type=float, help="capital budget, $M at 2025 prices "
                   "(default config budget.musd_per_year x --years)")
    g.add_argument("--years", type=int, help="years of the flat budget (default metro/generate.json selection.years)")
    g.add_argument("--out", help="output folder (default generated/<id>)")
    g.add_argument("--no-model", action="store_true", help="skip the dfwt demand-model run")
    sub.add_parser("adapt-dfw", help="write data/metros/dfw/ from the repo's DFW inputs")
    c = sub.add_parser("check-dfw", help="generate DFW at the 2M plan's capital and compare with it")
    c.add_argument("--no-model", action="store_true")
    c.add_argument("--reuse", action="store_true", help="compare generated/dfw/ as it is (no regeneration)")
    a = ap.parse_args(argv)

    if a.cmd in ("generate", "check-dfw"):
        os.environ.setdefault("OMP_NUM_THREADS", "2")       # a shared machine: keep BLAS small
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    if a.cmd == "generate":
        from .generate import generate
        generate(a.metro, budget_musd=a.budget_musd, years=a.years, out=a.out and os.path.abspath(a.out),
                 run_model=not a.no_model)
        return 0
    if a.cmd == "adapt-dfw":
        from .inputs import adapt_dfw
        print(adapt_dfw())
        return 0
    if a.cmd == "check-dfw":
        from .compare import main as check
        check(run_model=not a.no_model, reuse=a.reuse)
        return 0

    from . import fetch
    if a.cmd == "list":
        for m in fetch.registry().values():
            print(f"{m['id']:12s} CBSA {m['cbsa']}  {m['name']}  ({len(m['county_fips'])} counties)")
        return 0
    stages = a.only.split(",") if a.only else list(fetch.DEFAULT_STAGES)
    bad = [s for s in stages if s not in fetch.STAGES]
    if bad:
        ap.error(f"unknown stage(s) {bad}; stages: {','.join(fetch.STAGES)}")
    if a.jobs_proxy == "places" and "places" not in stages:
        stages.append("places")
    am = tuple(float(x) for x in a.am.split("-"))
    fetch.run(a.metro, stages, force=a.force, lodes_year=a.lodes_year, overture_release=a.overture_release,
              am=am, frequent=a.frequent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
