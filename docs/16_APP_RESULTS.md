# 16 — IDR Nav: build results, measurements, deviations, field protocol

Built 5 Sep 2026 (16:20–22:30 IST) from `docs/15_NAV_APP_BUILD_BRIEF.md`. Everything below was measured on this Mac (M2 Pro, JDK 21) and on the connected Samsung Galaxy S23 Ultra (SM-S918B, Android 16) unless a line says otherwise. Illustrative values are labelled as such; there are none in the tables.

## 0. Status against the acceptance list (handoff §11)

| # | Acceptance | Result | Where |
|---|---|---|---|
| 11.1 | JVM conformance on both reference sessions: max Δpos < 1.0 m, modes ±0.2 s, heading < 1°, model speed < 0.02 m/s | **PASS.** Route-2 run 4: max Δpos **0.007 m**, heading **0.154°**, modes **0.00 s**. Route-1 run 1: **0.006 m**, **0.047°**, **0.00 s**. Kotlin CNN vs PyTorch on 500 real windows: max Δμ **1.2e-6**, Δv **1.2e-6 m/s** | §3.1, §3.2; `./gradlew :engine:test` |
| 11.2 | LiteRT = Kotlin CNN within 1e-4 on 500 windows; < 5 ms per window on the phone, both paths | **PASS.** max LiteRT − Kotlin **1.9e-6**; LiteRT **0.074 ms** median / 0.086 p95; Kotlin CNN **1.41 ms** median / 1.71 p95 (SM-S918B, 1 thread) | §4 |
| 11.3 | Device replay of route-2 run 4 reproduces the JVM run within 0.5 m; band, dead reckoning and reveal shown with the right figure | **PASS.** Device (LiteRT) vs JVM (Kotlin CNN): max Δpos **0.001 m**, heading 0.000°, Δv 0.001 m/s over 2977 ticks; band, dashed trail + ribbon, reveal "Off by 17.3 m after 569 m without GNSS" on screen | §3.3, §6 screenshots |
| 11.4 | Live bench 10 min: acc/gyr ≥ 400 Hz, zero dropped rows, tick ≤ 2 ms mean, UI ≥ 55 fps, no ANR, service survives screen-off | **PASS** on the desk: 629 s, acc/gyr **418.85 Hz**, **0 gaps, 0 dropped rows**, tick **0.83 ms mean** (p99 1.35, max 4.05 ms), map **120 fps** / Compose 115 fps with the map moving, thermal status 0, no ANR; screen-off ride logged through 75 s of doze without a gap. GNSS gave no fix indoors (see §7) | §7 |
| 11.5 | Scenario gate on the raw fix; real-outage detector still fires; recovery inflation + 3 s RECOVERING; trail never rewritten | **PASS** (JVM tests `BandScenarioTest`, `RealOutageTest`): band withheld at 96.1 s while armed; a forced 10 s fix gap fires REAL_OUTAGE at 100.6 s without the SIM flag, RECOVERING 111.1→114.1 s (3.0 s), reveal after the real gap "off 3.3 m after 41 m"; the trail is only ever appended | §5 |
| 11.6 | Corridor recognised within 10 s of motion start with the right direction; general mode outside the library | **PASS.** Route 2: corridor at t = 8.1 s (during the stand), direction A→B at 37.1 s = motion start + 1.0 s; route 1: corridor at 7.3 s, direction at motion start + 1.0 s (device and JVM identical). Route-1 session against a library holding only route 2: stays `general` for the whole ride, 13 % of ticks map-matched with confidence | §5 |
| 11.7 | Nav ride writes the 22 logger streams + `engine_out.csv` + `engine_events.csv`, `route_id` set, summary, zip/share | **PASS**: 24 files per ride (21 present logger streams — geomagrot does not exist on this phone — + engine_out + engine_events + session.json), `route_id`/`direction`/`speed_model` in session.json, summary screen with outages and files, Zip + share through the FileProvider | §7 |
| 11.8 | Design pass on the device, dark theme + font scale 1.3, screenshots in `docs/screens/`, puck chosen and justified, no clipping, contrast, 48 dp targets | **DONE.** 26 screenshots; puck = Blade (§6.2); font scale 1.3 wraps without clipping; one label/value spacing fix applied afterwards | §6 |
| 11.9 | Satellite online with attribution; airplane mode + Location on still positions | Satellite **PASS** (Esri imagery renders under our overlays, attribution in Settings and on the map). Airplane mode: **inconclusive indoors** (no GNSS fix at the desk before, during or after the 64 s window); the app requests `GPS_PROVIDER` only, so it must be confirmed on the first field ride | §6, §7 |
| 11.10 | This document | this file | — |

