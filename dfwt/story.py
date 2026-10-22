"""The story page (docs/index.html): why the 2 million riders plan is feasible, told against the
current track (today's system, no expansion: scenarios/current_track). The map moves to
docs/map.html.

    python -m dfwt story        # the page from the last build's results plus a few model runs

Everything on the page comes from here, from the model, or from cited facts in
dfwt/templates/story_facts.json; the template (dfwt/templates/story.html) only draws it."""
import csv
import json
import os

import numpy as np

from . import config, demand, geo, growth
from .network import Network

YEARS = (2025, 2050, 2100)
SCEN = ("current_track", "two_million")
WALK_KM = 0.8    # "a 10-minute walk": station-area figures use block groups within this distance

# A few trips that show what the network connects: (origin station, destination station, title, why).
CONNECTIONS = [
    ("Waxahachie", "Union Station", "Waxahachie to downtown Dallas",
     "An express bus in I-35E's managed lanes from 2027: Ellis County's first frequent link, decades before rail."),
    ("Downtown Arlington", "Union Station", "Arlington to downtown Dallas",
     "The largest US city without regular public transit gets the I-30 Line by 2038, on to Fort Worth with FW Blue by about 2043."),
    ("Downtown Arlington", "Central Station", "Arlington to downtown Fort Worth",
     "One line between the two downtowns, through Arlington's stadiums and UTA."),
    ("Irving Convention Center", "DFW Airport North", "Las Colinas to DFW Airport north",
     "The SH-114 Line ties the region's second job center to the airport and Grapevine."),
    ("Frisco Main St", "Pearl/Arts District", "Frisco to downtown Dallas",
     "DNT East reaches Frisco in the 2040s; BRT on Dallas Parkway and Preston Road comes first."),
    ("Stockyards Main", "Central Station", "The Stockyards to downtown Fort Worth",
     "FW Orange, the first of Fort Worth's own metro lines (2035)."),
]


def _simplify(pts, tol):
    """Ramer-Douglas-Peucker on (lon, lat) points, tol in degrees."""
    if len(pts) < 3:
        return pts
    a, b = np.array(pts[0]), np.array(pts[-1])
    P = np.array(pts)
    d = b - a
    n = np.hypot(*d)
    q = P - a
    dist = np.abs(d[0] * q[:, 1] - d[1] * q[:, 0]) / n if n else np.hypot(q[:, 0], q[:, 1])
    k = int(np.argmax(dist))
    if dist[k] <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[:k + 1], tol)[:-1] + _simplify(pts[k:], tol)


def _station_index(net):
    """station name -> station id, among stations some line serves (first one wins)."""
    served = {s for ln in net.lines.values() for s in ln.stop_ids}
    out = {}
    for sid, s in net.stations.items():
        if sid in served:
            out.setdefault(s.name, sid)
    return out


def _garage(net, sid):
    """Park & ride spaces the plan gives a station (as Network.stop_cost charges them)."""
    if net.in_core(sid):
        return 0
    sp = net.cfg["access"]["pnr_spaces"]
    best = 0
    for ln in net.lines.values():
        if sid not in ln.stop_ids:
            continue
        i = ln.stop_ids.index(sid)
        if ln.mode == "commuter":
            best = max(best, sp["commuter_station"])
        elif i in (0, len(ln.stop_ids) - 1) or sid in ln.pnr_stops:
            best = max(best, sp.get(ln.mode + "_terminus", sp["terminus"]))
    return best


def _years_csv(key):
    p = config.path("results", key, "years.csv")
    if not os.path.exists(p):
        return []
    keep = ("year", "daily_trips", "all_boardings", "pop", "jobs", "capex_busd", "opex_busd_per_year",
            "pop_800m", "jobs_45min", "stations")
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        out.append({k: float(r[k]) for k in keep if r.get(k) not in (None, "")})
    return out


