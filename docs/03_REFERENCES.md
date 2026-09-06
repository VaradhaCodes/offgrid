# References — verified links only (fetched Fri 4 Sep 2026)

Sections: A. Datasets · B. Learned inertial odometry / speed nets · C. Classical fusion engines · D. Map matching / OSM · E. On-device · F. Alignment · G. 1-D corridor DR · H. Android logging specifics · I. Stop-gap logger apps


## A. Datasets (newer than IO-VNBD, and what IO-VNBD really is)

### IO-VNBD (the judged benchmark) — verified from repo + paper
- Repo: https://github.com/onyekpeu/IO-VNBD — all zips/CSVs are **Git LFS pointers**; you must `git lfs install && git lfs clone`, a plain zip download gives 132-byte stubs. No LICENSE file. Paper: https://arxiv.org/abs/2005.01701
- Two families: **`V-` files** = Ford Fiesta CAN via Racelogic VBOX HD2 at a true 10 Hz (VBOX GPS lat/lon/velocity/heading, 4 wheel speeds, yaw rate, indicated speed, steering, brake, pedal; 29 columns). **`S-` files** = phone via AndroSensor app (accel, gravity, gyro, mag, orientation, GPS lat/lon/alt/speed/accuracy; 24 columns). Phones: Huawei P20 Pro (most), Moto G7 Power, BlackBerry Priv.
- Phone rows are 10 Hz but **phone GPS is 1 Hz held for ~10 rows** (stepwise labels). ~40 h / 1,300 km V-, ~58 h / 4,400 km S-, UK/France/Nigeria; ~1-min stationary bias sequences included.
- For training labels use the `V-` VBOX 10 Hz velocity or wheel speeds, not the stepwise `S-` GPS speed.

### Ranked table
| # | Dataset (year) | Link | Sensors / ground truth | Vehicle, size, licence | Speed-from-IMU pretrain | Bicycle transfer |
|---|---|---|---|---|---|---|
| 1 | **Google Smartphone Decimeter Challenge 2022/2023** | https://www.kaggle.com/competitions/smartphone-decimeter-2023/data · https://www.kaggle.com/competitions/smartphone-decimeter-2022/data · overview https://www.ion.org/gnss/upload/Smartphone-Decimeter-Challenge-2023-2024.pdf · mirror https://ieee-dataport.org/documents/google-smartphone-decimeter-challenge-2023-2024 (2.7 GB train.zip) | `device_imu.csv` (UncalAccel/UncalGyro/UncalMag + elapsedRealtimeNanos), raw GNSS, **NovAtel SPAN ground-truth position + velocity** at 1 Hz epochs | Car, dash-mounted; 196 drives (156 train), SF Bay + LA; phones incl. Pixel 4–7, Xiaomi Mi8, **Samsung S20/S21/S22/S23 Ultra** | **Best**: newest, phone-native, SPAN velocity labels, same Samsung family as our phone | Medium (car dynamics) |
| 2 | **comma2k19** (2018) | https://github.com/commaai/comma2k19 · https://arxiv.org/abs/1812.05752 | comma EON (phone-class): LSM6DS3 IMU 100 Hz, mag 10 Hz, u-blox raw GNSS 10 Hz, **CAN wheel speeds**, Laika poses | RAV4 + Civic, 33 h / 2,019 × 1-min, I-280 highway only, processed chunks ~10 GB, **MIT** | Very good (CAN labels at 100 Hz IMU) | Low (highway) |
| 3 | nuScenes CAN-bus expansion (2020) | https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/can_bus/README.md | IMU 100 Hz, pose 50 Hz, wheel speeds 100 Hz | Renault Zoe, 1,000 × 20 s, CC BY-NC-SA, tiny CAN files | Good for urban stop-go | Low |
| 4 | KAIST Complex Urban (2019) | https://sites.google.com/view/complex-urban-dataset | Xsens MTi-300 100 Hz, FOG, wheel encoders 100 Hz, VRS-GPS | Prius, large, CC BY-NC-SA | Good but not phone | Low |
| 5 | UrbanNav (HK PolyU, 2021) | https://github.com/IPNL-POLYU/UrbanNavDataset | Xsens 400 Hz, GNSS 1–10 Hz, SPAN GT, no wheel speed | HK + Tokyo, rosbags 17–147 GB | Fair; huge | Low |
| 6 | ANSFL Autonomous Platforms Inertial Dataset (2022) | https://github.com/ansfl/Navigation-Data-Project | Jimny car segment, Inertial Labs GT, reportedly a Huawei P40 log | 805 min mixed platforms, CC BY 4.0 | Fair | Low |
| 7 | KITTI raw + AI-IMU baseline | https://www.cvlibs.net/datasets/kitti/raw_data.php · https://github.com/mbrossar/ai-imu-dr | OXTS GPS/IMU 10 Hz | Car; ready IMU-only IEKF baseline, MIT | Baseline code | — |
| 8 | i2Nav awesome-gins-datasets (2022) | https://github.com/i2Nav-WHU/awesome-gins-datasets | ICM20602/ADIS16465 + RTK | Car, 1,617 s | Low | — |
| 9 | SimRa (2019–25) | https://github.com/simra-project/dataset | Phone accel 4–10 Hz, gyro ≤ 4 Hz, GPS every 3 s | **Bicycle**, > 65k crowdsourced rides, CC BY-NC | Useless for DR (too slow) | Placement classifier only |
| 10 | M2DGR (2021) | https://github.com/SJTU-ViSYS/M2DGR | 100–200 Hz IMUs, RTK/Leica | Ground robot, ~1 TB | Low | Low |
| 11 | OxIOD / RoNIN / RIDI / TLIO | https://arxiv.org/abs/1809.07491 · https://ronin.cs.sfu.ca/ · https://github.com/CathIAS/TLIO | Phone/headset IMU 100–200 Hz, Vicon/VIO GT | **Pedestrian** | Wrong domain; borrow code only | No |