Everything in the handoff was built. Two things are honestly weaker than the brief's wording and are explained in §8: the raw phone path differs from the Python reference by a few metres because the reference used a batch alignment (the maths path matches to 7 mm), and the brief's prediction files were not the ones that produced the reference CSVs.

## 1. What was built

```
IDRNav/                              Gradle 8.14.3 · AGP 8.13.2 · Kotlin 2.2.10 · compileSdk 36 · minSdk 29 · applicationId com.snu.idrlogger (unchanged)
  engine/  (pure Kotlin JVM, no Android imports, fixed arrays, no per-sample allocation)          1 830 lines
     Geo.kt            ENU origin, wrap, Rodrigues, Euler
     Resampler.kt      gyro→accel time interpolation, causal 4th-order Butterworth 40 Hz (2 SOS, DF2T, DC steady-state start), 10 ms grid
     Aligner.kt        stand gravity + robust bias + quiet check; ψ_init (first speed-up), sway ψ (20 s, every 10 s), ride-time gravity blocks, moved-phone rule
     HeadingFilter.kt  kfpsic: quaternion @100 Hz, gated tilt (τ 10 s), course measurement (v > 1.5, 1.5 s after turns), 5σ gate, 5-rejection reset; bias state only for a non-quiet stand
     SpeedModel.kt     model pack loader, Kotlin CNN (BN folded, weights transposed to [ci][k][co]), 256×6 ring, stop rule, CNN / prediction-CSV speed sources
     Fusion.kt         corridor [s,v,k] and general [px,py,v,k] filters, delayed-state GNSS updates (LAG_POS 0.5, LAG_V 0.2), ZUPT, recovery inflation ×4 for 3 s, k off
     Corridor.kt       corridor library entry + ENU polyline (project / point / tangent / heading)
     MapMatcher.kt     Newson–Krumm HMM on the campus graph, 2 Hz, 3 s lag, display only
     Engine.kt         100 Hz step + 10 Hz tick orchestration, gate (band / timer / manual + rule-1 detector), corridor recognition and off-corridor fallback, readiness, outage bookkeeping, EngineState
     replay/SessionReader.kt   raw session folder → engine at 1×/4×/max; ProcessedTrackReader for the maths-only conformance
     tests: ConformanceTest (levels A, C, recognition, band scenario, real gap, resampler experiment), ModelTest
  app/     (Kotlin + Compose BOM 2026.06.01 / Material 3 1.4.0 + MapLibre 13.6.0 vulkan-opengl + LiteRT 2.2.0)     3 700 lines
     LogService.kt     the logger service evolved: nav mode (engine thread fed from the sensor and GNSS threads), replay mode, manual denial, engine_out / engine_events streams, route_id patch
     service/EngineRunner.kt   SPSC rings → engine thread ("idr-engine", URGENT_DISPLAY), NavLive StateFlow/SharedFlow, CSV rows
     model/LiteRtSpeedModel.kt CompiledModel, Accelerator.CPU, CpuOptions(numThreads = 1), buffers allocated once, 20 warm-up runs
     map/MapAssets.kt  pmtiles copy to filesDir, style injection (Esri raster, campus GeoJSON layers, band/ribbon/trail/reveal/cone sources, 3-D buildings, label layers)
     map/MapController.kt  eased course-up camera (pitch 50°, zoom 18.6→17.2 by speed, top padding 35 %), trail/ribbon/cone/band/reveal sources at 10 Hz, satellite toggle
     ui/  Theme (tokens, Barlow), Puck (4 variants, spring rotation, stop morph, accuracy ring), RideScreen, EngineSheet, Screens (Settings, Field test, Summary, conformance compare, model bench), LoggerPanel (old logger as a hosted View), AppModel (prefs, service intents, SYNC tones)
     NavActivity.kt    edge-to-edge, tabs Ride / Logger / Settings, hidden Field test (long-press the version line), debug prefs receiver
     DebugReceiver.kt  adb entry point for tests (debug builds only)
     assets/ corridors (SNU_R1, SNU_R2 + GeoJSON), model (weights.bin 224 KB, model.json, .tflite 236 KB, 500 fixture windows 2.9 MB), map (snu.pmtiles 812 KB, style.json, buildings/campus/features/labels/roads GeoJSON, graph.json), glyphs 620 KB, sprites 52 KB; res/font Barlow ×3
tools/   export_weights.py (model pack + fixtures, verified fold 1.4e-6), make_map_assets.py, extract_pmtiles.sh, make_style.py, compare_engine_out.py, compose_video.sh
docs/qa_app/   JVM engine_out for the reference session; docs/screens/ 26 screenshots
data/field/device_replay/   pulled device replays; data/field/bench/ the bench ride
```

