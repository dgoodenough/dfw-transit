"""Builds docs/map.html: the interactive map, from evaluated scenarios.

Everything the page needs is embedded as one JSON blob. The routing graph for
each year is exported from the same Python model the reports use (runs, ride
times, waits, transfer walks), so the in-page trip planner can't drift from it; so
are the access rules its door-to-door trips use (dfwt/tripplan.py).
"""
import json
import os

from . import bundle, config, demand, layers, schematic, tripplan
from .graph import YearGraph

TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "map.html")
SCHEM_FILES = [os.path.join(os.path.dirname(__file__), "templates", n) for n in ("schematic.css", "schematic.js")]
LABELS = {"two_million": "2 million riders by 2100 (default)", "plan": "v2 plan, budget-constrained", "v2_phasing": "v2, hand-set phasing (before the optimizer)", "v1_baseline": "v1 plan (before review)",
          "right_sized": "v2, suburban metro as BRT", "staged": "v2, optimizer's build order",
          "unstaged": "v2, lines open whole",
          "downtown_main": "Downtown FW: Main St trunk", "downtown_jones": "Downtown FW: Jones St trunk",
          "downtown_events": "Downtown FW: Main St via Convention Center",
          "current_track": "Today's lines only (current track)"}

# Regions for the Lines panel. Each stop falls in one of four zones, split along county
# lines that are nearly straight survey lines: the Tarrant / Dallas county line
# (lon -97.035), the line between those two counties and Denton / Collin to their north
# (lat 32.99), and the Denton / Collin county line (lon -96.84):
#   south of 32.99, west of -97.035: Fort Worth (Tarrant, and Parker / Johnson beyond)
#   south of 32.99, east of -97.035: Dallas (Dallas County, and Ellis / Kaufman / Rockwall)
#   north of 32.99, east of -96.84:  Collin County
#   north of 32.99, west of -96.84:  Denton County and beyond (no region of its own)
# A line belongs to the region holding more than half of its stops; otherwise (a line
# between regions, or one based in Denton County) it is "Other".
REGIONS = {"fw": "Fort Worth", "dal": "Dallas", "col": "Collin County", "other": "Other"}


def stop_zone(lat, lon):
    if lat < 32.99:
        return "fw" if lon < -97.035 else "dal"
    return "col" if lon > -96.84 else "other"


def line_region(stations, stop_ids):
    zones = [stop_zone(stations[s].lat, stations[s].lon) for s in stop_ids]
    for z in ("fw", "dal", "col"):
        if zones.count(z) * 2 > len(zones):
            return z
    return "other"


def reroutes(net, ln):
    """A rerouted line's old routings: [(until year, Line)] (net.variants; see network._reroute)."""
    return [(until, old) for _, until, old, it in net.variants.get(ln.id, []) if it.get("reroute")]


def line_extras(net, ln, region_of=None):
    """Display fields of a line beyond the model's: its region (Lines panel) and, for a rerouted
    line, the old routing it runs until the new track opens (the diagram draws it in those
    years from schematic paths[key + schematic.PRE])."""
    out = {"region": (region_of or line_region)(net.stations, ln.stop_ids)}
    for until, old in reroutes(net, ln):
        out["pre"] = {"until": until, "segs": [[s.year, round(s.km, 2)] for s in old.segments]}
    return out


def station_grades(net):
    """Where each station's platform is, per mode, when it isn't at street level: station_id ->
    {mode: grade} from the grade of the segments on either side of it (a stop next to a tunnel
    segment is underground, as network.stop_cost prices it; likewise elevated)."""
    out = {}
    for ln in net.lines.values():
        for i, sid in enumerate(ln.stop_ids):
            near = {ln.segments[k].grade for k in (i - 1, i) if 0 <= k < len(ln.segments)}
            g = "tunnel" if "tunnel" in near else next((x for x in sorted(near) if x not in ("surface", "freeway")), None)
            if g:
                out.setdefault(sid, {})[ln.mode] = g
    return out


def shared_track(net):
    """station_id -> [[line name, owner line name, year the owner builds it]]: lines that run here on
    track another line of the same mode builds (one construction period, not two), for popups."""
    ex = net.cfg["existing_year"]
    owner = net.track_owner()
    out = {}
    for ln in net.lines.values():
        for i, s in enumerate(ln.segments):
            y, oid = owner[(ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))]
            if oid == ln.id or y <= ex or oid not in net.lines or s.year >= 9999:
                continue
            row = [ln.name, net.lines[oid].name, y]
            for sid in ln.stop_ids[i:i + 2]:
                if row not in out.setdefault(sid, []):
                    out[sid].append(row)
    return out


