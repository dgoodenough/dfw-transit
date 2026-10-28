"""Step-1 inputs as the network generator reads them (the data contract).

data/metros/<id>/
  zones.csv            geoid, lat, lon, pop, jobs, area_km2, county_fips   (2020 block groups;
                       jobs may be blank while LEHD is unreachable)
  od_tracts.csv        h_tract, w_tract, jobs                              (optional, LODES)
  existing/            today's transit in dfwt table format (optional)
  osm/roads.parquet    Overture road segments  (the schema dfwt/osmroute.py reads)
  osm/rail.parquet     Overture rail segments
  meta.json            bbox, sources, ...

`load(metro_id)` returns a `Metro`. Nothing here invents data: a missing jobs column
is reported (`jobs_ok` False) and the generator switches to population-only scoring.

`adapt_dfw()` writes DFW's existing inputs (data/metroplex_density.csv, data/osm,
the existing lines of network/ via scenarios/current_track) in the contract shape, so
the generator can be run end to end on the one metro that has everything today.
"""
import csv
import json
import math
import os

import numpy as np

from dfwt import config

TABLES = {
    "lines.csv": ["line_id", "name", "mode", "status", "color", "headway_min", "notes"],
    "stations.csv": ["station_id", "name", "lat", "lon"],
    "line_stops.csv": ["line_id", "seq", "station_id", "year_opens"],
    "line_segments.csv": ["line_id", "seq", "year_opens", "grade", "geometry_source", "locked", "geometry_wkt"],
    "transfers.csv": ["station_a", "station_b", "walk_min", "note"],
}


def metro_dir(metro_id, *parts):
    return config.path("data", "metros", metro_id, *parts)


def read_csv(path):
    csv.field_size_limit(1 << 28)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _num(s):
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


