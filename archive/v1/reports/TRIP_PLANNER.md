# Trip Planner — Sanity-Check Layer

*Answers "how do I get from A to B, and how long?" over the unified DB, as a
journey itinerary. `data/plan_trip.ps1 -Origin <name|lat,lon> -Dest <...> -Year <YYYY>`.*

## What it does
Builds a line-aware time graph from `db/stations.csv` + `db/segments.csv` at a
chosen year: platform nodes + per-line nodes, ride edges (metro 32 / BRT 22 /
commuter 50 km/h incl. dwell), board/wait (metro+BRT 5 min, commuter 12 min),
walk access ≤1.6 km (else P&R drive ≤10 km), 400 m transfer walks. Dijkstra
ORIG→DEST, then reconstructs a labeled itinerary (walk · board/ride · transfer ·
walk) with a door-to-door total. **On "no route" it diagnoses the break** — how
many platforms are reachable and the closest the reachable network gets to the
destination.

## Validated examples (2070 network)
- **Frisco → Mesquite**: 2 h 15 min, DNT-East → Line 76, 1 transfer.
- **South Arlington → Dallas**: 1 h 49 min, Purple → Blue Ctd → Jefferson BRT,
  2 transfers.

## RESOLVED — FW commuter convergence (all western lines now meet downtown)
`data/converge_fw.ps1` rail-routes each FW-side commuter inner terminus into
**Fort Worth Central** along real ROW (these corridors meet at Tower 55); tails
in `db/fw_convergence.geojson`, appended to each line in `build_stations`, and a
hub-snap forces each converging line's downtown-most stop exactly onto Central.
**Fort Worth Central now carries TRE · TexRail · TexRail 3rd · SE TexRail ·
FTW/Denton · Bowie · Gainesville** — the western grand interchange.
**Bowie → Mesquite = 4 h 38 min** (Bowie Line → *FW Central* → TRE → *Dallas
Union* → Terrell Line → Mesquite; 3 vehicles, 2 transfers). Honest note: SE
TexRail's downtown stop was moved 2.16 km onto the hub (others ≤1.6 km).

## (historical) FINDING — Bowie → Mesquite was IMPOSSIBLE (disconnected network)
The planner returns NO ROUTE. Diagnosis: from Bowie only **12 platforms are
reachable** — the entire Bowie Line + Gainesville Line and nothing else. The
closest the reachable network gets to Mesquite is **Haltom City, 61 km short**,
where it dead-ends.

**Root cause:** the NW commuter pair (Bowie + Gainesville) is an **island**. Its
south terminus "Haltom City" sits **1.12 km from the FTW/Denton line's own
"Haltom City" station** and **1.13 km from TexRail's Mercantile Center** — but
the transfer threshold is 400 m, so no connection exists. Two same-named
"Haltom City" stations 1.1 km apart that should be one interchange.

**Recommended fixes (pick one — design decision):**
1. **Reroute the Bowie/Gainesville south end to terminate at TexRail Mercantile
   Center** — best onward connectivity (TexRail → FW Central, T&P, DFW Airport).
2. **Merge the two "Haltom City" stations** onto the FTW/Denton line (commuter↔
   commuter transfer; FTW/Denton then carries them into the FW core).
3. Cheapest model-only: add an explicit transfer edge for the 1.1 km gap — but
   1.1 km is too far to model as an in-station walk; (1) or (2) is the honest fix.

Until then, the entire NW commuter wing serves only itself — a real planning
defect this layer surfaced.

## Next step to make it a live HTML layer
Wire `sendPrompt`-style click-two-stations into the map: clicking an origin then
a destination station calls this logic and draws the itinerary. Currently CLI;
the graph build is identical to the demand engine so it can be ported to the
in-page JS or run as a precompute for common pairs.
