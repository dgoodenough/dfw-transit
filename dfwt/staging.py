"""Staged build-out: `stages.csv` -> per-segment and per-stop opening years,
interim through-running, staging checks, and capital spread over construction.

stages.csv (hand-edited, optional, one row per stage of a line; lines without
rows keep the years stored in line_segments.csv):

  line_id      line being staged
  stage        1, 2, 3 ... (authoring order; years should not decrease with stage)
  kind         starter   - first operable piece
               extension - must touch track of this line that is already open
               via       - interim: between from_stop and to_stop this line runs
                           over via_line's track from year_opens until until_year
  from_stop    station_id, a station name unique on the line, or #seq (loops)
  to_stop      "
  year_opens   year the stage opens (via: first year of the interim routing)
  until_year   via only: first year the interim routing no longer runs
  via_line     via only: host line whose track is borrowed
  headway_min  optional: the line's headway from this stage's year
  locked       1 = the optimizer must keep this stage as written
  note         free text

When a line has stage rows they are the source of truth for its years; the
segment years stored in line_segments.csv are ignored (validation reports any
that disagree, so the two never silently drift).
"""
import collections
import copy

STAGE_COLS = ["line_id", "stage", "kind", "from_stop", "to_stop", "year_opens",
              "until_year", "via_line", "headway_min", "locked", "note"]


def resolve(stop, stop_ids, names):
    """Index of a stop on a line: '#seq', a station_id, or a name unique on the line."""
    stop = stop.strip()
    if stop.startswith("#"):
        return int(stop[1:]) - 1
    if stop_ids.count(stop) == 1:
        return stop_ids.index(stop)
    hits = [i for i, s in enumerate(stop_ids) if names.get(s, "").lower() == stop.lower()]
    if len(hits) == 1:
        return hits[0]
    raise KeyError(f"'{stop}' is {'ambiguous' if hits else 'not a stop'} on this line")


def stop_ref(stop_ids, names, i):
    """The friendliest unambiguous reference to stop i."""
    sid = stop_ids[i]
    if stop_ids.count(sid) > 1:
        return f"#{i + 1}"
    nm = names.get(sid, sid)
    return nm if sum(1 for s in stop_ids if names.get(s) == nm) == 1 else sid