APK (debug): **81.3 MB** with the arm64-v8a filter (166 MB with all four ABIs: MapLibre ships both rendering backends and LiteRT its natives); a copy of the installed build is `docs/IDRNav-debug-arm64.apk`. Offline map payload 1.5 MB.

## 2. Build and run

```
export JAVA_HOME=/opt/homebrew/opt/openjdk@21 ANDROID_HOME=$HOME/Library/Android/sdk PATH=$HOME/Library/Android/sdk/platform-tools:$PATH
cd IDRNav && ./gradlew :engine:test            # JVM conformance + model tests (~20 s)
./gradlew :app:assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.snu.idrlogger/.NavActivity
adb logcat -s IDR
# push a session for on-device replay / conformance
adb push data/route2/sessions/20260905_033817_SNU_AJB_AB_run4 /sdcard/Android/data/com.snu.idrlogger/files/replay/
# adb-driven replay (debug builds): scenario band|timer|manual|none, replay_speed 0 = max
adb shell am broadcast -a com.snu.idrlogger.DEBUG -n com.snu.idrlogger/.DebugReceiver --es cmd REPLAY \
  --es replay_dir /sdcard/Android/data/com.snu.idrlogger/files/replay/20260905_033817_SNU_AJB_AB_run4 --ed replay_speed 4 \
  --es scenario band --ed band_from 200 --ed band_to 780 --es model litert
adb pull /sdcard/Android/data/com.snu.idrlogger/files/replay_out/ data/field/device_replay/
.venv/bin/python tools/compare_engine_out.py data/field/device_replay/<run>/engine_out.csv --jvm docs/qa_app/jvm_<session>_engine_out.csv --ref data/qa/replay/<session>_corridor_mm0.csv
```
Never pass an empty `--es` value through `adb shell` (the device shell drops it and the next token becomes the value); omit the extra instead. Regenerate assets with `tools/export_weights.py`, `tools/make_map_assets.py`, `tools/extract_pmtiles.sh` (idempotent).

## 3. Conformance (spec §9)

### 3.1 Level A — the maths, isolated (JVM)

Inputs: `data/processed/<session>/track_100hz.csv` (the offline 100 Hz phone-frame track), the offline alignment from `align.json` (R_pb, bias, |g|), fixes from `gnss_fixes.csv`, speed from the deployed model's own predictions (`data/speed_model/pred/deploy_joint_r{1,2}/<session>.csv`), corridor mode forced, outage from motion start + 30 s to the end. Reference: `data/qa/replay/<session>_corridor_mm0.csv`.

| Session | ticks | max Δpos | mean Δpos | max Δheading | max Δv | mode transitions |
|---|---|---|---|---|---|---|
| route-2 run 4 (`20260905_033817_SNU_AJB_AB_run4`) | 2977 | **0.007 m** | 0.002 m | **0.154°** | 0.000 m/s | GNSS_INS@0.0, INERTIAL@66.1 (identical) |
| route-1 run 1 (`20260905_003612_SNU_AJB_AB_run1`) | 1437 | **0.006 m** | 0.002 m | **0.047°** | 0.000 m/s | GNSS_INS@0.0, INERTIAL@49.3 (identical) |

The residual millimetres come from one difference the port keeps on purpose: the fusion filter is created at the first fix (the phone cannot know a position before it), whereas `replay.py` creates it at t = 0 with the first fix as x0; the state history is seeded so the first fix is not lost.

### 3.2 Level B — the model (JVM and phone)

500 real windows from the 100 Hz training set of both roads (stands included), PyTorch float32 outputs as truth (`tools/export_weights.py`, fixtures in `assets/model/`):

| Path | max Δμ | max Δlog σ² | max Δv | latency per window |
|---|---|---|---|---|
| Kotlin CNN, Mac JVM | 1.2e-6 | 1.4e-6 | 1.2e-6 m/s | 0.42 ms (warm, 1 thread) |
| Kotlin CNN, SM-S918B | 1.43e-6 vs PyTorch | — | — | **median 1.41 ms · p95 1.71 · max 1.84 ms** |
| LiteRT 2.2.0 CompiledModel, CPU/XNNPACK, 1 thread, SM-S918B | 1.43e-6 vs PyTorch; **1.91e-6 vs Kotlin** | — | — | **median 0.074 ms · p95 0.086 · max 0.113 ms** |

