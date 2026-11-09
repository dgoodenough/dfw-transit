"""Greedy budgeted selection of candidate lines (step 2d).

Lazy greedy (CELF): a candidate's value can only fall as lines are chosen (the sketch counts
trips over the best share already offered), so stale values are upper bounds and only the top
of the queue needs re-evaluating. Each pick:
  * the most new daily trips per $M of (capital + value_opex_years x operating cost);
  * stop when the best is below selection.min_trips_per_musd;
  * a pick that would overrun the budget is skipped (cheaper ones may still fit);
  * a pick with no station within stations.transfer_m of today's or a chosen line's stations
    waits (it would be an island) and is retried after the next pick;
  * a pick running within duplicate_m of chosen or existing lines for more than
    duplicate_share of its length is rejected as a duplicate, unless it extends a chosen
    line of its mode (that line's centers are the start or end of the candidate's): then the
    chosen line is replaced and only the extra cost is charged; or unless it runs at least
    branch_min_km on its own (a branch off a shared trunk): then the share of it within
    branch_share_m of chosen lines of its mode isn't charged;
  * a pick that would put more than max_per_segment[mode] lines of its mode on the same street
    for more than stack_km (lines within branch_share_m of each other) is rejected: the corridor
    is full (texas-transit study/hsr_buildout.md, Phase 3: at most 2 BRT or 3 metro lines a street).
    Off by default (null): on Austin a cap of 2 BRT lines cost 6% of the network's riders and left the
    median BRT line's overlap where it was (75%), since that overlap is branches sharing a trunk and
    BRT alongside rail, not duplicates.
"""
import heapq
import math

from . import geom


def extends(c, d):
    """Does candidate c extend chosen line d (same mode, d's centers a prefix/suffix of c's)?"""
    if c.mode != d.mode or c.kind != d.kind or len(c.seq) <= len(d.seq):
        return False
    a, b = list(c.seq), list(d.seq)
    k = len(b)
    return a[:k] == b or a[-k:] == b or a[:k] == b[::-1] or a[-k:] == b[::-1]


def connected(c, stations, r_km):
    """Does a station of c lie within r_km of one of `stations` [(x, y)]?"""
    return any(math.dist(p, q) <= r_km for p in c.station_xy for q in stations
               if abs(p[0] - q[0]) <= r_km and abs(p[1] - q[1]) <= r_km)


