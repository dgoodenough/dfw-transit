"""Names and colours for a generated network's lines and stations (texas-transit study/site_parity.md, phase 1).

    python -m metro names <id> [--out generated/<id>] [--overrides DIR]

The generator names each center after its nearest cross streets, and each line after its two end centers
("Pellicano / George Dieter - Nonap / Mark Twain BRT"), which reads like a survey, not a transit map. This
renames a finished network the way an agency would:

  today's lines    keep their agency name and colour, cleaned of GTFS route numbers and capitals
                   ("700 METRORAIL RED LINE" -> "METRORail Red Line")
  metro           a colour name, in the order the lines were chosen, skipping colours today's lines use
                   ("Blue Line"); streetcars the same ("Teal Streetcar")
  regional rail    the town at its outer end ("Katy Line"), in a rail colour
  BRT              the street it runs on most ("Westheimer BRT"), or its two main streets ("Illinois-Lake June
                   BRT"), in the BRT palette
  stations         today's keep their names (direction and platform suffixes dropped); new ones are named by
                   dfwt's Namer with the metro's gazetteer (step 1's gazetteer stage): a landmark within
                   250 m, a neighbourhood within 350 m, the cross streets at the nearest arterial, a street

Hand fixes win: <overrides>/line_names.csv (line_id, name, color) and <overrides>/station_renames.csv
(station_id, new_name), DFW's format. Rewrites lines.csv, stations.csv, the chosen lines' names in
candidates.csv and the line names in report.md, and writes names.csv (every name and why).
"""
import collections
import csv
import math
import os
import re

from . import inputs

RAIL_COLORS = [("Red", "#d32f2f"), ("Blue", "#1565c0"), ("Green", "#2e7d32"), ("Orange", "#ef6c00"),
               ("Purple", "#6a1b9a"), ("Gold", "#f9a825"), ("Silver", "#78909c"), ("Teal", "#00897b"),
               ("Brown", "#6d4c41"), ("Pink", "#d81b60"), ("Lime", "#9e9d24"), ("Navy", "#283593"),
               ("Crimson", "#b71c1c"), ("Aqua", "#0097a7"), ("Copper", "#bf360c"), ("Indigo", "#4527a0")]
COMMUTER_COLORS = ["#4e342e", "#37474f", "#1b5e20", "#4a148c", "#3e2723", "#263238", "#004d40", "#311b92"]
BRT_COLORS = ["#8e24aa", "#00897b", "#3949ab", "#c0ca33", "#e64a19", "#546e7a", "#0277bd", "#558b2f",
              "#ad1457", "#00838f", "#5d4037", "#6a1b9a", "#ef6c00", "#2e7d32", "#c62828", "#1565c0"]
COLOR_WORDS = [c for c, _ in RAIL_COLORS]
AGENCY = [(r"\bmetrorail\b", "METRORail"), (r"\bmetro rail\b", "MetroRail"), (r"\bmetrorapid\b", "MetroRapid"),
          (r"\bvia\b", "VIA"), (r"\bcapmetro\b", "CapMetro"), (r"\bdart\b", "DART"), (r"\butep\b", "UTEP"),
          (r"\butsa\b", "UTSA"), (r"\bbrt\b", "BRT")]
SAMPLE_KM = 0.25
STREET_NEAR_M = 45


def clean_line(name):
    """A GTFS route name as an agency would print it: no route number, no shouting."""
    s = re.sub(r"^\s*\d+[A-Za-z]?\s*(?:[-:]\s*|\s+)", "", (name or "").strip())
    if s.isupper() or sum(w.isupper() for w in s.split()) > len(s.split()) / 2:
        s = " ".join(w.capitalize() if len(w) > 3 or not w.isalpha() else w.capitalize() for w in s.lower().split())
    for pat, rep in AGENCY:
        s = re.sub(pat, rep, s, flags=re.I)
    return s.strip() or name


def clean_station(name):
    """A GTFS stop name without direction, bay or platform ("Fannin South Stn SB" -> "Fannin South")."""
    s = (name or "").strip()
    s = re.sub(r"\s*-\s*(?:platform|bay|track|gate)\s*\w+$", "", s, flags=re.I)
    s = re.sub(r"\s+(?:stn|station)?\s*(?:[NSEW]B|northbound|southbound|eastbound|westbound)$", "", s, flags=re.I)
    s = re.sub(r"\s+stn$", "", s, flags=re.I)
    return s or name


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write(path, rows, fields):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _wkt(s):
    return [(float(b), float(a)) for a, b in (p.split() for p in re.sub(r"^\w+\s*\(|\)$", "", s).split(","))]


def _key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def line_paths(segs):
    """{line_id: [(lat, lon)]} joined from its segments in order."""
    by = collections.defaultdict(list)
    for r in sorted(segs, key=lambda r: (r["line_id"], int(r["seq"]))):
        by[r["line_id"]] += _wkt(r["geometry_wkt"])
    return by


