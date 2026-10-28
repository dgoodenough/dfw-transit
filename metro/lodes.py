"""LEHD LODES 8 (2020 Census blocks): workplace jobs (WAC) and home->work flows (OD).

WAC  <st>_wac_S000_JT00_<year>.csv.gz   w_geocode (15-digit block), C000 = all jobs
OD   <st>_od_main_JT00_<year>.csv.gz    home and work both in <st>
     <st>_od_aux_JT00_<year>.csv.gz     work in <st>, home in another state
     columns w_geocode, h_geocode, S000 = all jobs
"""
import collections
import csv
import gzip

BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"
# Newest first; the fetcher takes the first year the server has (LODES8 currently runs 2002-2022/23).
YEARS = (2024, 2023, 2022, 2021)


def wac_url(st, year):
    return f"{BASE}/{st}/wac/{st}_wac_S000_JT00_{year}.csv.gz"


def od_url(st, part, year):
    return f"{BASE}/{st}/od/{st}_od_{part}_JT00_{year}.csv.gz"


def _rows(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def aggregate_wac(path, counties):
    """WAC file -> {block-group geoid12: jobs} for blocks in `counties` (5-digit FIPS)."""
    out = collections.Counter()
    for r in _rows(path):
        g = r["w_geocode"]
        if g[:5] in counties:
            out[g[:12]] += int(r["C000"])
    return dict(out)


def aggregate_od(paths, counties):
    """OD files -> {(home_tract11, work_tract11): jobs}, both ends in `counties`."""
    out = collections.Counter()
    for p in paths:
        for r in _rows(p):
            h, w = r["h_geocode"], r["w_geocode"]
            if h[:5] in counties and w[:5] in counties:
                out[(h[:11], w[:11])] += int(r["S000"])
    return dict(out)


def write_od(od, path):
    """Same columns dfwt reads (config demand.lodes_od_path): h_tract, w_tract, jobs."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["h_tract", "w_tract", "jobs"])
        for (h, wk), n in sorted(od.items()):
            w.writerow([h, wk, n])
    return len(od)
