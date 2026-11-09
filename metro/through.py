"""Through-running and winding (Phase 3 of texas-transit's study/hsr_buildout.md).

Two lines of a mode that both end downtown from opposite sides are better run as one line through
it: riders crossing downtown get a one-seat ride and the terminal tracks downtown aren't needed.
The greedy selection picks such stubs one at a time (each scores well alone) and then rejects the
through line as their duplicate, so the hand-drawn plans run more lines through downtown than the
generator does (DFW: 53% of hand-drawn metro lines against 15% generated). pair() joins chosen
stubs into through lines after the sketch selection, before the full model prunes the pool.
"""
import math

from . import geom


def _oriented(c, profile, end):
    """c's route for `profile` oriented to finish at center `end` (one of its ends), and its centers
    in that order; None if it doesn't end there."""
    P = c.routes.get(profile) if c.routes else None
    if not P:
        return None, None
    if c.seq[-1] == end:
        return P, list(c.seq)
    if c.seq[0] == end:
        return P[::-1], list(c.seq)[::-1]
    return None, None


def angle_at(by, d, a_next, b_next):
    """Angle (degrees) at center d between the directions to a_next and to b_next."""
    ax, ay = by[a_next].x - by[d].x, by[a_next].y - by[d].y
    bx, by_ = by[b_next].x - by[d].x, by[b_next].y - by[d].y
    na, nb = math.hypot(ax, ay), math.hypot(bx, by_)
    if not na or not nb:
        return 0.0
    cos = max(-1.0, min(1.0, (ax * bx + ay * by_) / (na * nb)))
    return math.degrees(math.acos(cos))


def pair(chosen, by, downtown_ids, make, min_angle=135.0, log=print):
    """Join chosen road lines that end at the same downtown from opposite sides (the angle between
    them at downtown >= min_angle) into through lines, best-aligned pairs first. `make(seq, routes)`
    builds and decides a candidate (a Cand with mode and status set). A pair is joined only if the
    through line gets the stubs' mode and passes the generator's tests. Returns (lines, joined
    [(through, a, b)])."""
    out = list(chosen)
    joined = []
    for d in downtown_ids:
        stubs = [c for c in out if c.kind == "road" and c.mode and d in (c.seq[0], c.seq[-1])]
        pairs = []
        for i, a in enumerate(stubs):
            for b in stubs[i + 1:]:
                if a.mode != b.mode:
                    continue
                _, sa = _oriented(a, a.mode if a.mode in a.routes else "brt", d)
                _, sb = _oriented(b, b.mode if b.mode in b.routes else "brt", d)
                if not sa or not sb or len(sa) < 2 or len(sb) < 2:
                    continue
                ang = angle_at(by, d, sa[-2], sb[-2])
                if ang >= min_angle:
                    pairs.append((ang, a, b))
        used = set()
        for ang, a, b in sorted(pairs, key=lambda x: -x[0]):
            if a.uid in used or b.uid in used:
                continue
            routes, seq = {}, None
            for prof in ("metro", "brt"):
                Pa, sa = _oriented(a, prof, d)
                Pb, sb = _oriented(b, prof, d)
                if Pa and Pb:
                    routes[prof] = geom.join(Pa, Pb[::-1])
                    seq = sa + sb[::-1][1:]
            if not routes or len(set(seq)) != len(seq):
                continue
            t = make(tuple(seq), routes)
            if t is None or t.mode != a.mode or t.status != "pool":
                continue
            used |= {a.uid, b.uid}
            t.status, t.order = "chosen", min(a.order or 9999, b.order or 9999)
            t.reason = f"through line joining {a.uid} and {b.uid} across downtown ({ang:.0f} degrees)"
            for s in (a, b):
                s.status, s.reason = "replaced", f"joined into through line {t.uid}"
                out.remove(s)
            out.append(t)
            joined.append((t, a, b))
            if log:
                log(f"  through line {t.uid}: {a.uid} + {b.uid} across {by[d].name} ({t.mode}, {t.km:.0f} km)")
    return out, joined


def max_winding(P, window_km=3.0, step_km=0.25):
    """The largest route length / straight distance over any window of `window_km` along P (1 for a
    straight line); a staircase route scores high where an end-to-end check sees nothing."""
    S = geom.resample(P, step_km)
    n = max(1, int(round(window_km / step_km)))
    worst = 1.0
    for i in range(0, max(1, len(S) - n)):
        j = min(len(S) - 1, i + n)
        chord = math.dist(S[i], S[j])
        if chord > 0.2:
            worst = max(worst, (j - i) * step_km / chord)
    return worst


def metrics(chosen, by, downtown_ids, anchor_centers, station_m=600):
    """Rider-sense checks on a chosen network (texas-transit study/hsr_buildout.md, Phase 3 acceptance):
    the share of metro lines running through a downtown (a downtown center inside the line, not at an
    end), the median share of a BRT line within 400 m of another line, the anchors with a station
    within station_m, the least straight line (chord over length) and the worst winding."""
    lines = [c for c in chosen if c.mode]
    metro = [c for c in lines if c.mode == "metro"]
    through = sum(1 for c in metro if any(d in c.seq[1:-1] for d in downtown_ids))
    brt = [c for c in lines if c.mode == "brt"]
    overlaps = sorted(geom.share_near(c.P, [o.P for o in lines if o is not c], 0.4) for c in brt) if len(lines) > 1 else []
    served = []
    for a in anchor_centers:
        ok = any(math.dist((a.x, a.y), s) <= station_m / 1000 for c in lines for s in c.station_xy)
        served.append((a, ok))
    straight = [math.dist(c.P[0], c.P[-1]) / max(geom.length(c.P), 0.1) for c in lines if c.P]
    return {"metro": len(metro), "metro_through": through, "brt": len(brt),
            "brt_overlap_median": overlaps[len(overlaps) // 2] if overlaps else 0.0,
            "anchors": [(a.anchor_name, a.anchor, ok) for a, ok in served],
            "min_straightness": min(straight) if straight else 1.0,
            "max_winding": max((max_winding(c.P) for c in lines if c.P), default=1.0)}
