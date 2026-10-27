"""`python -m metro fetch <id>`: gather one metro's inputs into data/metros/<id>/.

Stages (all by default, or pick with --only):
  zones     CenPop 2020 block-group population + centres, TIGER 2020 land area,
            LODES8 WAC jobs  -> zones.csv  (and checks the CBSA county list)
  od        LODES8 OD main+aux, aggregated to tract pairs -> od_tracts.csv
  gtfs      Mobility Database catalog -> GTFS zips -> existing/*.csv
  overture  Overture transportation segments in the bbox -> osm/roads.parquet, osm/rail.parquet
  places    (off by default; --jobs-proxy places) Overture places per block group
            -> zones_places_proxy.csv, a labelled proxy, never written into zones.jobs

A blocked or missing source never stops the run: its columns/files stay empty and
meta.json records the host and error under sources.<name> and in `missing`.
Nothing is ever filled with synthetic values.
"""
import csv
import datetime as dt
import json
import os

from dfwt import config

from . import census, gtfs, lodes, mobilitydb, net, overture

STAGES = ("zones", "od", "gtfs", "overture", "places")
DEFAULT_STAGES = ("zones", "od", "gtfs", "overture")
ZONE_COLUMNS = ["geoid", "lat", "lon", "pop", "jobs", "area_km2", "county_fips"]


def registry(path=None):
    with open(path or os.path.join(os.path.dirname(__file__), "metros.json"), encoding="utf-8") as f:
        return {m["id"]: m for m in json.load(f)["metros"]}


def metro_dir(mid):
    return config.path("data", "metros", mid)


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


