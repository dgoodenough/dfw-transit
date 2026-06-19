# Fort Worth Subway — Phase One Routing & Stop Review

*Analysis pass #1 of the DFW transit project. Reviews the Fort Worth Phase One
subway (target year 2050 in the planning sheet) against four routing rules +
density logic. Built from the KMZ geometry, not the stylized SVG.*

---

## 0. Basis & honesty note

- **Geometry** is read directly from `FW Subway.kmz` (extracted to
  `Downloads/FW_Subway_extracted/doc.kml`). I dumped every stop and line to
  `Downloads/FW_stations.csv` (180 stops) and `Downloads/FW_lines.csv` (51
  segments) for reference.
- **Density / jobs / tourism judgments below are knowledge-based, not yet
  data-grounded.** I have *not* pulled LEHD LODES (jobs), ACS (population), or
  visitor data. Where a verdict would actually flip on real numbers, I say so.
  Section 8 lists exactly what I'd pull to upgrade this from "informed" to
  "verified."
- Scope = **Fort Worth Phase One only**: Teal, Blue, Orange, Purple. No Silver /
  Red / Yellow (those are Phase 2–3), no Dallas/Mid-Cities.

### The four rules being checked
1. Commuter Rail follows existing rail lines.
2. Minimize tunnels under rivers where possible.
3. Metro follows existing ROW when possible.
4. BRT only follows existing ROW.

---

## 1. How the three artifacts reconcile

| Artifact | What it actually is |
|---|---|
| **CSV (planning sheet)** | The authoritative *phasing* skeleton. Phase One = Teal/Blue/Orange/Purple. |
| **SVG** | The stylized, abstract Phase One FW map (8 colors c0–c7). Clean but not geographic. |
| **KMZ** | The working **geographic** scratchpad — all phases + Dallas + Arlington, plus ~120 unsorted "potential stop" pins in the FW↔Dallas folder. Phase One lines live in the `Subway Lines` folder. |

Line color → name mapping I'm using (from KML style IDs):

| KML color | Line | Phase One role |
|---|---|---|
| `87CEAC` mint / SVG green | **Teal** | E–W backbone: Woodhaven/Riverbend → downtown → Ridgmar Mall |
| `01579B` blue | **Blue** | E–W: Handley → downtown → (temp) Ridgmar |
| `F9A825` amber / SVG orange | **Orange** | N–S then SW: Meacham → downtown → Medical → Waterside |
| `9C27B0` purple | **Purple** (Main St Line) | N–S spine: Meacham → downtown → La Gran Plaza |

> Heads-up for later artifacts: the KMZ FW↔Dallas folder is full of scratch pins
> (`ugh`, `i wish`, `Point 7`, two `Point 74`s, two `Point 78`s). The `Also Red
> Line` and Dallas `Line 9` segments are degenerate loops (first point = last
> point). All of this needs a cleanup pass before any time-series build.

---

## 2. Line-by-line review

### Teal Line (E–W backbone) — *strongest line, one bad kink*
**Path:** Woodhaven → Riverbend → Haltom North → (My Lan/Six Points) → Trinity
Bluff → downtown → TCC → W 7th → Museum Way → Arlington Heights → Ridglea →
Ridgmar → Ridgmar Mall.

- **West of downtown = textbook.** W 7th / Camp Bowie is the single best metro
  corridor in the city: dense (West 7th/Crockett Row apartments + entertainment),
  high tourism (Cultural District museums), a former streetcar street with wide
  ROW, and it terminates on a dead mall (Ridgmar) = latent TOD + BRT transfer.
  Keep all of it.
- **East of downtown = a routing smell.** The stop *order* Woodhaven (32.766) →
  Riverbend (32.795) → Haltom North (32.803) → My Lan (32.781) is
  non-monotonic — it climbs north, then doubles back south. Geographically the
  line zigzags across the **West Fork** near Gateway Park to do this. See §7.1.

**Verdict:** Keep the western 2/3 as-is. Re-plan the eastern tail.

### Blue Line (E–W, southern) — *best ROW in the system, but duplicates Teal west*
**Path:** Handley → Oakland Corners → Poly/Wesleyan → Lancaster → Butler Place →
downtown → **(blue line ctd)** → W 7th → Museum Way → Ridglea → Ridgmar.

