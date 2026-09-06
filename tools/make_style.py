#!/usr/bin/env python3
"""
tools/make_style.py — build the offline MapLibre style for the IDR Nav app.

Fetches the Protomaps v4 *dark* style, saves it verbatim, then rewrites it for
fully-offline use inside the APK:

  * source   -> pmtiles://file://__FILESDIR__/snu.pmtiles  (app substitutes at runtime)
  * glyphs   -> asset://glyphs/{fontstack}/{range}.pbf
  * sprite   -> asset://sprites/dark
  * colours  -> the IDR design tokens (docs/15_NAV_APP_BUILD_BRIEF.md §4)
  * the flat `buildings` fill layer is removed (the app draws 3-D buildings from GeoJSON)
  * every `text-font` is pinned to one of the three bundled Noto stacks

Also writes style_meta.json, the layer-id index the app uses to reorder /
toggle layers without re-parsing the style.

Pure stdlib (urllib); `requests` is used only if it happens to be importable and
urllib fails.  Never needs node.

Usage:
    tools/make_style.py                 # fetch + build (re-runnable)
    tools/make_style.py --offline       # rebuild from the saved original only
    tools/make_style.py --build 20260905
    tools/make_style.py --check         # verify the built artefacts
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO_ROOT, "IDRNav", "app", "src", "main", "assets")
MAP_DIR = os.path.join(ASSETS, "map")
GLYPH_DIR = os.path.join(ASSETS, "glyphs")
SPRITE_DIR = os.path.join(ASSETS, "sprites")
FONT_DIR = os.path.join(REPO_ROOT, "IDRNav", "app", "src", "main", "res", "font")

ORIGINAL_PATH = os.path.join(MAP_DIR, "protomaps_dark_original.json")
STYLE_PATH = os.path.join(MAP_DIR, "style.json")
META_PATH = os.path.join(MAP_DIR, "style_meta.json")
BUILD_STAMP = os.path.join(MAP_DIR, ".protomaps_build")  # dotfile: aapt does not package it

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------
BBOX = [77.5639, 28.5133, 77.5823, 28.5335]           # W, S, E, N — SNU campus
PMTILES_URL = "pmtiles://file://__FILESDIR__/snu.pmtiles"
GLYPHS_URL = "asset://glyphs/{fontstack}/{range}.pbf"
SPRITE_URL = "asset://sprites/dark"

STYLE_URL = "https://api.protomaps.com/styles/v4/dark/en.json?key={key}"
TESTSTYLES_URL = (
    "https://raw.githubusercontent.com/maplibre/maplibre-native/main/platform/android/"
    "MapLibreAndroidTestApp/src/main/java/org/maplibre/android/testapp/styles/TestStyles.kt"
)
# Same public demo key that docs.protomaps.com/basemaps/maplibre publishes.
FALLBACK_KEY = "e761cc7daedf832a"

BUILD_BASE = "https://build.protomaps.com"
BUILD_START = "20260905"
BUILD_LOOKBACK = 30

BUNDLED_FONTS = ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"]
DEFAULT_FONT = "Noto Sans Regular"
GLYPH_RANGES = ["0-255", "256-511"]
SPRITE_FILES = ["dark.json", "dark.png", "dark@2x.json", "dark@2x.png"]
TTF_FILES = ["barlow_regular.ttf", "barlow_medium.ttf", "barlow_semicondensed_semibold.ttf"]

# --------------------------------------------------------------------------
# design tokens — docs/15_NAV_APP_BUILD_BRIEF.md §4
# --------------------------------------------------------------------------
GROUND = "#101010"       # background + earth
WATER = "#1F262B"
CASING = "#1A1A1A"       # every road casing
ROAD_MINOR = "#2E2E2E"   # minor / service / residential (and rail, pier)
ROAD_MAJOR = "#383838"   # major / highway / trunk / primary / secondary / link
PATH = "#202020"         # footways, paths, tracks — dashed
PATH_DASH = [2, 2]
BOUNDARY = "#262626"
LABEL = "#8C8C8C"
LABEL_PLACE = "#A9A9A9"  # place labels are allowed to sit brighter
HALO = "#101010"
HALO_WIDTH = 1.2
PITCH = "#151B16"        # sports pitches (the only greens, with PARK)
PITCH_EDGE = "#1C241D"
PARK = "#141A15"         # park / forest / vegetation

# neutral landuse greys, all inside the #141414–#181818 window
LU_DARKEST, LU_DARK, LU_MID, LU_LIGHT, LU_LIGHTEST = (
    "#141414", "#151515", "#161616", "#171717", "#181818",
)

LANDUSE_FILL = {
    "landuse_urban_green": PARK,        # allotments, village_green, playground
    "landuse_hospital": LU_LIGHT,
    "landuse_industrial": LU_MID,
    "landuse_school": LU_LIGHT,         # school / university / college — the SNU campus ground
    "landuse_beach": LU_LIGHTEST,
    "landuse_zoo": LU_MID,
    "landuse_aerodrome": LU_DARK,
    "landuse_pedestrian": LU_LIGHTEST,
    "landuse_pier": LU_LIGHTEST,
    "landuse_runway": LU_LIGHTEST,
}

# landcover `kind` -> colour (replaces the shipped rgba() match arms)
LANDCOVER_MATCH = [
    ("grassland", PARK),
    ("barren", LU_LIGHT),
    ("urban_area", LU_DARK),
    ("farmland", LU_MID),
    ("glacier", LU_LIGHTEST),
    ("scrub", PARK),
]
LANDCOVER_DEFAULT = LU_MID

# landuse_park `kind` -> colour, in evaluation order
PARK_CASES = [
    (["national_park", "park", "cemetery", "protected_area",
      "nature_reserve", "forest", "golf_course"], PARK),
    (["wood", "nature_reserve", "forest"], PARK),
    (["scrub", "grassland", "grass"], PARK),
    (["glacier"], LU_LIGHT),
    (["sand"], LU_LIGHTEST),
    (["military", "naval_base", "airfield"], LU_MID),
]
PARK_DEFAULT = LU_MID

# Sports pitches exist in the SNU extract (pitch / sports_centre / recreation_ground:
# Cricket Ground, Football Ground, Tennis Courts, Basketball Court, ...) but NO layer in
# the stock Protomaps style paints them, so they would render as bare earth.  One added
# layer gives the #151B16 token something to colour.
PITCH_KINDS = ["pitch", "sports_centre", "recreation_ground", "stadium", "track"]

ALLOWED_COLORS = {
    GROUND, WATER, CASING, ROAD_MINOR, ROAD_MAJOR, PATH, BOUNDARY,
    LABEL, LABEL_PLACE, HALO, PITCH, PITCH_EDGE, PARK,
    LU_DARKEST, LU_DARK, LU_MID, LU_LIGHT, LU_LIGHTEST,
}

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def log(msg: str = "") -> None:
    print(msg)


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "idr-nav-map-build/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        try:
            import requests  # optional; only reached if urllib failed
        except ImportError:
            raise
        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": "idr-nav-map-build/1.0"})
        resp.raise_for_status()
        return resp.content


def http_ok(url: str, timeout: int = 30) -> bool:
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "idr-nav-map-build/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def resolve_key() -> str:
    """Take the public demo key out of MapLibre's own Android test app."""
    try:
        src = http_get(TESTSTYLES_URL, timeout=40).decode("utf-8", "replace")
        m = re.search(r"api\.protomaps\.com/[^\"']*[?&]key=([A-Za-z0-9_-]+)", src)
        if m:
            log(f"  demo key from TestStyles.kt: {m.group(1)}")
            return m.group(1)
        log("  TestStyles.kt fetched but no protomaps key matched; using fallback")
    except Exception as exc:
        log(f"  TestStyles.kt fetch failed ({exc}); using fallback key")
    return FALLBACK_KEY


