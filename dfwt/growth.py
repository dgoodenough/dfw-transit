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
3. Growth capture (a land-use policy, config.growth.capture; off by default):
   from `start_year`, a share of each period's regional growth is steered into
   station areas (zones within `radius_m` of an open station) up to a target
   density of people + jobs per km2 by setting and mode (Toronto MTSA targets,
   Rosslyn-Ballston levels), and a share of job growth into named job centers.
   The captured growth is taken from the rest of the region in proportion to
   its own growth that period, so regional totals do not change.
4. Congestion: peak drive times (the moving part, not the terminal time) grow by
   `per_decade` from `base_year`, capped at `cap`.

`growth.case` picks the regional trajectory: "mid" (default), or "low"/"high"
from growth.alt (jobs follow population in proportion unless alt has a jobs table).
`growth.spatial` picks where it lands: "even" (default: every zone by the regional
multiplier) or "county" (growth.alt.county_weights: each zone's growth scaled by its
county's weight, the fringe counties faster, as NCTCOG's county forecasts have it; the
regional totals don't change).
`growth.tod.upzone_existing_year`, if set, gives stations that already exist the
same TOD uplift as new ones, as if they opened (were upzoned) that year.

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


def regional(cfg, kind, year):
    """Regional multiplier ('pop' or 'jobs') for `year` under config.growth.case."""
    g = cfg["growth"]
    mid = interp(g[f"regional_{kind}"], year)
    case = g.get("case", "mid")
    if case == "mid":
        return mid
    alt = g["alt"]
    if f"{case}_{kind}" in alt:
        return interp(alt[f"{case}_{kind}"], year)
    return mid * interp(alt[f"{case}_pop"], year) / interp(g["regional_pop"], year)


def congestion(cfg, year):
    c = cfg["drive"].get("congestion")
    if not c:
        return 1.0
    decades = max(0.0, (year - c["base_year"]) / 10)
    return 1.0 + min(c["cap"], c["per_decade"] * decades)


class Walksheds:
    """Block groups apportioned by area: the region on a CELL_KM grid, each cell given to the
    nearest block-group centroid (a Voronoi estimate of each group's land, no farther than
    MAX_KM from it), so a station's walkshed counts the share of each group's land within
    walking distance rather than whole groups by their centre point."""
    CELL_KM, BUCKET_KM, MAX_KM = 0.2, 4.0, 8.0

    def __init__(self, zx, zy):
        c, b = self.CELL_KM, self.BUCKET_KM
        self.x0, self.y0 = zx.min() - 2, zy.min() - 2
        nx, ny = int((zx.max() + 2 - self.x0) / c) + 1, int((zy.max() + 2 - self.y0) / c) + 1
        self.nx, self.ny = nx, ny
        owner = np.full(nx * ny, -1)
        bx, by = ((zx - self.x0) // b).astype(int), ((zy - self.y0) // b).astype(int)
        buckets = {}
        for i, k in enumerate(zip(bx, by)):
            buckets.setdefault(k, []).append(i)
        per = int(b / c)
        ring = int(np.ceil(self.MAX_KM / b))
        for gx in range(int(nx / per) + 1):
            for gy in range(int(ny / per) + 1):
                cand = [i for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)
                        for i in buckets.get((gx + dx, gy + dy), ())]
                ix = np.arange(gx * per, min(nx, (gx + 1) * per))
                iy = np.arange(gy * per, min(ny, (gy + 1) * per))
                if not cand or not len(ix) or not len(iy):
                    continue
                cx, cy = np.meshgrid(self.x0 + (ix + 0.5) * c, self.y0 + (iy + 0.5) * c, indexing="ij")
                cand = np.array(cand)
                d2 = (cx.ravel()[:, None] - zx[cand][None, :]) ** 2 + (cy.ravel()[:, None] - zy[cand][None, :]) ** 2
                k = np.argmin(d2, axis=1)
                ok = d2[np.arange(len(k)), k] <= self.MAX_KM ** 2
                II, JJ = np.meshgrid(ix, iy, indexing="ij")
                flat = (II.ravel() * ny + JJ.ravel())[ok]
                owner[flat] = cand[k[ok]]
        self.owner = owner
        self.cells = np.bincount(owner[owner >= 0], minlength=len(zx)).astype(float)

    def cells_near(self, x, y, r=0.8):
        c = self.CELL_KM
        i0, i1 = max(0, int((x - r - self.x0) / c)), min(self.nx - 1, int((x + r - self.x0) / c))
        j0, j1 = max(0, int((y - r - self.y0) / c)), min(self.ny - 1, int((y + r - self.y0) / c))
        I, J = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
        d2 = (self.x0 + (I + 0.5) * c - x) ** 2 + (self.y0 + (J + 0.5) * c - y) ** 2
        return (I * self.ny + J)[d2 <= r * r]

    def share(self, flat):
        """Each block group's share of its land inside the given cells."""
        o = self.owner[np.unique(flat)]
        o = o[o >= 0]
        return np.bincount(o, minlength=len(self.cells)) / np.maximum(self.cells, 1)



def walksheds(zones):
    """Walksheds for the base zones (built once)."""
    base = getattr(zones, "base", zones)
    if "_walksheds" not in base.__dict__:
        base._walksheds = Walksheds(base.x, base.y)
    return base._walksheds


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
    mode_year = net.station_mode_years()
    up_ex = t.get("upzone_existing_year")
    for sid, modes in opened.items():
        # each mode's uplift ramps from the year that mode arrives (a BRT stop that gets
        # metro 30 years later earns metro-level TOD from then, not from the BRT opening);
        # existing service counts only once upzoned (from upzone_existing_year)
        ramps = {}
        for m in modes:
            y0 = mode_year[sid].get(m, year)
            if y0 <= ex:
                if not up_ex or up_ex > year:
                    continue
                y0 = max(y0, up_ex)
            ramps[m] = 1.0 / (1.0 + np.exp(-((year - y0) - t["ramp_mid_years"]) / t["ramp_width_years"]))
        if not ramps:
            continue
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
        w = np.clip((r - d[near]) / (r - r0), 0.0, 1.0)
        best_p = t["pop_uplift"][kind] * max(t["mode_factor_pop"][m] * q for m, q in ramps.items())
        best_j = t["jobs_uplift"][kind] * max(t["mode_factor_jobs"][m] * q for m, q in ramps.items())
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


def station_areas(zones, net, year, cfg, radius_m, include_existing=True):
    """Station areas of the stations open in `year` (cached by station set).

    Returns a dict: `sids`, each station's `setting` and best `mode`, `zone_st`
    (index of each zone's nearest station if within radius_m, else -1), `zone_d`
    (km to it) and `area` (km2 of each station's disc that is closer to it than to
    any other station: a Voronoi split of the union of discs on a 50 m grid, so
    stations 1 km apart don't both count the land between them)."""
    opened = net.open_stations(year)
    ex = cfg["existing_year"]
    sids = sorted(s for s in opened if include_existing or net.station_year(s) > ex)
    cache = zones.__dict__.setdefault("_areas", {})
    key = (tuple(sids), radius_m)
    if key in cache:
        return cache[key]
    r = radius_m / 1000
    rank = {"metro": 0, "commuter": 1, "brt": 2}
    sc = zones.__dict__.setdefault("_setting", {})
    out = {"sids": sids, "zone_st": np.full(zones.n, -1), "zone_d": np.full(zones.n, np.inf),
           "area": np.zeros(len(sids)), "setting": [], "mode": []}
    if sids:
        sx, sy = geo.Projector().xy(np.array([net.stations[s].lat for s in sids]),
                                    np.array([net.stations[s].lon for s in sids]))
        for s in sids:
            st = net.stations[s]
            k = (round(st.lat, 5), round(st.lon, 5))
            if k not in sc:
                sc[k] = setting(zones, st.lat, st.lon, cfg)
            out["setting"].append(sc[k])
            out["mode"].append(min(opened[s], key=lambda m: rank.get(m, 9)))
        d = np.sqrt((zones.x[:, None] - sx[None, :]) ** 2 + (zones.y[:, None] - sy[None, :]) ** 2)
        near = d.argmin(axis=1)
        dn = d[np.arange(zones.n), near]
        inside = dn < r
        out["zone_st"][inside] = near[inside]
        out["zone_d"][inside] = dn[inside]
        g = np.arange(-r, r + 1e-9, 0.05)
        gx, gy = np.meshgrid(g, g)
        disc = gx ** 2 + gy ** 2 <= r * r
        ox, oy = gx[disc], gy[disc]
        for i in range(len(sids)):
            nb = np.nonzero((sx - sx[i]) ** 2 + (sy - sy[i]) ** 2 < (2 * r) ** 2)[0]
            dd = (sx[i] + ox[:, None] - sx[None, nb]) ** 2 + (sy[i] + oy[:, None] - sy[None, nb]) ** 2
            out["area"][i] = float((nb[dd.argmin(axis=1)] == i).sum()) * 0.05 ** 2
    cache[key] = out
    return out


def _in_centers(zones, centers):
    pj = geo.Projector()
    m = np.zeros(zones.n, dtype=bool)
    for v in centers.values():
        if isinstance(v, dict):
            cx, cy = pj.xy(v["lat"], v["lon"])
            m |= (zones.x - cx) ** 2 + (zones.y - cy) ** 2 <= v["radius_km"] ** 2
    return m


def capture(zones, net, year, cfg, pop, jobs):
    """Growth-capture policy (config.growth.capture) on this year's grown `pop` and
    `jobs`. Each `step_years` period from start_year: job_centers.jobs_share of the
    region's job growth goes to the job centers (in proportion to their jobs); then
    pop_share / jobs_share of the growth that would have landed outside station areas
    is moved into them, filling each station's headroom up to its target density
    (people + jobs per km2 by setting x mode factor) in proportion to headroom. What
    doesn't fit stays where it was. Returns (pop, jobs, info)."""
    c = cfg["growth"].get("capture") or {}
    sp, sj = c.get("pop_share", 0.0), c.get("jobs_share", 0.0)
    centers = c.get("job_centers") or {}
    sc = centers.get("jobs_share", 0.0)
    info = {"captured_pop": 0.0, "captured_jobs": 0.0, "center_jobs": 0.0}
    t = c.get("start_year", 9999)
    if year <= t or (sp <= 0 and sj <= 0 and sc <= 0):
        return pop, jobs, info
    r = c["radius_m"] / 1000
    r0 = c["full_radius_m"] / 1000
    tgt, mf = c["target_density_per_km2"], c["mode_factor"]
    floor = c.get("weight_floor", 500.0)
    add_p, add_j = np.zeros(zones.n), np.zeros(zones.n)
    sub_p, sub_j = np.zeros(zones.n), np.zeros(zones.n)
    in_c = _in_centers(zones, centers) if sc > 0 else np.zeros(zones.n, dtype=bool)
    while t < year:
        t1 = min(t + c.get("step_years", 5), year)
        inc_p = zones.pop * max(regional(cfg, "pop", t1) - regional(cfg, "pop", t), 0.0)
        inc_j = zones.jobs * max(regional(cfg, "jobs", t1) - regional(cfg, "jobs", t), 0.0)
        if sc > 0 and in_c.any():
            cj = sc * inc_j.sum()
            w = np.where(in_c, jobs + add_j, 0.0)
            add_j += cj * w / w.sum()
            out = np.where(in_c, 0.0, inc_j)
            sub_j += cj * out / out.sum()
        sa = station_areas(zones, net, t1, cfg, c["radius_m"], c.get("include_existing", True))
        if sa["sids"] and (sp > 0 or sj > 0):
            zs = sa["zone_st"]
            ins = zs >= 0
            ns = len(sa["sids"])
            cap = np.array([tgt[s] * mf[m] for s, m in zip(sa["setting"], sa["mode"])]) * sa["area"]
            now = pop + add_p - sub_p + jobs + add_j - sub_j
            head = np.maximum(cap - np.bincount(zs[ins], weights=now[ins], minlength=ns), 0.0)
            op = np.where(ins, 0.0, inc_p)
            oj = np.where(ins | in_c, 0.0, inc_j)
            cp, cj = sp * op.sum(), sj * oj.sum()
            want = cp + cj
            if want > 0 and head.sum() > 0:
                a = head * min(1.0, want / head.sum())          # people + jobs placed at each station
                wz = np.where(ins, np.clip((r - sa["zone_d"]) / (r - r0), 0.0, 1.0) * (pop + jobs + floor), 0.0)
                tot = np.bincount(zs[ins], weights=wz[ins], minlength=ns)
                got = np.zeros(zones.n)
                got[ins] = wz[ins] / np.maximum(tot[zs[ins]], 1e-9) * a[zs[ins]]
                gp, gj = got * (cp / want), got * (cj / want)
                add_p += gp
                add_j += gj
                if cp > 0:
                    sub_p += gp.sum() * op / op.sum()
                if cj > 0:
                    sub_j += gj.sum() * oj / oj.sum()
        t = t1
    info = {"captured_pop": float(add_p.sum()), "captured_jobs": float(add_j[~in_c].sum()),
            "center_jobs": float(add_j[in_c].sum())}
    return np.maximum(pop + add_p - sub_p, 0.0), np.maximum(jobs + add_j - sub_j, 0.0), info


def near_stations(zones, net, year, radius_m=800):
    """Zones whose centroid is within radius_m of a station open in `year`."""
    sids = list(net.open_stations(year))
    m = np.zeros(zones.n, dtype=bool)
    if not sids:
        return m
    sx, sy = geo.Projector().xy(np.array([net.stations[s].lat for s in sids]),
                                np.array([net.stations[s].lon for s in sids]))
    r2 = (radius_m / 1000) ** 2
    for i0 in range(0, len(sids), 200):
        d = (zones.x[:, None] - sx[None, i0:i0 + 200]) ** 2 + (zones.y[:, None] - sy[None, i0:i0 + 200]) ** 2
        m |= (d <= r2).any(axis=1)
    return m


def _spatial(zones, cfg, kind, mult):
    """Base values to grow by the regional multiplier `mult` so that growth lands as growth.spatial
    says: "county" scales each zone's growth (mult - 1) by its county's weight (jobs by
    jobs_factor of the deviation), normalized so the regional total is unchanged."""
    base = zones.pop if kind == "pop" else zones.jobs
    g = cfg["growth"]
    if g.get("spatial", "even") != "county" or mult == 1.0:
        return base
    cw = g["alt"]["county_weights"]
    raw = np.array([float(cw["weights"].get(i[:5], cw["other"])) for i in zones.ids])
    if kind == "jobs":
        raw = 1 + (raw - 1) * cw.get("jobs_factor", 1.0)
    w = raw * base.sum() / (raw * base).sum()
    return base * (1 + (mult - 1) * w) / mult


def grown_zones(zones, net, year, cfg):
    """A shallow copy of `zones` with this year's population, jobs and congestion."""
    g = cfg["growth"]
    up_p, up_j = tod_uplift(zones, net, year, cfg)
    z = copy.copy(zones)
    z.base = getattr(zones, "base", zones)   # base-year data (e.g. for a station's setting)
    nn = g["tod"]["net_new_share"]
    mp, mj = regional(cfg, "pop", year), regional(cfg, "jobs", year)
    z.pop = _grow(_spatial(zones, cfg, "pop", mp), mp, up_p, nn)
    z.jobs = _grow(_spatial(zones, cfg, "jobs", mj), mj, up_j, nn)
    z.pop, z.jobs, z.capture = capture(zones, net, year, cfg, z.pop, z.jobs)
    z.cong = congestion(cfg, year)
    z.year = year
    z.tod_key = (round(z.cong, 4), z.pop.round(1).tobytes(), z.jobs.round(1).tobytes(), year)
    return z
