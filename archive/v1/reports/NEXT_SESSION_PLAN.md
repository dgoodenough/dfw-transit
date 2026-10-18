# Next Sessions: Demand Engine → Line & Stop Deep-Dive

## ⚙️ SESSION A FIRST — "Demand engine" prep (approved, runs autonomously)
Build the ridership-proxy engine so the deep-dive proposals are defensible:
1. **Travel-time network model** over the existing DB graph — mode speeds
   (metro ~32 km/h, BRT ~22, commuter ~50 incl. stops), ~7 min transfer penalty,
   walk access; transit time vs. drive-time estimate for any OD pair.
2. **LODES OD flows** (LEHD `tx_od_main_JT00.csv.gz`, same source family as the
   WAC jobs pull) filtered to metroplex counties → real home→work block flows.
3. → **Ridership proxy per line**: daily commutes made transit-competitive
   (≤1.3× drive time). **Calibrate against existing DART** vs. its actual
   ridership; report the error honestly.
4. **Tier 2 if time**: DART + Trinity Metro **GTFS** (revealed-demand corridors,
   real platform locations); **NCTCOG 2045/2050 TAZ forecasts** (growth-aware
   phasing, grounds the latent-density thesis). Tier 3 (ACS zero-vehicle, OSM
   parking polygons) only if cheap.
5. Output: ranked line table (ridership proxy ÷ cost/km by mode: BRT ~$20M,
   LRT ~$75M, metro ~$200M, commuter-on-ROW ~$10M/km) + missing-corridor scan
   (high OD flows with no proposed service).
*Known limits to state in outputs: LODES = commute-only (undercounts
Stockyards/stadium/airport demand); no congestion model; ranking tool, not
forecast.*

## 🎯 SESSION B — Deep-dive: Claude PROPOSES lines/years/stops with reasons
attached (ridership, cost, dependency), user vetoes/adjusts via the R/B/L menu
below. The menu items remain live — engine results may resolve several
automatically (e.g. R4 infill, L1 years, B1 mode identity).

*Tee-up written 2026-06-10. Goal: maximum decisions per token. Review the three
files below offline, then open the next session with one-liner verdicts on the
numbered items (e.g. **"R1 keep T&P only · R3 yes · R4 Hulen only · B1 loop=suburban"**).
I'll batch-apply everything in one regeneration pass.*

## Review offline before the session
| File | What it tells you |
|---|---|
| `data/line_review.csv` | Per line: mode, #segments, year range, avg/min/max spacing, conformance flag count |
| `data/stop_conformance.csv` | Per segment: spacing verdict + drop/infill recommendation |
| `stop_conformance_report.md` | The narrative version with my honest read of each finding |
| `FW_map_interactive.html` | The map itself (click stations for act/years) |

---

## Edit menu — reply with item numbers + verdicts

### Stations
- **R1 — T&P / S Main / S Main S chain** (FW core): 3 stations, each ~4.9k act,
  within ~900 m. Options: (a) keep T&P only, (b) keep T&P + S Main S, (c) leave.
- **R2 — FW CBD close pairs** (Courthouse↔Sundance etc., 371–595 m): my verdict
  = false positives, keep all. Say "R2 agreed" unless you want changes.
- **R3 — Add small towns to long commuter legs** (Alvord, Valley View, Krum,
  Van Alstyne + whatever `place=village` finds): fixes most 17–54 km gaps.
  Yes/no (+ any towns to force-include).
- **R4 — Infill FW suburban metro gaps** (one station at the density peak of
  each): Waterside↔Hulen 6.6 km · La Gran Plaza↔Everman 6.5 · Silver legs
  5.2–5.7 · Benbrook↔Waterside 5.6 · Handley↔Oakland 4.3. Name which (or all/none).
- **R5 — Name the gap-guard survivors**: the >3.5 km-gap stations retained on
  Beltline/Mansfield-Purple still have generic names ("Stop 55"). I'd run the
  neighborhood-name fallback over them. Yes/no.

### BRT
- **B1 — Corridor identity, per corridor** (drives respacing): *urban-ITDP*
  (~0.5–0.8 km stops) vs *suburban-TCRP* (1–2 km, as-built). My suggestion:
  Crosstown Loop + 183 + Jacksboro = suburban; Race St + Lancaster/E Berry +
  Hemphill = urban. Confirm or amend per corridor.
- **B2 — Road-ROW snapping for BRT** (and metro spurs): apply the rail-router
  framework to OSM roads so BRT actually follows arterials (rule #4). Bigger
  job (~1 session on its own). Schedule or skip.

### Lines
- **L1 — Year hand-tune**: I produce a compact per-line year table (current
  auto-derived values from `line_review.csv` yr_min/yr_max), you reply with
  moves ("Sherman line → 2060", "stagger Silver to 2045"). Always available.
- **L2 — Outer commuter legs as intercity** (Bowie/Chico/Sherman/Gainesville):
  alternative to R3 — reclassify as a distinct "intercity/flag-stop" style
  (thinner dash, fewer stops is then *correct*). Choose R3, L2, or both-by-leg.
- **L3 — Kaufman**: no rail ROW exists (15 km gap). Drop the town, or accept a
  road-running connector as an exception. Decide.
- **L4 — Blue-West vs Teal shared trunk** (820 extension rides Teal's corridor
  west of downtown FW): keep as deliberate frequency trunk, or reroute Blue via
  White Settlement Rd for coverage. Decide.
- **L5 — Cleburne corridor duplication check**: the routed Cleburne ROW line and
  the KMZ "TexPress Expansion" may overlap south of FW. I'll diff and merge if
  confirmed. Yes/no to investigate.

### Standards
- **D1 — TCRP 155**: still missing (14619.pdf was a pavement doc). Drop the
  correct *Track Design Handbook for LRT, 2nd ed.* PDF in `refs/` and I'll cite
  real metro bands + re-run conformance.
- **D2 — Curve-radius checks** (FRA superelevation is in hand; AREMA still
  paywalled): build the geometric validation pass over all alignments. Schedule
  or skip.

---

## How I'll execute (one batch, in this order)
1. Apply station/line decisions as **generator edits** (not hand CSV edits — so
   they survive regeneration; the DB regen overwrites hand edits).
2. One pipeline run: `build_extra → build_rail_router (only if routes change) →
   build_stations → build_db_full → build_feasibility → build_app`.
3. Re-run `build_conformance` + render Existing/2050/2070 verification.
4. Update `stop_conformance_report.md` deltas + memory.

**Costs, roughly**: R1/R2/R5/L3/L4 are trivial; R3/R4/L1/L5 moderate (one regen
covers all); B1 moderate; B2 and D2 are each their own session.

## Open items not in this menu (parked)
Stylized/octolinear schematic · POI layer · offset crossing-minimization ·
in-core commuter stops on real TRE/TexRail platforms · AREMA/APTA excerpts.
