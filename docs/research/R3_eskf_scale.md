# R3 — Loosely-coupled ESKF for bicycle DR: state, NHC/ZUPT, GNSS-bearing gyro-bias aiding, online scale factor, outage recovery, corridor filter

**Project:** SIH 2026 problem 26168 (ISRO) — AI/ML dead-reckoning engine.
**Setup assumed:** Samsung S23 Ultra wedged in bottle cage (down-tube), accel+gyro 100–400 Hz, GNSS 1 Hz when healthy, learned speed model emitting (v, sigma_v) at 10 Hz, heading from integrating gyro-z in the bike frame, **accelerometer NOT integrated for velocity**.
**All sources below were fetched on 2026-09-05.** Anything I could not fetch is marked UNVERIFIED and carries no numbers.

---

## 0. The one paper that matches our architecture almost exactly

**MoE-Based Learned Inertial Odometry for Bicycle Localization** — Hao Qiao, Yan Wang, Shuo Yang, Xiaoyao Yu, Jian Kuang, Xiaoji Niu (i2Nav / GNSS Research Center, Wuhan University). arXiv:2510.17604, v1 2025-10-20, **v2 2026-07-26**, cs.RO. Fetched: https://arxiv.org/abs/2510.17604 and PDF.
Licence: "submitted to the IEEE"; no open licence stated. No public repo or dataset found.

Why it matters: smartphone **mounted on a bicycle**, network predicts **body-frame velocity + covariance every 0.1 s**, fused in an error-state EKF whose state is exactly ours. It is the single closest published reference we have and it is from the same group as KF-GINS/Wheel-INS.

Their measurement update (their eq. 18–20) is the template for our learned-speed update:

```
h(X_t) = R_hat_t^T v_t^n = v_hat_t^b + n,   n ~ N(0, Sigma_vb)   # network-supplied covariance
H_phi   = R_hat_t^T (v_hat_t^n)_x           # skew of nav-frame velocity
H_dv    = R_hat_t^T
K_t     = P H^T (H P H^T + Sigma_vb)^-1
P_t     = (I-KH) P (I-KH)^T + K Sigma_vb K^T   # Joseph form
```

Numbers (their Table I and hyperparameter table, over a standardised outage protocol: 10 s of reference-position init, then **120 s with no position aiding**, metrics computed only over the 120 s):

| Method | ATE overall | RTE (1 min) | Paved ATE/RTE | Unpaved ATE/RTE |
|---|---|---|---|---|
| Classical NHC ESKF baseline (lever arm + installation angle in state, estimated online) | 10.82 m | 4.01 m | 8.54 / 3.36 m | 13.86 / 4.44 m |
| MoE-8-2-128 (learned velocity + cov) | 9.49 m | 2.58 m | 9.86 / 2.44 m | 8.76 / 2.86 m |

Model: 28.76 MFLOPs, 7.18 M params, velocity inference error 0.333 m/s. Dataset: >25 h cycling, 8 riders, multiple bicycles/surfaces, 70/10/20 split, ground truth from GNSS/INS pose-graph optimisation.
**Read this way:** on paved road a well-tuned NHC filter beats the network on ATE; the network wins on unpaved. Our down-tube bottle-cage mount is more rigid than their handlebar mount, so NHC should be *more* valid for us, not less. Do not drop NHC because a learned model exists — run both.

---

## 1. State vector and error-state propagation

### 1.1 Recommended state (18 error states; drop what you cannot observe)

Nominal state: `x = (q_nb or R_nb, p^n, v^n, b_g, b_a, k, psi_mis)`.
Error state (what the filter actually carries, all small):

```
dx = [ dp^n(3), dv^n(3), phi(3), db_g(3), db_a(3), dk(1), dpsi_mis(1) ]   -> 18
```

- `dp^n, dv^n` — position/velocity error in the local ENU/NED nav frame.
- `phi` — attitude error (phi-angle model). KF-GINS uses the phi-angle model explicitly; the MoE bicycle filter uses `phi = log_SO3(R R_hat^-1)`, i.e. a left-invariant error on SO(3). Use the SO(3) log form — it is what the bicycle paper validated and it is cleaner in numpy.
- `db_g, db_a` — gyro/accel biases, first-order Gauss-Markov.
- `dk` — **learned-speed scale factor error** (section 4).
- `dpsi_mis` — yaw installation angle of the phone in the bottle cage relative to the bike forward axis.

**We do NOT need gyro/accel scale-factor states (6 more).** KF-GINS carries them (21 states: dp, dv, phi, b_g, b_a, s_g, s_a) but that is for a 200 Hz navigation-grade Leador A15. Wheel-INS argued the 21-state beats the 15-state *for a rotating wheel IMU* where cross-axis coupling matters; a body-fixed phone on a bike does not have that geometry. Source: https://github.com/i2Nav-WHU/KF-GINS (README, 21-state list) and arXiv:1912.07805v3 sec. III-A.

**We DO need `dpsi_mis` and we can skip the lever arm.** Wheel-INS handles installation via an explicit `MisalignAngle` and lever arm `WheelLA` in its config, both *fixed constants measured offline* rather than filter states (values in section 5 table). The MoE bicycle NHC baseline instead augments lever arm and installation angle into the state and estimates them online. Given a bottle-cage mount, the lever arm from IMU to the bike's constraint point is ~0.3–0.5 m and mostly along the forward/down axes; the NHC lever-arm term is `omega x l`, which at a typical bike yaw rate of 0.3 rad/s and l=0.4 m contributes ~0.12 m/s of apparent lateral velocity — **not negligible against a 0.02–0.05 m/s NHC sigma**. Either measure `l` once with a tape measure and compensate it deterministically (Wheel-INS style, cheaper) or inflate the NHC lateral sigma during turns (AI-IMU style, section 2.3).

### 1.2 Propagation

Because we are not integrating the accelerometer for velocity, the propagation is a hybrid:

```
# attitude: full gyro integration in body frame
R_{k+1} = R_k * Exp( (omega_ib^b - b_g) * dt )

# velocity: driven by the learned speed model, not by INS mechanization
v^n_{k+1} = R_{k+1} * [ (1+k) * v_model , 0 , 0 ]^T          # forward-only body velocity
# (the 0,0 come from NHC being enforced structurally rather than as a measurement;
#  see section 2.4 for why you should NOT do this and should keep NHC as a measurement)

# position
p^n_{k+1} = p^n_k + 0.5*(v^n_k + v^n_{k+1})*dt               # trapezoidal, as in arXiv:2510.17604 eq.15
```

Error-state transition, continuous form, with `f^b` the specific force and `omega_in^n ~ 0` for a local-level bike over a few km:

```
d(phi)/dt   = -(omega_in^n) x phi - R_nb * db_g - R_nb * n_g
d(dv^n)/dt  =  R_nb * [ (1+k) v_model ]_x * phi  + R_nb*e1*v_model*dk + R_nb*e1*(1+k)*n_v
d(dp^n)/dt  =  dv^n
d(db_g)/dt  = -(1/T_g) db_g + w_bg
d(db_a)/dt  = -(1/T_a) db_a + w_ba
d(dk)/dt    =  w_k                                            # random walk, section 4
d(dpsi)/dt  =  w_psi                                          # near-constant
```

Discretise with `Phi = I + F*dt` (first order is fine at dt=0.0025–0.01 s) and `Q_d = Phi G Q G^T Phi^T * dt` or van Loan. KF-GINS models IMU bias *and* scale errors as first-order Gauss-Markov with a single `corrtime`; source: https://github.com/i2Nav-WHU/KF-GINS README ("IMU bias errors and scale factor errors are modeled as first-order Gauss-Markov process"), config `corrtime: 4.0 # [hr]` at https://raw.githubusercontent.com/i2Nav-WHU/KF-GINS/main/dataset/kf-gins.yaml.

