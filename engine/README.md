# The engine

The reference implementation, in Python. This is the truth: everything the Android app does was measured here first, and the Kotlin port is tested against this code's output, not against its own idea of correct.

Two runtimes, one engine. Runtime code stays in plain NumPy with fixed shapes and explicit constants — no SciPy at inference — because every line of it has to be reproducible in Kotlin. That is why it is compact; it is not an effort limit.

## Modules

| | |
|---|---|
| `session.py` | Reads a raw session folder. Stream formats, event parsing, unit checks. |
| `decode_session.py` | Session folder → `data/processed/<session>/`: the native IMU table, the uniform 100 Hz track, GNSS fixes, an overview plot. |
| `qa.py` | Per-run quality control. Rates, gaps, duplicate and non-monotonic timestamps, GNSS quality, mount pitch and roll against the set median, rider motion during the stands, gyro-bias agreement between the two stands, impacts, anchor sanity, direction mislabelling. Emits flags with reasons; never drops anything silently. |
| `align.py` | Phone→vehicle rotation. Tilt from gravity during the stand, forward axis from the first straight acceleration and then from the sway axis of pedalling, ride-time re-levelling, and a moved-phone rule. |
| `heading.py` | Heading and gyro bias. Quaternion at 100 Hz, gated tilt correction, yaw from GNSS course while GNSS is healthy, and the variant sweep that settled how bias is handled. |
| `speed_model/` | `dataset.py` builds the windowed arrays, `train.py` defines and trains the CNN, `transfer.py` runs the cross-road experiments, `ensemble.py` the multi-seed ones. |
| `export/export.py` | PyTorch → ONNX and → a Keras twin → LiteRT, with a verification pass over 2,000 real windows and an op inventory. |
| `filter.py` | The error-state Kalman filter: general 2-D mode, delayed-state GNSS updates, ZUPT, non-holonomic constraints, the optional scale state, recovery inflation. |
| `corridor.py` | The 1-D corridor filter: arc length along a known polyline plus speed. The strongest mode, and the demo mode. |
| `mapmatch.py` | Newson–Krumm HMM over the campus road graph. Display output only — it never feeds back into the estimate. |
| `replay.py` | Runs a recorded session through the whole engine causally, exactly as the phone would, and produces the 10 Hz conformance references under `data/qa/replay/`. |
| `evaluate.py` | The harness. Outage cuts, drift, RMSE, heading error, stop latency, recovery jump, per-run distributions. Nothing enters the design without a measured gain here. |
| `baseline_dr.py` | The classical baselines: pure strapdown, forward-only integration, gyro heading with held speed, gyro heading with a speed oracle. |
| `ml_rectify_demo.py` | The first pilot: hand features, a gradient-boosting speed proxy, the physical stop rule. The bar the CNN had to beat. |
| `loro_cv.py` | Leave-one-run-out cross-validation with outage replay. |
| `iovnbd.py` | The same engine on IO-VNBD, an external vehicle dataset with a non-phone IMU. |

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install numpy pandas scipy matplotlib scikit-learn torch onnxruntime tensorflow
```

TensorFlow is only needed for the LiteRT export; everything else runs without it.

## Typical runs

```bash
# Quality-check a collection
.venv/bin/python engine/qa.py data/route2/sessions --tag route2

# Decode raw sessions into data/processed/
.venv/bin/python engine/decode_session.py data/route2/sessions

# Train the joint speed model, leave-one-run-out
.venv/bin/python engine/speed_model/train.py --tag route1+route2 --split loro

# Score the filter on held-out speeds
.venv/bin/python engine/evaluate.py --tag route2 --mode corridor

# Full causal replay: what the phone would have done
.venv/bin/python engine/replay.py --all --tag route2 --mode corridor

# Export the deployment model and verify it against PyTorch
.venv/bin/python engine/export/export.py cnn_r100_w256_joint_deploy
```

## The rules this code is held to

1. **One engine, always running.** GNSS is a measurement that may stop. Nothing is switched on at the outage.
2. **The accelerometer is never integrated for speed.** Speed comes from the model, heading from the gyro; the accelerometer supplies tilt and the stop rule.
3. **Causal only.** No window ever straddles the stand/ride boundary, and no future sample is ever used.
4. **Split by whole runs.** Normalisation constants come from training runs only. Locked test runs are never used for any choice.
5. **The harness decides.** Nothing enters the design without a measured gain on held-out runs, and results are reported as distributions — median, worst, count under target — never as a single best run.

The design decisions and every measurement that produced them are in [`../docs/11_ENGINE_RESULTS.md`](../docs/11_ENGINE_RESULTS.md). The portable specification is [`../docs/12_ENGINE_SPEC_for_kotlin.md`](../docs/12_ENGINE_SPEC_for_kotlin.md).
