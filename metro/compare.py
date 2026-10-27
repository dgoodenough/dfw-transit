"""Cross-check the generator on DFW against the hand-built 2 million plan.

    python -m metro check-dfw [--no-model]

Runs `generate dfw` with the 2M plan's own new capital (2025 prices, dfwt costing) as the
budget, then compares the two networks on the same footing: new km by mode, capital,
residents and jobs within 800 m of a station, which hand-plan corridors the generator finds
(a hand line counts as matched when >= 50% of its new track lies within 1 km of generated
track, partly when 20-50%) and which generated lines the hand plan doesn't have, and dfwt's
demand model on today's land use with every line open (base config.json for both, so only the
networks differ). Writes reports/generator_dfw_check.md and generated/dfw/compare_lines.csv.
"""
import collections
import os

from dfwt import config
from dfwt.network import Network

from . import geom, inputs, model, output
from .generate import generate

MATCH_KM = 1.0


def new_track(m, net):
    """{line_id: polyline xy of its track opening after existing_year} (pieces joined in order)."""
    ex = net.cfg["existing_year"]
    out = {}
    for ln in net.lines.values():
        pieces = []
        for s in ln.segments:
            if s.year <= ex or s.borrowed:
                continue
            Q = geom.to_xy(m, [(lat, lon) for lon, lat in s.pts])
            if pieces and pieces[-1][-1] == Q[0]:
                pieces[-1] = pieces[-1] + Q[1:]
            else:
                pieces.append(Q)
        if pieces:
            out[ln.id] = pieces
    return out


def length(pieces):
    return sum(geom.length(P) for P in pieces)


def share(pieces, others, r=MATCH_KM):
    """Length-weighted share of `pieces` within r km of any polyline in `others` (lists of pieces)."""
    flat = [Q for o in others for Q in o]
    L = length(pieces)
    if not flat or not L:
        return 0.0
    return sum(geom.share_near(P, flat, r) * geom.length(P) for P in pieces) / L


def km_by_mode(net):
    ex = net.cfg["existing_year"]
    out = collections.Counter()
    for ln in net.lines.values():
        out[ln.mode] += sum(s.km for s in ln.segments if s.year > ex and not s.borrowed)
    return out


def capital(net):
    return sum(net.shared_cost_musd(ln) for ln in net.lines.values())


FAMILY = {"metro": "rail", "streetcar": "rail", "commuter": "regional rail", "brt": "bus"}


def main(run_model=True, reuse=False, log=print):
    """reuse: compare the tables already in generated/dfw/ (and the model results cached there)
    instead of generating again."""
    import json
    from .generate import Existing
    cfg = config.load()
    m = inputs.load("dfw")
    hand = Network.load("two_million", cfg=config.load())
    budget = capital(hand)
    out = config.path("generated", "dfw")
    if reuse:
        tables = {k: inputs.read_csv(os.path.join(out, k)) for k in inputs.TABLES}
        g = {"out": out, "tables": tables, "ex_tables": Existing(m, cfg["modes"]).tables}
        gen = output.load_net(tables, cfg, "generated")
    else:
        log(f"2M plan new capital ${budget / 1e3:.1f}B (2025 $): generating DFW with that budget")
        # same money as the hand plan: no value floor, so the generator may spend all of it
        g = generate("dfw", budget_musd=budget, run_model=False, log=log,
                     override={"selection": {"min_trips_per_musd": 0.0, "max_lines": 200}})
        gen = g["stats"]["net"]
    cur = output.load_net(g["ex_tables"], cfg, "existing")
    hand_tr, gen_tr = new_track(m, hand), new_track(m, gen)
    ex_tr = {ln.id: [geom.to_xy(m, [(lat, lon) for lon, lat in s.pts]) for s in ln.segments]
             for ln in cur.lines.values()}

    def fam(net, lid):
        return FAMILY[net.lines[lid].mode]
    rows = []
    for side, net, mine, other, onet in (("hand", hand, hand_tr, gen_tr, gen), ("generated", gen, gen_tr, hand_tr, hand)):
        for lid, P in sorted(mine.items()):
            ln = net.lines[lid]
            sh = share(P, list(other.values()))
            sh05 = share(P, list(other.values()), 0.5)
            same = share(P, [Q for oid, Q in other.items() if fam(onet, oid) == fam(net, lid)])
            best = max(((share(P, [Q]), oid) for oid, Q in other.items()), default=(0, ""))
            if side == "hand":
                verdict = "matched" if sh >= 0.5 else "partly" if sh >= 0.2 else "missed"
            else:
                verdict = "in hand plan" if sh >= 0.5 else "partly" if sh >= 0.2 else (
                    "beside today's lines" if share(P, list(ex_tr.values())) >= 0.5 else "added")
            rows.append({"side": side, "line_id": lid, "name": ln.name, "mode": ln.mode,
                         "new_km": round(length(P), 1), "share_near_other": round(sh, 2),
                         "share_within_500m": round(sh05, 2), "share_near_same_family": round(same, 2),
                         "verdict": verdict,
                         "closest_other": f"{best[1]} {onet.lines[best[1]].name} ({onet.lines[best[1]].mode})"
                         if best[1] and best[0] > 0.1 else ""})
    output.write_csv(os.path.join(g["out"], "compare_lines.csv"), rows)
    nets = {"today": cur, "generated": gen, "2M hand plan": hand}
    cov = {k: output.coverage_800(m, model.all_open(n)) for k, n in nets.items()}
    # chance level: how much of the region's population lives within 1 km of the hand plan's new track
    near = set()
    for P in (Q for pieces in hand_tr.values() for Q in pieces):
        near.update(_near(m, P))
    base = float(m.pop[list(near)].sum() / m.pop.sum())
    cache = os.path.join(out, "compare_model.json")
    res = {}
    if run_model and reuse and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            res = json.load(f)
    elif run_model:
        ctx = model.context(m, cfg)
        for k, n in nets.items():
            log(f"  model: {k}")
            res[k] = model.run_today(ctx, n, cur)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
    write_report(m, g, nets, rows, cov, res, budget, hand_tr, gen_tr, base)


