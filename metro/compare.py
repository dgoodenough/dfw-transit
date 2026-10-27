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


def main(run_model=True, log=print):
    cfg = config.load()
    m = inputs.load("dfw")
    hand = Network.load("two_million", cfg=config.load())
    budget = capital(hand)
    log(f"2M plan new capital ${budget / 1e3:.1f}B (2025 $): generating DFW with that budget")
    # same money as the hand plan, all of it spent: no value floor, so the two networks cost the same
    g = generate("dfw", budget_musd=budget, run_model=False, log=log,
                 override={"selection": {"min_trips_per_musd": 0.0, "max_lines": 200}})
    gen = g["stats"]["net"]
    cur = output.load_net(g["ex_tables"], cfg, "existing")
    hand_tr, gen_tr = new_track(m, hand), new_track(m, gen)
    ex_tr = {ln.id: [geom.to_xy(m, [(lat, lon) for lon, lat in s.pts]) for s in ln.segments]
             for ln in cur.lines.values()}
    rows = []
    for lid, P in sorted(hand_tr.items()):
        ln = hand.lines[lid]
        sh = share(P, list(gen_tr.values()))
        best = max(((share(P, [Q]), gid) for gid, Q in gen_tr.items()), default=(0, ""))
        rows.append({"side": "hand", "line_id": lid, "name": ln.name, "mode": ln.mode, "new_km": round(length(P), 1),
                     "share_near_other": round(sh, 2),
                     "verdict": "matched" if sh >= 0.5 else "partly" if sh >= 0.2 else "missed",
                     "closest_other": f"{best[1]} {gen.lines[best[1]].name} ({gen.lines[best[1]].mode})"
                     if best[1] and best[0] > 0.1 else ""})
    for lid, P in sorted(gen_tr.items()):
        ln = gen.lines[lid]
        sh = share(P, list(hand_tr.values()))
        sh_ex = share(P, list(ex_tr.values()))
        best = max(((share(P, [Q]), hid) for hid, Q in hand_tr.items()), default=(0, ""))
        rows.append({"side": "generated", "line_id": lid, "name": ln.name, "mode": ln.mode,
                     "new_km": round(length(P), 1), "share_near_other": round(sh, 2),
                     "verdict": "in hand plan" if sh >= 0.5 else "partly" if sh >= 0.2 else (
                         "beside today's lines" if sh_ex >= 0.5 else "added"),
                     "closest_other": f"{best[1]} {hand.lines[best[1]].name} ({hand.lines[best[1]].mode})"
                     if best[1] and best[0] > 0.1 else ""})
    output.write_csv(os.path.join(g["out"], "compare_lines.csv"), rows)
    nets = {"today": cur, "generated": gen, "2M hand plan": hand}
    cov = {k: output.coverage_800(m, model.all_open(n)) for k, n in nets.items()}
    res = {}
    if run_model:
        ctx = model.context(m, cfg)
        for k, n in nets.items():
            log(f"  model: {k}")
            res[k] = model.run_today(ctx, n, cur)
    write_report(m, g, nets, rows, cov, res, budget, hand_tr, gen_tr)


def write_report(m, g, nets, rows, cov, res, budget, hand_tr, gen_tr):
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
    beside = vg["beside today's lines"]
    kmh = collections.Counter()
    for r in hand_rows:
        kmh[r["verdict"]] += r["new_km"]
    w("## Which corridors match")
    w("")
    w(f"A hand-plan line is **matched** when at least half of its new track lies within {MATCH_KM:g} km of "
      f"generated track, **partly** at 20-50%. Of {len(hand_rows)} hand-plan lines with new track: "
      f"{vh['matched']} matched ({kmh['matched']:,.0f} km), {vh['partly']} partly ({kmh['partly']:,.0f} km), "
      f"{vh['missed']} missed ({kmh['missed']:,.0f} km). Of {len(gen_rows)} generated lines: "
      f"{vg['in hand plan']} lie in hand-plan corridors, {vg['partly']} partly, {beside} "
      f"beside today's lines, {vg['added']} are corridors the hand plan doesn't have.")
    w("")
    by_mode = collections.defaultdict(collections.Counter)
    for r in hand_rows:
        by_mode[r["mode"]][r["verdict"]] += r["new_km"]
    w("| hand-plan mode | matched km | partly km | missed km |")
    w("|---|---|---|---|")
    for mode, c in sorted(by_mode.items()):
        w(f"| {mode} | {c['matched']:,.0f} | {c['partly']:,.0f} | {c['missed']:,.0f} |")
    w("")
    w("### Hand-plan lines")
    w("")
    w("| line | mode | new km | share near generated | verdict | closest generated line |")
    w("|---|---|---|---|---|---|")
    for r in sorted(hand_rows, key=lambda r: (r["verdict"] != "matched", r["verdict"] != "partly", r["mode"], -r["new_km"])):
        w(f"| {r['line_id']} {r['name']} | {r['mode']} | {r['new_km']} | {r['share_near_other']:.0%} | {r['verdict']} | "
          f"{r['closest_other']} |")
    w("")
    w("### Generated lines")
    w("")
    w("| line | mode | km | share near hand plan | verdict | closest hand-plan line |")
    w("|---|---|---|---|---|---|")
    for r in gen_rows:
        w(f"| {r['line_id']} {r['name']} | {r['mode']} | {r['new_km']} | {r['share_near_other']:.0%} | "
          f"{r['verdict']} | {r['closest_other']} |")
    w("")
    with open(config.path("reports", "generator_dfw_check.md.tmp"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    os.replace(config.path("reports", "generator_dfw_check.md.tmp"), config.path("reports", "generator_dfw_check.md"))
