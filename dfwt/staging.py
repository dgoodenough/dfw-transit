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

from . import config

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


def resolve_on(net, ln, stop, names):
    """resolve() on a line that may have absorbed others (through_route): a stage of the
    absorbed line may name its old terminus, which merged into the junction."""
    try:
        return resolve(stop, ln.stop_ids, names)
    except KeyError:
        for old, new in net.stop_alias.items():
            if stop.strip() == old or stop.strip().lower() == names.get(old, "").lower():
                return resolve(new, ln.stop_ids, names)
        raise


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
            new_track = any(s.year > cfg["existing_year"] for s in base.segments[a:b])   # a through-routed line's old part isn't built
            if yo - rules["construction_years"][mode] < cfg["existing_year"] and base.status != "existing" and new_track:
                add("warn", "BUILD_STARTED", base.name, f"stage {r['stage']} opens {yo} but takes "
                    f"{rules['construction_years'][mode]} years to build")
            if km > rules["max_km_per_stage"][mode] and not all(s.grade == "freeway" for s in base.segments[a:b]):
                add("warn", "STAGE_TOO_BIG", base.name, f"stage {r['stage']} is {km:.1f} km "
                    f"(limit {rules['max_km_per_stage'][mode]} km for {mode})")
        if all(s.grade == "freeway" for s in base.segments):   # an express bus in existing freeway lanes: nothing to build in pieces
            continue
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
            if it.get("via") is None:   # a reroute's old routing, not a borrowed track
                continue
            host = net.lines[it["via"]]
            for y in (yy for yy in years if y0 <= yy < y1):
                if not all(s.year <= y for s in v.segments[it["a"]:it["a"] + it["n_mid"]]):
                    add("error", "INTERIM_HOST_CLOSED", base.name, f"{y}: runs via {host.name} but that track is not open")
                    break
            own = base.segments[it["a"]:it["b"]]
            if max(s.year for s in own) > y1:
                add("error", "INTERIM_GAP", base.name, f"via routing ends {y1} but its own track opens {max(s.year for s in own)}")

    # budget: spend spread over construction, against a flat annual budget with carryover
    per_year = cfg["budget"]["musd_per_year"]
    worst = over_budget(net, max(years))
    if worst:
        add("warn", "OVER_BUDGET", "", f"cumulative spending exceeds the flat ${per_year / 1000:.1f}B/yr budget; "
            f"worst in {worst[0]} by ${worst[1] / 1000:.1f}B")
    return out


# ---------------------------------------------------------------- money
def allocate_spending(items, cfg, horizon=2200):
    """Spend each (opening_year, cost, construction_years) item in the years before it
    opens, earliest years first and no year more than 1.5x an even share, without
    letting cumulative spending pass the money accrued (config.budget, with its
    tolerance); items are funded in order of opening. What can't be funded within
    its window is spread evenly over it (and shows up as over budget).
    Returns {year: $M}."""
    import numpy as np
    ex = cfg["existing_year"]
    per_year = cfg["budget"]["musd_per_year"] * (1 + cfg["budget"]["tolerance"])
    H = horizon - ex + 1
    spend = np.zeros(H)
    budget = per_year * np.arange(H)
    for y, cost, n in sorted(items):
        slack = budget - np.cumsum(spend)
        slack = np.minimum.accumulate(slack[::-1])[::-1]   # what year t can still take without breaking a later year
        lo = max(y - n, ex + 1) - ex
        hi = min(max(y - ex, lo + 1), H)
        left, extra, cap = cost, 0.0, cost * 1.5 / n
        for t in range(lo, hi):
            put = min(left, cap, slack[t] - extra)
            if put > 0:
                spend[t] += put
                left -= put
                extra += put
        if left > 1e-9:
            spend[lo:hi] += left / (hi - lo)
    return {ex + t: float(v) for t, v in enumerate(spend) if v}