- **East of downtown = the cleanest alignment you have.** E Lancaster Ave is old
  US-80: enormous ROW, dead-flat, and the historic Dallas–Fort Worth interurban
  ran out this way through Handley. Handley as a terminus is a good "former
  downtown / latent density" pick exactly per your thesis. Poly/Wesleyan adds
  Texas Wesleyan + an underserved community (equity win). **Notably this whole
  east leg crosses *zero* rivers** — Lancaster stays south of the West Fork the
  entire way. Rule 2 win.
- **West of downtown = a near-exact duplicate of Teal.** `blue line ctd`
  coordinates match the Teal corridor within ~10 m all the way to Ridgmar Mall.
  The sheet flags this western piece as "(temporary)" and Phase 2 says "extend
  Blue westward to 820," so you already sense it. See §7.2.

**Verdict:** Keep the east leg (it's a star). Resolve the western duplication.

### Orange Line (N–S → SW) — *great destinations, softest ROW*
**Path:** Meacham → (down ~Henderson/Forest Park) → downtown → S Main → Medical
City-Baylor → Magnolia → University Park → Stonegate → Clearfork → Waterside.

- **Magnolia / Near Southside + Medical District** is a genuinely dense,
  walkable, fast-redeveloping segment and a major jobs cluster (JPS, Baylor All
  Saints, Medical City). Strong.
- **SW tail (Stonegate → Clearfork → Waterside)** hits real new density
  (Clearfork & WaterSide mixed-use), but the ROW gets suburban (Bryant Irvin
  corridor) and it shadows the **Clear Fork** valley — 1–2 river crossings (§3).
- **North end shares Meacham origin + a parallel West Fork crossing with Purple.**
  See §7.3.

**Verdict:** Keep destinations. Tighten the north crossing; accept the SW tail
but route it on the existing Bryant Irvin/Vickery bridge alignments.

### Purple Line (Main St spine) — *the anchor*
**Path:** Meacham → Mercado → Stockyards → Marine Park → Panther Island
(Lagrave/South) → Courthouse → Sundance → Central Station → T&P → S Main → JPS →
Hemphill → La Gran Plaza.

- Hits nearly every top destination on one wire: Stockyards (top tourism),
  Panther Island (the city's #1 *latent*-density TOD site — literally a
  river-district redevelopment), downtown core, Central Station (TEXRail/TRE
  intermodal), T&P, Near Southside, JPS, and La Gran Plaza (huge Hispanic retail
  anchor on I-35W). 
- Follows real ROW the whole way (N Main → Houston/Main → S Main/Hemphill, all
  former streetcar streets).
- One unavoidable West Fork crossing at Panther Island — but that's a bridge
  district by design, so elevate it (§3).

**Verdict:** Keep essentially as-is. This is the spine everything else hangs on.

---

## 3. River-crossing audit (Rule 2: minimize tunnels under rivers)

Fort Worth's geography is a **"Y"**: the **West Fork** (north arm, past the
Stockyards/Panther Island) and the **Clear Fork** (SW arm, past the Cultural
District and Clearfork/WaterSide) meet just NW of downtown. Any north or west
line crosses one of them. Goal: cross at **existing bridge corridors and
elevate** rather than tunnel, and don't cross twice where once will do.

**These are now computed** — actual intersections of your KML line geometry
against OSM waterway polylines (`data/fw_rivers.json`, 92 ways), not estimates.

| Line | Crossings (computed) | Verdict |
|---|---|---|
| **Purple** | West Fork **×1** @ 32.759, −97.334 | Accept — elevate at Panther Island (planned bridge/TOD district). |
| **Orange North** | West Fork **×1** @ 32.759, −97.335 | **Same spot as Purple — ~70 m apart.** Consolidate onto one shared crossing (§7.3); this is nearly free. |
| **Blue East** | Clear Fork **×1** @ 32.750, −97.347 | Accept — the 7th St bridge corridor at downtown's west edge. |
| **Blue West** | **none** | Clean (starts west of the Clear Fork). |
| **Teal** | West Fork **×2** (32.770,−97.313 and 32.783,−97.224) + Big Fossil Creek ×1 + Little Fossil Creek ×1 + 1 unnamed creek + Clear Fork ×1 (7th St) | **5 of these 6 are on the east zigzag.** The eastern tail is a hydrological mess — strongest argument to re-plan it (§7.1). |
| **Orange South** | Clear Fork **×4** (32.729,−97.358 · 32.719,−97.380 · 32.710,−97.391 · 32.706,−97.402) | The single most crossing-heavy segment. The Clear Fork meanders and the SW tail chases it. Either accept 4 elevated road-bridge crossings (Clear Fork is small here) or hug one bank. |

