# Build brief — IDR Logger APK

Goal: a debug APK for a Samsung Galaxy S23 Ultra (One UI 8.5 / Android 16) that logs every navigation-relevant sensor stream to CSV files while the phone is taped to a bicycle, so the team can collect training data TONIGHT. No map, no model, no navigation UI. Full stream/screen spec is in `01_APP_SPEC_logger.md` (same folder); this file is the execution order.

## Environment facts (already verified on this Mac)
- Android SDK: `~/Library/Android/sdk` with platforms android-36 and android-37, build-tools 35.0.0 / 36.0.0 / 37.0.0, platform-tools (adb 37.0.1), cmdline-tools/latest (sdkmanager). No Android Studio. No `gradle` on PATH.
- JDK: Homebrew OpenJDK 21 at `/opt/homebrew/opt/openjdk@21` (keg-only, not on PATH). Use `export JAVA_HOME=/opt/homebrew/opt/openjdk@21` and `export ANDROID_HOME=$HOME/Library/Android/sdk` and `export PATH=$ANDROID_HOME/platform-tools:$JAVA_HOME/bin:$PATH`.
- Gradle: no wrapper jar exists yet. Either `brew install gradle` then `gradle wrapper --gradle-version 8.11.1` inside the project, or download `https://services.gradle.org/distributions/gradle-8.11.1-bin.zip`, unzip to a scratch dir, and run its `bin/gradle wrapper`.
- Versions that work together: Gradle 8.11.1, AGP 8.10.x (compileSdk 36) or AGP 8.6+ (compileSdk 35), Kotlin 2.0.x, JDK 21. Use `local.properties` with `sdk.dir=$HOME/Library/Android/sdk`. If `platforms;android-35` is needed, `sdkmanager "platforms;android-35"`; otherwise compileSdk 36 with the installed android-36.
- Phone: enable Developer options (tap Build number 7×), USB debugging ON, plug in, accept the RSA prompt. `adb devices` must show the phone. Wireless debugging (pair with code) is the backup.

## Project shape (Kotlin, XML Views, no Compose)
```
IDRLogger/
  settings.gradle.kts, build.gradle.kts, gradle.properties, local.properties
  app/build.gradle.kts   (applicationId com.snu.idrlogger, minSdk 29, targetSdk 35, compileSdk 36)
  app/src/main/AndroidManifest.xml
  app/src/main/java/com/snu/idrlogger/
     MainActivity.kt        setup form + big START/STOP + live stats
     LogService.kt          foreground service (type location), wake lock, all listeners
     StreamWriter.kt        per-stream buffered CSV writer on its own thread
     SensorInventory.kt     dumps every sensor (name, vendor, version, type, resolution, maxRange, minDelay, maxDelay, isWakeUp, fifoMax) to session.json
     Anchors.kt             averages stationary GNSS fixes at start/end, geodesic distance
  app/src/main/res/layout/activity_main.xml
```
Dependencies: only `androidx.core:core-ktx`, `androidx.appcompat:appcompat`, `com.google.android.material:material`, `androidx.lifecycle:lifecycle-service` (optional). No Play Services needed: use `LocationManager` (GPS_PROVIDER for the reference; also register FUSED_PROVIDER as a secondary stream if available on API 31+).

## Manifest essentials
```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION"/>
<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
<uses-permission android:name="android.permission.HIGH_SAMPLING_RATE_SENSORS"/>
<uses-permission android:name="android.permission.WAKE_LOCK"/>
<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS"/>
<service android:name=".LogService" android:foregroundServiceType="location" android:exported="false"/>
```
Start the service from the visible Activity with `startForegroundService`, then inside it `ServiceCompat.startForeground(this, 1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)`. Runtime-request FINE_LOCATION and POST_NOTIFICATIONS before starting. Acquire a PARTIAL_WAKE_LOCK and set `FLAG_KEEP_SCREEN_ON` on the Activity.