### Bicycle / two-wheeler findings (no public dataset with good ground truth exists)
- Wuhan University, **Learned Inertial Odometry for Cycling (mixture-of-experts)**, Oct 2025: handlebar-mounted phone, 25 h, 8 riders, GNSS/INS pose-graph ground truth, 0.33 m/s speed error, RTE 2.58 m. Data private. https://arxiv.org/abs/2510.17604 — the closest published work to our prototype; cite it, and note their finding that pedalling harmonics and lean-in-turns break the *lateral* non-holonomic constraint (keep the vertical one, loosen the lateral one).
- DiDi/BJTU shared-bike **MTIMNet + pseudo-wheel-speed**, May 2026, < 0.5 m/s at P95: https://arxiv.org/abs/2605.07412
- Melbourne cycling set (100 Hz IMU, 1 Hz GPS, 7,006 km) not released: https://arxiv.org/abs/2410.19194 · AuRa cargo-bike is images only: https://github.com/ovgu-mtk/aura_dataset/ · DCU e-mobility sets are GPS-only: https://github.com/SFIEssential/DualEMobilityData-datasets · IIT-Jodhpur phone IMU+GPS multi-mode set is IEEE-DataPort subscription-only: https://ieee-dataport.org/documents/smartphone-imu-and-gps-dataset
- Car speed-from-IMU papers with private data, for numbers to quote: Freydin & Or 2022 (LSTM, RMSE 0.9 m/s) https://arxiv.org/abs/2205.07883 · AVNet 2025 (CNN-GRU + IEKF, 0.4% drift) https://satellite-navigation.springeropen.com/articles/10.1186/s43020-025-00168-7

### So-what for us
1. Download only three things: IO-VNBD via git-lfs (judged benchmark), GSDC-2023 train.zip (needs Kaggle login), one comma2k19 processed chunk. Skip the rosbag datasets.
2. Optional pretraining chain if time allows: comma2k19 (100 Hz, CAN speed) → IO-VNBD `V-` (wheel speed) → fine-tune on GSDC Samsung S22/S23-Ultra traces (same IMU family, SPAN velocity labels). For the 40-hour prototype the bicycle model is trained from our own rides; the pretraining chain is the national-round story.
3. Benchmark IO-VNBD at 10 Hz with ≥ 1 s windows; make a properly anti-aliased 10 Hz branch of our 100+ Hz phone data so the same code path runs both.
4. A ~₹1,000 BLE bicycle wheel-speed sensor would give a true speed label independent of GNSS. Only if one can be bought Friday; otherwise GNSS Doppler speed is the label (that is what DeepOdo and DVSE did).
5. Literature targets to quote: ≤ 0.5 m/s speed error and ~1% drift for cars; 0.33 m/s and RTE ≈ 2.6 m for bicycles.

---

## B. Learned inertial odometry, IMU speed nets, NHC/ZUPT