**Net (corrected by data):** ~13 water crossings total — West Fork ×4, Clear
Fork ×6, creeks ×3. **No tunnel-under-river is required anywhere** if you elevate
at existing bridge corridors. Two clear wins: (1) Orange/Purple cross the West
Fork essentially on top of each other → merge into one structure; (2) the Teal
east tail accounts for 5 crossings by itself → re-plan it. The Orange SW tail's
4 Clear Fork crossings are the surprise — previously rated "accept," now worth a
second look at hugging the east bank toward Clearfork.

---

## 4. ROW audit (Rule 3: metro follows existing ROW)

| Segment | Corridor | ROW quality | Note |
|---|---|---|---|
| Purple, full | N Main → Houston/Main → S Main/Hemphill | ★★★ | Former streetcar streets, wide. |
| Teal, west | W 7th → Camp Bowie | ★★★ | Best corridor in system. |
| Blue, east | E Lancaster (old US-80) | ★★★ | Old interurban; flat, huge ROW. |
| Teal, east | Belknap/Riverside + zigzag | ★☆☆ | Zigzag isn't on a continuous ROW (§7.1). |
| Orange, Magnolia | Hemphill/8th → Magnolia | ★★☆ | Near Southside grid, fine. |
| Orange, SW tail | Bryant Irvin/Vickery | ★★☆ | Suburban arterial; usable but not rail-grade. |

Everything is on *some* real ROW except the Teal east kink. The only "greenfield"
feel is Orange's SW tail, which is acceptable because it's chasing real new
density and can ride existing road bridges.

---

## 5. Commuter rail & BRT quick-check (Rules 1 & 4)

**Commuter rail (must be on existing rail):**
- TexRail → **Crowley** (TexPress Expansion, SW): rides the BNSF (ex-ATSF)
  FW–Cleburne line through Crowley/Burleson. ✓ Real corridor.
- South extensions (toward Burleson): same BNSF spine. ✓
- **FTW/Denton**: BNSF Fort Worth Sub / DCTA corridor. ✓ Plausible.
- **Mansfield** ("new line to Mansfield"): ⚠️ **Verify.** There's freight ROW in
  the area but I'm not certain a continuous, service-grade passenger alignment
  exists into Mansfield. Flag to confirm against actual rail maps before drawing.

**BRT (must be on existing ROW):** Phase One BRT (US-287 Kennedale–Race St;
Jacksboro Hwy/SH-199 Lake Worth–Medical; Woodhaven direct) is all on existing
highways/arterials. ✓ Consistent with the rule. One to-do: confirm `Line 80`
(49 vertices — it wiggles) stays on arterials end-to-end.

---

## 6. Stop-by-stop verdicts

Legend: **KEEP** = solid on density/destination/latent logic · **WEAK** =
justify or cut · **RENAME** · **ADD** = proposed new.

