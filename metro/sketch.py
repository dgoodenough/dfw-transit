"""Sketch demand: how many daily trips a single line adds (used to rank candidates).

For a line with stations along it:
  * walk catchment: zones within walk_km of a station (nearest station; walk minutes at
    config access.walk_speed_kmh x walk_circuity);
  * park & ride catchment (home end only): zones beyond walking and within
    access.pnr_max_km (but not closer than pnr_min_km) of a garage station (regional-rail
    stations and the termini of other modes, as in dfwt), driving at pnr_speed_kmh plus
    pnr_penalty_min; garage riders are capped at pnr_spaces x pnr_people_per_space;
  * for each zone pair (i, j) served from two different stations: door-to-door transit time =
    access + perceived wait (config wait) + in-vehicle minutes (cruise speed and stop
    penalty) + egress, against the peak drive time (dfwt.demand.drive_minutes); the transit
    share is the config.json ridership logit (asc, in-vehicle, out-of-vehicle, ratio and
    driving-cost terms, park & ride constant) against driving;
  * commuters = commutes (gravity or LODES, the same flows the full model uses) x share x
    telework; daily trips = commuters x round_trip / work_share_of_transit_trips.

The value of a line is the commuters it adds over the best share any chosen or existing line
already gives each zone pair (`best`), so a line duplicating another is worth little. Trips
that need a transfer between two lines are not counted here (the full model does).
"""
import numpy as np

from dfwt import demand

from . import geom


