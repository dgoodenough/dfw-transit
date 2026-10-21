# Transfers, October 2026 (v2.12)

The owner asked whether infill stations or small track changes could cut the transfers trips
need. This is what the analysis found, what was tested, and what changed. Numbers are daily
trips from the ridership model (each trip counted once).

## How trips transfer today (before v2.12)

Every station-to-station flow the model assigns was followed along its path and its boardings
counted.

| | No transfer | One | Two | Three+ | Transfers per trip |
|---|---|---|---|---|---|
| Plan, 2100 | 62.6% | 35.1% | 2.3% | 0.0% | 0.40 |
| 2M, 2050 | 58.8% | 34.8% | 6.2% | 0.2% | 0.48 |
| 2M, 2100 | 51.9% | 40.1% | 7.5% | 0.5% | 0.57 |

- **Where people change (2M, 2100):** Victory (118k transfers a day), Pearl (75k), Farmers
  Branch (44k), Downtown Carrollton (43k), Saint Paul, Irving West, Bachman, MLK Jr.,
  Grapevine-Main Street, Central Station. Biggest line pairs: Green / SH-114 at Farmers Branch
  (44k), Orange / I-20 Crosstown at Victory (38k), DNT West / I-20 at Pearl (30k), TEXRail /
  SH-114 at Grapevine (29k).
- **Three-seat rides (2M, 2100, ~177k trips):** they cluster where a line ends one change short
  of where riders go. The SH-114 Line ended at Farmers Branch, so ~20k riders from Dallas rode
  X > Green > SH-114 (I-20, Orange, MDC, Beltline, Josey BRT, Sherman, I-30...). The
  Stemmons-Brookhollow BRT started at Inwood, so I-20 > Orange > Stemmons BRT (5.7k) and I-30 >
  Orange > Stemmons BRT (2.5k). Fort Worth: Hulen BRT > FW Red > FW Green, I-20 > FW Berry > FW
  Green.
- **Lines that cross with no station:** 148 places in the 2M network where two lines cross or
  run within 150 m with no interchange within 800 m (many BRT-BRT, some tunnels under each
  other downtown). Ranked by the multi-transfer riders whose line sequence holds both lines.

## What was tested

Each candidate was applied to the network and two model years (2050, 2100) re-run. An infill
stop slows everyone riding through it, so many lost riders.

- **Kept** (added riders alone, and still added riders with all the others in; leave-one-out
  gain in 2050 / 2100):

  | Change | 2M | Plan |
  |---|---|---|
  | Red/Orange at Main / Sherman Street (Richardson, Beltline Line) | +6.1k / +9.4k | +2.3k / +3.3k |
  | SH-114 trains run on over the Green Line to Victory (2M) | +4.8k / +8.4k | |
  | TEXRail extension x FW Berry (Pennsylvania / Henderson) | 0 / +7.7k | 0 / +3.0k |
  | Red/Blue/Orange at Central / Hall (I-20, I-30) | +4.7k / +4.0k | +2.0k / +1.9k |
  | Stemmons-Brookhollow BRT from Victory (2M) | +1.4k / +3.0k | |
  | Blue at Shiloh (Garland) | +1.8k / +2.9k | 0 / +0.3k |
  | TRE at Belt Line (Irving) | +4.1k / +2.5k | +0.6k / +1.4k |
  | Silver Line at Marsh (walk to DNT West) | +1.3k / +2.2k | +0.7k / +1.3k |
  | Midlothian at I-20 | 0 / +1.8k | 0 / +1.2k |
  | TRE x FW Green at Riverside | +2.3k / +1.7k | +0.7k / +1.1k |
  | Red/Orange at NW Highway | +1.0k / +1.5k | +0.2k / +0.4k |
  | Orange at SH-114 / Freeport | +1.9k / +1.3k | +0.5k / +0.7k |
  | Walk link Commerce / Harwood - Marilla / Pearl (2M) | +0.7k / +1.0k | |

- **Dropped** (lost riders or too little for the cost): a commuter hub where FW Green crosses
  the rail lines north of Fort Worth Central (slows four lines), TRE at Stemmons / Commonwealth,
  Hi Line, Lamar Street; Red/Blue at Corinth (-5.3k: slows the trunk); I-30/SH-360 at Collins
  and Cooper; I-20 at Collins and Kiest; Red at K / Legacy; DNT East at the Dallas Parkway BRT;
  a Beltline BRT stop at I-20; DNT West at Metro Center (+2.0k in 2100 for a ~$150M
  underground platform).

## What changed

All of the kept list, plus the owner's hand-drawn SH-114 realignment. After the full build:

| | 2050 | 2100 |
|---|---|---|
| Plan, daily trips | 370k -> 388k | 771k -> 788k |
| 2M, daily trips | 1.030M -> 1.064M | 2.235M -> 2.254M |

(2M also rescheduled, which moves several lines by years; the 2100 numbers are the cleaner
comparison.)

## Did transfers go down? Mostly no.

The fair test holds the commutes fixed: for every zone pair that both networks can serve,
the transfers on the model's best path, weighted by commuters.

| Same commutes | Transfers per commute | Two or more | Fewer / more transfers | Newly served |
|---|---|---|---|---|
| Plan, 2100 | 0.327 -> 0.335 | 2.1% -> 2.2% | 11k / 21k | 27k |
| 2M, 2050 | 0.372 -> 0.381 | 4.3% -> 3.8% | 83k / 92k | 309k |
| 2M, 2100 | 0.465 -> 0.471 | 6.2% -> 6.2% | 36k / 43k | 32k |

The changes add riders by making trips faster and reaching new areas. Transfers per commute stay
about level because the model's transfer penalty is 3 minutes, the low end of practice. A new
interchange lets many riders trade a slower one-seat ride for a faster trip with one change.
Three-seat rides do fall where a one-seat link appears: SH-114 through to Victory, the Stemmons
BRT from Victory, and 2M's share of commutes needing two or more transfers in 2050.

**Left for later (owner):** a longer transfer penalty (5-8 min). It would make the model value
one-seat rides more, and lower the headline numbers (-7.6% at 8 min in the 2026 review). It is
a model change with its own recalibration.