def compute(log=print):
    from . import webmap
    from .evaluate import Context, run_year
    cfg0 = config.load()
    base = demand.Zones(cfg0)
    nets = {sc: Network.load(sc) for sc in SCEN}
    runs = {}
    for sc, net in nets.items():
        ctx = Context(net.cfg)
        for y in YEARS:
            r = run_year(ctx, net, y, want_loads=False)
            z, _ = ctx.year_inputs(net, y)
            runs[(sc, y)] = {"jobs45": r["jobs_reach"][45], "pop": z.pop.copy(), "jobs": z.jobs.copy(),
                             "graph": r["graph"], "z": z, "trips": r["daily_trips"]}
            if log:
                log(f"  story: {sc} {y}: {r['daily_trips']:,.0f} daily trips")
    # jobs a rush-hour drive reaches in 45 minutes (the same for both: the roads don't change)
    drive45 = {}
    for y in YEARS:
        z = runs[("two_million", y)]["z"]
        out = np.zeros(z.n)
        for i0 in range(0, z.n, 500):
            i1 = min(z.n, i0 + 500)
            out[i0:i1] = ((z.drive_min(z.dist_rows(i0, i1)) <= 45) * z.jobs[None, :]).sum(axis=1)
        drive45[y] = out

    zones = {"lat": [round(float(v), 4) for v in base.lat], "lon": [round(float(v), 4) for v in base.lon],
             "pop": [int(round(float(v))) for v in base.pop]}
    for (sc, y), r in runs.items():
        zones[f"jobs45_{sc}_{y}"] = [int(round(float(v), -2)) for v in r["jobs45"]]
    for y in (2025, 2100):
        zones[f"drive45_{y}"] = [int(round(float(v), -2)) for v in drive45[y]]
        zones[f"pop_{y}"] = [int(round(float(v))) for v in runs[("two_million", y)]["pop"]]
    zones["pop_ct_2100"] = [int(round(float(v))) for v in runs[("current_track", 2100)]["pop"]]

    # stations of the proposal, with what is built there and how the area around it changes
    net = nets["two_million"]
    grades = webmap.station_grades(net)
    my = net.station_mode_years()
    pj = geo.Projector()
    zx, zy = pj.xy(base.lat, base.lon)
    st_lines = {}
    for ln in net.lines.values():
        for sid in ln.stop_ids:
            st_lines.setdefault(sid, []).append(ln)
    stations = []
    for sid, lns in st_lines.items():
        s = net.stations[sid]
        years = {m: y for m, y in my[sid].items() if y < 9999}
        if not years:
            continue
        x, y = pj.xy(s.lat, s.lon)
        near = np.hypot(zx - x, zy - y) <= WALK_KM
        stations.append({
            "id": sid, "name": s.name, "lat": round(s.lat, 5), "lon": round(s.lon, 5),
            "setting": growth.setting(base, s.lat, s.lon, net.cfg),
            "years": years, "grade": grades.get(sid, {}),
            "lines": sorted({(ln.name, ln.color, ln.mode) for ln in lns}),
            "headway": min(ln.headway_at(2050) for ln in lns),
            "garage": _garage(net, sid),
            "existing": min(years.values()) <= net.cfg["existing_year"],
            "pop": [int(round(float(runs[k]["pop"][near].sum()), -1)) for k in
                    (("two_million", 2025), ("current_track", 2100), ("two_million", 2100))],
            "jobs": [int(round(float(runs[k]["jobs"][near].sum()), -1)) for k in
                     (("two_million", 2025), ("current_track", 2100), ("two_million", 2100))],
        })
    stations.sort(key=lambda r: r["name"])
    # how much of the region a station area touches at all
    near_any = np.zeros(base.n, dtype=bool)
    for st in stations:
        x, y = pj.xy(st["lat"], st["lon"])
        near_any |= np.hypot(zx - x, zy - y) <= WALK_KM
    p25, p_ct, p_p = (runs[k]["pop"] for k in (("two_million", 2025), ("current_track", 2100), ("two_million", 2100)))
    change = {
        "zones_near": int(near_any.sum()), "zones": int(base.n),
        "pop_near_2025": float(p25[near_any].sum()), "pop_2025": float(p25.sum()),
        "pop_near_2100_ct": float(p_ct[near_any].sum()), "pop_near_2100": float(p_p[near_any].sum()),
        "pop_far_2100_ct": float(p_ct[~near_any].sum()), "pop_far_2100": float(p_p[~near_any].sum()),
        "pop_2100": float(p_p.sum()),
    }

    # connections: ride time on the proposal by year, the rush-hour drive, jobs reachable at the start
    names = _station_index(net)
    conns = []
    for o, d, title, why in CONNECTIONS:
        if o not in names or d not in names:
            if log:
                log(f"  story: connection {o} -> {d} skipped (station not found)")
            continue
        so, sd = net.stations[names[o]], net.stations[names[d]]
        oz = int(np.argmin(np.hypot(zx - pj.xy(so.lat, so.lon)[0], zy - pj.xy(so.lat, so.lon)[1])))
        row = {"from": o, "to": d, "title": title, "why": why,
               "from_ll": [so.lat, so.lon], "to_ll": [sd.lat, sd.lon], "ride": {}, "drive": {}, "jobs45": {}}
        km = geo.hav_km(so.lat, so.lon, sd.lat, sd.lon)
        for y in YEARS:
            row["drive"][y] = round(float(demand.drive_minutes(net.cfg["drive"], km, growth.congestion(net.cfg, y))))
            for sc in SCEN:
                g = runs[(sc, y)]["graph"]
                a, b = g.sidx.get(names[o]), g.sidx.get(names[d])
                t = None
                if a is not None and b is not None:
                    legs, _ = g.itinerary(a, b)
                    if any(k == "ride" for k, *_ in legs):
                        t = round(sum(m for *_, m in legs))
                row["ride"][f"{sc}_{y}"] = t
                row["jobs45"][f"{sc}_{y}"] = int(round(float(runs[(sc, y)]["jobs45"][oz]), -2))
        row["opens"] = min(net.station_mode_years()[names[o]].values())
        conns.append(row)

    # network lines, simplified, with the years each piece opens
    lines = []
    for ln in net.lines.values():
        segs = []
        for s in ln.segments:
            if s.year >= 9999:
                continue
            pts = _simplify([(round(x, 5), round(y, 5)) for x, y in s.pts], 0.0006)
            segs.append([s.year, [[round(x, 4), round(y, 4)] for x, y in pts]])
        if segs:
            lines.append({"id": ln.id, "name": ln.name, "mode": ln.mode, "color": ln.color,
                          "existing": ln.status == "existing", "segs": segs})

    budget = cfg0["budget"]["musd_per_year"]
    return {
        "years": {k: _years_csv(k) for k in ("current_track", "two_million", "plan")},
        "zones": zones, "stations": stations, "change": change, "connections": conns, "lines": lines,
        "assumptions": {
            "budget_musd": budget,
            "cost_per_km": {m: v for m, v in cfg0["cost_musd_per_km"].items() if not m.startswith("_")},
            "station_cost": {m: v for m, v in cfg0["station_cost_musd"].items() if not m.startswith("_")},
            "transfer_min": cfg0["transfer"]["penalty_min"],
            "tod": {k: v for k, v in nets["two_million"].cfg["growth"]["tod"].items() if not k.startswith("_")},
            "capture": nets["two_million"].cfg["growth"].get("capture", {}),
            "pnr_spaces": cfg0["access"]["pnr_spaces"],
            "walk_km": WALK_KM,
        },
    }


def write(out_path, data=None, log=print):
    data = data or compute(log=log)
    tdir = os.path.join(os.path.dirname(__file__), "templates")
    with open(os.path.join(tdir, "story.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(tdir, "story_facts.json"), encoding="utf-8") as f:
        data["facts"] = json.load(f)
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html.replace("/*__DATA__*/null", blob))
    return out_path