The first Kotlin implementation ran at 7.9 ms on the phone (loop order co→ci→k→t); transposing the weights to [ci][k][co] so the inner loop is a contiguous saxpy over output channels brought it to 1.4 ms with identical outputs. LiteRT is the deployment path; the Kotlin path is the JVM-testable twin and the fallback.

### 3.3 Level C — the phone path (raw files → causal resampler → online alignment → CNN)

This is what the phone does live: `acc.csv`/`gyr.csv` at 420 Hz through the causal filter, the alignment estimated online (stand → ψ_init → sway ψ → ride-time gravity), the CNN on the live window. Compared with the same reference CSV, which used the **batch** alignment (R_pb over the whole ride, bias from both stands) and zero-phase resampling:

| Session · path | max Δpos vs reference | mean | end | max Δheading (t > 40 s) | modes |
|---|---|---|---|---|---|
| route-2 run 4 · JVM, Kotlin CNN | 7.81 m (t = 59 s) | 4.90 m | 4.38 m | 0.90° | identical |
| route-2 run 4 · **device, LiteRT** | 7.81 m | 4.90 m | 4.38 m | 0.90° | identical |
| route-1 run 1 · JVM | 6.73 m (t = 26 s) | 1.83 m | 2.01 m | 4.91° (t = 81 s, re-level block) | identical |
| route-1 run 1 · device, LiteRT | 6.86 m | 1.90 m | 2.40 m | 4.91° | identical |

Device vs JVM on the same raw files: **0.001 m** (route 2), i.e. the phone reproduces the JVM to the millimetre; the metres are the online-vs-batch alignment, not the port (see §8.2). Speed from the live CNN vs the deployed model's offline predictions on the same session: mean |Δv| 0.12 m/s, signed +0.06 m/s (route 2); one or two causal filter passes make no difference (0.124 vs 0.132 mean |Δv|), so the spec's single pass stays.

Alignment the phone found online on route-2 run 4 (offline align.json in brackets): stand pitch 2.33° → ride-time 1.0–1.5° (offline ride-time g used), ψ_init 20.8° at motion start + 6 s, sway ψ 89.9° at motion start + 20 s converging to 90.7–91.1° (offline sway 90.6°), 25 ride-time gravity blocks, no moved-phone event; route-1 run 1: sway ψ 95.1° → 83.9° after a moved-phone re-level at 80 s (offline align.json also reports a 3° tilt change in that run).

### 3.4 Timing on the phone (replay at max speed, whole session)

| Run | ticks | tick mean | tick p95 | tick max | model mean | model p95 |
|---|---|---|---|---|---|---|
| route-2 run 4, LiteRT | 2994 | 0.161 ms | 0.243 ms | 8.1 ms (first tick) | 0.117 ms | 0.168 ms |
| route-1 run 1, LiteRT | 1453 | 0.144 ms | 0.229 ms | 2.4 ms | 0.112 ms | 0.175 ms |
| route-2 run 4 at 4× with the map live | 2994 | 0.50 ms | — | 11.5 ms | — | — |

The whole 300 s session replays in 1.3 s of wall time at max speed. Budget was 5 ms per tick.

## 4. Scenario, recognition, reveal (device and JVM agree to the millimetre)

Route-2 run 4, auto recognition, band 200 → 780 m from the ride start (the "GNSS returns 70 m before the stop" variant so the reveal can be seen):

| Event | t (s) | detail |
|---|---|---|
| CORRIDOR recognised | 8.1 | SNU_R2 (Circular Rd), 8 consecutive stand fixes within 15 m; s = 11.2, d = 1.0 m |
| MOTION_START | 36.1 | first fix > 1 m/s |
| DIRECTION | 37.1 | A→B from the arc-length progression |
| ARMED | 57.1 | heading initialised, sway ψ available (20 s of motion), GNSS healthy 5 s, window full, stand quiet |
| BAND_ENTER / INERTIAL (sim) | 96.1 | raw fix 200 m from the start → withheld; SIM tag on, chip "Dead reckoning · … m · m:ss" |
| REVEAL / RECOVERING | 246.1 | **off by 17.3 m after 570 m / 151 s**, max error 17.9 m; recovery step 2.1 m |
| GNSS_INS | 249.1 | RECOVERING lasted exactly 3.0 s |

