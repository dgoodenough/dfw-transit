"""Build a potential transit network for any metro from its step-1 inputs.

    python -m metro generate <metro-id> [--budget-musd N | --years N] [--no-model] [--out DIR]

Steps (each module's docstring has the details and every threshold is in metro/generate.json):
  1. centers     activity centers from people + jobs density (metro/centers.py)
  2. corridors   center-to-center links routed on real roads and rail, chained into candidate
                 lines (metro/candidates.py, routing via dfwt/osmroute.py + tools/gen_expansion.py)
  3. mode        metro / streetcar / BRT / regional rail from corridor density and length;
                 stations at spacing by mode and setting, shared with today's stations
  4. value       sketch demand (metro/sketch.py): new daily trips per $M; greedy selection
                 within the budget, duplicates of existing / chosen lines rejected (metro/select.py)
  5. output      generated/<id>/: dfwt tables (lines, stations, line_stops, line_segments,
                 transfers + empty stages/service/infill so nothing falls back to DFW's plan),
                 centers.csv, candidates.csv, report.md, preview.png; then (unless --no-model)
                 dfwt's demand model on today's land use for a ridership estimate.

The output folder loads in the existing tools: python -m dfwt validate --scenario <abs path>.
"""
import collections
import json
import math
import os
import time

import numpy as np

from dfwt import config, geo

from . import candidates, centers, geom, inputs, model, output, routing, select, sketch

PARAMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate.json")


def params(metro_id=None, override=None):
    with open(PARAMS, encoding="utf-8") as f:
        gp = json.load(f)
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
                "reason": self.reason}


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
             jobs_proxy=None):
    """Run every step for one metro; `metro` (an inputs.Metro) replaces reading data/metros/<id>/ (tests)."""
    t0 = time.time()
    gp = params(metro_id, override)
    cfg0 = config.load()
    m = metro or inputs.load(metro_id, jobs_proxy)
    out = out or config.path("generated", metro_id + ("_places_proxy" if m.jobs_proxy else ""))
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
    towns = centers.towns(m, surf, cp, urban)
    namer = output.make_namer(m)
    used_names = set()
    for c in urban + towns:
        c.name = output.place_name(namer, c.lat, c.lon, used_names, c.id)
    log(f"  centers: {sum(c.kind == 'downtown' for c in urban)} downtown, {sum(c.kind == 'major' for c in urban)} major, "
        f"{sum(c.kind == 'minor' for c in urban)} minor; {len(towns)} towns")
    cfg = model.metro_cfg(m, urban, cfg0)
    downtowns = [(c.x, c.y) for c in urban if c.kind == "downtown"]
    core_r = gp["grade"]["core_radius_km"]
    urban_density = cfg["growth"]["tod"]["setting_density_per_km2"]["urban"]
    dens800 = centers.Surface(m, cp["grid_km"], 0.8)

    def dens_fn(x, y):
        return float(dens800.density_at(x, y))

    # 2. links and candidate paths -----------------------------------------------
    router = routing.Router(m, os.path.join(out, "cache", "routes.json"))
    links = candidates.build_links(m, router, urban, towns, gp, log)
    by = {c.id: c for c in urban + towns}
    ex = Existing(m, cfg["modes"])
    zidx = geom.ZoneIndex(m, 1.0)
    road_metro = dict(candidates.paths(urban + towns, links, "road", "metro", gp))
    road_brt = dict(candidates.paths(urban + towns, links, "road", "brt", gp))
    rail, rail_why = candidates.rail_lines(m, router, urban, towns, gp, log)
    log(f"  paths: {len(road_metro)} metro-profile, {len(road_brt)} BRT-profile, {len(rail)} rail")

    # 3. mode, stations, cost, sketch value per candidate ---------------------------
    ctx, od = model.gravity_od(m, cfg)
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
    chosen, spent = select.run(cands, sk, budget, gp, cfg, exist_P, [v[:2] for v in ex.stations.values()], log)

    # 5. output ---------------------------------------------------------------------
    y_open = cfg["existing_year"] + gp["opens_after_years"]
    tables = output.tables(m, ex, chosen, by, gp, cfg, y_open, namer, used_names, downtowns, core_r)
    output.write_tables(out, tables)
    output.write_csv(os.path.join(out, "centers.csv"), [c.as_row() for c in urban + towns])
    output.write_csv(os.path.join(out, "candidates.csv"), [c.row() for c in sorted(cands, key=_cand_key)])
    stats = output.network_stats(out, m, cfg, tables, ex.tables)
    res = None
    if run_model:
        log("  demand model (dfwt, today's land use, every line open) ...")
        res = output.model_runs(m, cfg, ctx, tables, ex)
    output.report(out, m, gp, cfg, urban, towns, links, cands, chosen, budget, spent, stats, res, flags,
                  time.time() - t0, metro_id, rail_why=rail_why, skipped=ex.skipped)
    output.preview(out, m, surf, urban, towns, ex, chosen, tables)
    log(f"  wrote {os.path.relpath(out, config.ROOT)}/ in {time.time() - t0:.0f}s")
    return {"out": out, "chosen": chosen, "cands": cands, "centers": urban, "towns": towns, "stats": stats,
            "model": res, "budget": budget, "spent": spent, "tables": tables, "ex_tables": ex.tables, "m": m, "cfg": cfg}


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
            mode, why = None, why + "; but no freeway/arterial corridor route for metro"
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