Wheel-INS gives the discrete GM form explicitly (arXiv:1912.07805v3 eq. 8): `x_{k+1} = exp(-dt/T) x_k + w_k`.

---

## 2. NHC and ZUPT

### 2.1 NHC — the canonical measurement

Foundational source (cite this one, it is the paper everyone builds on): **G. Dissanayake, S. Sukkarieh, E. Nebot, H. Durrant-Whyte, "The Aiding of a Low-Cost Strapdown Inertial Measurement Unit Using Vehicle Model Constraints for Land Vehicle Applications," IEEE Trans. Robotics and Automation, 17(5):731–747, Oct 2001.** Fetched PDF: http://www-personal.acfr.usyd.edu.au/nebot/publications/gps_ins_constraints.pdf

Their statement: "motion of a wheeled vehicle on a surface is governed by two nonholonomic constraints. When the vehicle does not jump off the ground and does not slide on the ground, velocity of the vehicle in the plane perpendicular to the forward direction is zero." They explicitly model violations as additive zero-mean Gaussian noise on the two constraints, "the strength of the noise can be chosen to reflect the extent of the expected constraint violations" — i.e. NHC is a *soft* constraint, never a hard one.

Measurement equation with lever arm and installation angle, following Wheel-INS (arXiv:1912.07805v3 eq. 10–13) and AI-IMU (arXiv:1904.06064 eq. 14–15):

```
v^v = C_v_b * ( C_b_n^T v^n  +  (omega_ib^b - b_g)  x  l_b )
z   = [ v^v_lateral , v^v_vertical ]^T  -  [0, 0]^T
```

where `C_v_b` is the constant rotation from IMU/phone frame to bike frame (the installation angles — roll, pitch, yaw misalignment) and `l_b` is the lever arm from the IMU to the bike's constraint point, expressed in the body frame.

Jacobians (usable directly in numpy):
```
H_dv   = S * C_v_b * C_b_n^T
H_phi  = S * C_v_b * C_b_n^T * (v^n)_x        # sign depends on your phi convention — verify numerically
H_dbg  = -S * C_v_b * (l_b)_x
S      = [[0,1,0],[0,0,1]]                     # selects lateral and vertical rows
R_nhc  = diag(sigma_lat^2, sigma_vert^2)
```

AI-IMU makes the important theoretical point (arXiv:1904.06064 sec. II-B): the vertical component is expressed **in the car/bike frame**, so the assumption survives 3-D motion on a slope; it is not the same as assuming zero vertical velocity in the world frame. That matters on any campus route with gradient.

### 2.2 ZUPT and ZIHR

ZUPT: `z = v^n - 0`, `H_dv = I3`, applied only when the detector fires.
Detector thresholds from a 2025 paper we fetched (arXiv:2510.08880, sec. VI): "we adopt the NHC when the mean angular velocity from the gyroscope is less than 5 deg/s and the mean forward velocity from the odometer is greater than 1 m/s in one second. We also adopt the ZUPT when the mean angular velocity from gyroscope is less than 0.05 deg/s in one second."

For a bicycle, the 0.05 deg/s over 1 s gyro-quiet test is a good stationarity detector because a stopped-but-upright bike still wobbles. Add an accelerometer-variance test.

ZIHR (zero integrated heading rate): Wheel-INS notes (arXiv:1912.07805v3) that heading error "accumulates rapidly when the vehicle remains stationary for a long time" and applies ZIHR in that case — hold heading constant across a stationary interval and feed the integrated yaw drift back as a pseudo-measurement on `db_gz`. **This is our single cheapest gyro-z-bias estimator and it needs no GNSS.** Every traffic light on the route is a free bias observation.

### 2.3 Do not use a fixed NHC sigma

AI-IMU's whole contribution is that the NHC covariance must vary: their learned adapter "increases the covariances during the bend, i.e. when the gyro yaw rate is important... its associated covariance is inflated by a factor of 10^2 between t = 90 s and t = 110 s" (arXiv:1904.06064 sec. V). Cheap non-ML version we can implement in numpy:

```
sigma_lat = sigma_lat_0 * (1 + alpha * |omega_z| / omega_ref)     # alpha ~ 3-10, omega_ref ~ 0.3 rad/s
```
so that hard cornering and the associated bike lean widen the gate by roughly the order of magnitude AI-IMU's network learned.

### 2.4 Warning: do not enforce NHC structurally

If you build the velocity purely as `R * [v_model,0,0]^T`, NHC becomes vacuous (zero innovation always) and the filter loses the observability path from lateral-velocity error to attitude error, which is exactly how NHC estimates roll/pitch/heading in Dissanayake 2001. Propagate a full 3-vector `v^n` and apply NHC as a *measurement* with non-zero R.

---

## 3. Gyro-bias estimation aided by GNSS bearing (course over ground)

### 3.1 Two ways to write it; prefer the velocity form

**Form A — explicit course measurement (what the task asked for):**
```
z = wrap_pi( psi_hat - psi_gnss )        psi_gnss = atan2(v_E_gnss, v_N_gnss)
H = [ 0(1x3 dp) , 0(1x3 dv) , u_z^T , 0 , 0 , 0 , -1 ]     # u_z^T picks yaw out of phi; -1 hits dpsi_mis
R = sigma_psi^2
```
This is the form used by the 2026 tractor paper: during motion the observation vector is `Z_k = [position error ; (heading_INS - heading_GNSS)]`. Source: Hu, Chen, Wang, Meng, Fu, Ren, Li, Wang, "Adaptive Trajectory-Constrained Heading Estimation for Tractor GNSS/SINS Integrated Navigation," *Sensors* 26(2):595, 2026-01-15, DOI 10.3390/s26020595, CC BY 4.0. Fetched: https://pmc.ncbi.nlm.nih.gov/articles/PMC12845551/

**Form B — fuse the GNSS NE velocity vector directly (recommended).** This is what ArduPilot's EKF-GSF yaw estimator does: a bank of 3-state EKFs with state `(v_N, v_E, yaw)` fusing GNSS NE velocity as a direct state observation with `velObsVar = max(velAcc, 0.5 m/s)^2`, innovations compressed to 5 sigma. Source (GPL-3.0, fetched raw): https://raw.githubusercontent.com/ArduPilot/ardupilot/master/libraries/AP_NavEKF/EKFGSF_yaw.cpp, function `fuseVelData` / `correct`.
Form B needs no atan2, no angle wrapping, and **automatically gives the 1/v weighting**, which is why it is more robust.

### 3.2 Where sigma proportional to 1/v comes from (derived, not quoted)

With `v_N = v cos psi`, `v_E = v sin psi`, the Jacobian of the velocity measurement w.r.t. yaw is `[-v sin psi, v cos psi]^T`, whose norm is `v`. Fisher information in yaw is therefore `v^2 / sigma_v^2`, so

```
sigma_psi  ~=  sigma_v / v          [rad]
```

This is a derivation from the geometry, consistent with the ArduPilot code above; I did **not** find a paper that states `sigma_psi = sigma_v / v` in that form — mark it as derived. Two independent sources support the qualitative claim:
- Fossen & Fossen, "Five-State Extended Kalman Filter for Estimation of SOG, COG and Course Rate of USVs," *Sensors* 21(23):7910, 2021, DOI 10.3390/s21237910, CC BY 4.0. Fetched: https://pmc.ncbi.nlm.nih.gov/articles/PMC8659471/ — COG/SOG estimable "with great accuracy when the speed is above a certain threshold value (typically 0.5 m/s)"; at zero speed the course angle is undefined.
- Hu et al. 2026 (above) — tractor treated as stationary and GNSS heading not used below **0.2 m/s**.

