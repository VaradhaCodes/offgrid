# R7 — Map data for an offline map of Shiv Nadar University, Greater Noida

Workstream R7. All fetches performed **2026-09-05** (UTC times given per item) from
`/Users/lokkeshayyappan/HACKATHON` on macOS 25.2 (Darwin), Python 3.12.4 in
`/Users/lokkeshayyappan/HACKATHON/.venv`.

**Area of interest**: bbox `28.5133, 77.5639, 28.5335, 77.5823` (S, W, N, E).
Centre `28.524416, 77.573818`. Physical extent **1 800 m E–W × 2 249 m N–S = 4.05 km²**
(measured, not quoted).

**Verification rule used throughout**: every number below came from a file this review
downloaded or a page this review fetched. Items marked **UNVERIFIED** could not be
fetched and must not be quoted in the judged document.

---

## 0. Files produced

All under `/Users/lokkeshayyappan/HACKATHON/data/map/`.

| File | Bytes | gzip | Contents |
|---|---:|---:|---|
| `snu_osm_full.geojson` | 857 739 | 236 972 | Full OSM extract of the bbox, 513 features, MapLibre-ready |
| `snu_buildings_open.geojson` | 333 968 | 75 240 | Google Open Buildings v3, 700 footprints in bbox |
| `snu_buildings_ms.geojson` | 159 667 | 37 487 | Microsoft Global ML Building Footprints, 302 footprints in bbox |
| `snu_campus_boundary.geojson` | 4 458 | 1 674 | Campus polygon, 115.7 ha, extracted from OSM way/369248213 |
| `snu_overpass_query.txt` | 171 | — | The exact Overpass QL used |
| `osm2geojson.py` | 8 282 | — | Overpass JSON → GeoJSON converter (stdlib only, no GDAL) |
| `s2cell.py` | 2 039 | — | Pure-Python S2 cell id / token, used to find the Open Buildings shard |
| `tile_samples/` | ~1.3 MB | — | 7 Esri test tiles, 4 Sentinel-2 cloudless tiles, 1 OSM Carto tile, 3 rendered check images |

Total `data/map/` after this workstream: **2.8 MB**. Everything except the check
images is small enough to ship inside the APK assets.

Pre-existing files left untouched: `snu_osm_highways_900m.json`,
`corridor_route1.geojson`, `corridor_route2.geojson`, `corridor_AJB.geojson`.

---

## 1. Full OSM extract

### 1.1 The query

Fetched **2026-09-05 06:51:21 UTC** by HTTP POST to `https://overpass-api.de/api/interpreter`.
Response: HTTP 200, 2 153 696 bytes, 10.1 s wall.

```
[out:json][timeout:180];
(
  node(28.5133,77.5639,28.5335,77.5823);
  way(28.5133,77.5639,28.5335,77.5823);
  relation(28.5133,77.5639,28.5335,77.5823);
);
out body geom;
```

Deliberately **untyped** — pulling every element in the bbox rather than a tag filter
list is 2.1 MB and one round trip, and it removes the risk of a later "we forgot to ask
for `barrier`" bug. Everything the brief listed (buildings, `building:levels`, `height`,
names, amenity, leisure, natural, landuse, water, all highway classes including
`footway`/`path`/`steps`, barrier, parking, sport, campus boundary) is therefore
guaranteed present.

Server metadata returned in the response:
- generator `Overpass API 0.7.62.11 87bfad18`
- `timestamp_osm_base` **2026-09-05T06:50:40Z** — the extract is 41 seconds stale
- copyright: data from www.openstreetmap.org, made available under **ODbL**

Reproduce with:
```bash
curl -s -X POST https://overpass-api.de/api/interpreter \
  --data-urlencode "data=$(cat data/map/snu_overpass_query.txt)" -o raw.json
.venv/bin/python data/map/osm2geojson.py raw.json data/map/snu_osm_full.geojson
```

### 1.2 Raw counts

3 786 elements: **3 330 nodes, 451 ways, 5 relations**. Of those, **514 carry tags**;
the other 3 272 are geometry-only vertices.

`out body geom` returns full member/vertex geometry inline, so the converter needs no
node dereferencing and no external dependency. **Note the extract is not clipped to the
bbox** — Overpass returns whole ways that *intersect* the bbox, so some farmland and
highway ways run well outside it. This is what you want for rendering (no cut edges),
but it means area sums by class exceed the 4.05 km² bbox.

### 1.3 Converted GeoJSON: 513 features

One tagged element is dropped: `relation/10398538` ("Football Gound", `type=site`,
one node member, no geometry). Everything else converts.

Geometry mix: **58 Point, 321 LineString, 130 Polygon, 4 MultiLineString**.

Every feature gets a coarse `@class` property so the style can filter with one cheap
comparison instead of a tag expression tree:

| `@class` | count | note |
|---|---:|---|
| `path` | 188 | footway / path / pedestrian / track |
| `road` | 127 | service / residential / tertiary / trunk / secondary |
| `building` | 58 | |
| `landuse` | 39 | |
| `crossing_node` | 29 | `highway=crossing` nodes |
| `other` | 13 | |
| `sport` | 13 | pitches, sports centre, golf course, athletics track |
| `manmade` | 12 | masts, power towers, water works |
| `water` | 8 | |
| `green` | 8 | parks, scrub, tree rows, forest |
| `poi` | 8 | bank, ATM, shops, theatre, clinic, pharmacy |
| `barrier` | 5 | 4 gates + 1 fence |
| `parking` | 3 | |
| `tree` | 1 | |
| `campus` | 1 | the campus polygon |

### 1.4 Highway network — 54.00 km inside the bbox

| `highway=` | ways | length |
|---|---:|---:|
| `service` | 94 | 16.04 km |
| `footway` | 175 | 13.67 km |
| `tertiary` | 4 | 8.22 km |
| `trunk` | 6 | 4.80 km |
| `residential` | 15 | 3.78 km |
| `track` | 5 | 3.36 km |
| `trunk_link` | 4 | 2.34 km |
| `secondary` | 3 | 1.00 km |
| `path` | 6 | 0.30 km |
| `secondary_link` | 1 | 0.26 km |
| `pedestrian` | 2 | 0.23 km |
| `crossing` (nodes) | 29 | — |

`footway` subtypes: 130 plain, **25 `footway=sidewalk`**, 20 `footway=crossing`.
No `highway=steps` anywhere in the bbox.
All 43 tagged crossings are `crossing=unmarked`.

### 1.5 Buildings

**58 buildings**, total footprint area **94 731 m²** (shoelace on a local equirectangular
projection at lat 28.5244).

- `building=dormitory` 23, `building=yes` 20, `building=university` 13, `building=greenhouse` 2
- **26 have a `name`** (45 %)
- **15 have `building:levels`**, **1 has `height`** (Central Library, `height=12`, `building:levels=3`)
- After the height rule (§5.3): 14 extruded from levels, 1 from `height`, **43 from a
  type default** — i.e. **74 % of buildings have no real height information**

The named ones, with levels where tagged:

| Name | building= | levels | amenity |
|---|---|---:|---|
| Block A, Block B, Block C, Block D | university | 4 each | — |
| Central Library | yes | 3 (`height=12`) | library |
| Management Block | university | — | — |
| Research Annexe | university | — | — |
| Hostel 1A / 1B / 1C / 2A / 2B / 2C / 3A / 3B / 3C | dormitory | 6 each | student_accommodation |
| Dining Hall 1 / 2 / 3 (3 appears twice, two ways) | yes | — | food_court |
| Indoor Sports Complex | yes | — | leisure=sports_centre |
| Health and wellness centre, SNU | yes | — | clinic |
| Pharmacy | yes | — | pharmacy |
| Auctus Supermarket | yes | — | shop=convenience |
| Shiv Nadar University Post Office | yes | — | post_office |
| Entrance Security Office | yes | — | office=security |

