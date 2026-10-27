"""Generator output: dfwt tables, network statistics, model runs, report.md, preview.png."""
import collections
import math
import os

import numpy as np

from dfwt import config, geo, validate
from dfwt.network import Network

from . import geom, inputs, model

OPTIONAL_EMPTY = {   # written empty so dfwt doesn't fall back to DFW's plan tables (network/)
    "stages.csv": ["line_id", "stage", "kind", "from_stop", "to_stop", "year_opens", "until_year", "via_line",
                   "headway_min", "locked", "note"],
    "service.csv": ["line_id", "from_year", "headway_min", "note"],
    "infill.csv": ["station_id", "lines", "partners", "year_min", "note"],
}
COLORS = {"metro": ["#d32f2f", "#1976d2", "#388e3c", "#7b1fa2", "#f57c00", "#0097a7", "#c2185b", "#5d4037",
                    "#303f9f", "#689f38"],
          "brt": ["#8e24aa", "#00897b", "#6d4c41", "#3949ab", "#c0ca33", "#e64a19", "#546e7a"],
          "commuter": ["#4e342e", "#37474f", "#1b5e20", "#4a148c"],
          "streetcar": ["#e57373", "#a1887f"]}
LABEL = {"metro": "Metro", "brt": "BRT", "commuter": "Rail", "streetcar": "Streetcar"}
SNAP_M = 250


def make_namer(m):
    from dfwt.naming import Namer
    return Namer(roads=True, roads_path=m.osm.get("roads"), places=False)


def place_name(namer, lat, lon, used, fallback):
    try:
        return namer.name(lat, lon, used, fallback)[0]
    except Exception:   # naming is cosmetic; never fail a run on it
        return fallback


def write_csv(path, rows):
    if not rows:
        return
    inputs.write_csv(path, rows, list(rows[0].keys()))


def write_tables(out, t):
    for name, fields in inputs.TABLES.items():
        inputs.write_csv(os.path.join(out, name), t[name], fields)
    for name, fields in OPTIONAL_EMPTY.items():
        inputs.write_csv(os.path.join(out, name), [], fields)


