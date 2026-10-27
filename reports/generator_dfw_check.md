# Generator cross-check on DFW

`python -m metro check-dfw` runs the metro-agnostic generator (`python -m metro generate dfw`, `metro/generate.py`) on DFW's inputs, ignoring the hand plan, with the hand plan's own new capital as its budget, and compares the result with the hand-built 2 million plan (`network/` + `scenarios/two_million/`). Generated network: `generated/dfw/` (its `report.md` lists the centers, every candidate and why it was chosen or rejected; `preview.png` is a map). Line-by-line matching: `generated/dfw/compare_lines.csv`.

## Totals

| | today | generated | 2M hand plan |
|---|---|---|---|
| metro / light rail km (new) | - | 267 | 580 |
| BRT km (new) | - | 1,230 | 1,135 |
| regional rail km (new) | - | 554 | 711 |
| streetcar km (new) | - | 0 | 0 |
| new lines | - | 73 | 76 (incl. extended existing lines) |
| capital, 2025 $ (dfwt costing) | - | $116.3B | $169.0B |
| residents within 800 m of a station | 3.6% | 30.5% | 30.7% |
| jobs within 800 m of a station | 15.8% | 54.8% | 56.3% |
| daily transit trips, today's land use, all lines open | 80,553 | 251,329 | 315,143 |
| daily rail + BRT boardings, same | 82,965 | 322,838 | 422,869 |
| jobs within 45 min, average resident | 21,261 | 67,950 | 69,091 |
| new daily trips per $M of capital | - | 1.47 | 1.39 |

Model runs: dfwt's demand model (gravity flows, the config.json logit calibrated to DFW's 2025 rail boardings, feeder buses) on 2026 land use with no station-area growth, every line open; the 2M plan's own policy overlay (`scenarios/two_million/config.json`: parking, access and land-use levers) is NOT applied, so both networks face the same assumptions. The 2M plan's published 2100 numbers are far higher because they include 75 years of growth, transit-oriented development and those policies.

## Which corridors match

Share of each network's new track lying within 1 km (500 m) of the other's, length-weighted: hand plan near generated 55% (40%), generated near hand plan 69% (51%); counting only a line of the same family (rail transit / BRT / regional rail): hand plan 36%, generated 47%. Chance level: 51% of the region's residents live within 1 km of the hand plan's new track (27% within 500 m), 68% (41%) of those in urban-density zones; a corridor drawn at random through populated (urban) places would lie that close about that often, so only the excess over these numbers is agreement.

A hand-plan line is **matched** when at least half of its new track lies within 1 km of generated track (any mode), **partly** at 20-50%. Of 76 hand-plan lines with new track: 48 matched (1,322 km), 22 partly (759 km), 6 missed (345 km). Of 73 generated lines: 60 lie in hand-plan corridors (1,734 km), 13 partly (317 km), 0 are corridors the hand plan doesn't have (0 km).

| hand-plan mode | km | matched km | partly km | missed km | km near generated track of the same family |
|---|---|---|---|---|---|
| brt | 1,135 | 679 | 408 | 48 | 491 |
| commuter | 711 | 135 | 279 | 298 | 218 |
| metro | 580 | 508 | 72 | 0 | 171 |

### Hand-plan lines