The nine hostels at 6 levels and the four academic blocks at 4 levels are the backbone
of the 3D view — 13 of the 15 levels tags are on exactly the buildings a viewer will
look at first.

### 1.6 Sport, water, green, landuse

`leisure`: 11 `pitch`, 2 `park`, 1 `sports_centre`, 1 `golf_course`, 1 `track`.
`sport` values: basketball ×2, soccer ×2, volleyball, tennis, squash, badminton, chess,
cricket, running, equestrian, and `basketball;badminton;running;Gym` on the Indoor
Sports Complex.

Named sports and green features:
Football Ground, Cricket Ground, Basketball Court, Basketball Courts, Volleyball Court,
Tennis Courts, Squash Courts, Badminton Courts, Chess Garden, Golf Course, Ground
(`landuse=recreation_ground`), Shivaji park, SNU Biodiversity Park, Amphitheatre,
**Lake SNU** (`natural=water` + `water=pond`).

`natural`: 7 `water`, 3 `scrub`, 3 `tree_row`, 1 `tree` (named "The Lonely Tree").
`water`: 5 `pond`, 2 `waterlogging`. One `waterway=ditch`.
`landuse`: **26 `grass`**, 5 `construction` (two named "Hostels (under construction)"),
3 `farmland`, 2 `industrial`, 1 `residential` ("Faculty Residence"), 1 `forest`,
1 `recreation_ground`.

Area by class (whole ways, unclipped): landuse 5.62 km², campus polygon 1.16 km²,
green 97 874 m², buildings 94 731 m², sport 59 021 m², water 26 522 m², parking 10 168 m².

### 1.7 Campus boundary

`way/369248213` — tagged `amenity=university` **plus** `barrier=fence`, name
"Shiv Nadar University", alt_name "Shiv Nadar Institution of Eminence",
`wikidata=Q7499204`, `wikipedia=en:Shiv Nadar University`, operator, phone, website,
`addr:postcode=201314`.

136 vertices, closed. Measured area **115.7 ha**. Bounding box
`77.567953, 28.517809 → 77.581553, 28.533803`, i.e. the campus occupies about 29 % of
the requested bbox and sits in its middle-right.

**Trap fixed**: a naive OSM-to-GeoJSON rule treats any way with `barrier=*` as a line,
which turns this into an unfillable LineString. `osm2geojson.py` handles it explicitly —
a linear key (`highway`/`barrier`/`waterway`/`power`/`railway`) only forces a line if the
way carries no strong area key (`building`, `landuse`, `leisure`, `natural`, `amenity`,
`water`, `place`, …). Verified: 12 closed ways in this bbox; the campus fence and
`power=generator` correctly become polygons, the 10 closed service/footway loops
correctly stay lines.

### 1.8 Named POIs available for labels

Nodes: HDFC Bank (`amenity=bank`), PNB ATM, Mini Mart (`shop=convenience`),
Belleza (`shop=hairdresser`), Stage (`amenity=theatre`), The Lonely Tree
(`natural=tree`), **SNU Gate No. 1**, **SNU Gate No. 2** (`barrier=gate`).
Areas: Parking 1 (`amenity=parking`), Amphitheatre, Power Generator,
R.P. Foam Home Pvt. Ltd. (`landuse=industrial`, outside campus).
Plus 2 `amenity=parking_entrance` nodes and 8 `entrance=yes` nodes.

Relations: National Highway 91 (`relation/1289198`, 675 members),
NH 34 (`relation/5837160`), NH 334C (`relation/5932570`), an unnamed
`type=canal` relation (`relation/11645417`). These are route relations spanning far
beyond the bbox; the converter emits them as MultiLineStrings, but **do not render them** —
their member ways are already in the extract individually. Filter them out with
`["!=", ["get", "type"], "route"]`.

### 1.9 Completeness assessment vs satellite

Method: stitched a 4×5 block of Esri z16 tiles (`x 46888–46891, y 27344–27348`) into a
1024×1280 mosaic and rendered three check images, saved under `data/map/tile_samples/`:

- `campus_z16_mosaic.jpg` — plain imagery
- `campus_z16_osm_overlay.jpg` — OSM buildings in red, campus boundary yellow, sport
  pitches cyan, water blue, roads white
- `campus_z16_ml_overlay.jpg` — Microsoft (green) and Google Open Buildings (orange)
  footprints over the same imagery

**Present and correctly placed** (visually confirmed against the imagery):
the four academic Blocks A–D and the Central Library in the central cluster; all nine
hostels in the south-west cluster; the three dining halls; the Indoor Sports Complex;
the **circular football pitch** in the centre; the **athletics oval** in the north;
the **cricket ground** at the south edge; the tennis / basketball / volleyball /
badminton / squash courts; the **lake** on the east side; the campus fence line, which
follows a visible boundary all the way round including its stepped north-east extension;
and the road and footpath network, which tracks every visible road in the imagery.

**Missing.** Quantified by counting Microsoft footprints inside the campus polygon whose
centroid falls in no OSM building:

| Band | OSM bldgs | OSM area | MS bldgs | MS area | MS with no OSM |
|---|---:|---:|---:|---:|---:|
| north-east strip (lat > 28.5290) | 5 | 1 530 m² | 30 | 12 249 m² | **26 (10 774 m²)** |
| academic core (28.5255–28.5290) | 13 | 29 731 m² | 46 | 42 964 m² | 34 (21 586 m²) |
| hostel belt (28.5220–28.5255) | 25 | 39 480 m² | 49 | 37 752 m² | 31 (11 410 m²) |
| south (< 28.5220) | 8 | 16 596 m² | 14 | 9 000 m² | 12 (2 540 m²) |
| **campus total** | **51** | **87 336 m²** | **139** | **101 966 m²** | **103** |

The **north-east strip is the real gap**: OSM maps 1 530 m² of building there, the
imagery and both ML sets show ~12 000 m². That area is the faculty-residence and
new-hostel quarter next to the highway; OSM has the `landuse=residential` "Faculty
Residence" and two `landuse=construction` "Hostels (under construction)" polygons but
almost no individual footprints. Largest individually missing structures:

| Area | Centre (lat, lon) | MS confidence |
|---:|---|---:|
| 9 394 m² | 28.52558, 77.57580 | 0.801 |
| 4 455 m² | 28.52264, 77.57016 | 0.937 |
| 4 327 m² | 28.52363, 77.57045 | 0.921 |
| 3 105 m² | 28.52971, 77.57893 | 0.971 |
| 2 738 m² | 28.52866, 77.57826 | 0.982 |

**Verdict**: OSM is complete and correct for everything the demo narrates — every named
academic block, hostel, dining hall, the library, the sports complex, the football and
cricket grounds, the lake, the gates and the whole path network are there, with 26 usable
names. It under-maps the north-east residential quarter and a handful of large service
structures. Fix by union with the Microsoft set (§5.2), not by hand-tracing.

---

## 2. Building footprints and heights beyond OSM

### 2.1 Google Open Buildings v3 — FETCHED

Source page `https://sites.research.google/gr/open-buildings/` fetched 2026-09-05 07:02 UTC.

- **v3**, inference run **May 2023**, 1.8 billion detections over 58 million km²,
  146 countries and territories (Africa, South Asia, South-East Asia, Latin America,
  Caribbean).
- Confidence score range **[0.65, 1.0]**.
- **Licence: CC BY 4.0 *or* ODbL 1.0** — the page states the data is shared under both
  and the user picks one. For our purposes take **CC BY 4.0** (no share-alike on the
  rest of the style).
