"""Usage: PYTHONPATH=. python tools/diagram_preview.py OUT.html [--versions rail,brt,all] [--base docs/map.html]
                                                        [--pickle DIR]

A quick preview of the diagram view after a change to dfwt/schematic.py or its templates,
without the hour-long `python -m dfwt build`: the listed versions are laid out afresh over
every scenario (as the build does: schematic.version_nets over the networks of the plan and
scenarios/), and spliced into the data of an already built page (--base, default
docs/map.html; the other versions keep the layout that page has). The page is put together
from the current templates (map.html, schematic.css, schematic.js) the same way webmap.write
does, so template changes show too. --pickle DIR also saves each Layout object (for
analysis scripts) as DIR/<version>.pkl.

The page loads Leaflet from unpkg; offline, serve a local copy (route the request).
"""
import argparse
import json
import os
import pickle
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dfwt import config, schematic, webmap  # noqa: E402
from dfwt.__main__ import scenarios  # noqa: E402
from dfwt.network import Network  # noqa: E402

MARK = "const D = "


def page_data(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    i = html.index(MARK) + len(MARK)
    j = html.index(";\n", i)
    return json.loads(html[i:j])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--versions", default="rail")
    ap.add_argument("--base", default=config.path("docs", "map.html"))
    ap.add_argument("--pickle")
    a = ap.parse_args()
    t = time.time()
    data = page_data(a.base)
    raw = {sc or "plan": Network.load(sc) for sc in [None] + scenarios()}
    modes = {k: m for k, _, m in schematic.VERSIONS}
    for key in [v for v in a.versions.split(",") if v]:
        t0 = time.time()
        lay = schematic.compute(schematic.version_nets(raw, modes[key]), log=lambda s: print("  ", s, flush=True))
        data["schem"]["sets"][key] = schematic.to_json(lay)
        print(f"{key}: {schematic.quality(lay)} in {time.time() - t0:.0f}s", flush=True)
        if a.pickle:
            os.makedirs(a.pickle, exist_ok=True)
            with open(os.path.join(a.pickle, key + ".pkl"), "wb") as f:
                pickle.dump(lay, f)
    with open(webmap.TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    css, js = (open(p, encoding="utf-8").read() for p in webmap.SCHEM_FILES)
    html = html.replace("<!--__SCHEMATIC__-->", f"<style>\n{css}</style>\n<script>\n{js}</script>")
    html = html.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {a.out} in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
