"""Line planning: a local search over the whole network on the full model (step 4c).

The greedy (metro/select.py) picks lines one at a time on the sketch, which counts a line's riders
between its own stations: no transfers, no network. The full model then prunes what it picked
(metro/modelselect.py). Here the network that survives is improved as a whole, on the same full
model: dfwt assigns riders on a change-and-go graph, each wait half the line's headway and each
change a penalty (dfwt/graph.py), so through-running, transfers and frequency all count. One land
use (the network's, every line open, in the judge year) is fixed so that moves compare:

  J(S) = new daily trips(S) - floor x sum over lines (capital + value_opex_years x opex at its headway)
         - anchor_trips x (must-serve anchors with no station within anchor_m)

with the network's capital (shared track split among its lines) within the budget. floor is the
pruning's own (selection.model.min_trips_per_musd): a line is worth its cost when it carries that
many trips per $M. This is the line-planning program of texas-transit's study/cabinet/network.md
(after Borndoerfer, Groetschel and Pfetsch, and Schoebel), solved by local search rather than as
an integer program, since each evaluation is a run of the demand model.

Moves, each from the current network:
  merge    two lines of a mode ending in the same downtown core from opposite sides run as one
           through line (metro/through.py)
  anchor   for each must-serve anchor no station serves: add the best pool line that serves it, or
           swap it for the chosen line it overlaps most
  drop     a line, whose riders other lines may carry
  add      a pool line that fits the money left
  swap     one of the weakest lines for a pool line along the same corridor (longer, shorter or
           rerouted)
  headway  one step more or less frequent (less only if the line's peak load still fits)

Each round evaluates the drops (which also give every line's value in the network), then the other
moves, in parallel; applies the improving moves best first while they touch different lines;
checks the combination; and repeats until nothing improves J or the rounds run out.
"""
import math
import os

from dfwt import evaluate

from . import candidates, geom, sketch, through

_W = {}


def _job(job):
    key, uids, hw = job
    by = _W["by"]
    S = [by[u] for u in uids]
    for c in S:
        c.headway = hw.get(c.uid)
    net, uid_of = _W["build"](S)
    if net is None or not net.lines:
        return key, 0.0, 0.0
    r = evaluate.run_year(_W["ctx"], net, _W["year"], want_loads=False, inputs=_W["inputs"])
    cap = sum(net.shared_cost_musd(net.lines[lid]) for lid in uid_of)
    return key, r["daily_trips"], cap


def _evaluate(jobs, procs):
    if procs <= 1 or len(jobs) <= 2:
        return {k: (t, c) for k, t, c in map(_job, jobs)}
    import multiprocessing as mp
    with mp.get_context("fork").Pool(procs) as pool:
        return {k: (t, c) for k, t, c in pool.map(_job, jobs, chunksize=1)}