def compile_stages(tables, stage_rows):
    """Apply stage rows to the raw tables. Returns (tables, interims, findings);
    the input tables are not modified. Lines without stage rows are untouched."""
    t = copy.deepcopy(tables)
    t.setdefault("service.csv", [])
    findings = []
    add = lambda sev, code, line, msg: findings.append((sev, code, line, msg))
    names = {r["station_id"]: r["name"] for r in t["stations.csv"]}
    stops, segs = collections.defaultdict(list), collections.defaultdict(list)
    for r in t["line_stops.csv"]:
        stops[r["line_id"]].append(r)
    for r in t["line_segments.csv"]:
        segs[r["line_id"]].append(r)
    for d in (stops, segs):
        for v in d.values():
            v.sort(key=lambda r: int(r["seq"]))

    by_line = collections.defaultdict(list)
    for r in stage_rows:
        if r.get("line_id") and not r["line_id"].startswith("#"):
            by_line[r["line_id"]].append(r)
    interims = []
    for lid, rows in by_line.items():
        if lid not in stops:
            add("error", "STAGE_REF", lid, "stages.csv names a line that does not exist")
            continue
        sids = [r["station_id"] for r in stops[lid]]
        orig_seg = [int(r["year_opens"]) for r in segs[lid]]
        orig_stop = [int(r["year_opens"]) for r in stops[lid]]
        new_seg = [None] * len(orig_seg)
        rows.sort(key=lambda r: int(r["stage"]))
        for r in rows:
            try:
                a, b = sorted((resolve(r["from_stop"], sids, names), resolve(r["to_stop"], sids, names)))
            except KeyError as e:
                add("error", "STAGE_REF", lid, f"stage {r['stage']}: {e}")
                continue
            if a == b:
                add("error", "STAGE_REF", lid, f"stage {r['stage']}: from_stop and to_stop are the same stop")
                continue
            if r["kind"] == "via":
                interims.append({"line_id": lid, "a": a, "b": b, "via": r["via_line"],
                                 "from": int(r["year_opens"]), "until": int(r["until_year"]), "stage": r["stage"]})
                continue
            for i in range(a, b):
                if new_seg[i] is not None:
                    add("error", "STAGE_OVERLAP", lid,
                        f"stage {r['stage']} re-stages {names[sids[i]]} -> {names[sids[i + 1]]}")
                new_seg[i] = int(r["year_opens"])
        gaps = [i for i, y in enumerate(new_seg) if y is None]
        if gaps:
            add("error", "STAGE_GAP", lid, f"{len(gaps)} segments are in no stage, e.g. "
                f"{names[sids[gaps[0]]]} -> {names[sids[gaps[0] + 1]]}")
            new_seg = [y if y is not None else o for y, o in zip(new_seg, orig_seg)]
        years = [int(r["year_opens"]) for r in rows if r["kind"] != "via"]
        if years != sorted(years):
            add("warn", "STAGE_ORDER", lid, "stage numbers and opening years disagree")
        # A stop is served once track reaches it; a stop that was an infill station
        # (opened later than its own track) keeps that delay.
        for i, r in enumerate(stops[lid]):
            adj = [j for j in (i - 1, i) if 0 <= j < len(orig_seg)]
            delay = max(0, orig_stop[i] - min(orig_seg[j] for j in adj))
            r["year_opens"] = str(min(new_seg[j] for j in adj) + delay)
        drift = sum(1 for y, o in zip(new_seg, orig_seg) if y != o)
        if drift:
            add("info", "STAGE_DRIFT", lid, f"{drift} segment years in line_segments.csv differ from stages.csv "
                "(stages win; update or ignore the stored years)")
        for r, y in zip(segs[lid], new_seg):
            r["year_opens"] = str(y)
        for r in rows:
            if r.get("headway_min") and r["kind"] != "via":
                t["service.csv"].append({"line_id": lid, "from_year": r["year_opens"],
                                         "headway_min": r["headway_min"], "note": f"stage {r['stage']}"})
    return t, interims, findings


def infer_stages(tables, locked_lines=()):
    """Describe the stored per-segment years as stages (each contiguous block of
    equal year is one stage). compile_stages(infer_stages(t)) reproduces t."""
    names = {r["station_id"]: r["name"] for r in tables["stations.csv"]}
    stops, segs = collections.defaultdict(list), collections.defaultdict(list)
    for r in tables["line_stops.csv"]:
        stops[r["line_id"]].append(r)
    for r in tables["line_segments.csv"]:
        segs[r["line_id"]].append(r)
    rows = []
    for lid in sorted(stops):
        st = [r["station_id"] for r in sorted(stops[lid], key=lambda r: int(r["seq"]))]
        ys = [int(r["year_opens"]) for r in sorted(segs[lid], key=lambda r: int(r["seq"]))]
        blocks, a = [], 0
        for i in range(1, len(ys) + 1):
            if i == len(ys) or ys[i] != ys[a]:
                blocks.append((a, i, ys[a]))
                a = i
        for n, (a, b, y) in enumerate(sorted(blocks, key=lambda x: (x[2], x[0])), 1):
            rows.append({"line_id": lid, "stage": n, "kind": "starter" if n == 1 else "extension",
                         "from_stop": stop_ref(st, names, a), "to_stop": stop_ref(st, names, b),
                         "year_opens": y, "locked": "1" if lid in locked_lines else "", "note": ""})
    return rows


