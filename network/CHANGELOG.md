# Network changelog

## v2 (from the panel review)

Applied by `tools/apply_v2_changes.py` to the migrated v1 tables. Step IDs match `reports/panel/index.html`. The untouched v1 plan is kept as `scenarios/v1_baseline/` and in `archive/v1/`.


### A9

- line E20 'Cotton Belt' renamed 'Silver Line'
- line F05 'Silver' renamed 'Berry Line'
- line E19 'Silver' renamed 'I-20 Crosstown'
- line E18 'Line 76' renamed 'Las Colinas-Mesquite Line'
- line E22 'Blue Ctd' renamed 'I-30 Line'
- line E23 'Purple line' renamed 'SH-360 Line'
- line E01 'BRT' renamed 'White Settlement BRT'
- line E02 '3' renamed 'Riverside-Forest Hill BRT'
- line E04 '46' renamed 'Jacksboro BRT'
- line E25 'Collin Commuter' renamed 'McKinney Line'
- line E09 'Texrail' renamed 'TEXRail'
- line E11 'A Train' renamed 'A-train'
- line E16 'DNT Line - West' renamed 'DNT West'
- line E17 'DNT Line - East' renamed 'DNT East'
- dropped the '(ROW)' suffix from commuter line names
- station X208 'Turtel Creek' renamed 'Turtle Creek' (approximate cross-street/neighborhood)
- station X234 'Turtel Creek' renamed 'Turtle Creek' (approximate cross-street/neighborhood)
- station X203 'Plz' renamed 'Walnut Hill / Marsh' (approximate cross-street/neighborhood)
- station X232 'A famous place' renamed 'Preston Center' (approximate cross-street/neighborhood)
- station X249 'Great Restaurants' renamed 'Irving West' (approximate cross-street/neighborhood)
- station X221 'Dallas Baptist University (DBU North)' renamed 'Tollway / Park Blvd' (approximate cross-street/neighborhood)
- station X223 'Baylor Scott & White The Heart Hospital - Plano' renamed 'Tollway / Frankford' (approximate cross-street/neighborhood)
- station X215 'Haven Behavioral Hospital Of Frisco' renamed 'Frisco Main St' (approximate cross-street/neighborhood)
- station X218 'Dr pepper ballpark' renamed 'Riders Field' (approximate cross-street/neighborhood)
- station X504 'Dr pepper ballpark' renamed 'Riders Field' (approximate cross-street/neighborhood)
- station X219 'Eating Recovery Center Dallas / Plano NW' renamed 'Stonebriar' (approximate cross-street/neighborhood)
- station X505 'Eating Recovery Center Dallas / Plano NW2' renamed 'Stonebriar' (approximate cross-street/neighborhood)
- station X220 'Eating Recovery Center Dallas / Plano W' renamed 'Legacy West' (approximate cross-street/neighborhood)
- station X506 'Eating Recovery Center Dallas / Plano' renamed 'Legacy Town Center' (approximate cross-street/neighborhood)
- station X507 'Eating Recovery Center Dallas / Plano SE' renamed 'Preston / Legacy' (approximate cross-street/neighborhood)
- station X508 'Epic Strides' renamed 'Coit / Legacy' (approximate cross-street/neighborhood)
- station X509 'Epic Strides E' renamed 'Independence / Legacy' (approximate cross-street/neighborhood)
- station X510 'Epic Strides E2' renamed 'Custer / Legacy' (approximate cross-street/neighborhood)
- station X044 'Texas Health Care Rheumatology' renamed 'Hulen / Sycamore School' (approximate cross-street/neighborhood)
- station X043 'Texas Health Care Rheumatology E' renamed 'Wedgwood' (approximate cross-street/neighborhood)
- station X032 'A Stop' renamed 'Henderson St' (approximate cross-street/neighborhood)
- station X002 'BRT' renamed 'Jacksboro / Northside' (approximate cross-street/neighborhood)
- station X006 'BRT/ Subway' renamed 'Ridgmar North' (approximate cross-street/neighborhood)
- station X437 'Kindred Hospital Tarrant County' renamed 'North Arlington' (approximate cross-street/neighborhood)
- station X428 'Trusted Medical Centers Mansfield' renamed 'Mansfield North' (approximate cross-street/neighborhood)
- station X298 'Vibra Specialty Hospital of Desoto' renamed 'Camp Wisdom' (approximate cross-street/neighborhood)
- station X297 'A mall' renamed 'Red Bird' (approximate cross-street/neighborhood)
- station X444 'Texas Health Surgical Specialists' renamed 'DFW Airport South' (approximate cross-street/neighborhood)
- station X410 'Metrocare hillside adult mental health clinic and primary care S' renamed 'North Oak Cliff' (approximate cross-street/neighborhood)
- station X411 'Metrocare hillside adult mental health clinic and primary care' renamed 'West Dallas' (approximate cross-street/neighborhood)
- station X412 'Metrocare hillside adult mental health clinic and primary care NE' renamed 'Singleton / Sylvan' (approximate cross-street/neighborhood)

### A1

