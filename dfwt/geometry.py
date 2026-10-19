"""Make every alignment buildable: `python -m dfwt align [--lines F02,E10] [--write]`.

Per line, by mode:
  commuter rail  routed on real track (Overture/OSM rail graph, turn-limited), so
                 it follows the railroad it claims to use; stations snap onto the
                 track.
  metro          fitted with tangents, spirals and arcs (dfwt/align.py) to the
                 drawn corridor, after sliding stations that sit on a bend to the
                 straightest spot within reach so platforms are on tangent track.
  BRT, existing  de-noised only (out-and-back spikes and vertex jitter removed);
                 they already follow real streets or track.

Station moves up to config.geometry.station_move_auto_m are applied; larger
ones are listed for review and the line keeps its old geometry. Stations in the
downtown cores (config.cores) are not moved automatically. Segments marked
locked=1 in line_segments.csv are never touched. Track shared by several lines
gets the geometry of the line that opens it first. Without --write nothing in
network/ changes; reports/GEOMETRY.md is written either way.
"""
import collections
import csv
import math
import multiprocessing as mp
import os

import numpy as np

from . import align, config, geo
from .network import Network


def _xy(p):
    return align.to_xy(*p)


def _cut(xy, s0, s1):
    """Sub-polyline of xy (projected) between arc lengths s0 and s1."""
    s = align.cumlen(xy)
    out = [np.array([np.interp(s0, s, xy[:, 0]), np.interp(s0, s, xy[:, 1])])]
    out += [p for p, si in zip(xy, s) if s0 < si < s1]
    out.append(np.array([np.interp(s1, s, xy[:, 0]), np.interp(s1, s, xy[:, 1])]))
    return np.array(out)


def _project(xy, p, after=0.0):
    """(arc length, distance) of the closest point of xy to p, at or after `after`."""
    A, B = xy[:-1], xy[1:]
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    t = np.clip(((p - A) * AB).sum(1) / L2, 0, 1)
    q = A + t[:, None] * AB
    d = np.hypot(*(q - p).T)
    s = align.cumlen(xy)[:-1] + t * np.sqrt(L2)
    d = np.where(s >= after - 1e-6, d, np.inf)
    i = int(np.argmin(d))
    return float(s[i]), float(d[i])


def _in_core(cfg, st):
    for c in cfg["cores"].values():
        if isinstance(c, dict) and geo.hav_km(st.lat, st.lon, c["lat"], c["lon"]) <= c["radius_km"]:
            return True
    return False


def straighten(net, ln, pos, fixed, max_move, log_moves):
    """A real line runs straight along its corridor and the stations come to it.
    Stations that force a detour (a turn of 35+ degrees) move onto the straight
    path between their neighbors when that's within max_move m; between stations,
    a drawn path that wanders (8%+ longer than direct, or far off it) is replaced
    by the direct path. Returns (corridor points lon/lat, station index per point,
    new station positions)."""
    ids = ln.stop_ids
    P = {k: np.array(_xy(pos[s])) for k, s in enumerate(ids)}
    for _ in range(2):
        for k in range(1, len(ids) - 1):
            if fixed(ids[k]):
                continue
            a, b, c = P[k - 1], P[k], P[k + 1]
            ac = c - a
            L2 = float(ac @ ac)
            if L2 < 1:
                continue
            t = min(1.0, max(0.0, float((b - a) @ ac) / L2))
            q = a + t * ac
            off = float(np.hypot(*(b - q)))
            h1, h2 = math.atan2(*(b - a)[::-1]), math.atan2(*(c - b)[::-1])
            turn = abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi))
            if turn >= 35 and 1 < off <= max_move:
                P[k] = q
    moved = {}
    for k, sid in enumerate(ids):
        d = float(np.hypot(*(P[k] - np.array(_xy(pos[sid])))))
        if d > 1:
            moved[sid] = (*align.to_ll(*P[k]), d)
        elif not fixed(sid):
            # still a big detour that couldn't be fixed automatically
            pass
    for k in range(1, len(ids) - 1):
        if ids[k] in moved:
            continue
        a, b, c = P[k - 1], P[k], P[k + 1]
        h1, h2 = math.atan2(*(b - a)[::-1]), math.atan2(*(c - b)[::-1])
        turn = abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi))
        if turn >= 60:
            why = "interchange or fixed stop" if fixed(ids[k]) else f"more than {max_move:.0f} m off the direct path"
            log_moves.append((ln.name, net.stations[ids[k]].name, turn, why))
    pts, ends = [], [0]
    for i, seg in enumerate(ln.segments):
        a, b = P[i], P[i + 1]
        chord = float(np.hypot(*(b - a)))
        xy = np.array([_xy(p) for p in seg.pts])
        length = float(align.cumlen(xy)[-1])
        dev = float(align.pt_to_poly(xy, np.array([a, b])).max()) if len(xy) > 2 else 0.0
        wander = length > 1.08 * chord + 30 or dev > max(200.0, 0.2 * chord)
        if ids[i] in moved or ids[i + 1] in moved or wander:
            sub = [align.to_ll(*a), align.to_ll(*b)]
        else:  # keep the drawn route but drop wiggles smaller than ~150 m
            xy[0], xy[-1] = a, b
            keep = {0, len(xy) - 1}
            align.dp(xy, 150.0, 0, len(xy) - 1, keep)
            sub = [align.to_ll(*xy[j]) for j in sorted(keep)]
        pts += sub if not pts else sub[1:]
        ends.append(len(pts) - 1)
    return pts, ends, moved


