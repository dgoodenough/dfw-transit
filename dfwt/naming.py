"""Station names from real places: cross streets, neighbourhoods, landmarks.

DART names its stations after the cross streets ("Forest/Jupiter", "Walnut
Hill/Denton"), a neighbourhood ("Lake Highlands") or a landmark ("VA Medical
Center"). `Namer` proposes names the same way for a point:

1. a landmark (hospital, university, mall) within 250 m,
2. a neighbourhood within 350 m,
3. the cross streets at the nearest arterial intersection within 450 m, the
   street the station sits on first ("Belt Line / Jupiter"),
4. a neighbourhood within 900 m, the street it sits on alone ("Kingsley
   Road"), or the nearest street with the next one,
5. a street further off.

Streets come from data/osm/roads.parquet (Overture, tools/fetch_osm.py: motorway
to tertiary, so arterials only); intersections are the segments' shared
connectors. Places come from data/dfw_gazetteer.json and data/dfw_hoods.json
(OpenStreetMap). A name already in use (compared like the diagram does:
case, spaces and punctuation ignored) is skipped, so every proposal is unique.
"""
import collections
import json
import math
import os
import re

from . import config, geo

SUFFIX = re.compile(r"\s+(?:N|S|E|W|NE|NW|SE|SW)\d*$")
LANDMARK_M, HOOD_NEAR_M, CROSS_M, HOOD_FAR_M, STREET_M = 250, 350, 450, 900, 600
_TYPES = (r"Street|St|Road|Rd|Avenue|Ave|Av|Boulevard|Blvd|Drive|Dr|Lane|Ln|Parkway|Pkwy|Freeway|Fwy|"
          r"Expressway|Expy|Highway|Hwy|Trail|Trl|Way|Court|Ct|Place|Pl|Circle|Cir|Pike|Tollway|Turnpike|Loop")
_DIRS = r"North|South|East|West|Northeast|Northwest|Southeast|Southwest|N|S|E|W|NE|NW|SE|SW"
_ALIASES = [  # (pattern on the full street name, short form), first match wins
    (r"^(?:interstate|ih|i)[ -]?(\d+)[ewns]?\b.*", r"I-\1"),
    (r"^(?:us|u\.s\.)(?: highway| hwy| route)?[ -]?(\d+)\b.*", r"US-\1"),
    (r"^(?:state highway|texas state highway|sh|tx)[ -]?(\d+)\b.*", r"SH-\1"),
    (r"^(?:state highway loop|loop)[ -]?(\d+)\b.*", r"Loop \1"),
    (r"^(?:state highway spur|spur)[ -]?(\d+)\b.*", r"Spur \1"),
    (r"^(?:farm[- ]to[- ]market road|farm[- ]to[- ]market|fm|ranch road)[ -]?(\d+)\b.*", r"FM \1"),
    (r"^lyndon b\.? johnson.*", "LBJ"),
    (r"^(?:president )?george bush turnpike.*", "Bush Turnpike"),
    (r"^dallas north tollway.*", "Tollway"),
    (r"^dallas[- ]fort worth turnpike.*", "I-30"),
    (r"^sam rayburn tollway.*", "Sam Rayburn"),
    (r"^(?:north )?central expressway.*", "Central"),
    (r"^stemmons.*", "Stemmons"),
    (r"^r\.? ?l\.? thornton.*", "Thornton"),
    (r"^northwest highway.*", "NW Highway"),
    (r"^chisholm trail parkway.*", "Chisholm Trail"),
]


def norm(s):
    """The comparison key the diagram uses for 'the same name'."""
    s = s.lower().replace("square", "sq")
    return re.sub(r"[^a-z0-9]", "", s)


def keys(s):
    """norm() of a name, and of its cross streets the other way round ("Long / Deen" = "Deen / Long")."""
    parts = [p.strip() for p in s.split("/")]
    return {norm(s), norm("/".join(parts[::-1]))}


_NOT_A_STREET = re.compile(r"\b(?:Connection|Connector|Ramp|Exit|Entrance|Turnaround|Crossover|Driveway|Viaduct|Bridge|Overpass|Underpass|Tunnel)\b", re.I)


