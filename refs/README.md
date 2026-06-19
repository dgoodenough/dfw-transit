# refs/ — design-standard source documents

Drop the free PDFs here and I'll extract the exact tables locally (the Read tool
parses PDFs directly — no web gating). This is the reliable path: automated web
fetching of these is blocked (ITDP loads numbers in dynamic subsections, TRB
redirects PDFs to catalog pages and serves "read" pages as image scans, BART
returns 403).

## Free downloads — confirmed sources

| File to save here | Document | Where to download |
|---|---|---|
| `tcrp155_track_design.pdf` | TCRP Report 155 — Track Design Handbook for Light Rail Transit (2nd ed.) | nap.nationalacademies.org/catalog/14619 → "Download Free PDF" |
| `tcrp90_brt_v1.pdf` / `_v2.pdf` | TCRP Report 90 — Bus Rapid Transit, Vol 1 & 2 | nap.nationalacademies.org (search "TCRP Report 90") |
| `itdp_brt_standard.pdf` | ITDP — The BRT Standard | itdp.org/library/standards-and-guides/the-brt-standard/ |
| `itdp_brt_planning_guide.pdf` | ITDP — BRT Planning Guide | brtguide.itdp.org (online; design in Ch. 22 Roadway & Station Configs, Ch. 23 Roadway Design, Ch. 24 Intersections, Ch. 25 Stations) |
| `bart_bfs_design_criteria.pdf` | BART Facilities Standards — Facility Design Criteria | bart.gov/about/business/standards (download in a browser) |
| `fra_superelevation.pdf` | FRA — Mixed Freight & Higher-Speed Passenger Trains: Framework for Superelevation Design | railroads.dot.gov eLibrary (search the title) |
| `trec_commuter_rail_econdev.pdf` | TREC/PSU — Commuter Rail Transit and Economic Development | pdxscholar.library.pdx.edu (search the title) |

Paywalled (not here): **AREMA** Manual (Ch. 5 Track, Ch. 11 Commuter) — university
excerpts only; **APTA** Running Ways standard — membership/purchase.

## After you drop files
Ping me and I'll: (1) extract the exact numeric tables (curve radii, grades,
spacing, lane/track widths, platform), (2) replace the `[approx]` flags in
`../reports/DESIGN_STANDARDS.md` with cited figures, (3) add a curve-radius + spacing
conformance check to the build/validation.