def tables(m, ex, chosen, by, gp, cfg, y_open, namer, used_names, downtowns, core_r):
    """Today's tables plus the chosen lines (status proposed, opening y_open)."""
    t = {k: [dict(r) for r in v] for k, v in ex.tables.items()}
    for r in t["stations.csv"]:
        used_names |= _keys(r["name"])
    reg = {r["station_id"]: (float(r["lat"]), float(r["lon"])) for r in t["stations.csv"]}
    xy = {sid: tuple(float(v) for v in m.xy(*ll)) for sid, ll in reg.items()}
    n_new = 0
    line_names = {r["name"] for r in t["lines.csv"]}
    color_k = collections.Counter()
    new_ids = []
    for k, c in enumerate(sorted(chosen, key=lambda c: c.order)):
        lid = f"G{k + 1:02d}"
        sids, pos = [], []
        cum = geom.cumlen(c.P)
        for s, p, ref in c.stops:
            if ref and ref[0] == "E":
                sid = ref[1]
            else:
                near = min(((math.dist(p, q), sid) for sid, q in xy.items() if abs(q[1] - p[1]) < 1),
                           default=(1e9, None))
                if near[0] * 1000 <= SNAP_M:
                    sid = near[1]
                else:
                    n_new += 1
                    sid = f"N{n_new:04d}"
                    lat, lon = (float(v) for v in m.ll(*p))
                    nm = place_name(namer, lat, lon, used_names, f"{c.name.split(' - ')[0]} {n_new}")
                    reg[sid], xy[sid] = (lat, lon), p
                    t["stations.csv"].append({"station_id": sid, "name": nm, "lat": f"{lat:.6f}", "lon": f"{lon:.6f}"})
                    new_ids.append(sid)
            if sid in sids:      # the line passes a station twice (snapping): drop the repeat
                continue
            sids.append(sid)
            pos.append(s)
        if len(sids) < 2:
            continue
        mode = c.mode
        nm = f"{c.name} {LABEL[mode]}"
        while nm in line_names:
            nm += "'"
        line_names.add(nm)
        col = COLORS[mode][color_k[mode] % len(COLORS[mode])]
        color_k[mode] += 1
        c.line_id, c.line_name = lid, nm
        t["lines.csv"].append({"line_id": lid, "name": nm, "mode": mode, "status": "proposed", "color": col,
                               "headway_min": "", "notes": f"generated ({c.uid}): {c.mode_reason}; {c.reason}"})
        for i, sid in enumerate(sids):
            t["line_stops.csv"].append({"line_id": lid, "seq": i + 1, "station_id": sid, "year_opens": y_open})
        for i in range(len(sids) - 1):
            seg = geom.cut(c.P, cum, pos[i], pos[i + 1]) if pos[i + 1] > pos[i] else [xy[sids[i]], xy[sids[i + 1]]]
            moved = (math.dist(seg[0], xy[sids[i]]), math.dist(seg[-1], xy[sids[i + 1]]))
            seg[0], seg[-1] = xy[sids[i]], xy[sids[i + 1]]
            if max(moved) > 0.03:   # a stop snapped onto a station beside the route: no stub out and back
                lo, hi = (max(1.5 * d, 0.15) if d > 0.03 else 0.0 for d in moved)
                seg = [seg[0]] + [p for p in seg[1:-1] if math.dist(p, seg[0]) > lo and math.dist(p, seg[-1]) > hi] \
                    + [seg[-1]]
            core = any(math.dist(seg[0], d) <= core_r or math.dist(seg[-1], d) <= core_r for d in downtowns)
            grade = "tunnel" if mode == "metro" and core else "surface"
            ll = geom.to_ll(m, seg)
            t["line_segments.csv"].append({"line_id": lid, "seq": i + 1, "year_opens": y_open, "grade": grade,
                                           "geometry_source": "generated", "locked": "",
                                           "geometry_wkt": "LINESTRING (" + ", ".join(
                                               f"{lon:.6f} {lat:.6f}" for lat, lon in ll) + ")"})
    # walk links from new stations to other stations beyond the model's own radius
    r_auto = cfg["transfer"]["walk_radius_m"] / 1000
    r_link = gp["stations"]["transfer_m"] / 1000
    on = collections.defaultdict(set)
    for r in t["line_stops.csv"]:
        on[r["station_id"]].add(r["line_id"])
    linked = {frozenset((r["station_a"], r["station_b"])) for r in t["transfers.csv"]}
    for sid in new_ids:
        if sid not in on:
            continue
        for oid, q in xy.items():
            if oid == sid or oid not in on or on[oid] & on[sid]:
                continue
            d = math.dist(xy[sid], q)
            if r_auto < d <= r_link and frozenset((sid, oid)) not in linked:
                t["transfers.csv"].append({"station_a": sid, "station_b": oid, "walk_min": "",
                                           "note": f"generated: {d * 1000:.0f} m walk"})
                linked.add(frozenset((sid, oid)))
    t["stations.csv"] = [r for r in t["stations.csv"] if r["station_id"] in on]
    return t


def _keys(name):
    from dfwt.naming import keys
    return keys(name)


def load_net(t, cfg, name):
    raw = {k: v for k, v in t.items()}
    for k in OPTIONAL_EMPTY:
        raw.setdefault(k, [])
    return Network.from_raw(raw, [], cfg, name)


def coverage(m, cfg, net, lines=None):
    """(people, jobs) within each mode's walkshed (config coverage.walkshed_m) of the stations
    of `lines` (default: all), on the base data."""
    near = np.zeros(m.n, dtype=bool)
    ws = cfg["coverage"]["walkshed_m"]
    for ln in net.lines.values():
        if lines is not None and ln.id not in lines:
            continue
        r = ws[ln.mode] / 1000
        for sid in ln.stop_ids:
            s = net.stations[sid]
            x, y = m.xy(s.lat, s.lon)
            near |= (m.x - x) ** 2 + (m.y - y) ** 2 <= r * r
    return float(m.pop[near].sum()), float(m.jobs[near].sum())


def coverage_800(m, net, lines=None):
    near = np.zeros(m.n, dtype=bool)
    for ln in net.lines.values():
        if lines is not None and ln.id not in lines:
            continue
        for sid in ln.stop_ids:
            s = net.stations[sid]
            x, y = m.xy(s.lat, s.lon)
            near |= (m.x - x) ** 2 + (m.y - y) ** 2 <= 0.64
    return float(m.pop[near].sum()), float(m.jobs[near].sum())