class Run:
    def __init__(self, m, force=False, opts=None):
        self.m, self.force, self.opts = m, force, opts or {}
        self.dir = metro_dir(m["id"])
        self.raw = os.path.join(self.dir, "raw")
        os.makedirs(self.raw, exist_ok=True)
        self.meta_path = os.path.join(self.dir, "meta.json")
        self.meta = {}
        if os.path.exists(self.meta_path):
            with open(self.meta_path, encoding="utf-8") as f:
                self.meta = json.load(f)
        self.meta["metro"] = {k: m[k] for k in m if not k.startswith("_")}
        self.meta.setdefault("sources", {})
        self.meta.setdefault("outputs", {})
        self.counties = set(m["county_fips"])

    def rawp(self, url_or_name):
        return os.path.join(self.raw, os.path.basename(url_or_name.split("?")[0]))

    def source(self, key, **kw):
        kw.setdefault("checked_at", now())
        self.meta["sources"][key] = kw
        return kw

    def output(self, name, **kw):
        kw.setdefault("written_at", now())
        self.meta["outputs"][name] = kw

    def save(self):
        self.meta["fetched_at"] = now()
        self.meta["missing"] = missing(self.meta)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2)
            f.write("\n")

    # ---------- zones ----------
    def cbsa_check(self):
        try:
            p = net.download(census.CBSA_URL, self.rawp(census.CBSA_URL), force=self.force)
            got = census.cbsa_counties(p, self.m["cbsa"])
            want = set(self.m["county_fips"])
            have = set(got["counties"])
            self.source("cbsa_delineation", status="ok", url=census.CBSA_URL, vintage="2023 (OMB Bulletin 23-01)",
                        cbsa_title=got["cbsa_title"], registry_matches=(have == want),
                        missing_from_registry=sorted(have - want), not_in_cbsa=sorted(want - have))
            if have != want:
                print(f"  WARNING: registry counties differ from the CBSA file: add {sorted(have - want)}, drop {sorted(want - have)}")
        except net.FetchError as e:
            self.source("cbsa_delineation", registry_matches=None,
                        note="county list in metros.json not verified against the delineation file", **_err(e))

    def cenpop(self):
        zones = {}
        info = []
        for st in self.m["state_fips"]:
            abbr = self.m["state_abbr"][st]
            url = census.CENPOP_URL.format(st=st)
            local = self.rawp(url)
            repo_copy = config.path("data", f"CenPop2020_BG_{abbr.upper()}.txt")
            if os.path.exists(local) and not self.force:
                path, how = local, "cache"
            elif os.path.exists(repo_copy):
                path, how = repo_copy, "repo copy"
            else:
                try:
                    path, how = net.download(url, local, force=self.force), "download"
                except net.FetchError as e:
                    info.append({"state": st, "url": url, **_err(e)})
                    continue
            z = census.parse_cenpop(path, self.counties)
            zones.update(z)
            info.append({"state": st, "url": url, "status": "ok", "read_from": how,
                         "path": os.path.relpath(path, config.ROOT), "rows": len(z)})
        self.source("cenpop2020", vintage="2020 Census (P.L. 94-171), centres of population by block group",
                    status=_status(info), files=info)
        return zones

    def tiger(self):
        area, info = {}, []
        for st in self.m["state_fips"]:
            url = census.TIGER_BG_URL.format(st=st)
            try:
                p = net.download(url, self.rawp(url), force=self.force)
                a = census.parse_tiger_bg(p, self.counties)
                area.update(a)
                info.append({"state": st, "url": url, "status": "ok", "rows": len(a)})
            except net.FetchError as e:
                info.append({"state": st, "url": url, **_err(e)})
        self.source("tiger2020_bg", vintage="TIGER/Line 2020 block groups (ALAND)", status=_status(info), files=info)
        return area

    def lodes_files(self, kind):
        """Download WAC ('wac') or OD ('od') files for every state, one common year."""
        years = [self.opts["lodes_year"]] if self.opts.get("lodes_year") else list(lodes.YEARS)
        info, paths, year = [], [], None
        for st in self.m["state_fips"]:
            ab = self.m["state_abbr"][st]
            cand_years = [year] if year else years
            parts = ["main", "aux"] if kind == "od" else [None]
            for part in parts:
                urls = [lodes.wac_url(ab, y) if kind == "wac" else lodes.od_url(ab, part, y) for y in cand_years]
                try:
                    u, p = net.first_available(urls, self.rawp, force=self.force)
                    year = year or int(u.rsplit("_", 1)[1][:4])
                    paths.append(p)
                    info.append({"state": st, "url": u, "status": "ok"})
                except net.FetchError as e:
                    info.append({"state": st, "url": urls[0], "tried": urls, **_err(e)})
        return year, paths, info

    def stage_zones(self):
        print("zones")
        self.cbsa_check()
        zones = self.cenpop()
        if not zones:
            raise SystemExit("no block groups: CenPop could not be read (see meta.json sources.cenpop2020)")
        area = self.tiger()
        year, paths, info = self.lodes_files("wac")
        jobs = {}
        if paths and all(f["status"] == "ok" for f in info):
            for p in paths:
                for g, n in lodes.aggregate_wac(p, self.counties).items():
                    jobs[g] = jobs.get(g, 0) + n
        self.source("lodes_wac", vintage=f"LODES 8, {year}, all jobs (S000/JT00, C000)" if year else None,
                    year=year, status=_status(info), files=info)
        orphan = sorted(set(jobs) - set(zones))
        rows = []
        for g in sorted(zones):
            z = zones[g]
            a = area.get(g)
            rows.append({"geoid": g, "lat": f"{z['lat']:.6f}", "lon": f"{z['lon']:.6f}", "pop": z["pop"],
                         "jobs": jobs.get(g, 0) if jobs else "", "area_km2": f"{a['aland_m2'] / 1e6:.4f}" if a else "",
                         "county_fips": z["county_fips"]})
        p = os.path.join(self.dir, "zones.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ZONE_COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        empty = [c for c in ("jobs", "area_km2") if all(r[c] == "" for r in rows)]
        self.output("zones.csv", rows=len(rows), pop=sum(r["pop"] for r in rows),
                    jobs=sum(jobs.values()) if jobs else None, jobs_in_unknown_block_groups=len(orphan),
                    by_county={c: sum(1 for r in rows if r["county_fips"] == c) for c in sorted(self.counties)},
                    empty_columns=empty)
        self.meta["bbox"] = bbox_of(rows, self.m.get("bbox_margin_deg", 0.1))
        print(f"  zones.csv: {len(rows)} block groups, pop {sum(r['pop'] for r in rows):,}"
              + (f", jobs {sum(jobs.values()):,}" if jobs else ", jobs MISSING") + ("" if area else ", area MISSING"))

    # ---------- od ----------
    def stage_od(self):
        print("od")
        year, paths, info = self.lodes_files("od")
        self.source("lodes_od", vintage=f"LODES 8, {year}, all jobs (S000)" if year else None, year=year,
                    status=_status(info), files=info)
        p = os.path.join(self.dir, "od_tracts.csv")
        if paths and all(f["status"] == "ok" for f in info):
            n = lodes.write_od(lodes.aggregate_od(paths, self.counties), p)
            self.output("od_tracts.csv", rows=n)
            print(f"  od_tracts.csv: {n} tract pairs")
        else:
            self.meta["outputs"].pop("od_tracts.csv", None)
            print("  od_tracts.csv: not written (LODES OD unavailable)")

    # ---------- gtfs ----------
    def stage_gtfs(self):
        print("gtfs")
        bbox = self.need_bbox()
        try:
            cat = net.download(mobilitydb.CATALOG_URL, self.rawp("mdb_sources.csv"), force=self.force)
        except net.FetchError as e:
            self.source("mobility_database", **_err(e))
            self.source("gtfs", status="missing", feeds=[])
            return
        rows = mobilitydb.read_catalog(cat)
        feeds = mobilitydb.select_feeds(rows, bbox, self.m.get("gtfs_include"), self.m.get("gtfs_exclude"))
        self.source("mobility_database", status="ok", url=mobilitydb.CATALOG_URL, catalog_rows=len(rows),
                    selected=[r["mdb_source_id"] for r in feeds])
        results, finfo = [], []
        cfg = config.load()
        am = self.opts.get("am", (7, 9))
        for r in feeds:
            sid = r["mdb_source_id"]
            tag = f"m{sid}"
            label = r.get("provider", "").strip()
            entry = {"mdb_source_id": sid, "provider": label, "tag": tag}
            try:
                url, p = net.first_available(mobilitydb.feed_urls(r), lambda u, s=sid: self.rawp(f"gtfs_mdb{s}.zip"),
                                             force=self.force)
            except net.FetchError as e:
                finfo.append({**entry, **_err(e)})
                continue
            tables, info = gtfs.analyze(gtfs.Feed(p), tag, am=(int(am[0] * 3600), int(am[1] * 3600)),
                                        frequent_max=self.opts.get("frequent", 15.0),
                                        brt_pattern=self.m.get("brt_name_pattern"),
                                        existing_year=cfg["existing_year"], label=label)
            results.append(tables)
            fi = {**entry, "status": "ok" if "error" not in info else "failed", "url": url,
                  "sha256": overture.sha256(p), "feed_info": _feed_info(p), **info}
            if info.get("service_date") and dt.date.fromisoformat(info["service_date"]) < dt.date.today() - dt.timedelta(days=365):
                fi["warning"] = "stale: the feed's weekday service is over a year old; it may not match today's service"
            v = fi.get("feed_info") or {}
            if (v.get("feed_start_date") or "").isdigit() and (v.get("feed_end_date") or "").isdigit():
                days = (dt.datetime.strptime(v["feed_end_date"], "%Y%m%d") - dt.datetime.strptime(v["feed_start_date"], "%Y%m%d")).days
                if days < 60:
                    fi["warning"] = (fi.get("warning", "") + "; " if fi.get("warning") else "") + (
                        f"short validity window ({days} days, version {v.get('feed_version')!r}): may be a special-event "
                        "or seasonal schedule rather than regular service")
            finfo.append(fi)
            print(f"  {label}: service date {info.get('service_date')}, {info.get('lines', 0)} lines kept "
                  f"of {info.get('routes_considered', 0)} routes")
        self.source("gtfs", status=_status(finfo) if finfo else "missing", feeds=finfo)
        counts = gtfs.write_tables(gtfs.merge(results), os.path.join(self.dir, "existing"))
        for k, n in counts.items():
            self.output(f"existing/{k}", rows=n)

    # ---------- overture ----------
    def stage_overture(self):
        print("overture")
        bbox = self.need_bbox()
        rel = overture.resolve_release(self.opts.get("overture_release"))
        files = {"roads.parquet": ("road", overture.ROAD_CLASSES), "rail.parquet": ("rail", None)}
        out = {}
        for name, (subtype, classes) in files.items():
            p = os.path.join(self.dir, "osm", name)
            prev = self.meta["sources"].get("overture_transportation", {})
            try:
                if (os.path.exists(p) and not self.force and prev.get("release") == rel
                        and prev.get("bbox") == list(bbox)):
                    import pyarrow.parquet as pq
                    n = pq.read_metadata(p).num_rows
                    print(f"  overture {subtype}: {n} segments (cached; --force to refetch)")
                else:
                    n = overture.fetch_segments(rel, bbox, subtype, classes, p)
                out[name] = {"subtype": subtype, "classes": classes, "rows": n, "sha256": overture.sha256(p)}
                self.output(f"osm/{name}", rows=n)
            except Exception as e:   # pyarrow raises OSError subclasses for S3 failures
                out[name] = {"status": "failed", "error": str(e)[:300]}
        self.source("overture_transportation", status="ok" if all("rows" in v for v in out.values()) else "failed",
                    release=rel, url=overture.source_url(rel, "theme=transportation/type=segment"),
                    license="© OpenStreetMap contributors, ODbL 1.0 (via Overture Maps Foundation)",
                    bbox=bbox, files=out)

    # ---------- places proxy (opt-in) ----------
    def stage_places(self):
        print("places (job-location proxy, opt-in)")
        bbox = self.need_bbox()
        rel = overture.resolve_release(self.opts.get("overture_release"))
        p = os.path.join(self.raw, "overture_places.parquet")
        try:
            if self.force or not os.path.exists(p):
                overture.fetch_places(rel, bbox, p)
        except Exception as e:
            self.source("overture_places", status="failed", release=rel, error=str(e)[:300])
            return
        import pyarrow.parquet as pq
        t = pq.read_table(p, columns=["lon", "lat"])
        pts = list(zip(t.column("lon").to_pylist(), t.column("lat").to_pylist()))
        zones = read_zones(os.path.join(self.dir, "zones.csv"))
        counts, dropped = overture.nearest_zone_counts([(float(z["lon"]), float(z["lat"])) for z in zones], pts)
        out = os.path.join(self.dir, "zones_places_proxy.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["geoid", "places"])
            for z, n in zip(zones, counts):
                w.writerow([z["geoid"], n])
        self.source("overture_places", status="ok", release=rel, url=overture.source_url(rel, "theme=places/type=place"),
                    rows=len(pts), assigned=sum(counts), ignored_over_5km=dropped, license="Overture Maps places theme, CDLA Permissive 2.0",
                    method="open places with confidence >= 0.5 in the bbox, each assigned to the nearest block-group "
                           "centre of population within 5 km (no block-group polygons available, so places just "
                           "outside the counties can land in edge zones); a proxy for where jobs are, NOT a job count")
        self.output("zones_places_proxy.csv", rows=len(zones), places=sum(counts), proxy=True)

    def need_bbox(self):
        if "bbox" not in self.meta:
            p = os.path.join(self.dir, "zones.csv")
            if not os.path.exists(p):
                raise SystemExit("run the zones stage first (it sets the bbox)")
            self.meta["bbox"] = bbox_of(read_zones(p), self.m.get("bbox_margin_deg", 0.1))
        return tuple(self.meta["bbox"])


def read_zones(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def bbox_of(rows, margin):
    lon = [float(r["lon"]) for r in rows]
    lat = [float(r["lat"]) for r in rows]
    return [round(min(lon) - margin, 4), round(min(lat) - margin, 4), round(max(lon) + margin, 4), round(max(lat) + margin, 4)]


def _err(e):
    return e.as_meta() if isinstance(e, net.FetchError) else {"status": "failed", "error": str(e)}


def _status(items):
    s = {i.get("status") for i in items}
    if s == {"ok"}:
        return "ok"
    if "blocked" in s:
        return "blocked"
    return "failed" if s else "missing"


def _feed_info(path):
    try:
        f = gtfs.Feed(path)
        r = next(f.table("feed_info.txt"), None)
        return {k: r.get(k) for k in ("feed_publisher_name", "feed_version", "feed_start_date", "feed_end_date")} if r else None
    except Exception:
        return None


def missing(meta):
    """What the contract asks for that this run could not supply, and why."""
    out = []
    src, outs = meta.get("sources", {}), meta.get("outputs", {})

    def why(key):
        s = src.get(key, {})
        hosts = sorted({f.get("host") for f in s.get("files", []) if f.get("host")} | ({s["host"]} if s.get("host") else set()))
        if s.get("status") == "blocked":
            return f"host blocked by network policy: {', '.join(hosts)}"
        return s.get("error") or s.get("status") or "not fetched"

    z = outs.get("zones.csv", {})
    if "jobs" in z.get("empty_columns", []):
        out.append({"item": "zones.csv jobs", "source": "lodes_wac", "why": why("lodes_wac")})
    if "area_km2" in z.get("empty_columns", []):
        out.append({"item": "zones.csv area_km2", "source": "tiger2020_bg", "why": why("tiger2020_bg")})
    if "od_tracts.csv" not in outs:
        out.append({"item": "od_tracts.csv", "source": "lodes_od", "why": why("lodes_od")})
    g = src.get("gtfs", {})
    if g.get("status") != "ok":
        bad = [f"{f.get('provider')}: {f.get('error') or f.get('status')}" for f in g.get("feeds", []) if f.get("status") != "ok"]
        out.append({"item": "existing/", "source": "gtfs", "why": "; ".join(bad) or why("mobility_database")})
    if src.get("cbsa_delineation", {}).get("registry_matches") is not True:
        out.append({"item": "CBSA county list verification", "source": "cbsa_delineation", "why": why("cbsa_delineation")})
    for k in ("roads.parquet", "rail.parquet"):
        if f"osm/{k}" not in outs:
            out.append({"item": f"osm/{k}", "source": "overture_transportation", "why": why("overture_transportation")})
    return out


def run(mid, stages=DEFAULT_STAGES, force=False, **opts):
    reg = registry()
    if mid not in reg:
        raise SystemExit(f"unknown metro {mid!r}; known: {', '.join(sorted(reg))} (metro/metros.json)")
    r = Run(reg[mid], force=force, opts=opts)
    for s in STAGES:
        if s in stages:
            getattr(r, f"stage_{s}")()
            r.save()
    print(f"wrote {os.path.relpath(r.dir, config.ROOT)}/ (meta.json: {len(r.meta['missing'])} missing item(s))")
    for m in r.meta["missing"]:
        print(f"  MISSING {m['item']}: {m['why']}")
    return r.meta