class Metro:
    """One metro's inputs. Arrays are per zone (block group)."""

    def __init__(self, metro_id, folder, zones, meta, existing, osm, od_path=None):
        self.id, self.folder, self.meta = metro_id, folder, meta
        self.geoid = [z["geoid"] for z in zones]
        self.lat = np.array([float(z["lat"]) for z in zones])
        self.lon = np.array([float(z["lon"]) for z in zones])
        self.pop = np.array([_num(z.get("pop")) or 0.0 for z in zones])
        jobs = [_num(z.get("jobs")) for z in zones]
        n_jobs = sum(j is not None for j in jobs)
        # jobs count as available when (nearly) every zone has a number and they don't all
        # read zero; otherwise population-only scoring, flagged in every output
        self.jobs_ok = n_jobs >= 0.95 * len(zones) and sum(j or 0 for j in jobs) > 0
        self.jobs = np.array([j or 0.0 for j in jobs]) if self.jobs_ok else np.zeros(len(zones))
        self.jobs_note = "" if self.jobs_ok else (
            f"jobs missing for {len(zones) - n_jobs:,} of {len(zones):,} zones: population-only scoring")
        self.area = np.array([_num(z.get("area_km2")) or np.nan for z in zones])
        self.county = [z.get("county_fips") or z["geoid"][:5] for z in zones]
        self.existing = existing          # {table name: rows} or None
        self.osm = osm                    # {"roads": path or None, "rail": path or None}
        self.od_path = od_path
        self.jobs_proxy = None           # a note when jobs are a proxy (load(..., jobs_proxy="places"))
        w = self.pop + self.jobs
        # projection origin: the activity-weighted centre (equirectangular, km)
        self.lat0 = float(np.average(self.lat, weights=w)) if w.sum() else float(self.lat.mean())
        self.lon0 = float(np.average(self.lon, weights=w)) if w.sum() else float(self.lon.mean())
        self.kx = math.radians(1) * 6371.0088 * math.cos(math.radians(self.lat0))
        self.ky = math.radians(1) * 6371.0088
        self.x, self.y = self.xy(self.lat, self.lon)

    @property
    def n(self):
        return len(self.geoid)

    @property
    def activity(self):
        return self.pop + self.jobs

    def xy(self, lat, lon):
        return ((np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky)

    def ll(self, x, y):
        return (np.asarray(y) / self.ky + self.lat0, np.asarray(x) / self.kx + self.lon0)

    def status(self):
        """What is there and what is missing, for the report."""
        out = [f"{self.n:,} zones, {self.pop.sum() / 1e6:.2f}M people, "
               + (f"{self.jobs.sum() / 1e6:.2f}M jobs" if self.jobs_ok else "NO JOBS DATA")]
        if not self.jobs_ok:
            out.append(self.jobs_note)
        if self.jobs_proxy:
            out.append(self.jobs_proxy)
        out.append("existing transit: " + (f"{len(self.existing['lines.csv'])} lines" if self.existing else "none given"))
        for k in ("roads", "rail"):
            out.append(f"osm {k}: " + (os.path.relpath(self.osm[k], config.ROOT) if self.osm.get(k) else "MISSING"))
        out.append("commute flows: " + ("LODES tract OD" if self.od_path else "gravity model (no od_tracts.csv)"))
        return out


JOBS_PER_RESIDENT = 0.53   # US: ~160M jobs / ~330M residents (BLS, Census); used only by the opt-in proxy


def load(metro_id, jobs_proxy=None):
    """The metro's inputs. jobs_proxy="places" (opt-in, flagged everywhere): when zones.csv has
    no jobs, use zones_places_proxy.csv (Overture places per block group, from step 1's
    --jobs-proxy places) as the *spatial distribution* of jobs, scaled to JOBS_PER_RESIDENT x
    population. Where jobs are is then a proxy; how many is an assumption, not data."""
    folder = metro_dir(metro_id)
    if metro_id == "dfw" and not os.path.exists(os.path.join(folder, "zones.csv")):
        adapt_dfw()
    zp = os.path.join(folder, "zones.csv")
    if not os.path.exists(zp):
        raise SystemExit(f"{os.path.relpath(zp, config.ROOT)} is missing: run step 1 (python -m metro fetch {metro_id}) first")
    zones = [z for z in read_csv(zp) if _num(z.get("lat")) is not None and _num(z.get("lon")) is not None]
    proxy_note = None
    if jobs_proxy == "places":
        pp = os.path.join(folder, "zones_places_proxy.csv")
        if not os.path.exists(pp):
            raise SystemExit(f"--jobs-proxy places: {os.path.relpath(pp, config.ROOT)} is missing "
                             f"(python -m metro fetch {metro_id} --jobs-proxy places)")
        if sum(_num(z.get("jobs")) is not None for z in zones) >= 0.95 * len(zones):
            raise SystemExit("--jobs-proxy places: zones.csv has jobs; the proxy is only for metros without them")
        places = {r["geoid"]: _num(r.get("places")) or 0.0 for r in read_csv(pp)}
        tot_p = sum(places.get(z["geoid"], 0.0) for z in zones)
        tot_pop = sum(_num(z.get("pop")) or 0.0 for z in zones)
        if tot_p <= 0:
            raise SystemExit("--jobs-proxy places: the proxy file has no places")
        k = JOBS_PER_RESIDENT * tot_pop / tot_p
        zones = [dict(z, jobs=str(places.get(z["geoid"], 0.0) * k)) for z in zones]
        proxy_note = (f"JOBS ARE A PROXY: Overture places per block group (zones_places_proxy.csv, {tot_p:,.0f} places) "
                      f"scaled to {JOBS_PER_RESIDENT} jobs per resident; where jobs are is approximate, how many is "
                      "an assumption, not LODES data")
    meta = {}
    if os.path.exists(os.path.join(folder, "meta.json")):
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
    existing = None
    ed = os.path.join(folder, "existing")
    if os.path.exists(os.path.join(ed, "lines.csv")):
        existing = {t: (read_csv(os.path.join(ed, t)) if os.path.exists(os.path.join(ed, t)) else [])
                    for t in TABLES}
        if not existing["lines.csv"]:
            existing = None
    osm = {}
    for k in ("roads", "rail"):
        p = os.path.join(folder, "osm", f"{k}.parquet")
        osm[k] = p if os.path.exists(p) else None
    od = os.path.join(folder, "od_tracts.csv")
    m = Metro(metro_id, folder, zones, meta, existing, osm, od if os.path.exists(od) else None)
    m.jobs_proxy = proxy_note
    return m


# ---------------------------------------------------------------- DFW adapter
def adapt_dfw(out=None):
    """DFW in the contract shape: data/metros/dfw/ (zones.csv, existing/, osm/ links, meta.json).

    zones: data/metroplex_density.csv (2020 block-group population, 2022 LODES jobs; no land
    area in that file, so area_km2 is left blank). existing: every line of scenarios/current_track
    (today's DART, TRE, TEXRail, A-train, Silver Line, streetcars) as running today. osm: links to
    data/osm/*.parquet."""
    from dfwt.network import Network
    out = out or metro_dir("dfw")
    os.makedirs(os.path.join(out, "existing"), exist_ok=True)
    rows = read_csv(config.path("data", "metroplex_density.csv"))
    write_csv(os.path.join(out, "zones.csv"),
              [{"geoid": r["geoid"], "lat": r["lat"], "lon": r["lon"], "pop": r["pop"], "jobs": r["jobs"],
                "area_km2": "", "county_fips": r["geoid"][:5]} for r in rows],
              ["geoid", "lat", "lon", "pop", "jobs", "area_km2", "county_fips"])
    with open(os.path.join(out, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("# generated by metro.inputs.adapt_dfw from files already in the repo\n*\n")
    net = Network.load("current_track")
    t = export_tables(net, status="existing", max_year=net.cfg["existing_year"])
    for name, fields in TABLES.items():
        write_csv(os.path.join(out, "existing", name), t[name], fields)
    osm_dir = os.path.join(out, "osm")
    os.makedirs(osm_dir, exist_ok=True)
    for k in ("roads", "rail"):
        src = config.path("data", "osm", f"{k}.parquet")
        dst = os.path.join(osm_dir, f"{k}.parquet")
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(os.path.relpath(src, osm_dir), dst)
    lat = [float(r["lat"]) for r in rows]
    lon = [float(r["lon"]) for r in rows]
    meta = {"id": "dfw", "name": "Dallas-Fort Worth (nine core counties)",
            "bbox": [min(lon), min(lat), max(lon), max(lat)],
            "sources": {"zones": "data/metroplex_density.csv (2020 Census block groups, 2022 LODES WAC jobs)",
                        "existing": "scenarios/current_track (today's lines)",
                        "osm": "data/osm (Overture 2026-09-23.1)"},
            "adapter": "metro.inputs.adapt_dfw"}
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return out


def export_tables(net, status=None, lines=None, max_year=None):
    """A dfwt Network's lines as the five tables (after stages/edits are applied). With
    max_year, only what is open by then: later stops are dropped (their segments joined)."""
    t = {k: [] for k in TABLES}
    used = set()
    for lid, ln in sorted(net.lines.items()):
        if (status and ln.status != status) or (lines and lid not in lines):
            continue
        keep = [i for i, y in enumerate(ln.stop_years) if max_year is None or y <= max_year]
        if max_year is not None:
            keep = [i for i in keep if all(s.year <= max_year for s in ln.segments[min(keep):max(keep)])]
        if len(keep) < 2:
            continue
        t["lines.csv"].append({"line_id": lid, "name": ln.name, "mode": ln.mode, "status": ln.status,
                               "color": ln.color, "headway_min": f"{ln.headway:g}", "notes": ln.notes})
        for k, i in enumerate(keep):
            sid = ln.stop_ids[i]
            t["line_stops.csv"].append({"line_id": lid, "seq": k + 1, "station_id": sid, "year_opens": ln.stop_years[i]})
            used.add(sid)
        for k, (i, j) in enumerate(zip(keep, keep[1:])):
            pts = []
            for s in ln.segments[i:j]:
                pts.extend(s.pts if not pts else s.pts[1:])
            s = ln.segments[i]
            t["line_segments.csv"].append({"line_id": lid, "seq": k + 1, "year_opens": max(x.year for x in ln.segments[i:j]),
                                           "grade": s.grade, "geometry_source": "existing", "locked": "",
                                           "geometry_wkt": "LINESTRING (" + ", ".join(
                                               f"{x:.6f} {y:.6f}" for x, y in pts) + ")"})
    for sid in sorted(used):
        s = net.stations[sid]
        t["stations.csv"].append({"station_id": sid, "name": s.name, "lat": f"{s.lat:.6f}", "lon": f"{s.lon:.6f}"})
    for a, b, w, note in net.transfers:
        if a in used and b in used:
            t["transfers.csv"].append({"station_a": a, "station_b": b, "walk_min": "" if w is None else w, "note": note})
    return t