- Polygons total **178 GB**, points 48 GB.

GCS bucket listing (`storage.googleapis.com/storage/v1/b/open-buildings-data`,
fetched 07:02 UTC) confirms six prefixes under `v3/`:
`points_s2_level_4_gzip/`, `points_s2_level_6_gzip_no_header/`,
`polygons_s2_level_4/`, `polygons_s2_level_4_gzip/`,
`polygons_s2_level_6_gzip_no_header/`, `polygons_single_csv/`.
The level-4 polygon prefix has **333 files totalling 178.3 GB** (matches the site).

**S2 cell ids for the campus.** Computed with a pure-Python S2 implementation
(`data/map/s2cell.py`, quadratic UV→ST projection, Hilbert `kIJtoPos` /
`kPosToOrientation` tables). All four bbox corners and the centre land in the same cell
at every level ≤ 8:

| level | token | Open Buildings file | size |
|---:|---|---|---:|
| 4 | **`391`** | `v3/polygons_s2_level_4_gzip/391_buildings.csv.gz` | **7 189.1 MB** |
| 6 | **`390d`** | `v3/polygons_s2_level_6_gzip_no_header/390d_buildings.csv.gz` | **1 299.9 MB** |
| 7 | `390cc` | (used by the 2.5D temporal geotiffs) | — |
| 8 | `390c9` | — | — |

The S2 implementation was validated 14/14 against the published coverage of Open
Buildings v3: Delhi (`391`), the campus (`391`), Mumbai (`3bf`), Chennai (`3a5`),
Lagos (`103`), Nairobi (`183`), São Paulo (`94d`), Jakarta (`2e7`) all resolve to cells
that exist in the bucket, while Paris (`47f`), London (`487`), New York (`89d`),
Tokyo (`601`), Sydney (`6b1`) and Moscow (`46b`) all resolve to cells that do not — which
is exactly the dataset's stated coverage.

**Access method used.** GCS delivered 2.85 MB/s (measured on a 21 MB range request), so
the 1.30 GB level-6 shard was **streamed and filtered without ever landing on disk**:

```bash
curl -s "https://storage.googleapis.com/open-buildings-data/v3/\
polygons_s2_level_6_gzip_no_header/390d_buildings.csv.gz" \
 | gzcat \
 | awk -F',' '($1+0)>28.5100 && ($1+0)<28.5370 && ($2+0)>77.5600 && ($2+0)<77.5860' \
 > ob_390d_snu.csv
```

Started 07:04:13 UTC, finished within ~8 min, 3 044 rows survived the padded window.
No Earth Engine account needed. Peak disk use: 0.
Schema (level-6 files have **no header**): `latitude, longitude, area_in_meters,
confidence, geometry (WKT), full_plus_code`.

**Result** → `data/map/snu_buildings_open.geojson`, **700 footprints** with centroid
inside the exact bbox:

- area: min 5.5 m², **median 57.9 m²**, mean 176.1 m², max 6 822.6 m²; total 123 265 m²
- confidence: min 0.650, median 0.781, max 0.954
- ≥ 0.70: 569 · ≥ 0.75: 441 · ≥ 0.80: 289 · ≥ 0.85: 153 · ≥ 0.90: 47
- 143 footprints ≥ 200 m², 21 ≥ 1 000 m²
- 0 multipolygons, 1 polygon with a hole

**Assessment: do not use Google Open Buildings for the extrusion layer.** A median
footprint of 57.9 m² with 382 polygons inside a campus that has 51 real buildings means
the model has shattered each hostel block and each academic block into a dozen roof
facets. It renders as gravel, not architecture. Its confidence ceiling of 0.954 is also
low. Keep the file for the completeness cross-check in §1.9 and throw it away for
rendering.

### 2.2 Google Open Buildings 2.5D Temporal (heights) — LOCATED, NOT FETCHED

Source page `https://sites.research.google/gr/open-buildings/temporal/` fetched
2026-09-05 07:02 UTC.

- Three raster bands: **`building_fractional_count`, `building_height`,
  `building_presence`**. Effective resolution ~4 m, rasters stored at **0.5 m**.
- Annual, **2016–2023** (8 years).
- **"The mean absolute error of building height prediction is 1.5 meters and was only
  evaluated in North America, Europe and Japan."** — i.e. the 1.5 m figure is *not*
  validated for India. Quote it with that caveat or not at all.
- Licence: **CC BY 4.0 or ODbL 1.0**, and it leverages Copernicus Sentinel-2 data.
- Earth Engine collection id `GOOGLE/Research/open-buildings-temporal/v1`
  (catalog entry `GOOGLE_Research_open-buildings-temporal_v1`).
- GCS bucket `open-buildings-temporal-data`, prefixes `v1/geotiffs/` and `v1/manifests/`
  (listing fetched 07:03 UTC; the bucket exists, `open-buildings-temporal` does not).

**The exact file covering this campus was identified.** Downloaded the Earth Engine
ingest manifest `v1/manifests/39_EPSG_32643_2023_06_30.json` (3 076 541 bytes, fetched
07:07 UTC), which lists 8 312 source tiles with affine transforms in **EPSG:32643
(UTM 43N)**. Projecting the campus centre with a Snyder-series forward transform gives
**E = 751 875.0, N = 3 157 999.6**, which falls in exactly one tile:

```
gs://open-buildings-temporal-data/v1/geotiffs/390cc_2023_06_30/tile_-POG-fNZgug.tif
  size          270 448 181 bytes (270.4 MB)
  dimensions    25 000 × 25 000 px
  pixel size    0.5 m
  extent (32643) E 750 204 – 762 704,  N 3 155 792 – 3 168 292
  bands         building_fractional_count, building_height, building_presence
  nodata        -99.0
```

**Not fetched.** Two reasons, both stated so the lead can overrule: (a) 270 MB exceeds
the 200 MB budget in the brief; (b) more decisively, **there is no GDAL, rasterio or
pyarrow in this environment** (`gdalinfo`, `gdal_translate`, `ogr2ogr` all absent;
`rasterio`, `geopandas`, `pyproj`, `duckdb`, `pyarrow` all absent from the venv), so a
25 000² three-band float GeoTIFF could be downloaded but not read. If the lead wants it:

```bash
# option A, needs GDAL (brew install gdal) — reads only the campus window over HTTP
gdal_translate -projwin 750900 3159800 752900 3157300 \
  /vsicurl/https://storage.googleapis.com/open-buildings-temporal-data/v1/geotiffs/390cc_2023_06_30/tile_-POG-fNZgug.tif \
  snu_height.tif -b 2
# option B, Earth Engine (free non-commercial account)
ee.ImageCollection('GOOGLE/Research/open-buildings-temporal/v1')
  .filterDate('2023-01-01','2024-01-01').select('building_height')
  .mosaic().clip(bbox)   # then Export.image.toDrive at 4 m
```

**Is the height data worth using for extrusions? No, for this map.** Three arguments:
1. Effective resolution is 4 m and the product is a **raster of mean building height per
   pixel**, not a per-building attribute. To extrude an OSM footprint you would have to
   zonal-average the raster inside the polygon — an extra offline preprocessing step with
   a GDAL dependency, for ~58 buildings.
2. The 1.5 m MAE is from North America, Europe and Japan only. Nothing validates it here.
3. We already have `building:levels` on the 13 buildings that dominate the skyline
   (9 hostels at 6 levels, 4 academic blocks at 4 levels), and those are the ones a judge
   will look at. A raster average would probably make them *worse*, since Sentinel-2 at
   10 m cannot resolve a 4-storey block from its courtyard.