def stacked_km(P, same, r_km, limit, step_km=0.25):
    """The longest stretch of P (km) along which `limit` or more of the routes `same` already run
    within r_km: adding P there would make limit + 1."""
    if len(same) < limit:
        return 0.0
    grid = {}
    for k, Q in enumerate(same):
        for q in geom.resample(Q, step_km):
            grid.setdefault((int(q[0] // r_km), int(q[1] // r_km)), []).append((k, q))
    run_, best = 0, 0
    for p in geom.resample(P, step_km):
        cx, cy = int(p[0] // r_km), int(p[1] // r_km)
        near = {k for i in (cx - 1, cx, cx + 1) for j in (cy - 1, cy, cy + 1)
                for k, q in grid.get((i, j), ()) if math.dist(p, q) <= r_km}
        run_ = run_ + 1 if len(near) >= limit else 0
        best = max(best, run_)
    return best * step_km


def run(cands, sketch, budget, gp, cfg, existing_lines, existing_stations, log=print):
    sel = gp["selection"]
    years = cfg["staging"].get("value_opex_years", 20)
    floor = sel["min_trips_per_musd"]
    chosen = []
    spent = 0.0
    heap = []
    for c in cands:
        if c.status == "pool":
            heapq.heappush(heap, (-c.ratio, c.uid))
    by = {c.uid: c for c in cands}
    exist_P = [P for P in existing_lines]
    net_st = list(existing_stations)      # stations of the network so far (today's + chosen)
    r_link = gp["stations"]["transfer_m"] / 1000
    waiting = []                          # best when their turn came, but not yet touching the network
    order = 0
    while heap and len(chosen) < sel["max_lines"]:
        _, uid = heapq.heappop(heap)
        c = by[uid]
        if c.status != "pool":
            continue
        ext = next((d for d in chosen if extends(c, d)), None)
        cap = c.capital - (ext.capital if ext else 0.0)
        opx = c.opex - (ext.opex if ext else 0.0)
        cost = max(cap + years * opx, 1.0)
        r = sketch.line(c.mode, c.station_xy, c.along, c.pnr, c.pnr_cap, commit=False)
        c.new_trips = r["new_trips"]
        c.ratio = c.new_trips / cost
        if heap and c.ratio < -heap[0][0] - 1e-12:
            heapq.heappush(heap, (-c.ratio, uid))
            continue
        if c.ratio < floor:
            c.status, c.reason = "rejected", f"below {floor} new trips per $M when its turn came ({c.ratio:.2f})"
            for _, u in heap:
                d = by[u]
                if d.status == "pool":
                    d.status, d.reason = "rejected", f"below {floor} new trips per $M (upper bound {d.ratio:.2f})"
            break
        others = [d.P for d in chosen if d is not ext] + exist_P
        dup = geom.share_near(c.P, others, sel["duplicate_m"] / 1000) if others else 0.0
        branch = None
        if dup > sel["duplicate_share"]:
            own_km = c.km * (1 - dup)
            if own_km < (sel.get("branch_min_km") or float("inf")):
                near = _nearest_name(c, [d for d in chosen if d is not ext], sel["duplicate_m"] / 1000)
                c.status, c.reason = "rejected", f"duplicate: {dup:.0%} of it within {sel['duplicate_m']} m of " + (
                    f"chosen line {near}" if near else "existing transit") + (
                    f", {own_km:.1f} km of its own" if sel.get("branch_min_km") else "")
                continue
            # a branch: shares a trunk but runs at least branch_min_km on its own. Track it shares with a chosen
            # line of its mode (stations within the tables' snap distance, so the same station pairs) isn't built
            # twice: charge only its own share (the network's costs split shared track the same way)
            same = [d.P for d in chosen if d is not ext and d.mode == c.mode]
            shared = geom.share_near(c.P, same, sel.get("branch_share_m", 250) / 1000) if same else 0.0
            cap *= 1 - shared
            cost = max(cap + years * opx, 1.0)
            c.ratio = c.new_trips / cost
            branch = (dup, own_km, shared)
        lim = (sel.get("max_per_segment") or {}).get(c.mode)
        if lim:
            same_all = [d.P for d in chosen if d is not ext and d.mode == c.mode]
            km_full = stacked_km(c.P, same_all, sel.get("branch_share_m", 250) / 1000, lim)
            if km_full > sel.get("stack_km", 1.0):
                c.status, c.reason = "rejected", (f"corridor full: {km_full:.1f} km of it on a street that already "
                                                  f"has {lim} chosen {c.mode} lines")
                continue
        if spent + cap > budget:
            c.status, c.reason = "rejected", f"over budget (needs ${cap / 1e3:.1f}B, ${(budget - spent) / 1e3:.1f}B left)"
            continue
        if net_st and not ext and not connected(c, net_st, r_link):
            waiting.append(c)             # retried after the next pick (which may reach it)
            c.status = "waiting"
            continue
        sketch.line(c.mode, c.station_xy, c.along, c.pnr, c.pnr_cap, commit=True)
        order += 1
        spent += cap
        c.status, c.order, c.cost_charged = "chosen", order, cap
        c.reason = f"{c.new_trips:,.0f} new daily trips for ${cap / 1e3:.2f}B capital ({c.ratio:.2f} per $M incl. opex)"
        if branch:
            c.reason += (f"; a branch: {branch[0]:.0%} within {sel['duplicate_m']} m of other lines, {branch[1]:.1f} km "
                         f"of its own, {branch[2]:.0%} on a same-mode trunk (not charged)")
        if ext:
            ext.status, ext.reason = "replaced", f"extended by {c.uid}"
            chosen.remove(ext)
            c.reason += f"; extends {ext.uid}"
        chosen.append(c)
        net_st += c.station_xy
        for d in waiting:
            d.status = "pool"
            heapq.heappush(heap, (-d.ratio, d.uid))
        waiting = []
        log(f"  {order:2d}. {c.uid} {c.mode:9} {c.km:5.1f} km  {c.name[:44]:44}  +{c.new_trips:7,.0f} trips  "
            f"${cap / 1e3:5.2f}B  {c.ratio:5.2f}/$M  spent ${spent / 1e3:.1f}B")
    for _, u in heap:
        d = by[u]
        if d.status == "pool":
            d.status, d.reason = "rejected", "not reached (line limit)" if len(chosen) >= sel["max_lines"] else "not reached"
    for d in waiting:
        d.status, d.reason = "rejected", f"no station within {gp['stations']['transfer_m']} m of the network (an island)"
    return chosen, spent


def _nearest_name(c, chosen, r_km):
    best = None
    for d in chosen:
        s = geom.share_near(c.P, [d.P], r_km)
        if best is None or s > best[0]:
            best = (s, d)
    return f"{best[1].uid} ({best[1].name})" if best and best[0] > 0.2 else None
