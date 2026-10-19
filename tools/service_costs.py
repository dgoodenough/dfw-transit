"""Usage: PYTHONPATH=. python tools/service_costs.py lever_service_package [...]

Operating cost, peak fleet and plan capital per scenario vs the plan.

Revenue hours/day per run = 2 directions x (run minutes / headway) trips/h x 18 h span x 1.15
(layover/recovery). 300 weekday-equivalent days/yr. $/revenue train- or bus-hour: metro 250,
BRT 150, commuter 400 (owner's assumptions). Peak fleet = 2 x run minutes x 1.15 / headway.
Fleet unit cost (2025 $M): metro 2-car LRT train 10, commuter 4-car EMU/DMU set 25, BRT 60-ft bus 1.2.
"""
import collections
import sys

from dfwt import config
from dfwt.network import Network

COST = {"metro": 250, "brt": 150, "commuter": 400}
FLEET = {"metro": 10, "brt": 1.2, "commuter": 25}
SPAN_H, LAYOVER, DAYS = 18, 1.15, 300


def stats(net, year):
    opex, fleet = collections.Counter(), collections.Counter()
    for r in net.runs(year):
        hw = r.line.headway_at(year)
        rmin = sum(r.hop_min)
        opex[r.line.mode] += 2 * (rmin / hw) * SPAN_H * LAYOVER * COST[r.line.mode] * DAYS / 1e6
        fleet[r.line.mode] += 2 * rmin * LAYOVER / hw
    capex = sum(net.line_cost_musd(ln, by_year=year) for ln in net.lines.values())
    return opex, fleet, capex


cfg = config.load()
base = Network.load(None, cfg)
for scen in sys.argv[1:]:
    net = Network.load(scen, cfg)
    for y in (2050, 2070, 2100):
        o0, f0, c0 = stats(base, y)
        o1, f1, c1 = stats(net, y)
        do = {m: o1[m] - o0[m] for m in COST}
        df = {m: f1[m] - f0[m] for m in COST}
        fleet_cost = sum(max(df[m], 0) * FLEET[m] for m in COST)
        print(f"{scen:26} {y} opex +${sum(do.values()):6,.0f}M/yr (" + ", ".join(f"{m} {do[m]:+,.0f}" for m in COST)
              + f")  fleet " + ", ".join(f"{m} {df[m]:+.0f}" for m in COST)
              + f"  fleet capex ${fleet_cost / 1000:.1f}B  plan-capex delta ${(c1 - c0) / 1000:+.1f}B")
