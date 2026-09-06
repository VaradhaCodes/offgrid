# Logger app spec — "IDR Logger" (Kotlin, Android, S23 Ultra)

Purpose: record every navigation-relevant stream the phone exposes, with monotonic timestamps, reliably for 20-minute sessions while taped to a bicycle. It is NOT the navigation UI. The navigation UI comes later as a second screen in the same app, using the same engine interface.

## Build / install (all from this Mac, no Android Studio)
- Kotlin + plain XML Views (no Compose: fewer deps to download, faster first build). minSdk 29, targetSdk 35, compileSdk 35. AGP ≥ 8.6 (compileSdk 35 requirement), Gradle wrapper ≥ 8.7, JAVA_HOME=/opt/homebrew/opt/openjdk@21 (JDK 21 verified OK).
- Hardware in the S23 Ultra (iFixit): LSM6DSO accel+gyro, AK09918C magnetometer, LPS22HH barometer, Snapdragon 8 Gen 2 GNSS with L1+L5. Carrier phase (ADR) probably unsupported; check the ADR state flag on device and do not plan on it.
- `./gradlew assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk` → `adb install -r`.
- Phone side: Settings → About phone → Software information → tap Build number 7× → Developer options → USB debugging ON. Plug in, accept the RSA prompt. Wireless debugging is the backup (pair with code from Developer options).
- Data comes back with `adb pull /sdcard/Android/data/<pkg>/files/sessions/`. Session folders are also shareable via the share sheet (zip).
- Debugging: `adb logcat -s IDR` from the Mac.

## Permissions (manifest)
- ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, FOREGROUND_SERVICE, FOREGROUND_SERVICE_LOCATION, POST_NOTIFICATIONS, HIGH_SAMPLING_RATE_SENSORS, WAKE_LOCK, ACTIVITY_RECOGNITION (not required; skip).
- Foreground service with `foregroundServiceType="location"`. Partial wake lock for the session. Ask user once to exclude the app from battery optimisation (Samsung kills background listeners otherwise; also turn OFF "Put unused apps to sleep" for this app).
- Screen: keep-screen-on during a session (the screen faces out on the down tube and is the status display). Brightness can be low. Reason beyond visibility: default sensors are non-wake-up; if the AP suspends, the hardware FIFO drops old events. So: screen on + PARTIAL_WAKE_LOCK for the whole session.
- Gotcha: if the phone's system-wide microphone toggle is OFF, Android rate-limits motion sensors even with HIGH_SAMPLING_RATE_SENSORS. Leave the mic toggle ON.
- Samsung checklist per install: Settings → Apps → IDR Logger → Battery → Unrestricted; add to Never sleeping apps; Location → Allow all the time; accept the ignore-battery-optimisations prompt.

## Streams (one file per stream per session, CSV, header row; all timestamps = SensorEvent.timestamp / Location.elapsedRealtimeNanos, same monotonic clock)

### Tier 1 — essential
| Stream | Android source | Rate request | Columns |
|---|---|---|---|
| acc | TYPE_ACCELEROMETER | FASTEST (expect 100–500 Hz) | t_ns, ax, ay, az, accuracy |
| acc_unc | TYPE_ACCELEROMETER_UNCALIBRATED | FASTEST | t_ns, ax, ay, az, bx, by, bz |
| gyr | TYPE_GYROSCOPE | FASTEST | t_ns, gx, gy, gz, accuracy |
| gyr_unc | TYPE_GYROSCOPE_UNCALIBRATED | FASTEST | t_ns, gx, gy, gz, bx, by, bz |
| mag | TYPE_MAGNETIC_FIELD | FASTEST (~100 Hz) | t_ns, mx, my, mz, accuracy |
| mag_unc | TYPE_MAGNETIC_FIELD_UNCALIBRATED | FASTEST | t_ns, mx, my, mz, bx, by, bz |
| gnss_fix | LocationManager GPS_PROVIDER, minTime 0, minDist 0 | ~1 Hz | t_ns, wall_ms, lat, lon, alt, acc_h, acc_v, speed, speed_acc, bearing, bearing_acc, provider, elapsed_unc_ns, is_mock, n_sats_used |
| fused_fix | FusedLocationProviderClient, HIGH_ACCURACY, 1000 ms | ~1 Hz | same columns, provider="fused" (secondary; never used as reference) |
| gnss_status | GnssStatus.Callback | per fix | t_ns, constellation, svid, cn0, elev, azim, used_in_fix, carrier_freq_hz, has_ephemeris |
| events | app UI / gate | sparse | t_ns, wall_ms, type (SESSION_START, CALIB_START, CALIB_END, RIDE_START, STOP, OUTAGE_ON, OUTAGE_OFF, NOTE), text |

### Tier 2 — useful virtual sensors
| Stream | Source | Columns |
|---|---|---|
| grav | TYPE_GRAVITY | t_ns, gx, gy, gz |
| linacc | TYPE_LINEAR_ACCELERATION | t_ns, ax, ay, az |
| rotvec | TYPE_ROTATION_VECTOR | t_ns, qx, qy, qz, qw, heading_acc_rad |
| gamerot | TYPE_GAME_ROTATION_VECTOR | t_ns, qx, qy, qz, qw |
| geomagrot | TYPE_GEOMAGNETIC_ROTATION_VECTOR | t_ns, qx, qy, qz, qw |
| baro | TYPE_PRESSURE (~25 Hz) | t_ns, hPa |

