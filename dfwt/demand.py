"""Zones, commute demand, and the per-year transit evaluation.

Zones are 2020 Census block groups (data/metroplex_density.csv: population and
2022 LODES jobs). Commute flows come from LODES origin-destination data when
data/raw/od_tracts.csv is present; otherwise a doubly-constrained gravity model
is synthesized from zone population and jobs (see `gravity`). Either way the
flows are expressed at block-group level.
"""
import csv
import os

import numpy as np

from . import config, geo

CHUNK = 400


class Zones:
    def __init__(self, cfg):
        rows = list(csv.DictReader(open(config.path("data", "metroplex_density.csv"), encoding="utf-8-sig")))
        self.ids = [r["geoid"] for r in rows]
        self.pop = np.array([float(r["pop"]) for r in rows])
        self.jobs = np.array([float(r["jobs"]) for r in rows])
        self.lat = np.array([float(r["lat"]) for r in rows])
        self.lon = np.array([float(r["lon"]) for r in rows])
        pj = geo.Projector()
        self.x, self.y = pj.xy(self.lat, self.lon)
        self.n = len(rows)
        d = cfg["drive"]
        self.cfg = cfg

    def dist_rows(self, i0, i1):
        dx = self.x[i0:i1, None] - self.x[None, :]
        dy = self.y[i0:i1, None] - self.y[None, :]
        return np.sqrt(dx * dx + dy * dy).astype(np.float32)

    def drive_min(self, dist):
        d = self.cfg["drive"]
        return dist * d["circuity"] / d["speed_kmh"] * 60 + d["terminal_min"]


def gravity(zones, cfg, beta=None):
    """Doubly-constrained gravity: T_ij = A_i O_i B_j D_j exp(-beta * drive_ij).
    O_i (home-end commuters) scales with population, D_j with jobs; both sum to
    config.demand.total_commutes. Returns a float32 matrix."""
    dc = cfg["demand"]
    beta = dc["gravity_beta_per_min"] if beta is None else beta
    total = dc["total_commutes"]
    O = zones.pop / zones.pop.sum() * total
    D = zones.jobs / zones.jobs.sum() * total
    n = zones.n
    K = np.empty((n, n), dtype=np.float32)
    for i0 in range(0, n, CHUNK):
        i1 = min(n, i0 + CHUNK)
        K[i0:i1] = np.exp(-beta * zones.drive_min(zones.dist_rows(i0, i1)))
    B = np.ones(n)
    for _ in range(dc["gravity_iterations"]):
        A = 1.0 / np.maximum(K @ (B * D), 1e-30)
        B = 1.0 / np.maximum(K.T @ (A * O), 1e-30)
    K *= (A * O)[:, None].astype(np.float32)
    K *= (B * D)[None, :].astype(np.float32)
    return K


def lodes_or_gravity(zones, cfg):
    p = config.path(cfg["demand"]["lodes_od_path"])
    if not os.path.exists(p):
        return gravity(zones, cfg), "gravity"
    # LODES at tract level -> spread to block groups by population (home) and jobs (work)
    tract_of = np.array([z[:11] for z in zones.ids])
    tracts, inv = np.unique(tract_of, return_inverse=True)
    tix = {t: i for i, t in enumerate(tracts)}
    pop_t = np.bincount(inv, weights=zones.pop, minlength=len(tracts))
    jobs_t = np.bincount(inv, weights=zones.jobs, minlength=len(tracts))
    flows = np.zeros((len(tracts), len(tracts)))
    with open(p) as f:
        for r in csv.DictReader(f):
            h, w = tix.get(r["h_tract"]), tix.get(r["w_tract"])
            if h is not None and w is not None:
                flows[h, w] += float(r["jobs"])
    hs = zones.pop / np.maximum(pop_t[inv], 1)
    ws = zones.jobs / np.maximum(jobs_t[inv], 1)
    od = np.empty((zones.n, zones.n), dtype=np.float32)
    for i0 in range(0, zones.n, CHUNK):
        i1 = min(zones.n, i0 + CHUNK)
        od[i0:i1] = flows[inv[i0:i1]][:, inv] * hs[i0:i1, None] * ws[None, :]
    return od, "lodes"