def _fit_job(args):
    lid, pts, ends, grades, stations, m = args
    segs, rep = align.fit_line(pts, ends, grades, stations, m)
    return lid, segs, rep


def run(lines=None, write=False, procs=2, log=print):
    cfg = config.load()
    gcfg = cfg["geometry"]
    auto = gcfg["station_move_auto_m"]
    tables, _ = Network.read_tables()
    net = Network.load()
    seg_rows = {(r["line_id"], int(r["seq"])): r for r in tables["line_segments.csv"]}
    locked = {k for k, r in seg_rows.items() if r.get("locked") == "1"}
    st_lines = net.station_lines()
    pos = {sid: (s.lon, s.lat) for sid, s in net.stations.items()}
    moves, review, reports, new_geom, source = {}, [], {}, {}, {}
    want = set(lines.split(",")) if lines else set(net.lines)

    def lines_of_mode(mode, status=None):
        return [l for l in net.lines.values() if l.id in want and l.mode == mode and (status is None or l.status == status)
                and not any((l.id, i + 1) in locked for i in range(len(l.segments)))]

    # 1. commuter rail on real track
    rail = lines_of_mode("commuter")
    if rail:
        from . import osmroute
        G = osmroute.Graph("rail")
        for ln in rail:
            S = np.array([_xy(pos[s]) for s in ln.stop_ids])
            P, why = osmroute.route(G, [tuple(p) for p in S], max_turn=gcfg["rail_max_turn_deg"])
            if P is None:
                review.append((ln.name, f"kept drawn geometry: {why}"))
                continue
            xy = np.array(P)
            arcs, far, after = [], [], 0.0
            for k, p in enumerate(S):
                s, d = _project(xy, p, after)
                arcs.append(s)
                after = s
                if d > auto:
                    far.append((net.stations[ln.stop_ids[k]].name, d))
            if far:
                review.append((ln.name, "kept drawn geometry; stations too far from the track to move automatically: "
                               + ", ".join(f"{n} {d:.0f} m" for n, d in far)))
                continue
            for k, sid in enumerate(ln.stop_ids):
                q = _cut(xy, arcs[k], arcs[k])[0]
                d = float(np.hypot(*(q - S[k])))
                if d > 1:
                    moves[sid] = (*align.to_ll(*q), d, ln.name)
            for i in range(len(ln.segments)):
                seg = _cut(xy, arcs[i], arcs[i + 1])
                new_geom[(ln.id, i + 1)] = [align.to_ll(*p) for p in align._thin(seg)]
                source[(ln.id, i + 1)] = "osm_rail"
            reports[ln.id] = dict(kind="routed on rail", km_before=ln.km, km_after=(arcs[-1] - arcs[0]) / 1000)
            log(f"  {ln.name}: routed on track, {reports[ln.id]['km_after']:.1f} km (was {ln.km:.1f})")

    # 2. BRT and existing metro: de-noise
    for ln in lines_of_mode("brt") + lines_of_mode("metro", "existing"):
        before = after = 0
        for i, s in enumerate(ln.segments):
            pts = align.denoise(s.pts)
            pts[0], pts[-1] = pos[ln.stop_ids[i]], pos[ln.stop_ids[i + 1]]
            before += len(s.pts)
            after += len(pts)
            new_geom[(ln.id, i + 1)] = pts
            source.setdefault((ln.id, i + 1), "denoised")
        reports[ln.id] = dict(kind="de-noised", vertices_before=before, vertices_after=after)

    # 3. proposed metro: straighten detours, slide stations off bends, then fit tangents/spirals/arcs
    metro = lines_of_mode("metro", "proposed")
    near_other = collections.defaultdict(set)
    for a, b, _, _ in net.transfers:
        near_other[a].add(b)
        near_other[b].add(a)
    detours = []

    def fixed(sid):
        st = net.stations[sid]
        return (len(st_lines[sid]) > 1 or near_other[sid] or _in_core(cfg, st) or sid in moves
                or any(net.lines[l].status == "existing" for l in st_lines[sid]))
    jobs = []
    for ln in metro:
        m = align.params(cfg, ln.mode)
        if ln.stop_ids[0] == ln.stop_ids[-1]:
            continue
        pts, ends, moved = straighten(net, ln, pos, lambda s: fixed(s) or s in (ln.stop_ids[0], ln.stop_ids[-1]),
                                      gcfg["straighten_move_max_m"], detours)
        for sid, (lon, lat, d) in moved.items():
            moves[sid] = (lon, lat, d, ln.name + " (straightened)")
            pos[sid] = (lon, lat)
        movable = [not _in_core(cfg, net.stations[sid]) and (sid not in moves or sid in moved)
                   and all(net.lines[l].mode == "metro" and net.lines[l].status == "proposed" for l in st_lines[sid])
                   for sid in ln.stop_ids]
        for k, (lon, lat, d) in align.station_slides(pts, ends, m, auto, movable).items():
            sid = ln.stop_ids[k]
            if sid not in moves:
                moves[sid] = (lon, lat, d, ln.name)
        stations = [moves[s][:2] if s in moves else pos[s] for s in ln.stop_ids]
        # rebuild the corridor with moved stations inserted on it
        xy = np.array([_xy(p) for p in pts])
        arcs, after = [], 0.0
        for p in stations:
            s, _ = _project(xy, np.array(_xy(p)), after)
            arcs.append(s)
            after = s
        cpts, cends = [], [0]
        for k in range(len(arcs) - 1):
            seg = _cut(xy, arcs[k], arcs[k + 1])
            cpts += [align.to_ll(*p) for p in (seg if not cpts else seg[1:])]
            cends.append(len(cpts) - 1)
        jobs.append((ln.id, cpts, cends, [s.grade for s in ln.segments], stations, m))
    if jobs:
        log(f"  fitting {len(jobs)} metro lines ({procs} processes)...")
        with mp.get_context("fork").Pool(procs) as pool:
            for lid, segs, rep in pool.imap_unordered(_fit_job, jobs):
                ln = net.lines[lid]
                if rep.get("failed"):
                    review.append((ln.name, "kept drawn geometry: the curve fit failed (the drawn line probably "
                                   "doubles back on itself); redraw that stretch"))
                    for i, pts in enumerate(segs):  # drawn line, re-ended at any moved stations
                        new_geom[(lid, i + 1)] = pts
                    continue
                for i, pts in enumerate(segs):
                    new_geom[(lid, i + 1)] = pts
                    source[(lid, i + 1)] = "fitted"
                rep["kind"] = "fitted"
                rep["flag_stations"] = sorted({net.stations[ln.stop_ids[k]].name for k in rep.pop("flag_where")})
                reports[lid] = rep
                log(f"  {ln.name}: min radius {rep['min_radius_m']:.0f} m, {rep['curves_below_min']} curves below "
                    f"minimum, max deviation {rep['max_deviation_m']:.0f} m"
                    + (f"; flagged at {', '.join(rep['flag_stations'])}" if rep["flag_stations"] else ""))

    for name, stn, turn, why in detours:
        review.append((name, f"still turns {turn:.0f} degrees at {stn} ({why}); move or drop the stop, or accept the curve"))

    # 4. shared track: every line on a station pair uses the first-opening line's geometry
    owner = net.track_owner()
    by_pair = {}
    for ln in net.lines.values():
        for i in range(len(ln.segments)):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if owner[key][1] == ln.id and (ln.id, i + 1) in new_geom:
                by_pair[key] = (ln.stop_ids[i], new_geom[(ln.id, i + 1)])
    for ln in net.lines.values():
        for i in range(len(ln.segments)):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if key in by_pair and owner[key][1] != ln.id and (ln.id, i + 1) not in locked:
                a, pts = by_pair[key]
                new_geom[(ln.id, i + 1)] = pts if a == ln.stop_ids[i] else pts[::-1]
                source[(ln.id, i + 1)] = source.get((ln.id, i + 1), "shared")

    # 5. stations that moved: every segment touching them ends at the new spot
    for (lid, seq), r in seg_rows.items():
        ln = net.lines[lid]
        a, b = ln.stop_ids[seq - 1], ln.stop_ids[seq]
        if (a in moves or b in moves) and (lid, seq) not in new_geom and (lid, seq) not in locked:
            pts = list(ln.segments[seq - 1].pts)
            if a in moves:
                pts[0] = moves[a][:2]
            if b in moves:
                pts[-1] = moves[b][:2]
            new_geom[(lid, seq)] = pts
    write_report(net, moves, review, reports, cfg)
    if write:
        for key, pts in new_geom.items():
            r = seg_rows[key]
            r["geometry_wkt"] = geo.to_wkt(pts)
            if key in source:
                r["geometry_source"] = source[key]
        for r in tables["stations.csv"]:
            if r["station_id"] in moves:
                lon, lat = moves[r["station_id"]][:2]
                r["lon"], r["lat"] = f"{lon:.6f}", f"{lat:.6f}"
        fields = ["line_id", "seq", "year_opens", "grade", "geometry_source", "locked", "geometry_wkt"]
        for r in tables["line_segments.csv"]:
            r.setdefault("geometry_source", r.get("geometry_source") or "drawn")
            r.setdefault("locked", "")
        _write(config.path("network", "line_segments.csv"), fields, tables["line_segments.csv"])
        _write(config.path("network", "stations.csv"), ["station_id", "name", "lat", "lon"], tables["stations.csv"])
        log(f"wrote {len(new_geom)} segments and {len(moves)} station moves to network/")
    return reports, moves, review