| Name | Link | Year | Stars/Lang/Licence | What | Use in 40 h |
|---|---|---|---|---|---|
| AI-IMU Dead-Reckoning (Brossard) | https://github.com/mbrossar/ai-imu-dr · https://arxiv.org/abs/1904.06064 | 2019 / T-IV 2020 | 1.0k / Python / MIT | Invariant EKF for wheeled vehicle; CNN adapts NHC/ZUPT noise covariances; 1.1% on KITTI | Read; borrow the IEKF + pseudo-measurement structure |
| RINS-W | https://github.com/mbrossar/RINS-W · https://arxiv.org/abs/1903.02210 | IROS 2019 | 98 / Python / MIT | RNN detects zero-velocity / no-lateral-slip events for KF | Port the learned ZUPT/NHC detector idea (bicycle stops) |
| AirIMU (SAIR lab) | https://github.com/haleqiu/AirIMU | 2023 | 168 / Python / BSD-3 | Learned IMU denoising + uncertainty | Read only; too heavy to train now |
| AirIO (SAIR lab) | https://github.com/Air-IO/Air-IO | RA-L 2025 | 254 / Python / BSD-3 | Body-frame learned IO (UAV) | Read; body-frame representation |
| TLIO (Meta) | https://github.com/CathIAS/TLIO | 2020 | 405 / Python | ResNet displacement + EKF, pedestrian | Read; NN-measurement-into-EKF pattern |
| RoNIN | https://github.com/Sachini/ronin | ICRA 2020 | 423 / Python / GPL-3 | Pedestrian neural inertial nav | Read only |
| IONet | https://arxiv.org/abs/1802.02209 | AAAI 2018 | paper | Windowed LSTM velocity regression on phone | Windowing recipe |
| CarSpeedNet (Or) | https://arxiv.org/abs/2401.07468 | 2024 | paper, no code | Accelerometer-only car speed, 178k params, 4 s window, MAE 0.72 m/s | Template for speed-net size/window |
| DVSE (Xiao et al.) | https://arxiv.org/abs/2505.18490 | 2025 | paper, no code | GNSS-supervised GRU speed net (572 KB) + learned phone-to-vehicle rotation; phones S9/P40/Reno | Best blueprint: GRU beat LSTM/TCN/Transformer; labels from phone GNSS |
| Shin, Li, Kim (Applied Sciences) | https://doi.org/10.3390/app15168824 | 2025 | paper | LSTM+attention acc+gyro, underground parking, RMSE 0.38 m/s | GNSS-denied evaluation protocol |
| DeepOdo (PolyU, IEEE TIM 2023) | https://ira.lib.polyu.edu.hk/bitstream/10397/99370/1/Wang_Novel_Deep_Odometry.pdf | 2023 | paper | CNN-GRU velocity from IMU+baro, labels from phone GNSS/INS, deployed on Android; 73% better than NHC-only | Closest to our spec; copy architecture + label strategy |
| AVNet / DMDVDR (Satellite Navigation 2025) | https://www.eurekalert.org/news-releases/1089377 (doi 10.1186/s43020-025-00168-7) | 2025 | paper | CNN+GRU attitude/velocity → invariant EKF + learned noise adapter; 0.4–0.64% drift | Cite as state of the art; same topology |
| OdoNet (Niu group) | https://arxiv.org/abs/2109.03091 | 2021 | paper | CNN pseudo-odometer speed from IMU; 68% error cut vs NHC-only | Justifies speed net as ESKF measurement |
| Wheel-INS (i2Nav) | https://github.com/i2Nav-WHU/Wheel-INS · https://arxiv.org/abs/2012.10589 | TVT 2021 | 388 / C++ / GPL-3 | ESKF DR with NHC + velocity/ZUPT measurement models | Copy NHC/ZUPT measurement equations |
| NHC observability (Li, Niu et al., ION GNSS 2012) | https://www.ion.org/publications/abstract.cfm?articleID=10362 | 2012 | paper | NHC makes MEMS GNSS/INS observable in outages | Cite for NHC |
| DL for inertial nav survey (Cohen & Klein) | https://arxiv.org/abs/2307.00014 | 2023 | paper | Survey | Citations |
| Road-vibration positioning (Or et al., TITS 2024) | https://arxiv.org/abs/2303.03942 | 2023 | paper | CNN/RF learn road-signature position, ~50 m car / 30 m e-scooter | Optional corridor bonus feature |

## C. Classical GNSS/INS fusion engines

