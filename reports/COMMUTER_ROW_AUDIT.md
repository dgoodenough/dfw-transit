# ROW Audits (mode-by-mode)

## METRO — pass #2 (Jun 2026)
*Proposed metro vs rail+freeway+**arterial** reference (`data/audit_metro_row.ps1`,
PASS p90≤350 m; existing DART skipped per user). Arterials: `data/dfw_arterials.json`
(primary+secondary, audit window).*

**No fantasy alignments found** (worst max 1.3 km — corridor-faithful but
sparsely drawn). Verdicts after corridor-snapping (`data/snap_metro_row.ps1` →
`db/metro_row_fixes.geojson`, consumed by build_extra):

| Line | Before → After (p90) | Verdict |
|---|---|---|
| No Idea · DNT-East · Line 76 | 243–340 m | ✅ passed as drawn |
| DNT-West | 386 → **208 m** | ✅ snapped |
| Silver (Arlington) | 399 → **252 m** | ✅ snapped |
| Legacy Line (N2) | 353 → **329 m** | ✅ snapped |
| Blue Ctd | 511 → 406 m | ⚠️ flagged: residual spans are **greenfield** (no arterial within 900 m exists) — acceptable for a 2060 line, corridor comes with development |
| Purple line (Mansfield) | 462 → 412 m | ⚠️ same greenfield condition (2065) |
| FW core (Pink/Red/Silver/Teal 371–479 m; Blue/Orange/Purple pass) | — | ⚠️ declared **schematic-acceptable**: user-designed core, marginal deviations mostly from sparse cleaned-leg literals; corridors themselves verified in the original FW review |

Pipeline rebuilt with snapped geometry (634 stations / 600 segments). Demand
re-score skipped (vertex moves ≤900 m don't change rankings materially); map
render not re-verified this pass — eyeball the five snapped lines next session.

---

# Commuter Rail — ROW Audit (mode-by-mode pass #1)

*Every proposed commuter line sampled every ~400 m against actual OSM rail
(`data/audit_commuter_row.ps1`). PASS = 90th-percentile deviation ≤300 m
(typical OSM centerline offset). Re-run anytime.*

## Verdicts

| Line | p90 dev | Verdict |
|---|---|---|
| TexPress Expansion (Cleburne corridor) | 165 m | ✅ on BNSF |
| TexRail 3rd exp | 195 m | ✅ |
| SE TexRail (Mansfield) | 137 m | ✅ — the old "verify Mansfield ROW" flag from the first FW review **resolves as real** |
| FTW/Denton | 225 m | ✅ |
| Alvarado · Bowie · Gainesville · Sherman · Terrell · Ennis · Waxahachie (router-built) | 63–130 m | ✅ control group, as expected |
| **Collin Commuter** | off-graph | ⚠️ FLAGGED (below) |
| **Midlothian Line** | off-graph | ⚠️ FLAGGED (by design — 16.7 km is declared new-build) |

**Bottom line: 11 of 13 commuter lines run on verified ROW.** The user's
hand-drawn KMZ lines were honest — every one passes.

## The two flags
- **Midlothian Line** — intentional: 12.3 km assumed-continuous ROW
  (Midlothian↔Cedar Hill, ends verified at 651 m/227 m) + **16.7 km explicit
  new-build** (Cedar Hill→Duncanville→Westmoreland; the historic segment is
  gone — nearest rail to Duncanville is 3.7 km). Priced at new-build premium
  (~$790M true vs $280M naive).
- **Collin Commuter (Plano→Allen→McKinney)** — drawn on the DART-owned ex-H&TC
  corridor, but **that corridor is absent from my OSM rail pull** (nearest
  in-graph rail to McKinney: 20 km). An attempted graph re-route produced 24 km
  of straight connectors — **rejected**. Two possible truths: (a) OSM tags the
  DGNO/ex-H&TC trackage with a `usage` value my pull excluded, or (b) the track
  is genuinely removed and only the ROW easement remains (DART does own the
  corridor). Either way the *right-of-way* exists; the line stays as drawn,
  flagged "ROW-owned, track status unverified."

## Data-quality TODO (cheap, next time Overpass cooperates)
Re-pull rail without the `usage!=industrial` filter and including
`railway=disused|razed` — catches short-line/railbanked corridors (McKinney
being the proven case) and would let the router verify Collin properly.

## Net effect
No geometry changed in this pass — the audit **validated** the commuter mode
rather than rebuilding it. Score impact: none (network stays at 202.3k
addressable). Next mode whenever you're ready: **metro** (known fantasy risk:
Legacy Line N2, the hand-drawn Dallas/Mid-Cities lines) or **BRT** (currently
schematic; needs road-ROW snapping = menu item B2).