def drawn(net):
    """The map's shared-track pieces (bundle.pieces) and where each station sits on them
    (bundle.station_pieces). A rerouted line draws its old track too, until the new one opens."""
    def segs(ln):
        out = [(s.year, s.pts) for s in ln.segments]
        have = {(tuple(s.pts[0]), tuple(s.pts[-1])) for s in ln.segments}
        for until, old in reroutes(net, ln):
            out += [(s.year, s.pts, until) for s in old.segments
                    if (tuple(s.pts[0]), tuple(s.pts[-1])) not in have and (tuple(s.pts[-1]), tuple(s.pts[0])) not in have]
        return out
    lines = list(net.lines.values())
    raw = bundle.pieces([(i, ln.mode, ln.status, ln.first_year, segs(ln)) for i, ln in enumerate(lines)])
    stops = {i: ln.stop_ids + [s for _, old in reroutes(net, ln) for s in old.stop_ids if s not in ln.stop_ids]
             for i, ln in enumerate(lines)}
    st_piece = bundle.station_pieces(raw, {sid: (st.lon, st.lat) for sid, st in net.stations.items()}, stops)
    return raw, st_piece


# What a page for another region changes (write(..., site=...)): DFW's literals in the template, replaced as text
# so that DFW's own page is unchanged when no site is given.
DFW_TEXT = {
    "title": "<title>DFW Transit Map</title>",
    "aria": 'aria-label="Map of the DFW transit network"',
    "h1": "<h1>DFW Transit</h1>",
    "sub": "A phased plan for Dallas–Fort Worth. Drag the year, switch plans, plan a trip from any address. Speculative, not an official plan.",
    "story": '<a class="sub" href="index.html" style="display:inline-block;margin-top:2px">&larr; Why this plan: the story</a>',
    "view": "setView([32.84, -97.03], 10)",
    "box": "const GEO_BOX = [-98.1, 32.2, -95.9, 33.6];   // lon/lat box addresses are searched in (the metroplex)",
    "kmlat": "Math.cos(32.8 * Math.PI / 180)",
    "geo": "&lat=32.8&lon=-97.0&limit=8",
    "area": "No address in the DFW area matches",
    "region": "(the Dallas–Fort Worth region,",
    "layers": ("loadScript('layers/zones.js')", "loadScript(`layers/${key}.js`)", "beside the map, in layers/)"),
}


def _site_text(html, site):
    """The template with a region's own title, header, view, address box and layers folder (site: see write)."""
    lat, lon = site["center"]
    box = site["geo_box"]
    lay = site.get("layers_url", "layers/")
    rep = [(DFW_TEXT["title"], f"<title>{site['title']}</title>"),
           (DFW_TEXT["aria"], f'aria-label="Map of the {site["short"]} transit network"'),
           (DFW_TEXT["h1"], f"<h1>{site['title']}</h1>"),
           (DFW_TEXT["sub"], site["sub"]),
           (DFW_TEXT["story"], f'<a class="sub" href="{site.get("back_href", "index.html")}" style="display:inline-block;margin-top:2px">&larr; {site.get("back_text", "Back")}</a>'),
           (DFW_TEXT["view"], f"setView([{lat:.3f}, {lon:.3f}], {site.get('zoom', 10)})"),
           (DFW_TEXT["box"], f"const GEO_BOX = [{box[0]}, {box[1]}, {box[2]}, {box[3]}];   // lon/lat box addresses are searched in"),
           (DFW_TEXT["kmlat"], f"Math.cos({lat:.1f} * Math.PI / 180)"),
           (DFW_TEXT["geo"], f"&lat={lat:.1f}&lon={lon:.1f}&limit=8"),
           (DFW_TEXT["area"], f"No address in the {site['short']} area matches"),
           (DFW_TEXT["region"], f"(the {site['short']} region,"),
           (DFW_TEXT["layers"][0], f"loadScript('{lay}zones.js')"),
           (DFW_TEXT["layers"][1], f"loadScript(`{lay}${{key}}.js`)"),
           (DFW_TEXT["layers"][2], f"beside the map, in {lay})")]
    if site.get("start_year"):   # the year the page opens on (DFW's opens on its first); the nearest model year
        rep.append(("let scenKey = D.order[0], yi = 0,",
                    f"let scenKey = D.order[0], yi = Math.max(0, D.years.findIndex(y => y >= {int(site['start_year'])})),"))
        rep.append(("$('slider').max = D.years.length - 1;", "$('slider').max = D.years.length - 1; $('slider').value = yi;"))
    for a, b in rep:
        if a not in html:
            raise ValueError(f"template changed: {a[:60]!r} not found")
        html = html.replace(a, b)
    return html


