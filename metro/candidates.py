"""Candidate corridors (step 2b) and their stations, mode, cost (step 2c).

1. Links: a Gabriel graph over the centers (no other center inside the circle on a link as
   diameter), up to links.max_km. Road links join urban centers and are routed twice on the
   road graph (metro profile: freeways and major arterials; BRT profile: arterials); rail
   links also reach towns and are routed on standard-gauge track. A link whose route is too
   roundabout (links.max_detour) or starts too far from its centers is dropped.
2. Lines: for every pair of centers, the shortest path through the links (route km) is a
   candidate line if it is the right length for some mode, not too circuitous and has no
   sharp turn at a center it passes (config "lines").
3. Mode: from corridor density, people + jobs within 800 m of the routed line per route-km
   (config "modes"). Road paths: metro / streetcar / BRT by threshold; rail paths: regional rail.
4. Stations: every center the line passes, every existing station within snap_existing_m of it,
   both ends, and stops in between at the mode's spacing for the setting (config "stations").
5. Cost: config.json unit costs (cost_musd_per_km by mode and grade, station_cost_musd,
   park & ride garages at termini and regional-rail stations), metro in tunnel near downtowns;
   operating cost as dfwt.network.opex_musd computes it.
"""
import collections
import heapq
import itertools
import math

import numpy as np

from . import geom


class Link:
    def __init__(self, a, b, kind):
        self.a, self.b, self.kind = a, b, kind
        self.routes = {}     # profile -> [(x, y)] oriented a -> b, or None
        self.km = {}
        self.why = {}

    def oriented(self, profile, frm):
        P = self.routes.get(profile)
        if P is None:
            return None
        return P if frm == self.a else P[::-1]


def gabriel(nodes, max_km, slack):
    """Links (i, j) of the Gabriel graph over nodes [(x, y)], at most max_km long."""
    out = []
    n = len(nodes)
    for i in range(n):
        for j in range(i + 1, n):
            (xi, yi), (xj, yj) = nodes[i], nodes[j]
            d = math.hypot(xi - xj, yi - yj)
            if d > max_km or d < 0.5:
                continue
            mx, my, r = (xi + xj) / 2, (yi + yj) / 2, d / 2 * slack
            if any(math.hypot(nodes[k][0] - mx, nodes[k][1] - my) < r for k in range(n) if k not in (i, j)):
                continue
            out.append((i, j, d))
    return out


def build_links(m, router, urban, towns, gp, log=print):
    """Road links among urban centers, rail links among urban centers + towns, all routed."""
    L = gp["links"]
    links = []
    xy = [(c.x, c.y) for c in urban]
    for i, j, d in gabriel(xy, L["max_km"]["road"], L["gabriel_slack"]):
        lk = Link(urban[i].id, urban[j].id, "road")
        lk.straight = d
        for prof in ("metro", "brt"):
            pts = router.route(prof, (urban[i].lat, urban[i].lon), (urban[j].lat, urban[j].lon))
            lk.routes[prof] = _check(m, pts, urban[i], urban[j], d, L["max_detour"]["road"], L["end_gap_km"]["road"],
                                     lk, prof)
        links.append(lk)
    router.save()
    n_ok = {p: sum(1 for k in links if k.routes.get(p)) for p in ("metro", "brt")}
    log(f"  links: {len(links)} road; routed metro profile {n_ok['metro']}, BRT profile {n_ok['brt']}")
    return links


def rail_lines(m, router, urban, towns, gp, log=print):
    """Regional rail candidates: from every downtown or major center along existing standard-gauge
    track to every center or town lines.min_km..max_km away (straight line / max_circuity). The
    route must stay within links.max_detour of the straight line and start/end within
    links.end_gap_km of the two places. Its centers: every center and town within end_gap_km of
    the track, in order. Returns [(seq, polyline)] and the per-route outcomes for the report."""
    if not m.osm.get("rail"):
        return [], collections.Counter({"no osm/rail.parquet": 1})
    L, Lc = gp["links"], gp["lines"]
    gap_km = L["end_gap_km"]["rail"]
    allc = urban + towns
    lo, hi = Lc["min_km"]["commuter"] / Lc["max_circuity"], Lc["max_km"]["commuter"] / 1.1
    out, why = {}, collections.Counter()
    for a in [c for c in urban if c.kind in ("downtown", "major")]:
        for b in allc:
            d = math.hypot(a.x - b.x, a.y - b.y)
            if b is a or not lo <= d <= hi:
                continue
            pts = router.route("rail", (a.lat, a.lon), (b.lat, b.lon), snap_km=gap_km)
            lk = Link(a.id, b.id, "rail")
            P = _check(m, pts, a, b, d, L["max_detour"]["rail"], gap_km, lk, "rail")
            if P is None:
                why[_why_bucket(lk.why["rail"])] += 1
                continue
            why["routed"] += 1
            cum = geom.cumlen(P)
            on = sorted((geom.project(P, cum, (c.x, c.y))[0], c.id) for c in allc
                        if c is not a and c is not b and geom.project(P, cum, (c.x, c.y))[1] <= gap_km)
            seq = (a.id,) + tuple(cid for _, cid in on) + (b.id,)
            if seq not in out and seq[::-1] not in out:
                out[seq] = P
    router.save()
    log(f"  rail routes: " + ", ".join(f"{k} {v}" for k, v in why.most_common()))
    return list(out.items()), why