def _write(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_report(net, moves, review, reports, cfg):
    L = ["# Geometry", "", "Generated by `python -m dfwt align`. Design limits are in `config.json` "
         "under `geometry`; method in `dfwt/geometry.py` and `dfwt/align.py`.", ""]
    fitted = {k: v for k, v in reports.items() if v["kind"] == "fitted"}
    if fitted:
        L += ["## Metro alignments (tangent, spiral and arc fit)", "",
              "| Line | Min radius (m) | Curves below minimum | Max deviation (m) | Length change | Flagged near |",
              "|---|---|---|---|---|---|"]
        for lid, r in sorted(fitted.items(), key=lambda kv: net.lines[kv[0]].name):
            L.append(f"| {net.lines[lid].name} | {r['min_radius_m']:.0f} | {r['curves_below_min']} | "
                     f"{r['max_deviation_m']:.0f} | {r['length_change_pct']:+.1f}% | {', '.join(r['flag_stations']) or '-'} |")
        L.append("")
    routed = {k: v for k, v in reports.items() if v["kind"] == "routed on rail"}
    if routed:
        L += ["## Commuter rail routed on real track", "", "| Line | km before | km after |", "|---|---|---|"]
        for lid, r in sorted(routed.items(), key=lambda kv: net.lines[kv[0]].name):
            L.append(f"| {net.lines[lid].name} | {r['km_before']:.1f} | {r['km_after']:.1f} |")
        L.append("")
    if moves:
        L += [f"## Station moves (up to {cfg['geometry']['station_move_auto_m']} m, applied)", "",
              "| Station | Moved (m) | Because of |", "|---|---|---|"]
        for sid, (lon, lat, d, why) in sorted(moves.items(), key=lambda kv: -kv[1][2]):  # noqa: B007
            L.append(f"| {net.stations[sid].name} | {d:.0f} | {why} |")
        L.append("")
    if review:
        L += ["## Needs review", ""] + [f"- **{n}**: {msg}" for n, msg in review] + [""]
    with open(config.path("reports", "GEOMETRY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
