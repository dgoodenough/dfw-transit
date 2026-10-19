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
        if getattr(self, "_dist", None) is None:   # all pairs, once (shared by grown copies)
            dx = self.x[:, None] - self.x[None, :]
            dy = self.y[:, None] - self.y[None, :]
            self._dist = np.sqrt(dx * dx + dy * dy).astype(np.float32)
        return self._dist[i0:i1]

    def paid_parking_utility(self):
        """Per destination zone: utility of not paying for parking there."""
        if getattr(self, "_park", None) is None:
            rc = self.cfg["ridership"]
            u = np.zeros(self.n)
            for name, p in rc["paid_parking"].items():
                if name.startswith("_"):
                    continue
                px, py = geo.Projector().xy(p["lat"], p["lon"])
                d = np.sqrt((self.x - px) ** 2 + (self.y - py) ** 2)
                u = np.maximum(u, np.where(d <= p["radius_km"], rc["b_per_dollar"] * p["usd_per_day"] / 2, 0.0))
            self._park = u.astype(np.float32)
        return self._park

    cong = 1.0  # peak drive-time multiplier for the year (growth.grown_zones sets it)

    def drive_min(self, dist):
        d = self.cfg["drive"]
        return dist * (d["circuity"] / d["speed_kmh"] * 60 * self.cong) + d["terminal_min"]


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


def balance(K, O, D, iters):
    """Doubly-constrained balancing of a seed matrix K to row totals O and column
    totals D: returns K * a_i * b_j (a new float32 matrix)."""
    B = np.ones(len(D))
    for _ in range(iters):  # float32 vectors keep numpy from copying K to float64 each pass
        A = 1.0 / np.maximum(K @ (B * D).astype(np.float32), 1e-30)
        B = 1.0 / np.maximum(K.T @ (A * O).astype(np.float32), 1e-30)
    out = K * (A * O)[:, None].astype(np.float32)
    out *= (B * D)[None, :].astype(np.float32)
    return out


