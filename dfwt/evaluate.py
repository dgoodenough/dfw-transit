"""Evaluate a scenario across every milestone year, plus per-line value.

Outputs (build/<scenario>/):
  years.csv      one row per year: stations, km, cumulative capital, coverage,
                 job access, competitive commutes
  lines.csv      one row per line: km, stops, cost, opening years, peak load vs
                 mode capacity, passenger-km, marginal commutes (leave-one-out
                 in the final year) and commutes per $M
  stations.csv   one row per station: opening year, lines, nearby activity,
                 boardings (final year)
"""
import csv
import os

import numpy as np

from . import config, demand, growth
from .geo import Projector
from .graph import YearGraph
from .network import Network


class Context:
    """Zones and demand are shared across scenarios; build once."""

    def __init__(self, cfg=None):
        self.cfg = cfg or config.load()
        self.zones = demand.Zones(self.cfg)
        self.od, self.od_source = demand.lodes_or_gravity(self.zones, self.cfg)
        self._seed = (None, None)     # (congestion, gravity seed) for the last year asked
        self._year = {}               # tod_key -> (zones, od), a couple of recent entries

    def year_inputs(self, net, year):
        """Zones grown to `year` (regional growth + TOD near this network's new
        stations + congestion) and commute flows re-balanced to them."""
        z = growth.grown_zones(self.zones, net, year, self.cfg)
        hit = self._year.get(z.tod_key)
        if hit:
            return hit
        dc = self.cfg["demand"]
        total = dc["total_commutes"] * z.jobs.sum() / self.zones.jobs.sum()
        O = z.pop / z.pop.sum() * total
        D = z.jobs / z.jobs.sum() * total
        if self.od_source == "lodes":
            seed = self.od
        else:
            if self._seed[0] != z.cong:
                self._seed = (z.cong, demand.gravity_seed(z, self.cfg))
            seed = self._seed[1]
        od = demand.balance(seed, O, D, dc["gravity_iterations"])
        if len(self._year) >= 2:
            self._year.pop(next(iter(self._year)))
        self._year[z.tod_key] = (z, od)
        return z, od

    def station_activity(self, net):
        """Population + jobs within 1 km of each station (block-group centroids)."""
        z, pj = self.zones, Projector()
        out = {}
        for s in net.stations.values():
            x, y = pj.xy(s.lat, s.lon)
            m = (z.x - x) ** 2 + (z.y - y) ** 2 <= 1.0
            out[s.id] = (float(z.pop[m].sum()), float(z.jobs[m].sum()))
        return out


def coverage(ctx, net, year):
    """Share of population and jobs within the walkshed of an open station."""
    z, cfg = ctx.year_inputs(net, year)[0], ctx.cfg
    pj = Projector()
    near = np.zeros(z.n, dtype=bool)
    for sid, modes in net.open_stations(year).items():
        s = net.stations[sid]
        x, y = pj.xy(s.lat, s.lon)
        r = max(cfg["coverage"]["walkshed_m"][m] for m in modes) / 1000
        near |= (z.x - x) ** 2 + (z.y - y) ** 2 <= r * r
    return float(z.pop[near].sum() / z.pop.sum()), float(z.jobs[near].sum() / z.jobs.sum())


