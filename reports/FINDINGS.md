# Findings

Analyses run outside the build, kept for reference. Not shown on the map or the story page.

## Non-commute trips modelled on their own (2026-11-02, revised 2026-11-03 with NCTCOG inputs; off by default)

**Question:** the model scales commutes to all trips (x 1.9 round trip / 0.5 work share), so
shopping, errand, school, airport and event trips go where commuters go. What changes if they
get their own trip table, destinations and service levels?

**Prototype** (`config.json` -> `ridership.nonwork`, `enabled: false`; `demand.nonwork_od`,
`evaluate._with_nonwork`, `evaluate.calibrate_nonwork`, `tests/test_nonwork.py`; each input's
source is in `ridership.nonwork._sources`):
- Purposes as in NCTCOG's TAFT model: home-based non-work (2.06 trips per resident) and
  non-home-based (1.10), from NCTCOG's review of the 2009 NHTS (3.67 weekday trips per person:
  56.1% home-based non-work, 30.1% non-home-based, 13.6% home-based work). That is 26M trips a
  day in 2025, against 6.7M work trips.
- Each purpose is a doubly-constrained gravity model on off-peak drive times. The decay is set
  so trips average 0.55x (home-based) and 0.65x (non-home-based) the length of commutes, as in
  NCTCOG's NHTS trip durations (14.8, 17.8 and 27.2 minutes): exp(-0.21 x minutes) and
  exp(-0.11 x minutes).
- Attractions: households and retail, service and basic jobs at NCHRP 365 rates (TAFT uses the
  same three employment types but doesn't publish its rates), from LODES WAC 2022 jobs by sector
  (`data/lodes_wac_sectors_bg_2022.csv`, `tools/fetch_wac.py`).
- Special generators, as TAFT has for airports, universities and hospitals: DFW Airport (145k
  ground trips a day; NCTCOG's 2015 airport survey found 63% of departing passengers
  originating), Love Field (28k; 56% originating), the Arlington entertainment district, the
  Stockyards, Fair Park, Victory, the Fort Worth Cultural District and six universities. Each
  has its own reach and venue parking. The airport's block group is moved onto the terminals
  for these trips: its population centroid sits 2.5 km away, out of walking range of both
  airport stations.
- Mode choice: the commute logit with its own constant and half the value of time (TAFT:
  home-based non-work 50% of work), no telework, off-peak headways (x1.5, regional rail x2,
  feeder buses x1.5), 30% of the peak's extra road delay, short-stay parking and half of each
  garage.
- Calibration: today's network still carries 80k rail boardings in 2025, 55.7% of them work
  trips (NCTCOG's 2022-23 on-board survey: home-based work is 55.9% of light rail and 54.1% of
  commuter rail trips). Commute constant +0.58, non-commute constant -2.05.

**Daily trips (each counted once):**

| Plan | Year | Today's method | With non-commute trips | Change | Work share | First version (Nov 2) |
|---|---|---|---|---|---|---|
| both | 2025 | 77,118 | 77,697 | +0.7% | 55% | 77,749 |
| Budget plan | 2050 | 370,456 | 396,632 | +7.1% | 51% | 410,547 (+10.8%) |
| Budget plan | 2100 | 740,278 | 836,041 | +12.9% | 48% | 866,920 (+17.1%) |
| 2 million plan | 2050 | 890,075 | 921,134 | +3.5% | 52% | 979,356 (+10.0%) |
| 2 million plan | 2100 | 1,899,808 | 1,983,757 | +4.4% | 52% | 2,130,008 (+12.1%) |

The first version used national trip rates, one decay for both purposes, a 50% work share and
the commutes' value of time. Rail and BRT boardings barely move (2 million plan 2100: 2.75M ->
2.73M). Feeder bus boardings fall (non-commute trips are shorter and the off-peak buses less
frequent), so all boardings drop from 3.42M to 3.29M.

**Where it lands** (2 million plan, 2100; daily transit trip ends, two per trip):

| Area | Today's method | With non-commute trips | Change |
|---|---|---|---|
| Downtown Dallas | 411,700 | 430,499 | +5% |
| Downtown Fort Worth | 87,596 | 84,411 | -4% |
| Arlington entertainment district | 20,733 | 48,364 | +133% |
| DFW Airport | 2,280 | 12,266 | +438% |
| Love Field | 11,448 | 18,172 | +59% |
| Stockyards | 1,800 | 3,316 | +84% |
| Fair Park | 4,646 | 10,008 | +115% |
| Six universities | 50,628 | 58,756 | +16% |
| Rest of the region | 3,208,784 | 3,301,722 | +3% |

**Airport check:** in 2025 the model has about 1,470 non-commute transit trip ends at DFW
Airport and 690 at Love Field. NCTCOG's 2022-23 on-board survey (Tables 48-49) counts about
1,580 weekday rail boardings by airline passengers going to or from an airport, and the model's
airport ends also include other visits to the airports. The airports are not undercounted; the
first version compared them with TEXRail's total ridership, the wrong yardstick.

**Density:** residents within 800 m of the 45 stations within 2.5 km of either downtown raised
to 25,000/km² (+0.62M, taken from the rest of the region) add +88.0k trips with today's method
and +43.7k with non-commute trips (+46.4k work, -2.7k non-commute). Non-work trips make density
matter less here, not more. Downtown residents' errands are short (the home-based decay is
steep), so most are walked or under the 2 km minimum for a transit trip. The residents moved
downtown also stop making the longer trips elsewhere that transit could serve.

**Sensitivity** (2 million plan, 2100, each recalibrated):

| Variant | Daily trips | Change against today's method |
|---|---|---|
| As above (half the value of time, on the time coefficients) | 1,983,757 | +4.4% |
| Half the value of time, on the cost coefficient instead | 2,083,644 | +9.7% |
| Same value of time as commutes | 2,111,559 | +11.1% |
| First version (national inputs) | 2,130,008 | +12.1% |

The value of time decides the size of the gain. TAFT gives non-work trips half the value of
time in route choice, but how that carries into mode choice (weaker time sensitivity, or
stronger cost sensitivity) isn't published. The config keeps the cautious reading
(`value_of_time_on: "time"`).

**Caveats:** attraction rates are national defaults (TAFT's aren't published) and venue figures
approximate; universities and hospitals use simple generators where TAFT has special models;
one average weekday, no event peaks.

## Transit commute mode share against peer metros (2026-11-01, revised for real commute flows)

**Question:** where would DFW's transit share of commutes rank against other US metros,
with and without the plan?

**Peers, 2023:** ACS 1-year table B08301, from the Census bulk file
`www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/1YRData/acsdt1y2023-b08301.dat`.
The share is public transportation (excluding taxi) over all workers, including those who work
from home. Rank is among the 39 largest metros found (Cleveland's code didn't match).

| Rank | Metro | Transit share |
|---|---|---|
| 1 | New York | 26.6% |
| 2 | San Francisco-Oakland | 10.1% |
| 3 | Boston | 9.3% |
| 4 | Chicago | 8.5% |
| 5 | Washington DC | 8.2% |
| 6 | Philadelphia | 6.4% |
| 7 | Seattle | 5.7% |
| 8 | Honolulu | 5.3% |
| 9 | Pittsburgh | 3.6% |
| 10 | Baltimore | 3.4% |
| 11 | Los Angeles | 3.3% |
| 12 | Portland | 3.0% |
| 14 | Miami | 2.8% |
| 16 | Denver | 2.3% |
| 19 | Minneapolis-St Paul | 2.1% |
| 21 | Atlanta | 1.5% |
| 22 | Houston | 1.4% |
| 25 | Phoenix | 1.2% |
| 31 | Charlotte | 0.9% |
| 32 | Austin | 0.9% |
| **36** | **Dallas-Fort Worth** | **0.71%** |
| 39 | Kansas City | 0.56% |

**The model's share** is transit commuters (rail and BRT, with feeder buses) over all commutes,
after the switch to LODES flows (v2.16). Commutes are 3.32M scaled with jobs. Riders already
allow for working from home (`ridership.telework` 0.85), so the denominator matches the Census.

| Plan | 2025 | 2050 | 2100 |
|---|---|---|---|
| Current track (no plan) | 0.57% | 0.65% | 0.70% |
| Budget plan | 0.57% | 1.88% | 2.90% |
| 2 million riders | 0.57% | 4.48% | 7.28% |

The model's 0.57% for 2025 is rail only, calibrated to today's 80k rail boardings. The Census
puts all transit at 0.71%, so local buses carry about another 0.14 points. Adding that:

- **No plan:** about 0.85% in 2100. Still about 36th of the 40 largest; the region grows
  around a network that barely grows.
- **Budget plan:** about 3.0% by 2100, around 12th today: Portland, Los Angeles (3.3%),
  Baltimore (3.4%).
- **2 million plan:** about 4.6% by 2050, between Seattle (5.7%) and Pittsburgh (3.6%), about
  9th. About 7.4% by 2100, between Philadelphia (6.4%) and Washington (8.2%), about 6th.

**Caveats:**
- Peers move too. This compares DFW's future with other metros' 2023, and most of them are
  still below their 2019 shares (Washington and Chicago were over 12%).
- The model counts commutes only, scaled to all trips. Mode share here is commute share, the
  same measure the Census uses.
- The model covers nine counties; the Census metro has eleven.
- An earlier version of this entry used search-snippet figures, some from 5-year estimates.
  The table above replaces them.

## Denser station areas: what more residents near the densest stations add (2026-10-31)

**Question:** downtown growth looks anemic. What would 2100 ridership be if the densest
station areas got a bigger population boost? (Run on the gravity-model flows, before v2.16;
the comparisons hold, but the absolute numbers are about 4-5% high.)

**Why downtowns grow slowly in the model:**
- Growth multiplies each area's 2020 population, so downtowns, which have few residents today,
  gain few. Within 1.5 km of the centre, Fort Worth goes from 10k residents to 40k in 2100
  under the 2 million plan, and Dallas from 16k to 69k.
- Growth capture (`growth.capture`) counts people plus jobs against its density targets.
  Downtown Dallas is already over its target on jobs alone, so it never takes residents.

**Experiment:**
- 2 million plan, 2100.
- Residents within 800 m of the chosen stations were raised to a target density.
- By default the extra people were taken from the rest of the region in proportion. Adding
  them as net new growth instead gave almost the same results, because the model's commute
  total follows jobs, which were held fixed.

| Boost | Residents added | Daily trips |
|---|---|---|
| none | 0 | 1.99M |
| downtown Fort Worth (18 stations within 2.5 km), 25,000/km² | 0.46M | 2.01M |
| downtown Dallas (27 stations), 25,000/km² | 0.26M | 2.03M |
| both downtowns, 15,000 / 25,000 / 40,000/km² | 0.37M / 0.72M / 1.29M | 2.02M / 2.06M / 2.13M |
| top 25 stations by today's density, 25,000/km² | 0.69M | 2.11M |
| top 50 stations, 15,000 / 25,000/km² | 0.94M / 1.79M | 2.12M / 2.24M |
| top 100 stations, 15,000/km² | 2.50M | 2.33M |
| top 200 stations, 15,000/km² | 5.03M | 2.60M |

**Takeaway:**
- The downtowns are too small to move the regional total, even at Manhattan density. Gains
  need density along the corridors: 100 or more station areas.
- The owner judged Manhattan-level density unrealistic and the gains too small to pursue.
  Nothing was changed.
- The same look found that the 2 million plan spends $135B of its $172.5B budget by 2100,
  because building stops around 2075 when the project list runs out. Its weakest additions
  are the outer regional rail lines, at 0.4-0.6 daily trips per $1M against a median of 4.6.
