#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# extract_pmtiles.sh — package the offline basemap for IDRNav (MapLibre Android)
#
#   1. locate (or install) the `pmtiles` CLI
#   2. find the newest available Protomaps daily planet build
#   3. cut the SNU campus bbox out of it into assets/map/snu.pmtiles
#   4. download the offline glyphs (PBF) + sprites + Barlow TTFs
#   5. verify everything and print a summary
#
# Idempotent: every artefact that already exists and passes its validator is
# left alone.  Re-run with --force to re-download everything.
#
# Usage:
#   tools/extract_pmtiles.sh            # do the work, then check
#   tools/extract_pmtiles.sh --force    # ignore existing artefacts
#   tools/extract_pmtiles.sh --check    # only run the verification pass
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ASSETS="$REPO_ROOT/IDRNav/app/src/main/assets"
MAP_DIR="$ASSETS/map"
GLYPH_DIR="$ASSETS/glyphs"
SPRITE_DIR="$ASSETS/sprites"
FONT_DIR="$REPO_ROOT/IDRNav/app/src/main/res/font"
PMTILES_OUT="$MAP_DIR/snu.pmtiles"

# --- constants (from docs/research/R6_map_stack_android.md §4.1, §5) ---------
BBOX="77.5639,28.5133,77.5823,28.5335"     # W,S,E,N — SNU campus
MAXZOOM=15                                  # Protomaps planet ceiling
START_DATE=20260905                         # probe backwards from here
LOOKBACK_DAYS=30
BUILD_BASE="https://build.protomaps.com"
ASSETS_BASE="https://protomaps.github.io/basemaps-assets"
GFONTS_RAW="https://github.com/google/fonts/raw/main"
GO_PMTILES_VER="1.31.2"
GO_PMTILES_URL="https://github.com/protomaps/go-pmtiles/releases/download/v${GO_PMTILES_VER}/go-pmtiles-${GO_PMTILES_VER}_Darwin_arm64.zip"

PMTILES_MIN_BYTES=400000      # accept 0.4 MB .. 3 MB (expect ~0.85 MB)
PMTILES_MAX_BYTES=3000000
PBF_MIN_BYTES=10240           # each glyph range must be > 10 KB

CACHE="${PMTILES_CACHE_DIR:-${TMPDIR:-/tmp}/idr_map_tools}"
BREW_LOG="${BREW_PMTILES_LOG:-}"

FORCE=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

log()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

fsize() { [ -f "$1" ] && wc -c < "$1" | tr -d ' ' || echo 0; }
magic() { od -An -tx1 -N"${2:-4}" "$1" 2>/dev/null | tr -d ' \n'; }

# --- validators -------------------------------------------------------------
# validators all take the file path as their LAST argument (see fetch)
is_min_size() { [ "$(fsize "$2")" -ge "$1" ]; }
is_ttf() {
  local m; m="$(magic "$1" 4)"
  [ "$m" = "00010000" ] || [ "$m" = "74727565" ]   # sfnt 1.0  |  'true'
}
is_png() { [ "$(magic "$1" 4)" = "89504e47" ]; }
is_json() { "$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$1" >/dev/null 2>&1; }

# fetch <url> <dest> <validator...>   — idempotent, atomic
fetch() {
  local url="$1" dest="$2"; shift 2
  if [ "$FORCE" -eq 0 ] && [ -f "$dest" ] && "$@" "$dest"; then
    log "  ok (cached)  $(printf '%8s' "$(fsize "$dest")") B  ${dest#$REPO_ROOT/}"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  local tmp="$dest.part"
  curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 600 -o "$tmp" "$url" \
    || { rm -f "$tmp"; die "download failed: $url"; }
  "$@" "$tmp" || { rm -f "$tmp"; die "validation failed for $url -> $dest"; }
  mv -f "$tmp" "$dest"
  log "  downloaded   $(printf '%8s' "$(fsize "$dest")") B  ${dest#$REPO_ROOT/}"
}

