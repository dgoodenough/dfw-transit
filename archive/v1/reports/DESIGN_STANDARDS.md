# DFW Transit — Design Standards & Best Practices

Reference library + the **applied design parameters** I should conform to when
generating, routing, and validating lines and stations. When the user says
"best practices," this is the intended basis.

> ⚠️ **Provenance flags.** Values marked **[std]** are well-established figures
> from these standards / common practice. Values marked **[approx]** are my
> distillation and should be checked against the actual document before being
> treated as authoritative. Several primary docs are **paywalled** (AREMA, APTA) —
> see Access notes. I have **not** ingested the full PDFs; this captures the
> design intent so the modeling respects it.

---

## Quick reference — parameters to apply

| Parameter | BRT | Commuter Rail | Metro / Heavy & Light Rail |
|---|---|---|---|
| **Station spacing** | **[cited]** ITDP 2024: optimal avg ≈**450 m**, scoring band **0.3–0.8 km** in built-up areas (non-built-up excluded) · TCRP 118 (US practice): arterial **0.25–1.2 mi**, most >0.5 mi; busways **0.6–1.3 mi**; "wide spacing desirable except downtown"; P&R at outlying stations | **[cited]** Nelson/TREC empirical: **~3.5–10 mi** between stations (19 stn/70 mi; 8/42; 9/80); station walkshed defined as **0.5 mi**; systems reach 10–100 mi from downtown | 0.5–1.0 mi (≈**800–1,600 m**) [approx — TCRP 155 still missing, see note]; ~½ mi urban core |
| **Min horizontal curve radius** | bus turning, not track | mainline large; ~**1,000+ ft** for speed [approx, AREMA] | LRT absolute min ~**25 m (82 ft)** constrained, mainline **≥150 m** [approx, TCRP 155]; heavy rail larger |
| **Transition (spiral) curves** | n/a | required on curves [std, AREMA] | required tangent↔curve [std, WMATA/TCRP 155] |
| **Lane / track width** | dedicated lane **3.3–3.5 m** (11–12 ft) [std, APTA] | track centers ~**14 ft (4.3 m)** [approx, AREMA] | LRT track centers ~**12–14 ft**; gauge **4 ft 8½ in** [std] |
| **Max grade** | road grade | ~**1.5–2%** sustained (freight-shared) [approx, FRA] | LRT ≤**4–6%**, heavy rail ≤**3–4%** [approx, TCRP 155] |
| **ROW / alignment** | **dedicated, median-running** preferred (ITDP "gold") [std] | **shares freight ROW**; superelevation balances mixed speeds [std, FRA] | exclusive ROW; follow existing rail/road corridors |
| **Platform** | level boarding, off-board fare [std, ITDP] | low or high, train-length | high platform, train-length (e.g. DART ~3-car) |

**Current build knobs vs. target** (`data/build_stations.ps1`):
- BRT spacing **1,200 m** → within 0.3–0.8 mi band but at the high end; **tighten to ~800 m in dense core**.
- Metro spacing **1,500 m** → top of 0.5–1 mi band; **~1,000–1,200 m would be more urban**. (Density-anchoring already pulls stations to real nodes, which is good.)
- Commuter **6,000 m** outside core + **3,500 m** in-core → squarely in the 2–5 mi band. ✓ Town-centers-only outside core matches commuter land-use criteria. ✓
- No curve-radius check yet — the ROW router follows real track (inherits real radii); hand-drawn metro/BRT spurs do **not** yet respect min radii.

---

## References by mode

### 1. Bus Rapid Transit (BRT)
- **ITDP — The BRT Planning Guide** & **The BRT Standard** (scoring: Gold/Silver/Bronze).
  Global gold standard. Governs: dedicated/median lanes, station spacing,
  intersection geometry, turn radii (standard & articulated buses), off-board
  fare, platform-level boarding. *Free online.*
- **APTA — Designing BRT Running Ways (APTA-BTS-BRT-RP-003-10).**
  Engineering geometry: cross-section dimensions, lane widths, ROW isolation,
  running-way types. *APTA member / purchase.*
- **TCRP Report 90 — Bus Rapid Transit** (Vol 1 & 2).
  Foundational US doc: system capacities, route configurations, station layouts,
  performance metrics. *Free PDF (TRB).*

### 2. Commuter Rail
- **FRA — Mixed Freight and Higher-Speed Passenger Trains: Framework for
  Superelevation Design.** Curve geometry physics on shared corridors:
  superelevation (banking), unbalance, curve speed limits. *Free (FRA).*
- **PSU / TREC — Commuter Rail Transit and Economic Development.**
  Planning criteria: **station spacing averages 2–5 miles**, land-use needed to
  justify a stop. *Free (PDX Scholar).*
