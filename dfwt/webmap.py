"""Builds docs/index.html: the interactive map, from evaluated scenarios.

Everything the page needs is embedded as one JSON blob. The routing graph for
each year is exported from the same Python model the reports use (runs, ride
times, waits, transfer walks), so the in-page trip planner can't drift from it.
"""
import json
import os

from . import config, schematic

TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "map.html")
SCHEM_FILES = [os.path.join(os.path.dirname(__file__), "templates", n) for n in ("schematic.css", "schematic.js")]
LABELS = {"plan": "v2 plan (recommended)", "v1_baseline": "v1 plan (before review)",
          "right_sized": "v2, suburban metro as BRT"}


def write(nets, evals, out_path):
    cfg = next(iter(nets.values())).cfg
    geoms, gidx = [], {}
    stations = {}

    def geom_id(pts):
        key = tuple((round(x, 5), round(y, 5)) for x, y in pts)
        if key not in gidx:
            gidx[key] = len(geoms)
            geoms.append([list(p) for p in key])
        return gidx[key]

    scen = {}
    for key, net in nets.items():
        ev = evals[key]
        line_metrics = {r["line_id"]: r for r in ev["lines"]}
        st_metrics = {r["station_id"]: r for r in ev["stations"]}
        lines, lix = [], {}
        for ln in net.lines.values():
            lix[ln.id] = len(lines)
            m = line_metrics.get(ln.id, {})
            lines.append({
                "id": ln.id, "name": ln.name, "mode": ln.mode, "color": ln.color, "status": ln.status,
                "notes": ln.notes, "first": ln.first_year, "km": round(ln.km, 1),
                "cost": m.get("cost_musd", 0), "value": m.get("value_per_musd", ""),
                "load": m.get("peak_hour_load", 0),
                "segs": [[s.year, geom_id(s.pts)] for s in ln.segments],
            })
        for sid, r in st_metrics.items():
            s = net.stations[sid]
            prev = stations.get(sid)
            stations[sid] = [s.name, round(s.lat, 5), round(s.lon, 5), r["pop_1km"], r["jobs_1km"]] if not prev else prev
        years = {}
        for y, res in ev["results"].items():
            g = res["graph"]
            runs = []
            wcap = cfg["wait"]["max_wait_min"]
            for run in g.runs:
                wait = min(run.line.headway_at(y) * cfg["wait"]["fraction_of_headway"], wcap)
                runs.append([lix[run.line.id], run.stops, [round(t, 2) for t in run.hop_min], round(wait, 1)])
            walks = []
            for i in range(g.n_st):
                for j, w, kind in g.adj[i]:
                    if kind == "walk" and i < j:
                        walks.append([g.station_ids[i], g.station_ids[j], round(w, 1)])
            years[y] = {"runs": runs, "walks": walks}
        scen[key] = {"label": LABELS.get(key, key), "lines": lines, "years": years,
                     "metrics": ev["years"],
                     "boardings": {r["station_id"]: r["boardings_final"] for r in ev["stations"]}}
    data = {"years": cfg["years"], "boardPenalty": cfg["transfer"]["penalty_min"],
            "modes": {m: v["label"] for m, v in cfg["modes"].items()},
            "geoms": geoms, "stations": stations, "scen": scen,
            "order": [k for k in ("plan", "v1_baseline", "right_sized") if k in scen] +
                     [k for k in scen if k not in ("plan", "v1_baseline", "right_sized")]}
    data["schem"] = schematic.build(nets)       # diagram view (dfwt/schematic.py)
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    css, js = (open(p, encoding="utf-8").read() for p in SCHEM_FILES)
    html = html.replace("<!--__SCHEMATIC__-->", f"<style>\n{css}</style>\n<script>\n{js}</script>")
    html = html.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
