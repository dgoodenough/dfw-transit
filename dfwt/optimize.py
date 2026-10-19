"""Suggest a staged build order: which piece of which line opens in which interval.

    python -m dfwt optimize [--out staged] [--procs 3]

Writes scenarios/<out>/stages.csv, which `build` then evaluates next to the plan.
A person promotes it by copying the file to network/stages.csv.

Method (period-by-period greedy with lazy re-evaluation, scored by the real model):

1. Each proposed line is cut into *packages*: contiguous runs of segments cut at
   interchanges, shared-trunk ends, tunnel portals and existing phase breaks, sized
   between a minimum and config.staging.max_km_per_stage. Short BRT corridors stay whole.
   Stages marked locked=1 in stages.csv are kept exactly as written.
2. For each 5-year interval in turn, candidate moves are: start a line with a
   starter big enough to operate (config.staging.min_operable) that touches the
   network open that year, or extend an open line by one or two packages at either
   end. Each is scored by competitive commutes gained in that year per $M.
3. Moves are taken best-first while they gain anything and fit the constraints:
   cumulative spending (spread over construction years) within the flat
   budget, km per line per interval, and construction lead time. Unspent money
   carries forward. Scores are re-checked lazily: the top candidate is
   re-evaluated against the current schedule before it is accepted.
4. Packages still unbuilt after the last interval are left past the horizon and
   reported. The model never builds them because they gained nothing in their year.

Benefits are not additive (network effects), so this is a heuristic. A
two-package look-ahead lets a starter that only pays off with its neighbor
still be found.
"""
import collections
import csv
import heapq
import multiprocessing as mp
import os
import time

from . import config, geo, staging
from .network import NEVER, Line, Network, Segment

PAST = 2075  # "after the horizon"

_CTX = _BASE = _PKGS = None


# ---------------------------------------------------------------- packages
def station_neighbors(net, radius_km=0.4):
    nb = {s: {s} for s in net.stations}
    ids = list(net.stations)
    for i, a in enumerate(ids):
        A = net.stations[a]
        for b in ids[i + 1:]:
            B = net.stations[b]
            if abs(A.lat - B.lat) <= 0.005 and geo.hav_km(A.lat, A.lon, B.lat, B.lon) <= radius_km:
                nb[a].add(b)
                nb[b].add(a)
    for a, b, _, _ in net.transfers:
        if a in nb and b in nb:
            nb[a].add(b)
            nb[b].add(a)
    return nb


def make_packages(net, ln, nb, lo_km, hi_km):
    """[(seg_lo, seg_hi)] half-open segment ranges for one line."""
    n = len(ln.segments)
    if ln.mode == "brt" and ln.km <= hi_km:
        return [(0, n)]
    key = lambda l, i: (l.mode, frozenset((l.stop_ids[i], l.stop_ids[i + 1])))
    share = collections.defaultdict(set)
    for l2 in net.lines.values():
        for i in range(len(l2.segments)):
            share[key(l2, i)].add(l2.id)
    others = {s for l2 in net.lines.values() if l2.id != ln.id for s in l2.stop_ids}

    def infill(j):  # stops that open after their track can't be temporary termini
        return ln.stop_years[j] > min(ln.segments[k].year for k in (j - 1, j) if 0 <= k < n)

    soft = set()
    for j in range(1, n):
        if infill(j):
            continue
        if nb[ln.stop_ids[j]] & others or share[key(ln, j - 1)] != share[key(ln, j)] \
                or ln.segments[j - 1].grade != ln.segments[j].grade:
            soft.add(j)
    cuts, acc = [], 0.0
    for i in range(n - 1):
        acc += ln.segments[i].km
        j = i + 1
        if infill(j):
            continue
        if (acc >= lo_km and j in soft) or (acc + ln.segments[j].km > hi_km and acc >= lo_km / 2):
            cuts.append(j)
            acc = 0.0
    b = [0] + cuts + [n]
    pk = [(b[k], b[k + 1]) for k in range(len(b) - 1)]
    km = lambda p: sum(ln.segments[k].km for k in range(*p))
    merged = True
    while merged and len(pk) > 1:  # fold short tails into a neighbor
        merged = False
        for k, p in enumerate(pk):
            if km(p) < lo_km / 2:
                j = k + 1 if k + 1 < len(pk) else k - 1
                lo, hi = min(pk[k][0], pk[j][0]), max(pk[k][1], pk[j][1])
                pk[min(k, j):max(k, j) + 1] = [(lo, hi)]
                merged = True
                break
    return pk