# ---------------------------------------------------------------- interims
def build_variants(net, interims):
    """lid -> [(from_year, until_year, line_variant, interim)]: during the window the
    line's stops between a and b are replaced by the host line's stops and track."""
    from .network import Segment
    variants = collections.defaultdict(list)
    for it in interims:
        ln, host = net.lines[it["line_id"]], net.lines[it["via"]]
        a_sid, b_sid = ln.stop_ids[it["a"]], ln.stop_ids[it["b"]]
        ha, hb = host.stop_ids.index(a_sid), host.stop_ids.index(b_sid)
        step = 1 if hb > ha else -1
        mid_stops = host.stop_ids[ha + step:hb:step]
        mid_years = host.stop_years[ha + step:hb:step]
        mid_segs = []
        for k in range(ha, hb, step):
            s = host.segments[min(k, k + step)]
            mid_segs.append(Segment(s.year, s.grade, s.pts if step > 0 else s.pts[::-1], s.km))
        v = copy.copy(ln)
        v.stop_ids = ln.stop_ids[:it["a"] + 1] + mid_stops + ln.stop_ids[it["b"]:]
        v.stop_years = ln.stop_years[:it["a"] + 1] + mid_years + ln.stop_years[it["b"]:]
        v.segments = ln.segments[:it["a"]] + mid_segs + ln.segments[it["b"]:]
        it["n_mid"] = len(mid_segs)
        variants[ln.id].append((it["from"], it["until"], v, it))
    return variants


# ---------------------------------------------------------------- checks
def _open_pieces(ln, year):
    out, start = [], None
    for i, s in enumerate(ln.segments):
        if s.year <= year and start is None:
            start = i
        if s.year > year and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(ln.segments)))
    return out