def _why_bucket(w):
    if w.startswith("route ends"):
        return "no track near both ends"
    if w.startswith("route "):
        return "track too roundabout"
    return "no track route"


def _check(m, pts, ca, cb, d, max_detour, max_gap, lk, prof):
    if not pts or len(pts) < 2:
        lk.why[prof] = "no route"
        return None
    P = geom.to_xy(m, pts)
    if math.dist(P[0], (ca.x, ca.y)) > math.dist(P[-1], (ca.x, ca.y)):
        P = P[::-1]
    gap = max(math.dist(P[0], (ca.x, ca.y)), math.dist(P[-1], (cb.x, cb.y)))
    km = geom.length(P)
    if gap > max_gap:
        lk.why[prof] = f"route ends {gap:.1f} km from a center"
        return None
    if km > max_detour * max(d, 1.0):
        lk.why[prof] = f"route {km:.1f} km for {d:.1f} km straight"
        return None
    if prof != "rail" and gap > 0.05:
        # a road line runs to the center point itself (the station there is placed on the route);
        # a rail line stays on the track (its stop is the track point nearest the center)
        P = [(ca.x, ca.y)] + P + [(cb.x, cb.y)]
    lk.km[prof] = geom.length(P)
    return P


def paths(centers, links, kind, profile, gp, ends_ok=None):
    """Shortest paths (route km) between every pair of centers over links of `kind` routed
    with `profile`; filtered by length, circuity and turns. Returns [(node ids, polyline)]."""
    by = {c.id: c for c in centers}
    adj = {c.id: [] for c in centers}
    for lk in links:
        if lk.kind == kind and lk.routes.get(profile) and lk.a in adj and lk.b in adj:
            adj[lk.a].append((lk.b, lk.km[profile], lk))
            adj[lk.b].append((lk.a, lk.km[profile], lk))
    Lc = gp["lines"]
    lo = min(Lc["min_km"][m] for m in (["commuter"] if kind == "rail" else ["metro", "brt", "streetcar"]))
    hi = max(Lc["max_km"][m] for m in (["commuter"] if kind == "rail" else ["metro", "brt", "streetcar"]))
    out = {}
    for s in adj:
        dist, prev, pq = {s: 0.0}, {}, [(0.0, s)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, 1e18) or d > hi:
                continue
            for v, w, lk in adj[u]:
                if d + w < dist.get(v, 1e18):
                    dist[v], prev[v] = d + w, (u, lk)
                    heapq.heappush(pq, (d + w, v))
        for t, d in dist.items():
            if t <= s or d < lo or d > hi:
                continue
            if ends_ok and not ends_ok(by[s], by[t]):
                continue
            seq, lks = [t], []
            while seq[-1] != s:
                u, lk = prev[seq[-1]]
                lks.append(lk)
                seq.append(u)
            seq.reverse()
            lks.reverse()
            straight = math.hypot(by[s].x - by[t].x, by[s].y - by[t].y)
            if d > Lc["max_circuity"] * max(straight, 1.0):
                continue
            pts = [(by[c].x, by[c].y) for c in seq]
            if any(geom.turn_deg(pts[k - 1], pts[k], pts[k + 1]) > Lc["max_turn_deg"] for k in range(1, len(pts) - 1)):
                continue
            P = []
            for k, lk in enumerate(lks):
                Q = lk.oriented(profile, seq[k])
                P.extend(Q if not P else Q[1:])
            out[tuple(seq)] = P
    return list(out.items())


# ------------------------------------------------------------------ stations
def place_stations(P, mode, anchors, gp, dens_fn, urban_density):
    """Stops along polyline P: anchors [(s, priority, ref)] (centers, existing stations)
    are kept, both ends added, gaps filled at the mode's spacing for the setting.
    Returns [(s, (x, y), ref)] in order along P."""
    cum = geom.cumlen(P)
    L = cum[-1]
    sp = gp["stations"]["spacing_km"][mode]
    min_gap = gp["stations"]["min_gap_km"][mode]
    pts = sorted([(max(0.0, min(L, s)), pr, ref) for s, pr, ref in anchors] + [(0.0, 0, None), (L, 0, None)])
    # merge anchors closer than min_gap: keep the higher priority (existing 3 > center 2 > end 0)
    kept = []
    for a in pts:
        if kept and a[0] - kept[-1][0] < min_gap:
            if a[1] > kept[-1][1]:
                kept[-1] = a
            continue
        kept.append(a)
    if kept[-1][0] < L - min_gap:
        kept.append((L, 0, None))

    def gap(s):
        x, y = geom.point_at(P, cum, s)
        return sp["urban"] if dens_fn(x, y) >= urban_density else sp["suburban"]

    out = []
    for (s0, _, r0), (s1, _, r1) in zip(kept, kept[1:]):
        if not out:
            out.append((s0, r0))
        cuts, pos = [], s0
        while pos + gap(pos) < s1 - 0.5 * gap(pos):
            pos += gap(pos)
            cuts.append(pos)
        if cuts:
            k = (s1 - s0) / (cuts[-1] + gap(cuts[-1]) - s0)
            cuts = [s0 + (c - s0) * k for c in cuts]
        out += [(c, None) for c in cuts]
        out.append((s1, r1))
    return [(s, geom.point_at(P, cum, s), ref) for s, ref in out]


