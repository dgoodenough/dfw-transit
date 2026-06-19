# Proposed-Stop Conformance Pass — vs. Uploaded Design Standards

*All 463 proposed (non-existing) inter-station segments evaluated against the
cited spacing standards extracted from `refs/`. Full per-segment verdicts in
`data/stop_conformance.csv`. Re-run: `data/build_conformance.ps1`.*

## The standards applied (now cited, not approximated)
| Mode | Band used | Source |
|---|---|---|
| BRT | too-close <300 m · ok 0.3–1.9 km · wide >1.9 km | **ITDP BRT Standard 2024**: optimal avg ≈450 m, scoring band 0.3–0.8 km (built-up only) · **TCRP 118**: US arterial practice 0.25–1.2 mi, busways 0.6–1.3 mi |
| Metro | too-close <600 m · ok 0.6–2.5 km · wide >2.5 km | industry band — **TCRP 155 still missing** (the uploaded 14619.pdf is a pavement doc, wrong NAP id — my earlier error) |
| Commuter | too-close <2.4 km · ok 2.4–16 km · wide >16 km | **Nelson/TREC** empirical: ~3.5–10 mi spacing; 0.5-mi station walkshed |

## Two root-cause fixes applied during the pass (regenerated everything)
1. **Commuter dedup radius 700 m → 2.5 km** — termini and their town-center pins
   now merge. Killed the `Gainesville`+`Gainesville 2` / `Burleson 2` /
   `Watauga 3` duplicates → **commuter too-close violations: 3 → 0**.
2. **Gap guard on station pruning** — zero-activity stops are no longer pruned if
   removal opens a >3.5 km hole on a metro/BRT line. Killed the 17.4 km and
   15.7 km phantom gaps on Beltline/Mansfield-Purple → **+25 stations retained**
   (network now 624 stations / 590 segments).

## Results after fixes
| Mode | ok | too-close | wide |
|---|---|---|---|
| Metro | 266 | 7 | 33 |
| BRT | 26 | 0 | 56 |
| Commuter | 64 | 0 | 11 |

## Verdicts, called honestly

### Metro "too-close" (7) — mostly fine, one real call for you
All 7 are **FW downtown/CBD pairs at 371–595 m**. CBD spacing of 350–600 m is
normal practice (DART's downtown transit mall runs ~400 m), so most are **false
positives of the band**, *not* stations to drop — Courthouse↔Sundance (both
~46k activity) stays, W 7th E↔W (32k) stays, Magnolia W↔Medical City (25k) stays.
**The one genuine candidate:** the **T&P → S Main → S Main S chain** — three
stations, *each* only ~4.9k activity, packed into ~900 m. Consolidating to one
(keep T&P, the historic intermodal anchor) would be standard practice. Your call
— they're your hand-placed FW stations.

### BRT "wide" (56) — systematic, by design tension
Most BRT segments run 1.9–3.4 km — **wide of the ITDP 0.3–0.8 km band but close
to TCRP 118 US busway practice (1.0–2.1 km)**. The two standards genuinely
disagree; ITDP describes core urban BRT, TCRP describes US suburban busways.
Reading: your suburban BRT (Crosstown Loop, 183) is defensible per TCRP; if any
BRT corridor is meant to be *urban* BRT (Race St, Lancaster), it needs roughly
2× the stations to be ITDP-credible. This is a **policy choice to make once**,
then I can apply it.

### Metro "wide" (33) — your hand-designed suburban stretches
Top gaps are all on the FW network you drew: Waterside↔Hulen (6.6 km),
La Gran Plaza↔Everman (6.5), the Silver line legs (5.2–5.7), Benbrook↔Waterside
(5.6), Handley↔Oakland Corners (4.3). These read as **deliberate
express/suburban legs** — fine to keep, but each is an infill opportunity
(act data in the DB will say where). No action taken.

### Commuter "wide" (11) — the honest outliers
Rural runs of 17–54 km. Nelson's empirical ceiling is ~10 mi (16 km) between
stations; the outer **Bowie (45.9 km), Chico (52.3), Sherman (45.5),
Gainesville (54.1)** legs blow far past anything in US practice. Two readings:
(a) they're **intercity, not commuter** — real-world analog is an Amtrak-style
flag-stop service, or (b) they need **intermediate small-town stops** (Alvord,
Valley View, Krum, Van Alstyne are on those corridors but weren't in my OSM
town pull). Mid-band gaps (Midlothian↔Waxahachie 17.6, Forney↔Terrell 18.7,
Denton↔Roanoke 25.5) would close naturally with one added town each.

## Recommended next actions (pick any)
1. Decide the **T&P/S Main consolidation** (one-liner from you, I apply).
2. Decide the **BRT identity** per corridor (urban-ITDP vs suburban-TCRP) — I
   then re-space BRT stations accordingly.
3. **Add the missing small towns** on the long commuter legs (widen the OSM
   place pull to `place=village`, re-snap) — fixes most commuter wides honestly.
4. Drop the correct **TCRP 155** PDF into `refs/` (NAP record for the *Track
   Design Handbook for Light Rail Transit, 2nd ed.*) and I'll replace the metro
   band with cited numbers.
