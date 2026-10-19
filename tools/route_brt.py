"""Put BRT on the street: route every BRT line along real arterials.

    python tools/route_brt.py [--scenario two_million] [--lines E04,XB20] [--write]

BRT runs in the street, so it should follow the road network more closely than any
other mode. Each BRT line is routed through its stops, in order, on the Overture road
network (dfwt/osmroute.py: turn-limited, no U-turns), preferring primary and
secondary arterials over tertiary streets and freeways. Stops served only by BRT
move onto the street they serve (up to `MOVE_M`); stops shared with rail stay put
and the bus pulls up to them. The route is then cut back into station-to-station
segments (geometry_source "osm_road").

Writes the plan's network/line_segments.csv and stations.csv, or, with --scenario,
that scenario's own segment and station tables (*.patch.csv / *.add.csv /
full tables, whichever holds each line). Needs data/osm/roads.parquet
(python tools/fetch_osm.py) and pyarrow.
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config, geo, osmroute  # noqa: E402
from dfwt.network import Network  # noqa: E402
from gen_expansion import _cut_loops, street_hint  # noqa: E402

CLASSES = {"primary", "secondary", "tertiary", "trunk", "motorway"}
W_CLS = {"primary": 1.0, "secondary": 1.0, "trunk": 1.15, "tertiary": 1.35, "motorway": 1.6}
MAX_TURN = 100      # a bus turns 90 degrees at an intersection; no U-turns
TURN_PEN = 700.0    # metres-equivalent per (turn/90)^2: prefer staying on one street
SNAP_M = 700
MOVE_M = 400
# streets the plan's BRT lines are named for, where the name doesn't say "Road", "Lane"...
HINTS = {"SH-121 BRT": r"\b121\b|Sam Rayburn", "Jacksboro BRT": "Jacksboro", "Beltline Line": r"Belt ?Line"}


def cut(P, stops):
    """Split polyline P (xy) at the points nearest each stop, in order. Returns
    (segments, snapped stop points, snap distances)."""
    cum = [0.0]
    for a, b in zip(P, P[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    cuts, lo = [], 0
    for s in stops:
        best = None
        for i in range(lo, len(P) - 1):
            a, b = P[i], P[i + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-9
            t = max(0.0, min(1.0, ((s[0] - a[0]) * dx + (s[1] - a[1]) * dy) / L2))
            q = (a[0] + t * dx, a[1] + t * dy)
            d = math.dist(q, s)
            if best is None or d < best[0] - 1e-6:
                best = (d, i, t, q)
        d, i, t, q = best
        cuts.append((i, t, q, d))
        lo = i
    segs = []
    for (i0, t0, q0, _), (i1, t1, q1, _) in zip(cuts, cuts[1:]):
        pts = [q0] + P[i0 + 1:i1 + 1] + [q1]
        clean = [pts[0]]
        for p in pts[1:]:
            if math.dist(p, clean[-1]) > 0.5:
                clean.append(p)
        if len(clean) < 2:
            clean = [q0, q1]
        segs.append(clean)
    return segs, [c[2] for c in cuts], [c[3] for c in cuts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario")
    ap.add_argument("--lines")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    net = Network.load(args.scenario)
    only = set(args.lines.split(",")) if args.lines else None
    serving = {}
    for ln in net.lines.values():
        for s in ln.stop_ids:
            serving.setdefault(s, set()).add(ln.mode)
    G = osmroute.Graph("road", classes=CLASSES)
    new_geom, moved, failed = {}, {}, []
    for ln in sorted(net.lines.values(), key=lambda l: l.id):
        if ln.mode != "brt" or (only and ln.id not in only):
            continue
        stops = [osmroute.xy(net.stations[s].lon, net.stations[s].lat) for s in ln.stop_ids]
        hint = HINTS.get(ln.name) or street_hint(ln.name)
        P, why = osmroute.route(G, stops, max_turn=MAX_TURN, snap_r=SNAP_M, w_cls=W_CLS, turn_pen=TURN_PEN,
                                detour=2.5, snap_w=3.0, prefer=hint)   # the plan's stops are real places
        if P is not None:
            P = _cut_loops(P)
        if P is None:
            failed.append((ln.id, ln.name, why))
            continue
        segs, snapped, dist = cut(P, stops)
        direct = sum(math.dist(a, b) for a, b in zip(stops, stops[1:]))
        routed = sum(sum(math.dist(a, b) for a, b in zip(s, s[1:])) for s in segs)
        for k, (sid, q, d) in enumerate(zip(ln.stop_ids, snapped, dist)):
            if serving[sid] == {"brt"} and 15 < d <= MOVE_M:
                moved[sid] = osmroute.ll(q)
            elif d > 250:  # a station well off the street (a rail station): the bus pulls in to serve it
                if k > 0:
                    segs[k - 1].append(stops[k])
                if k < len(segs):
                    segs[k].insert(0, stops[k])
        new_geom[ln.id] = [[osmroute.ll(p) for p in s] for s in segs]
        print(f"{ln.id:6s} {ln.name:38s} {len(ln.stop_ids):3d} stops  {direct / 1000:5.1f} km straight -> "
              f"{routed / 1000:5.1f} km on streets", flush=True)
    for lid, name, why in failed:
        print(f"FAILED {lid} {name}: {why}")
    print(f"{len(new_geom)} BRT lines routed on streets, {len(moved)} bus-only stops moved onto them, "
          f"{len(failed)} kept as drawn")
    if not args.write:
        print("dry run; add --write to save")
        return
    write(args.scenario, new_geom, moved)


def _rewrite(path, fn):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else None
    changed = sum(fn(r) for r in rows)
    if changed:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    return changed


def write(scenario, new_geom, moved):
    folders = [config.path("scenarios", scenario)] if scenario else [config.path("network")]
    seg_files, st_files = [], []
    for folder in folders:
        for n in ("line_segments.csv", "line_segments.patch.csv", "line_segments.add.csv"):
            if os.path.exists(os.path.join(folder, n)):
                seg_files.append(os.path.join(folder, n))
        for n in ("stations.csv", "stations.add.csv"):
            if os.path.exists(os.path.join(folder, n)):
                st_files.append(os.path.join(folder, n))

    def seg(r):
        g = new_geom.get(r["line_id"])
        if not g:
            return False
        k = int(r["seq"]) - 1
        if k >= len(g):
            return False
        r["geometry_wkt"] = geo.to_wkt(g[k])
        r["geometry_source"] = "osm_road"
        return True

    def st(r):
        p = moved.get(r["station_id"])
        if not p:
            return False
        r["lon"], r["lat"] = f"{p[0]:.6f}", f"{p[1]:.6f}"
        return True

    for p in seg_files:
        print(f"{p}: {_rewrite(p, seg)} segments")
    for p in st_files:
        print(f"{p}: {_rewrite(p, st)} stations")


if __name__ == "__main__":
    main()