class Access:
    """Zone <-> station connectors for one year's open stations."""

    def __init__(self, zones, net, graph, cfg):
        ac = cfg["access"]
        k = ac["max_access_stations"]
        sids = graph.station_ids
        slat = np.array([net.stations[s].lat for s in sids])
        slon = np.array([net.stations[s].lon for s in sids])
        sx, sy = geo.Projector().xy(slat, slon)
        # which stations allow park & ride: commuter stations and line termini
        pnr = np.zeros(len(sids), dtype=bool)
        idx = graph.sidx
        for run in graph.runs:
            if run.line.mode == "commuter":
                for s in run.stops:
                    pnr[idx[s]] = True
            pnr[idx[run.stops[0]]] = pnr[idx[run.stops[-1]]] = True
        walk_km = ac["walk_max_m"] / 1000
        run_cols = [np.array(sorted({idx[s] for s in run.stops})) for run in graph.runs]
        k = min(k, len(run_cols))
        nz = zones.n
        self.acc_st = np.zeros((nz, k), dtype=np.int32)
        self.acc_t = np.full((nz, k), np.inf, dtype=np.float32)
        self.egr_st = np.zeros((nz, k), dtype=np.int32)
        self.egr_t = np.full((nz, k), np.inf, dtype=np.float32)
        self.walk_min_dist = np.full(nz, np.inf, dtype=np.float32)
        for i0 in range(0, nz, CHUNK):
            i1 = min(nz, i0 + CHUNK)
            d = np.sqrt((zones.x[i0:i1, None] - sx[None, :]) ** 2 + (zones.y[i0:i1, None] - sy[None, :]) ** 2)
            self.walk_min_dist[i0:i1] = d.min(axis=1)
            walk = np.where(d <= walk_km, d * ac["circuity"] / ac["walk_speed_kmh"] * 60, np.inf)
            drive = np.where(pnr[None, :] & (d <= ac["pnr_max_km"]),
                             d * ac["circuity"] / ac["pnr_speed_kmh"] * 60 + ac["pnr_penalty_min"], np.inf)
            acc = np.minimum(walk, drive)
            for arr, st, t in ((acc, self.acc_st, self.acc_t), (walk, self.egr_st, self.egr_t)):
                st[i0:i1], t[i0:i1] = _diverse_nearest(arr, run_cols, k)


def _diverse_nearest(arr, run_cols, k):
    """Pick up to k connector stations per zone: the nearest stop of each line run
    first, so a nearby stop on a minor line can't crowd out the trunk line."""
    m = arr.shape[0]
    cand_st = np.zeros((m, len(run_cols)), dtype=np.int32)
    cand_t = np.full((m, len(run_cols)), np.inf, dtype=np.float32)
    for j, cols in enumerate(run_cols):
        sub = arr[:, cols]
        best = np.argmin(sub, axis=1)
        cand_st[:, j] = cols[best]
        cand_t[:, j] = sub[np.arange(m), best]
    order = np.argsort(cand_t, axis=1)[:, :k]
    return np.take_along_axis(cand_st, order, axis=1), np.take_along_axis(cand_t, order, axis=1)


