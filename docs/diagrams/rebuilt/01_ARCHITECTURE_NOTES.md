# Architecture detail revision

The diagram retains the original eight-block flow, with targeted technical detail and a wide 1600 × 660 content canvas for placement beneath a PPT heading. Output PNG is 3840 × 1584. Barlow font embedded. Prior version saved in previous/01_before_detail_revision/.

## Evidence and scope

- Phone IMU: approximately 420 Hz measured sensor capture and common monotonic timestamps. See docs/16_APP_RESULTS.md and Engine.kt.
- Filter and alignment: causal 40 Hz anti-alias filter, 100 Hz resampling, gravity levelling and forward-axis alignment. See Resampler.kt, Aligner.kt, docs/12_ENGINE_SPEC_for_kotlin.md §§2–3.
- CNN: the shipped joint model consumes 256 samples across six channels, predicts speed and variance, and occupies approximately 240 KB as a LiteRT model. See SpeedModel.kt, engine/export/export.py, docs/16_APP_RESULTS.md §8.12. The route-specific override described in an earlier spec is not shipped.
- Heading and stops: a logical group for the parallel IMU motion checks, not a single source-code class. Gyro heading includes stand-bias and gated tilt correction; accepted GNSS course aids yaw. A 0.5-second accelerometer-vibration/gyro-RMS check supplies the stop flag. The diagram explicitly connects heading and stop information to fusion.
- GNSS gate: fix age, horizontal accuracy, used satellites and C/N0 determine whether fixes aid alignment, heading, corridor recognition and fusion. Bad or absent fixes suppress GNSS updates. No millisecond outage-detection claim is made.
- Corridor: recognised offline road geometry and travel direction constrain progress along a polyline; general mode integrates speed and heading when not on a recognised corridor.
- Fusion: predicted model variance controls speed measurement weight; stillness triggers a zero-velocity update; GNSS measurement noise is inflated during the first three seconds after reacquisition. This softens corrections but is not a promise of jump-free recovery.
- HMM map matching: an optional general-mode display adjustment only, never feedback into fusion. The actual corridor constraint is a separate estimator input.

## Visual audit

All connections have defined source and destination blocks. No HMM feedback arrow. No model-training accuracy is presented as live field performance. Render inspected at 1280 × 528; no overflowing blocks or content beyond the canvas. The working-prototype content is unchanged.