### Tier 3 — archive for diagnosis
| Stream | Source | Columns |
|---|---|---|
| gnss_raw | GnssMeasurementsEvent.Callback | t_ns, clock fields (timeNanos, fullBiasNanos, biasNanos, driftNanosPerSecond, hwClockDiscontinuityCount), per-sat: constellation, svid, cn0, pseudorangeRate, pseudorangeRateUnc, adrState, adr_m, adrUnc, carrierFreq, multipathIndicator, receivedSvTimeNanos, state |
| nmea | OnNmeaMessageListener | t_ns, sentence |
| sys | BatteryManager + PowerManager thermal + Display rotation, every 5 s | t_ns, batt_pct, charging, batt_temp, thermal_status, rotation |
| light/prox | TYPE_LIGHT, TYPE_PROXIMITY | t_ns, value |

Not recorded: camera, microphone, Wi-Fi/BT scans (permissions, no value for the IMU engine).

### Session metadata (session.json, written at start, patched at stop)
session_uuid, route_id, direction (AB/BA), run_no, purpose (pilot/train/val/test/demo), rider_id, vehicle_id ("roadeo_1"), mount_id ("downtube_tape_v1"), mount_photo_ref, phone model/Android/OneUI/build, app_version, sensor inventory (name, vendor, version, type, resolution, maxRange, minDelay, maxDelay, power) for every sensor, requested vs achieved rates (median dt, p99 dt, gaps>50 ms count) per stream, wall_clock_at_start vs elapsedRealtimeNanos_at_start (and a re-sample every 60 s), start/stop wall time, weather/notes, start_anchor {lat, lon, n_fixes, std_m}, end_anchor {…}, anchor_distance_m, polyline_length_m.

## Writing
- Each listener → lock-free queue → one writer thread per stream, 64 KB buffered writer, flush every 1 s, fsync at stop. Never write on the sensor thread.
- Register IMU listeners with an explicit samplingPeriodUs = 2000 (500 Hz request; the HAL clamps to its minDelay) and maxReportLatencyUs = 0 on a dedicated HandlerThread. The manifest declares HIGH_SAMPLING_RATE_SENSORS, otherwise everything is capped at 200 Hz.
- Raw GNSS: GnssMeasurementRequest with setFullTracking(true) and setIntervalMillis(0). NMEA timestamps are UTC ms from the chipset, not elapsedRealtime: store both clocks and map through the (elapsedRealtimeNanos, currentTimeMillis) pair written at file start and every 60 s.
- On stop: patch session.json, zip the folder, show the summary (achieved rates, gaps, anchors, distance).
- Never drop a stream silently: if a sensor type is absent, write a `MISSING` line in session.json and show it in the inventory screen.

## Screens
1. **Setup**: route_id, direction (AB/BA toggle), run_no (auto-increment), purpose, rider, notes. Sensor inventory button (lists every sensor + vendor + min delay, screenshot this once). Permission checks with red/green.
2. **Session** (big, readable from 1 m): live achieved rates per stream (acc/gyr/mag Hz), GNSS age (s), accuracy (m), sats used/visible, mean C/N0, battery, storage, dropped-event counter, current state. One large START button → 15 s stationary countdown (CALIB) → "RIDE" state. One large STOP → 15 s stationary countdown at the end → writes anchors.
3. **Outage gate** (used from Saturday): a toggle "SIMULATED GNSS DENIAL" that only writes OUTAGE_ON/OFF events during collection; in nav mode it also blocks GNSS from the estimator. Predetermined-interval mode: "start outage X s after RIDE, hold for Y s" so the rider never touches the phone.
4. **Breadcrumb** (tiny map-free canvas of lat/lon points) just to confirm fixes are arriving.
5. **Sessions list**: zip / share / delete.

## Protocol per run (the rider's checklist)
1. Tape check, cage stop check, phone top edge clear.
2. Fill Setup (direction, run_no auto). Tap START. Stand still, bike upright, both feet on ground, 15 s.
3. Ride the corridor normally unless the run has a variation. Do not touch the phone.
4. At the end anchor: stop, stand still 15 s, tap STOP. Read the summary: rates ≥ 100 Hz, gaps = 0, GNSS accuracy < 10 m, sats ≥ 8. If not, redo.
5. Every 4 runs: `adb pull` or share the zips to the Mac.

## Rates and clocks
- IMU: request FASTEST, log what arrives. 100 Hz is the minimum acceptable; Samsung flagships commonly deliver 200–500 Hz on FASTEST. Do not decimate in the app; a filtered 10 Hz branch for IO-VNBD compatibility is made offline (anti-aliased, not every-nth sample).
- GNSS fixes ≈ 1 Hz. The 10 Hz requirement is for the filter output, not the fixes.
- Join streams by t_ns only. Never by row.