def evaluate(zones, od, net, graph, cfg, want_loads=True):
    """Run the year: transit times for every zone pair, competitive commutes,
    accessibility, and (optionally) station-pair flows for load assignment."""
    T = graph.T
    acc = Access(zones, net, graph, cfg)
    cc = cfg["competitive"]
    thresholds = cfg["accessibility"]["thresholds_min"]
    nz, ns = zones.n, graph.n_st
    k = acc.acc_st.shape[1]
    comp_total, comp_from = 0.0, np.zeros(nz)
    comp_to = np.zeros(nz)
    jobs_reach = {t: np.zeros(nz) for t in thresholds}
    flows = np.zeros((ns, ns)) if want_loads else None
    tt_sum, tt_w = 0.0, 0.0
    for i0 in range(0, nz, CHUNK):
        i1 = min(nz, i0 + CHUNK)
        m = i1 - i0
        # origin zone -> any station b, via best access station a
        R = np.full((m, ns), np.inf, dtype=np.float32)
        Ra = np.zeros((m, ns), dtype=np.int32)
        for j in range(k):
            a = acc.acc_st[i0:i1, j]
            cand = acc.acc_t[i0:i1, j, None] + T[a]
            better = cand < R
            R = np.where(better, cand, R)
            Ra = np.where(better, a[:, None], Ra)
        # -> destination zone via best egress station b
        TT = np.full((m, nz), np.inf, dtype=np.float32)
        Bst = np.zeros((m, nz), dtype=np.int32)
        for j in range(k):
            b = acc.egr_st[:, j]
            cand = R[:, b] + acc.egr_t[None, :, j]
            better = cand < TT
            TT = np.where(better, cand, TT)
            Bst = np.where(better, b[None, :], Bst)
        dist = zones.dist_rows(i0, i1)
        drive = zones.drive_min(dist)
        for t in thresholds:
            jobs_reach[t][i0:i1] = ((TT <= t) * zones.jobs[None, :]).sum(axis=1)
        ok = (TT <= cc["ratio"] * drive + cc["slack_min"]) & (TT <= cc["max_min"]) & (dist > cc["min_km"])
        q = np.where(ok, od[i0:i1], 0.0)
        comp_total += float(q.sum())
        comp_from[i0:i1] = q.sum(axis=1)
        comp_to += q.sum(axis=0)
        fin = np.isfinite(TT) & ok
        tt_sum += float((np.where(fin, TT, 0) * q).sum())
        tt_w += float(q.sum())
        if want_loads:
            oi, dj = np.nonzero(q)
            if len(oi):
                b = Bst[oi, dj]
                a = Ra[oi, b]
                np.add.at(flows, (a, b), q[oi, dj])
    pop = zones.pop
    return {
        "competitive_commutes": comp_total,
        "comp_from": comp_from,
        "comp_to": comp_to,
        "jobs_reach": jobs_reach,
        "access_jobs": {t: float((jobs_reach[t] * pop).sum() / pop.sum()) for t in thresholds},
        "avg_transit_min": tt_sum / tt_w if tt_w else 0.0,
        "flows": flows,
        "walk_min_dist": acc.walk_min_dist,
    }


def assign_loads(graph, flows):
    """Push station-pair flows along shortest paths. Returns per-run hop loads
    (list per run of per-hop volumes, both directions summed) and per-station boardings."""
    hop_load = [np.zeros(max(len(r.stops) - 1, 0)) for r in graph.runs]
    boardings = np.zeros(graph.n_st)
    info = graph.node_info
    stop_pos = []
    for r in graph.runs:
        pos = {}
        for i, s in enumerate(r.stops):
            pos.setdefault(s, i)
        stop_pos.append(pos)
    ns = graph.n_st
    for a in range(ns):
        row = flows[a]
        dests = np.nonzero(row)[0]
        if not len(dests):
            continue
        pred = graph.preds[a]
        # accumulate flow onto nodes of the predecessor tree (each node's subtree demand)
        node_flow = {}
        for b in dests:
            if b == a:
                continue
            u = b
            v = row[b]
            while u != -1 and u != a:
                node_flow[u] = node_flow.get(u, 0.0) + v
                u = pred[u]
        for u, v in node_flow.items():
            p = pred[u]
            if p == -1:
                continue
            ku, kp = info[u], info[p]
            if ku[0] == "L" and kp[0] == "L" and ku[2] == kp[2]:
                ri = ku[2]
                i, j = sorted((stop_pos[ri][ku[1]], stop_pos[ri][kp[1]]))
                hop_load[ri][i] += v
            elif ku[0] == "L" and kp[0] == "P":
                boardings[graph.sidx[kp[1]]] += v
    return hop_load, boardings