def network_stats(out, m, cfg, t, ex_tables, name="generated"):
    with model.projection(m):
        net = load_net(t, cfg, name)
        findings = validate.run(net)
    new = [ln for ln in net.lines.values() if ln.status != "existing"]
    km = collections.Counter()
    n_lines = collections.Counter()
    for ln in new:
        km[ln.mode] += ln.km
        n_lines[ln.mode] += 1
    cap = sum(net.shared_cost_musd(ln) for ln in new)
    y = cfg["existing_year"] + 1
    all_open = model.all_open(net)
    opex_all = sum(all_open.opex_musd(y).values())
    with model.projection(m):
        ex_net = load_net(ex_tables, cfg, "existing")
    opex_ex = sum(model.all_open(ex_net).opex_musd(y).values()) if ex_net.lines else 0.0
    new_ids = {ln.id for ln in new}
    stations_new = {sid for ln in new for sid in ln.stop_ids}
    stations_ex = {sid for ln in net.lines.values() if ln.status == "existing" for sid in ln.stop_ids}
    return {"km": dict(km), "lines": dict(n_lines), "capital_musd": cap, "opex_new_musd": opex_all - opex_ex,
            "stations_new": len(stations_new - stations_ex), "stations_shared": len(stations_new & stations_ex),
            "cov_all": coverage(m, cfg, net), "cov_existing": coverage(m, cfg, net, {ln.id for ln in net.lines.values()
                                                                                     if ln.status == "existing"}),
            "cov800_all": coverage_800(m, net), "cov800_new": coverage_800(m, net, new_ids),
            "cov800_existing": coverage_800(m, net, {ln.id for ln in net.lines.values() if ln.status == "existing"}),
            "findings": collections.Counter((f[0], f[1]) for f in findings), "net": net}


def model_runs(m, cfg, ctx, t, ex):
    with model.projection(m):
        base = load_net(ex.tables, cfg, "existing")
        gen = load_net(t, cfg, "generated")
        r0 = model.run_today(ctx, base, base) if base.lines else None
        r1 = model.run_today(ctx, gen, base)
    return {"existing": r0, "generated": r1, "od_source": ctx.od_source, "year": cfg["existing_year"] + 1}


# ------------------------------------------------------------------ report
def metro_name(m):
    meta = m.meta or {}
    return meta.get("name") or (meta.get("metro") or {}).get("name") or m.id


def _f(x, unit=""):
    return f"{x:,.0f}{unit}"


