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
        self._park_cache = {}   # shared with grown copies (parking_usd)

    def dist_rows(self, i0, i1):
        if getattr(self, "_dist", None) is None:   # all pairs, once (shared by grown copies)
            dx = self.x[:, None] - self.x[None, :]
            dy = self.y[:, None] - self.y[None, :]
            self._dist = np.sqrt(dx * dx + dy * dy).astype(np.float32)
        return self._dist[i0:i1]

    def parking_usd(self):
        """Per destination zone: (daily parking price $, parking cash-out $, share of
        commuters offered cash-out), for this zones' year (growth.grown_zones sets
        `year`; base zones have none and get today's prices).

        Today's paid-parking districts are config.ridership.paid_parking. The policy
        block config.ridership.parking_policy (off when absent) phases in linearly
        from start_year to full_year: district prices rise by price_growth (fewer free
        or cheap spaces), `priced_centers` charges usd_per_day wherever jobs within
        800 m reach min_jobs_per_km2 (paid-parking districts follow density), and
        `cashout` offers usd_per_day in lieu of free parking to `coverage` of the
        commuters to other zones with at least min_jobs_per_km2."""
        cache = self.__dict__.setdefault("_park_cache", {})
        year = getattr(self, "year", None)
        key = getattr(self, "tod_key", None)
        if key in cache:
            return cache[key]
        rc = self.cfg["ridership"]
        pol = rc.get("parking_policy") or {}
        ramp = 0.0
        if pol and year is not None:
            ramp = float(np.clip((year - pol["start_year"]) / max(pol["full_year"] - pol["start_year"], 1), 0.0, 1.0))
        mult = 1.0 + pol.get("price_growth", 0.0) * ramp
        pj = geo.Projector()
        usd = np.zeros(self.n)
        for name, p in rc["paid_parking"].items():
            if name.startswith("_"):
                continue
            px, py = pj.xy(p["lat"], p["lon"])
            d = np.sqrt((self.x - px) ** 2 + (self.y - py) ** 2)
            usd = np.maximum(usd, np.where(d <= p["radius_km"], p["usd_per_day"] * mult, 0.0))
        cash, cov = np.zeros(self.n), np.zeros(self.n)
        pc, co = pol.get("priced_centers"), pol.get("cashout")
        if ramp > 0 and (pc or co):
            dens = (self.dist_rows(0, self.n) <= 0.8) @ self.jobs / (np.pi * 0.64)
            if pc:
                usd = np.maximum(usd, np.where(dens >= pc["min_jobs_per_km2"], pc["usd_per_day"] * mult * ramp, 0.0))
            if co:
                m = (dens >= co["min_jobs_per_km2"]) & (usd <= 0)
                cash = np.where(m, co["usd_per_day"], 0.0)
                cov = np.where(m, co["coverage"] * ramp, 0.0)
        cache[key] = (usd, cash, cov)
        return cache[key]

    def paid_parking_utility(self):
        """Per destination zone: utility of not paying for parking there."""
        b = self.cfg["ridership"]["b_per_dollar"]
        return (b * self.parking_usd()[0] / 2).astype(np.float32)

    cong = 1.0  # peak drive-time multiplier for the year (growth.grown_zones sets it)

    def drive_min(self, dist):
        return drive_minutes(self.cfg["drive"], dist, self.cong)


def drive_minutes(d, dist, cong=1.0):
    """Peak drive minutes for straight-line km `dist` (config.drive): road km = dist x circuity,
    the first local_km on local streets at local_kmh, the rest at freeway_kmh (longer trips use
    freeways), the moving part x congestion, plus terminal minutes (parking, walking in)."""
    road = dist * d["circuity"]
    local = np.minimum(road, d["local_km"])
    moving = local / d["local_kmh"] * 60 + (road - local) / d["freeway_kmh"] * 60
    return moving * cong + d["terminal_min"]


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


# Access modes. Walk and park & ride are the base model; feeder bus, micromobility
# and kiss-and-ride are levers (config.access.feeder / micromobility / kiss_ride),
# all off by default.
WALK, PNR, FEEDER, BIKE, KISS = range(5)
_SETTING = {}   # id(base zones) -> {station id: 'downtown' / 'urban' / 'suburban'}
ACCESS_MODES = ("walk", "pnr", "feeder", "bike", "kiss")


