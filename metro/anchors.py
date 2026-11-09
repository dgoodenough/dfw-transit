"""Anchors (Phase 3 of texas-transit's study/hsr_buildout.md): places a line should be able to end at
or must serve even when they aren't density peaks: airports, universities, medical districts,
stadiums, transit centers, and the downtown itself.

The registry entry's `anchors` ([{name, lat, lon, kind, weight}], kind one of downtown, airport,
university, medical, stadium, hub) are added to the centers the generator links and routes between:
an anchor within MERGE_KM of a center marks that center (a downtown anchor moves it onto the
anchor, makes it the downtown and demotes any other downtown within downtown_sep_km). Other anchors
don't move their center: an airport terminal or a campus can sit off the road graph the routes
snap to (moving El Paso's airport center there lost half its routed links), and a node of their
own so near splits the corridors into stubs too short for rail (UT Austin beside downtown). Those
are listed on the center and reported as served or not. Otherwise it becomes a center of its own,
kind "major", its activity the people and jobs around it plus its weight (riders a day it draws
beyond them: an airport's passengers, a campus's students). Without registry anchors nothing
changes.
"""
import math

from .centers import Center

MERGE_KM = 3.0   # an anchor this close to a center marks it: a new node so near would split corridors


def apply(m, centers, anchors, p, log=print):
    """Add or mark anchors among `centers` (in place). Returns the anchor centers."""
    if not anchors:
        return []
    out = []
    r_act = p.get("downtown_radius_km", 1.5)
    for k, a in enumerate(anchors):
        x, y = (float(v) for v in m.xy(a["lat"], a["lon"]))
        near = min(centers, key=lambda c: math.hypot(c.x - x, c.y - y), default=None)
        dist = math.hypot(near.x - x, near.y - y) if near is not None else float("inf")
        if dist <= MERGE_KM:
            c = near
            if a.get("kind") == "downtown":   # the downtown is where the registry says (job density, the transit hub)
                c.x, c.y, c.lat, c.lon = x, y, a["lat"], a["lon"]
        else:
            inside = (m.x - x) ** 2 + (m.y - y) ** 2 <= r_act ** 2
            pop, jobs = float(m.pop[inside].sum()), float(m.jobs[inside].sum()) if m.jobs_ok else 0.0
            c = Center(f"A{k + 1:02d}", x, y, a["lat"], a["lon"], pop + jobs + float(a.get("weight", 0)), pop, jobs,
                       0.0, 0.0, "major", [])
            c.near_jobs = jobs
            centers.append(c)
        if getattr(c, "anchor", None) is None or a.get("kind") == "downtown":   # a downtown anchor names its center
            c.anchor, c.anchor_name = a.get("kind", "hub"), a["name"]
        c.anchor_list = getattr(c, "anchor_list", []) + [(a["name"], a.get("kind", "hub"), float(x), float(y))]
        if a.get("kind") == "downtown":
            for o in centers:
                if o is not c and o.kind == "downtown" and math.hypot(o.x - c.x, o.y - c.y) <= p["downtown_sep_km"]:
                    o.kind = "major"
            c.kind = "downtown"
        if c not in out:
            out.append(c)
    if log:
        log(f"  anchors: {', '.join(f'{n} ({k})' for c in out for n, k, *_ in c.anchor_list)}")
    return out
