"""Usage: PYTHONPATH=. python tools/service_trunks.py lever_service_package 2070

Trains/buses per hour per direction on shared track (busiest physical segments), and
rough operating cost (revenue hours) by mode for a scenario and year.

usage: python trunks.py <scenario|-> <year> [<year>...]
Operating cost: revenue vehicle(train)-hours/day = 2 directions x run minutes / headway
x service hours, with service span 18 h/day at the base headway (peak-only extras
ignored), x 1.15 layover/recovery; 300 equivalent weekday-days/yr.
$/revenue-hour: metro 250 (per train), BRT 150 (per bus), commuter 400 (per train).
"""
import collections
import sys

from dfwt import config
from dfwt.network import Network

COST = {"metro": 250, "brt": 150, "commuter": 400}
SPAN_H, LAYOVER, DAYS = 18, 1.15, 300
LIMIT = {"metro": 24, "brt": 60, "commuter": 12}   # flag thresholds, tph per direction


def opex(net, year):
    by = collections.Counter()
    for r in net.runs(year):
        hw = r.line.headway_at(year)
        rmin = sum(r.hop_min)
        veh_h = 2 * (rmin / hw) * SPAN_H * LAYOVER      # trips/h each way x hours per trip x span
        by[r.line.mode] += veh_h * COST[r.line.mode] * DAYS / 1e6
    return by


def trunks(net, year):
    seg = collections.defaultdict(list)
    for r in net.runs(year):
        for a, b in zip(r.stops, r.stops[1:]):
            seg[(r.line.mode, frozenset((a, b)))].append((r.line.id, 60 / r.line.headway_at(year)))
    out = []
    for (mode, k), v in seg.items():
        tph = sum(x for _, x in v)
        if len(v) > 1:
            out.append((tph, mode, [net.stations[s].name for s in k], [l for l, _ in v]))
    return sorted(out, key=lambda t: -t[0])


if __name__ == "__main__":
    scen = sys.argv[1]
    cfg = config.load()
    net = Network.load(None if scen == "-" else scen, cfg)
    for y in map(int, sys.argv[2:]):
        o = opex(net, y)
        print(f"{scen} {y} opex $M/yr: " + ", ".join(f"{m} {v:,.0f}" for m, v in sorted(o.items()))
              + f", total {sum(o.values()):,.0f}")
        seen = set()
        for tph, mode, names, lines in trunks(net, y)[:40]:
            key = (mode, tuple(sorted(lines)))
            if key in seen:
                continue
            seen.add(key)
            flag = "  OVER" if tph > LIMIT[mode] else ""
            print(f"   {tph:5.1f} tph {mode:8} {' - '.join(names)[:50]:50} {','.join(lines)}{flag}")
