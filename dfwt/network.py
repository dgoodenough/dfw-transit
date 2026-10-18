"""The network model: load the source-of-truth tables, apply a scenario, and
derive what is actually running in any given year.

Source tables (network/ or a scenario folder):
  lines.csv          line_id, name, mode, status, color, headway_min, notes
  stations.csv       station_id, name, lat, lon
  line_stops.csv     line_id, seq, station_id, year_opens   (year this line serves this stop)
  line_segments.csv  line_id, seq, year_opens, grade, geometry_wkt   (stop seq -> seq+1)
  service.csv        line_id, from_year, headway_min, note   (optional; frequency changes over time)
  transfers.csv      station_a, station_b, walk_min, note    (optional; walk links beyond the auto radius)

A scenario is a folder under scenarios/ holding any subset of those
tables (each replaces the base table wholesale) and/or an edits.csv of small
overrides applied on top: op, target, field, value, note.
  set_line          lines.csv field `field` of line `target` := value
  shift_line_years  add `value` years to every stop/segment of line `target`
  set_line_year     move line `target` so its earliest opening is `value`
  drop_line         remove line `target`
  set_headway       line `target` runs every `value` minutes from year `field`
"""
import collections
import csv
import os
from dataclasses import dataclass, field

from . import config, geo

NEVER = 9999
TABLES = ("lines.csv", "stations.csv", "line_stops.csv", "line_segments.csv")
OPTIONAL = ("service.csv", "transfers.csv")


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
        self.cfg = cfg
        self.name = name

    # ---------- loading ----------
    @classmethod
    def load(cls, scenario=None, cfg=None):
        cfg = cfg or config.load()
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
        edits = []
        if folder and os.path.exists(os.path.join(folder, "edits.csv")):
            with open(os.path.join(folder, "edits.csv"), encoding="utf-8-sig") as f:
                edits = [r for r in csv.DictReader(f) if r.get("op") and not r["op"].startswith("#")]
        net = cls.from_tables(tables, cfg, name=scenario or "plan")
        net.apply_edits(edits)
        return net

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
            elif op in ("shift_line_years", "set_line_year"):
                delta = int(e["value"]) if op == "shift_line_years" else int(e["value"]) - self._first_new_year(ln)
                ex = self.cfg["existing_year"]
                ln.stop_years = [y if y <= ex else y + delta for y in ln.stop_years]
                for s in ln.segments:
                    if s.year > ex:
                        s.year += delta
            else:
                raise ValueError(f"unknown scenario op {op}")

    def _first_new_year(self, ln):
        ex = self.cfg["existing_year"]
        return min([y for y in ln.stop_years + [s.year for s in ln.segments] if y > ex] or [ex])

    # ---------- derived state ----------
    def runs(self, year):
        """Every operating run in `year`. Track opens per segment; a stop is served
        once the stop is open and track reaches it; unopened stops are run through."""
        out = []
        for ln in self.lines.values():
            mode = self.cfg["modes"][ln.mode]
            cur, acc, i0, i1 = None, 0.0, 0, 0
            for i, sid in enumerate(ln.stop_ids):
                if cur is not None:
                    seg = ln.segments[i - 1] if i - 1 < len(ln.segments) else None
                    if seg is not None and seg.year <= year:
                        acc += seg.km
                        if ln.stop_years[i] <= year:
                            cur.stops.append(sid)
                            cur.hop_km.append(acc)
                            cur.hop_min.append(acc / mode["cruise_kmh"] * 60 + mode["stop_penalty_min"])
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
        a station is charged to the first line that opens it."""
        ex = self.cfg["existing_year"]
        if ln.status == "existing":
            return 0.0
        owner = owner or self.track_owner()
        by_year = by_year or NEVER
        per_km = self.cfg["cost_musd_per_km"][ln.mode]
        track = 0.0
        for i, s in enumerate(ln.segments):
            key = (ln.mode, frozenset((ln.stop_ids[i], ln.stop_ids[i + 1])))
            if ex < s.year <= by_year and owner[key][1] == ln.id:
                track += s.km * per_km.get(s.grade, per_km["surface"])
        first_line = self._station_first_line()
        stops = sum(1 for sid, y in zip(ln.stop_ids, ln.stop_years)
                    if ex < y <= by_year and first_line.get(sid) == ln.id)
        return track + stops * self.cfg["station_cost_musd"][ln.mode]

    def _station_first_line(self):
        first = {}
        for ln in self.lines.values():
            for sid, y in zip(ln.stop_ids, ln.stop_years):
                if sid not in first or (y, ln.id) < first[sid]:
                    first[sid] = (y, ln.id)
        return {k: v[1] for k, v in first.items()}
