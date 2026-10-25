"""Overture Maps transportation segments (roads, rail) for a metro bbox, in exactly
the schema dfwt/osmroute.py reads. Same release, columns and road classes as the
DFW extract (tools/fetch_osm.py), only the bbox differs.

Optional, off by default: Overture places (points of interest) counted per block
group, as a clearly-labelled proxy for job locations when LODES is unreachable.
"""
import importlib.util
import os
import time

from dfwt import config

_spec = importlib.util.spec_from_file_location("fetch_osm", config.path("tools", "fetch_osm.py"))
_fo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fo)
RELEASE, ROAD_CLASSES, COLUMNS, sha256 = _fo.RELEASE, _fo.ROAD_CLASSES, _fo.COLUMNS, _fo.sha256

BUCKET = "overturemaps-us-west-2"
REGION = "us-west-2"


def releases():
    """Release folders on the public bucket (newest last). Overture prunes old ones after a few months."""
    from metro.net import open_url
    u = f"https://{BUCKET}.s3.amazonaws.com/?list-type=2&delimiter=/&prefix=release/"
    with open_url(u, 60) as r:
        txt = r.read().decode()
    return sorted({p.split("/")[1] for p in txt.split("<Prefix>")[1:] if p.startswith("release/2")})


def resolve_release(want=None):
    """The pinned DFW release if the bucket still has it, else the newest one."""
    want = want or RELEASE
    try:
        have = releases()
    except Exception:
        return want
    return want if want in have or not have else have[-1]


def _bbox_filter(pc, bbox):
    xmin, ymin, xmax, ymax = bbox
    return ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin) &
            (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin))


def fetch_segments(release, bbox, subtype, classes, out):
    """One subtype ('road' / 'rail') of transportation/segment inside bbox -> parquet. Returns rows."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    import pyarrow.parquet as pq
    s3 = fs.S3FileSystem(anonymous=True, region=REGION)
    d = ds.dataset(f"{BUCKET}/release/{release}/theme=transportation/type=segment/", filesystem=s3, format="parquet")
    f = _bbox_filter(pc, bbox) & (pc.field("subtype") == subtype)
    if classes:
        f = f & pc.field("class").isin(classes)
    t0 = time.time()
    tbl = d.to_table(columns=[c for c in COLUMNS if c in d.schema.names], filter=f)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pq.write_table(tbl, out)
    print(f"  overture {subtype}: {tbl.num_rows} segments in {time.time() - t0:.0f}s")
    return tbl.num_rows


def fetch_places(release, bbox, out, min_confidence=0.5):
    """Overture places (id, lon, lat, primary category, confidence) inside bbox -> parquet."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    import pyarrow.parquet as pq
    s3 = fs.S3FileSystem(anonymous=True, region=REGION)
    d = ds.dataset(f"{BUCKET}/release/{release}/theme=places/type=place/", filesystem=s3, format="parquet")
    f = _bbox_filter(pc, bbox) & (pc.field("confidence") >= min_confidence)
    t0 = time.time()
    names = d.schema.names
    if "operating_status" in names:   # newer releases: drop places marked closed
        f = f & ~pc.field("operating_status").isin(["permanently_closed", "temporarily_closed"])
    cat_col = "basic_category" if "basic_category" in names else "categories"   # older releases: categories.primary
    tbl = d.to_table(columns=["id", "bbox", cat_col, "confidence"], filter=f)
    bb = tbl.column("bbox").combine_chunks()
    cat = tbl.column(cat_col).combine_chunks()
    if cat_col == "categories":
        cat = cat.field("primary")
    slim = pa.table({"id": tbl.column("id"), "lon": bb.field("xmin"), "lat": bb.field("ymin"),
                     "category": cat, "confidence": tbl.column("confidence")})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pq.write_table(slim, out)
    print(f"  overture places: {slim.num_rows} in {time.time() - t0:.0f}s")
    return slim.num_rows


def nearest_zone_counts(zone_lonlat, pt_lonlat, max_km=5.0, chunk=4000):
    """Count points by nearest zone centroid (equirectangular distance), ignoring points more
    than `max_km` from every centroid (outside the metro's counties, mostly). Returns
    (counts per zone, points ignored)."""
    import numpy as np
    Z = np.asarray(zone_lonlat, dtype=float)
    P = np.asarray(pt_lonlat, dtype=float).reshape(-1, 2)
    if len(Z) == 0:
        return [], len(P)
    k = np.cos(np.radians(Z[:, 1].mean()))
    Zx, Zy = Z[:, 0] * k, Z[:, 1]
    counts = np.zeros(len(Z), dtype=int)
    lim = (max_km / 111.2) ** 2
    dropped = 0
    for i in range(0, len(P), chunk):
        px, py = P[i:i + chunk, 0:1] * k, P[i:i + chunk, 1:2]
        d2 = (px - Zx) ** 2 + (py - Zy) ** 2
        j = d2.argmin(axis=1)
        ok = d2[np.arange(len(j)), j] <= lim
        dropped += int((~ok).sum())
        counts += np.bincount(j[ok], minlength=len(Z))
    return counts.tolist(), dropped


def source_url(release, kind):
    return f"s3://{BUCKET}/release/{release}/{kind}/"
