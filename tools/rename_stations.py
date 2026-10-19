"""Give stations real, unique names; keep every table that refers to them in step.

    python tools/rename_stations.py              apply network/station_renames.csv everywhere
    python tools/rename_stations.py --propose    add renames for stations that still need one, then apply
    python tools/rename_stations.py --check      list stations whose names still need work (exit 1 if any)

Many proposed stations were named automatically after the nearest place plus a
compass point ("Fair Park E10", "Irving W3"), some twice over ("Uptown" four
times within a kilometre). `--propose` renames those after their cross streets,
neighbourhood or a landmark (dfwt/naming.py, DART style: "Belt Line / Jupiter"),
and keeps one spelling per station. Names are unique across the whole set of
networks (plan and every scenario): the same name is only shared by stations
within 400 m of each other (one interchange). Stations on lines that exist
today keep their names.

The mapping lives in network/station_renames.csv:
    station_id, old_name, new_name, lat, lon, basis
A station row is renamed when its name is old_name and it lies within 200 m of
(lat, lon); station_id is for reference only (expansion scenarios reuse ids
for different stations, regenerated ones get new ids, and v1 has a few ids at
other places).

Applying rewrites the name in network/stations.csv and every
scenarios/*/stations.csv, and the references by name: stages.csv from_stop /
to_stop, edits.csv add_express stop lists, scenarios/*/corridors.json named
stops, and the "A <-> B" names in transfers.csv notes. It is idempotent: rows
already renamed no longer match an old_name.
"""
import argparse
import collections
import csv
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config, geo  # noqa: E402
from dfwt.naming import SUFFIX, keys, norm  # noqa: E402

MAP = config.path("network", "station_renames.csv")
COLS = ["station_id", "old_name", "new_name", "lat", "lon", "basis"]
MATCH_KM = 0.20       # a mapping row applies to stations of its old name this close to its point
SAME_KM = 0.06        # same name this close = the same station (regenerated under another id)
COMPLEX_KM = 0.40     # same name this close = one interchange (the diagram merges them too)


def bad_name(n):
    """A generated or unusable name."""
    return bool(SUFFIX.search(n) or "?" in n or n[:1].islower() or n.endswith("Historic District"))


# ---------------------------------------------------------------- tables
def folders():
    return [config.path("network")] + sorted(d for d in glob.glob(config.path("scenarios", "*")) if os.path.isdir(d))


