"""The story page (docs/index.html): why the 2 million riders plan is feasible, told against the
current track (today's system, no expansion: scenarios/current_track). The map moves to
docs/map.html.

    python -m dfwt story        # the page from the last build's results plus a few model runs

Everything on the page comes from here, from the model, or from cited facts in
dfwt/templates/story_facts.json; the template (dfwt/templates/story.html) only draws it."""
import collections
import copy
import csv
import json
import os

import numpy as np

from . import config, demand, geo, growth
from .network import Network

YEARS = (2025, 2050, 2100)
SCEN = ("current_track", "two_million")
WALK_KM = 0.8    # "a 10-minute walk": station-area figures count the share of each block group's land within it
MERGE_KM = 0.3   # stations of the same name this close are one place on the page

# A few trips that show what the network connects: (origin station, destination station, title, why).
CONNECTIONS = [
    ("Waxahachie", "Union Station", "Waxahachie to downtown Dallas",
     "An express bus in I-35E's managed lanes from 2027: Ellis County's first frequent link, decades before rail."),
    ("Downtown Arlington", "Union Station", "Arlington to downtown Dallas",
     "The largest US city without regular public transit gets rail in {opens}: the I-30 / FW Blue Line to downtown Dallas, and to Fort Worth from 2042."),
    ("Downtown Arlington", "Fort Worth Central", "Arlington to downtown Fort Worth",
     "One line between the two downtowns from {year}: I-30 trains run on as FW Blue at Handley, through Arlington's stadiums and UTA."),
    ("Irving Convention Center", "DFW Airport North", "Las Colinas to DFW Airport north",
     "The SH-114 Line ties the region's second job center to the airport and Grapevine."),
    ("Frisco Main St", "Pearl/Arts District", "Frisco to downtown Dallas",
     "BRT on Dallas Parkway and Preston Road comes first; DNT East rail reaches Frisco Main St in {year}."),
    ("Stockyards Main", "Magnolia / 8th Avenue", "The Stockyards to Magnolia Avenue",
     "FW Orange, the first of Fort Worth's own metro lines ({year}), from the Stockyards through downtown to the Near Southside."),
    ("Bishop Arts District", "Deep Ellum", "Bishop Arts to Deep Ellum",
     "Jefferson Boulevard BRT from 2030 and the Green Line: two of Dallas's night-out districts, with late-night service to about 2 a.m."),
    ("Union Station", "Fort Worth Central", "Downtown Dallas to downtown Fort Worth",
     "No high-speed link is planned between the two downtowns: TRE trains, faster and more often, and the I-30 / FW Blue Line through Arlington."),
]


# The range (review 3, R1 and R4): 2100 trips on three growth cases, for the plan, the current
# track, and the current track with the plan's access and parking policies (so the page can say
# what the network does and what policy does).
GROWTH_CASES = {"mid": {}, "county": {"spatial": "county"}, "low": {"case": "low"}}
POLICY_KEYS = ("access", "ridership")


def _variant(scen, growth=None, policy_from=None):
    cfg = config.load(scenario=scen)
    if policy_from:
        pol = config.load(scenario=policy_from)
        for k in POLICY_KEYS:
            cfg[k] = copy.deepcopy(pol[k])
    cfg["growth"].update(growth or {})
    return cfg, Network.load(scen, cfg=cfg)


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
    """station name -> station id, among stations some line serves (where platforms of several
    modes share a name, the one most lines serve)."""
    n_lines = collections.Counter(s for ln in net.lines.values() for s in set(ln.stop_ids))
    out = {}
    for sid in sorted(n_lines, key=lambda s: (-n_lines[s], s)):
        out.setdefault(net.stations[sid].name, sid)
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


def _grade_timeline(net):
    """station_id -> {mode: [[year, grade], ...]}: where its platform is from each year on
    ("surface", "elevated", "tunnel"), from the segments on either side as they open (Deep Ellum
    is at street level today and underground once the D2 subway opens)."""
    out = {}
    for ln in net.lines.values():
        for i, sid in enumerate(ln.stop_ids):
            adj = [ln.segments[k] for k in (i - 1, i) if 0 <= k < len(ln.segments) and ln.segments[k].year < 9999]
            tl = []
            for y in sorted({sg.year for sg in adj}):
                near = {sg.grade for sg in adj if sg.year <= y}
                g = "tunnel" if "tunnel" in near else "elevated" if "elevated" in near else "surface"
                if not tl or tl[-1][1] != g:
                    tl.append([y, g])
            if tl:
                cur = out.setdefault(sid, {}).get(ln.mode)
                if cur is None or tl[-1][1] == "tunnel" or (cur[-1][1] == "surface" and tl[-1][1] != "surface"):
                    out[sid][ln.mode] = tl
    return out


