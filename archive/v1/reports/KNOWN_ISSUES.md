# Known Issues & Backlog

Triage of the open items as of the latest build. Validation flags come from
`data/validate_network.ps1` (full list in `data/validation_flags.txt`).

## Validation flags — triage (8)

### Accepted (by design — not bugs)
A line has to end somewhere, and outer-edge termini / dedicated yards are real
infrastructure costs, not modeling errors.

- **V1 Pink → Everman** — line terminus at a town edge; no nearby transfer expected.
- **V1 Purple line → Lake Port Village** (Mansfield) — outer terminus.
- **V1 TexPress Expansion → Primrose** — rural Cleburne-corridor terminus.
- **V3 Mansfield Purple — yard spur needed (~8.7 km)** — realistic fixed-cost line
  item for an outer line; the validator is correctly surfacing the capital cost.
- **V3 Waxahachie Line — yard spur needed (~6.5 km)** — same.

### TODO (minor, fix via the geometry edit round-trip)
- **V2 Arlington Silver hairpin** @ 32.669,−96.961 — a >25° back-bend left by ROW
  snapping; cosmetic. Fix: nudge that vertex in `edit/dfw_lines.*` and re-import.
- **V1 Ross Avenue BRT → "Swiss Avenue Historic District E"** and
  **V1 Woodhaven direct → "Haltom City SE2"** — east ends left orphaned after the
  Silver corridor reroute. Re-tie to a nearby transfer or trim one stop.

## Name collision
- **"Silver" (FW core) vs "Silver" (extra Arlington)** share a name, so the map's
  line selector toggles both together. Permanent fix: rename the extra line (e.g.
  "Silver (Arlington)") in `build_extra.ps1` + `line_years.csv` +
  `corridor_share.ps1` (which references `'Silver'` for the Blue Ctd pairing). The
  edit round-trip already disambiguates the FW one via its " (core)" suffix.

## Backlog (each roughly a session)
- **Stylized / octolinear schematic** map (the "easy-read" version from the
  original project goal).
- **POI layer** on the interactive map.
- **Tier-2 demand data** — NCTCOG 2045/2050 TAZ growth forecasts (growth-aware
  phasing) + GTFS revealed-demand calibration against today's high-frequency
  corridors.
- **TCRP 155** — drop the real document in `refs/` to replace the approximated
  metro stop-spacing / curve-radius figures with cited numbers.
- **Curve-radius geometric validation** — build the alignment-curvature pass
  (FRA superelevation data already in `refs/`).

## Reproducibility note
- `build_db.ps1` and `analyze.ps1` still read the author's original design inputs
  from `C:\Users\justd\Downloads\` (FW subway KML, FW stations CSV). These are
  gitignored; the committed `db/fw_*.csv` let the rest of the pipeline run without
  them. For a clone-and-reproduce build, move those two files into the repo (e.g.
  `data/source/`) and repoint.
