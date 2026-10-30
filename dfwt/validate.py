"""Network checks. Each finding is (severity, code, line, message).

error   - the data is inconsistent; outputs can't be trusted
warn    - a planning defect worth fixing (broken connections, hairpins, ...)
info    - a standards note (stop spacing outside the band for the mode)
"""
import collections

from . import geo
from .graph import YearGraph


def run(net):
    cfg = net.cfg
    std = cfg["standards"]
    out = []
    add = lambda sev, code, line, msg: out.append((sev, code, line, msg))

    names = collections.Counter(ln.name for ln in net.lines.values())
    for n, c in names.items():
        if c > 1:
            add("error", "DUP_NAME", n, f"{c} lines share the name '{n}' (the map toggles them together)")

    for ln in net.lines.values():
        if ln.mode not in cfg["modes"]:
            add("error", "MODE", ln.name, f"unknown mode {ln.mode}")
        if len(ln.segments) != len(ln.stop_ids) - 1:
            add("error", "SEGCOUNT", ln.name, f"{len(ln.stop_ids)} stops but {len(ln.segments)} segments")
            continue
        for sid in ln.stop_ids:
            if sid not in net.stations:
                add("error", "STATION", ln.name, f"unknown station {sid}")
        # geometry endpoints sit on their stations
        for i, s in enumerate(ln.segments):
            a, b = net.stations[ln.stop_ids[i]], net.stations[ln.stop_ids[i + 1]]
            for st, p in ((a, s.pts[0]), (b, s.pts[-1])):
                d = geo.hav_km(st.lat, st.lon, p[1], p[0])
                if d > 0.3:
                    add("warn", "GEOM_GAP", ln.name, f"segment {i + 1} ends {d * 1000:.0f} m from {st.name}")
        # contiguity: in every year the line's open track must be one piece
        for y in cfg["years"]:
            open_ = [s.year <= y for s in net.line_at(ln.id, y).segments]   # the routing in force that year
            pieces = sum(1 for i, o in enumerate(open_) if o and (i == 0 or not open_[i - 1]))
            if pieces > 1:
                add("warn", "SPLIT", ln.name, f"opens in {pieces} disconnected pieces in {y}")
                break
        # hairpins (an express bus in a freeway leaves it to reach a station and comes back)
        for i in range(1 if any(s.grade != "freeway" for s in ln.segments) else len(ln.segments), len(ln.segments)):
            p, q = ln.segments[i - 1].pts, ln.segments[i].pts
            if len(p) < 2 or len(q) < 2:
                continue
            t = geo.turn_deg(geo.bearing_deg(p[-2], p[-1]), geo.bearing_deg(q[0], q[1]))
            if t > 180 - std["hairpin_deg"] and min(ln.segments[i - 1].km, ln.segments[i].km) > 0.25:
                st = net.stations[ln.stop_ids[i]]
                add("warn", "HAIRPIN", ln.name, f"reverses direction ({t:.0f} deg) at {st.name}")
        # stop spacing vs the mode's band (skip shared run-through of unopened stops)
        lo, hi = std["spacing_km"][ln.mode]
        for i, s in enumerate(ln.segments):
            if s.km < lo or s.km > hi:
                a, b = net.stations[ln.stop_ids[i]].name, net.stations[ln.stop_ids[i + 1]].name
                kind = "short" if s.km < lo else "long"
                add("info", "SPACING", ln.name, f"{kind} {s.km:.1f} km gap {a} -> {b} (band {lo}-{hi})")

    # termini that connect to nothing (in the final year)
    final = max(cfg["years"])
    by_station = net.station_lines()
    st = net.stations
    r = std["orphan_terminus_m"] / 1000
    for ln in net.lines.values():
        if ln.status == "existing":
            continue
        for sid in {ln.stop_ids[0], ln.stop_ids[-1]}:
            if len(by_station[sid]) > 1:
                continue
            s = st[sid]
            near = [o for o in st.values() if o.id != sid and abs(o.lat - s.lat) < 0.01
                    and geo.hav_km(s.lat, s.lon, o.lat, o.lon) <= r and by_station.get(o.id)]
            if not near and ln.mode != "commuter":   # an outer end serving a neighbourhood is normal: a note
                add("info", "DANGLING", ln.name, f"terminus {s.name} has no transfer within {std['orphan_terminus_m']} m")

    # explicit transfer links must point at real stations
    linked = set()
    for a, b, _, _ in net.transfers:
        for x in (a, b):
            if x not in st:
                add("error", "TRANSFER", "", f"transfer references unknown station {x}")
        linked.add(frozenset((a, b)))

    # near-miss transfers: two lines' stops 400-1200 m apart with no walk link
    tr = net.cfg["transfer"]["walk_radius_m"] / 1000
    ids = list(by_station)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = st[a], st[b]
            if abs(A.lat - B.lat) > 0.012:
                continue
            if set(by_station[a]) & set(by_station[b]) or frozenset((a, b)) in linked:
                continue
            d = geo.hav_km(A.lat, A.lon, B.lat, B.lon)
            if tr < d <= 1.2 and A.name.split(" ")[0] == B.name.split(" ")[0]:
                add("info", "NEAR_MISS", "", f"{A.name} and {B.name} are {d * 1000:.0f} m apart with no transfer link")

    # co-located platforms: two station ids of the same mode a few metres apart (two platforms
    # paid for, and two of a zone's access slots) should be one station
    co_m = std.get("co_located_m", 60) / 1000
    by_mode = collections.defaultdict(set)
    for ln in net.lines.values():
        for sid in ln.stop_ids:
            by_mode[sid].add(ln.mode)
    ids = sorted(by_mode)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = st[a], st[b]
            if abs(A.lat - B.lat) > 0.001 or not (by_mode[a] & by_mode[b]):
                continue
            d = geo.hav_km(A.lat, A.lon, B.lat, B.lon)
            if d <= co_m:
                add("warn", "CO_LOCATED", "", f"{A.name} ({a}) and {B.name} ({b}) are {d * 1000:.0f} m apart, "
                    f"both {'/'.join(sorted(by_mode[a] & by_mode[b]))}: merge them into one station")

    # every year's network should be one connected system
    for y, comps in _components(net):
        for sids, lines in comps[1:]:
            add("warn", "ISLAND", ", ".join(lines), f"{y}: {len(sids)} stations ({', '.join(lines)}) cannot reach the main network")
    out.extend(_curves(net))
    out.extend(_staging(net))
    return out


