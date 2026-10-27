"""Command line for the metro-agnostic planner.

  python -m metro generate <metro-id> [--budget-musd N | --years N] [--no-model] [--out DIR]
  python -m metro adapt-dfw                 write DFW's inputs in the step-1 contract shape
  python -m metro check-dfw                 generate DFW and compare with the hand plan
                                            (reports/generator_dfw_check.md)
"""
import argparse
import os
import sys


def main(argv=None):
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    ap = argparse.ArgumentParser(prog="python -m metro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="build a potential network from data/metros/<id>/")
    g.add_argument("metro")
    g.add_argument("--budget-musd", type=float, help="capital budget, $M at 2025 prices "
                   "(default config budget.musd_per_year x --years)")
    g.add_argument("--years", type=int, help="years of the flat budget (default metro/generate.json selection.years)")
    g.add_argument("--out", help="output folder (default generated/<id>)")
    g.add_argument("--no-model", action="store_true", help="skip the dfwt demand-model run")
    sub.add_parser("adapt-dfw", help="write data/metros/dfw/ from the repo's DFW inputs")
    c = sub.add_parser("check-dfw", help="generate DFW at the 2M plan's capital and compare")
    c.add_argument("--no-model", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "generate":
        from .generate import generate
        generate(a.metro, budget_musd=a.budget_musd, years=a.years, out=a.out and os.path.abspath(a.out),
                 run_model=not a.no_model)
    elif a.cmd == "adapt-dfw":
        from .inputs import adapt_dfw
        print(adapt_dfw())
    elif a.cmd == "check-dfw":
        from .compare import main as check
        check(run_model=not a.no_model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
