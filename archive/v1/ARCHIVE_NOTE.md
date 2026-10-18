# v1 snapshot (frozen)

This folder is an untouched copy of the project as it stood at commit `ad6a4cb`
("Rewrite README as a PM-focused case study"), before the v2 re-engineering.

- `db/` — the four v1 source-of-truth tables + geojson exports
- `data/` — the v1 PowerShell/C# pipeline (`build_*.ps1`, `DemandEngine.cs`,
  `RoadRouter.cs`) and its inputs
- `maps/` — the v1 interactive map, time-series and Phase One renders
- `reports/` — v1 analysis notes
- `edit/` — v1 editable line geometry

The v1 scripts resolve paths relative to their own folder, so they still run
from here on Windows PowerShell (`archive/v1/data/build_app.ps1`). Nothing in v2
reads from this folder except `tools/migrate_v1.py`, which converted it into the
normalized `network/` tables. The same v1 phasing is also re-evaluated by the v2
engine as the `v1_baseline` scenario, so the two plans can be compared side by side.
