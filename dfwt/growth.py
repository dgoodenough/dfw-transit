"""Population and job growth, transit-oriented development, and congestion by year.

The zones (2020 block groups) are the base. For a given network and year:

1. Regional growth scales every zone's population and jobs by the regional
   multiplier for that year (config.growth.regional_pop / regional_jobs,
   interpolated linearly between the listed years).
2. Transit-oriented development (TOD) adds growth near stations that opened after
   the existing network (config.existing_year). How much depends on the station's
   setting (downtown core, urban or suburban, by people + jobs within 800 m) times
   a mode factor (BRT and commuter rail draw less than metro). It ramps in along a
   logistic curve after opening, is full within `full_radius_m`, and fades to zero
   at `radius_m`. Overlapping stations don't stack (the largest uplift wins).
   Only `net_new_share` of the uplift is new to the region; the rest is drawn
   proportionally from everywhere else, so the regional total stays honest.
3. Congestion: peak drive times (the moving part, not the terminal time) grow by
   `per_decade` from `base_year`, capped at `cap`.

Commute flows are then re-balanced to the grown zones (doubly constrained), with
the total growing in step with jobs. See Context.year_inputs in evaluate.py.
"""
import copy

import numpy as np

from . import geo


def interp(table, year):
    pts = sorted((int(k), float(v)) for k, v in table.items() if not k.startswith("_"))
    ys, vs = zip(*pts)
    return float(np.interp(year, ys, vs))


def congestion(cfg, year):
    c = cfg["drive"].get("congestion")
    if not c:
        return 1.0
    decades = max(0.0, (year - c["base_year"]) / 10)
    return 1.0 + min(c["cap"], c["per_decade"] * decades)


def setting(zones, lat, lon, cfg):
    """'downtown', 'urban' or 'suburban' for a point, from the base data."""
    pj = geo.Projector()
    x, y = pj.xy(lat, lon)
    for c in cfg["cores"].values():
        if isinstance(c, dict) and geo.hav_km(lat, lon, c["lat"], c["lon"]) <= c["radius_km"]:
            return "downtown"
    near = (zones.x - x) ** 2 + (zones.y - y) ** 2 <= 0.8 ** 2
    dens = (zones.pop[near].sum() + zones.jobs[near].sum()) / (np.pi * 0.8 ** 2)
    return "urban" if dens >= cfg["growth"]["tod"]["setting_density_per_km2"]["urban"] else "suburban"


def tod_uplift(zones, net, year, cfg):
    """(pop_uplift, jobs_uplift) per zone: fractional extra growth from stations
    that opened after the existing network."""
    t = cfg["growth"]["tod"]
    ex = cfg["existing_year"]
    up_p = np.zeros(zones.n)
    up_j = np.zeros(zones.n)
    opened = net.open_stations(year)
    if not opened:
        return up_p, up_j
    pj = geo.Projector()
    r, r0 = t["radius_m"] / 1000, t["full_radius_m"] / 1000
    cache = zones.__dict__.setdefault("_setting", {})
    for sid, modes in opened.items():
        y0 = net.station_year(sid)
        if y0 <= ex:
            continue
        ramp = 1.0 / (1.0 + np.exp(-((year - y0) - t["ramp_mid_years"]) / t["ramp_width_years"]))
        s = net.stations[sid]
        x, y = pj.xy(s.lat, s.lon)
        d = np.sqrt((zones.x - x) ** 2 + (zones.y - y) ** 2)
        near = d < r
        if not near.any():
            continue
        key = (round(s.lat, 5), round(s.lon, 5))
        if key not in cache:
            cache[key] = setting(zones, s.lat, s.lon, cfg)
        kind = cache[key]
        w = np.clip((r - d[near]) / (r - r0), 0.0, 1.0) * ramp
        best_p = t["pop_uplift"][kind] * max(t["mode_factor_pop"][m] for m in modes)
        best_j = t["jobs_uplift"][kind] * max(t["mode_factor_jobs"][m] for m in modes)
        up_p[near] = np.maximum(up_p[near], best_p * w)
        up_j[near] = np.maximum(up_j[near], best_j * w)
    return up_p, up_j


def _grow(base, regional, uplift, net_new):
    grown = base * regional * (1 + uplift)
    target = base.sum() * regional * (1 + net_new * (base * uplift).sum() / base.sum())
    extra = grown.sum() - target            # the captured part, drawn from all zones in proportion
    if extra > 0:
        other = base * regional
        grown -= other * (extra / other.sum())
    return grown


def grown_zones(zones, net, year, cfg):
    """A shallow copy of `zones` with this year's population, jobs and congestion."""
    g = cfg["growth"]
    up_p, up_j = tod_uplift(zones, net, year, cfg)
    z = copy.copy(zones)
    nn = g["tod"]["net_new_share"]
    z.pop = _grow(zones.pop, interp(g["regional_pop"], year), up_p, nn)
    z.jobs = _grow(zones.jobs, interp(g["regional_jobs"], year), up_j, nn)
    z.cong = congestion(cfg, year)
    z.tod_key = (round(z.cong, 4), up_p.round(4).tobytes(), up_j.round(4).tobytes(), year)
    return z