- TEXRail: every 30 -> 15 min from 2030
- TRE: every 30 -> 15 min from 2030
- A-train: every 30 -> 15 min from 2030
- Orange Line: every 15 -> 10 min from 2030
- Green Line: every 15 -> 10 min from 2030
- Red Line: every 15 -> 10 min from 2030
- Blue Line: every 15 -> 10 min from 2030
- Silver Line: every 30 -> 10 min from 2030

### A2

- Forest Lane BRT: opens 2030 (-15 years)
- Ross Avenue BRT: opens 2030 (-10 years)
- Jacksboro BRT: opens 2030 (-25 years)
- Jefferson Blvd BRT: opens 2030 (-15 years)

### A3

- FW Orange: southwest tail Medical City -> Altamesa deferred to 2045 (saves $2.1B of 2035-40 spending for ~1.5 competitive commutes per $1M); the Stockyards/Panther Island north leg stays in 2035 for tourism and TOD demand LODES undercounts

### A4

- Midlothian Line extended Oak Cliff -> Westmoreland (DART) so it is not an island from 2045 to 2065 (sketch geometry, ~1.1 km)
- McKinney Line extended Watters Creek -> Parker Road (DART) and moved to 2035 (-5 years); it connected to nothing until 2050 (sketch geometry on the DART-owned rail corridor)
- Jacksboro BRT routed Magnolia W -> Fort Worth T&P -> Henderson St so it connects to TEXRail/TRE when it opens in 2030 (sketch geometry)
- Riverside-Forest Hill BRT moved to 2045 (+10 years): before then it touched no other open line

### A6

- new SH-121 BRT (E38) McKinney -> Craig Ranch -> Frisco/Riders Field -> Stonebriar -> Legacy West, 2040 (sketch alignment)

### A7

- dropped TexRail 3rd exp (E06): repeats the Alvarado line's Edgecliff-Crowley corridor (~0 marginal value)
- dropped Woodhaven direct (E03): Woodhaven direct adds no measurable value next to Teal and the Crosstown Loop
- Ennis Line held as 2070 long-range reserve (+10 years)
- White Settlement BRT held as 2070 long-range reserve (+10 years)

### A5

- 72 explicit transfer links between stations 400-800 m apart on different lines (walk time computed from distance; previously no transfer existed)

## v2.1 (geometry and staging review)

- **Teal** now starts at Woodhaven. The drawn line ran Haltom North -> Riverside / Race St ->
  Woodhaven -> back to Riverside / Race St, so every train reversed on the Woodhaven spur
  (the "east tail zigzag" from the original Phase One review). Haltom North stays served by
  the FW Crosstown Loop.
- Geometry: commuter rail routed on real track, metro curves fitted, BRT de-noised, 74
  stations moved up to 100 m off bends (`python -m dfwt align`; details in
  `reports/GEOMETRY.md`).
