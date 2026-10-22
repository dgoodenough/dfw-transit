"""Door-to-door trips for the map's trip planner (docs/map.html).

The page plans a trip from any address: an access leg to a station, the ride, and an
egress leg. It reaches stations by the demand model's rules (dfwt/demand.py Access,
config.json `access`): walk, drive to a park & ride garage, the feeder bus where the
zone is dense enough, and bike / drop-off where a scenario enables them. Everything
those rules need is exported here per scenario and year, so the page can't drift
from the model: the rules in effect each year (`rules`), which stations have a garage
(demand.garages), which zones the feeder grid serves (demand.activity_density on that
year's grown zones), congestion, and the peak drive the model compares transit with
(demand.Zones.drive_min).
"""
import numpy as np

from . import demand, geo, growth


def constants(cfg):
    """Scenario-wide terms of the path choice and the drive-alone baseline."""
    rc, d = cfg["ridership"], cfg["drive"]
    pj = geo.Projector()
    return {
        # riders rank access options and paths by perceived minutes (demand.Access / _paths)
        "ovtW": rc["b_ovt_extra_per_min"] / rc["b_ivt_per_min"],
        "pnrPen": -rc.get("pnr_asc_offset", 0.0) / rc["b_ivt_per_min"],
        "waitW": cfg["wait"].get("weight", 1.0),
        "k": cfg["access"]["max_access_stations"],
        # demand.drive_minutes: local streets, then freeway; moving part x congestion + terminal
        "drive": {"circuity": d["circuity"], "localKm": d["local_km"], "localKmh": d["local_kmh"],
                  "freewayKmh": d["freeway_kmh"], "terminal": d["terminal_min"]},
        # geo.Projector: the model measures every distance on this plane
        "proj": [pj.lat0, pj.lon0, pj.kx, pj.ky],
    }


def rules(cfg, year):
    """Access and egress rules in effect in `year` (mirrors demand.Access). Minutes per
    straight-line km; drive, feeder and drop-off minutes are multiplied by the year's
    congestion on the page, as the model does."""
    ac = cfg["access"]
    eff = demand.in_effect
    out = {
        "walkKm": eff(ac["walk_max_m"], year) / 1000,
        "walkPerKm": eff(ac.get("walk_circuity", ac["circuity"]), year) / ac["walk_speed_kmh"] * 60,
        "pnr": {"minKm": eff(ac.get("pnr_min_km", 0), year), "maxKm": ac["pnr_max_km"],
                "perKm": ac["circuity"] / ac["pnr_speed_kmh"] * 60, "pen": ac["pnr_penalty_min"]},
    }
    fh = demand.feeder_headway(cfg, year)
    if fh:
        fd, w = ac["feeder"], cfg["wait"]
        wait = min(fh * w["fraction_of_headway"], w["max_wait_min"])
        out["feeder"] = {"ovt": fd["stop_walk_min"] + wait + fd["transfer_penalty_min"],
                         "perKm": fd["circuity"] / fd["speed_kmh"] * 60, "maxKm": fd["max_km"],
                         "egress": bool(fd.get("egress", True)), "headway": fh}
    extra = {m for _, ms in demand.access_segments(cfg, year) for m in ms}
    if demand.BIKE in extra:
        mm = ac["micromobility"]
        out["bike"] = {"perKm": mm["circuity"] / mm["speed_kmh"] * 60, "maxKm": mm["max_km"], "pen": mm["penalty_min"],
                       "egress": bool(mm.get("egress", True)), "share": mm["share"]}
    if demand.KISS in extra:
        kr = ac["kiss_ride"]
        out["kiss"] = {"perKm": ac["circuity"] / ac["pnr_speed_kmh"] * 60, "maxKm": kr["max_km"], "pen": kr["penalty_min"],
                       "share": kr["share"]}
    return out


def feeder_zones(zones, net, cfg, years):
    """Per zone, the years the feeder grid serves it (activity density of that year's grown
    zones at least access.feeder.min_density_per_km2): the first such year, 0 for never, or
    a list of the years it switches on and off when it isn't once-and-for-all. None when the
    scenario has no feeder in any year."""
    fd = cfg["access"].get("feeder") or {}
    on_years = [y for y in years if demand.feeder_headway(cfg, y)]
    if not on_years:
        return None
    flips = [[] for _ in range(zones.n)]
    prev = np.zeros(zones.n, dtype=bool)
    for y in on_years:
        z = growth.grown_zones(zones, net, y, cfg)
        z.__dict__.pop(("_density", 0.8), None)   # never the base zones' cached density
        ok = demand.activity_density(z) >= fd.get("min_density_per_km2", 0)
        for i in np.nonzero(ok != prev)[0]:
            flips[i].append(y)
        prev = ok
    return [0 if not f else f[0] if len(f) == 1 else f for f in flips]


def zone_points(zones):
    """Block-group centroids as a flat [lat x 1e4, lon x 1e4, ...] list: the page finds an
    address's zone (for the feeder rule) by the nearest centroid."""
    return [v for la, lo in zip(zones.lat, zones.lon) for v in (int(round(la * 1e4)), int(round(lo * 1e4)))]


def _round(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, dict):
        return {k: _round(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_round(x) for x in v]
    return v


def export(zones, net, graphs):
    """The planner's block for one scenario. `graphs` maps year -> YearGraph. Garages
    (demand.garages) are given per station as the years they open and close: [first
    year] for a garage that stays, [open, close, open, ...] otherwise."""
    cfg = net.cfg
    years = sorted(graphs)
    rule_sets, rule_idx, year_rules = [], {}, {}
    garage, prev, cong = {}, set(), {}
    for y in years:
        r = _round(rules(cfg, y))
        k = repr(r)
        if k not in rule_idx:
            rule_idx[k] = len(rule_sets)
            rule_sets.append(r)
        year_rules[y] = rule_idx[k]
        g = graphs[y]
        is_pnr, _ = demand.garages(zones, net, g, cfg)
        now = {s for s, p in zip(g.station_ids, is_pnr) if p}
        for s in now ^ prev:
            garage.setdefault(s, []).append(y)
        prev = now
        cong[y] = round(growth.congestion(cfg, y), 4)
    return {**_round(constants(cfg)), "rules": rule_sets, "yearRules": year_rules, "garages": garage,
            "cong": cong, "feed": feeder_zones(zones, net, cfg, years)}