| Stop | Line | Verdict | Reason |
|---|---|---|---|
| Meacham Airport | Purple/Orange | KEEP (as terminus) | GA airport itself is a weak generator; value is the surrounding industrial jobs + Mercado + N-terminus layover. Aim the platform at the jobs, not the airfield. |
| Mercado, Stockyards N/Main, Marine Park | Purple | KEEP | N Main density + #1 tourism (Stockyards). |
| Panther Island (Lagrave / South) | Purple | KEEP | Empty *today*, but the marquee latent-TOD site — exactly your thesis. |
| Courthouse / Sundance / Central / T&P / Convention | Purple | KEEP | Downtown core + intermodal hub. |
| S Main / S Main S / JPS / Hemphill | Purple | KEEP | Near Southside + county hospital jobs. |
| La Gran Plaza | Purple | KEEP | Major Hispanic retail anchor, I-35W. Strong S terminus. |
| TCC Trinity River | Teal | KEEP | Large downtown college campus on the river. |
| W 7th E/W, Museum Way | Teal | KEEP | Densest + most touristy non-downtown nodes. |
| Arlington Heights / Ridglea / Ridgmar / Ridgmar Mall | Teal | KEEP | Camp Bowie corridor + dead-mall TOD + BRT transfer. |
| Six Points | Teal | KEEP | Historic streetcar six-points node, redeveloping. |
| "My Lan (My Favorites)" | Teal | RENAME | Personal pin — rename to the node (e.g. **Riverside**). |
| Trinity Bluff | Teal | KEEP | Real riverfront apartment district E of downtown. |
| Woodhaven / Riverbend / Haltom North | Teal | WEAK (re-plan) | Real-ish density, but the zigzag that links them is the line's worst geometry (§7.1). Consider serving Woodhaven by BRT (already in the sheet) and giving Teal one clean NE alignment. |
| Handley | Blue | KEEP | Former streetcar-suburb "downtown" + interurban heritage — strong latent pick. |
| Poly/Wesleyan | Blue | KEEP | Texas Wesleyan + equity. |
| Lancaster Ave / Butler Place | Blue | KEEP | Butler = large redevelopment site; Lancaster corridor. |
| Oakland Corners | Blue | WEAK | Justify with a real generator or treat as infill; long gaps either side. |
| Medical City-Baylor / Magnolia W/E | Orange | KEEP | Jobs + dense walkable Magnolia. |
| University Park | Orange | WEAK | Confirm it's a distinct generator vs. just spacing toward TCU. |
| Stonegate / Clearfork / Waterside | Orange | KEEP | Real new mixed-use density (jobs+retail+apts). |
| **Meadowbrook** (Blue, ~−97.24,32.74) | Blue | **ADD?** | Big gap Handley→Oakland→Poly; Meadowbrook fills it if density supports. |

---

## 6.5 Density results (data-grounded)

Now backed by **2022 LODES jobs** (Tarrant blocks, 1.04 M jobs) + **2020
block-group population/centroids**. For each stop: sum of population and jobs in
block groups whose centroid is within **1 km** (BG-resolution proxy — coarse but
fair for ranking). Full table in `data/stop_scores.csv`.

**Top of the list validates beautifully** — the downtown core + the two strong
corridors all score highest (activity = pop + jobs within 1 km):

| Rank | Stop | Pop | Jobs | Activity |
|---|---|---|---|---|
| 1 | Sundance Square | 7,756 | 43,279 | **51,035** |
| 2 | Convention Center | 7,072 | 42,749 | 49,821 |
| 3 | Courthouse | 7,715 | 38,906 | 46,621 |
| 4 | Central Station | 6,345 | 36,322 | 42,667 |
| 6 | Magnolia E | 7,835 | 31,821 | 39,656 |
| 7 | W 7th E | 6,608 | 29,245 | 35,853 |
| 8 | TCC Trinity River | 7,676 | 28,109 | 35,785 |
| 11 | Medical City-Baylor | 3,960 | 21,641 | 25,601 |
| 14–15 | TCU / TCU E | ~10k | ~6k | ~16k (residential-led — students) |

**The data flips or sharpens several §6 calls:**