def _existing_lots(net, base):
    """Today's park & ride lots (access.pnr_existing, as the demand model gives them): station_id -> spaces."""
    ex = net.cfg["access"].get("pnr_existing") or {}
    if not ex.get("enabled"):
        return {}
    today = net.cfg["existing_year"]
    out = {}
    for ln in net.lines.values():
        for sid, y in zip(ln.stop_ids, ln.stop_years):
            if y <= today and sid not in out:
                st = net.stations[sid]
                if growth.setting(base, st.lat, st.lon, net.cfg) in ex["settings"]:
                    out[sid] = ex["spaces"]
    return out


def _one_seat_year(net, a, b):
    """The first year one line serves both places (a station name, any of its platforms), else 9999."""
    out = 9999
    for ln in net.lines.values():
        ya = [y for s, y in zip(ln.stop_ids, ln.stop_years) if net.stations[s].name == a]
        yb = [y for s, y in zip(ln.stop_ids, ln.stop_years) if net.stations[s].name == b]
        if ya and yb:
            out = min(out, max(min(ya), min(yb)))
    return out


def _years_csv(key):
    p = config.path("results", key, "years.csv")
    if not os.path.exists(p):
        return []
    keep = ("year", "daily_trips", "all_boardings", "pop_m", "jobs_m", "capex_busd", "opex_busd_per_year",
            "pop_covered_pct", "jobs_45min", "stations")
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        out.append({k: float(r[k]) for k in keep if r.get(k) not in (None, "")})
    return out