def gravity_seed(zones, cfg):
    """exp(-beta * drive) for every zone pair at this zones' congestion."""
    beta = cfg["demand"]["gravity_beta_per_min"]
    n = zones.n
    K = np.empty((n, n), dtype=np.float32)
    for i0 in range(0, n, CHUNK):
        i1 = min(n, i0 + CHUNK)
        K[i0:i1] = np.exp(-beta * zones.drive_min(zones.dist_rows(i0, i1)))
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
        # which stations allow park & ride: commuter stations and each line's planned
        # termini (where the garage gets built). A temporary end of a partly built line
        # gets none, or every stub would look like a park & ride hub.
        pnr = np.zeros(len(sids), dtype=bool)
        spaces = np.zeros(len(sids))
        sp = ac["pnr_spaces"]
        idx = graph.sidx
        for run in graph.runs:
            if run.line.mode == "commuter":
                for s in run.stops:
                    pnr[idx[s]] = True
                    spaces[idx[s]] = max(spaces[idx[s]], sp["commuter_station"])
            full = net.lines.get(run.line.id, run.line)
            for s in (full.stop_ids[0], full.stop_ids[-1]):
                if s in idx:
                    pnr[idx[s]] = True
                    spaces[idx[s]] = max(spaces[idx[s]], sp["terminus"])
        # people a garage can serve per day (one car per commuter, plus drop-offs)
        self.pnr_cap = spaces * ac["pnr_people_per_space"]
        walk_km = ac["walk_max_m"] / 1000
        run_cols = [np.array(sorted({idx[s] for s in run.stops})) for run in graph.runs]
        k = min(k, len(run_cols))
        nz = zones.n
        self.acc_st = np.zeros((nz, k), dtype=np.int32)
        self.acc_t = np.full((nz, k), np.inf, dtype=np.float32)
        self.acc_pnr = np.zeros((nz, k), dtype=bool)
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
            wsel = np.take_along_axis(walk, self.acc_st[i0:i1], axis=1)
            self.acc_pnr[i0:i1] = self.acc_t[i0:i1] < wsel - 1e-6


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
    expected transit riders, accessibility, and (optionally) station-pair rider
    flows for load assignment.

    Park & ride garages hold a limited number of cars (config.access.pnr_spaces).
    Trips that reach transit by driving are tallied per garage; where a garage's
    riders exceed its capacity, its trips are scaled down to fit.
    """
    T = graph.T
    acc = Access(zones, net, graph, cfg)
    cc = cfg["competitive"]
    rc = cfg["ridership"]
    thresholds = cfg["accessibility"]["thresholds_min"]
    nz, ns = zones.n, graph.n_st
    k = acc.acc_st.shape[1]
    park = zones.paid_parking_utility()
    jobs_reach = {t: np.zeros(nz) for t in thresholds}
    # walk-access tallies, and per-garage park & ride tallies (scaled to capacity at the end)
    comp_w, rid_w, tt_w_sum = 0.0, 0.0, 0.0
    comp_from_w, comp_to_w = np.zeros(nz), np.zeros(nz)
    comp_p, rid_p, tt_p_sum = np.zeros(ns), np.zeros(ns), np.zeros(ns)
    comp_from_p, comp_to_p = np.zeros(ns * nz), np.zeros(ns * nz)
    flows_w = np.zeros((ns, ns)) if want_loads else None
    flows_p = np.zeros((ns, ns)) if want_loads else None
    for i0 in range(0, nz, CHUNK):
        i1 = min(nz, i0 + CHUNK)
        m = i1 - i0
        # origin zone -> any station b, via best access station a
        R = np.full((m, ns), np.inf, dtype=np.float32)
        Ra = np.zeros((m, ns), dtype=np.int32)
        Rp = np.zeros((m, ns), dtype=bool)
        Rt = np.zeros((m, ns), dtype=np.float32)     # access minutes of the chosen access leg
        for j in range(k):
            a = acc.acc_st[i0:i1, j]
            cand = acc.acc_t[i0:i1, j, None] + T[a]
            better = cand < R
            R = np.where(better, cand, R)
            Ra = np.where(better, a[:, None], Ra)
            Rp = np.where(better, acc.acc_pnr[i0:i1, j, None], Rp)
            Rt = np.where(better, acc.acc_t[i0:i1, j, None], Rt)
        # -> destination zone via best egress station b
        TT = np.full((m, nz), np.inf, dtype=np.float32)
        Bst = np.zeros((m, nz), dtype=np.int32)
        OVT = np.zeros((m, nz), dtype=np.float32)    # access + egress minutes
        for j in range(k):
            b = acc.egr_st[:, j]
            cand = R[:, b] + acc.egr_t[None, :, j]
            better = cand < TT
            TT = np.where(better, cand, TT)
            Bst = np.where(better, b[None, :], Bst)
            OVT = np.where(better, Rt[:, b] + acc.egr_t[None, :, j], OVT)
        rows = np.arange(m)[:, None]
        Ast = Ra[rows, Bst]                       # access station of each pair
        P = Rp[rows, Bst]                         # reached by park & ride?
        dist = zones.dist_rows(i0, i1)
        drive = zones.drive_min(dist)
        for t in thresholds:
            jobs_reach[t][i0:i1] = ((TT <= t) * zones.jobs[None, :]).sum(axis=1)
        usable = np.isfinite(TT) & (TT <= cc["max_min"]) & (dist > cc["min_km"])
        ok = usable & (TT <= cc["ratio"] * drive + cc["slack_min"])
        odc = od[i0:i1]
        q = np.where(ok, odc, 0.0)
        # expected transit commuters: binary logit (config.ridership)
        du = (rc["asc"] + rc["b_ivt_per_min"] * (drive - np.where(usable, TT, 0))
              - rc["b_ovt_extra_per_min"] * OVT + park[None, :])
        share = 1.0 / (1.0 + np.exp(-du))
        rq = np.where(usable, odc * share * rc["telework"], 0.0)
        tt = np.where(ok, TT, 0)
        w, p = ~P, P
        comp_w += float(q[w].sum())
        rid_w += float(rq[w].sum())
        tt_w_sum += float((tt * q)[w].sum())
        comp_from_w[i0:i1] += np.where(w, q, 0).sum(axis=1)
        comp_to_w += np.where(w, q, 0).sum(axis=0)
        if p.any():
            ap = Ast[p]
            comp_p += np.bincount(ap, weights=q[p], minlength=ns)
            rid_p += np.bincount(ap, weights=rq[p], minlength=ns)
            tt_p_sum += np.bincount(ap, weights=(tt * q)[p], minlength=ns)
            zi = np.broadcast_to(np.arange(i0, i1)[:, None], (m, nz))[p]
            zj = np.broadcast_to(np.arange(nz)[None, :], (m, nz))[p]
            comp_from_p += np.bincount(ap * nz + zi, weights=q[p], minlength=ns * nz)
            comp_to_p += np.bincount(ap * nz + zj, weights=q[p], minlength=ns * nz)
        if want_loads:
            for mask, fl in ((w, flows_w), (p, flows_p)):
                sel = mask & (rq > 0)
                if sel.any():
                    np.add.at(fl, (Ast[sel], Bst[sel]), rq[sel])
    # garages over capacity: scale their park & ride trips down to fit
    f = np.where(rid_p > acc.pnr_cap, acc.pnr_cap / np.maximum(rid_p, 1e-9), 1.0)
    comp_total = comp_w + float((f * comp_p).sum())
    riders = rid_w + float((f * rid_p).sum())
    comp_from = comp_from_w + (f[:, None] * comp_from_p.reshape(ns, nz)).sum(axis=0)
    comp_to = comp_to_w + (f[:, None] * comp_to_p.reshape(ns, nz)).sum(axis=0)
    tt_sum = tt_w_sum + float((f * tt_p_sum).sum())
    flows = flows_w + f[:, None] * flows_p if want_loads else None
    pop = zones.pop
    return {
        "competitive_commutes": comp_total,
        "transit_commuters": riders,
        "pnr_riders": float(np.minimum(rid_p, acc.pnr_cap).sum()),
        "pnr_full_garages": int((rid_p > acc.pnr_cap).sum()),
        "comp_from": comp_from,
        "comp_to": comp_to,
        "jobs_reach": jobs_reach,
        "access_jobs": {t: float((jobs_reach[t] * pop).sum() / pop.sum()) for t in thresholds},
        "avg_transit_min": tt_sum / comp_total if comp_total else 0.0,
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