Route 1: corridor at 7.3 s, direction at 19.3 s, band 110 m → stop drives a 229 m / 97 s outage on the reference run (the reference outage runs to the end, so no return figure; the summary says so instead of showing a dash).

Held-out expectations from docs/14 §6 stand unchanged (they were measured offline): route-2 A→B 200 m → stop: 0.7 % median / 4.6 m end error. The 17.3 m above is on a **training** run replayed with the live alignment through a 570 m band that ends 70 m before the stop; it is a conformance/UI figure, not an accuracy claim.

## 5. Gate and detector (JVM tests, acceptance 11.5)

- Band scenario: withheld on the raw fix from the first fix ≥ 200 m along the corridor (`BandScenarioTest`, 1500 INERTIAL ticks, figures above).
- Real gap: fixes dropped for 100 ≤ t < 110 s with no scenario (`RealOutageTest`): REAL_OUTAGE at 100.6 s ("no fix for 1.5 s" at the tick), INERTIAL without the SIM flag, RECOVERING at 111.1 s for 3.0 s with the ×4 measurement inflation, reveal "off by 3.3 m after 41 m", then GNSS_INS.
- The displayed trail is never rewritten: the UI only appends positions (locked and dead-reckoning parts kept as separate frozen line strings); the truth path lives in the reveal layer.
- Corridor recognition outside the library (route-1 session, library = route 2 only): general mode for the whole session, 13.4 % of ticks map-matched with the HMM's confidence margin > ln 20 (display only; the estimate is never fed back).

## 6. Design pass (device, dark theme, font scale 1.0 and 1.3)

Screenshots in `docs/screens/` (1080×2316):

| File | Shows |
|---|---|
| `00_first_launch.png` | idle ride screen: dark vector basemap, campus labels, chip "Ready", compass, card, START, tabs |
| `replay_02b_band_close.png` | GNSS locked · 64 satellites, SIM tag, hatched red band ahead on 2011 Street, mint cone (12° half-angle), blade puck, solid trail, "No GNSS ahead · 31 m" |
| `replay_04_dead_reckoning_deep.png` | "Dead reckoning · 347 m · 1:40", amber dashed trail with the 2σ ribbon, amber cone widened by σψ, band, "Position from motion sensors" |
| `replay_05_relock_reveal.png` | reveal: "Off by 17.3 m after 569 m without GNSS" with the dotted white truth path under the dashed estimate |
| `replay_07_end_stand.png` | stopped: blade morphed to the 14 dp disc, dim cone |
| `ui_puck_gallery.png` | the four puck variants over the live map |
| `ui_satellite.png` | Esri imagery, no roads/extrusions, haloed labels, overlays on top |
| `ui_settings.png`, `ui_field_test.png`, `ui_engine_sheet.png`, `ui_summary.png`, `ui_logger_tab.png` | the other screens |
| `fs13_ride.png`, `fs13_settings.png`, `fs13_field_test.png`, `fs13_engine_sheet.png` | font scale 1.3 |
| `ride_01_stand_countdown.png` | live ride start: "Hold still, brakes on · 11 s", card "0.00 km · 0:00", Hold to stop |
| `replay_1x_riding.png` | the final build during a 1× replay (frame-rate measurement run) |
| `bench_live_5min.png`, `bench_summary.png`, `bench_airplane_mode.png` | the live bench (§7) |

### 6.1 Checks
- Dark theme only (single use scene, every colour painted). Contrast: body text #F2F2F2 on #1A1A1A = 15.6:1, secondary #A9A9A9 on #1A1A1A = 7.3:1, faint #8C8C8C on #101010 = 5.6:1, chip text on the 92 % card = 14:1; all ≥ 4.5:1. Amber #FFB454 and mint #9BE8C4 on #1A1A1A: 9.7:1 and 12.5:1 for the state dots (large graphics, ≥ 3:1 needed).
- Touch targets: START 64 dp, hold-to-stop 64 dp, compass 48 dp, tabs 80 dp, switches/segments ≥ 48 dp.
- Font scale 1.3: the card text wraps to a second line, nothing clips; the engine sheet's label/value rows could touch when a value wrapped, fixed with a 12 dp gap and end alignment.
- Copy uses the product's words only ("GNSS locked · 14 satellites", "Dead reckoning · 360 m · 1:38", "Re-locking · N satellites", "Hold still, brakes on · 12 s", "No GNSS ahead · 40 m", "Off by 6 m after 204 m without GNSS", "Position from motion sensors"); INERTIAL/SIMULATED appear only in the engine sheet and the CSVs. Icons are drawn vectors, no emoji.
- One authored motion: the trail style switches at the puck when dead reckoning starts and the cone hue changes with the state; the reveal fades in over 0.6 s, holds, fades out by 6 s. Reduce motion (Settings) snaps the camera and the puck.

