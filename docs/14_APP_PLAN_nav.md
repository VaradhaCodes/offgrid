# 14 — Navigation app plan ("IDR Nav"): the final deliverable

v2, Sat 5 Sep 2026 ~13:45 IST (v1 12:30). Status at the time of writing: agreed plan; nothing built yet. Companions: `docs/12_ENGINE_SPEC_for_kotlin.md` v2 (maths, joint model), `docs/research/R5_map_ui_references.md` (design direction + references), R6 (Android map stack) and R7 (campus map data) when they land, and the v2 screen mockup.

**User decisions (5 Sep 13:00):** no cage constraint, full-screen app; satellite toggle wanted if it works properly; ghost dot only if it adds value (→ replaced by the re-lock "reveal", §2.8); stack is my call; field tests whenever the app is ready; camera rig undecided. **The main screen must not show route pickers**: the app looks like a general nav app that "just works" anywhere; corridor recognition and the demo scenario are hidden (§2.6, §2.9). **The outage must sit where the engine is strongest** (§6, measured).

## 0. Where we actually are (facts checked today)

| Item | State |
|---|---|
| Kotlin engine | **Does not exist.** There is no `.kt` file outside the logger. What exists is the *spec* (`docs/12`) and the Python truth (`engine/*.py`). The port (~1,000 lines of plain Kotlin) is job 1. |
| Logger app | `IDRLogger/` (Kotlin, XML Views, AGP 8.13.2, Gradle 8.14.3, JDK 21, compileSdk 36). Foreground service with all 22 streams at 420 Hz, verified on the S23 Ultra. Reusable as-is for sensor/GNSS plumbing, writers, anchors, permissions. |
| Speed model | **Settled by the engine session (spec v2, 5 Sep ~12:00): one joint model** `cnn_r100_w256_joint_deploy.tflite` (240 KB, trained on all 30 runs of both roads, corrected labels; held-out MAE 0.179 m/s route 1 / 0.164 route 2), exported and verified to 1.9e-6; the v1 file is superseded. One model for everything, including free rides: that is the "solved for the world" story, honestly framed as device+mount adapted with two campus roads. |
| Engine spec | `docs/12` is now v2 and matches the code: heading `kfpsic` (ψ refined from the position course, robust stand bias held; bias state only after a non-quiet stand, then no outage before 60 s), `LAG_V = 0.2`, **k off everywhere on bicycle roads**, joint model, route-2 corridor with a 20 m overhang. Port from the spec v2 + code. |
| Conformance references | Regenerated 11:55 with the v2 engine + joint model: route-1 run 1 (outage 229 m / 82 s, endpoint 6.7 m) and route-2 run 4 (789 m / 218 s, endpoint 20.7 m), `data/qa/replay/*_corridor_mm0.csv`, 10 Hz. Tolerance: max |Δpos| < 1 m, modes ±0.2 s, heading 1°, model speed 0.02 m/s. |
| Map data | `corridor_route1.geojson` (37 vertices, 339 m incl. 15 m overhangs, A at s=15, B at s=335), `corridor_route2.geojson` (41 vertices, 927 m, one 120° bend at s=464), `snu_osm_highways_900m.json` (276 ways; 89 service roads, 175 footways, 6 paths). No buildings/fields yet. |
| Toolchain | Network OK (Google/Maven Central). LiteRT `com.google.ai.edge.litert:litert:2.2.0`; MapLibre `org.maplibre.gl:android-sdk-vulkan-opengl:13.6.0` (maplibre-compose excluded, see §2.2); Compose BOM 2026.08.00 (ui 1.12.0, material3 1.4.0). `ffmpeg 9.0.1` on the Mac. Esri satellite tiles, OSM raster tiles and Overpass all reachable (for a one-time offline cache). No node/npm (so no React Native/Flutter detour; native Kotlin it is). Phone not connected at the time of writing. |

## 1. What the app has to show (the demo, in one paragraph each)

