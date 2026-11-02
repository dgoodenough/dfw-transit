"""Jobs by sector for the non-commute trip model (config ridership.nonwork): LEHD LODES 8
workplace area characteristics (WAC, all jobs, 2022), summed from blocks to the block groups of
data/metroplex_density.csv and grouped the way trip attraction models group employment
(NCHRP Report 365 / 716): retail (NAICS 44-45 retail trade, CNS07, plus 72 accommodation and
food services, CNS18), service (NAICS 51-56, 61, 62, 71, 81, 92: CNS09-CNS17, CNS19, CNS20) and
basic (the rest: farming, mining, utilities, construction, manufacturing, wholesale,
transport and warehousing, CNS01-CNS06, CNS08). Writes data/lodes_wac_sectors_bg_2022.csv
(columns geoid, jobs, retail, service, basic, arts, food, education, health).

    python tools/fetch_wac.py
"""
import collections
import csv
import gzip
import io
import os
import urllib.request

URL = "https://lehd.ces.census.gov/data/lodes/LODES8/tx/wac/tx_wac_S000_JT00_2022.csv.gz"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "lodes_wac_sectors_bg_2022.csv")
GROUPS = {
    "retail": ("CNS07", "CNS18"),
    "service": ("CNS09", "CNS10", "CNS11", "CNS12", "CNS13", "CNS14", "CNS15", "CNS16", "CNS17", "CNS19", "CNS20"),
    "basic": ("CNS01", "CNS02", "CNS03", "CNS04", "CNS05", "CNS06", "CNS08"),
    "arts": ("CNS17",),        # arts, entertainment and recreation (detail, inside service)
    "food": ("CNS18",),        # accommodation and food services (detail, inside retail)
    "education": ("CNS15",),
    "health": ("CNS16",),
}


def main(src=None):
    with open(os.path.join(ROOT, "data", "metroplex_density.csv"), encoding="utf-8-sig") as f:
        bgs = [r["geoid"] for r in csv.DictReader(f)]
    want = set(bgs)
    tot = collections.defaultdict(lambda: collections.Counter())
    opener = (lambda: open(src, "rb")) if src else (lambda: urllib.request.urlopen(URL))
    with opener() as resp, gzip.open(io.BufferedReader(resp), "rt") as f:
        for r in csv.DictReader(f):
            bg = r["w_geocode"][:12]
            if bg not in want:
                continue
            c = tot[bg]
            c["jobs"] += int(r["C000"])
            for g, cols in GROUPS.items():
                c[g] += sum(int(r[k]) for k in cols)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["geoid", "jobs", *GROUPS])
        for bg in bgs:
            c = tot.get(bg, collections.Counter())
            w.writerow([bg, c["jobs"], *(c[g] for g in GROUPS)])
    print(f"{OUT}: {len(bgs):,} block groups, {sum(c['jobs'] for c in tot.values()):,} jobs")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
