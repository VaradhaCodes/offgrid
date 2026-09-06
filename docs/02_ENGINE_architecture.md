# Engine architecture (prototype) — offline Python first, then Kotlin port

Design rule: one engine, two runtimes. `engine/` in Python is the truth (evaluation, plots, IO-VNBD, "edge deployable engine"). The Kotlin port only re-implements the small pieces needed for the live phone demo and must produce the same output on the same recorded run (replay test).

## Data flow
```
raw session (CSV, t_ns)  ──►  loader  ──►  100 Hz uniform IMU grid (interp), GNSS list, events
        │
        ▼
 stationary detector (acc/gyr variance, 1 s windows) ──► gyro bias, gravity vector, ZUPT flags
        │
        ▼
 alignment (phone→bicycle): tilt from gravity; yaw from PCA of horizontal accel during
 the first straight acceleration, sign from GNSS speed increase ──► R_pb (3×3), reported on screen
        │
        ▼
 vehicle-frame IMU (fwd, left, up)  ──►  speed model (window 2–4 s) ──► v_hat, sigma_v (10 Hz)
        │                                                       │
        ▼                                                       ▼
 ESKF / corridor filter  ◄── GNSS gate (pos, speed, bearing; blocked during outage)
        │                ◄── NHC, ZUPT, road-bearing prior, map-matched cross-track
        ▼
 10 Hz state (lat, lon, v, heading, mode, uncertainty)  ──►  UI marker / metrics
```

## Modules
1. **loader.py** — reads a session folder, checks units, achieved rates, gaps, clipping, GNSS quality flags. Emits a QA report per run (this is what tells you whether Friday's data is usable).
2. **stationary.py** — variance thresholds on |a| and |ω| over 1 s; produces ZUPT intervals and per-run gyro bias (median during stationary), accelerometer gravity vector.
3. **align.py** — R_pb from gravity (roll, pitch) + forward-axis yaw. Validation: after alignment, gyro z should match GNSS-bearing rate of change in sign and magnitude on turns, and forward accel should be positive during the first speed-up. Reports pitch/roll/yaw in degrees.
4. **speed_model/** — features: 6-ch vehicle-frame IMU at 100 Hz, window 256 samples (2.56 s), stride 10 (10 Hz outputs). Model A: 1-D CNN (3 conv layers, ~20–40k params) → (v, log σ²) with Gaussian NLL loss. Model B (explainable backup): STFT of vertical+lateral accel, wheel-line tracker → v = f_wheel × circumference; plus vibration-energy regression. Labels: GNSS speed where speed_acc < 1 m/s and accuracy < 10 m, linearly interpolated to 10 Hz, masked ±1 s around gaps. Train on train runs only; normalisation from train runs only.
5. **eskf.py** — state [pN, pE, v_fwd, ψ, b_gz, k_v] (6) or the full 15-state (p, v, q, b_a, b_g) if time permits. Propagation from vehicle-frame gyro z (heading) and forward accel (velocity prior). Measurements: speed model (σ_v from model), NHC (v_up = 0, σ 0.2 m/s; v_lat = 0 with a LOOSE σ 0.8 m/s because pedalling and lean break the lateral constraint on a bicycle — arXiv 2510.17604), ZUPT (v = 0, σ 0.05), GNSS position (σ = reported accuracy, gated: accuracy < 20 m, not during outage), GNSS speed/bearing (bearing only when speed > 1.5 m/s), road bearing (σ 10°, only when confidently matched), cross-track = 0 to matched edge (σ 3 m).
6. **corridor.py** — the 1-D fallback and the demo's strongest mode: state s (arc-length along the route polyline) + v + k_v. s += v·dt; position = polyline(s). Turn landmarks: when integrated heading change over 3 s exceeds 40°, snap s to the nearest bend of matching sign within ±40 m. GNSS (when allowed) measures s by projection.
7. **mapmatch.py** — general case: HMM (Newson–Krumm) over an OSM/campus graph with emission = Gaussian on distance to edge, transition = route-distance vs straight-line ratio; Viterbi with a 3 s lag for the live UI (small latency is acceptable and can be disclosed) or greedy nearest-edge with heading gating for zero-lag.
8. **gate.py** — GNSS deficit handler. Modes: GNSS_INS, INERTIAL, RECOVERING, and the SIMULATED flag. Real-outage trigger: no fix for > 1.5 s OR accuracy > 30 m OR sats used < 4 OR mean C/N0 of used sats < 22 dB-Hz. Recovery: on first good fix after outage, do NOT jump; feed the fix with inflated σ for 3 s then normal σ (the marker glides). Never rewrite the already-displayed outage trajectory.
9. **evaluate.py** — per run and per outage window: endpoint error, drift % of outage distance, 2-D RMSE vs withheld GNSS, max error, along/cross-track error, recovery jump size, stop overshoot. Baselines: last-position hold, constant-velocity, pure INS, ESKF without model, ESKF with model, corridor. Plots: trajectory on map, error vs time, speed model vs GNSS speed.

## Training recipe (Saturday morning, ~2 h)
- Split by run ID (whole rides). Fit scaler on train. Train CNN 30–60 epochs on CPU (data is tiny: 12 runs × ~150 s × 10 Hz ≈ 18k windows). Early stop on validation NLL.
- Report speed MAE on validation (target < 0.4 m/s, i.e. < 10% at 15 km/h).
- Export: TorchScript → ONNX → TFLite (or train in tf.keras directly to avoid conversion pain). Input [1, 256, 6] float32, output [1, 2].

## Kotlin port (Saturday afternoon)
- `EngineCore.kt`: ring buffer of vehicle-frame IMU, stationary detector, alignment (from a 15 s calibration + first acceleration, same math), corridor filter, small ESKF, gate state machine, 10 Hz ticker.
- Speed model via LiteRT/TFLite interpreter (single thread, ~1 ms per window on S23 Ultra).
- `NavScreen`: MapLibre (offline style with the corridor GeoJSON drawn, or a plain canvas of the corridor if MapLibre integration eats time), marker updated at 10 Hz, mode badge (GNSS+INS / INERTIAL / RECOVERING / SIMULATED), speed, heading, alignment angles, GNSS age, error estimate.
- Replay test: feed a recorded session through the Kotlin engine and diff against Python output (max |Δpos| < 0.5 m).

## IO-VNBD track (same engine, external IMU)
- Pick 2–3 sequences with wheel-speed/odometer reference. Run loader → align → speed model (retrained on IO-VNBD car data; the bicycle model does not transfer) → ESKF with simulated outages (mask GNSS 30–120 s). Output: trajectory plots with outage windows shaded + drift table. This is the mandatory screening artefact and the "edge engine on external IMU" evidence.
