"""Census inputs: block-group population and centres of population (CenPop 2020),
block-group land area (TIGER/Line 2020 attribute table), and the OMB CBSA
delineation (to check a registry entry's county list).

Parsers are pure functions over local files so they can be tested offline.
"""
import csv
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

CENPOP_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/blkgrp/CenPop2020_Mean_BG{st}.txt"
TIGER_BG_URL = "https://www2.census.gov/geo/tiger/TIGER2020/BG/tl_2020_{st}_bg.zip"
CBSA_URL = ("https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/"
            "2023/delineation-files/list1_2023.xlsx")


# ---------- CenPop 2020 (block-group centres of population) ----------
def parse_cenpop(path, counties=None):
    """CenPop2020_Mean_BG<ST>.txt -> {geoid12: {pop, lat, lon, county_fips}}.
    `counties`: 5-digit FIPS to keep (None = all)."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            st, co = r["STATEFP"].zfill(2), r["COUNTYFP"].zfill(3)
            cf = st + co
            if counties is not None and cf not in counties:
                continue
            geoid = cf + r["TRACTCE"].zfill(6) + r["BLKGRPCE"]
            out[geoid] = {"pop": int(r["POPULATION"]), "lat": float(r["LATITUDE"]),
                          "lon": float(r["LONGITUDE"]), "county_fips": cf}
    return out


# ---------- TIGER/Line block groups: the .dbf attribute table only ----------
def read_dbf(data):
    """Minimal dBASE III reader: bytes -> list of {field: str}. Enough for TIGER .dbf files."""
    nrec, hlen, rlen = struct.unpack_from("<IHH", data, 4)
    fields, off = [], 32
    while data[off] != 0x0D:
        name = data[off:off + 11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, data[off + 16]))
        off += 32
    rows = []
    for i in range(nrec):
        p = hlen + i * rlen
        if data[p:p + 1] == b"*":       # deleted record
            continue
        p += 1
        row = {}
        for name, ln in fields:
            row[name] = data[p:p + ln].decode("latin-1").strip()
            p += ln
        rows.append(row)
    return rows


def parse_tiger_bg(zip_path, counties=None):
    """tl_2020_<st>_bg.zip -> {geoid12: {aland_m2, awater_m2, intpt_lat, intpt_lon}}."""
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".dbf"))
        rows = read_dbf(z.read(name))
    out = {}
    for r in rows:
        g = r.get("GEOID") or r.get("GEOID20")
        if counties is not None and g[:5] not in counties:
            continue
        out[g] = {"aland_m2": float(r.get("ALAND") or r.get("ALAND20") or 0),
                  "awater_m2": float(r.get("AWATER") or r.get("AWATER20") or 0),
                  "intpt_lat": float(r.get("INTPTLAT") or r.get("INTPTLAT20")),
                  "intpt_lon": float(r.get("INTPTLON") or r.get("INTPTLON20"))}
    return out


# ---------- OMB CBSA delineation (xlsx, no openpyxl needed) ----------
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx_rows(path):
    """First worksheet of an .xlsx as a list of rows (lists of str)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
        sheet = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
        root = ET.fromstring(z.read(sheet))
    rows = []
    for row in root.iter("{%s}row" % _NS["m"]):
        cells = {}
        for c in row.findall("m:c", _NS):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            ci = 0
            for ch in col:
                ci = ci * 26 + ord(ch) - 64
            v = c.find("m:v", _NS)
            if c.get("t") == "s" and v is not None:
                val = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                val = "".join(t.text or "" for t in c.iter("{%s}t" % _NS["m"]))
            else:
                val = v.text if v is not None else ""
            cells[ci - 1] = val
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return rows


def cbsa_counties(path, cbsa):
    """list1_<year>.xlsx -> {cbsa_title, counties: {fips5: county name}} for one CBSA code."""
    rows = read_xlsx_rows(path)
    hi = next(i for i, r in enumerate(rows) if "CBSA Code" in r)
    h = rows[hi]
    ix = {k: h.index(k) for k in ("CBSA Code", "CBSA Title", "FIPS State Code", "FIPS County Code")}
    name_col = next((h.index(k) for k in ("County/County Equivalent", "County/County Equivalent Name") if k in h), None)
    title, counties = None, {}
    for r in rows[hi + 1:]:
        if len(r) <= ix["FIPS County Code"] or str(r[ix["CBSA Code"]]).strip() != str(cbsa):
            continue
        title = r[ix["CBSA Title"]]
        fips = str(r[ix["FIPS State Code"]]).zfill(2) + str(r[ix["FIPS County Code"]]).zfill(3)
        counties[fips] = r[name_col] if name_col is not None else ""
    return {"cbsa_title": title, "counties": counties}

