"""The network model: load the source-of-truth tables, apply a scenario, and
derive what is actually running in any given year.

Source tables (network/ or a scenario folder):
  lines.csv          line_id, name, mode, status, color, headway_min, notes
  stations.csv       station_id, name, lat, lon
  line_stops.csv     line_id, seq, station_id, year_opens   (year this line serves this stop)
  line_segments.csv  line_id, seq, year_opens, grade, geometry_wkt   (stop seq -> seq+1)
  service.csv        line_id, from_year, headway_min, note   (optional; frequency changes over time)
  transfers.csv      station_a, station_b, walk_min, note    (optional; walk links beyond the auto radius)
  stages.csv         staged build-out per line (optional; see dfwt/staging.py). When a line
                     has stages they set its segment and stop years.

A scenario is a folder under scenarios/ holding any subset of those
tables (each replaces the base table wholesale) and/or an edits.csv of small
overrides applied on top: op, target, field, value, note.
  set_line          lines.csv field `field` of line `target` := value
  shift_line_years  add `value` years to every stop/segment of line `target`
  set_line_year     move line `target` so its earliest opening is `value`
  drop_line         remove line `target`
  set_headway       line `target` runs every `value` minutes from year `field`
  through_route     line `target` and line `field` end at the same station (or two
                    stations within THROUGH_SNAP_KM): run them as one line, keeping
                    `target`'s id; `field` is removed. `value` (optional) is the new
                    name. The junction keeps its park & ride (Line.pnr_stops).
  reroute           from year `field`, line `target` runs a new routing between two of its
                    stops: `value` is "grade|A;stop;@lat,lon;stop;B" (A and B on the line,
                    stops by id or unique name, @lat,lon shape points). The new track is
                    built for that year (and costed); before it the old routing runs.
  add_express       add line `field`: a copy of line `target` that stops only at the
                    `;`-separated stops in `value` (names or ids) and runs through the
                    rest; set its headway with a later set_headway row
"""
import collections
import copy
import csv
import os
from dataclasses import dataclass, field

from . import config, geo, growth

NEVER = 9999


def cost_factor(cfg, year, mode):
    """Unit-cost factor for work opening in `year` (config cost_efficiency): costs fall as a
    steady program builds local contractor and agency experience. Linear between the
    table's years, flat outside them; measured at the middle of construction."""
    t = cfg.get("cost_efficiency")
    if not t:
        return 1.0
    y = year - cfg["staging"]["construction_years"].get(mode, 0) / 2
    pts = sorted((int(k), float(v)) for k, v in t.items() if not str(k).startswith("_"))
    if y <= pts[0][0]:
        return pts[0][1]
    for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
        if y <= y1:
            return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
    return pts[-1][1]
THROUGH_SNAP_KM = 0.3   # through_route: termini this close count as one station
csv.field_size_limit(1 << 28)  # long fitted alignments make large WKT cells
TABLES = ("lines.csv", "stations.csv", "line_stops.csv", "line_segments.csv")
OPTIONAL = ("service.csv", "transfers.csv", "stages.csv")


@dataclass
class Station:
    id: str
    name: str
    lat: float
    lon: float


@dataclass
class Segment:
    year: int
    grade: str
    pts: list
    km: float


@dataclass
class Line:
    id: str
    name: str
    mode: str
    status: str
    color: str
    headway: float
    notes: str
    stop_ids: list = field(default_factory=list)
    stop_years: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    service: list = field(default_factory=list)   # [(from_year, headway_min)], sorted
    pnr_stops: list = field(default_factory=list)  # former termini (through-routed) that keep a garage

    def headway_at(self, year):
        hw = self.headway
        for y, h in self.service:
            if y <= year:
                hw = h
        return hw

    @property
    def first_year(self):
        return min(self.stop_years + [s.year for s in self.segments])

    @property
    def last_year(self):
        return max(self.stop_years + [s.year for s in self.segments])

    @property
    def km(self):
        return sum(s.km for s in self.segments)


