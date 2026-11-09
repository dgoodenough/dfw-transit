"""Build a potential transit network for any metro from its step-1 inputs.

    python -m metro generate <metro-id> [--budget-musd N | --years N] [--no-model] [--out DIR]

Steps (each module's docstring has the details and every threshold is in metro/generate.json):
  1. centers     activity centers from people + jobs density (metro/centers.py)
  2. corridors   center-to-center links routed on real roads and rail, chained into candidate
                 lines (metro/candidates.py, routing via dfwt/osmroute.py + tools/gen_expansion.py)
  3. mode        metro / streetcar / BRT / regional rail from corridor density and length;
                 stations at spacing by mode and setting, shared with today's stations
  4. value       sketch demand (metro/sketch.py): new daily trips per $M; greedy selection
                 within the budget, duplicates of existing / chosen lines rejected (metro/select.py);
                 with the full model, it prunes the greedy's pool (metro/modelselect.py) and a local
                 search improves the whole network on it (metro/lineplan.py)
  5. output      generated/<id>/: dfwt tables (lines, stations, line_stops, line_segments,
                 transfers + empty stages/service/infill so nothing falls back to DFW's plan),
                 centers.csv, candidates.csv, report.md, preview.png; then (unless --no-model)
                 dfwt's demand model on today's land use for a ridership estimate.

The output folder loads in the existing tools: python -m dfwt validate --scenario <abs path>.
"""
import collections
import copy
import json
import math
import os
import time

import numpy as np

from dfwt import config, evaluate, geo

from . import anchors as anchors_mod, candidates, centers, geom, inputs, lineplan, model, output, modelselect, routing, select, sketch, through

PARAMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate.json")