def clean_street(name, keep_type=False, places=()):
    """'North Belt Line Road' -> 'Belt Line'; 'Interstate 30 Frontage Road' -> 'I-30'.
    keep_type keeps 'Lane', 'Road' ... (for a street named alone); a street whose
    stem is a place name keeps its type ('Plano Parkway')."""
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"\bMc (?=[A-Z])", "Mc", s)
    s = re.sub(r"\s+-\s+", "-", s)                                 # 'Bryan - Belt Line' -> 'Bryan-Belt Line'                         # 'Mc Lean' -> 'McLean'
    s = re.sub(r"\s*\b(?:Frontage|Service|Access) Road\b.*$|\s*\b(?:Express|HOV|Managed) Lanes?\b.*$|\s*\bRamp\b.*$", "", s, flags=re.I)
    if not s or _NOT_A_STREET.search(s):
        return ""
    bare = re.sub(rf"^(?:{_DIRS})\.?\s+", "", s)
    for pat, rep in _ALIASES:
        for t in (s, bare):
            if re.match(pat, t, flags=re.I):
                return re.sub(pat, rep, t, flags=re.I)
    s = re.sub(rf"^(?:{_DIRS})\.?\s+(?=\S+\s+\S)", "", s)          # 'North Belt Line Road' -> 'Belt Line Road'
    t = re.sub(rf"\s+(?:{_DIRS})$", "", s)                         # 'Main Street North', not 'Avenue E'
    s = s if re.fullmatch(rf"(?:{_TYPES})", t, flags=re.I) else t
    stem = re.sub(rf"\s+(?:{_TYPES})\.?$", "", s, flags=re.I)
    if keep_type or not stem or stem.lower() in places or re.fullmatch(_DIRS, stem, flags=re.I) or re.fullmatch(r"\d+(?:st|nd|rd|th)?", stem, flags=re.I):
        return s
    return stem