_ZI = {}


def _near(m, P):
    zi = _ZI.setdefault(id(m), geom.ZoneIndex(m, 1.0))
    return zi.near_points(geom.resample(P, 0.25), MATCH_KM).tolist()


def write_report(m, g, nets, rows, cov, res, budget, hand_tr, gen_tr, base):
    L = []
    w = L.append
    gen, hand = nets["generated"], nets["2M hand plan"]
    km_g, km_h = km_by_mode(gen), km_by_mode(hand)
    cap_g, cap_h = capital(gen), capital(hand)
    P, J = m.pop.sum(), m.jobs.sum()
    w("# Generator cross-check on DFW")
    w("")
    w("`python -m metro check-dfw` runs the metro-agnostic generator (`python -m metro generate dfw`, "
      "`metro/generate.py`) on DFW's inputs, ignoring the hand plan, with the hand plan's own new capital as its "
      "budget, and compares the result with the hand-built 2 million plan (`network/` + `scenarios/two_million/`). "
      "Generated network: `generated/dfw/` (its `report.md` lists the centers, every candidate and why it was "
      "chosen or rejected; `preview.png` is a map). Line-by-line matching: `generated/dfw/compare_lines.csv`.")
    w("")
    w("## Totals")
    w("")
    w("| | today | generated | 2M hand plan |")
    w("|---|---|---|---|")
    for mode, lab in (("metro", "metro / light rail km (new)"), ("brt", "BRT km (new)"),
                      ("commuter", "regional rail km (new)"), ("streetcar", "streetcar km (new)")):
        w(f"| {lab} | - | {km_g.get(mode, 0):,.0f} | {km_h.get(mode, 0):,.0f} |")
    w(f"| new lines | - | {sum(1 for ln in gen.lines.values() if ln.status != 'existing')} | "
      f"{len(hand_tr)} (incl. extended existing lines) |")
    w(f"| capital, 2025 $ (dfwt costing) | - | ${cap_g / 1e3:,.1f}B | ${cap_h / 1e3:,.1f}B |")
    w(f"| residents within 800 m of a station | {cov['today'][0] / P:.1%} | {cov['generated'][0] / P:.1%} | "
      f"{cov['2M hand plan'][0] / P:.1%} |")
    w(f"| jobs within 800 m of a station | {cov['today'][1] / J:.1%} | {cov['generated'][1] / J:.1%} | "
      f"{cov['2M hand plan'][1] / J:.1%} |")
    if res:
        for key, lab in (("daily_trips", "daily transit trips, today's land use, all lines open"),
                         ("daily_boardings", "daily rail + BRT boardings, same"),
                         ("access_jobs_45", "jobs within 45 min, average resident")):
            w(f"| {lab} | {res['today'][key]:,.0f} | {res['generated'][key]:,.0f} | {res['2M hand plan'][key]:,.0f} |")
        tg = res["generated"]["daily_trips"] - res["today"]["daily_trips"]
        th = res["2M hand plan"]["daily_trips"] - res["today"]["daily_trips"]
        w(f"| new daily trips per $M of capital | - | {tg / cap_g * 1:,.2f} | {th / cap_h:,.2f} |")
    w("")
    if res:
        w("Model runs: dfwt's demand model (gravity flows, the config.json logit calibrated to DFW's 2025 rail "
          "boardings, feeder buses) on 2026 land use with no station-area growth, every line open; the 2M plan's "
          "own policy overlay (`scenarios/two_million/config.json`: parking, access and land-use levers) is NOT "
          "applied, so both networks face the same assumptions. The 2M plan's published 2100 numbers are far higher "
          "because they include 75 years of growth, transit-oriented development and those policies.")
        w("")
    hand_rows = [r for r in rows if r["side"] == "hand"]
    gen_rows = [r for r in rows if r["side"] == "generated"]
    vh = collections.Counter(r["verdict"] for r in hand_rows)
    vg = collections.Counter(r["verdict"] for r in gen_rows)
    kmh, kmg = collections.Counter(), collections.Counter()
    for r in hand_rows:
        kmh[r["verdict"]] += r["new_km"]
    for r in gen_rows:
        kmg[r["verdict"]] += r["new_km"]
    other_g = vg["added"] + vg["beside today's lines"]
    other_km = kmg["added"] + kmg["beside today's lines"]

    def kw(rs, key):   # length-weighted mean share
        L = sum(r["new_km"] for r in rs)
        return sum(r[key] * r["new_km"] for r in rs) / L if L else 0.0
    notes = config.path("metro", "compare_notes.md")
    if os.path.exists(notes):   # the hand-written reading of these numbers (kept apart so a rerun keeps it)
        with open(notes, encoding="utf-8") as f:
            w(f.read().rstrip())
            w("")
    w("## Which corridors match")
    w("")
    w(f"Share of each network's new track lying within {MATCH_KM:g} km (500 m) of the other's, length-weighted: "
      f"hand plan near generated {kw(hand_rows, 'share_near_other'):.0%} ({kw(hand_rows, 'share_within_500m'):.0%}), "
      f"generated near hand plan {kw(gen_rows, 'share_near_other'):.0%} ({kw(gen_rows, 'share_within_500m'):.0%}); "
      f"counting only a line of the same family (rail transit / BRT / regional rail): hand plan "
      f"{kw(hand_rows, 'share_near_same_family'):.0%}, generated {kw(gen_rows, 'share_near_same_family'):.0%}. "
      f"Chance level: {base:.0%} of the region's residents live within {MATCH_KM:g} km of the hand plan's new track, "
      "so a corridor drawn through populated places at random would lie near it about that often.")
    w("")
    w(f"A hand-plan line is **matched** when at least half of its new track lies within {MATCH_KM:g} km of "
      f"generated track (any mode), **partly** at 20-50%. Of {len(hand_rows)} hand-plan lines with new track: "
      f"{vh['matched']} matched ({kmh['matched']:,.0f} km), {vh['partly']} partly ({kmh['partly']:,.0f} km), "
      f"{vh['missed']} missed ({kmh['missed']:,.0f} km). Of {len(gen_rows)} generated lines: "
      f"{vg['in hand plan']} lie in hand-plan corridors ({kmg['in hand plan']:,.0f} km), {vg['partly']} partly "
      f"({kmg['partly']:,.0f} km), {other_g} are corridors the hand plan doesn't have ({other_km:,.0f} km).")
    w("")
    by_mode = collections.defaultdict(collections.Counter)
    for r in hand_rows:
        by_mode[r["mode"]][r["verdict"]] += r["new_km"]
        by_mode[r["mode"]]["same"] += r["new_km"] * r["share_near_same_family"]
        by_mode[r["mode"]]["all"] += r["new_km"]
    w("| hand-plan mode | km | matched km | partly km | missed km | km near generated track of the same family |")
    w("|---|---|---|---|---|---|")
    for mode, c in sorted(by_mode.items()):
        w(f"| {mode} | {c['all']:,.0f} | {c['matched']:,.0f} | {c['partly']:,.0f} | {c['missed']:,.0f} | "
          f"{c['same']:,.0f} |")
    w("")
    w("### Hand-plan lines")
    w("")
    w("| line | mode | new km | near generated (1 km) | same family | verdict | closest generated line |")
    w("|---|---|---|---|---|---|---|")
    for r in sorted(hand_rows, key=lambda r: (r["verdict"] != "matched", r["verdict"] != "partly", r["mode"], -r["new_km"])):
        w(f"| {r['line_id']} {r['name']} | {r['mode']} | {r['new_km']} | {r['share_near_other']:.0%} | "
          f"{r['share_near_same_family']:.0%} | {r['verdict']} | {r['closest_other']} |")
    w("")
    w("### Generated lines")
    w("")
    w("| line | mode | km | near hand plan (1 km) | same family | verdict | closest hand-plan line |")
    w("|---|---|---|---|---|---|---|")
    for r in gen_rows:
        w(f"| {r['line_id']} {r['name']} | {r['mode']} | {r['new_km']} | {r['share_near_other']:.0%} | "
          f"{r['share_near_same_family']:.0%} | {r['verdict']} | {r['closest_other']} |")
    w("")
    with open(config.path("reports", "generator_dfw_check.md.tmp"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    os.replace(config.path("reports", "generator_dfw_check.md.tmp"), config.path("reports", "generator_dfw_check.md"))