**Concrete numbers for us.** With `sigma_v` = PX4's default GNSS velocity noise of **0.3 m/s** (EKF2_GPS_V_NOISE, https://raw.githubusercontent.com/PX4/PX4-Autopilot/main/src/modules/ekf2/params_gnss.yaml):
- v = 5 m/s (typical campus cycling): sigma_psi = 0.06 rad = **3.4 deg**
- v = 2 m/s: sigma_psi = 0.15 rad = **8.6 deg**
- v = 1 m/s: sigma_psi = 0.3 rad = **17 deg** — barely informative
- v = 0.5 m/s: sigma_psi = 0.6 rad = **34 deg** — useless

**Recommended gate:** use GNSS bearing only when `v > 2 m/s` (bicycle-appropriate; well above the 0.5 m/s USV threshold and the 0.2 m/s tractor threshold, and where sigma is still under 10 deg), and reject if the innovation exceeds ~3 sigma. ArduPilot only accepts a GSF yaw when its variance is below `GSF_YAW_ACCURACY_THRESHOLD_DEG = 15.0 deg` and the velocity innovation length is below `maxYawEstVelInnov = 2.0 m/s` (both fetched from AP_NavEKF3_core.h / AP_NavEKF3.h). Copy those two gates.

Also gate on **bike lean**: a leaning bike puts the phone's z-axis off vertical, so "gyro z in the bike frame" is not the yaw rate. Either project the gyro onto the estimated gravity direction or drop bearing updates when |roll| exceeds ~10 deg.

### 3.3 Observability of gyro-z bias: straight vs turning

- **Dissanayake et al. 2001** (fetched PDF, sec. II-D): under NHC alone, "forward velocity ... is not observable" when the vehicle "moves in a trajectory that does not excite the relevant degrees-of-freedom", specifically "along straight lines"; and heading and position "are always unobservable. Therefore, external information, for example from a GPS is always required." That is the canonical statement that **you cannot get heading or yaw-bias from IMU + NHC alone — you need GNSS bearing (or a magnetometer, which we do not have a usable one of).**
- **Fan, Hu, He, Tang, Luo, "Observability Analysis of a MEMS INS/GPS Integration System with Gyroscope G-Sensitivity Errors," *Sensors* 14(9):16003, 2014, DOI 10.3390/s140916003, CC BY 3.0.** Fetched: https://pmc.ncbi.nlm.nih.gov/articles/PMC4208158/ — under constant-velocity straight-line motion "observability of accelerometer bias and gyro bias is relatively weak"; under varying accelerated motion, turns and climbs all error states become observable. Reported: yaw RMS error dropped from 1.34 deg to 0.17 deg, roll from 2.25 deg to 0.54 deg once the manoeuvres made the states observable.
- **Practical mechanism for us:** with GNSS bearing available, yaw error and yaw-gyro bias are separable because bias integrates linearly in time while an initial yaw error is constant. So a **straight run of 30–60 s with good bearing is actually excellent for b_gz** (constant true heading, bias makes the estimate ramp). Turns are what make the *horizontal* gyro biases and the installation yaw angle observable. Plan the calibration ride to contain both.
- Not found: a paper that does an observability analysis specifically of yaw-gyro bias under a *GNSS-course* measurement for a bicycle. Nearest is the tractor paper (section 3.1), whose contribution is precisely that heading is hard to observe at low speed / low excitation. The MDPI paper "Global Observability Analysis of Rotational MEMS Inertial Navigation System for Land Vehicle Applications" (Sensors 26(9):2599) appeared in search but **mdpi.com returned HTTP 403 to both WebFetch and curl — UNVERIFIED, no numbers taken from it.**

### 3.4 GNSS latency: use a stored-state / delayed-state design

