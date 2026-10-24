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

## v2.9 — Review fixes

Nine reviewers and a UX pass went over the project (reports/REVIEW.md lists what they found
and what is left to decide). Fixed:

- Model: riders rank access modes, connector stations and routes by the same perceived
  minutes as the mode choice, including the drive-to-transit constant (garages had been
  chosen on raw minutes and penalised afterwards, so a full garage could add riders).
  Recalibrated to 2025: transit constant -0.797, drive-to-transit constant -1.0 (51% of
  rail riders drive to a garage, 80.6k rail boardings). Walks between nearby platforms no
  longer count as transit trips. Station-area growth ramps from each mode's arrival.
- **The 2M scenario now reaches about 1.87M daily trips in 2100** (was 2.04M). The access
  fix moves riders off garages (5% of 2100 riders, was 20%), and the scenario's
  walkability package now starts in 2030 instead of applying to today's network (its 2025
  run was 13% above calibration). Whether to add levers to reach 2M is an open decision.
- Costs: platforms are charged per mode (a metro line at a BRT stop builds its own).
- Network: new BRT stops at every station within 300 m of the route, so new corridors meet
  the lines they cross (three had been cut off and pushed past 2100); Shiloh Road BRT
  stops at SpringPark. The aligner no longer moves interchange stations.
- Schedule: a local repair replaces shrinking the whole budget (100% used, was 97%);
  `schedule --write` clears stale stage files; build stops on default-scenario errors.
- Reports: peak-hour loads use daily riders (were ~3.8x low); light-rail capacity 12k/h.
- Map: continuous side-by-side shared track, interchange capsules, stations by zoom,
  contrast guard, recoloured clashing lines (SH-114, I-30, Gainesville, Bowie, SE TexRail,
  Alvarado), trips drawn along their route, trip-planner messages, popup/panel/touch fixes.

## v2.10 — Peer costs, D2, levers to 2M, Weatherford and Greenville

- **Costs** at 2025 US peer levels (commuter rail $45M/km, arterial BRT $30M/km, light rail
  $140M/km at grade, $600M/km in tunnel; stations $4-50M, $200M underground), garages charged
  at ~$30k a space (BRT termini 400 spaces), falling with a steady program: 15% lower by 2040,
  25% by 2055 (config cost_efficiency). Operating cost is reported per year. The plan costs
  $103.6B (was $94.4B) and is rescheduled into the budget (last opening 2075).
- **D2 subway** (2M): Green and Orange leave the downtown mall in 2035 for a tunnel under
  Commerce Street (Victory - Metro Center - Commerce / Harwood, then Deep Ellum or Pearl); the
  mall keeps Red and Blue. New `reroute` edit: the old routing runs until the new track opens.
- **Levers** (2M): parking prices double downtown by 2050 and $5/day parking spreads to the
  densest job centers; regional rail runs through Fort Worth and Dallas (TRE to Alvarado and
  Terrell, TEXRail to Primrose, Mansfield-Denton-Carrollton); the Red Line runs on to McKinney
  as light rail. The suburban Wiehle-Reston garages are dropped. **About 2.24M daily trips in
  2100** (1.85M without the parking policy).
- **New regional rail** (2M, locked by 2100 for a complete network): Weatherford Line (Fort
  Worth T&P - Benbrook - Aledo - Hudson Oaks / Willow Park - Weatherford, 2090), Greenville
  Line (Downtown Rowlett - Rockwall - Fate - Royse City - Caddo Mills - Greenville, 2095), Alvarado
  Line on to Cleburne (2088). Hunt County is outside the model's zones, so Greenville's
  ridership is understated.
- **Network**: DNT East starts at Frisco Main St (Frisco Square); the Legacy Line runs as a DNT
  East branch from Spring Creek Parkway via Legacy West to Pearl (each branch every 10 min);
  FW Orange ends at Medical City - Baylor (FW Red serves the rest); Fort Worth metro lines are
  named "FW Green / Blue / Orange / Pink / Berry / Red / Purple".
- **Scheduler**: through-routed lines' stages price their part of the joined line; today's
  service is never moved; new track no stage covers (D2) is reserved at its own year; lines
  briefly cut off open when they connect.