class Sketch:
    def __init__(self, m, cfg, od, walk_km):
        self.m, self.cfg, self.od = m, cfg, od
        self.walk_km = walk_km
        self.zidx = geom.ZoneIndex(m, 1.0)
        self.best = np.zeros((m.n, m.n), dtype=np.float32)
        rc = cfg["ridership"]
        self.trip_factor = rc["round_trip"] / rc["work_share_of_transit_trips"]

    def catchment(self, stations, pnr):
        """Zones served by a line: (zone idx, station idx, access min, ovt min, is_pnr, egress_ok)."""
        ac = self.cfg["access"]
        m = self.m
        best = {}
        for k, (x, y) in enumerate(stations):
            z = self.zidx.near(x, y, self.walk_km)
            d = np.hypot(m.x[z] - x, m.y[z] - y)
            for zi, di in zip(z.tolist(), d.tolist()):
                if zi not in best or di < best[zi][1]:
                    best[zi] = (k, di)
        walk = {zi: (k, d * ac["walk_circuity"] / ac["walk_speed_kmh"] * 60) for zi, (k, d) in best.items()}
        drive = {}
        for k in pnr:
            x, y = stations[k]
            z = self.zidx.near(x, y, ac["pnr_max_km"])
            d = np.hypot(m.x[z] - x, m.y[z] - y)
            for zi, di in zip(z.tolist(), d.tolist()):
                if zi in walk or di < ac["pnr_min_km"]:
                    continue
                t = di * ac["circuity"] / ac["pnr_speed_kmh"] * 60 + ac["pnr_penalty_min"]
                if zi not in drive or t < drive[zi][1]:
                    drive[zi] = (k, t)
        zs = list(walk) + list(drive)
        st = [walk[z][0] for z in walk] + [drive[z][0] for z in drive]
        acc = [walk[z][1] for z in walk] + [drive[z][1] for z in drive]
        ovt = [walk[z][1] for z in walk] + [0.0] * len(drive)
        is_p = [False] * len(walk) + [True] * len(drive)
        return (np.array(zs, dtype=int), np.array(st, dtype=int), np.array(acc), np.array(ovt),
                np.array(is_p, dtype=bool))

    def line(self, mode, stations, along, pnr, pnr_cap, headway=None, commit=False):
        """Evaluate one line. stations [(x, y)], along = km along the line of each, pnr = garage
        station indices, pnr_cap = {station idx: max park & ride commuters}. Returns a dict:
        new_trips (daily, over `best`), trips (daily, standalone), peak_hour_load (riders in the
        peak hour, peak direction, on the busiest link), served pop/jobs (walk)."""
        cfg, m = self.cfg, self.m
        rc, mc = cfg["ridership"], cfg["modes"][mode]
        Z, S, A, O, Pk = self.catchment(stations, pnr)
        out = {"new_trips": 0.0, "trips": 0.0, "peak_hour_load": 0.0, "walk_pop": 0.0, "walk_jobs": 0.0}
        if len(Z) == 0:
            return out
        walk = ~Pk
        out["walk_pop"] = float(m.pop[Z[walk]].sum())
        out["walk_jobs"] = float(m.jobs[Z[walk]].sum())
        dest = np.where(walk)[0]               # destinations: walk catchment only
        hw = headway or mc["default_headway_min"]
        wc = cfg["wait"]
        wait = min(hw * wc["fraction_of_headway"], wc["max_wait_min"]) * wc.get("weight", 1.0)
        along = np.asarray(along)
        ride = np.abs(along[S][:, None] - along[S[dest]][None, :]) / mc["cruise_kmh"] * 60 \
            + np.abs(S[:, None] - S[dest][None, :]) * mc["stop_penalty_min"]
        dist = np.hypot(m.x[Z][:, None] - m.x[Z[dest]][None, :], m.y[Z][:, None] - m.y[Z[dest]][None, :])
        drive = demand.drive_minutes(cfg["drive"], dist)
        tt = A[:, None] + wait + ride + A[dest][None, :]
        ovt = O[:, None] + O[dest][None, :]
        cc = cfg["competitive"]
        usable = (S[:, None] != S[dest][None, :]) & (dist > cc["min_km"]) & (tt <= cc["max_min"])
        dcost = rc["b_per_dollar"] * rc.get("drive_usd_per_km", 0.0) * cfg["drive"]["circuity"]
        u = (rc["asc"] + rc["b_ivt_per_min"] * (drive - tt) - rc["b_ovt_extra_per_min"] * ovt + dcost * dist
             - rc.get("b_ratio", 0.0) * np.maximum(tt / drive - 1.0, 0.0)
             + rc.get("pnr_asc_offset", 0.0) * Pk[:, None])
        eu = np.exp(np.minimum(u, 30))
        share = np.where(usable, eu / (1.0 + eu), 0.0)
        od = self.od[np.ix_(Z, Z[dest])]
        riders = od * share * rc["telework"]
        # garages: scale each one's park & ride riders down to its capacity
        if Pk.any():
            tot = np.bincount(S[Pk], weights=riders[Pk].sum(axis=1), minlength=len(stations))
            f = np.ones(len(stations))
            for k, cap in pnr_cap.items():
                if tot[k] > cap:
                    f[k] = cap / tot[k]
            scale = np.where(Pk, f[S], 1.0)
            share = share * scale[:, None]
            riders = riders * scale[:, None]
        prev = self.best[np.ix_(Z, Z[dest])]
        gain = od * np.maximum(share - prev, 0.0) * rc["telework"]
        out["trips"] = float(riders.sum()) * self.trip_factor
        out["new_trips"] = float(gain.sum()) * self.trip_factor
        # load on each link between consecutive stations (morning commuters both ways x trips per commuter)
        n = len(stations)
        flow = np.zeros((n, n))
        np.add.at(flow, (np.broadcast_to(S[:, None], riders.shape), np.broadcast_to(S[dest][None, :], riders.shape)),
                  riders)
        load = np.zeros(max(n - 1, 1))
        for a in range(n):
            for b in range(n):
                if flow[a, b] > 0:
                    lo, hi = min(a, b), max(a, b)
                    load[lo:hi] += flow[a, b]
        daily_on_link = load * self.trip_factor
        out["peak_hour_load"] = float(daily_on_link.max() * 0.1 * 0.6) if n > 1 else 0.0
        if commit:
            self.best[np.ix_(Z, Z[dest])] = np.maximum(prev, share)
        return out


def capacity_per_hour(cfg, mode, headway=None):
    mc = cfg["modes"][mode]
    hw = headway or mc["default_headway_min"]
    return 60.0 / hw * mc["vehicle_capacity"]


def pnr_capacity(cfg, mode, n_stops, in_core):
    """{station idx: park & ride commuters} for a line's garages (dfwt's rule)."""
    sp = cfg["access"]["pnr_spaces"]
    per = cfg["access"]["pnr_people_per_space"]
    out = {}
    if mode == "commuter":
        for k in range(n_stops):
            if not in_core(k):
                out[k] = sp["commuter_station"] * per
    elif mode != "streetcar":
        for k in (0, n_stops - 1):
            if not in_core(k):
                out[k] = sp.get(mode + "_terminus", sp["terminus"]) * per
    return out