# ---------------------------------------------------------------- schedule -> network
def apply_schedule(base, sched, pkgs):
    """A copy of `base` with each scheduled line's years set from package years."""
    lines = dict(base.lines)
    for lid, yrs in sched.items():
        l0 = base.lines[lid]
        n = len(l0.segments)
        segy = [NEVER] * n
        for (a, b), y in zip(pkgs[lid], yrs):
            for k in range(a, b):
                segy[k] = y
        stop_y = []
        for i in range(len(l0.stop_ids)):
            adj = [k for k in (i - 1, i) if 0 <= k < n]
            ty = min(segy[k] for k in adj)
            delay = max(0, l0.stop_years[i] - min(l0.segments[k].year for k in adj))
            stop_y.append(ty + delay if ty < NEVER else NEVER)
        lines[lid] = Line(l0.id, l0.name, l0.mode, l0.status, l0.color, l0.headway, l0.notes,
                          list(l0.stop_ids), stop_y,
                          [Segment(y, s.grade, s.pts, s.km) for s, y in zip(l0.segments, segy)], list(l0.service))
    net = Network(base.stations, lines, base.cfg, "staged", base.transfers)
    return net


def _score(args):
    sched, year = args
    from .evaluate import run_year
    net = apply_schedule(_BASE, {k: list(v) for k, v in sched}, _PKGS)
    return run_year(_CTX, net, year, want_loads=False)["competitive_commutes"]


def _frozen(sched):
    return tuple((k, tuple(v)) for k, v in sorted(sched.items()))