**Recommendation**: skip the raster; do a 20-minute campus walk and add `building:levels`
to the remaining ~30 buildings in OSM (which also gives back to OSM and is a nice line in
the presentation). Fall back to the type defaults in §5.3 in the meantime.

### 2.3 Microsoft Global ML Building Footprints — FETCHED

Repo `https://github.com/microsoft/GlobalMLBuildingFootprints` fetched 2026-09-05 07:09 UTC;
raw README fetched the same minute (20 819 bytes).

- **1.9k GitHub stars**; most recent dataset refresh **2026-08-13**; repo actively
  maintained through 2026.
- **1.4 billion buildings** detected from Bing Maps imagery 2014–2024
  (Maxar, Airbus, IGN France sources).
- **Licence: "The data is freely available for download and use under CDLA Permissive 2.0."**
  (Community Data License Agreement – Permissive, Version 2.0.) Note this is *not* ODbL —
  it is more permissive and imposes no share-alike.
- Heights exist for ~174 M footprints globally, but the India contribution came in the
  **2024-03-26** release ("Added 128M building footprint edits and 3.5M height estimates …
  Primary contributions are in India (110M) and Nepal (7M)") and nearly all height
  estimates in the changelog go to the US and Western Europe.

**Tile id for this campus**: the whole bbox — all four corners — sits inside a single
level-9 quadkey, **`123121312`** (slippy tile z9 x=366 y=213). Two releases were
downloaded and clipped to be sure the file is current:

| Release index | URL | Download | Lines | In bbox | With height |
|---|---|---:|---:|---:|---:|
| 2026-02-03 | `minedbuildings.z5.web.core.windows.net/global-buildings/2026-02-03/…/quadkey=123121312/part-00106-4feead82-….csv.gz` | 102 385 002 B (97.6 MB label), 5 min 14 s | 1 001 982 | 302 | **0** |
| 2026-08-13 | `bfppub.z5.web.core.windows.net/2026-08-13/…/quadkey=123121312/part-00106-110f5303-….csv.gz` | 102 739 126 B (98.0 MB label) | 1 001 982 | 302 | **0** |

The two releases are byte-identical in content for this area. `snu_buildings_ms.geojson`
therefore holds the current data. **Every footprint in this tile carries `height: -1.0`,
Microsoft's "no estimate" sentinel — there are no Microsoft heights for SNU.**

Confidence in the clipped set: min 0.723, median 0.976, max 1.0.
Inside the campus polygon: 139 footprints, 101 966 m², **103 of them with no OSM
counterpart**. Median footprint is far larger and better shaped than Google's.

The current index is now at `https://bfppub.blob.core.windows.net/$web/2026-08-13/dataset-links.csv`
(6 382 044 B, 30 341 rows, 667 for India). The old `minedbuildings.z5.web.core.windows.net`
host still serves the 2026-02-03 index (7 171 802 B, 30 345 rows) — the repo notes a
hosting migration.

### 2.4 Overture Maps — documented, not fetched

`https://docs.overturemaps.org/guides/buildings/` and `/attribution/` fetched
2026-09-05 07:11 UTC.

- Current release **2026-08-19.0**.
- Buildings theme merges OSM (highest priority), Esri Community Maps, national
  authoritative sets, and ML roofprints from **Microsoft, Google Open Buildings** and an
  East Asian dataset — i.e. it is the union we are about to build by hand, already
  conflated and deduplicated, with `height`, `num_floors`, `min_height`, `roof_shape` and
  `names` columns.
- **Licence: ODbL** for buildings (because OSM is in it); places is CDLA Permissive 2.0 + Apache 2.0.
  Required buildings attribution: **"© OpenStreetMap contributors. Available under the
  Open Database License"**. Publication citation: **"Overture Maps Foundation, overturemaps.org"**.
- Paths: `s3://overturemaps-us-west-2/release/2026-08-19.0/theme=buildings/type=building/*`
  and `https://overturemapswestus2.blob.core.windows.net/release/2026-08-19.0/theme=buildings/type=building/*`.

**Not fetched** because a bbox query over the GeoParquet needs `duckdb` (with `spatial`
and `httpfs`) or `pyarrow`, neither of which is installed, and installing into the
project venv is outside this workstream's write scope. If the lead approves
`pip install duckdb`, this is a 30-second job and probably supersedes §2.1 and §2.3:

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;
COPY (SELECT id, names.primary AS name, height, num_floors, class, sources,
             ST_AsText(geometry) AS wkt
      FROM read_parquet('s3://overturemaps-us-west-2/release/2026-08-19.0/theme=buildings/type=building/*',
                        filename=true, hive_partitioning=1)
      WHERE bbox.xmin BETWEEN 77.5639 AND 77.5823
        AND bbox.ymin BETWEEN 28.5133 AND 28.5335)
TO 'snu_overture_buildings.csv';
```

---

## 3. Satellite imagery

### 3.1 Tile scheme

`https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
— note **`{y}` before `{x}`**, the ArcGIS convention. Otherwise it is standard Web
Mercator / GoogleMapsCompatible: 256×256 JPEG, LOD 0–23 advertised (service metadata
fetched 07:03 UTC; max LOD 23 has resolution 0.01866 m/px, scale 1:70.5).

Service `copyrightText`: **"Source: Esri, Vantor, Earthstar Geographics, and the GIS
User Community"**. (Vantor is Maxar's current name — the identify service returns
`SOURCE: Vantor` with `DESCRIPTION: WV03`, i.e. WorldView-3.)

### 3.2 Test tiles at the campus centre — all fetched 2026-09-05 06:52 UTC

Saved to `data/map/tile_samples/`.

| z | x | y | HTTP | bytes | verdict |
|---:|---:|---:|---:|---:|---|
| 15 | 23444 | 13673 | 200 | 14 291 | real imagery |
| 16 | 46889 | 27346 | 200 | 17 715 | real imagery |
| 17 | 93779 | 54692 | 200 | 14 962 | real imagery — cricket ground and hostels clearly resolved |
| 18 | 187559 | 109385 | 200 | 15 143 | real imagery — individual buildings, bike parking, tree crowns |
| 19 | 375119 | 218771 | 200 | 13 462 | real imagery — individual parked cars visible |
| 20 | 750238 | 437543 | 200 | **2 521** | **grey placeholder, "Map data not yet available"** |
| 21 | 1500476 | 875086 | 200 | **2 521** | same placeholder |

Every response is HTTP 200 — **the server never 404s, it serves a 2 521-byte grey
placeholder JPEG**. Any bulk downloader must therefore filter on file size or content,
not status code. Both z20 and z21 returned byte-identical placeholders (visually
confirmed by opening them).

**Maximum usable zoom is 19.**

### 3.3 Imagery source, resolution and capture date at this point

Queried the World Imagery `identify` endpoint at `77.573818, 28.524416` (fetched
06:52:49 UTC, HTTP 200, 8 254 bytes). Five layers respond; the substantive answer:

| Field | Value |
|---|---|
| `SOURCE_INFO` | **Vivid Advanced** |
| `SOURCE` | **Vantor** (Maxar) |
| `DESCRIPTION` | **WV03** (WorldView-3) |
| `DATE (YYYYMMDD)` | **20230208** — 8 February 2023 |
| `RESOLUTION (M)` | **0.31** |
| `ACCURACY (M)` | **5** |
| `BlockName` | `Vivid_Advanced_Delhi_IN_23Q2` |
| `ReleaseName` | `Maps 2023.R07` |
| cache levels | 60 cm layer 12–18, **30 cm layer 19–19** |

