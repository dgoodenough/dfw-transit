"""Write the lever_service_* scenario edits.csv files (edit here, then: python tools/make_service_levers.py)."""
import csv
import os

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenarios")

DART_LRT = ["E12", "E13", "E14", "E15"]
COMMUTER_INNER = ["E05", "E07", "E08", "E25", "E30", "E34", "E37"]     # proposed, <60 km
COMMUTER_OUTER = ["E31", "E32", "E33", "E35", "E36"]                   # long rural lines
COMMUTER_EXIST = ["E09", "E10", "E11"]
BRT = ["E01", "E02", "E04", "E21", "E24", "E27", "E28", "E29", "E38"]
NEW_METRO_OPEN = ["F01", "F02", "F05", "F06", "E16", "E17", "E18", "E19", "E22", "E23", "E26"]
# F03, F04, F07 share the Fort Worth Jones St tunnel (Central Station - T&P) at 30 tph already


def frequent():
    rows = []
    for l in DART_LRT:
        rows.append(("set_headway", l, 2035, 7.5, "DART LRT 7.5 min; needs D2 subway (mall would be 32 tph)"))
        rows.append(("set_headway", l, 2045, 6, "DART LRT 6 min: mall 2 lines x 10 tph, D2 2 lines x 10 tph, CityPlace tunnel 30 tph"))
    rows.append(("set_headway", "E20", 2045, 7.5, "Silver Line 7.5 min with added passing sidings"))
    for l in COMMUTER_EXIST:
        rows.append(("set_headway", l, 2035, 10, "regional rail 10 min all day; full double track + PTC dispatching"))
    for l in COMMUTER_INNER:
        rows.append(("set_headway", l, 2030, 15, "15 min from opening (plan default 20)"))
        rows.append(("set_headway", l, 2045, 10, "regional rail 10 min all day"))
    for l in COMMUTER_OUTER:
        rows.append(("set_headway", l, 2030, 15, "15 min clockface on long outer lines"))
    for l in BRT:
        rows.append(("set_headway", l, 2030, 6, "BRT every 6 min (plan default 8)"))
    for l in NEW_METRO_OPEN:
        rows.append(("set_headway", l, 2050, 5, "metro every 5 min from 2050"))
    return rows


def through(headways=True):
    rows = [
        ("through_route", "F02", "E22", "Blue / I-30", "Ridgmar Mall - FW - Handley - Arlington - Dallas, one train"),
        ("through_route", "F05", "E19", "Berry / I-20", "Lake Worth - Berry - I-20 - Dallas, one train"),
        ("through_route", "E10", "E30", "TRE", "TRE runs through FW T&P to Alvarado"),
        ("through_route", "E10", "E34", "TRE", "TRE runs through Union Station to Terrell (Dallas station 270 m away, one platform)"),
        ("through_route", "E09", "E05", "TEXRail", "TEXRail runs through FW T&P to Primrose"),
        ("through_route", "E07", "E08", "Mansfield-Denton", "SE TexRail + FTW/Denton through FW Central"),
        ("through_route", "E07", "E11", "Mansfield-Denton-Carrollton", "and on over the A-train to Trinity Mills"),
    ]
    return rows


EXPRESS = {   # stops kept: termini, every transfer station, and at least one stop per ~4.5 km (BRT 3.5)
    "E17": "#1;#4;#5;#6;#7;#10;#12;#13;#17;#19;#21;#22;#23;#24;#25;#26;#27;#28;#29;#30;#31;#34;#35",
    "E19": "#1;#3;#6;#7;#9;#11;#14;#17;#20;#23;#25;#27;#28;#29;#30;#32;#33;#34;#35;#36;#37;#38;#39",
    "E22": "#1;#3;#6;#7;#8;#10;#13;#15;#18;#21;#22;#23;#27;#28;#29;#30;#31;#32;#33;#34",
    "E23": "#1;#4;#7;#9;#10;#11;#13;#15;#19;#21;#22;#25;#29;#31;#33;#36",
    "E18": "#1;#4;#7;#11;#14;#15;#16;#17;#18;#19;#20;#21;#22;#23;#25;#27",
    "E21": "#1;#3;#4;#6;#8;#10;#12;#14;#16;#18;#20;#22;#24;#26;#27;#29;#31;#32;#33;#35;#37;#39;#41;#43;#45;#47;#49;#51;#53;#55;#57;#59;#61;#63;#65",
}


def express():
    rows = []
    for l, stops in EXPRESS.items():
        x = l + "X"
        rows.append(("add_express", l, x, stops, "skip-stop express over the local; needs passing tracks/lanes at ~1 in 3 express stops"))
        rows.append(("set_headway", x, 2030, 10, "express every 10 min (local unchanged)"))
    return rows


def upgrade():
    rows = [
        ("set_line", "E25", "mode", "metro", "McKinney corridor (DART-owned) built as light rail instead of commuter rail"),
        ("through_route", "E14", "E25", "Red Line", "Red Line runs on from Parker Road to McKinney: no transfer"),
    ]
    for l, nm in (("E04", "Jacksboro"), ("E27", "Ross Avenue"), ("E28", "Forest Lane")):
        rows.append(("set_line", l, "mode", "metro", f"{nm} BRT rebuilt as light rail by 2050 (evaluate 2050+ only)"))
        rows.append(("set_line", l, "headway", "6", "light rail every 6 min"))
    return rows


def package():
    """Recommended: the frequent network plus commuter-rail through-running (an operating enabler for
    10-minute regional rail: no terminal turnbacks at FW Central, FW T&P or Union Station). Headways
    are set on the original lines first; a joined line runs at the better of its parts' headways.
    The metro joins (Blue/I-30, Berry/I-20), express overlays and mode upgrades are left out: they
    add nothing or little in the model for their cost (see the lever scenarios)."""
    return frequent() + [r for r in through() if r[1] in ("E10", "E09", "E07")]


def write(name, rows):
    d = os.path.join(ROOT, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "edits.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["op", "target", "field", "value", "note"])
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    write("lever_service_frequent", frequent())
    write("lever_service_through", through())
    write("lever_service_express", express())
    write("lever_service_upgrade", upgrade())
    write("lever_service_package", package())