def spend_by_year(net):
    """Capital by calendar year (2025 $M), charged as Network.line_cost_musd does,
    funded in the years before each piece opens (see allocate_spending)."""
    from . import network
    cfg = net.cfg
    ex = cfg["existing_year"]
    cy = cfg["staging"]["construction_years"]
    owner = net.track_owner()
    first = net._station_first_line()
    items = collections.defaultdict(float)     # (opening year, line, mode) -> cost: a piece is built as one project

    for ln in net.lines.values():   # existing lines too: a rerouted line builds new track
        for i, s in enumerate(ln.segments):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if ex < s.year < 9999 and owner[key][1] == ln.id:
                items[(s.year, ln.id, ln.mode)] += net.segment_cost(ln, i)
        for i, (sid, y) in enumerate(zip(ln.stop_ids, ln.stop_years)):
            if ex < y < 9999 and first.get((sid, ln.mode)) == ln.id and sid not in ln.stop_ids[:i]:
                items[(y, ln.id, ln.mode)] += net.stop_cost(ln, i)
        for y, c, _ in net.capital_items(ln):
            if ex < y < 9999:
                items[(y, ln.id, ln.mode)] += c * network.cost_factor(cfg, y, ln.mode)
    return allocate_spending([(y, c, cy[m]) for (y, _, m), c in items.items()], cfg)


def over_budget(net, last_year):
    """(year, $M) where cumulative spending most exceeds the money accrued, or None."""
    cfg = net.cfg
    spend = spend_by_year(net)
    per_year = cfg["budget"]["musd_per_year"]
    cum_s = cum_b = 0.0
    worst = None
    for y in range(cfg["existing_year"] + 1, last_year + 1):
        cum_s += spend.get(y, 0.0)
        cum_b += per_year
        if cum_s > cum_b * (1 + cfg["budget"]["tolerance"]) + 1e-6 and (worst is None or cum_s - cum_b > worst[1]):   # (rounding at the limit)
            worst = (y, cum_s - cum_b)
    return worst


def _repair(scenario, rows, last_year, tries=150):
    """Per-stage costs (what exact_years schedules with) and the year-by-year spending
    check disagree a little where track ownership shifts. Close the gap locally: push the
    first stage that opens after the over-budget year back a year (and its line's later
    stages with it), until the plan fits. Returns the rows, or None if it doesn't fit."""
    from .network import Network
    from .validate import islands as find_islands
    rows = copy.deepcopy(rows)
    cy = max(_cfg_for(scenario)["staging"]["construction_years"].values())
    for _ in range(tries):
        test = Network.load(scenario, stage_rows=rows)
        worst = over_budget(test, last_year)
        if not worst:
            return rows   # a line briefly cut off is reported (validate ISLAND), not a budget failure
        y = worst[0]
        cand = [r for r in rows if r.get("locked") != "1" and r["kind"] != "via" and y < int(r["year_opens"]) <= y + cy]
        if not cand:
            return None
        r = min(cand, key=lambda r: (int(r["year_opens"]), r["line_id"], -int(r["stage"])))
        new = int(r["year_opens"]) + 1
        for q in rows:
            if q["line_id"] == r["line_id"] and q["kind"] != "via" and int(q["stage"]) >= int(r["stage"]) and int(q["year_opens"]) < new:
                q["year_opens"] = str(new)
    return None


def _attach_islands(scenario, rows, test, rounds=6):
    """A line still cut off from the network in some year opens the stages it had by then a
    year later, until it connects. Delaying spending can't break the cumulative budget."""
    from .network import Network
    from .validate import islands as find_islands
    for _ in range(rounds):
        late = find_islands(test)
        if not late:
            break
        for r in rows:
            host = test.host_line(r["line_id"])
            lid = host.id if host else r["line_id"]
            y = late.get(r["line_id"], late.get(lid))
            if y and r["kind"] != "via" and r.get("locked") != "1" and test.cfg["existing_year"] < int(r["year_opens"]) <= y:
                r["year_opens"] = str(y + 1)
        rows = renumber(keep_attached(test, rows))
        test = Network.load(scenario, stage_rows=rows)
    return rows, test


def _cfg_for(scenario):
    return config.load(scenario=scenario)