- Staging: `stages.csv` added (inferred from the plan's years); Orange's Stockyards /
  Panther Island leg is locked to 2035 at the owner's request.

## v2.2 — downtown Fort Worth: Jones St trunk (owner's choice)

The drawn downtown zigzagged every north-south line Courthouse -> Sundance Square -> east to
Central Station -> back west to Convention Center -> south to T&P, with 67-84 degree turns
between stations as little as 255 m apart. Three re-sequenced options were fitted and scored
(`tools/downtown_options.py`); the owner chose the Jones St trunk:

- **Orange / Pink**: Panther Island South -> Courthouse -> Central Station -> T&P -> S Main.
  Every north-south line now meets TRE / TEXRail at Central Station.
- **Blue**: east-west Butler Place -> Central Station -> Sundance Square -> TCC Trinity River
  -> W 7th (direct Handley -> TCC, 24 min instead of 34 with a transfer).
- **Teal**: Trinity Bluff -> Courthouse -> TCC Trinity River (Sundance Square is a 255 m walk).
- **Purple**: Central Station -> T&P -> Magnolia.
- **Convention Center** is no longer a metro stop (420 m from Central Station, 440 m from T&P).

Scored against the previous downtown (2070): +2,400 competitive commutes, +$0.06B capital,
Fort Worth metro curves tighter than 150 m: 25 -> 11 (the rest are outside the core).
The Main St and Main St via Convention Center alternatives scored +1,300 / +900 commutes at
+$0.31B / +$0.52B; their tables can be regenerated with `tools/downtown_options.py`.

## v2.3 — straight corridors (owner's "what would actually be built" review)

- Metro lines run straight along their corridors and stations come to the line: stops
  that forced a detour moved onto the direct path (up to 800 m, or 1.5 km for sharp jogs);
  drawn paths that wandered became the direct route; small wiggles smoothed.
- Stops the line had to double back for were dropped from that line: I-20 Crosstown
  (Lindberg SW, Sunset Acres), SH-360 (Cypress Waters SW2/SW3, DFW Airport South,
  Estelle W), Bowie (Haltom City), Gainesville (Melody Hills, Stockyards NHD NE3).
- Commuter lines with no usable track are straightened and fitted to commuter-rail
  curve limits; stations up to 800 m from real track move onto it.
- Tight curves on proposed lines: 342 (as drawn) -> 41. See `reports/GEOMETRY.md`.

## v2.4 — the optimizer's build order becomes the plan (owner's decision)

- `stages.csv` is now the optimizer's build order under the flat $2.3B/yr budget
  (`python -m dfwt optimize`; every opening and its gain per $M is in
  `reports/build_order_log.csv`). Orange's Stockyards/Panther Island leg stays locked to 2035.
- The previous hand-set phasing is kept as the `v2_phasing` scenario.
- More opens early: the best BRT and commuter corridors in 2030, then the Dallas
  crosstowns and Fort Worth metro from 2035.
- Left past 2070, because no interval showed a measurable gain: the Gainesville (90 km),
  Ennis (55 km) and Bowie (45 km) commuter lines, 41 km of the FW Crosstown Loop,
  White Settlement BRT and a 2.4 km Teal tail. They stay in the network for a later decade.
- Model fixes that came with it: park & ride sits at commuter stations and each line's
  planned termini (not at temporary ends of partly built lines), and the optimizer
  never opens a line in disconnected pieces.

## v2.5 — growth, ridership, a yearly horizon to 2100, and the 2 million riders scenario

Model (config.json; reports/RESULTS.md has the numbers):
- Population and jobs grow by year (NCTCOG Mobility 2050 mid case, flattening toward 2100), plus
  development near new stations (10-30% uplift by setting, mostly drawn from elsewhere).
- Peak drive times grow 3% a decade (capped at +15%); BRT takes a quarter of that.
- Daily ridership: commute mode choice (drive / transit / walk-bike, households without a car),
  waits and out-of-vehicle time weighted as riders perceive them, driving cost and paid parking,
  calibrated to today's ~80k rail boardings with today's buses as feeders and about half of
  riders driving to a lot. Reported per mode (metro, regional rail, BRT, feeder bus), as an
  all-mode total, and as daily trips with each trip counted once.
- Park & ride garages hold real numbers of cars (1,500 at line ends, 400 at regional rail
  stations, ~500 at today's suburban lots); people a full garage turns away walk or take the bus.
- Every year from 2025 to 2100. Stages open in exact years: `python -m dfwt schedule` keeps the
  build order and moves each stage to its earliest affordable year under the flat budget.

Network:
- Station names are real places (cross streets, neighbourhoods, landmarks) instead of generated
  compass suffixes: network/station_renames.csv, tools/rename_stations.py. Today's stations keep
  their names.
- Line colors distinguishable (DNT West gold, Berry, I-20 brown, regional rail tints); BRT drawn
  as a solid, thinner line.

Scenarios:
- `two_million` (the default on the map): the plan plus an arterial BRT grid, an SH-114 metro,
  job-campus BRT and infill stations (2065-2090), frequent service, 15-minute feeder buses,
  bike and walk access, Wiehle-Reston-style garages at selected suburban stations, and moderate
  upzoning with 20% of growth steered to station areas. Reaches about 2 million daily trips by
  2100. Parking pricing and cash-out are not included.
- `lever_*` folders: the four planners' individual levers, kept for analysis (not on the map).

## v2.6 — BRT on the streets

- Every BRT line follows real arterials (Overture roads; `tools/route_brt.py` for the plan's lines,
  `tools/gen_expansion.py` for new corridors, whose stops are now placed along the routed street).
  Bus-only stops moved onto the street; rail stations well off the street get a pull-in.
- The 2M scenario leaves out 10 corridors that added under 5 daily trips per $M
  (`scenarios/two_million/drop_lines.txt`, 137 km, $2.4B); it still reaches 2M daily trips (2089).
- An extension never opens before the stage it attaches to (budget scheduler).

## v2.7 — Fewer BRT stops, best value first

- New BRT corridors stop every 1.2 km in dense areas and 1.6 km in suburban ones (was 0.8 km);
  new corridors average 1.5 km between stops.
- The 2M scenario schedules by riders per dollar (`"staging": {"priority": "value_per_musd"}`):
  the strongest corridors are built first, whatever their mode. BRT now opens at a median of 2051
  (was 2070), metro at 2045 (was 2037), commuter rail at 2058 (was 2030). Three weak BRT
  corridors fall past 2100. 2.04M daily trips in 2100.

## v2.8 — Shared track, McKinney straightened, map groups

- DNT East runs on the Legacy Line's track from Frisco to Stonebriar (Frisco, Stonebrook / Dallas
  Parkway, The T's, Dallas Parkway / Gaylord, Stonebriar) instead of a parallel alignment 0.5 km
  west. Starwood / Stonebrook (DNT East only) is removed; Frisco Main St, Riders Field and the
  western Stonebriar stay as BRT stops.
- The McKinney Line runs straight up the DART-owned railroad from Parker Road (no detour west to
  Watters Creek), with a new Spring Creek Parkway station where the Legacy Line now ends (extended
  1.6 km from Watters Creek). Transfers Red / McKinney at Parker Road, Legacy / McKinney at Spring
  Creek Parkway.
- Map: lines on the same track are drawn side by side when zoomed in (dfwt/bundle.py), and the
  Lines panel has a checkbox per group (each mode, split into plan lines and scenario additions).
