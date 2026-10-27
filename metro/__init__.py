"""Metro-agnostic transit planner for any US metro listed in metro/metros.json.

Step 1 (inputs): zones (population, jobs), commute flows, today's transit (GTFS) and the
road/rail network (Overture), cached under data/metros/<id>/. See metro/README.md for the
data contract.

Step 2 (network): `python -m metro generate <id>` builds a potential network from those
inputs (metro/generate.py) and writes it in dfwt's table format under generated/<id>/.
"""