## Listeners (all on one dedicated HandlerThread; timestamps as delivered, never re-stamped)
- SensorManager: for each of TYPE_ACCELEROMETER, TYPE_ACCELEROMETER_UNCALIBRATED, TYPE_GYROSCOPE, TYPE_GYROSCOPE_UNCALIBRATED, TYPE_MAGNETIC_FIELD, TYPE_MAGNETIC_FIELD_UNCALIBRATED, TYPE_GRAVITY, TYPE_LINEAR_ACCELERATION, TYPE_ROTATION_VECTOR, TYPE_GAME_ROTATION_VECTOR, TYPE_GEOMAGNETIC_ROTATION_VECTOR, TYPE_PRESSURE, TYPE_LIGHT, TYPE_PROXIMITY: `registerListener(l, sensor, samplingPeriodUs = 2000, maxReportLatencyUs = 0, handler)`; skip and record MISSING if `getDefaultSensor` returns null. Write `event.timestamp` (ns, elapsedRealtime base) + all values (+ accuracy).
- LocationManager: `requestLocationUpdates(GPS_PROVIDER, 0L, 0f, listener, looper)`; write elapsedRealtimeNanos, time (UTC ms), lat, lon, altitude, accuracy, verticalAccuracyMeters, speed/hasSpeed, speedAccuracyMetersPerSecond, bearing/hasBearing, bearingAccuracyDegrees, elapsedRealtimeUncertaintyNanos, isMock, provider.
- `registerGnssStatusCallback`: per satellite svid, constellationType, cn0DbHz, basebandCn0DbHz, elevation, azimuth, usedInFix, hasEphemeris, hasAlmanac, carrierFrequencyHz; count used/visible for the UI.
- `registerGnssMeasurementsCallback(GnssMeasurementRequest.Builder().setFullTracking(true).build(), executor, cb)`: write GnssClock fields once per event and one row per measurement (svid, constellation, cn0, pseudorangeRateMetersPerSecond, pseudorangeRateUncertainty, accumulatedDeltaRangeState/Meters/Uncertainty, carrierFrequencyHz, receivedSvTimeNanos, state, multipathIndicator, agc if available, codeType if API ≥ 31). Wrap in try/catch; not fatal if unsupported.
- `addNmeaListener(executor) { msg, ts -> }`: ts is UTC ms; also write `SystemClock.elapsedRealtimeNanos()` at receipt.
- Every 5 s: battery %, charging, battery temp, `PowerManager.currentThermalStatus`, display rotation. At session start and every 60 s: one line with (elapsedRealtimeNanos, currentTimeMillis) for clock mapping.
- Events file: SESSION_START, CALIB_START, CALIB_END, RIDE_START, STOP_CALIB_START, SESSION_END, plus a NOTE button.

## Files
Session dir: `getExternalFilesDir(null)/sessions/<yyyyMMdd_HHmmss>_<route>_<dir>_run<N>/` with one CSV per stream (header row), `session.json` (metadata + sensor inventory + achieved rates + anchors), and `events.csv`. Writer: lock-free queue per stream → single writer thread, 64 KB buffer, flush every 1 s, fsync on stop. On STOP compute per-stream median dt, p99 dt, count of gaps > 50 ms, and start/end anchors (mean of fixes with accuracy < 15 m during the two stationary windows) with geodesic distance; show them on screen. Optional: zip the folder.
Pull with `adb pull /sdcard/Android/data/com.snu.idrlogger/files/sessions ./data/raw/`.

## Screen (one activity, readable from 1 m, dark background, large text)
Top: route_id (default `SNU_AJB`), direction toggle AB/BA, run_no (auto-increment, editable), purpose spinner (pilot/train/val/test/demo), notes. Middle: live acc/gyr/mag Hz, GNSS age s, accuracy m, sats used/visible, mean C/N0, battery %, dropped-events counter, state label. Bottom: one huge START button → 15 s countdown labelled STAND STILL → state RIDE; one huge STOP button → 15 s countdown STAND STILL → summary dialog. A small NOTE button. A "Sensor inventory" menu item that lists every sensor.

## Acceptance test before riding (10 min)
1. `./gradlew assembleDebug` succeeds; `adb install -r app/build/outputs/apk/debug/app-debug.apk`.
2. Samsung settings: app Battery → Unrestricted; Location → Allow all the time; keep the microphone system toggle ON (else sensors are rate-limited).
3. Run a 2-minute session on a table outdoors: acc/gyr ≥ 200 Hz shown, gaps = 0, GNSS accuracy < 10 m, sats ≥ 8, all Tier-1 files non-empty, session.json has the inventory. `adb pull` works.
4. If the build is not working within ~2 hours, do NOT block collection: install Sensor Logger (Kelvin Choi; enable the raw/uncalibrated toggle and the highest rate, location ON) on the S23 Ultra and Google GnssLogger on phone 2 in the rider's pocket, and collect with those. The offline pipeline accepts both formats.

## Ride protocol tonight (same for the custom app or the stop-gap apps)
- Mount: pad under the phone, three full cellotape wraps around tube + phone plus one long strip, phone bottom edge butted against the bottle cage (remove the can), top edge of phone uncovered, pen mark on the tube at the phone's top edge. Shake test before every run.
- Corridor `SNU_AJB` (see `00_PLAN_prototype.md` §1 and `docs/figures/campus_candidate_corridors.png`): A (28.528955, 77.575448) → J (28.524890, 77.573604, 90° right) → B (28.525982, 77.570515), 812 m. Ride it once first to confirm it is rideable; shorten from A if needed and note the new A.
- Per run: fill direction + run_no → START → stand still 15 s (bike upright, feet down) → ride → stop at the end anchor → STOP → stand still 15 s. Never touch the phone while moving.
- Order: P1 stationary 2 min on the mount; P2 one A→B and one B→A; check the summary numbers; then 12–16 runs alternating direction with these variations spread across them: normal pace ×5, slow ×2, brisk ×2, coast-and-brake ×2, a 3–5 s mid-route stop ×2, one standing-pedal run. Keep a paper log: run_no, direction, time, variation, anything odd.
- Phone 2 in the rider's pocket runs GnssLogger for the whole session as an independent GNSS reference. Phone 3 films one run for camera framing.