def run_year(ctx, net, year, want_loads=True):
    g = YearGraph(net, year)
    g.skim()
    z, od = ctx.year_inputs(net, year)
    res = demand.evaluate(z, od, net, g, ctx.cfg, want_loads=want_loads)
    res["graph"] = g
    res["pop"], res["jobs"] = float(z.pop.sum()), float(z.jobs.sum())
    near = growth.near_stations(z, net, year, 800)
    res["pop_800m"], res["jobs_800m"] = float(z.pop[near].sum()), float(z.jobs[near].sum())
    res["capture"] = getattr(z, "capture", {})
    rc = ctx.cfg["ridership"]
    res["daily_trips"] = res["transit_commuters"] * rc["round_trip"] / rc["work_share_of_transit_trips"]
    if want_loads:
        res["hop_load"], res["boardings"], run_board = demand.assign_loads(g, res["flows"])
        bpt = float(res["boardings"].sum()) / max(float(res["flows"].sum()), 1e-9)
        res["boardings_per_trip"] = bpt
        share = {}
        for run, b in zip(g.runs, run_board):
            share[run.line.mode] = share.get(run.line.mode, 0.0) + float(b)
        tot = sum(share.values()) or 1.0
        share = {m: v / tot for m, v in share.items()}
    else:
        bpt = rc["boardings_per_trip"]
        share = None
    res["daily_boardings"] = res["daily_trips"] * bpt
    # feeder bus legs (access.feeder) are local-bus boardings, kept apart from rail + BRT
    res["feeder_boardings"] = res["feeder_legs"] * rc["round_trip"] / rc["work_share_of_transit_trips"]
    # boardings by mode (metro, commuter rail, BRT, feeder bus), their sum, and linked trips:
    # each trip counted once however many lines and modes it uses
    res["boardings_by_mode"] = {m: res["daily_boardings"] * share.get(m, 0.0) for m in ctx.cfg["modes"]} \
        if share is not None else {}
    res["boardings_by_mode"]["feeder_bus"] = res["feeder_boardings"]
    res["all_boardings"] = res["daily_boardings"] + res["feeder_boardings"]
    return res


def calibrate_asc(ctx, net, lo=-4.0, hi=2.0, tol=0.01, log=None):
    """Set ctx.cfg.ridership.asc so the calibration year's network carries the
    calibration boardings (config.ridership.calibration), by bisection. Needed
    when an access assumption that also applies to the calibration year changes
    (e.g. a feeder bus table that starts in 2025). Returns the asc."""
    rc = ctx.cfg["ridership"]
    cal = rc["calibration"]
    for _ in range(40):
        rc["asc"] = round((lo + hi) / 2, 4)
        b = run_year(ctx, net, cal["year"])["daily_boardings"]
        if log:
            log(f"  asc {rc['asc']:+.4f}: {b:,.0f} boardings in {cal['year']}")
        if abs(b / cal["rail_boardings"] - 1) < tol:
            break
        lo, hi = (rc["asc"], hi) if b < cal["rail_boardings"] else (lo, rc["asc"])
    return rc["asc"]


def calibrate(ctx, net, log=None):
    """Calibrate both constants for the calibration year: the walk/bike constant
    so config.ridership.calibration.active_share of commuters walk or bike, then
    the transit constant so the network carries the calibration rail boardings.
    Two rounds (they barely interact). Returns (asc, active asc)."""
    rc = ctx.cfg["ridership"]
    cal = rc["calibration"]
    for _ in range(2):
        if rc.get("active") and cal.get("active_share"):
            lo, hi = -8.0, 2.0
            for _ in range(30):
                rc["active"]["asc"] = round((lo + hi) / 2, 4)
                z, od = ctx.year_inputs(net, cal["year"])
                r = run_year(ctx, net, cal["year"], want_loads=False)
                share = r["active_commuters"] / (float(od.sum()) * rc["telework"])
                if log:
                    log(f"  active asc {rc['active']['asc']:+.4f}: {share:.2%} walk or bike")
                if abs(share / cal["active_share"] - 1) < 0.01:
                    break
                lo, hi = (rc["active"]["asc"], hi) if share < cal["active_share"] else (lo, rc["active"]["asc"])
        calibrate_asc(ctx, net, log=log)
    return rc["asc"], rc.get("active", {}).get("asc")


_POOL = {}


def _slim(r, keep_loads):
    """What the reports and the map need from a run_year result (no matrices)."""
    out = {k: v for k, v in r.items() if k not in ("graph", "flows", "comp_from", "comp_to", "jobs_reach",
                                                      "walk_min_dist", "hop_load", "boardings")}
    out["n_st"] = r["graph"].n_st
    out["n_lines"] = len({run.line.id for run in r["graph"].runs})
    if keep_loads:
        out["hop_load"], out["boardings"] = r["hop_load"], r["boardings"]
    return out


