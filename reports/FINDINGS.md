# Findings

Analyses run outside the build, kept for reference. Not shown on the map or the story page.

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
