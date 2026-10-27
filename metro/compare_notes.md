## Reading

*(Hand-written from the run of 2026-10-27; `python -m metro check-dfw` regenerates every number on this
page except this section, which it copies from `metro/compare_notes.md`.)*

**Outcomes: about the same network value per dollar.** Given the 2M plan's $169B, the generator found
$116B of corridors worth building before its candidates ran out (the other 700-odd candidates
duplicate a chosen or existing line, are too thin for any mode, or are the wrong length). With
69% of the capital it reaches the same share of residents (30.5% vs 30.7% within 800 m of a
station) and jobs (55% vs 56%), the same jobs-in-45-minutes for the average resident (68.0k vs
69.1k), and 73% of the hand plan's added daily trips (+171k vs +235k on today's land use), so
slightly more trips per $M (1.47 vs 1.39). That is the main evidence the method is sensible:
built from nothing but zones, roads and rail, it produces a network the DFW model values about
as highly as the hand plan.

**Where it agrees.** The regional skeleton is the same: the Dallas North Tollway / Legacy corridor
as metro (hand E16 DNT West, E17 DNT East, E26 Legacy Line ~ generated G21/G33, 56-100% within 1 km
of generated metro), Mansfield-Denton-Carrollton and Weatherford regional rail (E07, E40: 99-100%),
a Las Colinas-Dallas-Terrell rail line beside the TRE/I-30, I-30 between the two downtowns,
Mesquite, and much of the Beltline and Coit Road BRT. Every hand-plan metro line but SH-360 (47%) has
generated track (of some mode) within 1 km along at least half of it.

**Where it differs: mode, not place.** The hand plan builds 580 km of metro, the generator 267 km
(and 1,230 km of BRT to the hand plan's 1,135). On today's land use most of the hand plan's long
suburban metro corridors (SH-360 4,300, I-20 Crosstown 5,000, I-30 6,100, SH-114 6,100 people + jobs
per route-km) are below the 7,000 metro threshold, so the generator runs BRT or regional rail
there; the hand plan chose metro for 2100's population, station-area growth and capacity, which
the generator (one year, today's land use) does not see. Only 171 km of the hand plan's metro lies
near generated rail transit. Fort Worth is the clearest case: its density gives the generator few
centers, so it serves Fort Worth with one metro line (near FW Pink and Orange), BRT and regional rail where
the hand plan draws a seven-line metro network.

**What it misses.** The long regional rail lines to Gainesville, Bowie and Sherman (300 km): those
towns lie outside the nine counties the zones cover, so the generator never sees them. Several
outer regional-rail branches (Ennis, Midlothian, Greenville) only partly.

**How much of the overlap is chance.** The hand plan blankets urban DFW: 68% of residents of
urban-density zones live within 1 km of its new track. Generated track lies within 1 km of hand
track 69% of the time, about chance; within 500 m 51% against 41% by chance. So line-by-line
"matched" verdicts below overstate agreement: both networks cover the same dense places (which is
what the coverage and ridership numbers show), but the generator's exact streets and freeways are
its own. The corridor tables are for inspecting individual lines, not a score.

**Known weaknesses this shows.** (1) Today's land use only: the generator under-builds metro
where growth is planned. (2) Single-line sketch values: trips needing transfers count only in the
model run, which favours many cheap BRT lines over a few trunk lines. (3) Center names are the
nearest cross streets, so line names read oddly. (4) Routed geometry is a corridor, not a design
alignment (CURVE_RADIUS warnings; `python -m dfwt align` would fit it).