- **Map**: From/To station search; hidden lines are left out of trips (as if not built); BRT
  routes on one street draw as one stroke with route names on hover; operating cost on the
  capital card.

## v2.11 — Streetcars, road corridors, BRT ends, I-30 through Uptown

- **Dallas streetcars** (existing service): the Dallas Streetcar (Union Station - Bishop Arts -
  Methodist Medical Center, every 20 min) and the McKinney Avenue M-Line Trolley (Olive / Ross -
  Uptown, every 15 min). New `streetcar` mode: 18 km/h, 400 m walkshed, no park-and-ride.
- **I-30 Line shares the I-20 Crosstown's tunnel**: from Victory it runs on with the I-20
  Crosstown (Victory - Pearl - Central / Hall - Ross / Bennett) instead of its own Design
  District / McKinnon / Uptown alignment: one tunnel north of downtown instead of two.
- **Road corridors**: the Las Colinas-Mesquite Line's surface sections follow freeways and
  arterials instead of cutting through neighborhoods (single-line stations moved onto them); the SH-114 Line (2M) follows
  SH-114 and runs on, express, to Roanoke (Westlake Solana - Roanoke, 2090).
- **BRT ends**: a new BRT terminus that turns into a side street for its last few hundred meters
  ends on the arterial instead (unless that end is within a short walk of another line).
- **Park-and-ride**: terminus garages sized per mode (none at streetcar ends).
- **Scheduler**: re-checks the budget after holding cut-off lines back.
- **Results**: the plan costs $103.1B (was $103.6B) and carries ~771k daily trips in 2100; the 2M
  scenario reaches 2M in 2077 and ~2.23M daily trips in 2100 at $135.0B.
- **Map and diagram**: a second station click works again (the trip layer swallowed it); track
  still to come is grey in the diagram.

## v2.12 — Infill stations, one-seat links, SH-114 realigned, straighter diagrams

A transfer analysis followed every modelled trip through the network (`reports/TRANSFERS.md`):
which stations and line pairs carry the transfers, which trips need two or more, and where
two lines cross or pass close with no station to change at. About 40 candidate fixes were
tested one by one in the ridership model (an extra stop slows everyone riding through, so
many lost riders); the ones that gained riders were tested together and kept only if each
still added riders next to the others. **They add riders (+2% in 2100) by making trips faster
and reaching new areas, not by cutting transfers:** with the model's 3-minute transfer penalty,
many riders trade a slow one-seat ride for a faster trip with a change at a new interchange, so
transfers per commute stay about level (0.33 to 0.34 in the plan, 0.47 in 2M, same commutes).
Three-seat rides fall where a one-seat link appears (SH-114 and the Stemmons BRT to Victory).
A longer transfer penalty is noted for a later round.

- **Infill stations** (plan and 2M): Red/Orange at Main / Sherman Street (downtown Richardson,
  Beltline Line) and NW Highway / Shady Brook; Red/Blue/Orange at Central / Hall (I-20
  Crosstown and I-30); Blue at Shiloh / Forest (Garland); Orange at John W Carpenter /
  Freeport (SH-114 Line in 2M); TRE at Rock Island / Briery (Beltline Line, Irving) and at
  Airport / Beach with FW Green (Fort Worth); the TEXRail extension and FW Berry at
  Pennsylvania / Henderson; Silver Line at Marsh / Arapaho (walk to DNT West's Belt Line /
  Marsh); Midlothian Line at I-20 / Oriole (I-20 Crosstown). Each opens when both lines are
  there. The plan costs $103.2B (+$0.1B) and carries ~788k daily trips in 2100 (was ~771k).
- **SH-114 Line** (2M), redrawn by the owner: in the LBJ/SH-114 freeway corridor without the
  loops in Las Colinas, Freeport North and Southlake; beside TEXRail through Grapevine (Ira E.
  Woods - Grapevine-Main Street - DFW Airport North); Trophy Club and Westlake stations on
  SH-114 instead of the Kirkwood / Dove Road / Westlake Solana detour. Belt Line / Royal moves
  onto the SH-114 crossing (Belt Line / SH-114). Its trains run on over the Green Line from
  Farmers Branch to Victory (new `run_over` edit), so riders from Love Field, Market Center
  and Victory reach Las Colinas and DFW north without changing at Farmers Branch.
- **Stemmons-Brookhollow BRT** (2M) starts at Victory (via Medical/Market Center) instead of
  Inwood/Love Field: one change from the I-20 Crosstown, I-30 and TRE.
- **Walk link** Commerce / Harwood (D2) - Marilla / Pearl (DNT East).
- **2M schedule**: rescheduled with the new values; DNT East (2043) and the I-20 Crosstown
  (2037) move earlier, the I-30 (2056) and Las Colinas-Mesquite (2063) lines later. ~1.06M
  daily trips in 2050 (was 1.03M), ~2.25M in 2100, 2M reached in 2077; $136.6B (more is built
  before unit costs fall).
- **Diagram**: Rail / BRT / All versions, each laid out for its own lines (Rail is the default),
  with straightness rules: long runs on their axis, a cost per bend and more for zig-zags,
  straight-through lines kept opposite at junctions, and no run laid across another line.
  The Rail diagram has about half the bends of the old all-modes diagram.
- `tools/gen_expansion.py`: a spec's `road_weights` (keep a line in its freeway), and stops
  whose leg follows an existing railway (`"follow": "rail"`) or a hand-drawn straight line
  (`"follow": "straight"`).

## v2.13 — A more realistic model, a stable build order, every region served

From the second review (experts, six residents across the region, and a downtown group).

**The model is more realistic, and the headline is now a range.**
- A change of vehicle costs 5 minutes (3 before; 8 is a sensitivity).
- The drive it competes with gets faster on long trips: local streets first, then freeway
  speed, so Mesquite - Wilmer is about 42 min by car, not 67.
- BRT runs at 30 km/h on average; drop-off works like park & ride; 6% of commuters will bike
  to a station.
- Operating cost is per train or bus hour plus feeder buses (about twice the old figure).
- The capacity check uses the frequency each line actually runs.
- With the review's fixes below, **the 2 million riders scenario carries ~866k daily trips in
  2050 and ~1.88M in 2100 (was 1.06M and 2.25M); 2 million is no longer reached by 2100.** On
  the low growth path it is ~705k and ~1.17M. The budget plan carries ~370k and ~756k (was
  388k and 788k). Capital is about the same ($136.4B and $103.2B); operating cost in 2100 is $4.8B
  and $2.7B a year.

**The 2M build order no longer flips between builds.**
- Before, the schedule ranked lines by the last build's values, and shared track was charged
  to whichever line opened first, so DNT East and the I-30 Line swapped decades from build to
  build.
- Each line is now valued by the trips lost when it is removed from the 2100 network, on one
  land use (the network's with everything open), per $M of its share of capital (shared track
  and stations split among their lines, 2025 prices). Through-routed lines (Red Line to
  McKinney, TRE to Alvarado and Terrell, TEXRail to Primrose, Mansfield-Denton) are measured
  too. `python -m dfwt values` computes them (`results/two_million/line_values.csv`).
- The schedule starts from the generated stages every time and charges each shared piece once,
  in the earliest year a stage opens it. Two schedules in a row are identical, and a line's
  value is identical under two different schedules.

**Rules for the order (owner decisions).**
- Stages of plan lines that reach downtown Dallas or Fort Worth open no later than in the
  budget plan: FW Green and FW Blue 2042, DNT East and the I-20 Crosstown 2043, FW Pink 2046,
  DNT West 2047.
- Arlington's first rail by 2038: the I-30 Line from Dallas via Grand Prairie to Downtown
  Arlington, the stadiums and Six Flags. On to Handley with FW Blue by about 2043 (tested:
  +9k daily trips in 2050 and +31k in 2060).
- A county's next line goes ahead of the value order once its share of population of the money
  committed so far covers it. Denton County's BRTs open in 2029-30; its share of capital still
  tops out near 7% (12% of people), because its projects are all low-cost BRT. Weatherford
  (2061), Greenville (2063) and Cleburne (2075) are no longer pinned to the 2090s.
