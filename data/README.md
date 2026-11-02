# data/ — model inputs

| File | What it is | Used by |
|---|---|---|
| `metroplex_density.csv` | 4,276 block groups in the nine core counties: 2020 Census population + 2022 LODES WAC jobs, with centroids | demand zones (`dfwt/demand.py`) |
| `lodes_wac_sectors_bg_2022.csv` | the same block groups' 2022 LODES WAC jobs by sector: retail (NAICS 44-45 and 72, CNS07 + CNS18), service (CNS09-17, CNS19-20), basic (the rest), plus arts, food, education and health detail. Built by `python tools/fetch_wac.py` from [tx_wac_S000_JT00_2022.csv.gz](https://lehd.ces.census.gov/data/lodes/LODES8/tx/wac/tx_wac_S000_JT00_2022.csv.gz); its job totals match `metroplex_density.csv` exactly | non-commute trip attractions (`config.json` -> `ridership.nonwork`, off by default) |
| `tract_centroids.csv` | the same aggregated to 1,667 tracts | reference |
| `CenPop2020_BG_TX.txt` | Census 2020 block-group centers of population (Texas) | source of the centroids |
| `existing_geom.json`, `existing_stops.json` | today's DART/TRE/TEXRail/A-train alignments and stops (OSM) | v1 network build (archived) |
| `waterways.geojson` | the Trinity (West, Clear, Elm and East Forks and the main stem) and 14 major lakes (Lake Worth, Eagle Mountain, Benbrook, Arlington, Grapevine, Lewisville, White Rock, Ray Hubbard, Joe Pool, Mountain Creek, Lavon, Ray Roberts, North Lake, Bachman), simplified with Douglas–Peucker to ~80 KB. From Overture Maps release `2026-09-23.1`, theme `base`, type `water`, read anonymously from S3 with a bounding-box filter by `tools/fetch_waterways.py`. Overture water is OpenStreetMap data: © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) | map "Waterways" layer and diagram view (`dfwt/schematic.py`) |
| `fw_rivers.json`, `dfw_yards.json`, `dfw_poi.json`, `dfw_hoods.json`, `dfw_gazetteer.json`, `dfw_route_stops.json` | OpenStreetMap extracts (© OpenStreetMap contributors, ODbL) | v1 audits and naming (archived); kept for the v2 backlog |
| `metros/<id>/` | inputs for any US metro gathered by `python -m metro fetch <id>`: block-group zones, LODES OD, existing transit from GTFS, Overture roads/rail, `meta.json` (see `metro/README.md`) | the metro-agnostic planner |

## Commute flows

`lodes_od_tracts_2022.csv.gz` holds the real commute flows: LEHD LODES 8 home-to-work pairs
(all jobs, 2022, both ends in Texas), summed to tract pairs within counties 113, 439, 085,
121, 397, 251, 139, 367 and 257. It has 827,288 pairs and 3,318,762 commutes, in columns
`h_tract,w_tract,jobs`. `python tools/fetch_lodes.py` downloads and rebuilds it. If the file
(`config.json` -> `demand.lodes_od_path`) is missing, the model falls back to a gravity model,
and `python -m dfwt build` reports `Demand source: gravity` instead of `lodes`.