This independently confirms z19 as the ceiling: the 30 cm layer is cached at level 19
only, and nothing exists above it.

**Two numbers matter for the demo narrative.** The imagery is **3.6 years old** as of
today (Feb 2023 → Sep 2026) — recent construction on campus, notably the north-east
hostels, may look different on the ground. And the stated horizontal accuracy is **5 m**,
which is the same order as the positioning error the dead-reckoning engine is trying to
demonstrate. **Do not use the satellite layer as ground truth for a trajectory overlay**;
a track that looks 3 m off the road may be the basemap, not the estimator. Say this
before a judge says it.

### 3.4 Terms of use — VERIFIED, and the answer is no

Two independent verified sources.

**(a) The ArcGIS Online item record.** `https://www.arcgis.com/sharing/rest/content/items/10df2279f9684e4a9f6a7f08febac2a9?f=json`
(fetched 06:53:40 UTC, HTTP 200). `licenseInfo` says the layer is licensed under the Esri
Master License Agreement, then, verbatim:

> **Export:** This layer is not intended to be used to export tiles for offline.

with a pointer to a separate item, **World Imagery (for Export)**
(`226d23f076da478bba4589e7eae95952`, fetched 06:54:07 UTC). That item's own description
confirms it "is designed to support exporting small volumes of basemap tiles for offline
use", allows up to 150 000 tiles per request, is served from `tiledbasemaps.arcgis.com`,
and — decisively — its licenseInfo states: *"This item requires an ArcGIS Online
organizational subscription or an ArcGIS Developer account"*, and it *"is intended to
support export of basemap tiles for offline use in ArcGIS applications and other
applications built with an ArcGIS Runtime SDK"*. A MapLibre app is neither.

**(b) The Terms of Use summary.** `https://goto.arcgis.com/termsofuse/viewsummary`
301-redirects to `https://www.esri.com/content/dam/arcgisonline/docs/tou_summary.pdf`
(fetched 06:53 UTC, 111 987 bytes; text extracted with `pdftotext -layout`).
Title: *"Frequently asked questions about items owned by Esri in ArcGIS Online"*,
**last updated 21 April 2025**. Verbatim:

> **YOU MAY NOT**
> Systematically harvest basemap tiles through any method other than using Esri Content Packages
> Redistribute basemap tiles
> Download, redistribute or self-host any content hosted by Esri.

and under what a subscriber *may* do:

> Use the basemap data offline in the following manner.
> • The data may only be taken offline using Esri Content Packages
> • The package can be used with any device as long as it is used exclusively with Esri software.

and the conditions:

> Provide attribution to Esri and its data providers.
> Use with Esri software and comply with its terms of use. If you do not have Esri
> software, you must purchase an ArcGIS Online subscription.

**There is no non-commercial or educational exemption anywhere in the document.** The
word "student", "education" and "non-commercial" do not appear except in the Living Atlas
clause, which restricts *commercial* use and does not grant an academic carve-out for
caching.

**Verdict for the team.** Pre-downloading z15–z19 into the APK is a clear breach of three
of the four "YOU MAY NOT" bullets. Two compliant options:

- **Option A (recommended)**: satellite toggle is **online-only**. Fetch tiles live from
  the Esri endpoint when there is a network, let MapLibre's normal ephemeral HTTP cache do
  what a browser does, ship nothing. Attribution string in the corner whenever the layer
  is on. The demo's actual claim — offline dead reckoning — is about the *vector* map,
  which is 237 KB gzipped and genuinely offline.
- **Option B**: cache **Sentinel-2 cloudless** instead (§3.6). Legal, ugly, 10 m.

### 3.5 Tile-count and size estimate for z15–z19 over the bbox

Computed from the slippy-tile ranges; MB assumes 15 KB/tile, the mean of the five real
tiles measured above.

| z | x range | y range | tiles | MB | m/px at 28.52 N |
|---:|---|---|---:|---:|---:|
| 15 | 23444–23445 | 13672–13674 | 6 | 0.09 | 4.197 |
| 16 | 46888–46891 | 27344–27348 | 20 | 0.29 | 2.099 |
| 17 | 93776–93782 | 54689–54697 | 63 | 0.92 | 1.049 |
| 18 | 187552–187565 | 109378–109395 | 252 | 3.69 | 0.525 |
| 19 | 375104–375131 | 218756–218790 | 980 | 14.36 | 0.262 |
| **z15–19 total** | | | **1 321** | **19.4 MB** | |
| (z20, for reference) | 750209–750262 | 437513–437580 | 3 672 | 53.79 | 0.131 |

Adding z12–z14 costs 4 more tiles and 0.06 MB, so a z12–z19 pyramid is **1 325 tiles,
19.4 MB**. Technically trivial. Legally forbidden per §3.4. No bulk download was
performed — only the 7 test tiles plus the 20-tile z16 block used for the completeness
render, 27 Esri tiles in total.

### 3.6 A legal offline satellite alternative: Sentinel-2 cloudless (EOX)

WMTS capabilities `https://tiles.maps.eox.at/wmts/1.0.0/WMTSCapabilities.xml`
fetched 2026-09-05 07:11 UTC (67 911 bytes) — the authoritative, machine-readable source
for licence and attribution.

- Layers `s2cloudless-2017` … **`s2cloudless-2025`**, each with a `_3857` variant, JPEG,
  `GoogleMapsCompatible` matrix set advertised to **level 21** (upsampled; the underlying
  data is 10 m Sentinel-2, so real detail runs out around z14–z15).
- RESTful tile URL, verified working:
  `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg`
  — z15 → HTTP 200, 10 103 B; z17 → HTTP 200, 5 975 B; 2023 and 2020 also 200.
- **Licence, verbatim from the layer abstract**: 2018 onwards (including 2024 and 2025)
  are *"released under Creative Commons Attribution-NonCommercial-ShareAlike 4.0
  International License"*. **2017 is CC BY 4.0** (no NC, no SA) — the only year that is
  safe if the project might ever be commercialised.
- Service-level `ows:AccessConstraints`: *"Proper attribution is required for any usage."*
- Attribution to use: `Sentinel-2 cloudless 2024 by EOX IT Services GmbH (Contains
  modified Copernicus Sentinel data 2024) — CC BY-NC-SA 4.0`.

Visual check (`tile_samples/s2cloudless_2024_z15.jpg`): the campus is recognisable —
the white hostel roofs, the field pattern, the highway — but at 10 m the buildings are
blobs. **Usable as a distant backdrop below ~z15, useless as a campus basemap.**
A student hackathon demo is non-commercial, so CC BY-NC-SA is satisfiable, and unlike
Esri this data *may* be cached and shipped.

Also test-fetched, for completeness: `https://tile.openstreetmap.org/17/93779/54692.png`
→ HTTP 200, 19 111 B, real OSM Carto raster. **Do not bulk-download it** — the OSMF Tile
Usage Policy forbids bulk downloading from tile.openstreetmap.org. It is only useful as a
visual reference while designing the style.

---

## 4. Other open data worth adding, and the gaps

### 4.1 Campus boundary — HAVE IT

`data/map/snu_campus_boundary.geojson`, 115.7 ha, from OSM way/369248213. Use it for the
vignette/mask outside campus, for the "you are here" fit-bounds, and for filtering ML
footprints. §1.7.

### 4.2 Tree cover — THIN, and here is the cheap fix

OSM in this bbox has **1 `natural=tree`** (a named specimen, "The Lonely Tree"),
**3 `natural=tree_row`**, **1 `landuse=forest`**, **3 `natural=scrub`**. That is nothing —
the satellite imagery shows dense avenue planting along every campus road and a large
wooded belt on the east side.