def write(nets, evals, out_path, site=None):
    """The map page. `site` (another region; None for DFW): {"title", "short" (name in messages), "sub" (header
    line), "center" (lat, lon), "zoom", "geo_box" [lon0, lat0, lon1, lat1], "zones" (a demand.Zones: the trip
    planner's feeder zones and the data layers), "regions" ({key: label} for the Lines panel) and "region_of"
    (fn(stations, stop_ids) -> key), "labels" ({scenario key: label}), "start_year" (the year it opens on), "cities" ([(name, lat, lon)] for the
    diagram), "waterways" (a geojson path, "" for none), "layers_dir" and "layers_url" (where the data layers
    go and how the page finds them), "back_href" / "back_text" (the header link)}."""
    site = site or {}
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
    zones = site.get("zones") or demand.Zones(cfg)   # base-year block groups: the trip planner's feeder zones and garages
    labels = dict(LABELS, **(site.get("labels") or {}))
    feeds = False
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
                "segs": [[s.year, round(s.km, 2)] for s in ln.segments], **line_extras(net, ln, site.get("region_of")),
            })
        # drawn geometry: shared-track pieces, each with its lines in side-by-side order
        raw, st_piece = drawn(net)
        pieces = [[geom_id(pts), [list(u) for u in users]] for pts, users in raw]
        for sid, r in st_metrics.items():
            s = net.stations[sid]
            prev = stations.get(sid)
            stations[sid] = [s.name, round(s.lat, 5), round(s.lon, 5), r["pop_1km"], r["jobs_1km"]] if not prev else prev
        graphs, gkey, years, ygraphs = [], {}, {}, {}
        for y in ev["results"]:
            g = ygraphs[y] = YearGraph(net, y)
            runs = []
            wcap = cfg["wait"]["max_wait_min"]
            for run in g.runs:
                wait = min(run.line.headway_at(y) * cfg["wait"]["fraction_of_headway"], wcap)
                runs.append([lix[run.line.id], run.stops, [round(t, 2) for t in run.hop_min], round(wait, 1),
                             round(run.line.headway_at(y), 1)])
            walks = []
            for i in range(g.n_st):
                for j, w, kind in g.adj[i]:
                    if kind == "walk" and i < j:
                        walks.append([g.station_ids[i], g.station_ids[j], round(w, 1)])
            # most years change nothing: store each distinct routing graph once
            k = json.dumps([runs, walks], separators=(",", ":"))
            if k not in gkey:
                gkey[k] = len(graphs)
                graphs.append({"runs": runs, "walks": walks})
            years[y] = gkey[k]
        scen[key] = {"label": labels.get(key, key), "lines": lines, "pieces": pieces, "stPiece": st_piece, "graphs": graphs, "yearGraph": years,
                     "metrics": ev["years"],
                     "boardings": {r["station_id"]: r["boardings_final"] for r in ev["stations"]},
                     "grades": station_grades(net),
                     "shared": shared_track(net),
                     # "What it means for you": the plan's capital budget ($B a year, 2025 dollars)
                     "budget": net.cfg["budget"]["musd_per_year"] / 1000,
                     # door-to-door trips: the model's access rules, garages and feeder zones by year
                     "trip": tripplan.export(zones, net, ygraphs)}
        feeds = feeds or scen[key]["trip"]["feed"] is not None
    data = {"years": cfg["years"], "boardPenalty": cfg["transfer"]["penalty_min"],
            "build": cfg["staging"]["construction_years"],
            "modes": {m: v["label"] for m, v in cfg["modes"].items()}, "regions": site.get("regions", REGIONS),
            # "What it means for you": the costed service day; feeder buses are in the operating cost
            # when the model prices them (operating.feeder_usd_per_boarding)
            "operating": {**{k: cfg["operating"][k] for k in ("span_hours", "days_per_year")},
                          "feeder": bool(cfg["operating"].get("feeder_usd_per_boarding")),
                          "late": {k: v for k, v in (cfg["operating"].get("late_night") or {}).items() if not k.startswith("_")}},
            "geoms": geoms, "stations": stations, "scen": scen,
            "zones": tripplan.zone_points(zones) if feeds else [],
            "order": [k for k in (cfg.get("default_scenario"), "plan", "v1_baseline", "right_sized") if k in scen] +
                     [k for k in scen if k not in (cfg.get("default_scenario"), "plan", "v1_baseline", "right_sized")]}
    # diagram view (dfwt/schematic.py): one layout per version (schematic.VERSIONS): Rail, BRT
    # (every BRT line, the 2M arterial grid too) and All (rail and the plan's BRT corridors).
    old = schematic.CITIES, schematic.WATERWAYS
    try:
        if site:
            schematic.CITIES, schematic.WATERWAYS = site.get("cities", []), site.get("waterways", "")
        data["schem"] = schematic.build(nets)
    finally:
        schematic.CITIES, schematic.WATERWAYS = old
    # data layers (dfwt/layers.py): per-area numbers by year, in scripts the page loads on demand
    data["layers"] = layers.write(zones, evals, site.get("layers_dir") or os.path.join(os.path.dirname(out_path), "layers"))
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    if site:
        html = _site_text(html, site)
    css, js = (open(p, encoding="utf-8").read() for p in SCHEM_FILES)
    html = html.replace("<!--__SCHEMATIC__-->", f"<style>\n{css}</style>\n<script>\n{js}</script>")
    html = html.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