def check(net):
    """Staging rules (config.json "staging"). Contiguity is judged on the routing in
    force that year, so a via interim can bridge a gap."""
    cfg, out = net.cfg, []
    rules = cfg["staging"]
    add = lambda sev, code, line, msg: out.append((sev, code, line, msg))
    years = cfg["years"]
    names = {k: v.name for k, v in net.stations.items()}
    out.extend(net.stage_findings)
    staged = sorted({r["line_id"] for r in net.stage_rows if r["line_id"] in net.lines})
    for lid in staged:
        base = net.lines[lid]
        mode = base.mode
        for y in years:
            p = _open_pieces(net.line_at(lid, y), y)
            if len(p) > 1:
                add("warn", "STAGE_DETACHED", base.name, f"{y}: open in {len(p)} pieces; an extension must "
                    "touch open track of the line (or add a via interim)")
                break
        for r in net.stage_rows:
            if r["line_id"] != lid or r["kind"] == "via":
                continue
            a, b = sorted((resolve(r["from_stop"], base.stop_ids, names), resolve(r["to_stop"], base.stop_ids, names)))
            km = sum(s.km for s in base.segments[a:b])
            yo = int(r["year_opens"])
            if yo > max(years):
                add("warn", "PAST_HORIZON", base.name, f"stage {r['stage']} opens {yo}, after {max(years)}")
            if yo - rules["construction_years"][mode] < cfg["existing_year"] and base.status != "existing":
                add("warn", "BUILD_STARTED", base.name, f"stage {r['stage']} opens {yo} but takes "
                    f"{rules['construction_years'][mode]} years to build")
            if km > rules["max_km_per_stage"][mode]:
                add("warn", "STAGE_TOO_BIG", base.name, f"stage {r['stage']} is {km:.1f} km "
                    f"(limit {rules['max_km_per_stage'][mode]} km for {mode})")
        mink, minst = rules["min_operable"][mode]
        stub_since = {}
        for i, y in enumerate(years):
            ln = net.line_at(lid, y)
            p = _open_pieces(ln, y)
            prev = years[i - 1] if i else 0
            new_km = sum(s.km for s in base.segments if prev < s.year <= y)
            if new_km > rules["max_km_per_interval"][mode] and base.status != "existing":
                add("warn", "INTERVAL_TOO_BIG", base.name, f"{y}: {new_km:.1f} km opens in one interval "
                    f"(limit {rules['max_km_per_interval'][mode]} km for {mode})")
            if p and (i == 0 or not _open_pieces(net.line_at(lid, prev), prev)) and base.status != "existing":
                km_open = sum(s.km for s in ln.segments if s.year <= y)
                nst = p[0][1] - p[0][0] + 1
                if km_open < mink or nst < minst:
                    add("warn", "STAGE_MIN_OPERABLE", base.name, f"{y}: starter is {km_open:.1f} km / {nst} stops "
                        f"(minimum {mink} km / {minst})")
            term = set()
            for a, b in p:
                for k in (a, b):
                    term.add(ln.stop_ids[k])
                    if ln.stop_years[k] > y:
                        add("error", "TERMINUS_UNSERVED", base.name, f"{y}: open track ends at {names[ln.stop_ids[k]]}, "
                            f"which the line does not serve until {ln.stop_years[k]}")
            for sid in term - {base.stop_ids[0], base.stop_ids[-1]}:
                stub_since.setdefault(sid, y)
                if y - stub_since[sid] == rules["max_stub_years"]:
                    add("info", "LONG_STUB", base.name, f"{names[sid]} has been a temporary terminus since {stub_since[sid]}")
        for y0, y1, v, it in net.variants.get(lid, []):
            host = net.lines[it["via"]]
            for y in (yy for yy in years if y0 <= yy < y1):
                if not all(s.year <= y for s in v.segments[it["a"]:it["a"] + it["n_mid"]]):
                    add("error", "INTERIM_HOST_CLOSED", base.name, f"{y}: runs via {host.name} but that track is not open")
                    break
            own = base.segments[it["a"]:it["b"]]
            if max(s.year for s in own) > y1:
                add("error", "INTERIM_GAP", base.name, f"via routing ends {y1} but its own track opens {max(s.year for s in own)}")

    # budget: spend spread over construction, against a flat annual budget with carryover
    spend = spend_by_year(net)
    per_year = cfg["budget"]["musd_per_year"]
    cum_s = cum_b = 0.0
    worst = None
    for y in range(cfg["existing_year"] + 1, max(years) + 1):
        cum_s += spend.get(y, 0.0)
        cum_b += per_year
        if cum_s > cum_b * (1 + cfg["budget"]["tolerance"]) and (worst is None or cum_s - cum_b > worst[1]):
            worst = (y, cum_s - cum_b)
    if worst:
        add("warn", "OVER_BUDGET", "", f"cumulative spending exceeds the flat ${per_year / 1000:.1f}B/yr budget; "
            f"worst in {worst[0]} by ${worst[1] / 1000:.1f}B")
    return out


# ---------------------------------------------------------------- money
def spend_by_year(net):
    """Capital by calendar year (2025 $M), charged as Network.line_cost_musd does,
    spread evenly over the construction years before each piece opens."""
    cfg = net.cfg
    ex = cfg["existing_year"]
    cy = cfg["staging"]["construction_years"]
    owner = net.track_owner()
    first = net._station_first_line()
    out = collections.defaultdict(float)

    def book(year, cost, mode):
        n = cy[mode]
        for k in range(n):
            out[max(year - 1 - k, ex + 1)] += cost / n

    for ln in net.lines.values():
        if ln.status == "existing":
            continue
        per_km = cfg["cost_musd_per_km"][ln.mode]
        for i, s in enumerate(ln.segments):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if ex < s.year < 9999 and owner[key][1] == ln.id:
                book(s.year, s.km * per_km.get(s.grade, per_km["surface"]), ln.mode)
        for sid, y in zip(ln.stop_ids, ln.stop_years):
            if ex < y < 9999 and first.get(sid) == ln.id:
                book(y, cfg["station_cost_musd"][ln.mode], ln.mode)
    return out
