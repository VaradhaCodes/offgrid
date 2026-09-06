# R6 — Implementation stack for a premium, fully offline map/navigation screen
### Android · Jetpack Compose · MapLibre · Samsung Galaxy S23 Ultra · Android 16

**Workstream:** R6 (map/UI stack)
**Author:** navigation-systems research agent
**All facts below were fetched on 2026-09-05** unless a different date is stated next to the item.
**Verification rule used:** every version number, URL, size and licence in this document came from a
page or artifact fetched during this review. Anything that could not be fetched is explicitly
marked `UNVERIFIED`. Numbers marked **[measured]** were produced by running code in this review
against the live service, not copied from documentation.

---

## 0. Executive summary — the recommended stack

| Layer | Choice | Exact version | Verified from |
|---|---|---|---|
| Map renderer | `org.maplibre.gl:android-sdk-vulkan-opengl` | **13.6.0** (released 2026-08-28) | Maven Central metadata + GitHub release |
| Map integration | `androidx.compose.ui.viewinterop.AndroidView` wrapping `org.maplibre.android.maps.MapView` | Compose UI 1.12.0 | Compose BOM 2026.08.00 POM |
| **Not** maplibre-compose | `org.maplibre.compose:maplibre-compose:0.15.0` — **blocked**, see §3 | 0.15.0 | its own POM (Kotlin 2.4.10) |
| Basemap data | Protomaps planet PMTiles → `pmtiles extract` → local `.pmtiles` in `filesDir` | daily build `20260904.pmtiles` | live header read **[measured]** |
| Basemap style | Protomaps v4 **dark** flavour, edited to point at `pmtiles://file://` | style@4.4.0 / `@protomaps/basemaps` npm 5.7.2 | live style JSON |
| Glyphs / sprites | `protomaps/basemaps-assets`, bundled in `src/main/assets` | repo pushed 2025-10-31 | GitHub API + live PBF sizes **[measured]** |
| Satellite | **Not** Esri offline (terms forbid). Ship a small self-captured/permitted raster PMTiles, or drop the toggle | — | Esri E300 (2025-11-13) + item `licenseInfo` |
| Compose | `androidx.compose:compose-bom` | **2026.08.00** → UI/foundation/runtime/animation **1.12.0**, material3 **1.4.0** | Google Maven POM |
| Activity / lifecycle | `androidx.activity:activity-compose:1.13.0`, `androidx.lifecycle:lifecycle-runtime-compose:2.11.0` | stable | Google Maven metadata |
| Borrowed camera/route recipes | Stadia Maps **Ferrostar 0.54.0** (BSD-3-Clause) — copy numbers, do not depend on it | 0.54.0 (2026-08-18) | GitHub + Maven |

**Two decisions the lead must make** — see §11.

---

## 1. Environment reconciliation (what the team already has vs what the libraries want)

Team environment as stated in the brief: Kotlin 2.2.10, AGP 8.13.2, Gradle 8.14.3, compileSdk 36,
JDK 21, no Android Studio, Samsung Galaxy S23 Ultra (Snapdragon 8 Gen 2, **Adreno 740**), Android 16.

Verified facts that interact with this:

- **AGP 8.13.2 is the newest AGP 8.x on Google Maven** (metadata fetched 2026-09-05: `8.13.0-alpha01 … 8.13.0 … 8.13.1 … 8.13.2`). Good — the team is current on the 8.x line.
- **MapLibre Native Android 13.6.0** is the newest `org.maplibre.gl:android-sdk` (`<lastUpdated>20260828132607</lastUpdated>`; GitHub tag `android-v13.6.0` published 2026-08-28T13:38:55Z). It is a plain AAR with no Kotlin-metadata forward-compat problem.
- **maplibre-compose 0.15.0** is built with **Kotlin 2.4.10**, **AGP 9.1.1**, **JDK 25 toolchain**, **compileSdk 37** (read from `gradle/libs.versions.toml` at tag `v0.15.0`). This is two Kotlin minors ahead of the team. See §3 — this is a hard blocker, not a preference.

---

## 2. MapLibre Native Android 13.x — the API as it actually stands

### 2.1 Artifacts, rendering backend, and the Adreno risk

From `platform/android/docs/data/rendering-engine.md` (fetched from `main`, 2026-09-05):

| Artifact | Backend | AAR size at 13.6.0 **[measured]** |
|---|---|---|
| `org.maplibre.gl:android-sdk` | **Vulkan (current default)** | 18,447,674 B (17.6 MiB) |
| `org.maplibre.gl:android-sdk-opengl` | OpenGL ES | 15,594,913 B (14.9 MiB) |
| `org.maplibre.gl:android-sdk-vulkan` | Vulkan | 18,447,674 B (identical bytes to `android-sdk`) |
| `org.maplibre.gl:android-sdk-vulkan-opengl` | both, chosen at runtime | 33,176,114 B (31.6 MiB) |

(Sizes read from `Content-Length` on `repo1.maven.org` for each `*-13.6.0.aar`.)

**13.0.0 was a breaking change:** "Use Vulkan as rendering backend for the `org.maplibre.gl:android-sdk` package. You can still use OpenGL ES with the `org.maplibre.gl:android-sdk-opengl` package." (Android CHANGELOG.)

Backend selection API:
```java
MapLibre.getInstance(context, apiKey, tileServer, RenderingEngine.Type.VULKAN); // explicit
MapLibre.getInstance(context);                                                  // auto-detect
RenderingEngine.Type active = RenderingEngine.getCurrentType();
```
Auto-detect picks Vulkan on API 24+ when `PackageManager.FEATURE_VULKAN_HARDWARE_VERSION` is reported. The backend is fixed for the process lifetime after the first `getInstance()`.

**Adreno risk (relevant to the S23 Ultra).** Merged PR #4442 (2026-08-12, shipped in 13.5.0):
"fix(android): Workaround for Adreno `VK_ERROR_DEVICE_LOST`" — body: "When using the specialized
location indicator on Adreno 600 series GPUs with the Vulkan backend, the driver can sporadically
trigger a device lost error (GPU hang/driver crash)." Related open/recent Vulkan issues found via
GitHub search: #4506 (open, 2026-08-26, Vulkan colour banding on PowerVR), #4491 (closed
2026-08-18, "Android/Vulkan: any custom layer crashes with SIGSEGV (null renderPass) since 13.5.0 —
regression").

**Recommendation:** ship `org.maplibre.gl:android-sdk-vulkan-opengl:13.6.0` (+~16 MiB APK vs the
OpenGL-only AAR) so a demo-day GPU fault can be recovered by forcing
`RenderingEngine.Type.OPENGL` in a debug switch, without a rebuild. If APK size matters more than
insurance, use `android-sdk-opengl:13.6.0` — OpenGL is the "longest track record" path per MapLibre's
own comparison table and the 2 km² campus scene is nowhere near GPU-bound.

### 2.2 Package names (API docs are published at 13.4.1 as of today)

`https://maplibre.org/maplibre-native/android/api/` states "Version: 13.4.1 (openglRelease)" — the
published KDoc lags the Maven release by two patch versions. Top-level packages:

```
org.maplibre.android                     org.maplibre.android.location
org.maplibre.android.annotations         org.maplibre.android.location.engine   (LocationEngine…)
org.maplibre.android.attribution         org.maplibre.android.location.modes    (CameraMode, RenderMode)
org.maplibre.android.camera              org.maplibre.android.location.permissions
org.maplibre.android.constants           org.maplibre.android.log
org.maplibre.android.exceptions          org.maplibre.android.maps
org.maplibre.android.geometry            org.maplibre.android.module.http
org.maplibre.android.http                org.maplibre.android.module.loader
org.maplibre.android.net                 org.maplibre.android.offline
org.maplibre.android.snapshotter         org.maplibre.android.storage
org.maplibre.android.style.expressions   org.maplibre.android.style.layers
org.maplibre.android.style.light         org.maplibre.android.style.sources
org.maplibre.android.text                org.maplibre.android.util / .utils
```

Layer classes present in `org.maplibre.android.style.layers` (read from the source tree on `main`):
`BackgroundLayer, CircleLayer, ColorReliefLayer, CustomLayer, FillExtrusionLayer, FillLayer,
HeatmapLayer, HillshadeLayer, LineLayer, RasterLayer, SymbolLayer` plus `Property`,
`PropertyFactory`, `TransitionOptions`. **There is no public `LocationIndicatorLayer` on Android** —
the native puck is reached through `LocationComponentActivationOptions.useSpecializedLocationLayer(true)`
(see §2.5).

### 2.3 Compose integration: `AndroidView` (recommended) — exact shape

Google's `AndroidView` signature (fetched from developer.android.com, "Using Views in Compose"):

```kotlin
@Composable
fun AndroidView(
    factory: (Context) -> View,
    modifier: Modifier = Modifier,
    update: (View) -> Unit = {},
    onReset: ((View) -> Unit)? = null,   // 1.4.0+
    onRelease: ((View) -> Unit)? = null
)
```

Guidance that matters for a 60 fps map screen:
- `factory` runs **once**; `update` runs on first inflate and **whenever a `State` read inside it changes**.
- Therefore **do not read the 10 Hz pose `State` inside `update`** — that recomposes `AndroidView` 10×/s for nothing. Push the pose into the map from a `LaunchedEffect` collecting a `Flow`, or from a plain callback holding the `MapLibreMap` reference. Only put slow-changing things (style id, satellite on/off) in `update`.
- `onReset` only matters for lazy lists (view recycling); irrelevant here.
- `onRelease` is where you call `mapView.onDestroy()`.
- Google's own words: "Use `AndroidView` as a wrapper only for missing SDK components without Compose support."  A map renderer is exactly that case.
- `MapView` lifecycle must still be pumped manually: `onCreate/onStart/onResume/onPause/onStop/onLowMemory/onDestroy/onSaveInstanceState` (see the MapLibre quickstart). Wire these from a `DisposableEffect(lifecycleOwner)`.

Frame-rate levers that exist on the SDK itself:
- `MapView.setMaximumFps(int)` — throttles the whole map (gestures + animations). Must be called after the renderer exists or it throws `IllegalStateException("Calling MapView#setMaximumFps before mapRenderer is created.")`.
- `MapView.setRenderingRefreshMode(MapRenderer.RenderingRefreshMode)`.
- `LocationComponent.setMaxAnimationFps(int)` — throttles only the puck animator. The KDoc's own worked example ramps `3 → 5 → 7 → 15 → Integer.MAX_VALUE` as zoom crosses 10/15/18. At our zoom (≥16) leave it unthrottled.

### 2.4 The 10 Hz update path: `GeoJsonSource` throughput

`org.maplibre.android.style.sources.GeoJsonSource` (Kotlin, on `main`) exposes four setters:

```kotlin
fun setGeoJson(feature: Feature?)
fun setGeoJson(geometry: Geometry?)
fun setGeoJson(featureCollection: FeatureCollection?)
fun setGeoJson(json: String)          // raw FeatureCollection string
```

All four carry the same KDoc: *"The update is performed synchronously or asynchronously, based on
the source synchronous update flag. In the case of asynchronous updates, the data won't be
immediately visible or available to query when this method returns."* All call `checkThread()` —
**they must be called on the main thread**.

Two important details:
- `setGeoJson(FeatureCollection)` **copies the feature list** (`ArrayList(features)` then
  `FeatureCollection.fromFeatures(...)`) before crossing JNI. `setGeoJson(String)` goes straight to
  `nativeSetGeoJsonString`. For a growing breadcrumb trail at 10 Hz, prefer keeping one
  `LineString` and calling `setGeoJson(geometry)`, or hand a pre-serialised string.