def params(metro_id=None, override=None, buildout=False):
    """Generator parameters: metro/generate.json, the build-out block merged over it when `buildout`,
    then the metro's own data/metros/<id>/generate.json, then `override`."""
    with open(PARAMS, encoding="utf-8") as f:
        gp = json.load(f)
    bo = gp.pop("buildout", None)
    if buildout and bo:
        config.merge(gp, {k: v for k, v in bo.items() if not k.startswith("_")})
    gp["buildout_mode"] = bool(buildout)
    if metro_id:
        p = inputs.metro_dir(metro_id, "generate.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                config.merge(gp, json.load(f))
    if override:
        config.merge(gp, override)
    return gp


def pop_only(gp):
    """Without jobs, activity is people alone: scale every people + jobs threshold by
    centers.pop_only_factor (in place). Returns the factor."""
    f = gp["centers"]["pop_only_factor"]
    c = gp["centers"]
    for k in ("min_density", "min_activity", "major_activity", "town_min_density", "town_min_activity",
              "downtown_jobs", "downtown_job_density"):
        c[k] = c[k] * f
    for k in ("metro", "streetcar", "brt", "commuter_1600m"):
        gp["modes"][k] = gp["modes"][k] * f
    return f


class Cand:
    """One candidate line."""

    def __init__(self, uid, kind, seq, P):
        self.uid, self.kind, self.seq, self.P = uid, kind, tuple(seq), P
        self.mode, self.reason, self.mode_reason, self.status = None, "", "", "pool"
        self.order, self.cost_charged = None, 0.0
        self.new_trips = self.trips = self.ratio = self.capital = self.opex = 0.0
        self.peak_hour_load = 0.0
        self.headway = None   # minutes; None: the mode's default (metro/lineplan.py may set it)
        self.name = ""
        self.stops = []

    @property
    def km(self):
        return geom.length(self.P)

    def row(self):
        return {"cand_id": self.uid, "name": self.name, "kind": self.kind, "centers": " ".join(self.seq),
                "mode": self.mode or "", "km": round(self.km, 1), "stops": len(self.stops),
                "density_per_route_km": round(getattr(self, "rho", 0)),
                "capital_musd": round(self.capital), "opex_musd_yr": round(self.opex, 1),
                "trips_standalone": round(self.trips), "new_trips": round(self.new_trips),
                "trips_per_musd": round(self.ratio, 2), "peak_hour_load": round(self.peak_hour_load),
                "status": self.status, "order": self.order or "", "mode_reason": self.mode_reason,
                "reason": self.reason,
                # full-model selection (metro/modelselect.py), when it ran
                "model_trips": round(self.model_trips) if getattr(self, "model_trips", None) is not None else "",
                "model_trips_per_musd": round(self.model_ratio, 2) if getattr(self, "model_ratio", None) is not None else ""}


class Existing:
    """Today's transit from the metro's existing/ tables."""

    def __init__(self, m, modes):
        """`modes`: the modes dfwt models (config.json modes). Lines of other modes (GTFS local and
        express buses, mode "bus") are left out, as in DFW, where today's buses are the model's
        feeder grid (config access.feeder) rather than lines; they are listed in self.skipped."""
        self.stations, self.lines, self.station_modes = {}, [], {}
        t = m.existing or {k: [] for k in inputs.TABLES}
        keep = {r["line_id"] for r in t["lines.csv"] if r["mode"] in modes}
        self.skipped = collections.Counter(r["mode"] for r in t["lines.csv"] if r["line_id"] not in keep)
        used = {r["station_id"] for r in t["line_stops.csv"] if r["line_id"] in keep}
        self.tables = {
            "lines.csv": [r for r in t["lines.csv"] if r["line_id"] in keep],
            "line_stops.csv": [r for r in t["line_stops.csv"] if r["line_id"] in keep],
            "line_segments.csv": [r for r in t["line_segments.csv"] if r["line_id"] in keep],
            "stations.csv": [r for r in t["stations.csv"] if r["station_id"] in used],
            "transfers.csv": [r for r in t.get("transfers.csv", []) if r["station_a"] in used and r["station_b"] in used]}
        for r in self.tables["stations.csv"]:
            x, y = m.xy(float(r["lat"]), float(r["lon"]))
            self.stations[r["station_id"]] = (float(x), float(y), r["name"])
        modes = {r["line_id"]: r["mode"] for r in self.tables["lines.csv"]}
        hw = {r["line_id"]: r.get("headway_min") for r in self.tables["lines.csv"]}
        stops = {}
        for r in sorted(self.tables["line_stops.csv"], key=lambda r: (r["line_id"], int(r["seq"]))):
            stops.setdefault(r["line_id"], []).append(r["station_id"])
            self.station_modes.setdefault(modes.get(r["line_id"]), set()).add(r["station_id"])
        segs = {}
        for r in sorted(self.tables["line_segments.csv"], key=lambda r: (r["line_id"], int(r["seq"]))):
            pts = [(lat, lon) for lon, lat in geo.parse_wkt(r["geometry_wkt"])]
            segs.setdefault(r["line_id"], []).append(geom.to_xy(m, pts))
        for lid, mode in modes.items():
            P = []
            for Q in segs.get(lid, []):
                P.extend(Q if not P else Q[1:])
            if len(P) < 2 or lid not in stops:
                continue
            st = [self.stations[s][:2] for s in stops[lid] if s in self.stations]
            cum = geom.cumlen(P)
            along = [geom.project(P, cum, q)[0] for q in st]
            self.lines.append({"line_id": lid, "mode": mode, "P": P, "stations": st, "along": along,
                               "ids": stops[lid], "headway": float(hw[lid]) if hw.get(lid) else None})

    def near(self, P, r_km):
        """[(s along P, station id)] of today's stations within r_km of polyline P."""
        cum = geom.cumlen(P)
        xs = [p[0] for p in P]
        ys = [p[1] for p in P]
        lo_x, hi_x, lo_y, hi_y = min(xs) - r_km, max(xs) + r_km, min(ys) - r_km, max(ys) + r_km
        out = []
        for sid, (x, y, _) in self.stations.items():
            if lo_x <= x <= hi_x and lo_y <= y <= hi_y:
                s, d = geom.project(P, cum, (x, y))
                if d <= r_km:
                    out.append((s, sid))
        return out


def generate(metro_id, budget_musd=None, years=None, out=None, run_model=True, override=None, log=print, metro=None,
             jobs_proxy=None, buildout=None, policies=None, future_years=None, full_model=None):
    """Run every step for one metro; `metro` (an inputs.Metro) replaces reading data/metros/<id>/ (tests)."""
    t0 = time.time()
    if buildout is None:   # the registry can ask for it (metros.json buildout: true)
        from . import fetch
        try:
            buildout = bool((fetch.registry().get(metro_id) or {}).get("buildout"))
        except FileNotFoundError:
            buildout = False
    gp = params(metro_id, override, buildout)
    cfg0 = config.load()
    m = metro or inputs.load(metro_id, jobs_proxy)
    out = out or inputs.home("generated", metro_id + ("_places_proxy" if m.jobs_proxy else ""))
    os.makedirs(out, exist_ok=True)
    log(f"{metro_id}: " + "; ".join(m.status()))
    if not m.osm.get("roads"):
        raise SystemExit(f"{metro_id}: osm/roads.parquet is missing; corridors can't be routed")
    flags = ([] if m.jobs_ok else [m.jobs_note]) + ([m.jobs_proxy] if m.jobs_proxy else [])
    if not m.jobs_ok:
        f = pop_only(gp)
        flags.append(f"every people + jobs threshold (centers, towns, mode densities) x {f} "
                     "(people are about that share of people + jobs in US metros); commutes go to where people "
                     "live (destinations follow population); the full model's absolute numbers are not meaningful")

    # 1. centers -------------------------------------------------------------
    cp = gp["centers"]
    surf = centers.Surface(m, cp["grid_km"], cp["kernel_km"])
    urban = centers.find(m, surf, cp)
    centers.classify(m, urban, cp)
    if not m.jobs_ok or m.jobs_proxy:   # residents or a proxy can't place a downtown reliably
        note = centers.registry_downtowns(m, surf, urban, cp)
        if note:
            flags.append(note)
    entry = registry_entry(metro_id, m)
    anchor_centers = anchors_mod.apply(m, urban, entry.get("anchors"), cp, log)   # airports, campuses, the downtown
    towns = centers.towns(m, surf, cp, urban)
    namer = output.make_namer(m)
    used_names = set()
    for c in urban + towns:
        c.name = output.place_name(namer, c.lat, c.lon, used_names, c.id)
    log(f"  centers: {sum(c.kind == 'downtown' for c in urban)} downtown, {sum(c.kind == 'major' for c in urban)} major, "
        f"{sum(c.kind == 'minor' for c in urban)} minor; {len(towns)} towns")
    for c in anchor_centers:   # an anchor keeps its own name
        c.name = c.anchor_name
    cfg = model.metro_cfg(m, urban, cfg0, growth=entry.get("growth"))   # the metro's own growth, if the registry gives it
    downtowns = [(c.x, c.y) for c in urban if c.kind == "downtown"]
    core_r = gp["grade"]["core_radius_km"]
    urban_density = cfg["growth"]["tod"]["setting_density_per_km2"]["urban"]
    dens800 = centers.Surface(m, cp["grid_km"], 0.8)

    def dens_fn(x, y):
        return float(dens800.density_at(x, y))

    # 2. links and candidate paths -----------------------------------------------
    router = routing.Router(m, os.path.join(out, "cache", "routes.json"), frontage=dens_fn, brt=gp.get("routing", {}).get("brt"))
    # anchors listed on a center but more than a station's walk from it: routes between centers may pass them
    vias = [(n, x, y) for c in anchor_centers for n, k, x, y in getattr(c, "anchor_list", [])
            if math.hypot(c.x - x, c.y - y) > anchors_mod.SERVE_KM and k != "airport"]
    gp["_vias"] = [(x, y) for _, x, y in vias]
    links = candidates.build_links(m, router, urban, towns, gp, log, vias=vias)
    by = {c.id: c for c in urban + towns}
    ex = Existing(m, cfg["modes"])
    zidx = geom.ZoneIndex(m, 1.0)
    road_metro = dict(candidates.paths(urban + towns, links, "road", "metro", gp))
    road_brt = dict(candidates.paths(urban + towns, links, "road", "brt", gp))
    rail, rail_why = candidates.rail_lines(m, router, urban, towns, gp, log)
    log(f"  paths: {len(road_metro)} metro-profile, {len(road_brt)} BRT-profile, {len(rail)} rail")

    # 3. mode, stations, cost, sketch value per candidate ---------------------------
    ctx, od = model.gravity_od(m, cfg)
    asc_note = ridership_constant(metro_id, m, cfg, ctx, ex, log)   # before the sketch: it uses the constant too
    if policies:
        # A policy package (config.json keys, e.g. a scenario's access and parking levers) goes on top of the
        # constant fitted to today's riders under today's conditions. Fitting it with the policies already on
        # would make today's lines carry today's riders despite them, cancelling them on every line.
        asc = cfg["ridership"]["asc"]
        config.merge(cfg, copy.deepcopy(policies))
        cfg["ridership"]["asc"] = asc
        ctx, od = model.gravity_od(m, cfg)   # a fresh context: zones cache parking prices
        asc_note += "; with a policy package on top (" + ", ".join(
            f"{k}.{kk}" for k, v in policies.items() if not k.startswith("_") for kk in (v if isinstance(v, dict) else [k])) + ")"
    sk = sketch.Sketch(m, cfg, od, gp["sketch"]["walk_km"])
    for ln in ex.lines:   # today's lines set the bar every candidate must beat
        n = len(ln["stations"])
        sk.line(ln["mode"], ln["stations"], ln["along"], list(range(n)) if ln["mode"] == "commuter" else [0, n - 1],
                sketch.pnr_capacity(cfg, ln["mode"], n, lambda k: False), headway=ln["headway"], commit=True)
    cands = []
    seqs = sorted(set(road_metro) | set(road_brt))
    for seq in seqs:
        c = Cand(f"R{len(cands) + 1:03d}", "road", seq, None)
        c.routes = {"metro": road_metro.get(seq), "brt": road_brt.get(seq)}
        cands.append(c)
    for seq, P in sorted(rail):
        c = Cand(f"Q{len(cands) + 1:03d}", "rail", seq, P)
        c.routes = {"rail": P}
        cands.append(c)
    router.save()
    exist_P = [ln["P"] for ln in ex.lines]
    for c in cands:
        _decide(c, m, cfg, gp, zidx, by, ex, sk, downtowns, core_r, dens_fn, urban_density, exist_P)
    pool = [c for c in cands if c.status == "pool"]
    log(f"  candidates: {len(cands)} paths, {len(pool)} with a mode "
        f"({', '.join(f'{k} {sum(c.mode == k for c in pool)}' for k in ('metro', 'streetcar', 'brt', 'commuter'))})")

    # 4. selection ------------------------------------------------------------------
    years = years or gp["selection"]["years"]
    budget = budget_musd or cfg0["budget"]["musd_per_year"] * years
    log(f"  budget ${budget / 1e3:.1f}B (capital, 2025 $)")
    mc = gp["selection"]["model"]
    if full_model is None:
        full_model = mc.get("enabled", False)
    full_model = bool(full_model and run_model)
    gsel = gp
    if full_model:   # a wider pool for the full model to prune (metro/modelselect.py)
        gsel = copy.deepcopy(gp)
        gsel["selection"]["min_trips_per_musd"] *= mc["pool_floor_factor"]
        gsel["selection"]["max_lines"] = max(gsel["selection"]["max_lines"], mc.get("pool_max_lines", 0))
        log(f"  sketch pool (floor {gsel['selection']['min_trips_per_musd']} per $M) for the full model:")
    chosen, spent = select.run(cands, sk, budget * (mc.get("pool_budget_factor", 1.0) if full_model else 1.0), gsel, cfg,
                               exist_P, [v[:2] for v in ex.stations.values()], log)
    y_open = cfg["existing_year"] + gp["opens_after_years"]
    joined = []
    gpt = copy.deepcopy(gp)
    gpt["lines"]["max_km"].update(gp["lines"].get("through_max_km", {}))

    def make(seq, routes):   # a through line across downtown (metro/through.py, metro/lineplan.py)
        c = Cand(f"T{len(cands) + 1:03d}", "road", seq, None)
        c.routes = routes
        _decide(c, m, cfg, gpt, zidx, by, ex, sk, downtowns, core_r, dens_fn, urban_density, exist_P)
        cands.append(c)
        return c
    downtown_ids = [c.id for c in urban if c.kind == "downtown"]
    if gsel["selection"].get("through", {}).get("enabled") and chosen:
        chosen, joined = through.pair(chosen, by, [c.id for c in urban if c.kind == "downtown"], make,
                                      gsel["selection"]["through"].get("min_angle_deg", 135), log, links=links,
                                      core_km=gsel["selection"]["through"].get("core_km", 3.0))
        spent = sum(c.capital for c in chosen)
    model_rounds = plan_result = None
    if full_model and chosen:
        judge = mc.get("judge_year") or (min(future_years) if future_years else cfg["existing_year"] + 1)

        def build_net(cs):
            t = output.tables(m, ex, cs, by, gp, cfg, y_open, namer, set(used_names), downtowns, core_r)
            return output.load_net(t, cfg, "generated"), modelselect.line_cands(t)
        with model.projection(m):
            chosen, model_rounds = modelselect.prune(chosen, build_net, ctx, budget, gp, cfg, judge, log)
        spent = sum(getattr(c, "model_capital", c.capital) for c in chosen)
        model_rounds = {"year": judge, "floor": mc["min_trips_per_musd"], "pool_floor": gsel["selection"]["min_trips_per_musd"],
                        "rounds": model_rounds}
        log(f"  full model kept {len(chosen)} lines, ${spent / 1e3:.1f}B")
        if gp["selection"].get("plan", {}).get("enabled") and chosen:
            anchor_pts = [a for c in anchor_centers for a in getattr(c, "anchor_list", [])]
            with model.projection(m):
                net0, _ = build_net(chosen)
                planner = lineplan.Planner(cands, build_net, ctx, cfg, gp, budget, judge, make, by, downtown_ids, links,
                                           anchor_pts, [v[:2] for v in ex.stations.values()],
                                           modelselect.land_use(ctx, net0, judge), log)
                chosen = planner.run(chosen)
            spent = planner.end["capital"]
            plan_result = {"start": planner.start, "end": planner.end, "history": planner.history, "floor": planner.floor,
                           "anchor_trips": planner.anchor_trips}

    # 5. output ---------------------------------------------------------------------
    tables = output.tables(m, ex, chosen, by, gp, cfg, y_open, namer, used_names, downtowns, core_r)
    output.write_tables(out, tables)
    output.write_csv(os.path.join(out, "centers.csv"), [c.as_row() for c in urban + towns])
    output.write_csv(os.path.join(out, "candidates.csv"), [c.row() for c in sorted(cands, key=_cand_key)])
    stats = output.network_stats(out, m, cfg, tables, ex.tables)
    res = None
    if run_model and not chosen:
        log("  no line chosen: demand model skipped")
        flags.append("no candidate corridor reached a mode's density threshold, so no line was chosen")
    elif run_model:
        log("  demand model (dfwt, today's land use, every line open) ...")
        res = output.model_runs(m, cfg, ctx, tables, ex)
        if future_years:
            # every line open in later years: the metro's growth plus station-area development (config growth),
            # today's network under the same growth for comparison
            res["future"] = {}
            with model.projection(m):
                base = output.load_net(ex.tables, cfg, "existing")
                gen = output.load_net(tables, cfg, "generated")
                for y in future_years:
                    log(f"  demand model, {y} ...")
                    res["future"][y] = {"generated": model.run_future(ctx, gen, y),
                                        "existing": model.run_future(ctx, base, y) if base.lines else None}
    sense = through.metrics(chosen, by, downtown_ids, anchor_centers)
    output.report(out, m, gp, cfg, urban, towns, links, cands, chosen, budget, spent, stats, res, flags,
                  time.time() - t0, metro_id, rail_why=rail_why, skipped=ex.skipped, asc_note=asc_note,
                  model_select=model_rounds, sense=sense, plan=plan_result)
    output.preview(out, m, surf, urban, towns, ex, chosen, tables)
    log(f"  wrote {os.path.relpath(out, config.ROOT)}/ in {time.time() - t0:.0f}s")
    return {"out": out, "asc": cfg["ridership"]["asc"], "asc_note": asc_note, "chosen": chosen, "cands": cands, "centers": urban, "towns": towns, "stats": stats,
            "model": res, "model_select": model_rounds, "plan": plan_result, "sense": sense, "through": joined, "budget": budget, "spent": spent, "tables": tables, "ex_tables": ex.tables, "m": m, "cfg": cfg}


def registry_entry(metro_id, m):
    """The metro's registry entry as it is now (the registry may have changed since step 1), else
    the copy step 1 saved in meta.json."""
    from . import fetch
    try:
        entry = fetch.registry().get(metro_id)
    except FileNotFoundError:
        entry = None
    return entry or (m.meta or {}).get("metro") or {}


def ridership_constant(metro_id, m, cfg, ctx, ex, log=print):
    """Set config ridership.asc for metro m (in place, before anything uses it) and say where it
    came from. Registry keys:
      calibration    {"weekday_boardings": N, "source": "..."}: fit the constant so today's lines (the
                     modes dfwt models, buses as the feeder grid) carry N boardings on a weekday in
                     existing_year, as DFW's constant is fitted to DFW's rail boardings
                     (evaluate.calibrate_asc).
      ridership_asc  {"asc": x, "source": "..."}: use x (a constant derived elsewhere).
    Neither: DFW's constant, a transfer."""
    rc = cfg["ridership"]
    if metro_id == "dfw":
        return f"DFW's own calibration (asc {rc['asc']:+.3f})"
    entry = registry_entry(metro_id, m)
    cal, fixed = entry.get("calibration"), entry.get("ridership_asc")
    if cal:
        if not ex.tables["lines.csv"]:
            raise SystemExit(f"{metro_id}: calibration needs today's lines, and existing/ has none dfwt models")
        target = float(cal["weekday_boardings"])
        rc["calibration"] = dict(rc["calibration"], year=cfg["existing_year"], rail_boardings=target)
        log(f"  calibrating the ridership constant to {target:,.0f} weekday boardings on today's lines ...")
        with model.projection(m):
            base = output.load_net(ex.tables, cfg, "existing")
            evaluate.calibrate_asc(ctx, base, lo=-6.0, hi=4.0, tol=0.01,
                                   log=lambda t: log("  " + t.strip()))
        return (f"calibrated here (asc {rc['asc']:+.3f}; DFW {config.load()['ridership']['asc']:+.3f}): today's lines "
                f"carry {target:,.0f} weekday boardings ({cal.get('source', 'registry')})")
    if fixed:
        rc["asc"] = float(fixed["asc"])
        return (f"set from the registry (asc {rc['asc']:+.3f}; DFW {config.load()['ridership']['asc']:+.3f}): "
                f"{fixed.get('source', 'no source given')}")
    return f"DFW's calibration transferred, not fitted here (asc {rc['asc']:+.3f})"


def calibrate(metro_id, log=print):
    """The ridership constant alone (registry `calibration`), without generating: centers (for the
    downtown parking the model prices), today's lines, the commute flows, then the fit.
    Returns {"asc", "note", "today": the model on today's lines}."""
    gp = params(metro_id)
    m = inputs.load(metro_id)
    cp = gp["centers"]
    urban = centers.find(m, centers.Surface(m, cp["grid_km"], cp["kernel_km"]), cp)
    centers.classify(m, urban, cp)
    cfg = model.metro_cfg(m, urban, config.load(), growth=registry_entry(metro_id, m).get("growth"))
    ex = Existing(m, cfg["modes"])
    ctx, _ = model.gravity_od(m, cfg)
    note = ridership_constant(metro_id, m, cfg, ctx, ex, log)
    today = None
    if ex.tables["lines.csv"]:
        with model.projection(m):
            base = output.load_net(ex.tables, cfg, "existing")
            today = model.run_today(ctx, base, base)
        today = {k: float(v) for k, v in today.items() if isinstance(v, (int, float, np.floating))}
    return {"asc": cfg["ridership"]["asc"], "note": note, "today": today}


def _cand_key(c):
    rank = {"chosen": 0, "replaced": 1, "rejected": 2, "pool": 3, "no mode": 4}
    return (rank.get(c.status, 5), c.order or 0, -c.ratio)


def _setup(c, mode, P, m, cfg, gp, by, ex, sk, downtowns, core_r, dens_fn, urban_density):
    """Stations, cost and standalone sketch value of candidate c as `mode` on polyline P."""
    P = geom.despike(P)
    c.mode, c.P = mode, P
    cum = geom.cumlen(P)
    anchors = []
    for cid in c.seq:
        s, d = geom.project(P, cum, (by[cid].x, by[cid].y))
        anchors.append((s, 2, ("C", cid)))
    for s, sid in ex.near(P, gp["stations"]["snap_existing_m"] / 1000):
        anchors.append((s, 3, ("E", sid)))
    for vx, vy in gp.get("_vias", ()):   # a campus or medical district a route passes: a stop there
        s, d = geom.project(P, cum, (vx, vy))
        if d <= 0.3:
            anchors.append((s, 2, None))
    c.stops = candidates.place_stations(P, mode, anchors, gp, dens_fn, urban_density)
    c.station_xy = [p for _, p, _ in c.stops]
    c.along = [s for s, _, _ in c.stops]
    refs = [r[1] if r and r[0] == "E" else None for _, _, r in c.stops]
    c.capital, c.grades = candidates.line_cost(cfg, mode, [(s, p, rf) for (s, p, _), rf in zip(c.stops, refs)], P,
                                               downtowns, core_r, ex.station_modes)
    c.opex = candidates.opex_musd(cfg, mode, c.stops)
    n = len(c.stops)
    in_core = lambda k: any(math.dist(c.station_xy[k], d) <= core_r for d in downtowns)  # noqa: E731
    c.pnr = list(range(n)) if mode == "commuter" else ([] if mode == "streetcar" else [0, n - 1])
    c.pnr = [k for k in c.pnr if not in_core(k)]
    c.pnr_cap = sketch.pnr_capacity(cfg, mode, n, in_core)
    r = sk.line(mode, c.station_xy, c.along, c.pnr, c.pnr_cap)
    c.trips, c.new_trips, c.peak_hour_load = r["trips"], r["new_trips"], r["peak_hour_load"]
    c.walk_pop, c.walk_jobs = r["walk_pop"], r["walk_jobs"]
    years = cfg["staging"].get("value_opex_years", 20)
    c.ratio = c.new_trips / max(c.capital + years * c.opex, 1.0)


def _decide(c, m, cfg, gp, zidx, by, ex, sk, downtowns, core_r, dens_fn, urban_density, exist_P):
    a, b = by[c.seq[0]], by[c.seq[-1]]
    c.name = f"{a.name} - {b.name}"
    if c.kind == "rail":
        P = c.routes["rail"]
        pop, jobs, _ = candidates.corridor_activity(m, zidx, P, 1.6)
        c.rho1600 = (pop + jobs) / max(geom.length(P), 0.1)
        pop, jobs, _ = candidates.corridor_activity(m, zidx, P, 0.8)
        c.rho = (pop + jobs) / max(geom.length(P), 0.1)
        mode, why = candidates.choose_mode("rail", geom.length(P), c.rho, c.rho1600, gp)
    else:
        # density measured on the BRT-profile route (arterials, where the activity is), the
        # metro-profile route used if the line is metro
        P = c.routes.get("brt") or c.routes.get("metro")
        pop, jobs, _ = candidates.corridor_activity(m, zidx, P, 0.8)
        c.rho = (pop + jobs) / max(geom.length(P), 0.1)
        c.rho1600 = 0.0
        mode, why = candidates.choose_mode("road", geom.length(P), c.rho, 0.0, gp)
        if mode == "metro" and c.routes.get("metro"):
            P = c.routes["metro"]
        elif mode == "metro":
            Lb = geom.length(c.routes["brt"]) if c.routes.get("brt") else 0.0
            if c.routes.get("brt") and gp["lines"]["min_km"]["brt"] <= Lb <= gp["lines"]["max_km"]["brt"]:
                # dense enough for metro, but the freeways and major arterials don't run there (a street
                # through a campus): BRT on the street route rather than nothing
                mode, P, why = "brt", c.routes["brt"], why + "; no freeway/arterial route for metro: BRT on the street route"
            else:
                mode, why = None, why + "; but no freeway/arterial corridor route for metro"
        elif mode in ("brt", "streetcar") and not c.routes.get("brt"):
            # a bus or streetcar runs on the street route or not at all: the metro-profile route
            # follows freeways (light rail in a median), which a BRT station can't use
            mode, why = None, why + "; but no street route for it (the street profile found none)"
    c.mode_reason = why
    if mode is None:
        c.status, c.reason, c.P = "no mode", why, P
        return
    _setup(c, mode, P, m, cfg, gp, by, ex, sk, downtowns, core_r, dens_fn, urban_density)
    # BRT that its own riders would overfill at its headway: metro when the corridor allows
    cap = sketch.capacity_per_hour(cfg, "brt")
    if mode == "brt" and c.peak_hour_load > cap and c.routes.get("metro"):
        L = geom.length(c.routes["metro"])
        if gp["lines"]["min_km"]["metro"] <= L <= gp["lines"]["max_km"]["metro"]:
            load = c.peak_hour_load
            _setup(c, "metro", c.routes["metro"], m, cfg, gp, by, ex, sk, downtowns, core_r, dens_fn, urban_density)
            c.mode_reason = why + f"; BRT over capacity ({load:,.0f} riders/h > {cap:,.0f}): metro"
    if c.kind == "road" and geom.share_near(c.P, exist_P, gp["selection"]["duplicate_m"] / 1000) > \
            gp["selection"]["duplicate_share"]:
        c.status, c.reason = "rejected", "duplicate of existing transit"
    # mean people+jobs near stations etc. for the report
    c.station_density = float(np.mean([dens_fn(*p) for p in c.station_xy]))