Options, cheapest first:
1. **Render the 26 `landuse=grass` polygons plus the 2 parks and the biodiversity park in
   a layered green palette** and add a subtle noise/pattern fill. This alone reads as
   "leafy campus" and costs nothing. Recommended.
2. **Draw the tree canopy as a buffer around the 3 `natural=tree_row` ways** with a
   soft-edged fill.
3. **Trace ~10 wood polygons by hand** from the z18 imagery (30 minutes) and tag them
   `natural=wood` in OSM. Best value per hour of any data task in this workstream.
4. Global canopy products (ESA WorldCover 10 m, CC BY 4.0; Meta/WRI 1 m canopy height)
   exist but need a raster toolchain we do not have, and 10 m canopy over a 4 km² campus
   is not going to look better than option 1. **UNVERIFIED** — not fetched this review.

### 4.3 Street lighting — ABSENT

**Zero features in the bbox carry a `lit` tag.** No `highway=street_lamp` nodes either.
If the demo wants a day/night toggle, lamp positions must be surveyed. Low priority.

### 4.4 Road surface — SPARSE BUT USEFUL

Only 20 ways in the bbox have `surface`: `concrete` ×6, `asphalt` ×3, `paving_stones` ×3,
`unpaved` ×3, `grass` ×4, `sand` ×1. Out of 261 road+path ways, that is **8 % coverage**.

Route 1 (`corridor_route1.geojson`, OSM ways 547215901 + 547215900) and route 2
(`corridor_route2.geojson`, ways 369151490, 369149867, 547215917, 432385377, 369231604)
run on campus service roads. `way/369149867` ("2011 Street", part of route 2) is tagged
`surface=asphalt` and `access=private`. The rest are untagged.

This matters to the IMU work, not just the map: surface class is a plausible covariate for
vibration energy, and the render should show route 1 and route 2 in different styling
anyway.

### 4.5 Speed bumps — **ABSENT, AND THIS IS AN ACTION ITEM**

**There are zero `traffic_calming=*` features anywhere in the 4.05 km² bbox.** Not one
bump, hump, table, cushion or rumble strip. The team's own recordings say otherwise.

This is the single most valuable survey the team can do, because a speed bump is a
**hard, repeatable, geo-referenced vertical-acceleration landmark** — exactly the kind of
ZUPT-adjacent constraint the ESKF can use, and exactly the kind of thing that makes a
demo look engineered rather than lucky.

Procedure:
1. Ride each corridor at a constant speed with the logger running. Every bump is an
   unmistakable spike in the down-axis accelerometer.
2. Convert each spike's timestamp to a position using the existing route-1 solution
   (3.4 % median drift over 339 m is ≈ 12 m, tight enough to identify which bump).
3. Confirm each candidate against the z19 Esri tile (0.26 m/px — a painted hump is
   visible) and, better, by standing on it with the phone.
4. Add to OSM as nodes on the way: `traffic_calming=bump` (short, abrupt),
   `traffic_calming=hump` (long, rounded), or `traffic_calming=table` (raised crossing).
   Optionally `surface=*` and `traffic_calming:material=*`.
5. Re-run the Overpass query; they appear in `snu_osm_full.geojson` automatically and can
   be rendered as chevrons on the corridor and used as ESKF landmarks.

Even 6–10 bumps across the two corridors would be a strong, honest, novel contribution —
both to the project and back to OSM.

### 4.6 Gates, entrances, parking, crossings — HAVE THEM

4 `barrier=gate` nodes, two of them named **SNU Gate No. 1** and **SNU Gate No. 2**;
8 `entrance=yes` nodes; 3 `amenity=parking` polygons (10 168 m², one named "Parking 1")
plus 2 `amenity=parking_entrance`; 43 `crossing=unmarked` nodes. Gates are good
"trip start/end" markers in the UI.

### 4.7 Labels — 46 named features

26 named buildings (§1.5) + ~20 named non-building features (§1.6, §1.8). Enough for a
map that reads as a real place without any hand-authored label file. Label priority in §5.4.

---

## 5. Layer plan for the MapLibre style

Renderer: MapLibre Native Android. `fill-extrusion` paint properties confirmed against
`https://maplibre.org/maplibre-style-spec/layers/` (fetched 2026-09-05 07:12 UTC):
`fill-extrusion-color`, `-height`, `-base`, `-opacity`, `-pattern`, `-translate`,
`-translate-anchor`, **`-vertical-gradient`**. Symbol layers confirmed to support
`text-field`, `text-size`, `symbol-sort-key`, `text-allow-overlap`. Recent MapLibre
Native also added `fill-extrusion-rounded-corner-distance` for rounded building corners —
nice-to-have, check it exists in the pinned version before using it, otherwise the style
fails to parse.

### 5.1 Sources

| Source id | Type | File | Bytes (gz) | Notes |
|---|---|---|---:|---|
| `snu` | geojson | `snu_osm_full.geojson` | 237 KB | everything OSM; filter per layer on `@class` |
| `campus` | geojson | `snu_campus_boundary.geojson` | 1.7 KB | mask + fit-bounds |
| `bldg_ms` | geojson | `snu_buildings_ms.geojson` | 37 KB | gap-fill only, see §5.2 |
| `corridor1` | geojson | `corridor_route1.geojson` | — | 339 m, 37 pts |
| `corridor2` | geojson | `corridor_route2.geojson` | — | 927 m, 41 pts |
| `track` | geojson | in-memory | — | the live dead-reckoning estimate |
| `sat` | raster | Esri XYZ, **online only** | — | `tileSize 256`, `maxzoom 19` |

All five static GeoJSONs together are **352 KB gzipped**. Ship them in `assets/`.
MapLibre parses local GeoJSON sources with no network and no tile server.

### 5.2 Building merge rule (do this offline once, not at runtime)

Do **not** feed OSM and Microsoft into the same extrusion layer unmerged — the 32 OSM
buildings that already have a Microsoft twin will z-fight and look doubled.

```
keep every OSM building                          (51 in campus, all names + levels)
add a Microsoft footprint only if
      its centroid is inside no OSM building     (103 qualify in campus)
  and its area >= 40 m2                          (drops sheds and noise)
  and its confidence >= 0.85                     (median is 0.976, so this is cheap)
tag the added ones source="ms", name=null, render_height = 6.4 m default
```

Google Open Buildings is **excluded from rendering** (median footprint 57.9 m², shatters
blocks — §2.1). Keep it as the completeness cross-check only.

Attribution consequence: adding Microsoft data means the CDLA-Permissive-2.0 credit must
appear alongside the OSM one (§5.5).

### 5.3 Extrusion height rule

Implemented in `data/map/osm2geojson.py`; every building feature in
`snu_osm_full.geojson` already carries `render_height`, `render_min_height` and
`height_source`, so the style can read `["get","render_height"]` with no expression logic.

```
render_height =
    height                        if tagged and > 0      (1 building: Central Library, 12 m)
    else building:height          if tagged and > 0      (0 buildings)
    else building:levels * 3.2 m                         (14 buildings)
    else default_by_type                                 (43 buildings)

render_min_height =
    min_height  else  building:min_level * 3.2 m  else  0
```

3.2 m/level is the usual OSM rendering convention and matches the one datapoint we have:
Central Library is `building:levels=3` with `height=12`, i.e. 4.0 m/level — a library
with tall reading floors, so 3.2 m stays the right default for hostels and offices.

Defaults by `building=` value:

