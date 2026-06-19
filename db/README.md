# DFW Transit — Unified Network Database

**The four tables below are the single source of truth** for the whole metroplex
network (FW core + Dallas + commuter + BRT + existing systems). The interactive
map (`../maps/FW_map_interactive.html`) is generated *from these tables only* — edit a
cell (e.g. a `year_opens`), run `../data/build_app.ps1`, done.

## The tables

### `stations.csv` — every station (599)
| column | meaning |
|---|---|
| `station_id` | `S###` = FW core, `X###` = rest of metroplex |
| `name`, `mode`, `lat`, `lon` | display name, metro/commuter/brt, WGS84 |
| **`year_opens`** | 2025 = existing today; else 2035–2070 in 5-yr steps. **Edit me.** |
| `act` | pop+jobs within 1 km (2020 census + 2022 LODES) |
| `lines`, `n_lines` | serving lines (`;`-sep); FW interchanges have ≥2 |
| `color`, `src` | render color; `fw` or `extra` |

### `lines.csv` — every line (44)
`line_id` (`F##` FW / `E##` extra), name, mode, color, src, n_stations.

### `station_lines.csv` — line↔station membership (638)
line_id, line, `seq` (stop order), station_id/name, `year` (station opens on
that line). Answers "which lines at X" / "stop order of Y".

### `segments.csv` — geometry between adjacent stations (565)
| column | meaning |
|---|---|
| `segment_id` | `SEG###` FW (multi-line, shared trunks listed once), `XSEG###` extra |
| `line` | FW: `;`-sep lines on shared track · extra: one line |
| **`year_opens`** | FW: `;`-sep per-line years (parallel to `line`) · extra: single year, computed with the **clip rule** = max(min year toward each end), which makes lines grow contiguously from their first-opened stations — no orphan fragments, no overhang past termini. **Edit me.** |
| `from_/to_` id+name, `mode`, `color`, `src`, `geometry_wkt` | endpoints + LINESTRING |

## Regeneration pipeline (only needed if geometry/stations change)
```
build_existing_routes -> build_extra -> build_rail_router -> build_stations
   -> build_db_full -> build_feasibility -> build_app
```
- `build_db.ps1` (FW core generator) writes `fw_*.csv`; `build_stations.ps1`
  writes `_extra_*.csv`; **`build_db_full.ps1` merges both into the four unified
  tables** (and materializes all years as data).
- ⚠️ Regenerating **overwrites hand edits** to the four tables. If you've
  hand-tuned, either re-apply edits or tell Claude what you changed so the
  generators learn it.
- `build_feasibility.ps1` re-scores stations (act + freeway distance) →
  `../data/feasibility_stations.csv` (classification lives outside the DB).

## Aux files
`extra_final.geojson` (debug/geojson.io view of the extra network),
`network*.geojson` + `stations/segments.geojson` (FW-only legacy exports),
`commuter_ext.geojson` (ROW-routed town extensions), `lines_extra.csv` (legacy
line registry; superseded by `lines.csv`).
