"""Fetch the rail and road network for the nine-county area from Overture Maps
(OpenStreetMap-derived transportation segments), for alignment routing.

    pip install -r requirements-geometry.txt
    python tools/fetch_osm.py

Writes data/osm/rail.parquet and data/osm/roads.parquet (gitignored, ~45 MB) and
data/osm/MANIFEST.json (committed: release, filters, row counts, checksums).
Data © OpenStreetMap contributors, ODbL 1.0, via Overture Maps Foundation.
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dfwt import config  # noqa: E402

RELEASE = "2026-09-23.1"
BBOX = (-98.0, 31.95, -95.95, 33.45)
ROAD_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary"]
COLUMNS = ["id", "geometry", "subtype", "class", "subclass", "names", "connectors",
           "road_flags", "rail_flags", "access_restrictions", "bbox"]


def fetch(subtype, classes, out):
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    import pyarrow.parquet as pq
    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")
    d = ds.dataset(f"overturemaps-us-west-2/release/{RELEASE}/theme=transportation/type=segment/",
                   filesystem=s3, format="parquet")
    xmin, ymin, xmax, ymax = BBOX
    f = ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin) &
         (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin) & (pc.field("subtype") == subtype))
    if classes:
        f = f & pc.field("class").isin(classes)
    t0 = time.time()
    tbl = d.to_table(columns=[c for c in COLUMNS if c in d.schema.names], filter=f)
    pq.write_table(tbl, out)
    print(f"{subtype}: {tbl.num_rows} segments in {time.time() - t0:.0f}s -> {os.path.relpath(out, config.ROOT)}")
    return tbl.num_rows


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    out = config.path("data", "osm")
    os.makedirs(out, exist_ok=True)
    files = {"rail.parquet": ("rail", None), "roads.parquet": ("road", ROAD_CLASSES)}
    manifest = {"source": f"Overture Maps transportation/segment, release {RELEASE}",
                "license": "© OpenStreetMap contributors, ODbL 1.0 (via Overture Maps Foundation)",
                "bbox": BBOX, "files": {}}
    for name, (subtype, classes) in files.items():
        p = os.path.join(out, name)
        n = fetch(subtype, classes, p)
        manifest["files"][name] = {"subtype": subtype, "classes": classes, "rows": n, "sha256": sha256(p)}
    with open(os.path.join(out, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    main()