def schedule(scenario=None, log=print):
    """exact_years with a safety margin: stage costs are estimated per stage, so if
    the resulting plan trips the budget check, retry against a slightly smaller
    budget. Returns the new stage rows."""
    import csv
    import os
    from .network import Network
    net = Network.load(scenario)
    src = config.path("scenarios", scenario, "stages.unscheduled.csv") if scenario else None
    if src and os.path.exists(src):   # start from the generated stages, not the last schedule
        with open(src, encoding="utf-8") as f:
            net = Network.load(scenario, stage_rows=list(csv.DictReader(f)))
    for k in range(15):
        scale = 1.0 - 0.01 * k
        floor = {}
        for _ in range(4):
            rows = net.stage_rows
            for _ in range(3):   # shared track is charged to whoever opens it first, which moving stages changes
                cur = Network.load(scenario, stage_rows=rows)
                rows = exact_years(cur, rows, log=None, scale=scale, floor=floor)
            test = Network.load(scenario, stage_rows=rows)
            # a line whose partner was delayed may now open alone: hold it until it connects
            from .validate import islands as find_islands
            late = find_islands(test)
            if not late:
                break
            for lid, y in late.items():
                floor[lid] = max(floor.get(lid, 0), y + 1)
        if late and log:
            log("warning: still cut off from the network: " + ", ".join(sorted(late)))
        if any(f[1] == "OVER_BUDGET" for f in check(test)):
            fixed = _repair(scenario, rows, max(test.cfg["years"]))
            if fixed is not None:
                rows, test = fixed, Network.load(scenario, stage_rows=fixed)
        if not any(f[1] == "OVER_BUDGET" for f in check(test)):
            rows, test = _attach_islands(scenario, rows, test)
            if any(f[1] == "OVER_BUDGET" for f in check(test)):   # shared track changed hands: try a smaller budget
                continue
            moved = sum(1 for a, b in zip(net.stage_rows, rows) if a["year_opens"] != b["year_opens"])
            if log:
                log(f"{moved} of {len(rows)} stages moved to their earliest affordable year "
                    f"(scheduled against {scale:.0%} of the budget)")
            return rows
    raise RuntimeError("could not fit the stages in the budget")


def stage_costs(net, rows):
    """Capital ($M) of each non-via stage row: the track it opens that its line owns
    and the stations it opens first (as Network.line_cost_musd charges them)."""
    cfg = net.cfg
    names = {k: v.name for k, v in net.stations.items()}
    owner = net.track_owner()
    first = net._station_first_line()
    ex = cfg["existing_year"]
    out = {}
    for r in rows:
        ln = net.host_line(r["line_id"])   # a through-routed line's stages price its part of the joined line
        if ln is None or r["kind"] == "via" or int(r["year_opens"]) <= ex:   # today's service costs nothing
            continue
        a, b = sorted((resolve_on(net, ln, r["from_stop"], names), resolve_on(net, ln, r["to_stop"], names)))
        cost = 0.0
        for i in range(a, b):
            if ln.segments[i].year > ex and owner[(ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))][1] == ln.id:
                cost += net.segment_cost(ln, i)
        y = int(r["year_opens"])
        for i in range(a, b + 1):   # stations this line opens first, charged to the stage that first reaches them
            reach = min(ln.segments[k].year for k in (i - 1, i) if 0 <= k < len(ln.segments))
            if reach > ex and first.get((ln.stop_ids[i], ln.mode)) == ln.id and reach == y and ln.stop_ids[i] not in ln.stop_ids[:i] \
                    and (i > a or i == 0 or ln.segments[i - 1].year != y):
                cost += net.stop_cost(ln, i)
        out[id(r)] = (cost, ln.mode)
    return out


