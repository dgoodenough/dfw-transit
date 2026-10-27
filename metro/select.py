"""Greedy budgeted selection of candidate lines (step 2d).

Lazy greedy (CELF): a candidate's value can only fall as lines are chosen (the sketch counts
trips over the best share already offered), so stale values are upper bounds and only the top
of the queue needs re-evaluating. Each pick:
  * the most new daily trips per $M of (capital + value_opex_years x operating cost);
  * stop when the best is below selection.min_trips_per_musd;
  * a pick that would overrun the budget is skipped (cheaper ones may still fit);
  * a pick running within duplicate_m of chosen or existing lines for more than
    duplicate_share of its length is rejected as a duplicate, unless it extends a chosen
    line of its mode (that line's centers are the start or end of the candidate's): then the
    chosen line is replaced and only the extra cost is charged.
"""
import heapq

from . import geom


def extends(c, d):
    """Does candidate c extend chosen line d (same mode, d's centers a prefix/suffix of c's)?"""
    if c.mode != d.mode or c.kind != d.kind or len(c.seq) <= len(d.seq):
        return False
    a, b = list(c.seq), list(d.seq)
    k = len(b)
    return a[:k] == b or a[-k:] == b or a[:k] == b[::-1] or a[-k:] == b[::-1]


def run(cands, sketch, budget, gp, cfg, existing_lines, log=print):
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
        if dup > sel["duplicate_share"]:
            near = _nearest_name(c, [d for d in chosen if d is not ext], sel["duplicate_m"] / 1000)
            c.status, c.reason = "rejected", f"duplicate: {dup:.0%} of it within {sel['duplicate_m']} m of " + (
                f"chosen line {near}" if near else "existing transit")
            continue
        if spent + cap > budget:
            c.status, c.reason = "rejected", f"over budget (needs ${cap / 1e3:.1f}B, ${(budget - spent) / 1e3:.1f}B left)"
            continue
        sketch.line(c.mode, c.station_xy, c.along, c.pnr, c.pnr_cap, commit=True)
        order += 1
        spent += cap
        c.status, c.order, c.cost_charged = "chosen", order, cap
        c.reason = f"{c.new_trips:,.0f} new daily trips for ${cap / 1e3:.2f}B capital ({c.ratio:.2f} per $M incl. opex)"
        if ext:
            ext.status, ext.reason = "replaced", f"extended by {c.uid}"
            chosen.remove(ext)
            c.reason += f"; extends {ext.uid}"
        chosen.append(c)
        log(f"  {order:2d}. {c.uid} {c.mode:9} {c.km:5.1f} km  {c.name[:44]:44}  +{c.new_trips:7,.0f} trips  "
            f"${cap / 1e3:5.2f}B  {c.ratio:5.2f}/$M  spent ${spent / 1e3:.1f}B")
    for _, u in heap:
        d = by[u]
        if d.status == "pool":
            d.status, d.reason = "rejected", "not reached (line limit)" if len(chosen) >= sel["max_lines"] else "not reached"
    return chosen, spent


def _nearest_name(c, chosen, r_km):
    best = None
    for d in chosen:
        s = geom.share_near(c.P, [d.P], r_km)
        if best is None or s > best[0]:
            best = (s, d)
    return f"{best[1].uid} ({best[1].name})" if best and best[0] > 0.2 else None