def _curves(net):
    """Distinct tight curves (radius below the mode minimum, measured on a 20 m
    resampling so vertex noise doesn't count) on proposed lines."""
    from . import align
    out = []
    g = net.cfg.get("geometry")
    if not g:
        return out
    for ln in net.lines.values():
        if ln.status == "existing":
            continue
        rmin = g["check_radius_m"][ln.mode]
        pts = []
        for s in ln.segments:
            pts += s.pts if not pts else s.pts[1:]
        R = align.chord_radii(pts)
        tight = R < rmin * 0.9
        n = int((tight[1:] & ~tight[:-1]).sum() + (1 if len(tight) and tight[0] else 0))
        if n:
            out.append(("warn", "CURVE_RADIUS", ln.name, f"{n} curves tighter than {rmin} m "
                        f"(tightest {float(R.min()):.0f} m)"))
    return out


def _staging(net):
    from . import staging
    return staging.check(net)


def summarize(findings):
    c = collections.Counter((f[0], f[1]) for f in findings)
    return ", ".join(f"{sev}:{code}={n}" for (sev, code), n in sorted(c.items()))


def _components(net):
    """[(year, [(station_ids, line names), ...])] connected pieces per year, largest
    first (union-find over runs and walk links)."""
    out = []
    for y in net.cfg["years"]:
        g = YearGraph(net, y)
        parent = list(range(g.n_st))

        def find(v):
            while parent[v] != v:
                parent[v] = parent[parent[v]]
                v = parent[v]
            return v
        for r in g.runs:
            idx = [g.sidx[s] for s in r.stops]
            for a, b in zip(idx, idx[1:]):
                parent[find(a)] = find(b)
        for i in range(g.n_st):
            for j, _, kind in g.adj[i]:
                if kind == "walk":
                    parent[find(i)] = find(j)
        groups = {}
        for i in range(g.n_st):
            groups.setdefault(find(i), set()).add(g.station_ids[i])
        comps = sorted(groups.values(), key=len, reverse=True)
        out.append((y, [(c, sorted({r.line.name for r in g.runs if c & set(r.stops)})) for c in comps]))
    return out


def islands(net):
    """line_id -> the last year any of its stations sits in a piece cut off from the main network."""
    name_to_id = {ln.name: ln.id for ln in net.lines.values()}
    out = {}
    for y, comps in _components(net):
        for _, lines in comps[1:]:
            for n in lines:
                lid = name_to_id.get(n)
                if lid:
                    out[lid] = max(out.get(lid, 0), y)
    return out