**Storyboard (both corridors, same shape).** Rider taps START, stands still 15 s (the app shows the alignment settling: gravity, gyro bias, GNSS anchor). Rides off; the marker follows GNSS+INS, course-up like a car nav. A readiness row fills in as the engine arms (heading initialised from the first course fix, forward axis from the pedalling sway after 20 s of motion, model running). A red hatched **GNSS-denied zone** is drawn on the corridor ahead with a countdown in metres. On entry the chip flips to amber **INERTIAL · simulated denial**, a timer and "m dead-reckoned" counter start, the trail turns amber, an uncertainty ring grows slowly, and (optionally) a faint grey **truth dot** shows where GNSS actually is, hidden from the engine. The marker carries through the S-bend/arc (route 1) or the 120° junction and 340 m beyond (route 2), stops if the bike stops. On zone exit the chip turns sky-blue **RECOVERING**, the marker glides (no jump) onto the fix within 3 s, and a result card appears: outage distance, duration, endpoint error in metres and %, recovery step. Rider stops, stands 15 s, the summary card is written and the session is saved (every demo ride is also a full logger session).

**Three test cases the app must handle:**
1. Route 1 (A↔B, 320 m): corridor mode `[s, v, k]`, k off. Zone proposal: s ∈ [125 m, B] ≈ 210 m (second half of the S-bend + the whole arc), entered ~30 s after motion start at 3.5 m/s.
2. Route 2 (B→north or reverse, 853 m): corridor mode, k on. Zone proposal: s ∈ [300, 800] = 500 m, covering the 120° junction at s=464 and 340 m after it; 100 m of GNSS before the end for recovery.
3. Random road on campus: **general mode** `[px, py, v, k]`, no corridor; the HMM map matcher over the campus graph snaps the *display* to the road (display only, as measured; the estimate is never fed back). Denial by timer ("30 s after motion, hold 60 s") or manual. Expect larger drift than the corridors and say so on screen.

## 2. Product decisions (recommendation first; alternatives noted)