def in_effect(table, year):
    """Value of a {year: value} table in `year`: the entry with the latest year
    <= `year`, or None before the first. A plain number applies to every year."""
    if not isinstance(table, dict):
        return table
    out = None
    for y, v in sorted((int(k), v) for k, v in table.items() if not str(k).startswith("_")):
        if y <= year:
            out = v
    return out


def feeder_headway(cfg, year):
    """Feeder bus headway (min) in `year`, or None where no feeder grid is assumed."""
    f = cfg["access"].get("feeder") or {}
    return in_effect(f.get("headway_min"), year) if f.get("enabled") else None


def access_segments(cfg, year):
    """[(weight, extra_modes)]: the commuter market split by which optional access
    modes each part will use. Everyone can walk, park & ride (where a garage is) and
    ride a feeder bus; only `share` of commuters will bike/scoot or be dropped off."""
    ac = cfg["access"]
    segs, rest = [], 1.0
    for key, mode in (("micromobility", BIKE), ("kiss_ride", KISS)):
        o = ac.get(key) or {}
        if o.get("enabled") and o.get("share", 0) > 0 and year >= o.get("from_year", 0):
            segs.append((float(o["share"]), (mode,)))
            rest -= float(o["share"])
    return [(rest, ())] + segs


def no_car_share(zones, cfg):
    """Per zone: share of commuters from households without a car (they can't park
    & ride and their alternative to transit is getting a ride, not driving). Rises
    with density (config.ridership.no_car; ACS: ~5% of DFW households, ~9% in the
    city of Dallas, far more in dense inner neighborhoods)."""
    nc = cfg["ridership"].get("no_car") or {}
    if not nc.get("enabled"):
        return None
    dens = activity_density(zones)
    xs, ys = zip(*nc["share_by_density"])
    return np.interp(dens, xs, ys)


def activity_density(zones, r_km=0.8):
    """People + jobs per km2 within r_km of each zone centroid (cached per zones object)."""
    key = ("_density", r_km)
    hit = zones.__dict__.get(key)
    if hit is not None:
        return hit
    act = (zones.pop + zones.jobs).astype(np.float32)
    out = np.empty(zones.n)
    for i0 in range(0, zones.n, CHUNK):
        i1 = min(zones.n, i0 + CHUNK)
        d2 = (zones.x[i0:i1, None] - zones.x[None, :]) ** 2 + (zones.y[i0:i1, None] - zones.y[None, :]) ** 2
        out[i0:i1] = (d2 <= r_km * r_km).astype(np.float32) @ act
    out /= np.pi * r_km * r_km
    zones.__dict__[key] = out
    return out


