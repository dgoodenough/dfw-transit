"""Command line.

  python -m dfwt validate [--scenario NAME]
  python -m dfwt build [--quick]            evaluate plan + scenarios, write results/, reports/, docs/
  python -m dfwt trip "Handley" "JPS" --year 2040 [--scenario NAME]
  python -m dfwt stage F03 [--show]                       how a line grows, interval by interval
  python -m dfwt stage F03 --split-at "Central Station,Medical City - Baylor" --years 2035,2040,2045 [--write]
  python -m dfwt optimize [--out staged]                  suggest a staged build order (writes a scenario)
  python -m dfwt align [--lines F02,E10] [--write]        make alignments buildable (see dfwt/geometry.py)
  python -m dfwt schedule [--scenario NAME] [--write]     stages to exact years under the flat budget
  python -m dfwt ridership [--scenario NAME] [--years 2050,2070,2100]   daily boardings, growth, garages
"""
import argparse
import csv
import os
import sys
import time

from . import config, validate
from .network import Network


def scenarios(levers=False):
    """Scenario folders. lever_* folders are analysis runs (tools/*_levers.py, the 2M study);
    the build and the map leave them out unless asked."""
    d = config.path("scenarios")
    return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))
                  and (levers or not n.startswith("lever_")))


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
    names = [None] + scenarios(levers=args.all)
    evals, nets, findings = {}, {}, {}
    for sc in names:
        key = sc or "plan"
        net = Network.load(sc)
        sctx = evaluate.Context(net.cfg) if config.has_overlay(sc) else ctx   # the scenario's own assumptions
        findings[key] = validate.run(net)
        errors = [f for f in findings[key] if f[0] == "error"]
        if errors and (sc is None or sc == net.cfg.get("default_scenario")):
            for f in errors:
                print("error", f[1], f[2], f[3])
            print(f"{key} has data errors; fix them before building")
            return 1
        print(f"{key}: evaluating")
        wanted = sc is None or sc == net.cfg.get("default_scenario")
        evals[key] = evaluate.evaluate(sctx, net, line_values=wanted and not args.quick)
        nets[key] = net
        out = config.path("results", key)
        if wanted and args.quick:   # keep the last full build's line values instead of blanking them
            evaluate.carry_line_values(out, evals[key])
        elif wanted:
            evaluate.stamp_line_values(out, evals[key])
        evaluate.write(out, evals[key])
    report.write_all(ctx, nets, evals, findings)
    webmap.write(nets, evals, config.path("docs", "map.html"))
    from . import story
    story.write(config.path("docs", "index.html"))
    print(f"done in {time.time() - t0:.0f}s: results/, reports/RESULTS.md, reports/VALIDATION.md, docs/map.html, docs/index.html (story)")
    return 0


def cmd_ridership(args):
    from .evaluate import Context, run_year
    cfg = config.load(scenario=args.scenario)
    ctx = Context(cfg)
    net = Network.load(args.scenario, cfg)
    years = [int(y) for y in args.years.split(",")]
    modes = list(cfg["modes"]) + ["feeder_bus"]
    print("year    pop   jobs stations  trips(dedup)  " + "  ".join(f"{m:>10}" for m in modes)
          + "  all-boardings  full-garages")
    for y in years:
        r = run_year(ctx, net, y, want_loads=True)
        bm = r["boardings_by_mode"]
        print(f"{y} {r['pop'] / 1e6:5.2f}M {r['jobs'] / 1e6:5.2f}M {r['graph'].n_st:8d}  {r['daily_trips']:12,.0f}  "
              + "  ".join(f"{bm.get(m, 0):10,.0f}" for m in modes)
              + f"  {r['all_boardings']:13,.0f}  {r['pnr_full_garages']:12d}", flush=True)
    return 0