1. **One app, two modes.** Evolve `IDRLogger` into "IDR Nav" with a Nav screen and the existing Logger kept as a tab. Reuses the proven service, writers, permissions; nav rides keep logging all 22 streams plus a new `engine_out.csv` (10 Hz state) and `engine_events.csv`. Alternative: a new app — costs a second Gradle/permissions setup for nothing.
2. **UI: Jetpack Compose + Material 3, map via MapLibre Native (R6, 5 Sep, exact versions verified on Maven).** `org.maplibre.gl:android-sdk-vulkan-opengl:13.6.0` (Vulkan default since 13.0 with OpenGL fallback; PR #4442 fixed an Adreno device-lost crash triggered by the specialised location indicator, our exact case on the S23 Ultra's Adreno 740), wrapped in `AndroidView` (the `maplibre-compose` library is excluded: built with Kotlin 2.4 / AGP 9.1 / JDK 25 / compileSdk 37 and a second native stack, incompatible with our toolchain). Compose BOM `2026.08.00` (ui 1.12.0, material3 1.4.0), `activity-compose 1.13.0`, `lifecycle-runtime-compose 2.11.0`. Puck = `LocationComponent` with `useDefaultLocationEngine(false)`, `useSpecializedLocationLayer(true)` and `forceLocationUpdate()` at 10 Hz (interpolates over 110 ms); camera `CameraMode.TRACKING_GPS` with zoom/tilt/padding-while-tracking; overlays through `GeoJsonSource` with `setOverrideSynchronousUpdate(true)` (13.5+). Borrowed from Ferrostar 0.54 (BSD-3): bicycle camera zoom 18, tilt 45°, puck in the lower half via 50 % top padding. Compose gives animated state cheaply; MapLibre gives the real nav camera and a style JSON we own.
3. **Map content: an offline vector basemap plus our own layers (R6 + R7, 5 Sep).** Base = a **PMTiles extract of the Protomaps daily planet** for the campus bbox (measured: 22 tiles, 0.85 MB at z0–15; the OpenFreeMap equivalent is 2.4 MB and one zoom shallower) with the Protomaps v4 dark style rewired to our tokens, local glyphs (Noto, Latin-1 ranges, ~230 KB) and sprites; total offline payload ≈ 1.6 MB. Traps: `pmtiles://asset://` is not supported (no byte-range reads from assets), so the archive is copied to `filesDir` on first run and opened as `pmtiles://file://…`; there is no `mbtiles://` scheme on Android. On top, our own GeoJSON layers: extruded buildings from `data/map/snu_osm_full.geojson` (513 features: 58 buildings, 26 named, 15 with levels; height → levels × 3.2 m → 6 m default; hostels 6 levels and Blocks A–D 4 levels carry the skyline) gap-filled in the north-east quarter with unnamed Microsoft footprints (`snu_buildings_ms.geojson`), building-name labels, the campus boundary, corridor, denial band, trail, ribbon, puck extras and the reveal, all updated at 10 Hz. Watch: "Dining Hall 3" is two OSM ways (dedupe) and the four `type=route` relations must be dropped or NH-91 draws twice. **Satellite = online toggle, not an offline cache**: Esri World Imagery is real to z19 (Maxar WorldView-3, 2023-02-08, 0.31 m, stated accuracy 5 m, so never presented as ground truth), z20+ is a placeholder; the item licence and Esri's terms forbid tile export and offline redistribution (`exportTilesAllowed: false`), so the app loads tiles live through a raster source with attribution and relies only on the SDK's normal ambient cache (view the road once before the ride). Every other imagery source was checked and rejected (Bhuvan placeholder without credentials, Sentinel-2 10 m, no Maxar open scene, GIBS z12). Why not Google Maps: API key, online, no camera/style control, hides our marker behind theirs.
4. **Engine as a pure-Kotlin Gradle module `:engine`** (no Android imports): alignment, causal resampler, heading filter, corridor, fusion filter, map matcher, gate/state machine, plus a **pure-Kotlin forward pass of the CNN** (4 conv1d with BN folded + 2 dense, 57.6 k weights, ~1.8 M MACs ≈ 1–2 ms). This makes the whole engine runnable and testable on the Mac JVM against the Python CSVs in seconds, with no phone. LiteRT is added on top as the "edge deployment" path and its latency measured on device; if a LiteRT version ever regresses (tensorflow#62615 doubled latency on this exact device class), the Kotlin path is the fallback. Weights ship as a **model pack** in assets: `weights.bin` + `model.json` (shapes, norm mean/std, window, rate, version). Swapping the retrained/joint model = replacing two files.
5. **Replay mode inside the app.** Push any recorded session folder to the phone; the app feeds it through the *same* engine at 1×, 4× or max speed with the same UI, labelled REPLAY in the chip. This is how I test the UI and the outage/recovery behaviour at the desk, how conformance is checked on the real CPU, and the honest fallback for the video (rung 5 of the ladder in `docs/00`).
6. **Denial definition = a zone on the corridor** (arc-length interval, editable), with timer and manual as alternatives. The gate decides on the *raw* GNSS fix (inside the polygon → withheld), the engine sees nothing while inside — the same rule as `replay.py --polygon`. The real-outage detector (gap > 1.5 s, acc > 30 m, sats < 4 ×2, C/N0 < 22) stays active underneath, always.
7. **Positioning uses GPS_PROVIDER only, never the fused/network provider**, and the engine sheet says so ("fix source: GNSS chipset"). Airplane mode is optional now that satellite tiles are online; if we want it for the video, view the road once beforehand so the ambient tile cache is warm, then switch data off.
8. **The re-lock "reveal" instead of a live ghost dot.** During the denial the viewer sees only what the engine sees (no clutter). When GNSS returns, the withheld true path fades in for 6 s as a thin dotted white line under the dashed dead-reckoned trail with one figure: "off by 6 m after 204 m without GNSS", then fades out. Same honesty, one clean beat, no bloat. The engine sheet still shows the live error number for us.
9. **Invisible corridors ("road memory").** The app ships a small library of learned corridors (today: the two campus roads; the format is extensible). Once GNSS shows the rider on a library corridor for 8 fixes, the engine silently switches to corridor mode; otherwise it runs general mode on the campus road graph. Nothing on the main screen says "route 1"; the engine sheet shows "corridor: Circular Rd (learned)" for those who look. This is exactly how a deployed system would commission tunnels and underpasses, and it is true.
10. **Hidden field-test screen.** Long-press the version line in Settings → "Field test": scenario per corridor and direction (zone start/end in metres from the ride start, from the sweep in §6), replay of a recorded ride, reveal on/off, engine sheet on/off, logging on/off. When a scenario is armed, the main screen shows only a small "SIM" tag beside the state chip (honesty; a real outage shows no tag) and the no-GNSS zone drawn on the map as a hatched band once the direction is known, which reads like a tunnel marking.
11. **Design direction = `docs/research/R5` §4**: near-black neutral base (Protomaps-black / Dark Matter family, not blue-grey), extruded campus buildings, one saturated thing at a time; state carried by hue and line style (solid = locked, dashed = dead-reckoned, ribbon width = 2σ); a headlight cone instead of a glow; Barlow type; Material 3 structure; one authored motion moment. Satellite = Esri imagery with corridor/zone/labels only.

## 3. Screens (v2)

1. **Ride** (the app): full-screen map, edge-to-edge, course-up, pitched. Top-left: one state chip ("GNSS locked · 14 satellites" / "Dead reckoning · 87 m · 23 s" / "Re-locking"), plus the "SIM" micro-tag when a scenario is armed. Top-right: compass/follow control. Bottom: a low card with the speed figure (Barlow Semi Condensed, 72 sp), unit, and one status line; pull it up for the **engine sheet** (alignment pitch/roll/ψ, gyro bias, heading σ, model μ/σ/stop, mode, corridor name, σ pos, tick and model latency, IMU/GNSS rates, real-outage detector state, replay speed). One FAB-sized START/STOP control with hold-to-stop.
2. **Stand** overlay (15 s): countdown ring on the puck, "Hold still, brakes on"; the alignment numbers settle in the status line (pitch, bias, satellites).
3. **Ride summary** after the end stand: distance, time, outages with their reveal numbers, file saved; share.
4. **Settings**: units, map style (night / satellite), rider name, sync flash on/off, screen band insets (default full), version line (long-press → Field test).
5. **Field test** (hidden): corridor auto/forced, scenario per corridor/direction (zone start/end m, timer, manual), replay a session at 1×/4×/max, reveal on/off, engine sheet on/off, logging on/off, sensor inventory, conformance self-test (runs the reference session and prints max |Δpos|).
6. **Logger** tab as today, for data collection.

## 4. Architecture

```
NavService (foreground, type=location; reuses LogService plumbing)
  SensorHub   acc+gyr 420 Hz on the sensor HandlerThread → CausalResampler (SOS Butterworth 40 Hz + 10 ms grid) → 100 Hz bike-frame samples
  GnssHub     GPS_PROVIDER fixes + GnssStatus (sats, C/N0) → Gate (real-outage rules ∥ simulated: zone / timer / manual)
  Engine (:engine, pure Kotlin, single thread "idr-engine")
      Aligner        stand gravity + robust bias → R1; ψ_init from the first speed-up; sway-axis ψ after 20 s; ride-time gravity blocks; moved-phone rule
      HeadingFilter  kfpsic: quaternion at 100 Hz, gated tilt correction, course measurement on straight fast fixes, 5σ gate + 5-reject reset
      SpeedModel     256×6 window → z-score → CNN (Kotlin / LiteRT) → μ, σ; physical stop rule on the last 0.5 s
      Fusion         corridor [s, v, k] or general [px, py, v, k]; 10 Hz tick; delayed-state GNSS updates (LAG_POS 0.5, LAG_V 0.2); ZUPT; recovery inflation ×4 for 3 s
      Corridor       polyline in ENU about the session anchor; project / point / tangent; off-corridor fallback (|d| > 15 m ×3 → general)
      MapMatcher     HMM over the campus graph, 2 Hz, 3 s lag, display only (general mode)
      ModeMachine    STAND → RIDE(GNSS_INS) → ARMED → INERTIAL → RECOVERING → GNSS_INS; SIMULATED flag
  Logger      the 22 streams as today + engine_out.csv (10 Hz: t, lat, lon, x, y, v, ψ, mode, k, σ_pos, v_model, σ_model, stop, tick_ms) + engine_events.csv
  Output      StateFlow<NavState> at 10 Hz → Compose UI; MapLibre sources updated on the main thread
ReplayEngine  reads a session folder from the phone storage; same Engine; 1× / 4× / max
```
Threads: sensors (URGENT_AUDIO priority) → lock-free ring → engine thread (100 Hz step, 10 Hz tick) → main thread (UI). GNSS callbacks post into the engine thread. Nothing allocates per sample (fixed arrays).

## 5. Engine port notes (deltas from `docs/12`, taken from the code)

- Heading = `kfpsic`: P is 2×2 but K[1] = 0 always (bias not refined); robust stand bias from the start stand (1 s chunks, quietest half, |mean| < 0.01 rad/s); first accepted course initialises ψ and sets P00 = (10°)². Route-2 finding: the fixed stand bias is within 0.03 °/s of the oracle; a bias state hurts long outages.
- `LAG_V = 0.2 s` (measured Doppler latency), `LAG_POS = 0.5 s`.
- k: enabled per route config (`k_est`): false for route 1, true for route 2 and free ride (transfer gains 6.4 → 2.4 % on route 2).
- Resampling: the phone runs the causal SOS filter from `engine/export/resample_constants.json` on the native 420 Hz stream and samples the 10 ms grid; gyro is interpolated onto accelerometer times first (as `imu_native()` does).
- Live alignment order: stand → g_ref, bias; RIDE_START; ψ_init from the first speed-up window (GNSS acceleration > 0.15 over −2…+6 s around the first fix > 1 m/s); switch to the sway-axis ψ after 20 s of moving samples, recomputed every 10 s; ride-time g_ref blocks of 10 s with the gates in §3.1 of the spec.
- Readiness ("ARMED") = heading initialised ∧ ψ from sway available ∧ GNSS healthy for ≥ 5 s ∧ model window full. Entering the zone before ARMED: the app still withholds GNSS (honest) but the chip says "NOT ARMED" and the result card is flagged.
- Conformance: two levels. (a) JVM: `:engine` fed the reference session's 100 Hz track + the Python model predictions → max |Δpos| < 1 m, modes within ±0.2 s, heading within 1°. (b) Device: the Kotlin/LiteRT model on the same windows vs `pred/deploy_r1/…csv` → |Δv| < 0.02 m/s; then the full live replay on the phone vs the Python CSV.

## 6. Where the outage goes (measured, 5 Sep 13:15)

Sweep: every kept run of both roads (20 + 10) replayed through the v2 engine in corridor mode with the joint model's held-out predictions (`pred/cnn_r100_w256_joint`), GNSS withheld while the true position is between d0 and d1 metres from the ride's own start (direction-relative, so one scenario serves both directions), scored at the moment GNSS returns. Offline batch alignment was used; the live app aligns online, so expect slightly worse. Sweep outputs: `zone_sweep_route{1,2}.csv`.

| Road | Zone (m from start) | outage | drift median / p75 / worst | runs < 5 % | end error median / worst | note |
|---|---|---|---|---|---|---|
| Route 2 **A→B** (Shivaji end → north) | 200 → stop | 671 m / 178 s | **0.7 / – / 4.4 %** | 5/5 | **4.6 m / 29 m** | covers the 120° junction (450 m in) + 380 m after; the demo take |
| Route 2 A→B | 200 → 780 | 568 m / 147 s | 1.6 / – / 5.2 % | 5/5 | 8.7 m / 29 m | GNSS back 70 m before the stop: the glide is seen while moving |
| Route 2 both dirs | 200 → stop | 671 m | 2.7 / 4.0 / 6.6 % | 9/10 | 17.6 m / 44.6 m | B→A is worse (heading bias on the first pair: run 3 −8°) |
| Route 1 both dirs | 100 → stop | 210 m / 54 s | 4.4 / 5.4 / 7.3 % | 12/20 | 9.2 m / 14.9 m | 20/20 under 10 %; zone starts 25 s after motion |
| Route 1 both dirs | 120 → stop | 191 m / 49 s | 4.6 / 5.7 / 7.2 % | 12/20 | 8.6 m / 13.4 m | safer for the live alignment (30 s) |
| Route 1 both dirs | 100 → 270 | 164 m / 39 s | 7.2 / 8.2 / 12.5 % | 3/20 | 11.6 m / 19.5 m | ending before the stop looks worse in % (same metres) |

Decisions: **demo take = route 2, A→B, zone 200 m → stop** (or 200 → 780 if we want the re-lock while still rolling); route 1 = zone 110 m → stop, either direction; free ride = timer 40 s after motion, 90 s hold, general mode. These numbers go into the hidden scenario config, not the main screen. Honesty note for the writeup: the placement was chosen on held-out replays of the same roads.

Route config = `assets/corridors/<id>.json` (corridor path, anchors, overhangs, display name, per-direction scenario). The nav session writes `route_id` = SNU_R1 / SNU_R2 / FREE into `session.json`.

## 7. Test and AI workflow (what I do, in order)

1. **JVM conformance first** (no phone needed): `./gradlew :engine:test` replays the reference session from the Python 100 Hz track and pred CSV; diff vs the replay CSV. Iterate here until the maths match.
2. **Model conformance on the JVM**: Kotlin forward pass vs the PyTorch outputs on 2,000 real windows (exported with the weights).
3. **Device replay**: `adb push data/route1/sessions/<run> /sdcard/Android/data/<pkg>/files/replay/`, start Replay from the app; watch via `adb exec-out screencap -p` and `adb screenrecord`; read `adb logcat -s IDR`; pull `engine_out.csv` and diff vs Python. Measures tick and model latency on the real CPU.
4. **Bench live**: phone on the desk by a window: rates, GNSS health, UI at 60 fps, thermal, battery over 10 min.
5. **Field**: route 1 with the zone armed (rider: still stand, ≥ 30 s of riding before the zone, normal pace). Pull the session, run the *Python* replay on it, compare to the on-device output: that is the field conformance. Then route 2, then a free ride.

## 8. Video plan

- Screen: One UI screen recorder (Settings → Advanced features → Screenshots and screen recorder: sound = Media, no taps, 1080p) started before START. The app shows a big wall-clock and a **SYNC flash + beep** (3 white frames, 3 tones) at START, zone entry and zone exit. The beep lands in the screen recording's audio and in the camera's mic → align by audio in DaVinci Resolve/CapCut or by the first flash if the camera sees the screen.
- Camera: simplest rig that works: phone 3 in a handlebar phone holder facing forward (the one mount that was wrong for the data phone is right for the camera), 1080p60, wide lens; a chest strap or a following rider is optional B-roll. The nav phone stays in its usual spot.
- Assembly on the Mac with ffmpeg (side-by-side, offset from the sync beep), captions rendered in-app (mode chip, counters, result card) so no editing text is needed:
  `ffmpeg -i cam.mp4 -itsoffset 3.42 -i screen.mp4 -filter_complex "[0:v]scale=-2:1080[a];[1:v]scale=-2:1080[b];[a][b]hstack" -c:v libx264 -crf 18 out.mp4`
- Fallback: an on-device REPLAY of a fresh recorded ride, labelled REPLAY on screen.

## 9. Intermediate steps we are missing (asks, and who)

1. **Engine session**: export the final model (r1deploy / r2deploy / joint) with `export.py` → `.tflite` + `_export.json`, and add a weights dump for the Kotlin path (I will write `engine/export/export_weights.py`; it only reads `.pt`). Decide which model the demo uses per route (or one joint model).
2. **Engine session**: regenerate the conformance references with the deployed predictions and the `kfpsic` heading: run 1 corridor (route 1), one route-2 run corridor, one route-1 run general mm=1; and append a "v2 deltas" section to `docs/12` (kfpsic, LAG_V, k policy).
3. **Map data**: done by R7 (files in `data/map/`); no tile cache (terms). Optional later: a campus walk to tag `building:levels`, and a survey of speed bumps (zero `traffic_calming` tags exist) which would double as IMU landmarks.
4. **Phone prep** (user): screen recorder settings, screen timeout = never while charging, adaptive brightness off, DND on, airplane mode + Location on; USB debugging stays on; free space ≥ 5 GB (10.8 MB/min logging + 1080p screen recording ≈ 100 MB/min).
5. **Ride protocol for demo rides** (user/team): brakes held, no turning during both stands; ≥ 30 s of normal riding before the zone; no touching; one run per direction per route; one run with a full stop inside the zone (shows the stop rule).
6. **Latency**: measured in the app (tick ms, model ms) and logged; goes into the results doc.
7. **Free-route honesty**: general mode numbers on route 2 were 12 % vs 2–4 % corridor; the app shows "general mode · map display matched" and the result card, nothing hidden.

## 10. Build order

1. `:engine` module + JVM conformance harness (alignment, resampler, heading, corridor, fusion, gate, model forward pass). Gate: max |Δpos| < 1 m on the reference session.
2. NavService + SensorHub/GnssHub + engine_out logging; Replay engine. Gate: device replay matches the JVM run.
3. Map: style + offline layers + camera; marker/trail/zone/ghost sources.
4. Nav screen (Compose) + Set up + Engine sheet + Summary; band-aware layout; sync flash/beep.
5. LiteRT path + latency readout; satellite toggle; polish (animations, haptics, TTS "GNSS denied / GNSS restored").
6. Field test route 1 → fix → route 2 → free ride → video.

## 11. Open items

1. Field-test windows: whenever the app is ready (user). Route 2 A→B is the demo take; ride it 2–3 times.
2. Camera rig: handlebar holder for phone 3 (suggested above).
3. Run the R5 §3 design checklist over the first screens as soon as they exist.
