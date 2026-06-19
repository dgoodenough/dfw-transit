# DFW Transit — Hypothetical Network Model

A from-scratch model of a **hypothetical mass-transit network for the
Dallas–Fort Worth metroplex** — a Fort Worth subway core plus commuter rail, BRT,
and the existing systems across the wider metroplex. It's a single source-of-truth
database that drives an interactive map, demand scoring, a trip planner, and
time-series build-out visuals.

> Speculative urbanism, not an official plan. Geometry and phasing are the
> author's own; demand figures use real Census + LODES data where noted.

## The four routing rules

Every line in the model is checked against four rules:

1. **Commuter rail follows existing rail lines.**
2. **Minimize tunnels under rivers** where possible.
3. **Metro follows existing right-of-way (ROW)** when possible.
4. **BRT only follows existing ROW.**

## How it works

The network lives in **four CSV tables** (`db/`) that are the single source of
truth — edit a `year_opens` cell, re-run the build, and every artifact updates:

| Table | Rows | What it holds |
|---|---|---|
| `stations.csv` | 599 | id, name, mode, lat/lon, `year_opens`, activity (pop+jobs within 1 km), serving lines |
| `lines.csv` | 44 | line id, name, mode, color |
| `station_lines.csv` | 638 | line ↔ station membership + stop order |
| `segments.csv` | 565 | geometry (WKT LINESTRING) between adjacent stations, with per-line open years |

From those tables, the pipeline (`data/build_*.ps1` + two C# engines) generates:

- **`maps/FW_map_interactive.html`** — a Leaflet map rendered entirely from the DB.
- **Time-series build-out maps** (`maps/FW_timeseries_P*.{png,svg}`) — the network
  growing over time.
- **A demand engine** (`data/DemandEngine.cs`) — scores stations by population +
  jobs accessibility (2020 Census + 2022 LODES).
- **A road/ROW router** (`data/RoadRouter.cs`, `data/build_rail_router.ps1`) — snaps
  lines to existing rail/road right-of-way per the routing rules.
- **A trip planner** (`data/plan_trip.ps1`, `data/route_graph.json`).
- **Audits & validation** (`data/audit_*.ps1`, `validate_network.ps1`) — ROW
  conformance, river crossings, orphan segments.

## Repository layout

```
db/        the 4 source-of-truth tables (+ geojson exports)        ← edit here
data/      build_*.ps1 generators, DemandEngine.cs / RoadRouter.cs, source data
maps/      generated visuals: interactive map, time-series, Phase One review
reports/   analysis notes (DESIGN_STANDARDS, DEMAND_ENGINE, TRIP_PLANNER, audits)
edit/      editable line geometry (geojson + kml)
refs/      README pointing to the design-standard source PDFs (the PDFs themselves
           are not redistributed — see below)
```

Start with [`reports/FW_PhaseOne_Review.md`](reports/FW_PhaseOne_Review.md) for a
worked analysis pass, and [`db/README.md`](db/README.md) for the data model.

## Data sources & attribution

- **US Census Bureau** — 2020 Decennial (block-group centers of population),
  2022 LEHD LODES (origin-destination + jobs). Public domain.
- **OpenStreetMap** — road/rail right-of-way extracts. © OpenStreetMap
  contributors, licensed under the [ODbL](https://www.openstreetmap.org/copyright).

## What's excluded from this repo

To keep it lean and avoid redistributing third-party material, `.gitignore` omits:

- **`refs/*.pdf`** — copyrighted design standards (TCRP, ITDP BRT Standard, TxDOT
  specs, FRA superelevation). `refs/README.md` lists each document and a free
  download source.
- **Large raw geodata** — the multi-megabyte OSM network extracts and Census LODES
  files (`data/dfw_arterials.json`, `data/tx_od.csv.gz`, etc.). They're reproducible
  from the sources above; the curated `db/` tables and smaller derived data remain.

## Stack

PowerShell · C# · Leaflet · CSV/GeoJSON/WKT · Census + LODES + OSM data.

## License

[MIT](LICENSE) — covers the original code and the author's network data, not the
third-party datasets or reference documents it draws on.
