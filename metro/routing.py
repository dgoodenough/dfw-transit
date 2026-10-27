"""Corridors on real right-of-way, reusing the DFW tools' router.

dfwt/osmroute.py does the routing (turn-limited, station-constrained Dijkstra on Overture
segments); tools/gen_expansion.py holds the tuned corridor profiles the hand-made expansion
levers use, and this module calls them unchanged:

  metro   gen_expansion.metro_road_path: freeway / major-arterial corridors, changing road
          costs a lot (light rail beside a freeway or in a boulevard median)
  brt     gen_expansion.road_path: arterials preferred, freeways dear, few turns
  rail    osmroute.route on standard-gauge railway (regional rail on existing track), with a
          wider snap than gen_expansion.rail_path because the ends are activity centers, not
          stations already on the track

The graphs are read from the metro's own osm/*.parquet and the projection is re-centred on
the metro (osmroute.set_origin). Routes are cached in the generator's output folder.
"""
import json
import math
import os
import sys

from dfwt import config, osmroute

sys.path.insert(0, config.path("tools"))
import gen_expansion as ge  # noqa: E402

ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary"}
RAIL_CLASSES = {"standard_gauge"}


class Router:
    def __init__(self, m, cache_path=None):
        self.m = m
        osmroute.set_origin(m.lat0, m.lon0)
        self._roads = self._rail = None
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
        key = f"{kind}:" + ":".join(f"{a[0]:.5f},{a[1]:.5f}" for a in stops)
        if key in self.cache:
            return self.cache[key]
        pts = None
        try:
            if kind == "metro":
                self.roads()
                pts = ge.metro_road_path(list(stops))
            elif kind == "brt":
                self.roads()
                pts = ge.road_path(list(stops), "")
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
