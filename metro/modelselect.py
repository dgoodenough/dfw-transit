"""Full-model selection (step 4b): the demand model, not the sketch, decides which lines stay.

The sketch (metro/sketch.py) values a candidate by commutes between its own stations: no
transfers, no feeder buses, no network. Here the greedy sketch selection runs with a lower floor
(selection.model.pool_floor_factor) to give a wider pool, and the full model (dfwt) prunes it:

  value of a line = mean of two measures, on one land use (every pool line open, in judge_year,
                    with the metro's growth and station-area development: dfwt evaluate._all_open,
                    as DFW Transit's final_values):
                      without  daily trips the pool network loses without the line
                      alone    daily trips the line adds alone to today's network
                    per $M of capital + staging.value_opex_years x operating cost (the sketch's
                    measure, now in the model's trips)

Each round drops the worse half of the lines below selection.model.min_trips_per_musd (at least
one) and values the rest again, since a dropped line's riders may move to its neighbours; then,
if the pool costs more than the budget, the lowest-valued lines go until it fits. The lines that
stay open in order of value. The two measures together keep both of two parallel lines from
looking worthless because each makes the other redundant (alone counts each in full).
"""
import copy
import math
import os
import re

from dfwt import evaluate

_POOL = {}


def _job(args):
    lid, mode = args
    net, gen = _POOL["net"], _POOL["gen"]
    off = {"full": set(), "none": gen, "without": {lid}, "alone": gen - {lid}}[mode]
    sub = copy.copy(net)
    sub.lines = {k: v for k, v in net.lines.items() if k not in off}
    if not sub.lines:   # a metro with no transit today, every new line off: no transit trips
        return lid, mode, 0.0
    r = evaluate.run_year(_POOL["ctx"], sub, _POOL["year"], want_loads=False, inputs=_POOL["inputs"])
    return lid, mode, r["daily_trips"]


def values(ctx, net, gen_ids, year, procs=None):
    """{line_id: (without, alone)} daily trips for each line in gen_ids."""
    net = evaluate._all_open(net)
    gen = set(gen_ids)
    jobs = [(None, "full"), (None, "none")] + [(l, m) for l in sorted(gen) for m in ("without", "alone")]
    _POOL.update(ctx=ctx, net=net, gen=gen, year=year, inputs=ctx.year_inputs(net, year))
    procs = procs or max(1, min(3, (os.cpu_count() or 2) - 1))
    if procs <= 1 or len(jobs) <= 4:
        res = [_job(j) for j in jobs]
    else:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procs) as pool:
            res = pool.map(_job, jobs, chunksize=1)
    out = {(lid, mode): t for lid, mode, t in res}
    full, none = out[(None, "full")], out[(None, "none")]
    return {l: (full - out[(l, "without")], out[(l, "alone")] - none) for l in gen}, full, none


def prune(pool, build_net, ctx, budget, gp, cfg, year, log=print):
    """Prune `pool` (chosen Cands) by the full model. build_net(cands) -> (Network, {line_id: cand uid}).
    Sets each kept and dropped cand's model_trips / model_ratio; returns (kept, rounds)."""
    mc = gp["selection"]["model"]
    floor = mc["min_trips_per_musd"]
    years = cfg["staging"].get("value_opex_years", 20)
    pool = list(pool)
    rounds = []

    def value_all():
        net, uid_of = build_net(pool)
        v, full, none = values(ctx, net, uid_of.keys(), year, mc.get("procs"))
        by = {c.uid: c for c in pool}
        for lid, (w, a) in v.items():
            c = by[uid_of[lid]]
            c.model_without, c.model_alone = w, a
            c.model_trips = (w + a) / 2
            c.model_ratio = c.model_trips / max(c.capital + years * c.opex, 1.0)
        return full, none

    while pool:
        full, none = value_all()
        below = sorted((c for c in pool if c.model_ratio < floor), key=lambda c: c.model_ratio)
        rounds.append({"lines": len(pool), "trips": full - none, "below": len(below)})
        log(f"  full model, {year}: {len(pool)} lines, {full - none:,.0f} new daily trips; {len(below)} below {floor}/$M")
        if not below:
            break
        for c in below[:max(1, math.ceil(len(below) / 2))]:
            c.status = "rejected"
            c.reason = (f"full model: {c.model_trips:,.0f} new daily trips in {year} "
                        f"({c.model_ratio:.2f} per $M incl. opex, below {floor})")
            pool.remove(c)
    over = False
    while pool and sum(c.capital for c in pool) > budget:
        c = min(pool, key=lambda c: c.model_ratio)
        c.status, c.reason = "rejected", f"full model: over budget, lowest value ({c.model_ratio:.2f} per $M)"
        pool.remove(c)
        over = True
    if over and pool:
        full, none = value_all()
        rounds.append({"lines": len(pool), "trips": full - none, "below": 0})
    pool.sort(key=lambda c: -c.model_ratio)
    for k, c in enumerate(pool, 1):
        c.status, c.order = "chosen", k
        c.reason = (f"full model: {c.model_trips:,.0f} new daily trips in {year} ({c.model_ratio:.2f} per $M incl. "
                    f"opex; {c.model_without:,.0f} lost without it, {c.model_alone:,.0f} alone); sketch: {c.reason}")
    return pool, rounds


def line_cands(tables):
    """{line_id: cand uid} for the generated lines of `tables` (output.tables notes)."""
    out = {}
    for r in tables["lines.csv"]:
        mm = re.search(r"generated \(([A-Z]\d+)\)", r.get("notes") or "")
        if mm:
            out[r["line_id"]] = mm.group(1)
    return out
