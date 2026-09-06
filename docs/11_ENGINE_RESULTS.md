# Engine results — route 1 first (living document; updated after every build step)

Brief: `docs/10_ENGINE_BUILD_BRIEF.md`. Every number below is from held-out runs unless it is a data statistic. Research pages land in `docs/research/`.

## Status (final for routes 1 and 2, 5 Sep 2026 — the route-1 numbers in this table are re-measured after the two corrections found through route 2: the label-lag sign and the heading bias state; the original route-1 sections below are kept as the record)

| Step | Module | Status | Key result (held-out runs only) |
|---|---|---|---|
| 1 | `engine/qa.py`, `engine/session.py` | done, both routes | Route 1: 21 runs, 20 kept (run 8 aborted). Route 2: 12 runs, 10 kept (runs 1 and 7 false starts, 0 s ride); mount pitch sd 0.24° on runs 3–12, run 2's start stand contaminated (18° re-seat, 1.9 °/s bias) and handled. |
| 2 | `engine/align.py` | done, both routes | Sway-axis forward direction: 2.1° spread on route 1, 1.0° on route 2; ride-time levelling absorbs run 2's 18° stand offset; moved-phone monitor silent on route 2. |
| 3 | `engine/heading.py` | done, changed | Bias state dropped: `kfpsic` (ψ from the position course, robust stand bias held) is 28/30 runs under 3° at the 30 s cut over both routes (worst 4.1°); the v1 `kfc` state cost up to 20° on route 2's 200 s outages. Causal fallback for a moved stand measured (60 s to recover). |
| 4 | `engine/speed_model/` | done, corrected | Label lag re-measured (0.2 s, both routes) and its sign fixed (v1 model output was 0.8 s late). Joint model `cnn_r100_w256_joint` held out by pair: MAE 0.179 m/s on route 1 (route-1-only 0.195), 0.164 on route 2 (route-2-only LORO 0.172, transfer 0.228, GBR 0.212); 0 false stops on 30 runs; stop rule fires 0.7 s after rolling ends. |
| 5 | `engine/filter.py` (scale state k) | closed | Off on bicycle roads in both modes (30 runs: costs 0.3–3 % in the general mode, flips corridor runs both ways; Doppler labels within 0.5 % of position distance, so no scale to learn). On only for a grossly biased external source (IO-VNBD 24 → 14 %). |
| 6 | `engine/filter.py`, `engine/corridor.py` | done, both routes | 30 s cut, drift median / worst / under 10 %: route 1 (joint model) general 2.58 / 6.82 / 20, corridor 4.31 / 7.13 / 20; route 2 (800 m outages; route-2 corridor model, LORO) corridor 1.52 / 5.73 / 10, general 1.73 / 6.86 / 10; joint set under the same LORO 2.50 / 7.95 / 10; route 1 → route 2 transfer corridor 1.74 / 5.24 / 10. `LAG_V` 0.7 → 0.2 s (neutral). Route-2 corridor polyline validated on all runs, 20 m overhang added. |
| 7 | `engine/mapmatch.py` | display only | Unchanged (feedback rejected on route 1). |
| 8 | `engine/replay.py` | done, both routes | Route 2 corridor mode, all runs: 30 s cut 2.43 / 6.40 / 10 of 10, 18 m at the end of ~800 m. Conformance references regenerated for route-2 run 4 (2.62 %) and route-1 run 1 (2.92 %). |
| 9 | `docs/12_ENGINE_SPEC_for_kotlin.md` | v2 | Heading without bias state + stand rule, LAG_V 0.2, k off, label-lag constant, route-2 corridor, joint model section, two conformance references, v1 → v2 changelog. |
| 4-export | `engine/export/export.py` | done | Joint model: ONNX 230 KB / TFLite 240 KB, both within 1.9e-6 of PyTorch, XNNPACK-only ops, 0.07 ms per window on the Mac; phone latency still to be measured in the APK. |
| 10 | `engine/iovnbd.py` | done | Unchanged. |
| 11 | route 2 | **done** | QA → align → heading → LORO → transfer both ways → joint model → like-for-like LORO → engine and replay on route 2 → demo road = **route 2** (corridor mode 1.52 % / 5.73 % over 800 m with the route-2 corridor model against route 1's 4.31 / 7.13 over 200 m; four times the outage length through a 120° turn). Deployment: joint model everywhere, route-2 corridor model (seed-1 instance, acceptance-checked) on the demo corridor. Rider-held-out impossible (all sessions `rider_1`). |

### Targets vs achieved (held out; route 1 with the joint model by pair, route 2 with its corridor model under leave-one-run-out; engine with the v2 heading)

| Target | Route 1 (20 runs) | Route 2 (10 runs, outages 4× longer) |
|---|---|---|
| speed MAE < 0.20 m/s | 0.179 median, 0.406 worst run (joint) | 0.172 / 0.316 (route-2 corridor model, LORO); joint set 0.166 / 0.294 |
| median drift < 4 % and every run < 10 % at the 30 s cut | general 2.58 % / worst 6.82 %, corridor 4.31 % / 7.13 %, 20/20 both (joint model) | corridor 1.52 % / 5.73 %, general 1.73 % / 6.86 %, 10/10 both (route-2 corridor model, LORO); joint model 2.50 / 7.95 and 2.27 / 6.29 |
| heading < 3° on every run | 19/20 at the 30 s cut (worst 3.33°) | 9/10 (worst 4.14°: the first pair's 0.03 °/s residual stand bias over 200 s) |
| stop within 1 s, zero false stops | 0.7 s median after rolling ends (0.2–1.7 s), 0 false stops on 30 runs (mid-ride stops still unrecorded) | same |
| model < 300 KB, < 5 ms per tick single-thread | 240 KB TFLite, 0.07 ms on the Mac; phone unmeasured (no APK yet) | same model |

## Research inputs (as they land)

- **R1 training recipes** (`docs/research/R1_training_recipes.md`, verified from the four PDFs): no paper releases code or states normalisation. CarSpeedNet is the only window sweep and it is monotone (1 s → 1.30 m/s MAE, 2 s → 1.00, 4 s → 0.72); DVSE uses 10 s of 1 s features, the bicycle MoE 2 s. All train at 20–50 Hz; nothing above 50 Hz is shown to help. DVSE's ablation makes random 3-axis rotation augmentation the single most valuable trick (+58 % error without it). Only the bicycle MoE uses Gaussian NLL, and it uses MSE + NLL with a diagonal covariance fed to the EKF. Sizes that work on ~10 h: 178 k params (0.68 MiB). Stops are handled outside the network (DeepOdo: std-threshold ZUPT). GNSS speed labels lag the IMU by ~1 s (DVSE: min-over-shift loss). Smallest published corpus is 20× our 30 min. **Consequences for the step-4 sweep**: keep 2.56 s as the default window and add 5.12 s; test 50/100/200 Hz instead of assuming 200 Hz; rotation + gain augmentation mandatory; MSE + NLL head; cap at ~200 k params and prefer far smaller; estimate the GNSS label lag per run by cross-correlation before training; the harness (not the paper) decides each of these.
- **R2 mobile export** (`docs/research/R2_mobile_export.md`, 41 fetched sources): LiteRT rewrites Conv1D to CONV_2D, which is on XNNPACK's fp32 fast path; ONNX Runtime's XNNPACK provider supports 2-D conv only, so a 1-D CNN gets no acceleration there. Recurrent layers are where LiteRT hurts (stateful Keras LSTM conversion is "future work", GRU lowers to While ops, Flex delegate takes the runtime from 0.56 to 8 MB). No single-thread TFLite table exists for the Snapdragon 8 Gen 2; the closest measurement is a 1-D CNN IMU regressor at 387 µs on a Galaxy S10 (IMUNet), so the 5 ms budget has ~10× headroom and our in-app number will be original. Post-training int8 can be slower on XNNPACK and perturbs a log-variance head multiplicatively. **Consequences**: Keras → LiteRT float32, XNNPACK on, one thread, runtime version pinned; stateless CNN first, carried GRU state only if the harness shows > 10 % gain; strided convs rather than dilated TCN (SPACE_TO_BATCH is not an XNNPACK op); no quantisation; latency quoted only from inside an APK.
- **R4 stop detection** (`docs/research/R4_stop_detection.md`, 14 fetched sources): no bicycle zero-velocity detector with thresholds and false-positive rates exists in the literature; the only bicycle latency benchmark is a start detector at 0.16 s. Transferable numbers: 88 % of bicycle road excitation power lies in 10–50 Hz; the closest vehicle detector uses 10–50 Hz peaks with a 3 s window (too slow for us); a 0.1 s confirmation window buys most of the false-positive suppression (63 → 90 % accuracy, nothing gained beyond 0.1 s); learned detectors threshold at 0.85–0.95 probability because a false stop is worse than a missed one; regressors leak to positive speed at standstill, so the hard rule must clamp the model. **Consequences for step 4**: 0.5 s statistic + 0.1–0.2 s confirmation, dual thresholds with immediate exit, 10–40 Hz band energy at 100 Hz input (10–50 Hz at 200 Hz), the phone's own stationary noise floor measured from our stands sets the absolute thresholds, and false stops per hour at 1–2 m/s is a number we must measure ourselves.
- **R3 ESKF / scale factor** (`docs/research/R3_eskf_scale.md`, 21 fetched sources): the closest published system is the i2Nav bicycle MoE paper (arXiv 2510.17604 v2), phone + learned body-frame velocity with covariance in an ESKF, whose plain NHC baseline beats the network on paved road (ATE 8.5 vs 9.9 m) — so NHC stays a parallel constraint. MEMS noise values to start from come from Wheel-INS (gyro ARW 1.2 °/√h, bias 50 °/h GM 1 h, NHC/odo sigma 0.02–0.035 m/s at 2 Hz); the bearing-to-yaw sigma is σ_v/v (derived, σ_v 0.3–0.5 m/s → 3.4° at 5 m/s, 17° at 1 m/s), gate above 2 m/s, and ArduPilot's velocity-vector yaw form avoids atan2 wrapping. Yaw bias separates from the initial yaw error on a straight run because bias ramps linearly; turns make the horizontal biases and the installation yaw observable. GNSS latency 50–300 ms plus jitter is handled with a stored-state ring buffer, not a delay state. The odometer scale factor model v_true = (1+k)·v_model with a Gauss–Markov k (σ 0.05, T 600 s, Q frozen in the outage) is standard for wheel odometers (residual 6e-4 to 2e-3 after calibration) and unpublished for a learned velocity — a legitimate novelty claim. Recovery: buffer the first fixes, require 5 consistent fixes, chi-square gate 16.27, inflate R 4× for 5 epochs, draw the track through a 0.25 s output layer. A published route-constrained filter (arXiv 2606.19687) cuts tunnel RMSE 187 → 1.7 m but leaves along-track error, so the corridor mode's honest claim is "along-track bounded by the speed scale". **Consequences**: step 5/6 use the (s, v, k) corridor state with GNSS fused as arc length only and a mandatory off-corridor fallback, the k state as above, NHC with lean-inflated sigma in the general mode, ZIHR at every stop as a free bias observation, and a measured (not borrowed) gyro noise table from our own stands.
- The open questions the research raised (window length, sample rate, covariance head, recurrence, lever arm, corridor-as-headline) are settled by the harness in the steps below, not by choice.

## Step 1 — Data QA (`engine/qa.py`)

What it computes per run, from the raw session folder (never from the app's own summary): IMU rate, p99/max dt, gaps > 50 ms, duplicate or non-monotonic timestamps; GNSS fix rate, max gap during the ride, accuracy, satellites used, mean C/N0 of used signals per epoch, and the number of epochs that would trip the real-outage detector of design rule 1 (gap > 1.5 s, accuracy > 30 m, sats < 4, C/N0 < 22 dB-Hz); mount pitch and roll from the mean accelerometer over each 15 s stand (trimmed 1 s each side; pitch = atan2(g_z, g_y), roll = atan2(g_x, √(g_y²+g_z²)), the manifest's convention) and their deviation from the set median; the gravity-direction change between the start and end stands (mount change); rider/bike motion during each stand as the net gyro rotation (with a robust bias from the quietest 1 s chunks of both stands), the fraction of quiet 1 s chunks, the accelerometer RMS, and an independent check from the phone's game-rotation vector; the gyro bias estimated separately from each stand and their mismatch; impacts (> 30 m/s²) and clipping (> 150 m/s²) during the ride; motion-start lag, moving speed, path length, mid-ride stops; start/end anchors recomputed from the fixes vs the app's anchors, and vs the A/B clusters of the whole set (A = median of AB starts and BA ends, B likewise), which also catches mislabelled directions; battery and thermal state.

Verdicts: FAIL = status not COMPLETE, rate < 100 Hz, any IMU gap or drop, anchor > 50 m from its cluster, ride < 60 % of the set median, mislabelled direction, mock location, clipping, missing stand. WARN = stand motion (net rotation > 5°, quiet chunks < 50 %, or accel RMS > 0.3 m/s²), bias mismatch between stands > 0.15 °/s, mount change > 5°, pitch outlier > 3° or roll outlier > 6° vs the set median, impact, GNSS gap/accuracy/satellite/C/N0 epochs, anchor 10–50 m off. Info flags (prefix `i:`, no effect on the verdict): slow stand rotation 2–5°, a single-sample impact under 40 m/s². Nothing is excluded; the harness reads the CSV.

Files: `data/qa/route1.csv`, `data/qa/route1_flags.md`, `data/qa/route2.csv`, `data/qa/route2_flags.md`. Rerun: `.venv/bin/python engine/qa.py data/route1/sessions --tag route1`.

### Route 1 (21 runs, 5 Sep 00:36–01:28, rider_1)

| run | dir | verdict | ride_s | v_mean_moving | v_max | path_m | pitch_start | pitch_end | roll_start | stand_rot_start_deg | stand_quiet_start | stand_rot_end_deg | biasz_start_dps | biasz_end_dps | bias_mismatch_dps | impact_events | a_max | start_off_m | end_off_m | flags_str |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AB | WARN | 115.3 | 3.04 | 3.79 | 317 | 24.83 | 29.12 | -7.22 | 0.88 | 0.83 | 6.06 | -0.18 | 0.09 | 0.27 | 3 | 93.9 | 0.9 | 1.5 | STAND_MOTION_END(rot 6.1deg); BIAS_MISMATCH(0.27dps); IMPACT(3 events, 42 samples, max 94 m/s2 at 66s) |
| 2 | BA | WARN | 98.3 | 3.33 | 3.72 | 314.4 | 24.3 | 22.82 | 2.52 | 5.68 | 0.75 | 1.37 | -0.14 | -0.23 | 0.1 | 0 | 22 | 0.6 | 0.7 | STAND_MOTION_START(rot 5.7deg) |
| 3 | AB | WARN | 104.4 | 3.28 | 4.19 | 312.6 | 23.01 | 26.22 | -2.44 | 1.87 | 0.67 | 1.3 | -0.11 | -0.01 | 0.1 | 1 | 103.3 | 0.5 | 2.6 | GNSS_GAP(1x>1.5s, max 1.6s); SATS_LOW(2 epochs <4); IMPACT(1 events, 39 samples, max 103 m/s2 at 60s) |
| 4 | BA | PASS | 89.2 | 3.7 | 4.18 | 310 | 26.12 | 25.99 | 0.39 | 3.57 | 0.67 | 1.73 | -0.09 | -0.21 | 0.12 | 0 | 26 | 3.9 | 0.3 | i:STAND_SLOW_ROT_START(3.6deg) |
| 5 | AB | PASS | 96.9 | 3.39 | 3.9 | 314.2 | 26.63 | 25.88 | -2.45 | 3.03 | 0.75 | 0.97 | -0.03 | -0.04 | 0.03 | 0 | 20.7 | 0.8 | 1.8 | i:STAND_SLOW_ROT_START(3.0deg) |
| 6 | BA | PASS | 90.2 | 3.69 | 4.12 | 317.1 | 26.83 | 26.38 | 1.62 | 1.24 | 0.75 | 0.88 | -0.01 | 0.02 | 0.03 | 0 | 25.2 | 1.9 | 0.3 |  |
| 7 | AB | PASS | 96.2 | 3.45 | 4.08 | 316.5 | 27.12 | 26.21 | 0.02 | 1.05 | 0.75 | 0.22 | -0.06 | -0.07 | 0.02 | 0 | 26.2 | 0.6 | 0.7 |  |
| 8 | BA | FAIL | 31.1 | 3.17 | 3.73 | 53.5 | 27.5 | 25.61 | 3.44 | 4.85 | 0.58 | 2.14 | -0.01 | 0.12 | 0.13 | 2 | 111.7 | 0.2 | 218.9 | i:STAND_SLOW_ROT_START(4.8deg); i:STAND_SLOW_ROT_END(2.1deg); IMPACT(2 events, 37 samples, max 112 m/s2 at 14s); ANCHOR_OFF_END(219m); SHORT_RIDE(31s, 54m vs median 85s, 314m) |
| 9 | BA | PASS | 95.3 | 3.43 | 4.54 | 314.2 | 25.91 | 24.72 | -3.55 | 0.4 | 0.5 | 1.07 | 0.16 | 0.03 | 0.13 | 0 | 29.3 | 0.9 | 0.5 |  |
| 10 | AB | PASS | 71.2 | 4.59 | 5.45 | 312.3 | 25.27 | 23.96 | 0.8 | 1.55 | 0.5 | 2.59 | -0.12 | -0.1 | 0.08 | 1 | 30.2 | 1.3 | 1.1 | i:STAND_SLOW_ROT_END(2.6deg); i:IMPACT_MINOR(1 events, 1 samples, max 30 m/s2 at 40s) |
| 11 | BA | PASS | 65.5 | 5.14 | 7.25 | 310.5 | 24.52 | 24.6 | -3.77 | 2.15 | 0.83 | 0.29 | -0 | -0.15 | 0.15 | 0 | 24.9 | 1.7 | 1.1 | i:STAND_SLOW_ROT_START(2.2deg) |
| 12 | AB | WARN | 71.8 | 4.66 | 7.35 | 317.9 | 24.96 | 23.84 | 2.5 | 6.04 | 0.17 | 2.16 | 0.15 | 0.1 | 0.13 | 0 | 26.9 | 1.2 | 1.7 | STAND_MOTION_START(rot 6.0deg, quiet 17%); i:STAND_SLOW_ROT_END(2.2deg) |
| 13 | BA | WARN | 72.3 | 4.92 | 7.14 | 316.4 | 25.22 | 24.78 | 2.08 | 7.35 | 0.5 | 0.51 | -0.07 | -0.17 | 0.09 | 0 | 26.7 | 0.2 | 1.9 | STAND_MOTION_START(rot 7.3deg) |
| 14 | AB | WARN | 72.3 | 4.64 | 5.78 | 316 | 25.12 | 24.76 | -0.13 | 5.03 | 0.67 | 1.39 | 0.01 | -0.17 | 0.18 | 0 | 25.7 | 2.3 | 1.4 | STAND_MOTION_START(rot 5.0deg); BIAS_MISMATCH(0.18dps) |
| 15 | BA | WARN | 78.6 | 4.26 | 5.3 | 313.2 | 25.48 | 25.05 | 0.29 | 1.01 | 0.42 | 1.94 | -0.34 | -0 | 0.34 | 0 | 28.9 | 1.3 | 0.1 | STAND_MOTION_START(quiet 42%); BIAS_MISMATCH(0.34dps) |
| 16 | AB | WARN | 92.7 | 3.58 | 4.45 | 316.6 | 24.94 | 24.03 | -2.57 | 2.51 | 0.33 | 2.41 | 0.14 | -0.19 | 0.33 | 0 | 26.8 | 1.1 | 1.4 | STAND_MOTION_START(quiet 33%); i:STAND_SLOW_ROT_END(2.4deg); BIAS_MISMATCH(0.33dps) |
| 17 | BA | WARN | 86.4 | 3.9 | 4.87 | 316.1 | 25.76 | 24.74 | -3.95 | 2.23 | 0.58 | 1.8 | -0.05 | 0.03 | 0.16 | 0 | 27.9 | 0 | 0.3 | i:STAND_SLOW_ROT_START(2.2deg); BIAS_MISMATCH(0.16dps) |
| 18 | AB | PASS | 79.2 | 4.23 | 5.53 | 314.3 | 25.56 | 24.28 | -3.22 | 2.31 | 0.83 | 2.82 | -0.14 | -0.06 | 0.08 | 0 | 23.7 | 2.1 | 1.2 | i:STAND_SLOW_ROT_START(2.3deg); i:STAND_SLOW_ROT_END(2.8deg) |
| 19 | BA | WARN | 69.7 | 4.77 | 6.73 | 312.1 | 25.8 | 24.68 | -1.99 | 4.79 | 0.42 | 1.15 | 0.26 | 0.11 | 0.15 | 0 | 24.4 | 0.4 | 0.6 | STAND_MOTION_START(quiet 42%) |
| 20 | AB | PASS | 80.9 | 4.19 | 5.44 | 314.6 | 25.13 | 24.37 | -3.32 | 1.91 | 0.75 | 2.7 | -0.07 | -0.05 | 0.01 | 0 | 27.6 | 0.7 | 1.8 | i:STAND_SLOW_ROT_END(2.7deg) |
| 21 | BA | WARN | 84.6 | 3.92 | 4.76 | 316.1 | 25.63 | 24.62 | -1.4 | 7.02 | 0.42 | 2.49 | 0.06 | 0.01 | 0.05 | 1 | 30.3 | 0.9 | 1 | STAND_MOTION_START(rot 7.0deg, quiet 42%); i:STAND_SLOW_ROT_END(2.5deg); i:IMPACT_MINOR(1 events, 1 samples, max 30 m/s2 at 34s) |

Set statistics over the 20 non-FAIL runs: pitch median 25.38° (sd 0.93°), roll median -1.69° (sd 2.59°), start-stand net rotation median 2.3°, start-to-end mount change median 2.3°, gyro z bias at the start median -0.053 °/s, bias mismatch between the stands median 0.110 °/s with 5 runs above 0.15 °/s. IMU 420.3 Hz on every run, zero gaps, zero duplicates. GNSS 1.00 Hz, accuracy 3.79 m on every fix (the receiver reports a constant), 48–57 signals used, C/N0 ≥ 29 dB-Hz. A = (28.522683, 77.573990), B = (28.521553, 77.571598); anchor offsets from the clusters ≤ 3.9 m on all kept runs; the app's anchors agree with the recomputed ones to < 0.05 m.

### Route 2 (2 runs, 5 Sep 03:09 / 03:17, teammates' bike and cage)

| run | dir | verdict | ride_s | v_mean_moving | v_max | path_m | pitch_start | pitch_end | roll_start | stand_rot_start_deg | stand_quiet_start | stand_rot_end_deg | biasz_start_dps | biasz_end_dps | bias_mismatch_dps | impact_events | a_max | start_off_m | end_off_m | flags_str |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | AB | WARN | 291.4 | 3.4 | 5.29 | 851.4 | 43.74 | 26.07 | -3.4 | 37.88 | 0 | 2.8 | 1.85 | -0.01 | 1.86 | 0 | 26.4 | 3.4 | 1.8 | STAND_MOTION_START(rot 37.9deg, quiet 0%, acc rms 1.94); i:STAND_SLOW_ROT_END(2.8deg); MOUNT_CHANGE(18.0deg start->end); BIAS_MISMATCH(1.86dps); PITCH_OUTLIER(+10.4deg vs median 33.3) |
| 3 | BA | WARN | 250.9 | 3.99 | 5.31 | 853.8 | 22.86 | 23.42 | 4.3 | 1.09 | 0.75 | 1.3 | 0.06 | 0.15 | 0.09 | 2 | 33.8 | 1.8 | 3.4 | IMPACT(2 events, 7 samples, max 34 m/s2 at 49s); PITCH_OUTLIER(-10.4deg vs median 33.3) |

A = (28.525930, 77.570680), B = (28.527102, 77.577006), path 851–854 m.

### Findings

1. **The data are electrically clean.** Every run: 420 Hz accel and gyro with no gaps, 1 Hz GNSS with no gap > 1.6 s, no clipping, thermal status 0, battery 52 → 37 % over the session. Nothing about the recording limits the engine.
2. **Stand motion is the dominant defect, and it is measurable.** 7 of 20 kept runs have the rider or bike moving during the start stand (net rotation 5–7° or fewer than half the 1 s chunks quiet): runs 2, 12, 13, 14, 15, 16, 19, 21. Runs 15 and 16 have a 0.33–0.34 °/s disagreement between the start-stand and end-stand bias estimates, run 1 0.27 °/s, runs 14 and 17 0.16–0.18 °/s. A 0.3 °/s bias error is 18° of heading after a 60 s outage, which is exactly the failure mode reported in `docs/09` for runs 12/15/17. The game-rotation-vector check agrees with the gyro integral on every run (e.g. run 21: 7.0° vs 7.4°), so the number is real motion, not our bias estimate. **Consequence for step 3**: the static bias cannot be trusted on a third of the runs; the bias must be a filter state refined from GNSS bearing while GNSS is healthy, and the step-3 gate (heading < 3° on all 20 runs) must be checked on runs 12/13/15/16/17/19/21 explicitly.
3. **The mount is repeatable to about 1° in pitch and 2.6° in roll on route 1.** The 3–4° pitch difference between start and end stands (median 2.3°) is the bike leaning differently at rest, not the phone moving. Route 2 run 2 is the counter-example: pitch 43.7° at the start stand and 26.1° at the end stand, an 18° change, with a 38° rotation and 1.9 m/s² accel RMS during the start stand (the rider was moving the whole time) and a 1.9 °/s bias mismatch. The phone was seated wrongly and settled into the cage during the ride. **Consequence for step 2**: alignment must be re-estimated from ride-time gravity when it changes, not taken once from the stand; route 2 run 2 is the test case.
4. **Impacts** above 30 m/s² occur in runs 1, 3 and 8 only (94, 103, 112 m/s²; 37–42 samples each, i.e. 90–100 ms events) plus single 30 m/s² samples in runs 10 and 21 and a 34 m/s² event in route 2 run 3. They are at inconsistent positions (66 s, 60 s, 14 s into the ride), consistent with the mount settling in the first rides. **Consequence for step 4**: clip the window inputs at ±40 m/s² or use robust normalisation so three events cannot dominate the loss.
5. **GNSS health glitch**: run 3 has two consecutive stationary epochs (t = 114–115 s, bike stopped at B) where `n_sats_used` is reported as 0 with an unchanged position and 3.79 m accuracy, and a 1.57 s gap. The real-outage rule "sats < 4" would fire falsely. **Consequence for step 6**: the outage detector needs a 2-epoch debounce and should treat a zero satellite count with a valid fix as "unknown", not as an outage.
6. **Route 1 content**: rides 65–115 s, 310–318 m, moving mean 3.0–5.1 m/s, max 7.4 m/s, no mid-ride stop in any run, 0–6 % of the ride below 2 m/s. Stop behaviour can only be scored at the end-of-ride stop ("outage + 20 s after the stop" in the protocol); the slow-speed regime is thin. Route 2 adds 250–290 s rides at 3.4–4.0 m/s but still no mid-ride stop.
7. **run 8** is the only FAIL: 31 s ride, ends 219 m short of A. It stays in the table with its flags; the harness excludes FAIL runs from training and never from reporting.

Harness input: the 20 non-FAIL route-1 runs, with the QA flags carried as run metadata (stand-motion runs are the heading gate's targets, not exclusions).


## Step 2 — Alignment (`engine/align.py`)

Frames: phone (Android x right, y top, z out of the screen) → bike (x forward, y left, z up), R_pb = Rz(−ψ)·R1. Runtime maths is plain numpy (Rodrigues levelling, 2×2 principal axis, trailing means). Per-run output `data/processed/<session>/align.json`; tables `data/qa/align_route{1,2}.csv`, plot `data/qa/align_route1.png`.

**Levelling R1.** Two references were evaluated: the start-stand gravity and ride-time gravity (mean of the 0.5 s low-passed accelerometer over quasi-steady riding: |ω| < 0.15 rad/s, | |a| − g | < 1 m/s², v > 1.5 m/s, |GNSS acceleration| < 0.3 m/s²). They differ by 0.3–6.2° on route 1 (median 2.2°) because the bike leans differently at rest than when ridden, and by 18° on route-2 run 2 where the phone was re-seated during the stand. The gyro-z check cannot separate the two (slopes identical to 0.01), so the engine uses ride-time gravity as soon as it exists (the stand only initialises), and the step-4 sweep keeps the stand variant as an ablation.

**Forward axis ψ.** Four estimators were run on every run; the mount was fixed across the 20 route-1 runs (pitch sd 0.9°), so cross-run spread is the selection criterion:

| Estimator | Signal | Circular mean | RMS spread | Max deviation |
|---|---|---:|---:|---:|
| First speed-up mean force | accelerometer | 88.8° | 11.0° | 27.5° |
| Velocity-integral least squares on straights | accelerometer + GNSS speed | 87.7° | 18.6° | 60.4° |
| Lean–yaw coupling, corr(roll rate, d/dt −atan(v·ω_z/g)) | gyro + GNSS speed | 90.5° | 15.9° | 36.5° |
| **Pedalling-sway axis** (principal axis of the 0.25 s − 2 s band-passed horizontal gyro; sign from the start force) | **gyro only** | **89.8°** | **2.1°** | **6.1° (run 1)** |

The brief's PCA of horizontal acceleration is wrong on a bicycle: the 0.5 m/s² forward acceleration is smaller than the gravity leak from 1–3° of pitch/roll motion and than the 1 Hz pedalling sway, so accelerometer-based axes scatter by 10–20°. The sway itself is a roll about the bike's longitudinal axis and gives the forward axis to 2° with an eigenvalue ratio of 4–13 on every run. Route 2 (different bike, cage, riders) gives 90.7° and 89.6°, the same axis as route 1, consistent with the phone's long axis lying in the bike's symmetry plane.

**Validation (20 kept route-1 runs, ride-time levelling + sway ψ):**
- Bike yaw rate = gyro z: gyro-integrated heading change per 1 s fix interval vs GNSS bearing change (v > 1.5 m/s): slope 0.929–1.088 (median 0.972), correlation ≥ 0.925, residual RMS median 2.2 °/s (max 4.4, run 18), GNSS bearing latency 0.1–0.7 s (median 0.5 s) — the latency the heading filter must compensate.
- Forward specific force positive at the start on every run (0.35–1.32 m/s²); 1 s means correlate with GNSS acceleration at median 0.83 (min 0.56, run 1) with slope 0.76–1.05 (run 1: 1.52, run 3: 1.34).
- Roll = lean in turns: correlation of the 2 s-smoothed roll rate with d/dt(−atan(v·ω_z/g)) inside turns median 0.85 (min 0.47, run 1), positive on every run, so the handedness of the frame is right.
- Residual mean specific force on straights |f_x| ≤ 0.14, |f_y| ≤ 0.04 m/s² on 19 runs; run 1 has 0.49 / 0.31 because its mount moved mid-ride.
- Moved-phone monitor (10 s blocks vs a running ride-time reference, > 3° for two consecutive blocks): fires only on run 1 at 70 s of riding, 4 s after that run's 94 m/s² impact (block angles 3.3°, 5.3°, then 0.3° after re-levelling), and on no other run (max single-block deviation 3.4°). Route-2 run 2 is caught by the stand-vs-ride difference (18°), not by the ride monitor, since the phone moved before the ride.

Route 1 table:

| run | dir | tilt_stand_vs_ride_deg | max_block_angle_deg | moved_at_s | ride_psi_sway_deg | ride_sway_ratio | ride_psi_init_deg | ride_psi_lean_deg | ride_psi_fit_deg | ride_yaw_slope | ride_yaw_corr | ride_yaw_rms_dps | ride_yaw_lag_s | ride_fwd_start_mps2 | ride_fwd_corr | ride_lean_corr | ride_mean_fx_straight | ride_mean_fy_straight |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AB | 6.23 | 5.33 | 70 | 83.65 | 9.6 | 60.8 | 126 | 59.98 | 0.94 | 0.95 | 2.23 | 0.6 | 1.32 | 0.56 | 0.47 | 0.49 | -0.31 |
| 2 | BA | 2.59 | 0.72 |  | 89.41 | 5.5 | 90 | 82 | 81.95 | 0.95 | 0.97 | 1.72 | 0.4 | 0.45 | 0.84 | 0.87 | -0.02 | 0.01 |
| 3 | AB | 3.06 | 3.42 |  | 93.61 | 7 | 96.66 | 106 | 60.82 | 0.96 | 0.98 | 1.55 | 0.5 | 0.68 | 0.73 | 0.84 | -0 | -0.05 |
| 4 | BA | 0.3 | 0.76 |  | 91.9 | 5.3 | 85 | 78 | 94.11 | 0.95 | 0.98 | 1.44 | 0.6 | 0.57 | 0.78 | 0.85 | -0 | 0.02 |
| 5 | AB | 3.12 | 0.97 |  | 85.37 | 5 | 104.34 | 107 | 85.36 | 0.95 | 0.97 | 1.9 | 0.5 | 0.52 | 0.85 | 0.81 | -0.01 | 0.01 |
| 6 | BA | 0.65 | 1.16 |  | 90.85 | 7 | 82.3 | 76 | 88.23 | 0.96 | 0.97 | 2.15 | 0.7 | 0.41 | 0.74 | 0.88 | -0.01 | -0 |
| 7 | AB | 1.3 | 0.57 |  | 89.13 | 4.4 | 100.57 | 100 | 110.52 | 0.97 | 0.96 | 2.26 | 0.7 | 0.35 | 0.75 | 0.88 | -0.02 | 0.01 |
| 8 | BA | 5.94 | 11.75 |  | -1.9 | 6.3 | 86.69 | -86 | 96.51 | 0.81 | 0.87 | 1.24 | 0.2 | 0.04 | 0.05 | 0.21 | 0.09 | -0.3 |
| 9 | BA | 3.33 | 0.55 |  | 89.81 | 8.8 | 111.09 | 79 | 72.62 | 0.94 | 0.97 | 1.88 | 0.5 | 0.43 | 0.79 | 0.83 | -0.02 | 0.01 |
| 10 | AB | 1.05 | 1.16 |  | 91.32 | 6.5 | 88.62 | 99 | 97.03 | 1.04 | 0.98 | 1.96 | 0.3 | 0.58 | 0.96 | 0.91 | -0.04 | 0.01 |
| 11 | BA | 3.44 | 1.93 |  | 89.62 | 8.3 | 83.1 | 85 | 89.2 | 1.01 | 0.98 | 2.06 | 0.1 | 0.43 | 0.95 | 0.91 | -0.07 | 0.02 |
| 12 | AB | 2.79 | 1.92 |  | 89.5 | 7.6 | 88.69 | 102 | 92.8 | 0.97 | 0.96 | 2.95 | 0.3 | 0.67 | 0.89 | 0.86 | 0.04 | 0.01 |
| 13 | BA | 2.26 | 1.63 |  | 88.88 | 11.3 | 87.31 | 76 | 92.59 | 1.04 | 0.97 | 2.72 | 0.3 | 0.8 | 0.9 | 0.84 | 0.14 | 0.02 |
| 14 | AB | 0.99 | 0.93 |  | 89.58 | 6.5 | 89.03 | 104 | 101.33 | 1.05 | 0.97 | 2.99 | 0.3 | 0.61 | 0.88 | 0.89 | 0.01 | 0.02 |
| 15 | BA | 1.45 | 0.72 |  | 90.52 | 10.3 | 82.56 | 76 | 79.59 | 0.99 | 0.97 | 2.27 | 0.3 | 0.67 | 0.9 | 0.83 | 0.03 | 0.02 |
| 16 | AB | 1.84 | 1.34 |  | 88.77 | 10.2 | 79 | 102 | 76 | 0.97 | 0.97 | 2.08 | 0.6 | 0.46 | 0.78 | 0.81 | -0.02 | -0.01 |
| 17 | BA | 3.14 | 1.59 |  | 91.72 | 7.3 | 88.97 | 67 | 87.4 | 0.93 | 0.97 | 2.27 | 0.6 | 0.45 | 0.73 | 0.85 | -0 | 0.02 |
| 18 | AB | 2.23 | 1.21 |  | 91.71 | 10 | 86.77 | 102 | 67.6 | 1.02 | 0.92 | 4.36 | 0.5 | 0.56 | 0.83 | 0.87 | -0 | 0.04 |
| 19 | BA | 0.58 | 0.84 |  | 90.24 | 12.9 | 79.04 | 72 | 91.35 | 1.01 | 0.99 | 1.34 | 0.1 | 0.75 | 0.93 | 0.79 | 0.06 | -0.03 |
| 20 | AB | 2.6 | 1.71 |  | 90.24 | 9.8 | 110.63 | 102 | 84.54 | 1.09 | 0.98 | 2.32 | 0.1 | 0.56 | 0.85 | 0.88 | 0 | 0.03 |
| 21 | BA | 0.79 | 1.35 |  | 89.42 | 11.7 | 90.05 | 71 | 148.04 | 0.95 | 0.97 | 2.5 | 0.4 | 0.61 | 0.77 | 0.79 | 0.01 | -0.01 |

Route 2:

| run | dir | tilt_stand_vs_ride_deg | max_block_angle_deg | moved_at_s | ride_psi_sway_deg | ride_sway_ratio | ride_psi_init_deg | ride_psi_lean_deg | ride_psi_fit_deg | ride_yaw_slope | ride_yaw_corr | ride_yaw_rms_dps | ride_yaw_lag_s | ride_fwd_start_mps2 | ride_fwd_corr | ride_lean_corr | ride_mean_fx_straight | ride_mean_fy_straight |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | AB | 18.02 | 1.75 |  | 90.68 | 9.4 | 88.16 | 114 | 106.83 | 0.91 | 0.92 | 1.84 | 0.1 | 0.34 | 0.74 | 0.54 | -0 | 0 |
| 3 | BA | 0.83 | 1.08 |  | 89.56 | 9.7 | 71.19 | 80 | 113.53 | 0.95 | 0.97 | 1.16 | 0.2 | 0.61 | 0.84 | 0.52 | 0.05 | 0.01 |

Consequences: the runtime uses the stand levelling for the first ~10 s of riding (2–6° off, inside the ±5° rotation augmentation of step 4) and ride-time gravity afterwards; ψ from the sway axis needs ~20 s of pedalling and is replaced by the accelerometer start estimate until then. Run 1 is kept but its `moved_at` flag travels with it into the speed-model split.


## Step 3 — Heading and gyro bias (`engine/heading.py`, protocol in `engine/evaluate.py`)

Protocol (`evaluate.py`): kept runs from the QA table; cuts at motion start + 10 s, + 30 s, + 60 s (when ≥ 10 s of moving outage remain), and inside the sharpest turn that begins ≥ 10 s after motion start (cut at 25 % of the turn's span); outage = cut → end of the ride; heading error at fixes with v > 1.5 m/s with the 0.5 s GNSS latency measured in step 2. Metrics: mean signed error over the outage (what drives position drift), RMS, max, and drift (last 5 s minus first 5 s). Distributions over the 20 runs: median, worst, count under 3°.

**Reference change, measured first.** The receiver's reported bearing is not a clean reference: on run 18 it differs from the course computed from consecutive positions by up to 26° inside the S-bend and stays offset by +3 to +6° for 25 s afterwards; on run 11 by −2 to −6° at 7 m/s. The gyro heading tracks the position course, not the reported bearing. Since position is what dead reckoning must match, the course from consecutive fix positions (centred 0.5 s before the fix, so the same latency model) is the primary reference and the primary measurement; the reported-bearing numbers are kept as a secondary column (`brg_*`).

Engine: quaternion attitude (bike → ENU) propagated at 100 Hz with the stand bias removed, Mahony-style tilt correction (τ = 10 s) gated to quasi-steady riding; a 2-state Kalman filter [ψ, b_z] with the course as measurement at fixes with v > 1.5 m/s on straight segments only (|ω_z| < 0.1 rad/s and none for 1.5 s after a turn, because the receiver's course lags in turns); measurement model h = ψ − I_τ + τ·b_z with I_τ the raw gyro-z integral over the last τ = 0.5 s (stored-state latency compensation), H = [1, τ], σ² = (0.3 m/s ÷ v)² + (0.2 s · ω_z)² + (2°)²; bias updates only at v > 2 m/s and clamped to ± 0.3 °/s around the robust stand value (prior σ 0.2 °/s, 0.3 °/s if the QA flagged stand motion); Joseph-form update; the alignment fix resets the ψ variance and the cross term (a missing cross-term reset made P indefinite and was the cause of the first divergent runs). After the cut: propagation only. Everything is plain numpy/math; constants are listed above.

Variants: `robust` = robust stand bias, heading aligned on the first fix, no refinement (the `loro_cv.py` equivalent); `kfpsi` = ψ refined from the reported bearing; `kfpsic` = ψ refined from the position course; `kfc` = ψ and b_z refined from the course (engine choice); `kfpsic2d` = the same with plain yaw integration instead of the 3-D attitude; `kfpsic_notilt` = 3-D without the accelerometer tilt correction.

| cut | variant | n | mean_med | mean_worst | n_under3 | rms_med | drift_med | drift_worst | drift_under3 | max_med | worst_run | brg_mean_med | brg_mean_worst | brg_under3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c10 | robust | 20 | 2.21 | 5.53 | 14 | 3.88 | 1.62 | 7.92 | 17 | 12.35 | 17 | 2.26 | 5.65 | 15 |
| c10 | kfpsi | 20 | 0.57 | 3.98 | 17 | 3.33 | 1.62 | 7.92 | 17 | 11.2 | 17 | 1.04 | 3.97 | 18 |
| c10 | kfpsic | 20 | 1.38 | 4.43 | 17 | 3.19 | 1.62 | 7.92 | 17 | 11.29 | 1 | 1.11 | 5.16 | 14 |
| c10 | kfc | 20 | 1.67 | 4.29 | 17 | 3.28 | 2.31 | 7.37 | 13 | 12.86 | 14 | 2 | 5.16 | 14 |
| c10 | kfpsic2d | 20 | 1.41 | 5.13 | 14 | 3.5 | 1.43 | 6.54 | 18 | 12.71 | 17 | 1.25 | 6.21 | 16 |
| c10 | kfpsic_notilt | 20 | 1.37 | 4.73 | 17 | 3.17 | 1.76 | 7.71 | 17 | 11.27 | 1 | 1.14 | 5.05 | 14 |
| c30 | robust | 20 | 2.33 | 5.87 | 13 | 3.61 | 1.56 | 6.48 | 12 | 10.42 | 17 | 2.5 | 6.73 | 13 |
| c30 | kfpsi | 20 | 0.92 | 4.21 | 17 | 3.16 | 1.56 | 6.48 | 12 | 10.02 | 1 | 1.29 | 5.61 | 16 |
| c30 | kfpsic | 20 | 1.33 | 3.33 | 19 | 2.98 | 1.56 | 6.48 | 12 | 10.28 | 17 | 1.45 | 5.88 | 16 |
| c30 | kfc | 20 | 1.18 | 3.03 | 19 | 2.93 | 1.85 | 7.04 | 14 | 10.19 | 6 | 1.4 | 5.28 | 15 |
| c30 | kfpsic2d | 20 | 1.4 | 4.53 | 15 | 3.7 | 1.49 | 6.5 | 14 | 10.52 | 20 | 1.52 | 8.03 | 15 |
| c30 | kfpsic_notilt | 20 | 1.43 | 3.29 | 19 | 2.91 | 1.54 | 6.3 | 13 | 10.32 | 17 | 1.38 | 6.01 | 16 |
| c60 | robust | 14 | 2.34 | 6.09 | 11 | 3.22 | 2.16 | 7.2 | 10 | 7.04 | 17 | 2.46 | 6.93 | 8 |
| c60 | kfpsi | 14 | 1.07 | 6.04 | 11 | 3.04 | 2.16 | 7.2 | 10 | 6.63 | 1 | 1.17 | 5.87 | 11 |
| c60 | kfpsic | 14 | 1.11 | 4.82 | 11 | 2.73 | 2.16 | 7.2 | 10 | 6.46 | 1 | 0.8 | 4.65 | 10 |
| c60 | kfc | 14 | 1.41 | 3.84 | 12 | 2.46 | 2.3 | 7.44 | 10 | 6.27 | 1 | 0.97 | 4.24 | 11 |
| c60 | kfpsic2d | 14 | 0.74 | 5.76 | 11 | 2.33 | 2.23 | 7.35 | 9 | 6.2 | 17 | 0.73 | 6.61 | 9 |
| c60 | kfpsic_notilt | 14 | 1.08 | 3.79 | 11 | 2.73 | 2.15 | 7.6 | 10 | 6.46 | 1 | 0.78 | 4.41 | 10 |
| turn | robust | 20 | 2.31 | 5.76 | 13 | 4.43 | 1.39 | 6.42 | 16 | 12.35 | 17 | 2.75 | 7.04 | 13 |
| turn | kfpsi | 20 | 0.73 | 4.22 | 17 | 3.96 | 1.39 | 6.42 | 16 | 11.59 | 1 | 1 | 5.35 | 16 |
| turn | kfpsic | 20 | 1.14 | 3.22 | 19 | 3.9 | 1.39 | 6.42 | 16 | 11.48 | 17 | 1.01 | 4.46 | 17 |
| turn | kfc | 20 | 1.21 | 3.34 | 19 | 3.55 | 1.39 | 2.85 | 20 | 12.2 | 15 | 0.93 | 3.93 | 18 |
| turn | kfpsic2d | 20 | 0.89 | 5.35 | 16 | 4.05 | 1.96 | 6.64 | 16 | 12.54 | 17 | 1.25 | 6.63 | 16 |
| turn | kfpsic_notilt | 20 | 1.19 | 3.2 | 19 | 3.77 | 1.39 | 6.05 | 16 | 11.52 | 17 | 0.9 | 4.58 | 17 |

Per run, engine variant `kfc`, cut at motion start + 30 s (bias columns in °/s: robust stand estimate, filter estimate at the cut, batch whole-ride estimate):

| run | dir | outage_s | mean_deg | start_err_deg | end_err_deg | drift_deg | rms_deg | max_abs_deg | bias_stand_dps | bias_cut_dps | bias_oracle_dps | brg_mean_deg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AB | 81.99 | -0.92 | 0.27 | 0.4 | 0.13 | 3.24 | 12.85 | -0.03 | 0.04 | 0.04 | -1.53 |
| 2 | BA | 65.21 | -0.29 | 0.86 | -1.5 | -2.37 | 2.45 | 10.95 | -0.01 | -0.02 | -0.03 | -0.05 |
| 3 | AB | 71.73 | -0.02 | -1.15 | 2.73 | 3.87 | 2.82 | 10.9 | -0.03 | -0.03 | -0.05 | 0.28 |
| 4 | BA | 56.58 | -1.36 | -1.57 | -2.22 | -0.65 | 3.02 | 10.98 | -0.03 | -0.02 | -0.04 | -1.26 |
| 5 | AB | 64.07 | -1.18 | -3.74 | -0.15 | 3.58 | 2.6 | 7.09 | -0.02 | 0 | -0.03 | -0.72 |
| 6 | BA | 57.59 | -3.03 | -2.2 | -5.35 | -3.14 | 5.04 | 20.83 | -0.01 | 0.04 | -0.01 | -3.2 |
| 7 | AB | 61.98 | -0.8 | -6.13 | 0.92 | 7.04 | 3.11 | 13.68 | -0.01 | -0.03 | -0.05 | -0.21 |
| 9 | BA | 62.78 | -0.08 | -0.25 | 0.33 | 0.58 | 2.69 | 9.47 | -0.01 | -0.02 | -0.01 | -0.03 |
| 10 | AB | 39.46 | 0.53 | -1.6 | 2.56 | 4.16 | 2.69 | 6.48 | -0.02 | -0.02 | -0.04 | -1.93 |
| 11 | BA | 31.6 | 0.34 | -2 | 0.93 | 2.94 | 2.13 | 5.45 | -0.01 | -0.08 | -0.04 | -0.64 |
| 12 | AB | 39.61 | -2.34 | -1.28 | -1.66 | -0.38 | 3.51 | 9.21 | 0.02 | 0.03 | -0.03 | -0.71 |
| 13 | BA | 39.65 | -1.44 | -1.25 | -2.13 | -0.89 | 3.61 | 11.7 | -0.02 | 0.03 | 0.02 | -3.07 |
| 14 | AB | 39.52 | -1 | -1.62 | -1.5 | 0.12 | 1.88 | 5.85 | -0.06 | 0.04 | -0.04 | -2.76 |
| 15 | BA | 46.35 | -2.72 | -0.15 | -5.39 | -5.24 | 4.44 | 15.91 | 0 | 0.04 | -0.03 | -0.09 |
| 16 | AB | 59.42 | 2.18 | 2.84 | 3.22 | 0.39 | 3.38 | 9.13 | -0.04 | -0.03 | -0.03 | 2.18 |
| 17 | BA | 51.88 | 1.92 | 3.02 | 0.88 | -2.13 | 4.51 | 15.82 | -0.04 | -0 | 0.02 | 1.86 |
| 18 | AB | 45.54 | -0.6 | -1.92 | 0.04 | 1.96 | 2.6 | 5.89 | -0 | -0.02 | -0.04 | -5.28 |
| 19 | BA | 37.32 | 2.25 | 1.87 | 1.6 | -0.27 | 2.84 | 5.3 | 0.01 | 0.01 | 0.04 | 3.3 |
| 20 | AB | 47.49 | -1.98 | -2.87 | -1.13 | 1.74 | 2.79 | 7.16 | -0.01 | -0.01 | -0.03 | -4.54 |
| 21 | BA | 52.21 | 1.18 | 1 | -0.24 | -1.24 | 3.75 | 12.6 | -0.01 | -0.06 | -0 | 1.17 |

Findings:
1. **Gate status**: at the 30 s cut the engine variant has 19 of 20 runs under 3° (worst 3.03°, run 6); at the in-turn cut 19/20 (worst 3.34°); at 10 s 17/20 (worst 4.29°); at 60 s 12/14 (worst 3.84°, run 1, the run whose mount moved after an impact). The gate "< 3° on every run" is met on 19 of 20 runs at the demo-relevant cuts; the residual 3–4° cases are initial-heading errors right after the S-bend, not bias drift (drift under 3° on 20/20 runs at the in-turn cut).
2. **Refining ψ from GNSS is the big gain** (median 2.3° → 1.2–1.3°, worst 5.9° → 3.0–3.3°): aligning once on a single fix leaves a 2–6° offset for the whole outage. The bias state adds a small further gain in the worst case (3.33° → 3.03° at 30 s, 4.82° → 3.84° at 60 s) once it is clamped and fed only by straight, fast fixes; unclamped and fed by the reported bearing it diverged on 6 runs (bias pushed to 0.3–1.3 °/s).
3. **The 3-D attitude matters**: plain yaw integration (`kfpsic2d`) has worst cases of 4.5–5.8° at 30 s and 60 s versus 3.0–3.8° with the quaternion attitude; the lean in the S-bend at 5–7 m/s reaches 10–16° and the bike-z rate is no longer the heading rate. The accelerometer tilt correction is not decisive over these durations (`kfpsic_notilt` within 0.1° of `kfpsic`).
4. **Runs 12/15/17** (the stand-motion runs called out in the brief): 0.8°, 0.4°, 0.5° mean error at the 30 s cut with the engine variant.
5. The fast rides (10, 11, 18, 20) show a whole-ride batch bias 0.1–0.14 °/s away from the stand value with the reported bearing as reference, but only 0.03–0.05 °/s with the position course: the "speed-dependent bias" was the bearing's offset, not the gyro.

Files: `data/qa/heading_route1.csv` (run × cut × variant), `data/qa/heading_route1_summary.csv`, `data/qa/heading_route1.png`. Rerun: `.venv/bin/python engine/heading.py --tag route1 --plot`.


## Step 4 — Speed model: datasets and the bar to beat (`engine/speed_model/`)

Datasets (`dataset.py`): bike-frame 6-channel IMU (R_pb from step 2, gravity and gyro bias left in) at 50, 100 and 200 Hz (Butterworth 0.4·rate on the 420 Hz native table), GNSS Doppler speed as label, invalid where accuracy > 10 m or speed accuracy > 1 m/s, zero by protocol inside the stands. Label lag: the Doppler speed lags the IMU; per-run cross-correlation of the 1 s vibration RMS against GNSS speed gives 0–1.5 s with median 0.7 s (a noisy estimator), and the single median 0.7 s is applied to every run. Windows are cut at training time, always causal, never straddling a stand/ride boundary, stride 0.1 s; stand windows kept at 30 %.

Sweep harness (`train.py`): grouped 5-fold by round-trip pair for the wide sweep, leave-one-run-out for finalists; per-channel normalisation from the training runs only; early stopping on two inner-validation runs taken from the training folds (test runs never touch any choice); Gaussian head (μ, log σ²) trained by NLL with an MSE warm-up; augmentation (train only): ±5° rotation about a random axis applied to accelerometer and gyro alike, ±5 % gain, white noise, ±5 % time-warp. Physical stop rule as a hard override after smoothing (vibration RMS < 0.6 m/s² and gyro RMS < 0.06 rad/s over the last 0.5 s). Every held-out run is scored on speed MAE (moving), bias, NLL, 1-σ coverage, false stops, stop latency at the end-of-ride stop, and the replay drift at every cut with the step-3 heading.

**GBR baseline (hand features, 100 Hz, 2.56 s window), 20 held-out runs, grouped 5-fold:**

| Metric | median | worst | count |
|---|---:|---:|---:|
| speed MAE moving (m/s) | 0.25 | 0.52 (run 13) | |
| speed bias (m/s) | −0.02 | −0.26 (run 10) | |
| 1-σ coverage | 0.81 | | |
| drift at 10 s cut | 3.3 % | 9.1 % | 20/20 under 10 % |
| drift at 30 s cut | 4.3 % | 10.6 % | 19/20 |
| drift at in-turn cut | 4.7 % | 14.0 % | 19/20 |
| error 20 s after the stop, 30 s cut | 7.6 m | 21 m | |
| stop latency (s) | 0.2 | | false stops 0 |

The hard override fixed a 4.3 s stop latency that the 1 s smoother had introduced when the rule was applied before it. The stop-latency number is measured only at the end-of-ride stop (route 1 has no mid-ride stops).

CNN sweep (12 configurations: 1-D CNN at 100 Hz with 1.28/2.56/5.12 s windows, 200 Hz and 50 Hz at 2.56 s, no augmentation, ResNet-1D, dilated TCN, CNN + hand features, CNN + GRU, stop head, half width) is running in three lanes; results are appended to `data/speed_model/summary.csv` and will be reported here when complete.

## Steps 5 + 6 — Fusion filter (`engine/filter.py`, corridor `engine/corridor.py`), evaluated with the GBR speeds

Corridor polyline: `data/map/corridor_route1.geojson`, the shortest path between the A and B anchor clusters over the graph formed by OSM ways 547215901 + 547215900 (they share one node; a naive end-to-end chaining gives a 735 m loop), 320 m plus 15 m overhangs; every kept run's fixes project onto it monotonically with a 3–4 m median lateral offset (the rider's line versus the mapped centreline), which the filter carries as a held offset instead of snapping to the line.

Filter: general mode [px, py, v, k] and corridor mode [s, v, k]; model speed as a measurement with σ = max(σ_model, 0.15 m/s); ZUPT from the physical stop flag (σ 0.05 m/s); GNSS position with σ = max(reported accuracy, 3 m) and 0.5 s latency through stored states, GNSS speed σ 0.3 m/s with 0.7 s latency; k Gauss–Markov (σ 0.05, T 600 s), observed only at steady speed above 2 m/s, frozen in the outage; on GNSS return σ inflated ×4 for 3 s, and in corridor mode the lateral offset glides to the new fix instead of jumping. Turn-landmark resets (heading change > 40° in 3 s → nearest bend of matching sign within 40 m) are implemented and measured: no effect on any run (`cor_lm` = `cor`).

Results, 20 held-out runs, drift % of outage distance (median / worst / runs under 10 %), plus error 20 s after the stop (median):

| Cut | plain integration (step-4 replay) | general, k fixed | general, k estimated | corridor, k fixed | corridor, k estimated |
|---|---|---|---|---|---|
| 10 s | 3.31 / 9.11 / 20; 9.1 m | 2.98 / 9.01 / 20; 8.2 m | 3.95 / 8.46 / 20; 11.2 m | 2.06 / 6.47 / 20; 5.8 m | **1.04 / 2.73 / 20; 3.2 m** |
| 30 s | 4.26 / 10.60 / 19; 7.6 m | **3.54 / 9.06 / 20; 6.9 m** | 6.22 / 16.69 / 17; 12.8 m | 4.20 / 8.59 / 20; 7.4 m | 4.31 / 10.78 / 19; 7.4 m |
| 60 s (14 runs) | 7.92 / 20.47 / 10; 6.5 m | 6.54 / 20.72 / 9; 5.9 m | 5.00 / 19.21 / 10; 5.2 m | **4.40 / 14.87 / 12; 3.8 m** | 4.54 / 13.32 / 11; 4.2 m |
| in-turn | 4.75 / 14.00 / 19; 6.8 m | 3.68 / 10.90 / 18; 5.7 m | 5.92 / 21.02 / 18; 9.2 m | **3.67 / 7.75 / 20; 6.6 m** | 3.10 / 13.08 / 19; 5.4 m |

Recovery scenario (GNSS withheld from +30 s, returned at +60 s): error at return 4.8 m (general) / 7.6 m (corridor); 3 s later 5.0 / 6.1 m; largest single 0.1 s step of the displayed marker 0.4 m (general) / 1.5 m (corridor). No track is rewritten.

Findings:
1. **The filter beats the plain integration at every cut** even with the same speeds and heading, through sigma-weighted speed fusion and the ZUPT (general, k fixed: 4.3 → 3.5 % at 30 s; corridor: 7.9 → 4.4 % at 60 s, 4.75 → 3.67 % in-turn with 20/20 under 10 %).
2. **Corridor mode is the demo mode**: at the 10 s cut the drift median drops to 1.0 % and the error 20 s after the stop to 3.2 m, because cross-track error is structurally zero and only the along-track speed scale remains; at longer cuts it is on par with or better than the general mode and never worse in the worst case.
3. **The online scale state k does not help on route 1 at 30 s**: the model's residual in the first 30 s of a ride (the acceleration phase) is a −2 % transient that k reads as a scale error (k_end 1.02) and then applies to the whole outage; by 60 s k has converged to 1.00 and the state is neutral. A delayed-state form of the model measurement was tried and rejected (measured 2× worse: the model is the only driver of v in the outage, so the delay makes a feedback loop). k stays in the engine, default off for route 1, and is judged on the route-2 rider-held-out and cross-road tests where the brief expects its gain.
4. Turn-landmark resets add nothing on route 1 and stay off.

Files: `data/qa/filter_gbr_r100_w256.csv`, `_summary.csv`, tracks in `data/qa/tracks/gbr_r100_w256/`. Rerun: `.venv/bin/python engine/filter.py --pred gbr_r100_w256`.


## Step 7 — Map matching for the general mode (`engine/mapmatch.py`)

Newson–Krumm HMM over the campus OSM graph (276 ways, 1785 segments, 449 junction nodes): candidates within 25 m of the filter position, emission N(perpendicular distance; 5 m) with a 60° heading gate (undirected edges, penalty ×0.05), transition exp(−|route distance − travelled distance| / 5 m) with a bounded Dijkstra over the node graph, evaluated every 0.5 s, output = the state 3 s back on the current best path (causal, ≤ 3 s lag), confidence = log-probability margin over the runner-up (confident above ln 20). Feedback under test: the matched edge's bearing (oriented by travel) as a heading measurement (σ 10°) when confident and on a straight edge ≥ 20 m, and cross-track = 0 to the matched edge (σ 3 m) as a delayed position pseudo-measurement during outages.

Measured through the replay harness on the 20 kept runs with the GBR speeds, general mode (drift median / worst / runs under 10 %):

| Cut | no matching | matching, no feedback | matching + feedback, full graph | matching + feedback, rideable ways only |
|---|---|---|---|---|
| 10 s | 3.46 / 8.70 / 20 | 3.46 / 8.70 / 20 | 3.46 / 7.85 / 20 | 3.46 / 7.85 / 20 |
| 30 s | **2.99 / 8.35 / 20** | 2.99 / 8.35 / 20 | 4.31 / 15.67 / 19 | 4.31 / 12.95 / 19 |
| 60 s (14) | 5.60 / 19.97 / 9 | 5.60 / 19.97 / 9 | 5.79 / 23.17 / 10 | 5.79 / 23.17 / 10 |
| in-turn | 3.33 / 11.41 / 18 | 3.33 / 11.41 / 18 | 4.37 / 13.14 / 18 | 4.37 / 11.64 / 18 |

Verdict: the matcher runs causally within the 3 s lag and matches every tick (33 distinct segments along run 1), but it is confident on only 13 % of ticks because footways run parallel to the road within the candidate radius, and the confident matches that do fire are sometimes the wrong parallel edge: the feedback degrades the general mode at every cut beyond 10 s. Restricting the graph to rideable ways does not repair it. Per design rule 5 the feedback is off; the matched road is a display output only, and the corridor mode (unaffected) remains the demo mode. Files: `data/qa/replay/all_gbr_r100_w256_general_mm{0,1,2}_fb{0,1}_k0.csv`.

## Step 8 — Replay harness (`engine/replay.py`)

`--session <dir> --pred <model> --outage t0,t1 | --polygon file.geojson [--mode corridor|general] [--mm 0|1|2] [--plot]` runs the whole engine loop (100 Hz heading filter, 10 Hz fusion tick, 2 Hz matcher) with GNSS withheld inside the time window (seconds after motion start) or the polygon, plus the rule-1 real-outage detector (gap > 1.5 s, accuracy > 30 m, satellites < 4 debounced over two epochs), and writes a 10 Hz CSV (t, x, y, lat, lon, v, heading, mode GNSS_INS/INERTIAL/RECOVERING, k, σ_pos, matched segment, confidence), the metrics and a plot. `--all` evaluates every kept run at every cut. Through this harness the corridor mode gives 30 s-cut drift median 4.22 %, worst 9.31 %, 20/20 under 10 % (step-6 filter: 4.20 / 8.59 / 20; the 0.1–0.7 % differences come from fixes being consumed at the next 10 Hz tick). This harness is the app's conformance test: the Kotlin engine must reproduce its CSV on a recorded session (tolerance in the spec).


## Step 10 — IO-VNBD: the engine on an external IMU (`engine/iovnbd.py`)

Data: `data/external/IO-VNBD` (git-lfs, pointers only; pulled V-files Vfa01, Vfa02, vta2, vta3, vta4, vta6, Vw12, Vw13). The phone file of the same drive was measured and rejected as the inertial source: its GPS updates only every 9 s (122 changes in 1148 s) and its 10 Hz gyro z correlates at −0.14 with the vehicle yaw rate (the gravity vector says the phone lies flat, so the yaw should be on z; at 10 Hz the phone IMU is aliased vibration). The V-file's CAN signals are clean: yaw rate vs GNSS course rate slope 1.000 (corr 0.996), longitudinal acceleration vs dv/dt corr 0.94 on Vfa01. The external IMU is therefore the car's own 10 Hz inertial unit, which is the stronger demonstration for the "edge engine on an external IMU" claim, and the VBOX GNSS subsampled to 1 Hz is the engine's GNSS input (masked 120 s every 300 s); truth is the 10 Hz VBOX track.

Pipeline (the same modules): alignment = sign/scale calibration of the yaw rate and longitudinal acceleration against GNSS while healthy, from the training drives only; heading = the step-3 filter (2-D, CAN yaw rate, course measurement with latency); speed = GBR on 5.12 s windows of (a_long, a_lat, yaw rate) with the window's integrated acceleration and the a_lat/yaw-rate cue, trained on the other drives (2.4 h for Vfa02, 1.4 h for Vfa01); CAN stop rule (3 s with |yaw| < 0.003 rad/s and |a| < 0.05 m/s²), 0 false stops; filter = general mode, with and without the scale state; baselines = plain integration and the classical INS speed (integral of a_long with a bias estimated while GNSS is healthy).

| Test drive | speed model MAE (bias) | variant | masks | drift median | worst | under 10 % | endpoint median | heading error median |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Vfa02, motorway, 24.5 m/s, 3.2 km per mask | 5.99 m/s (−5.6) | plain | 22 | 24.7 % | 34.4 % | 1 | 793 m | 5.5° |
| | | INS speed | 22 | 27.5 % | 86.3 % | 1 | 715 m | |
| | | general, k fixed | 22 | 24.3 % | 34.4 % | 1 | 784 m | |
| | | **general, k estimated** | 22 | **14.5 %** | 30.6 % | **9** | **408 m** (k → 1.31) | |
| Vfa01, mixed, 17.5 m/s, 2.3 km per mask | 3.18 m/s (−0.5) | plain | 5 | 13.4 % | 16.7 % | 2 | 272 m | 5.5° |
| | | INS speed | 5 | 17.2 % | 221.6 % | 1 | 497 m | |
| | | general, k fixed | 5 | 13.2 % | 17.2 % | 2 | 277 m | |
| | | general, k estimated | 5 | 15.2 % | 23.1 % | 1 | 306 m (k → 1.06) | |

Findings: the engine runs unchanged on an external 10 Hz IMU end to end; drift is dominated by the car speed model (a 10 Hz CAN IMU carries no vibration cue, so the model is 3–6 m/s off), and the heading from the CAN yaw rate holds 5.5° over 120 s. The online scale state does what the brief predicted for transfer: where the model has a large bias (−23 % on the motorway) k converges to 1.31 within the healthy periods and cuts the drift by 40 %; where the model bias is small it is neutral to slightly negative. Two robustness fixes came out of this track and were fed back into the bicycle engine (re-verified below): both the heading filter and the position filter now reset after five consecutive gate rejections, because a transient heading error beyond the 5σ gate had made the filters reject GNSS permanently; the heading process noise is (0.1°)²/s so the gate can reopen. Plots: `data/qa/iovnbd_Vfa02.png`, `data/qa/iovnbd_Vfa01.png`; tables `data/qa/iovnbd_Vfa0{1,2}.csv`.


## Stop rule — measured margins (R4 asked for the phone's own noise floor)

Half-second windows of the 100 Hz bike-frame data, 20 route-1 runs: vibration RMS = √mean|a − mean a|², gyro RMS = √mean|ω|²; the rule fires when vibration < 0.6 m/s² AND gyro < 0.06 rad/s.

| Regime | windows | vibration RMS p5 / median / p95 (m/s²) | gyro RMS p5 / median / p95 (rad/s) | rule fires |
|---|---:|---|---|---:|
| stands (speed 0 by protocol) | 5508 | 0.05 / 0.16 / 0.77 | 0.005 / 0.019 / 0.092 | 87.5 % |
| riding 0.5–1 m/s | 228 | 0.45 / 1.27 / 3.52 | 0.051 / 0.146 / 0.372 | 5.7 % |
| riding 1–2 m/s | 445 | 0.80 / 1.38 / 2.82 | 0.073 / 0.155 / 0.369 | 0.0 % |
| riding 2–3 m/s | 1332 | 0.88 / 1.27 / 2.36 | 0.090 / 0.168 / 0.453 | 0.0 % |
| riding > 3 m/s | 14184 | 1.24 / 1.91 / 3.80 | 0.108 / 0.197 / 0.485 | 0.0 % |

The stationary noise floor sits at 0.05–0.16 m/s² (the phone in the cage, rider still), an order of magnitude below the threshold; rolling at 1–2 m/s is separated from it on both signals (no false stop in 44 s of slow riding, 0 in every sweep configuration); the 12 % of stand windows where the rule does not fire are rider movement, which is why the stop latency is scored at the moment the bike stops (0.2 s median with the hard override). Below 1 m/s the rule fires on 6 % of windows: at walking pace the rider's feet are typically down, and the filter's ZUPT σ of 0.05 m/s makes a 0.5 s false stop cost < 0.5 m. Route 1 has no mid-ride stops, so stop latency is measured only at the end-of-ride stop.

## Step 11 (preliminary) — route 2 transfer with the two pilot runs

Route 2 still has only the two pilot runs (AB run 2 with the 18° re-seated phone, BA run 3), so the LORO on route 2, the rider-held-out test and the joint model wait for the data. What can be measured now is train-on-route-1 → test-on-route-2 (different bike, cage and riders, 850 m rides), for the GBR and the CNN deployment model. Dataset: `data/speed_model/route2_100hz.npz` (label lag 1.1 s on route 2 vs 0.7 s on route 1 — the median of two runs, applied to both). Runs whose stand was flagged get a wider bias clamp (±1.5 °/s instead of ±0.3 °/s) because route-2 run 2's stand bias is 1.9 °/s off.

GBR trained on all 20 route-1 runs, tested on route 2: speed MAE 0.29 / 0.40 m/s, bias −0.06 / −0.25 m/s (the model under-reads the other bike by up to 6 %). Filter, 30 s cut (outage ≈ 800 m, 220 s): plain 10.8 / 11.9 %; general k fixed 10.5 / 10.6 %; general k estimated 13.4 / 20.5 % (k → 1.12, over-correction); corridor k fixed 6.4 / 9.2 %; **corridor k estimated 2.4 / 3.2 %** (k → 1.13). 60 s cut: corridor 6.4 % with k vs 7.0 % without; general 9.9 % with vs 5.2 % without. In-turn cut: corridor 7.1 % with vs 6.2 % without. Two runs are not a distribution; the sign of the k gain in corridor mode at the demo cut is the encouraging part and the general-mode over-correction the warning. CNN transfer numbers are appended when the deployment model finishes.


### Route-2 transfer with the CNN deployment model (trained on all 20 route-1 runs)

Speed on the two route-2 runs: MAE 0.179 / 0.173 m/s, bias +0.06 / −0.11 m/s, 0 / 3 false stops (the GBR: 0.29 / 0.40 m/s, bias −0.06 / −0.25). The CNN carries across bike, cage and rider far better than the hand-feature model. Filter (drift median / worst over the two runs):

| Cut | plain | general k fixed | general k est. | corridor k fixed | corridor k est. |
|---|---|---|---|---|---|
| 10 s | 4.50 / 5.13 | 4.79 / 5.59 | 6.81 / 10.30 | 2.65 / 5.05 | **1.94 / 2.90** |
| 30 s (≈ 800 m) | 12.40 / 14.53 | 12.25 / 13.82 | 13.09 / 17.21 | 2.78 / 5.15 | **2.64 / 3.19** |
| 60 s | 4.81 / 5.17 | 4.85 / 5.23 | 5.18 / 6.41 | 3.06 / 5.41 | 3.24 / 3.75 |
| in-turn | 5.90 / 6.55 | 5.94 / 7.49 | 6.00 / 6.32 | 3.68 / 5.37 | **3.26 / 3.78** |

On the long route-2 outages the general mode is limited by heading (12 % at the 30 s cut for every general variant, k or not), the corridor mode holds 2–4 %, and the scale state lowers the worst case in corridor mode at three of four cuts (k → 1.03–1.08) while hurting the general mode. Two runs only; the route-2 verdict waits for the collection.

## Step 4 close-out — deployment model and export

Deployment model `cnn_r100_w256_deploy` (100 Hz, 2.56 s window, width 32, 57 602 parameters, trained on all 20 kept route-1 runs with runs 14 and 18 as the early-stopping validation, 17 epochs). Export (`engine/export/export.py`, verified on 2000 real windows): ONNX 230 450 bytes, max |Δ| vs PyTorch 1.4e-6; TFLite float32 239 688 bytes via an exact Keras twin, max |Δ| 1.9e-6 (target 1e-4); TFLite ops CONV_2D ×4, FULLY_CONNECTED ×2, MEAN, PAD ×4, RESHAPE/EXPAND_DIMS (all XNNPACK fp32 kernels); single-thread latency on this Mac 0.08 ms (ONNX Runtime) / 0.07 ms (LiteRT) per window — the phone figure must be measured in the APK, but the 5 ms budget has two orders of magnitude of margin. Model section of the spec: `docs/12_ENGINE_SPEC_for_kotlin.md` §8. Conformance reference: `data/qa/replay/20260905_003612_SNU_AJB_AB_run1_corridor_mm0.csv` (run 1, corridor mode, outage from +30 s, deployment model; 2.95 % drift, 6.8 m after the stop; note this run is in the deployment model's training set, so the number is a conformance reference, not an accuracy claim).


## Step 6 re-scored with the CNN held-out speeds (grouped 5-fold predictions of `cnn_r100_w256`)

Drift % (median / worst / runs under 10 %), 20 route-1 runs; `k` = online scale state:

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 2.33 / 8.01 / 20 | 3.02 / 7.92 / 20 | 3.52 / 8.32 / 20 | 2.62 / 7.41 / 20 | **1.09 / 6.40 / 20** |
| 30 s | 3.05 / 6.61 / 20 | **2.52 / 6.80 / 20** | 4.86 / 11.61 / 19 | 4.47 / 10.55 / 19 | 4.36 / 10.78 / 19 |
| 60 s (14) | 7.74 / 15.91 / 9 | 5.90 / 14.09 / 11 | 6.28 / 17.59 / 10 | **4.20 / 10.73 / 12** | 5.14 / 15.14 / 10 |

Endpoint error at the 30 s cut: general k fixed 4.6 m median (13.1 m worst), corridor 7.5–7.7 m; error 20 s after the stop: 4.6 m vs 7.4 m. Recovery step ≤ 0.4 m (general), 1.6 m (corridor).

Reading: once the speed error is small, the corridor mode's residual — the lateral offset held from the last fix (the rider's line wanders 3–7 m from the OSM centreline) and the polyline's own geometry — costs 1–3 m at the endpoint, which at the 30 s cut is more than the heading-induced cross-track error it removes; at the 10 s and 60 s cuts (longer outages, heading error growing) the corridor mode is still ahead. The scale state again hurts on route 1 (general 2.52 → 4.86 %) and stays off there. Both engine modes meet the 30 s target on every run (worst 6.8 % general, 10.6 % corridor with one run just over); the demo choice by these numbers is the general mode for the 30 s cut with the corridor mode for outages beyond a minute or on the route-2-length rides where it held 2–4 % against 12 %.


## Step 4 — sweep results (grouped 5-fold by round-trip pair, 20 held-out runs, plain replay with the step-3 heading)

| Configuration | params | MAE median / worst (m/s) | bias | 1-σ cov. | drift 10 s | drift 30 s median / worst / <10 % | drift in-turn / <10 % | after-stop 30 s (m) | false stops | stop lat. (s) |
|---|---:|---|---:|---:|---:|---|---|---:|---:|---:|
| GBR, hand features (the bar) | 2100 | 0.246 / 0.515 | -0.018 | 0.81 | 3.31 | 4.26 / 10.60 / 19 | 4.75 / 19 | 7.6 | 0 | 0.2 |
| CNN 100 Hz, 2.56 s, seed 0 (deployment) | 57602 | 0.173 / 0.404 | -0.041 | 0.65 | 2.33 | 3.05 / 6.61 / 20 | 4.37 / 20 | 6.0 | 0 | 0.2 |
| same, seed 1 | 57602 | 0.177 / 0.318 | +0.022 | 0.69 | 3.51 | 4.96 / 9.45 / 20 | 4.91 / 19 | 9.0 | 0 | 0.2 |
| same, seed 2 | 57602 | 0.175 / 0.376 | +0.008 | 0.67 | 3.13 | 4.32 / 7.48 / 20 | 4.70 / 20 | 8.1 | 0 | 0.2 |
| ensemble of the 3 seeds (3× size) | 3×57.6 k | 0.161 / 0.355 | -0.016 | 0.78 | 2.65 | 3.79 / 6.78 / 20 | 4.70 / 20 | 7.6 | 0 | 0.2 |
| CNN 100 Hz, 1.28 s | 57602 | 0.167 / 0.398 | -0.061 | 0.71 | 2.63 | 3.47 / 6.59 / 20 | 3.77 / 20 | 6.8 | 0 | 0.2 |
| CNN 100 Hz, 5.12 s | 57602 | 0.191 / 0.359 | -0.009 | 0.63 | 3.45 | 4.16 / 9.55 / 20 | 4.74 / 18 | 8.2 | 0 | 0.3 |
| CNN 200 Hz, 2.56 s | 57602 | 0.189 / 0.391 | -0.020 | 0.64 | 2.45 | 3.71 / 6.50 / 20 | 4.75 / 20 | 6.9 | 0 | 0.2 |
| CNN 50 Hz, 2.56 s | 57602 | 0.183 / 0.378 | +0.038 | 0.66 | 3.64 | 4.93 / 8.62 / 20 | 6.26 / 19 | 9.1 | 7 | 0.1 |
| CNN 2.56 s, no augmentation | 57602 | 0.169 / 0.424 | -0.018 | 0.65 | 2.27 | 3.49 / 8.86 / 20 | 5.01 / 18 | 6.9 | 0 | 0.2 |
| CNN 2.56 s + stop head | 57667 | 0.168 / 0.446 | -0.052 | 0.68 | 2.77 | 3.64 / 6.78 / 20 | 4.51 / 20 | 7.2 | 0 | 0.2 |
| CNN 2.56 s, half width (16.6 k params) | 16610 | 0.172 / 0.371 | -0.011 | 0.70 | 2.85 | 3.96 / 6.82 / 20 | 5.79 / 19 | 7.6 | 0 | 0.2 |
| CNN + hand features | 58818 | 0.193 / 0.356 | -0.029 | 0.68 | 2.93 | 3.61 / 7.38 / 20 | 4.49 / 19 | 7.8 | 0 | 0.2 |
| CNN + GRU | 61794 | 0.168 / 0.404 | -0.004 | 0.70 | 3.03 | 4.33 / 8.14 / 20 | 5.04 / 19 | 8.6 | 0 | 0.2 |
| ResNet-1D (181 k params) | 180994 | 0.167 / 0.380 | -0.002 | 0.63 | 3.40 | 4.46 / 6.61 / 20 | 4.36 / 20 | 8.5 | 0 | 0.2 |
| dilated TCN | 55554 | 0.200 / 0.390 | -0.013 | 0.72 | 3.32 | 3.93 / 7.54 / 20 | 5.97 / 20 | 7.5 | 0 | 0.2 |

Findings (selection criterion: drift at the 30 s cut, tie-break latency and size):
1. **The 100 Hz CNN family wins over the GBR bar** on every metric that matters: speed MAE 0.17 vs 0.25 m/s, 30 s-cut worst case 6.6 vs 10.6 %, 20/20 under 10 % at every cut for the 2.56 s and 1.28 s windows, after-stop error 6.0 vs 7.6 m.
2. **Seed spread is as large as the spread between configurations**: the same 2.56 s model at seeds 0/1/2 gives 30 s-cut medians of 3.05 / 4.96 / 4.32 % (worst 6.6 / 9.4 / 7.5 %), while the whole CNN family spans 3.05–4.96 %. Rankings inside the family are therefore not resolved by 30 minutes of riding; what is resolved is family-level: 100 Hz ≥ 200 Hz (3.71 %, a tie), 50 Hz hurts (4.93 % and 7 false stops because the stop rule's vibration band is cut at 20 Hz), 5.12 s windows lag speed changes (4.16 %, worst 9.6 %, in-turn 18/20), augmentation protects the worst case and the turn (no-aug worst 8.9 %, in-turn 18/20), and recurrence (CNN+GRU 4.33 %), ResNet-1D (4.46 %, 181 k params), the dilated TCN (3.93 %, MAE 0.20) and feature concatenation (3.61 %) bring nothing the plain strided CNN does not.
3. **Ensembling three seeds** gives the best speed MAE (0.161 m/s), the best calibration (1-σ coverage 0.78 vs 0.65–0.69, target 0.68) and removes the bad-seed risk (worst 6.8 %), but its median drift (3.79 %) does not beat the best single seed and it is 720 KB against the 300 KB target; the deployment stays a single model.
4. The half-width model (16.6 k params, 69 KB) is within the seed spread of the full one (3.96 % median, MAE 0.172) and is the fallback if the phone latency ever matters; the stop head adds nothing (stop behaviour is the hard rule's job); the uncertainty head of single seeds is slightly overconfident (coverage 0.65–0.71).
5. Finalist for leave-one-run-out: `cnn_r100_w256` (seed 0, the exported deployment model). Its LORO result and the filter scoring on the LORO predictions follow below.


## Finalist under leave-one-run-out and the final route-1 numbers

`cnn_r100_w256` trained 20 times on 19 runs (two of them as early-stopping validation), tested on the held-out run: speed MAE median 0.162 m/s, worst run 0.305 (run 13), bias −0.011 m/s, 1-σ coverage 0.63, 0 false stops, stop latency 0.2 s; plain replay drift: 10 s cut 2.97 %, 30 s cut 4.08 % median / 7.57 % worst / 20/20 under 10 %, in-turn 4.78 % / 20/20, error 20 s after the stop 8.3 m. Filter with these speeds (drift % median / worst / runs under 10 %; error 20 s after the stop):

| Cut | plain integration | general mode (k fixed) | corridor mode (k fixed) | corridor mode (k est.) |
|---|---|---|---|---|
| 10 s | 2.98 / 8.32 / 20; 8.3 m | 2.44 / 7.35 / 20; 6.9 m | 1.46 / 4.28 / 20; 4.0 m | **1.10 / 5.14 / 20; 3.2 m** |
| 30 s | 4.08 / 7.57 / 20; 8.3 m | **3.38 / 7.02 / 20; 6.9 m** | 3.38 / 7.10 / 20; 6.9 m | 2.96 / 9.56 / 20; 6.7 m |
| 60 s (14 runs) | 7.83 / 18.96 / 9; 6.7 m | 6.24 / 16.24 / 10; 5.3 m | **4.09 / 10.59 / 13; 3.3 m** | 5.14 / 18.98 / 10; 5.1 m |

Recovery (GNSS withheld +30 s, back at +60 s): error at return 4.2 m (general) / 7.5 m (corridor); largest displayed step 0.4 m / 1.6 m.

What to demo, by these numbers: corridor mode for the demo road (best at the 10 s and 60 s cuts, equal at 30 s, 20/20 under 10 % everywhere, and the mode that held 2–4 % on the 800 m route-2 outages against 12 % for the general mode); general mode with k fixed as the always-running estimator underneath (it is what runs off-corridor and what recovers with a 0.4 m step); the scale state enabled only when the model is known to be biased (other bike, other road: measured on IO-VNBD and route 2), not on the training road. The cut for the demo should come ≥ 30 s after motion start so the heading filter has had a straight with GNSS (19/20 runs under 3°).

Open items: phone latency and the Kotlin conformance run (needs the app); route 2 collection (QA → LORO on route 2 → transfer both ways → joint model); a mid-ride-stop dataset to score stop latency away from the end-of-ride stop; the seed spread says more riding data is the highest-value next input for the speed model.


## Step 11 — Route 2 (10 kept runs, 5 Sep 03:03–04:30; the 12-session collection landed 5 Sep 11:00)

Steps 1–3 and 6 rerun on `data/route2/sessions` with the same code and constants (`--tag route2`); the harness additions are a manifest-driven pair grouping (`evaluate.grouped_folds` reads `data/<tag>/manifest.csv`, route-1 folds unchanged), joint datasets (`train.py --tag route1+route2`), the QA handling of sessions with no ride window, and a merge-on-write for the heading tables. `route_id` reads `SNU_AJB` on both routes (the app was never reconfigured); routes are separated by folder only.

### QA (`data/qa/route2.csv`, `route2_flags.md`)

| run | dir | verdict | ride_s | v_mean_moving | v_max | path_m | pitch_start | pitch_end | roll_start | stand_rot_start_deg | stand_quiet_start | stand_rot_end_deg | biasz_start_dps | biasz_end_dps | bias_mismatch_dps | impact_events | a_max | start_off_m | end_off_m | flags_str |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AB | FAIL |  |  |  |  |  | 67.71 |  |  |  | 19.19 |  | 6.51 |  | 0 |  | 287.9 | 825.4 | NO_EVENT_CALIB_END; NO_EVENT_RIDE_START; NO_STAND_START; STAND_MOTION_END(rot 19.2deg, quiet 0%, acc rms 0.76); NO_RIDE_WINDOW; NO_MOTION; ANCHOR_OFF_START(288m); ANCHOR_OFF_END(825m) |
| 2 | AB | WARN | 291.4 | 3.4 | 5.29 | 851.4 | 43.74 | 26.07 | -3.4 | 37.88 | 0.0 | 2.8 | 1.85 | -0.01 | 1.86 | 0 | 26.4 | 6.6 | 20.5 | STAND_MOTION_START(rot 37.9deg, quiet 0%, acc rms 1.94); i:STAND_SLOW_ROT_END(2.8deg); MOUNT_CHANGE(18.0deg start->end); BIAS_MISMATCH(1.86dps); PITCH_OUTLIER(+21.2deg vs median 22.6); ANCHOR_DRIFT_END(20m) |
| 3 | BA | WARN | 250.9 | 3.99 | 5.31 | 853.8 | 22.86 | 23.42 | 4.3 | 1.09 | 0.75 | 1.3 | 0.06 | 0.16 | 0.09 | 2 | 33.8 | 24.0 | 0.2 | IMPACT(2 events, 7 samples, max 34 m/s2 at 49s); ROLL_OUTLIER(+6.2deg vs median -1.9); ANCHOR_DRIFT_START(24m) |
| 4 | AB | WARN | 269.3 | 3.61 | 5.63 | 879.2 | 22.29 | 23.09 | -2.35 | 1.71 | 0.92 | 1.78 | 0.04 | 0.15 | 0.11 | 1 | 47.4 | 2.8 | 0.8 | MOUNT_CHANGE(5.3deg start->end); IMPACT(1 events, 8 samples, max 47 m/s2 at 217s) |
| 5 | BA | WARN | 280.0 | 3.46 | 5.13 | 874.7 | 22.56 | 23.01 | -1.75 | 3.83 | 0.75 | 2.52 | -0.12 | 0.47 | 0.59 | 0 | 27.4 | 3.3 | 1.6 | i:STAND_SLOW_ROT_START(3.8deg); i:STAND_SLOW_ROT_END(2.5deg); BIAS_MISMATCH(0.59dps) |
| 6 | AB | PASS | 212.5 | 4.31 | 6.43 | 878.9 | 22.97 | 23.19 | -0.94 | 0.45 | 0.83 | 3.62 | 0.13 | 0.08 | 0.04 | 1 | 33.1 | 1.2 | 2.9 | i:STAND_SLOW_ROT_END(3.6deg); i:IMPACT_MINOR(1 events, 2 samples, max 33 m/s2 at 72s) |
| 7 | BA | FAIL |  |  |  |  |  | 23.39 |  |  |  | 6.03 |  | -0.36 |  | 0 |  | 2.8 | 659.5 | NO_EVENT_CALIB_END; NO_EVENT_RIDE_START; NO_STAND_START; STAND_MOTION_END(rot 6.0deg, quiet 25%); NO_RIDE_WINDOW; NO_MOTION; ANCHOR_OFF_END(659m) |
| 8 | BA | WARN | 266.4 | 3.77 | 4.83 | 877.3 | 22.31 | 23.11 | -0.84 | 0.9 | 0.92 | 0.93 | 0.02 | 0.04 | 0.02 | 2 | 37.0 | 0.3 | 0.2 | IMPACT(2 events, 5 samples, max 37 m/s2 at 79s) |
| 9 | AB | PASS | 252.7 | 3.9 | 6.04 | 877.1 | 22.68 | 23.12 | -2.52 | 2.65 | 0.75 | 0.74 | 0.09 | 0.04 | 0.05 | 1 | 30.2 | 2.6 | 3.0 | i:STAND_SLOW_ROT_START(2.7deg); i:IMPACT_MINOR(1 events, 1 samples, max 30 m/s2 at 208s) |
| 10 | BA | WARN | 235.5 | 4.08 | 6.22 | 879.6 | 22.58 | 21.47 | -1.55 | 0.62 | 1.0 | 1.52 | -0.02 | -0.03 | 0.03 | 2 | 46.1 | 1.1 | 1.6 | IMPACT(2 events, 16 samples, max 46 m/s2 at 99s) |
| 11 | AB | WARN | 207.1 | 4.39 | 6.88 | 874.2 | 22.55 | 23.34 | -1.97 | 2.38 | 0.92 | 0.92 | 0.14 | 0.1 | 0.04 | 1 | 51.0 | 1.8 | 3.4 | i:STAND_SLOW_ROT_START(2.4deg); IMPACT(1 events, 10 samples, max 51 m/s2 at 160s) |
| 12 | BA | WARN | 289.1 | 3.15 | 4.22 | 879.5 | 22.25 | 22.19 | -2.93 | 0.29 | 1.0 | 2.15 | 0.04 | 0.07 | 0.02 | 1 | 31.9 | 0.9 | 1.2 | i:STAND_SLOW_ROT_END(2.1deg); IMPACT(1 events, 5 samples, max 32 m/s2 at 137s) |

Set statistics over the 10 kept runs: pitch median 22.57° (sd 6.70°; 0.25° without run 2), roll median -1.86° (sd 2.16°), start-stand net rotation median 1.4°, start-to-end mount change median 2.3°, gyro-z bias at the start median +0.054 °/s, bias mismatch between the stands median 0.049 °/s. Rides 207–291 s, paths 851–880 m, moving mean 3.15–4.39 m/s, max 6.88 m/s, no mid-ride stop in any run. IMU 420.4 Hz, zero gaps; GNSS 1 Hz at 3.79 m, C/N0 ≥ 29.5 dB-Hz. A = (28.525945, 77.570652), B = (28.527123, 77.577232).

Findings:
1. **Two false starts, both FAIL and excluded from training**: runs 1 and 7 were stopped 4–6 s into the opening stand (no `CALIB_END`, no `RIDE_START`, 0 s ride). The QA code met a session without a ride window for the first time and crashed on it; it now flags `NO_RIDE_WINDOW` (FAIL tier) and carries the row.
2. **The mount was far more repeatable than on route 1**: pitch 22.3–23.0° at the start stand on runs 3–12 (sd 0.24°) against route 1's 0.93°, start-to-end change under 1.1°, no stand-motion warning on any run but run 2, no bias mismatch above 0.15 °/s except run 5 (0.59 °/s, slow 2.5–3.8° rotations at both stands). Route 2 sits ~3° shallower than route 1 (25.4°), a different seating of the same cage.
3. **Run 2 is the contaminated-stand case**: 37.9° of rotation and 1.9 m/s² of accelerometer RMS during the start stand, pitch 43.7° at the start against 26.1° at the end, start-stand gyro bias 1.85 °/s against −0.01 °/s at the end stand. The ride is clean (steady 24.6–26.8° pitch). Its offline bias comes from the end stand through the robust estimator (the quietest 1 s chunks of both stands together, 0 % of the start-stand chunks qualify), its levelling from ride-time gravity; the causal question (what the phone has at `RIDE_START`) is answered in the heading step below.
4. **Impacts** of 30–51 m/s² on 8 of 10 runs (5–16 samples each), at inconsistent positions (72–217 s into the ride): road bumps, not the mount, and within the ±40 m/s² robustness the model was given.
5. **The first pair turned around 25 m short of B** (run 2 end 20 m and run 3 start 24 m from the B cluster, both `ANCHOR_DRIFT`); every later pair stopped within 3.4 m of the cluster. Harmless for the engine (the corridor polyline covers both), noted for the demo-zone geometry.

### Alignment (`data/qa/align_route2.csv`, same code)

| run | dir | tilt_stand_vs_ride_deg | max_block_angle_deg | moved_at_s | ride_psi_sway_deg | ride_sway_ratio | ride_psi_init_deg | ride_psi_lean_deg | ride_psi_fit_deg | ride_yaw_slope | ride_yaw_corr | ride_yaw_rms_dps | ride_yaw_lag_s | ride_fwd_start_mps2 | ride_fwd_corr | ride_lean_corr | ride_mean_fx_straight | ride_mean_fy_straight |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | AB | 18.02 | 1.75 |  | 90.68 | 9.4 | 88.16 | 114.0 | 106.83 | 0.91 | 0.92 | 1.84 | 0.1 | 0.34 | 0.74 | 0.54 | -0.0 | 0.0 |
| 3 | BA | 0.83 | 1.08 |  | 89.56 | 9.7 | 71.19 | 80.0 | 113.53 | 0.95 | 0.97 | 1.16 | 0.2 | 0.61 | 0.84 | 0.52 | 0.05 | 0.01 |
| 4 | AB | 1.07 | 0.89 |  | 90.72 | 11.6 | 64.33 | 98.0 | 98.34 | 0.84 | 0.91 | 2.12 | 0.5 | 0.26 | 0.75 | 0.6 | -0.01 | 0.0 |
| 5 | BA | 0.76 | 0.92 |  | 88.6 | 8.8 | 117.03 | 88.0 | 157.62 | 0.72 | 0.86 | 2.07 | 0.5 | 0.36 | 0.61 | 0.38 | 0.03 | 0.0 |
| 6 | AB | 0.14 | 1.34 |  | 89.19 | 9.8 | 65.79 | 103.0 | 99.29 | 0.94 | 0.96 | 1.38 | 0.1 | 0.48 | 0.78 | 0.52 | 0.02 | -0.01 |
| 8 | BA | 0.75 | 1.27 |  | 91.1 | 14.0 | 61.99 | 67.0 | 114.02 | 0.66 | 0.82 | 2.6 | 0.4 | 0.37 | 0.62 | 0.46 | 0.02 | 0.01 |
| 9 | AB | 1.67 | 1.1 |  | 88.97 | 15.7 | 62.69 | 104.0 | 83.32 | 0.96 | 0.95 | 1.74 | 0.1 | 0.61 | 0.86 | 0.42 | 0.03 | 0.0 |
| 10 | BA | 0.89 | 1.7 |  | 89.73 | 17.1 | 71.87 | 85.0 | 91.99 | 0.99 | 0.97 | 1.36 | 0.2 | 0.42 | 0.8 | 0.58 | 0.05 | 0.02 |
| 11 | AB | 1.48 | 1.37 |  | 88.98 | 32.9 | 70.05 | 109.0 | 98.71 | 1.0 | 0.98 | 1.12 | 0.3 | 0.6 | 0.81 | 0.5 | 0.08 | -0.0 |
| 12 | BA | 1.75 | 0.91 |  | 91.67 | 13.8 | 40.54 | 90.0 | 87.0 | 0.61 | 0.84 | 2.79 | 0.4 | 0.36 | 0.55 | 0.52 | 0.02 | 0.01 |

The pedalling-sway axis gives ψ = 89.8° with an RMS spread of 1.0° over the 10 runs (max deviation 1.9°; route 1: 2.1° / 6.1°), eigenvalue ratios 8.8–32.9; the accelerometer estimators scatter by 11–21° as on route 1. Stand-vs-ride gravity differs by 0.1–1.8° on runs 3–12 and 18.0° on run 2 (the re-seated phone); the moved-phone monitor fires on no run (max 10 s block 1.7°). Forward specific force is positive at the start on every run (0.26–0.61 m/s²), 1 s means correlate with GNSS acceleration at median 0.77; residual mean force on straights |f_x| ≤ 0.08, |f_y| ≤ 0.02 m/s². The gyro-z vs course-rate slope is 0.61–1.00 (median 0.93, route 1 0.97): route 2 has one 120° turn and long straights, so the slope is set by a few seconds of turning where the receiver's course lags, and the heading step below (measured against the position course) is the real test.

### Corridor (`data/map/corridor_route2.geojson`)

The as-ridden polyline from `docs/13` (OSM ways 547215917 + 369149867 + 369151490 plus the two short connectors, 906 m) was validated against all 10 runs: every run's fixes project monotonically, median lateral offset 1.1–2.6 m per run (2.0 m over runs), p95 ≤ 7.0 m, max 9.1 m. The later pairs stop exactly at the polyline's north end (s = 903–906 m), so the north end was extended by a straight 20 m tangent overhang (927 m total; the road ends at a junction there, so following an OSM way would have added a fake 61° bend landmark). One bend landmark remains at s = 464 m (120°). Route 2's corridor is 2.9× route 1's 320 m.

### Heading (`data/qa/heading_route2.csv`; variants as in step 3 plus `kfct` = bias state with a prior matched to the measured stand accuracy, σ_b0 0.05 °/s quiet / 0.1 °/s flagged)

| cut | variant | n | mean_med | mean_worst | n_under3 | rms_med | drift_med | drift_worst | max_med | worst_run |
|---|---|---|---|---|---|---|---|---|---|---|
| c10 | robust | 10 | 3.46 | 6.71 | 4 | 4.24 | 1.68 | 8.29 | 9.18 | 2 |
| c10 | kfpsi | 10 | 1.82 | 4.61 | 9 | 2.76 | 1.94 | 8.3 | 8.34 | 11 |
| c10 | kfpsic | 10 | 1.14 | 4.71 | 9 | 2.41 | 1.98 | 8.32 | 8.36 | 12 |
| c10 | kfc | 10 | 2.26 | 5.4 | 7 | 3.76 | 4.0 | 8.92 | 9.16 | 9 |
| c10 | kfct | 10 | 1.13 | 4.71 | 8 | 2.4 | 2.11 | 8.32 | 8.54 | 12 |
| c10 | kfpsic2d | 10 | 0.87 | 4.76 | 9 | 2.45 | 1.64 | 6.51 | 7.4 | 12 |
| c10 | kfpsic_notilt | 10 | 1.11 | 4.7 | 9 | 2.63 | 1.46 | 6.77 | 8.04 | 12 |
| c30 | robust | 10 | 3.36 | 6.58 | 4 | 4.2 | 1.73 | 8.55 | 9.18 | 2 |
| c30 | kfpsi | 10 | 0.79 | 6.49 | 8 | 2.54 | 1.73 | 8.6 | 8.34 | 11 |
| c30 | kfpsic | 10 | 0.75 | 4.14 | 9 | 2.3 | 1.73 | 8.65 | 8.02 | 3 |
| c30 | kfc | 10 | 2.14 | 11.37 | 6 | 3.32 | 4.16 | 19.61 | 10.3 | 2 |
| c30 | kfct | 10 | 0.92 | 4.38 | 8 | 2.4 | 2.48 | 9.43 | 8.58 | 2 |
| c30 | kfpsic2d | 10 | 1.17 | 2.81 | 10 | 2.52 | 1.85 | 6.77 | 8.16 | 3 |
| c30 | kfpsic_notilt | 10 | 0.82 | 3.63 | 8 | 2.52 | 1.92 | 7.09 | 8.24 | 2 |
| c60 | robust | 10 | 3.18 | 6.42 | 4 | 4.26 | 2.22 | 7.24 | 9.18 | 2 |
| c60 | kfpsi | 10 | 0.97 | 6.73 | 7 | 2.64 | 2.22 | 7.24 | 8.57 | 3 |
| c60 | kfpsic | 10 | 1.34 | 3.18 | 9 | 2.47 | 2.23 | 7.24 | 7.64 | 3 |
| c60 | kfc | 10 | 2.22 | 4.58 | 7 | 3.41 | 3.9 | 8.98 | 8.8 | 10 |
| c60 | kfct | 10 | 1.6 | 3.32 | 9 | 2.93 | 3.28 | 5.71 | 7.76 | 2 |
| c60 | kfpsic2d | 10 | 1.04 | 2.04 | 10 | 2.54 | 1.9 | 5.29 | 7.36 | 2 |
| c60 | kfpsic_notilt | 10 | 1.54 | 3.6 | 9 | 2.83 | 2.07 | 5.55 | 7.56 | 2 |
| turn | robust | 10 | 3.31 | 6.03 | 3 | 4.23 | 2.27 | 5.23 | 9.18 | 2 |
| turn | kfpsi | 10 | 1.16 | 4.07 | 9 | 2.68 | 2.27 | 5.23 | 6.97 | 3 |
| turn | kfpsic | 10 | 0.86 | 4.57 | 9 | 2.53 | 2.27 | 5.23 | 6.5 | 3 |
| turn | kfc | 10 | 1.32 | 3.97 | 8 | 2.74 | 0.74 | 7.05 | 7.63 | 3 |
| turn | kfct | 10 | 1.19 | 4.13 | 9 | 2.54 | 0.73 | 6.41 | 7.22 | 3 |
| turn | kfpsic2d | 10 | 0.59 | 2.59 | 10 | 2.46 | 2.45 | 4.37 | 7.18 | 3 |
| turn | kfpsic_notilt | 10 | 1.09 | 4.71 | 8 | 2.84 | 2.42 | 5.72 | 7.18 | 2 |

Per run, variant `kfpsic`, cut at motion start + 30 s (outages 171–252 s, 600–850 m):

| run | dir | outage_s | mean_deg | start_err_deg | end_err_deg | drift_deg | rms_deg | max_abs_deg | bias_stand_dps | bias_oracle_dps |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | AB | 223.51 | -1.4 | -0.41 | -1.34 | -0.94 | 2.4 | 7.06 | -0.02 | -0.04 |
| 3 | BA | 204.0 | -4.14 | 0.4 | -8.24 | -8.65 | 5.01 | 10.4 | 0.0 | -0.03 |
| 4 | AB | 218.23 | -0.65 | -0.61 | -1.75 | -1.15 | 2.17 | 6.82 | 0.02 | 0.0 |
| 5 | BA | 225.54 | 0.05 | -1.0 | -0.26 | 0.73 | 2.19 | 8.35 | 0.02 | 0.02 |
| 6 | AB | 176.21 | 0.82 | 0.38 | 4.08 | 3.69 | 2.18 | 5.6 | 0.01 | -0.0 |
| 8 | BA | 218.18 | -0.09 | -0.1 | 0.03 | 0.14 | 2.76 | 8.66 | 0.02 | 0.03 |
| 9 | AB | 198.62 | 1.7 | -0.06 | 3.46 | 3.52 | 2.85 | 7.69 | 0.01 | 0.01 |
| 10 | BA | 186.99 | 0.87 | 0.46 | -1.36 | -1.81 | 1.99 | 7.3 | 0.02 | 0.03 |
| 11 | AB | 171.29 | 0.69 | -0.74 | 1.27 | 2.01 | 2.04 | 8.59 | 0.01 | 0.01 |
| 12 | BA | 251.94 | 0.24 | -0.42 | 1.23 | 1.65 | 3.25 | 10.46 | 0.01 | 0.02 |

Findings:

1. **The route-1 engine variant (`kfc`, ψ and gyro-bias states) fails on route 2's long outages**: 30 s-cut median 2.15°, worst 11.4° (run 2: −20.7° at the end of a 224 s outage, run 3: −13.3°), 6/10 under 3°. Its bias state leaves the first 30 s of GNSS 0.05–0.11 °/s away from the whole-ride oracle (bias is barely observable in 30 s: a 0.1 °/s bias is 3° of heading, the size of the course noise), which cost 2–4° over route 1's 40–80 s outages and costs 10–20° over 200 s. The robust stand bias is within 0.03 °/s of the oracle on every route-2 run (run 2 included, through the end stand), so the state has nothing to correct on this road.

2. **Harness choice over both routes at the 30 s cut** (median / worst / runs under 3°): route 1 — kfc 1.18 / 3.03 / 19, kfpsic 1.33 / 3.33 / 19, kfct 1.23 / 3.36 / 19, kfpsic2d 1.40 / 4.53 / 15; route 2 — kfc 2.15 / 11.37 / 6, kfpsic 0.75 / 4.14 / 9, kfct 0.92 / 4.38 / 8, kfpsic2d 1.17 / 2.81 / 10. Summed over 30 runs: **`kfpsic` 28/30 under 3°, worst 4.1°**; kfct 27/30, worst 4.4°; kfc 25/30, worst 11.4°; kfpsic2d 25/30, worst 4.5°. The engine heading is now `kfpsic` (ψ refined from the position course on straight, fast fixes; the robust stand bias held fixed; 3-D attitude): `heading.ENGINE_HEADING`, used by `filter.py` and `replay.py` (`--heading` overrides). The tight-prior bias state repairs kfc's failure but does not beat the fixed bias, and the 2-D yaw wins on route 2 (no S-bend lean) and loses on route 1, so the 3-D attitude stays.

3. **What bounds the long outages** is the residual stand-bias error: runs 2 and 3 (the first pair) drift −7 to −9° over 200+ s under every fixed-bias variant, with the stand bias 0.02–0.03 °/s from the oracle; 0.03 °/s is 6° in 200 s. Every other run stays within 3.3° of drift at the 30 s cut. A longer stand or a ZIHR at a mid-ride stop is the only cheaper bias than GNSS time.

4. **The causal case for a contaminated stand** (`kfc_loose`: the plain start-stand mean bias, which is what the phone has at `RIDE_START`, a 2 °/s bias prior and a 3 °/s clamp, ψ and bias refined from the course). On route-2 run 2 the start-stand bias is 1.9 °/s wrong; the bias state pulls it to within 0.14 °/s by the 30 s cut (heading −14.8° mean, −28° drift over 224 s) and to under 5° of error at the 60 s cut. But the loose state also *damages quiet runs*: at the 30 s cut it walks run 12's bias 0.2 °/s off (26° error), route 1's run 13 by 0.6 °/s, and its 30 s-cut medians are 5.6° (route 2) and 2.3° (route 1) with 14 of 30 runs under 3°; at 60 s it is 2.2° / 1.5° median, 19 of 24 under 3°. So a bias state cannot replace a quiet stand within 30 s, and it should be armed only when the stand check fails. Engine rule (all computable on the phone): stand quiet (≥ 50 % of 1 s chunks with |ω| < 0.57 °/s, net rotation < 5°) → `kfpsic` with the robust stand bias; stand not quiet → the loose bias state, and the outage may only be trusted 60 s after motion start. The demo must not start with a moved stand, and the logger's stand check already reports this.

### Label lag: a sign error found and corrected (affects route 1 too)

Route 2's vibration-based lag estimator returned 1.4 s with 5 of 10 runs pinned at its 1.5 s search cap (route 1: 0.7 s), which prompted a direct measurement. Cross-correlating the receiver's Doppler speed against the position-derived speed (PCHIP track) gives a lag of **0.2 s** median on route 1 and **0.3 s** on route 2 (correlations 0.98–0.99); the aligned forward accelerometer against d(v_GNSS)/dt gives 0.25 / 0.30 s. The route-1 held-out predictions (`cnn_r100_w256_loro`) lag the position-derived speed by **0.8 s** raw and **1.7 s** after the 1 s smoother. Cause: `dataset.py` measured the lag correctly (GNSS speed reported ~0.7 s after the vibration it matches) but labelled IMU time t with v_GNSS(t − lag) instead of v_GNSS(t + lag), so the labels lagged the true speed by 2 × 0.7 − 0.2 ≈ 0.9 s and the model learned to output the speed 0.8 s ago. In an outage that integrates as an along-track overshoot of about lag × v(cut) − (distance of the last lag seconds before the stop) ≈ 0.8 × 3.5 − 1 ≈ 2 m per outage (0.7 % of route 1's 300 m, more on the in-turn cut where a late speed also lags the corner), and it is what the step-5 scale state read as a "2 % early-ride transient".

Fix: the estimator is now the Doppler-vs-position correlation (per run, median across runs, −0.5–1.5 s search) and the label is v_GNSS(t + lag); measured 0.20 s on route 1 (0.0–0.3 s per run) and 0.25 s on route 2 (0.1–0.4 s), so **one constant of 0.2 s** is applied to both routes and goes into the spec. Both 100 Hz datasets were rebuilt (`route{1,2}_100hz.npz`; the old files are kept as `*_lagold.npz`) and every model below is trained on the corrected labels; the route-1 finalist is retrained on them so that route 1, route 2 and the joint model are compared like for like. The 1 s exponential smoother stays in the plain-replay baseline only (the filter consumes the raw model speed with its σ).

The same mis-estimate had set the fusion filter's GNSS-speed latency `LAG_V` to 0.7 s. Set to the measured 0.2 s and compared on the route-2 GBR speeds (10 runs, kfpsic heading): identical within 0.1 % drift at every cut and variant except the general mode with the scale state at the 10 s cut (4.40 → 3.84 % median) and the corridor recovery error (6.5 → 5.7 m at GNSS return); the measured value stays (`filter.LAG_V = 0.2`, spec §5).

### Stop rule on route 2 (same thresholds)

| Regime | windows | vibration RMS p5 / median / p95 (m/s²) | gyro RMS p5 / median / p95 (rad/s) | rule fires |
|---|---:|---|---|---:|
| stands | 551 | 0.046 / 0.098 / 0.574 | 0.006 / 0.015 / 0.082 | 91.7 % |
| riding 0.5–1 m/s | 20 | 0.89 / 1.64 / 4.37 | 0.065 / 0.161 / 0.347 | 0.0 % |
| riding 1–2 m/s | 91 | 0.83 / 1.15 / 2.08 | 0.094 / 0.189 / 0.445 | 0.0 % |
| riding 2–3 m/s | 479 | 0.90 / 1.26 / 1.91 | 0.105 / 0.196 / 0.397 | 0.0 % |
| riding > 3 m/s | 4042 | 1.28 / 2.02 / 4.30 | 0.126 / 0.219 / 0.446 | 0.0 % |

The route-2 road excites the phone slightly more than route 1 (median vibration 2.0 vs 1.9 m/s² above 3 m/s) and the rule never fires while rolling, at any speed; the stationary floor (0.05–0.10 m/s²) is again an order of magnitude under the threshold.

**Stop latency, re-measured.** The harness scores latency from the last Doppler speed above 0.5 m/s to the first zeroed output, and on route 2 that reads 1.0–2.3 s (median 1.7 s) against 0.2 s on route 1. The reference moved, not the rule: with the corrected labels the receiver's zero is no longer shifted late, and on route 2's slow roll-ins the receiver reports zero speed while the bike is still rolling (the Doppler zero precedes the end of rolling-level vibration by 0.6 s median, up to 3.3 s on run 9). Against the end of rolling vibration (last 0.5 s window above 1 m/s² within 5 s of the Doppler zero) the hard rule fires after **0.7 s median, 0.2–1.7 s** (runs 6, 8, 12 at 1.4–1.7 s are gyro settling as the feet come down), i.e. inside the 1 s target at the median and never a false stop. Route 1's 0.2 s was the same rule measured against labels that were 0.9 s late; the rule is unchanged. The physical reference is the one to use from here on.

### Route 1 re-scored with the corrected labels and the new heading (`cnn_r100_w256_lagfix`, grouped 5-fold, `filter_cnn_r100_w256_lagfix`)

Speed model on the corrected labels: MAE 0.195 / 0.446 m/s, bias -0.010, 1-σ cov. 0.59, false stops 0; plain replay (kfc heading, 1 s smoother, for comparability with the sweep table) 30 s cut 3.04 % median / 6.86 % worst / 20/20, in-turn 3.71 % / 20/20, after-stop 5.8 m. The MAE rises from 0.173 to 0.195 m/s because the label is now the speed at the window's end instead of a point 0.9 s inside it; the GBR bar moves the same way (0.246 → 0.280). Filter with the `kfpsic` heading and `LAG_V` 0.2 s (drift % median / worst / runs under 10 %; error 20 s after the stop):

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 2.24 / 7.88 / 20; 6.2 m | 2.28 / 7.72 / 20; 5.8 m | 2.53 / 8.56 / 20; 6.8 m | 2.41 / 9.09 / 20; 6.8 m | 1.42 / 4.61 / 20; 3.6 m |
| 30 s | 2.96 / 7.31 / 20; 5.7 m | 2.90 / 7.89 / 20; 5.1 m | 3.50 / 13.22 / 18; 7.2 m | 3.66 / 9.59 / 20; 7.7 m | 4.36 / 10.78 / 18; 7.6 m |
| 60 s (14) | 6.65 / 12.81 / 12; 4.4 m | 3.50 / 17.02 / 11; 3.6 m | 5.00 / 18.78 / 10; 4.3 m | 4.06 / 10.95 / 13; 4.3 m | 5.28 / 15.77 / 12; 4.9 m |
| in-turn | 3.79 / 10.24 / 19; 5.9 m | 3.59 / 12.78 / 19; 5.4 m | 3.79 / 14.69 / 17; 6.6 m | 4.27 / 10.43 / 19; 7.6 m | 4.80 / 12.04 / 19; 7.6 m |
recovery (median): cor: at return 7.2 m, +3 s 5.0 m, max step 1.57 m; cor_k1: at return 8.7 m, +3 s 7.7 m, max step 1.57 m; cor_lm: at return 7.2 m, +3 s 5.0 m, max step 1.52 m; gen: at return 5.2 m, +3 s 5.0 m, max step 0.40 m; gen_k1: at return 3.9 m, +3 s 4.0 m, max step 0.40 m
k_end at 30 s (median): gen 1.018, cor 1.016


Against the previous route-1 table (old labels, kfc heading): plain 3.05 → 2.96 %, general k fixed 2.52 → 2.90 %, corridor k fixed 4.47 → 3.66 % at the 30 s cut, all 20/20; at 60 s general 5.90 → 3.50 %, corridor 4.20 → 4.06 % (13 of 14 under 10 %); at 10 s corridor with k 1.09 → 1.42 % but worst 6.40 → 4.61 %. The shifts are within the measured seed spread (3.1–5.0 %); what changed is that every number is now against the true current speed and with the heading that survives long outages. Both modes still meet the 30 s targets on all 20 runs. The scale state still hurts on route 1 (general 2.90 → 3.50 %, 18/20) and stays off on the training road; its k_end median is now 1.018 (was 1.02 on the late labels, so the residual is not only the lag).

### Cross-road transfer, speed model (`transfer.py`; all-runs models `cnn_r100_w256_r1deploy` / `_r2deploy`, corrected labels)

| Train → test | model | speed MAE median / worst (m/s), bias, 1-σ coverage | plain replay 30 s drift (kfc heading) |
|---|---|---|---|
| route 1 (20 runs) → route 2 (10 runs) | CNN | 0.228 / 0.322, +0.010, 0.49 | 3.66 % / 14.16 %, 8/10 |
| route 1 → route 2 | GBR | 0.398 / 0.550, -0.094, 0.41 | 7.83 % / 13.64 %, 7/10 |
| route 2 (10 runs) → route 1 (20 runs) | CNN | 0.233 / 0.633, -0.046, 0.61 | 3.45 % / 7.98 %, 20/20 |
| route 2 → route 1 | GBR | 0.288 / 0.746, -0.070, 0.25 | 4.42 % / 9.94 %, 20/20 |

In-road references on the same labels: route 1 CNN 0.195 m/s (grouped 5-fold), route 2 GBR 0.212 m/s (LORO). The CNN crosses roads at a cost of 0.03–0.04 m/s (0.228 / 0.233 m/s), with bias +0.01 (route 1 → 2) and −0.05 m/s (route 2 → 1, the smaller set under-reads the faster route-1 rides by ~1 %); the hand-feature GBR loses 0.1–0.2 m/s and reads −0.09 m/s low on route 2. The two roads therefore share the same vibration-to-speed relation to within the seed noise, which is what the joint model needs. The engine (filter) numbers on these transfer speeds follow.

### Cross-road transfer in the engine, route 2 → route 1 (`filter_xfer_r2_to_r1_cnn`; 20 route-1 runs, model trained on the 10 route-2 runs only)

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 2.38 / 8.99 / 20; 6.1 m | 2.26 / 8.40 / 20; 5.9 m | 3.28 / 8.94 / 20; 8.5 m | 2.64 / 10.02 / 19; 7.2 m | 1.36 / 7.23 / 20; 4.2 m |
| 30 s | 4.18 / 7.66 / 20; 7.5 m | 2.50 / 8.08 / 20; 4.5 m | 5.40 / 16.18 / 17; 11.0 m | 4.62 / 13.40 / 19; 8.1 m | 4.24 / 10.78 / 19; 7.2 m |
| 60 s (14) | 8.38 / 14.74 / 7; 6.2 m | 4.14 / 17.88 / 12; 3.5 m | 7.21 / 20.61 / 9; 5.9 m | 3.78 / 10.82 / 13; 3.7 m | 5.14 / 16.04 / 10; 5.1 m |
| in-turn | 5.64 / 11.39 / 19; 6.8 m | 3.48 / 13.28 / 19; 4.4 m | 5.24 / 18.81 / 16; 8.7 m | 4.14 / 13.19 / 19; 7.6 m | 3.34 / 16.22 / 18; 6.6 m |
recovery (median): cor: at return 7.4 m, +3 s 5.6 m, max step 1.59 m; cor_k1: at return 10.1 m, +3 s 9.2 m, max step 1.59 m; cor_lm: at return 7.4 m, +3 s 5.6 m, max step 1.59 m; gen: at return 4.5 m, +3 s 4.8 m, max step 0.40 m; gen_k1: at return 2.3 m, +3 s 2.1 m, max step 0.39 m
k_end at 30 s (median): gen 1.036, cor 1.030

A model that has never seen route 1 runs the general mode on it at 2.50 % median / 8.08 % worst / 20 of 20 at the 30 s cut, the same as the in-road model (2.90 / 7.89); the corridor mode is 1 % worse than in-road (4.62 vs 3.66 %). The scale state reads the model's −1.3 % bias (k_end 1.036) and still degrades every cut (general 2.50 → 5.40 %, 17/20): on a bias this small the k state trades a 1 % gain for its own 30 s identifiability noise, as on the training road. k remains a large-bias tool (IO-VNBD's −23 %).

### Cross-road transfer in the engine, route 1 → route 2 (`filter_xfer_r1_to_r2_cnn2`; 10 route-2 runs, model trained on the 20 route-1 runs only; outages 600–850 m, 170–250 s)

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 4.04 / 6.74 / 10; 33.9 m | 4.36 / 6.78 / 10; 36.9 m | 4.27 / 9.17 / 10; 36.3 m | 1.78 / 5.03 / 10; 15.1 m | 1.69 / 5.33 / 10; 14.4 m |
| 30 s | 3.22 / 6.36 / 10; 24.3 m | 3.78 / 6.78 / 10; 28.9 m | 4.61 / 7.93 / 10; 34.9 m | 1.74 / 5.24 / 10; 13.4 m | 2.00 / 5.83 / 10; 14.8 m |
| 60 s (10) | 3.62 / 6.43 / 10; 23.2 m | 4.38 / 6.76 / 10; 28.2 m | 5.16 / 8.89 / 10; 34.1 m | 1.88 / 5.75 / 10; 12.5 m | 3.18 / 5.33 / 10; 20.2 m |
| in-turn | 4.26 / 8.01 / 10; 17.7 m | 4.50 / 8.25 / 10; 18.5 m | 7.15 / 9.63 / 10; 32.1 m | 2.27 / 6.50 / 10; 10.7 m | 4.93 / 8.28 / 10; 20.9 m |
recovery (median): cor: at return 6.1 m, +3 s 5.9 m, max step 0.79 m; cor_k1: at return 7.3 m, +3 s 7.3 m, max step 0.85 m; cor_lm: at return 6.1 m, +3 s 5.9 m, max step 0.79 m; gen: at return 7.4 m, +3 s 7.9 m, max step 0.44 m; gen_k1: at return 5.1 m, +3 s 6.1 m, max step 0.49 m
k_end at 30 s (median): gen 1.050, cor 1.054

This is the unseen-road result the brief asked for: a model that has never seen route 2, on a corridor 2.9× longer, holds **1.74 % median / 5.24 % worst / 10 of 10 at the 30 s cut** in corridor mode (13 m after the stop over ~800 m), 1.88 / 5.75 at 60 s, 2.27 / 6.50 in the turn; the general mode holds 3.78 / 6.78 / 10 of 10 (its residual is the 4–9° heading drift of runs 2, 3 and 12 over 200 s, which the corridor's cross-track constraint removes). Every variant is 10 of 10 under 10 % at every cut.

**Scale state, closed.** On both roads k settles at 1.02–1.06 with models whose bias against the labels is +0.01 to −0.05 m/s, and enabling it costs 0.3–3 % of drift at the 30 s cut in the general mode (route 1 in-road 2.90 → 3.50, route 2 → 1 2.50 → 5.40, route 1 → 2 3.78 → 4.61) and is neutral in the corridor mode at 30 s (1.74 → 2.00 here, 3.16 → 2.42 with the GBR). The labels are not the cause: the Doppler speed integrates to within 0.3–0.5 % of the position-derived path on all 30 runs (median ratio 0.9945 route 1, 0.9967 route 2). The reading is the state's own 30 s identifiability artefact (its observation window sees the v-state lag behind the receiver's speed at every acceleration and books it as scale). k stays **off for bicycle roads in both modes** and on only where a model is known to be far off (IO-VNBD, −23 %, 24 → 14 %); the engine keeps the state so the app can enable it for an external IMU.

### Joint deployment model and export (`cnn_r100_w256_joint_deploy`, all 30 kept runs, corrected labels)

Trained on the 20 route-1 and 10 route-2 runs with runs [6, 21] as the early-stopping validation (16 epochs, val NLL -1.1298), 57602 parameters, same architecture and window as the route-1 finalist. Export (`engine/export/export.py`, verified on 2000 real windows): ONNX 230450 bytes, max |Δ| vs PyTorch 1.9e-06; TFLite float32 239688 bytes via the Keras twin, max |Δ| 1.9e-06 (target 1e-4); ops unchanged (CONV_2D ×4, FULLY_CONNECTED ×2, MEAN, PAD ×4, RESHAPE/EXPAND_DIMS, all XNNPACK fp32 kernels); single-thread latency on this Mac 0.067 ms (ONNX Runtime) / 0.066 ms (LiteRT) per window. Normalisation (training runs only, in `cnn_r100_w256_joint_deploy_export.json`): mean [0.03391, 0.00139, 9.30145, 0.00019, -0.0067, -0.00014], std [1.04142, 1.31722, 1.56807, 0.14452, 0.06602, 0.19358]. Whether this or a per-route model is the one to ship is decided by the held-out comparison below.

### Joint model, held out by pair on both roads (`cnn_r100_w256_joint`, grouped 5-fold over the 15 round-trip pairs: each fold holds out 2 route-1 pairs and 1 route-2 pair)

Speed model: on the 20 route-1 runs MAE 0.179 / 0.406 m/s (route-1-only model on the same labels: 0.195 / 0.446), bias −0.02, 1-σ coverage 0.65; on the 10 route-2 runs MAE 0.164 / 0.304 m/s (route-2 GBR 0.212, route-1-trained CNN 0.228), bias −0.01; 0 false stops on 30 runs. Adding route 2 makes the route-1 speed estimate better, not worse: the seed-spread finding of the sweep ("more riding data is the top next input") holds, and 41 minutes of a different road count as riding data.

Engine on route 1 with the joint held-out speeds (`filter_cnn_r100_w256_joint`, `--tag route1`):

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 3.60 / 5.05 / 10; 30.5 m | 3.68 / 4.78 / 10; 31.1 m | 3.65 / 7.18 / 10; 30.6 m | 2.36 / 6.10 / 10; 19.7 m | 2.44 / 8.40 / 10; 20.6 m |
| 30 s | 2.88 / 5.90 / 10; 22.3 m | 2.80 / 5.89 / 10; 21.4 m | 3.99 / 6.99 / 10; 30.8 m | 2.33 / 6.26 / 10; 17.3 m | 2.04 / 5.68 / 10; 15.1 m |
| 60 s (10) | 2.54 / 5.19 / 10; 16.5 m | 2.97 / 5.09 / 10; 19.2 m | 3.94 / 6.51 / 10; 23.6 m | 2.46 / 6.15 / 10; 14.9 m | 1.98 / 3.52 / 10; 12.1 m |
| in-turn | 2.49 / 7.48 / 10; 10.8 m | 3.29 / 7.13 / 10; 14.1 m | 4.04 / 7.37 / 10; 17.7 m | 2.69 / 5.97 / 10; 11.9 m | 1.57 / 4.81 / 10; 6.6 m |
recovery (median): cor: at return 3.7 m, +3 s 2.0 m, max step 0.85 m; cor_k1: at return 5.6 m, +3 s 5.1 m, max step 0.91 m; cor_lm: at return 3.7 m, +3 s 2.0 m, max step 0.85 m; gen: at return 5.1 m, +3 s 5.7 m, max step 0.45 m; gen_k1: at return 3.2 m, +3 s 3.1 m, max step 0.49 m
k_end at 30 s (median): gen 1.030, cor 1.039

Against the route-1-only model at the 30 s cut: general 2.90 → 2.58 % median, 7.89 → 6.82 % worst; corridor 3.66 → 4.31 % median, 9.59 → 7.13 % worst; 20 of 20 in both modes; at 10 s the corridor worst case 4.61 → 3.19 %; at 60 s 17.0 → 14.6 % worst in the general mode. Medians move within the seed spread, worst cases improve at the demo cut, and the speed MAE improves on both roads: **the joint model is the deployment model**. Its route-2 engine table follows.

### Engine on route 2 with the joint held-out speeds (`filter_cnn_r100_w256_joint_route2`; 10 runs, outages 600–850 m / 170–250 s from the 30 s cut)

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 3.60 / 5.05 / 10; 30.5 m | 3.68 / 4.78 / 10; 31.1 m | 3.65 / 7.18 / 10; 30.6 m | 2.36 / 6.10 / 10; 19.7 m | 2.44 / 8.40 / 10; 20.6 m |
| 30 s | 2.88 / 5.90 / 10; 22.3 m | 2.80 / 5.89 / 10; 21.4 m | 3.99 / 6.99 / 10; 30.8 m | 2.33 / 6.26 / 10; 17.3 m | 2.04 / 5.68 / 10; 15.1 m |
| 60 s (10) | 2.54 / 5.19 / 10; 16.5 m | 2.97 / 5.09 / 10; 19.2 m | 3.94 / 6.51 / 10; 23.6 m | 2.46 / 6.15 / 10; 14.9 m | 1.98 / 3.52 / 10; 12.1 m |
| in-turn | 2.49 / 7.48 / 10; 10.8 m | 3.29 / 7.13 / 10; 14.1 m | 4.04 / 7.37 / 10; 17.7 m | 2.69 / 5.97 / 10; 11.9 m | 1.57 / 4.81 / 10; 6.6 m |
recovery (median): cor: at return 3.7 m, +3 s 2.0 m, max step 0.85 m; cor_k1: at return 5.6 m, +3 s 5.1 m, max step 0.91 m; cor_lm: at return 3.7 m, +3 s 2.0 m, max step 0.85 m; gen: at return 5.1 m, +3 s 5.7 m, max step 0.45 m; gen_k1: at return 3.2 m, +3 s 3.1 m, max step 0.49 m
k_end at 30 s (median): gen 1.030, cor 1.039

Per run at the 30 s cut (drift %):

| run | plain | general k fixed | corridor k fixed | corridor k est. |
|---|---|---|---|---|
| 2 | 2.07 | 1.86 | 0.45 | 5.68 |
| 3 | 5.90 | 5.89 | 2.56 | 2.08 |
| 4 | 1.31 | 1.10 | 3.70 | 2.75 |
| 5 | 0.91 | 1.48 | 3.03 | 0.60 |
| 6 | 3.21 | 3.26 | 4.19 | 4.09 |
| 8 | 3.17 | 4.21 | 6.26 | 1.93 |
| 9 | 3.34 | 3.39 | 0.60 | 2.00 |
| 10 | 0.20 | 0.63 | 2.09 | 1.71 |
| 11 | 3.45 | 3.29 | 0.75 | 2.86 |
| 12 | 2.60 | 2.34 | 1.58 | 1.08 |

Replay harness (`replay.py --all --tag route2 --mode corridor`, k off, real-outage detector on, fixes consumed at the next 10 Hz tick): 30 s cut drift median 2.43 %, worst 6.40 %, 10 of 10; 10 s cut 2.42 / 6.17; 60 s 2.55 / 6.32; in-turn 2.74 / 5.96; endpoint median 18 m after ~800 m, all 10 of 10. Runs 2, 9 and 11 hold under 1 % over the whole leg; run 8 is the worst at 6.4 % (its heading drifts +5° over 220 s).

Findings:
1. **Every mode meets the 30 s targets on route 2 with margin**: medians 2.0–2.9 %, worst 5.7–6.3 %, 10 of 10 at every cut, and this over outages four times longer than route 1's. The general mode holds 2.80 % / 5.89 % on its own, so the off-corridor fallback is not a weak point on this road.
2. **Corridor mode is the demo mode on route 2 as well**: 2.33 % median / 6.26 % worst with k fixed against 2.80 / 5.89 for the general mode at 30 s, and clearly ahead at 60 s (2.46 vs 2.97 %) and in the turn (2.69 vs 3.29 %), where the heading residual costs the general mode cross-track error the corridor removes. Its recovery on GNSS return is 5.6 m with a 0.9 m largest step (general 3.2 m, 0.5 m).
3. **The scale state is not decided by route 2**: with k the corridor medians improve (2.33 → 2.04 % at 30 s, 2.46 → 1.98 at 60 s, 2.69 → 1.57 in the turn) but the 10 s worst case goes 6.10 → 8.40 %, and per run k flips the error both ways (run 2: 0.45 → 5.68 %, run 8: 6.26 → 1.93 %); with route 1's consistent loss it stays off. The along-track residual in corridor mode is the model's per-run speed scale (±2 %) plus the 1–3 m held lateral offset; on 800 m the scale term dominates.
4. **Demo road, by these numbers**: route 2. Same model, same engine, held out on both: corridor mode 2.33 % / 6.26 % (route 2) against 4.31 % / 7.13 % (route 1) at the 30 s cut, 10 of 10 against 20 of 20; general mode 2.80 / 5.89 against 2.58 / 6.82. Route 2 gives the lower corridor drift, holds it over four times the distance through a 120° turn, has the cleaner mount and stands, and its 440 m + 480 m straights let the video show a 400–500 m outage (at 2.3 % that is 9–12 m at the end). The cut must come ≥ 30 s after motion start (heading refined on the first straight) and the stand must be quiet (heading step, finding 4). Route 1 remains the short-corridor demo and the one with the sharper S-bend.

### Conformance references regenerated (v2 engine, joint deployment model, corridor mode, GNSS withheld from +30 s)

`data/qa/replay/r2only/20260905_033817_SNU_AJB_AB_run4_corridor_mm0.csv` (route 2, the demo configuration with the seed-1 corridor model): outage 789 m / 218 s, endpoint 22.1 m (2.81 %), RMSE 15.1 m; the joint-model variant `data/qa/replay/20260905_033817_SNU_AJB_AB_run4_corridor_mm0.csv` gives 20.7 m (2.62 %), RMSE 13.9 m. `data/qa/replay/20260905_003612_SNU_AJB_AB_run1_corridor_mm0.csv` (route 1): outage 229 m / 82 s, endpoint 6.7 m (2.92 %), RMSE 6.0 m. Both sessions are in the deployment model's training set, so these are the app's conformance targets (spec §9, tolerance max |Δposition| < 1 m), not accuracy claims; plots alongside the CSVs.

### Speed model on route 2, all candidates on the same labels (`results.csv`)

| Model on the 10 route-2 runs | MAE median / worst (m/s) | bias | 1-σ cov. | plain replay 30 s (kfc heading) | in-turn | false stops |
|---|---|---:|---:|---|---|---:|
| route-2-only CNN, leave-one-run-out (9 training runs) | 0.172 / 0.316 | +0.016 | 0.65 | 2.83 / 14.67 / 9 | 3.54 / 10 | 0 |
| joint CNN, grouped 5-fold (≈16 route-1 + 8 route-2 training runs) | 0.164 / 0.304 | -0.011 | 0.62 | 1.79 / 14.84 / 9 | 3.51 / 10 | 0 |
| route-1-only CNN, all 20 runs (transfer) | 0.228 / 0.322 | +0.010 | 0.49 | 3.66 / 14.16 / 8 | 4.82 / 10 | 0 |
| route-2-only GBR, leave-one-run-out (the bar) | 0.212 / 0.410 | -0.051 | 0.80 | 3.16 / 14.12 / 7 | 3.82 / 10 | 0 |
| route-1-only GBR, all 20 runs (transfer) | 0.398 / 0.550 | -0.094 | 0.41 | 7.83 / 13.64 / 7 | 7.48 / 8 | 0 |

The route-2-only model (`cnn_r100_w256_r2loro`, 10 folds) is the strict in-road number: MAE 0.172 m/s, worst run 0.316 (run 11), 0 false stops. The joint model beats it on route 2 (0.164 / 0.304) while training on fewer route-2 runs per fold, and beats the route-1-only model on route 1: the ranking is the same on both roads, so there is one deployment model. The plain-replay drift column uses the old kfc heading and is heading-dominated on route 2 (runs 2 and 12 at 10–15 % in every model); the engine numbers with the kfpsic heading are the tables above (10 of 10 under 10 % for every model, every mode). Rider-held-out was not possible: every route-2 session carries `rider_id = rider_1` (the app's default was never changed), so the cross-road transfer, which also crossed the mount seating (22.5° vs 25.4° pitch), is the held-out-condition test available.

### Engine on route 2 with the route-2-only LORO speeds (`filter_cnn_r100_w256_r2loro_route2`), for comparison

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 2.70 / 5.87 / 10; 22.6 m | 2.84 / 5.30 / 10; 23.8 m | 3.07 / 5.86 / 10; 25.4 m | 1.54 / 5.52 / 10; 13.1 m | 0.76 / 5.33 / 10; 6.3 m |
| 30 s | 2.12 / 6.47 / 10; 15.6 m | 1.73 / 6.86 / 10; 12.9 m | 3.56 / 5.80 / 10; 26.9 m | 1.52 / 5.73 / 10; 11.8 m | 1.86 / 5.48 / 10; 14.2 m |
| 60 s (10) | 2.99 / 5.80 / 10; 18.9 m | 2.92 / 6.16 / 10; 18.0 m | 2.64 / 4.91 / 10; 17.0 m | 1.69 / 6.43 / 10; 11.3 m | 1.79 / 3.12 / 10; 10.7 m |
| in-turn | 3.18 / 7.67 / 10; 13.8 m | 2.73 / 8.09 / 10; 12.1 m | 3.50 / 7.08 / 10; 15.2 m | 2.12 / 7.37 / 10; 9.6 m | 1.58 / 3.67 / 10; 6.9 m |
recovery (median): cor: at return 4.4 m, +3 s 3.9 m, max step 0.75 m; cor_k1: at return 4.4 m, +3 s 4.3 m, max step 0.88 m; cor_lm: at return 4.4 m, +3 s 3.9 m, max step 0.75 m; gen: at return 4.6 m, +3 s 5.4 m, max step 0.43 m; gen_k1: at return 3.3 m, +3 s 3.3 m, max step 0.44 m
k_end at 30 s (median): gen 1.028, cor 1.039

The route-2-only model measures **better drift** in the engine on route 2 than the joint model: at the 30 s cut corridor k fixed 1.52 % / 5.73 % against 2.33 % / 6.26 %, general 1.73 / 6.86 against 2.80 / 5.89, and 12–13 m against 17–21 m after the stop, although its speed MAE is worse (0.172 vs 0.164 m/s) and its bias is +0.016 m/s (the joint model under-reads route 2 by 0.011 m/s and over 800 m that 0.3 % scale difference is 2–3 m). The two were not trained alike (10-fold leave-one-run-out with 9 route-2 runs vs 5-fold by pair with 8 route-2 + 16 route-1 runs), and the brief selects by leave-one-run-out drift at the 30 s cut, so the like-for-like run — the joint training set under leave-one-run-out on the route-2 runs (`--tag route1+route2 --split loro --test_tag route2`) — is reported next before the deployment choice is called final.

### Like for like on the demo road: joint training set vs route-2-only, both leave-one-run-out on the 10 route-2 runs (`cnn_r100_w256_joint_r2loro`: train on 20 route-1 + 9 route-2 runs, test the held-out route-2 run)

Speed: joint set MAE 0.166 / 0.294 m/s, bias −0.026; route-2-only 0.172 / 0.316, bias +0.016 (the joint set under-reads route 2 by 0.7 %, the route-2-only model over-reads by 0.4 %). Engine on route 2 with the joint-set LORO speeds (`filter_cnn_r100_w256_joint_r2loro_route2`):

| Cut | plain integration | general, k fixed | general, k est. | corridor, k fixed | corridor, k est. |
|---|---|---|---|---|---|
| 10 s | 3.56 / 5.38 / 10; 29.8 m | 3.84 / 5.37 / 10; 32.2 m | 2.89 / 8.48 / 10; 24.1 m | 2.55 / 7.30 / 10; 21.5 m | 1.88 / 10.76 / 9; 15.8 m |
| 30 s | 2.45 / 6.07 / 10; 18.8 m | 2.27 / 6.29 / 10; 17.9 m | 3.80 / 6.12 / 10; 29.6 m | 2.50 / 7.95 / 10; 19.0 m | 2.00 / 7.69 / 10; 14.8 m |
| 60 s (10) | 2.54 / 5.28 / 10; 16.4 m | 2.67 / 5.49 / 10; 17.6 m | 3.84 / 7.41 / 10; 23.0 m | 2.84 / 7.74 / 10; 18.0 m | 2.04 / 3.52 / 10; 13.3 m |
| in-turn | 2.09 / 7.43 / 10; 8.8 m | 3.23 / 7.50 / 10; 14.1 m | 4.27 / 6.78 / 10; 19.3 m | 3.49 / 8.30 / 10; 15.6 m | 1.76 / 5.43 / 10; 8.2 m |
recovery (median): cor: at return 3.2 m, +3 s 2.9 m, max step 0.75 m; cor_k1: at return 6.5 m, +3 s 5.9 m, max step 0.81 m; cor_lm: at return 3.2 m, +3 s 2.9 m, max step 0.75 m; gen: at return 5.9 m, +3 s 6.1 m, max step 0.44 m; gen_k1: at return 3.4 m, +3 s 3.9 m, max step 0.44 m
k_end at 30 s (median): gen 1.028, cor 1.040

Route-2-only LORO on the same runs (table above): corridor k fixed **1.52 / 5.73 / 10** against the joint set's 2.50 / 7.95 / 10 at the 30 s cut, general 1.73 / 6.86 against 2.27 / 6.29, after the stop 12–13 m against 18–19 m. Per run at the 30 s cut the joint set is better on 4 of 10 (corridor) and 5 of 10 (general); the 1 % median gap is inside the seed spread measured on route 1 (3.1–5.0 %), so it is a measured tendency, not a proven ranking. What is robust: the joint model is the better speed estimator on both roads and the better model on route 1 (2.58 / 6.82 general, and the route-2-only model transferred to route 1 gives 2.50 / 8.08); the route-2-only model integrates 800 m of the demo road with the lower along-track residual because its bias on that road is smaller.

**The shipped instance must pass an acceptance check.** The leave-one-run-out tables average ten trained instances; the file that ships is one draw, and the per-run biases show ±0.05 m/s of seed-to-seed spread. Measured on the all-runs route-2 models against their own training runs: seed 0 bias −0.073 m/s (−2 %; its run-4 conformance replay drifts 4.39 % where the joint instance gives 2.62 %), seed 1 −0.012 m/s, seed 2 +0.024 m/s; the joint instance +0.007 on route 2 and +0.025 on route 1. Rule from here on: a deployed instance's median bias on its training runs must be within ±0.02 m/s on every road it serves, else retrain with another seed (`--seed`). Seed 1 passes and is the corridor instance.

**Deployment rule.** One general-purpose model: `cnn_r100_w256_joint_deploy` (route 1, any road without its own model, and the general mode). Per-corridor override: the route-2 corridor loads `cnn_r100_w256_r2deploy_s1` (route-2-only, all 10 runs, seed 1; exported and verified) for the demo. Both files are 240 KB, same architecture and input contract, so the app selects by corridor id from its config; the harness numbers for the demo configuration are the route-2-only LORO table (corridor 1.52 % / 5.73 % / 10 of 10 at the 30 s cut, 1.69 / 6.43 at 60 s, 2.12 / 7.37 in the turn), and on the run-4 conformance replay the seed-1 instance gives 2.81 % (22.1 m over 789 m) against the joint instance's 2.62 %: on this road the two are equivalent within the seed noise, and the override rests on the leave-one-run-out tendency plus the smaller along-track bias.

### What to demo, what remains (routes 1 and 2 closed)

Demo: **route 2, corridor mode, k off, the route-2 corridor model (`cnn_r100_w256_r2deploy_s1`, joint model everywhere else)**, GNSS cut ≥ 30 s after motion start on the first straight, outage 400–500 m through the 120° turn (1.5 % median → ~7 m at the end), stand quiet for the full 15 s (the logger's stand check must pass; a moved stand needs 60 s of GNSS first). Route 1 stays as the short-corridor demo (general mode 2.6 % median over 200 m). The map matcher remains a display output.

Remaining for the team: (1) the nav app — Kotlin port of spec v2, phone latency of the 240 KB model inside the APK, and the conformance run against the two reference CSVs (max |Δposition| < 1 m); (2) rides with mid-ride stops so stop latency is scored away from the end-of-ride stop (0.7 s after rolling ends today, measured only there); (3) a rider field set per rider in the logger so a rider-held-out test becomes possible (every session so far says `rider_1`); (4) more riding data remains the highest-value input for the speed model (route 2 improved route 1's MAE from 0.195 to 0.179 m/s).
