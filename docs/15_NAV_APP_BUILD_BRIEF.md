# IDR Nav — build brief

The final deliverable for SIH 26168 ("AI/ML intelligent dead reckoning for smartphones"): an Android app, **IDR Nav**, that shows a cyclist's position on a map at 10 Hz, keeps the marker moving with a learned speed model and gyro heading when GNSS is withheld, re-locks when GNSS returns, and records the on-device evidence needed for the demo video.

Written before the app existed. At that point the Python engine, the speed model, the ride data, the map data and the design direction were all finished and in this repository; nothing of the app was. This file is the specification the app was built against — every path, constant and acceptance test below was fixed in advance so the build could be measured rather than argued about. What was actually built, and where it deviates, is in `docs/16_APP_RESULTS.md`.

---

## 1. Read first (in this order, before writing code)

1. `docs/14_APP_PLAN_nav.md` — the agreed plan (v2), decisions and rationale. This brief supersedes it where they differ.
2. `docs/12_ENGINE_SPEC_for_kotlin.md` — the engine maths, v2 (joint model, heading without bias state, k off, LAG_V 0.2). The Python files it names are the truth: `engine/align.py`, `engine/heading.py`, `engine/filter.py`, `engine/corridor.py`, `engine/mapmatch.py`, `engine/replay.py`, `engine/session.py`, `engine/evaluate.py`, `engine/speed_model/train.py` (model definition), `engine/export/export.py` (Keras twin and TFLite export), `engine/export/resample_constants.json`.
3. `docs/research/R5_map_ui_references.md` — design direction and references; `docs/research/R6_map_stack_android.md` — Android map stack with exact versions and traps; `docs/research/R7_campus_map_data.md` — campus map data and satellite terms; `docs/research/R2_mobile_export.md` — LiteRT facts.
4. `IDRLogger/` — the existing logger app (Kotlin, XML Views). Reuse `LogService.kt` (sensor and GNSS plumbing, foreground service, wake lock), `StreamWriter.kt`, `Anchors.kt`, `SensorInventory.kt`, the manifest and Gradle setup. Read `docs/01_APP_SPEC_logger.md` and `docs/04_BUILD_BRIEF_logger_apk.md` for its design.
5. Data: `data/route1/sessions/*`, `data/route2/sessions/*` (raw sessions: `acc.csv`, `gyr.csv`, `gnss_fix.csv`, `gnss_status.csv`, `events.csv`, `session.json`; formats in `engine/session.py`), `data/route{1,2}/manifest.csv`, `data/processed/<session>/{track_100hz.csv, align.json, gnss_fixes.csv}`, `data/speed_model/pred/cnn_r100_w256_joint/<session>.csv` (held-out model predictions: `t_s, v_gnss, v_raw, sigma, still, v_model, phase`), `data/qa/replay/20260905_003612_SNU_AJB_AB_run1_corridor_mm0.csv` and `data/qa/replay/20260905_033817_SNU_AJB_AB_run4_corridor_mm0.csv` (conformance references, 10 Hz), `data/map/corridor_route1.geojson`, `data/map/corridor_route2.geojson`, `data/map/snu_osm_full.geojson`, `data/map/snu_buildings_ms.geojson`, `data/map/snu_campus_boundary.geojson`, `data/map/snu_osm_highways_900m.json`.
6. Model: `data/speed_model/models/cnn_r100_w256_joint_deploy.{pt,tflite,onnx}` and `cnn_r100_w256_joint_deploy_export.json` (norm constants, ops).

