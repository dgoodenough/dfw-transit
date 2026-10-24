"""Express buses for the 2 million riders scenario (scenarios/two_million/extra/): routed on the
freeway network between their stops, timed honestly.

    python tools/express_buses.py        # rewrites the XE rows of extra/ and their set_line speeds in edits.csv
    python tools/make_two_million.py     # then regenerate the scenario tables

A bus in a freeway's managed lanes averages FREEWAY_KMH; the stretches it runs on arterials and
frontage roads to reach a station go at the mode's BRT speed. Each line's speed (set_line
cruise_kmh) is the average of the two by distance, so a route with long street sections is
slower. Capital: stops, ramps and signs (grade "freeway", config cost_musd_per_km.brt.freeway)."""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dfwt import config, geo, osmroute  # noqa: E402

FREEWAY_KMH = 60
NEAR_M = 25    # a route piece this close to a motorway carriageway is in the freeway (frontage roads sit farther out)

# id, name, color, stop ids, headway, retire_with (rail line that replaces it), note, stage note
LINES = [
    ("XE01", "I-35E Express", "#8d6e63", ["X588", "XX01", "X375", "X301", "X187"], 7.5, "",
     "Express bus in I-35E's managed lanes: Waxahachie - Red Oak - Belt Line (Lancaster/DeSoto) - Zang / Illinois "
     "(Oak Cliff) - Union Station. Review 2 (residents): Ellis County gets a frequent link decades before regional rail. Every 7.5 min (review 3, R6).",
     "review 2 (D3): an early express for Ellis County"),
    ("XE02", "Mesquite Express", "#a1887f", ["X275", "X247", "X141"], 15, "E18",
     "Express bus on I-30: downtown Mesquite (Main / Galloway) - Town East - downtown Dallas (Pearl/Arts District), "
     "until the Las Colinas-Mesquite Line reaches Main / Galloway. Every city over 150,000 served by about 2040.",
     "review 2 (D2/D3): Mesquite served early"),
    ("XE03", "McKinney Express", "#bcaaa4", ["X500", "X498", "X125"], 15, "E25",
     "Express bus on US-75: McKinney - Allen - the Red and Orange lines at Parker Road, until the Red Line reaches "
     "McKinney. Every city over 150,000 served by about 2040. Reaches US-75 from downtown on McDonald Street (SH-5) and Spur 399, timed at street speed there.",
     "review 2 (D2/D3): McKinney served early"),
]
STATIONS = {"XX01": ("Red Oak", 32.517333, -96.804181)}
W_FREEWAY = {"motorway": 1.0, "trunk": 1.5, "primary": 2.5, "secondary": 3.0, "tertiary": 4.0}   # stay on the freeway