def compute(log=print):
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
    rng = {}
    for case, gr in GROWTH_CASES.items():
        rng[case] = {}
        for key, scen, pol in (("pr", "two_million", None), ("ct", "current_track", None),
                               ("ct_policy", "current_track", "two_million")):
            if case == "mid" and not pol:
                rng[case][key] = runs[(scen, 2100)]["trips"]
                continue
            cfg, n = _variant(scen, gr, pol)
            rng[case][key] = run_year(Context(cfg), n, 2100, want_loads=False)["daily_trips"]
            if log:
                log(f"  story: range {case} {key} 2100: {rng[case][key]:,.0f}")
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

    # stations of the proposal, with what is built there and how the area around it changes.
    # Stations of one name within MERGE_KM are one place on the page (a BRT stop beside a rail
    # station, say): their lines, years and walksheds together.
    net = nets["two_million"]
    ex = cfg0["existing_year"]
    my = net.station_mode_years()
    pj = geo.Projector()
    zx, zy = pj.xy(base.lat, base.lon)
    st_lines = {}
    for ln in net.lines.values():
        for sid in ln.stop_ids:
            st_lines.setdefault(sid, []).append(ln)
    places = []
    for sid in sorted(st_lines):
        s = net.stations[sid]
        if not any(y < 9999 for y in my[sid].values()):
            continue
        hit = next((p for p in places if p["name"] == s.name and
                    geo.hav_km(s.lat, s.lon, net.stations[p["ids"][0]].lat, net.stations[p["ids"][0]].lon) <= MERGE_KM), None)
        if hit:
            hit["ids"].append(sid)
        else:
            places.append({"name": s.name, "ids": [sid]})
    timeline = _grade_timeline(net)
    lots = _existing_lots(net, base)
    ws = growth.walksheds(base)
    stations, near_cells = [], []
    for p in places:
        ids = p["ids"]
        s = net.stations[ids[0]]
        lns = [ln for sid in ids for ln in st_lines[sid]]
        years = {}
        for sid in ids:
            for m, y in my[sid].items():
                if y < 9999:
                    years[m] = min(y, years.get(m, y))
        first = min(years.values())
        cells = np.concatenate([ws.cells_near(*pj.xy(net.stations[sid].lat, net.stations[sid].lon)) for sid in ids])
        near_cells.append(cells)
        near = ws.share(cells)   # each block group's share inside this walkshed
        hw_year = max(2050, first)   # how often it runs once it is open
        grade = {}
        for sid in ids:
            for m, tl in timeline.get(sid, {}).items():
                grade.setdefault(m, tl)
        garage = max(max(_garage(net, sid) for sid in ids), max(lots.get(sid, 0) for sid in ids))
        stations.append({
            "id": ids[0], "name": s.name, "lat": round(s.lat, 5), "lon": round(s.lon, 5),
            "setting": growth.setting(base, s.lat, s.lon, net.cfg),
            "years": years, "grade": grade,
            "lines": sorted({(ln.name, ln.color, ln.mode) for ln in lns}),
            "headway": [hw_year, min(ln.headway_at(hw_year) for ln in lns
                                     if min(my[sid].get(ln.mode, 9999) for sid in ids) <= hw_year)],
            "garage": garage, "garage_today": max(lots.get(sid, 0) for sid in ids),
            "existing": first <= ex,
            "pop": [int(round(float((runs[k]["pop"] * near).sum()), -1)) for k in
                    (("two_million", 2025), ("current_track", 2100), ("two_million", 2100))],
            "jobs": [int(round(float((runs[k]["jobs"] * near).sum()), -1)) for k in
                     (("two_million", 2025), ("current_track", 2100), ("two_million", 2100))],
        })
    stations.sort(key=lambda r: r["name"])
    # how much of the region is within a walk of a station: of the plan's (2100), and of today's
    near_any = ws.share(np.concatenate(near_cells))
    ct = nets["current_track"]
    ct_cells = [ws.cells_near(*pj.xy(ct.stations[sid].lat, ct.stations[sid].lon))
                for sid in {s for ln in ct.lines.values() for s in ln.stop_ids}]
    near_ct = ws.share(np.concatenate(ct_cells))
    p25, p_ct, p_p = (runs[k]["pop"] for k in (("two_million", 2025), ("current_track", 2100), ("two_million", 2100)))
    far = 1 - near_any
    change = {
        "pop_near_2025": float((p25 * near_any).sum()), "pop_2025": float(p25.sum()),
        "pop_near_2100_ct": float((p_ct * near_any).sum()), "pop_near_2100": float((p_p * near_any).sum()),
        "pop_far_2100_ct": float((p_ct * far).sum()), "pop_far_2100": float((p_p * far).sum()),
        "pop_2100": float(p_p.sum()), "pop_2100_ct": float(p_ct.sum()),
        "near_today_2100_ct": float((p_ct * near_ct).sum()),   # current track: today's stations
    }

    # connections: ride time on the proposal by year, the rush-hour drive, jobs reachable at the start
    names = _station_index(net)
    conns = []
    ww = net.cfg["wait"].get("weight", 1.0)
    for o, d, title, why in CONNECTIONS:
        if o not in names or d not in names:
            if log:
                log(f"  story: connection {o} -> {d} skipped (station not found)")
            continue
        so, sd = net.stations[names[o]], net.stations[names[d]]
        oz = int(np.argmin(np.hypot(zx - pj.xy(so.lat, so.lon)[0], zy - pj.xy(so.lat, so.lon)[1])))
        row = {"from": o, "to": d, "from_id": names[o], "to_id": names[d], "title": title, "why": why,
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
                    if any(k == "ride" for k, *_ in legs):   # clock minutes, station to station: waits unweighted
                        t = round(sum(m / ww if k == "wait" else m for k, *_, m in legs))
                        if sc == "two_million" and y == 2100:   # the lines the trip rides, for its map
                            row["lines"] = list(dict.fromkeys(run.line.id for k, _, _, run, _ in legs if k == "ride"))
                row["ride"][f"{sc}_{y}"] = t
                row["jobs45"][f"{sc}_{y}"] = int(round(float(runs[(sc, y)]["jobs45"][oz]), -2))
        row["opens"] = min(net.station_mode_years()[names[o]].values())
        row["why"] = why.replace("{year}", str(_one_seat_year(net, o, d))).replace("{opens}", str(row["opens"]))
        conns.append(row)

    # network lines, simplified, with the years each piece opens. Today's system (and the current
    # track) is drawn from current_track, where today's lines keep their own names and colors (in
    # the proposal several run through onto new lines)
    def line_rows(n, last):
        out = []
        for ln in n.lines.values():
            segs = []
            for s in ln.segments:
                if s.year > last:
                    continue
                pts = _simplify([(round(x, 5), round(y, 5)) for x, y in s.pts], 0.0006)
                segs.append([s.year, [[round(x, 4), round(y, 4)] for x, y in pts]])
            if segs:
                out.append({"id": ln.id, "name": ln.name, "mode": ln.mode, "color": ln.color, "segs": segs})
        return out
    lines, lines_today = line_rows(net, 9998), line_rows(nets["current_track"], ex)

    budget = cfg0["budget"]["musd_per_year"]
    return {
        "years": {k: _years_csv(k) for k in ("current_track", "two_million", "plan")},
        "zones": zones, "stations": stations, "change": change, "connections": conns, "lines": lines,
        "lines_today": lines_today, "range": rng,
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
