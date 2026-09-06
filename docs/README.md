# Documentation

These files were written as the work happened, in order, and they are numbered that way. Nothing has been tidied up after the fact to make a decision look better than it was — where a measurement overturned an earlier choice, both the earlier section and the correction are still here.

If you only read three: **[11](11_ENGINE_RESULTS.md)** for what the engine achieves, **[12](12_ENGINE_SPEC_for_kotlin.md)** for how it works, **[16](16_APP_RESULTS.md)** for what the phone actually does.

## Results

| | |
|---|---|
| [**11_ENGINE_RESULTS.md**](11_ENGINE_RESULTS.md) | The main results document. Every step of the engine, every sweep, every held-out table, per-run, for both roads. Also the record of what did not work: the scale state, the gyro-bias state, the label-lag sign error. |
| [**16_APP_RESULTS.md**](16_APP_RESULTS.md) | What was built on the phone and how it measures: JVM and device conformance to the Python engine, model latency, the outage scenario, the design pass, the live bench, and an explicit list of deviations from the brief. |
| [06_BASELINE_run3.md](06_BASELINE_run3.md) | The classical dead-reckoning baselines on real data. This is the document that establishes speed, not heading, as the problem to solve. |
| [07_ML_RECTIFY_pilot.md](07_ML_RECTIFY_pilot.md) | First evidence that a learned speed model rectifies IMU dead reckoning, on two pilot rides. |

## Specifications

| | |
|---|---|
| [**12_ENGINE_SPEC_for_kotlin.md**](12_ENGINE_SPEC_for_kotlin.md) | The engine as plain arithmetic on fixed-size arrays — every constant, gate and state transition, written to be portable line by line. v2 is the shipped version; changes from v1 are in §10. |
| [02_ENGINE_architecture.md](02_ENGINE_architecture.md) | The original architecture: data flow, module responsibilities, evaluation plan. |
| [01_APP_SPEC_logger.md](01_APP_SPEC_logger.md) | The data-collection app, screen by screen and stream by stream. |
| [14_APP_PLAN_nav.md](14_APP_PLAN_nav.md) | The navigation app's design: screens, camera, puck, the outage scenario, the offline map stack. |

## Build briefs

Written before each build, fixing the target and the acceptance tests in advance so the result could be measured rather than argued about.

| | |
|---|---|
| [00_PLAN_prototype.md](00_PLAN_prototype.md) | The whole prototype plan: vehicle, phone, route, protocol, schedule, and the rules about what may and may not be claimed. |
| [04_BUILD_BRIEF_logger_apk.md](04_BUILD_BRIEF_logger_apk.md) | The logger APK brief. |
| [10_ENGINE_BUILD_BRIEF.md](10_ENGINE_BUILD_BRIEF.md) | The engine and speed-model brief: design rules, evaluation protocol, build order, targets. |
| [15_NAV_APP_BUILD_BRIEF.md](15_NAV_APP_BUILD_BRIEF.md) | The navigation app brief: fixed facts, design tokens, the scenario, and the eleven acceptance tests scored in doc 16. |

## Field and data quality

| | |
|---|---|
| [05_PILOT_QA_20260904.md](05_PILOT_QA_20260904.md) | First two rides. Does the logger actually work on this phone? |
| [08_ROUTE2_QA_and_plan.md](08_ROUTE2_QA_and_plan.md) | Survey of the football-ground road, which became road 1. |
| [09_ROUTE1_verdict_and_next_data.md](09_ROUTE1_verdict_and_next_data.md) | Verdict on road 1 after 20 rides, the gyro-bias contamination finding, and what to collect next. |
| [13_ROUTE2_as_ridden_QA.md](13_ROUTE2_as_ridden_QA.md) | Survey of the Circular Road corridor, which became road 2 and the demo road. |

## Research

Seven reviews, in [`research/`](research/). Each one records what was actually fetched and marks anything it could not verify as `UNVERIFIED`.

| | |
|---|---|
| [R1_training_recipes.md](research/R1_training_recipes.md) | Published learned-speed models: window lengths, sample rates, losses, augmentation, corpus sizes. What the literature does and does not settle. |
| [R2_mobile_export.md](research/R2_mobile_export.md) | Getting a model onto the phone: LiteRT vs ONNX Runtime, XNNPACK op coverage, why recurrence hurts, why quantisation was rejected. |
| [R3_eskf_scale.md](research/R3_eskf_scale.md) | Error-state Kalman filtering, non-holonomic constraints, MEMS noise values, GNSS latency handling, and the odometer scale-factor model. |
| [R4_stop_detection.md](research/R4_stop_detection.md) | Zero-velocity detection. There is no published bicycle detector with thresholds, so this is what could be transferred and what had to be measured. |
| [R5_map_ui_references.md](research/R5_map_ui_references.md) | Navigation UI design references and the rules the app was held to. |
| [R6_map_stack_android.md](research/R6_map_stack_android.md) | The Android offline map stack, with exact versions and the traps in each. |
| [R7_campus_map_data.md](research/R7_campus_map_data.md) | Campus map data sources, licences and satellite imagery terms. |
| [03_REFERENCES.md](03_REFERENCES.md) | The consolidated bibliography — datasets, papers, repos. Verified links only. |

## Assets

| | |
|---|---|
| [slides/](slides/) | The submitted SIH deck: PDF and page images. |
| [diagrams/](diagrams/) | The slide artwork and the code that generates it. `rebuilt/` is the final set; its `*_NOTES.md` files record the evidence behind every claim on every diagram. |
| [figures/](figures/) | Result plots and route maps used across these documents. |
| [screens/](screens/) | 26 screenshots of the navigation app on the device, dark theme, at font scale 1.0 and 1.3. |
| [qa_app/](qa_app/) | Reference JVM engine output for the conformance sessions. |
