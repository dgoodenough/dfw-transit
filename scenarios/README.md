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