| line | mode | new km | near generated (1 km) | same family | verdict | closest generated line |
|---|---|---|---|---|---|---|
| E21 Beltline Line | brt | 147.7 | 52% | 46% | matched | G48 Fountain / Westpark - Highland / Weaver BRT (brt) |
| XB03 Illinois-Lake June BRT | brt | 35.6 | 57% | 32% | matched | G53 LBJ - 52nd Street / Horizon BRT (brt) |
| E38 SH-121 BRT | brt | 31.1 | 61% | 32% | matched | G45 Excel / Westgrove - Lukenbach / Rambling Metro (metro) |
| XP05 Stemmons-Brookhollow BRT | brt | 28.3 | 82% | 55% | matched | G44 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XE02 Mesquite Express | brt | 26.1 | 70% | 33% | matched | G25 Dallas / Arapaho - Masters / Bruton Metro (metro) |
| XB12 Coit Road BRT | brt | 24.5 | 75% | 44% | matched | G18 Coit / Churchill - Scenic / Sutherland BRT (brt) |
| XB28 Beach Street-Keller BRT | brt | 23.8 | 77% | 42% | matched | G72 Henderson / 5th Street - Avenue C / Hickory Rail (commuter) |
| E02 Riverside-Forest Hill BRT | brt | 21.5 | 75% | 39% | matched | G73 Henderson / 5th Street - John Arden / Solon Rail (commuter) |
| XB01 Northwest Highway BRT | brt | 20.3 | 87% | 76% | matched | G62 Lombardy / Webb Chapel - Bowser / Belt Line Metro (metro) |
| XB40 McKinney Virginia Parkway BRT | brt | 20.1 | 94% | 94% | matched | G56 Eldorado / Walker - White / Waddill BRT (brt) |
| XB09 Garland Broadway BRT | brt | 19.2 | 90% | 90% | matched | G66 Adleta / Skillman - US-80 / Pinson BRT (brt) |
| XB32 Josey Lane BRT | brt | 19.1 | 60% | 42% | matched | G65 Grapevine Mills Circle - Eldorado / Walker BRT (brt) |
| XB14 Spring Creek-Legacy BRT | brt | 18.4 | 55% | 46% | matched | G45 Excel / Westgrove - Lukenbach / Rambling Metro (metro) |
| XB38 Mid-Cities Boulevard BRT | brt | 17.5 | 75% | 64% | matched | G58 Centreport / Sovereign - Riverside Drive BRT (brt) |
| XB27 Hulen-Altamesa BRT | brt | 16.9 | 50% | 40% | matched | G38 Silver Creek / Las Vegas - Sycamore School / Meadow Creek BRT (brt) |
| XP06 Dallas Parkway BRT | brt | 16.8 | 51% | 51% | matched | G04 Excel / Westgrove - Eldorado / Walker BRT (brt) |
| XB24 Cooper Street BRT | brt | 16.4 | 92% | 79% | matched | G26 Cooper / Mitchell - Matlock / Turner Warnell BRT (brt) |
| XB26 Collins-Center BRT | brt | 16.3 | 76% | 76% | matched | G17 Waverly Drive - Bedford / Barr BRT (brt) |
| XB21 Hurst-Euless-Bedford BRT | brt | 15.8 | 100% | 100% | matched | G31 Centreport / Sovereign - Mercantile Drive BRT (brt) |
| XB41 Watauga-Keller BRT | brt | 15.7 | 100% | 100% | matched | G16 Mercantile Drive - Pearson / Fawkes BRT (brt) |
| XB02 Buckner Boulevard BRT | brt | 15.5 | 73% | 52% | matched | G53 LBJ - 52nd Street / Horizon BRT (brt) |
| E04 Jacksboro BRT | brt | 14.8 | 72% | 69% | matched | G57 Schwartz / Jasper - Silver Creek / Las Vegas BRT (brt) |
| E28 Forest Lane BRT | brt | 14.7 | 67% | 27% | matched | G25 Dallas / Arapaho - Masters / Bruton Metro (metro) |
| XB44 Sachse-Wylie BRT | brt | 14.6 | 65% | 65% | matched | G50 Bowser / Belt Line - Alanis / Stone BRT (brt) |
| XB06 Hampton-Westmoreland BRT | brt | 13.8 | 51% | 51% | matched | G19 Lombardy / Webb Chapel - Highway 67 / Marvin D Love BRT (brt) |
| E27 Ross Avenue BRT | brt | 13.2 | 94% | 27% | matched | G33 Stemmons / Medical District - Masters / Bruton Metro (metro) |
| XB35 Lewisville Main Street BRT | brt | 11.6 | 82% | 22% | matched | G20 Adleta / Skillman - Avenue C / Hickory Rail (commuter) |
| XB42 Denton Tap BRT | brt | 10.5 | 69% | 69% | matched | G42 Highland / Vista Ridge Mall - Grauwyler / O'Connor BRT (brt) |
| XB39 West Frisco BRT | brt | 10.3 | 64% | 64% | matched | G04 Excel / Westgrove - Eldorado / Walker BRT (brt) |
| XB33 Denton-Corinth BRT | brt | 9.1 | 100% | 100% | matched | G49 Avenue C / Hickory - Morriss / Olympia BRT (brt) |
| E07 Mansfield-Denton-Carrollton | commuter | 86.6 | 100% | 99% | matched | G72 Henderson / 5th Street - Avenue C / Hickory Rail (commuter) |
| E40 Weatherford Line | commuter | 48.4 | 100% | 100% | matched | G70 Mustang Drive - Russell / Park Rail (commuter) |
| E22 I-30 / FW Blue Line | metro | 82.9 | 82% | 23% | matched | G34 Field / Patterson - Mercantile Drive Rail (commuter) |
| E19 I-20 Crosstown | metro | 72.8 | 53% | 14% | matched | G36 Centreport / Sovereign - Treepoint / Pennsylvania BRT (brt) |
| E17 DNT East | metro | 63.9 | 80% | 56% | matched | G21 Stemmons / Medical District - Dallas / Arapaho Metro (metro) |
| E18 Las Colinas-Mesquite Line | metro | 45.5 | 91% | 33% | matched | G23 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| E26 Legacy Line | metro | 44.7 | 76% | 63% | matched | G21 Stemmons / Medical District - Dallas / Arapaho Metro (metro) |
| XP01 SH-114 Line | metro | 38.9 | 73% | 6% | matched | G14 John W Carpenter / Shorthorn - Pearson / Fawkes BRT (brt) |
| E16 DNT West | metro | 31.2 | 84% | 61% | matched | G44 Noel / Alpha - John Arden / Solon Rail (commuter) |
| F05 FW Berry | metro | 25.4 | 59% | 20% | matched | G73 Henderson / 5th Street - John Arden / Solon Rail (commuter) |
| F01 FW Green | metro | 21.9 | 89% | 20% | matched | G03 Brentwood Stair / Oak Hill - Bellaire / Watercourse BRT (brt) |
| F04 FW Pink | metro | 21.6 | 73% | 57% | matched | G54 Schwartz / Jasper - Sycamore School / Meadow Creek Metro (metro) |
| E14 Red Line | metro | 20.0 | 100% | 0% | matched | G43 Scenic / Sutherland - County Road 365 / McKinney BRT (brt) |
| F06 FW Red | metro | 13.7 | 91% | 0% | matched | G70 Mustang Drive - Russell / Park Rail (commuter) |
| F03 FW Orange | metro | 11.5 | 64% | 37% | matched | G54 Schwartz / Jasper - Sycamore School / Meadow Creek Metro (metro) |
| F07 FW Purple | metro | 7.6 | 80% | 25% | matched | G27 Henderson / 5th Street - Alsbury / Edgehill BRT (brt) |
| E13 Green Line | metro | 3.4 | 100% | 100% | matched | G33 Stemmons / Medical District - Masters / Bruton Metro (metro) |
| E12 Orange Line | metro | 3.1 | 100% | 100% | matched | G33 Stemmons / Medical District - Masters / Bruton Metro (metro) |
| E24 FW Crosstown Loop | brt | 66.3 | 43% | 29% | partly | G03 Brentwood Stair / Oak Hill - Bellaire / Watercourse BRT (brt) |
| XE01 I-35E Express | brt | 50.8 | 38% | 4% | partly | G44 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XB15 Frisco Main-Eldorado BRT | brt | 29.3 | 43% | 43% | partly | G56 Eldorado / Walker - White / Waddill BRT (brt) |
| XB17 Independence Parkway BRT | brt | 28.7 | 39% | 39% | partly | G43 Scenic / Sutherland - County Road 365 / McKinney BRT (brt) |
| XB13 Preston Road BRT | brt | 25.9 | 40% | 17% | partly |  |
| XP02 Coppell-Lewisville BRT | brt | 25.4 | 47% | 47% | partly | G65 Grapevine Mills Circle - Eldorado / Walker BRT (brt) |
| XB34 Shiloh Road BRT | brt | 21.2 | 42% | 40% | partly | G50 Bowser / Belt Line - Alanis / Stone BRT (brt) |
| XB31 DeSoto-Lancaster BRT | brt | 20.7 | 26% | 22% | partly | G51 Highway 67 / Marvin D Love - Highland / Weaver BRT (brt) |
| E01 White Settlement BRT | brt | 20.1 | 47% | 47% | partly | G38 Silver Creek / Las Vegas - Sycamore School / Meadow Creek BRT (brt) |
| XB07 Kiest-Ledbetter BRT | brt | 19.7 | 47% | 38% | partly | G53 LBJ - 52nd Street / Horizon BRT (brt) |
| XB25 Pioneer Parkway BRT | brt | 19.2 | 43% | 41% | partly | G52 Park Row / Susan - Parks / Parkerville BRT (brt) |
| XB20 Denton UNT-TWU BRT | brt | 18.5 | 27% | 18% | partly | G49 Avenue C / Hickory - Morriss / Olympia BRT (brt) |
| XB16 McKinney Lake Forest BRT | brt | 17.6 | 39% | 39% | partly | G43 Scenic / Sutherland - County Road 365 / McKinney BRT (brt) |
| XB11 Park Boulevard BRT | brt | 16.5 | 42% | 42% | partly | G18 Coit / Churchill - Scenic / Sutherland BRT (brt) |
| XB19 Flower Mound-Lewisville BRT | brt | 16.5 | 29% | 29% | partly | G06 Bedford / Barr - Morriss / Olympia BRT (brt) |
| E29 Jefferson Blvd BRT | brt | 11.4 | 42% | 31% | partly | G19 Lombardy / Webb Chapel - Highway 67 / Marvin D Love BRT (brt) |
| E10 TRE | commuter | 120.2 | 42% | 36% | partly | G23 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| E35 Ennis Line | commuter | 54.8 | 33% | 33% | partly | G47 Central / Fall Creek - Dowdy Ferry Road Rail (commuter) |
| E41 Greenville Line | commuter | 54.8 | 21% | 0% | partly | G67 Central / Fall Creek - Market Center / Tubbs BRT (brt) |
| E37 Midlothian Line | commuter | 29.1 | 30% | 7% | partly | G52 Park Row / Susan - Parks / Parkerville BRT (brt) |
| E09 TEXRail | commuter | 19.8 | 46% | 13% | partly | G27 Henderson / 5th Street - Alsbury / Edgehill BRT (brt) |
| E23 SH-360 Line | metro | 72.1 | 47% | 10% | partly | G17 Waverly Drive - Bedford / Barr BRT (brt) |
| XB29 North Fort Worth-Alliance BRT | brt | 21.0 | 8% | 8% | missed |  |
| XB37 Burleson-Crowley BRT | brt | 14.0 | 17% | 17% | missed | G27 Henderson / 5th Street - Alsbury / Edgehill BRT (brt) |
| XB45 Matlock-Mansfield BRT | brt | 12.8 | 5% | 0% | missed |  |
| E32 Gainesville Line | commuter | 107.4 | 9% | 5% | missed |  |
| E31 Bowie Line | commuter | 104.8 | 8% | 6% | missed |  |
| E33 Sherman Line | commuter | 85.4 | 16% | 7% | missed |  |

