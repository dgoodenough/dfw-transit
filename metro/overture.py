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


# Landmarks for station names (dfwt/naming.py): a place of one of these categories whose name says what it is.
# Overture's categories are noisy (a dental clinic filed as a hospital, a salon as a college), so the name has to
# match too, and the confidence be high.
LANDMARK = {
    "hospital": (r"hospital|medical cent(er|re)|health (system|science)", r"clinic|dental|urgent|dpc|imaging|surgery cent"),
    "general_hospital": (r"hospital|medical cent(er|re)", r"clinic"),
    "college_university": (r"university|college|\buniv\b", r"salon|bible|beauty|barber|institute of|academy|seminary|online|office|"
                                                         r"bookstore|football|athletic|department|school of|center for"),
    "shopping_mall": (r"\bmall\b|galleria|town cent(er|re)|outlets?\b", r"strip|plaza\b"),
    "stadium_arena": (r"stadium|arena|field|park\b|center\b", r"batting|indoor|skate|soccer complex"),
    "museum": (r"museum", r"kids|party|studio|gallery\b"),
    "zoo": (r"\bzoo\b", r""),
}
# Neighbourhoods: Overture's macrohoods, and neighbourhoods notable enough to have a Wikidata item (its
# neighbourhood layer also holds housing subdivisions: "Timbergrove Manor", "Maxroy Mews"). Airports come from the
# metro registry's anchors instead (Overture's include private strips and airline counters).
HOOD_SUBTYPES = ("macrohood", "neighborhood")
TOWN_SUBTYPES = ("locality",)


def fetch_gazetteer(release, bbox, out, min_confidence=0.9):
    """Landmarks, neighbourhoods and towns inside bbox -> out, in the Overpass JSON shape dfwt.naming.Namer
    reads ({"elements": [{lat, lon, tags: {name, amenity|shop|place|...}}]}). Returns (landmarks, hoods, towns)."""
    import re
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    s3 = fs.S3FileSystem(anonymous=True, region=REGION)
    els = []
    d = ds.dataset(f"{BUCKET}/release/{release}/theme=places/type=place/", filesystem=s3, format="parquet")
    f = _bbox_filter(pc, bbox) & (pc.field("confidence") >= min_confidence) & pc.field("basic_category").isin(list(LANDMARK))
    tbl = d.to_table(columns=["names", "basic_category", "bbox"], filter=f)
    tag = {"hospital": ("amenity", "hospital"), "general_hospital": ("amenity", "hospital"),
           "college_university": ("amenity", "university"), "shopping_mall": ("shop", "mall")}
    seen = set()
    for nm, cat, bb in zip(tbl.column("names").to_pylist(), tbl.column("basic_category").to_pylist(), tbl.column("bbox").to_pylist()):
        name = ((nm or {}).get("primary") or "").strip()
        good, bad = LANDMARK[cat]
        if not name or not re.search(good, name, re.I) or (bad and re.search(bad, name, re.I)) or re.search(r" - |[:,(]", name):
            continue
        key = (name.lower(), round(bb["ymin"], 2), round(bb["xmin"], 2))
        if key in seen:
            continue
        seen.add(key)
        k, v = tag.get(cat, ("amenity", "landmark"))
        els.append({"lat": bb["ymin"], "lon": bb["xmin"], "tags": {"name": name, k: v, "overture_category": cat}})
    n_land = len(els)
    d = ds.dataset(f"{BUCKET}/release/{release}/theme=divisions/type=division/", filesystem=s3, format="parquet")
    f = _bbox_filter(pc, bbox) & pc.field("subtype").isin(list(HOOD_SUBTYPES + TOWN_SUBTYPES))
    tbl = d.to_table(columns=["names", "subtype", "class", "wikidata", "bbox", "population"], filter=f)
    n_hood = n_town = 0
    for nm, sub, cls, wd, bb, pop in zip(tbl.column("names").to_pylist(), tbl.column("subtype").to_pylist(),
                                         tbl.column("class").to_pylist(), tbl.column("wikidata").to_pylist(),
                                         tbl.column("bbox").to_pylist(), tbl.column("population").to_pylist()):
        name = ((nm or {}).get("primary") or "").strip()
        if not name:
            continue
        lat, lon = (bb["ymin"] + bb["ymax"]) / 2, (bb["xmin"] + bb["xmax"]) / 2
        if sub in TOWN_SUBTYPES:   # cities and towns, not the hamlets and villages Overture also lists
            if cls in ("city", "town") or (pop or 0) >= 5000:
                els.append({"lat": lat, "lon": lon, "tags": {"name": name, "place": "town", "population": pop}})
                n_town += 1
        elif sub == "macrohood" or wd:
            els.append({"lat": lat, "lon": lon, "tags": {"name": name, "place": "suburb" if sub == "macrohood" else "neighbourhood"}})
            n_hood += 1
    os.makedirs(os.path.dirname(out), exist_ok=True)
    import json
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"source": f"Overture Maps {release}: places (landmark categories, confidence >= {min_confidence}, "
                             "names that say what they are) and divisions (macrohoods, neighbourhoods with a Wikidata item, "
                             "cities and towns among the localities)", "elements": els}, fh)
    print(f"  gazetteer: {n_land} landmarks, {n_hood} neighbourhoods, {n_town} towns")
    return n_land, n_hood, n_town


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
