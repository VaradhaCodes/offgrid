# Engine + model build brief, v2 — route 1 first, then route 2

Goal: the best-performing speed model and dead-reckoning engine we can MEASURE on held-out rides, exported for the Samsung S23 Ultra, with a written spec so the navigation app can port it exactly. No time budget is imposed here; the only arbiter is the evaluation harness. Bigger is not better: 20 runs is ~30 minutes of riding, so the harness will punish anything that overfits. Build in Python first. The app comes after the engine is frozen.

## What exists (read first)
- Plan/refs: `docs/00_PLAN_prototype.md`, `docs/02_ENGINE_architecture.md`, `docs/03_REFERENCES.md` (verified: DeepOdo, DVSE, CarSpeedNet, cycling MoE arXiv 2510.17604, AI-IMU, KF-GINS, Wheel-INS, LeuvenMapMatching, Newson–Krumm, LiteRT/ONNX Runtime). Results so far: `docs/06`, `07`, `09`, `13`.
- Data: route 1 = `data/route1/sessions/<session>/` (20 kept runs, run8 excluded, manifest `data/route1/manifest.csv`); route 2 = `data/route2/sessions/` (arriving, 10 round trips, several riders). Decoded tables: `data/processed/<session>/{imu_native.csv, track_100hz.csv, gnss_fixes.csv}` via `engine/decode_session.py`. Corridors: route 1 = OSM ways 547215901+547215900 (in `data/map/snu_osm_highways_900m.json`, build its polyline the way `corridor_route2.geojson` was built), route 2 = `data/map/corridor_route2.geojson`, campus graph = the same OSM json (276 ways).
- Code: `engine/decode_session.py`, `engine/baseline_dr.py` (quaternion strapdown), `engine/ml_rectify_demo.py` (window features, GBR proxy, physical stop rule, smoothing, robust gyro bias), `engine/loro_cv.py` (leave-one-run-out + outage replay, `--cut N`). Env: `.venv` (numpy, pandas, scipy, matplotlib, sklearn). Mac M2 Pro 16 GB is sufficient; add torch or tensorflow as needed.
- Measured baselines: pure INS 1.5 km error in 70 s; gyro heading ~2° when bias is right; proxy speed model 0.26 m/s MAE; LORO drift median 3.7 % (10 s cut) / 5.5 % (30 s cut), 16–17 of 20 under 10 %; last-speed-hold 13–19 %. The remaining bad runs (12/15/17) have a wrong gyro bias because the rider moved during the 15 s stand.
- Mount: phone wedged in the bottle cage of a KROSS bike; pitch ~25.5° ± 0.9° on route 1, but one route-2 run was seated 18° differently and several runs have rider motion during the stands. The engine must be robust to both.

## Hard design rules (quality rules, not shortcuts)
1. One engine, always running. GNSS is a measurement that may stop; nothing is switched on at the outage. Real-outage detector: no fix > 1.5 s OR accuracy > 30 m OR sats used < 4 OR mean C/N0 of used sats < 22 dB-Hz OR the simulated flag. Recovery: inflated GNSS sigma for ~3 s, then normal; never rewrite the displayed outage track.
2. The accelerometer is never integrated for speed. Speed = model; heading = gyro; accelerometer = tilt + stop rule.
3. Causal only. Windows never straddle the stand/ride boundary.
4. Split by whole runs; normalisation from training runs only; locked test runs are never used for any choice.
5. The harness decides. No component enters without a measured gain on held-out runs. Report distributions (median, worst, count under 10 %), never a single best run.
6. Port-friendly: runtime code in plain numpy (no scipy at inference), fixed shapes, explicit constants. The engine must be reproducible in Kotlin line by line. This is why the engine stays compact; it is not an effort limit.

## Evaluation protocol (implement first, `engine/evaluate.py`)
- Leave-one-run-out on route 1; grouped 5-fold for wide sweeps, LORO for finalists.
- Cuts at 10 s, 30 s, 60 s after motion start, plus a cut placed inside the sharp turn; outage runs to the end of the ride; also "outage + 20 s after the stop" to score stop behaviour.
- Rider-held-out on route 2 (rider field), and cross-road transfer both ways (train R1 → test R2, train R2 → test R1), then the joint model.
- Metrics: speed MAE (moving), speed bias, stop latency (s) and false stops, heading error during outage, endpoint error, drift %, RMSE, max error, error 20 s after the stop, recovery jump on GNSS return, per-tick latency of the exported model on the phone.
- Targets: speed MAE < 0.20 m/s; median drift < 4 % and every run < 10 % at the 30 s cut; heading < 3° on every run; stop detected within 1 s with zero false stops; model < 300 KB and < 5 ms per 10 Hz tick single-threaded.

## Build order (results go to `docs/11_ENGINE_RESULTS.md` after every step)
1. **Data QA automation** (`engine/qa.py`): per-run rates/gaps, mount pitch/roll vs the session median, impact count, rider motion during stands, start/end anchor sanity. Flags, never silent drops.
2. **Alignment** (`engine/align.py`): R_phone→bike from the stand (tilt) + first straight acceleration (forward axis by PCA of horizontal accel, sign from GNSS speed increase); re-estimate when the gyro says the phone moved. Validate: bike yaw rate = gyro z, forward accel positive at start, roll = lean in turns.
3. **Heading and bias** (`engine/heading.py`): gyro bias as a state, initialised from the stand (robust), refined from GNSS bearing rate while GNSS is healthy (speed > 1.5 m/s, latency-aware sigma); heading maintained continuously. Gate: heading < 3° on all 20 runs including 12/15/17.
4. **Speed model sweep** (`engine/speed_model/`), all with Gaussian NLL (speed + log-variance) and the physical stop rule as a hard override:
   (a) GBR on hand features (existing, the bar to beat);
   (b) 1-D CNN on raw vehicle-frame 6-ch windows (DeepOdo/CarSpeedNet style), windows 1.28 s and 2.56 s;
   (c) CNN + GRU with carried state (DVSE style), shorter window to cut stop latency;
   (d) TCN and ResNet-1D (RoNIN/TLIO style);
   (e) CNN + hand features concatenated;
   (f) inputs at 100 Hz vs 200 Hz (wheel harmonics live above 12 Hz).
   Augmentation: rotation ±5° (covers the 18° seating case partially; also train with per-run alignment), gain ±5 %, noise, time-warp ±5 %, random window offsets. Multi-task head: speed, stop probability. Ensemble 3–5 seeds if it measurably helps. Calibrate the uncertainty (coverage of the 1-sigma band ≈ 68 %); the filter needs it to be honest.
   Selection by LORO drift at the 30 s cut, tie-break by latency and size. Export (TFLite from Keras, or ONNX from PyTorch) and verify exported == Python to 1e-4.
5. **Online scale calibration** (`engine/filter.py`, the fusion "AI" part): while GNSS is healthy, estimate the model's scale/bias state k_v against GNSS speed; during the outage, apply it. This is what removes the per-rider/per-route bias seen in transfer. Measure its gain in the cross-road and rider-held-out tests.
6. **Filter**: corridor mode (arc-length s, speed v, scale k_v) with GNSS projected on the polyline, model speed as a measurement with the calibrated sigma, ZUPT, turn-landmark resets, recovery blending; plus general mode (position, heading, k_v) for roads without a corridor. Compare against the plain integration in `loro_cv.py`.
7. **Map matching for the general mode** (`engine/mapmatch.py`): Newson–Krumm HMM over the campus OSM graph (or LeuvenMapMatching offline), heading-gated, with the matched edge bearing fed back as a soft heading prior. Gate: must not degrade the corridor results; must run causally with ≤ 3 s lag.
8. **Replay harness** (`engine/replay.py`): any session + denial zone (time window or polygon) → 10 Hz output CSV, metrics, plot. Also the app's conformance test.
9. **Spec for the app** (`docs/12_ENGINE_SPEC_for_kotlin.md`): state, inputs/outputs, constants, step-by-step maths, exported model, one reference session with expected outputs (tolerance max |Δpos| < 1 m).
10. **IO-VNBD**: steps 2–6 on 2 sequences (car, 10 Hz, masked GNSS): plots + drift table. Mandatory screening artefact; proves external-IMU support.
11. **Route 2 when it lands**: QA → LORO on R2 → transfer both ways → joint model → pick the demo road on numbers.

## Deep-research tasks (agent type `deep-researcher`, background, one page each, verified sources only; reputable labs/repos; return only what changes a decision above)
R1. Exact training recipes of DeepOdo (IEEE TIM 2023), DVSE (arXiv 2505.18490), CarSpeedNet (2401.07468), cycling MoE (2510.17604): window, channels, normalisation, loss, augmentation, labels, size, MAE, code if any.
R2. LiteRT/TFLite and ONNX Runtime Mobile: exporting 1-D CNN / GRU / TCN with carried state, quantisation effects on regression, measured latency on Snapdragon 8 Gen 2 class CPUs, op pitfalls.
R3. Loosely-coupled ESKF with NHC/ZUPT and GNSS-bearing-aided gyro-bias estimation for MEMS IMUs: measurement models and noise settings from KF-GINS / Wheel-INS / AI-IMU; latency-compensated bearing; bias observability in turns; online scale-factor estimation of a learned speed/odometer (search: "odometer scale factor estimation Kalman", "learned velocity scale online calibration").
R4. Stop / zero-velocity detection for bicycles and two-wheelers from phone IMU (thresholds, windows, false-stop rates), and stop-latency handling with short windows or recurrent state.
Skip research on datasets and map matching libraries: done in docs/03.

## Optional experiments, only if the sweep plateaus above target
- Pretraining on comma2k19 / GSDC-2023 (car, GBs of data); catch: car vibration ≠ bicycle vibration, likely small gain, large download and time.
- Learned stop detector replacing the physical rule; catch: needs the stop-runs data that route 1 lacks.

## Do not
- Do not use the magnetometer. Do not integrate the accelerometer for speed.
- Do not train on route 2 before its QA and the transfer test.
- Do not report a number that is not from held-out runs. Do not tune on locked test runs.