urlenc() { "$PY" -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1"; }

date_minus() {  # <YYYYMMDD> <days>
  "$PY" -c 'import sys,datetime as d;print((d.datetime.strptime(sys.argv[1],"%Y%m%d")-d.timedelta(days=int(sys.argv[2]))).strftime("%Y%m%d"))' "$1" "$2"
}

# --- 1. locate the pmtiles binary ------------------------------------------
find_pmtiles() {
  local p
  if p="$(command -v pmtiles 2>/dev/null)"; then echo "$p"; return 0; fi
  [ -x /opt/homebrew/bin/pmtiles ] && { echo /opt/homebrew/bin/pmtiles; return 0; }
  [ -x "$CACHE/pmtiles" ]          && { echo "$CACHE/pmtiles"; return 0; }
  return 1
}

wait_for_brew() {
  [ -n "$BREW_LOG" ] && [ -f "$BREW_LOG" ] || return 1
  log "  waiting on background brew job ($BREW_LOG, max 300 s)..."
  local i=0
  while [ "$i" -lt 300 ]; do
    tail -n 1 "$BREW_LOG" 2>/dev/null | grep -q '^exit ' && return 0
    sleep 5; i=$((i + 5))
  done
  return 1
}

install_go_pmtiles() {
  log "  falling back to the go-pmtiles v${GO_PMTILES_VER} release zip"
  mkdir -p "$CACHE"
  curl -fsSL --retry 3 --connect-timeout 20 --max-time 600 -o "$CACHE/go-pmtiles.zip" "$GO_PMTILES_URL" \
    || die "could not download $GO_PMTILES_URL (and no pmtiles on PATH)"
  ( cd "$CACHE" && unzip -o -q go-pmtiles.zip ) || die "unzip of go-pmtiles failed"
  chmod +x "$CACHE/pmtiles"
  [ -x "$CACHE/pmtiles" ] || die "go-pmtiles zip did not contain a pmtiles binary"
}

resolve_pmtiles() {
  if PMTILES="$(find_pmtiles)"; then :; else
    wait_for_brew || true
    PMTILES="$(find_pmtiles || true)"
  fi
  if [ -z "${PMTILES:-}" ]; then
    install_go_pmtiles
    PMTILES="$CACHE/pmtiles"
  fi
  log "  pmtiles: $PMTILES  ($("$PMTILES" version 2>/dev/null | head -n1))"
}

# --- 2. newest available daily build ---------------------------------------
find_build() {
  local i=0 d code
  while [ "$i" -le "$LOOKBACK_DAYS" ]; do
    d="$(date_minus "$START_DATE" "$i")"
    code="$(curl -s -o /dev/null -w '%{http_code}' -I --connect-timeout 15 --max-time 60 "$BUILD_BASE/$d.pmtiles" || echo 000)"
    log "  HEAD $BUILD_BASE/$d.pmtiles -> $code" >&2
    [ "$code" = "200" ] && { echo "$d"; return 0; }
    i=$((i + 1))
  done
  return 1
}

# --- 3. extract -------------------------------------------------------------
do_extract() {
  mkdir -p "$MAP_DIR"
  if [ "$FORCE" -eq 0 ] && [ -f "$PMTILES_OUT" ] \
     && "$PMTILES" verify "$PMTILES_OUT" >/dev/null 2>&1 \
     && is_min_size "$PMTILES_MIN_BYTES" "$PMTILES_OUT"; then
    log "  ok (cached)  $(fsize "$PMTILES_OUT") B  ${PMTILES_OUT#$REPO_ROOT/}"
    BUILD_DATE="$(build_date_from_file || true)"
    [ -n "${BUILD_DATE:-}" ] || BUILD_DATE="$(find_build)" || die "no Protomaps build found"
    return 0
  fi
  BUILD_DATE="$(find_build)" || die "no Protomaps daily build returned 200 in the last $LOOKBACK_DAYS days"
  log "  using build $BUILD_DATE"
  rm -f "$PMTILES_OUT"
  "$PMTILES" extract "$BUILD_BASE/$BUILD_DATE.pmtiles" "$PMTILES_OUT" \
    --bbox="$BBOX" --maxzoom="$MAXZOOM" --download-threads=8
  printf '%s\n' "$BUILD_DATE" > "$MAP_DIR/.protomaps_build"
}

build_date_from_file() {
  [ -f "$MAP_DIR/.protomaps_build" ] && tr -d '[:space:]' < "$MAP_DIR/.protomaps_build"
}

# --- 4. glyphs, sprites, fonts ---------------------------------------------
FONT_STACKS=("Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic")
RANGES=(0-255 256-511)
SPRITES=(dark.json dark.png "dark@2x.json" "dark@2x.png")

do_glyphs() {
  local f r enc
  for f in "${FONT_STACKS[@]}"; do
    enc="$(urlenc "$f")"
    for r in "${RANGES[@]}"; do
      fetch "$ASSETS_BASE/fonts/$enc/$r.pbf" "$GLYPH_DIR/$f/$r.pbf" is_min_size "$PBF_MIN_BYTES"
    done
  done
}

do_sprites() {
  local s
  for s in "${SPRITES[@]}"; do
    case "$s" in
      *.png) fetch "$ASSETS_BASE/sprites/v4/$s" "$SPRITE_DIR/$s" is_png ;;
      *)     fetch "$ASSETS_BASE/sprites/v4/$s" "$SPRITE_DIR/$s" is_json ;;
    esac
  done
}

