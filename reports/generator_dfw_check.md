# Generator cross-check on DFW

`python -m metro check-dfw` runs the metro-agnostic generator (`python -m metro generate dfw`, `metro/generate.py`) on DFW's inputs, ignoring the hand plan, with the hand plan's own new capital as its budget, and compares the result with the hand-built 2 million plan (`network/` + `scenarios/two_million/`). Generated network: `generated/dfw/` (its `report.md` lists the centers, every candidate and why it was chosen or rejected; `preview.png` is a map). Line-by-line matching: `generated/dfw/compare_lines.csv`.

## Totals

| | today | generated | 2M hand plan |
|---|---|---|---|
| metro / light rail km (new) | - | 617 | 580 |
| BRT km (new) | - | 1,822 | 1,154 |
| regional rail km (new) | - | 779 | 711 |
| streetcar km (new) | - | 0 | 0 |
| new lines | - | 96 | 77 (incl. extended existing lines) |
| capital, 2025 $ (dfwt costing) | - | $177.7B | $169.0B |
| residents within 800 m of a station | 3.4% | 33.9% | 30.6% |
| jobs within 800 m of a station | 14.8% | 60.0% | 56.2% |
| daily transit trips, today's land use, all lines open | 78,990 | 337,855 | 321,904 |
| daily rail + BRT boardings, same | 81,965 | 439,309 | 425,771 |
| jobs within 45 min, average resident | 27,725 | 136,004 | 123,046 |
| new daily trips per $M of capital | - | 1.46 | 1.44 |

Model runs: dfwt's demand model (gravity flows, the config.json logit calibrated to DFW's 2025 rail boardings, feeder buses) on 2026 land use with no station-area growth, every line open; the 2M plan's own policy overlay (`scenarios/two_million/config.json`: parking, access and land-use levers) is NOT applied, so both networks face the same assumptions. The 2M plan's published 2100 numbers are far higher because they include 75 years of growth, transit-oriented development and those policies.

## Reading

*(Hand-written from the run of 2026-11-12; `python -m metro check-dfw` regenerates every number on this
page except this section, which it copies from `metro/compare_notes.md`.)*

This run is the sketch greedy (the generator's selection to the budget), without the line planner's
full-model search or the crowding check, which need the full model. It includes the generator's
November changes that apply to the sketch: metro tunnels only within 0.8 km of downtown, elevated to
1.5 km and at grade beyond (`candidates.hop_grade`), and terminal costs where a line ends downtown.

**Outcomes: as much value per dollar as the hand plan, and a little more of it.** Given the 2M plan's
$169B, the generator spends $167.7B at its own costing ($177.7B at dfwt's costing, the column above). It reaches more residents (33.9% against 30.6% within 800 m of a
station) and jobs (60% against 56%), more jobs in 45 minutes for the average resident (136k against
123k), and 5% more trips than the hand plan on today's land use (338k against 322k), so about the same
trips per $M (1.46 against 1.44). Built from nothing but zones, roads and rail, it produces a network
the DFW model values as highly as the hand plan. In October's run, before the cheaper grades and the router's changes, it found only
$116B worth building and 73% of the hand plan's added trips.

**Where it agrees.** The regional skeleton is the same, and now the mode mostly is too: 617 km of
metro against the hand plan's 580 (October: 267). Every hand-plan metro line has generated track
within 1 km along at least half of it but FW Berry (35%): 555 of its 580 km. The Dallas North Tollway
and Legacy corridors, I-30 between the downtowns, Mesquite, Fort Worth's Pink line, and most of the
Beltline, Coit Road and arterial BRT match. Of 77 hand lines with new track, 56 match, 15 partly, 6 are
missed; of 96 generated lines none runs where the hand plan has nothing.

**Where it differs.** BRT: 1,822 km against 1,154. The generator still prefers many cheap BRT lines
(its sketch values single lines, so trips needing a transfer count only in the model run), and it
runs BRT where the hand plan has metro in Fort Worth (Green, Orange, Purple are matched by place, not
by mode: 21-44% near generated rail transit). Fort Worth's density still gives it few centers.

**What it misses.** The long regional rail lines to Bowie, Gainesville and Sherman (300 km): those
towns lie outside the nine counties the zones cover, so the generator never sees them. The outer
branches to Ennis, Midlothian and Greenville, and Mansfield-Denton-Carrollton and TEXRail, only partly.
Three BRT lines on the edges: White Settlement, North Fort Worth-Alliance and Matlock-Mansfield.

**How much of the overlap is chance.** The hand plan blankets urban DFW: 68% of residents of
urban-density zones live within 1 km of its new track (41% within 500 m). Generated track lies within
1 km of hand track 69% of the time, about chance; within 500 m 51% against 41%. So line-by-line
"matched" verdicts below overstate agreement: both networks cover the same dense places (which is
what the coverage and ridership numbers show), but the generator's exact streets and freeways are
its own. The corridor tables are for inspecting individual lines, not a score.

**Known weaknesses this shows.** (1) Today's land use only: the generator sees none of the growth
the hand plan builds for. (2) Single-line sketch values favour BRT over trunks; the line planner
on the full model is the fix and isn't in this run. (3) Center names are the nearest cross streets, so
line names read oddly. (4) Routed geometry is a corridor, not a design alignment (CURVE_RADIUS
warnings; `python -m dfwt align` would fit it).

## Which corridors match

Share of each network's new track lying within 1 km (500 m) of the other's, length-weighted: hand plan near generated 57% (43%), generated near hand plan 69% (51%); counting only a line of the same family (rail transit / BRT / regional rail): hand plan 41%, generated 44%. Chance level: 51% of the region's residents live within 1 km of the hand plan's new track (27% within 500 m), 68% (41%) of those in urban-density zones; a corridor drawn at random through populated (urban) places would lie that close about that often, so only the excess over these numbers is agreement.

A hand-plan line is **matched** when at least half of its new track lies within 1 km of generated track (any mode), **partly** at 20-50%. Of 77 hand-plan lines with new track: 56 matched (1,618 km), 15 partly (476 km), 6 missed (352 km). Of 96 generated lines: 84 lie in hand-plan corridors (2,864 km), 12 partly (354 km), 0 are corridors the hand plan doesn't have (0 km).

| hand-plan mode | km | matched km | partly km | missed km | km near generated track of the same family |
|---|---|---|---|---|---|
| brt | 1,154 | 895 | 206 | 54 | 587 |
| commuter | 711 | 169 | 245 | 298 | 172 |
| metro | 580 | 555 | 25 | 0 | 239 |

### Hand-plan lines

| line | mode | new km | near generated (1 km) | same family | verdict | closest generated line |
|---|---|---|---|---|---|---|
| E21 Beltline Line | brt | 147.7 | 63% | 50% | matched | G44 Cooper / Mitchell - Highland / Weaver BRT (brt) |
| E24 FW Crosstown Loop | brt | 66.3 | 54% | 47% | matched | G93 Bedford / Barr - Treepoint / Pennsylvania BRT (brt) |
| XB03 Illinois-Lake June BRT | brt | 35.6 | 94% | 77% | matched | G77 Masters / Bruton - Highway 67 / Marvin D Love BRT (brt) |
| E38 SH-121 BRT | brt | 30.1 | 61% | 55% | matched | G11 Dallas / Arapaho - Lukenbach / Rambling BRT (brt) |
| XB17 Independence Parkway BRT | brt | 28.7 | 60% | 60% | matched | G26 Scenic / Sutherland - Mars / Firewheel BRT (brt) |
| XP05 Stemmons-Brookhollow BRT | brt | 28.3 | 84% | 65% | matched | G51 Grauwyler / O'Connor - Masters / Bruton Metro (metro) |
| XE02 Mesquite Express | brt | 26.1 | 70% | 37% | matched | G35 Excel / Westgrove - Masters / Bruton Metro (metro) |
| XP02 Coppell-Lewisville BRT | brt | 24.8 | 78% | 63% | matched | G48 Greenville / Holly Hill - Morriss / Olympia Metro (metro) |
| XB12 Coit Road BRT | brt | 24.5 | 81% | 75% | matched | G40 Coit / Churchill - Scenic / Sutherland BRT (brt) |
| XB28 Beach Street-Keller BRT | brt | 23.8 | 52% | 43% | matched | G39 Riverside Drive - Brentwood Stair / Oak Hill BRT (brt) |
| XE03 McKinney Express | brt | 22.3 | 90% | 90% | matched | G47 Scenic / Sutherland - County Road 365 / McKinney BRT (brt) |
| XB34 Shiloh Road BRT | brt | 21.2 | 57% | 50% | matched | G71 Central / Fall Creek - Masters / Bruton BRT (brt) |
| E02 Riverside-Forest Hill BRT | brt | 20.5 | 50% | 38% | matched | G75 Sycamore School / Meadow Creek - Matlock / Turner Warnell BRT (brt) |
| XB01 Northwest Highway BRT | brt | 20.3 | 87% | 71% | matched | G19 John W Carpenter / Shorthorn - Greenville / Holly Hill BRT (brt) |
| XB40 McKinney Virginia Parkway BRT | brt | 20.1 | 87% | 87% | matched | G89 Eldorado / Walker - White / Waddill BRT (brt) |
| XB07 Kiest-Ledbetter BRT | brt | 19.7 | 71% | 71% | matched | G69 Matilda / University - Dowdy Ferry Road BRT (brt) |
| XB09 Garland Broadway BRT | brt | 19.2 | 91% | 87% | matched | G87 Adleta / Skillman - US-80 / Pinson BRT (brt) |
| XB25 Pioneer Parkway BRT | brt | 19.2 | 61% | 61% | matched | G66 Waverly Drive - Highway 67 / Marvin D Love BRT (brt) |
| XB32 Josey Lane BRT | brt | 19.1 | 60% | 47% | matched | G81 Highland / Vista Ridge Mall - Eldorado / Walker BRT (brt) |
| XB14 Spring Creek-Legacy BRT | brt | 18.4 | 63% | 57% | matched | G64 Forest / Cromwell - Eldorado / Walker Metro (metro) |
| XB38 Mid-Cities Boulevard BRT | brt | 17.5 | 65% | 49% | matched | G54 Bedford / Barr - Riverside Drive BRT (brt) |
| XB27 Hulen-Altamesa BRT | brt | 16.9 | 53% | 40% | matched | G90 Alsbury / Edgehill - Bellaire / Watercourse BRT (brt) |
| XP06 Dallas Parkway BRT | brt | 16.8 | 65% | 51% | matched | G43 Coit / McCallum - Eldorado / Walker BRT (brt) |
| XB11 Park Boulevard BRT | brt | 16.5 | 77% | 77% | matched | G53 Communications / Legacy - Mars / Firewheel BRT (brt) |
| XB24 Cooper Street BRT | brt | 16.4 | 92% | 79% | matched | G23 Bedford / Barr - Matlock / Turner Warnell BRT (brt) |
| XB26 Collins-Center BRT | brt | 16.3 | 76% | 76% | matched | G23 Bedford / Barr - Matlock / Turner Warnell BRT (brt) |
| XB21 Hurst-Euless-Bedford BRT | brt | 15.8 | 100% | 100% | matched | G95 Country Club / Las Brisas - Mercantile Drive BRT (brt) |
| XB41 Watauga-Keller BRT | brt | 15.7 | 76% | 76% | matched | G39 Riverside Drive - Brentwood Stair / Oak Hill BRT (brt) |
| XB02 Buckner Boulevard BRT | brt | 15.5 | 75% | 53% | matched | G77 Masters / Bruton - Highway 67 / Marvin D Love BRT (brt) |
| E28 Forest Lane BRT | brt | 14.7 | 73% | 59% | matched | G04 John W Carpenter / Shorthorn - Adleta / Skillman BRT (brt) |
| XB44 Sachse-Wylie BRT | brt | 14.6 | 65% | 65% | matched | G83 LBJ - Alanis / Stone BRT (brt) |
| XB37 Burleson-Crowley BRT | brt | 14.0 | 83% | 19% | matched | G91 Field / Patterson - Alsbury / Edgehill Rail (commuter) |
| XB06 Hampton-Westmoreland BRT | brt | 13.8 | 63% | 53% | matched | G85 52nd Street / Horizon - Highland / Weaver BRT (brt) |
| E27 Ross Avenue BRT | brt | 13.2 | 94% | 73% | matched | G51 Grauwyler / O'Connor - Masters / Bruton Metro (metro) |
| XB35 Lewisville Main Street BRT | brt | 11.6 | 70% | 32% | matched | G37 Adleta / Skillman - Avenue C / Hickory Rail (commuter) |
| XB42 Denton Tap BRT | brt | 10.5 | 80% | 28% | matched | G78 Highland / Vista Ridge Mall - Grauwyler / O'Connor Metro (metro) |
| XB39 West Frisco BRT | brt | 10.3 | 68% | 64% | matched | G81 Highland / Vista Ridge Mall - Eldorado / Walker BRT (brt) |
| XB33 Denton-Corinth BRT | brt | 9.1 | 85% | 85% | matched | G42 Avenue C / Hickory - Morriss / Olympia BRT (brt) |
| E10 TRE | commuter | 120.2 | 51% | 51% | matched | G30 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| E40 Weatherford Line | commuter | 48.4 | 100% | 100% | matched | G63 Stemmons / Medical District - Russell / Park Rail (commuter) |
| E22 I-30 / FW Blue Line | metro | 82.9 | 85% | 33% | matched | G80 Henderson / 5th Street - Market Center / Tubbs Rail (commuter) |
| E19 I-20 Crosstown | metro | 72.8 | 55% | 17% | matched | G33 Cooper / Mitchell - Treepoint / Pennsylvania BRT (brt) |
| E23 SH-360 Line | metro | 72.1 | 66% | 13% | matched | G23 Bedford / Barr - Matlock / Turner Warnell BRT (brt) |
| E17 DNT East | metro | 63.9 | 87% | 69% | matched | G27 Stemmons / Medical District - Communications / Legacy Metro (metro) |
| E18 Las Colinas-Mesquite Line | metro | 45.5 | 99% | 64% | matched | G30 Lake Carolyn / O'Connor - US-80 / Pinson Rail (commuter) |
| E26 Legacy Line | metro | 44.7 | 75% | 68% | matched | G27 Stemmons / Medical District - Communications / Legacy Metro (metro) |
| XP01 SH-114 Line | metro | 38.9 | 71% | 41% | matched | G22 Bush Turnpike - Pearson / Fawkes BRT (brt) |
| E16 DNT West | metro | 31.2 | 87% | 76% | matched | G51 Grauwyler / O'Connor - Masters / Bruton Metro (metro) |
| F01 FW Green | metro | 21.9 | 90% | 44% | matched | G03 Brentwood Stair / Oak Hill - Bellaire / Watercourse BRT (brt) |
| F04 FW Pink | metro | 21.6 | 83% | 54% | matched | G86 Henderson / 5th Street - Sycamore School / Meadow Creek Metro (metro) |
| E14 Red Line | metro | 20.0 | 100% | 22% | matched | G47 Scenic / Sutherland - County Road 365 / McKinney BRT (brt) |
| F06 FW Red | metro | 13.7 | 91% | 21% | matched | G63 Stemmons / Medical District - Russell / Park Rail (commuter) |
| F03 FW Orange | metro | 11.5 | 100% | 31% | matched | G06 Schwartz / Jasper - Sycamore School / Meadow Creek BRT (brt) |
| F07 FW Purple | metro | 7.6 | 80% | 25% | matched | G06 Schwartz / Jasper - Sycamore School / Meadow Creek BRT (brt) |
| E13 Green Line | metro | 3.4 | 100% | 100% | matched | G51 Grauwyler / O'Connor - Masters / Bruton Metro (metro) |
| E12 Orange Line | metro | 3.1 | 100% | 100% | matched | G51 Grauwyler / O'Connor - Masters / Bruton Metro (metro) |
| XE01 I-35E Express | brt | 50.8 | 36% | 12% | partly | G49 Noel / Alpha - John Arden / Solon Rail (commuter) |
| XB15 Frisco Main-Eldorado BRT | brt | 29.3 | 46% | 42% | partly | G96 Eldorado / Walker - Greenville Avenue BRT (brt) |
| XB13 Preston Road BRT | brt | 25.9 | 49% | 33% | partly | G28 Noel / Alpha - Alanis / Stone Rail (commuter) |
| XB31 DeSoto-Lancaster BRT | brt | 20.7 | 26% | 22% | partly | G85 52nd Street / Horizon - Highland / Weaver BRT (brt) |
| XB20 Denton UNT-TWU BRT | brt | 18.5 | 24% | 19% | partly | G42 Avenue C / Hickory - Morriss / Olympia BRT (brt) |
| XB16 McKinney Lake Forest BRT | brt | 17.6 | 39% | 39% | partly | G58 Communications / Legacy - Greenville Avenue Metro (metro) |
| XB19 Flower Mound-Lewisville BRT | brt | 16.5 | 29% | 29% | partly | G48 Greenville / Holly Hill - Morriss / Olympia Metro (metro) |
| E04 Jacksboro BRT | brt | 14.8 | 38% | 38% | partly | G06 Schwartz / Jasper - Sycamore School / Meadow Creek BRT (brt) |
| E29 Jefferson Blvd BRT | brt | 11.4 | 42% | 39% | partly | G84 Field / Patterson - Parks / Parkerville BRT (brt) |
| E07 Mansfield-Denton-Carrollton | commuter | 86.6 | 43% | 24% | partly | G21 Central / Fall Creek - Alsbury / Edgehill Rail (commuter) |
| E35 Ennis Line | commuter | 54.8 | 32% | 16% | partly | G69 Matilda / University - Dowdy Ferry Road BRT (brt) |
| E41 Greenville Line | commuter | 54.8 | 25% | 22% | partly | G80 Henderson / 5th Street - Market Center / Tubbs Rail (commuter) |
| E37 Midlothian Line | commuter | 29.1 | 27% | 0% | partly | G84 Field / Patterson - Parks / Parkerville BRT (brt) |
| E09 TEXRail | commuter | 19.8 | 46% | 13% | partly | G70 Henderson / 5th Street - Alsbury / Edgehill BRT (brt) |
| F05 FW Berry | metro | 25.4 | 35% | 23% | partly | G86 Henderson / 5th Street - Sycamore School / Meadow Creek Metro (metro) |
| XB29 North Fort Worth-Alliance BRT | brt | 21.0 | 8% | 8% | missed |  |
| E01 White Settlement BRT | brt | 20.1 | 6% | 6% | missed |  |
| XB45 Matlock-Mansfield BRT | brt | 12.8 | 0% | 0% | missed |  |
| E32 Gainesville Line | commuter | 107.4 | 9% | 5% | missed |  |
| E31 Bowie Line | commuter | 104.8 | 8% | 6% | missed |  |
| E33 Sherman Line | commuter | 85.4 | 18% | 7% | missed |  |

### Generated lines

| line | mode | km | near hand plan (1 km) | same family | verdict | closest hand-plan line |
|---|---|---|---|---|---|---|
| G01 Central / Fall Creek - Coit / Churchill BRT | brt | 13.4 | 51% | 51% | in hand plan | E21 Beltline Line (brt) |
| G02 Forest / Cromwell - Parkwood / Chapel Hill BRT | brt | 21.2 | 79% | 33% | in hand plan | E26 Legacy Line (metro) |
| G03 Brentwood Stair / Oak Hill - Bellaire / Watercourse BRT | brt | 24.2 | 100% | 57% | in hand plan | F01 FW Green (metro) |
| G04 John W Carpenter / Shorthorn - Adleta / Skillman BRT | brt | 33.0 | 81% | 48% | in hand plan | XP01 SH-114 Line (metro) |
| G05 Bedford / Barr - Morriss / Olympia BRT | brt | 29.3 | 47% | 30% | partly | XP01 SH-114 Line (metro) |
| G06 Schwartz / Jasper - Sycamore School / Meadow Creek BRT | brt | 25.0 | 79% | 63% | in hand plan | F03 FW Orange (metro) |
| G07 Coit / McCallum - F / Executive BRT | brt | 8.4 | 61% | 61% | in hand plan | XB12 Coit Road BRT (brt) |
| G08 Matilda / University - F / Executive BRT | brt | 24.4 | 41% | 41% | partly | E28 Forest Lane BRT (brt) |
| G09 Noel / Alpha - Coit / McCallum BRT | brt | 11.9 | 90% | 75% | in hand plan | E26 Legacy Line (metro) |
| G10 Cockrell Hill / Falls - Perry Road BRT | brt | 34.5 | 71% | 50% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G11 Dallas / Arapaho - Lukenbach / Rambling BRT | brt | 34.3 | 88% | 66% | in hand plan | E17 DNT East (metro) |
| G12 Hill / SH-161 - Matlock / Turner Warnell BRT | brt | 23.6 | 72% | 54% | in hand plan | XB24 Cooper Street BRT (brt) |
| G13 Gilford / Denton - Grapevine Mills Circle BRT | brt | 31.7 | 66% | 49% | in hand plan | XP01 SH-114 Line (metro) |
| G14 Fountain / Westpark - Hill / SH-161 BRT | brt | 6.0 | 44% | 0% | partly | E23 SH-360 Line (metro) |
| G15 Communications / Legacy - White / Waddill BRT | brt | 30.8 | 92% | 76% | in hand plan | E14 Red Line (metro) |
| G16 Excel / Westgrove - Grauwyler / O'Connor BRT | brt | 28.0 | 63% | 45% | in hand plan | E21 Beltline Line (brt) |
| G17 Mercantile Drive - Pearson / Fawkes BRT | brt | 23.9 | 51% | 45% | in hand plan | XB41 Watauga-Keller BRT (brt) |
| G18 Fountain / Westpark - Waverly Drive BRT | brt | 15.2 | 81% | 56% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G19 John W Carpenter / Shorthorn - Greenville / Holly Hill BRT | brt | 26.2 | 62% | 47% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G20 Matilda / University - Hill / SH-161 BRT | brt | 33.5 | 84% | 41% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G21 Central / Fall Creek - Alsbury / Edgehill Rail | commuter | 92.0 | 66% | 23% | in hand plan | E21 Beltline Line (brt) |
| G22 Bush Turnpike - Pearson / Fawkes BRT | brt | 34.2 | 64% | 13% | in hand plan | XP01 SH-114 Line (metro) |
| G23 Bedford / Barr - Matlock / Turner Warnell BRT | brt | 31.4 | 97% | 89% | in hand plan | XB24 Cooper Street BRT (brt) |
| G24 Grauwyler / O'Connor - LBJ BRT | brt | 33.7 | 66% | 40% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G25 Field / Patterson - Communications / Legacy Metro | metro | 40.2 | 78% | 37% | in hand plan | E17 DNT East (metro) |
| G26 Scenic / Sutherland - Mars / Firewheel BRT | brt | 25.9 | 50% | 50% | in hand plan | XB17 Independence Parkway BRT (brt) |
| G27 Stemmons / Medical District - Communications / Legacy Metro | metro | 37.2 | 93% | 93% | in hand plan | E17 DNT East (metro) |
| G28 Noel / Alpha - Alanis / Stone Rail | commuter | 28.8 | 35% | 0% | partly | XB13 Preston Road BRT (brt) |
| G29 Gilford / Denton - Highway 67 / Marvin D Love BRT | brt | 27.5 | 90% | 58% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G30 Lake Carolyn / O'Connor - US-80 / Pinson Rail | commuter | 56.8 | 85% | 66% | in hand plan | E10 TRE (commuter) |
| G31 Highland / Vista Ridge Mall - Morriss / Olympia BRT | brt | 11.3 | 83% | 83% | in hand plan | XP02 Coppell-Lewisville BRT (brt) |
| G32 Highland / Vista Ridge Mall - Grapevine Mills Circle BRT | brt | 6.7 | 91% | 91% | in hand plan | XP02 Coppell-Lewisville BRT (brt) |
| G33 Cooper / Mitchell - Treepoint / Pennsylvania BRT | brt | 16.2 | 90% | 34% | in hand plan | E19 I-20 Crosstown (metro) |
| G34 Lombardy / Webb Chapel - Bedford / Barr BRT | brt | 31.3 | 74% | 61% | in hand plan | XB21 Hurst-Euless-Bedford BRT (brt) |
| G35 Excel / Westgrove - Masters / Bruton Metro | metro | 41.8 | 80% | 41% | in hand plan | E17 DNT East (metro) |
| G36 Coit / Churchill - Alanis / Stone BRT | brt | 32.0 | 73% | 73% | in hand plan | E21 Beltline Line (brt) |
| G37 Adleta / Skillman - Avenue C / Hickory Rail | commuter | 59.9 | 42% | 8% | partly | XB35 Lewisville Main Street BRT (brt) |
| G38 Mustang Drive - Matlock / Turner Warnell Metro | metro | 40.4 | 44% | 20% | partly | XB24 Cooper Street BRT (brt) |
| G39 Riverside Drive - Brentwood Stair / Oak Hill BRT | brt | 25.5 | 95% | 74% | in hand plan | XB41 Watauga-Keller BRT (brt) |
| G40 Coit / Churchill - Scenic / Sutherland BRT | brt | 22.4 | 84% | 77% | in hand plan | XB12 Coit Road BRT (brt) |
| G41 Greenville / Holly Hill - Greenville Avenue BRT | brt | 35.7 | 57% | 49% | in hand plan | E14 Red Line (metro) |
| G42 Avenue C / Hickory - Morriss / Olympia BRT | brt | 30.5 | 53% | 50% | in hand plan | XB33 Denton-Corinth BRT (brt) |
| G43 Coit / McCallum - Eldorado / Walker BRT | brt | 32.3 | 83% | 69% | in hand plan | E17 DNT East (metro) |
| G44 Cooper / Mitchell - Highland / Weaver BRT | brt | 30.7 | 84% | 81% | in hand plan | E21 Beltline Line (brt) |
| G45 Field / Patterson - Mercantile Drive Rail | commuter | 59.8 | 79% | 20% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G46 Lake Carolyn / O'Connor - Cooper / Mitchell BRT | brt | 31.2 | 61% | 18% | in hand plan | E23 SH-360 Line (metro) |
| G47 Scenic / Sutherland - County Road 365 / McKinney BRT | brt | 31.9 | 71% | 55% | in hand plan | E14 Red Line (metro) |
| G48 Greenville / Holly Hill - Morriss / Olympia Metro | metro | 43.2 | 71% | 16% | in hand plan | E21 Beltline Line (brt) |
| G49 Noel / Alpha - John Arden / Solon Rail | commuter | 85.2 | 64% | 13% | in hand plan | XE01 I-35E Express (brt) |
| G50 Matilda / University - Grapevine Mills Circle Metro | metro | 36.2 | 63% | 40% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G51 Grauwyler / O'Connor - Masters / Bruton Metro | metro | 42.4 | 75% | 54% | in hand plan | E18 Las Colinas-Mesquite Line (metro) |
| G52 Bedford / Barr - Pearson / Fawkes BRT | brt | 19.7 | 37% | 37% | partly | XB21 Hurst-Euless-Bedford BRT (brt) |
| G53 Communications / Legacy - Mars / Firewheel BRT | brt | 33.3 | 60% | 54% | in hand plan | E17 DNT East (metro) |
| G54 Bedford / Barr - Riverside Drive BRT | brt | 25.3 | 64% | 64% | in hand plan | XB21 Hurst-Euless-Bedford BRT (brt) |
| G55 Lombardy / Webb Chapel - Masters / Bruton BRT | brt | 30.9 | 69% | 37% | in hand plan | E18 Las Colinas-Mesquite Line (metro) |
| G56 John W Carpenter / Shorthorn - Cooper / Mitchell Metro | metro | 30.4 | 63% | 37% | in hand plan | E23 SH-360 Line (metro) |
| G57 Adleta / Skillman - Sycamore School / Meadow Creek Rail | commuter | 95.7 | 59% | 21% | in hand plan | E10 TRE (commuter) |
| G58 Communications / Legacy - Greenville Avenue Metro | metro | 20.1 | 79% | 32% | in hand plan | XB17 Independence Parkway BRT (brt) |
| G59 Henderson / 5th Street - Bellaire / Watercourse Metro | metro | 13.9 | 96% | 72% | in hand plan | F01 FW Green (metro) |
| G60 Gilford / Denton - Park Row / Susan BRT | brt | 32.2 | 39% | 13% | partly | E22 I-30 / FW Blue Line (metro) |
| G61 Gilford / Denton - Mars / Firewheel Metro | metro | 33.4 | 62% | 24% | in hand plan | XB01 Northwest Highway BRT (brt) |
| G62 Gilford / Denton - Highland / Vista Ridge Mall BRT | brt | 28.4 | 43% | 24% | partly | E33 Sherman Line (commuter) |
| G63 Stemmons / Medical District - Russell / Park Rail | commuter | 97.5 | 71% | 53% | in hand plan | E40 Weatherford Line (commuter) |
| G64 Forest / Cromwell - Eldorado / Walker Metro | metro | 44.3 | 78% | 71% | in hand plan | E17 DNT East (metro) |
| G65 Mustang Drive - Parkwood / Chapel Hill Metro | metro | 40.4 | 79% | 59% | in hand plan | XP01 SH-114 Line (metro) |
| G66 Waverly Drive - Highway 67 / Marvin D Love BRT | brt | 31.5 | 62% | 47% | in hand plan | XB25 Pioneer Parkway BRT (brt) |
| G67 Mustang Drive - Brentwood Stair / Oak Hill BRT | brt | 28.0 | 65% | 62% | in hand plan | XB21 Hurst-Euless-Bedford BRT (brt) |
| G68 Forest / Cromwell - Lukenbach / Rambling Metro | metro | 43.9 | 74% | 27% | in hand plan | E26 Legacy Line (metro) |
| G69 Matilda / University - Dowdy Ferry Road BRT | brt | 33.2 | 84% | 67% | in hand plan | E35 Ennis Line (commuter) |
| G70 Henderson / 5th Street - Alsbury / Edgehill BRT | brt | 26.6 | 51% | 43% | in hand plan | E09 TEXRail (commuter) |
| G71 Central / Fall Creek - Masters / Bruton BRT | brt | 34.8 | 72% | 49% | in hand plan | XB34 Shiloh Road BRT (brt) |
| G72 Park Row / Susan - 52nd Street / Horizon BRT | brt | 33.8 | 93% | 51% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G73 Adleta / Skillman - Market Center / Tubbs BRT | brt | 34.5 | 32% | 16% | partly | E41 Greenville Line (commuter) |
| G74 Cooper / Mitchell - Schwartz / Jasper BRT | brt | 30.4 | 73% | 46% | in hand plan | F01 FW Green (metro) |
| G75 Sycamore School / Meadow Creek - Matlock / Turner Warnell BRT | brt | 34.5 | 56% | 34% | in hand plan | E07 Mansfield-Denton-Carrollton (commuter) |
| G76 Henderson / 5th Street - Fountain / Westpark Rail | commuter | 32.4 | 88% | 6% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G77 Masters / Bruton - Highway 67 / Marvin D Love BRT | brt | 30.0 | 82% | 78% | in hand plan | XB03 Illinois-Lake June BRT (brt) |
| G78 Highland / Vista Ridge Mall - Grauwyler / O'Connor Metro | metro | 21.8 | 70% | 28% | in hand plan | XB42 Denton Tap BRT (brt) |
| G79 Country Club / Las Brisas - Highway 67 / Marvin D Love BRT | brt | 35.1 | 60% | 28% | in hand plan | E18 Las Colinas-Mesquite Line (metro) |
| G80 Henderson / 5th Street - Market Center / Tubbs Rail | commuter | 99.0 | 77% | 27% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G81 Highland / Vista Ridge Mall - Eldorado / Walker BRT | brt | 27.0 | 40% | 40% | partly | XB32 Josey Lane BRT (brt) |
| G82 Greenville / Holly Hill - Masters / Bruton Metro | metro | 25.0 | 66% | 35% | in hand plan | E18 Las Colinas-Mesquite Line (metro) |
| G83 LBJ - Alanis / Stone BRT | brt | 24.8 | 52% | 52% | in hand plan | XB44 Sachse-Wylie BRT (brt) |
| G84 Field / Patterson - Parks / Parkerville BRT | brt | 32.5 | 73% | 49% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G85 52nd Street / Horizon - Highland / Weaver BRT | brt | 21.9 | 67% | 61% | in hand plan | E19 I-20 Crosstown (metro) |
| G86 Henderson / 5th Street - Sycamore School / Meadow Creek Metro | metro | 18.5 | 82% | 63% | in hand plan | E10 TRE (commuter) |
| G87 Adleta / Skillman - US-80 / Pinson BRT | brt | 32.3 | 62% | 50% | in hand plan | XB09 Garland Broadway BRT (brt) |
| G88 Field / Patterson - Market Center / Tubbs Metro | metro | 43.8 | 67% | 17% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G89 Eldorado / Walker - White / Waddill BRT | brt | 29.7 | 77% | 71% | in hand plan | XB40 McKinney Virginia Parkway BRT (brt) |
| G90 Alsbury / Edgehill - Bellaire / Watercourse BRT | brt | 23.2 | 46% | 37% | partly | XB27 Hulen-Altamesa BRT (brt) |
| G91 Field / Patterson - Alsbury / Edgehill Rail | commuter | 71.3 | 83% | 33% | in hand plan | E22 I-30 / FW Blue Line (metro) |
| G92 Highland / Weaver - Parks / Parkerville BRT | brt | 10.4 | 92% | 92% | in hand plan | E21 Beltline Line (brt) |
| G93 Bedford / Barr - Treepoint / Pennsylvania BRT | brt | 32.7 | 84% | 68% | in hand plan | E24 FW Crosstown Loop (brt) |
| G94 LBJ - Dowdy Ferry Road BRT | brt | 28.2 | 54% | 32% | in hand plan | XB34 Shiloh Road BRT (brt) |
| G95 Country Club / Las Brisas - Mercantile Drive BRT | brt | 34.9 | 75% | 74% | in hand plan | XB21 Hurst-Euless-Bedford BRT (brt) |
| G96 Eldorado / Walker - Greenville Avenue BRT | brt | 33.4 | 77% | 67% | in hand plan | XB15 Frisco Main-Eldorado BRT (brt) |