### Generated lines

| line | mode | km | near hand plan (1 km) | same family | verdict | closest hand-plan line |
|---|---|---|---|---|---|---|
| G01 Greenville / Holly Hill - Excel / Westgrove Metro | metro | 18.8 | 65% | 45% | in hand plan | E26 Legacy Line (metro) |
| G02 John W Carpenter / Shorthorn - Country Club / Las Brisas BRT | brt | 5.5 | 100% | 100% | in hand plan | E21 Beltline Line (brt) |
| G03 Brentwood Stair / Oak Hill - Bellaire / Watercourse BRT | brt | 26.0 | 89% | 47% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G04 Excel / Westgrove - Eldorado / Walker BRT | brt | 28.7 | 78% | 47% | in hand plan | E17 DNT East (metro) |
| G05 Bush Turnpike - Perry Road BRT | brt | 5.6 | 69% | 69% | in hand plan | E21 Beltline Line (brt) |
| G06 Bedford / Barr - Morriss / Olympia BRT | brt | 28.6 | 50% | 34% | partly | XP01 SH-114 Line (metro) |
| G07 Bush Turnpike - Grapevine Mills Circle BRT | brt | 16.4 | 87% | 27% | in hand plan | XP01 SH-114 Line (metro) |
| G08 Grauwyler / O'Connor - Southwestern / Douglas BRT | brt | 20.2 | 66% | 53% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G09 Dallas / Arapaho - Greenville Avenue BRT | brt | 30.3 | 79% | 64% | in hand plan | E14 Red Line (metro) |
| G10 Bush Turnpike - Park Row / Susan BRT | brt | 32.8 | 60% | 32% | in hand plan | XP01 SH-114 Line (metro) |
| G11 Mustang Drive - Alsbury / Edgehill Rail | commuter | 51.6 | 51% | 34% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |
| G12 Greenville / Holly Hill - Masters / Bruton BRT | brt | 23.1 | 79% | 46% | in hand plan | E18 Las Colinas-Mesquite Line (metro) |
| G13 Matilda / University - Grauwyler / O'Connor BRT | brt | 24.1 | 70% | 27% | in hand plan | XP05 Stemmons-Brookhollow BRT (brt) |
| G14 John W Carpenter / Shorthorn - Pearson / Fawkes BRT | brt | 24.3 | 59% | 10% | in hand plan | XP01 SH-114 Line (metro) |
| G15 Communications / Legacy - Mars / Firewheel BRT | brt | 33.7 | 56% | 39% | in hand plan | E17 DNT East (metro) |
| G16 Mercantile Drive - Pearson / Fawkes BRT | brt | 25.1 | 50% | 45% | partly | XB41 Watauga-Keller BRT (brt) |
| G17 Waverly Drive - Bedford / Barr BRT | brt | 22.6 | 100% | 89% | in hand plan | E23 SH-360 Line (metro) |
| G18 Coit / Churchill - Scenic / Sutherland BRT | brt | 21.6 | 84% | 77% | in hand plan | XB12 Coit Road BRT (brt) |
| G19 Lombardy / Webb Chapel - Highway 67 / Marvin D Love BRT | brt | 31.1 | 90% | 68% | in hand plan | XP05 Stemmons-Brookhollow BRT (brt) |
| G20 Adleta / Skillman - Avenue C / Hickory Rail | commuter | 59.9 | 42% | 8% | partly | XB35 Lewisville Main Street BRT (brt) |
| G21 Stemmons / Medical District - Dallas / Arapaho Metro | metro | 20.2 | 100% | 100% | in hand plan | E26 Legacy Line (metro) |
| G22 Communications / Legacy - Scenic / Sutherland Metro | metro | 8.6 | 68% | 25% | in hand plan | XB14 Spring Creek-Legacy BRT (brt) |
| G23 Lake Carolyn / O'Connor - US-80 / Pinson Rail | commuter | 56.8 | 85% | 66% | in hand plan | E10 TRE (commuter) |
| G24 Bush Turnpike - Cockrell Hill / Falls BRT | brt | 28.9 | 33% | 13% | partly | XP01 SH-114 Line (metro) |
| G25 Dallas / Arapaho - Masters / Bruton Metro | metro | 37.6 | 80% | 38% | in hand plan | XE02 Mesquite Express (brt) |
| G26 Cooper / Mitchell - Matlock / Turner Warnell BRT | brt | 12.0 | 95% | 95% | in hand plan | XB24 Cooper Street BRT (brt) |
| G27 Henderson / 5th Street - Alsbury / Edgehill BRT | brt | 26.2 | 52% | 43% | in hand plan | E09 TEXRail (commuter) |
| G28 Field / Patterson - LBJ Metro | metro | 22.0 | 72% | 35% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G29 Bush Turnpike - Bowser / Belt Line Metro | metro | 26.6 | 65% | 27% | in hand plan | XP05 Stemmons-Brookhollow BRT (brt) |
| G30 Gilford / Denton - Hill / SH-161 BRT | brt | 28.2 | 40% | 26% | partly | E18 Las Colinas-Mesquite Line (metro) |
| G31 Centreport / Sovereign - Mercantile Drive BRT | brt | 24.9 | 83% | 80% | in hand plan | XB21 Hurst-Euless-Bedford BRT (brt) |
| G32 Central / Fall Creek - Lukenbach / Rambling BRT | brt | 28.7 | 52% | 46% | in hand plan | XB17 Independence Parkway BRT (brt) |
| G33 Stemmons / Medical District - Masters / Bruton Metro | metro | 23.1 | 72% | 58% | in hand plan | E16 DNT West (metro) |
| G34 Field / Patterson - Mercantile Drive Rail | commuter | 59.6 | 79% | 19% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G35 Adleta / Skillman - Mars / Firewheel BRT | brt | 13.8 | 54% | 54% | in hand plan | XB09 Garland Broadway BRT (brt) |
| G36 Centreport / Sovereign - Treepoint / Pennsylvania BRT | brt | 32.9 | 52% | 18% | in hand plan | E19 I-20 Crosstown (metro) |
| G37 Mustang Drive - Centreport / Sovereign Metro | metro | 11.5 | 32% | 17% | partly | E23 SH-360 Line (metro) |
| G38 Silver Creek / Las Vegas - Sycamore School / Meadow Creek BRT | brt | 22.2 | 72% | 54% | in hand plan | E01 White Settlement BRT (brt) |
| G39 F / Executive - LBJ BRT | brt | 24.8 | 29% | 29% | partly | XB09 Garland Broadway BRT (brt) |
| G40 Lombardy / Webb Chapel - Forest / Cromwell BRT | brt | 6.3 | 45% | 9% | partly | E16 DNT West (metro) |
| G41 Fountain / Westpark - Cooper / Mitchell Metro | metro | 10.3 | 79% | 49% | in hand plan | XB24 Cooper Street BRT (brt) |
| G42 Highland / Vista Ridge Mall - Grauwyler / O'Connor BRT | brt | 21.4 | 70% | 54% | in hand plan | E21 Beltline Line (brt) |
| G43 Scenic / Sutherland - County Road 365 / McKinney BRT | brt | 32.6 | 69% | 46% | in hand plan | E14 Red Line (metro) |
| G44 Noel / Alpha - John Arden / Solon Rail | commuter | 85.2 | 64% | 13% | in hand plan | XE01 I-35E Express (brt) |
| G45 Excel / Westgrove - Lukenbach / Rambling Metro | metro | 29.0 | 89% | 44% | in hand plan | E17 DNT East (metro) |
| G46 Dallas / Arapaho - Grapevine Mills Circle BRT | brt | 27.6 | 78% | 58% | in hand plan | E21 Beltline Line (brt) |
| G47 Central / Fall Creek - Dowdy Ferry Road Rail | commuter | 40.7 | 80% | 41% | in hand plan | E35 Ennis Line (commuter) |
| G48 Fountain / Westpark - Highland / Weaver BRT | brt | 30.4 | 75% | 65% | in hand plan | E21 Beltline Line (brt) |
| G49 Avenue C / Hickory - Morriss / Olympia BRT | brt | 28.7 | 51% | 49% | in hand plan | XB33 Denton-Corinth BRT (brt) |
| G50 Bowser / Belt Line - Alanis / Stone BRT | brt | 24.4 | 72% | 72% | in hand plan | E21 Beltline Line (brt) |
| G51 Highway 67 / Marvin D Love - Highland / Weaver BRT | brt | 9.1 | 57% | 57% | in hand plan | XB31 DeSoto-Lancaster BRT (brt) |
| G52 Park Row / Susan - Parks / Parkerville BRT | brt | 34.2 | 55% | 42% | in hand plan | XB25 Pioneer Parkway BRT (brt) |
| G53 LBJ - 52nd Street / Horizon BRT | brt | 30.9 | 90% | 69% | in hand plan | XB03 Illinois-Lake June BRT (brt) |
| G54 Schwartz / Jasper - Sycamore School / Meadow Creek Metro | metro | 28.0 | 87% | 59% | in hand plan | F04 FW Pink (metro) |
| G55 Forest / Cromwell - Perry Road Metro | metro | 7.5 | 28% | 5% | partly | XB32 Josey Lane BRT (brt) |
| G56 Eldorado / Walker - White / Waddill BRT | brt | 30.1 | 79% | 73% | in hand plan | XB40 McKinney Virginia Parkway BRT (brt) |
| G57 Schwartz / Jasper - Silver Creek / Las Vegas BRT | brt | 15.9 | 69% | 52% | in hand plan | E04 Jacksboro BRT (brt) |
| G58 Centreport / Sovereign - Riverside Drive BRT | brt | 34.0 | 96% | 91% | in hand plan | XB38 Mid-Cities Boulevard BRT (brt) |
| G59 Greenville Avenue - Lukenbach / Rambling BRT | brt | 17.3 | 84% | 66% | in hand plan | XB17 Independence Parkway BRT (brt) |
| G60 Park Row / Susan - Cooper / Mitchell BRT | brt | 5.8 | 77% | 77% | in hand plan | XB26 Collins-Center BRT (brt) |
| G61 Highway 67 / Marvin D Love - 52nd Street / Horizon BRT | brt | 12.3 | 76% | 67% | in hand plan | E19 I-20 Crosstown (metro) |
| G62 Lombardy / Webb Chapel - Bowser / Belt Line Metro | metro | 23.8 | 68% | 18% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G63 Mercantile Drive - Cooper / Mitchell BRT | brt | 29.6 | 73% | 45% | in hand plan | F01 FW Green (metro) |
| G64 Bedford / Barr - Pearson / Fawkes BRT | brt | 17.9 | 40% | 40% | partly | XB21 Hurst-Euless-Bedford BRT (brt) |
| G65 Grapevine Mills Circle - Eldorado / Walker BRT | brt | 32.7 | 48% | 48% | partly | XP02 Coppell-Lewisville BRT (brt) |
| G66 Adleta / Skillman - US-80 / Pinson BRT | brt | 32.3 | 63% | 51% | in hand plan | XB09 Garland Broadway BRT (brt) |
| G67 Central / Fall Creek - Market Center / Tubbs BRT | brt | 34.2 | 29% | 6% | partly | E41 Greenville Line (commuter) |
| G68 Matilda / University - Market Center / Tubbs BRT | brt | 33.8 | 64% | 41% | in hand plan | E41 Greenville Line (commuter) |
| G69 Cooper / Mitchell - Sycamore School / Meadow Creek BRT | brt | 34.6 | 79% | 37% | in hand plan | E19 I-20 Crosstown (metro) |
| G70 Mustang Drive - Russell / Park Rail | commuter | 79.7 | 85% | 78% | in hand plan | E40 Weatherford Line (commuter) |
| G71 Matlock / Turner Warnell - Treepoint / Pennsylvania BRT | brt | 11.3 | 45% | 29% | partly | XB24 Cooper Street BRT (brt) |
| G72 Henderson / 5th Street - Avenue C / Hickory Rail | commuter | 56.1 | 100% | 100% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |
| G73 Henderson / 5th Street - John Arden / Solon Rail | commuter | 64.3 | 57% | 52% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |

