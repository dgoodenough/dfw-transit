# metro/: inputs and a generated network for any US metro

`dfwt/` is a hand-built plan for Dallas–Fort Worth. `metro/` is the first half of a
version that works for any US metro. It gathers the inputs (population, jobs, commute
flows, today's transit, roads and rail) for a metro listed in `metro/metros.json` and
writes them to `data/metros/<id>/` in a fixed format (the **data contract** below).
The network builder (step 2, `python -m metro generate`, at the end of this page) reads that format.

```
python -m metro list
python -m metro fetch houston                      # zones, od, gtfs, overture
python -m metro fetch houston --only gtfs          # one or more stages
python -m metro fetch houston --jobs-proxy places  # also the opt-in Overture places proxy
python -m metro fetch houston --force              # download again even when raw/ has the file
```

Options: `--lodes-year` (default: the newest year the server has), `--overture-release`
(default: the release `tools/fetch_osm.py` uses for DFW, or the newest one if Overture has
pruned it), `--am 7-9` (AM peak window for headways) and `--frequent 15` (the longest peak
headway, in minutes, at which a bus route still counts as frequent).

Requirements: Python 3.9+, `numpy` and `pyarrow` (`requirements-geometry.txt`), which are
already needed for `dfwt`.

## Adding a metro

Add an entry to `metro/metros.json` with these fields: `id`, `name`, `cbsa`, `state_fips`,
`state_abbr` (state FIPS → USPS code, lower case), `county_fips` (5-digit), and
`downtowns` (reference points, `[{name, lat, lon}]`). Optional fields:

- `gtfs_include` / `gtfs_exclude`: Mobility Database source ids that replace or trim the
  bounding-box search.
- `brt_name_pattern`: a regex on route names that marks a bus route as BRT.
- `bbox_margin_deg`: padding around the block-group centres. The default is 0.1.

The zones stage checks the county list against the OMB delineation file (`list1_2023.xlsx`)
and records the result in `meta.json` → `sources.cbsa_delineation`.

## Sources

| Stage | Source | Host | Output |
|---|---|---|---|
| zones | Census 2020 block-group centres of population, `CenPop2020_Mean_BG<ST>.txt`. A repo copy `data/CenPop2020_BG_<ST>.txt` is used when one exists. | www2.census.gov | zones.csv `geoid, lat, lon, pop, county_fips` |
| zones | TIGER/Line 2020 block groups, `tl_2020_<ST>_bg.zip`. Only the `.dbf` attribute table is read, for `ALAND`. | www2.census.gov | zones.csv `area_km2` |
| zones | LODES 8 WAC `<st>_wac_S000_JT00_<year>.csv.gz`, `C000` (all jobs), newest year | lehd.ces.census.gov | zones.csv `jobs` |
| zones | OMB CBSA delineation 2023, `list1_2023.xlsx` | www2.census.gov | meta.json only |
| od | LODES 8 OD `<st>_od_main_JT00_<year>.csv.gz` + `_aux_` (home in another state), `S000` | lehd.ces.census.gov | od_tracts.csv |
| gtfs | Mobility Database catalog (`mdb-csv/sources.csv`), then each feed's `urls.latest` (MobilityData's hosted copy), falling back to the producer URL | storage.googleapis.com (producer hosts as fallback) | existing/ |
| overture | Overture `theme=transportation/type=segment`, read anonymously from S3 with a bbox filter. The columns, road classes and release are the same as `tools/fetch_osm.py`. | overturemaps-us-west-2.s3.amazonaws.com | osm/roads.parquet, osm/rail.parquet |
| places (opt-in) | Overture `theme=places/type=place` | same S3 bucket | zones_places_proxy.csv |

If a source is blocked or missing, the run continues. The columns or files that depend on
it stay empty, and `meta.json` records the host and the error under `sources.<name>` and in
`missing`. **Nothing is ever filled with synthetic values.**

## Data contract: `data/metros/<id>/`

Committed: the small derived tables and `meta.json`. Git-ignored: `raw/` (downloads) and
`osm/*.parquet` (large, reproducible, with sha256 checksums in `meta.json`).

### `zones.csv`: one row per 2020 Census block group in the metro's counties

| column | meaning |
|---|---|
| `geoid` | 12-digit 2020 block group GEOID (state 2, county 3, tract 6, block group 1) |
| `lat`, `lon` | Census 2020 centre of population (population-weighted). For the few zero-population block groups, this is the point Census publishes for them. |
| `pop` | 2020 Census population (integer) |
| `jobs` | LODES 8 WAC all jobs (`C000`) at workplaces in the block group, for the year in `meta.json` → `sources.lodes_wac.year`. **Blank when LODES was unavailable.** When it is filled, it is 0 for a block group with no jobs. |
| `area_km2` | TIGER 2020 land area (`ALAND` / 1e6). **Blank when TIGER was unavailable.** |
| `county_fips` | 5-digit state+county FIPS |

Rows are sorted by geoid. Block group `…0` in tract `99xxxx` is water-only. It is kept, and
its pop is 0.

### `od_tracts.csv` (optional; absent when LODES OD was unavailable)

`h_tract, w_tract, jobs`: LODES 8 OD (main + aux) for every state of the metro, summed to
pairs of 11-digit 2020 tracts, where both the home and the work tract are inside the
metro's counties. These are the column names `dfwt/demand.py` reads (config
`demand.lodes_od_path`). Tracts are the first 11 digits of a zone geoid.

### `existing/`: today's fixed-route rail and frequent bus, in `dfwt`'s network table format

`lines.csv`, `stations.csv`, `line_stops.csv` and `line_segments.csv` have exactly the
columns in `network/README.md`, so `dfwt.network.Network.from_raw` loads them. They are
built from GTFS like this:

- **Service day**: a typical Tuesday to Thursday inside the feed's `feed_info` dates.
  "Typical" means the most common trip count, so holidays drop out. `meta.json` → `sources.gtfs.feeds[].service_date`.
- **Kept routes**:
  - every rail, subway/metro and tram/light-rail route;
  - bus routes whose name matches `brt_name_pattern`;
  - bus routes whose AM-peak headway is at most 15 minutes.
  `routes.csv` lists every route, with its peak and midday headways and why it was kept or dropped.
- **`lines.csv`**
  - `line_id` is `m<mdb id>_<route_short_name>`.
  - `status` is always `existing`.
  - `headway_min` is the AM-peak headway (07:00–09:00, busier direction: 120 / trips leaving their first stop in the window).
  - `mode` is one of:
    - `commuter`: GTFS rail.
    - `metro`: subway, or tram ≥ 5 km with mean stop spacing ≥ 0.5 km.
    - `streetcar`: the other trams.
    - `brt`: a bus route matching `brt_name_pattern`.
    - `bus`: a frequent bus route. **`bus` is not one of `dfwt`'s config modes**: add a mode, or map it, before you evaluate.
  - `notes` give the feed, route, trip count, date and midday headway, or `PEAK-ONLY` when no trip runs 10:00–14:00. These are P&R expresses.
  - `color` is the GTFS `route_color`.
- **`stations.csv`**: `station_id` is `m<mdb id>_<stop_id>`. A stop is replaced by its `parent_station` when it has one, so platforms collapse into stations. Bus stops are one direction only: the busier direction's most common stop pattern.
- **`line_stops.csv`**: that pattern, with `year_opens` = `config.json` → `existing_year`.
- **`line_segments.csv`**
  - `geometry_source`:
    - `gtfs_shape_dist`: the trip's shape, cut at the stops by `shape_dist_traveled`.
    - `gtfs_shape`: the shape cut by projecting the stops onto it.
    - `straight`: the trip has no shape.
  - `grade` is always `surface`, because GTFS does not record it.
  - `locked` is 1.
- **`routes.csv`** (extra, not a dfwt table): `feed, route_id, short_name, long_name, route_type, class, trips_on_date, am_trips_busier_dir, headway_min, headway_basis, midday_headway_min, mode, kept, reason`.

### `osm/roads.parquet`, `osm/rail.parquet`

Overture transportation segments inside `meta.json` → `bbox`, with the same schema as
`data/osm/*.parquet`, which `dfwt/osmroute.py` reads. The columns are `id, geometry` (WKB
LineString), `subtype, class, subclass, names, connectors, road_flags, rail_flags,
access_restrictions, bbox`. Roads are limited to motorway, trunk, primary, secondary and
tertiary. Rail has every class. `osmroute.Graph` hard-codes `data/osm/`, so point it at
these files (or copy them there) to route on them.

### `zones_places_proxy.csv` (only with `--jobs-proxy places`)