# ---------------------------------------------------------------- optimizer
def optimize(out="staged", procs=3, log=print):
    global _CTX, _BASE, _PKGS
    from .evaluate import Context
    cfg = config.load()
    rules = cfg["staging"]
    base = Network.load()
    _BASE, _CTX = base, Context(cfg)
    names = {k: v.name for k, v in base.stations.items()}
    years = cfg["years"]
    ex = cfg["existing_year"]
    per_year = cfg["budget"]["musd_per_year"] * (1 + cfg["budget"]["tolerance"])
    nb = station_neighbors(base)

    locked = collections.defaultdict(list)
    for r in base.stage_rows:
        if r.get("locked") == "1":
            locked[r["line_id"]].append(r)
    free = [l for l in base.lines.values() if l.status != "existing" and l.id not in base.variants]
    pkgs, fixed = {}, {}
    for ln in free:
        lo = rules["min_operable"][ln.mode][0]
        hi = rules["max_km_per_stage"][ln.mode]
        # locked stages become fixed packages; the rest is cut automatically
        lock_ranges = []
        for r in locked.get(ln.id, []):
            a, b = sorted((staging.resolve(r["from_stop"], ln.stop_ids, names),
                           staging.resolve(r["to_stop"], ln.stop_ids, names)))
            lock_ranges.append((a, b, int(r["year_opens"])))
        pk, fx = [], []
        cursor = 0
        for a, b, y in sorted(lock_ranges) + [(len(ln.segments), len(ln.segments), None)]:
            if a > cursor:
                sub = Line(ln.id, ln.name, ln.mode, ln.status, ln.color, ln.headway, ln.notes,
                           ln.stop_ids[cursor:a + 1], ln.stop_years[cursor:a + 1], ln.segments[cursor:a])
                for p in make_packages(base, sub, nb, lo, hi):
                    pk.append((p[0] + cursor, p[1] + cursor))
                    fx.append(None)
            if y is not None:
                pk.append((a, b))
                fx.append(y)
            cursor = max(cursor, b)
        pkgs[ln.id], fixed[ln.id] = pk, fx
    _PKGS = pkgs
    pkm = {lid: [sum(base.lines[lid].segments[k].km for k in range(a, b)) for a, b in pk] for lid, pk in pkgs.items()}
    log(f"{len(free)} lines cut into {sum(len(p) for p in pkgs.values())} packages "
        f"({sum(1 for f in fixed.values() for y in f if y)} locked)")

    sched = {lid: [y if y else NEVER for y in fixed[lid]] for lid in pkgs}
    infill = {lid: [ln.stop_years[j] > min(ln.segments[k].year for k in (j - 1, j) if 0 <= k < len(ln.segments))
                    for j in range(len(ln.stop_ids))] for lid, ln in ((l, base.lines[l]) for l in pkgs)}

    def spend_ok(s):
        net = apply_schedule(base, s, pkgs)
        sp = staging.spend_by_year(net)
        cum = 0.0
        for y in range(ex + 1, max(years) + 1):
            cum += sp.get(y, 0.0)
            if cum > per_year * (y - ex) + 1e-6:
                return False
        return True

    def capex(s, y):
        net = apply_schedule(base, s, pkgs)
        own = net.track_owner()
        return sum(net.line_cost_musd(l, by_year=y, owner=own) for l in net.lines.values())

    def moves_for(lid, s, t, openst, period_km):
        ln = base.lines[lid]
        yrs = s[lid]
        if t - rules["construction_years"][ln.mode] < ex + 1:
            return []
        built = [i for i, y in enumerate(yrs) if y <= t]
        cands = []
        if not built:
            mink, minst = rules["min_operable"][ln.mode]
            for i, (a, b) in enumerate(pkgs[lid]):
                # infill stops open later than their track, so they can't be the link to the network
                if not any(nb[ln.stop_ids[j]] & openst for j in range(a, b + 1) if not infill[lid][j]):
                    continue
                for grp in ([i], [i, i + 1], [i - 1, i]):
                    if min(grp) < 0 or max(grp) >= len(yrs) or any(yrs[k] < NEVER for k in grp):
                        continue
                    km = sum(pkm[lid][k] for k in grp)
                    nst = pkgs[lid][max(grp)][1] - pkgs[lid][min(grp)][0] + 1
                    if km >= mink and nst >= minst or len(grp) == len(yrs):
                        cands.append(grp)
        else:
            lo, hi = min(built), max(built)
            for d in (1, 2):
                for grp in (list(range(hi + 1, hi + d + 1)), list(range(lo - d, lo))):
                    if grp and min(grp) >= 0 and max(grp) < len(yrs) and all(yrs[k] == NEVER for k in grp):
                        cands.append(grp)
        out = []
        for grp in cands:
            km = sum(pkm[lid][k] for k in grp)
            if period_km[lid] + km > rules["max_km_per_interval"][ln.mode]:
                continue
            s2 = {k: list(v) for k, v in s.items()}
            for k in grp:
                s2[lid][k] = t
            out.append((lid, tuple(grp), km, s2))
        return out

    t0 = time.time()
    evals = 0
    trace = []
    with mp.get_context("fork").Pool(procs) as pool:
        for t in years[1:]:
            period_km = collections.Counter()
            net = apply_schedule(base, sched, pkgs)
            openst = {x for r in net.runs(t) for x in r.stops}
            base_cc = _score((_frozen(sched), t))
            base_cost = capex(sched, t)
            cands = [m for lid in pkgs for m in moves_for(lid, sched, t, openst, period_km)]
            cands = [m for m in cands if spend_ok(m[3])]
            scores = pool.map(_score, [(_frozen(m[3]), t) for m in cands], chunksize=1) if cands else []
            evals += len(cands) + 1
            heap = []
            for m, cc in zip(cands, scores):
                cost = max(capex(m[3], t) - base_cost, 1.0)
                heapq.heappush(heap, (-(cc - base_cc) / cost, id(m), m, _frozen(sched)))
            while heap:
                neg, _, m, seen = heapq.heappop(heap)
                lid, grp, km, s2 = m
                # a move scored earlier may no longer fit: the line may have opened elsewhere since
                if grp not in {mv[1] for mv in moves_for(lid, sched, t, openst, period_km)}:
                    continue
                s2 = {k: list(v) for k, v in sched.items()}
                for k in grp:
                    s2[lid][k] = t
                if seen != _frozen(sched):  # stale score: re-check against the current schedule
                    if not spend_ok(s2):
                        continue
                    cc = _score((_frozen(s2), t))
                    evals += 1
                    cost = max(capex(s2, t) - base_cost, 1.0)
                    ratio = (cc - base_cc) / cost
                    if heap and ratio < -heap[0][0]:
                        heapq.heappush(heap, (-ratio, id(m), (lid, grp, km, s2), _frozen(sched)))
                        continue
                else:
                    cc = base_cc - neg * max(capex(s2, t) - base_cost, 1.0)
                    ratio = -neg
                if ratio <= 0:
                    break
                if not spend_ok(s2):
                    continue
                gain = cc - base_cc
                sched, base_cc, base_cost = s2, cc, capex(s2, t)
                period_km[lid] += km
                a, b = pkgs[lid][min(grp)][0], pkgs[lid][max(grp)][1]
                trace.append((t, lid, base.lines[lid].name, names[base.lines[lid].stop_ids[a]],
                              names[base.lines[lid].stop_ids[b]], round(km, 1), round(gain), round(ratio, 2)))
                log(f"  {t} {base.lines[lid].name}: {trace[-1][3]} - {trace[-1][4]} "
                    f"({km:.1f} km, +{gain:,.0f} commutes, {ratio:.2f}/$M)")
                # new moves for this line (it grew), scored against the new schedule
                net = apply_schedule(base, sched, pkgs)
                openst = {x for r in net.runs(t) for x in r.stops}
                fresh = [mv for l2 in pkgs for mv in moves_for(l2, sched, t, openst, period_km)
                         if l2 == lid or not any(sched[l2][k] != NEVER for k in range(len(sched[l2])))]
                for mv in fresh:
                    heapq.heappush(heap, (-1e9, id(mv), mv, None))  # force a fresh score when popped
            log(f"{t}: {sum(1 for x in trace if x[0] == t)} openings, {evals} evaluations, {time.time() - t0:.0f}s")

    left = {lid: [k for k, y in enumerate(v) if y == NEVER] for lid, v in sched.items()}
    for lid, ks in left.items():
        for k in ks:
            sched[lid][k] = PAST
    rows = to_stage_rows(base, sched, pkgs, fixed, locked, names, rules)
    folder = config.path("scenarios", out)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "stages.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=staging.STAGE_COLS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(folder, "optimizer_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["year", "line_id", "line", "from", "to", "km", "commutes_gained", "commutes_per_musd"])
        w.writerows(trace)
    unbuilt = [(base.lines[l].name, round(sum(pkm[l][k] for k in ks), 1)) for l, ks in left.items() if ks]
    log(f"wrote scenarios/{out}/stages.csv ({len(rows)} stages, {evals} evaluations, {time.time() - t0:.0f}s)")
    if unbuilt:
        log("left past 2070 (no measurable gain in any interval): " + ", ".join(f"{n} {k} km" for n, k in unbuilt))
    return rows