| `building=` | default | count | rationale |
|---|---:|---:|---|
| `dormitory` | 19.2 m | 23 | = 6 levels, matches the 9 tagged hostels |
| `university` | 12.8 m | 13 | = 4 levels, matches Blocks A–D |
| `apartments` | 16.0 m | 0 | 5 levels |
| `college` | 12.8 m | 0 | |
| `residential` / `commercial` / `school` | 9.6 m | 0 | 3 levels |
| `industrial` / `warehouse` | 8.0 m | 0 | |
| `retail` / `yes` | 6.4 m | 20 | 2 levels — conservative, avoids a fake skyline |
| `greenhouse` / `roof` | 4.0 m | 2 | |
| `shed` / `garage(s)` / `hut` / `service` | 3.2 m | 0 | |
| Microsoft gap-fill | 6.4 m | 103 | no height data exists (§2.3) |

Colour the extrusion by `height_source` during development (`height`/`levels` = solid,
`default` = 15 % desaturated) so you can see at a glance which blocks are guesses. Ship it
with a single colour.

### 5.4 Layer stack, bottom to top

| # | Layer id | Source / filter | Type | Zoom | Notes |
|---:|---|---|---|---|---|
| 0 | `bg` | — | background | 0+ | warm off-white `#f5f2ec` day / `#12161c` night |
| 1 | `sat` | `sat` | raster | 0–19 | opacity 0 unless toggled; `maxzoom 19`, overzoom above |
| 2 | `campus-mask` | `campus` | fill | 0+ | inverted-ish: dim everything outside with a low-opacity dark fill over the whole canvas beneath the campus fill |
| 3 | `landuse-grass` | `snu`, `@class=landuse` & `landuse=grass` | fill | 13+ | the 26 grass polygons — the campus's green base |
| 4 | `landuse-other` | `snu`, `@class=landuse` | fill | 13+ | farmland / construction / residential, muted |
| 5 | `green` | `snu`, `@class=green` | fill | 13+ | parks, biodiversity park, forest, scrub — darker green |
| 6 | `water-fill` | `snu`, `@class=water` polygons | fill | 12+ | Lake SNU + 4 ponds |
| 7 | `water-line` | `snu`, `@class=water` lines | line | 14+ | the ditch |
| 8 | `sport-fill` | `snu`, `@class=sport` | fill | 14+ | colour ramp by `sport`: soccer/cricket green, tennis/basketball clay, golf pale green |
| 9 | `sport-line` | `snu`, `@class=sport` | line | 15+ | white 1 px pitch markings |
| 10 | `parking` | `snu`, `@class=parking` | fill | 15+ | flat grey |
| 11 | `road-casing` | `snu`, `@class=road` | line | 12+ | width by class, dark casing |
| 12 | `road-fill` | `snu`, `@class=road` | line | 12+ | width by class; trunk > tertiary > residential > service |
| 13 | `path` | `snu`, `@class=path` | line | 15+ | 1.5 px dashed `[2,2]`; the 13.7 km of footway is what makes a campus map feel like a campus |
| 14 | `barrier` | `snu`, `@class=barrier` lines | line | 16+ | thin dotted |
| 15 | `building-3d` | merged buildings (§5.2) | **fill-extrusion** | 15.5+ | height `["get","render_height"]`, base `["get","render_min_height"]`, `fill-extrusion-vertical-gradient: true`, opacity 0.95 |
| 15b | `building-flat` | same | fill | 13–15.5 | flat footprints below the extrusion zoom, so the map does not pop |
| 16 | `corridor1` / `corridor2` | `corridor1`, `corridor2` | line | 14+ | 4 px, two distinct accent colours, `line-cap: round` |
| 17 | `track-live` | `track` | line | 14+ | the estimate; bright, 5 px, drawn last of the lines |
| 18 | `track-head` | `track` | circle | 14+ | current position + heading cone |
| 19 | `label-campus` | `campus` | symbol | 12–15 | "Shiv Nadar University" |
| 20 | `label-building` | merged buildings, `has name` | symbol | 16+ | see §5.4 priorities |
| 21 | `label-sport` | `snu`, `@class=sport` & `has name` | symbol | 16+ | |
| 22 | `label-water` | `snu`, `@class=water` & `has name` | symbol | 15+ | "Lake SNU" italic |
| 23 | `label-poi` | `snu`, `@class=poi`/`tree`/`barrier` & `has name` | symbol | 17+ | with icon |
| 24 | `label-gate` | `snu`, `barrier=gate` & `has name` | symbol | 16+ | gates are landmarks for the demo narrative |

**Label priority** via `symbol-sort-key` (lower draws first and wins collisions), with
`text-allow-overlap: false` everywhere except the live track head:

| sort-key | features | min zoom |
|---:|---|---|
| 0 | "Shiv Nadar University" | 12 |
| 10 | Central Library, Indoor Sports Complex, Blocks A–D | 15.5 |
| 20 | Hostels 1A–3C, Management Block, Research Annexe | 16 |
| 30 | Dining Halls 1–3, Health and wellness centre, Auctus Supermarket, Pharmacy, Post Office | 16.5 |
| 40 | Football Ground, Cricket Ground, Lake SNU, SNU Biodiversity Park, Shivaji park, Golf Course, Amphitheatre | 16 |
| 50 | Tennis / Basketball / Volleyball / Badminton / Squash Courts, Chess Garden | 17 |
| 60 | SNU Gate No. 1 & 2, Parking 1, Entrance Security Office | 16.5 |
| 70 | HDFC Bank, PNB ATM, Mini Mart, Belleza, Stage, The Lonely Tree | 17.5 |

Note `Dining Hall 3` exists as **two** ways (`way/729630264` and `way/1473676593`) — a
duplicate in OSM. Deduplicate on name before labelling, or you get two labels fighting.

### 5.5 Attribution strings — legally required

Show in a dismissible corner credit and again in an "About / Data sources" screen.
Per the OSMF attribution guidelines (fetched 2026-09-05 07:10 UTC; page last edited
16 March 2022), an app may show attribution on a splash screen or a corner credit that
collapses, provided the licence is reachable from a menu.

**Always on (vector map):**
```
Map data © OpenStreetMap contributors, ODbL
Building footprints © Microsoft, CDLA-Permissive-2.0
```
`https://www.openstreetmap.org/copyright` must be reachable — as a link, or as the literal
URL where links are impossible.

**Only while the Esri satellite layer is visible:**
```
Imagery: Esri, Vantor, Earthstar Geographics, and the GIS User Community
```
(exact `copyrightText` from the service metadata). Note §3.4: with no ArcGIS
subscription, using this layer at all is on thin ice; using it *online only* with this
credit is the defensible reading.

**If Sentinel-2 cloudless is used instead:**
```
Sentinel-2 cloudless 2024 by EOX IT Services GmbH
(Contains modified Copernicus Sentinel data 2024) — CC BY-NC-SA 4.0
```

**Only if Google Open Buildings is rendered** (currently it is not):
```
Building footprints © Google, Open Buildings v3 — CC BY 4.0
```

**If Overture is adopted instead of the DIY merge:**
```
© OpenStreetMap contributors. Available under the Open Database License
Overture Maps Foundation, overturemaps.org (accessed 2026-09-05)
```

### 5.6 Style polish that costs nothing

- **Vertical gradient on the extrusions** (`fill-extrusion-vertical-gradient: true`)
  plus a single directional light — free depth, one line of style.
- **Pitch the camera to 50–60° and bearing to align the corridor** when the demo starts.
  The corridors are the story; frame them.
- **Two green tones**, not one: `landuse=grass` (26 polygons) lighter, `leisure=park` and
  `landuse=forest` darker. The campus already has the geometry for this.
- **Draw the 13.67 km of footways.** More than anything else this is what separates
  "a road map" from "a campus map".
- **Colour the two corridors differently and label them** "Route 1 · 339 m" and
  "Route 2 · 927 m" from the properties already in the corridor files.