def unstaged_spending(net, rows):
    """[(year, $M, construction years)] for new track and stations no stage row covers (a
    reroute edit's new track, say): fixed spending the scheduler works around."""
    from . import network
    cfg = net.cfg
    ex, cy = cfg["existing_year"], cfg["staging"]["construction_years"]
    names = {k: v.name for k, v in net.stations.items()}
    owner, first = net.track_owner(), net._station_first_line()
    covered, covered_seg = set(), set()
    for r in rows:
        ln = net.host_line(r["line_id"])
        if ln is None or r["kind"] == "via" or int(r["year_opens"]) <= ex:
            continue
        try:
            a, b = sorted((resolve_on(net, ln, r["from_stop"], names), resolve_on(net, ln, r["to_stop"], names)))
        except KeyError:
            continue
        covered |= {(ln.id, i) for i in range(a, b + 1)}
        covered_seg |= {(ln.id, i) for i in range(a, b)}
    out = []
    for ln in net.lines.values():
        for i, s in enumerate(ln.segments):
            if ex < s.year < 9999 and (ln.id, i) not in covered_seg \
                    and owner[(ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))][1] == ln.id:
                out.append((s.year, net.segment_cost(ln, i), cy[ln.mode]))
        for i, y in enumerate(ln.stop_years):
            if ex < y < 9999 and (ln.id, i) not in covered and first.get((ln.stop_ids[i], ln.mode)) == ln.id \
                    and ln.stop_ids[i] not in ln.stop_ids[:i]:
                out.append((y, net.stop_cost(ln, i), cy[ln.mode]))
        for y, c, _ in net.capital_items(ln):   # fixed works (config capital_items), not in any stage
            if ex < y < 9999:
                out.append((y, c * network.cost_factor(cfg, y, ln.mode), cy[ln.mode]))
    return out


def _line_values(net):
    """line_id -> daily trips per $M: results/<scenario>/line_values.csv (evaluate.final_values:
    the same whatever order lines open in; through-routed lines too), else lines.csv."""
    import csv
    import os
    out = {}
    for name in ("lines.csv", "line_values.csv"):   # line_values.csv wins
        p = config.path("results", net.name, name)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                try:
                    out[r["line_id"]] = float(r["value_per_musd"])
                except (TypeError, ValueError):
                    pass
    return out


def _priorities(net, rows):
    """Row index -> acceptance order from the optimizer's log (reports/build_order_log.csv,
    or the scenario's optimizer_log.csv), matched by line and the stage's first stop."""
    import csv as _csv
    import os as _os
    paths = [config.path("scenarios", net.name, "optimizer_log.csv"), config.path("reports", "build_order_log.csv")]
    path = next((p for p in paths if _os.path.exists(p)), None)
    if not path:
        return {}
    log_rows = list(_csv.DictReader(open(path, encoding="utf-8")))
    out = {}
    for i, r in enumerate(rows):
        for k, lr in enumerate(log_rows):
            if lr["line_id"] == r["line_id"] and lr["from"] in (r["from_stop"], r["to_stop"]):
                out[i] = k
                break
    return out


def exact_years(net, rows, log=print, scale=1.0, floor=None):
    return _exact_years(net, rows, log, scale, floor or {})


_COUNTY = {}


def _station_counties(net):
    """station_id -> county (the census block group the station sits in, by nearest zone), and
    each county's share of the region's population."""
    key = (net.name, len(net.stations))
    if key not in _COUNTY:
        import numpy as np
        from . import demand
        z = demand.Zones(net.cfg)
        county = np.array([g[:5] for g in z.ids])
        out = {}
        for sid, s in net.stations.items():
            out[sid] = county[int(np.argmin((z.lat - s.lat) ** 2 + ((z.lon - s.lon) * 0.84) ** 2))]
        tot = float(z.pop.sum())
        share = {c: float(z.pop[county == c].sum()) / tot for c in set(county)}
        _COUNTY[key] = (out, share)
    return _COUNTY[key]


_PLAN = {}


