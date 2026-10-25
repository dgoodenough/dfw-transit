# data/ — model inputs

| File | What it is | Used by |
|---|---|---|
| `metroplex_density.csv` | 4,276 block groups in the nine core counties: 2020 Census population + 2022 LODES WAC jobs, with centroids | demand zones (`dfwt/demand.py`) |
| `tract_centroids.csv` | the same aggregated to 1,667 tracts | reference |
| `CenPop2020_BG_TX.txt` | Census 2020 block-group centers of population (Texas) | source of the centroids |
| `existing_geom.json`, `existing_stops.json` | today's DART/TRE/TEXRail/A-train alignments and stops (OSM) | v1 network build (archived) |
| `waterways.geojson` | the Trinity (West, Clear, Elm and East Forks and the main stem) and 14 major lakes (Lake Worth, Eagle Mountain, Benbrook, Arlington, Grapevine, Lewisville, White Rock, Ray Hubbard, Joe Pool, Mountain Creek, Lavon, Ray Roberts, North Lake, Bachman), simplified with Douglas–Peucker to ~80 KB. From Overture Maps release `2026-09-23.1`, theme `base`, type `water`, read anonymously from S3 with a bounding-box filter by `tools/fetch_waterways.py`. Overture water is OpenStreetMap data: © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) | map "Waterways" layer and diagram view (`dfwt/schematic.py`) |
| `fw_rivers.json`, `dfw_yards.json`, `dfw_poi.json`, `dfw_hoods.json`, `dfw_gazetteer.json`, `dfw_route_stops.json` | OpenStreetMap extracts (© OpenStreetMap contributors, ODbL) | v1 audits and naming (archived); kept for the v2 backlog |
| `metros/<id>/` | inputs for any US metro gathered by `python -m metro fetch <id>`: block-group zones, LODES OD, existing transit from GTFS, Overture roads/rail, `meta.json` (see `metro/README.md`) | the metro-agnostic planner |

## Optional: real commute flows

The model synthesizes commute flows with a gravity model unless it finds
`data/raw/od_tracts.csv` (columns `h_tract,w_tract,jobs`). To use real flows,
download `tx_od_main_JT00_2022.csv.gz` from the LEHD LODES 8 site, aggregate it
to tract pairs for counties 113, 439, 085, 121, 397, 251, 139, 367, 257
(the v1 script `archive/v1/data/build_od.ps1` does exactly this), and save it
there. `python -m dfwt build` then reports `Demand source: lodes`.