- **Do not render the 4 route relations** (`type=route`) — their member ways are already
  in the extract and you will draw NH-91 twice.

---

## 6. Open decisions for the lead

1. **Satellite layer.** Esri's terms forbid pre-caching tiles (§3.4, verified from two
   sources). Choose: (A) online-only Esri toggle with credit — recommended; (B) ship
   Sentinel-2 cloudless at 10 m, legal but coarse; (C) no satellite, vector only.
   The offline claim of the project rests on the vector map, which is 237 KB.
2. **`pip install duckdb` into `.venv`?** If yes, Overture 2026-08-19.0 replaces the
   hand-rolled OSM+Microsoft merge with a pre-conflated set carrying `height` and
   `num_floors`, in about 30 seconds. Outside this workstream's write scope, so not done.
3. **Open Buildings 2.5D height raster.** 270 MB, needs GDAL or Earth Engine, 4 m
   effective resolution, MAE validated only outside India. Recommendation: skip it, and
   instead survey `building:levels` for the ~30 untagged buildings on foot.
4. **Speed-bump survey (§4.5).** Zero exist in OSM here. This is the highest-value
   remaining data task and it feeds the IMU work, not just the map. Needs a decision on
   who does the ride and when.
5. **North-east quarter.** OSM maps 1 530 m² of building where the imagery shows ~12 000 m².
   Accept the Microsoft gap-fill (unnamed grey blocks), or hand-trace and name them in OSM?

---

## 7. Source log

Every URL below was fetched or downloaded during this review on **2026-09-05**.
Nothing in this document is cited from memory.

| # | URL | Fetched (UTC) | Result |
|---:|---|---|---|
| 1 | `https://overpass-api.de/api/interpreter` (POST, query in §1.1) | 06:51 | 200, 2 153 696 B |
| 2 | `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{15..21}/{y}/{x}` | 06:52 | 200 ×7; z20/z21 are placeholders |
| 3 | `https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/identify?…` | 06:52 | 200, 8 254 B, Vivid Advanced / WV03 / 2023-02-08 / 0.31 m |
| 4 | `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=json` | 06:53 | 200, 11 142 B, copyrightText + LODs 0–23 |
| 5 | `https://www.arcgis.com/sharing/rest/content/items/10df2279f9684e4a9f6a7f08febac2a9?f=json` | 06:53 | 200, "not intended to be used to export tiles for offline" |
| 6 | `https://www.arcgis.com/sharing/rest/content/items/226d23f076da478bba4589e7eae95952?f=json` | 06:54 | 200, World Imagery (for Export), subscription required |
| 7 | `https://goto.arcgis.com/termsofuse/viewsummary` → `https://www.esri.com/content/dam/arcgisonline/docs/tou_summary.pdf` | 06:53 | 301 then 200, 111 987 B, last updated 2025-04-21 |
| 8 | `https://www.esri.com/en-us/legal/terms/full-master-agreement` | 06:52 | 200 but index page only, no clause text — **UNVERIFIED as a clause source**; superseded by #7 |
| 9 | `https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv` | 06:55 | 200, 7 171 802 B, 30 345 rows |
| 10 | `https://minedbuildings.z5.web.core.windows.net/…/quadkey=123121312/part-00106-4feead82-….csv.gz` | 07:01 | 200, 102 385 002 B |
| 11 | `https://bfppub.blob.core.windows.net/$web/2026-08-13/dataset-links.csv` | 07:09 | 200, 6 382 044 B, 30 341 rows |
| 12 | `https://bfppub.z5.web.core.windows.net/2026-08-13/…/quadkey=123121312/part-00106-110f5303-….csv.gz` | 07:10–07:45 | 200, 102 739 126 B, identical campus content |
| 13 | `https://github.com/microsoft/GlobalMLBuildingFootprints` | 07:09 | 200, 1.9k stars, CDLA-Permissive-2.0 |
| 14 | `https://raw.githubusercontent.com/microsoft/GlobalMLBuildingFootprints/main/README.md` | 07:09 | 200, 20 819 B, full changelog |
| 15 | `https://storage.googleapis.com/storage/v1/b/open-buildings-data/o?prefix=v3/polygons_s2_level_4_gzip/` | 06:54 | 200, 333 files, 178.3 GB |
| 16 | `https://storage.googleapis.com/storage/v1/b/open-buildings-data/o?prefix=v3/&delimiter=/` | 07:02 | 200, 6 prefixes |
| 17 | `https://storage.googleapis.com/storage/v1/b/open-buildings-data/o/v3%2Fpolygons_s2_level_6_gzip_no_header%2F390d_buildings.csv.gz` | 07:02 | 200, 1 299 923 274 B, updated 2023-06-23 |
| 18 | `https://storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_6_gzip_no_header/390d_buildings.csv.gz` | 07:04–07:12 | 200, streamed + filtered, 3 044 rows kept |
| 19 | `https://sites.research.google/gr/open-buildings/` | 07:02 | 200, v3 / May 2023 / 1.8 B / CC BY 4.0 or ODbL |
| 20 | `https://sites.research.google/gr/open-buildings/temporal/` | 07:02 | 200, bands, 1.5 m MAE caveat, licence |
| 21 | `https://storage.googleapis.com/storage/v1/b/open-buildings-temporal-data/o?prefix=v1/&delimiter=/` | 07:03 | 200, `geotiffs/` + `manifests/` |
| 22 | `https://storage.googleapis.com/open-buildings-temporal-data/v1/manifests/39_EPSG_32643_2023_06_30.json` | 07:07 | 200, 3 076 541 B, 8 312 tiles |
| 23 | `https://storage.googleapis.com/storage/v1/b/open-buildings-temporal-data/o?prefix=v1/geotiffs/390cc_2023_06_30/` | 07:04 | 200, tile sizes 270 MB – 1.23 GB |
| 24 | `https://docs.overturemaps.org/guides/buildings/` | 07:11 | 200, release 2026-08-19.0, ODbL, S3/Azure paths |
| 25 | `https://docs.overturemaps.org/attribution/` | 07:11 | 200, per-theme attribution strings |
| 26 | `https://docs.overturemaps.org/release/latest/` | 07:10 | **404 — UNVERIFIED**, superseded by #24 |
| 27 | `https://tiles.maps.eox.at/wmts/1.0.0/WMTSCapabilities.xml` | 07:11 | 200, 67 911 B, per-year licences |
| 28 | `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-{2020,2023,2024}_3857/default/GoogleMapsCompatible/…` | 07:10 | 200 ×4, real JPEGs |
| 29 | `https://s2maps.eu/` and `/about` | 07:10 | 301 → `cloudless.eox.at/preview`, commercial page, no per-year licence — **UNVERIFIED**; superseded by #27 |
| 30 | `https://tile.openstreetmap.org/17/93779/54692.png` | 07:10 | 200, 19 111 B (reference only, no bulk use) |
| 31 | `https://www.openstreetmap.org/copyright` | 07:09 | 200, ODbL + attribution duty |
| 32 | `https://osmfoundation.org/wiki/Licence/Attribution_Guidelines` | 07:10 | 200, app/splash rules, page last edited 2022-03-16 |
| 33 | `https://maplibre.org/maplibre-style-spec/layers/` | 07:12 | 200, fill-extrusion + symbol properties |

**Marked UNVERIFIED**: #8 (Esri master agreement index page — the PDFs behind it were not
opened; the clause quotes in §3.4 come from #7 and #5/#6, which were fetched and parsed),
#26 (404), #29 (redirect to a commercial page with no licence text), and the canopy-height
products in §4.2 (not fetched at all).