def _deadlines(net, rows):
    """Row index -> the year a stage must open by: config staging.deadlines ({line_id, from_stop,
    to_stop, by}), and, with staging.core_by_plan, the plan's year for each stage of a plan line
    (metro, BRT, streetcar) that serves a downtown core: the scenario builds the core no later
    than the budget plan does. Stages are matched by their end stations (stage numbers follow
    opening order, so they move)."""
    from .network import Network
    sc = net.cfg["staging"]
    names = {k: v.name for k, v in net.stations.items()}

    def ends(n, r, nm):
        ln = n.host_line(r["line_id"])
        try:
            return r["line_id"], frozenset(ln.stop_ids[resolve_on(n, ln, r[c], nm)] for c in ("from_stop", "to_stop"))
        except (KeyError, IndexError, AttributeError):
            return None
    want = {}
    for d in sc.get("deadlines") or []:
        if isinstance(d, dict):
            want[ends(net, d, names)] = int(d["by"])
    if sc.get("core_by_plan") and net.name != "plan":
        if "net" not in _PLAN:
            _PLAN["net"] = Network.load()
        plan = _PLAN["net"]
        pnames = {k: v.name for k, v in plan.stations.items()}
        for r in plan.stage_rows:   # the stages that reach a core (metro, BRT, streetcar)
            ln = plan.host_line(r["line_id"])
            if ln is None or ln.mode == "commuter" or r["kind"] == "via":
                continue
            try:
                a, b = sorted(resolve_on(plan, ln, r[c], pnames) for c in ("from_stop", "to_stop"))
            except KeyError:
                continue
            if any(plan.in_core(s) for s in ln.stop_ids[a:b + 1]):
                want.setdefault(ends(plan, r, pnames), int(r["year_opens"]))
    out = {}
    key = {}
    for i, r in enumerate(rows):
        key[i] = ends(net, r, names) if r["kind"] != "via" else None
        y = want.get(key[i])
        if y is not None:
            out[i] = y
    # an extension can't open before a stage it attaches to (keep_attached): the earliest
    # stage it touches inherits its deadline, back along the line
    changed = True
    while changed:
        changed = False
        for i, y in list(out.items()):
            if rows[i]["kind"] != "extension" or key[i] is None:
                continue
            nb = [j for j in key if j != i and key[j] and key[j][0] == key[i][0] and key[j][1] & key[i][1]]
            if nb and min(out.get(j, 9999) for j in nb) > y:
                j = min(nb, key=lambda j: (int(rows[j]["year_opens"]), int(rows[j]["stage"])))
                out[j] = y
                changed = True
    return out


def _fair_order(net, rows, idx, value, oc, deadline, per_year):
    """Value order (best riders per $ first, a line's stages together), except that no county
    falls behind (staging.fair_share): once a county's population share (x ratio) of the capital
    committed so far covers its best remaining line, that line goes next (the county furthest
    behind first). Stages with a deadline count from about the year they open (the cumulative
    budget reaching it)."""
    fs = net.cfg["staging"].get("fair_share") or {}
    by_line = collections.defaultdict(list)
    for i in idx:
        by_line[rows[i]["line_id"]].append(i)
    lines = sorted(by_line, key=lambda lid: (-value.get(lid, 0.0), lid))
    if not fs.get("ratio"):
        return [i for lid in lines for i in by_line[lid]]
    cty, share = _station_counties(net)
    names = {k: v.name for k, v in net.stations.items()}
    ex = net.cfg["existing_year"]

    def weights(i):
        r = rows[i]
        ln = net.host_line(r["line_id"])
        try:
            a, b = sorted((resolve_on(net, ln, r["from_stop"], names), resolve_on(net, ln, r["to_stop"], names)))
        except KeyError:
            a, b = 0, len(ln.stop_ids) - 1
        c = collections.Counter(cty[s] for s in ln.stop_ids[a:b + 1])
        n = sum(c.values())
        return {k: v / n for k, v in c.items()}
    cost = {i: (oc[i][0] if oc[i] else 0.0) for i in range(len(rows))}
    line_w = {}
    for lid, ii in by_line.items():
        w = collections.Counter()
        for i in ii:
            for k, v in weights(i).items():
                w[k] += v * (cost[i] or 1e-6)
        tot = sum(w.values()) or 1.0
        line_w[lid] = {k: v / tot for k, v in w.items()}
    home = {lid: max(w, key=w.get) for lid, w in line_w.items()}
    dl = sorted(((y, cost[i], weights(i)) for i, y in deadline.items()), key=lambda d: d[:2])
    cum, total, k, order = collections.Counter(), 0.0, 0, []
    left = list(lines)
    while left:
        while k < len(dl) and dl[k][0] <= ex + total / per_year:   # deadline stages, about when they're funded
            for c, v in dl[k][2].items():
                cum[c] += v * dl[k][1]
            total += dl[k][1]
            k += 1
        best = {}
        for l in left:   # each county's best remaining line (left is in value order)
            best.setdefault(home[l], l)
        due = sorted((cum[c] / (share[c] * total), c) for c, l in best.items()
                     if total and cum[c] + sum(cost[i] for i in by_line[l]) * line_w[l].get(c, 0) <= fs["ratio"] * share[c] * total)
        pick = best[due[0][1]] if due else left[0]
        left.remove(pick)
        order += by_line[pick]
        for i in by_line[pick]:
            for c, v in line_w[pick].items():
                cum[c] += v * cost[i]
            total += cost[i]
    return order


