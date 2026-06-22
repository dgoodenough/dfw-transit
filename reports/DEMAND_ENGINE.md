# Demand Engine — Session A Results

*Ridership-proxy engine built per NEXT_SESSION_PLAN.md. Re-run:
`data/run_demand.ps1` (compiles `data/DemandEngine.cs` inline; all-pairs +
827k OD pairs evaluate in ~2 s). Inputs: 2022 LODES OD (11.6M rows → 3.32M
metroplex commutes across 827k tract-pairs), unified DB graph.*

## Model
Line-aware graph from `db/`: ride edges per segment-line using the **spacing-
dependent speed model** (segment time = length ÷ cruise + per-stop penalty;
cruise 63 / BRT 38 / commuter 72 km/h, stop penalty 1.2 / 0.9 / 1.4 min — same
model as the trip planner and map), board 6 min, transfers via street nodes +
400 m walk links (6 min), tract access = walk ≤1.5 km or P&R drive ≤8 km to
commuter/terminus stations. Drive baseline = **peak** door-to-door
(38 km/h ×1.35 routing + 8 min terminal). **Competitive** = transit ≤ 1.3×drive
+5 min, ≤90 min, trips >2 km only.

> **Updated:** speeds synced from the old flat values (metro 32 / BRT 22 /
> commuter 50) to the spacing model so the demand engine, trip planner, and map
> agree. This made transit faster on sparse-stop (esp. commuter) segments,
> roughly doubling addressable demand and — usefully — making the calibration
> *more* realistic (see below). Full current rankings: `data/line_ranking.csv`.

## Calibration (existing network only)
**160,892** addressable daily commutes vs. ~70k actual daily rail boardings
(DART LRT ~60k, TRE ~7k, TexRail ~5k, A-train ~1.5k) → implied **~44% capture**
of competitive trips — a realistic mode-share for "transit-competitive" O-D pairs
(the old flat-speed run implied ~87%, implausibly high). **Trust the relative
rankings over the absolute counts.** ⚠️ A first run with free-flow driving
(55 km/h) produced nonsense (0.2% competitive) — the peak-conditions drive
baseline is the model's biggest lever.

## Headline: full 2070 network = 376,436 addressable commutes (2.3× existing)
*(Numbers below predate the speed sync and are kept for shape; the live ranking
is `data/line_ranking.csv` — top proposed lines now: TexPress 47.6, SE TexRail
43.2, Ross BRT 38.2, TexRail-3rd 38, FTW/Denton 29.2 commutes per $M.)*

### Proposed lines ranked by value (commutes per $M capital)
| Line | Mode | km | $M | Commutes | per $M |
|---|---|---|---|---|---|
| TexPress Expansion (Cleburne) | commuter | 21 | 210 | 6,249 | **29.8** |
| Alvarado Line | commuter | 45 | 447 | 10,567 | **23.6** |
| Terrell Line | commuter | 55 | 553 | 9,701 | **17.5** |
| SE TexRail | commuter | 28 | 280 | 2,504 | 8.9 |
| Sherman Line | commuter | 92 | 922 | 7,332 | 8.0 |
| FTW/Denton | commuter | 46 | 455 | 3,314 | 7.3 |
| **Purple (TCU)** | metro | 7.7 | 1,155 | 7,843 | **6.8** |
| TexRail 3rd exp | commuter | 14 | 140 | 605 | 4.3 |
| **Orange (FW)** | metro | 27 | 4,050 | 14,653 | 3.6 |
| DNT-West | metro | 31 | 4,680 | 12,454 | 2.7 |
| Blue (FW) | metro | 24 | 3,600 | 8,881 | 2.5 |
| Teal (FW) | metro | 26 | 3,885 | 8,711 | 2.2 |
| DNT-East | metro | 65 | 9,690 | **18,493** (largest) | 1.9 |
| Ennis / Waxahachie | commuter | — | — | ~1k each | ~2.5 |

### What this says for Session B proposals
1. **Commuter-on-ROW is the best money in the plan** — the cheap freight-corridor
   lines (Cleburne, Alvarado, Terrell) should phase EARLY, not 2065–2070.
2. **Purple (TCU) is the best metro per dollar** — short, dense; early phase.
3. **FW Orange is FW's flagship** (14.7k); DNT-East is the region's biggest
   single ridership prize but pays metro prices for it.
4. **TRE is the backbone** (31.4k with the network feeding it) — anything that
   feeds or upgrades the TRE corridor compounds.
5. **Weak per OD data**: Ennis, Waxahachie, Gainesville/Bowie/Chico outer legs,
   and both Silvers (Arlington E23 at 0.66/$M) — phase late, shorten, or rethink.
6. **Missing corridors = Collin County**, overwhelmingly: Frisco/McKinney/
   Prosper → Plano/Legacy flows (5–7k per cell-pair, top 7 of 10), plus Cedar
   Hill→Dallas and intra-Dallas E–W. Your planning CSV's empty "Collin" rows are
   exactly where the data says to draw lines. (`data/missing_corridors.csv`)

## Honest limits
LODES = home→work only (undercounts Stockyards/airport/event demand — FW
tourism lines will rank below their true value). No congestion variation by
corridor. "Addressable ≠ ridden." Single-year (2022) — no growth; NCTCOG
forecasts (Tier 2) would re-weight outer lines upward. GTFS revealed-demand
check not yet run (Tier 2, optional).

## Files
`data/line_ranking.csv` (full table) · `data/missing_corridors.csv` ·
engine: `data/DemandEngine.cs` + `run_demand.ps1` · OD pipeline:
`build_od.ps1` → `od_tracts.csv`, `tract_centroids.csv`.