def main():
    from dfwt.network import Network
    net = Network.load()
    pos = {sid: (s.lat, s.lon) for sid, s in net.stations.items()}
    pos.update({k: (la, lo) for k, (_, la, lo) in STATIONS.items()})
    mw = osmroute.Graph("road", classes={"motorway"}, oneway=False)
    roads = osmroute.Graph("road", classes=set(W_FREEWAY), oneway=False)

    def road_path(A, B):
        for snap in (800, 1500, 2500):
            P, why = osmroute.route(roads, [osmroute.xy(A[1], A[0]), osmroute.xy(B[1], B[0])], max_turn=135, snap_r=snap,
                                    w_cls=W_FREEWAY, turn_pen=1500.0, detour=4.0, snap_w=3.0)
            if P:
                return [(la, lo) for lo, la in (osmroute.ll(p) for p in P)]
        raise SystemExit(f"no road route {A} -> {B}: {why}")

    def on_freeway(lat, lon):
        p = osmroute.xy(lon, lat)
        cx, cy = int(p[0] // 250), int(p[1] // 250)
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for e in mw.egrid.get((i, j), ()):
                    P = mw.edges[e][2]
                    for a, b in zip(P, P[1:]):
                        vx, vy = b[0] - a[0], b[1] - a[1]
                        L2 = vx * vx + vy * vy
                        t = 0 if L2 == 0 else max(0, min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
                        if math.dist(p, (a[0] + t * vx, a[1] + t * vy)) <= NEAR_M:
                            return True
        return False

    X = config.path("scenarios", "two_million", "extra")
    tabs = {}
    for name in ("lines.csv", "stations.csv", "line_stops.csv", "line_segments.csv", "stages.csv"):
        with open(os.path.join(X, name), encoding="utf-8") as f:
            r = csv.DictReader(f)
            tabs[name] = (r.fieldnames, [row for row in r if not row.get("line_id", "").startswith("XE")
                                         and row.get("station_id") not in STATIONS])
    speeds = {}
    for lid, name, color, stops, hw, retire, note, stage_note in LINES:
        legs, fw_km, tot_km = [], 0.0, 0.0
        for a, b in zip(stops, stops[1:]):
            A, B = pos[a], pos[b]
            P = road_path(A, B)
            inner = P[1:-1]
            if inner:   # join each station at the route's nearest point (no spurs past it)
                k0 = min(range(len(inner)), key=lambda i: geo.hav_km(*inner[i], *A))
                inner = inner[k0:]
                k1 = min(range(len(inner)), key=lambda i: geo.hav_km(*inner[i], *B))
                inner = inner[:k1 + 1]
            leg = [A] + inner + [B]
            legs.append(leg)
            for p, q in zip(leg, leg[1:]):
                d = geo.hav_km(*p, *q)
                tot_km += d
                if on_freeway((p[0] + q[0]) / 2, (p[1] + q[1]) / 2):
                    fw_km += d
        brt = config.load()["modes"]["brt"]["cruise_kmh"]
        kmh = tot_km / (fw_km / FREEWAY_KMH + (tot_km - fw_km) / brt)
        speeds[lid] = (round(kmh, 1), fw_km / tot_km, retire)
        print(f"{lid} {name}: {tot_km:.1f} km, {fw_km / tot_km:.0%} on freeway -> {kmh:.1f} km/h")
        tabs["lines.csv"][1].append({"line_id": lid, "name": name, "mode": "brt", "status": "proposed", "color": color,
                                     "headway_min": str(hw), "notes": note})
        tabs["line_stops.csv"][1].extend({"line_id": lid, "seq": str(k + 1), "station_id": s, "year_opens": "2030"}
                                         for k, s in enumerate(stops))
        tabs["line_segments.csv"][1].extend(
            {"line_id": lid, "seq": str(k + 1), "year_opens": "2030", "grade": "freeway", "geometry_source": "osm_road",
             "locked": "", "geometry_wkt": "LINESTRING (" + ", ".join(f"{lo:.6f} {la:.6f}" for la, lo in leg) + ")"}
            for k, leg in enumerate(legs))
        tabs["stages.csv"][1].append({"line_id": lid, "stage": "1", "kind": "starter", "from_stop": stops[0],
                                      "to_stop": stops[-1], "year_opens": "2030", "until_year": "", "via_line": "",
                                      "headway_min": "", "locked": "", "note": stage_note})
    for sid, (nm, la, lo) in STATIONS.items():
        tabs["stations.csv"][1].append({"station_id": sid, "name": nm, "lat": f"{la:.6f}", "lon": f"{lo:.6f}"})
    for name, (cols, rows) in tabs.items():
        with open(os.path.join(X, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    # speeds and retirements in edits.csv (replacing earlier XE rows)
    ep = config.path("scenarios", "two_million", "edits.csv")
    with open(ep, encoding="utf-8") as f:
        r = csv.DictReader(f)
        cols, rows = r.fieldnames, [e for e in r if not e["target"].startswith("XE")]
    for lid, (kmh, share, retire) in speeds.items():
        rows.append({"op": "set_line", "target": lid, "field": "cruise_kmh", "value": str(kmh),
                     "note": f"express bus: {share:.0%} of the route in freeway lanes at {FREEWAY_KMH} km/h, the rest at BRT speed"})
        if retire:
            rows.append({"op": "retire_with", "target": lid, "field": retire, "value": "",
                         "note": f"runs until {retire} opens (tools/express_buses.py)"})
    with open(ep, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