Measured latency figures we can cite:
- **50–300 ms** typical receiver delay plus **20–30 ms** jitter — Delama, Scheiber, Ge, Hamel et al., "Galilean State Estimation for Inertial Navigation Systems with Unknown Time Delay," arXiv:2605.13266, 2026-05-13, accepted RSS 2026. Fetched PDF. Their flight tests exhibited delays of 90 ms and 120 ms; simulations went to 500 ms.
- **50–200 ms** for GPS messages, handled by a **ring buffer of 100 IMU messages (1 s at 100 Hz)** — Kharwar, "FusionCore: A 23-State Unscented Kalman Filter...", arXiv:2605.25239, 2026-05-24. Fetched PDF: "on arrival of a delayed measurement, the filter restores the state snapshot closest to the measurement timestamp, applies the measurement, then re-propagates forward through buffered IMU messages."
- **100 ms – 1 s** total, with serial transmission alone contributing up to **350 ms** — Solomon, Wang, Rizos, "Latency Determination and Compensation in Real-Time GNSS/INS Integrated Navigation Systems," ISPRS Archives XXXVIII-1/C22, 2011. Fetched PDF: https://isprs-archives.copernicus.org/articles/XXXVIII-1-C22/303/2011/isprsarchives-XXXVIII-1-C22-303-2011.pdf. They name the two standard options: **measurement extrapolation** (Larsen et al. 1998) and **filter replay** (keep a lagged copy of the filter, fuse into it, replay forward).
- **PX4 EKF2** runs on a delayed "fusion time horizon": `EKF2_DELAY_MAX` default **200 ms**, max 1000 ms, "should be at least as large as the largest EKF2_XXX_DELAY parameter" (https://raw.githubusercontent.com/PX4/PX4-Autopilot/main/src/modules/ekf2/module.yaml). All sensors are FIFO-buffered and an output predictor propagates forward to present time.

**What we should do (portable to Kotlin):** keep a deque of the last 1.5 s of (timestamp, nominal state, error covariance is *not* stored — only the nominal states and the IMU samples). On a GNSS fix with timestamp `t_g`:
1. find the buffered nominal state at `t_g`;
2. apply the position/bearing update there, using the covariance from the delayed-time filter (i.e. run the filter itself at `t_g - delay` and keep a forward output predictor), **or** the cheaper Larsen approximation: propagate the measurement Jacobian forward, `H_eff = H * Phi(t_g -> t_now)^-1`, and fuse at `t_now`;
3. re-propagate to now through the buffered IMU.
At bicycle speeds the penalty for getting this wrong is bounded and quotable: arXiv:2510.08880 sec. VI notes that "for the ground robot ... with an average forward velocity of about 1.5 m/s, a time misalignment of 10 ms only leads to 0.015 m". At 5 m/s a 300 ms unmodelled latency costs **1.5 m of along-track position error** — comparable to the GNSS noise itself, so it must be modelled, but a simple 1-second ring buffer with re-propagation is sufficient; a delay *state* is over-engineering for us.

Android specifics: use `Location.getElapsedRealtimeNanos()` (monotonic, set at fix time) rather than `getTime()`, and compare it to `SensorEvent.timestamp`. Both are `SystemClock.elapsedRealtimeNanos`-based, so the subtraction is meaningful — this is what makes the stored-state approach actually implementable on the S23.

---

## 4. Online scale-factor estimation for the learned velocity

### 4.1 The standard model

Convention used by the state of the art (fetch: arXiv:2510.08880 eq. 4, Song, Xia, Yan, Zhong, Wen, Hsu, "Online IMU-odometer Calibration using GNSS Measurements for Autonomous Ground Vehicle Localization," 2025-10-10, PolyU):

```
v_m     = (1 + s_v) (v_hat_m - eps_v)        # measured = (1+scale) * true
omega_m = (1 + s_omega) (omega_hat_m - eps_omega)
```

and, verbatim in their notation, "the odometer scaling factors are modeled as random walk: `s_v_dot = eps_sv` and `s_omega_dot = eps_s_omega`."

For our learned model, the cleanest equivalent (only one scalar, because the model outputs speed not wheel ticks):

```
v_true = (1 + k) * v_model          # k is the state; k=0 means the network is unbiased
```
Measurement Jacobian into the velocity update: `dv^n/dk = R_nb * e1 * v_model`. Note the **Jacobian scales with speed** — k is only observable while moving, and observability improves linearly with speed, exactly like the bearing.

### 4.2 How to model k

Two options, both in the literature:
- **Random walk** (arXiv:2510.08880): `k_dot = w_k`, `Q_k = sigma_k_rw^2`. Simplest; k wanders freely and can absorb slow tyre-pressure / rider-posture changes.
- **First-order Gauss-Markov / random constant + small RW** — KF-GINS models all IMU bias and scale states as first-order GM with `corrtime: 4.0 hr` (config link in section 5). Wheel-INS uses `corrtime: 1.0 hr`. GM is safer because it prevents k from drifting off during a long GNSS outage where it is unobservable.

**Recommended:** GM with a long correlation time. `k ~ N(0, sigma_k0^2)`, `T_k = 600 s`, `sigma_k0 = 0.05` (5% initial uncertainty — the MoE bicycle network's own inference error is 0.333 m/s, ~7% of a 5 m/s ride, so 5% on the scale is the right order). Process noise `Q_k = 2 sigma_k0^2 / T_k * dt`, i.e. `sigma_k_rw ~= 0.003 / sqrt(s)`, letting k move about 1% over a 10-minute ride.

**Freeze k when unobservable.** During a GNSS outage set `Q_k = 0` (or a tiny value) so k holds its last converged value rather than random-walking. FusionCore does the analogous thing for its encoder-bias state: it "identifies b_ewz online through the cross-covariance between encoder omega_z error and the heading implied by GPS bearing: when GPS is available... During GPS blackouts (coast mode), the estimated b_ewz is subtracted from encoder angular velocity before integration" (arXiv:2605.25239 sec. II).

### 4.3 Observability and published residuals

- **Needs GNSS while healthy.** Wheel-INS states this directly (arXiv:1912.07805v3 sec. III-A): "the scale factor error of the wheel ... cannot be substituted by other error states in the EKF because they impact the navigation results in different ways. The scale factor error of the wheel should be estimated online if other absolute positioning information is available, such as that of GNSS."
- **Observability analysis** (arXiv:2510.08880): under general planar motion, two horizontal translation and three rotation extrinsics are observable; vertical translation is not. Scale factors converge "in a several seconds under general planar motion."
- **Published residual scale errors after calibration** (their Table III, simulation, AGV at 0.25 m/s): tightly-coupled scheme reached **6.0e-4** residual error on the linear-velocity scale factor and 3.1e-3 on the angular scale factor; loosely-coupled variants reached 2.0e-3 on the linear scale factor. Extrinsic translation converged within 0.2 m consistently across 100 Monte-Carlo runs.
- **Effect on positioning** (their field test): IMU-odometer dead reckoning with their calibrated parameters gave an absolute maximum error of **17.75 m** versus **61.51 m** with loosely-coupled calibration — a **71.14% improvement**.
- Caution they raise and we should copy into our doc: "the reported uncertainty should be treated as a reference rather than a strict bound" — the filter's own sigma on k under-covers the true error distribution.

Not found: any paper that estimates an online scale factor for a *learned* velocity model as a Kalman state. The MoE bicycle paper (arXiv:2510.17604) does **not** carry a scale state — it relies on the network's learned covariance instead. **This is a genuine gap and therefore a defensible novelty claim for our submission**, provided we present it as "we apply the standard odometer-scale-factor treatment (arXiv:2510.08880) to a learned velocity."

---

## 5. Numeric noise table (source per row)

Everything below was read out of a fetched config file, source code, or paper table. **Read the "grade" column — copying navigation-grade numbers onto a phone IMU is the classic tuning mistake.**

| Quantity | Value | IMU / platform grade | Source (fetched 2026-09-05) |
|---|---|---|---|
| Gyro ARW | 0.003 deg/sqrt(hr) | nav-grade (Leador A15) | KF-GINS `dataset/kf-gins.yaml` — https://raw.githubusercontent.com/i2Nav-WHU/KF-GINS/main/dataset/kf-gins.yaml |
| Accel VRW | 0.03 m/s/sqrt(hr) | nav-grade | same |
| Gyro bias std (GM) | 0.027 deg/hr | nav-grade | same |
| Accel bias std (GM) | 15.0 mGal | nav-grade | same |
| Gyro/accel scale std | 300 ppm each | nav-grade | same |
| GM correlation time | 4.0 hr | nav-grade | same |
| GNSS antenna lever arm | [0.136, -0.301, -0.184] m (fwd, right, down) | vehicle | same |
| Initial pos/vel/att std | [0.005,0.004,0.008] m / [0.003,0.004,0.004] m/s / [0.003,0.003,0.023] deg | nav-grade, post-alignment | same |
| **Gyro ARW** | **1.2 deg/sqrt(hr)** | **MEMS (ICM20602-class) — closest to a phone** | Wheel-INS `config/car.yaml` — https://raw.githubusercontent.com/i2Nav-WHU/Wheel-INS/master/config/car.yaml |
| **Accel VRW** | **6 m/s/sqrt(hr)** | MEMS | same |
| **Gyro bias std (GM)** | **50 deg/hr** | MEMS | same |
| **Accel bias std (GM)** | **2000 mGal (= 0.0196 m/s^2)** | MEMS | same |
| Gyro / accel scale std | 50 ppm / 500 ppm | MEMS | same |
| GM correlation time | 1.0 hr | MEMS | same |
| **NHC + odometer measurement std** | **[0.035, 0.02, 0.02] m/s** (forward, lateral, vertical) | MEMS on a car | same (`ODO_std`) |
| **NHC/ODO update interval** | **0.5 s (2 Hz)** | — | same (`ODO_dt`); confirmed in arXiv:2012.10589 sec. IV-A: "The update frequency was set as 2 Hz" |
| Installation (misalignment) angle | [0, 1.32, 0] deg (car), [0, -3.38, 0] deg (robot) | — | Wheel-INS `config/car.yaml`, `config/robot.yaml` |
| Lever arm IMU->wheel centre | [-0.01, 0.01, -0.01] m (car); [-0.015, 0.005, 0.005] m (robot) | — | same |
| Datasheet gyro bias / ARW (ICM20602) | 200 deg/h / 0.24 deg/sqrt(h) | consumer MEMS | Wheel-INS paper Table I, arXiv:1912.07805v3 |
| Datasheet accel bias / VRW (ICM20602) | 0.01 m/s^2 / 3 m/s/sqrt(h) | consumer MEMS | same |
| NHC lateral pseudo-meas. sigma | 1 m/s | KITTI car, IMU-only | AI-IMU, arXiv:1904.06064 eq. 20 |
| NHC vertical pseudo-meas. sigma | 3 m/s | same | same |
| Gyro process noise sigma_omega | 1.4e-2 rad/s | KITTI car (100 Hz OXTS) | AI-IMU eq. 19 |
| Accel process noise sigma_a | 3e-2 m/s^2 | same | same |
| Gyro-bias RW sigma | 1e-4 rad/s | same | same |
| Accel-bias RW sigma | 1e-3 m/s^2 | same | same |
| Initial vel std | 0.3 m/s | same | AI-IMU eq. 18 |
| Initial gyro-bias std | 1e-4 rad/s | same | same |
| Initial accel-bias std | 3e-2 m/s^2 | same | same |
| Initial installation-angle / lever-arm std | 3e-3 rad / 1e-1 m | same | same |
| Learned-velocity R | network-predicted `Sigma_v_b`, per-sample | bicycle + smartphone | arXiv:2510.17604 eq. 18–20 |
| Learned-velocity update rate | 10 Hz (every 0.1 s) | bicycle + smartphone | arXiv:2510.17604 sec. III |
| GNSS position noise (default) | 0.5 m | consumer GNSS | PX4 `EKF2_GPS_P_NOISE` — https://raw.githubusercontent.com/PX4/PX4-Autopilot/main/src/modules/ekf2/params_gnss.yaml |
| GNSS velocity noise (default) | 0.3 m/s | consumer GNSS | PX4 `EKF2_GPS_V_NOISE`, same file |
| GNSS innovation gate | 5.0 standard deviations (position and velocity) | — | PX4 `EKF2_GPS_P_GATE`, `EKF2_GPS_V_GATE`, same file |
| GNSS quality accept thresholds | EPH 3.0 m, EPV 5.0 m, speed accuracy 0.5 m/s | — | PX4 `EKF2_REQ_EPH/EPV/SACC`, same file |
| Gyro noise / accel noise for cov. prediction | 0.015 rad/s / 0.35 m/s^2 | consumer MEMS on a drone | PX4 `EKF2_GYR_NOISE`, `EKF2_ACC_NOISE` — module.yaml |
| Gyro-bias / accel-bias process noise | 1e-3 rad/s^2 / 3e-3 m/s^3 | same | PX4 `EKF2_GYR_B_NOISE`, `EKF2_ACC_B_NOISE` — params_gyro_bias.yaml, params_accel_bias.yaml |
| Max sensor delay buffered | 200 ms default (max 1000 ms) | — | PX4 `EKF2_DELAY_MAX` — module.yaml |
| Output-predictor smoothing tau | 0.25 s (position and velocity) | — | PX4 `EKF2_TAU_POS`, `EKF2_TAU_VEL` — module.yaml |
| GNSS-velocity obs. variance for yaw | max(reported velAcc, 0.5 m/s)^2 | — | ArduPilot `EKFGSF_yaw.cpp::fuseVelData` |
| GSF yaw accept gate | yaw sigma < 15 deg; vel innovation < 2.0 m/s | — | ArduPilot `AP_NavEKF3_core.h` (`GSF_YAW_ACCURACY_THRESHOLD_DEG 15.0f`), `AP_NavEKF3.h` (`maxYawEstVelInnov = 2.0f`) |
| NHC enable gate | mean \|omega\| < 5 deg/s AND mean v > 1 m/s over 1 s | ground vehicle | arXiv:2510.08880 sec. VI |
| ZUPT enable gate | mean \|omega\| < 0.05 deg/s over 1 s | ground vehicle | same |
| Chi-square outlier gate, 3-DOF position | 16.27 (chi2(3, 0.999)) | — | FusionCore, arXiv:2605.25239 sec. IV-A |
| Adaptive-R innovation window | 50 samples, alpha = 0.01, floor R_ii >= R0_ii | — | same |

### Starting point I would actually use for the S23 Ultra

Derived from the MEMS column above, adjusted for a phone-grade IMU logged at ~400 Hz (our measured ceiling is 418.8 Hz):

| Parameter | Value | Rationale |
|---|---|---|
| gyro ARW | 1.5–3 deg/sqrt(hr) | between Wheel-INS MEMS (1.2) and ICM20602 datasheet (0.24 is optimistic for a phone in a vibrating bottle cage); **measure it with an Allan variance on 2 h of static logging before trusting either** |
| gyro bias std (GM), T = 1 hr | 50 deg/hr | Wheel-INS `car.yaml` |
| accel VRW | 6 m/s/sqrt(hr) | Wheel-INS `car.yaml` — only affects tilt, since we do not integrate accel for velocity |
| accel bias std (GM) | 0.02 m/s^2 | Wheel-INS `car.yaml` (2000 mGal) |
| NHC sigma_lat, sigma_vert (straight) | 0.10 m/s, 0.10 m/s | Wheel-INS uses 0.02; AI-IMU uses 1.0 and 3.0. A leaning bike violates NHC far more than a car, and the bottle-cage lever arm is larger than Wheel-INS's 1 cm. Start conservative at 0.10, widen with the omega_z rule of section 2.3 up to ~1 m/s in hard turns. |
| ZUPT sigma | 0.02 m/s | Wheel-INS ODO lateral/vertical value; a stopped bike really is stopped |
| GNSS position R | (max(reported accuracy, 3.0 m))^2 | Android `Location.getAccuracy()` is a 68% horizontal radius; floor it. PX4's 0.5 m default assumes a much better receiver. |
| GNSS bearing R | (sigma_v / v)^2 with sigma_v = 0.5 m/s, gated to v > 2 m/s | section 3.2 |
| learned speed R | (network sigma)^2, floored at (0.15 m/s)^2 | MoE bicycle IE was 0.333 m/s; never trust a network sigma below half that |
| k (scale) init / T / Q | sigma_k0 = 0.05, T_k = 600 s, frozen during outage | section 4.2 |
| psi_mis init | sigma = 5 deg | arXiv:2510.08880 uses 5 deg initial uncertainty on IMU-odometer rotation |

---

## 6. Recovery when GNSS returns

Three published mechanisms, all fetched:

**(a) Innovation gating with a chi-square threshold, and adaptive R.** FusionCore (arXiv:2605.25239) applies a per-sensor Mahalanobis chi-square gate before any state change — GPS position (3 DOF) threshold **16.27 = chi2(3, 0.999)**, VSLAM pose (6 DOF) **22.46** — and adapts R from the innovation sequence over a sliding window of **50 samples with alpha = 0.01**, with a floor `R_ii >= R0_ii`. When GPS errors exceed the driver-reported covariance, "the adaptive window inflates the noise model and recalibrates the chi-squared gate accordingly."
Their failure mode is a direct warning for us: on 2012-08-20 the GPS stream contained "105 mode-3 fixes that are 720–840 m away from the RTK ground truth, concentrated in a 24-second window **at the end of a 211-second blackout**", and the filter's ATE blew out to 98.3 m. **The single most dangerous moment in our pipeline is the first fix after re-acquisition.**
Their counter-measure: "FusionCore counts consecutive gate" rejections — a run of rejections triggers re-initialisation rather than silent divergence.

**(b) Smooth blending rather than a hard jump — this is exactly the "no teleport" behaviour we want in the demo.** PX4 solves it structurally: the EKF fuses at a delayed fusion time horizon and a separate **output predictor** runs a complementary filter forward to present time with gains `pos_gain = dt / EKF2_TAU_POS` and `vel_gain = dt / EKF2_TAU_VEL`, both tau defaulting to **0.25 s**. On an actual state reset, `resetHorizontalPositionTo` / `resetQuaternion` add the delta to **every entry in the output ring buffer**, so the reported output shifts as one piece with no discontinuity in its derivative. Source (BSD-3-Clause): https://raw.githubusercontent.com/PX4/PX4-Autopilot/main/src/modules/ekf2/EKF/output_predictor/output_predictor.cpp
**Copy this design:** keep the filter's estimate rigorous and let a 0.25 s-tau output layer be what you draw on the map.

**(c) Inflate the process noise on the states you know are drifting, not the measurement noise on the ones you trust.** FusionCore's "coast mode inflates Q_position and adjusts the IMU weighting so that encoder omega_z dominates heading."

**How the error actually grows during outage, so we can size the expectation.** FusionCore on the NCLT dataset: sequences with max blackouts under 203 s drift **1–2.6 m/km**; sequences with 240–462 s blackouts drift **6–10 m/km** — "at 100 Hz with a small uncorrected heading rate residual, lateral position error grows quadratically with blackout duration." That quadratic-in-time lateral growth from residual yaw-rate error is our dominant error term too, and it is why sections 3 and 7 matter more than section 4.

**Recommended recipe:**
1. Buffer the fix; do not fuse the first fix after an outage immediately.
2. Require N consecutive fixes (ArduPilot uses `GPS_VEL_YAW_ALIGN_COUNT_THRESHOLD = 5` before trusting GPS-derived yaw) that are mutually consistent and pass the chi-square gate at a *widened* R.
3. Fuse with R inflated by ~4x (2x on sigma) for the first ~5 epochs, then decay to nominal.
4. If the innovation exceeds the gate for more than ~5 consecutive fixes while GNSS quality flags are good, **reset** position (and covariance) to GNSS rather than continuing to reject — PX4's documented behaviour is to reset to GNSS when it becomes available again after loss.
5. Apply the correction through the 0.25 s output-predictor layer so the drawn track never teleports.

---

## 7. Corridor / 1-D arc-length filter

### 7.1 The most directly usable published treatment (2026)

**Cui, Zhang, Mao, Lü, Li, Che, Zhang, "Route-Constrained Robust Fusion Estimation for MEMS/GNSS Integrated Navigation of Unmanned Ground Vehicles in GNSS Degraded Environments," arXiv:2606.19687, 2026-06-18.** Fetched PDF.

Their approach, which maps cleanly onto "we know the corridor A<->B":
1. Keep a short window of the historical dead-reckoned trajectory `S = {s_1..s_N}` in the local ENU plane, and the local mission-route polyline `N_k = {q_1..q_M}` from the map.
2. Resample both at a **fixed spatial interval** and establish point correspondences "according to the cumulative arc-length order" — i.e. match by arc length s, not by nearest neighbour. (This is the key trick: nearest-neighbour matching is what makes naive map matching snap to the wrong lane/branch.)
3. Estimate a 2-D rigid transform by SVD of the cross-covariance `C_k = sum_i (s_i - s_bar)(t_i - t_bar)^T`, with `R_rot = V diag(1, det(VU^T)) U^T` and `t = t_bar - R_rot s_bar`.
4. Gate on azimuth consistency: compute terminal tangent unit vectors from the last two resampled points of each set and require `|cos theta_k| >= gamma_h`.
5. Feed the resulting route-referenced position into the 15-state ESKF as a **pseudo-position observation**, not as a hard snap.
6. Apply "a projection-based correction ... to suppress accumulated longitudinal drift" before output, plus trigger control, matching-quality validation, and **single-update correction limiting** (cap how much any one pseudo-position update may move the state).

Results (their Table I; route-relative position deviation in m, heading in deg):

| Scenario | Method | Max pos dev | Mean pos dev | Pos RMSE | Mean heading dev | Heading RMSE |
|---|---|---|---|---|---|---|
| Long tunnel | Baseline | 386.3 | 142.909 | 186.821 | 2.073 | 3.524 |
| Long tunnel | Route-constrained | **22.7** | **0.745** | **1.672** | **0.048** | **1.257** |
| Curved tunnel | Baseline | 32.6 | 7.908 | 10.376 | -0.216 | 0.793 |
| Curved tunnel | Route-constrained | 27.5 | 1.431 | 1.889 | -0.179 | 0.946 |
| Multi-segment | Baseline | 23.3 | 3.576 | 6.502 | 0.011 | 1.839 |
| Multi-segment | Route-constrained | 8.5 | 1.755 | 2.351 | 0.018 | 1.332 |

Their own honest caveat, worth repeating in our doc: the benefit "is first reflected in suppressing position drift, while the azimuth solution is mainly improved indirectly through state coupling." **A corridor constraint fixes cross-track error; it does almost nothing for along-track error.** That is precisely the split we should design around.

### 7.2 The (s, v) along-track formulation

I did **not** find a paper that publishes exactly the 2-state `(s, v)` arc-length filter with lateral error handled by projection. Closest published items:
- The route-constrained paper above, which uses arc-length-ordered correspondence and a projection-based longitudinal correction but keeps a full 15-state ESKF in Cartesian space.
- Jeon, Hwang, Jeong, Park, Kweon, Choi, "Lane Detection Aided Online Dead Reckoning for GNSS Denied Environments," *Sensors* 21(20):6805, 2021, DOI 10.3390/s21206805, CC BY 4.0. Fetched: https://pmc.ncbi.nlm.nih.gov/articles/PMC8538960/ — 9-state DR with lane geometry constraining **lateral** position at multiple preview distances. Their tunnel scenario (5290 m, 225 s of GNSS outage) gave **5.12 m RMSE = 4.31 m lateral + 2.78 m longitudinal**, heading drift under 2 deg across all scenarios. Note the error is still lateral-dominated even with a lane constraint, because their lanes are nearly straight.
- Gupta & Hauser, "Kalman Filtering with Equality and Inequality State Constraints," Oxford University Computing Laboratory report NA-07/18. Fetched PDF: https://www.cs.ox.ac.uk/files/728/NA-07-18.pdf — the general machinery for constraining a KF state to `A x = b` (which is what "the bike is on the polyline" is, locally), including the estimate-projection method and the extension to inequality constraints (useful for "s must be within the corridor's length"). Dan Simon's 2010 IET survey is the more commonly cited version of the same material but **I could not fetch its full text — UNVERIFIED, no numbers taken from it.**

**Design I would propose (mine, built from the above, not a citation):**

```
Corridor filter state:  x_c = [ s , v , k ]        # arc length along polyline, along-track speed, learned-speed scale
Propagate:              s += v dt ;  v = (1+k) v_model
Measurements:
  learned speed  -> z = v_model,     H = [0, 1/(1+k), -v/(1+k)]   (or fuse v directly)
  GNSS fix p     -> project p onto the polyline: (s_gnss, d_gnss) = project(p)
                    fuse s: z = s_gnss - s,  H = [1,0,0],  R = sigma_along^2
                    DISCARD d_gnss, or use it only to validate corridor membership (|d| < w)
  corridor       -> lateral error is not a state; it is structurally zero
Output:            p^n = polyline_point(s),   heading = polyline_tangent(s)
```

Why this is attractive for our specific problem (same-corridor A<->B, known route): it removes the yaw-drift-to-lateral-error coupling that FusionCore identified as the quadratic-in-time killer, and it turns the entire estimation problem into 1-D, where the only error source is the along-track speed scale — which is exactly the state that GNSS observes best and that our learned model estimates directly. The failure mode is equally clear: it is catastrophically wrong if the rider leaves the corridor, so the `|d_gnss| < w` membership test and a fall-back to the full 2-D ESKF are mandatory, and the corridor filter must never be the only estimator running.

---

## 8. What changes our decision

- **The bicycle+smartphone+learned-velocity+ESKF architecture is already published (arXiv:2510.17604, v2 July 2026, Wuhan i2Nav) and its NHC baseline beats the network on paved road.** We must run NHC as a parallel/fused constraint, not present the network as a replacement, or a knowledgeable judge will ask why we ignored the cheaper method that wins on our surface type. Their measurement equations (H_phi = R^T (v^n)_x, H_dv = R^T) are directly copyable into numpy.
- **Use ArduPilot's GNSS-velocity-vector yaw formulation (Form B), not an explicit atan2 course measurement.** It gives the 1/v weighting for free, avoids angle wrapping, and comes with two validated gates we can copy verbatim (yaw sigma < 15 deg, velocity innovation < 2.0 m/s). Gate bearing at v > 2 m/s: below that, sigma_psi = sigma_v/v exceeds 10 deg and the update is noise.
- **ZIHR at every stop is free gyro-z bias observability and needs no GNSS.** Wheel-INS uses it precisely because heading drifts fastest when stationary. Given a campus route with traffic lights, this may outperform the GNSS-bearing path — build the stationarity detector (mean |omega| < 0.05 deg/s over 1 s, per arXiv:2510.08880) before building the bearing update.
- **The scale factor `k` must be a Gauss-Markov state with Q frozen during outage, not a random walk.** It is unobservable without GNSS and will wander into the trajectory if left free. Published residual after proper calibration is 6e-4 to 2e-3 (arXiv:2510.08880 Table III), i.e. **sub-0.2% speed error is achievable**, which over a 2 km outage is under 4 m of along-track error — an order of magnitude better than our likely cross-track error.
- **Latency is worth exactly one ring buffer, not a delay state.** Use `Location.getElapsedRealtimeNanos()` against `SensorEvent.timestamp`, buffer 1.5 s of nominal states + IMU, re-propagate. At 5 m/s an unmodelled 300 ms delay costs 1.5 m along-track; a delay *state* (arXiv:2605.13266) is aimed at drones with 500 ms delays and is over-engineering here.
- **The first fix after an outage is the highest-risk event in the whole pipeline** (FusionCore's worst sequence: 98.3 m ATE from bad fixes clustered at a blackout boundary). Implement: buffer, require 5 consecutive consistent fixes, chi-square gate at 16.27 for 3-DOF position, inflate R 4x for 5 epochs, and reset-to-GNSS if the gate rejects for >5 consecutive good-quality fixes.
- **Draw the map track from a 0.25 s-tau output-predictor layer, never from the raw filter state.** PX4's `resetHorizontalPositionTo` applies the reset delta across the whole output buffer so the displayed track shifts smoothly. This is a 20-line change that makes the demo look professional and removes the "it teleported" objection.
- **Corridor constraint kills cross-track error and does nothing for along-track error** (route-constrained paper: long-tunnel position RMSE 186.8 m -> 1.7 m, but heading RMSE only 3.52 -> 1.26 deg). Decide deliberately: if we ship the corridor filter, our accuracy story becomes "along-track only, bounded by the learned speed scale (<0.2% after calibration)", which is a much stronger claim than a 2-D drift percentage — but it only holds while the rider stays on the corridor, so a `|lateral| < w` membership test and a fall-back to the full ESKF are non-negotiable.

---

## Appendix: source ledger

All fetched 2026-09-05. "Repo" rows report star count and last push from the GitHub REST API on that date.

| # | Title / artefact | Authors / org | Date | Venue / id | URL | Licence | Contribution -> our use |
|---|---|---|---|---|---|---|---|
| 1 | KF-GINS: An EKF-Based GNSS/INS Integrated Navigation System | i2Nav Group, GNSS Research Center, Wuhan University | last push 2026-06-10; 1189 stars | GitHub repo (C++/CMake) | https://github.com/i2Nav-WHU/KF-GINS | GPL-3.0 | Canonical 21-state loosely-coupled ESKF; phi-angle model; GM bias/scale modelling. Copy the state layout and the config schema; **do not** copy its nav-grade noise numbers. |
| 2 | KF-GINS demo config `kf-gins.yaml` | same | same | config file | https://raw.githubusercontent.com/i2Nav-WHU/KF-GINS/main/dataset/kf-gins.yaml | GPL-3.0 | Exact nav-grade noise defaults + lever arm. Cite as the "high-grade reference" row in our noise table. |
| 3 | Wheel-INS: A Wheel-mounted MEMS IMU-based Dead Reckoning System | X. Niu, Y. Wu, J. Kuang (Wuhan Univ.) | arXiv v4 2021-04-24; IEEE TVT 70(10):9814-9825, 2021 | arXiv:1912.07805 | https://arxiv.org/abs/1912.07805 ; PDF https://www.arxiv.org/pdf/1912.07805v3 | arXiv (no open licence stated) | NHC + lever arm + installation angle measurement equations; 21 vs 15 state discussion; ZIHR; explicit statement that wheel scale factor needs GNSS. Copy eq. 10–13 structure. Drift < 1.8% of distance; 23% better than ODO/INS. |
| 4 | Wheel-INS repo + `config/car.yaml`, `config/robot.yaml` | i2Nav | last push 2025-01-25; 388 stars | GitHub repo | https://github.com/i2Nav-WHU/Wheel-INS ; https://raw.githubusercontent.com/i2Nav-WHU/Wheel-INS/master/config/car.yaml | GPL-3.0 | **The MEMS-grade noise numbers we should actually start from**, plus `ODO_std`, `ODO_dt`, `MisalignAngle`, `WheelLA`. |
| 5 | A Comparison of Three Measurement Models for the Wheel-mounted MEMS IMU-based DR System | Y. Wu, X. Niu, J. Kuang | 2020-12 | arXiv:2012.10589 | https://arxiv.org/pdf/2012.10589 | arXiv | Velocity vs displacement-increment vs contact-point-ZUPT models; all < 2% drift; 2 Hz update rate. Use to justify choosing the simple velocity model. |
| 6 | MoE-Based Learned Inertial Odometry for Bicycle Localization | H. Qiao, Y. Wang, S. Yang, X. Yu, J. Kuang, X. Niu | v1 2025-10-20, **v2 2026-07-26** | arXiv:2510.17604 | https://arxiv.org/abs/2510.17604 | "submitted to IEEE"; no open licence | **Closest published work to our system.** Copy the EKF measurement update and the 120 s-outage evaluation protocol. Cite ATE 9.49 m / RTE 2.58 m / IE 0.333 m/s and the NHC-vs-MoE paved/unpaved split. |
| 7 | AI-IMU Dead-Reckoning | M. Brossard, A. Barrau, S. Bonnabel (MINES ParisTech) | 2019 (arXiv:1904.06064) | arXiv / IEEE T-IV | https://arxiv.org/pdf/1904.06064 | arXiv; code stated open-source | The definitive treatment of NHC as *soft* pseudo-measurements with adaptive covariance. Copy sigma_lat/sigma_up starting values and the "inflate covariance during bends by up to 10^2" rule. 1.10% mean KITTI translational error, IMU-only. |
| 8 | The Aiding of a Low-Cost Strapdown IMU Using Vehicle Model Constraints for Land Vehicle Applications | G. Dissanayake, S. Sukkarieh, E. Nebot, H. Durrant-Whyte | 2001-10 | IEEE T-RA 17(5):731–747 | http://www-personal.acfr.usyd.edu.au/nebot/publications/gps_ins_constraints.pdf | publisher copyright; author copy | **Foundational NHC paper.** Cite for the two-constraint definition, soft-noise modelling, and the observability result that heading is always unobservable without external aiding. |
| 9 | Online IMU-odometer Calibration using GNSS Measurements for AGV Localization | B. Song, X. Xia, P. Yan, Y. Zhong, W. Wen, L.-T. Hsu (PolyU) | 2025-10-10 | arXiv:2510.08880 | https://arxiv.org/pdf/2510.08880 | arXiv; dataset released open-source | **Primary source for section 4.** Scale-factor model `v_m=(1+s_v)(v_hat-eps)` as random walk; observability; NHC/ZUPT gating thresholds; residual scale errors 6e-4 to 2e-3; 17.75 m vs 61.51 m field result. |
| 10 | FusionCore: A 23-State Unscented Kalman Filter for IMU, Wheel Encoder, GPS, and Visual SLAM Fusion in ROS 2 | M. Kharwar | 2026-05-24 | arXiv:2605.25239; repo 341 stars, last push 2026-09-04 | https://arxiv.org/pdf/2605.25239 ; https://github.com/manankharwar/fusioncore | Apache-2.0 (repo) | Ring-buffer retrodiction for 50–200 ms GPS delay; chi-square gates (16.27 for 3-DOF); adaptive R (50-sample window, alpha=0.01); coast mode; **the encoder-yaw-rate-bias-from-GPS-bearing state is the direct analogue of our gyro-z-bias-from-bearing**; blackout-length vs drift-rate table. |
| 11 | Galilean State Estimation for INS with Unknown Time Delay | G. Delama, M. Scheiber, Y. Ge, T. Hamel et al. | 2026-05-13 | arXiv:2605.13266; accepted RSS 2026 | https://arxiv.org/pdf/2605.13266 | arXiv; RSS proceedings | Cite for the measured GNSS delay range 50–300 ms plus 20–30 ms jitter. Their full delay-as-a-state method is more than we need — say so and move on. |
| 12 | Latency Determination and Compensation in Real-Time GNSS/INS Integrated Navigation Systems | P. D. Solomon, J. Wang, C. Rizos (Clearbox / UNSW) | 2011-09 | ISPRS Archives XXXVIII-1/C22:303 | https://isprs-archives.copernicus.org/articles/XXXVIII-1-C22/303/2011/isprsarchives-XXXVIII-1-C22-303-2011.pdf | ISPRS open archive | Names the two canonical delayed-measurement techniques (Larsen measurement extrapolation; filter replay with a lagged filter copy) and quotes 100 ms–1 s total, 350 ms worst-case serial. Older but it is the clearest short statement of the two options. |
| 13 | PX4 EKF2 parameter definitions + output predictor | PX4 / Dronecode | fetched from `main` 2026-09-05 | source files | https://raw.githubusercontent.com/PX4/PX4-Autopilot/main/src/modules/ekf2/params_gnss.yaml ; .../module.yaml ; .../EKF/output_predictor/output_predictor.cpp | BSD-3-Clause | Real, battle-tested defaults for GNSS noise/gates/quality checks, IMU noise, delay buffering (200 ms), and the 0.25 s-tau smooth-blending output layer. Copy the output predictor design for the map display. |
| 14 | ArduPilot EKF-GSF yaw estimator | ArduPilot | fetched from `master` 2026-09-05 | `libraries/AP_NavEKF/EKFGSF_yaw.cpp`, `AP_NavEKF3/AP_NavEKF3_core.h`, `AP_NavEKF3.h` | https://raw.githubusercontent.com/ArduPilot/ardupilot/master/libraries/AP_NavEKF/EKFGSF_yaw.cpp | GPL-3.0 | The reference implementation of yaw-from-GNSS-velocity, with `velObsVar = max(velAcc, 0.5)^2`, 5-sigma innovation compression, and the 15 deg / 2.0 m/s accept gates. **Note GPL-3.0 — read the code for the method, do not paste it into our app.** |
| 15 | Adaptive Trajectory-Constrained Heading Estimation for Tractor GNSS/SINS Integrated Navigation | S. Hu, S. Chen, L. Wang, Z. Meng, W. Fu, Y. Ren, C. Li, H. Wang | 2026-01-15 | *Sensors* 26(2):595, DOI 10.3390/s26020595 | https://pmc.ncbi.nlm.nih.gov/articles/PMC12845551/ | CC BY 4.0 | Explicit `Z = [pos err ; psi_INS - psi_GNSS]` heading observation with a **0.2 m/s** stationarity gate and Sage-Husa adaptive R (window m=10). Results at 1 m/s: heading RMSE 0.10–0.30 deg, convergence 7.8–12.6 s. Cite for the low-speed gate and for adaptive R on the heading channel. |
| 16 | Five-State EKF for SOG, COG and Course Rate of USVs | S. Fossen, T. I. Fossen | 2021 | *Sensors* 21(23):7910, DOI 10.3390/s21237910 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8659471/ | CC BY 4.0 | Independent confirmation that COG is only reliable above ~0.5 m/s and undefined at zero speed. Use as the second citation for the speed gate. |
| 17 | Observability Analysis of a MEMS INS/GPS Integration System with Gyroscope G-Sensitivity Errors | C. Fan, X. Hu, X. He, K. Tang, B. Luo | 2014 | *Sensors* 14(9):16003, DOI 10.3390/s140916003 | https://pmc.ncbi.nlm.nih.gov/articles/PMC4208158/ | CC BY 3.0 | Observability under straight-line vs manoeuvring motion; yaw RMS 1.34 -> 0.17 deg once observable. Older, included because it is open-access and states the straight-vs-turn result quantitatively. |
| 18 | Route-Constrained Robust Fusion Estimation for MEMS/GNSS Integrated Navigation of UGVs in GNSS Degraded Environments | J. Cui, C. Zhang, Y. Mao, S. Lü, D. Li, H. Che, R. Zhang | 2026-06-18 | arXiv:2606.19687 | https://arxiv.org/pdf/2606.19687 | arXiv | **Primary source for the corridor filter.** Arc-length-ordered correspondence, SVD rigid registration, pseudo-position observation, azimuth-consistency gate, single-update correction limiting. Long-tunnel position RMSE 186.8 -> 1.7 m. |
| 19 | Lane Detection Aided Online Dead Reckoning for GNSS Denied Environments | J. Jeon, Y. Hwang, Y. Jeong, S. Park, I. S. Kweon, S. B. Choi | 2021 | *Sensors* 21(20):6805, DOI 10.3390/s21206805 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8538960/ | CC BY 4.0 | Lateral-only map constraint with numbers: 5290 m / 225 s tunnel outage -> 5.12 m RMSE (4.31 lateral, 2.78 longitudinal), heading drift < 2 deg. Use to argue that lateral constraints alone leave a lateral-dominated residual. |
| 20 | Kalman Filtering with Equality and Inequality State Constraints | N. Gupta, R. Hauser | 2007 | Oxford Univ. Computing Lab report NA-07/18 | https://www.cs.ox.ac.uk/files/728/NA-07-18.pdf | Oxford technical report | The general estimate-projection machinery for constraining a KF to `A x = b`, and the inequality extension. Foundational; use for the mathematical justification of corridor projection. |
| 21 | TLIO: Tight Learned Inertial Odometry | W. Liu, D. Caruso, E. Ilg, J. Dong, A. Mourikis, K. Daniilidis, V. Kumar, J. Engel | 2020-07-06 | arXiv:2007.01867; repo 406 stars, last push 2023-08-08 | https://arxiv.org/abs/2007.01867 ; https://github.com/CathIAS/TLIO | repo licence "NOASSERTION" — check before reuse | The origin of "network regresses displacement + uncertainty, fused into a stochastic-cloning EKF", which is the pattern the bicycle MoE paper follows and the source of the RTE metric. Repo has been static since 2023 — treat as reference, not a dependency. |

### Marked UNVERIFIED (fetch failed; no numbers used)

- **"Global Observability Analysis of Rotational MEMS Inertial Navigation System for Land Vehicle Applications," *Sensors* 26(9):2599 (2026)** — https://www.mdpi.com/1424-8220/26/9/2599 returned **HTTP 403** to both WebFetch and curl with a browser user-agent. Appeared in search results as relevant to gyro-bias observability under turning; **do not cite until someone opens it in a browser.**
- **D. Simon, "Kalman Filtering with State Constraints: A Survey of Linear and Nonlinear Algorithms," IET Control Theory & Applications 4(8):1303–1318, 2010** — the Cleveland State repository copy returned an HTML error page rather than a PDF. Bibliographic details come from search results only. Superseded for our purposes by source #20, which I did fetch.

### Explicitly not found

- No paper stating `sigma_heading = sigma_velocity / v` in closed form for a GNSS course measurement. The relation is derived in section 3.2 and is consistent with ArduPilot's implementation, but it must be presented as our derivation.
- No published work that estimates an online **scale factor for a learned velocity model** as a Kalman state. The odometer literature (source #9) has it; the learned-inertial-odometry literature (sources #6, #21) uses a learned covariance instead. This is a real gap and a legitimate novelty claim for our submission.
- No published 2-state `(s, v)` arc-length corridor filter with lateral error handled purely by projection. Sources #18 and #19 are the nearest; the formulation in section 7.2 is ours.
