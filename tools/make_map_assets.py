#!/usr/bin/env python3
"""Build the offline campus-map GeoJSON assets for the IDRNav Android app.

Reads the read-only extracts under ``data/map/`` and writes six files to
``IDRNav/app/src/main/assets/map/``:

    buildings.geojson  OSM buildings + Microsoft gap-fill  (R7 sections 5.2, 5.3)
    campus.geojson     the campus boundary polygon         (R7 section 1.7)
    features.geojson   sport / water / green / landuse / parking fills
    labels.geojson     one point label per distinct name   (R7 section 5.4)
    roads.geojson      road + path lines
    graph.json         the map-matcher road graph          (900 m Overpass extract)

Re-runnable and deterministic; stdlib + numpy only (no shapely, no GDAL).
All coordinates are rounded to 6 decimals and the JSON is written compact.

Usage:
    .venv/bin/python tools/make_map_assets.py [--ms-campus-only]

``--ms-campus-only`` additionally requires a Microsoft footprint's centroid to be
inside the campus polygon.  Off by default: R7 section 5.2 states the merge rule
with three conditions only (see the note printed at the end of a run).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, OrderedDict

import numpy as np

# --------------------------------------------------------------------------- paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "map")
DST = os.path.join(ROOT, "IDRNav", "app", "src", "main", "assets", "map")

F_OSM = os.path.join(SRC, "snu_osm_full.geojson")
F_MS = os.path.join(SRC, "snu_buildings_ms.geojson")
F_CAMPUS = os.path.join(SRC, "snu_campus_boundary.geojson")
F_HIGHWAYS = os.path.join(SRC, "snu_osm_highways_900m.json")

# ------------------------------------------------------------------ local metric CRS
# Equirectangular metres about the campus centre (R7 header).
LAT0, LON0 = 28.524416, 77.573818
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 111320.0

NDIGITS = 6
MS_HEIGHT = 6.4          # R7 section 5.3: no Microsoft height estimates exist for SNU
MS_MIN_AREA = 40.0       # m^2
MS_MIN_CONF = 0.85


# ------------------------------------------------------------------- geometry helpers
def to_xy(ring):
    """[[lon, lat], ...] -> Nx2 array of local metres."""
    a = np.asarray(ring, dtype=float)
    return np.column_stack(((a[:, 0] - LON0) * KX, (a[:, 1] - LAT0) * KY))


def ring_area_m2(ring):
    """Absolute shoelace area of a closed ring, in square metres."""
    p = to_xy(ring)
    if len(p) < 4:
        return 0.0
    x, y = p[:, 0], p[:, 1]
    return abs(float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))) / 2.0


def ring_centroid(ring):
    """Shoelace centroid of a closed ring, back in [lon, lat]."""
    p = to_xy(ring)
    x, y = p[:, 0], p[:, 1]
    cross = x[:-1] * y[1:] - x[1:] * y[:-1]
    a = float(cross.sum()) / 2.0
    if abs(a) < 1e-9:                                   # degenerate: vertex mean
        cx, cy = float(x.mean()), float(y.mean())
    else:
        cx = float(((x[:-1] + x[1:]) * cross).sum()) / (6.0 * a)
        cy = float(((y[:-1] + y[1:]) * cross).sum()) / (6.0 * a)
    return [LON0 + cx / KX, LAT0 + cy / KY]


def polygons_of(geom):
    """Geometry -> list of polygons, each a list of rings (outer first)."""
    if geom is None:
        return []
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    return []


def outer_rings(geom):
    return [poly[0] for poly in polygons_of(geom) if poly]


def geom_area_m2(geom):
    total = 0.0
    for poly in polygons_of(geom):
        if not poly:
            continue
        total += ring_area_m2(poly[0]) - sum(ring_area_m2(r) for r in poly[1:])
    return total


def point_in_ring(pt, ring):
    """Ray casting on a closed ring, in lon/lat (the local scale is monotone in both
    axes so the test is identical in metres)."""
    x, y = pt
    r = np.asarray(ring, dtype=float)
    x1, y1 = r[:-1, 0], r[:-1, 1]
    x2, y2 = r[1:, 0], r[1:, 1]
    straddles = (y1 > y) != (y2 > y)
    if not straddles.any():
        return False
    x1, y1, x2, y2 = x1[straddles], y1[straddles], x2[straddles], y2[straddles]
    xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    return bool((xint > x).sum() % 2 == 1)


def point_in_geom(pt, geom):
    """Inside an outer ring and outside every hole of the same polygon."""
    for poly in polygons_of(geom):
        if not poly or not point_in_ring(pt, poly[0]):
            continue
        if any(point_in_ring(pt, hole) for hole in poly[1:]):
            continue
        return True
    return False


def bbox_of(geom):
    xs, ys = [], []
    for poly in polygons_of(geom):
        for ring in poly:
            a = np.asarray(ring, dtype=float)
            xs.append(a[:, 0]); ys.append(a[:, 1])
    if not xs:
        return None
    xs = np.concatenate(xs); ys = np.concatenate(ys)
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def label_point(feature):
    """Where a label for this feature goes: the largest polygon's centroid, the
    middle vertex of a line, or the point itself."""
    geom = feature["geometry"]
    t = geom["type"]
    if t == "Point":
        return list(geom["coordinates"])
    if t in ("Polygon", "MultiPolygon"):
        rings = outer_rings(geom)
        if rings:
            return ring_centroid(max(rings, key=ring_area_m2))
    if t == "LineString":
        c = geom["coordinates"]
        return list(c[len(c) // 2])
    if t == "MultiLineString":
        c = max(geom["coordinates"], key=len)
        return list(c[len(c) // 2])
    raise ValueError("no label point for geometry type %s" % t)


def round_coords(obj):
    """Round every coordinate in a GeoJSON geometry to NDIGITS."""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), NDIGITS) for v in obj]
        return [round_coords(v) for v in obj]
    return obj


def round_geometry(geom):
    g = {"type": geom["type"], "coordinates": round_coords(geom["coordinates"])}
    return g


def feature(geom, props):
    return {"type": "Feature", "properties": props, "geometry": round_geometry(geom)}


def fc(features, name):
    return {"type": "FeatureCollection", "name": name, "features": features}


def write_json(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False)
    return os.path.getsize(path)


# ------------------------------------------------------------------ height rule (5.3)
DEFAULT_H = {
    "dormitory": 19.2, "residential": 9.6, "apartments": 16.0, "university": 12.8,
    "school": 9.6, "college": 12.8, "commercial": 9.6, "retail": 6.4,
    "industrial": 8.0, "warehouse": 8.0, "greenhouse": 4.0, "roof": 4.0,
    "shed": 3.2, "garage": 3.2, "garages": 3.2, "hut": 3.2, "service": 3.2,
    "construction": 9.6, "yes": 6.4,
}
LEVEL_M = 3.2


def parse_len(v):
    if v is None:
        return None
    s = str(v).strip().lower().replace("m", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def height_for(props):
    """R7 section 5.3.  Prefer the value osm2geojson.py already stamped on the feature,
    recompute it when absent so the script survives a re-extract."""
    h = parse_len(props.get("render_height"))
    src = props.get("height_source")
    if h and h > 0 and src:
        return round(h, 2), ("height" if src == "building:height" else src)
    h = parse_len(props.get("height"))
    if h and h > 0:
        return round(h, 2), "height"
    h = parse_len(props.get("building:height"))
    if h and h > 0:
        return round(h, 2), "height"
    lv = parse_len(props.get("building:levels"))
    if lv and lv > 0:
        return round(lv * LEVEL_M, 2), "levels"
    return DEFAULT_H.get(props.get("building", "yes"), 6.4), "default"


def min_height_for(props):
    if "render_min_height" in props:
        mh = parse_len(props.get("render_min_height"))
        if mh is not None and mh >= 0:
            return round(mh, 2)
    mh = parse_len(props.get("min_height"))
    if mh:
        return round(mh, 2)
    ml = parse_len(props.get("building:min_level"))
    if ml:
        return round(ml * LEVEL_M, 2)
    return 0.0


# --------------------------------------------------------------- label priority (5.4)
SORT_BY_NAME = {
    "Shiv Nadar University": 0,
    # 10 - the landmarks a viewer looks for first
    "Central Library": 10, "Indoor Sports Complex": 10,
    "Block A": 10, "Block B": 10, "Block C": 10, "Block D": 10,
    # 20 - hostels and the two other academic blocks
    "Hostel 1A": 20, "Hostel 1B": 20, "Hostel 1C": 20,
    "Hostel 2A": 20, "Hostel 2B": 20, "Hostel 2C": 20,
    "Hostel 3A": 20, "Hostel 3B": 20, "Hostel 3C": 20,
    "Management Block": 20, "Research Annexe": 20,
    # 30 - daily-use services
    "Dining Hall 1": 30, "Dining Hall 2": 30, "Dining Hall 3": 30,
    "Health and wellness centre, SNU": 30, "Auctus Supermarket": 30,
    "Pharmacy": 30, "Shiv Nadar University Post Office": 30,
    # 40 - big open features
    "Football Ground": 40, "Cricket Ground": 40, "Lake SNU": 40,
    "SNU Biodiversity Park": 40, "Shivaji park": 40, "Golf Course": 40,
    "Amphitheatre": 40,
    # 50 - courts
    "Tennis Courts": 50, "Basketball Court": 50, "Basketball Courts": 50,
    "Volleyball Court": 50, "Squash Courts": 50, "Badminton Courts": 50,
    "Chess Garden": 50,
    # 60 - gates, parking, security
    "SNU Gate No. 1": 60, "SNU Gate No. 2": 60, "Parking 1": 60,
    "Entrance Security Office": 60,
    # 70 - small POIs
    "HDFC Bank": 70, "PNB ATM": 70, "Mini Mart": 70, "Belleza": 70,
    "Stage": 70, "The Lonely Tree": 70,
}

MINZOOM = {0: 12, 10: 15.5, 20: 16, 30: 16.5, 40: 16, 50: 17, 60: 16.5, 70: 17.5}

BIG_SPORTS = {"soccer", "cricket", "equestrian", "running"}


def sort_key_fallback(kind, props, geom_type):
    """Used only for a named feature that is not in R7's table, so a future OSM edit
    still gets a sensible priority instead of crashing the build."""
    if kind == "campus":
        return 0
    if kind == "building":
        b = props.get("building")
        amenity = props.get("amenity")
        if amenity == "library" or props.get("leisure") == "sports_centre":
            return 10
        if b == "dormitory":
            return 20
        if b in ("university", "college"):
            return 20
        if amenity in ("food_court", "clinic", "pharmacy", "post_office", "restaurant",
                       "cafe", "doctors") or props.get("shop"):
            return 30
        if props.get("office") == "security":
            return 60
        return 70
    if kind == "sport":
        if props.get("leisure") in ("golf_course", "track", "stadium"):
            return 40
        if props.get("sport") in BIG_SPORTS:
            return 40
        return 50
    if kind == "water":
        return 40
    if kind == "gate" or kind == "parking":
        return 60
    if kind == "poi":
        # An area POI is a place (Amphitheatre, the parks); a node POI is a shop.
        if geom_type in ("Polygon", "MultiPolygon"):
            return 40
        return 70
    return 70


# ------------------------------------------------------------------------------ build
def load(path):
    with open(path) as fh:
        return json.load(fh)


def build_buildings(osm_feats, ms_feats, campus_geom, ms_campus_only, log):
    out = []

    osm_b = [f for f in osm_feats if f["properties"].get("@class") == "building"]
    dropped_routes = [f for f in osm_b if f["properties"].get("type") == "route"]
    osm_b = [f for f in osm_b if f["properties"].get("type") != "route"]
    if dropped_routes:
        log.append("  dropped %d type=route relation(s) from buildings" % len(dropped_routes))

    # "Dining Hall 3" is tagged on two ways ~1.25 km apart (R7 section 5.4 calls it a
    # duplicate).  Both are real footprints, so keep both polygons and let only the
    # larger one carry the name -- that is what the label dedupe needs.
    by_name = {}
    for f in osm_b:
        n = f["properties"].get("name")
        if n:
            by_name.setdefault(n, []).append(f)
    demoted = set()
    for n, group in by_name.items():
        if len(group) < 2:
            continue
        group_sorted = sorted(group, key=lambda f: -geom_area_m2(f["geometry"]))
        keeper = group_sorted[0]
        for f in group_sorted[1:]:
            demoted.add(id(f))
        log.append("  duplicate building name %r on %d ways: name kept on %s (%.0f m2), "
                   "dropped from %s" % (n, len(group), keeper["properties"]["@id"],
                                        geom_area_m2(keeper["geometry"]),
                                        ", ".join("%s (%.0f m2)" % (
                                            g["properties"]["@id"], geom_area_m2(g["geometry"]))
                                            for g in group_sorted[1:])))

    for f in osm_b:
        p = f["properties"]
        h, hsrc = height_for(p)
        out.append(feature(f["geometry"], {
            "name": None if id(f) in demoted else (p.get("name") or None),
            "render_height": h,
            "render_min_height": min_height_for(p),
            "height_source": hsrc,
            "source": "osm",
            "building": p.get("building") or "yes",
        }))

    # ------------------------------------------------- Microsoft gap-fill (section 5.2)
    osm_geoms = [f["geometry"] for f in osm_b]
    osm_boxes = [bbox_of(g) for g in osm_geoms]
    counts = Counter()
    kept_ms = []
    for f in ms_feats:
        geom = f["geometry"]
        rings = outer_rings(geom)
        if not rings:
            counts["no_polygon"] += 1
            continue
        c = ring_centroid(max(rings, key=ring_area_m2))
        conf = float(f["properties"].get("confidence", 0.0))
        area = geom_area_m2(geom)
        inside_campus = point_in_geom(c, campus_geom)
        if inside_campus:
            counts["in_campus"] += 1
        hit = False
        for g, bb in zip(osm_geoms, osm_boxes):
            if bb is None:
                continue
            if not (bb[0] <= c[0] <= bb[2] and bb[1] <= c[1] <= bb[3]):
                continue
            if point_in_geom(c, g):
                hit = True
                break
        if hit:
            counts["rej_osm_overlap"] += 1
            continue
        counts["no_osm_twin"] += 1
        if inside_campus:
            counts["no_osm_twin_in_campus"] += 1
        if area < MS_MIN_AREA:
            counts["rej_area"] += 1
            continue
        if conf < MS_MIN_CONF:
            counts["rej_conf"] += 1
            continue
        counts["pass_rule"] += 1
        if inside_campus:
            counts["pass_rule_in_campus"] += 1
        if ms_campus_only and not inside_campus:
            counts["rej_outside_campus"] += 1
            continue
        kept_ms.append(f)

    for f in kept_ms:
        out.append(feature(f["geometry"], {
            "name": None,
            "render_height": MS_HEIGHT,
            "render_min_height": 0.0,
            "height_source": "ms",
            "source": "ms",
            "building": "ms",
        }))

    return out, len(osm_b), len(kept_ms), counts


def build_features(osm_feats, log):
    """Fill / line features, keyed by a single `kind` the style can filter on."""
    LANDUSE_KIND = {
        "grass": "grass",
        "farmland": "farmland",
        "construction": "construction",
        "forest": "green",             # R7 section 5.4 layer 5 groups forest with the parks
        "recreation_ground": "grass",  # "Ground" -- an open field, renders as grass
    }
    out = []
    skipped = Counter()
    for f in osm_feats:
        p = f["properties"]
        cls = p.get("@class")
        gt = f["geometry"]["type"]
        if cls == "sport":
            kind = "sport"
        elif cls == "water":
            kind = "water"
        elif cls == "green":
            kind = "green"
        elif cls == "parking":
            kind = "parking"
        elif cls == "landuse":
            kind = LANDUSE_KIND.get(p.get("landuse"))
            if kind is None:
                skipped["landuse=" + str(p.get("landuse"))] += 1
                continue
        else:
            continue
        if gt not in ("Polygon", "MultiPolygon", "LineString", "MultiLineString"):
            skipped["geometry=" + gt] += 1
            continue
        out.append(feature(f["geometry"], {
            "kind": kind,
            "name": p.get("name") or None,
            "sport": p.get("sport") or None,
        }))
    for k, v in sorted(skipped.items()):
        log.append("  features: skipped %d x %s (no kind in the agreed enum)" % (v, k))
    return out


def build_roads(osm_feats, log):
    out = []
    skipped = Counter()
    for f in osm_feats:
        p = f["properties"]
        cls = p.get("@class")
        if cls not in ("road", "path"):
            continue
        if f["geometry"]["type"] != "LineString":
            skipped[f["geometry"]["type"]] += 1
            continue
        out.append(feature(f["geometry"], {
            "highway": p.get("highway"),
            "kind": cls,
            "name": p.get("name") or None,
            "surface": p.get("surface") or None,
        }))
    for k, v in sorted(skipped.items()):
        log.append("  roads: skipped %d non-LineString (%s)" % (v, k))
    return out


def build_labels(osm_feats, buildings, campus_feature, log):
    """One point per distinct name.  Sources in precedence order, so the first feature
    to claim a name wins."""
    cands = []  # (kind, props_for_priority, geometry_holder)

    cname = campus_feature["properties"].get("name") or "Shiv Nadar University"
    cands.append(("campus", cname, {"geometry": campus_feature["geometry"]},
                  campus_feature["properties"]))

    for f in buildings:                      # the merged set, so the demoted twin is null
        n = f["properties"].get("name")
        if n:
            cands.append(("building", n, f, f["properties"]))

    # OSM tags carry the detail the fallback priority needs; index them by name.
    osm_props = {}
    for f in osm_feats:
        n = f["properties"].get("name")
        if n:
            osm_props.setdefault(n, f["properties"])

    def collect(kind, pred):
        for f in osm_feats:
            p = f["properties"]
            n = p.get("name")
            if n and pred(p):
                cands.append((kind, n, f, p))

    collect("sport", lambda p: p.get("@class") == "sport")
    collect("water", lambda p: p.get("@class") == "water")
    collect("parking", lambda p: p.get("@class") == "parking")
    collect("gate", lambda p: p.get("barrier") == "gate")
    # R7 section 5.4 layer 23 labels @class poi / tree / barrier; the two named parks
    # (@class green) are in the sort-key 40 row of the priority table, so they belong here.
    collect("poi", lambda p: p.get("@class") in ("poi", "tree", "green"))

    out = []
    seen = {}
    for kind, name, holder, props in cands:
        if name in seen:
            if seen[name] != kind:
                log.append("  label dedupe: %r already taken by kind=%s, dropped kind=%s"
                           % (name, seen[name], kind))
            continue
        seen[name] = kind
        sk = SORT_BY_NAME.get(name)
        if sk is None:
            sk = sort_key_fallback(kind, osm_props.get(name, props),
                                   holder["geometry"]["type"])
            log.append("  label %r not in the R7 priority table, fallback sort_key=%d"
                       % (name, sk))
        pt = label_point(holder)
        out.append(feature({"type": "Point", "coordinates": pt}, {
            "name": name,
            "kind": kind,
            "sort_key": sk,
            "minzoom": MINZOOM[sk],
        }))
    out.sort(key=lambda f: (f["properties"]["sort_key"], f["properties"]["name"]))
    return out


def build_graph(raw, log):
    ways, nodes = [], OrderedDict()
    kinds = Counter()
    for e in raw.get("elements", []):
        if e.get("type") != "way":
            continue
        tags = e.get("tags") or {}
        hw = tags.get("highway")
        if not hw:
            continue
        ids = e.get("nodes") or []
        geom = e.get("geometry") or []
        if len(ids) < 2 or len(ids) != len(geom):
            log.append("  graph: skipped way %s (%d node ids vs %d geometry points)"
                       % (e.get("id"), len(ids), len(geom)))
            continue
        for nid, pt in zip(ids, geom):
            nid = int(nid)
            lat, lon = round(float(pt["lat"]), NDIGITS), round(float(pt["lon"]), NDIGITS)
            prev = nodes.get(nid)
            if prev is not None and (abs(prev[0] - lat) > 1e-6 or abs(prev[1] - lon) > 1e-6):
                log.append("  graph: node %d has conflicting coordinates" % nid)
            nodes[nid] = (lat, lon)
        kinds[hw] += 1
        ways.append({"id": int(e["id"]), "highway": hw, "nodes": [int(n) for n in ids]})
    log.append("  graph highway mix: " + ", ".join("%s=%d" % kv for kv in kinds.most_common()))
    return {
        "nodes": [[nid, lat, lon] for nid, (lat, lon) in nodes.items()],
        "ways": ways,
    }


# ------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ms-campus-only", action="store_true",
                    help="also require a Microsoft footprint centroid inside the campus")
    args = ap.parse_args()

    os.makedirs(DST, exist_ok=True)
    log = []

    osm_feats = load(F_OSM)["features"]
    ms_feats = load(F_MS)["features"]
    campus_fc = load(F_CAMPUS)
    campus_feature = campus_fc["features"][0]
    campus_geom = campus_feature["geometry"]

    # 1 -------------------------------------------------------------------- buildings
    buildings, n_osm_b, n_ms_b, ms_counts = build_buildings(
        osm_feats, ms_feats, campus_geom, args.ms_campus_only, log)

    # 2 ----------------------------------------------------------------------- campus
    campus = [feature(campus_geom, {"name": campus_feature["properties"].get("name")
                                    or "Shiv Nadar University"})]

    # 3 --------------------------------------------------------------------- features
    features = build_features(osm_feats, log)

    # 4 ----------------------------------------------------------------------- labels
    labels = build_labels(osm_feats, buildings, campus_feature, log)

    # 5 ------------------------------------------------------------------------ roads
    roads = build_roads(osm_feats, log)

    # 6 ------------------------------------------------------------------------ graph
    graph = build_graph(load(F_HIGHWAYS), log)

    outputs = [
        ("buildings.geojson", fc(buildings, "snu_buildings_merged"), len(buildings)),
        ("campus.geojson", fc(campus, "snu_campus"), len(campus)),
        ("features.geojson", fc(features, "snu_features"), len(features)),
        ("labels.geojson", fc(labels, "snu_labels"), len(labels)),
        ("roads.geojson", fc(roads, "snu_roads"), len(roads)),
    ]

    print("=== outputs (%s) ===" % os.path.relpath(DST, ROOT))
    sizes = {}
    for fname, obj, n in outputs:
        path = os.path.join(DST, fname)
        sizes[fname] = write_json(path, obj)
        print("  %-18s %4d features  %9d bytes" % (fname, n, sizes[fname]))
    gpath = os.path.join(DST, "graph.json")
    sizes["graph.json"] = write_json(gpath, graph)
    print("  %-18s %4d ways %5d nodes  %9d bytes"
          % ("graph.json", len(graph["ways"]), len(graph["nodes"]), sizes["graph.json"]))
    print("  %-18s %28d bytes" % ("TOTAL", sum(sizes.values())))

    # ------------------------------------------------------------------------- counts
    named_buildings = sum(1 for f in buildings if f["properties"]["name"])
    print("\n=== counts ===")
    print("  OSM buildings kept        : %d (%d carry a name)" % (n_osm_b, named_buildings))
    print("  Microsoft footprints added: %d" % n_ms_b)
    print("  named labels              : %d" % len(labels))
    print("  label kinds               : %s"
          % dict(Counter(f["properties"]["kind"] for f in labels)))
    print("  label sort keys           : %s"
          % dict(sorted(Counter(f["properties"]["sort_key"] for f in labels).items())))
    print("  feature kinds             : %s"
          % dict(Counter(f["properties"]["kind"] for f in features).most_common()))
    print("  road kinds                : %s"
          % dict(Counter(f["properties"]["kind"] for f in roads).most_common()))
    print("  height sources            : %s"
          % dict(Counter(f["properties"]["height_source"] for f in buildings).most_common()))

    print("\n=== Microsoft merge rule (R7 section 5.2) ===")
    print("  candidates in file            : %d" % len(ms_feats))
    print("  centroid inside campus        : %d   (R7: 139)" % ms_counts["in_campus"])
    print("  centroid inside an OSM building: %d  -> rejected" % ms_counts["rej_osm_overlap"])
    print("  no OSM twin                   : %d   (of which in campus: %d, R7: 103)"
          % (ms_counts["no_osm_twin"], ms_counts["no_osm_twin_in_campus"]))
    print("  rejected area < %.0f m2         : %d" % (MS_MIN_AREA, ms_counts["rej_area"]))
    print("  rejected confidence < %.2f     : %d" % (MS_MIN_CONF, ms_counts["rej_conf"]))
    print("  pass all three conditions     : %d   (of which in campus: %d)"
          % (ms_counts["pass_rule"], ms_counts["pass_rule_in_campus"]))
    if args.ms_campus_only:
        print("  --ms-campus-only dropped      : %d" % ms_counts["rej_outside_campus"])
    else:
        print("  --ms-campus-only would drop   : %d"
              % (ms_counts["pass_rule"] - ms_counts["pass_rule_in_campus"]))

    if log:
        print("\n=== notes ===")
        for line in log:
            print(line)

    # ------------------------------------------------------------------------ asserts
    print("\n=== checks ===")
    for f in buildings:
        h = f["properties"]["render_height"]
        assert isinstance(h, (int, float)) and not isinstance(h, bool) and h > 0, \
            "bad render_height %r" % (h,)
        mh = f["properties"]["render_min_height"]
        assert isinstance(mh, (int, float)) and mh >= 0, "bad render_min_height %r" % (mh,)
    print("  ok  every render_height is a number > 0 (%d buildings, min %.1f m, max %.1f m)"
          % (len(buildings),
             min(f["properties"]["render_height"] for f in buildings),
             max(f["properties"]["render_height"] for f in buildings)))

    names = [f["properties"]["name"] for f in labels]
    dupes = [n for n, c in Counter(names).items() if c > 1]
    assert not dupes, "duplicate label names: %r" % dupes
    assert all(n for n in names), "a label has an empty name"
    print("  ok  no two label features share a name (%d labels)" % len(names))

    assert len(graph["ways"]) > 200, "graph has only %d ways" % len(graph["ways"])
    node_ids = {n[0] for n in graph["nodes"]}
    assert len(node_ids) == len(graph["nodes"]), "duplicate node ids in graph"
    missing = {n for w in graph["ways"] for n in w["nodes"]} - node_ids
    assert not missing, "%d way node ids missing from nodes" % len(missing)
    assert all(isinstance(n, int) for n in node_ids), "node ids must be ints"
    print("  ok  graph.json has %d ways (> 200), %d nodes, no dangling node id"
          % (len(graph["ways"]), len(graph["nodes"])))

    for fname in list(sizes):
        with open(os.path.join(DST, fname)) as fh:
            obj = json.load(fh)
        assert obj, "%s parsed empty" % fname
    print("  ok  all %d outputs re-parse with json.load" % len(sizes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