def read(path):
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def write(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def table(folder, name):
    """A folder's own table, else the plan's (scenarios replace tables wholesale)."""
    own = os.path.join(folder, name)
    return own if os.path.exists(own) else config.path("network", name)


def km(lat0, lon0, lat1, lon1):
    return geo.hav_km(float(lat0), float(lon0), float(lat1), float(lon1))


def load_map():
    return read(MAP)[1] or []


def lookup(maps, name, lat, lon):
    """The mapping row for a station row, or None."""
    rows = maps.get(name)
    if not rows:
        return None
    d, i = min((km(lat, lon, m["lat"], m["lon"]), i) for i, m in enumerate(rows))
    return rows[i] if d <= MATCH_KM else None


# ---------------------------------------------------------------- apply
def apply(mapping, verbose=True):
    maps = collections.defaultdict(list)
    for m in mapping:
        if m["old_name"] != m["new_name"]:
            maps[m["old_name"]].append(m)
    changed = collections.Counter()
    renamed = {}            # folder -> {sid: (old, new)} for the folder's effective station table
    base = config.path("network")
    for folder in folders():
        path = os.path.join(folder, "stations.csv")
        fields, rows = read(path)
        if rows is None:
            continue
        ren = {}
        for r in rows:
            m = lookup(maps, r["name"], r["lat"], r["lon"])
            if m:
                ren[r["station_id"]] = (r["name"], m["new_name"])
                r["name"] = m["new_name"]
        if ren:
            write(path, fields, rows)
            changed[os.path.relpath(path, config.ROOT)] += len(ren)
        renamed[folder] = ren
    for folder in folders():
        ren = renamed.get(folder, renamed[base]) if os.path.exists(os.path.join(folder, "stations.csv")) else renamed[base]
        _, st = read(table(folder, "stations.csv"))
        names = {r["station_id"]: r["name"] for r in st}            # already renamed
        old = {sid: o for sid, (o, n) in ren.items()}
        _, ls = read(table(folder, "line_stops.csv"))
        stops = collections.defaultdict(list)
        for r in ls:
            stops[r["line_id"]].append(r["station_id"])

        def fix(ref, line_id):
            """A stop reference by name on a line, renamed if it named a renamed stop."""
            s = ref.strip()
            if not s or s.startswith("#") or s in names:
                return ref
            on = stops.get(line_id, [])
            if any(names.get(x, "").lower() == s.lower() for x in on):
                return ref
            hits = [x for x in on if old.get(x, "").lower() == s.lower()]
            return names[hits[0]] if len(set(hits)) == 1 else ref
        p = os.path.join(folder, "stages.csv")
        fields, rows = read(p)
        if rows:
            n = 0
            for r in rows:
                for c in ("from_stop", "to_stop"):
                    v = fix(r[c], r["line_id"])
                    n += v != r[c]
                    r[c] = v
            if n:
                write(p, fields, rows)
                changed[os.path.relpath(p, config.ROOT)] += n
        p = os.path.join(folder, "edits.csv")
        fields, rows = read(p)
        if rows:
            n = 0
            for r in rows:
                if r.get("op") == "add_express" and r.get("value"):
                    v = ";".join(fix(s, r["target"]) for s in r["value"].split(";"))
                    n += v != r["value"]
                    r["value"] = v
            if n:
                write(p, fields, rows)
                changed[os.path.relpath(p, config.ROOT)] += n
        p = os.path.join(folder, "transfers.csv")
        fields, rows = read(p)
        if rows and old:
            n = 0
            for r in rows:
                a, b = r["station_a"], r["station_b"]
                if (a in old or b in old) and r.get("note"):
                    oa, ob = old.get(a, names.get(a)), old.get(b, names.get(b))
                    v = r["note"].replace(f"{oa} <-> {ob}", f"{names.get(a)} <-> {names.get(b)}")
                    n += v != r["note"]
                    r["note"] = v
            if n:
                write(p, fields, rows)
                changed[os.path.relpath(p, config.ROOT)] += n
        p = os.path.join(folder, "corridors.json")
        if os.path.exists(p):
            # named stops {"name": ..., "lat": ..., "lon": ...}: edit the text in place (hand formatted)
            with open(p, encoding="utf-8") as f:
                text = f.read()
            out, pos, n = [], 0, 0
            for mt in re.finditer(r'"name"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
                ahead = text[mt.end():mt.end() + 160].split("}")[0]
                la = re.search(r'"lat"\s*:\s*(-?[\d.]+)', ahead)
                lo = re.search(r'"lon"\s*:\s*(-?[\d.]+)', ahead)
                m = la and lo and lookup(maps, json.loads(f'"{mt.group(1)}"'), la.group(1), lo.group(1))
                if m:
                    out.append(text[pos:mt.start(1)] + json.dumps(m["new_name"], ensure_ascii=False)[1:-1])
                    pos = mt.end(1)
                    n += 1
            if n:
                with open(p, "w", encoding="utf-8") as f:
                    f.write("".join(out) + text[pos:])
                changed[os.path.relpath(p, config.ROOT)] += n
    if verbose:
        for k, v in sorted(changed.items()):
            print(f"  {k}: {v} changed")
        if not changed:
            print("  nothing to change")
    return changed


# ---------------------------------------------------------------- survey
def survey():
    """Physical stations across every folder: [{rows: [(folder, row)], name, lat, lon, protected, plan}]."""
    rows = []
    protected_ids, plan_used = set(), set()
    for folder in folders():
        _, st = read(os.path.join(folder, "stations.csv"))
        if st is None:
            continue
        for r in st:
            rows.append((os.path.basename(folder), r))
        if os.path.basename(folder) in ("network", "v1_baseline"):
            _, lines = read(table(folder, "lines.csv"))
            status = {r["line_id"]: r["status"] for r in lines}
            _, ls = read(table(folder, "line_stops.csv"))
            for r in ls:
                if status.get(r["line_id"]) == "existing":
                    protected_ids.add(r["station_id"])
                if os.path.basename(folder) == "network":
                    plan_used.add(r["station_id"])
    plan_xy = {r["station_id"]: (r["lat"], r["lon"]) for f, r in rows if f == "network"}
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    by_id, by_name = collections.defaultdict(list), collections.defaultdict(list)
    for i, (_, r) in enumerate(rows):
        by_id[r["station_id"]].append(i)
        by_name[norm(r["name"])].append(i)
    for group, lim in ((by_id, MATCH_KM), (by_name, SAME_KM)):
        for idx in group.values():
            for a in idx:
                for b in idx:
                    if a < b and km(rows[a][1]["lat"], rows[a][1]["lon"], rows[b][1]["lat"], rows[b][1]["lon"]) <= lim:
                        parent[find(b)] = find(a)
    groups = collections.defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(rows[i])
    out = []
    for g in groups.values():
        plan_rows = [r for f, r in g if f == "network"]
        names = collections.Counter(r["name"] for f, r in g)
        name = plan_rows[0]["name"] if plan_rows else max(names, key=lambda n: (names[n], len(n), n))
        r0 = plan_rows[0] if plan_rows else g[0][1]
        prot = any(r["station_id"] in protected_ids and r["station_id"] in plan_xy and
                   km(r["lat"], r["lon"], *plan_xy[r["station_id"]]) <= MATCH_KM for _, r in g)
        out.append({"rows": g, "name": name, "lat": float(r0["lat"]), "lon": float(r0["lon"]), "protected": prot,
                    "plan": any(r["station_id"] in plan_used for r in plan_rows), "id": r0["station_id"]})
    out.sort(key=lambda p: (not p["protected"], not p["plan"], not any(f == "network" for f, _ in p["rows"]), p["id"], p["lat"]))
    return out


def complexes(stations):
    """{name key: [[station, ...] per interchange]} (single linkage within COMPLEX_KM)."""
    by = collections.defaultdict(list)
    for p in stations:
        by[min(keys(p["name"]))].append(p)          # "Long / Deen" and "Deen / Long" are one name
    out = {}
    for k, ps in by.items():
        cl = []
        for p in ps:
            hit = [c for c in cl if any(km(p["lat"], p["lon"], q["lat"], q["lon"]) <= COMPLEX_KM for q in c)]
            merged = [p] + [q for c in hit for q in c]
            cl = [c for c in cl if c not in hit] + [merged]
        out[k] = cl
    return out


def problems(stations):
    """[(station, why)] for names that still need work."""
    out = []
    for k, cl in complexes(stations).items():
        if len(cl) > 1:
            for c in cl:
                for p in c:
                    out.append((p, f"'{p['name']}' also names {len(cl) - 1} other place(s) over {COMPLEX_KM * 1000:.0f} m away"))
    for p in stations:
        if bad_name(p["name"]) and not p["protected"]:
            out.append((p, f"'{p['name']}' looks generated"))
        names = {r["name"] for _, r in p["rows"]}
        if len(names) > 1:
            out.append((p, f"one station, several spellings: {sorted(names)}"))
    return out


# ---------------------------------------------------------------- propose
def propose(mapping):
    from dfwt.naming import Namer
    stations = survey()
    namer = Namer()
    places = collections.defaultdict(list)       # a place's own location, to pick which same-named station keeps it
    for q, nm in namer.hoods + namer.landmarks + namer.towns:
        places[norm(nm)].append(q)
    proj = namer.proj
    new = []

    def add(p, new_name, basis):
        for f, r in p["rows"]:
            hit = [m for m in new if m["station_id"] == r["station_id"] and m["old_name"] == r["name"]
                   and km(m["lat"], m["lon"], r["lat"], r["lon"]) <= MATCH_KM]
            if hit:                                 # renamed again (a spelling fix, then a real rename)
                hit[0]["new_name"], hit[0]["basis"] = new_name, basis
            elif r["name"] != new_name:
                new.append({"station_id": r["station_id"], "old_name": r["name"], "new_name": new_name,
                            "lat": r["lat"], "lon": r["lon"], "basis": basis})
        p["name"] = new_name
    # 1. one spelling per station, and per interchange
    for p in stations:
        if len({r["name"] for _, r in p["rows"]}) > 1:
            add(p, p["name"], "one station, one spelling (the plan's)")
    for k, cl in complexes(stations).items():
        for c in cl:
            spell = collections.Counter(p["name"] for p in c)
            if len(spell) > 1:
                prot = [p["name"] for p in c if p["protected"]]
                best = prot[0] if prot else max(spell, key=lambda n: (" / " in n, len(n), n))   # "Renaissance Square"
                for p in c:
                    if p["name"] != best:
                        add(p, best, "same interchange, one spelling")
    # 2. who has to change: generated names, and every holder of a shared name but one
    todo = []
    for k, cl in complexes(stations).items():
        keep = None
        if len(cl) > 1:
            def rank(c):
                prot = any(p["protected"] for p in c)
                own = [math.hypot(*(a - b for a, b in zip(proj.xy(c[0]["lat"], c[0]["lon"]), q))) for q in places.get(k, [])]
                return (not prot, not any(p["plan"] for p in c), min(own) if own else 99, c[0]["id"])
            keep = min(cl, key=rank)
        for c in cl:
            for p in c:
                if p["protected"]:
                    continue
                if (keep is not None and c is not keep) or bad_name(p["name"]):
                    todo.append(p)
    order = {id(p): i for i, p in enumerate(stations)}
    todo.sort(key=lambda p: order[id(p)])
    todo_ids = {id(p) for p in todo}
    used = set().union(*(keys(p["name"]) for p in stations if id(p) not in todo_ids))
    for p in todo:
        nm, basis = namer.name(p["lat"], p["lon"], used, p["name"])
        add(p, nm, basis)
    # keep the rows already in the file; new rows for what they don't cover yet
    have = [(m["station_id"], m["old_name"], m["lat"], m["lon"]) for m in mapping]
    out = list(mapping) + [m for m in new if not any(
        (s, o) == (m["station_id"], m["old_name"]) and km(la, lo, m["lat"], m["lon"]) <= MATCH_KM for s, o, la, lo in have)]
    print(f"  {len(new)} new mapping rows ({len(todo)} stations renamed)")
    return out


def save_map(rows):
    rows = sorted((m for m in rows if m["old_name"] != m["new_name"]), key=lambda m: (m["station_id"], m["old_name"], m["lat"]))
    write(MAP, COLS, [{c: m.get(c, "") for c in COLS} for m in rows])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--propose", action="store_true", help="add renames for stations that still need one")
    ap.add_argument("--check", action="store_true", help="only list the names that still need work")
    a = ap.parse_args()
    if a.check:
        bad = problems(survey())
        for p, why in bad:
            print(f"  {p['id']:8} {why}")
        print(f"{len(bad)} problem(s)")
        return 1 if bad else 0
    mapping = load_map()
    apply(mapping)
    if a.propose:
        mapping = propose(mapping)
        save_map(mapping)
        apply(mapping)
    bad = problems(survey())
    print(f"{len(bad)} name problem(s) left" + (" (run with --check to list them)" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