def resolve_build(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("PROTOMAPS_BUILD")
    if env:
        return env
    if os.path.exists(BUILD_STAMP):
        with open(BUILD_STAMP) as fh:
            stamp = fh.read().strip()
        if re.fullmatch(r"\d{8}", stamp):
            return stamp
    start = datetime.datetime.strptime(BUILD_START, "%Y%m%d")
    for i in range(BUILD_LOOKBACK + 1):
        day = (start - datetime.timedelta(days=i)).strftime("%Y%m%d")
        if http_ok(f"{BUILD_BASE}/{day}.pmtiles"):
            log(f"  newest Protomaps build: {day}")
            return day
    return "unknown"


# --------------------------------------------------------------------------
# font handling
# --------------------------------------------------------------------------
# expression operators that must never be mistaken for a font stack
EXPR_OPS = {
    "literal", "get", "has", "case", "match", "step", "interpolate", "coalesce",
    "concat", "format", "zoom", "all", "any", "!", "==", "!=", "<", "<=", ">",
    ">=", "in", "!in", "to-string", "to-number", "downcase", "upcase", "let",
    "var", "at", "length", "index-of", "slice", "number-format", "image",
    "is-supported-script", "resolved-locale", "collator", "+", "-", "*", "/",
    "%", "^", "exponential", "linear", "cubic-bezier", "rgb", "rgba",
}


def map_font(name: str) -> str:
    return name if name in BUNDLED_FONTS else DEFAULT_FONT


def fix_font_value(value):
    """Pin every font name inside a `text-font` value to a bundled stack.

    Handles both a plain stack (["Noto Sans Regular"]) and data-driven
    expressions (["case", cond, ["literal", [...]], ["literal", [...]]]).
    """
    if isinstance(value, list):
        # ["literal", ["Noto Sans Medium"]]
        if (len(value) == 2 and value[0] == "literal"
                and isinstance(value[1], list)
                and all(isinstance(x, str) for x in value[1])):
            return ["literal", [map_font(x) for x in value[1]]]
        # a bare font stack: every element a string, head is not an operator
        if value and all(isinstance(x, str) for x in value) and value[0] not in EXPR_OPS:
            return [map_font(x) for x in value]
        return [fix_font_value(x) for x in value]
    return value


def collect_font_stacks(value, out: set) -> None:
    if isinstance(value, list):
        if (len(value) == 2 and value[0] == "literal"
                and isinstance(value[1], list)
                and all(isinstance(x, str) for x in value[1])):
            out.add(tuple(value[1]))
            return
        if value and all(isinstance(x, str) for x in value) and value[0] not in EXPR_OPS:
            out.add(tuple(value))
            return
        for x in value:
            collect_font_stacks(x, out)


# --------------------------------------------------------------------------
# layer classification
# --------------------------------------------------------------------------
def road_class(lid: str) -> str:
    """casing | path | minor | major, from a Protomaps v4 road layer id."""
    if lid.endswith("_casing") or "_casing_" in lid:
        return "casing"
    base = lid[len("roads_"):] if lid.startswith("roads_") else lid
    for prefix in ("tunnels_", "bridges_"):
        if base.startswith(prefix):
            base = base[len(prefix):]
    if base == "other":                     # kind in (other, path) -> footways/tracks
        return "path"
    if base in ("minor", "minor_service", "pier", "rail"):
        return "minor"
    if base in ("link", "major", "highway", "runway", "taxiway"):
        return "major"
    return "minor"


def is_place_label(lid: str) -> bool:
    return lid.startswith("places")


# --------------------------------------------------------------------------
# the transform
# --------------------------------------------------------------------------
def build_style(original: dict) -> dict:
    style = json.loads(json.dumps(original))          # deep copy
    attribution = original["sources"]["protomaps"].get("attribution", "")

    # (a) offline PMTiles source
    style["sources"] = {
        "protomaps": {
            "type": "vector",
            "url": PMTILES_URL,
            "attribution": attribution,
        }
    }
    # (b)(c) bundled glyphs + sprites
    style["glyphs"] = GLYPHS_URL
    style["sprite"] = SPRITE_URL
    # (g)
    style["metadata"] = {"idr_tokens": "v1"}

    layers = []
    for layer in style["layers"]:
        lid = layer["id"]
        ltype = layer["type"]
        slayer = layer.get("source-layer")
        paint = layer.setdefault("paint", {})

        # (e) drop the flat buildings fill — the app extrudes its own from GeoJSON
        if lid == "buildings":
            continue

        if ltype == "background":
            paint["background-color"] = GROUND

        elif ltype == "fill":
            if lid == "earth":
                paint["fill-color"] = GROUND
            elif slayer == "water":
                paint["fill-color"] = WATER
            elif lid == "landcover":
                arms = []
                for kind, colour in LANDCOVER_MATCH:
                    arms += [kind, colour]
                paint["fill-color"] = ["match", ["get", "kind"]] + arms + [LANDCOVER_DEFAULT]
            elif lid == "landuse_park":
                expr = ["case"]
                for kinds, colour in PARK_CASES:
                    expr += [["in", ["get", "kind"], ["literal", kinds]], colour]
                expr.append(PARK_DEFAULT)
                paint["fill-color"] = expr
            elif lid in LANDUSE_FILL:
                paint["fill-color"] = LANDUSE_FILL[lid]
            else:
                paint["fill-color"] = LU_MID
            if "fill-outline-color" in paint:
                paint["fill-outline-color"] = paint["fill-color"]

        elif ltype == "line":
            if slayer == "water":
                paint["line-color"] = WATER
            elif slayer == "boundaries":
                paint["line-color"] = BOUNDARY
            elif slayer == "roads":
                cls = road_class(lid)
                if cls == "casing":
                    paint["line-color"] = CASING
                elif cls == "path":
                    paint["line-color"] = PATH
                    paint["line-dasharray"] = list(PATH_DASH)   # (d) keep footways dashed
                elif cls == "major":
                    paint["line-color"] = ROAD_MAJOR
                else:
                    paint["line-color"] = ROAD_MINOR
            else:
                paint["line-color"] = ROAD_MINOR

        elif ltype == "symbol":
            paint["text-color"] = LABEL_PLACE if is_place_label(lid) else LABEL
            paint["text-halo-color"] = HALO
            paint["text-halo-width"] = HALO_WIDTH

        # (f) pin every font to a bundled stack
        layout = layer.get("layout")
        if isinstance(layout, dict) and "text-font" in layout:
            layout["text-font"] = fix_font_value(layout["text-font"])

        layers.append(layer)

    # sports pitches: no stock layer paints them, so add one above the other landuse
    # fills (the campus ground is landuse=university and would otherwise cover them)
    # and below water/roads.
    pitch_layer = {
        "id": "landuse_pitch",
        "type": "fill",
        "source": "protomaps",
        "source-layer": "landuse",
        "filter": ["in", "kind"] + PITCH_KINDS,
        "paint": {"fill-color": PITCH, "fill-outline-color": PITCH_EDGE},
    }
    insert_at = next((i for i, l in enumerate(layers) if l["id"] == "water"), None)
    if insert_at is None:
        insert_at = next((i + 1 for i, l in enumerate(layers)
                          if l["id"] == "landuse_aerodrome"), len(layers))
    layers.insert(insert_at, pitch_layer)

    style["layers"] = layers
    return style


def build_meta(style: dict, build_date: str) -> dict:
    layers = style["layers"]
    road_ids = [l["id"] for l in layers
                if l.get("source-layer") == "roads" and l["type"] == "line"]
    label_ids = [l["id"] for l in layers if l["type"] == "symbol"]
    landuse_ids = [l["id"] for l in layers
                   if l["type"] == "fill" and l.get("source-layer") in ("landuse", "landcover")]
    water_ids = [l["id"] for l in layers
                 if l.get("source-layer") == "water" and l["type"] in ("fill", "line")]
    first_symbol = label_ids[0] if label_ids else None
    return {
        "road_layer_ids": road_ids,
        "label_layer_ids": label_ids,
        "landuse_layer_ids": landuse_ids,
        "water_layer_ids": water_ids,
        "first_symbol_layer_id": first_symbol,
        "bbox": BBOX,
        "protomaps_build": build_date,
        "attribution": style["sources"]["protomaps"].get("attribution", ""),
    }


# --------------------------------------------------------------------------
# colour audit
# --------------------------------------------------------------------------
COLOR_RE = re.compile(r"^(#[0-9A-Fa-f]{3,8}|rgba?\()")


def collect_colors(node, key: str = "", out: set | None = None) -> set:
    if out is None:
        out = set()
    if isinstance(node, dict):
        for k, v in node.items():
            collect_colors(v, k, out)
    elif isinstance(node, list):
        for v in node:
            collect_colors(v, key, out)
    elif isinstance(node, str):
        if "color" in key.lower() and COLOR_RE.match(node):
            out.add(node)
    return out


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
def do_build(args) -> int:
    os.makedirs(MAP_DIR, exist_ok=True)

    log("== Protomaps v4 dark style")
    original = None
    if not args.offline:
        key = resolve_key()
        url = STYLE_URL.format(key=key)
        try:
            raw = http_get(url, timeout=60)
            original = json.loads(raw)
            with open(ORIGINAL_PATH, "wb") as fh:
                fh.write(raw)
            log(f"  fetched {len(raw)} B -> {os.path.relpath(ORIGINAL_PATH, REPO_ROOT)}")
        except Exception as exc:
            log(f"  fetch failed ({exc}); falling back to the saved original")
    if original is None:
        if not os.path.exists(ORIGINAL_PATH):
            log("ERROR: no network and no saved protomaps_dark_original.json")
            return 1
        with open(ORIGINAL_PATH) as fh:
            original = json.load(fh)
        log(f"  reusing {os.path.relpath(ORIGINAL_PATH, REPO_ROOT)}")

    log(f"  name: {original.get('name')}   layers: {len(original['layers'])}")

    build_date = resolve_build(args.build)
    style = build_style(original)
    meta = build_meta(style, build_date)

    with open(STYLE_PATH, "w", encoding="utf-8") as fh:
        json.dump(style, fh, separators=(",", ":"), ensure_ascii=False)
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, separators=(",", ":"), ensure_ascii=False)

    log(f"  wrote {os.path.relpath(STYLE_PATH, REPO_ROOT)} "
        f"({os.path.getsize(STYLE_PATH)} B, {len(style['layers'])} layers)")
    log(f"  wrote {os.path.relpath(META_PATH, REPO_ROOT)} "
        f"({os.path.getsize(META_PATH)} B)")
    if build_date != "unknown" and re.fullmatch(r"\d{8}", build_date):
        with open(BUILD_STAMP, "w") as fh:
            fh.write(build_date + "\n")
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------
def do_check() -> int:
    rc = 0
    log("")
    log("== CHECK — style.json")
    if not os.path.exists(STYLE_PATH):
        log("  FAIL: style.json missing")
        return 1
    try:
        with open(STYLE_PATH, encoding="utf-8") as fh:
            style = json.load(fh)
    except Exception as exc:
        log(f"  FAIL: style.json does not parse: {exc}")
        return 1

    log(f"  file      : {os.path.relpath(STYLE_PATH, REPO_ROOT)}  "
        f"({os.path.getsize(STYLE_PATH)} B)")
    log(f"  parses    : PASS   version {style.get('version')}   "
        f"name {style.get('name')!r}")

    layers = style["layers"]
    kinds = {}
    for l in layers:
        kinds[l["type"]] = kinds.get(l["type"], 0) + 1
    log(f"  layers    : {len(layers)}  ("
        + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())) + ")")

    src = style.get("sources", {}).get("protomaps", {})
    if src.get("url") == PMTILES_URL:
        log(f"  source    : PASS  {src['url']}")
    else:
        log(f"  FAIL      : source url is {src.get('url')!r}, expected {PMTILES_URL!r}")
        rc = 1
    log(f"  attribution: {src.get('attribution')!r}")

    for label, got, want in (("glyphs", style.get("glyphs"), GLYPHS_URL),
                             ("sprite", style.get("sprite"), SPRITE_URL)):
        if got == want:
            log(f"  {label:<10}: PASS  {got}")
        else:
            log(f"  FAIL      : {label} is {got!r}, expected {want!r}")
            rc = 1

    if style.get("metadata", {}).get("idr_tokens") == "v1":
        log("  metadata  : PASS  idr_tokens=v1")
    else:
        log(f"  FAIL      : metadata is {style.get('metadata')!r}")
        rc = 1

    if any(l["id"] == "buildings" for l in layers):
        log("  FAIL      : flat `buildings` fill layer is still present")
        rc = 1
    else:
        log("  buildings : PASS  flat fill layer removed")

    # font stacks
    stacks: set = set()
    for l in layers:
        tf = l.get("layout", {}).get("text-font")
        if tf is not None:
            collect_font_stacks(tf, stacks)
    log(f"  text-font stacks in use ({len(stacks)}):")
    for st in sorted(stacks):
        log(f"      {list(st)}")
    bad = sorted({f for st in stacks for f in st if f not in BUNDLED_FONTS})
    if bad:
        log(f"  FAIL      : fonts outside the 3 bundled stacks: {bad}")
        rc = 1
    else:
        log("  fonts     : PASS  only the 3 bundled Noto stacks are referenced")

    # every referenced stack must have both glyph ranges on disk
    log("  glyph directories referenced by the style:")
    for font in sorted({f for st in stacks for f in st}):
        d = os.path.join(GLYPH_DIR, font)
        present = []
        for rng in GLYPH_RANGES:
            p = os.path.join(d, f"{rng}.pbf")
            if os.path.exists(p) and os.path.getsize(p) > 10240:
                present.append(f"{rng}.pbf {os.path.getsize(p)} B")
            else:
                present.append(f"{rng}.pbf MISSING")
                rc = 1
        log(f"      {'OK ' if 'MISSING' not in ' '.join(present) else 'FAIL'} "
            f"glyphs/{font}/  ->  {', '.join(present)}")

    # colour audit
    colors = collect_colors(style)
    stray = sorted(c for c in colors if c not in ALLOWED_COLORS)
    log(f"  colours   : {len(colors)} distinct, all from the token palette"
        if not stray else f"  FAIL      : off-token colours present: {stray}")
    if stray:
        rc = 1

    # sprites / fonts, for completeness when run standalone
    log("")
    log("== CHECK — sprites / res-font (as referenced by the style)")
    for s in SPRITE_FILES:
        p = os.path.join(SPRITE_DIR, s)
        if os.path.exists(p):
            log(f"  ok   {os.path.getsize(p):>8} B  sprites/{s}")
        else:
            log(f"  FAIL missing sprites/{s}")
            rc = 1
    for t in TTF_FILES:
        p = os.path.join(FONT_DIR, t)
        if os.path.exists(p):
            log(f"  ok   {os.path.getsize(p):>8} B  res/font/{t}")
        else:
            log(f"  FAIL missing res/font/{t}")
            rc = 1

    log("")
    log("== CHECK — style_meta.json")
    if not os.path.exists(META_PATH):
        log("  FAIL: style_meta.json missing")
        return 1
    with open(META_PATH, encoding="utf-8") as fh:
        meta = json.load(fh)
    ids = {l["id"] for l in layers}
    for key in ("road_layer_ids", "label_layer_ids", "landuse_layer_ids", "water_layer_ids"):
        vals = meta.get(key, [])
        missing = [v for v in vals if v not in ids]
        log(f"  {key:<18}: {len(vals):>2}  {'PASS' if not missing else 'FAIL ' + str(missing)}")
        if missing:
            rc = 1
    fs = meta.get("first_symbol_layer_id")
    first_actual = next((l["id"] for l in layers if l["type"] == "symbol"), None)
    log(f"  first_symbol      : {fs!r} "
        f"{'PASS' if fs == first_actual else 'FAIL expected ' + repr(first_actual)}")
    if fs != first_actual:
        rc = 1
    log(f"  bbox              : {meta.get('bbox')} "
        f"{'PASS' if meta.get('bbox') == BBOX else 'FAIL'}")
    if meta.get("bbox") != BBOX:
        rc = 1
    log(f"  protomaps_build   : {meta.get('protomaps_build')}")
    log(f"  attribution       : {meta.get('attribution')!r}")

    log("")
    log(f"== STYLE CHECK: {'PASS' if rc == 0 else 'FAILURES ABOVE'}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the built artefacts only")
    ap.add_argument("--offline", action="store_true",
                    help="rebuild from the saved original, do not hit the network")
    ap.add_argument("--build", metavar="YYYYMMDD",
                    help="Protomaps build date to record in style_meta.json")
    args = ap.parse_args()
    if args.check:
        return do_check()
    rc = do_build(args)
    return rc or do_check()


if __name__ == "__main__":
    sys.exit(main())
