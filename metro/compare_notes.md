## Reading

*(Hand-written from the run of 2026-11-12; `python -m metro check-dfw` regenerates every number on this
page except this section, which it copies from `metro/compare_notes.md`.)*

This run is the sketch greedy (the generator's selection to the budget), without the line planner's
full-model search or the crowding check, which need the full model. It includes the generator's
November changes that apply to the sketch: metro tunnels only within 0.8 km of downtown, elevated to
1.5 km and at grade beyond (`candidates.hop_grade`), and terminal costs where a line ends downtown.

**Outcomes: as much value per dollar as the hand plan, and a little more of it.** Given the 2M plan's
$169B, the generator spends $167.7B at its own costing ($177.7B at dfwt's costing, the column above). It reaches more residents (33.9% against 30.6% within 800 m of a
station) and jobs (60% against 56%), more jobs in 45 minutes for the average resident (136k against
123k), and 5% more trips than the hand plan on today's land use (338k against 322k), so about the same
trips per $M (1.46 against 1.44). Built from nothing but zones, roads and rail, it produces a network
the DFW model values as highly as the hand plan. In October's run, before the cheaper grades and the router's changes, it found only
$116B worth building and 73% of the hand plan's added trips.

**Where it agrees.** The regional skeleton is the same, and now the mode mostly is too: 617 km of
metro against the hand plan's 580 (October: 267). Every hand-plan metro line has generated track
within 1 km along at least half of it but FW Berry (35%): 555 of its 580 km. The Dallas North Tollway
and Legacy corridors, I-30 between the downtowns, Mesquite, Fort Worth's Pink line, and most of the
Beltline, Coit Road and arterial BRT match. Of 77 hand lines with new track, 56 match, 15 partly, 6 are
missed; of 96 generated lines none runs where the hand plan has nothing.

**Where it differs.** BRT: 1,822 km against 1,154. The generator still prefers many cheap BRT lines
(its sketch values single lines, so trips needing a transfer count only in the model run), and it
runs BRT where the hand plan has metro in Fort Worth (Green, Orange, Purple are matched by place, not
by mode: 21-44% near generated rail transit). Fort Worth's density still gives it few centers.

**What it misses.** The long regional rail lines to Bowie, Gainesville and Sherman (300 km): those
towns lie outside the nine counties the zones cover, so the generator never sees them. The outer
branches to Ennis, Midlothian and Greenville, and Mansfield-Denton-Carrollton and TEXRail, only partly.
Three BRT lines on the edges: White Settlement, North Fort Worth-Alliance and Matlock-Mansfield.

**How much of the overlap is chance.** The hand plan blankets urban DFW: 68% of residents of
urban-density zones live within 1 km of its new track (41% within 500 m). Generated track lies within
1 km of hand track 69% of the time, about chance; within 500 m 51% against 41%. So line-by-line
"matched" verdicts below overstate agreement: both networks cover the same dense places (which is
what the coverage and ridership numbers show), but the generator's exact streets and freeways are
its own. The corridor tables are for inspecting individual lines, not a score.

**Known weaknesses this shows.** (1) Today's land use only: the generator sees none of the growth
the hand plan builds for. (2) Single-line sketch values favour BRT over trunks; the line planner
on the full model is the fix and isn't in this run. (3) Center names are the nearest cross streets, so
line names read oddly. (4) Routed geometry is a corridor, not a design alignment (CURVE_RADIUS
warnings; `python -m dfwt align` would fit it).