### 6.2 The puck: Blade, and why
All four variants were rendered over the live map at the tracking point (`ui_puck_gallery.png`) and judged at arm's length on the S23 Ultra:
- **Blade (chosen)**: the 30×22 dp arrowhead with two 60 % bevels and a lit ridge reads as a direction at a glance, the 2 dp #F4F4F4 outline separates it from both the near-black ground and the mid-grey building tops, the offset shadow gives it height without a glow; squashed by cos(pitch) it lies on the road.
- Teardrop: soft and pleasant but the rounded tail makes the direction ambiguous when the map turns.
- Chevron + disc: the chevron detaches visually from the disc at 60 % zoom of the gallery and reads as two objects.
- Beam + dot: the beam duplicates the headlight cone, which already carries the confidence, so the dot alone is left and the dot has no direction.
Stopped state: after 2 s at v = 0 every variant morphs to the 14 dp disc (direction is meaningless when stopped) and the cone dims to 40 %.

### 6.3 Map and camera
Protomaps v4 dark recoloured to the tokens (ground #101010, roads #2E2E2E/#383838 on #1A1A1A casings, footways #202020 dashed, water #1F262B, pitches #151B16), 3-D buildings from our merged OSM + Microsoft footprints (`render_height`, vertical gradient), campus labels with 1.2 px halos, Noto glyphs and sprites bundled. Camera: course-up, pitch 50°, zoom 18.6 at rest → 17.2 at 8 m/s, bearing eased with a 120 ms time constant, camera eased over 110 ms every tick (MapLibre's location component was not used: the puck is Compose-drawn at the padded centre, 32.5 % from the bottom), drag frees the camera for 6 s, compass tap = north-up. Satellite: Esri World Imagery raster source, online only, ambient SDK cache only, no bulk download; roads, land fills, extrusions and our fills hidden; label halos 1.6 px.

## 7. Live bench (acceptance 11.4, 11.7, 11.9)

Three live rides on the desk where the phone stood (indoors, USB-connected, charging), started and stopped through the adb hook, nav mode with all sensor streams logged, LiteRT:

| Ride | Duration | acc / gyr | gaps > 50 ms | dropped rows | engine ticks | tick mean / p95 / p99 / max | model mean / p95 | files |
|---|---|---|---|---|---|---|---|---|
| `20260905_220741_NAV_run901` (10 min bench) | 629 s | **418.85 Hz** both (p99 dt 2.39 ms, max 2.43 ms) | **0** | **0** | 6292 (10.0 Hz) | **0.83 / 1.11 / 1.35 / 4.05 ms** | 0.70 / 0.93 ms | 24: the 21 present logger streams (geomagrot does not exist on this phone) + `engine_out.csv` + `engine_events.csv` + `session.json` |
| `…_221958_NAV_run902` (screen-off attempt, stay-awake dev option on) | 164 s | 418.85 Hz | 0 | 0 | 1639 | 0.80 ms mean | — | 24 |
| `…_222512_NAV_run903` (screen off: doze 20 s → 95 s) | 117 s | 418.85 Hz, 49 084 rows = 418.9 × 117 s | **0** | **0** | 1168 (10.0 Hz) | — | — | 24 |

- **Service survives screen-off**: with the "stay awake while charging" developer option disabled, `KEYCODE_SLEEP` put the display into DOZE (`mWakefulness=Dozing`, `mScreenState=DOZE`) 20 s into ride 903; logging and the engine continued without a gap through the dark period (the partial wake lock), the display came back on `KEYCODE_WAKEUP` and the ride ended normally.
- **Thermal**: `Thermal Status: 0` at every minute of the 10 min bench; battery temperature 36.1–36.3 °C throughout.
- **Battery**: 80 → 83 % during the bench because the phone was on USB power; a battery slope cannot be measured while charging (open item for the field day: unplugged ride).
- **GNSS at the desk: no fix.** `gnss_fix.csv` has 0 rows in all three rides (1530 `gnss_status` epochs and 625 raw-measurement events were received, no position). The engine therefore never left `GNSS_INS` with `hasPosition = false` and the chip showed "Waiting for GNSS"; the stand alignment ran (pitch −0.45°, roll 0.86°, bias −0.03/−0.02/−0.03 °/s, quiet), the timer scenario never armed (no motion start), and `route_id` was written as `FREE`. The **airplane-mode check** (airplane mode on from 22:09:58 to 22:11:02, session 136–200 s, Location on) is therefore inconclusive indoors: the GNSS chipset produced no fix before, during or after; the app's provider request is `GPS_PROVIDER` only, so nothing in the airplane state can change what it receives outdoors. To be repeated on the first field ride (30 s of airplane mode while riding).
- **UI frame rate** (`dumpsys gfxinfo com.snu.idrlogger`, 60 s window, 1× replay of route-2 run 4 with the band scenario, ride screen visible, map moving, 120 Hz panel): **6 936 frames rendered = 116 fps**, janky 2.3 % (legacy metric 11.0 %), frame time p50 13 ms, p90 14 ms, p95 14 ms, p99 17 ms. `gfxinfo` counts the Compose/HWUI frames (puck, cone, trail source pushes, chip); MapLibre renders on its own GL thread, see the map frame line below. No ANR at any point in the session (no `ANR in com.snu.idrlogger` in logcat across ~4 h of testing).
- **Logging (11.7)**: every nav ride wrote the logger streams plus `engine_out.csv` (10 Hz, 19 columns as specified) and `engine_events.csv`; `session.json` carries `route_id` (SNU_R1 / SNU_R2 / FREE), `direction`, `nav_mode`, `sensor_logging`, `speed_model`, the anchors and per-stream rates; the summary screen lists the outages and the files, and Zip + share produces `<session>.zip` through the FileProvider (the logger tab's Zip / Zip + share / Delete are unchanged).

- **Map frame rate** (MapLibre `OnDidFinishRenderingFrame` counter, 5 s windows, same 1× replay, ride screen visible, camera easing every tick): **119.5–120.2 fps** in every window (the panel's 120 Hz); the Compose layer over it: 6 885 frames in 60 s = **115 fps**, janky 2.8 %, p50 9 ms, p99 21 ms. Acceptance 11.4's ≥ 55 fps holds for both layers.

## 8. Deviations from the brief, and why

1. **Compose BOM 2026.06.01 (Compose 1.11.4, Material 3 1.4.0), lifecycle 2.10.0** instead of BOM 2026.08.00 / lifecycle 2.11.0: every Compose 1.12.0 artifact declares `minAgpVersion 9.1.0` and `compileSdk 37` in its AAR metadata, which AGP 8.13.2 refuses at `checkDebugAarMetadata`. Upgrading to AGP 9 / Gradle 9 was out of scope for the pinned toolchain; the newest BOM whose artifacts accept AGP 8.13 is 2026.06.01.
2. **Conformance prediction files**: the brief names `data/speed_model/pred/cnn_r100_w256_joint/<session>.csv` (held-out cross-validation predictions, 2735 rows). The reference CSVs were generated from the deployed model's own predictions `pred/deploy_joint_r{1,2}` (2892 rows). With the brief's files the maths path differs by up to 9 m; with `deploy_joint_r*` it matches to 7 mm, and a Python trace of `filter.py` with the same inputs reproduces the reference to 7e-5 m. The JVM test uses `deploy_joint_r*`.
3. **The < 1 m tolerance holds for the maths path, not for the raw phone path.** The reference was produced with a batch alignment (ride-time gravity and sway ψ over the whole ride, bias from both stands). The phone must align online; the resulting 0.9° (route 2) to 4.9° (route 1, at a re-level) heading differences give 2–8 m over the 200 s outages. The device reproduces the JVM raw path to 0.001 m, so the port is verified; the online-vs-batch gap is the honest cost of running live and it is what the field ride will show.
4. **Replay origin**: on-device replays set the ENU origin to the session's start anchor (from `session.json`) so `engine_out.csv` is directly comparable with the JVM run and the reference; live rides use the first fix as origin (an anchor does not exist yet). Nothing in the estimate depends on the origin.
5. **Debug entry points**: `DebugReceiver` (broadcast → service) and the `com.snu.idrlogger.PREFS` receiver in the activity exist so every test in this document could be driven from the Mac; both are inert unless `BuildConfig.DEBUG`.
6. **Logger tab layout**: the 1:2:1 taping-band layout kept 50 % of the screen black; with the bottle-cage mount the whole screen is visible, so the dead zones became thin 12 % margins. Behaviour (states, hold-to-stop, dialogs, files) is unchanged.
7. **Forced corridor id not in the library** (or an empty id) falls back to automatic recognition with an event, after an adb quoting artefact showed how easily a stray value can switch recognition off.
8. **Satellite mode also hides the Protomaps `earth` land fill**, which sits above the raster in the style order; without that the imagery was covered (first attempt rendered black).
9. **Reveal trigger**: the UI keys the reveal animation off the engine state, not the REVEAL event, because the event precedes the tick that carries the figures by up to one tick.
10. **First trail push**: MapLibre rejects a one-point LineString (`Error setting geo json`); the trail source only receives parts with ≥ 2 points.
11. **Two label layers** (sort key ≤ 20 from zoom 15.5, the rest from 16.5) replace the per-feature `minzoom` the plan suggested, because `["zoom"]` is not allowed inside a filter expression.
12. **Speed model**: one joint model everywhere, as the handoff says; docs/12 §8 also mentions a route-2 override model (`cnn_r100_w256_r2deploy_s1`), which is not shipped. The model pack format supports swapping it (two files).

## 9. Field protocol and video (checklist for the rider)

Phone: Battery → Unrestricted for IDR Nav, Location → Allow all the time, system microphone toggle ON (motion sensors are rate-limited otherwise), screen timeout long, adaptive brightness off, Do Not Disturb on, One UI screen recorder: 1080p, sound = Media, no touches, started before START. Airplane mode is optional (the map is offline; satellite needs data). Free space ≥ 5 GB (logging 10.8 MB/min + recording).

Before the ride (Settings → long-press the version line → Field test): scenario **Band**, from **200**, to **0** (= to the stop) for route 2 A→B; route 1: from 110; corridor Auto; model LiteRT; reveal on; logging on. Back to Ride. The SIM tag beside the chip confirms the scenario is armed; the band is drawn on the map as soon as the direction is known (≈ 1 s after the bike moves).

The ride: tap START, then **stand still 15 s with brakes held and no turning** (chip: "Hold still, brakes on · 12 s"); ride off normally; **≥ 30 s of riding before the band** (route 2 A→B reaches 200 m after ≈ 60 s); do not touch the phone; ride through the band to the stop; hold still 15 s again; hold-to-stop 800 ms. One ride per direction per road; one ride with a full stop inside the band. The summary shows every outage with distance, duration, off-by, max error and recovery step; Zip + share sends the folder.

After each ride (Mac):
```
adb pull /sdcard/Android/data/com.snu.idrlogger/files/sessions/<session> data/field/
.venv/bin/python engine/replay.py --session data/field/<session> --pred <pred> --tag route2 --outage <t0>,<t1>      # Python replay (needs the offline pipeline first)
IDRNav/gradlew -p IDRNav :engine:test    # or compare engine_out.csv of the ride with a JVM SessionReader run of the pulled folder
```
`engine_out.csv` (10 Hz: t_s, lat, lon, x_m, y_m, v, heading_deg, mode, sim, k, sigma_pos, v_model, sigma_model, stop, tick_ms, model_ms, corridor_id, s_m, d_m) and `engine_events.csv` are in the session folder next to the 22 logger streams; `session.json` carries `route_id` = SNU_R1 / SNU_R2 / FREE, `direction`, `speed_model`, `nav_mode`.

Camera rig: phone 3 in a handlebar holder facing forward, 1080p60. SYNC: three white frames and three tones at START, band entry and band exit; find the beeps with `tools/compose_video.sh --beeps cam.mp4` and assemble:
```
tools/compose_video.sh cam.mp4 screen.mp4 <offset_s> out.mp4
# = ffmpeg -i cam.mp4 -itsoffset <offset_s> -i screen.mp4 -filter_complex "[0:v]scale=-2:1080[a];[1:v]scale=-2:1080[b];[a][b]hstack" -c:v libx264 -crf 18 out.mp4
```
Fallback for the video: Field test → Replay of the fresh ride at 1× with the same scenario; the card shows "Replay · <session>" and the summary says "Replay".

## 10. Open items

- Field rides (route 2 A→B ×2–3, route 1, free ride) and their Python/JVM/device three-way comparison: not possible from the desk.
- The live bench (§7) ran indoors on the desk where the phone stood; GNSS quality there is whatever the desk offers.
- The Field-test conformance self-test button reads `conformance.json` + `reference.csv` beside a pushed session and prints max |Δpos|; verified by code and by the adb path of the same comparison, not by tapping the button.
- The R5 §3 design checklist was applied by hand rather than by tooling.
- The bottom sheet opens on tap of the card (Material `ModalBottomSheet`) rather than by dragging the card itself.
