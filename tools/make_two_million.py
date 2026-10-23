"""Rebuild scenarios/two_million's network tables from the expansion package.

    python tools/make_two_million.py && python -m dfwt schedule --scenario two_million --write

The 2M scenario is the plan plus lever_expand_package's new lines (tools/gen_expansion.py),
stored as additions: *.add.csv for new lines, stations, transfers; *.patch.csv for the plan
lines the package changes (infill stops); stages.csv (the plan's stages plus the new lines')
is then rescheduled into exact years.
Lines listed in scenarios/two_million/drop_lines.txt (weak corridors) are left out,
with the stations and transfers only they used; hand-authored lines in
scenarios/two_million/extra/ (full-table format) are added, or replace a plan line whole. Its config.json (policies) and
edits.csv (service) are left as they are.
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
    drop_path = os.path.join(OUT, "drop_lines.txt")
    drop = set()
    if os.path.exists(drop_path):
        drop = {ln.split("#")[0].strip() for ln in open(drop_path, encoding="utf-8")} - {""}
    for t in ("lines.csv", "line_stops.csv", "line_segments.csv", "stages.csv"):
        pkg[t] = [r for r in pkg[t] if r["line_id"] not in drop]
    # hand-authored lines (scenarios/two_million/extra/, full-table format): new lines, or
    # whole replacements of a plan line (its stops, segments and stages)
    extra = {}
    xdir = os.path.join(OUT, "extra")
    for t in ("lines.csv", "stations.csv", "transfers.csv", "line_stops.csv", "line_segments.csv", "stages.csv"):
        if os.path.exists(os.path.join(xdir, t)):
            with open(os.path.join(xdir, t), encoding="utf-8-sig") as f:
                extra[t] = list(csv.DictReader(f))
    for t, rows in extra.items():
        if t in KEYS:
            keys = {tuple(r[x] for x in KEYS[t]) for r in rows}
            pkg[t] = [r for r in pkg[t] if tuple(r[x] for x in KEYS[t]) not in keys] + rows
        else:
            ids = {r["line_id"] for r in rows}
            pkg[t] = [r for r in pkg[t] if r["line_id"] not in ids] + rows
    used = {r["station_id"] for r in pkg["line_stops.csv"]} | {r["station_id"] for r in extra.get("stations.csv", [])}
    pkg["stations.csv"] = [r for r in pkg["stations.csv"] if r["station_id"] in used]
    pkg["transfers.csv"] = [r for r in pkg["transfers.csv"] if r["station_a"] in used and r["station_b"] in used]
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
    restaged = {r["line_id"] for r in extra.get("stages.csv", []) if r["line_id"] in base_lines}
    # a full table (the plan's stages, then the new lines'), which `schedule --write` replaces in place
    # the plan's stages, with stop references as the package renumbered them ('#seq' moves past infill stops)
    pstops = {(r["line_id"], r["stage"]): (r["from_stop"], r["to_stop"]) for r in pkg["stages.csv"]}
    base_stages = [dict(r, **dict(zip(("from_stop", "to_stop"), pstops.get((r["line_id"], r["stage"]), (r["from_stop"], r["to_stop"])))))
                   for r in base["stages.csv"]]
    stages = ([r for r in base_stages if r["line_id"] not in restaged]
              + [r for r in extra.get("stages.csv", []) if r["line_id"] in restaged] + new_stages)
    # stages.csv is what `schedule --write` replaces; stages.unscheduled.csv is where every
    # schedule starts from, so the result doesn't depend on the last one
    stages = [r for r in stages if r["line_id"] not in drop]   # a plan line left out (drop_line in edits.csv)
    for name in ("stages.csv", "stages.unscheduled.csv"):
        write(name, stages, list(pkg["stages.csv"][0].keys()))
    print(f"two_million: {len(new_stages)} new stages ({len(drop)} corridors left out); now run python -m dfwt schedule --scenario two_million --write")


if __name__ == "__main__":
    main()