def cmd_schedule(args):
    import csv as _csv
    from . import staging
    net = Network.load(args.scenario)
    rows = staging.schedule(args.scenario)
    folder = config.path("scenarios", args.scenario) if args.scenario else config.path("network")
    if args.write:
        with open(os.path.join(folder, "stages.csv"), "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=staging.STAGE_COLS, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        for n in ("stages.add.csv", "stages.patch.csv"):   # the full table replaces them; left in place they'd add rows twice
            if os.path.exists(os.path.join(folder, n)):
                os.remove(os.path.join(folder, n))
        print(f"wrote {os.path.join(folder, 'stages.csv')}")
    else:
        for a, b in zip(net.stage_rows, rows):
            if a["year_opens"] != b["year_opens"]:
                print(f"  {a['line_id']} stage {a['stage']}: {a['from_stop']} -> {a['to_stop']}  {a['year_opens']} -> {b['year_opens']}")
        print("dry run; add --write to save")
    return 0


def cmd_values(args):
    from . import evaluate
    cfg = config.load(scenario=args.scenario)
    net = Network.load(args.scenario, cfg)
    ctx = evaluate.Context(cfg) if config.has_overlay(args.scenario) else evaluate.Context()
    only = set(args.lines.split(",")) if args.lines else None
    rows = evaluate.final_values(ctx, net, procs=args.procs, only=only)
    path = config.path("results", net.name, "line_values.csv")
    if only and os.path.exists(path):   # merge into the last full set
        with open(path, encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["line_id"] not in only] + rows
        for r in rows:
            r["marginal_final"], r["cost_shared_musd"] = int(r["marginal_final"]), int(r["cost_shared_musd"])
            r["value_per_musd"] = float(r["value_per_musd"]) if r["value_per_musd"] != "" else ""
    evaluate.write_final_values(config.path("results", net.name), rows)
    for r in sorted(rows, key=lambda r: -(r["value_per_musd"] or 0)):
        print(f"  {r['line_id']:6} {net.host_line(r['line_id']).name if not r['host'] else r['line_id'] + ' (via ' + r['host'] + ')':32}"
              f" {r['marginal_final']:>8,} trips  ${r['cost_shared_musd']:>7,}M  {r['value_per_musd']}")
    print(f"wrote {config.path('results', net.name, 'line_values.csv')}")
    return 0


def cmd_story(args):
    from . import story
    print("wrote", story.write(config.path("docs", "index.html")))
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


def cmd_stage(args):
    import csv
    from . import staging
    tables, _ = Network.read_tables(args.scenario)
    rows = tables["stages.csv"]
    net = Network.load(args.scenario)
    if args.line not in net.lines:
        sys.exit(f"unknown line {args.line}")
    ln = net.lines[args.line]
    names = {k: v.name for k, v in net.stations.items()}
    if args.split_at:
        try:
            cuts = sorted(staging.resolve(c, ln.stop_ids, names) for c in args.split_at.split(",") if c.strip())
        except KeyError as e:
            sys.exit(f"{e}. Stops on {ln.name}: " + ", ".join(names[s] for s in ln.stop_ids))
        idx = [0] + cuts + [len(ln.stop_ids) - 1]
        pieces = list(zip(idx[:-1], idx[1:]))
        years = [int(y) for y in args.years.split(",")] if args.years else []
        if len(years) != len(pieces):
            sys.exit(f"{len(cuts)} cut(s) make {len(pieces)} pieces; give {len(pieces)} years in line order")
        hws = (args.headways or "").split(",")
        new = []
        for n, k in enumerate(sorted(range(len(pieces)), key=lambda k: (years[k], k)), 1):
            a, b = pieces[k]
            new.append({"line_id": ln.id, "stage": n, "kind": "starter" if n == 1 else "extension",
                        "from_stop": staging.stop_ref(ln.stop_ids, names, a),
                        "to_stop": staging.stop_ref(ln.stop_ids, names, b),
                        "year_opens": years[k], "headway_min": hws[k] if k < len(hws) else "", "note": args.note or ""})
        rows = sorted([r for r in rows if r["line_id"] != ln.id] + new, key=lambda r: (r["line_id"], int(r["stage"])))
        net = Network.load(args.scenario, stage_rows=rows)
        if args.write:
            folder = config.path("scenarios", args.scenario) if args.scenario else config.path("network")
            with open(os.path.join(folder, "stages.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=staging.STAGE_COLS, lineterminator="\n", extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            print(f"wrote {len(new)} stages for {ln.name}")
        else:
            print("dry run; add --write to save:")
            for r in new:
                print(f"  {r['stage']}. {r['kind']:9} {r['from_stop']} -> {r['to_stop']}  {r['year_opens']}")
    show_growth(net, args.line)
    return 0


def show_growth(net, line_id):
    from . import staging
    names = {k: v.name for k, v in net.stations.items()}
    ln = net.lines[line_id]
    print(f"{ln.name} ({ln.mode}, {ln.km:.1f} km)")
    prev = None
    for y in net.cfg["years"]:
        runs = [r for r in net.runs(y) if r.line.id == ln.id]
        if not runs:
            continue
        desc = "; ".join(f"{names[r.stops[0]]} - {names[r.stops[-1]]}" for r in runs)
        if desc != prev:
            km = sum(sum(r.hop_km) for r in runs)
            print(f"  {y}: {km:5.1f} km  {desc}  (every {ln.headway_at(y):g} min)")
        prev = desc
    for f in staging.check(net):
        if f[2] == ln.name:
            print(f"  {f[0]} {f[1]}: {f[3]}")


def cmd_align(args):
    from . import geometry
    reports, moves, review = geometry.run(lines=args.lines, write=args.write, procs=args.procs)
    for n, msg in review:
        print(f"review  {n}: {msg}")
    print(f"{len(reports)} lines processed, {len(moves)} station moves, {len(review)} need review; "
          f"see reports/GEOMETRY.md" + ("" if args.write else " (dry run; add --write to save)"))
    return 0


def cmd_optimize(args):
    from . import optimize
    optimize.optimize(out=args.out, procs=args.procs)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="dfwt", description="DFW Transit network model")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--scenario")
    v.add_argument("-v", "--verbose", action="store_true")
    b = sub.add_parser("build")
    b.add_argument("--quick", action="store_true",
                   help="skip per-line leave-one-out values (~40 min); keep the last full build's")
    b.add_argument("--all", action="store_true", help="also evaluate the lever_* analysis scenarios")
    sc = sub.add_parser("schedule", help="move stages to the earliest year the flat budget allows (keeps the order)")
    sc.add_argument("--scenario")
    sc.add_argument("--write", action="store_true")
    rd = sub.add_parser("ridership", help="daily boardings and growth for chosen years (any year, e.g. 2100)")
    rd.add_argument("--scenario")
    rd.add_argument("--years", default="2025,2050,2070,2100")
    va = sub.add_parser("values", help="line values for the build order (final-year leave-one-out, ~20-30 min)")
    va.add_argument("--scenario")
    va.add_argument("--procs", type=int, default=3)
    va.add_argument("--lines", help="comma-separated line_ids to (re)measure; the rest keep their values")
    sub.add_parser("story", help="the story page (docs/index.html) from the last build's results (~10 min)")
    t = sub.add_parser("trip")
    t.add_argument("origin")
    t.add_argument("dest")
    t.add_argument("--year", type=int, default=2070)
    t.add_argument("--scenario")
    st = sub.add_parser("stage", help="show or re-stage how a line is built over time")
    st.add_argument("line", help="line_id, e.g. F03")
    st.add_argument("--split-at", help="comma-separated stops to cut the line at")
    st.add_argument("--years", help="opening year of each piece, in line order")
    st.add_argument("--headways", help="optional headway per piece, in line order")
    st.add_argument("--note")
    st.add_argument("--scenario")
    st.add_argument("--write", action="store_true")
    o = sub.add_parser("optimize", help="suggest a staged build order under the flat budget")
    o.add_argument("--out", default="staged", help="scenario folder to write stages.csv into")
    o.add_argument("--procs", type=int, default=3)
    a = sub.add_parser("align", help="make alignments buildable (route rail on real track, fit metro curves)")
    a.add_argument("--lines", help="comma-separated line_ids (default: all)")
    a.add_argument("--procs", type=int, default=2)
    a.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    return {"validate": cmd_validate, "build": cmd_build, "trip": cmd_trip, "stage": cmd_stage,
            "optimize": cmd_optimize, "align": cmd_align,
            "ridership": cmd_ridership, "schedule": cmd_schedule, "values": cmd_values, "story": cmd_story}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