def garages(zones, net, graph, cfg):
    """Park & ride garages open in `graph`'s year: (is_pnr, spaces), one entry per graph
    station. `zones` are the (grown or base) zones; a station's setting comes from the
    base-year data. Shared by Access and the map's trip planner (webmap)."""
    ac = cfg["access"]
    year = graph.year
    sids = graph.station_ids
    slat = np.array([net.stations[s].lat for s in sids])
    slon = np.array([net.stations[s].lon for s in sids])
    sx, sy = geo.Projector().xy(slat, slon)
    # which stations allow park & ride: commuter stations and each line's planned
    # termini (where the garage gets built). A temporary end of a partly built line
    # gets none, or every stub would look like a park & ride hub.
    is_pnr = np.zeros(len(sids), dtype=bool)
    spaces = np.zeros(len(sids))
    sp = ac["pnr_spaces"]
    idx = graph.sidx
    for run in graph.runs:
        if run.line.mode == "commuter":
            for s in run.stops:
                is_pnr[idx[s]] = True
                spaces[idx[s]] = max(spaces[idx[s]], sp["commuter_station"])
        full = net.lines.get(run.line.id, run.line)
        term = sp.get(run.line.mode + "_terminus", sp["terminus"])   # smaller at BRT ends, none for streetcars
        for s in (full.stop_ids[0], full.stop_ids[-1], *full.pnr_stops):
            if s in idx and term > 0:
                is_pnr[idx[s]] = True
                spaces[idx[s]] = max(spaces[idx[s]], term)
    # today's lots at existing suburban stations (DART has parking at most stations
    # outside the core; access.pnr_existing approximates their size)
    ex = ac.get("pnr_existing") or {}
    if ex.get("enabled"):
        from . import growth
        base = getattr(zones, "base", zones)
        cache = _SETTING.setdefault(id(base), {})
        for run in graph.runs:
            if run.line.status != "existing":
                continue
            for s in run.stops:
                i = idx[s]
                if sids[i] not in cache:
                    st = net.stations[sids[i]]
                    cache[sids[i]] = growth.setting(base, st.lat, st.lon, cfg)
                if cache[sids[i]] in ex["settings"]:
                    is_pnr[i] = True
                    spaces[i] = max(spaces[i], ex["spaces"])
    # optional lever: garages at selected suburban stations (Wiehle-Reston East style:
    # a structured garage wrapped by development, so TOD uplift is unchanged). Only
    # stations whose setting is suburban (growth.setting on base-year density), at
    # least min_core_km from a downtown, and min_spacing_km from every other garage;
    # outermost candidates first.
    sub = ac.get("pnr_suburban") or {}
    if sub.get("enabled") and year >= sub.get("from_year", 0):
        from . import growth
        base = getattr(zones, "base", zones)
        cores = [c for c in cfg["cores"].values() if isinstance(c, dict)]
        core_km = np.full(len(sids), np.inf)
        for c in cores:
            cx, cy = geo.Projector().xy(c["lat"], c["lon"])
            core_km = np.minimum(core_km, np.sqrt((sx - cx) ** 2 + (sy - cy) ** 2))
        cand = sorted({idx[s] for run in graph.runs if run.line.mode in sub["modes"] for s in run.stops
                       if core_km[idx[s]] >= sub["min_core_km"] and not is_pnr[idx[s]]},
                      key=lambda i: (-core_km[i], i))
        cache = _SETTING.setdefault(id(base), {})
        gap = sub.get("min_spacing_km", 0)
        for i in cand:
            if sub.get("setting"):
                if sids[i] not in cache:
                    st = net.stations[sids[i]]
                    cache[sids[i]] = growth.setting(base, st.lat, st.lon, cfg)
                if cache[sids[i]] != sub["setting"]:
                    continue
            if gap and is_pnr.any() and np.sqrt((sx[is_pnr] - sx[i]) ** 2 + (sy[is_pnr] - sy[i]) ** 2).min() < gap:
                continue
            is_pnr[i] = True
            spaces[i] = sub["spaces"]
    return is_pnr, spaces


