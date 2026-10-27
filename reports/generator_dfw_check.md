# Generator cross-check on DFW

`python -m metro check-dfw` runs the metro-agnostic generator (`python -m metro generate dfw`, `metro/generate.py`) on DFW's inputs, ignoring the hand plan, with the hand plan's own new capital as its budget, and compares the result with the hand-built 2 million plan (`network/` + `scenarios/two_million/`). Generated network: `generated/dfw/` (its `report.md` lists the centers, every candidate and why it was chosen or rejected; `preview.png` is a map). Line-by-line matching: `generated/dfw/compare_lines.csv`.

## Totals

| | today | generated | 2M hand plan |
|---|---|---|---|
| metro / light rail km (new) | - | 212 | 580 |
| BRT km (new) | - | 384 | 1,135 |
| regional rail km (new) | - | 574 | 711 |
| streetcar km (new) | - | 0 | 0 |
| new lines | - | 36 | 76 (incl. extended existing lines) |
| capital, 2025 $ (dfwt costing) | - | $75.8B | $169.0B |
| residents within 800 m of a station | 3.6% | 16.1% | 30.7% |
| jobs within 800 m of a station | 15.8% | 41.5% | 56.3% |
| daily transit trips, today's land use, all lines open | 80,553 | 198,487 | 315,143 |
| daily rail + BRT boardings, same | 82,965 | 239,154 | 422,869 |
| jobs within 45 min, average resident | 21,261 | 64,500 | 69,091 |
| new daily trips per $M of capital | - | 1.56 | 1.39 |

Model runs: dfwt's demand model (gravity flows, the config.json logit calibrated to DFW's 2025 rail boardings, feeder buses) on 2026 land use with no station-area growth, every line open; the 2M plan's own policy overlay (`scenarios/two_million/config.json`: parking, access and land-use levers) is NOT applied, so both networks face the same assumptions. The 2M plan's published 2100 numbers are far higher because they include 75 years of growth, transit-oriented development and those policies.

## Which corridors match

A hand-plan line is **matched** when at least half of its new track lies within 1 km of generated track, **partly** at 20-50%. Of 76 hand-plan lines with new track: 28 matched (820 km), 21 partly (800 km), 27 missed (807 km). Of 36 generated lines: 30 lie in hand-plan corridors, 6 partly, 0 beside today's lines, 0 are corridors the hand plan doesn't have.

| hand-plan mode | matched km | partly km | missed km |
|---|---|---|---|
| brt | 226 | 523 | 385 |
| commuter | 135 | 175 | 401 |
| metro | 458 | 102 | 20 |

### Hand-plan lines

