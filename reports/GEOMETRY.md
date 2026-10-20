# Geometry

How the alignments were made buildable (`python -m dfwt align`; method in
`dfwt/geometry.py` and `dfwt/align.py`, limits in `config.json` → `geometry`).

## Current state

Distinct curves tighter than the mode minimum (150 m metro, 175 m commuter rail,
measured on a 20 m resampling), on proposed lines:

| Pass | Tight curves |
|---|---|
| v2 as drawn | 342 |
| Rail routed on real track, metro curves fitted | 146 |
| Stations come to the line (straightening, stops within 800 m) | 107 |
| Stops that forced a reversal dropped, sharp jogs moved up to 1.5 km | 75 |
| Unroutable commuter lines straightened and fitted; geometry thinned | **41** |

Most of the 41 left are 85-120 m curves at junction stations (the platform has to
be straight and the line turns right after it). The rest are listed under
"Needs review".

## Rules

- **Commuter rail** follows real track (Overture / OpenStreetMap rail, turn-limited
  routing). Stations up to 800 m off the track move onto it. Lines with no usable
  track (Sherman, Bowie, Gainesville, FTW/Denton, TexPress, McKinney, Midlothian) are
  straightened and fitted like metro, with commuter-rail curve limits.
- **Metro** runs straight along its corridor and the stations come to it:
  - a stop the line had to double back for (90+ degree turn) is dropped from the line;
  - a stop that forced a detour moves onto the direct path between its neighbors,
    up to 800 m (35+ degree turns) or 1.5 km (60+ degree turns);
  - a drawn path more than 8% longer than the direct route, or far off it, becomes
    the direct route; smaller wiggles (under ~150 m) are smoothed out;
  - then tangents, spirals and arcs are fitted, with every platform on straight track.
- **Fixed**: interchanges, line ends, existing stations and the downtown cores are
  never moved or dropped. **BRT** and **existing lines** are only de-noised.

## Stops dropped

| Line | Stop | Why |
|---|---|---|
| I-20 Crosstown | Lindberg SW | the line doubled back to reach it |
| I-20 Crosstown | Sunset Acres | the line doubled back to reach it (near Camp Wisdom Rd) |
| SH-360 Line | Cypress Waters SW2, Cypress Waters SW3 | the line doubled back to reach them |
| SH-360 Line | DFW Airport South | the line doubled back to reach it |
| SH-360 Line | Estelle W | the line doubled back to reach it |
| Bowie Line | Haltom City | the line doubled back to reach it |
| Gainesville Line | Melody Hills, Fort Worth Stockyards NHD NE3 | the line doubled back to reach them |

The stations stay in `network/stations.csv`; add one back to a line in
`network/line_stops.csv` if you want it served, and re-run `python -m dfwt align --lines <id> --write`.

## Needs review (curves at fixed stops)

- **Berry Line** turns 87 degrees at Hemphill/Berry (interchange).
- **Purple** turns 72 degrees at Magnolia E (interchange with Orange).
- **DNT East** and **Las Colinas-Mesquite** turn ~70 degrees at South Side (interchange).
- **Las Colinas-Mesquite** turns 78 degrees at Las Colinas SW (interchange).
- **SH-360 Line** turns 80-87 degrees at UTA W, Irving West and Irving W3 (interchanges).
- **Gainesville Line** turns 77 degrees at Stockyards NHD NE2; **Sherman Line** 97 degrees
  at Carrollton NW2 (interchanges).

Each needs a design decision: move the interchange, split the line there, or accept a
slow curve at the station.

## Data

Rail and road network: Overture Maps transportation segments (release in
`data/osm/MANIFEST.json`), © OpenStreetMap contributors, ODbL 1.0. Re-fetch with
`python tools/fetch_osm.py`.
