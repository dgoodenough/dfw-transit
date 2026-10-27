"""dfwt's demand model on any metro's inputs.

dfwt reads DFW from fixed paths (demand.Zones reads data/metroplex_density.csv and every
geo.Projector() defaults to a DFW origin). Here the zones come from the metro's zones.csv
and the projection origin is moved to the metro for the duration of a run (`projection`),
so `Network.from_tables` + `evaluate.run_year` run unchanged.

The model's behavioural parameters (logit, access, waits) are DFW's calibration
(config.json ridership.asc fitted to DFW's 2025 rail boardings); elsewhere they are a
transfer, not a calibration, and the report says so. Region-specific config entries are
replaced for other metros: downtown cores and paid parking come from the detected downtown
centers (DFW's own CBD price), total commutes scale with jobs (DFW's commutes per job),
late-night service names no lines (growth runs "even", so DFW's county weights are unused).
"""
import contextlib
import copy
import os

import numpy as np

from dfwt import config, demand, evaluate, geo


@contextlib.contextmanager
def projection(m):
    """Every geo.Projector() in dfwt projects around the metro while this is open."""
    old = geo.Projector.__init__.__defaults__
    geo.Projector.__init__.__defaults__ = (m.lat0, m.lon0)
    try:
        yield
    finally:
        geo.Projector.__init__.__defaults__ = old


def metro_cfg(m, centers, base=None):
    """config.json adapted to metro m (unchanged for DFW, the model's home)."""
    cfg = copy.deepcopy(base or config.load())
    if m.id == "dfw":
        return cfg
    downtowns = [c for c in centers if c.kind == "downtown"]
    dfw_jobs_per_commute = cfg["demand"]["total_commutes"] / 3963000.0   # DFW: 3.32M commutes, 3.96M LODES jobs
    jobs = m.jobs.sum() if m.jobs_ok else m.pop.sum() * 0.53   # US: ~0.53 jobs per resident (flagged when used)
    cfg["demand"]["total_commutes"] = float(jobs * dfw_jobs_per_commute)
    cfg["demand"]["lodes_od_path"] = m.od_path or os.path.join(m.folder, "od_tracts.csv")
    price = max((v.get("usd_per_day", 0) for v in cfg["ridership"]["paid_parking"].values() if isinstance(v, dict)),
                default=0)
    cfg["cores"] = {"_doc": "detected downtowns (metro/centers.py)"}
    cfg["ridership"]["paid_parking"] = {"_doc": "detected downtowns at DFW's CBD price"}
    for c in downtowns:
        cfg["cores"][c.name] = {"lat": c.lat, "lon": c.lon, "radius_km": 1.5}
        cfg["ridership"]["paid_parking"][c.name] = {"lat": c.lat, "lon": c.lon, "radius_km": 1.5, "usd_per_day": price}
    cfg["operating"]["late_night"]["lines"] = []
    return cfg


def zones(m, cfg):
    """A dfwt.demand.Zones built from the metro's zones (call inside `projection(m)`)."""
    z = demand.Zones.__new__(demand.Zones)
    z.ids = list(m.geoid)
    z.pop = m.pop.astype(float).copy()
    # without jobs data destinations follow population (flagged by the caller)
    z.jobs = m.jobs.astype(float).copy() if m.jobs_ok else m.pop.astype(float) * 0.53
    z.lat, z.lon = m.lat.copy(), m.lon.copy()
    z.x, z.y = geo.Projector().xy(z.lat, z.lon)
    z.n = m.n
    z.cfg = cfg
    z._park_cache = {}
    return z


def context(m, cfg):
    """An evaluate.Context on the metro's zones and commute flows."""
    ctx = evaluate.Context.__new__(evaluate.Context)
    ctx.cfg = cfg
    ctx.zones = zones(m, cfg)
    if m.id == "dfw":
        ctx.od, ctx.od_source = demand.lodes_or_gravity(ctx.zones, cfg)
    elif m.od_path and m.jobs_ok:
        ctx.od, ctx.od_source = demand.lodes_or_gravity(ctx.zones, cfg)
    else:
        ctx.od, ctx.od_source = demand.gravity(ctx.zones, cfg), "gravity"
    ctx._seed = (None, None)
    ctx._year = {}
    return ctx


def all_open(net):
    return evaluate._all_open(net)


def run_today(ctx, net, base_net, want_loads=True):
    """run_year with every line of `net` open, on today's land use: the year after
    existing_year, zones grown only by the regional forecast for that one year (no
    station-area growth: the land use is that of `base_net`, today's lines)."""
    y = ctx.cfg["existing_year"] + 1
    inputs = ctx.year_inputs(base_net, y)
    r = evaluate.run_year(ctx, all_open(net), y, want_loads=want_loads, inputs=inputs)
    out = {k: r[k] for k in ("daily_trips", "daily_boardings", "transit_commuters", "pop_800m", "jobs_800m", "pop",
                             "jobs", "all_boardings", "feeder_boardings", "competitive_commutes")}
    out["boardings_by_mode"] = r.get("boardings_by_mode", {})
    out["access_jobs_45"] = r["access_jobs"].get(45, 0.0)
    out["stations"] = r["graph"].n_st
    return out


def gravity_od(m, cfg):
    """Zone-to-zone commutes for the sketch (same source the model uses)."""
    with projection(m):
        ctx = context(m, cfg)
    return ctx, np.asarray(ctx.od, dtype=np.float32)
