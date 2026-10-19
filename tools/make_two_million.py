"""Rebuild scenarios/two_million's network tables from the expansion package.

    python tools/make_two_million.py && python -m dfwt schedule --scenario two_million --write

The 2M scenario is the plan plus lever_expand_package's new lines (tools/gen_expansion.py),
stored as additions: *.add.csv for new lines, stations, transfers; *.patch.csv for the plan
lines the package changes (infill stops); stages.csv is then rescheduled into exact years.
Its config.json (policies) and edits.csv (service) are left as they are.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config  # noqa: E402
from dfwt.network import Network  # noqa: E402

OUT = config.path("scenarios", "two_million")
KEYS = {"lines.csv": ("line_id",), "stations.csv": ("station_id",), "transfers.csv": ("station_a", "station_b")}


def write(name, rows, fields):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    for n in os.listdir(OUT):
        if n.endswith((".add.csv", ".patch.csv")) or n == "stages.csv":
            os.remove(os.path.join(OUT, n))
    base, _ = Network.read_tables(None)
    pkg, _ = Network.read_tables("lever_expand_package")
    base_lines = {r["line_id"] for r in base["lines.csv"]}
    for t, k in KEYS.items():
        have = {tuple(r[x] for x in k) for r in base[t]}
        new = [r for r in pkg[t] if tuple(r[x] for x in k) not in have]
        if new:
            write(t[:-4] + ".add.csv", new, list(pkg[t][0].keys()))
    for t in ("line_stops.csv", "line_segments.csv"):
        bmap = {(r["line_id"], r["seq"]): r for r in base[t]}
        changed = {r["line_id"] for r in pkg[t] if r["line_id"] in base_lines and bmap.get((r["line_id"], r["seq"])) != r}
        rows = [r for r in pkg[t] if r["line_id"] not in base_lines or r["line_id"] in changed]
        write(t[:-4] + ".patch.csv", rows, list(pkg[t][0].keys()))
    new_stages = [r for r in pkg["stages.csv"] if r["line_id"] not in base_lines]
    write("stages.add.csv", new_stages, list(pkg["stages.csv"][0].keys()))
    print(f"two_million: {len(new_stages)} new stages; now run python -m dfwt schedule --scenario two_million --write")


if __name__ == "__main__":
    main()