def _km(a, b):
    return math.hypot((a[0] - b[0]) * 110.57, (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0])))


def main_streets(namer, P):
    """[(clean name, share of the line's sampled length)] of the streets a line runs along, most first."""
    from dfwt.naming import _TYPES, clean_street
    pts, acc = [P[0]], 0.0
    for a, b in zip(P, P[1:]):
        d = _km(a, b)
        while acc + d >= SAMPLE_KM:
            t = (SAMPLE_KM - acc) / d
            a = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            d = _km(a, b)
            pts.append(a)
            acc = 0.0
        acc += d
    c = collections.Counter()
    for lat, lon in pts:
        st = namer.streets(lat, lon, STREET_NEAR_M)
        if st:
            nm = clean_street(st[0][2], places=namer.places)
            if re.fullmatch(_TYPES, nm, flags=re.I):   # "Highway Boulevard" -> "Highway": keep its type
                nm = clean_street(st[0][2], keep_type=True, places=namer.places)
            c[nm] += 1
    n = max(sum(c.values()), 1)   # shares of the stretches on a named street (ramps and gaps aside)
    return [(nm, k / n) for nm, k in c.most_common() if nm]


def end_label(station_name):
    """A station name short enough for a line's end: a place as it is, cross streets by the first street."""
    return station_name.split(" / ")[0].strip() if " / " in station_name else station_name


def outer_town(namer, P, downtown, stations):
    """The town nearest the line's end farther from downtown (within 6 km), else that end's station name."""
    end = P[0] if _km(P[0], downtown) > _km(P[-1], downtown) else P[-1]
    best = None
    p = namer.proj.xy(*end)
    for q, nm in namer.towns:
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d <= 6.0 and (best is None or d < best[0]):
            best = (d, nm)
    if best:
        return best[1]
    near = min(stations, key=lambda s: _km((s[1], s[2]), end))
    return near[0]