| Name | Link | Stars/Lang/Licence | Notes | Use |
|---|---|---|---|---|
| KF-GINS | https://github.com/i2Nav-WHU/KF-GINS | 1.2k / C++ / GPL-3 | 21-state loosely coupled ESKF | Reference design; trim to 15 states |
| KF-GINS-Py | https://github.com/salmoshu/KF-GINS-Py | 13 / Python / GPL-3 | NumPy/SciPy port | Use directly for the laptop engine |
| KF-GINS-Matlab | https://github.com/i2Nav-WHU/KF-GINS-Matlab | 138 / MATLAB / GPL-3 | Official Matlab port | Read |
| OB_GINS | https://github.com/i2Nav-WHU/OB_GINS | 648 / C++ / GPL-3 | Sliding-window optimisation | Too heavy; skip |
| PSINS | https://github.com/WangShanpeng/PSINS | 38 (mirror) / MATLAB / BSD-2 | Yan Gongmin toolbox | Alignment/attitude maths |
| filterpy | https://github.com/rlabbe/filterpy | 3.9k / Python / MIT | pip KF/EKF/UKF/PF | Particle filter for the 1-D corridor mode |
| Kalman & Bayesian Filters in Python | https://github.com/rlabbe/Kalman-and-Bayesian-Filters-in-Python | 19.2k / notebooks | Tutorial | Onboarding |
| ESEKF_IMU | https://github.com/aipiano/ESEKF_IMU | 185 / Python | Clean ESKF (IMU only) | Borrow quaternion error-state code |
| LS_INS_GNSS_EKF | https://github.com/maysjeff/LS_INS_GNSS_EKF | 22 / Python+C++ / MIT | Loosely coupled ESKF | Small, MIT; good port base |
| Error-State EKF (Bozkurt) | https://github.com/enginBozkurt/Error-State-Extended-Kalman-Filter | 272 / Python | Coursera ESKF | Read |

## D. Map matching / offline OSM

| Name | Link | Stars/Lang/Licence | Notes | Offline Python? / Android? |
|---|---|---|---|---|
| fmm | https://github.com/cyang-kth/fmm · https://fmm-wiki.github.io/ | 1.0k / C++ + Python / Apache-2 | HMM (FMM/STMATCH); needs shapefile from osmnx; last release 2020 | Python bindings offline; not Android |
| LeuvenMapMatching | https://github.com/wannesm/LeuvenMapMatching · https://leuvenmapmatching.readthedocs.io/en/latest/usage/openstreetmap.html | 255 / Python / Apache-2 | HMM with non-emitting states; InMemMap from osmnx | Pure Python offline; core portable to Kotlin |
| GraphHopper map-matching | https://github.com/graphhopper/map-matching → https://github.com/graphhopper/graphhopper | archived / 6.7k / Java / Apache-2 | Newson–Krumm HMM in GraphHopper core | Java; Android offline not officially supported |
| Valhalla (Meili) | https://github.com/valhalla/valhalla · https://valhalla.github.io/valhalla/api/map-matching/ | 6.2k / C++ / MIT | trace_route / trace_attributes, HMM, local tiles | Runs on Android via NDK; heavy for 40 h |
| OSRM match | https://github.com/Project-OSRM/osrm-backend | 8k / C++ / BSD-2 | Match service | Server only |
| OSMnx | https://github.com/gboeing/osmnx · https://osmnx.readthedocs.io/en/stable/user-reference.html | 5.8k / Python / MIT | graph_from_xml / save_graphml / project_graph | Pull once online, ship GraphML |
| pyrosm | https://github.com/HTenkanen/pyrosm | 436 / Python / MIT | .osm.pbf → GeoDataFrame / networkx | Offline extract |
| Newson & Krumm 2009 | https://www.microsoft.com/en-us/research/publication/hidden-markov-map-matching-noise-sparseness/ | paper | Canonical HMM map matching | Cite; own Viterbi ≈ 150 lines |

## E. On-device deployment