def to_stage_rows(base, sched, pkgs, fixed, locked, names, rules):
    rows = [r for l, rs in locked.items() for r in rs if l not in sched]
    # existing lines and anything not optimized keep their plan stages
    done = set(sched)
    rows += [r for r in base.stage_rows if r["line_id"] not in done and r.get("locked") != "1"]
    for lid, yrs in sched.items():
        ln = base.lines[lid]
        groups = []  # merge adjacent packages opening together, within the stage size limit
        for (a, b), y, fx in zip(pkgs[lid], yrs, fixed[lid]):
            km = sum(s.km for s in ln.segments[a:b])
            if groups and groups[-1][2] == y and groups[-1][1] == a and not fx and not groups[-1][4] \
                    and groups[-1][3] + km <= rules["max_km_per_stage"][ln.mode]:
                g = groups[-1]
                groups[-1] = (g[0], b, y, g[3] + km, False)
            else:
                groups.append((a, b, y, km, bool(fx)))
        order = sorted(groups, key=lambda g: (g[2], g[0]))
        lock_note = {(staging.resolve(r["from_stop"], ln.stop_ids, names), int(r["year_opens"])): r
                     for r in locked.get(lid, [])}
        for n, (a, b, y, km, fx) in enumerate(order, 1):
            src = lock_note.get((a, y)) or lock_note.get((b, y))
            rows.append({"line_id": lid, "stage": n, "kind": "starter" if n == 1 else "extension",
                         "from_stop": staging.stop_ref(ln.stop_ids, names, a),
                         "to_stop": staging.stop_ref(ln.stop_ids, names, b), "year_opens": y,
                         "locked": "1" if fx else "",
                         "note": src["note"] if fx and src else ("after the 2070 horizon" if y == PAST else "optimizer")})
    rows.sort(key=lambda r: (r["line_id"], int(r["stage"])))
    return rows