class Access:
    """Zone <-> station connectors for one year's open stations.

    Per zone, up to k access (origin end) and egress (destination end) stations,
    each with door-to-platform minutes (`*_t`), the out-of-vehicle part of those
    minutes (`*_o`, weighted extra in the mode-choice logit) and the access mode
    (`*_mode`, one of ACCESS_MODES). `extra` adds the segment-only modes (BIKE,
    KISS); `pnr=False` drops park & ride (the fallback for riders a full garage
    turns away)."""

    def __init__(self, zones, net, graph, cfg, extra=(), pnr=True):
        ac = cfg["access"]
        year = graph.year
        k = ac["max_access_stations"]
        sids = graph.station_ids
        slat = np.array([net.stations[s].lat for s in sids])
        slon = np.array([net.stations[s].lon for s in sids])
        sx, sy = geo.Projector().xy(slat, slon)
        idx = graph.sidx
        is_pnr, spaces = garages(zones, net, graph, cfg)
        if not pnr:
            is_pnr[:] = False
        # people a garage can serve per day (one car per commuter, plus drop-offs)
        self.pnr_cap = spaces * ac["pnr_people_per_space"]
        walk_km = in_effect(ac["walk_max_m"], year) / 1000   # walk settings may be year tables
        cong = getattr(zones, "cong", 1.0)
        rc = cfg["ridership"]
        ovt_w = rc["b_ovt_extra_per_min"] / rc["b_ivt_per_min"]
        pen = np.zeros((5, 1, 1), dtype=np.float32)
        pen[PNR] = -rc.get("pnr_asc_offset", 0.0) / rc["b_ivt_per_min"]
        # feeder bus: walk to the bus stop, wait half the headway, ride at bus speed
        # in general traffic (it takes the congestion), transfer to the line.
        fh = feeder_headway(cfg, year)
        fd = ac.get("feeder") or {}
        if fh:
            wcap = cfg["wait"]["max_wait_min"]
            f_ovt = fd["stop_walk_min"] + min(fh * cfg["wait"]["fraction_of_headway"], wcap) + fd["transfer_penalty_min"]
            f_ivt = fd["circuity"] / fd["speed_kmh"] * 60 * cong   # minutes per straight-line km
            f_zone = activity_density(zones) >= fd.get("min_density_per_km2", 0)
        mm = ac.get("micromobility") or {}
        kr = ac.get("kiss_ride") or {}
        run_cols = [np.array(sorted({idx[s] for s in run.stops})) for run in graph.runs]
        k = min(k, len(run_cols))
        nz = zones.n
        self.acc_st = np.zeros((nz, k), dtype=np.int32)
        self.acc_t = np.full((nz, k), np.inf, dtype=np.float32)
        self.acc_o = np.full((nz, k), np.inf, dtype=np.float32)
        self.acc_mode = np.zeros((nz, k), dtype=np.int8)
        self.egr_st = np.zeros((nz, k), dtype=np.int32)
        self.egr_t = np.full((nz, k), np.inf, dtype=np.float32)
        self.egr_o = np.full((nz, k), np.inf, dtype=np.float32)
        self.egr_mode = np.zeros((nz, k), dtype=np.int8)
        self.walk_min_dist = np.full(nz, np.inf, dtype=np.float32)
        self.acc_g = np.full((nz, k), np.inf, dtype=np.float32)   # perceived minutes (what riders rank by)
        self.egr_g = np.full((nz, k), np.inf, dtype=np.float32)
        for i0 in range(0, nz, CHUNK):
            i1 = min(nz, i0 + CHUNK)
            d = np.sqrt((zones.x[i0:i1, None] - sx[None, :]) ** 2 + (zones.y[i0:i1, None] - sy[None, :]) ** 2)
            self.walk_min_dist[i0:i1] = d.min(axis=1)
            inf = np.full(d.shape, np.inf)
            walk = np.where(d <= walk_km, d * in_effect(ac.get("walk_circuity", ac["circuity"]), year) / ac["walk_speed_kmh"] * 60,
                            np.inf)
            drive = np.where(is_pnr[None, :] & (d <= ac["pnr_max_km"]) & (d >= in_effect(ac.get("pnr_min_km", 0), year)),
                             d * ac["circuity"] / ac["pnr_speed_kmh"] * 60 * cong + ac["pnr_penalty_min"], np.inf)
            drive_o = np.where(np.isfinite(drive), ac["pnr_penalty_min"], np.inf)   # park + walk from the garage
            # (minutes, out-of-vehicle minutes) per mode; the drive itself is in-vehicle time
            acc_modes = [(walk, walk), (drive, drive_o), (inf, inf), (inf, inf), (inf, inf)]
            egr_modes = [(walk, walk), (inf, inf), (inf, inf), (inf, inf), (inf, inf)]
            if fh:
                ok = f_zone[i0:i1, None] & (d <= fd["max_km"])
                bus = np.where(ok, f_ovt + d * f_ivt, np.inf)
                bus_o = np.where(ok, f_ovt, np.inf)
                acc_modes[FEEDER] = (bus, bus_o)
                if fd.get("egress", True):
                    egr_modes[FEEDER] = (bus, bus_o)
            if BIKE in extra:
                bike = np.where(d <= mm["max_km"], d * mm["circuity"] / mm["speed_kmh"] * 60 + mm["penalty_min"], np.inf)
                acc_modes[BIKE] = (bike, bike)
                if mm.get("egress", True):
                    egr_modes[BIKE] = (bike, bike)
            if KISS in extra:
                kiss = np.where(d <= kr["max_km"], d * ac["circuity"] / ac["pnr_speed_kmh"] * 60 * cong + kr["penalty_min"],
                                np.inf)
                acc_modes[KISS] = (kiss, np.where(np.isfinite(kiss), kr["penalty_min"], np.inf))
            for modes, st, t, o, md, g in ((acc_modes, self.acc_st, self.acc_t, self.acc_o, self.acc_mode, self.acc_g),
                                           (egr_modes, self.egr_st, self.egr_t, self.egr_o, self.egr_mode, self.egr_g)):
                tt = np.stack([m[0] for m in modes])
                oo = np.stack([m[1] for m in modes])
                # riders pick the access mode by perceived minutes (out-of-vehicle time weighs
                # more, and driving to a garage carries its constant, pnr_asc_offset, in minutes),
                # not raw minutes; ties go to the earlier mode (walk first)
                gen = tt + ovt_w * np.where(np.isfinite(oo), oo, 0) + pen
                best = np.argmin(gen, axis=0)
                arr = np.take_along_axis(tt, best[None], axis=0)[0]
                garr = np.take_along_axis(gen, best[None], axis=0)[0]
                ovt = np.take_along_axis(oo, best[None], axis=0)[0]
                # connector stations are ranked by the same perceived minutes (the path search too)
                st[i0:i1], g[i0:i1] = _diverse_nearest(garr, run_cols, k)
                t[i0:i1] = np.take_along_axis(arr, st[i0:i1], axis=1)
                o[i0:i1] = np.take_along_axis(ovt, st[i0:i1], axis=1)
                md[i0:i1] = np.take_along_axis(best, st[i0:i1], axis=1)
        self.acc_pnr = self.acc_mode == PNR


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