def _year_job(y):
    ctx, net, final = _POOL["ctx"], _POOL["net"], _POOL["final"]
    r = run_year(ctx, net, y, want_loads=True)  # loads every year: boardings per trip comes from them
    out = _slim(r, y == final)
    out["coverage"] = coverage(ctx, net, y)
    return y, out


def _without_job(args):
    lid, y = args
    r = run_year(_POOL["ctx"], _POOL["net"].without(lid), y, want_loads=False)
    return lid, y, r["daily_trips"]


def _pool_map(fn, items, ctx, net, final, procs):
    """Map fn over items in forked workers that share ctx and net (or inline when procs <= 1)."""
    _POOL.update(ctx=ctx, net=net, final=final)
    if procs <= 1:
        return [fn(x) for x in items]
    import multiprocessing as mp
    with mp.get_context("fork").Pool(procs) as pool:
        return pool.map(fn, items, chunksize=1)


def evaluate(ctx, net, line_values=True, log=print, procs=None):
    cfg = ctx.cfg
    years = cfg["years"]
    final = max(years)
    year_rows, results = [], {}
    owner = net.track_owner()
    from . import staging
    spend = staging.spend_by_year(net)
    per_year = cfg["budget"]["musd_per_year"]
    procs = procs or max(1, min(3, (os.cpu_count() or 2) - 1))
    for y, r in sorted(_pool_map(_year_job, years, ctx, net, final, procs)):
        results[y] = r
        pcov, jcov = r["coverage"]
        opened = [ln for ln in net.lines.values() if ln.status != "existing"]
        capex = sum(net.line_cost_musd(ln, by_year=y, owner=owner) for ln in opened)
        km = {m: 0.0 for m in cfg["modes"]}
        seen = set()  # count shared track once
        for ln in net.lines.values():
            for s in ln.segments:
                if s.year <= y:
                    key = (ln.mode, round(s.pts[0][0], 4), round(s.pts[0][1], 4), round(s.pts[-1][0], 4), round(s.pts[-1][1], 4))
                    rkey = (ln.mode, key[3], key[4], key[1], key[2])
                    if key in seen or rkey in seen:
                        continue
                    seen.add(key)
                    km[ln.mode] += s.km
        row = {"year": y, "stations": r["n_st"], "lines": r["n_lines"],
               "km_metro": round(km["metro"]), "km_brt": round(km["brt"]), "km_commuter": round(km["commuter"]),
               "capex_busd": round(capex / 1000, 1),
               "spent_busd": round(sum(v for yy, v in spend.items() if yy <= y) / 1000, 1),
               "budget_busd": round(per_year * (y - cfg["existing_year"]) / 1000, 1),
               "pop_covered_pct": round(pcov * 100, 1), "jobs_covered_pct": round(jcov * 100, 1),
               "pop_m": round(r["pop"] / 1e6, 2), "jobs_m": round(r["jobs"] / 1e6, 2),
               "competitive_commutes": round(r["competitive_commutes"]),
               "transit_commuters": round(r["transit_commuters"]),
               "daily_boardings": round(r["daily_boardings"]),
               "daily_trips": round(r["daily_trips"]),
               "all_boardings": round(r["all_boardings"]),
               **{f"boardings_{m}": round(v) for m, v in r["boardings_by_mode"].items()},
               "boardings_per_trip": round(r["boardings_per_trip"], 2),
               "pnr_full_garages": r["pnr_full_garages"],
               "avg_transit_min": round(r["avg_transit_min"], 1)}
        for t, v in r["access_jobs"].items():
            row[f"jobs_{t}min"] = round(v)
        year_rows.append(row)
        log(f"  {net.name} {y}: {row['stations']} stations, {row['daily_boardings']:,} daily boardings, "
            f"{row['competitive_commutes']:,} competitive commutes, "
            f"{row['jobs_45min']:,} jobs in 45 min, ${row['capex_busd']}B")

    fr = results[final]
    g = YearGraph(net, final)       # same runs, in the same order, as the evaluated graph
    caps = {m: cfg["modes"][m]["capacity_pphpd"] for m in cfg["modes"]}
    line_rows = []
    for ln in net.lines.values():
        runs = [(i, run) for i, run in enumerate(g.runs) if run.line is ln]
        loads = [fr["hop_load"][i] for i, _ in runs]
        pkm = sum(float((l * np.array(run.hop_km)).sum()) for l, (_, run) in zip(loads, runs))
        peak = max([float(l.max()) for l in loads if len(l)] or [0.0])
        # crude peak-hour, peak-direction load: 10% of daily one-way commutes in the peak hour, 60% peak direction
        peak_hour = peak * 0.10 * 0.6
        spacing = ln.km / max(len(ln.stop_ids) - 1, 1)
        line_rows.append({
            "line_id": ln.id, "name": ln.name, "mode": ln.mode, "status": ln.status,
            "first_year": ln.first_year, "last_year": ln.last_year,
            "km": round(ln.km, 1), "stops": len(set(ln.stop_ids)), "avg_spacing_km": round(spacing, 2),
            "headway_min": ln.headway_at(final), "cost_musd": round(net.line_cost_musd(ln)),
            "daily_commuters_peak_link": round(peak), "peak_hour_load": round(peak_hour),
            "capacity_used_pct": round(peak_hour / caps[ln.mode] * 100, 1),
            "passenger_km": round(pkm),
        })
    if line_values:
        # Two views of each proposed line's value, because each misleads alone:
        #  at_opening - commutes lost if the line is removed in the year it opens
        #               (fair to trunks that later get shared with branches)
        #  final      - commutes lost if removed from the finished network
        #               (fair to lines whose value depends on what is built later)
        # measured in daily transit trips (each counted once)
        base = {y: results[y]["daily_trips"] for y in years}
        jobs = []
        for row in line_rows:
            if row["status"] == "existing" or row["first_year"] > final:  # existing, or opens after the horizon
                for k in ("marginal_at_opening", "marginal_final", "value_per_musd"):
                    row[k] = ""
                continue
            y0 = min(y for y in years if y >= row["first_year"])
            row["_y0"] = y0
            jobs += [(row["line_id"], y0), (row["line_id"], final)]
        without = {(lid, y): v for lid, y, v in _pool_map(_without_job, jobs, ctx, net, final, procs)}
        for row in line_rows:
            y0 = row.pop("_y0", None)
            if y0 is None:
                continue
            m0 = base[y0] - without[(row["line_id"], y0)]
            m1 = base[final] - without[(row["line_id"], final)]
            row["marginal_at_opening"] = round(m0)
            row["marginal_final"] = round(m1)
            best = max(m0, m1)
            row["value_per_musd"] = round(best / row["cost_musd"], 2) if row["cost_musd"] else ""
        log(f"  {net.name}: line values for {sum(1 for r in line_rows if r['status'] != 'existing')} proposed lines")

    act = ctx.station_activity(net)
    st_lines = net.station_lines()
    st_rows = []
    for sid, s in net.stations.items():
        if sid not in st_lines:
            continue
        bi = g.sidx.get(sid)
        st_rows.append({"station_id": sid, "name": s.name, "lat": s.lat, "lon": s.lon,
                        "year_opens": net.station_year(sid),
                        "lines": ";".join(net.lines[l].name for l in st_lines[sid]),
                        "modes": ";".join(sorted({net.lines[l].mode for l in st_lines[sid]})),
                        "pop_1km": round(act[sid][0]), "jobs_1km": round(act[sid][1]),
                        "boardings_final": round(float(fr["boardings"][bi])) if bi is not None else 0})
    return {"years": year_rows, "lines": line_rows, "stations": st_rows, "results": results}


def write(out_dir, ev):
    os.makedirs(out_dir, exist_ok=True)
    for name in ("years", "lines", "stations"):
        rows = ev[name]
        if not rows:
            continue
        with open(os.path.join(out_dir, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