| line | mode | new km | share near generated | verdict | closest generated line |
|---|---|---|---|---|---|
| XP05 Stemmons-Brookhollow BRT | brt | 28.3 | 84% | matched | G21 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XB28 Beach Street-Keller BRT | brt | 23.8 | 65% | matched | G35 Henderson / 5th Street - Avenue C / Hickory Rail (commuter) |
| E02 Riverside-Forest Hill BRT | brt | 21.5 | 61% | matched | G36 Henderson / 5th Street - John Arden / Solon Rail (commuter) |
| XB01 Northwest Highway BRT | brt | 20.3 | 64% | matched | G10 Country Club / Las Brisas - Southwestern / Douglas BRT (brt) |
| XB25 Pioneer Parkway BRT | brt | 19.2 | 53% | matched | G27 Henderson / 5th Street - Waverly Drive BRT (brt) |
| XB24 Cooper Street BRT | brt | 16.4 | 58% | matched | G07 Waverly Drive - Bedford / Barr BRT (brt) |
| XB26 Collins-Center BRT | brt | 16.3 | 83% | matched | G07 Waverly Drive - Bedford / Barr BRT (brt) |
| XB21 Hurst-Euless-Bedford BRT | brt | 15.8 | 100% | matched | G19 Centreport / Sovereign - Mercantile Drive BRT (brt) |
| E04 Jacksboro BRT | brt | 14.8 | 70% | matched | G29 Schwartz / Jasper - Silver Creek / Las Vegas BRT (brt) |
| E28 Forest Lane BRT | brt | 14.7 | 67% | matched | G15 Bush Turnpike - Adleta / Skillman Metro (metro) |
| E27 Ross Avenue BRT | brt | 13.2 | 94% | matched | G12 Bowser / Belt Line - Cockrell Hill / Falls Metro (metro) |
| XB35 Lewisville Main Street BRT | brt | 11.6 | 60% | matched | G09 Adleta / Skillman - Avenue C / Hickory Rail (commuter) |
| XB42 Denton Tap BRT | brt | 10.5 | 69% | matched | G01 Highland / Vista Ridge Mall - Country Club / Las Brisas BRT (brt) |
| E07 Mansfield-Denton-Carrollton | commuter | 86.6 | 99% | matched | G35 Henderson / 5th Street - Avenue C / Hickory Rail (commuter) |
| E40 Weatherford Line | commuter | 48.4 | 100% | matched | G32 Lake Carolyn / O'Connor - Russell / Park Rail (commuter) |
| E22 I-30 / FW Blue Line | metro | 82.9 | 86% | matched | G16 Henderson / 5th Street - Gilford / Denton Rail (commuter) |
| E23 SH-360 Line | metro | 72.1 | 50% | matched | G07 Waverly Drive - Bedford / Barr BRT (brt) |
| E17 DNT East | metro | 63.9 | 56% | matched | G20 Communications / Legacy - Southwestern / Douglas Metro (metro) |
| E18 Las Colinas-Mesquite Line | metro | 45.5 | 78% | matched | G14 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| E26 Legacy Line | metro | 44.7 | 60% | matched | G20 Communications / Legacy - Southwestern / Douglas Metro (metro) |
| XP01 SH-114 Line | metro | 38.9 | 65% | matched | G26 Mustang Drive - Perry Road Metro (metro) |
| E16 DNT West | metro | 31.2 | 78% | matched | G21 Noel / Alpha - John Arden / Solon Rail (commuter) |
| F05 FW Berry | metro | 25.4 | 58% | matched | G36 Henderson / 5th Street - John Arden / Solon Rail (commuter) |
| F01 FW Green | metro | 21.9 | 78% | matched | G06 Henderson / 5th Street - Silver Creek / Las Vegas BRT (brt) |
| F06 FW Red | metro | 13.7 | 73% | matched | G32 Lake Carolyn / O'Connor - Russell / Park Rail (commuter) |
| F03 FW Orange | metro | 11.5 | 56% | matched | G04 Mustang Drive - Alsbury / Edgehill Rail (commuter) |
| E13 Green Line | metro | 3.4 | 89% | matched | G12 Bowser / Belt Line - Cockrell Hill / Falls Metro (metro) |
| E12 Orange Line | metro | 3.1 | 100% | matched | G12 Bowser / Belt Line - Cockrell Hill / Falls Metro (metro) |
| E21 Beltline Line | brt | 147.7 | 27% | partly |  |
| E24 FW Crosstown Loop | brt | 66.3 | 31% | partly |  |
| XE01 I-35E Express | brt | 50.8 | 34% | partly | G21 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XB03 Illinois-Lake June BRT | brt | 35.6 | 34% | partly | G21 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XE02 Mesquite Express | brt | 26.1 | 27% | partly | G14 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| XP02 Coppell-Lewisville BRT | brt | 25.4 | 46% | partly | G13 Highland / Vista Ridge Mall - Bedford / Barr BRT (brt) |
| XB12 Coit Road BRT | brt | 24.5 | 31% | partly | G24 Dallas / Arapaho - Central / Fall Creek Metro (metro) |
| E01 White Settlement BRT | brt | 20.1 | 46% | partly | G06 Henderson / 5th Street - Silver Creek / Las Vegas BRT (brt) |
| XB32 Josey Lane BRT | brt | 19.1 | 32% | partly | G21 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XB38 Mid-Cities Boulevard BRT | brt | 17.5 | 36% | partly | G04 Mustang Drive - Alsbury / Edgehill Rail (commuter) |
| XB27 Hulen-Altamesa BRT | brt | 16.9 | 23% | partly | G04 Mustang Drive - Alsbury / Edgehill Rail (commuter) |
| XP06 Dallas Parkway BRT | brt | 16.8 | 27% | partly | G20 Communications / Legacy - Southwestern / Douglas Metro (metro) |
| XB41 Watauga-Keller BRT | brt | 15.7 | 25% | partly | G19 Centreport / Sovereign - Mercantile Drive BRT (brt) |
| XB02 Buckner Boulevard BRT | brt | 15.5 | 29% | partly | G23 Central / Fall Creek - Dowdy Ferry Road Rail (commuter) |
| XB06 Hampton-Westmoreland BRT | brt | 13.8 | 26% | partly | G12 Bowser / Belt Line - Cockrell Hill / Falls Metro (metro) |
| E29 Jefferson Blvd BRT | brt | 11.4 | 42% | partly | G12 Bowser / Belt Line - Cockrell Hill / Falls Metro (metro) |
| E10 TRE | commuter | 120.2 | 36% | partly | G14 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| E35 Ennis Line | commuter | 54.8 | 33% | partly | G23 Central / Fall Creek - Dowdy Ferry Road Rail (commuter) |
| E19 I-20 Crosstown | metro | 72.8 | 24% | partly | G12 Bowser / Belt Line - Cockrell Hill / Falls Metro (metro) |
| F04 FW Pink | metro | 21.6 | 45% | partly | G36 Henderson / 5th Street - John Arden / Solon Rail (commuter) |
| F07 FW Purple | metro | 7.6 | 45% | partly | G32 Lake Carolyn / O'Connor - Russell / Park Rail (commuter) |
| E38 SH-121 BRT | brt | 31.1 | 6% | missed |  |
| XB15 Frisco Main-Eldorado BRT | brt | 29.3 | 0% | missed |  |
| XB17 Independence Parkway BRT | brt | 28.7 | 7% | missed |  |
| XB13 Preston Road BRT | brt | 25.9 | 19% | missed |  |
| XB34 Shiloh Road BRT | brt | 21.2 | 13% | missed | G23 Central / Fall Creek - Dowdy Ferry Road Rail (commuter) |
| XB29 North Fort Worth-Alliance BRT | brt | 21.0 | 8% | missed |  |
| XB31 DeSoto-Lancaster BRT | brt | 20.7 | 4% | missed |  |
| XB40 McKinney Virginia Parkway BRT | brt | 20.1 | 0% | missed |  |
| XB07 Kiest-Ledbetter BRT | brt | 19.7 | 19% | missed | G21 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XB09 Garland Broadway BRT | brt | 19.2 | 0% | missed |  |
| XB20 Denton UNT-TWU BRT | brt | 18.5 | 16% | missed |  |
| XB14 Spring Creek-Legacy BRT | brt | 18.4 | 19% | missed | G20 Communications / Legacy - Southwestern / Douglas Metro (metro) |
| XB16 McKinney Lake Forest BRT | brt | 17.6 | 0% | missed |  |
| XB11 Park Boulevard BRT | brt | 16.5 | 12% | missed | G20 Communications / Legacy - Southwestern / Douglas Metro (metro) |
| XB19 Flower Mound-Lewisville BRT | brt | 16.5 | 0% | missed |  |
| XB44 Sachse-Wylie BRT | brt | 14.6 | 0% | missed |  |
| XB37 Burleson-Crowley BRT | brt | 14.0 | 0% | missed |  |
| XB45 Matlock-Mansfield BRT | brt | 12.8 | 5% | missed |  |
| XB39 West Frisco BRT | brt | 10.3 | 0% | missed |  |
| XB33 Denton-Corinth BRT | brt | 9.1 | 17% | missed | G35 Henderson / 5th Street - Avenue C / Hickory Rail (commuter) |
| E32 Gainesville Line | commuter | 107.4 | 6% | missed |  |
| E31 Bowie Line | commuter | 104.8 | 7% | missed |  |
| E33 Sherman Line | commuter | 85.4 | 10% | missed |  |
| E41 Greenville Line | commuter | 54.8 | 0% | missed |  |
| E37 Midlothian Line | commuter | 29.1 | 7% | missed |  |
| E09 TEXRail | commuter | 19.8 | 13% | missed | G32 Lake Carolyn / O'Connor - Russell / Park Rail (commuter) |
| E14 Red Line | metro | 20.0 | 0% | missed |  |

### Generated lines

| line | mode | km | share near hand plan | verdict | closest hand-plan line |
|---|---|---|---|---|---|
| G01 Highland / Vista Ridge Mall - Country Club / Las Brisas BRT | brt | 18.1 | 100% | in hand plan | E21 Beltline Line (brt) |
| G02 Excel / Westgrove - Matilda / University Metro | metro | 23.4 | 65% | in hand plan | E26 Legacy Line (metro) |
| G03 Matilda / University - Grauwyler / O'Connor BRT | brt | 25.6 | 71% | in hand plan | XP05 Stemmons-Brookhollow BRT (brt) |
| G04 Mustang Drive - Alsbury / Edgehill Rail | commuter | 51.6 | 51% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |
| G05 Lake Carolyn / O'Connor - Park Row / Susan BRT | brt | 28.7 | 48% | partly | E23 SH-360 Line (metro) |
| G06 Henderson / 5th Street - Silver Creek / Las Vegas BRT | brt | 16.1 | 98% | in hand plan | F01 FW Green (metro) |
| G07 Waverly Drive - Bedford / Barr BRT | brt | 23.0 | 100% | in hand plan | E23 SH-360 Line (metro) |
| G08 Coit / McCallum - F / Executive BRT | brt | 8.2 | 62% | in hand plan | XB17 Independence Parkway BRT (brt) |
| G09 Adleta / Skillman - Avenue C / Hickory Rail | commuter | 60.4 | 41% | partly | XB35 Lewisville Main Street BRT (brt) |
| G10 Country Club / Las Brisas - Southwestern / Douglas BRT | brt | 23.5 | 76% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G11 Country Club / Las Brisas - Cooper / Mitchell BRT | brt | 28.6 | 52% | in hand plan | E23 SH-360 Line (metro) |
| G12 Bowser / Belt Line - Cockrell Hill / Falls Metro | metro | 37.3 | 68% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G13 Highland / Vista Ridge Mall - Bedford / Barr BRT | brt | 28.2 | 61% | in hand plan | XP02 Coppell-Lewisville BRT (brt) |
| G14 Lake Carolyn / O'Connor - US-80 / Pinson Rail | commuter | 56.8 | 85% | in hand plan | E10 TRE (commuter) |
| G15 Bush Turnpike - Adleta / Skillman Metro | metro | 28.9 | 68% | in hand plan | E28 Forest Lane BRT (brt) |
| G16 Henderson / 5th Street - Gilford / Denton Rail | commuter | 66.4 | 76% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G17 Waverly Drive - Hill / SH-161 BRT | brt | 16.3 | 77% | in hand plan | XB26 Collins-Center BRT (brt) |
| G18 Gilford / Denton - Highland / Vista Ridge Mall BRT | brt | 31.8 | 52% | in hand plan | E33 Sherman Line (commuter) |
| G19 Centreport / Sovereign - Mercantile Drive BRT | brt | 25.8 | 84% | in hand plan | XB21 Hurst-Euless-Bedford BRT (brt) |
| G20 Communications / Legacy - Southwestern / Douglas Metro | metro | 32.5 | 91% | in hand plan | E17 DNT East (metro) |
| G21 Noel / Alpha - John Arden / Solon Rail | commuter | 85.4 | 64% | in hand plan | XE01 I-35E Express (brt) |
| G22 Fountain / Westpark - Cooper / Mitchell Metro | metro | 10.9 | 77% | in hand plan | XB24 Cooper Street BRT (brt) |
| G23 Central / Fall Creek - Dowdy Ferry Road Rail | commuter | 40.9 | 80% | in hand plan | E35 Ennis Line (commuter) |
| G24 Dallas / Arapaho - Central / Fall Creek Metro | metro | 15.4 | 63% | in hand plan | XB12 Coit Road BRT (brt) |
| G25 Stemmons / Medical District - Greenville / Holly Hill Metro | metro | 15.1 | 100% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G26 Mustang Drive - Perry Road Metro | metro | 26.0 | 79% | in hand plan | XP01 SH-114 Line (metro) |
| G27 Henderson / 5th Street - Waverly Drive BRT | brt | 24.6 | 94% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G28 Bush Turnpike - Hill / SH-161 BRT | brt | 30.3 | 30% | partly | XP01 SH-114 Line (metro) |
| G29 Schwartz / Jasper - Silver Creek / Las Vegas BRT | brt | 17.4 | 67% | in hand plan | E04 Jacksboro BRT (brt) |
| G30 Mustang Drive - Centreport / Sovereign Metro | metro | 12.9 | 39% | partly | XB21 Hurst-Euless-Bedford BRT (brt) |
| G31 Country Club / Las Brisas - Cockrell Hill / Falls BRT | brt | 23.9 | 33% | partly | E22 I-30 / FW Blue Line (metro) |
| G32 Lake Carolyn / O'Connor - Russell / Park Rail | commuter | 92.3 | 73% | in hand plan | E40 Weatherford Line (commuter) |
| G33 Waverly Drive - Park Row / Susan Metro | metro | 10.1 | 56% | in hand plan | E19 I-20 Crosstown (metro) |
| G34 Bush Turnpike - Highland / Vista Ridge Mall BRT | brt | 13.5 | 48% | partly | E21 Beltline Line (brt) |
| G35 Henderson / 5th Street - Avenue C / Hickory Rail | commuter | 56.1 | 100% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |
| G36 Henderson / 5th Street - John Arden / Solon Rail | commuter | 64.3 | 57% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |

