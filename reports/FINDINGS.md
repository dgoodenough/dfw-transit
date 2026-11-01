# Findings

Analyses run outside the build, kept for reference. Not shown on the map or the story page.

## Transit commute mode share against peer metros (2026-11-01)

**Question:** where would DFW's transit share of commutes rank against other US metros,
with and without the plan?

**The model's share** is transit commuters (rail and BRT, with feeder buses) as a share of
all commutes, from `results/<plan>/years.csv`. Commutes are `demand.total_commutes` (3.32M)
scaled with jobs. Riders already allow for working from home (`ridership.telework` 0.85), so
the denominator is all workers, as in the Census figures.

| Plan | 2025 | 2050 | 2100 |
|---|---|---|---|
| Current track (no plan) | 0.58% | 0.66% | 0.72% |
| Budget plan (v2) | 0.58% | 1.88% | 3.04% |
| 2 million riders | 0.58% | 4.63% | 7.61% |

**Local buses aren't in the model.** It is calibrated to today's 80k rail boardings, so its 0.58%
for 2025 is rail only. The Census puts all transit at about 1.0% of DFW workers in 2023,
which leaves roughly 0.4 points on local buses. Adding that back, assuming it holds:
- the current track stays about 1.1% in 2100;
- the budget plan reaches about 3.4%;
- the 2 million plan reaches about 5.0% by 2050 and 8.0% by 2100.

**Peers in 2023** (share of workers commuting by public transit):

| Metro | Share | Source |
|---|---|---|
| New York | 23.8% | ACS 2023 1-year, via Cox (New Geography) |
| San Francisco-Oakland | 10.3% | ACS 2019-2023 5-year, via censusdepth.com |
| Boston | 9.0% | 5-year, as above |
| Chicago | 8.2% | 5-year, as above |
| Washington DC | 7.9% | 5-year, as above |
| Philadelphia | 6.5% | 5-year, as above |
| Seattle | 5.8% | 5-year, as above |
| *United States* | *3.5%* | ACS 2023, via Cox |
| Denver | 2.6% | 5-year, as above |
| Milwaukee | 2.2% | 5-year, as above |
| Houston | about 2% | ACS 2024, rounded, via autoinsurance.com (less reliable) |
| Atlanta | about 1% | as above |
| **Dallas-Fort Worth** | **1.0% or less** | ACS 2023 1-year, via Cox: with Austin, Charlotte and Virginia Beach-Norfolk, despite their rail spending |

APTA's 2026 Fact Book gives slightly higher figures for the top group: San Francisco 10.9%,
Boston 9.8%, Chicago 9.0%, Washington 9.0%, Philadelphia 7.3%, Seattle 6.3%. The order is the
same.

**Where DFW would rank, against today's peers:**
- **Without the plan (current track):** about 1% in 2100. Still near the bottom of the large
  metros, with Atlanta, Austin and Charlotte.
- **Budget plan:** about 3.4% by 2100. Above Denver and Houston, about today's national
  average, well short of Seattle.
- **2 million plan:** about 5% by 2050, between Denver and Seattle. About 8% by 2100, level with
  Washington DC and Chicago today, behind only New York, San Francisco and Boston. In other
  words, roughly 5th among US metros.

**Caveats:**
- Peers move too. These compare DFW's future with other metros' present, and most of them
  are still below their 2019 shares (Washington and Chicago were over 12%).
- The model counts commutes only, scaled to all trips. Mode share here is commute share, the
  same measure the Census uses.
- The model covers nine counties; the Census metro has eleven.
- The 5-year figures average 2019-2023, so they include pandemic years. They run below
  2019 levels and probably above 2023.
- Search-snippet sources; the Census API and the pages behind them are blocked from this
  environment. Check against ACS table B08301 before quoting.

Sources: [New Geography, Work Access 2023](https://www.newgeography.com/content/008325-work-access-major-metropolitan-areas-2023);
[censusdepth.com metro ranking](https://censusdepth.com/transit-commuters/metros);
[APTA 2026 Public Transportation Fact Book](https://www.apta.com/wp-content/uploads/2026/04/APTA-2026-Public-Transportation-Fact-Book.pdf);
[autoinsurance.com commuting statistics](https://www.autoinsurance.com/research/us-commuting-statistics/).

## Denser station areas: what more residents near the densest stations add (2026-10-31)

**Question:** downtown growth looks anemic. What would 2100 ridership be if the densest
station areas got a bigger population boost?

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