def _exact_years(net, rows, log=print, scale=1.0, floor=None):
    """Move each stage to the earliest calendar year the flat budget allows, keeping
    the build order: stages are taken in order of their current year (then line and
    stage), each opens no earlier than the line's previous stage and no sooner than
    its construction time after existing_year, and its capital is spread over the
    construction years before opening; the cumulative spend may never pass
    budget x years (config.budget, with its tolerance). Locked and via rows keep
    their years. Stages past the horizon are scheduled last, after everything else,
    and stay past it if the money runs out. Returns new rows."""
    from . import network
    cfg = net.cfg
    ex, end = cfg["existing_year"], max(cfg["years"])
    cy = cfg["staging"]["construction_years"]
    per_year = cfg["budget"]["musd_per_year"] * (1 + cfg["budget"]["tolerance"]) * scale
    cmap = stage_costs(net, rows)               # with ownership as `net` (compiled from `rows`) has it
    oc = [cmap.get(id(r)) for r in rows]
    old = [dict(r) for r in rows]
    rows = [dict(r) for r in old]
    horizon = 2200
    priority = _priorities(net, rows)
    spend = [0.0] * (horizon - ex + 1)
    last = {}
    # locked stages reserve their money first; then the rest in build order, or, with
    # staging.priority = "value_per_musd", best riders per dollar first (line values from the
    # last full build, results/<scenario>/lines.csv), each line's stages in their own order
    by_value = cfg["staging"].get("priority") == "value_per_musd"
    value = _line_values(net) if by_value else {}
    if by_value:   # a line not measured yet (new since the last full build) ranks at its mode's median
        import statistics
        med = {m: statistics.median([v for l, v in value.items() if l in net.lines and net.lines[l].mode == m] or [0.0])
               for m in {ln.mode for ln in net.lines.values()}}
        value = {r["line_id"]: value.get(r["line_id"], med[net.host_line(r["line_id"]).mode]) for r in rows
                 if net.host_line(r["line_id"])}
        # locked and running stages first, then stages with a deadline (by it), then the rest by
        # value per $ with no county left behind (_fair_order)
        fixed = [i for i, r in enumerate(rows) if r.get("locked") == "1" or int(r["year_opens"]) <= ex]
        deadline = {i: y for i, y in _deadlines(net, rows).items() if i not in fixed}
        rest = sorted((i for i in range(len(rows)) if i not in deadline and i not in fixed),
                      key=lambda i: (rows[i]["line_id"], int(rows[i]["stage"])))
        order = (fixed + sorted(deadline, key=lambda i: (deadline[i], rows[i]["line_id"], int(rows[i]["stage"])))
                 + _fair_order(net, rows, rest, value, oc, deadline, per_year))
    else:
        deadline = {}
    if not by_value:
        order = sorted(range(len(rows)), key=lambda i: (rows[i].get("locked") != "1" and int(rows[i]["year_opens"]) > ex,
                                                        int(rows[i]["year_opens"]) > end, int(rows[i]["year_opens"]),
                                                        priority.get(i, 1e9), rows[i]["line_id"], int(rows[i]["stage"])))

    placed = list(unstaged_spending(net, rows))   # e.g. the D2 subway, built by a reroute edit
    bcfg = dict(cfg, budget=dict(cfg["budget"], musd_per_year=cfg["budget"]["musd_per_year"] * scale))

    def ok(items):
        """Does funding these items (as the budget check funds them) stay within the money accrued?"""
        sp = allocate_spending(items, bcfg, horizon)
        cum = 0.0
        for t in range(ex + 1, horizon):
            cum += sp.get(t, 0.0)
            if cum > per_year * (t - ex) + 1e-6:
                return False
        return True

    # by value, shared track and platforms are charged as the network charges them: once, in the
    # earliest year a placed stage opens them (so the result doesn't depend on who opened them
    # in the last schedule)
    pieces = _stage_pieces(net, rows) if by_value else {}
    charged, agg = {}, collections.Counter()

    def with_stage(i, t, commit=False):
        trial = agg if commit else collections.Counter(agg)
        for key, base, mode in pieces.get(i, ()):
            c = charged.get(key)
            if c is not None and c[0] <= t:
                continue
            if c is not None:
                trial[(c[0], c[2])] -= c[1] * network.cost_factor(cfg, c[0], c[2])
                base, mode = c[1], c[2]
            trial[(t, mode)] += base * network.cost_factor(cfg, t, mode)
            if commit:
                charged[key] = (t, base, mode)
        return placed + [(y, c, cy[m]) for (y, m), c in trial.items() if c > 1e-9]

    for i in order:
        r, o = rows[i], old[i]
        y0 = int(r["year_opens"])
        if r["kind"] == "via" or oc[i] is None:
            continue
        cost, mode = oc[i]
        n = cy[mode]
        if r.get("locked") == "1" or y0 <= ex:   # locked, or running today (a through-routed existing line)
            if by_value:
                with_stage(i, y0, commit=True)
            else:
                placed.append((y0, cost, n))
            last[r["line_id"]] = max(last.get(r["line_id"], 0), y0)
            continue
        lo = max(ex + n, last.get(r["line_id"], 0))
        if r["kind"] == "starter":   # a new line needs the network it joins: never earlier than planned
            host = net.host_line(r["line_id"])
            lo = max(lo, y0 if (y0 <= end and not by_value) else lo, floor.get(r["line_id"], 0),
                     floor.get(host.id, 0) if host else 0)
        hi = horizon - 10   # earlier if the money is there, later if it isn't
        fund = (lambda t: with_stage(i, t)) if by_value else (lambda t: placed + [(t, cost, n)])
        if i in deadline:     # by its deadline, as late as that allows (the money goes to value first)
            d = max(deadline[i], lo)
            y = next((t for t in [*range(d, lo - 1, -1), *range(d + 1, hi + 1)] if ok(fund(t))), None)
        else:
            y = next((t for t in range(lo, hi + 1) if ok(fund(t))), None)
        if y is None:
            y = max(y0, lo)   # keep it where it was (or after its line's previous stage)
        if y > end:
            r["note"] = f"after the {end} horizon"
        elif (r.get("note") or "").startswith(("after the", "deferred by the optimizer")):
            r["note"] = "value per $" if by_value else "optimizer"
        r["year_opens"] = str(y)
        if by_value:
            with_stage(i, y, commit=True)
        else:
            placed.append((y, cost, n))
        last[r["line_id"]] = y
    if by_value and cfg["staging"].get("min_starter_stops"):
        _no_stubs(net, rows, cfg["staging"]["min_starter_stops"], {id(rows[i]) for i in deadline})
    moved = sum(1 for a, b in zip(old, rows) if a["year_opens"] != b["year_opens"])
    if log:
        log(f"{moved} of {len(rows)} stages moved to their earliest affordable year")
    return renumber(keep_attached(net, rows))


def _stage_pieces(net, rows):
    """Row index -> [(piece, $M at 2025 prices before the cost factor, mode)]: the new track
    pieces (mode + station pair) and platforms (station + mode) a stage opens, shared ones
    included (whoever opens them first pays)."""
    from . import network
    cfg = net.cfg
    ex = cfg["existing_year"]
    names = {k: v.name for k, v in net.stations.items()}
    old_track, old_plat = set(), set()
    for ln in net.lines.values():
        for i, sg in enumerate(ln.segments):
            if sg.year <= ex:
                old_track.add((ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1]))))
        for sid, y in zip(ln.stop_ids, ln.stop_years):
            if y <= ex:
                old_plat.add((sid, ln.mode))
    out = {}
    for k, r in enumerate(rows):
        ln = net.host_line(r["line_id"])
        if ln is None or r["kind"] == "via":
            continue
        try:
            a, b = sorted((resolve_on(net, ln, r["from_stop"], names), resolve_on(net, ln, r["to_stop"], names)))
        except KeyError:
            continue
        ps = []
        for i in range(a, b):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if key not in old_track and not ln.segments[i].borrowed:
                ps.append((key, net.segment_cost(ln, i) / network.cost_factor(cfg, ln.segments[i].year, ln.mode), ln.mode))
        for i in range(a, b + 1):
            key = (ln.stop_ids[i], ln.mode)
            if key not in old_plat:
                ps.append((key, net.stop_cost(ln, i) / network.cost_factor(cfg, ln.stop_years[i], ln.mode), ln.mode))
        out[k] = ps
    return out


