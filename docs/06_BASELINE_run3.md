# Classical dead-reckoning baselines on run3 (20260904_234839, 70 s ride, 197 m, GNSS withheld for the whole ride)

Script: `engine/baseline_dr.py` on `data/processed/<session>/`. Outputs: baseline_dr.png, baseline_dr_errors.csv, baseline_dr_summary.json.

| Variant | What it uses | Endpoint error | RMSE | Error at 10 s / 30 s / 60 s | Path length error | Drift % of distance |
|---|---|---:|---:|---|---:|---:|
| A pure INS | accel + gyro double integration, tilt from gravity, gyro bias from calib, yaw from first 8 s | 2889 m | 1105 m | 4.8 / 236 / 1869 m | +1411 % | 1469 % |
| B INS forward-only | same, but only forward specific force integrated, lateral/vertical velocity = 0 | 785 m | 446 m | 4.9 / 144 / 784 m | +481 % | 399 % |
| C gyro heading + last speed held | heading from gyro; speed frozen at cut (5 s after motion) | 26 m | 11 m | 2.8 / 8.2 / 16 m | +1.1 % | 13.3 % |
| D gyro heading + true speed | heading from gyro; GNSS Doppler speed (speed cheat) | 15 m | 9.5 m | 2.7 / 7.2 / 14.7 m | −1.1 % | 7.7 % |
| D with the 5.6° initial-heading offset removed | same, heading start aligned properly | 1.2 m | 2.7 m | max 4.0 m | | 0.6 % |

Heading: gyro-integrated heading vs GNSS bearing while moving: constant offset −5.6° (from aligning on only 3 s of low-speed bearing), residual drift −2.8°/min, residual scatter 2.6° (mostly GNSS bearing lag through the turn). The LSM6DSO gyro, bias-corrected from the 15 s stationary window, is good enough for a 70 s outage on its own.
Speed: integrating the accelerometer gives 8 m/s after 15 s against a true 3 m/s (bias + residual tilt of the taped mount); it is not a usable speed source even with the forward-only constraint.

## What this says about the engine design
1. Speed is the whole problem. A perfect speed with gyro heading gives 0.6 % drift; last-speed-hold gives 13 %; the accelerometer gives hundreds of percent. The learned speed model (or the explainable wheel-line tracker) is the core deliverable, exactly as planned.
2. Initial heading at the moment of the cut must come from the GNSS+INS filter using the last 10–15 s of good bearing, not from 3 s. That alone is the difference between 15 m and 1 m here.
3. The magnetometer is not needed and not usable on this frame.
4. On this 200 m road the 10 % target is met by C already; on the 812 m corridor it will not be. Do not read C as sufficient.
