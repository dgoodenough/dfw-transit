"""Small geometry helpers (WGS84 lon/lat, distances in km)."""
import math

R_KM = 6371.0088


def hav_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(a))


def parse_wkt(wkt):
    """LINESTRING (lon lat, lon lat, ...) -> [(lon, lat), ...]"""
    inner = wkt[wkt.index("(") + 1: wkt.rindex(")")]
    pts = []
    for p in inner.split(","):
        x, y = p.split()
        pts.append((float(x), float(y)))
    return pts


def to_wkt(pts):
    return "LINESTRING (" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in pts) + ")"


def polyline_km(pts):
    return sum(hav_km(a[1], a[0], b[1], b[0]) for a, b in zip(pts, pts[1:]))


def bearing_deg(a, b):
    """Initial bearing from (lon,lat) a to b."""
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dl = math.radians(b[0] - a[0])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


def turn_deg(b1, b2):
    """Absolute heading change between two bearings, 0..180."""
    d = abs(b1 - b2) % 360
    return 360 - d if d > 180 else d


class Projector:
    """Local equirectangular projection to km, good to <0.5% across the metroplex."""

    def __init__(self, lat0=32.8, lon0=-97.0):
        self.kx = math.radians(1) * R_KM * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * R_KM
        self.lat0, self.lon0 = lat0, lon0

    def xy(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)