`geoid, places`: open Overture places with confidence ≥ 0.5, each assigned to the nearest
block-group centre within 5 km. There are no block-group polygons, so places just outside
the counties can land in edge zones. This is a **proxy for where jobs are, not a job
count**. It is never written into `zones.jobs`.

### `meta.json`

- `metro`: the registry entry.
- `bbox`: `[xmin, ymin, xmax, ymax]`, the block-group centres plus the margin.
- `fetched_at`.
- `sources.<name>`: for each source, its `status` (`ok` / `blocked` / `failed`), its URLs, vintage or year or release, row counts, checksums and errors.
- `outputs.<file>`: row counts. `zones.csv` also has `empty_columns`.
- `missing`: everything the contract asks for that this run could not supply, and why.

## Step 2: a potential network (`python -m metro generate <id>`)

```
python -m metro generate houston                      # budget: config budget.musd_per_year x 30 years
python -m metro generate houston --budget-musd 100000 --no-model
python -m metro generate houston --jobs-proxy places  # no jobs data: places proxy, flagged (generated/houston_places_proxy/)
python -m metro check-dfw [--reuse]                   # DFW cross-check against the hand plan
```

It reads only `data/metros/<id>/` (DFW is presented in that shape by `metro/inputs.py:adapt_dfw`,
which `generate dfw` runs on first use) and writes `generated/<id>/`:

- `lines.csv`, `stations.csv`, `line_stops.csv`, `line_segments.csv`, `transfers.csv`: today's lines
  (status `existing`) plus the generated ones (`proposed`, opening five years after `existing_year`),
  with empty `stages.csv` / `service.csv` / `infill.csv` so nothing falls back to DFW's plan. They load in
  the DFW tools: `python -m dfwt validate --scenario $PWD/generated/<id>`.
- `report.md`: inputs and their gaps, the centers, the corridors, every chosen line (order, mode and why,
  km, cost, value) and the best rejected ones with the reason; `candidates.csv` (all of them), `centers.csv`,
  `preview.png`.

How it works (every threshold is in `metro/generate.json`, documented there; costs, speeds, headways,
walksheds and the ridership logit come from `config.json`):

1. **Centers** (`metro/centers.py`): people + jobs per km2 on a 500 m grid (1 km kernel); dense cells climb
   to their local peak (density clustering), clusters of 20,000+ people + jobs are centers; downtowns by
   jobs; smaller towns at the edge for regional rail.
2. **Corridors** (`metro/candidates.py`, `metro/routing.py`): a Gabriel graph over the centers, each link
   routed on the metro's own Overture roads with `tools/gen_expansion.py`'s metro and BRT profiles (via
   `dfwt/osmroute.py`); candidate lines are shortest paths through it. Regional rail: routes on existing
   standard-gauge track from each downtown or major center to centers and towns 13-90 km away.
3. **Mode and stations**: people + jobs within 800 m per route-km picks metro / streetcar / BRT (BRT over
   capacity becomes metro); stations at every center, at today's stations within 300 m (shared ids) and at
   the mode's spacing (urban / suburban) in between; walk transfers up to 650 m.
4. **Value and selection** (`metro/sketch.py`, `metro/select.py`): a sketch demand model (the same commute
   flows and logit as `dfwt`) gives each line the daily trips it adds over today's lines and the lines
   already chosen; lazy-greedy selection by new trips per $M (capital + 20 years' operating cost) within the
   budget, rejecting duplicates and lines that would be islands.
5. **Model run** (`metro/model.py`): `dfwt`'s demand model (`Network.from_tables` + `evaluate.run_year`) on
   the metro's zones, today's land use, every line open, against today's lines.

Data gaps are never filled silently: without jobs (Houston today) every people + jobs threshold is scaled by
0.65, commutes go to where people live, downtowns come from the registry's reference points
(`meta.json` `metro.downtowns`), and `report.md` says so at the top. `--jobs-proxy places` (opt-in) uses
Overture places as where jobs are, scaled to 0.53 jobs per resident, flagged the same way. Local buses in
`existing/` (mode `bus`) are left out of the network, as in DFW (they are the model's feeder grid). The
model's behavioural constants are DFW's calibration; elsewhere they are a transfer, not a fit.

Results: `reports/generator_dfw_check.md` (DFW against the hand-built 2M plan), `generated/houston/report.md`
(population only) and `generated/houston_places_proxy/report.md`.
