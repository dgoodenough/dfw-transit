"""Anchors (Phase 3 of texas-transit's study/hsr_buildout.md): places a line should be able to end at
or must serve even when they aren't density peaks: airports, universities, medical districts,
stadiums, transit centers, and the downtown itself.

The registry entry's `anchors` ([{name, lat, lon, kind, weight}], kind one of downtown, airport,
university, medical, stadium, hub) are added to the centers the generator links and routes between:
an anchor within merge_km of a center marks that center (a downtown anchor makes it the downtown
and demotes any other downtown within downtown_sep_km); otherwise it becomes a center of its own,
kind "major", its activity the people and jobs around it plus its weight (riders a day it draws
beyond them: an airport's passengers, a campus's students). Without registry anchors nothing
changes.
"""
import math

from .centers import Center

MERGE_KM = 1.5


def apply(m, centers, anchors, p, log=print):
    """Add or mark anchors among `centers` (in place). Returns the anchor centers."""
    if not anchors:
        return []
    out = []
    r_act = p.get("downtown_radius_km", 1.5)
    for k, a in enumerate(anchors):
        x, y = (float(v) for v in m.xy(a["lat"], a["lon"]))
        near = min(centers, key=lambda c: math.hypot(c.x - x, c.y - y), default=None)
        if near is not None and math.hypot(near.x - x, near.y - y) <= MERGE_KM:
            c = near
        else:
            inside = (m.x - x) ** 2 + (m.y - y) ** 2 <= r_act ** 2
            pop, jobs = float(m.pop[inside].sum()), float(m.jobs[inside].sum()) if m.jobs_ok else 0.0
            c = Center(f"A{k + 1:02d}", x, y, a["lat"], a["lon"], pop + jobs + float(a.get("weight", 0)), pop, jobs,
                       0.0, 0.0, "major", [])
            c.near_jobs = jobs
            centers.append(c)
        c.anchor = a.get("kind", "hub")
        c.anchor_name = a["name"]
        if c.anchor == "downtown":
            for o in centers:
                if o is not c and o.kind == "downtown" and math.hypot(o.x - c.x, o.y - c.y) <= p["downtown_sep_km"]:
                    o.kind = "major"
            c.kind = "downtown"
        out.append(c)
    if log:
        log(f"  anchors: {', '.join(f'{c.anchor_name} ({c.anchor})' for c in out)}")
    return out