def name_network(out, m, anchors=None, overrides=None, log=print):
    from . import output
    lines = _rows(os.path.join(out, "lines.csv"))
    if not lines:
        return {}
    stations = _rows(os.path.join(out, "stations.csv"))
    stops = _rows(os.path.join(out, "line_stops.csv"))
    paths = line_paths(_rows(os.path.join(out, "line_segments.csv")))
    namer = output.make_namer(m, anchors)
    downtown = next(((a["lat"], a["lon"]) for a in (anchors or []) if a.get("kind") == "downtown"),
                    (float(m.lat0), float(m.lon0)))
    log_rows = []
    # ---- stations: today's cleaned; new ones named from the gazetteer, in the order lines were chosen
    on_line = collections.defaultdict(list)
    for r in stops:
        on_line[r["station_id"]].append(r["line_id"])
    existing_lines = {r["line_id"] for r in lines if r["status"] == "existing"}
    used = set()
    st_new = {}
    for s in stations:
        if any(l in existing_lines for l in on_line[s["station_id"]]) or not s["station_id"].startswith("N"):
            nm = clean_station(s["name"])
            st_new[s["station_id"]] = (nm, "today's stop" + ("" if nm == s["name"] else f" ({s['name']})"))
            used |= {_key(nm)}
    order = {r["line_id"]: k for k, r in enumerate(lines)}
    for s in sorted(stations, key=lambda s: min((order.get(l, 999) for l in on_line[s["station_id"]]), default=999)):
        if s["station_id"] in st_new:
            continue
        from dfwt.naming import keys
        nm, basis = namer.name(float(s["lat"]), float(s["lon"]), used, s["name"])
        st_new[s["station_id"]] = (nm, basis)
    ov = {r["station_id"]: r["new_name"] for r in _rows(os.path.join(overrides, "station_renames.csv"))} if overrides else {}
    for sid, nm in ov.items():
        if sid in st_new:
            st_new[sid] = (nm, "hand fix")
    for s in stations:
        nm, basis = st_new[s["station_id"]]
        log_rows.append({"kind": "station", "id": s["station_id"], "old": s["name"], "new": nm, "color": "", "basis": basis})
        s["name"] = nm
    st_ll = {s["station_id"]: (s["name"], float(s["lat"]), float(s["lon"])) for s in stations}

    # ---- lines
    taken_colors = set()
    for r in lines:
        if r["status"] == "existing":
            for w in COLOR_WORDS:
                if re.search(rf"\b{w}\b", r["name"], re.I):
                    taken_colors.add(w)
    rail = [c for c in RAIL_COLORS if c[0] not in taken_colors]
    names_used, k_rail, k_comm, k_brt = set(), 0, 0, 0
    new = {}
    for r in lines:
        lid, mode, old = r["line_id"], r["mode"], r["name"]
        P = paths.get(lid) or []
        sts = [st_ll[x["station_id"]] for x in stops if x["line_id"] == lid and x["station_id"] in st_ll]
        if r["status"] == "existing":
            nm, col, basis = clean_line(old), r["color"], "today's line"
        elif mode in ("metro", "streetcar"):
            cn, col = rail[k_rail % len(rail)]
            k_rail += 1
            nm, basis = f"{cn} {'Line' if mode == 'metro' else 'Streetcar'}", "rail: the next colour"
        elif mode == "commuter":
            town = outer_town(namer, P, downtown, sts) if P and sts else old
            nm, col, basis = f"{town} Line", COMMUTER_COLORS[k_comm % len(COMMUTER_COLORS)], f"regional rail: its outer end, {town}"
            k_comm += 1
        else:
            ms = main_streets(namer, P) if P else []
            col = BRT_COLORS[k_brt % len(BRT_COLORS)]
            k_brt += 1
            if ms and ms[0][1] >= 0.55:
                nm, basis = f"{ms[0][0]} BRT", f"BRT: {ms[0][1]:.0%} of it on {ms[0][0]}"
            elif len(ms) >= 2 and ms[0][1] + ms[1][1] >= 0.45:
                nm, basis = f"{ms[0][0]}-{ms[1][0]} BRT", f"BRT: {ms[0][1]:.0%} on {ms[0][0]}, {ms[1][1]:.0%} on {ms[1][0]}"
            elif sts:   # no street dominates: its two ends, as the agencies' crosstown routes are named
                a_, b_ = (end_label(x[0]) for x in (sts[0], sts[-1]))
                nm, basis = f"{a_}-{b_} BRT", "BRT: no street carries most of it, so its two ends"
            else:
                nm, basis = (old.strip() or f"{lid} BRT"), "BRT: no street found"
        if _key(nm) in names_used and sts:   # two lines on one street: the second gets its far end
            far = end_label(max(sts, key=lambda s: _km((s[1], s[2]), downtown))[0])
            nm, basis = f"{nm[:-4] if nm.endswith(' BRT') else nm} to {far}" + (" BRT" if nm.endswith(" BRT") else ""), basis + "; another line has the name, so its far end"
        names_used.add(_key(nm))
        new[lid] = (nm, col, basis)
    ovl = {x["line_id"]: x for x in _rows(os.path.join(overrides, "line_names.csv"))} if overrides else {}
    for lid, x in ovl.items():
        if lid in new:
            new[lid] = (x.get("name") or new[lid][0], x.get("color") or new[lid][1], "hand fix")
    renamed = {}
    for r in lines:
        nm, col, basis = new[r["line_id"]]
        log_rows.append({"kind": "line", "id": r["line_id"], "old": r["name"], "new": nm, "color": col, "basis": basis})
        if r["name"] != nm:
            renamed[r["name"]] = nm
        r["name"], r["color"] = nm, col
    _write(os.path.join(out, "lines.csv"), lines, list(lines[0].keys()))
    _write(os.path.join(out, "stations.csv"), stations, list(stations[0].keys()))
    # the chosen lines' names in candidates.csv (what texas-transit's schedule reads), by the cand id in the notes
    cp = os.path.join(out, "candidates.csv")
    cands = _rows(cp)
    if cands:
        by_cand = {}
        for r in lines:
            mm = re.search(r"generated \(([A-Z]+\d+)\)", r.get("notes", ""))
            if mm:
                by_cand[mm.group(1)] = r["name"]
        for c in cands:
            if c["cand_id"] in by_cand:
                c["name"] = by_cand[c["cand_id"]]
        _write(cp, cands, list(cands[0].keys()))
    rp = os.path.join(out, "report.md")
    if os.path.exists(rp) and renamed:
        txt = open(rp, encoding="utf-8").read()
        for o in sorted(renamed, key=len, reverse=True):
            if o.strip():
                txt = txt.replace(o, renamed[o])
        open(rp, "w", encoding="utf-8").write(txt)
    _write(os.path.join(out, "names.csv"), log_rows, ["kind", "id", "old", "new", "color", "basis"])
    n_st = sum(1 for r in log_rows if r["kind"] == "station" and r["old"] != r["new"])
    n_ln = sum(1 for r in log_rows if r["kind"] == "line" and r["old"] != r["new"])
    if log:
        log(f"  names: {n_ln} of {len(lines)} lines and {n_st} of {len(stations)} stations renamed")
    return {"lines": new, "stations": st_new}


def main(metro_id, out=None, overrides=None):
    from .generate import registry_entry
    m = inputs.load(metro_id)
    entry = registry_entry(metro_id, m)
    out = out or inputs.home("generated", metro_id)
    return name_network(out, m, entry.get("anchors"), overrides)
