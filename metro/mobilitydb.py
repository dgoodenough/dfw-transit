"""Mobility Database catalog -> the GTFS feeds that serve a metro.

The catalog is the MobilityData CSV export (one row per source). Each row has a
bounding box and `urls.latest`, a copy of the newest validated dataset that
MobilityData hosts on Google Cloud Storage (the producer's own `urls.direct_download`
is the fallback).
"""
import csv

# The catalog's CSV export (columns mdb_source_id, data_type, status, redirect.id,
# location.bounding_box.*, urls.latest, urls.direct_download, ...).
CATALOG_URL = "https://storage.googleapis.com/mdb-csv/sources.csv"


def _f(r, k):
    try:
        return float(r.get(k) or "")
    except ValueError:
        return None


def read_catalog(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select_feeds(rows, bbox, include=None, exclude=None, min_share=0.5):
    """Active GTFS sources whose bounding box lies mostly (>= min_share of its area, or its
    centre) inside `bbox` (xmin, ymin, xmax, ymax). `include` (source ids) overrides the search."""
    exclude = {str(x) for x in (exclude or [])}
    if include:
        want = {str(x) for x in include}
        return [r for r in rows if r["mdb_source_id"] in want]
    xmin, ymin, xmax, ymax = bbox
    out = []
    for r in rows:
        if r.get("data_type") != "gtfs" or r["mdb_source_id"] in exclude:
            continue
        if (r.get("status") or "").strip() in ("deprecated", "inactive") or (r.get("redirect.id") or "").strip():
            continue
        a, b = _f(r, "location.bounding_box.minimum_latitude"), _f(r, "location.bounding_box.maximum_latitude")
        c, d = _f(r, "location.bounding_box.minimum_longitude"), _f(r, "location.bounding_box.maximum_longitude")
        if None in (a, b, c, d) or b <= a or d <= c or a == 0 or b == 0:
            continue
        ix = max(0.0, min(d, xmax) - max(c, xmin)) * max(0.0, min(b, ymax) - max(a, ymin))
        share = ix / ((d - c) * (b - a))
        cx, cy = (c + d) / 2, (a + b) / 2
        if share >= min_share or (xmin <= cx <= xmax and ymin <= cy <= ymax):
            out.append(r)
    return out


def feed_urls(r):
    """Download candidates for one source: MobilityData's hosted latest copy, then the producer URL."""
    urls = []
    latest = (r.get("urls.latest") or "").strip()
    if latest:
        urls.append(latest)
    direct = (r.get("urls.direct_download") or "").strip()
    if direct and (r.get("urls.authentication_type") or "0").strip() in ("", "0"):
        urls.append(direct)
    return urls