- 🔴 **Meacham Airport = 0 pop / 0 jobs within 1 km.** As sited it's a null stop
  (it's the airfield). But the jobs are *right next door*: a BG with **11,868
  jobs** sits 2.3 km away at 32.816,−97.330. **Relocate the north terminus** off
  the runway toward the Meacham industrial/Mercado-North jobs.
- 🔴 **Riverbend = 0 / 0 / 0.** Another null stop, and it's tangled in the Teal
  east zigzag. **Cut or relocate** — strongest cut candidate in Phase One.
- 🟠 **"My Lan" = 1,701** (and it's a personal pin). The real east-side density
  (BG with **11,989 activity**) is 2 km away at 32.774,−97.270. Rename *and*
  shift east-side coverage there.
- 🟠 **University Park (2,506)** and **Oakland Corners (4,653)** — data confirms
  the earlier WEAK flags.
- 🟡 **La Gran Plaza only 6,809** — lower than expected. Caveat: **LODES
  undercounts retail/informal employment**, and a regional mall is a *destination*
  generator that ambient density misses. Keep as the southern anchor, but it's not
  the density powerhouse it feels like.
- 🟢 **Panther Island (1,812) low today — as expected.** This is the latent-TOD
  bet; the data simply confirms it's empty *now*. Keep on thesis.

**Biggest coverage gap = the one you'd most want to fix:**

| Gap (lat, lon) | Pop | Jobs | Activity | Nearest stop | Dist |
|---|---|---|---|---|---|
| 32.776, −97.449 | 0 | **20,034** | 20,034 | The L Word | 1.13 km |
| 32.830, −97.303 | 1,867 | 15,243 | 17,110 | Haltom North | 4.67 km |
| 32.774, −97.270 | 2,021 | 9,968 | 11,989 | My Lan | 2.04 km |
| 32.816, −97.330 | 100 | 11,868 | 11,968 | Meacham | 2.31 km |
| 32.716, −97.373 | 1,612 | 4,025 | 5,637 | TCU | 1.35 km |

- 🟢🟢 **#1 is the Lockheed Martin F-35 plant (~20,000 jobs)** — the largest job
  site in the city, and your "The L Word" stop sits **1.1 km south of it**. Move
  that stop *onto* the plant/Vandergriff entrance. This is the single highest-value
  fix in the whole Phase One density review.
- The NE gaps (Haltom industrial, 17k jobs) are real but read as Phase 2–3.
- The 32.774,−97.270 gap reinforces re-centering the Teal east stops (see §7.1).

---

## 7. Top routing smells & recommended changes

**7.1 — Teal east zigzag (highest priority).** The Woodhaven→Riverbend→Haltom
North→My Lan ordering doubles back and crosses the West Fork awkwardly. Pick
**one** coherent NE alignment (Belknap/SH-121-ish to Haltom) as the Teal trunk,
and demote Woodhaven/Riverbend to the **Woodhaven-direct BRT** the sheet already
plans (it even says "remove after Green line extension"). Cleaner line, one river
crossing instead of a back-and-forth.

**7.2 — Blue/Teal western duplication.** `blue line ctd` ≈ Teal corridor to ~10 m.
Two clean options: (a) **Shared trunk** — explicitly run both on W 7th/Camp Bowie
for a frequency boost (legit on a corridor this strong), and *draw it as one
shared alignment*; or (b) honor the "(temporary)" note and **terminate Blue
downtown** in Phase One, freeing it to take a *different* west corridor later
(e.g. White Settlement Rd) for actual coverage gain. Right now it reads as
accidental duplication; make it a deliberate choice.

**7.3 — Orange/Purple parallel north crossings.** Both start at Meacham and the
computed crossings show they hit the West Fork **~70 m apart** (32.759,−97.334 vs
32.759,−97.335) — effectively the *same* crossing. Just **consolidate** onto one
shared Meacham→downtown trunk (cross once, split south of downtown). This is
nearly free under Rule 2 and there's no coverage argument for two structures this
close. (Pairs with the §6.5 finding that Meacham itself should move toward the
north jobs cluster.)

**7.4 — Cleanup before any build.** Purge the scratch pins and degenerate loops
from the KMZ (listed in §1) so they don't leak into the time-series artifacts.

---

## 8. Data sources & what's next

**Pulled and used (in `data/`):**

- **2022 LEHD LODES WAC** (`tx_wac.csv.gz`) — jobs per census block, Tarrant
  filtered (1.04 M jobs), aggregated to block group. Drives §6.5.
- **2020 Census block-group population + population-weighted centroids**
  (`CenPop2020_BG_TX.txt`) — residential density + the geometry to join on.
- **OSM waterways via Overpass** (`fw_rivers.json`, 92 ways incl. West Fork,
  Clear Fork, Fossil Creeks) — drives the computed §3 crossings.
- Repro scripts: `data/analyze.ps1` (density + gaps), `data/river_cross.ps1`
  (crossings). Outputs: `data/stop_scores.csv`.

**Honest limits of the current numbers:**

- Density is at **block-group resolution** (centroid-in-1 km), not block or
  parcel — fine for ranking, coarse near big BGs. A block-level job join would
  sharpen downtown/Lockheed precision.
- LODES **undercounts retail/informal** jobs (see La Gran Plaza) and is a
  *workplace* count — it doesn't capture *destination* pull (malls, museums,
  stadiums). No tourism layer yet.
- River crossings test your **schematic KML lines**; once alignments are
  finalized to real ROW, re-run `river_cross.ps1` for exact structure counts.

**Natural next steps:** (a) act on the §7 routing fixes + §6.5 relocations and
re-score; (b) add a tourism/POI layer; or (c) move to the visual time-series
build now that the network is validated.