class Planner:
    def __init__(self, cands, build_net, ctx, cfg, gp, budget, year, make, by, downtown_ids, links,
                 anchors, existing_xy, inputs, log=print):
        lp = gp["selection"].get("plan", {})
        mc = gp["selection"]["model"]
        self.cfg, self.gp, self.budget, self.make, self.by, self.links, self.log = cfg, gp, budget, make, by, links, log
        self.downtown_ids = downtown_ids
        self.floor = lp.get("floor") or mc["min_trips_per_musd"]
        self.years = cfg["staging"].get("value_opex_years", 20)
        self.anchor_trips = lp.get("anchor_trips", 1000.0)
        self.anchor_km = lp.get("anchor_m", 600) / 1000
        self.rounds = lp.get("rounds", 3)
        self.k_swap = lp.get("swap_weakest", 8)
        self.k_add = lp.get("add_best", 8)
        self.headways = lp.get("headways", {})
        self.procs = lp.get("procs") or max(1, min(4, (os.cpu_count() or 2) - 1))
        self.anchors = [(n, x, y) for n, kind, x, y in anchors if kind in lp.get("must_serve", ("downtown", "airport", "university", "medical"))]
        self.existing_xy = existing_xy
        self.pool = {c.uid: c for c in cands if c.mode and c.stops and c.status != "no mode"
                     and not c.reason.startswith("duplicate of existing")}
        self.through = {}   # seq -> made through cand (or None)
        _W.update(ctx=ctx, build=build_net, year=year, inputs=inputs, by=self.pool)
        self.history = []

    # ---------------------------------------------------------------- the objective
    def opex(self, c, hw):
        return candidates.opex_musd(self.cfg, c.mode, c.stops, hw) if hw else c.opex

    def unserved(self, S):
        pts = list(self.existing_xy) + [p for u in S for p in self.pool[u].station_xy]
        out = []
        for n, x, y in self.anchors:
            r = self.anchor_km
            if not any(abs(p[0] - x) <= r and abs(p[1] - y) <= r and math.dist(p, (x, y)) <= r for p in pts):
                out.append(n)
        return out

    def J(self, S, H, trips, cap):
        if cap > self.budget + 1e-6:
            return -math.inf
        opx = sum(self.opex(self.pool[u], H.get(u)) for u in S)
        return trips - self.floor * (cap + self.years * opx) - self.anchor_trips * len(self.unserved(S))

    def run_moves(self, moves, S, H):
        """moves: [(name, S', H')] -> [(J, name, S', H', trips, cap)]."""
        jobs = [(k, tuple(sorted(S2)), {u: h for u, h in H2.items() if u in S2}) for k, (_, S2, H2) in enumerate(moves)]
        res = _evaluate(jobs, self.procs)
        # the network's capital plus the downtown terminals its costs leave out (candidates.terminal_cost)
        res = {k: (t, c + sum(getattr(self.pool[u], "terminal_cost", 0.0) for u in moves[k][1])) for k, (t, c) in res.items()}
        return [(self.J(S2, H2, *res[k]), nm, S2, H2) + res[k] for k, (nm, S2, H2) in enumerate(moves)]

    # ---------------------------------------------------------------- moves
    def corridor(self, a, b, r=0.4):
        return geom.share_near(b.P, [a.P], r) if a.P and b.P else 0.0

    def merges(self, S, H):
        cs = [self.pool[u] for u in S]
        out = []
        tc = self.gp["selection"].get("through", {})
        lp = self.gp["selection"].get("plan", {})
        for ang, a, b, seq, routes, d in through.options(cs, self.by, self.downtown_ids,
                                                          lp.get("merge_min_angle_deg", tc.get("min_angle_deg", 135)),
                                                          self.links, tc.get("core_km", 3.0)):
            if seq not in self.through:
                t = self.make(seq, routes)
                self.through[seq] = t if t is not None and t.mode == a.mode and t.status == "pool" else None
                if self.through[seq] is not None:
                    self.pool[t.uid] = t
            t = self.through[seq]
            if t is not None and t.uid not in S:
                out.append((f"merge {a.uid} + {b.uid} into through line {t.uid} ({ang:.0f} degrees)",
                            (S - {a.uid, b.uid}) | {t.uid}, dict(H)))
        return out

    def anchor_moves(self, S, H, cap):
        out = []
        free = self.budget - cap
        for n, x, y in self.anchors:
            if n not in self.unserved(S):
                continue
            serving = [c for u, c in self.pool.items() if u not in S and
                       any(math.dist(p, (x, y)) <= self.anchor_km for p in c.station_xy)]
            for c in sorted(serving, key=lambda c: -c.ratio)[:3]:
                if c.capital <= free:
                    out.append((f"add {c.uid} to serve {n}", S | {c.uid}, dict(H)))
                near = max((u for u in S), key=lambda u: self.corridor(self.pool[u], c), default=None)
                if near and self.corridor(self.pool[near], c) >= 0.3:
                    out.append((f"swap {near} for {c.uid} to serve {n}", (S - {near}) | {c.uid}, dict(H)))
        return out

    def adds(self, S, H, cap):
        free = self.budget - cap
        chosen = [self.pool[u].P for u in S]
        opts = [c for u, c in self.pool.items() if u not in S and c.capital <= free and c.ratio > 0
                and (not chosen or geom.share_near(c.P, chosen, 0.4) <= 0.5)]
        return [(f"add {c.uid}", S | {c.uid}, dict(H)) for c in sorted(opts, key=lambda c: -c.ratio)[:self.k_add]]

    def swaps(self, S, H, weakest):
        out = []
        for u in weakest:
            a = self.pool[u]
            alts = [c for v, c in self.pool.items() if v not in S and c.kind == a.kind and
                    self.corridor(a, c) >= 0.5 and self.corridor(c, a) >= 0.5]
            for c in sorted(alts, key=lambda c: -c.ratio)[:2]:
                out.append((f"swap {u} for {c.uid} ({c.km:.0f} km against {a.km:.0f})", (S - {u}) | {c.uid}, dict(H)))
        return out

    def headway_moves(self, S, H, strongest, weakest):
        out = []
        for u, direction in [(u, -1) for u in strongest] + [(u, +1) for u in weakest]:
            c = self.pool[u]
            opts = sorted(self.headways.get(c.mode, []))
            cur = H.get(u) or self.cfg["modes"][c.mode]["default_headway_min"]
            nxt = [h for h in opts if (h < cur if direction < 0 else h > cur)]
            if not nxt:
                continue
            h = max(nxt) if direction < 0 else min(nxt)
            if direction > 0 and sketch.capacity_per_hour(self.cfg, c.mode, h) < c.peak_hour_load:
                continue
            H2 = dict(H)
            H2[u] = h
            out.append((f"{c.uid} every {h:g} min (was {cur:g})", set(S), H2))
        return out

    # ---------------------------------------------------------------- the search
    def run(self, chosen):
        S = {c.uid for c in chosen}
        for c in chosen:
            self.pool[c.uid] = c
        H = {c.uid: c.headway for c in chosen if getattr(c, "headway", None)}
        (j0, _, _, _, t0, cap0), = self.run_moves([("start", S, H)], S, H)
        cur = (j0, S, H, t0, cap0)
        self.start = {"J": j0, "trips": t0, "capital": cap0, "lines": len(S), "unserved": self.unserved(S)}
        self.log(f"  line planning: {len(S)} lines, {t0:,.0f} daily trips, ${cap0 / 1e3:.1f}B, J {j0:,.0f}, "
                 f"{len(self.start['unserved'])} must-serve anchors unserved")
        tabu = set()   # lines the last round took out: not brought straight back (two moves undoing each other)
        for rnd in range(1, self.rounds + 1):
            j, S, H, trips, cap = cur
            drops = self.run_moves([(f"drop {u}", S - {u}, dict(H)) for u in sorted(S)], S, H)
            value = {nm.split()[1]: j - jj for jj, nm, *_ in drops}   # what J loses without each line
            ranked = sorted(S, key=lambda u: value[u])
            kinds = {"merge": self.merges(S, H), "anchor": self.anchor_moves(S, H, cap), "add": self.adds(S, H, cap),
                     "swap": self.swaps(S, H, ranked[:self.k_swap]),
                     "headway": self.headway_moves(S, H, ranked[-5:], ranked[:5])}
            moves = [mv for v in kinds.values() for mv in v if not ((mv[1] - S) & tabu)]
            res = drops + self.run_moves(moves, S, H)
            better = sorted((r for r in res if r[0] > j + 1e-6), key=lambda r: -r[0])
            self.log(f"  line planning round {rnd}: {len(res)} moves tried ({len(drops)} drop, "
                     + ", ".join(f"{len(v)} {k}" for k, v in kinds.items()) + f"), {len(better)} improve J")
            if not better:
                break
            # apply the improving moves best first while they touch different lines, then check the whole
            S2, H2, touched, applied = set(S), dict(H), set(), []
            for jj, nm, Sm, Hm, *_ in better:
                diff = (S ^ Sm) | {u for u in set(H) | set(Hm) if H.get(u) != Hm.get(u)}
                if diff & touched:
                    continue
                S2 = (S2 - (S - Sm)) | (Sm - S)
                for u in diff:
                    if u in Hm:
                        H2[u] = Hm[u]
                    else:
                        H2.pop(u, None)
                touched |= diff
                applied.append((nm, jj - j))
            (jc, _, _, _, tc, capc), = self.run_moves([("combined", S2, H2)], S2, H2)
            best = better[0]
            if len(applied) > 1 and jc >= best[0]:
                cur = (jc, S2, H2, tc, capc)
                self.history.append({"round": rnd, "moves": applied, "J": jc})
            else:
                cur = (best[0], best[2], best[3], best[4], best[5])
                self.history.append({"round": rnd, "moves": [(best[1], best[0] - j)], "J": best[0]})
            for nm, dj in self.history[-1]["moves"]:
                self.log(f"    {nm}: J {dj:+,.0f}")
            tabu = S - cur[1]
        j, S, H, trips, cap = cur
        self.end = {"J": j, "trips": trips, "capital": cap, "lines": len(S), "unserved": self.unserved(S)}
        self.log(f"  line planning: {len(S)} lines, {trips:,.0f} daily trips, ${cap / 1e3:.1f}B, J {j:,.0f} "
                 f"({j - self.start['J']:+,.0f}); {len(self.end['unserved'])} must-serve anchors unserved")
        out = []
        start_ids = {c.uid for c in chosen}
        nxt = max([c.order or 0 for c in chosen] + [0])
        for u in sorted(S):
            c = self.pool[u]
            c.headway = H.get(u)
            if c.headway:
                c.opex = self.opex(c, c.headway)
            if u not in start_ids:
                nxt += 1
                c.status, c.order = "chosen", nxt
                c.reason = "line planning: " + "; ".join(nm for h in self.history for nm, _ in h["moves"] if u in nm.split()) + \
                    (f"; sketch: {c.reason}" if c.reason else "")
            out.append(c)
        for c in chosen:
            if c.uid not in S:
                c.status = "replaced" if any(c.uid in nm.split() and ("merge" in nm or "swap" in nm)
                                             for h in self.history for nm, _ in h["moves"]) else "rejected"
                c.reason = "line planning: " + "; ".join(nm for h in self.history for nm, _ in h["moves"] if c.uid in nm.split())
        return out