def report(out, m, gp, cfg, urban, towns, links, cands, chosen, budget, spent, st, res, flags, secs, metro_id):
    L = []
    w = L.append
    w(f"# Generated network: {metro_name(m)}")
    w("")
    w(f"Generated by `python -m metro generate {metro_id}` from the step-1 inputs in "
      f"`data/metros/{metro_id}/`, with no hand-drawn lines. Parameters: `metro/generate.json`; unit costs, speeds, "
      "headways and the ridership logit: `config.json`. Load it in the DFW tools with "
      f"`python -m dfwt validate --scenario $PWD/generated/{metro_id}`.")
    w("")
    if flags:
        w("**Data warnings:** " + "; ".join(flags) + ".")
        w("")
    w("## Inputs")
    w("")
    for s in m.status():
        w(f"- {s}")
    w("")
    w("## Summary")
    w("")
    tot_km = sum(st["km"].values())
    modes_txt = ", ".join(f"{LABEL[k]} {v:,.0f} km / {st['lines'][k]} lines" for k, v in sorted(st["km"].items()))
    w(f"- **{len(chosen)} lines, {tot_km:,.0f} km** "
      f"({modes_txt}), "
      f"{st['stations_new']} new stations, {st['stations_shared']} shared with today's lines.")
    w(f"- **Capital ${st['capital_musd'] / 1e3:,.1f}B** (2025 $, dfwt costing of the tables) against a budget of "
      f"${budget / 1e3:,.1f}B (selection's own estimate ${spent / 1e3:,.1f}B); operating "
      f"${st['opex_new_musd']:,.0f}M a year more than today's lines.")
    p_all, j_all = st["cov800_all"]
    p_ex, j_ex = st["cov800_existing"]
    P, J = m.pop.sum(), max(m.jobs.sum(), 1)
    w(f"- **Within 800 m of a station:** {p_all / P:.1%} of residents ({p_ex / P:.1%} today), "
      + (f"{j_all / J:.1%} of jobs ({j_ex / J:.1%} today)." if m.jobs_ok else "jobs unknown."))
    if res:
        r0, r1 = res["existing"], res["generated"]
        base = r0["daily_trips"] if r0 else 0.0
        w(f"- **Ridership (dfwt demand model, {res['year']} land use, every line open, demand source "
          f"{res['od_source']}):** {r1['daily_trips']:,.0f} daily transit trips "
          f"({r1['daily_boardings']:,.0f} rail + BRT boardings) vs {base:,.0f} on today's lines; "
          f"{r1['access_jobs_45']:,.0f} jobs within 45 min for the average resident"
          + (f" ({r0['access_jobs_45']:,.0f} today)." if r0 else "."))
        if metro_id != "dfw":
            w("  The model's behaviour (logit constants, access) is DFW's calibration transferred, not fitted here.")
    f = st["findings"]
    w(f"- `dfwt validate`: {sum(v for (s, _), v in f.items() if s == 'error')} errors, "
      f"{sum(v for (s, _), v in f.items() if s == 'warn')} warnings "
      f"({', '.join(f'{c} {v}' for (s, c), v in sorted(f.items()) if s == 'warn') or 'none'}).")
    w(f"- Run time {secs / 60:.1f} min.")
    w("")
    w("## 1. Activity centers")
    w("")
    cp = gp["centers"]
    w(f"People + jobs per km2 within {cp['kernel_km']} km on a {cp['grid_km']} km grid; cells of at least "
      f"{cp['min_density']:,}/km2 climb to their local peak (peaks within {cp['merge_km']} km merge); a cluster of "
      f"at least {cp['min_activity']:,} people + jobs is a center. Downtown: >= {cp['downtown_jobs']:,} jobs within "
      f"{cp['downtown_radius_km']} km and peak job density >= {cp['downtown_job_density']:,}/km2. Towns (regional-rail "
      f"ends): {cp['town_min_density']:,}/km2 and {cp['town_min_activity']:,} people + jobs, "
      f">= {cp['town_min_sep_km']} km from a center.")
    w("")
    w("| id | name | kind | people + jobs | jobs | peak density /km2 | lat, lon |")
    w("|---|---|---|---|---|---|---|")
    for c in urban + towns:
        w(f"| {c.id} | {c.name} | {c.kind} | {_f(c.activity)} | {_f(c.jobs)} | {_f(c.peak_density)} | "
          f"{c.lat:.4f}, {c.lon:.4f} |")
    w("")
    w("## 2. Corridors")
    w("")
    nr = sum(1 for k in links if k.kind == "road")
    nrail = sum(1 for k in links if k.kind == "rail")
    w(f"{nr} road links (Gabriel graph over centers, <= {gp['links']['max_km']['road']} km) and {nrail} rail links "
      f"(centers + towns, <= {gp['links']['max_km']['rail']} km). Routed: metro profile "
      f"{sum(1 for k in links if k.routes.get('metro'))}, BRT profile {sum(1 for k in links if k.routes.get('brt'))}, "
      f"rail {sum(1 for k in links if k.routes.get('rail'))}.")
    why = collections.Counter(_bucket_link(v) for k in links for v in k.why.values())
    if why:
        w("Link routes dropped: " + "; ".join(f"{n} x {k}" for k, n in why.most_common()) + ".")
    w("")
    pool = [c for c in cands if c.mode]
    w(f"{len(cands)} candidate lines (shortest center-to-center paths that pass the length, circuity and turn "
      f"tests), {len(pool)} dense enough for a mode: "
      + ", ".join(f"{LABEL[k]} {sum(c.mode == k for c in pool)}" for k in ("metro", "streetcar", "brt", "commuter")) + ".")
    w("")
    M = gp["modes"]
    w(f"Mode rule (people + jobs within 800 m per route-km): metro >= {M['metro']:,} "
      f"({gp['lines']['min_km']['metro']}-{gp['lines']['max_km']['metro']} km), streetcar >= {M['streetcar']:,} "
      f"(<= {gp['lines']['max_km']['streetcar']} km), BRT >= {M['brt']:,} (BRT over capacity becomes metro); "
      f"regional rail on existing track with >= {M['commuter_1600m']:,} within 1.6 km per km.")
    w("")
    w("## 3. Chosen lines")
    w("")
    w("In the order chosen (most new daily trips per $M first; sketch demand, single-line trips).")
    w("")
    w("| # | line | mode | km | stops | density /route-km | capital $B | new trips/day | trips per $M | "
      "peak-hour load | why this mode |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(chosen, key=lambda c: c.order):
        w(f"| {c.order} | {getattr(c, 'line_id', '')} {c.name} | {c.mode} | {c.km:.1f} | {len(c.stops)} | {_f(c.rho)} | "
          f"{c.capital / 1e3:.2f} | {_f(c.new_trips)} | {c.ratio:.2f} | {_f(c.peak_hour_load)} | {c.mode_reason} |")
    w("")
    w("## 4. Rejected candidates")
    w("")
    rej = [c for c in cands if c.status in ("rejected", "replaced")]
    w(f"{len(rej)} candidates with a mode were not chosen. The 40 with the highest value:")
    w("")
    w("| candidate | mode | km | new trips/day | trips per $M | reason |")
    w("|---|---|---|---|---|---|")
    for c in sorted(rej, key=lambda c: -c.ratio)[:40]:
        w(f"| {c.uid} {c.name} | {c.mode} | {c.km:.1f} | {_f(c.new_trips)} | {c.ratio:.2f} | {c.reason} |")
    w("")
    nomode = [c for c in cands if c.status == "no mode"]
    w(f"{len(nomode)} paths had no mode: " + "; ".join(f"{n} x {k}" for k, n in collections.Counter(
        _bucket(c.reason) for c in nomode).most_common()) + ".")
    w("")
    w("All candidates with their scores: `candidates.csv`; centers: `centers.csv`; map: `preview.png`.")
    w("")
    w("## Method notes and limits")
    w("")
    w("- Value is a sketch: commutes between station catchments of one line (walk, and park & ride at regional-rail "
      "stations and termini), each pair's transit share from the config.json logit against driving. Trips that "
      "need a transfer are not credited to a line, so the network effect (and the full model's feeder buses) "
      "appear only in the model run.")
    w("- Corridors connect detected centers: a dense residential arterial that links no two centers is not a "
      "candidate (the hand plans' residential BRT grids are mostly missed).")
    w("- Geometry is the routed corridor, not a design alignment (`python -m dfwt align` fits one).")
    w("- New lines open together (a potential network, not a staged plan).")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def _bucket_link(why):
    if why.startswith("route ends"):
        return "route ends too far from a center"
    if why.startswith("route "):
        return "route too roundabout"
    return why


def _bucket(reason):
    for key in ("too thin", "rail corridor too thin", "longer than a metro", "length range", "no freeway", "outside"):
        if key in reason:
            return key
    return reason[:40]


# ------------------------------------------------------------------ preview
def preview(out, m, surf, urban, towns, ex, chosen, t):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(11, 11), dpi=110)
    d = surf.density_at(m.x, m.y)
    sel = d > 300
    ax.scatter(m.lon[sel], m.lat[sel], s=6, c=np.log10(d[sel]), cmap="Greys", vmin=2.0, vmax=5.0, linewidths=0,
               alpha=0.6)
    for r in t["line_segments.csv"]:
        if r["line_id"].startswith("G"):
            continue
        pts = geo.parse_wkt(r["geometry_wkt"])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#777", lw=1.4, alpha=0.9)
    col = {r["line_id"]: r["color"] for r in t["lines.csv"]}
    mode = {r["line_id"]: r["mode"] for r in t["lines.csv"]}
    for r in t["line_segments.csv"]:
        if not r["line_id"].startswith("G"):
            continue
        pts = geo.parse_wkt(r["geometry_wkt"])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col[r["line_id"]],
                lw={"metro": 2.6, "commuter": 2.0, "brt": 1.6, "streetcar": 1.6}[mode[r["line_id"]]],
                ls="--" if mode[r["line_id"]] == "commuter" else "-")
    for c in urban + towns:
        mk = {"downtown": ("*", 160), "major": ("o", 50), "minor": ("o", 20), "town": ("s", 18)}[c.kind]
        ax.scatter([c.lon], [c.lat], marker=mk[0], s=mk[1], c="#000" if c.kind != "town" else "#777", zorder=5)
        if c.kind in ("downtown", "major"):
            ax.annotate(c.name, (c.lon, c.lat), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_aspect(1 / math.cos(math.radians(m.lat0)))
    if sel.any():   # frame the populated area, not the whole bounding box
        lo, hi = np.percentile(m.lon[sel], [1, 99]), np.percentile(m.lat[sel], [1, 99])
        ax.set_xlim(lo[0] - 0.08, lo[1] + 0.08)
        ax.set_ylim(hi[0] - 0.08, hi[1] + 0.08)
    ax.set_title(f"{metro_name(m)}: generated network (metro solid, BRT thin, regional rail dashed; "
                 "grey = today)", fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(os.path.join(out, "preview.png"))
    plt.close(fig)