def _paths(acc, T, i0, i1, nz, ns):
    """Best door-to-door path for origin zones i0:i1 to every zone through `acc`:
    (minutes, access station, egress station, access mode, egress mode, out-of-vehicle minutes).
    Paths are ranked by perceived minutes (in-vehicle + weighted out-of-vehicle + the
    drive-to-transit constant, the terms the mode choice uses); the minutes returned are
    the path's actual minutes. Only the minutes and the winning connector index are kept
    per pass (in place); stations, modes and out-of-vehicle minutes are looked up at the end."""
    m = i1 - i0
    k = acc.acc_st.shape[1]
    rows = np.arange(m)[:, None]
    # origin zone -> any station b, via best access station a
    R = np.full((m, ns), np.inf, dtype=np.float32)
    Rg = np.full((m, ns), np.inf, dtype=np.float32)
    Ja = np.zeros((m, ns), dtype=np.int8)
    better = np.empty((m, ns), dtype=bool)
    for j in range(k):
        Tj = T[acc.acc_st[i0:i1, j]]
        cand = acc.acc_g[i0:i1, j, None] + Tj
        np.less(cand, Rg, out=better)
        np.copyto(Rg, cand, where=better)
        np.copyto(R, acc.acc_t[i0:i1, j, None] + Tj, where=better)
        np.copyto(Ja, j, where=better)
    Ra = acc.acc_st[i0:i1][rows, Ja]
    Rm = acc.acc_mode[i0:i1][rows, Ja]
    Ro = acc.acc_o[i0:i1][rows, Ja]
    # -> destination zone via best egress station b
    TT = np.full((m, nz), np.inf, dtype=np.float32)
    TG = np.full((m, nz), np.inf, dtype=np.float32)
    Jb = np.zeros((m, nz), dtype=np.int8)
    better = np.empty((m, nz), dtype=bool)
    for j in range(k):
        cand = Rg[:, acc.egr_st[:, j]]
        cand += acc.egr_g[None, :, j]
        np.less(cand, TG, out=better)
        np.copyto(TG, cand, where=better)
        np.copyto(TT, R[:, acc.egr_st[:, j]] + acc.egr_t[None, :, j], where=better)
        np.copyto(Jb, j, where=better)
    cols = np.arange(nz)[None, :]
    Bst = acc.egr_st[cols, Jb]
    Em = acc.egr_mode[cols, Jb]
    OVT = Ro[rows, Bst] + acc.egr_o[cols, Jb]
    return TT, Ra[rows, Bst], Bst, Rm[rows, Bst], Em, OVT