- Every city over 150,000 is served by about 2040 (Frisco 2043 is the latest).
- No new line opens as a stub of fewer than 8 stops ahead of the rest of it.

**New and changed service.**
- **Express buses** in freeway managed lanes (cheap: stops, ramps and garages):
  - I-35E Express: Waxahachie - Red Oak - Belt Line - Oak Cliff - Union Station, every 15 min,
    2027. It is the best value per dollar in the scenario.
  - Mesquite Express (I-30) and McKinney Express (US-75 to Parker Road) by 2032, decades
    ahead of their rail.
- Rural regional rail (Bowie, Gainesville, Sherman, Ennis, Waxahachie) every 30 min, not 15.
- Streetcars every 10 min from 2030.
- Late-night service to about 2 a.m. on the Red, Blue, Green, Orange, FW Orange lines and the
  TRE, with late feeder buses: in the operating cost (the commute model doesn't count its riders).
- $400M for a Victory pocket track and the junctions where SH-114 trains join the Green Line.
- Tested and not adopted: a TRE skip-stop express (no gain) and the M-Line on to Deep Ellum
  (no gain in a commute model that doesn't see evening or visitor trips).

**Fixes.**
- Infill stations open with their own line's track there, or when their partner line arrives
  (`network/infill.csv`). TEXRail x FW Berry opened in 2105 in v2.12's 2M build;
  `reports/TRANSFERS.md` is corrected.
- No new park & ride garages inside the downtown cores.
- `run_over`: the old terminus keeps its garage, a line can't borrow its own stops, and
  borrowed track never makes the borrower its owner.
- The Beltline BRT is a closed ring (no ride - walk - ride on the same line at Main / Galloway).
- `tools/gen_expansion.py`: generated stations keep their ids (`scenarios/station_ids.csv`), and
  regenerating is byte-identical.

**Map and diagram.**
- The trip planner ranks trips as the model's riders would, and shows clock minutes. Park &
  ride is off by default, and the drive estimate matches the model.
- New: "What it means for you" (frequencies, hours, cost per resident) and a "near me" summary.
- Station popups show the opening year and the construction window.
- Duplicate station names now name their line.
- Diagram:
  - every walk link between stations is drawn;
  - "All" is now "Rail + BRT corridors";
  - BRT routes are named and tinted by area;
  - area names sit at each city's core station;
  - fewer label collisions.

## v2.14 — Third review: honest baselines, fairer early decades, faster fixes

From the third review (experts and residents on v2.13 and the new story page). The owner
approved all of the recommendations.

**Headline numbers.** The 2 million riders scenario carries ~919k daily trips in 2050 and ~1.99M
in 2100. It carries ~1.73M if growth follows the county forecasts out to Collin and Denton (new:
`growth.spatial = "county"`), and ~1.23M on the low growth path. The budget plan carries ~370k
and ~778k. Capital is $135.2B and $103.4B; operating cost in 2100 is $4.9B and $2.7B a year.
Today's network with no expansion (the current track) carries ~185k in 2100. Run with the plan's
parking and access policies, it carries ~327k. The story now shows both baselines: the network
alone multiplies ridership about 6 times, and the network with the policies about 11 (5-12 across
the growth cases).

**Bugs fixed.**
- **Express buses.**
  - They are routed on the freeway network (`tools/express_buses.py`) and run at freeway speed
    only on the freeway parts: I-35E 51 km/h (every 7.5 min), Mesquite 51 km/h.
  - An interim express stops when its rail opens (`retire_with`). It is dropped altogether if the
    rail opens first: the McKinney Express goes, because the Red Line reaches McKinney in 2030.
- **Duplicate stations merged.** Handley, Berry / Stalcup, TCC Trinity River and Fair Oaks each
  had two ids a few metres apart, which wasted access slots and paid for two platforms. A
  station also takes only one of a block group's eight access slots.
- **Stops open with their track.** About 110 stops on new track used to open five years after
  it; they now open with it. Rescheduling the plan to fit the earlier spending moves 27 of 98
  stages by 1-3 years.
- **Today's lots.** Today's park & ride lots stay on lines that run through onto new track
  (Dallas Zoo, Tyler / Vernon).
- **Line values.** A line is valued by its own stages, so a through-run (Red Line to McKinney)
  is no longer scored as if riders had to change. It is valued two ways:
  - the trips lost when its stages are held back from the full 2100 network;
  - the trips it adds to the network without the new lines.
  The average is divided by its share of capital plus 20 years of operating cost.
- **Scheduling.**
  - One budget rule is shared by the scheduler and the check.
  - Missed deadlines are reported.
  - The budget repair delays stages without a deadline first.
  - Two schedules in a row are identical, and every deadline is met.
- **Story.**
  - Today's maps show today's lines, including TRE, TEXRail, the Red Line and the A-train.
  - Station areas count the share of each block group's land within a walk, so no station
    shows 0 residents.
  - Station cards: platform level over time, service in the year a station is open, today's lots,
    one entry per place.
  - Wrong claims corrected: "ten times either way", "grow exactly as on the current track",
    "commuters only", 43% vs 38%, the $277 / $271 / $270 per resident, DNT East in the 2040s,
    "one line between the downtowns".
- **Trip planner.**
  - Totals are clock minutes; the transfer penalty is perceived, not added.
  - One clear note when a faster trip exists.
  - No doubled line names.
  - "Today's lines only" is labelled in the plan picker.

**Owner decisions R1-R7.**
- **Service.**
  - I-30 and FW Blue run through at Handley as one line.
  - A line runs over track another line has already opened (`staging.ride_open_track`), so I-30
    uses the I-20 Crosstown's downtown track from 2043.
  - DNT East and Legacy run every 7.5 min.
  - 4-car trains on the I-20 / I-30 trunk, with platforms built by 2060 ($575M).
- **Trims.** FW Orange every 10 min, Riverside-Forest Hill every 12, Bowie and Gainesville at
  rush hours only. The Waxahachie Line is left out (about 436 trips for $1.5B).
- **Late night** is added on FW Blue, FW Purple, Jefferson BRT and the streetcars.
- **Order.**
  - The inner ring opens no later than in the budget plan: I-20 to Oak Cliff, the FW Crosstown
    Loop, FW Green and Blue west of 7th Street, and DNT West north.
  - Knox-Henderson infill opens in 2035.
  - Fair share is measured over ten-year bands. Collin gets 16% of capital through the 2030s
    (it had none before 2040); Denton is still short (4-7% against 12% of population).
  - No more than a stage's worth of a line opens in one year, unless a deadline requires it.
- **Consequence of counting operating cost.** The SH-114 Line ranks lower (5.6 trips per $M) and
  opens in 2066, not 2031.
- **Station names.** Town East / Belt Line (was "Rowlett", in Mesquite), Pearl / Cedar Springs,
  Fort Worth Central and Fort Worth T&P for the metro platforms, Main / 5th Street (Frisco),
  John Hickman / Legendary, John Hickman / Dallas Parkway, Colony Boulevard, Belt Line / Preston,
  Belt Line / Midway.
- **Story.**
  - The case is framed as reach, not speed.
  - Connections: Bishop Arts - Deep Ellum, Stockyards - Magnolia, and downtown to downtown (no
    high-speed link is planned).
  - Operating cost per resident, Mobility 2050's $57.9B (likely including operations) put in
    context, the 2100 population cited.
  - Votes chart sorted with a 50% line.
  - City names and labelled colour steps on the maps.
  - Phone charts stay above the text.
  - Better contrast, reduced motion and text equivalents for the charts.
  - Links into the map (`map.html#station=`, `#trip=`, `#year=`).
- **Diagram (owner's screenshots).**
  - Same-place interchanges are one node (Akard · Metro Center).
  - Long walk links are no longer drawn across downtown Dallas.
  - FW Pink runs straight north-south through La Gran Plaza.
  - No line doubles back around DFW Airport, Grapevine and Las Colinas.
- **Recalibrated** after the access-slot fix: transit constant 0.3594 -> 0.4062.

**Not done.** The one-seat Tollway - Las Colinas route and a Denton County corridor test.
