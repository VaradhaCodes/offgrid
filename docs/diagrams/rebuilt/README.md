# OFFGRID presentation visuals

Two full-slide diagrams rebuilt from the implemented bicycle system, then simplified for a one-minute explanation. No material from the proposed vehicle research architecture is included.

## Use in PowerPoint

- `01_architecture.png`: Navigation architecture.
- `02_working_prototype.png`: Recording, preparation, model training, validation and the app replay.
- Each image is **3840 × 2160**, exactly **16:9**. Insert the PNG as a picture and fit it to the full slide. The title is already included. Use the original image file rather than a screenshot of a preview.
- The two same-named HTML files are independent, offline documents. Fonts and screenshots are embedded. Open either in a browser to view at any window size. `index.html` shows both together.
- Font: **Barlow**, regular and semibold. The actual app uses Barlow for its text and Barlow Semi Condensed for the large speed numbers. The diagram text uses ordinary Barlow to keep body text readable.
- `build.mjs` is the editable HTML/CSS/SVG source. `render.mjs` exports the images using a browser. Phone images remain the original captures, without simulated interface text or generated details.

## Source and claim decisions

The current Kotlin application and `docs/16_APP_RESULTS.md` take precedence over the older attachment where they disagree. The attachment predates the completed app results and says that document did not yet exist.

### Architecture

Sources: `docs/12_ENGINE_SPEC_for_kotlin.md`, `docs/16_APP_RESULTS.md`, `IDRNav/engine/src/main/kotlin/com/snu/idr/engine/Engine.kt`, `Fusion.kt`, `HeadingFilter.kt`, `Aligner.kt`, `SpeedModel.kt`, and `IDRNav/app/src/main/java/com/snu/idrlogger/service/EngineRunner.kt`.

- Approximately 420 Hz accelerometer/gyro, causally filtered and resampled to 100 Hz.
- The CNN consumes 256 samples across six IMU channels, a 2.56 s window. 57,602 parameters and 239,688-byte TFLite export, rounded to 57.6k and 240 KB.
- Gyro heading is corrected by accepted GNSS course measurements. The GNSS gate separately supplies alignment with speed, the heading filter with course, and fusion with accepted position/speed.
- Corridor recognition combines offline corridor geometry with accepted GNSS fixes. In corridor mode the filter advances along the road. General mode uses gyro heading. The inactive scale state is omitted in the displayed state notation.
- The physical stop rule supplies zero-velocity updates. CNN measurement updates continue during a GNSS outage. The architecture does not say “prediction only.”
- GNSS recovery reduces measurement weight for three seconds. No claim of zero position jumps is made.
- The HMM road matcher is display-only in general mode, never a feedback correction to the fusion estimate. This secondary display feature is omitted from the simplified visual.
- Arrows show principal data dependencies, not every internal feedback or code call. The simplified fusion box omits state notation and detailed timings. The engine also supplies a fallback speed to the aligner during outages.

### Prototype evidence

- 30 quality-controlled rides: 20 on road 1, 10 on road 2. The small road figures show actual stored corridor coordinates at independent scales, without scale claims.
- The sensor trace uses `docs/diagrams/src/imu_window.json` and is not a decorative invented waveform.
- The current visual shows 10 out of 10 below 10%. Supporting results are 2.33% median / 6.26% worst: `docs/11_ENGINE_RESULTS.md`, “Engine on route 2 with the joint held-out speeds,” 30-second cut, corridor mode with fixed scale, grouped five-fold evaluation. Outages span 600–850 m. These are endpoint drift percentages relative to withheld-GNSS reference, measured offline. They are not live field-test results.
- The previous diagram's 1.52% result is for a route-specific model evaluated under a different split. The current app's `EngineRunner` constructs the joint model, and its packaged `model/model.json` confirms that model. The rebuilt slide therefore uses the matching joint-model result.
- App captures: `docs/diagrams/src/img/hp_locked.png`, `hp_dr.png`, `hp_reveal.png` and `hp_logger.png`.
- 17.3 m after 569 m is the recorded-route-2-run-4 replay shown in the real app UI, also documented in `docs/16_APP_RESULTS.md` §4. This is a training-run demonstration with online alignment, distinct from held-out evaluation.
- During a simulated outage, GNSS remains recorded as a reference. Its measurements are withheld from the estimator. No completed fresh navigation field ride or lane-level validation is implied.

Design reference: [Impeccable's published design guidance](https://impeccable.style/slop/), consulted for visual hierarchy and removal of unnecessary interface decoration. No Impeccable plugin or automated detector was installed or run.

## Simplification audit

See `AUDIT.md` for the content cuts and evidence checks. The architecture has 57% less authored text and the prototype 44% less than the previous version. Earlier files are preserved in `previous/`.
