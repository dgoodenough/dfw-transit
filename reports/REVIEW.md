# Review, October 2026

Nine reviewers went over the whole project after v2.8: the four planners (service,
long-range, land use, access/model critic), the phasing mathematician, the geometry and
routing pair, the data-model engineer, the graphic designer and the parameter
researcher. A UX/UI functionality pass followed. Their full write-ups are not in the
repository; this file keeps what they found, what was fixed, and what is left for the
owner to decide.

## Fixed

Bugs, fixed and committed (see network/CHANGELOG.md v2.9 for detail):

- **Disconnected BRT corridors.** Wider BRT stop spacing made 14 of 34 new corridors miss
  the stations they pass; three (Denton UNT-TWU, Shiloh Road, Sachse-Wylie) never
  connected and were pushed past 2100. New BRT now stops at every station within 300 m
  of its route.
- **Interchange stations moved by the aligner.** The v2.8 alignment run slid stations
  shared by several lines (DNT East broke at Stonebriar). Interchanges no longer move;
  DNT East/Legacy were re-fitted without moving any station.
- **Scheduler gave up budget.** A small mismatch between per-stage and year-by-year
  costs made it shrink the whole 75-year budget; a local repair now closes the gap
  (100% of the budget used, was 97%).
- **2M rebuild could double its stages** (a leftover `stages.add.csv`); the build now
  also stops on data errors in the default scenario.
- **Peak-hour loads ~3.8x low** (one-way commuters instead of daily riders); light-rail
  capacity set to 12k/h.
- **Station platforms charged once per station**, not per mode (~$0.8B missing when
  metro reaches a BRT or commuter station).
- **Station-area growth (TOD) started with a station's first bus**, not with the mode
  that earns it.
- **Park-and-ride in the choice model.** Riders chose their access mode, connector
  station and route on raw minutes, and the drive-to-transit constant (~60 min) applied
  only afterwards, so adding a garage could lower ridership. Choices now use the same
  perceived minutes as the mode choice; the model is recalibrated to 2025.
- **Walk-only "transit" trips** between nearby platforms are no longer counted.
- **2M scenario's 2025 baseline 13% above calibration**: its walkability package now
  starts in 2030.
- **Quick builds** divided carried riders by stale costs.
- **Map**: shared track side by side without steps or side swaps; interchange capsules;
  stations by zoom; softer "new" glow; contrast guard on the map; recoloured lines that
  met near-identical colours; trips drawn along their route; clearer trip-planner
  messages; popups, Lines panel, keyboard and touch fixes.

## Owner's decisions (v2.10)

- Keep the 2M target and add levers: D2 subway, regional-rail through-running, parking pricing
  (downtown prices double, $5/day at the densest job centers), Red Line to McKinney. The 2M
  scenario reaches ~2.24M daily trips in 2100.
- Take the cost concerns on board, with costs falling as a steady program matures
  (config cost_efficiency): 2025 peer-level unit costs, garages charged, operating cost reported.
- Add the Weatherford and Greenville lines by 2100 (and Cleburne): a complete-looking network
  matters ("80% art, 20% science").
- All the smaller decisions below (items 9-10) are taken.

## Decisions for the owner (as reviewed)

Ranked by how much they change the plan or its headline numbers.

1. **Is 2M still the target, and on which assumptions?** After the fixes the 2M scenario
   lands at about 1.87M daily trips in 2100. The reviewers' sensitivity runs say the
   margin is thin and several assumptions are at the generous end:
   - population: 15.9M by 2100 is at or above the state demographer's high path after
     2060; on a mid path 2100 trips fall ~18% (land-use planner);
   - access: kiss-and-ride is priced like a free chauffeur (−7% if given the P&R
     constant), bike/scooter access is 16–17% of riders (BART's US high is 6–8%; −5%),
     the car-free share grows to 10.7% of commuters (ACS ~3%; −4%) (access critic);
   - BRT runs 26–28 km/h at the new stop spacing with no signal delay; US arterial BRT
     is 18–22 km/h (−5% at 30 km/h) (access critic, parameter researcher);
   - the transfer penalty (3 min) is the low end of practice (−7.6% at 8 min).
   Options: keep the target and add levers (parking policy, D2 subway, commuter
   through-running), or present 2M as a range (~1.6–2.1M) depending on growth and access
   assumptions.
2. **Costs.** Unit costs are low for 2025 (commuter rail ~$33M/km vs DART Silver Line
   ~$48–50M/km; BRT $16M/km vs ~$55M/km for Houston University BRT): mid-range peer costs
   give ~$138B (+25%), pushing completion years later. Garages are free (~$5.5–6.5B for
   218k spaces); operating cost (~$1.6B/yr by 2100, plus feeder buses) is in neither the
   budget nor the value-per-$ ranking (parameter researcher, service planner).
3. **DART light-rail frequency needs the D2 subway**, which isn't in the plan: the 2M
   scenario runs 32–40 trains/h through the downtown mall from 2035. Add D2 (~$1.2B at
   model rates) or cap the mall at 24/h (−4.5% of trips) (service planner).
4. **Commuter through-running** at Fort Worth (5 rows from the service package): +16.7k
   trips at the same operating cost (service planner).
5. **A value floor for every mode**, not just BRT: ~$12B of commuter rail is under 4 trips
   per $M (Gainesville 0.5, Bowie 0.7, Ennis 1.2, Waxahachie 1.9). Note the zone data
   has no Grayson, Cooke, Montague or Wise counties, so far-end demand is zero by
   construction (long-range planner).
6. **Weatherford commuter line**: modelled at 2.9 trips per $M (+4.4k trips, $1.53B, 48.6
   km on the UP Baird Sub). Recommended as a documented reserve with right-of-way
   protection, and an I-30 express bus/BRT test instead (long-range planner).
7. **Build order inputs.** Value per $ comes from the last full build and shared-track
   cost depends on who opens first, so the order feeds back on itself. Reordering can
   gain 0–2% of trips over 2030–75 and nothing in 2100; a stage-level value test is a
   ~45 min run (phasing mathematician, data-model engineer).
8. **Spending profile.** The program is fully funded by ~2075; front-loading (~$2.6–2.7B/yr
   until done) finishes years earlier, ~+20k trips per year earlier mid-period
   (phasing mathematician).
9. **Smaller network calls**: end DNT East at Frisco Main St (−$70M, Frisco Square keeps
   rail); run Legacy as a DNT East branch via Legacy West (one-seat ride from Plano,
   ~25% fewer train-km); McKinney corridor as a Red Line light-rail extension (+23.6k
   trips, ~$1.7B); drop or trim the 9 suburban garages; Rowlett–Rockwall and
   Alvarado–Cleburne tests; trim Orange's 2071 southwest tail.
10. **Map**: rename the Fort Worth "Orange/Red/Blue" and green "Teal" lines (they clash
    with DART's names and with BRT teal); merged BRT strokes with hover names; From/To
    station search; should hidden lines drop out of the trip planner?

## Left for later (small, not yet done)

- Riders on shared track wait for one line, not the combined frequency (+2.2% when
  fixed; needs recalibration) (service planner).
- BRT stops on freeway main lanes (8), out-and-back spurs (HAIRPIN warnings), and an
  unanchored street-name hint in BRT routing (geometry/routing).
- McKinney Line north of Allen is up to 1.3 km off the DART corridor; a healed-routing
  prototype exists (geometry/routing).
- Make the lever_expand_* scenarios overlays instead of full copies, and retire
  make_two_million.py (data-model engineer).
- Diagram popups don't refresh with the year; trips to 2M-only BRT stops draw partly
  (UX pass).
