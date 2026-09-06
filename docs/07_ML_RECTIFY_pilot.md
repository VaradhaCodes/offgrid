# How the ML speed model rectifies IMU dead reckoning — pilot evidence (two 70 s rides, 5 Sep 2026)

Script: `engine/ml_rectify_demo.py <train_processed> <test_processed> --model gbr|ridge`. Per-timestamp table: `ml_timeline_10hz_<model>.csv` in the test folder (10 Hz: GNSS truth, gyro heading + error, IMU-accel speed + error, last-speed + error, ML speed raw/filtered + error, positions and position errors of all three, and the ML-vs-IMU correction size).

Setup: proxy speed model = gradient boosting (or ridge) on 2 s windows of phone-frame IMU features (vibration RMS, five band energies of |a|, spectral peaks, gyro RMS), trained on ONE run, tested on the OTHER run (opposite direction, same road). Stop rule: vibration RMS < 0.6 m/s² and gyro RMS < 0.06 rad/s → speed 0. Filter proxy: 1 s exponential smoothing + 3 m/s² rate limit. GNSS cut 10 s after motion starts; heading from the gyro initialised on the 10 s before the cut; position at the cut from GNSS.

| Test run (outage) | Speed source after the cut | Speed MAE | Endpoint error | Drift % | Error after the bike stops |
|---|---|---:|---:|---:|---:|
| run3, 168 m / 58 s | IMU accelerometer integrated | 39 m/s | 1486 m | 887 % | 2063 m |
| run3 | last GNSS speed held | 0.24 m/s | 11.1 m | 6.6 % | 57 m |
| run3 | **ML (gbr, trained on run2)** | 0.24 m/s | **10.3 m** | **6.2 %** | **10.5 m** |
| run2, 172 m / 60 s | IMU accelerometer integrated | 12 m/s | 744 m | 433 % | 1088 m |
| run2 | last GNSS speed held | 0.30 m/s | 6.9 m | 4.0 % | 51 m |
| run2 | **ML (gbr, trained on run3)** | 0.16 m/s | **1.1 m** | **0.6 %** | **0.8 m** |

Heading error during the outages: −0.9° and +0.8° mean (gyro, bias from the stationary window, initialised over 10 s). The accelerometer is never used for speed.

Findings
1. The dominant feature in both directions is the 5–12 Hz vibration band energy of |a|: road/wheel vibration scales with speed on this surface. Wheel line and gyro stats come next. A model trained on 70 s of one ride already reads speed to ~0.2 m/s on the other ride.
2. The stop rule matters as much as the model. An earlier data-driven threshold fired on smooth stretches and zeroed the speed (MAE 0.57 m/s, 24 m endpoint). The physical joint rule (vibration AND gyro both quiet) has zero false hits while moving in both runs.
3. Last-speed-hold looks competitive on a steady 3 m/s ride but fails at every speed change: at the end of each ride its error keeps growing (57 m and 51 m) while ML freezes at the true stop. The long corridor has an acceleration, a 90° turn with slowdown, and a stop: last-speed-hold will not survive it.
4. Residual ML error on run3 is a −0.13 m/s (4 %) bias: run2 was ridden slightly differently. More runs at slow/normal/brisk pace will remove it. This is the reason for the run-variation list in the collection plan.
5. Numbers below ~4 m are inside the GNSS reference accuracy and should not be over-read.

What the real engine adds on top of this proxy: a CNN/GRU on the raw vehicle-frame window instead of hand features, an uncertainty output that sets the filter gain, the corridor/map constraint on position, and heading maintenance across the cut from the fusion filter state.
