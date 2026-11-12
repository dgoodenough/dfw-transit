"""DFW Transit's map page for a generated metro (texas-transit study/site_parity.md, phase 2).

    from metro import pages
    pages.build("houston", scenarios={"ratio": {"G05": 2031, ...}, ...}, labels={...}, out_html=..., site={...})

The page is DFW's (dfwt/webmap.py and its template): line and station pages, the year slider over each
scenario, the door-to-door trip planner, the data layers and the diagram, all read from the model, so the page
can't drift from it. What makes it the metro's:

  the model     the metro's own zones, commute flows, ridership constant, growth, border crossers and policy
                package, rebuilt as the generator built them (model_setup: the same centers, metro_cfg and
                constant; the constant is the one the run fitted, read from its summary.json)
  the network   the generated folder's tables (generated/<id>/: today's lines and the plan's), named
                (metro/names.py)
  scenarios     each a staging of that network: every line opens in the year the scenario gives it (a line it
                doesn't give never opens; today's lines are open from the start)
  the years     YEARS, a decade grid (DFW's page runs every year; ten runs per scenario keep a big metro's
                build to minutes)
"""
import copy
import json
import os

from dfwt import config, evaluate, webmap

from . import anchors as anchors_mod, centers, inputs, model, output

YEARS = [2025, 2030, 2035, 2040, 2050, 2060, 2070, 2080, 2090, 2100]
NEVER = 9999


def model_setup(metro_id, asc, policies=None, budget_musd_per_year=None, years=YEARS, log=None):
    """(m, cfg, ctx): the metro's inputs, the config its generation run used and a model context on its zones."""
    from .generate import params, registry_entry
    m = inputs.load(metro_id)
    entry = registry_entry(metro_id, m)
    gp = params(metro_id)
    cp = gp["centers"]
    surf = centers.Surface(m, cp["grid_km"], cp["kernel_km"])
    urban = centers.find(m, surf, cp)
    centers.classify(m, urban, cp)
    if not m.jobs_ok or m.jobs_proxy:
        centers.registry_downtowns(m, surf, urban, cp)
    for c in anchors_mod.apply(m, urban, entry.get("anchors"), cp, log=None):
        c.name = c.anchor_name
    for c in urban:
        c.name = getattr(c, "name", None) or c.id
    cfg = model.metro_cfg(m, urban, config.load(), growth=entry.get("growth"))
    if entry.get("border"):
        cfg["demand"]["border"] = entry["border"]
    if policies:
        config.merge(cfg, copy.deepcopy(policies))
    cfg["ridership"]["asc"] = float(asc)
    cfg["years"] = list(years)
    if budget_musd_per_year:
        cfg["budget"]["musd_per_year"] = float(budget_musd_per_year)
    with model.projection(m):
        ctx = model.context(m, cfg)
    return m, cfg, ctx


def staged(folder, open_years):
    """The generated tables with each proposed line opening in open_years[line_id] (absent: never)."""
    t = {k: inputs.read_csv(os.path.join(folder, k)) if os.path.exists(os.path.join(folder, k)) else []
         for k in inputs.TABLES}
    status = {r["line_id"]: r["status"] for r in t["lines.csv"]}
    for k in ("line_stops.csv", "line_segments.csv"):
        for r in t[k]:
            if status.get(r["line_id"]) != "existing":
                r["year_opens"] = str(open_years.get(r["line_id"], NEVER))
    return t


def site_for(m, entry, title, sub, back_href, back_text, layers_url):
    """The page's region settings (webmap.write site=): view, address box, diagram labels."""
    gz = os.path.join(m.folder, "gazetteer.json")
    towns = []
    if os.path.exists(gz):
        for e in json.load(open(gz, encoding="utf-8"))["elements"]:
            t = e.get("tags", {})
            if t.get("place") == "town" and t.get("population"):
                towns.append((t["population"], t["name"], e["lat"], e["lon"]))
    down = [(a["name"], a["lat"], a["lon"]) for a in entry.get("anchors") or [] if a.get("kind") == "downtown"]
    cities = (down[:1] or [(m.id, float(m.lat0), float(m.lon0))]) + \
        [(n, la, lo) for _, n, la, lo in sorted(towns, reverse=True)[1:6]]
    lat, lon = (down[0][1], down[0][2]) if down else (float(m.lat0), float(m.lon0))
    pad = 0.15
    box = [round(float(m.lon.min()) - pad, 2), round(float(m.lat.min()) - pad, 2),
           round(float(m.lon.max()) + pad, 2), round(float(m.lat.max()) + pad, 2)]
    return {"title": title, "short": title.replace(" Transit", ""), "sub": sub, "center": (lat, lon), "zoom": 10,
            "geo_box": box, "regions": {"all": "Lines"}, "region_of": lambda stations, stop_ids: "all",
            "cities": cities, "waterways": "", "back_href": back_href, "back_text": back_text, "layers_url": layers_url}


def build(metro_id, scenarios, labels, out_html, folder=None, asc=None, policies=None, budget_musd_per_year=None,
          title=None, sub="", back_href="../index.html", back_text="The statewide plan", start_year=None, log=print):
    """Evaluate each scenario of the metro's network on its own model and write the DFW-style page.
    scenarios: {key: {line_id: opening year}}; labels: {key: label}. Returns the page's path."""
    from .generate import registry_entry
    folder = folder or inputs.home("generated", metro_id)
    summ = json.load(open(os.path.join(folder, "summary.json"), encoding="utf-8"))
    years = list(YEARS)
    if not any(r["status"] == "existing" for r in inputs.read_csv(os.path.join(folder, "lines.csv"))):
        # no line the model runs today: the page starts when every scenario has one open (a year with no
        # station has nothing to model)
        first = max(min(v.values()) for v in scenarios.values() if v)
        years = [first] + [y for y in YEARS if y > first]
    m, cfg, ctx = model_setup(metro_id, asc if asc is not None else summ["asc"], policies, budget_musd_per_year, years)
    entry = registry_entry(metro_id, m)
    base = os.path.splitext(os.path.basename(out_html))[0]
    site = site_for(m, entry, title or f"{summ.get('name', metro_id).split(',')[0].split('-')[0]} Transit", sub,
                    back_href, back_text, f"{base}_layers/")
    site["labels"] = labels
    site["start_year"] = start_year
    site["layers_dir"] = os.path.join(os.path.dirname(out_html), f"{base}_layers")
    nets, evals = {}, {}
    with model.projection(m):
        site["zones"] = ctx.zones
        for key, years in scenarios.items():
            net = output.load_net(staged(folder, years), cfg, key)
            log(f"  {metro_id} {key}: evaluating {len(net.lines)} lines in {len(cfg['years'])} years ...")
            evals[key] = evaluate.evaluate(ctx, net, line_values=False, log=lambda *a: None)
            nets[key] = net
        cfg["default_scenario"] = next(iter(scenarios))
        webmap.write(nets, evals, out_html, site=site)
    log(f"  wrote {out_html}")
    return out_html