def evaluate(zones, od, net, graph, cfg, want_loads=True):
    """Run the year: transit times for every zone pair, competitive commutes,
    expected transit riders, accessibility, and (optionally) station-pair rider
    flows for load assignment.

    Park & ride garages hold a limited number of cars (config.access.pnr_spaces).
    Trips that reach transit by driving are tallied per garage; where a garage's
    riders exceed its capacity, its trips are scaled down to fit. With
    access.pnr_overflow_fallback the riders a full garage turns away instead take
    their best access without parking (walk, feeder bus, ...); that needs a first
    pass to find the full garages.
    """
    T = graph.T
    ac = cfg["access"]
    nz, ns = zones.n, graph.n_st
    fallback = bool(ac.get("pnr_overflow_fallback"))
    segs = []
    nc = no_car_share(zones, cfg)
    bonus = cfg["ridership"]["no_car"]["ride_bonus"] if nc is not None else 0.0
    for w, extra in access_segments(cfg, graph.year):
        main = Access(zones, net, graph, cfg, extra)
        walkers = Access(zones, net, graph, cfg, extra, pnr=False) if (fallback or nc is not None) else None
        if nc is None:
            segs.append((w, main, walkers if fallback else None, 0.0))
        else:   # car households, and households without a car (no garage; "drive" means getting a ride)
            segs.append((w * (1 - nc), main, walkers if fallback else None, 0.0))
            segs.append((w * nc, walkers, None, bonus))
    cap = segs[0][1].pnr_cap
    fixed = None
    if fallback:
        demand_p = _sweep(zones, od, T, segs, cfg, nz, ns, None, False, light=True)["rid_p"]
        fixed = np.where(demand_p > cap, cap / np.maximum(demand_p, 1e-9), 1.0)
    s = _sweep(zones, od, T, segs, cfg, nz, ns, fixed, want_loads)
    rid_p = s["rid_p"]
    # garages over capacity: scale their park & ride trips down to fit (already done when fixed)
    f = np.where(rid_p > cap, cap / np.maximum(rid_p, 1e-9), 1.0) if fixed is None else np.zeros(ns)
    comp_total = s["comp_w"] + float((f * s["comp_p"]).sum())
    riders = s["rid_w"] + float((f * rid_p).sum())
    comp_from = s["comp_from_w"] + (f[:, None] * s["comp_from_p"].reshape(ns, nz)).sum(axis=0)
    comp_to = s["comp_to_w"] + (f[:, None] * s["comp_to_p"].reshape(ns, nz)).sum(axis=0)
    tt_sum = s["tt_w_sum"] + float((f * s["tt_p_sum"]).sum())
    flows = s["flows_w"] + f[:, None] * s["flows_p"] if want_loads else None
    by_mode = s["mode_w"]
    pnr_riders = float(np.minimum(rid_p, cap).sum())
    by_mode[PNR] = pnr_riders
    feeder_legs = s["feed_w"] + float((f * s["feed_p"]).sum())
    pop = zones.pop
    jobs_reach = s["jobs_reach"]
    return {
        "competitive_commutes": comp_total,
        "transit_commuters": riders,
        "pnr_riders": pnr_riders,
        "pnr_demand": float(rid_p.sum()),
        "pnr_full_garages": int((rid_p > cap).sum()),
        "pnr_spaces": float(cap.sum() / ac["pnr_people_per_space"]),
        "riders_by_access": {m: float(by_mode[i]) for i, m in enumerate(ACCESS_MODES)},
        "feeder_legs": feeder_legs,
        "active_commuters": s["active_commuters"],
        "comp_from": comp_from,
        "comp_to": comp_to,
        "jobs_reach": jobs_reach,
        "access_jobs": {t: float((jobs_reach[t] * pop).sum() / pop.sum()) for t in jobs_reach},
        "avg_transit_min": tt_sum / comp_total if comp_total else 0.0,
        "flows": flows,
        "walk_min_dist": segs[0][1].walk_min_dist,
    }


def _rows(w, i0, i1):
    """A segment weight: a scalar, or one value per origin zone."""
    return w[i0:i1, None] if isinstance(w, np.ndarray) else w