@dataclass
class Run:
    """A contiguous operating stretch of one line in one year."""
    line: Line
    stops: list        # station ids actually served, in order
    hop_km: list       # track km between consecutive served stops
    hop_min: list      # in-vehicle minutes between consecutive served stops
    pts: list          # geometry of the whole run


def _join(segments):
    pts = []
    for s in segments:
        pts.extend(s.pts if not pts else s.pts[1:])
    return pts


class Network:
    def __init__(self, stations, lines, cfg, name="network", transfers=None):
        self.stations = stations
        self.lines = lines
        self.transfers = transfers or []   # [(station_a, station_b, walk_min or None, note)]
        self.variants = {}                 # line_id -> [(from_year, until_year, Line, interim)]
        self.absorbed = {}                 # through-routed line id -> the line it now runs as
        self.stop_alias = {}               # a merged-away terminus -> the junction that replaced it
        self.stage_rows = []
        self.stage_findings = []
        self.cfg = cfg
        self.name = name

    # ---------- loading ----------
    @staticmethod
    def read_tables(scenario=None):
        """Raw rows of every table for the plan or a scenario, plus its edits.csv rows."""
        base = config.path("network")
        folder = config.path("scenarios", scenario) if scenario else None
        tables = {}
        for t in TABLES + OPTIONAL:
            p = os.path.join(folder, t) if folder and os.path.exists(os.path.join(folder, t)) else os.path.join(base, t)
            if t in OPTIONAL and not os.path.exists(p):
                tables[t] = []
                continue
            with open(p, encoding="utf-8-sig") as f:
                tables[t] = list(csv.DictReader(f))
            # <table>.add.csv appends rows to whatever the table is (the plan's, or the scenario's own);
            # <table>.patch.csv replaces every row of the lines it names (line-keyed tables) and adds the rest
            add = os.path.join(folder, t[:-4] + ".add.csv") if folder else None
            if add and os.path.exists(add):
                with open(add, encoding="utf-8-sig") as f:
                    tables[t] = tables[t] + list(csv.DictReader(f))
            patch = os.path.join(folder, t[:-4] + ".patch.csv") if folder else None
            if patch and os.path.exists(patch):
                with open(patch, encoding="utf-8-sig") as f:
                    rows = list(csv.DictReader(f))
                lines = {r["line_id"] for r in rows}
                tables[t] = [r for r in tables[t] if r.get("line_id") not in lines] + rows
        edits = []
        if folder and os.path.exists(os.path.join(folder, "edits.csv")):
            with open(os.path.join(folder, "edits.csv"), encoding="utf-8-sig") as f:
                edits = [r for r in csv.DictReader(f) if r.get("op") and not r["op"].startswith("#")]
        return tables, edits

    @classmethod
    def load(cls, scenario=None, cfg=None, stage_rows=None):
        """Load the plan or a scenario. `stage_rows` replaces its stages.csv (for previews)."""
        tables, edits = cls.read_tables(scenario)
        if stage_rows is not None:
            tables["stages.csv"] = stage_rows
        return cls.from_raw(tables, edits, cfg or config.load(scenario=scenario), scenario or "plan")

    @classmethod
    def from_raw(cls, tables, edits, cfg, name):
        from . import staging
        tables = dict(tables)
        stage_rows = tables.pop("stages.csv", [])
        tables, interims, findings = staging.compile_stages(tables, stage_rows)
        net = cls.from_tables(tables, cfg, name=name)
        net.stage_rows, net.stage_findings = stage_rows, findings
        net.variants = staging.build_variants(net, interims)
        net.apply_edits(edits)
        return net

    def without(self, line_id):
        """The same network with one line removed (for leave-one-out values)."""
        net = Network(self.stations, {k: v for k, v in self.lines.items() if k != line_id},
                      self.cfg, self.name, self.transfers)
        net.variants = {k: v for k, v in self.variants.items()
                        if k != line_id and all(it.get("via") != line_id for *_, it in v)}
        net.absorbed, net.stop_alias = dict(self.absorbed), dict(self.stop_alias)
        return net

    def host_line(self, line_id):
        """The line a stage row's line now runs as: itself, or the line it was through-routed
        into (its stages still name it), or None if it was dropped."""
        while line_id in self.absorbed and line_id not in self.lines:
            line_id = self.absorbed[line_id]
        return self.lines.get(line_id)

    def line_at(self, line_id, year):
        """The line's routing in force in `year` (an interim via-routing, or itself)."""
        for y0, y1, v, _ in self.variants.get(line_id, []):
            if y0 <= year < y1:
                return v
        return self.lines[line_id]

    @classmethod
    def from_tables(cls, t, cfg, name="plan"):
        stations = {r["station_id"]: Station(r["station_id"], r["name"], float(r["lat"]), float(r["lon"]))
                    for r in t["stations.csv"]}
        lines = {}
        for r in t["lines.csv"]:
            hw = float(r["headway_min"]) if r.get("headway_min") else float(cfg["modes"][r["mode"]]["default_headway_min"])
            lines[r["line_id"]] = Line(r["line_id"], r["name"], r["mode"], r["status"], r["color"], hw, r.get("notes", ""))
        for r in sorted(t["line_stops.csv"], key=lambda r: (r["line_id"], int(r["seq"]))):
            ln = lines[r["line_id"]]
            ln.stop_ids.append(r["station_id"])
            ln.stop_years.append(int(r["year_opens"]))
        for r in sorted(t["line_segments.csv"], key=lambda r: (r["line_id"], int(r["seq"]))):
            pts = geo.parse_wkt(r["geometry_wkt"])
            lines[r["line_id"]].segments.append(Segment(int(r["year_opens"]), r.get("grade") or "surface", pts, geo.polyline_km(pts)))
        for r in t.get("service.csv", []):
            if r["line_id"] in lines:
                lines[r["line_id"]].service.append((int(r["from_year"]), float(r["headway_min"])))
        for ln in lines.values():
            ln.service.sort()
        transfers = [(r["station_a"], r["station_b"], float(r["walk_min"]) if r.get("walk_min") else None, r.get("note", ""))
                     for r in t.get("transfers.csv", [])]
        return cls(stations, lines, cfg, name, transfers)

    def apply_edits(self, edits):
        for e in edits:
            op, lid = e["op"], e["target"]
            if lid not in self.lines:
                raise KeyError(f"scenario edit {op}: unknown line {lid}")
            ln = self.lines[lid]
            if op == "drop_line":
                del self.lines[lid]
            elif op == "set_headway":
                ln.service = sorted([x for x in ln.service if x[0] != int(e["field"] or 0)] + [(int(e["field"] or 0), float(e["value"]))])
            elif op == "set_line":
                setattr(ln, e["field"], float(e["value"]) if e["field"] == "headway" else e["value"])
            elif op == "through_route":
                self._through_route(ln, e["field"], e.get("value") or "")
            elif op == "reroute":
                self._reroute(ln, int(e["field"]), e["value"])
            elif op == "add_express":
                self._add_express(ln, e["field"], e["value"])
            elif op in ("shift_line_years", "set_line_year"):
                delta = int(e["value"]) if op == "shift_line_years" else int(e["value"]) - self._first_new_year(ln)
                ex = self.cfg["existing_year"]
                ln.stop_years = [y if y <= ex else y + delta for y in ln.stop_years]
                for s in ln.segments:
                    if s.year > ex:
                        s.year += delta
            else:
                raise ValueError(f"unknown scenario op {op}")

    @staticmethod
    def _reversed(ln):
        ln.stop_ids.reverse()
        ln.stop_years.reverse()
        ln.segments.reverse()
        for s in ln.segments:
            s.pts = s.pts[::-1]

    def _through_route(self, a, b_id, name):
        """Join line b onto line a where their termini meet (see module doc)."""
        if b_id not in self.lines:
            raise KeyError(f"through_route: unknown line {b_id}")
        b = self.lines[b_id]
        if a.mode != b.mode:
            raise ValueError(f"through_route {a.id}+{b_id}: modes differ ({a.mode}, {b.mode})")
        st = self.stations

        def gap(s1, s2):
            return 0.0 if s1 == s2 else geo.hav_km(st[s1].lat, st[s1].lon, st[s2].lat, st[s2].lon)
        options = [(gap(a.stop_ids[ia], b.stop_ids[ib]), ia, ib) for ia in (0, -1) for ib in (0, -1)]
        d, ia, ib = min(options)
        if d > THROUGH_SNAP_KM:
            raise ValueError(f"through_route {a.id}+{b_id}: no shared terminus (closest {d:.2f} km)")
        if ia == 0:
            self._reversed(a)        # junction at the end of a
        if ib == -1:
            self._reversed(b)        # junction at the start of b
        junction = a.stop_ids[-1]
        b_first = b.stop_ids[0]
        # the joined line runs as often as the more frequent of the parts already running
        years = sorted({y for y, _ in a.service + b.service} | {a.first_year, b.first_year})

        def hw(y):
            on = [p.headway_at(y) for p in (a, b) if p.first_year <= y]
            return min(on) if on else a.headway_at(y)
        a.service = [(y, hw(y)) for y in years]
        a.headway = min(a.headway, b.headway)
        a.stop_years[-1] = min(a.stop_years[-1], b.stop_years[0])
        a.stop_ids += b.stop_ids[1:]
        a.stop_years += b.stop_years[1:]
        a.segments += b.segments
        # both old termini had a garage; keep them (a through station still has its lot)
        a.pnr_stops = list(dict.fromkeys(a.pnr_stops + b.pnr_stops + [junction]))
        if name:
            a.name = name
        if a.status != b.status:
            a.status = "proposed"
        del self.lines[b_id]
        self.absorbed[b_id] = a.id
        if b_first != junction:   # b's own terminus merged into a's (within THROUGH_SNAP_KM)
            self.stop_alias[b_first] = junction
        self.variants.pop(b_id, None)
        self.variants.pop(a.id, None)

    def _reroute(self, ln, year, spec):
        """Replace the line's stops between two of its stops with a new routing from `year`
        (see module doc); the old routing becomes a variant that runs until then."""
        grade, _, path = spec.partition("|")
        by_name = {}
        for sid, st in self.stations.items():
            by_name.setdefault(st.name, []).append(sid)

        def sid_of(x):
            x = x.strip()
            if x in self.stations:
                return x
            hits = by_name.get(x, [])
            if len(hits) != 1:
                raise KeyError(f"reroute {ln.id}: '{x}' is not a station id or a unique station name")
            return hits[0]
        items = [x.strip() for x in path.split(";") if x.strip()]
        stops, shape = [], []   # stop ids; shape points before each stop after the first
        pending = []
        for x in items:
            if x.startswith("@"):
                lat, lon = (float(v) for v in x[1:].split(","))
                pending.append((lon, lat))
            else:
                stops.append(sid_of(x))
                shape.append(pending)
                pending = []
        a, b = ln.stop_ids.index(stops[0]), ln.stop_ids.index(stops[-1])
        if a > b:
            self._reversed(ln)
            a, b = ln.stop_ids.index(stops[0]), ln.stop_ids.index(stops[-1])
        old = copy.deepcopy(ln)
        segs = []
        for k in range(1, len(stops)):
            p, q = self.stations[stops[k - 1]], self.stations[stops[k]]
            pts = [(p.lon, p.lat)] + shape[k] + [(q.lon, q.lat)]
            segs.append(Segment(year, grade or "surface", pts, geo.polyline_km(pts)))
        ln.stop_ids = ln.stop_ids[:a] + stops + ln.stop_ids[b + 1:]
        ln.stop_years = ln.stop_years[:a + 1] + [year] * (len(stops) - 2) + ln.stop_years[b:]
        ln.segments = ln.segments[:a] + segs + ln.segments[b:]
        self.variants.setdefault(ln.id, []).append((0, year, old, {"via": None, "reroute": year}))

    def _add_express(self, base, new_id, stops):
        """A skip-stop copy of `base` (see module doc)."""
        from .staging import resolve
        if new_id in self.lines:
            raise ValueError(f"add_express: line {new_id} already exists")
        names = {k: s.name for k, s in self.stations.items()}
        keep = {resolve(s, base.stop_ids, names) for s in stops.split(";") if s.strip()}
        keep |= {0, len(base.stop_ids) - 1}
        ex = copy.deepcopy(base)
        ex.id, ex.name, ex.service = new_id, base.name + " Express", []   # own headways (set_headway)
        ex.stop_years = [y if i in keep else NEVER for i, y in enumerate(base.stop_years)]
        ex.pnr_stops = []
        self.lines[new_id] = ex

    def _first_new_year(self, ln):
        ex = self.cfg["existing_year"]
        return min([y for y in ln.stop_years + [s.year for s in ln.segments] if y > ex] or [ex])

    # ---------- derived state ----------
    def runs(self, year):
        """Every operating run in `year`. Track opens per segment; a stop is served
        once the stop is open and track reaches it; unopened stops are run through."""
        out = []
        # BRT shares some of the road congestion (dedicated lanes, but signals and crossings)
        cg = self.cfg["drive"].get("congestion")
        brt_slow = 1.0 + (growth.congestion(self.cfg, year) - 1.0) * cg["brt_share"] if cg else 1.0
        for ln in (self.line_at(k, year) for k in self.lines):
            mode = self.cfg["modes"][ln.mode]
            slow = brt_slow if ln.mode == "brt" else 1.0
            cur, acc, i0, i1 = None, 0.0, 0, 0
            for i, sid in enumerate(ln.stop_ids):
                if cur is not None:
                    seg = ln.segments[i - 1] if i - 1 < len(ln.segments) else None
                    if seg is not None and seg.year <= year:
                        acc += seg.km
                        if ln.stop_years[i] <= year:
                            cur.stops.append(sid)
                            cur.hop_km.append(acc)
                            cur.hop_min.append(acc / mode["cruise_kmh"] * 60 * slow + mode["stop_penalty_min"])
                            acc, i1 = 0.0, i
                        continue
                    if len(cur.stops) > 1:
                        cur.pts = _join(ln.segments[i0:i1])
                        out.append(cur)
                    cur = None
                if ln.stop_years[i] <= year:
                    cur, acc, i0, i1 = Run(ln, [sid], [], [], []), 0.0, i, i
            if cur is not None and len(cur.stops) > 1:
                cur.pts = _join(ln.segments[i0:i1])
                out.append(cur)
        return out

    def open_stations(self, year):
        """station_id -> set of modes serving it in `year`."""
        out = collections.defaultdict(set)
        for r in self.runs(year):
            for sid in r.stops:
                out[sid].add(r.line.mode)
        return out

    def station_lines(self):
        """station_id -> [line ids] over the whole plan."""
        out = collections.defaultdict(list)
        for ln in self.lines.values():
            for sid in dict.fromkeys(ln.stop_ids):
                out[sid].append(ln.id)
        return out

    def station_year(self, sid):
        ys = [y for ln in self.lines.values() for s, y in zip(ln.stop_ids, ln.stop_years) if s == sid]
        return min(ys) if ys else NEVER

    def track_owner(self):
        """Shared track is built (and paid for) once: map each physical track piece
        (mode + station pair) to the (year, line_id) that opens it first."""
        owner = {}
        for ln in self.lines.values():
            for i, s in enumerate(ln.segments):
                key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
                cand = (s.year, ln.id)
                if key not in owner or cand < owner[key]:
                    owner[key] = cand
        return owner

    def line_cost_musd(self, ln, by_year=None, owner=None):
        """Capital cost of a line's new track and stations (2025 USD), opened by
        `by_year` if given. Track shared with an earlier line is not charged again;
        a station is charged to the first line of its mode that opens it."""
        ex = self.cfg["existing_year"]   # today's track and stations (opened by then) cost nothing
        owner = owner or self.track_owner()
        by_year = by_year or NEVER
        track = 0.0
        for i, s in enumerate(ln.segments):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if ex < s.year <= by_year and owner[key][1] == ln.id:
                track += self.segment_cost(ln, i)
        first_line = self._station_first_line()
        stops = sum(self.stop_cost(ln, i) for i, (sid, y) in enumerate(zip(ln.stop_ids, ln.stop_years))
                    if ex < y <= by_year and first_line.get((sid, ln.mode)) == ln.id)
        return track + stops

    def opex_musd(self, year):
        """Operating cost ($M/yr) of the service running in `year`, by mode (config.operating):
        revenue vehicle-hours = 2 directions x run minutes / headway x service hours a day
        x layover/recovery, x cost per revenue hour x weekday-equivalent days."""
        oc = self.cfg.get("operating")
        if not oc:
            return {}
        out = collections.Counter()
        for r in self.runs(year):
            hw = r.line.headway_at(year)
            veh_h = 2 * sum(r.hop_min) / hw * oc["span_hours"] * oc["layover"]
            out[r.line.mode] += veh_h * oc["usd_per_revenue_hour"][r.line.mode] * oc["days_per_year"] / 1e6
        return dict(out)

    def segment_cost(self, ln, i):
        """Capital ($M) of segment i of a line: km x the mode's cost per km for its grade, x the
        program's cost factor when it's built (cost_factor)."""
        s = ln.segments[i]
        per_km = self.cfg["cost_musd_per_km"][ln.mode]
        return s.km * per_km.get(s.grade, per_km["surface"]) * cost_factor(self.cfg, s.year, ln.mode)

    def stop_cost(self, ln, i):
        """Capital ($M) of stop i of a line, for the line that first serves it in its mode: the
        platform (an underground metro station costs station_cost_musd.metro_tunnel), plus the
        park-and-ride garage the demand model gives it (every commuter station; a line's
        termini and kept through-route junctions), x the cost factor when it's built."""
        cfg = self.cfg
        sc = cfg["station_cost_musd"]
        sid, y = ln.stop_ids[i], ln.stop_years[i]
        under = any(ln.segments[k].grade == "tunnel" for k in (i - 1, i) if 0 <= k < len(ln.segments))
        cost = sc.get(ln.mode + "_tunnel", sc[ln.mode]) if under else sc[ln.mode]
        per_space = cfg.get("garage_musd_per_space", 0.0)
        if per_space:
            sp = cfg["access"]["pnr_spaces"]
            if ln.mode == "commuter":
                spaces = sp["commuter_station"]
            elif i in (0, len(ln.stop_ids) - 1) or sid in ln.pnr_stops:
                spaces = sp.get(ln.mode + "_terminus", sp["terminus"])
            else:
                spaces = 0
            cost += spaces * per_space
        return cost * cost_factor(cfg, y, ln.mode)

    def _station_first_line(self):
        """(station_id, mode) -> the line that first serves that station in that mode: it
        pays for the mode's platform (a metro line reaching a BRT stop builds its own)."""
        first = {}
        for ln in self.lines.values():
            for sid, y in zip(ln.stop_ids, ln.stop_years):
                k = (sid, ln.mode)
                if k not in first or (y, ln.id) < first[k]:
                    first[k] = (y, ln.id)
        return {k: v[1] for k, v in first.items()}

    def station_mode_years(self):
        """station_id -> {mode: first year a line of that mode serves it}."""
        out = collections.defaultdict(dict)
        for ln in self.lines.values():
            for sid, y in zip(ln.stop_ids, ln.stop_years):
                out[sid][ln.mode] = min(out[sid].get(ln.mode, NEVER), y)
        return out
