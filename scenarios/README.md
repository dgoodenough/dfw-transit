# Scenarios

A scenario is an alternative to the plan in `network/`. Each folder can hold:

- any of the network tables (`lines.csv`, `stations.csv`, `line_stops.csv`,
  `line_segments.csv`, `service.csv`, `transfers.csv`); each one present
  replaces the base table wholesale, and
- an `edits.csv` of small overrides applied on top:

| op | target | field | value |
|---|---|---|---|
| `set_line` | line_id | column (`name`, `mode`, `color`, ...) | new value |
| `set_line_year` | line_id | | first opening year (the whole line shifts) |
| `shift_line_years` | line_id | | years to add to every stop and segment |
| `set_headway` | line_id | from year | minutes between trains/buses |
| `drop_line` | line_id | | |

`python -m dfwt build` evaluates the plan and every scenario and writes a
side-by-side comparison to `reports/SCENARIOS.md` and the map.

| Scenario | What it is |
|---|---|
| `v1_baseline` | The v1 plan exactly as it was before the panel review (full copy of the migrated v1 tables, no service upgrades, no extra transfers). |
| `v2_phasing` | The v2 plan's hand-set phasing from before the optimizer's build order was adopted (its `stages.csv`). |
| `right_sized` | Step A8: the three long suburban metro lines (SH-360, I-30, I-20 Crosstown) built as BRT instead. |
| `lever_expand_jobs` | Expansion lever, 2075-2090: SH-114 light metro (Farmers Branch - Freeport - DFW north - Grapevine - Southlake - Westlake), Coppell-Lewisville, Stemmons-Brookhollow and Dallas Parkway BRT, and 8 infill stops where existing track passes big job zones. |
| `lever_expand_brtgrid` | Expansion lever, 2075-2090: 31 arterial BRT corridors (~520 km) filling the residential coverage gaps the rail plan leaves. |
| `lever_expand_core` | Expansion lever, 2075-2090: urban-core metro (Dallas inner loop, Polk-Greenville second downtown trunk, Collins St in Arlington). Kept as the comparison: poor value per $ in this model. |
| `lever_expand_package` | Recommended expansion: `jobs` + `brtgrid` + 14 phase-2 BRT corridors, moved 10 years earlier (2065-2090) into the budget the plan leaves unspent after 2060. |
| `lever_expand_max` | Upper bound: `package` + `core`. |

The `lever_expand_*` folders are generated: edit `corridors.json` and run
`python tools/gen_expansion.py <name>` to rebuild their tables (a scenario that
includes another must be rebuilt after it).
