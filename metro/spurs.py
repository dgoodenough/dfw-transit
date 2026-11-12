"""Airport spurs (texas-transit study/second_session.md, item 11).

An airport's terminal usually sits off the road graph the routes use (terminal loops and service
roads are in neither road profile), so an airport anchor marks the nearest center, often 2 km or more
away, and every line that "reaches the airport" stops there: Hobby, San Antonio and El Paso had no
station at their terminals. Here every pool line of a mode that ends within lines.airport_spur.max_km
of a terminal gets a variant running on to it: a short spur, elevated where it leaves the road (the
spur's km priced at the mode's elevated rate), with a station at the terminal. The variant is an
ordinary candidate whose centers extend the original's by the terminal, so the greedy treats it as an
extension (metro/select.py extends), and the line planner can add it or swap it in to serve the
anchor (metro/lineplan.py). Riders are the model's: the terminal's jobs and the trips through it;
air passengers aren't in the trip tables, which is what the planner's anchor penalty stands in for.
"""
import math

from .anchors import SERVE_KM
from .centers import Center


def add(m, cands, by, anchor_centers, gp, cfg, make_cand, setup, log=print):
    """Add spur variants to `cands` (in place) and the terminals to `by`. make_cand(uid, seq) -> a new
    road Cand; setup(cand, mode, P) sets its stations, cost and sketch value. Returns the variants."""
    sp = gp["lines"].get("airport_spur") or {}
    if not sp.get("enabled"):
        return []
    out = []
    max_km, per_airport = sp.get("max_km", 4.0), sp.get("per_airport", 6)
    years = cfg["staging"].get("value_opex_years", 20)
    for c0 in anchor_centers:
        for name, kind, ax, ay in getattr(c0, "anchor_list", []):
            if kind != "airport" or math.hypot(c0.x - ax, c0.y - ay) <= SERVE_KM:
                continue
            lat, lon = (float(v) for v in m.ll(ax, ay))
            t = Center(f"X{sum(1 for k in by if k.startswith('X')) + 1:02d}", ax, ay, lat, lon, 0.0, 0.0, 0.0, 0.0, 0.0,
                       "major", [])
            t.name, t.anchor, t.anchor_name = name, "airport", name
            by[t.id] = t
            ends = []
            for c in cands:
                if not (c.mode and c.kind == "road" and c.status == "pool" and c.P and len(c.P) > 1):
                    continue
                d0, d1 = math.dist(c.P[0], (ax, ay)), math.dist(c.P[-1], (ax, ay))
                if min(d0, d1) <= max_km:
                    ends.append((c, d1 <= d0))
            n = 0
            for c, at_end in sorted(ends, key=lambda e: -e[0].ratio):
                if n >= per_airport:
                    break
                P = list(c.P) if at_end else list(c.P)[::-1]
                seq = tuple(c.seq) if at_end else tuple(c.seq)[::-1]
                if t.id in seq:
                    continue
                gap = math.dist(P[-1], (ax, ay))
                k = max(1, int(math.ceil(gap / 0.1)))
                spur = [(P[-1][0] + (ax - P[-1][0]) * i / k, P[-1][1] + (ay - P[-1][1]) * i / k) for i in range(1, k + 1)]
                v = make_cand(seq + (t.id,))
                v.routes = {("metro" if c.mode == "metro" else "brt"): P + spur}
                v.mode_reason = (c.mode_reason + "; " if c.mode_reason else "") + f"with a {gap:.1f} km spur to the {name} terminal"
                setup(v, c.mode, P + spur)
                v.rho, v.rho1600 = getattr(c, "rho", 0.0), getattr(c, "rho1600", 0.0)   # the corridor's, for the report
                v.station_density = getattr(c, "station_density", 0.0)
                per_km = cfg["cost_musd_per_km"][c.mode]
                v.capital += gap * (per_km.get("elevated", per_km["surface"]) - per_km["surface"])
                v.spur_km = gap
                v.ratio = v.new_trips / max(v.capital + years * v.opex, 1.0)
                cands.append(v)
                out.append(v)
                n += 1
    if out and log:
        log(f"  airport spurs: {len(out)} variants to " + ", ".join(sorted({by[v.seq[-1]].name for v in out})))
    return out