class Namer:
    def __init__(self, roads=True, roads_path=None, places=True):
        """roads_path: another region's roads.parquet (default data/osm/roads.parquet);
        places=False skips the DFW gazetteer files (a metro elsewhere)."""
        self.proj = geo.Projector()
        self.places, self.hoods, self.landmarks, self.towns = [], [], [], []
        for fn in ("dfw_gazetteer.json", "dfw_hoods.json", "dfw_poi.json") if places else ():
            p = config.path("data", fn)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                els = json.load(f)["elements"]
            for e in els:
                t = e.get("tags", {})
                nm = t.get("name")
                if not nm or "lat" not in e:
                    continue
                xy = self.proj.xy(e["lat"], e["lon"])
                if t.get("place") in ("neighbourhood", "quarter", "suburb"):
                    self.hoods.append((xy, nm))
                if t.get("place") in ("city", "town", "village", "hamlet", "suburb"):
                    self.places.append(nm.lower())
                    self.towns.append((xy, nm))
                if t.get("amenity") in ("hospital", "university", "college") or t.get("healthcare") == "hospital" \
                        or t.get("shop") == "mall":
                    self.landmarks.append((xy, nm))
        self.places = set(self.places)
        self.hoods = sorted(set(self.hoods))
        self.landmarks = sorted(set(self.landmarks))
        self.segs = []                                  # (name, class, [xy ...])
        self.grid = collections.defaultdict(set)        # 250 m cell -> segment indices
        self.conn = collections.defaultdict(set)        # connector id -> segment indices
        self.conn_xy = {}
        roads_path = roads_path or config.path("data", "osm", "roads.parquet")
        if roads and os.path.exists(roads_path):
            self._load_roads(roads_path)

    # ------------------------------------------------------------ roads
    def _load_roads(self, path=None):
        import pyarrow.parquet as pq
        from .osmroute import wkb_linestring
        t = pq.read_table(path or config.path("data", "osm", "roads.parquet"), columns=["geometry", "class", "names", "connectors"])
        for r in t.to_pylist():
            nm = ((r["names"] or {}).get("primary") or "").strip()
            if not nm:
                continue
            P = [self.proj.xy(lat, lon) for lon, lat in wkb_linestring(r["geometry"])]
            k = len(self.segs)
            self.segs.append((nm, r["class"], P))
            for (x0, y0), (x1, y1) in zip(P, P[1:]):
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.2))
                for i in range(n + 1):
                    self.grid[(int((x0 + (x1 - x0) * i / n) // 0.25), int((y0 + (y1 - y0) * i / n) // 0.25))].add(k)
            L = [0.0]
            for a, b in zip(P, P[1:]):
                L.append(L[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
            for c in r["connectors"] or []:
                self.conn[c["connector_id"]].add(k)
                if c["connector_id"] not in self.conn_xy:
                    s = c["at"] * L[-1]
                    j = next((j for j in range(1, len(L)) if L[j] >= s), len(L) - 1)
                    f = (s - L[j - 1]) / ((L[j] - L[j - 1]) or 1)
                    self.conn_xy[c["connector_id"]] = (P[j - 1][0] + f * (P[j][0] - P[j - 1][0]),
                                                       P[j - 1][1] + f * (P[j][1] - P[j - 1][1]))
        self.seg_conns = collections.defaultdict(list)
        for cid, ks in self.conn.items():
            for k in ks:
                self.seg_conns[k].append(cid)

    def _near_segs(self, p, r_km):
        cx, cy, n = int(p[0] // 0.25), int(p[1] // 0.25), int(r_km // 0.25) + 1
        out = set()
        for i in range(cx - n, cx + n + 1):
            for j in range(cy - n, cy + n + 1):
                out |= self.grid.get((i, j), set())
        return out

    @staticmethod
    def _pdist(p, P):
        best = 1e9
        for a, b in zip(P, P[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
        return best

    def streets(self, lat, lon, r_m=STREET_M):
        """[(distance m, clean name, raw name, class)] of the streets near a point, nearest first."""
        p = self.proj.xy(lat, lon)
        best = {}
        for k in self._near_segs(p, r_m / 1000):
            nm, cls, P = self.segs[k]
            c = clean_street(nm, places=self.places)
            if not c:
                continue
            d = self._pdist(p, P) * 1000
            if d <= r_m and (c not in best or d < best[c][0]):
                best[c] = (d, c, nm, cls)
        return sorted(best.values())

    def crossings(self, lat, lon, r_m=CROSS_M):
        """[(score, distance m, street the station is on, cross street)] at intersections near a point."""
        p = self.proj.xy(lat, lon)
        on = self.streets(lat, lon, 150)
        on_rank = {c: i for i, (_, c, _, _) in enumerate(on)}
        seen = {}
        for k in self._near_segs(p, r_m / 1000):
            for cid in self.seg_conns.get(k, ()):
                q = self.conn_xy[cid]
                d = math.hypot(q[0] - p[0], q[1] - p[1]) * 1000
                if d > r_m:
                    continue
                names = {}
                for j in self.conn[cid]:
                    nm, cls, _ = self.segs[j]
                    c = clean_street(nm, places=self.places)
                    if c:
                        names[c] = cls
                ns = sorted(names)
                for a in ns:
                    for b in ns:
                        if a >= b or a.lower() in b.lower() or b.lower() in a.lower():
                            continue
                        # the street the station is on goes first
                        first, second = (a, b) if on_rank.get(a, 99) <= on_rank.get(b, 99) else (b, a)
                        motor = sum(names[x] == "motorway" for x in (a, b))
                        score = d + 120 * motor + (0 if first in on_rank else 150)
                        key = (first, second)
                        if key not in seen or score < seen[key][0]:
                            seen[key] = (score, d, first, second)
        return sorted(seen.values())

    # ------------------------------------------------------------ names
    def candidates(self, lat, lon):
        """[(name, basis)] in order of preference."""
        p = self.proj.xy(lat, lon)
        dist = lambda q: math.hypot(q[0] - p[0], q[1] - p[1]) * 1000  # noqa: E731
        out = []
        for q, nm in sorted(self.landmarks, key=lambda t: dist(t[0])):
            if dist(q) <= LANDMARK_M:
                out.append((nm, f"landmark {nm} ({dist(q):.0f} m)"))
        hoods = sorted(self.hoods, key=lambda t: dist(t[0]))
        for q, nm in hoods:
            if dist(q) <= HOOD_NEAR_M:
                out.append((nm, f"neighbourhood {nm} ({dist(q):.0f} m)"))
        for _, d, a, b in self.crossings(lat, lon):
            out.append((f"{a} / {b}", f"cross streets {a} x {b} ({d:.0f} m)"))
        for q, nm in hoods:
            if HOOD_NEAR_M < dist(q) <= HOOD_FAR_M:
                out.append((nm, f"neighbourhood {nm} ({dist(q):.0f} m)"))
        st = self.streets(lat, lon)
        # a street alone before two streets that don't actually meet here
        for d, c, raw, _ in st:
            if d <= 250:
                out.append((clean_street(raw, keep_type=True, places=self.places), f"street {raw} ({d:.0f} m)"))
        for i, (d, c, raw, _) in enumerate(st):
            for d2, c2, _, _ in st[i + 1:]:
                if c.lower() not in c2.lower() and c2.lower() not in c.lower():
                    out.append((f"{c} / {c2}", f"nearest streets {c} ({d:.0f} m), {c2} ({d2:.0f} m)"))
        for d, c, raw, _ in st:
            out.append((clean_street(raw, keep_type=True, places=self.places), f"street {raw} ({d:.0f} m)"))
        return out

    def name(self, lat, lon, used, fallback):
        """The first unused candidate (added to `used`, a set of keys())."""
        for nm, basis in self.candidates(lat, lon):
            if len(nm) <= 32 and not keys(nm) & used and not SUFFIX.search(nm) and not nm.endswith("Historic District"):
                used |= keys(nm)
                return nm, basis
        base = SUFFIX.sub("", fallback).strip() or fallback
        st = self.streets(lat, lon, 2000)
        for i, (d, c, raw, _) in enumerate(st):
            for d2, c2, _, _ in st[i + 1:i + 6]:
                nm = f"{c} / {c2}"
                if len(nm) <= 32 and not keys(nm) & used and c.lower() not in c2.lower() and c2.lower() not in c.lower():
                    used |= keys(nm)
                    return nm, f"nearest streets {c} ({d:.0f} m), {c2} ({d2:.0f} m)"
        for d, c, raw, _ in st:
            nm = f"{base} / {c}"
            if not keys(nm) & used:
                used |= keys(nm)
                return nm, f"place {base} and street {raw} ({d:.0f} m)"
        k = 2
        while keys(f"{base} {k}") & used:
            k += 1
        used |= keys(f"{base} {k}")
        return f"{base} {k}", "no street or place nearby"