# Android resource names must match [a-z0-9_]+
do_fonts() {
  fetch "$GFONTS_RAW/ofl/barlow/Barlow-Regular.ttf"                       "$FONT_DIR/barlow_regular.ttf"               is_ttf
  fetch "$GFONTS_RAW/ofl/barlow/Barlow-Medium.ttf"                        "$FONT_DIR/barlow_medium.ttf"                is_ttf
  fetch "$GFONTS_RAW/ofl/barlowsemicondensed/BarlowSemiCondensed-SemiBold.ttf" "$FONT_DIR/barlow_semicondensed_semibold.ttf" is_ttf
}

# --- 5. verification --------------------------------------------------------
do_check() {
  local rc=0
  step "CHECK — pmtiles"
  if [ -f "$PMTILES_OUT" ]; then
    log "  file      : ${PMTILES_OUT#$REPO_ROOT/}"
    log "  size      : $(fsize "$PMTILES_OUT") B ($("$PY" -c "print(f'{$(fsize "$PMTILES_OUT")/1048576:.3f}')") MiB)"
    if [ "$(fsize "$PMTILES_OUT")" -lt "$PMTILES_MIN_BYTES" ] || [ "$(fsize "$PMTILES_OUT")" -gt "$PMTILES_MAX_BYTES" ]; then
      log "  FAIL      : size outside the accepted 0.4-3 MB window"; rc=1
    fi
    if "$PMTILES" verify "$PMTILES_OUT" >/dev/null 2>&1; then log "  verify    : PASS"; else log "  verify    : FAIL"; rc=1; fi
    "$PMTILES" show "$PMTILES_OUT" --header-json > "$CACHE/header.json" 2>/dev/null || true
    "$PMTILES" show "$PMTILES_OUT" > "$CACHE/show.txt" 2>/dev/null || true
    if [ -s "$CACHE/header.json" ]; then
      "$PY" - "$CACHE/header.json" "$BBOX" <<'HDR_PY' || rc=1
import json, sys
h = json.load(open(sys.argv[1]))
w, s, e, n = [float(x) for x in sys.argv[2].split(",")]
g = lambda *k: next((h[x] for x in k if x in h), None)
mnz, mxz = g("minzoom", "min_zoom"), g("maxzoom", "max_zoom")
b = g("bounds")
if b is None:                      # some builds emit E7 integers instead
    b = [g("min_lon_e7") / 1e7, g("min_lat_e7") / 1e7,
         g("max_lon_e7") / 1e7, g("max_lat_e7") / 1e7]
bw, bs, be, bn = [float(x) for x in b]
c = g("center") or []
print(f"  zoom      : min {mnz}  max {mxz}")
print(f"  tile type : {g('tile_type')}   tile compression: {g('tile_compression')}")
print(f"  bounds    : {bw:.4f},{bs:.4f},{be:.4f},{bn:.4f}")
if c:
    print(f"  center    : {float(c[0]):.4f},{float(c[1]):.4f}  z{c[2] if len(c) > 2 else '?'}")
ok = True
if mxz != 15:
    print(f"  FAIL      : maxzoom is {mxz}, expected 15"); ok = False
if not (bw <= w + 1e-6 and bs <= s + 1e-6 and be >= e - 1e-6 and bn >= n - 1e-6):
    print(f"  FAIL      : header bounds do not cover the bbox {w},{s},{e},{n}"); ok = False
else:
    print("  bbox cover: PASS")
sys.exit(0 if ok else 1)
HDR_PY
    else
      log "  FAIL      : pmtiles show --header-json produced nothing"; rc=1
    fi
    if [ -s "$CACHE/show.txt" ]; then
      grep -E '^(pmtiles spec version|addressed tiles count|tile entries count|tile contents count|clustered|internal compression):' "$CACHE/show.txt" | sed 's/^/  /'
      grep -E '^(version|attribution) ' "$CACHE/show.txt" | sed 's/^/  meta /'
    fi
    log "  build     : $(build_date_from_file || echo unknown)"
  else
    log "  FAIL      : $PMTILES_OUT missing"; rc=1
  fi

  step "CHECK — glyphs"
  local f r p n=0
  for f in "${FONT_STACKS[@]}"; do
    for r in "${RANGES[@]}"; do
      p="$GLYPH_DIR/$f/$r.pbf"
      if [ -f "$p" ] && is_min_size "$PBF_MIN_BYTES" "$p"; then
        log "  ok  $(printf '%8s' "$(fsize "$p")") B  glyphs/$f/$r.pbf"; n=$((n+1))
      else
        log "  FAIL  missing or < 10 KB: glyphs/$f/$r.pbf"; rc=1
      fi
    done
  done
  log "  $n/6 glyph ranges present"

  step "CHECK — sprites"
  local s ok
  for s in "${SPRITES[@]}"; do
    p="$SPRITE_DIR/$s"; ok=0
    if [ -f "$p" ]; then case "$s" in *.png) is_png "$p" && ok=1 ;; *) is_json "$p" && ok=1 ;; esac; fi
    if [ "$ok" -eq 1 ]; then log "  ok  $(printf '%8s' "$(fsize "$p")") B  sprites/$s"
    else log "  FAIL  missing or wrong type: sprites/$s"; rc=1; fi
  done

  step "CHECK — Barlow fonts (res/font)"
  for p in barlow_regular.ttf barlow_medium.ttf barlow_semicondensed_semibold.ttf; do
    if [ -f "$FONT_DIR/$p" ] && is_ttf "$FONT_DIR/$p"; then
      log "  ok  $(printf '%8s' "$(fsize "$FONT_DIR/$p")") B  res/font/$p  (sfnt magic $(magic "$FONT_DIR/$p" 4))"
    else log "  FAIL  missing or not a TTF: res/font/$p"; rc=1; fi
    case "$p" in *[!a-z0-9_.]*) log "  FAIL  illegal Android resource name: $p"; rc=1 ;; esac
  done

  if [ -f "$SCRIPT_DIR/make_style.py" ]; then
    "$PY" "$SCRIPT_DIR/make_style.py" --check || rc=1
  else
    step "CHECK — style"; log "  SKIP: tools/make_style.py not present yet"
  fi

  printf '\n== RESULT: %s\n' "$([ "$rc" -eq 0 ] && echo 'ALL CHECKS PASSED' || echo 'FAILURES ABOVE')"
  return "$rc"
}

# --- main -------------------------------------------------------------------
mkdir -p "$CACHE" "$MAP_DIR" "$GLYPH_DIR" "$SPRITE_DIR" "$FONT_DIR"

step "pmtiles binary"
resolve_pmtiles

if [ "$CHECK_ONLY" -eq 0 ]; then
  step "Protomaps extract  bbox=$BBOX  maxzoom=$MAXZOOM"
  do_extract
  log "  size: $(fsize "$PMTILES_OUT") B"
  "$PMTILES" verify "$PMTILES_OUT"
  "$PMTILES" show "$PMTILES_OUT" --header-json

  step "glyphs -> assets/glyphs/<stack>/<range>.pbf"
  do_glyphs
  step "sprites -> assets/sprites/"
  do_sprites
  step "Barlow TTFs -> res/font/"
  do_fonts
fi

do_check
