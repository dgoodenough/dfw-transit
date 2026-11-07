"""Corridors on real right-of-way, reusing the DFW tools' router.

dfwt/osmroute.py does the routing (turn-limited, station-constrained Dijkstra on Overture
segments); tools/gen_expansion.py holds the tuned corridor profiles the hand-made expansion
levers use, and this module calls them unchanged:

  metro   gen_expansion.metro_road_path: freeway / major-arterial corridors, changing road
          costs a lot (light rail beside a freeway or in a boulevard median)
  brt     the generator's own street profile (brt_path): arterials, where people and jobs line the
          street (cheaper per km as the density within walking distance rises), freeways and
          highways dear, few turns. A BRT station serves the blocks around it, and the frontage is
          where development can follow, so a bus lane beside a freeway is a poor line. (The DFW
          hand plan's BRT kept gen_expansion.road_path, which only mildly penalises highways.)
  rail    osmroute.route on standard-gauge railway (regional rail on existing track), with a
          wider snap than gen_expansion.rail_path because the ends are activity centers, not
          stations already on the track

The graphs are read from the metro's own osm/*.parquet and the projection is re-centred on
the metro (osmroute.set_origin). Routes are cached in the generator's output folder.
"""
import json
import math
import re
import os
import sys

from dfwt import config, osmroute

sys.path.insert(0, config.path("tools"))
import gen_expansion as ge  # noqa: E402

ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary"}
BRT_CLASSES = ROAD_CLASSES | {"tertiary"}
# a highway's frontage roads (Texas "feeder" roads): classed as ordinary streets in the map data, but a
# bus on one runs beside the highway, with its walk catchment cut in half and no frontage to develop
FRONTAGE_ROAD = re.compile(r"frontage|service r(oa)?d|access r(oa)?d|feeder", re.I)
RAIL_CLASSES = {"standard_gauge"}


class Router:
    def __init__(self, m, cache_path=None, frontage=None, brt=None):
        """`frontage(x, y)`: people + jobs per km2 within walking distance at metro point (x, y) km, for
        the BRT profile; `brt`: its parameters (metro/generate.json routing.brt)."""
        self.m = m
        osmroute.set_origin(m.lat0, m.lon0)
        self._roads = self._rail = self._streets = None
        self.frontage, self.brt = frontage, brt or {}
        self._front = {}
        self.cache_path = cache_path
        self.cache = {}
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                self.cache = json.load(f)
        self.dirty = False

    # graphs are loaded on first use (reading roads takes a while)
    def roads(self):
        if self._roads is None:
            if not self.m.osm.get("roads"):
                raise RuntimeError("no osm/roads.parquet")
            self._roads = osmroute.Graph("road", classes=ROAD_CLASSES, oneway=False, path=self.m.osm["roads"])
            ge._FREEWAYS = ge._ROADS = self._roads   # gen_expansion's profiles route on this metro's graph
        return self._roads

    def streets(self):
        """The BRT graph: the road graph plus tertiary streets."""
        if self._streets is None:
            if not self.m.osm.get("roads"):
                raise RuntimeError("no osm/roads.parquet")
            self._streets = osmroute.Graph("road", classes=BRT_CLASSES, oneway=False, path=self.m.osm["roads"])
        return self._streets

    def _frontage_w(self, ed):
        """Cost factor of a street edge for BRT: 1 where nobody lives or works along it, falling toward
        brt.frontage_min as people + jobs within walking distance reach brt.frontage_ref per km2."""
        k = id(ed)
        if k not in self._front:
            P = ed[2]
            lon, lat = osmroute.ll(P[len(P) // 2])
            x, y = (float(v) for v in self.m.xy(lat, lon))
            d = max(float(self.frontage(x, y)), 0.0)
            lo, ref = self.brt.get("frontage_min", 0.6), self.brt.get("frontage_ref", 6000.0)
            w = lo + (1 - lo) * math.exp(-d / ref)
            if FRONTAGE_ROAD.search(ed[7] or ""):
                w *= self.brt.get("frontage_road", 2.0)
            self._front[k] = w
        return self._front[k]

    def brt_path(self, stops):
        G = self.streets()
        w_cls = self.brt.get("w_cls", {"primary": 1.0, "secondary": 1.0, "tertiary": 1.2, "trunk": 2.0, "motorway": 5.0})
        xy = [osmroute.xy(lon, lat) for lat, lon in stops]
        w_fn = self._frontage_w if self.frontage else None
        for snap, turn in ((900, 100), (1500, 135)):
            P, _ = osmroute.route(G, xy, max_turn=turn, snap_r=snap, w_cls=w_cls, turn_pen=700.0, detour=2.5,
                                  snap_w=1.0, w_fn=w_fn)
            if P:
                return [(lat, lon) for lon, lat in (osmroute.ll(p) for p in ge._cut_loops(P))]
        return None

    def rail(self):
        if self._rail is None:
            if not self.m.osm.get("rail"):
                raise RuntimeError("no osm/rail.parquet")
            self._rail = osmroute.Graph("rail", classes=RAIL_CLASSES, path=self.m.osm["rail"])
        return self._rail

    def save(self):
        if self.cache_path and self.dirty:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f)
            self.dirty = False

    def route(self, kind, a, b, snap_km=2.0):
        """(lat, lon) polyline from a to b ((lat, lon) each) for kind metro / brt / rail, or None."""
        return self.route_multi(kind, [a, b], snap_km)

    def route_multi(self, kind, stops, snap_km=2.0):
        """(lat, lon) polyline through `stops` [(lat, lon)] in order, or None."""
        tag = "brt-street-v2" if kind == "brt" else kind   # bump when the street profile changes: cached routes are keyed by it
        key = f"{tag}:" + ":".join(f"{a[0]:.5f},{a[1]:.5f}" for a in stops)
        if key in self.cache:
            return self.cache[key]
        pts = None
        try:
            if kind == "metro":
                self.roads()
                pts = ge.metro_road_path(list(stops))
            elif kind == "brt":
                self.roads()
                pts = self.brt_path(list(stops))
            elif kind == "rail":
                G = self.rail()
                xy = [osmroute.xy(a[1], a[0]) for a in stops]
                P, _ = osmroute.route(G, xy, max_turn=60, snap_r=snap_km * 1000, detour=1.6, snap_w=1.0)
                if P:
                    pts = [(lat, lon) for lon, lat in (osmroute.ll(p) for p in ge._cut_loops(P))]
        except RuntimeError:
            pts = None
        if pts:
            pts = [(round(p[0], 6), round(p[1], 6)) for p in pts]
        self.cache[key] = pts
        self.dirty = True
        return pts


def polyline_km(pts):
    from dfwt import geo
    return sum(geo.hav_km(*p, *q) for p, q in zip(pts, pts[1:]))


def gap_km(pts, end):
    """How far a routed polyline starts/ends from the asked point (lat, lon)."""
    from dfwt import geo
    return min(geo.hav_km(*pts[0], *end), geo.hav_km(*pts[-1], *end))


def heading(p, q):
    return math.atan2(q[0] - p[0], (q[1] - p[1]) * math.cos(math.radians(p[0])))