def _no_stubs(net, rows, min_stops, keep=()):
    """A new line doesn't open as a short stub years ahead of the rest (staging.min_starter_stops):
    a starter with fewer stops waits for its line's next stage and opens with it. Spending only
    moves later, so the budget still holds."""
    names = {k: v.name for k, v in net.stations.items()}
    by = collections.defaultdict(list)
    for r in rows:
        if r["kind"] != "via" and net.host_line(r["line_id"]) is not None:
            by[r["line_id"]].append(r)
    for lid, rs in by.items():
        rs.sort(key=lambda r: int(r["stage"]))
        st = rs[0]
        if st["kind"] != "starter" or len(rs) < 2 or st.get("locked") == "1" or int(st["year_opens"]) <= net.cfg["existing_year"] \
                or id(st) in keep:
            continue
        ln = net.host_line(lid)
        try:
            a, b = sorted((resolve_on(net, ln, st["from_stop"], names), resolve_on(net, ln, st["to_stop"], names)))
        except KeyError:
            continue
        if b - a + 1 < min_stops and int(rs[1]["year_opens"]) > int(st["year_opens"]):
            st["year_opens"] = rs[1]["year_opens"]


def keep_attached(net, rows):
    """An extension may not open before a stage it attaches to: each non-starter stage
    opens no earlier than the earliest stage of its line that shares one of its end
    stops (repeated until nothing moves)."""
    names = {k: v.name for k, v in net.stations.items()}
    by = collections.defaultdict(list)
    for r in rows:
        ln = net.host_line(r["line_id"])   # a through-routed line's stages price its part of the joined line
        if ln is None or r["kind"] == "via":
            continue
        try:
            a, b = sorted((resolve_on(net, ln, r["from_stop"], names), resolve_on(net, ln, r["to_stop"], names)))
        except KeyError:
            continue
        by[r["line_id"]].append((r, a, b))
    for stages in by.values():
        first = min(stages, key=lambda x: (int(x[0]["year_opens"]), int(x[0]["stage"])))[0]
        moved = True
        while moved:
            moved = False
            for r, a, b in stages:
                if r is first or r.get("locked") == "1":
                    continue
                touch = [int(o["year_opens"]) for o, c, d in stages if o is not r and (c in (a, b) or d in (a, b))]
                if touch and int(r["year_opens"]) < min(touch):
                    r["year_opens"] = str(min(touch))
                    moved = True
    return rows


def renumber(rows):
    """Stage numbers in opening order within each line (via rows keep their place)."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["line_id"]].append(r)
    for rs in by.values():
        rs.sort(key=lambda r: (int(r["year_opens"]), int(r["stage"])))
        for k, r in enumerate(rs, 1):
            r["stage"] = str(k)
            if r["kind"] in ("starter", "extension"):
                r["kind"] = "starter" if k == 1 else "extension"
    return sorted(rows, key=lambda r: (r["line_id"], int(r["stage"])))
