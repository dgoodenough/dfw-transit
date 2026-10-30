"""Put off-street bus stops on the street. Where a BRT or streetcar line leaves its street, runs
out to a stop and comes back the same way (a HAIRPIN warning), the stop moves onto the line at
the point where the detour starts, and both legs are trimmed there. Only stops that no train
serves move (a bus pulling into a rail station is normal), and only up to MAX_MOVE_M. Other
lines ending at a moved stop are re-pointed to it. A train reversing is real and left alone.

    python tools/despur.py network         # rewrites network/stations.csv and line_segments.csv

make_two_million.py applies the same step to the 2 million riders tables."""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import geo  # noqa: E402

NEAR_M = 30          # two legs within this run on the same street
MAX_MOVE_M = 700     # the furthest a stop moves
MIN_GAP_M = 400      # a moved stop stays at least this far from the stops either side
BUS = ("brt", "streetcar")


def _seg_dist_km(p, a, b):
    """Distance (km) from p to segment a-b; (lon, lat) points, local flat projection."""
    kx, ky = math.cos(math.radians(p[1])) * 111.32, 110.57
    ax, ay, bx, by = (a[0] - p[0]) * kx, (a[1] - p[1]) * ky, (b[0] - p[0]) * kx, (b[1] - p[1]) * ky
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    return math.hypot(ax + t * dx, ay + t * dy)


def _near_km(p, line):
    return min(_seg_dist_km(p, a, b) for a, b in zip(line, line[1:]))


def detour(A, B):
    """For legs A (ending at a stop) and B (starting there), (ia, jb): A[ia] is where the detour
    to the stop leaves the street and B[jb] where it rejoins it; None if there's no detour."""
    if len(A) < 3 or len(B) < 3:
        return None
    ia = len(A) - 1
    while ia > 1 and _near_km(A[ia - 1], B[1:]) * 1000 <= NEAR_M:
        ia -= 1
    if ia == len(A) - 1:   # B doesn't come back along A: is A's last hop out and back (a jump)?
        if geo.hav_km(A[-2][1], A[-2][0], B[1][1], B[1][0]) * 1000 > NEAR_M:
            return None
        ia = len(A) - 2
    d = A[ia]
    jb = min(range(1, len(B)), key=lambda k: geo.hav_km(d[1], d[0], B[k][1], B[k][0]))
    if jb >= len(B) - 1 or geo.hav_km(d[1], d[0], B[jb][1], B[jb][0]) * 1000 > NEAR_M:
        return None
    return ia, jb


def fix_tables(stations, lines, line_stops, line_segments, log=print, keep=()):
    """Move off-street bus stops onto their line (lists of row dicts, changed in place). Only a
    stop that one line serves moves (moving a shared stop onto one line's street would send the
    other on a detour), and none in `keep` (stations an overlay can't move: the base network's).
    Returns the number of stops moved."""
    from dfwt import config
    hairpin_deg = config.load()["standards"]["hairpin_deg"]
    mode = {r["line_id"]: r["mode"] for r in lines}
    st = {r["station_id"]: r for r in stations}
    stops, segs = {}, {}
    for r in line_stops:
        stops.setdefault(r["line_id"], []).append(r)
    for r in line_segments:
        segs.setdefault(r["line_id"], []).append(r)
    served, n_lines = {}, {}
    for lid, rs in stops.items():
        for r in rs:
            served.setdefault(r["station_id"], set()).add(mode.get(lid))
            n_lines.setdefault(r["station_id"], set()).add(lid)
    moved = 0
    for lid in sorted(stops):
        if mode.get(lid) not in BUS:
            continue
        sl = sorted(stops[lid], key=lambda r: int(r["seq"]))
        sg = sorted(segs.get(lid, []), key=lambda r: int(r["seq"]))
        if len(sg) != len(sl) - 1:
            continue
        for i in range(1, len(sl) - 1):
            sid = sl[i]["station_id"]
            if not served[sid] <= set(BUS) or sid not in st or len(n_lines[sid]) > 1 or sid in keep:
                continue
            if any(r.get("grade") == "freeway" for r in sg):   # an express bus leaves its freeway for a stop
                break
            A, B = geo.parse_wkt(sg[i - 1]["geometry_wkt"]), geo.parse_wkt(sg[i]["geometry_wkt"])
            # only what the validator calls a hairpin: the line turns straight back at the stop
            t = geo.turn_deg(geo.bearing_deg(A[-2], A[-1]), geo.bearing_deg(B[0], B[1]))
            if t <= 180 - hairpin_deg or min(geo.polyline_km(A), geo.polyline_km(B)) <= 0.25:
                continue
            hit = detour(A, B)
            if not hit:
                continue
            ia, jb = hit
            d = A[ia]
            s = st[sid]
            move = geo.hav_km(float(s["lat"]), float(s["lon"]), d[1], d[0]) * 1000
            if move > MAX_MOVE_M:
                continue
            # never onto a neighbouring stop (two off-street stops can share one turn-off)
            nb = [st[sl[k]["station_id"]] for k in (i - 1, i + 1) if sl[k]["station_id"] in st]
            if any(geo.hav_km(float(x["lat"]), float(x["lon"]), d[1], d[0]) * 1000 < MIN_GAP_M for x in nb):
                continue
            sg[i - 1]["geometry_wkt"] = geo.to_wkt(A[:ia + 1])
            sg[i]["geometry_wkt"] = geo.to_wkt([d] + B[jb + 1:])
            old = (float(s["lon"]), float(s["lat"]))
            s["lat"], s["lon"] = f"{d[1]:.6f}", f"{d[0]:.6f}"
            # other legs that end or start at the old stop point now end at the new one
            for other in segs.values():
                for r in other:
                    P = geo.parse_wkt(r["geometry_wkt"])
                    for end in (0, -1):
                        if geo.hav_km(P[end][1], P[end][0], old[1], old[0]) < 0.005:
                            P[end] = d
                            r["geometry_wkt"] = geo.to_wkt(P)
            moved += 1
            if log:
                log(f"  {lid}: {s['name']} moved {move:.0f} m onto the line (no detour)")
    return moved


def _read(folder, name):
    p = os.path.join(folder, name)
    with open(p, encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def _write(folder, name, cols, rows):
    with open(os.path.join(folder, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(folder):
    t = {n: _read(folder, n) for n in ("stations.csv", "lines.csv", "line_stops.csv", "line_segments.csv")}
    n = fix_tables(*(t[k][1] for k in ("stations.csv", "lines.csv", "line_stops.csv", "line_segments.csv")))
    for k in ("stations.csv", "line_segments.csv"):
        _write(folder, k, *t[k])
    print(f"{folder}: {n} stop(s) moved onto their line")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "network")