- **AREMA Manual for Railway Engineering** — Ch. 5 (Track), Ch. 11 (Commuter &
  Intercity Rail). North American legal standard: degree of curve / turn radii,
  track spacing, clearances. *Paywalled; university excerpts of Ch. 5 & 11 exist.*

### 3. Metro / Heavy Rail Transit
- **TCRP Report 155 — Track Design Handbook for Light Rail Transit** (TRB).
  600+ pp; applies to heavy rail too: wheel/rail interface, gauge, horizontal &
  vertical alignment, curve radii, turnouts, special trackwork. *Free PDF (TRB).*
- **BART Facilities Standards (BFS) — Facility Design Criteria.**
  Full engineering standard online: track alignment, clearance/train-control
  envelope, platform widths, station spacing. *Free PDFs.*
- **WMATA Manual of Design Criteria.**
  Heavy-rail clearance templates, spiral curves, track spacing, structural
  support (underground + elevated). *Public via procurement packages.*

> Also relevant to this project's existing rules: **NACTO Transit Street Design
> Guide** (BRT/streetcar in mixed traffic) and **TCRP Report 100 (Transit
> Capacity & Quality of Service Manual)** for headways/capacity.

---

## Uploaded to `refs/` (Jun 10 2026) — parsed locally
- ✅ **ITDP BRT Standard 2024** — spacing band extracted (above).
- ✅ **TCRP Report 118 — BRT Practitioner's Guide (2007)** (`23172.pdf`) — US spacing practice extracted. (Bonus doc — even better for siting than TCRP 90.)
- ✅ **Nelson/TREC — Commuter Rail Transit & Economic Development** — empirical spacing + 0.5-mi station-area definition extracted.
- ✅ **BART Standard Specifications R3.2.3 (May 2025)** — construction specs (Divisions); useful for engineering detail later, not stop siting.
- ✅ **FRA Superelevation (DOT/FRA/ORD-19/42)** — shared-corridor curve physics; for future alignment/speed checks, not stops.
- ❌ **`14619.pdf` is the WRONG document** — it's "Sustainable Pavement Maintenance Practices." My README pointed at the wrong NAP id; **TCRP 155 (Track Design Handbook for LRT) is still missing** — metro spacing/curve numbers remain [approx]. Correct source: search "TCRP Report 155 Track Design Handbook" at nap.nationalacademies.org (record 22800).

## Access notes & retrieval status
**Tried to auto-pull the free ones (Jun 2026) — blocked for bots:** ITDP loads
its numbers in dynamic subsections (chapter pages return intros only); TRB /
National Academies redirect PDFs to catalog pages and serve "read" pages as image
scans (no extractable text); BART returns HTTP 403; WebSearch was rate-limited.
So the table above is still design *intent*, not lifted figures.

**Confirmed canonical sources** (download the PDFs into `refs/` and I'll parse
them locally — that bypasses all the gating):
- TCRP 155 Track Design Handbook for LRT (2nd ed): `nap.nationalacademies.org/catalog/14619`
- ITDP BRT Planning Guide (online): `brtguide.itdp.org` — design in Ch. 22
  (Roadway & Station Configurations), 23 (Roadway Design), 24 (Intersections &
  Signal Control), 25 (BRT Stations)
- ITDP BRT Standard: `itdp.org/library/standards-and-guides/the-brt-standard/`
- BART Facilities Standards: `bart.gov/about/business/standards` (browser download)
- TCRP 90/100: nap.nationalacademies.org · FRA superelevation: railroads.dot.gov
  eLibrary · TREC: pdxscholar.library.pdx.edu
- **Paywalled:** AREMA Manual (Ch. 5/11 university excerpts), APTA Running Ways.

→ Next: drop the free PDFs in `refs/` (see `refs/README.md`), or I can retry
WebSearch after the limit resets to find directly-fetchable mirrors.

---

## How this maps to the project's routing rules
The existing four rules (commuter follows existing rail; minimize river tunnels;
metro follows existing ROW; BRT only existing ROW) are consistent with these
standards. Concrete upgrades these enable:
1. **Station-spacing conformance** — set per-mode spacing to the bands above;
   the generator already supports per-mode spacing.
2. **Curve-radius sanity check** — flag any hand-drawn metro/BRT segment whose
   local radius is below the min (a check I can add to the validation pass).
3. **Superelevation / shared-corridor realism** — commuter speeds/curves where
   freight-shared; informs which corridors can be "higher-speed."
4. **BRT quality scoring** — rate proposed BRT against ITDP (dedicated %,
   median-running, station spacing, intersection treatment) rather than just
   drawing a line.

*If you want, point me at the free ones (BART BFS, TCRP 155/90) and I'll pull the
specific numeric tables and wire conformance checks into the build/validation.*