`engine/`, `data/speed_model/`, `data/route*/`, `data/processed/`, `docs/11` and `docs/12` are frozen inputs and are not modified by the app work. New scripts go under `tools/`, the app under `IDRNav/` (the `IDRLogger/` tree evolved in place: the applicationId stays `com.snu.idrlogger` so the phone's granted permissions survive, only the label changes to IDR Nav), and results to `docs/16_APP_RESULTS.md`.

## 2. Facts that are fixed (measured, do not re-derive)

- Phone: Samsung Galaxy S23 Ultra SM-S918B, Android 16 / One UI 8.5, 1080×2316 in the current display mode, Adreno 740. Connected over USB with developer options and USB debugging on. `adb` is at `~/Library/Android/sdk/platform-tools/adb` (not on PATH). JDK 21 at `/opt/homebrew/opt/openjdk@21` (not on PATH). Android SDK at `~/Library/Android/sdk` (platforms 36, 37; build-tools 35–37). No Android Studio. Gradle wrapper 8.14.3 in `IDRLogger/`, AGP 8.13.2, Kotlin 2.2.10, compileSdk 36, targetSdk 35, minSdk 29. Build with `export JAVA_HOME=/opt/homebrew/opt/openjdk@21 ANDROID_HOME=$HOME/Library/Android/sdk; ./gradlew assembleDebug` then `adb install -r`.
- Sensors on this phone: accelerometer and gyroscope deliver 418.8 Hz (LSM6DSO, minDelay 2404 µs; requesting 2000 µs is clamped), zero gaps in 33 recorded sessions; GNSS fixes 1 Hz at 3.8 m median accuracy, 26–46 satellites used; `TYPE_GEOMAGNETIC_ROTATION_VECTOR` does not exist; the magnetometer is unusable (steel frame) and is never used; carrier phase is unusable. Keep the system microphone toggle on or motion sensors are rate-limited. Logging costs 10.8 MB/min.
- Mount: phone in the bottle cage of the bike, screen fully visible (no band constraint), pitch about 22–26° along the down tube; alignment absorbs it per session.
- Model (spec §8): one joint CNN `cnn_r100_w256_joint_deploy` (57,602 parameters, 240 KB TFLite, ops CONV_2D ×4, FULLY_CONNECTED ×2, MEAN, PAD ×4, RESHAPE/EXPAND_DIMS), input `[1, 256, 6]` float32 = the last 2.56 s of bike-frame `[ax, ay, az, gx, gy, gz]` at 100 Hz with gravity and gyro bias left in, per-channel z-score with mean `[0.03391, 0.00139, 9.30145, 0.00019, -0.0067, -0.00014]` and std `[1.04142, 1.31722, 1.56807, 0.14452, 0.06602, 0.19358]`; output `[μ, log σ²]`, `v = max(μ, 0)`, `σ = exp(0.5·clamp(log σ², −6, 4))`; μ is the speed at the window end. Architecture: Conv1d 6→32 k7 s2, 32→64 k5 s2, 64→64 k5 s2, 64→96 k3 s2 (symmetric zero padding k//2, BatchNorm eps 1e-5, ReLU), global average pool, Dense 96→64 ReLU, Dense 64→2. Held-out speed MAE 0.179 m/s (route 1) / 0.164 (route 2). Physical stop rule overrides it: vibration RMS < 0.6 m/s² and gyro RMS < 0.06 rad/s over the last 0.5 s. Latency budget 5 ms per tick; Mac single-thread LiteRT 0.066 ms.
- Engine (spec v2): 100 Hz IMU after a causal 4th-order Butterworth at 40 Hz (SOS in `resample_constants.json`) and linear sampling to the 10 ms grid; alignment per §3 (stand gravity → R1; ψ_init from the first speed-up; sway-axis ψ after 20 s of motion, recomputed every 10 s; ride-time gravity in 10 s blocks; moved-phone rule 3°); heading `kfpsic` per §4 (quaternion at 100 Hz, gated tilt correction τ 10 s, course measurement from consecutive fixes at v > 1.5 m/s on straight segments, 5σ gate, 5-rejection reset, robust stand bias held; bias state only if the stand was not quiet, then no outage trusted before 60 s after motion start); fusion per §5 (corridor `[s, v, k]` or general `[px, py, v, k]`, 10 Hz, SIG_A 1.0, SIG_M_FLOOR 0.15, SIG_VG 0.3, SIG_ZUPT 0.05, LAG_POS 0.5, LAG_V 0.2, REC_INFL 4 for REC_S 3 s, gate 5σ, N_REJECT 5, **k off**); corridor §6; map matcher §7 display-only; real-outage detector: fix gap > 1.5 s, or accuracy > 30 m, or satellites used < 4 on two consecutive epochs, or mean C/N0 of used signals < 22 dB-Hz, or the simulated flag. Modes: GNSS_INS, INERTIAL, RECOVERING (first 3 s after return). The displayed track is never rewritten. Off-corridor fallback: |d| > 15 m on 3 consecutive healthy fixes → general mode initialised at the fix.
- Conformance (spec §9): fed the reference session files, the Kotlin engine must match the reference CSV with max |Δposition| < 1.0 m over the whole session, mode transitions within ±0.2 s, heading within 1°, model speed within 0.02 m/s. Reference results: route-2 run 4, outage from motion start + 30 s to the end: 789 m / 218 s, endpoint 20.7 m; route-1 run 1: 229 m / 82 s, endpoint 6.7 m.
- Corridors: route 1 `corridor_route1.geojson` (37 vertices, 339 m with 15 m overhangs; A at s = 15.0, B at s = 334.9; S-bend at s ≈ 80/106/132 then an arc 168–248); route 2 `corridor_route2.geojson` (41 vertices, 927 m incl. a 20 m overhang at the north end; s = 0 at the Shivaji Park end, anchors A (28.525945, 77.570652) and north end (28.527123, 77.577232); one 120° junction at s = 464). Both validated against every run (median lateral offset 1–2.6 m).
- Route-2 A→B means Shivaji Park end → Cricket Ground road → library junction → 2011 Street → north up Circular Road; rides 207–291 s at 3.4–4.0 m/s. Route 1 is the football-ground road, 320 m, rides 65–115 s.

## 3. Product decisions (settled)

1. One app, two modes: IDR Nav (the ride screen) plus the existing Logger as a tab. Every nav ride keeps logging all 22 streams exactly as the logger does, plus `engine_out.csv` (10 Hz: `t_s, lat, lon, x_m, y_m, v, heading_deg, mode, sim, k, sigma_pos, v_model, sigma_model, stop, tick_ms, model_ms, corridor_id, s_m, d_m`) and `engine_events.csv` (state changes, scenario arm/entry/exit, reveal figures, real-outage triggers). `session.json.route_id` is `SNU_R1`, `SNU_R2` or `FREE` (fixes the old `SNU_AJB` collision).
2. **Nothing to pick on the main screen.** The app behaves like a general bike nav app. It carries a library of learned corridors (`assets/corridors/*.json`); once healthy GNSS shows the rider on a library corridor for 8 consecutive fixes within 15 m, the engine switches to corridor mode silently, otherwise it runs general mode with display-only map matching on the campus graph. The word "corridor" appears only in the engine sheet ("Positioning: corridor · Circular Rd (learned)").
3. **Hidden Field-test screen** (long-press the version line in Settings): scenario per corridor and direction (band start/end in metres from the ride start, timer, or manual), replay of a recorded session at 1×/4×/max, reveal on/off, engine sheet on/off, logging on/off, sensor inventory, and a conformance self-test that runs a reference session and prints max |Δpos|. When a scenario is armed the ride screen shows only a small "SIM" tag beside the state chip (honesty; a real outage shows no tag) and, once the direction is known, the "No GNSS" band drawn on the map as a hatched red band that reads like a tunnel marking.
4. The denial gate decides on the raw GNSS fix (inside the band → withheld) and the engine sees nothing while inside, exactly as `engine/replay.py --polygon` does; the real-outage detector stays active underneath at all times.
5. Positioning uses `GPS_PROVIDER` only, never the fused/network provider; the engine sheet states "Fix source: GNSS chipset". Airplane mode is optional.
6. **The re-lock reveal instead of a live ghost dot**: during the denial the viewer sees only what the engine sees. When GNSS returns, the withheld true path fades in for 6 s as a thin dotted white line under the dashed estimate with one figure ("Off by 4.6 m after 671 m without GNSS"), then fades out. The engine sheet keeps the live error for us.
7. Satellite = an **online** toggle: Esri World Imagery through a MapLibre raster source (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`, maxzoom 19, attribution "Esri, Maxar, Earthstar Geographics"), relying only on the SDK's normal ambient cache. Never bulk-download or bundle Esri tiles (their terms forbid export; z20+ returns a 2,521-byte placeholder). In satellite mode draw no roads and no extrusions: corridor band, trail, puck, labels with halos only. The offline claim rests on the vector map.
8. Sync for the video: a SYNC flash (three 120 ms white frames) and three tones at START, at band entry and at band exit, so the screen recording and the camera align by audio or by the flash.
9. Readiness ("ARMED") = heading initialised from a course fix ∧ sway-axis ψ available (≥ 20 s of motion) ∧ GNSS healthy ≥ 5 s ∧ model window full ∧ (stand quiet, or ≥ 60 s since motion start). If the band is entered before ARMED, GNSS is still withheld (honest) but the status line says "estimating, not yet aligned" and the result is flagged in the summary.

## 4. Design language (binding; improve within it, do not drift out of it)

Register: a tool operated at a glance on a moving bicycle, outdoors, often in sun. Material 3 governs structure and components; the brand lives in the map and the details. The v2 mockup (five frames on the route-2 demo take) is the reference for feel.

Tokens (single dark world by use scene; paint every colour explicitly):
- Map ground #101010 · buildings sides #181818 / tops #232323 (extruded: `height`, else `building:levels × 3.2`, else 6 m; hostels are 6 levels, Blocks A–D 4) · water #1F262B · sports fields #151B16 with #1C241D edge · road casing #1A1A1A · road fill #2E2E2E (service) / #383838 (main) · footways #202020 dashed · labels #8C8C8C with a 1.2 px #101010 halo.
- State: locked #9BE8C4 · dead-reckoning #FFB454 · re-locking #7FD3FF · no-GNSS band #FF5A5F at 22 % with a 45° hatch · reveal #FFFFFF at 72 % dotted.
- Surfaces: #1A1A1A card, #242424 raised, text #F2F2F2 / #A9A9A9. Tonal elevation, no glass, no glow halos, no gradients on text, no pulsing.
- Type: Barlow (Google Fonts, bundle the TTFs): Barlow Semi Condensed 600 for the speed figure (64–72 sp), Barlow 500/400 for everything else, tabular figures wherever numbers change; Roboto fallback. Material type scale in sp.
- Trail: 3 dp; solid in the locked colour; **dashed** (8/5) in amber while dead-reckoning, with a translucent ribbon under it whose width is 2σ of the filter's position (min 4 dp); the trail is never rewritten.
- Layout: full-screen map, edge-to-edge with insets. Top-left: one chip (state dot + text: "GNSS locked · 14 satellites" / "Dead reckoning · 360 m · 1:38" / "Re-locking · 14 satellites") plus the SIM tag when armed. Top-right: one round compass/follow control. Bottom: a low card, never above 28 % of the height, with the speed figure, unit and one line ("0.56 km · 2:19"; second line: street name or "Position from motion sensors"); pull it up for the engine sheet as a Material bottom sheet. START, hold-to-STOP (800 ms) and the stand countdown live in that card area. 48 dp touch targets.
- Camera: course-up, pitch 45–55°, puck at 30–35 % from the bottom (Ferrostar constants: zoom 18, tilt 45°, 50 % top padding), zoom 18.6 at rest → 17.2 at 8 m/s, bearing eased over 300 ms; compass tap = north-up; drag frees the camera and auto-recentres after 6 s.
- Motion: one authored moment, entering dead reckoning (trail style switches at the puck, the cone hue crossfades to amber, the status line slides in; 400 ms, exponential ease-out) and the re-lock reveal. Respect Reduce Motion.
- Copy: the product's own words. "GNSS locked", "Dead reckoning", "Re-locking", "No GNSS ahead · 40 m", "Off by 6 m after 204 m without GNSS", "Hold still, brakes on · 12 s". Never INERTIAL/SIMULATED in caps on the ride screen.
- Do not: blue-grey grounds, glow halos, pulsing chips, sparklines in the HUD, monospace as a costume, eyebrow labels, identical card grids, emoji or unicode glyphs as icons (draw them), toolbars of equal buttons, route pickers on the main screen.

**The puck (it must look like a top navigation app's).** Draw it in Compose (a Canvas overlay at the tracking screen point; hide MapLibre's location layer), not as a flat sprite:
- Form: a beveled arrowhead "blade", 30 dp long × 22 dp wide, three facets: a lit top face (state colour → 85 % of it, top-to-bottom), left and right bevels at 60 % of the state colour, a 2 dp near-white (#F4F4F4) outline for legibility on imagery, and a real shadow with offset (0, 3 dp), blur 6 dp, 35 % black. Squash it by cos(pitch) so it lies on the road like a 3-D object; rotate with heading using a critically damped spring (~250 ms). Render three or four variants (blade, teardrop, chevron with a disc, Google-style beam + dot) as bitmaps, screenshot them on the device over the real map, pick the one that reads best at arm's length, and write down why in `docs/16`.
- Headlight cone: a 60 m wedge on the road ahead in the state colour with a radial fade (42 % at the puck → 0), whose **half-angle encodes heading confidence**: 12° when the heading filter's σψ < 2°, widening to 35° at σψ ≥ 10° (the same idea as Google Maps' 2022 beam, here driven by our own filter).
- Stopped: after 2 s at v = 0 the blade morphs into a 14 dp disc with a dim cone (direction is meaningless when stopped); it grows back on motion.
- Accuracy ring only when σpos > 3 m, 1 dp dashed, never a filled circle.

Design process rules (from the R5 §3 checklist, applied by hand): build fully, then verify in bounded passes on the device (`adb exec-out screencap -p`), including dark theme and font scale 1.3 (`adb shell settings put system font_scale 1.3`, restore 1.0), fix in one batch, confirm once, stop polishing. Contrast ≥ 4.5:1 for text. Theme the parts you did not draw (focus, ripples, numerals).

## 5. Screens

1. **Ride**: as in §4. Chip, SIM tag, compass, map, card, engine sheet. Controls in the card: START (before a ride), hold-to-STOP (during), the 15 s stand countdown ("Hold still, brakes on · 12 s") with the alignment settling in the status line (pitch, gyro bias, satellites).
2. **Ride summary** after the end stand: distance, time, every outage with its reveal figures (distance, duration, endpoint error, max error, recovery step), files saved, share.
3. **Settings**: units, map style (night / satellite), rider name, sync flash on/off, screen insets, version line (long-press → Field test).
4. **Field test** (hidden): §3.3.
5. **Logger** tab: the existing logger UI, unchanged in behaviour.

## 6. Architecture and modules

```
IDRNav/                     (Gradle project; keep applicationId com.snu.idrlogger)
  engine/                   pure-Kotlin JVM module, no Android imports, fixed-size arrays, no per-sample allocation
     Resampler.kt           gyro interpolated onto accelerometer times, causal SOS Butterworth 40 Hz, 10 ms grid
     Aligner.kt             stand gravity + robust bias; R1 (Rodrigues); ψ_init, sway-axis ψ; ride-time gravity blocks; moved-phone rule
     HeadingFilter.kt       kfpsic per spec §4 (+ non-quiet-stand mode)
     SpeedModel.kt          window ring buffer, z-score, CNN forward pass in Kotlin (BN folded), stop rule; interface so LiteRT can plug in
     Fusion.kt              corridor + general modes per spec §5, delayed-state updates, ZUPT, recovery inflation
     Corridor.kt            polyline in ENU, project/point/tangent/heading, off-corridor rule
     MapMatcher.kt          HMM over the campus graph, 2 Hz, 3 s lag, display only
     Gate.kt                real-outage detector + scenario gate (band / timer / manual) + mode machine + ARMED readiness
     Engine.kt              the 100 Hz step + 10 Hz tick orchestration; produces EngineState
     replay/SessionReader.kt reads a raw session folder (acc/gyr/gnss_fix/gnss_status/events) and drives Engine at 1×/4×/max
  app/
     service/NavService.kt  foreground service (type location), reuses LogService plumbing; SensorHub → engine thread; GnssHub (GPS_PROVIDER + GnssStatus) → engine thread; logging
     model/LiteRtSpeedModel.kt  LiteRT 2.2.0 interpreter, XNNPACK, 1 thread; latency measured per call
     map/                   MapLibre style loader (PMTiles + our GeoJSON layers), camera controller, overlay sources at 10 Hz, satellite raster source
     ui/                    Compose: RideScreen, Puck (Canvas), EngineSheet, Summary, Settings, FieldTest, Logger tab (AndroidView of the old layout or a port)
     assets/                corridors/*.json, model/{weights.bin, model.json, cnn_r100_w256_joint_deploy.tflite}, map/{snu.pmtiles (copied to filesDir on first run), style.json, glyphs/, sprites/, buildings.geojson, campus.geojson, roads.geojson}
tools/
     export_weights.py      reads data/speed_model/models/cnn_r100_w256_joint_deploy.pt → assets/model/weights.bin (float32 LE) + model.json (shapes, order, norm, version)
     make_map_assets.py     builds the GeoJSON asset files from data/map/*.geojson (dedupe "Dining Hall 3", drop type=route relations, merge Microsoft footprints where OSM has none, compute heights)
     extract_pmtiles.sh     pmtiles extract of the Protomaps daily planet for bbox 77.5639,28.5133,77.5823,28.5335 at maxzoom 15 (≈ 0.85 MB); fetch Protomaps v4 dark style, glyphs (Noto, ranges 0–255 and 256–511) and sprites
     compose_video.sh       ffmpeg side-by-side with an audio offset
```
Threads: sensors on the URGENT_AUDIO HandlerThread (as today) → lock-free ring → one engine thread (100 Hz step, 10 Hz tick) → `StateFlow<EngineState>` → UI on the main thread; GNSS callbacks post into the engine thread. The engine never allocates per sample. Model pack: `model.json` + `weights.bin` are the truth for the Kotlin path; the `.tflite` is the LiteRT path; both must agree with the Python predictions.

## 7. Scenarios (measured 5 Sep 2026 on held-out replays; zones in metres from the ride's own start so one entry serves both directions)

| Corridor | Direction | Band | Expected (median / worst over held-out runs) |
|---|---|---|---|
| SNU_R2 (route 2) | A→B (Shivaji end → north) | 200 m → stop | 0.7 % / 4.4 % drift, 4.6 m median end error over 671 m / 178 s. **The demo take.** |
| SNU_R2 | B→A | 200 m → stop | 2.9 % / 6.6 %, ~19 m |
| SNU_R1 (route 1) | either | 110 m → stop | 4.5 % / 7.3 %, ~9 m over ~200 m / 50 s |
| FREE | n/a | timer: 40 s after motion start, hold 90 s | general mode, display-matched; expect more drift and say so |

`assets/corridors/SNU_R2.json` example: `{ "id": "SNU_R2", "name": "Circular Rd", "geojson": "corridor_route2.geojson", "anchors": {"A": [28.525945, 77.570652], "B": [28.527123, 77.577232]}, "overhang_m": {"A": 0, "B": 20}, "scenarios": {"AB": {"band_from_m": 200, "band_to_m": null}, "BA": {"band_from_m": 200, "band_to_m": null}} }`. Direction is detected from the arc-length progression of the first 8 healthy fixes (spec §5.2).

## 8. Map stack (from R6; exact)

- `org.maplibre.gl:android-sdk-vulkan-opengl:13.6.0` in an `AndroidView` (do not use `maplibre-compose`: incompatible toolchain). Compose BOM `androidx.compose:compose-bom:2026.08.00` (ui 1.12.0, material3 1.4.0), `androidx.activity:activity-compose:1.13.0`, `androidx.lifecycle:lifecycle-runtime-compose:2.11.0`, `androidx.core:core-splashscreen:1.2.0`. LiteRT `com.google.ai.edge.litert:litert:2.2.0`.
- Basemap: PMTiles extract (Protomaps daily planet, z0–15, ≈ 0.85 MB) opened as `pmtiles://file://<filesDir>/snu.pmtiles` after copying from assets on first run (`pmtiles://asset://` is unsupported; there is no `mbtiles://`). Style: Protomaps v4 dark (`style@4.4.0`) recoloured to the §4 tokens, `text-font` pointing at bundled glyphs (`asset://glyphs/{fontstack}/{range}.pbf`) and sprites (`asset://sprites/dark`); the flat `buildings` layer replaced by our own `fill-extrusion` layer from `buildings.geojson` (`height` property). Our layers on top: campus boundary, sports fields, water (from the extract where the tiles are too coarse), building name labels, corridor band (hatched), trail (two line layers: solid locked, dashed dead-reckoning), ribbon (line with data-driven width = 2σ), reveal (dotted line, opacity animated), all `GeoJsonSource` with `setOverrideSynchronousUpdate(true)` updated at 10 Hz from the engine thread's state on the main thread.
- Puck: Compose Canvas overlay at the fixed tracking point (§4); MapLibre's location component is not shown. Camera: `CameraMode.TRACKING_GPS` with `zoomWhileTracking`/`tiltWhileTracking`/`paddingWhileTracking`, or explicit `easeCamera` calls at 10 Hz if tracking mode fights the 10 Hz feed; measure and pick. If the `pmtiles` CLI cannot be installed, the R6 report documents the PMTiles v3 directory walk and a reader can be written against it.
- Satellite: raster source as in §3.7, `raster-opacity` 1, our overlays on top, roads and extrusions hidden.

## 9. Replay and conformance (the gate before any road test)

1. JVM: `./gradlew :engine:test` runs `SessionReader` on the two reference sessions with the outage from motion start + 30 s to the end, corridor mode, k off, first with speed from `data/speed_model/pred/cnn_r100_w256_joint/<session>.csv` (isolates the filter/heading/alignment maths) and then with the Kotlin CNN on the resampled windows (isolates the model). Assert spec §9 tolerances against the reference CSVs. Print max |Δpos|, heading error, mode transition times, speed error.
2. Device: push the same sessions to `/sdcard/Android/data/com.snu.idrlogger/files/replay/`, start Replay from Field test at max speed, pull `engine_out.csv`, diff against the JVM run and the reference; measure tick and model latency (LiteRT and Kotlin) and write both in `docs/16`.
3. Bench: phone on the desk by a window, live sensors, 10 min: rates ≥ 400 Hz, GNSS healthy, UI 60 fps (`adb shell dumpsys gfxinfo com.snu.idrlogger`), thermal status, battery slope, no dropped rows. Trigger a manual denial and a timer denial; check the mode machine, the band drawing, the reveal and the summary.
4. Only then the road: route 2 A→B with the scenario armed, two or three rides; pull each session and replay it in Python (`.venv/bin/python engine/replay.py --session <dir> --pred cnn_r100_w256_joint --tag route2 --outage <t0>,<t1>`) and on the JVM; the on-device `engine_out.csv` must match to the same tolerances. Then route 1, then a free ride.

## 10. Phone workflow (all from this Mac)

```
export JAVA_HOME=/opt/homebrew/opt/openjdk@21 ANDROID_HOME=$HOME/Library/Android/sdk PATH=$HOME/Library/Android/sdk/platform-tools:$PATH
adb devices -l                                   # SM-S918B must be listed; if unauthorized, the phone shows the RSA prompt
./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.snu.idrlogger/.MainActivity
adb logcat -s IDR                                # engine + service logs
adb exec-out screencap -p > /tmp/shot.png        # look at every screen you build
adb shell screenrecord --time-limit 60 /sdcard/rec.mp4 && adb pull /sdcard/rec.mp4
adb push data/route2/sessions/20260905_033817_SNU_AJB_AB_run4 /sdcard/Android/data/com.snu.idrlogger/files/replay/
adb pull /sdcard/Android/data/com.snu.idrlogger/files/sessions/<session> data/field/
adb shell cmd uimode night yes; adb shell settings put system font_scale 1.3   # verification passes; restore 1.0
```
Samsung settings to keep for the field ride: app Battery → Unrestricted, Location → Allow all the time, microphone toggle on, screen timeout long, adaptive brightness off for the video, One UI screen recorder at 1080p 60 fps with media sound and no touches. Remember the logger's trap: the theme parent is MaterialComponents, so any XML `<Button>` becomes a MaterialButton that ignores `android:background`; use `AppCompatButton` in the Logger tab layouts.

## 11. Acceptance (all must hold; report each with its number)

1. JVM conformance on both reference sessions: max |Δpos| < 1.0 m, modes ±0.2 s, heading < 1°, model speed < 0.02 m/s (Kotlin CNN vs Python predictions on the same windows).
2. LiteRT output equals the Kotlin CNN within 1e-4 on 500 real windows; per-window latency < 5 ms single-thread on the phone for both paths (report both).
3. Device replay of route-2 run 4 reproduces the JVM run within 0.5 m; the ride screen shows the band, dead reckoning, and the reveal with the right figure.
4. Live bench: acc/gyr ≥ 400 Hz for 10 min, zero dropped rows, engine tick ≤ 2 ms mean, UI ≥ 55 fps with the map moving, no ANR, service survives screen-off with the wake lock.
5. Scenario gate: entering the band withholds GNSS on the raw fix; the real-outage detector still fires on a real gap; recovery inflation and the 3 s RECOVERING window behave per spec; the displayed trail is never rewritten.
6. Corridor recognition: on the route-2 replay the engine reports the corridor within 10 s of motion start with the correct direction; on a session outside both corridors it stays in general mode.
7. Logging: a nav ride writes the 22 logger streams plus `engine_out.csv` and `engine_events.csv`, `route_id` set, summary shows anchors and rates, zip/share works.
8. Design pass done on the device in dark theme and at font scale 1.3, screenshots saved under `docs/screens/`, the puck variant chosen and justified, no text clipped, contrast ≥ 4.5:1, 48 dp targets.
9. Satellite toggle works online with attribution; airplane mode with Location on still positions from the GNSS chipset.
10. `docs/16_APP_RESULTS.md` written: what was built, every measured number above, latency, screenshots, deviations from this brief and why, the field-ride protocol, the ffmpeg command, and open items.

## 12. Build order (gates, not a schedule)

1. `tools/export_weights.py` + `:engine` module + JVM conformance (gate 11.1). The PMTiles/style/glyph extract and the map-asset preparation are independent of this and can run alongside it.
2. NavService with SensorHub/GnssHub, the engine thread, logging, and `SessionReader` replay through the same path (gate 11.3 on the device).
3. Map: style + layers + camera + overlay sources; then the ride screen and the puck (gate 11.8 first pass); LiteRT path + latency (gate 11.2).
4. Field test screen, scenarios, gate, reveal, summary, settings, Logger tab, sync flash (gates 11.5–11.7).
5. Bench (11.4), satellite (11.9), design verification pass, `docs/16` (11.10).

## 13. Field protocol and video (write into docs/16 as the checklist for the rider)

Stand still 15 s with brakes held and no turning at both ends; ride ≥ 30 s normally before the band; do not touch the phone; one ride per direction per road; one ride with a full stop inside the band. Camera: phone 3 in a handlebar holder facing forward, 1080p60; screen recording started before START; align on the SYNC beep. Assemble: `ffmpeg -i cam.mp4 -itsoffset <offset_s> -i screen.mp4 -filter_complex "[0:v]scale=-2:1080[a];[1:v]scale=-2:1080[b];[a][b]hstack" -c:v libx264 -crf 18 out.mp4`. Fallback: an on-device replay of a fresh recorded ride, labelled REPLAY.

## 14. Do not

Do not use the magnetometer or integrate the accelerometer for speed. Do not feed map matching back into the estimate. Do not turn k on. Do not bundle Esri tiles. Do not show route or scenario choices on the ride screen. Do not rewrite the displayed trail. Do not quantise the model. Do not change anything under `engine/` or `data/`. Do not claim a number you did not measure; label every illustrative value as an example.
