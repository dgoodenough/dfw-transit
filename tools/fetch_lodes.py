"""Real commute flows for the demand model: LEHD LODES 8 origin-destination pairs (all jobs,
2022, both ends in Texas) summed to census-tract pairs within the nine core counties, written
to data/lodes_od_tracts_2022.csv.gz (columns h_tract, w_tract, jobs; config demand.lodes_od_path).
2022 matches the workplace jobs in data/metroplex_density.csv.

    python tools/fetch_lodes.py
"""
import collections
import csv
import gzip
import io
import os
import urllib.request

URL = "https://lehd.ces.census.gov/data/lodes/LODES8/tx/od/tx_od_main_JT00_2022.csv.gz"
COUNTIES = {"113", "439", "085", "121", "397", "251", "139", "367", "257"}   # Texas county FIPS
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "lodes_od_tracts_2022.csv.gz")


def main():
    pairs = collections.Counter()
    with urllib.request.urlopen(URL) as resp, gzip.open(io.BufferedReader(resp), "rt") as f:
        rows = csv.reader(f)
        next(rows)
        for w, h, n, *_ in rows:   # w_geocode, h_geocode, S000 (all jobs), ...
            if h[2:5] in COUNTIES and w[2:5] in COUNTIES:
                pairs[(h[:11], w[:11])] += int(n)
    # mtime=0: the same flows always give the same file
    with open(OUT, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz, \
            io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(["h_tract", "w_tract", "jobs"])
        for (h, w), n in sorted(pairs.items()):
            out.writerow([h, w, n])
    print(f"{OUT}: {len(pairs):,} tract pairs, {sum(pairs.values()):,} commutes")


if __name__ == "__main__":
    main()