| Name | Link | Notes | Use |
|---|---|---|---|
| LiteRT (ex-TFLite) | https://developers.google.com/edge/litert · https://developers.google.com/edge/litert/models/convert/rnn | Keras LSTM converts to a fused op (stateless only); GRU not documented | 1-D CNN (+LSTM) if going LiteRT |
| ONNX Runtime Mobile | https://onnxruntime.ai/docs/tutorials/mobile/ | onnxruntime-android, NNAPI/XNNPACK, int8 | Use if keeping a GRU (PyTorch → ONNX) |
| MapLibre Native | https://github.com/maplibre/maplibre-native · OfflineManager https://maplibre.org/maplibre-native/android/api/-map-libre%20-native%20-android/org.maplibre.android.offline/-offline-manager/index.html | 2.2k, BSD-2, `org.maplibre.gl:android-sdk` | Offline map display |
| Dead-Reckoning-Pro | https://github.com/SaturnXIII/Dead-Reckoning-Pro | 21, Java, no licence; PDR + OSMDroid + foreground service | Sensor-service / OSMDroid scaffolding |
| DeadReckoning (nisargnp) | https://github.com/nisargnp/DeadReckoning | 265, Java, no licence | Sensor plumbing reference |
| GnssLogger (Google) | https://github.com/google/gps-measurement-tools | 841, Apache-2 | Raw GNSS logging reference |

## F. Phone-to-vehicle alignment

| Source | Link | Method |
|---|---|---|
| Hernández Sánchez et al., Sensors 2018 | https://pmc.ncbi.nlm.nih.gov/articles/PMC6111255/ | Gravity mean → roll/pitch; project accel to horizontal; PCA 1st/2nd components = longitudinal/lateral; sign fix |
| DVSE 2025 | https://arxiv.org/html/2505.18490v1 | Learned rotation net; prior work (VeTorch, DeepTrack) uses PCA |
| Opportunistic calibration (patent) | https://patents.google.com/patent/US10876859B2/en | Gyro stability gate → gravity roll/pitch → yaw from GNSS course vs heading |

## G. 1-D route-constrained dead reckoning (cite these for the corridor mode)

- von Einem et al. 2023, Path-Constrained State Estimation for Rail Vehicles (1-D along-track state, multi-hypothesis): https://arxiv.org/abs/2308.12082
- Löffler & Bengtsson, FUSION 2024, IMU + track-map particle filter, < 10 m over 30 s outages: https://arxiv.org/abs/2406.02339
- Heirich 2016, J. Sensors, RBPF topological along-track position with low-cost IMU: doi 10.1155/2016/2672640
- Toledo-Moreo et al., JSTSP 2009 (curvilinear abscissa, PF): https://www.um.es/gsit/research_lines/its/files/WebEdition.pdf ; TITS 2010 follow-up doi 10.1109/TITS.2009.2031625
- Fouque, Bonnifait, Bétaille, PLANS 2008, map heading as KF observation: doi 10.1109/PLANS.2008.4570082
- Kašpar et al. 2025, tram IEKF with track projection: https://arxiv.org/abs/2506.08032

## H. Android logging specifics (S23 Ultra, Android 14/15) — verified against developer.android.com / AOSP