def _sweep(zones, od, T, segs, cfg, nz, ns, fixed, want_loads, light=False):
    """Tally competitive commutes and logit riders over every zone pair and access
    segment. Park & ride pairs are tallied per garage (to be scaled to capacity
    afterwards) unless `fixed` gives each garage's share already; then the rest of
    those riders fall back to the segment's no-parking access. `light` tallies only
    garage demand."""
    cc, rc = cfg["competitive"], cfg["ridership"]
    thresholds = cfg["accessibility"]["thresholds_min"]
    park = zones.paid_parking_utility()
    act = rc.get("active") or {}
    dcost = rc["b_per_dollar"] * rc.get("drive_usd_per_km", 0.0) * cfg["drive"]["circuity"]
    _, cash_usd, cash_cov = zones.parking_usd()
    cash_u = (rc["b_per_dollar"] * cash_usd / 2).astype(np.float32)
    has_cash = bool(cash_cov.any())
    jobs_reach = {t: np.zeros(nz) for t in thresholds}
    # walk-access tallies, and per-garage park & ride tallies
    comp_w, rid_w, tt_w_sum, feed_w, act_w = 0.0, 0.0, 0.0, 0.0, 0.0
    mode_w = np.zeros(len(ACCESS_MODES))
    comp_from_w, comp_to_w = np.zeros(nz), np.zeros(nz)
    comp_p, rid_p, tt_p_sum, feed_p = np.zeros(ns), np.zeros(ns), np.zeros(ns), np.zeros(ns)
    comp_from_p, comp_to_p = np.zeros(ns * nz), np.zeros(ns * nz)
    flows_w = np.zeros((ns, ns)) if want_loads else None
    flows_p = np.zeros((ns, ns)) if want_loads else None

    def free(q, rq, tt, Ast, Bst, Am, Em, i0, i1):
        """Add pairs that need no garage space (weights already applied)."""
        nonlocal comp_w, rid_w, tt_w_sum, feed_w
        comp_w += float(q.sum())
        rid_w += float(rq.sum())
        tt_w_sum += float((tt * q).sum())
        feed_w += float((rq * ((Am == FEEDER).astype(np.float32) + (Em == FEEDER))).sum())
        mode_w[:] += np.bincount(Am.ravel(), weights=rq.ravel(), minlength=len(ACCESS_MODES))
        comp_from_w[i0:i1] += q.sum(axis=1)
        comp_to_w[:] += q.sum(axis=0)
        if want_loads:
            sel = rq > 0
            if sel.any():
                np.add.at(flows_w, (Ast[sel], Bst[sel]), rq[sel])

    for i0 in range(0, nz, CHUNK):
        i1 = min(nz, i0 + CHUNK)
        m = i1 - i0
        dist = zones.dist_rows(i0, i1)
        drive = zones.drive_min(dist)
        odc = od[i0:i1]
        # driving avoided is worth its running cost and its parking to both transit and active trips
        avoid = dcost * dist + park[None, :]
        if act:   # walk/bike the whole way (straight-line km x circuity at a blended speed)
            t_act = dist * act["circuity"] / act["speed_kmh"] * 60
            ua = np.where(dist <= act["max_km"],
                          act["asc"] + rc["b_ivt_per_min"] * drive - act["b_per_min"] * t_act + avoid, -np.inf)
            ea = np.exp(ua)
        else:
            ea = 0.0

        cache = {}

        def pair_riders(acc, wgt, bon=0.0):
            if id(acc) not in cache:      # the walk-only connectors serve both car-free riders and garage overflow
                cache[id(acc)] = _paths(acc, T, i0, i1, nz, ns)
            TT, Ast, Bst, Am, Em, OVT = cache[id(acc)]
            # a trip must ride the network: feeder-in, feeder-out at one station is a bus trip
            usable = np.isfinite(TT) & (TT <= cc["max_min"]) & (dist > cc["min_km"]) & (Ast != Bst)
            ok = usable & (TT <= cc["ratio"] * drive + cc["slack_min"])
            wgt = _rows(wgt, i0, i1)
            q = np.where(ok, odc * wgt, 0.0)
            # expected transit commuters: binary logit (config.ridership)
            TTu = np.where(usable, TT, 0)
            # transit vs drive vs walk/bike (multinomial logit; drive is the reference). Trips
            # far slower than driving lose extra appeal (b_ratio), so the long tail stays thin.
            du = (rc["asc"] + rc["b_ivt_per_min"] * (drive - TTu) - rc["b_ovt_extra_per_min"] * OVT + avoid
                  - rc.get("b_ratio", 0.0) * np.maximum(TTu / drive - 1.0, 0.0)
                  + rc.get("pnr_asc_offset", 0.0) * (Am == PNR))   # drive-to-transit is its own, less liked, option
            eu = np.exp(du + bon)
            eab = ea * np.exp(bon) if bon else ea
            share = eu / (1.0 + eu + eab)
            if has_cash:   # commuters offered parking cash-out see the cash as a price on parking
                cu = np.exp(cash_u[None, :])
                share = share + cash_cov[None, :] * (eu * cu / (1.0 + (eu + eab) * cu) - share)
            rq = np.where(usable, odc * wgt * share * rc["telework"], 0.0)
            return TT, Ast, Bst, Am, Em, q, rq, np.where(ok, TT, 0)

        if act and not light:   # walk/bike commuters (approx.: ignores the transit option)
            for wgt, _, _, bon in segs:
                eb = ea * np.exp(bon)
                act_w += float((odc * _rows(wgt, i0, i1) * eb / (1.0 + eb)).sum()) * rc["telework"]
        for si, (wgt, acc, alt, bon) in enumerate(segs):
            if light and not acc.acc_pnr.any():
                continue                  # only garage demand is needed, and this segment can't park
            TT, Ast, Bst, Am, Em, q, rq, tt = pair_riders(acc, wgt, bon)
            p = Am == PNR
            if light:
                if p.any():
                    rid_p += np.bincount(Ast[p], weights=rq[p], minlength=ns)
                continue
            if si == 0:
                for t in thresholds:
                    jobs_reach[t][i0:i1] = ((TT <= t) * zones.jobs[None, :]).sum(axis=1)
            if p.any():
                rid_p += np.bincount(Ast[p], weights=rq[p], minlength=ns)
            if fixed is not None:
                g = np.where(p, fixed[Ast], 1.0).astype(np.float32)   # share that finds a space
                free(q * g, rq * g, tt, Ast, Bst, Am, Em, i0, i1)
                if alt is not None and p.any():
                    h = np.where(p, 1.0 - g, 0.0)
                    TT2, Ast2, Bst2, Am2, Em2, q2, rq2, tt2 = pair_riders(alt, wgt, bon)
                    free(q2 * h, rq2 * h, tt2, Ast2, Bst2, Am2, Em2, i0, i1)
                continue
            w = ~p
            free(np.where(w, q, 0.0), np.where(w, rq, 0.0), tt, Ast, Bst, Am, Em, i0, i1)
            if p.any():
                ap = Ast[p]
                comp_p += np.bincount(ap, weights=q[p], minlength=ns)
                tt_p_sum += np.bincount(ap, weights=(tt * q)[p], minlength=ns)
                feed_p += np.bincount(ap, weights=(rq * (Em == FEEDER))[p], minlength=ns)
                zi = np.broadcast_to(np.arange(i0, i1)[:, None], (m, nz))[p]
                zj = np.broadcast_to(np.arange(nz)[None, :], (m, nz))[p]
                comp_from_p += np.bincount(ap * nz + zi, weights=q[p], minlength=ns * nz)
                comp_to_p += np.bincount(ap * nz + zj, weights=q[p], minlength=ns * nz)
                if want_loads:
                    sel = p & (rq > 0)
                    np.add.at(flows_p, (Ast[sel], Bst[sel]), rq[sel])
    mode_w[PNR] = 0.0   # park & ride riders are reported after the capacity check
    return {"comp_w": comp_w, "rid_w": rid_w, "tt_w_sum": tt_w_sum, "feed_w": feed_w, "mode_w": mode_w,
            "active_commuters": act_w,
            "comp_from_w": comp_from_w, "comp_to_w": comp_to_w, "comp_p": comp_p, "rid_p": rid_p,
            "tt_p_sum": tt_p_sum, "feed_p": feed_p, "comp_from_p": comp_from_p, "comp_to_p": comp_to_p,
            "flows_w": flows_w, "flows_p": flows_p, "jobs_reach": jobs_reach}


def assign_loads(graph, flows):
    """Push station-pair flows along shortest paths. Returns per-run hop loads
    (list per run of per-hop volumes, both directions summed), per-station boardings
    and per-run boardings."""
    hop_load = [np.zeros(max(len(r.stops) - 1, 0)) for r in graph.runs]
    boardings = np.zeros(graph.n_st)
    run_board = np.zeros(len(graph.runs))
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
                run_board[ku[2]] += v
    return hop_load, boardings, run_board