# ------------------------------------------------------------------ costing
def line_cost(cfg, mode, stops, P, downtowns, core_r, existing_mode_stations):
    """(capital $M at 2025 prices, [grade per hop], km) of a line with stops [(s, xy, ref)]."""
    per_km = cfg["cost_musd_per_km"][mode]
    sc = cfg["station_cost_musd"]
    grades, cap = [], 0.0

    def core(p):
        return any(math.dist(p, d) <= core_r for d in downtowns)
    for (s0, p0, _), (s1, p1, _) in zip(stops, stops[1:]):
        g = "tunnel" if mode == "metro" and (core(p0) or core(p1)) else "surface"
        grades.append(g)
        cap += (s1 - s0) * per_km.get(g, per_km["surface"])
    sp = cfg["access"]["pnr_spaces"]
    per_space = cfg.get("garage_musd_per_space", 0.0)
    for i, (s, p, ref) in enumerate(stops):
        if ref and ref in existing_mode_stations.get(mode, ()):
            continue    # today's platform of the same mode
        under = any(grades[k] == "tunnel" for k in (i - 1, i) if 0 <= k < len(grades))
        cap += sc.get(mode + "_tunnel", sc[mode]) if under else sc[mode]
        if per_space and not core(p):
            if mode == "commuter":
                cap += sp["commuter_station"] * per_space
            elif i in (0, len(stops) - 1):
                cap += sp.get(mode + "_terminus", sp["terminus"]) * per_space
    return cap, grades


def run_minutes(cfg, mode, stops):
    mc = cfg["modes"][mode]
    km = stops[-1][0] - stops[0][0]
    return km / mc["cruise_kmh"] * 60 + (len(stops) - 1) * mc["stop_penalty_min"]


def opex_musd(cfg, mode, stops, headway=None):
    oc = cfg["operating"]
    hw = headway or cfg["modes"][mode]["default_headway_min"]
    veh_h = 2 * run_minutes(cfg, mode, stops) / hw * oc["span_hours"] * oc["layover"]
    return veh_h * oc["usd_per_train_hour"][mode] * oc["days_per_year"] / 1e6


def corridor_activity(m, zidx, P, r_km=0.8):
    """(people, jobs) within r_km of polyline P."""
    z = zidx.near_points(geom.resample(P, 0.2), r_km)
    return float(m.pop[z].sum()), float(m.jobs[z].sum()), z


def choose_mode(kind, km, rho, rho1600, gp):
    """Mode by density and length (config "modes", "lines"); (mode or None, reason)."""
    M, Lc = gp["modes"], gp["lines"]

    def fits(mode):
        return Lc["min_km"][mode] <= km <= Lc["max_km"][mode]
    if kind == "rail":
        if rho1600 >= M["commuter_1600m"] and fits("commuter"):
            return "commuter", f"rail corridor, {rho1600:,.0f} people+jobs within 1.6 km per km >= {M['commuter_1600m']:,}"
        return None, f"rail corridor too thin ({rho1600:,.0f} per km within 1.6 km < {M['commuter_1600m']:,})" \
            if fits("commuter") else f"rail corridor {km:.0f} km outside the regional-rail length range"
    if rho >= M["metro"] and fits("metro"):
        return "metro", f"{rho:,.0f} people+jobs per route-km >= metro {M['metro']:,}"
    if rho >= M["streetcar"] and fits("streetcar"):
        return "streetcar", f"{rho:,.0f} per route-km >= streetcar {M['streetcar']:,}, {km:.1f} km short line"
    if rho >= M["brt"] and fits("brt"):
        return "brt", f"{rho:,.0f} per route-km >= BRT {M['brt']:,}" + (
            f" (< metro {M['metro']:,})" if rho < M["metro"] else f" (metro needs >= {Lc['min_km']['metro']} km)")
    if rho >= M["metro"] and km > Lc["max_km"]["metro"]:
        return None, f"{km:.0f} km is longer than a metro line (max {Lc['max_km']['metro']})"
    if rho < M["brt"]:
        return None, f"too thin: {rho:,.0f} people+jobs per route-km < BRT {M['brt']:,}"
    return None, f"{km:.1f} km outside the length range of the modes its density allows"


def line_name(seq, by):
    a, b = by[seq[0]], by[seq[-1]]
    return f"{a.name} - {b.name}"


def pairs(xs):
    return itertools.combinations(xs, 2)


def straightness(P):
    L = geom.length(P)
    return math.dist(P[0], P[-1]) / L if L else 1.0


def nearest_index(points, q):
    return int(np.argmin([math.dist(p, q) for p in points]))
