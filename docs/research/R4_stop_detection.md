# R4 — Zero-velocity / stop detection for a bicycle-mounted phone

**Scope:** published detectors, thresholds, error rates and latencies we can calibrate our
"physical stop rule + learned speed model" against.
**Target spec being tested:** trigger < 1 s after the bike stops; zero false stops at 1–2 m/s
coasting; causal; portable to Kotlin.
**All sources below were fetched on 2026-09-05.** Where a page could not be retrieved it is
marked UNVERIFIED. Where the literature contains nothing, it says **not found**.

**Headline for the lead: there is no published bicycle zero-velocity detector with thresholds
and FP/FN rates.** The closest bicycle-specific work (Qiao et al. 2026, Bieshaar et al. 2018)
either has no stop detector at all or measures *start* latency, not stop latency. Everything
numeric below is borrowed from cars, feet, or bicycle *vibration* studies, and the transfer
assumptions are stated explicitly.

---

## 1. Detector table

| # | Detector | Platform | Signal + window | Threshold as published | Reported FP / FN or accuracy | Latency | Source (fetched 2026-09-05) |
|---|---|---|---|---|---|---|---|
| 1 | **AMVD** (accel moving variance), grid-search-optimised | Car (KAIST urban, Xsens MTi-300 @100 Hz) | accel variance, W = 100 samples = **1.00 s** | γ = **1×10⁻³** on variance → σ_a ≈ **0.032 m/s²** | On 64×10⁴ test samples: FP ≈ 4×10³, FN ≈ 1×10⁴; **precision 0.974 / recall 0.940** | Not reported; ≥1 s implied by window | [arXiv:1903.02210v2](https://arxiv.org/pdf/1903.02210) |
| 2 | **RINS-W learned ZVD** (LSTM per motion profile) | Same car data | raw accel+gyro, recursive (hidden state), 100 Hz | sigmoid output > **0.95** for zero-velocity and zero-angular-velocity; 0.5 for lateral/vertical | **FP ≈ 7×10², FN ≈ 9×10³; precision 0.996 / recall 0.940** → ~**5.7× fewer false stops at identical recall** vs the tuned AMVD | Recursive, per-sample at 100 Hz; no window latency | same |
| 3 | **FFT idle-vibration detector** (Li et al.) | Car (MEMS IMU @200 Hz) | FFT of forward/up accel + pitch gyro; **3 s window, 1 s update** (600 samples), 2 s overlap | All spectral peaks < **15 mg (0.147 m/s²)** accel and **0.7 deg/s (0.0122 rad/s)** gyro; Peak-1 (12.495 Hz) and Peak-2 (24.991 Hz) must exceed the 0–10 Hz peak (accel peaks scaled ×1.5); gyro Peak-1 ≥ **7.0×** Peak-0; velocity < **0.5 m/s** | **99.7% correct** over stops (3487 of 3499 s; per-stop 99.9 / 99.5 / 99.7%). **No false-positive-while-moving rate published.** Failures all caused by passengers entering/exiting | ≥1 s (update rate); paper states larger windows mis-detect at the start/end of a stop | [Remote Sens. 16(5):902, 2024-03-04, CC BY](https://mdpi-res.com/d_attachment/remotesensing/remotesensing-16-00902/article_deploy/remotesensing-16-00902.pdf) |
| 4 | **SHOE** (accel+gyro GLRT) | Foot (200 Hz) | joint accel+gyro GLRT over N-sample window | per-trial optimal γ spans **4.75×10⁵ → 6.50×10⁸** (three orders of magnitude across 60 trials) | Best in 30/60 VICON trials, mean position error **0.068 m**; fixed-threshold hallway ARMSE **2.48 m** | Not reported | [arXiv:1910.00529v2](https://arxiv.org/html/1910.00529v2) |
| 5 | **ARED** (angular-rate energy) | Foot | gyro energy over window | γ_ω **1.25×10⁻² → 2.70×10⁰** | Best in 13/60 trials, mean **0.075 m** | Not reported | same |
| 6 | **AMVD** | Foot | accel variance | γ **1.00×10⁻³ → 1.95×10⁰** | Best in **0/60** trials, mean **0.336 m** (worst) | – | same |
| 7 | **MBGTD** | Foot | memory-based graph-theoretic | γ **5.75×10⁻³ → 9.75×10⁻¹** | Best in 2/60 trials, mean **0.329 m** | – | same |
| 8 | **LSTM ZVD** (Wagstaff) | Foot (200 Hz train, 125 Hz transfer) | 6 layers × 80 units + FC | confidence threshold **0.85** to suppress false positives | Hallway ARMSE **0.97 m** vs 2.48 m for best fixed-threshold SHOE (**−32.6%**); stair loop-closure 0.269 m vs 1.75 m (SHOE) / 3.081 m (ARED). Transfer to a new IMU costs accuracy: 2.17 m → 1.51 m after retraining (**−18.4%**) | Inference **3.35 kHz** on an Intel i7-6700HQ CPU (i.e. ~0.3 ms/sample) | same; code [utiasSTARS/pyshoe](https://github.com/utiasSTARS/pyshoe) |
| 9 | **LSTM ZVD** (earlier version) | Foot | LSTM replacing threshold detector | – | **34%** reduction in 3D position error vs fixed-threshold detectors over 7.5 km, 5 subjects, walk/run/stairs/crawl/ladder | – | [arXiv:1807.05275, IPIN'18](https://arxiv.org/abs/1807.05275) |
| 10 | **Double-threshold + pseudo-ZV re-detection** | Foot (100 Hz) | gyro magnitude + sliding re-detection | ω_threshold = **0.6 rad/s**; re-detect window **T_data = 10 samples = 0.10 s** | Step-detection accuracy **63.40% → 90.46%** (T_data = 10 or 20); T_data = 5 gives only **81.31%**. ~23.7% overall accuracy gain at 3–6 km/h | Adds T_data (0.1 s) confirmation delay | [Zhao, MASc thesis, U. Windsor 2020](https://uwindsor.scholaris.ca/bitstreams/5f7da953-f313-4518-8157-20e8dcd3bd84/download) (journal version IEEE Sens. J., paywalled) |
| 11 | **STD-threshold ZUPT gating a learned odometer (DeepOdo)** | Car + smartphone (50 Hz, EKF at 1 Hz) | per-axis std-dev of accel **and** gyro over a moving window | "lower than the empirical threshold T" — **T and window length are not published** | System-level: **73.14% / 98.33%** horizontal / vertical improvement vs NHC-aided IMU | Not reported | [IEEE TIM 72 (2023), OA copy](https://ira.lib.polyu.edu.hk/bitstream/10397/99370/1/Wang_Novel_Deep_Odometry.pdf) |
| 12 | **Smart-device cyclist *starting*-movement detector** | **Bicycle**, phone/smartwatch on rider, accel+gyro **100 Hz** | sliding windows **0.1 s and 0.5 s**; features over **0.2 s and 0.8 s**; polynomial fit over **0.64 s** (10th order); output averaged over last **0.1 s** | probability threshold swept | **F1 = 80% at mean detection time 0.16 s.** Precision explicitly low: "many false positives" from cyclists fidgeting while waiting (positioning the pedal, seesawing between legs). Camera+device ensemble: F1 = 99% at 0.24 s; 49 subjects, 84 starting motions | **0.16 s** mean (start, not stop) | [arXiv:1803.03487](https://arxiv.org/pdf/1803.03487) |
| 13 | **Learned speed regressor with *no* stop detector** | Handheld phone, 100 Hz | CNN over **2 s window** | – | RMSE **0.13 m/s** (10-fold CV), **0.20 m/s** on a held-out sequence. Authors report **"slight leaking towards higher speeds"** during standstill. Path RMSE: no constraint **238.38 m**, constant 0.75 m/s pseudo-speed **0.87 m**, CNN speed **0.62 m** | – | [arXiv:1808.03485](https://arxiv.org/pdf/1808.03485) |
| 14 | **MoE learned inertial odometry for bicycles** | **Bicycle**, smartphone on handlebar; >25 h, 8 riders, multiple bikes, paved+unpaved | MoE velocity predictor + error-state EKF; velocity updates every **0.1 s**; NHC (zero lateral/vertical velocity) | – | **0.333 m/s** velocity error, **9.49 m ATE**, **2.58 m RTE**, **28.76 M FLOPs** (≈7×/9× fewer than LLIO/TLIO backbones) | – | [arXiv:2510.17604v2, 2026-07-26](https://arxiv.org/pdf/2510.17604v2) |
| 15 | **SHL transport-mode "Still" class** | Phone, various body positions | 5 s windows, 100 Hz downsampled to 50 Hz | – | Overall F1 **0.83** (2019 challenge, general classifier + HMM), **0.82–0.834** (2020). Cross-mount degradation: training on hips + a little hand data gives F1 **0.765** vs 0.71 hand-only. **Per-class "Still" F1 not found** in the text fetched | 5 s window ⇒ ≥5 s latency | [Sensors 22(10):3613, 2022, CC BY](https://pmc.ncbi.nlm.nih.gov/articles/PMC9145859/) |

**Key negative results (all searched, none found):**
- No bicycle- , motorcycle- or e-scooter-specific zero-velocity detector publishing thresholds
  in m/s² or rad/s together with FP/FN rates. Searched "bicycle zero velocity detection IMU",
  "two-wheeler ZUPT", "motorcycle ZUPT inertial", "e-scooter IMU stop", "cycling stop detection
  smartphone". **Not found.**
- No paper measuring **stop**-detection latency for a bicycle in seconds. Row 12 measures
  *start* latency (0.16 s). **Not found.**
- No published spectrum comparing "rolling at ~1 m/s" against "stopped with rider fidgeting"
  for a bicycle. **Not found** — this is an original measurement we would have to make.
- Skog et al., "Zero-Velocity Detection — An Algorithm Evaluation", IEEE TBME 57(11):2657–2666,
  2010, DOI 10.1109/TBME.2010.2060723, 663 citations (OpenAlex, checked 2026-09-05) is the
  canonical SHOE paper but has **no open-access copy**; three fetch routes failed.
  **Its specific numbers are UNVERIFIED and must not be cited.** Use row 4 (Wagstaff et al.
  2019) instead — it restates the SHOE/ARED/AMVD/MBGTD definitions and threshold ranges and
  we did fetch it.

**Repo state (GitHub API, 2026-09-05):** `utiasSTARS/pyshoe` 111 stars, 30 forks, **no licence
declared**, last push 2021-12-17, not archived — reference implementation of SHOE/ARED/AMVD/
MBGTD plus the LSTM detector; read it, do not vendor it (no licence).
`mbrossar/ai-imu-dr` 1001 stars, **MIT**, last push 2025-01-08. `mbrossar/RINS-W` 98 stars, last
push 2020-08-08 (effectively dormant).

---

## 2. Vibration bands

The one hard number for bicycles on real roads: on a granular rough road, **88% of the road
excitation power falls within a 10–50 Hz bandwidth** (Lépine, Champoux & Drouet, *Experimental
Techniques*; PDF fetched from the Cambridge Apollo repository,
DOI [10.17863/cam.12641](https://api.repository.cam.ac.uk/server/api/core/bitstreams/42290fb3-da4d-4352-9240-68d568cd7ccd/content)).
That paper worked in an 8–100 Hz band (the hand-arm sensitive band), 1 Hz FFT resolution,
Hanning window with 67% overlap, fifth-order zero-phase Butterworth band-pass, and reported that
laboratory replication was excellent to 75 Hz with ≤1 dB error in 8–75 Hz.
Crenna et al. (*Eng* 6(9):245, published 2025-09-16, CC BY,
[PDF](https://mdpi-res.com/d_attachment/eng/eng-06-00245/article_deploy/eng-06-00245.pdf))
instrumented bicycle tyres at **1344 Hz** sampling, PSD resolution 0.2 Hz, and found the
significant vibration content extends to 200 Hz with **the main contribution below 100 Hz**;
they cite corroborating studies placing energy below 200 Hz, in 0–100 Hz, and in **0–80 Hz**.
Crucially they fit handlebar RMS acceleration (integrated 0–400 Hz) as
`aRMS = k0 + k1·S + k2·P + k3·W + k4·T + …` over 587 RMS values, R² = 0.944, RMSE 0.260 m/s²,
with **speed sensitivity k1 = 0.101 (m/s²) per (km/h)** — i.e. **≈0.36 (m/s²) per (m/s)** of
extra broadband vibration RMS. Speeds tested were only **25 and 40 km/h**, so extrapolating
that slope to our 1–2 m/s (3.6–7.2 km/h) case is *not* validated by the paper. Zang et al.
(*Sensors* 18(3):914, 2018, CC BY,
[PDF](https://mdpi-res.com/d_attachment/sensors/sensors-18-00914/article_deploy/sensors-18-00914.pdf))
chose **100 Hz** for a bicycle-mounted phone as the balance between "not less than ~15 Hz"
(needed for 300 mm IRI segments at 15.5 km/h) and phone compute, and high-passed at 0.5 Hz to
strip bike sway.

Does band-limited energy beat broadband variance at separating "rolling at 1 m/s" from "stopped
and fidgeting"? **No published bicycle experiment answers this.** The physics argument is that
road-texture excitation frequency scales as `f = v/λ`, so at v = 1 m/s a 10–50 Hz band is
excited by surface wavelengths of **20–100 mm** — exactly asphalt chip/macrotexture scale, so
the band *is* excited at walking pace — whereas at 5 m/s the same band maps to 100–500 mm
features. A rider fidgeting on a stopped bike, and the bike's own frame/rider modes, sit far
lower: pedalling cadence 60–90 rpm is **1.0–1.5 Hz**, and a 700C wheel (~2.17 m circumference)
turns at **0.46 Hz at 1 m/s**. So a 10–50 Hz band-pass should reject fidgeting and pedal
kinematics while keeping the rolling signature. *This paragraph's wavelength/cadence figures are
derived by us from f = v/λ and standard wheel circumference, not quoted from a paper — treat them
as a hypothesis to test, not a citation.* The one directly transferable published data point is
that the closest analogue (Li et al. 2024, row 3) also settled on the **10–50 Hz** region for its
vehicle vibration band, with its decisive peaks at **12.495 Hz and 24.991 Hz**. Note the sign
flips for us: for a car, *stopped* means a strong idle peak appears; for a bicycle, *stopped*
means the band goes quiet. We cannot copy their decision rule, only their band and their
window/update structure.

---

## 3. Latency and hysteresis

The window/latency trade-off is stated explicitly, and quantitatively, in three places. Li et al.
(row 3) chose a **3 s window with a 1 s update** and wrote that a *larger* window causes wrong
stationary decisions at the start and end of a stop because it carries historical dynamics,
while a *smaller* one is more easily corrupted by random disturbances — 3 s was their compromise
for a car that stops for 10–20 minutes. **That is far too slow for our 1 s spec**, and their
scenario (stops of 966 / 1321 / 1212 s) never stressed latency. RINS-W's AMVD baseline used a
**1.00 s** window and its learned replacement is a recurrent LSTM with no window at all — the
recurrent form is what buys RINS-W the 5.7× false-positive reduction at equal recall, because the
hidden state can hold "this vehicle was moving 300 ms ago" without paying a window-length delay.
That is the DVSE/TLIO-style answer to the trade-off: replace the window with recurrent state.
(TLIO and RoNIN themselves do not run an explicit zero-velocity detector; the bicycle-specific
MoE system, row 14, likewise has **no stop detector** — it uses only nonholonomic zero
lateral/vertical constraints. Confirmed by grepping the full text for "zero velocity", "ZUPT",
"stationary", "standstill": no hits.)

For hysteresis, the useful measured result is row 10: a single gyro threshold at 0.6 rad/s gave
63.40% step-detection accuracy; adding a **re-detection confirmation window of 10 samples
(0.10 s at 100 Hz)** raised it to **90.46%**, and shortening the confirmation to 5 samples
(0.05 s) dropped it back to 81.31%, while lengthening to 20 samples gained nothing. So there is
a measured knee: **~0.1 s of confirmation buys most of the false-positive suppression, and more
than that is wasted latency.** Row 12 independently reached the same design — averaging the
classifier output over the **last 0.1 s** to smooth it and suppress false positives — and paid
for it with a mean detection time of 0.16 s, while noting the general rule that filtering false
positives "comes at the cost of reduced detection speed". The best available latency benchmark
for a bicycle is therefore **0.16 s for an 80%-F1 phone-IMU start detector**, giving us a
generous budget against our 1 s target.

---

## 4. What changes our decision

1. **Drop the 3 s window idea; use ~0.5 s of statistic plus ~0.2 s of confirmation.** The only
   3 s-window stop detector in the literature (Li 2024) explicitly justified 3 s by a car
   stopping for 10–20 min and admitted it mis-detects at stop boundaries. RINS-W's car AMVD used
   1.00 s; the cyclist start detector used 0.1–0.8 s features. Budget: 0.5 s window + 0.1–0.2 s
   confirmation ⇒ worst case ~0.7 s, inside the 1 s spec.
2. **Adopt dual thresholds with a ~0.1 s enter-confirmation, and do not make the confirmation
   longer.** Provenance: 0.10 s (T_data = 10 @ 100 Hz) gave 90.46% vs 63.40% single-threshold and
   vs 81.31% at 0.05 s, with no further gain at 0.20 s (Zhao 2020). Make exit-from-stop
   immediate (1–2 samples over the high threshold) — a missed stop is harmless, a false stop
   is not.
3. **Set the false-positive asymmetry explicitly in the tuning objective, because both learned
   detectors in the literature do.** RINS-W thresholds its zero-velocity sigmoid at **0.95**
   (not 0.5) and Wagstaff's LSTM at **0.85**, both stated as false-positive suppression;
   RINS-W's rationale is that a missed stop degrades to ordinary dead reckoning while a false
   stop is incompatible with actual motion. Copy that: pick the operating point by
   "FP ≈ 0 at 1–2 m/s", then accept whatever recall falls out.
4. **Do not port the car AMVD threshold as-is.** RINS-W's grid-search-optimal γ = 1×10⁻³ over a
   1 s window is σ_a ≈ **0.032 m/s²** — but that was a Xsens MTi-300. A phone-grade accelerometer
   at 300 µg/√Hz over a 0–50 Hz band sits near σ ≈ 0.02 m/s² (our arithmetic, not cited), i.e.
   the car-optimal threshold is within a factor of ~1.5 of the S23 Ultra's own noise floor.
   **Action: measure the S23 Ultra's stationary σ_a and σ_ω in the bottle cage before choosing
   any absolute threshold.** This single measurement determines whether a variance rule is even
   viable for us.
5. **Use 10–50 Hz band energy as the primary rolling-vibration feature, and sample ≥ 200 Hz.**
   88% of bicycle road-excitation power is in 10–50 Hz (Lépine et al.), the main bicycle
   vibration contribution is below 100 Hz (Crenna et al. 2025), and the closest vehicle stop
   detector also works in 10–50 Hz (Li et al. 2024). At our measured 418.8 Hz ceiling Nyquist is
   209 Hz, ample; at 100 Hz Nyquist is 50 Hz and the top of the band would sit in the anti-alias
   roll-off — so if we ever downsample to 100 Hz, narrow the band to 10–40 Hz.
6. **Expect the band feature to be weak at 1 m/s and size the threshold accordingly.** The only
   quantified speed→vibration slope is k1 = 0.101 (m/s²)/(km/h) ≈ 0.36 (m/s²)/(m/s) at the
   *handlebar*, 0–400 Hz, fitted only at 25 and 40 km/h (Crenna et al. 2025). Extrapolated,
   1 m/s buys only ~0.36 m/s² RMS over standstill, at a down-tube mount that is stiffer and less
   excited than a handlebar. Plan for a low margin and validate on our own coast-down logs.
7. **Gate the learned speed regressor with the hard detector rather than trusting it to reach
   zero — the literature says regressors leak at standstill.** Cortés/Solin/Kannala report
   explicit "leaking towards higher speeds" during standstill from a CNN with 0.13–0.20 m/s
   RMSE, and the bicycle MoE model's velocity error is **0.333 m/s** — comparable to the 1 m/s
   we must not misclassify. Concretely: clamp regressor output to 0 when the stop detector is
   latched, and take the RINS-W/DeepOdo architecture (detector emits a pseudo-measurement into
   the filter, learned speed emits a separate measurement) rather than fusing them into one head.
8. **Budget for measuring our own FP-while-moving rate, because no source publishes one.**
   Li et al.'s 99.7% is *recall during stops only*; they never report false stops while driving.
   RINS-W is the only source with both (precision 0.996 / recall 0.940 at 100 Hz on a car). Our
   evaluation must therefore be: hours of 1–2 m/s coasting and slow riding logged with a GNSS
   speed reference, reporting false stops per hour — that number does not exist in the
   literature and will be a genuine contribution in the write-up.

---

## Source list (all fetched 2026-09-05)

1. Brossard, Barrau, Bonnabel — *RINS-W: Robust Inertial Navigation System on Wheels* — IEEE/RSJ
   IROS 2019 (Macao), arXiv:1903.02210v2 (rev. 2020-02-28). arXiv non-exclusive licence.
   https://arxiv.org/pdf/1903.02210 — LSTM detector for zero velocity / zero angular velocity /
   zero lateral & vertical velocity on a car, vs a grid-search-optimal AMVD. *Use:* copy the
   0.95 sigmoid threshold rationale and the precision/recall comparison as our baseline target.
2. Wagstaff, Peretroukhin, Kelly — *Robust Data-Driven Zero-Velocity Detection for Foot-Mounted
   Inertial Navigation* — IPIN 2019, arXiv:1910.00529v2. https://arxiv.org/html/1910.00529v2 —
   definitions and per-trial optimal threshold ranges for SHOE / ARED / AMVD / MBGTD, plus a
   6×80 LSTM detector. *Use:* cite the 3-orders-of-magnitude threshold spread as the reason a
   single fixed threshold will not survive our speed range.
3. Wagstaff & Kelly — *LSTM-Based Zero-Velocity Detection for Robust Inertial Navigation* —
   IPIN'18, arXiv:1807.05275. https://arxiv.org/abs/1807.05275 — 34% 3D error reduction over
   7.5 km. *Use:* one-line citation that learned ZVD beats thresholds.
4. Li, Nie, Suvorkin, Rovira-Garcia, Zhang, Xu, Xu — *Stationary Detection for Zero Velocity
   Update of IMU Based on the Vibrational FFT Feature of Land Vehicle* — Remote Sensing 16(5):902,
   published 2024-03-04, DOI 10.3390/rs16050902, CC BY. PDF:
   https://mdpi-res.com/d_attachment/remotesensing/remotesensing-16-00902/article_deploy/remotesensing-16-00902.pdf
   (note: www.mdpi.com returns HTTP 403 to scripted fetches; the mdpi-res.com PDF host works.)
   *Use:* copy the window/update structure and the 15 mg / 0.7 deg/s peak thresholds as a
   starting scale; do **not** copy the decision rule (their stopped-state has an engine idle
   peak, ours has silence).
5. Lépine, Champoux, Drouet — *A Laboratory Excitation Technique to Test Road Bike Vibration
   Transmission* — Experimental Techniques (DOI 10.1111/ext.12058 / 10.1007/s40799-016-0026-8);
   Cambridge Apollo copy DOI 10.17863/cam.12641.
   https://api.repository.cam.ac.uk/server/api/core/bitstreams/42290fb3-da4d-4352-9240-68d568cd7ccd/content
   — the "88% of road excitation power in 10–50 Hz" figure. *Use:* this is the citation that
   justifies our band-pass choice; it is the single most load-bearing number in this document.
6. Crenna, Belotti, Colò, Morettini, Tenerini — *A Measurement System to Characterize the Effects
   of Tires on Bicycle Vibrations* — Eng 6(9):245, published 2025-09-16, DOI 10.3390/eng6090245,
   CC BY. https://mdpi-res.com/d_attachment/eng/eng-06-00245/article_deploy/eng-06-00245.pdf —
   1344 Hz sampling, energy below 100 Hz, aRMS speed sensitivity 0.101 (m/s²)/(km/h), R² 0.944,
   587 samples. *Use:* cite the speed→vibration slope, and cite its 25–40 km/h calibration range
   as the honest caveat on extrapolating to 1–2 m/s.
7. Zang, Shen, Huang, Wan, Shi — *Assessing and Mapping of Road Surface Roughness based on GPS and
   Accelerometer Sensors on Bicycle-Mounted Smartphones* — Sensors 18(3):914, 2018-03-19,
   DOI 10.3390/s18030914, CC BY.
   https://mdpi-res.com/d_attachment/sensors/sensors-18-00914/article_deploy/sensors-18-00914.pdf
   — justifies 100 Hz for a bike-mounted phone and a 0.5 Hz high-pass for sway. *Use:* precedent
   for our sample-rate and de-swaying choices.
8. Bieshaar, Zernetsch, Hubert, Sick, Doll — *Cooperative Starting Movement Detection of Cyclists
   Using Convolutional Neural Networks and a Boosted Stacking Ensemble* — arXiv:1803.03487.
   https://arxiv.org/pdf/1803.03487 — 100 Hz accel+gyro on a rider-carried smart device;
   F1 80% at 0.16 s mean detection time; false positives from pedal-positioning and seesawing.
   *Use:* the only bicycle latency benchmark, and the best published description of exactly the
   fidget-induced false-positive mode we must avoid.
9. Cortés, Solin, Kannala — *Deep Learning Based Speed Estimation for Constraining Strapdown
   Inertial Navigation on Smartphones* — MLSP 2018, arXiv:1808.03485.
   https://arxiv.org/pdf/1808.03485 — CNN, 2 s @100 Hz, RMSE 0.13/0.20 m/s, standstill leakage,
   path RMSE 238.38 / 0.87 / 0.62 m. *Use:* the citation that justifies clamping the regressor
   instead of trusting it at zero.
10. Wang, Weng, Qu, Ding, Chen — *A Novel Deep Odometry Network for Vehicle Positioning Based on
    Smartphone* — IEEE Trans. Instrum. Meas. 72:1–12 (2023), DOI 10.1109/TIM.2023.3240227, 27
    citations. OA copy: https://ira.lib.polyu.edu.hk/bitstream/10397/99370/1/Wang_Novel_Deep_Odometry.pdf
    — the canonical "learned odometer + STD-threshold ZUPT" smartphone architecture, deployed on
    Android. *Use:* architectural precedent; also cite as evidence that the field routinely
    leaves the stop threshold unpublished, which is a gap we can fill.
11. Qiao, Wang, Yang, Yu, Kuang, Niu — *MoE-Based Learned Inertial Odometry for Bicycle
    Localization* — arXiv:2510.17604v2 (2026-07-26), Wuhan University GNSS Research Center.
    https://arxiv.org/pdf/2510.17604v2 — 0.333 m/s velocity error, 9.49 m ATE, 2.58 m RTE,
    28.76 M FLOPs, >25 h / 8 riders, handlebar phone mount, no stop detector. *Use:* the direct
    state-of-the-art comparison for our engine, and the evidence that a dedicated stop detector
    is an open gap in bicycle learned IO.
12. Zhao, T. — *Pseudo-Zero Velocity Re-Detection Double Threshold ZUPT for Inertial Sensor-Based
    Pedestrian Navigation* — MASc thesis, University of Windsor, 2020 (journal version IEEE
    Sensors J., DOI in IEEE Xplore 9391710, paywalled).
    https://uwindsor.scholaris.ca/bitstreams/5f7da953-f313-4518-8157-20e8dcd3bd84/download —
    0.6 rad/s gyro threshold, T_data confirmation-window sweep 5/10/20 samples at 100 Hz.
    *Use:* the measured knee that sets our confirmation window at ~0.1 s.
13. Kalabakov, Stankoski, Kiprijanovska, Andova, Reščič, Janko, Gjoreski, Gams, Luštrek — *What
    Actually Works for Activity Recognition in Scenarios with Significant Domain Shift: Lessons
    Learned from the 2019 and 2020 Sussex-Huawei Challenges* — Sensors 22(10):3613, 2022-05-10,
    DOI 10.3390/s22103613, CC BY. https://pmc.ncbi.nlm.nih.gov/articles/PMC9145859/ — 5 s windows,
    100 Hz → 50 Hz, overall F1 0.83, cross-mount F1 0.71→0.765. *Use:* evidence that
    transport-mode-style "still" classifiers are (a) too slow at 5 s windows and (b) mount-
    sensitive, so they are the wrong tool for a 1 s stop trigger.
14. Repo metadata via GitHub API, 2026-09-05: utiasSTARS/pyshoe (111★, no licence, last push
    2021-12-17); mbrossar/ai-imu-dr (1001★, MIT, last push 2025-01-08); mbrossar/RINS-W (98★,
    last push 2020-08-08).