- **`GeoJsonSource.setOverrideSynchronousUpdate(Boolean)`** was added in 13.5.0
  ("Android: setOverrideSynchronousUpdate for existing sources", PR #4366). KDoc: *"Overrides the
  synchronous update flag for this source at runtime. This is equivalent to constructing the source
  with `GeoJsonOptions.withSynchronousUpdate`, but can be applied to existing sources loaded from a
  style JSON."* Use this on the route/trail source so an update is visible on the very next frame —
  otherwise the trail lags the puck by a frame or two, which reads as jitter on video.

`GeoJsonOptions` builder (defaults from the KDoc): `withMinZoom` (default 0), `withMaxZoom`
(default **25.5**), `withBuffer` (default **128**, in 1/512ths of a tile), `withTolerance`
(Douglas-Peucker, default **0.375**), `withLineMetrics`, `withCluster` (default false),
`withClusterMaxZoom`, `withClusterRadius`, plus `withSynchronousUpdate`.

For a trail that grows over a 2 km ride at 10 Hz you will accumulate ~12,000 points in 20 minutes.
**Decimate before you push**: keep a full-rate array in the ViewModel but only push points that are
>1 m from the previous pushed point, or push a fixed-length sliding window plus a decimated tail.
Re-tessellating a 12k-vertex LineString 10×/s is the one thing on this screen that can actually
cost frames.

MapLibre's own worked example of exactly this pattern is
`platform/android/.../activity/style/RealTimeGeoJsonActivity.kt` (it refreshes a `GeoJsonSource`
from a `Handler`/`Looper` `Runnable` and sets `PropertyFactory.iconRotate(...)` from the last two
points). It runs at 2 s intervals in the demo; the mechanism is identical at 100 ms.

### 2.5 Moving the puck smoothly: `LocationComponent` vs a custom symbol layer

**Use `LocationComponent` with a null `LocationEngine` and `forceLocationUpdate()`.** This is the
single highest-leverage finding in this workstream, because MapLibre already implements the
interpolation you would otherwise hand-roll.

Verified from `LocationAnimatorCoordinator.java` on `main`:

```java
animationDuration = (long) ((locationUpdateTimestamp - previousUpdateTimeStamp) * durationMultiplier)
    /* make animation slightly longer with durationMultiplier, defaults to 1.1f */;
...
animationDuration = Math.min(animationDuration, MAX_ANIMATION_DURATION_MS);
```

So the puck **linearly interpolates between the last two pushed fixes over (Δt × 1.1)**, clamped to
`MAX_ANIMATION_DURATION_MS = 2000`. Push at 10 Hz → each fix animates over **110 ms**, i.e. the puck
is continuously moving and never steps. Constants from `LocationComponentConstants.java`:

| Constant | Value |
|---|---|
| `TRANSITION_ANIMATION_DURATION_MS` | 750 ms |
| `MAX_ANIMATION_DURATION_MS` | 2000 ms |
| `ACCURACY_RADIUS_ANIMATION_DURATION` | 250 ms |
| `DEFAULT_TRACKING_ZOOM_ANIM_DURATION` | 750 ms |
| `DEFAULT_TRACKING_PADDING_ANIM_DURATION` | 750 ms |
| `DEFAULT_TRACKING_TILT_ANIM_DURATION` | 1250 ms |
| `INSTANT_LOCATION_TRANSITION_THRESHOLD` | 50 000 (jump instead of animate beyond this) |
| `COMPASS_UPDATE_RATE_MS` | 500 ms |
| default `trackingAnimationDurationMultiplier` | **1.1f** |

Activation with our own estimator driving it (pattern from `ManualLocationUpdatesActivity.kt`):

```kotlin
val lc = map.locationComponent
lc.activateLocationComponent(
    LocationComponentActivationOptions.builder(context, style)
        .locationComponentOptions(
            LocationComponentOptions.builder(context)
                .pulseEnabled(true)
                .pulseColor(accent)
                .foregroundTintColor(accent)
                .elevation(4f)
                .trackingAnimationDurationMultiplier(1.1f)
                .layerBelow("road-label")       // keep the puck under labels
                .build()
        )
        .useDefaultLocationEngine(false)        // -> locationEngine == null
        .useSpecializedLocationLayer(true)      // native indicator, correct under pitch
        .build()
)
lc.isLocationComponentEnabled = true
lc.renderMode = RenderMode.GPS                 // bearing from Location.getBearing()
lc.cameraMode = CameraMode.TRACKING_GPS        // course-up
// ...then, at 10 Hz, on the main thread:
lc.forceLocationUpdate(location)               // location.bearing = our course estimate
```

Key API facts (all read from `LocationComponent.java` on `main`):
- `setLocationEngine(null)` → *"all updates will have to occur through the
  `LocationComponent#forceLocationUpdate(Location)` method."*
- `forceLocationUpdate(List<Location>, boolean lookAheadUpdate)` also exists — the look-ahead form
  lets you push a short predicted trajectory so the animator has a target ahead of "now". Worth a
  try if the 110 ms interpolation still reads as slightly behind on video.
- `CameraMode` constants: `NONE(0x08) NONE_COMPASS(0x10) NONE_GPS(0x16) TRACKING(0x18)
  TRACKING_COMPASS(0x20) TRACKING_GPS(0x22) TRACKING_GPS_NORTH(0x24)`.
- `RenderMode` constants: `NORMAL(0x12) COMPASS(0x04) GPS(0x08)`.
- **Puck-in-the-lower-third** is `paddingWhileTracking(double[] padding, long animationDuration, callback)` (750 ms default) — not `MapLibreMap.setPadding`, which fights the tracking controller. There is also `zoomWhileTracking(zoom, durationMs, cb)` and `tiltWhileTracking(tilt, durationMs, cb)`; use these for **speed-scaled zoom** instead of issuing `animateCamera` yourself. `cancelZoomWhileTrackingAnimation()`, `cancelTiltWhileTrackingAnimation()`, `cancelPaddingWhileTrackingAnimation()` exist for gesture hand-off.
- `setCameraMode(int mode, long transitionDuration, Double zoom, Double bearing, Double tilt, OnLocationCameraTransitionListener)` sets everything atomically on mode entry.
- `LocationComponentOptions.Builder` setters that matter for a premium look:
  `foregroundDrawable/backgroundDrawable/bearingDrawable` (+`*TintColor`), `elevation`,
  `accuracyColor/accuracyAlpha` (default alpha **0.15f**), `pulseEnabled/pulseColor/pulseAlpha/
  pulseMaxRadius` (default **35f**) `/pulseSingleDuration` (default **2300 ms**) `/pulseInterpolator/
  pulseFadeEnabled`, `minZoomIconScale` (default **0.6f**) / `maxZoomIconScale` (default **1f**),
  `layerAbove` / `layerBelow`, `enableStaleState` / `staleStateTimeout` (default **30 000 ms** — turn
  this **off**, our estimator is not "stale" in the GPS sense), `trackingGesturesManagement`,
  `trackingInitialMoveThreshold`, `trackingMultiFingerMoveThreshold`,
  `trackingMultiFingerProtectedMoveArea`, `bearingOnTop`, `compassAnimationEnabled`, `padding`.
- Internal layer ids you can anchor against: `mapbox-location-shadow-layer`,
  `mapbox-location-background-layer`, `mapbox-location-foreground-layer`,
  `mapbox-location-accuracy-layer`, `mapbox-location-bearing-layer`,
  `mapbox-location-pulsing-circle-layer`; source id `mapbox-location-source` (names kept from the
  Mapbox fork).

**When to use a custom `SymbolLayer` instead:** only if you need a puck shape MapLibre cannot draw
(e.g. a bicycle glyph that tilts with the map). Then use
`PropertyFactory.iconRotate(...)` + `iconRotationAlignment(Property.ICON_ROTATION_ALIGNMENT_MAP)` +
`iconPitchAlignment(...)` and drive it from a `GeoJsonSource` — but you then own the interpolation,
and you lose `paddingWhileTracking`/`zoomWhileTracking`. **Do not do this for the demo.**

### 2.6 Camera API

`MapLibreMap` (Java, on `main`):
```java
public final void moveCamera(CameraUpdate update)                 // jump
public final void easeCamera(CameraUpdate update)                 // constant ground speed
public final void easeCamera(CameraUpdate update, int durationMs)
public final void easeCamera(CameraUpdate update, int durationMs, boolean easingInterpolator)
public final void animateCamera(CameraUpdate update)              // Van Wijk & Nuij flight
public final void animateCamera(CameraUpdate update, int durationMs)
public void setPadding(int left, int top, int right, int bottom)
```
The `animateCamera` "powered flight" is documented as an implementation of
Van Wijk & Nuij, *"Smooth and efficient zooming and panning"*, INFOVIS '03, pp. 15–22 — this is the
right citation if the judges ask why the camera feels like Google Maps.

`CameraUpdateFactory` (Kotlin, `@JvmStatic`): `newCameraPosition`, `newLatLng`, `newLatLngBounds`
(×4 overloads incl. one taking `bearing`/`tilt`/per-edge padding), `newLatLngZoom`,
**`newLatLngPadding(latLng, left, top, right, bottom)`**, `zoomBy`, `zoomIn`, `zoomOut`, `zoomTo`,
`bearingTo`, `tiltTo`.

`CameraPosition.Builder`: `target`, `zoom`, `bearing`, `tilt`, **`roll`**, **`fov`**,
**`centerAltitude`**, `padding(left, top, right, bottom)` / `padding(double[4])`.
(`roll` arrived in 13.0.0: "core, android: add support for camera roll", PR #3011.)

Limits from `MapLibreConstants.java`: `MINIMUM_ZOOM = 0.0f`, `MAXIMUM_ZOOM = 25.5f`,
`MINIMUM_TILT = 0`, **`MAXIMUM_TILT = 60`**, `ANIMATION_DURATION = 300`,
`ANIMATION_DURATION_SHORT = 150`.

### 2.7 Tile-source URL schemes: what 13.x actually supports

From `platform/android/docs/data/PMTiles.md` (fetched from `main`):

> "Starting MapLibre Android 11.7.0, PMTiles archives are supported as tile sources. Prefix any tile
> source URL with `pmtiles://` to read from a PMTiles archive:
> - `pmtiles://https://` — stream tiles from a remote file
> - `pmtiles://file://` — read a file from device storage (use `getExternalFilesDir` or `filesDir` for the path)"

and:

> "The `pmtiles://` prefix works with any tile source type (e.g. `vector`, `raster`, `raster-dem`, etc.), from a style JSON or dynamically."

Three hard constraints, all quoted from that same page:

1. **`pmtiles://asset://` does NOT work.** *"`pmtiles://asset://` (files in `src/main/assets/`) is
   not currently supported. `AssetManagerFileSource` does not implement byte-range reads, which
   PMTiles requires to read its header and metadata. Use `file://` from device storage instead."*
   (tracking issue: maplibre/maplibre-native#4360). Confirmed in the C++: the Android
   `AssetManagerFileSource::Impl::request` does `AAssetManager_open(..., AASSET_MODE_BUFFER)` and
   returns the **whole** asset — no ranges.
   → **You must copy the `.pmtiles` out of `assets/` into `filesDir` on first launch.**
2. **Relative URLs are not resolved.** *"MapLibre Native requires the URL inside `pmtiles://` to be
   fully specified (e.g. `pmtiles://https://example.com/tiles.pmtiles`, not `pmtiles://tiles.pmtiles`)."*
3. **PMTiles sources are excluded from the offline pack system.** *"Note: PMTiles sources do not
   support offline pack downloads or caching."* (An **ambient** cache for PMTiles was added in 13.3.0
   — "Implement ambient cache for PMTiles sources", PR #4290 — but that is a runtime read cache, not
   an offline region.)

**`mbtiles://` does not exist.** There is no MBTiles scheme in MapLibre Native Android. Open issue
maplibre/maplibre-native#3559 "Load mbtiles from apk assets on Android" has been open since
2025-06-16; #2558 "Crash app when loading mbtiles" open since 2026-03-24. Using MBTiles on Android
requires you to run a local HTTP server in-process and serve `http://127.0.0.1:port/{z}/{x}/{y}`.
**Do not go down this road — PMTiles is the supported path.**

`asset://` **does** work for non-ranged resources: style JSON, glyph PBFs, sprite JSON/PNG, and
plain `{z}/{x}/{y}` tiles. `AssetManagerFileSource` strips the 8-character `asset://` prefix
(`url.substr(8)`) and percent-decodes the rest. So `"glyphs": "asset://fonts/{fontstack}/{range}.pbf"`
is valid, which is how we ship offline labels (§5).

Working reference code (verbatim from `PMTilesActivity.kt` on `main`):
```kotlin
val path = getExternalFilesDir(null)?.absolutePath + "/watercolor.pmtiles"
val source = RasterSource("watercolor", "pmtiles://file://$path", 256)
style.addSource(source)
style.addLayer(RasterLayer("watercolor", "watercolor"))
```
and for vector:
```kotlin
val src = VectorSource("overture-places", "pmtiles://https://…/places.pmtiles")
style.addSource(src)
val layer = CircleLayer("overture-layer", "overture-places")
layer.setSourceLayer("place")
```

Caveat carried in the same doc: *"`raster-dem` sources added programmatically cannot specify
`encoding` via the current Android API. Define `raster-dem` sources with terrarium encoding in the
style JSON instead."*

### 2.8 Open PMTiles defects to be aware of (and one famous false alarm)

Searched `repo:maplibre/maplibre-native pmtiles` (47 results) on 2026-09-05:

| # | State | Updated | Title / relevance |
|---|---|---|---|
| 4459 | **open** | 2026-08-04 | "Android: SIGSEGV (null deref) in `PMTilesFileSource` thread during normal map interaction" — reproduced on 13.2.0 opengl, Android 16 emulator, **two remote PMTiles sources still loading**. Mitigation for us: we use one **local** archive, fully present, so the racy remote-range path is not exercised. |
| 4462 | **open** | 2026-08-05 | "PMTiles: archives with `internal_compression = gzip` fail to load every tile ('incorrect header check')" — reported against **ios-v6.28.0**; only comment is a maintainer asking for a repro archive. **Counter-evidence for Android:** `https://demotiles.maplibre.org/pmtiles/raster/imagery.pmtiles` has `internal_compression=2 (gzip)` **[measured]** and is the archive MapLibre's own Android test app loads. Treat as iOS-specific but **smoke-test on device in week 1**. |
| 4421 | **open** | 2026-07-21 | "`PMTilesFileSource`: 'invalid map<K,T> key' on large archives — directory LRU evicts entries still in use". Reported against the **136 GB planet** archive. Another reason to ship a ~1 MB extract rather than stream the planet. |
| **4398** | **closed / invalid** | 2026-07-12 | "PMTiles archives produced by `pmtiles extract` do not render on Android (tiles silently empty)". **Read this one.** The reporter did deep instrumentation, then retracted: *"Retracting this — it is not a MapLibre bug… My 'blank' symptom was a self-inflicted data mismatch: the map snippet was centred on a location (Lisbon) that lay outside the geographic extent of the extract (which covered Florence)… `pmtiles extract` output works fine on maplibre-native Android."* **Mistake to avoid:** if your extract renders as background-only, check the camera is inside the extract bbox before blaming the encoder. |

### 2.9 The offline-pack API (why we are not using it)

`org.maplibre.android.offline.OfflineManager` (Kotlin, on `main`) exposes
`listOfflineRegions`, `getOfflineRegion`, `createOfflineRegion(definition, metadata, callback)`,
`mergeOfflineRegions(path, cb)`, `resetDatabase`, `packDatabase`, `invalidateAmbientCache`,
`clearAmbientCache`, `setMaximumAmbientCacheSize(size, cb)`, and the JNI externals
`setOfflineMapboxTileCountLimit(limit)` / `runPackDatabaseAutomatically(autopack)`.
Region definitions: `OfflineTilePyramidRegionDefinition(styleURL, LatLngBounds, minZoom, maxZoom,
pixelRatio [, includeIdeographs])` and `OfflineGeometryRegionDefinition`.

This machinery downloads a style's tiles/glyphs/sprites into an SQLite cache **over HTTP** — it is
the right tool when your tiles live on a server and you want them pinned before going offline. It is
the **wrong** tool for us because (a) PMTiles sources are explicitly excluded, and (b) we would need
a tile server at build time anyway. Ship the archive; skip offline packs. Mention them in the
architecture doc as "considered and rejected, with reason" — that reads well to judges.

### 2.10 Style-JSON features that carry the "premium" look

Fetched from `https://maplibre.org/maplibre-style-spec/layers/`:

**`fill-extrusion` (3D buildings)** — paint: `fill-extrusion-opacity` (number 0–1, default 1),
`fill-extrusion-color` (default `#000000`), `fill-extrusion-translate` (default `[0,0]`),
`fill-extrusion-translate-anchor` (`map`|`viewport`, default `map`), `fill-extrusion-pattern`,
**`fill-extrusion-height`** (metres, default 0), **`fill-extrusion-base`** (metres, default 0),
`fill-extrusion-vertical-gradient` (boolean, default **true**). Layout:
**`fill-extrusion-rounded-corner-distance`** (metres, default 0) — this is new in 13.4.0
("Add fill extrusion style property that enables rounded corners for extruded buildings", PR #4343)
and is a cheap, very visible premium touch on a dark basemap.

Kotlin recipe, verbatim from `BuildingFillExtrusionActivity.kt`:
```kotlin
val fillExtrusionLayer = FillExtrusionLayer("building-3d", "openmaptiles")
fillExtrusionLayer.sourceLayer = "building"
fillExtrusionLayer.setFilter(
    Expression.all(Expression.has("render_height"), Expression.has("render_min_height"))
)
fillExtrusionLayer.minZoom = 15f
fillExtrusionLayer.setProperties(
    PropertyFactory.fillExtrusionColor(Color.LTGRAY),
    PropertyFactory.fillExtrusionHeight(Expression.get("render_height")),
    PropertyFactory.fillExtrusionBase(Expression.get("render_min_height")),
    PropertyFactory.fillExtrusionOpacity(0.9f)
)
style.addLayer(fillExtrusionLayer)
```
That example is for the **OpenMapTiles** schema (`render_height` / `render_min_height`). For the
**Protomaps v4** schema the source-layer is `buildings` and the attributes are **`height`** and
**`min_height`** (Protomaps basemaps layer docs: buildings "contains `height` and `min_height` as
number values, though may be quantized at low zoom levels"; merged buildings z0–14, individual OSM
buildings z15+). So:
```kotlin
FillExtrusionLayer("buildings-3d", "protomaps").apply {
    sourceLayer = "buildings"
    minZoom = 15f
    setProperties(
        PropertyFactory.fillExtrusionColor("#1b1e24"),
        PropertyFactory.fillExtrusionHeight(Expression.get("height")),
        PropertyFactory.fillExtrusionBase(Expression.get("min_height")),
        PropertyFactory.fillExtrusionOpacity(0.92f),
        PropertyFactory.fillExtrusionVerticalGradient(true)
    )
}
```

**Lighting.** `style.light` is an `org.maplibre.android.style.light.Light`:
```kotlin
light.position = Position(1.15f, 210f, 30f)          // radial, azimuthal, polar
light.setColor(ColorUtils.colorToRgbaString(Color.BLUE))
light.anchor = Property.ANCHOR_MAP                    // or ANCHOR_VIEWPORT
light.intensity = 0.35f                               // 1.0f default in the sample
```
A cool low-intensity light anchored to the **map** gives buildings a consistent shadow side as the
camera rotates course-up — that is what makes a dark 3D basemap look expensive rather than flat.

**Line casing recipe.** `line-width` (default 1), `line-gap-width` (default 0), `line-blur`
(default 0), `line-dasharray`; layout `line-cap` (`butt`|`round`|`square`, default `butt`),
`line-join` (`bevel`|`round`|`miter`, default `miter`). The standard casing is two layers on one
source: a wider dark/light line **below** and the fill **above**. The Protomaps dark style already
does this — it ships 39 road layers including explicit `roads_minor_casing`,
`roads_major_casing_early`, `roads_major_casing_late`, `roads_highway_casing_early/late`,
`roads_bridges_*_casing`, `roads_tunnels_*_casing`. Copy the pattern rather than inventing one.

**Symbol labels.** `text-font` is an array with the spec default
`["Open Sans Regular","Arial Unicode MS Regular"]`; `text-field`, `text-halo-color`,
`text-halo-width` (px), `icon-rotate` (deg, default 0), `icon-rotation-alignment`
(`map`|`viewport`|`auto`, default `auto`), `icon-pitch-alignment` (same, default `auto`).
`symbol-rotate` is not a spec property — the rotation properties are `icon-rotate` and `text-rotate`.

**The glyph requirement is the offline trap.** Any layer with `text-field` forces MapLibre to fetch
`{glyphs}` PBFs for every `text-font` stack it encounters. With no network and no local glyphs, you
get a map with **zero labels and no error** — exactly the failure mode described in the closed issue
#4443 ("iOS: symbol-heavy style renders completely blank … when glyphs points at …"). §5 solves it.

---

## 3. `org.maplibre.compose:maplibre-compose:0.15.0` — assessed, and rejected for this project

**Repository state (GitHub API, 2026-09-05):** `maplibre/maplibre-compose`, **564 stars**,
`pushed_at 2026-09-05T06:38:00Z` (actively developed today), licence **BSD-3-Clause**,
979 commits on `main`. Releases: **v0.15.0 (2026-08-25)**, v0.14.0 (2026-08-08), v0.13.1
(2026-07-22), v0.13.0 (2026-05-20). Maven Central `<latest>0.15.0</latest>`,
`<lastUpdated>20260825235406</lastUpdated>`.

Stability per its own README: **Android Beta, iOS Beta, Desktop Alpha, Web Alpha**, and
*"The public API is still evolving, and minor releases can contain breaking changes."*

**Capabilities are genuinely good** (all read from the tagged `v0.15.0` doc snippets):

- Style: `MaplibreMap(baseStyle = BaseStyle.Uri("…"))`, including `Res.getUri("files/style.json")` for a bundled style.
- Layers/sources: `rememberGeoJsonSource(GeoJsonData.Uri | GeoJsonData.JsonString)`, `getBaseSource(id)`, `LineLayer`, `CircleLayer`, `Anchor`, and a typed expression DSL (`const`, `interpolate`, `exponential`, `zoom`, `LineCap`, `LineJoin`).
- Camera: `rememberCameraState(firstPosition = CameraPosition(target = Position(lat, lon), zoom = 13.0))`, `camera.animateTo(finalPosition = …, duration = 3.seconds)`, `camera.animateTo(boundingBox = …, padding = PaddingValues(32.dp))`, `camera.viewport.visibleBoundingBox`, `screenLocationFromPosition` / `positionFromScreenLocation`.
- Puck: `LocationPuck(idPrefix, location = locationState.location, bearing = locationState.mostAccurateBearing(), cameraState = cameraState)` with `rememberLocationState(provider, orientationProvider)` — **and `location` is a parameter**, so feeding a custom estimator is a first-class use case.
- Offline: `rememberOfflineManager()`, `OfflinePackDefinition.TilePyramid(styleUrl, bounds, minZoom, maxZoom)`, `offlineManager.create/resume/delete`, `DownloadProgress.{Healthy, Error, TileLimitExceeded, Unknown}`.
- Fill-extrusion: **UNVERIFIED** — a `FillExtrusionLayer` composable is not shown in the doc snippets I fetched; the layer list in `Layers.kt` covers `CircleLayer` and `LineLayer` only. The library tracks `@maplibre/maplibre-gl-style-spec` **26.3.0** and runs a `ci/style_spec_parity.py` check, so it is very likely present — but I did not verify it and will not claim it.

**Why it is blocked for this team.** From `gradle/libs.versions.toml` **at tag `v0.15.0`**:

```toml
android-compileSdk = "37"
android-minSdk     = "24"
android-targetSdk  = "36"
java-toolchain     = "25"
gradle-compose     = "1.12.0"
gradle-kotlin      = "2.4.10"
gradle-android     = "9.1.1"
```

And from `maplibre-compose-android-0.15.0.pom`:
`org.jetbrains.kotlin:kotlin-stdlib:2.4.10`, `org.jetbrains.compose.foundation:foundation-android:1.12.0`,
`org.maplibre.nativeffi:maplibre-native-ffi-android:0.202608.3`, `org.maplibre.spatialk:geojson-jvm:0.7.0`,
`kotlinx-coroutines 1.11.0`, `kermit 2.1.0`.

Two independent problems:

1. **Kotlin metadata.** The team compiles with Kotlin **2.2.10**; the library's classes carry Kotlin
   **2.4** metadata. Kotlin's own evolution policy (kotlinlang.org/docs/kotlin-evolution-principles.html,
   fetched 2026-09-05) states: *"All binaries are backwards compatible; that means a newer compiler
   can read older binaries"* and only *"Preferably (but we can't guarantee it), the binary format is
   mostly forwards compatible with the next language release, but not later ones."* 2.2 → 2.4 is two
   releases, i.e. explicitly outside even the best-effort window.
2. **Architecture change.** 0.13.1 depended on `org.maplibre.gl:android-sdk:13.0.2`. **0.15.0 does
   not** — it depends on `org.maplibre.nativeffi:maplibre-native-ffi-android:0.202608.3`, a new FFI
   binding, plus Compose Multiplatform 1.12.0 rather than plain AndroidX Compose. That is a second,
   parallel native stack in the APK, and it means everything you learn from the MapLibre Android
   docs/test app does not transfer 1:1.

**Fallback if the lead insists on Compose-native map code:** `maplibre-compose 0.13.1` (2026-07-22)
is compiled with Kotlin **2.3.21** — one minor ahead of 2.2.10, so inside the "preferably forwards
compatible with the next language release" window — and it still wraps `org.maplibre.gl:android-sdk`.
That is what **Ferrostar 0.54.0 ships against** (`maplibre-compose-android:0.13.0`, Kotlin BOM
2.3.20, Compose BOM 2026.02.01). It would still require bumping the project's Kotlin to at least
2.3.x to be safe. **Recommendation: don't. Use `AndroidView` + the plain SDK.** You lose nothing
that matters for one screen, and you gain `paddingWhileTracking`/`tiltWhileTracking`/
`forceLocationUpdate` which are the exact APIs this demo needs.

Artifacts published under `org.maplibre.compose` (Maven Central directory listing, for reference):
`maplibre-compose`, `-android`, `-desktop`, `-js`, `-jvm`, `-gms`, `-material3`,
`maplibre-compose-runtime-vulkan-android`, `maplibre-compose-runtime-opengl-android`,
`location`, `location-android`, `location-runtime-gms`, `location-runtime-hms`, `maplibre-js-bindings`.
Note the **runtime artifact is separate** — `implementation("org.maplibre.compose:maplibre-compose:0.15.0")`
alone will not render; you also need `maplibre-compose-runtime-vulkan-android:0.15.0` (or the opengl one).

---

## 4. A premium offline vector basemap for the 2 km × 2 km campus

Target bbox (from the brief): **W 77.5639, S 28.5133, E 77.5823, N 28.5335** (Shiv Nadar
University, Greater Noida).

### 4.1 Measured: Protomaps daily planet → `pmtiles extract`

I could not install the `pmtiles` binary in this sandbox (GitHub release assets on
`release-assets.githubusercontent.com` are blocked — `curl` exit 35, connection reset), so I wrote a
PMTiles v3 reader in Python and ran it against the **live** planet archive over HTTP range requests.
The numbers below are therefore direct measurements of what `pmtiles extract` will produce, not
estimates.

**Daily build availability probe** (HTTP `HEAD` on `https://build.protomaps.com/YYYYMMDD.pmtiles`):
`20260904` → 200, `20260903` → 404, `20260901` → 200, `20260828` → 404. Builds are not strictly
daily; check before scripting.

**Header of `https://build.protomaps.com/20260904.pmtiles` [measured]:**

```
root_dir      = offset 127, 15,556 bytes (2,917 entries)
leaf_dirs     = offset 137,384,631,024, 351,561,186 bytes
tile_data     = offset 16,384, 137,384,613,461 bytes   (~128 GiB / 137.4 GB)
addressed_tiles = 1,431,655,765
tile_entries    =   177,515,226
tile_contents   =   135,616,831
clustered=1  internal_compression=gzip  tile_compression=gzip  tile_type=MVT  minzoom=0  maxzoom=15
```

**Extract size for the SNU bbox [measured]** (unique deduplicated tile blobs, all zooms from 0):

| maxzoom | tiles in bbox | unique blobs present | tile bytes | |
|---|---|---|---|---|
| 14 | 16 | 16 | 807,053 B | **0.77 MiB** |
| **15** | **22** | **22** | **827,431 B** | **0.79 MiB** |

Only **8 leaf directories** had to be read to resolve all 22 tiles, so the extract is fast (seconds,
not minutes). Adding root directory + JSON metadata + PMTiles header, the output file will land at
roughly **0.85 MB**. That is small enough to ship inside the APK.

**Exact commands.** Install `go-pmtiles` (BSD-3-Clause, 591 stars, latest **v1.31.2**, released
2026-07-22; repo `pushed_at 2026-07-22`):

```bash
# macOS arm64
curl -L -o pmtiles.zip \
  https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles-1.31.2_Darwin_arm64.zip
unzip pmtiles.zip && chmod +x pmtiles
# (or: brew install pmtiles)

# Cut the campus straight out of the daily planet over HTTP range requests.
./pmtiles extract \
  https://build.protomaps.com/20260904.pmtiles \
  snu_campus.pmtiles \
  --bbox=77.5639,28.5133,77.5823,28.5335 \
  --maxzoom=15 \
  --download-threads=8

# Sanity-check before you ship it.
./pmtiles show snu_campus.pmtiles --header-json
./pmtiles show snu_campus.pmtiles --metadata
./pmtiles verify snu_campus.pmtiles
./pmtiles serve . --port=8080          # then open pmtiles.io or a local MapLibre GL JS page
```

Useful flags documented at `docs.protomaps.com/pmtiles/cli`: `--region=REGION.geojson` (Polygon /
MultiPolygon / Feature / FeatureCollection) if you want the corridor rather than a rectangle;
`--minzoom` (warns that partial sub-pyramids need more requests — leave it at 0);
`--overfetch` (e.g. `0.05` to batch small ranges, 5 % extra data); `--download-threads`.
Docs note: *"Extracting a full sub-pyramid from 0 to `maxzoom` is always an efficient operation that
makes minimal I/O or network requests."*

**Licence.** Protomaps basemaps are "distributed under the Open Database License as a Produced
Work", requiring OpenStreetMap attribution. The Protomaps daily build page also asks you not to
hotlink the planet — irrelevant for us since we extract once at build time. The
`protomaps/basemaps` repo itself is 727 stars, `pushed_at 2026-08-20`, licence `NOASSERTION`
(the styles are BSD-3-Clause via the npm package, see below).

**Zoom ceiling.** The Protomaps planet is z0–**15**. MapLibre overzooms z15 tiles up to whatever the
camera asks for, so a bicycle camera at z18 still renders crisp geometry from z15 data — this is
standard and is what every OSM vector basemap does. Only labels get sparse. Do **not** try to
generate z16+ yourself unless a judge asks.

### 4.2 Measured comparison: OpenFreeMap planet PMTiles (OpenMapTiles schema)

OpenFreeMap now publishes a planet **PMTiles** alongside its btrfs/mbtiles images. Index at
`https://btrfs.openfreemap.com/files.txt`; newest run at time of writing is
`areas/planet/20260830_080001_pt/tiles.pmtiles`.

**Header [measured]** — `Content-Length: 86,299,436,044` (86.3 GB), `accept-ranges: bytes`:
```
addressed_tiles=275,923,065  tile_entries=51,504,904  tile_contents=45,436,712
clustered=1  internal_compression=gzip  tile_compression=gzip  tile_type=MVT  minzoom=0  maxzoom=14
root dir 16,225 bytes / 3,501 entries
```
**Extract for the same SNU bbox [measured]: 16 tiles, 2,493,343 B = 2.38 MiB** (z0–14).

So OpenFreeMap's OpenMapTiles-schema extract is **3.0× larger** than Protomaps' and stops a zoom
level earlier. Its advantage is schema familiarity (`building.render_height`,
`building.render_min_height` — the exact attributes MapLibre's own `BuildingFillExtrusionActivity`
sample uses) and a ready-made **dark** style at `https://tiles.openfreemap.org/styles/dark`
(20,959 B, 47 layers, glyphs at `https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf`,
sprite `…/sprites/ofm_f384/ofm`). Its `building` layer is a flat `fill` (`rgb(10,10,10)`), minzoom
12 — you would still add your own `fill-extrusion` layer. OpenFreeMap repo: `hyperknot/openfreemap`,
**5.9k stars**, MIT.

### 4.3 Other options, checked and ranked

| Option | Verified state | Verdict |
|---|---|---|
| **Protomaps `pmtiles extract`** | 0.79 MiB, z0–15, ODbL, one command, no build machine cost | **Chosen** |
| OpenFreeMap planet pmtiles extract | 2.38 MiB, z0–14, MIT tooling / ODbL data | Fallback if you specifically want the OpenMapTiles schema |
| **Planetiler** (`onthegomap/planetiler`, 2,165 stars, Apache-2.0, latest **v0.10.2**, 2026-03-29) | `java -Xmx1g -jar planetiler.jar --download --area=monaco --output=data/output.pmtiles` — writes PMTiles directly; needs "at least 1GB of free SSD disk space plus 5-10x the size of the `.osm.pbf` file" | Only if you need a **custom schema** (e.g. bake your own campus footpaths). Costs an hour of build setup for a file we can get in 30 s. Team has JDK 21 already, so it is viable. |
| **VersaTiles** (`versatiles-org/versatiles-rs`, 317 stars, MIT, `pushed_at 2026-09-04`) | `versatiles convert --bbox-border 3 --bbox "…" https://download.versatiles.org/osm.versatiles out.versatiles`; also emits `.pmtiles`/`.mbtiles`. Style repo `versatiles-org/versatiles-style`, 109 stars, source **Unlicense**, sprites CC0-1.0; styles: colorful, **eclipse** (dark), graybeard, neutrino, shadow, satellite. Live: `https://tiles.versatiles.org/assets/styles/eclipse/style.json` → **200, 168,044 B, 324 layers**, glyphs `…/assets/glyphs/{fontstack}/{range}.pbf`, sprite `…/assets/sprites/basics/sprites`, tiles `…/tiles/osm/{z}/{x}/{y}`, **maxzoom 14**, Shortbread schema | Beautiful dark style, but Shortbread ≠ Protomaps ≠ OpenMapTiles, so the style is not portable, and maxzoom 14 is the weakest of the three. Keep as a look reference only. |
| **Render our own GeoJSON** (OSM roads/buildings we already have) | — | See §4.5 |

### 4.4 The style: Protomaps v4 dark, rewired for offline

Fetched live: `https://api.protomaps.com/styles/v4/dark/en.json?key=…` (the demo key that MapLibre's
own test app uses, `TestStyles.kt`).

```
"name": "style@4.4.0 theme@dark lang@en"      59,245 bytes, 67 layers
layer types: 41 line, 15 fill, 10 symbol, 1 background
background-color: #34373d
glyphs: https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf
sprite:  https://protomaps.github.io/basemaps-assets/sprites/v4/dark
source "protomaps": vector, maxzoom 15
source-layers used: boundaries, buildings, earth, landcover, landuse, places, pois, roads, water
font stacks: ["Noto Sans Regular"], ["Noto Sans Medium"], ["Noto Sans Italic"],
             and one data-driven case: min_zoom<=5 ? Medium : Regular
buildings layer today: { "type":"fill", "fill-color":"#111111", "fill-opacity":0.5 }   <- replace with fill-extrusion
```

npm package: `@protomaps/basemaps`, latest **5.7.2**, licence **BSD-3-Clause** (registry fetched
2026-09-05; `time.modified 2026-03-10`). API for building a style in JS:
`import { namedFlavor } from "@protomaps/basemaps"` then e.g.
`let flavor = {...namedFlavor("dark"), buildings:"red"}`. Flavours: **light, dark** (general purpose,
with icons) and **white, grayscale, black** (data-visualisation oriented). Each flavour ships a
spritesheet with townspots, highway shields and (light/dark only) POI icons.

**No Node on the build machine.** `node` and `npm` are not installed on this Mac (checked). You do
**not** need them: fetch the served style JSON once, then apply four edits by hand or with a 20-line
Python script:

```python
import json
s = json.load(open("pm_dark.json"))
s["sources"]["protomaps"] = {
    "type": "vector",
    "url": "pmtiles://file://__FILESDIR__/snu_campus.pmtiles",   # substituted at runtime
    "attribution": s["sources"]["protomaps"]["attribution"],
}
s["glyphs"] = "asset://fonts/{fontstack}/{range}.pbf"
s["sprite"] = "asset://sprites/dark"
# add the 3D buildings layer just above the flat one, then delete the flat one
json.dump(s, open("style_offline.json", "w"), separators=(",", ":"))
```

At runtime, read the asset, replace `__FILESDIR__` with `context.filesDir.absolutePath`, and load it
with `map.setStyle(Style.Builder().fromJson(editedJson))`. (You cannot use `asset://style.json`
directly because the `pmtiles://file://` path is device-specific.)

**Attribution is not optional.** ODbL Produced Work: keep "© OpenStreetMap contributors" visible.
MapLibre's `MapView` shows an attribution button by default — leave it on, and mention it in the
demo script. Judges notice licence hygiene.

### 4.5 Alternative: render our own GeoJSON in a custom style

**Pros.** Total control of the look; zero external data licence question beyond OSM itself; you
already have the corridor roads and building footprints; a hand-authored style with 8 layers is
easier to reason about than 67; `GeoJsonSource` from `asset://` needs no PMTiles machinery at all, so
the whole class of PMTiles bugs in §2.8 disappears; the file would be tens of KB.

**Cons — and they are the ones that decide it.**
1. **It will not look premium.** The 0.79 MiB Protomaps extract buys you landcover, landuse, water,
   POIs, boundaries, place labels, 39 tuned road layers with casings and per-zoom width
   interpolations, and highway shields. Hand-authoring an equivalent is a week of cartography.
2. **Zoom-dependent generalisation.** A vector tileset carries per-zoom simplification. A raw
   GeoJSON source is simplified once by `withTolerance` (default 0.375) across all zooms — either
   chunky when zoomed in or heavy when zoomed out.
3. **Labels still need glyphs.** No saving there.
4. **Cost is not the issue.** The PMTiles route costs one CLI command and 0.85 MB.

**Recommended hybrid — and this is what I would actually ship:** Protomaps PMTiles as the basemap,
**plus** your own GeoJSON sources on top for the things that make the demo *yours* — the corridor
polyline, A/B markers, geofenced zones, the breadcrumb trail, the ESKF uncertainty ellipse. That is
exactly what `GeoJsonSource` + `LineLayer`/`FillLayer`/`CircleLayer` are for, and it keeps the 10 Hz
update path isolated to sources you own.

---

## 5. Offline glyphs and sprites (the step everyone forgets)

Without this the map renders with **no labels and no error message**.

**Source:** `protomaps/basemaps-assets` — *"Fonts and sprites for basemaps, hosted on GitHub Pages"*,
89 stars, `pushed_at 2025-10-31`, no SPDX licence file at repo root but `fonts/OFL.txt` is present
(the Noto fonts are SIL Open Font License). Font directories present:
`Noto Sans Regular`, `Noto Sans Medium`, `Noto Sans Italic`, `Noto Sans Devanagari Regular v1`.

**Measured PBF sizes** (HTTP 200, `Content-Length`, fetched 2026-09-05):

| Font stack | `0-255.pbf` | `256-511.pbf` | `8192-8447.pbf` |
|---|---:|---:|---:|
| Noto Sans Regular | 76,044 | 127,726 | 64,220 |
| Noto Sans Medium | 77,628 | 129,635 | 65,101 |
| Noto Sans Italic | 79,344 | 132,976 | 52,891 |

**Bundle sizing:**
- Ranges `0-255` only, 3 stacks → **233,016 B (228 KiB)**. Covers ASCII + Latin-1. Enough for
  English campus labels.
- Ranges `0-255` + `256-511`, 3 stacks → **623,353 B (609 KiB)**. Adds Latin Extended-A/B.
- Add `Noto Sans Devanagari Regular v1` ranges `2304-2559` if you want Hindi place names — fetch and
  measure before committing; **UNVERIFIED** size.

**Sprites, measured:**
`sprites/v4/dark.json` 3,549 B · `dark.png` 16,054 B · `dark@2x.json` 3,579 B · `dark@2x.png`
28,407 B → **51,589 B (50 KiB) for all four**. Ship all four; MapLibre picks `@2x` on the S23 Ultra
(density 3.0, `pixelRatio` ≥ 2).

**Download script:**
```bash
BASE=https://protomaps.github.io/basemaps-assets
OUT=app/src/main/assets
for F in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
  mkdir -p "$OUT/fonts/$F"
  for R in 0-255 256-511; do
    curl -sL --get --data-urlencode "x=" -o "$OUT/fonts/$F/$R.pbf" \
      "$BASE/fonts/$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$F")/$R.pbf"
  done
done
mkdir -p "$OUT/sprites"
for S in dark.json dark.png dark@2x.json dark@2x.png; do
  curl -sL -o "$OUT/sprites/$S" "$BASE/sprites/v4/$S"
done
```
Then in the style: `"glyphs": "asset://fonts/{fontstack}/{range}.pbf"` and
`"sprite": "asset://sprites/dark"`. The `{fontstack}` token expands to the URL-encoded font name
(`Noto%20Sans%20Regular`); `AssetManagerFileSource` percent-decodes before opening the asset, so
directories with spaces work.

**Total offline payload:** 0.85 MB pmtiles + 0.61 MB glyphs + 0.05 MB sprites + 0.06 MB style
≈ **1.6 MB**. Trivial.

**Alternative that avoids glyphs entirely:** delete every `symbol` layer from the style (10 of the 67
layers) and draw the handful of labels you actually need (A, B, waypoints, zone names) as Compose
overlays positioned with `map.projection.toScreenLocation(LatLng)`. That gives you full typographic
control (Material 3 type scale, your own font) and a more "designed" look than map labels. It is a
legitimate premium choice, not just a shortcut. Cost: you must re-project on every camera move.
MapLibre also offers `MapLibreMapOptions.localIdeographFontFamily` (see
`org.maplibre.android.text.LocalGlyphRasterizer`) but that is **CJK-only** and will not help with
Latin or Devanagari.

---

## 6. Satellite imagery for the offline demo

### 6.1 Esri World Imagery — what is actually there at SNU (all [measured] today)

Tile URL pattern (note the **`/{z}/{y}/{x}`** order — row before column, which is the opposite of
XYZ conventions):
```
https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}
```

Fetched at 28.524 N, 77.574 E:

| z | tile x/y | HTTP | bytes | content |
|---|---|---|---|---|
| 16 | 46889 / 27346 | 200 | 17,715 | real imagery, 256×256 JPEG |
| 17 | 93779 / 54693 | 200 | 16,279 | real imagery |
| 18 | 187559 / 109386 | 200 | 14,795 | real imagery |
| **19** | 375119 / 218772 | 200 | 11,903 | **real imagery** — visually confirmed (the campus amphitheatre is clearly resolved) |
| 20 | 750238 / 437544 | 200 | 2,521 | **placeholder** — grey tile reading "Map data not yet available" |
| 21 | 1500477 / 875089 | 200 | 2,521 | placeholder, **byte-identical md5 to z20** (`f27d9de7…`) |

**Maximum usable zoom at SNU is z19.**

Service metadata (`…/World_Imagery/MapServer?f=json`): 256×256 JPEG, 96 dpi, **24 LODs (max level 23,
0.01866 m/px)**, `capabilities: Map,Query,Data,Tilemap`, **`exportTilesAllowed: false`**,
`copyrightText: "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"`.

Capture metadata via the **identify** endpoint — this is a great slide for the architecture doc:

```bash
curl -s -G "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/identify" \
  --data-urlencode "geometry=77.574,28.524" --data-urlencode "geometryType=esriGeometryPoint" \
  --data-urlencode "sr=4326" --data-urlencode "layers=all:0" --data-urlencode "tolerance=2" \
  --data-urlencode "mapExtent=77.56,28.51,77.59,28.54" --data-urlencode "imageDisplay=600,550,96" \
  --data-urlencode "returnGeometry=false" --data-urlencode "f=json"
```
Result at our point:
```json
{"DATE (YYYYMMDD)":"20230208","RESOLUTION (M)":"0.31","ACCURACY (M)":"5",
 "DESCRIPTION":"WV03","SOURCE_INFO":"Vivid Advanced","SOURCE":"Vantor",
 "MinMapLevel":"12","MaxMapLevel":"18","BlockName":"Vivid_Advanced_Delhi_IN_23Q2",
 "ReleaseName":"Maps 2023.R07"}
```
So: **WorldView-3, captured 2023-02-08, 0.31 m GSD, 5 m horizontal accuracy**, block
"Vivid_Advanced_Delhi_IN_23Q2". Quote these numbers — "the imagery under our route is 31 cm
WorldView-3 from 8 Feb 2023, geolocation accuracy 5 m" is exactly the kind of sentence that makes a
technical audience trust the rest of the document. (Note the block declares `MaxMapLevel 18` even
though z19 tiles are served; treat z19 as the practical ceiling and z18 as the guaranteed one.)

**Cache size if we were allowed to (measured by sampling 12 tiles per zoom and multiplying by the
exact tile count for the bbox):**

| z | grid | tiles | mean tile | zoom total |
|---|---|---:|---:|---:|
| 14 | 1×2 | 2 | 17,254 B | 0.03 MiB |
| 15 | 2×3 | 6 | 15,728 B | 0.09 MiB |
| 16 | 4×5 | 20 | 13,867 B | 0.26 MiB |
| 17 | 7×9 | 63 | 12,931 B | 0.78 MiB |
| 18 | 14×18 | 252 | 11,770 B | 2.83 MiB |
| 19 | 28×35 | 980 | 9,589 B | 8.96 MiB |
| | | **1,323** | | **≈ 13.0 MiB** |

### 6.2 …and why we must not ship that cache

Two independent, fetched sources say no.

1. **The layer's own `licenseInfo`** (ArcGIS sharing REST, item `10df2279f9684e4a9f6a7f08febac2a9`,
   owner `esri`, `modified` epoch-ms `1786117711000`):
   > "This work is licensed under the Esri Master License Agreement. … **Export:** This layer is not
   > intended to be used to export tiles for offline. If you would like to export imagery for offline
   > use in ArcGIS applications, you may use the World Imagery (for Export) layer, which is intended
   > for this purpose."
   Backed by the service flag `exportTilesAllowed: false`.

2. **Esri Product-Specific Terms of Use, document E300, dated 13 November 2025**, footnote 10
   (read directly from the PDF):
   > "Session tokens may only be used per Value Added Application / Customer Application per device.
   > Programmatic use of session tokens (e.g., exporting volumes of basemap tiles) is not permitted."

   (Footnote 96 similarly bars "exporting volumes of data larger than 10MB at a time" for ArcGIS
   Image services.) The E300 index page (esri.com/en-us/legal/terms/full-master-agreement) lists
   E204 / E204CW / E204SW / E300 with E300's most recent date **13 November 2025**.

The sanctioned route is **"World Imagery (for Export)"**, item `226d23f076da478bba4589e7eae95952`,
service `https://tiledbasemaps.arcgis.com/arcgis/rest/services/World_Imagery/MapServer`. Its
`licenseInfo` states:
> "**Important Note:** This item requires an ArcGIS Online organizational subscription or an ArcGIS
> Developer account and does not consume credits."

**Verdict:** an unauthenticated bulk cache of `services.arcgisonline.com` World Imagery is
non-compliant even for a non-commercial student demo. If the team wants Esri imagery offline, someone
must register a **free ArcGIS Developer account**, use the `tiledbasemaps.arcgis.com` "for Export"
service with a token, and honour whatever the developer-plan terms say. That is a real, defensible
path — but it is a decision, not a default (§11).

### 6.3 Alternatives, each checked

| Source | Verified finding | Usable? |
|---|---|---|
| **Bing / Google** | Excluded by the brief | — |
| **Bhuvan (ISRO NRSC)** — thematically ideal for an ISRO problem statement | `bhuvan-ras2.nrsc.gov.in/tilecache/tilecache.py?service=WMS&request=GetCapabilities` returns 200 (15,519 B). Layers advertised: `bhuvan_img, bhuvan_imagery_2018to20, bhuvan_testwsg, bhuvan_imagery2, assam_carto1s, bhuvan_imagery, assam_carto1g, bhuvan_testwss, bhuvan_img_3d, **bhuvan_900913**`. `bhuvan_900913` is EPSG:900913 with 20 resolution levels down to 0.2986 m/px (= z19), 256×256 JPEG. **But** every anonymous tile request at SNU (z12, z13, z14, z18, z19 tested) returns `302 → https://bhuvan-ras2.nrsc.gov.in/ivm.jpg`, and that image is the Bhuvan logo over the text **"Data not available"** (visually confirmed). Public WMS `GetMap` on the tilecache also 302s. | **No** without Bhuvan registration/API access. Worth a follow-up: register at bhuvan.nrsc.gov.in and ask for tile-service credentials — using ISRO's own imagery in an ISRO problem statement would be a strong differentiator. |
| **EOX Sentinel-2 cloudless** | Live proof it works with MapLibre offline: `https://demotiles.maplibre.org/pmtiles/raster/style-imagery.json` declares `"imagery": {"type":"raster","url":"pmtiles://https://demotiles.maplibre.org/pmtiles/raster/imagery.pmtiles","tileSize":256,"maxzoom":10,"attribution":"<a href='https://s2maps.eu'>Sentinel-2 cloudless 2023</a> by <a href='https://eox.at'>EOX</a> (modified Copernicus Sentinel data 2023; CC BY-NC-SA 4.0)"}`. That archive is 24,665,790 B of tile data, 1,289 tiles, **maxzoom 11**, `internal_compression=gzip`, `tile_compression=none` [measured]. `s2maps.eu` 301-redirects to `cloudless.eox.at`, which describes an annual cloud-free Sentinel-2 mosaic with a separate non-commercial licence deed; the specific resolution/year/max-zoom figures on that landing page were **not** stated (UNVERIFIED there, but the MapLibre demo style pins it at **CC BY-NC-SA 4.0** and **maxzoom 10–11**). | **No** for a campus close-up: Sentinel-2 is 10 m/px, and z10–11 is ~150–75 m/px. At bicycle zoom it is a green smear. |
| **Maxar Open Data** | `opengeos/maxar-open-data` `datasets.csv` lists event-driven collections only (cyclones, earthquakes, floods, wildfires). The only India entry is `India-Floods-Oct-2023` (51 scenes, Sikkim). | **No** — no Greater Noida coverage. |
| **OpenAerialMap** | `https://api.openaerialmap.org/meta?bbox=77.5639,28.5133,77.5823,28.5335` → **`found: 0`**. | **No** coverage. |
| **NASA GIBS** | WMTS REST pattern confirmed: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{Layer}/default/{Time}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.jpg`. Documented resolutions include 250 m, 1 km and 31.25 m; the Web-Mercator matrix set is `GoogleMapsCompatible_Level12` (i.e. **max z12**). Example layer given in the docs: `Landsat_WELD_CorrectedReflectance_Bands157_Global_Annual`. | **No** — z12 max, ≥31 m/px. Good for a "global context" inset, useless for a campus. |
| **Mapbox Satellite** | Mapbox Terms of Service (fetched) contain **no** clause about tile caching — the only "cach" hit is about content removal after account termination. The substantive rules live in the **Mapbox Product Terms, effective 21 July 2026**, a PDF that this review could not extract text from → **UNVERIFIED**. Historically Mapbox permits offline only through its own SDK's offline manager, which is not usable from MapLibre. | **Do not rely on it**; and it needs a token, which conflicts with "fully offline". |

### 6.4 What I recommend for the satellite toggle

Ranked:

1. **Cut the satellite toggle from the offline demo** and replace it with something you fully own —
   e.g. a "data layer" toggle that swaps the dark basemap for a high-contrast white/black flavour
   (Protomaps ships both from the same tileset, so it costs one extra 60 KB style JSON and **zero**
   extra tiles). Judges read "we checked the terms and chose a compliant alternative" as competence.
2. **Register a free ArcGIS Developer account** and use World Imagery (for Export) via
   `tiledbasemaps.arcgis.com` with a token, converting the 1,323-tile / ~13 MiB z14–19 pyramid into a
   raster PMTiles with `pmtiles convert` (from MBTiles). Compliant, and the imagery is genuinely
   0.31 m. Requires a decision by the lead and a written note of the account/terms in the doc.
3. **Fly the campus yourself** (a drone or even a georeferenced campus site plan), tile it with
   `gdal2tiles` → MBTiles → `pmtiles convert`. Fully owned, no licence questions, and "we captured
   our own orthomosaic" is a strong story. Cost: a day.
4. **Bhuvan with credentials** — best thematic fit for an ISRO jury, blocked only by registration.

### 6.5 Styling a hybrid (roads/labels over imagery) in MapLibre

The pattern is a single style with the raster source at the bottom of the layer list and a reduced
set of vector layers above it:

```json
{
  "version": 8,
  "glyphs": "asset://fonts/{fontstack}/{range}.pbf",
  "sprite": "asset://sprites/dark",
  "sources": {
    "sat":       { "type": "raster", "url": "pmtiles://file://…/snu_sat.pmtiles", "tileSize": 256, "maxzoom": 19 },
    "protomaps": { "type": "vector", "url": "pmtiles://file://…/snu_campus.pmtiles" }
  },
  "layers": [
    { "id": "sat", "type": "raster", "source": "sat",
      "paint": { "raster-opacity": 1.0, "raster-saturation": -0.25, "raster-contrast": 0.05 } },
    { "id": "roads-casing", "type": "line", "source": "protomaps", "source-layer": "roads",
      "paint": { "line-color": "rgba(0,0,0,0.55)", "line-width": 5, "line-blur": 0.5 },
      "layout": { "line-cap": "round", "line-join": "round" } },
    { "id": "roads", "type": "line", "source": "protomaps", "source-layer": "roads",
      "paint": { "line-color": "rgba(255,255,255,0.85)", "line-width": 2 } },
    { "id": "labels", "type": "symbol", "source": "protomaps", "source-layer": "places",
      "layout": { "text-field": ["get","name"], "text-font": ["Noto Sans Medium"], "text-size": 13 },
      "paint": { "text-color": "#ffffff", "text-halo-color": "rgba(0,0,0,0.85)", "text-halo-width": 1.6 } }
  ]
}
```

Three rules that make a hybrid look professional rather than cluttered:
- **Desaturate the imagery slightly** (`raster-saturation` ≈ −0.2 to −0.3) so the vector overlay
  reads as the foreground. Satellite basemaps in premium apps are almost never at full saturation.
- **Halo everything.** `text-halo-width` 1.5–2 px with an 85 % black halo is the difference between
  legible and unreadable over imagery.
- **Drop the fills.** Keep roads, labels, and your own overlays; delete landcover/landuse/water fills
  — the imagery already shows them.
- Switching the toggle: keep **one** style with both sources and flip
  `style.getLayer("sat")!!.setProperties(PropertyFactory.visibility(Property.NONE|Property.VISIBLE))`
  plus swap the vector paint. Re-calling `setStyle()` reloads the whole style and gives a visible
  white flash on video — avoid it.

---

## 7. Ferrostar and other open-source code worth borrowing

### 7.1 Ferrostar (Stadia Maps)

`stadiamaps/ferrostar` — *"A FOSS navigation SDK built from the ground up for the future"*.
**417 stars**, `pushed_at 2026-09-03`, 1,640 commits, licence file is **BSD 3-Clause**
("Copyright (c) 2023, Stadia Maps, Inc.", read from `LICENSE.txt`; GitHub's classifier reports
`NOASSERTION` because of the file name). Latest release **0.54.0, 2026-08-18** (previous: 0.53.0
2026-06-23, 0.52.0 2026-06-17, 0.51.0 2026-05-28). Maven Central `com.stadiamaps.ferrostar:ui-compose`
`<latest>0.54.0</latest>`, `<lastUpdated>20260818033404</lastUpdated>`; published versions start at
0.49.0 (older ones were on a different host).

Modules: `core`, `ui-compose`, `ui-maplibre`, `google-play-services`. Documented Gradle block:
```gradle
dependencies {
    def ferrostarVersion = 'X.Y.Z'
    implementation "com.stadiamaps.ferrostar:core:${ferrostarVersion}"
    implementation "com.stadiamaps.ferrostar:ui-maplibre:${ferrostarVersion}"
    implementation "com.stadiamaps.ferrostar:ui-compose:${ferrostarVersion}"
    implementation "com.stadiamaps.ferrostar:google-play-services:${ferrostarVersion}"
    implementation platform("com.squareup.okhttp3:okhttp-bom:4.11.0")
    implementation 'com.squareup.okhttp3:okhttp'
}
```

`ui-maplibre-0.54.0.pom` dependencies: **`org.maplibre.compose:maplibre-compose-android:0.13.0`**,
Kotlin BOM **2.3.20**, Compose BOM **2026.02.01**, `androidx.core:core-ktx:1.17.0`,
`androidx.appcompat:appcompat:1.7.1`, `androidx.activity:activity-compose:1.13.0`,
`androidx.lifecycle:lifecycle-runtime-compose-android:2.10.0` + `lifecycle-viewmodel-compose:2.10.0`.

**Do not take the dependency** — it drags in maplibre-compose 0.13.0 (Kotlin 2.3.20) and a Rust FFI
core built for turn-by-turn routing we do not need. **Do take the code**, with attribution (BSD-3
requires reproducing the copyright notice; add it to a THIRD_PARTY file).

The four files worth reading and porting (paths under
`android/ui-maplibre/src/main/java/com/stadiamaps/ferrostar/maplibreui/`):

**`runtime/NavigationCamera.kt` — the camera presets.** Verbatim:
```kotlin
sealed class NavigationActivity(val zoom: Double, val tilt: Double) {
  data object Automotive : NavigationActivity(zoom = 16.0, tilt = 45.0)
  data object Bicycle    : NavigationActivity(zoom = 18.0, tilt = 45.0)   // <- us
  data object Pedestrian : NavigationActivity(zoom = 20.0, tilt = 10.0)
}
enum class NavigationCameraMode { FOLLOW_USER, FOLLOW_USER_WITH_BEARING, OVERVIEW, FREE }
```
and the padding that puts the puck low in the frame:
```kotlin
internal fun navigationPaddingForScreen(orientation, screenWidthDp, screenHeightDp) =
  PaddingValues(
    start = if (orientation == ORIENTATION_LANDSCAPE) (screenWidthDp * 0.5f).dp else 0.dp,
    top   = (screenHeightDp * 0.5f).dp,
  )
```
plus a comment that saves an afternoon of debugging:
> "MapLibre centers the target in the padded viewport. Moving the bottom edge up by X only moves the
> center by X / 2, so double the needed target shift when converting it to padding."

**So: bicycle camera = zoom 18.0, tilt 45°, top padding = 50 % of screen height.** Those three
numbers are the whole "course-up, pitched, puck in the lower third" look, taken from a shipping
navigation SDK. Use them as the starting point and tune. For speed-scaled zoom, interpolate between
about z18.5 at 0 m/s and z16.5 at 8 m/s and drive it through
`locationComponent.zoomWhileTracking(zoom, 750)` rather than a raw `animateCamera`.

**`routeline/BorderedPolyline.kt` — the route line recipe.** Verbatim defaults:
```kotlin
color = Color(0xFF3583DD), borderColor = Color.White,
lineWidth = 10f, borderWidth = 3f,
// casing layer width = lineWidth + borderWidth*2 = 16 dp, drawn first
cap = LineCap.Round, join = LineJoin.Round
```

**`NavigationMapPuckStyle.kt` — the puck palette.** Verbatim:
```kotlin
dotFillColor = Color(0xFF3583DD), dotStrokeColor = Color.White,
shadowColor  = Color.Black.copy(alpha = 0.2f),
accuracyStrokeColor = Color(0xFF3583DD),
accuracyFillColor   = Color(0xFF3583DD).copy(alpha = 0.16f),
bearingColor = Color(0xFF0F5FB8),
dotRadius = 7.dp, dotStrokeWidth = 3.dp
```

**`runtime/TrackingCameraEffect.kt` — the anti-jitter insight.** Its KDoc:
> "Sets the camera position synchronously during composition so that camera and puck update on the
> same frame. On the first location or after a mode change, the camera snaps to the template position
> (setting zoom/tilt from `NavigationCameraOptions`). On subsequent updates it preserves zoom/tilt
> and only updates target/bearing."

**Mistake to avoid:** if you animate the camera to the new fix while the puck is separately
interpolating to it, the puck visibly swims inside the frame. Either let `CameraMode.TRACKING_GPS`
own both (which is what `LocationComponent` does — one animator drives puck and camera together), or
drive both from the same value on the same frame. Do **not** mix `forceLocationUpdate` with your own
`animateCamera` per fix.

Other reusable Ferrostar Compose pieces (in `android/ui-compose/.../views/`):
`components/TripProgressView.kt`, `components/CurrentRoadView.kt`,
`components/controls/NavigationUIButton.kt`, `controls/NavigationUIZoomButton.kt`,
`controls/PillDragHandle.kt`, `gridviews/NavigatingInnerGridView.kt`,
`overlays/PortraitNavigationOverlayView.kt` / `LandscapeNavigationOverlayView.kt`,
`theme/NavigationUITheme.kt` / `TripProgressViewTheme.kt`,
`runtime/KeepScreenOnDisposableEffect.kt` (you want this — a demo screen that dims mid-ride is
embarrassing), `runtime/WindowInsetSupport.kt`, `measurement/LocalizedSpeed.kt`,
`support/GreenScreenPreview.kt`. The overlay/grid views are a clean model for a HUD that must not
collide with the map attribution or the system bars.

### 7.2 `maplibre/maplibre-navigation-android`

**200 stars**, `pushed_at 2026-09-01`, **MIT**, no telemetry. Latest release **5.0.0 (2026-08-26)** —
note Maven Central's `<release>` for `org.maplibre.navigation:navigation-core` and
`navigation-ui-android` is still **`5.0.0-pre14`** (`lastUpdated 20260826214006`), so the GitHub tag
is ahead of the published artifacts. Coordinates:
```gradle
implementation 'org.maplibre.navigation:navigation-core:5.0.0-pre14'
implementation 'org.maplibre.navigation:navigation-ui-android:5.0.0-pre14'
implementation 'org.maplibre.navigation:navigation-location-gms-android:5.0.0-pre14'  // optional, GMS
```
5.0.0 highlights from the release notes: KMP conversion (JS/Wasm/JVM exports added in #231),
`LocationEngine.Request` generalised across Android and iOS (breaking), `GoogleLocationEngine` moved
out of `navigation-core` so the Android core is fully FLOSS, migrated from maplibre-java to
**Spatial-K** (pre14). It is a fork of Mapbox Navigation SDK v0.19 via flitsmeister.

**Relevance to us: low.** It is a turn-by-turn engine (route progress, off-route detection, voice
instructions) with the UI stripped out. We are not doing turn-by-turn. Two things are worth stealing
conceptually: its `LocationEngine` abstraction (a clean seam for injecting our estimator) and the
fact that a *very* recent open issue, **#4541 (open, 2026-09-02) "SIGABRT in `__cxa_pure_virtual`
when using MapLibre Navigation"**, is filed against maplibre-native — another argument for keeping
our stack thin.

### 7.3 Other 2025–2026 code to read

- **`maplibre/maplibre-native` test app** — the single best source of correct Android idioms.
  Directly relevant activities:
  `activity/style/BuildingFillExtrusionActivity.kt` (3D + `Light`),
  `activity/style/RealTimeGeoJsonActivity.kt` (10 Hz-style source updates + `iconRotate`),
  `activity/sources/PMTilesActivity.kt` (local + remote PMTiles),
  `activity/location/ManualLocationUpdatesActivity.kt` (**exactly our pattern**: null
  `LocationEngine` + `forceLocationUpdate`),
  `activity/location/LocationModesActivity.kt`, `CustomizedLocationPulsingCircleActivity.kt`,
  `activity/camera/CameraAnimationTypeActivity.kt` / `CameraAnimatorActivity.kt`,
  `activity/offline/DownloadRegionActivity.kt`. All BSD-2-Clause.
- **`maplibre/maplibre-compose` demo app** (`demo-app/common/src/commonMain/.../docsnippets/`) —
  `Camera.kt`, `Layers.kt`, `Location.kt`, `Styling.kt`, `Offline.kt`, `Material3.kt`,
  `Snapshotter.kt`, `Expressions.kt`. BSD-3-Clause. Read for API shape even if you do not depend on it.
- **`protomaps/basemaps`** (727 stars, `pushed_at 2026-08-20`) — the cartography reference for the
  dark flavour; the npm package `@protomaps/basemaps@5.7.2` is BSD-3-Clause.

---

## 8. Jetpack Compose specifics for a HUD-style screen

### 8.1 Exact artifact versions (all verified on Google Maven, 2026-09-05)

```kotlin
// libs.versions.toml
composeBom      = "2026.08.00"   // <lastUpdated>20260812170922</lastUpdated>
activityCompose = "1.13.0"       // latest *stable*; 1.14.0-alpha01 is the head
lifecycle       = "2.11.0"       // latest *stable*; 2.12.0-alpha02 is the head
splashscreen    = "1.2.0"        // androidx.core:core-splashscreen, 2025-11-05
maplibre        = "13.6.0"
```

`compose-bom:2026.08.00` pins (read from its POM and confirmed against the BOM mapping page):

| Artifact | Version |
|---|---|
| `androidx.compose.ui:ui` | **1.12.0** |
| `androidx.compose.foundation:foundation` / `-layout` | **1.12.0** |
| `androidx.compose.runtime:runtime` | **1.12.0** |
| `androidx.compose.animation:animation` / `-core` / `-graphics` | **1.12.0** |
| `androidx.compose.material:material` / `-ripple` | **1.12.0** |
| `androidx.compose.material3:material3` | **1.4.0** |
| `androidx.compose.material3:material3-window-size-class` | **1.4.0** |
| `androidx.compose.material3.adaptive:adaptive` / `-layout` / `-navigation` | **1.3.0** |
| `androidx.compose.material:material-icons-core` / `-extended` | 1.7.8 (frozen) |

### 8.2 Material 3 and "Expressive"

- **Stable material3 is 1.4.0, released 2026-08-26.**
- **Material 3 Expressive is NOT in a stable artifact.** The expressive APIs were de-experimentalised
  inside the **1.5.0-alpha** line: `materialExpressiveTheme` / `expressiveLightColorScheme` and
  `FloatingToolbar` / FAB Menu promoted in **1.5.0-alpha18 (2026-04-22)**; expressive button APIs in
  **1.5.0-alpha19 (2026-05-06)** — the same release **reverted** `MaterialShapes` and
  `LoadingIndicator` back out of stable; `ButtonGroup` promoted in **1.5.0-alpha22 (2026-06-17)**;
  a unified `rememberBottomSheetState` arrived in **1.5.0-alpha20 (2026-05-19)**. Head is
  **1.5.0-alpha27 (2026-08-26)**.
- **Decision:** ship on **material3 1.4.0** via the BOM, and hand-build the two or three "expressive"
  moments (a spring-y speed readout, a shape-morphing record button) with
  `androidx.compose.animation` 1.12.0 primitives. Pulling `material3:1.5.0-alpha27` into a
  hackathon build to get `FloatingToolbar` is a bad trade: alpha APIs break, and a jury cannot see
  the difference between a real `MaterialShapes` morph and a well-tuned `animateFloatAsState` on a
  `RoundedPolygon`.
- `ModalBottomSheet` / `BottomSheetScaffold`: **UNVERIFIED whether they are still
  `@ExperimentalMaterial3Api` in 1.4.0.** The release-notes page I fetched describes the bottom-sheet
  graduation in the 1.5.0-alpha line, not 1.4.0. Assume you still need
  `@OptIn(ExperimentalMaterial3Api::class)` on 1.4.0 and confirm at first compile — it is a
  one-annotation problem either way.

### 8.3 The HUD patterns you actually need

**Animated numeric readouts.** Two different tools, and picking the wrong one is the usual mistake:

- **`animateFloatAsState` (+ `Text` on the animated value)** for a *continuously varying* quantity —
  speed, distance travelled, heading. The number should glide, not flip.
  ```kotlin
  val speed by animateFloatAsState(
      targetValue = uiState.speedMps,
      animationSpec = spring(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessLow),
      label = "speed"
  )
  Text("%.1f".format(speed * 3.6f), style = MaterialTheme.typography.displayMedium)
  ```
  At 10 Hz input a low-stiffness spring gives a smooth readout without lag artefacts. Do **not** put
  a raw 10 Hz value into `Text` — it jitters in the last digit and looks cheap on video.
- **`AnimatedContent`** for a *discrete state change* — the mode chip flipping between
  "GNSS" / "DEAD RECKONING" / "ZUPT", or a digit rolling in an odometer. Use
  `transitionSpec = { slideInVertically { it } + fadeIn() togetherWith slideOutVertically { -it } + fadeOut() using SizeTransform(clip = false) }`.
- **Stability.** Hoist the map-facing state into a `@Stable` holder and expose the 10 Hz pose as a
  `StateFlow` collected with `collectAsStateWithLifecycle()` (lifecycle-runtime-compose **2.11.0**).
  Split the HUD into small composables so a speed change does not recompose the whole screen — read
  the value inside the leaf `Text`'s lambda where possible (`Text(text = { speed })`-style deferred
  reads) rather than at the top of the screen composable.
- **Never recompose the map.** See §2.3: keep the pose out of `AndroidView`'s `update` lambda.

**Haptics.** `LocalHapticFeedback.current.performHapticFeedback(HapticFeedbackType.…)`.
**UNVERIFIED:** I could not fetch the `HapticFeedbackType` constant list for Compose 1.12.0 (the
API-reference page returned only navigation chrome, and the androidx mirror path I tried 404'd).
Verify the available constants at first compile; `LongPress`, `TextHandleMove`, `Confirm`, `Reject`,
`ToggleOn`, `ToggleOff`, `SegmentTick` are the ones to look for. Use one short tick at
start/stop-recording and at zone entry/exit; nothing more. Haptics on a phone mounted to a down tube
are inaudible to the rider anyway — they are for the *demo-day* handheld run-through.

**Edge-to-edge on Android 16 (targetSdk 36).** Verified from
developer.android.com/about/versions/16/behavior-changes-16:
> "For apps targeting Android 16 (API level 36), `R.attr#windowOptOutEdgeToEdgeEnforcement` is
> deprecated and disabled, and your app can't opt-out of going edge-to-edge."

So: call `enableEdgeToEdge()` in `onCreate` **before** `super.onCreate` (MapLibre's own
`RealTimeGeoJsonActivity` does exactly this), let the map draw under the bars, and pad only the HUD
with `WindowInsets.safeDrawing` / `systemBars`. Also on targetSdk 36:
- **Predictive back is on by default**; `onBackPressed()` is not called and `KEYCODE_BACK` is not
  dispatched. Migrate to `BackHandler` / `onBackInvokedCallback`, or temporarily set
  `android:enableOnBackInvokedCallback="false"`.
- On displays with `smallestWidth ≥ 600dp`, `android:screenOrientation`, `resizableActivity="false"`,
  `minAspectRatio`/`maxAspectRatio` and `setRequestedOrientation()` are **ignored**. Irrelevant on a
  phone, but do not rely on a forced-portrait manifest if you ever demo on a tablet. Temporary
  opt-out property: `android.window.PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY`.

**Keeping the map at 60 fps with Compose on top.**
1. Map in `AndroidView`, HUD in a `Box` above it. One `AndroidView`, created once.
2. Nothing that changes at 10 Hz may be read in `update`.
3. Give the map `Modifier.fillMaxSize()` and avoid animating the `AndroidView`'s own `Modifier`
   (size/offset/graphicsLayer) — that forces a `SurfaceView`/`TextureView` reconfigure every frame.
4. If you need a scrim or blur behind the HUD, draw it in Compose, not by animating map layers.
5. Measure with `adb shell dumpsys gfxinfo <pkg> framestats`, and use MapLibre's
   `MapView.setMaximumFps` only as a battery lever, never to fix jank.
6. MapLibre 13.x ships Tracy profiling hooks (`docs/mdbook/src/profiling/tracy-profiling.md`) if you
   need to prove the renderer is not the bottleneck.

### 8.4 Minimal integration skeleton

```kotlin
@Composable
fun MapScreen(vm: MapViewModel) {
    val ctx = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var mapRef by remember { mutableStateOf<MapLibreMap?>(null) }

    val mapView = remember {
        MapLibre.getInstance(ctx)                       // auto-detects Vulkan/OpenGL
        MapView(ctx).apply { onCreate(null) }
    }

    DisposableEffect(lifecycleOwner) {
        val obs = LifecycleEventObserver { _, e -> when (e) {
            Lifecycle.Event.ON_START  -> mapView.onStart()
            Lifecycle.Event.ON_RESUME -> mapView.onResume()
            Lifecycle.Event.ON_PAUSE  -> mapView.onPause()
            Lifecycle.Event.ON_STOP   -> mapView.onStop()
            else -> Unit
        } }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs); mapView.onDestroy() }
    }

    Box(Modifier.fillMaxSize()) {
        AndroidView(
            factory = { mapView.also { mv -> mv.getMapAsync { m -> mapRef = m; vm.onMapReady(m) } } },
            modifier = Modifier.fillMaxSize(),
            update = { /* only slow-changing state here */ },
            onRelease = { /* mapView.onDestroy() handled above */ }
        )
        HudOverlay(vm, Modifier.align(Alignment.BottomCenter).windowInsetsPadding(WindowInsets.safeDrawing))
    }

    // 10 Hz path: never touches recomposition of AndroidView
    LaunchedEffect(mapRef) {
        val map = mapRef ?: return@LaunchedEffect
        vm.pose.collect { p ->                          // StateFlow<Pose>, main dispatcher
            map.locationComponent.forceLocationUpdate(p.toLocation())
            (map.style?.getSource("trail") as? GeoJsonSource)?.setGeoJson(p.trailLineString)
        }
    }
}
```

---

## 9. Clean screen recording on Samsung One UI 8

### 9.1 The built-in recorder — verified capabilities and limits

From Samsung's own support article "Record and capture your Galaxy phone or tablet's screen"
(samsung.com/us/support/answer/ANS10001616/, fetched 2026-09-05; the article says screen recorder is
available on "One UI 2 or later"):

| Setting | Documented values |
|---|---|
| Sound | **None**, **Media**, **Media and mic** |
| Video quality | **High (1080p)**, **Medium (720p)**, **Low (480p)** |
| Selfie video size | adjustable pop-up when using the front camera |
| Show taps and touches | "Small dots will appear whenever you touch or tap the screen while recording" |
| Storage location | selectable |

**Frame rate is not a documented setting.** Samsung does not expose a 60 fps toggle; the recorder
picks a rate based on content. SamMobile reported that One UI 6.0 added high-refresh-rate support to
the recorder, but that is a news site, not documentation — treat "1080p/60" as **not guaranteed**.

Practical settings for a clean demo capture:
1. Settings → Advanced features → **Screenshots and screen recorder** → Screen recorder settings.
2. Sound: **Media** (captures in-app audio, no room noise). Use **Media and mic** only if you are
   narrating live; otherwise narrate in post.
3. Video quality: **High (1080p)**.
4. **Show taps and touches: ON** — counter-intuitive, but for a jury it proves a human is driving the
   UI rather than a scripted animation. Turn it off only if the dots collide with your HUD.
5. Set the phone to **60 Hz** display (Settings → Display → Motion smoothness → Standard) *if* you
   want a deterministic frame cadence; **Adaptive** up to 120 Hz can produce a recorder output with
   uneven frame pacing.
6. Screen resolution: the S23 Ultra defaults below its native panel resolution; set Settings →
   Display → Screen resolution → **FHD+ (2340×1080)** so the recorder is not downscaling from QHD+.
7. Turn on **Do not disturb**, and hide notification content, before recording.

### 9.2 Hiding the status bar

There is **no One UI setting** that hides the status bar for a recording. Two workable routes:

- **In-app (recommended, verified API).** From
  developer.android.com/develop/ui/views/layout/immersive:
  ```kotlin
  val c = WindowCompat.getInsetsController(window, window.decorView)
  c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
  c.hide(WindowInsetsCompat.Type.systemBars())     // or .statusBars() / .navigationBars()
  ```
  Gate it behind a "presentation mode" toggle in the app. This is fully compatible with Android 16's
  edge-to-edge enforcement — enforcement removes your ability to *opt out* of drawing edge-to-edge;
  it does not remove your ability to *hide* the bars.
- **Legacy `adb shell settings put global policy_control immersive.full=*`** — do not rely on it.
  The immersive documentation does not mention `policy_control` at all and it was removed from AOSP
  years ago. **UNVERIFIED / assume broken on Android 16.**

### 9.3 In-app MediaProjection as an alternative

Only worth building if you need a recording that is guaranteed status-bar-free and starts/stops with
your own UI. Requirements confirmed for modern Android:
- Foreground service with `android:foregroundServiceType="mediaProjection"` and the
  `FOREGROUND_SERVICE_MEDIA_PROJECTION` permission.
- Android 15 explicitly bars `BOOT_COMPLETED` receivers from starting a `mediaProjection` foreground
  service (`ForegroundServiceStartNotAllowedException`); test toggle
  `adb shell am compat enable FGS_BOOT_COMPLETED_RESTRICTIONS <pkg>`.
- **UNVERIFIED:** the Android 14+ "consent required for every new capture session" rule, the
  partial-screen (single-app) capture flow, and the mandatory `MediaProjection.Callback`
  registration — I could not fetch a page stating these today. Verify against
  developer.android.com/media/grow/media-projection before committing engineering time.

**Recommendation:** use the built-in recorder plus the in-app immersive toggle. Building a
MediaProjection recorder for a hackathon demo is a day of work that produces the same 1080p file.

### 9.4 Cheapest quality wins, in order

1. FHD+ resolution + 60 Hz + Do-Not-Disturb.
2. In-app "presentation mode" hiding system bars.
3. Record the ride once, cleanly, then narrate over it in post — a live narration during a bicycle
   ride will have wind noise.
4. If you need >1080p or a guaranteed 60 fps: mirror to a Mac and capture with QuickTime
   (Wireless/USB screen mirroring), or `scrcpy --record` over USB. **UNVERIFIED** whether One UI 8
   permits USB screen mirroring to QuickTime on this device — test before demo day.

---

## 10. Risk register

| # | Risk | Evidence | Mitigation |
|---|---|---|---|
| R1 | Vulkan backend faults on Adreno | PR #4442 (Adreno `VK_ERROR_DEVICE_LOST` with the specialized location indicator, fixed 13.5.0); #4491 Vulkan custom-layer SIGSEGV regression in 13.5.0 | Ship `android-sdk-vulkan-opengl:13.6.0`, add a debug switch to force `RenderingEngine.Type.OPENGL`, test both on the actual S23 Ultra in week 1 |
| R2 | PMTiles gzip internal-compression failure | Open issue #4462 (iOS-reported) | Counter-evidence: MapLibre's own demotiles raster PMTiles is gzip-compressed and loads on Android [measured]. Still: smoke-test `snu_campus.pmtiles` on device before anything else |
| R3 | `PMTilesFileSource` SIGSEGV | Open issue #4459 | We use one local, complete archive rather than two streaming remote sources — the reported repro does not apply. Wrap style load in a try/catch and keep a plain-GeoJSON fallback style |
| R4 | Blank map because the camera is outside the extract | Closed issue #4398 (retracted false alarm) | Assert at startup that the initial camera target is inside the extract bbox; log the bbox |
| R5 | No labels offline | Glyph fetch failure is silent | Ship glyphs in `assets/` (§5) and add a startup check that `assets/fonts/Noto Sans Regular/0-255.pbf` exists |
| R6 | Satellite toggle is non-compliant | Esri E300 fn.10 (2025-11-13) + item `licenseInfo` + `exportTilesAllowed:false` | See §11 decision D2 |
| R7 | maplibre-compose adopted by mistake | Kotlin 2.4.10 / AGP 9.1.1 / JDK 25 vs team's 2.2.10 / 8.13.2 / 21 | Written down here; do not add the dependency |
| R8 | 10 Hz GeoJSON re-tessellation eats frames | 12k points after 20 min | Decimate to >1 m spacing; use `setOverrideSynchronousUpdate(true)` only on the small sources |
| R9 | Recorder does not deliver 60 fps | Samsung documents resolution only, not frame rate | Force 60 Hz display, FHD+, and accept 30 fps if that is what you get; do not promise 60 in the script |

---

## 11. Decisions for the lead

**D1 — MapLibre artifact.** `android-sdk-vulkan-opengl:13.6.0` (31.6 MiB AAR, runtime backend
switch, insurance against R1) **or** `android-sdk-opengl:13.6.0` (14.9 MiB, no Vulkan at all,
simplest)? My recommendation: **`android-sdk-vulkan-opengl`** for the demo build. APK size is not a
judging criterion; a black map on stage is.

**D2 — Satellite toggle.** Pick one:
- **(a) Drop it** and ship a light/dark basemap toggle from the same PMTiles instead (zero extra
  data, zero licence risk). *My recommendation for the hackathon.*
- **(b) Register a free ArcGIS Developer account**, pull World Imagery (for Export) from
  `tiledbasemaps.arcgis.com` with a token, and ship ~13 MiB of z14–19 raster PMTiles. Compliant, and
  the imagery is 0.31 m WorldView-3 from 2023-02-08. Needs someone to own the account and write the
  terms note.
- **(c) Chase Bhuvan credentials** (ISRO's own imagery, best thematic fit for this jury) — highest
  upside, unknown lead time, anonymous access is confirmed blocked.

**D3 (minor) — glyph coverage.** Latin-1 only (228 KiB) or Latin Extended (609 KiB)? Add Devanagari
if any campus labels are in Hindi. Default: **Latin Extended, 609 KiB.**

**D4 (minor) — labels.** Use the Protomaps `symbol` layers (needs glyphs), or delete them and draw
all labels as Compose overlays projected with `map.projection.toScreenLocation()` (more designed,
more work, no glyph dependency). Default: **keep map labels, add Compose overlays only for A/B and
zones.**

---

## 12. Source ledger

Every item below was fetched during this review on **2026-09-05**. `[m]` marks facts I measured by
executing code against the live service rather than reading documentation.

**MapLibre Native**
1. `https://repo1.maven.org/maven2/org/maplibre/gl/android-sdk/maven-metadata.xml` — 13.6.0 latest, `lastUpdated 20260828132607`. *(WebFetch 403s on repo1; fetched with curl.)*
2. `https://repo1.maven.org/maven2/org/maplibre/gl/{android-sdk,android-sdk-opengl,android-sdk-vulkan,android-sdk-vulkan-opengl}/13.6.0/*.aar` — AAR sizes `[m]`
3. `https://api.github.com/repos/maplibre/maplibre-native` — 2,190 stars, BSD-2-Clause, `pushed_at 2026-09-05T00:42:15Z`
4. `https://api.github.com/repos/maplibre/maplibre-native/releases` — `android-v13.6.0` 2026-08-28T13:38:55Z
5. `https://raw.githubusercontent.com/maplibre/maplibre-native/main/platform/android/CHANGELOG.md` — 13.0.0 → 13.6.0 notes
6. `https://maplibre.org/maplibre-native/android/api/` — package list, docs at 13.4.1
7. `.../platform/android/docs/data/PMTiles.md` — `pmtiles://` schemes, asset:// exclusion, offline-pack exclusion
8. `.../platform/android/docs/data/rendering-engine.md` — artifact/backend table
9. `.../platform/android/docs/{getting-started.md, configuration.md, location-component.md, styling/building-layer.md, styling/live-realtime-data.md, camera/animation-types.md}`
10. `.../MapLibreAndroidTestApp/.../activity/sources/PMTilesActivity.kt`, `.../style/BuildingFillExtrusionActivity.kt`, `.../style/RealTimeGeoJsonActivity.kt`, `.../location/ManualLocationUpdatesActivity.kt`, `.../styles/TestStyles.kt`
11. `.../MapLibreAndroid/src/main/java/org/maplibre/android/location/{LocationComponent.java, LocationComponentOptions.java, LocationComponentConstants.java, LocationComponentActivationOptions.java, LocationAnimatorCoordinator.java, modes/CameraMode.java, modes/RenderMode.java}`
12. `.../style/sources/{GeoJsonSource.kt, GeoJsonOptions.kt}`; `.../offline/{OfflineManager.kt, OfflineTilePyramidRegionDefinition.kt}`; `.../maps/MapView.java`, `.../maps/MapLibreMap.java`; `.../camera/{CameraUpdateFactory.kt, CameraPosition.kt}`; `.../constants/MapLibreConstants.java`
13. `.../platform/android/MapLibreAndroid/src/cpp/asset_manager_file_source.cpp` — `url.substr(8)`, whole-asset read, no ranges
14. GitHub issue search `repo:maplibre/maplibre-native pmtiles` (47 results) and issues **#4459, #4462, #4421, #4398** (full bodies + comments); PR **#4442**, **#4278**; issue search `vulkan adreno` (#4506, #4491, #4541)
15. `https://maplibre.org/maplibre-style-spec/layers/` — fill-extrusion / line / symbol property tables

**MapLibre Compose**
16. `https://api.github.com/repos/maplibre/maplibre-compose` — 564 stars, BSD-3-Clause, `pushed_at 2026-09-05T06:38:00Z`; releases v0.15.0 2026-08-25
17. `https://repo1.maven.org/maven2/org/maplibre/compose/` (artifact list), `maplibre-compose/maven-metadata.xml`, `maplibre-compose-android/{0.15.0,0.13.1}/*.pom` — Kotlin 2.4.10 vs 2.3.21, FFI switch `[m]`
18. `https://raw.githubusercontent.com/maplibre/maplibre-compose/v0.15.0/gradle/libs.versions.toml` — compileSdk 37, JDK 25, AGP 9.1.1
19. `https://maplibre.org/maplibre-compose/`, `…/getting-started/`; demo snippets `Camera.kt`, `Layers.kt`, `Location.kt`, `Styling.kt`, `Offline.kt` at tag v0.15.0
20. `https://kotlinlang.org/docs/kotlin-evolution-principles.html` — binary backwards/forwards compatibility statement

**Basemap production**
21. `https://build.protomaps.com/20260904.pmtiles` — PMTiles v3 header + directory walk + per-tile byte sums for the SNU bbox `[m]`
22. `https://btrfs.openfreemap.com/files.txt` and `…/areas/planet/20260830_080001_pt/tiles.pmtiles` — 86.3 GB, z0–14, bbox extract 2.38 MiB `[m]`
23. `https://docs.protomaps.com/basemaps/downloads`, `…/basemaps/flavors`, `…/basemaps/layers`, `…/pmtiles/cli`
24. `https://api.protomaps.com/styles/v4/dark/en.json?key=…` — style@4.4.0, 67 layers, fonts, glyph/sprite URLs `[m]`
25. `https://registry.npmjs.org/@protomaps/basemaps` — 5.7.2, BSD-3-Clause
26. `https://api.github.com/repos/{protomaps/go-pmtiles, protomaps/basemaps, protomaps/basemaps-assets, onthegomap/planetiler, versatiles-org/versatiles-rs}` — stars, licences, push dates
27. `https://github.com/onthegomap/planetiler` + releases API — v0.10.2 2026-03-29, Apache-2.0
28. `https://docs.versatiles.org/`, `…/guides/download_tiles.html`, `https://github.com/versatiles-org/versatiles-style`, `https://tiles.versatiles.org/assets/styles/eclipse/style.json` `[m]`
29. `https://openfreemap.org/`, `https://github.com/hyperknot/openfreemap`, `https://tiles.openfreemap.org/styles/{liberty,bright,dark,positron,fiord}` `[m]`
30. `https://protomaps.github.io/basemaps-assets/fonts/…` and `…/sprites/v4/dark*` — glyph/sprite byte sizes `[m]`

**Satellite**
31. `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` at z16–z21 over SNU — sizes, md5s, visual inspection of z19 and z20 `[m]`
32. `…/World_Imagery/MapServer/identify?…` — WV03, 2023-02-08, 0.31 m, 5 m, MinMapLevel 12 / MaxMapLevel 18 `[m]`
33. `…/World_Imagery/MapServer?f=json` — 24 LODs, `exportTilesAllowed:false` `[m]`
34. `https://www.arcgis.com/sharing/rest/content/items/10df2279f9684e4a9f6a7f08febac2a9?f=json` — the "not intended to be used to export tiles for offline" clause
35. `https://www.arcgis.com/sharing/rest/search?q=title:"World Imagery (for Export)" owner:esri` — item `226d23f076da478bba4589e7eae95952`, subscription/developer-account requirement
36. `https://www.esri.com/content/dam/esrisites/en-us/media/legal/product-specific-terms-of-use/e300.pdf` — E300, 13 Nov 2025, footnotes 10 and 96 (read as PDF pages)
37. `https://www.esri.com/en-us/legal/terms/full-master-agreement` — E204/E204CW/E204SW/E300 index
38. `https://demotiles.maplibre.org/pmtiles/raster/style-imagery.json` + headers of `imagery.pmtiles` / `terrain.pmtiles` — EOX Sentinel-2 cloudless CC BY-NC-SA 4.0, maxzoom 10–11 `[m]`
39. `https://bhuvan-ras2.nrsc.gov.in/tilecache/tilecache.py?service=WMS&request=GetCapabilities` + tile probes at z12–z19 → `ivm.jpg` "Data not available" `[m]`
40. `https://api.openaerialmap.org/meta?bbox=…` → `found: 0` `[m]`; `https://raw.githubusercontent.com/opengeos/maxar-open-data/master/datasets.csv` `[m]`
41. `https://nasa-gibs.github.io/gibs-api-docs/access-basics/` — WMTS REST pattern, `GoogleMapsCompatible_Level12`
42. `https://www.mapbox.com/legal/tos` (no caching clause) and `https://www.mapbox.com/legal/product-terms` (effective 21 July 2026; PDF body **UNVERIFIED**)

**Navigation SDKs / Compose / recording**
43. `https://api.github.com/repos/stadiamaps/ferrostar` (+ releases, file tree, `LICENSE.txt`); `https://stadiamaps.github.io/ferrostar/android-getting-started.html`; `https://repo1.maven.org/maven2/com/stadiamaps/ferrostar/{ui-compose/maven-metadata.xml, ui-maplibre/0.54.0/ui-maplibre-0.54.0.pom}`
44. Ferrostar sources at tag 0.54.0: `runtime/NavigationCamera.kt`, `runtime/TrackingCameraEffect.kt`, `routeline/BorderedPolyline.kt`, `NavigationMapPuckStyle.kt`
45. `https://api.github.com/repos/maplibre/maplibre-navigation-android` (+ release 5.0.0 body, README); `https://repo1.maven.org/maven2/org/maplibre/navigation/{navigation-core,navigation-ui-android}/maven-metadata.xml`
46. `https://dl.google.com/dl/android/maven2/androidx/compose/compose-bom/{maven-metadata.xml, 2026.08.00/compose-bom-2026.08.00.pom}`; `androidx/compose/material3/material3/maven-metadata.xml`; `androidx/activity/activity-compose`, `androidx/lifecycle/lifecycle-runtime-compose`, `androidx/core/core-splashscreen`, `com/android/tools/build/gradle` metadata `[m]`
47. `https://developer.android.com/jetpack/androidx/releases/compose-material3`; `…/releases/compose`; `https://developer.android.com/develop/ui/compose/bom/bom-mapping`
48. `https://developer.android.com/develop/ui/compose/migrate/interoperability-apis/views-in-compose` — `AndroidView` signature and guidance
49. `https://developer.android.com/about/versions/16/behavior-changes-16` — edge-to-edge enforcement, predictive back, resizability
50. `https://developer.android.com/about/versions/15/behavior-changes-15` — `mediaProjection` FGS restriction from `BOOT_COMPLETED`
51. `https://developer.android.com/develop/ui/views/layout/immersive` — `WindowInsetsControllerCompat.hide(...)`, `BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE`
52. `https://www.samsung.com/us/support/answer/ANS10001616/` — screen recorder settings

**Fetch failures / marked UNVERIFIED**
- `repo1.maven.org` and `dl.google.com` return **403 to WebFetch**; all Maven facts were fetched with `curl` instead and are quoted from the raw XML/POM.
- GitHub **release binaries** (`release-assets.githubusercontent.com`) are blocked in this sandbox (`curl` exit 35), so `go-pmtiles` could not be executed here. The PMTiles numbers were produced by a from-scratch PMTiles v3 reader run against the live archives instead — arguably better evidence, since it measures the actual archive.
- `https://maplibre.org/maplibre-native/docs/book/android/pmtiles.html` → **404** (the PMTiles doc lives under `platform/android/docs/data/PMTiles.md`, published on the mkdocs site, not the mdBook).
- `https://maplibre.org/maplibre-compose/user-location/` → **404** (the page is `location`, not `user-location`).
- `https://www.esri.com/en-us/legal/terms/product-specific-terms-of-use` → **404** (the live PDF path is in item 36).
- Mapbox Product Terms PDF body — could not extract text. **UNVERIFIED.**
- `HapticFeedbackType` constant list for Compose 1.12.0 — **UNVERIFIED.**
- `ModalBottomSheet` / `BottomSheetScaffold` experimental status **in material3 1.4.0 specifically** — **UNVERIFIED.**
- `maplibre-compose` `FillExtrusionLayer` composable existence — **UNVERIFIED.**
- EOX Sentinel-2 cloudless resolution/latest-year/max-zoom from `cloudless.eox.at` — not stated on the landing page; the CC BY-NC-SA 4.0 licence and maxzoom 10–11 come from MapLibre's demo style and archive header instead.
- Android 14+ MediaProjection per-session consent, partial-screen capture, and `MediaProjection.Callback` requirements — **UNVERIFIED.**
- One UI 8 screen recorder frame rate (60 fps) — Samsung documents resolution only. **UNVERIFIED.**
