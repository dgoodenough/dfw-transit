"""Command line.

  python -m dfwt validate [--scenario NAME]
  python -m dfwt build [--quick]            evaluate plan + scenarios, write results/, reports/, docs/
  python -m dfwt trip "Handley" "JPS" --year 2040 [--scenario NAME]
"""
import argparse
import os
import sys
import time

from . import config, validate
from .network import Network


def scenarios():
    d = config.path("scenarios")
    return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))


def cmd_validate(args):
    net = Network.load(args.scenario)
    findings = validate.run(net)
    for sev, code, line, msg in findings:
        if sev != "info" or args.verbose:
            print(f"{sev:5} {code:9} {line[:28]:28} {msg}")
    print(validate.summarize(findings))
    return 1 if any(f[0] == "error" for f in findings) else 0


def cmd_build(args):
    from . import evaluate, report, webmap
    t0 = time.time()
    ctx = evaluate.Context()
    print(f"demand: {ctx.od_source} ({ctx.od.sum():,.0f} commutes, {ctx.zones.n} zones)")
    names = [None] + scenarios()
    evals, nets, findings = {}, {}, {}
    for sc in names:
        key = sc or "plan"
        net = Network.load(sc)
        findings[key] = validate.run(net)
        errors = [f for f in findings[key] if f[0] == "error"]
        if errors and sc is None:
            for f in errors:
                print("error", f[1], f[2], f[3])
            print("the plan has data errors; fix them before building")
            return 1
        print(f"{key}: evaluating")
        values = not args.quick and (sc is None or sc == "v1_baseline")
        evals[key] = evaluate.evaluate(ctx, net, line_values=values)
        nets[key] = net
        evaluate.write(config.path("results", key), evals[key])
    report.write_all(ctx, nets, evals, findings)
    webmap.write(nets, evals, config.path("docs", "index.html"))
    print(f"done in {time.time() - t0:.0f}s: results/, reports/RESULTS.md, reports/VALIDATION.md, docs/index.html")
    return 0


def cmd_trip(args):
    from .graph import YearGraph
    net = Network.load(args.scenario)
    g = YearGraph(net, args.year)

    def find(q):
        ql = q.lower()
        hits = [s for s in g.station_ids if net.stations[s].name.lower() == ql] or \
               [s for s in g.station_ids if ql in net.stations[s].name.lower()]
        if not hits:
            sys.exit(f"no station open in {args.year} matches '{q}'")
        return hits[0]

    a, b = find(args.origin), find(args.dest)
    legs, total = g.itinerary(g.sidx[a], g.sidx[b])
    if total == float("inf"):
        print(f"no route from {net.stations[a].name} to {net.stations[b].name} in {args.year}")
        return 1
    print(f"{net.stations[a].name} -> {net.stations[b].name}, {args.year}: {total:.0f} min station to station")
    for kind, s0, s1, run, t in legs:
        if kind == "ride":
            print(f"  ride {run.line.name:28} {net.stations[s0].name} -> {net.stations[s1].name} ({t:.0f} min)")
        elif kind == "wait":
            print(f"  wait for {run.line.name:24} at {net.stations[s0].name} ({t:.0f} min)")
        else:
            print(f"  walk {net.stations[s0].name} -> {net.stations[s1].name} ({t:.0f} min)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="dfwt", description="DFW Transit network model")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--scenario")
    v.add_argument("-v", "--verbose", action="store_true")
    b = sub.add_parser("build")
    b.add_argument("--quick", action="store_true", help="skip per-line leave-one-out values")
    t = sub.add_parser("trip")
    t.add_argument("origin")
    t.add_argument("dest")
    t.add_argument("--year", type=int, default=2070)
    t.add_argument("--scenario")
    args = p.parse_args(argv)
    return {"validate": cmd_validate, "build": cmd_build, "trip": cmd_trip}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