- **Silicon** (iFixit chip ID): STMicro LSM6DSO accel+gyro, AKM AK09918C magnetometer, STMicro LPS22HH barometer, Snapdragon 8 Gen 2 modem GNSS with L1+L5 (GPS/Galileo/BeiDou/QZSS dual-frequency, per Notebookcheck). Raw GnssMeasurement is mandatory on Android 10+; carrier phase (ADR) is probably UNSUPPORTED on Snapdragon Samsungs (GPSTest maintainer report for S21 Ultra) — check `getAccumulatedDeltaRangeState() & ADR_STATE_VALID` on device.
- **200 Hz cap**: apps targeting SDK ≥ 31 get accel/gyro/mag capped at 200 Hz unless the manifest declares `android.permission.HIGH_SAMPLING_RATE_SENSORS` (normal permission, no prompt). Gotcha: if the system-wide microphone toggle is OFF, sensors are rate-limited regardless. Ceiling with the permission = `Sensor.minDelay` from the HAL; S23 Ultra's actual maximum is unverified, treat 200 Hz as the floor and measure.
- **Registration**: `registerListener(listener, sensor, samplingPeriodUs = 2000, maxReportLatencyUs = 0, handler)` on a dedicated HandlerThread. Pass an explicit period, not SENSOR_DELAY_FASTEST, so the request is known. `SensorEvent.timestamp` is the physical event time on the `SystemClock.elapsedRealtimeNanos()` base, batching never alters it.
- **Screen-off / suspend**: default sensors are non-wake-up; if the AP suspends, the hardware FIFO drops old events. Hold a PARTIAL_WAKE_LOCK for the whole session AND keep the screen on.
- **SensorDirectChannel** (RATE_VERY_FAST nominal 800 Hz) exists but needs shared-memory ring parsing; not worth it here.
- **Foreground service**: `foregroundServiceType="location"`, permissions FOREGROUND_SERVICE + FOREGROUND_SERVICE_LOCATION + ACCESS_FINE_LOCATION + POST_NOTIFICATIONS + WAKE_LOCK; start from a visible Activity with `startForegroundService`, then `ServiceCompat.startForeground(..., FOREGROUND_SERVICE_TYPE_LOCATION)`. Missing type → MissingForegroundServiceTypeException.
- **Samsung**: One UI 6+ pledges correct FGS behaviour, but set Settings → Apps → [app] → Battery → Unrestricted, add to "Never sleeping apps", location "Allow all the time", and request `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (dontkillmyapp.com/samsung).
- **Location**: use `LocationManager` + `GPS_PROVIDER` for the reference (satellite-only). Fused providers may mix Wi-Fi/cell. Consumer chipsets deliver fixes at 1 Hz regardless of minTime. `Location` fields: elapsedRealtimeNanos, elapsedRealtimeUncertaintyNanos, accuracy, verticalAccuracyMeters, speed/hasSpeed, speedAccuracyMetersPerSecond, bearing/hasBearing, bearingAccuracyDegrees, altitude (WGS84), mslAltitudeMeters (API 34), isMock (API 31), time (UTC ms). `Location.getElapsedRealtimeNanos()` and `SensorEvent.timestamp` share the same monotonic base (verified).
- **GnssStatus.Callback**: svid, constellationType, cn0DbHz, basebandCn0DbHz, elevation, azimuth, usedInFix, hasEphemeris/Almanac, carrierFrequencyHz (L5 ≈ 1176.45 MHz, L1 ≈ 1575.42 MHz), onFirstFix(ttff).
- **Raw**: `registerGnssMeasurementsCallback(GnssMeasurementRequest.Builder().setFullTracking(true).setIntervalMillis(0).build(), executor, cb)`; log GnssClock + per-measurement pseudorangeRate, ADR + state, cn0, carrierFreq, constellation, svid, receivedSvTimeNanos, state, multipathIndicator, AGC, codeType.
- **NMEA**: `addNmeaListener(executor, listener)`; its timestamp is Unix ms UTC from the chipset, NOT elapsedRealtime — store both and map via the once-per-file (elapsedRealtimeNanos, currentTimeMillis) pair.
- **Build**: Gradle wrapper only, no Android Studio (developer.android.com/build/building-cmdline). compileSdk 35 needs AGP ≥ 8.6 (Gradle ≥ 8.7); compileSdk 36 needs AGP ≥ 8.10 (Gradle ≥ 8.11.1). JDK 21 works. Wireless adb: Developer options → Wireless debugging → pair with code → `adb pair ip:port` → `adb connect ip:port`.

## I. Stop-gap logger apps (usable tonight, before the custom APK exists)

| App | What it records | Verdict |
|---|---|---|
| **GnssLogger** (Google, github.com/google/gps-measurement-tools, v3.1.1.3, Apache-2) | Raw GnssMeasurement + clock, Fix (provider, lat/lon/alt, speed, accuracy, bearing, speedAcc, bearingAcc, elapsedRealtimeNanos, verticalAcc, mock), Status (per-signal C/N0, az/el, usedInFix), NMEA, **UncalAccel/UncalGyro/UncalMag/OrientationDeg** keyed by utcTimeMillis + elapsedRealtimeNanos. No barometer / rotation vectors; IMU rate not configurable. | **Primary stop-gap**: same clock as our app, drop-in for the pipeline. |
| **Sensor Logger** (Kelvin Choi, com.kelvin.sensorapp, v1.64) | Accelerometer (gravity-removed), TotalAcceleration, Gyroscope, Magnetometer, Orientation, Gravity, Barometer, Location (speed, bearing, accuracies), Metadata; "raw" toggle adds uncalibrated; time = Unix ns + seconds_elapsed; background OK. No raw GNSS. Probably ≤ 200 Hz. Docs: tszheichoi.com/sensorlogger, github.com/tszheichoi/awesome-sensor-logger | Run **simultaneously** with GnssLogger if barometer/rotation vectors are wanted tonight. |
| MIMIR (github.com/agrenier-gnss/mimir, Kotlin, Apache-2, 17 stars) | Raw GNSS + uncalibrated IMU + mag + baro, 1–200 Hz, one txt log | Closest to our target design; small project, reference for code. |
| phyphox / Physics Toolbox / AndroSensor | phyphox derives GPS speed from consecutive fixes; AndroSensor unpublished 2023 | Skip. |
