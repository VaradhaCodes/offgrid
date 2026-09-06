# SIH26168 — Prototype plan (bicycle + Samsung S23 Ultra)

Written: Fri 4 Sep 2026, ~02:00. Hackathon: Sat 5 Sep 22:00 → Sun 6 Sep 10:00.
Status of everything below: PLAN. Nothing has been measured yet. No route recorded, no sensor inventory captured.

Companion files:
- `01_APP_SPEC_logger.md` — the data-collection app, screen by screen, stream by stream.
- `02_ENGINE_architecture.md` — the estimation engine (offline Python first, then Kotlin port).
- `03_REFERENCES.md` — datasets, papers, repos (only verified links).

---

## 0. The two-sentence version

Collect 12–16 clean rides of one fixed campus corridor (A→B and B→A as separate runs) with a phone taped rigidly to the bicycle **down tube**, then train a small model that turns vehicle-frame IMU windows into forward speed, and run it inside a causal filter that is constrained to the road polyline. Evaluate and demo on **fresh rides of the same corridor** with GNSS withheld from the estimator for a predetermined interval, while a separate logger keeps GNSS as the reference.

## 1. What is fixed (decided)

| Decision | Value |
|---|---|
| Vehicle | Bicycle only (Hercules Roadeo, hardtail, front disc). Frame material unknown and irrelevant: the engine will not rely on the magnetometer for heading. |
| Phone | Samsung Galaxy S23 Ultra on One UI 8.5 (Android 16) as the logger/nav phone. Two more phones exist: phone 2 = independent GNSS reference in the rider's pocket running GnssLogger, phone 3 = camera for the demo video. |
| Mount | Down tube, frame-fixed (photo 1 position). NOT the stem/handlebar (photo 2). Cellotape available; wrap fully around tube + phone, not just the sides; pad underneath; bottle cage as slide stop. |
| Route | Shiv Nadar University, Greater Noida (pin 28.524416, 77.573818). OSM coverage is excellent (276 highway ways within 900 m). Candidate corridor A→J→B = OSM ways 369217550 + 547215917: A (28.528955, 77.575448) at the north end of the straight academic road → 487 m SSW → J (28.524890, 77.573604) at 2011 Street / Central Library, 57 m from the bike parking → 90° right → 325 m WNW → B (28.525982, 77.570515) near Shivaji park. 812 m total; can be shortened by starting 200 m south of A. Polyline saved in data/map/corridor_AJB.geojson, map in docs/figures/campus_candidate_corridors.png. Alternative: Circular Road ring (ways 369151490 + 369250382). A→B and B→A are separate runs. |
| Train/test | Train on early traversals, test and demo on fresh traversals of the same corridor. Stated honestly as corridor adaptation. |
| Build machine | This Mac (SDK 35–37 + adb 37.0.1 + OpenJDK 21 already present). APK built here, installed by USB/ADB. |
| Engine order | Python offline engine first (all evaluation happens there), then Kotlin port of the small pieces for the live demo. |

## 2. Mounting — answers

### Handlebar/stem vs frame
Frame (down tube). The handlebar is how a bicycle balances: at low speed the rider makes continuous ±5–15° steering corrections, and in every turn the bar turns more than the frame yaws. A gyro on the stem therefore measures steering + heading; a gyro on the frame measures heading + lean. Lean (roll) is actually useful: on a bicycle, roll ≈ atan(v·yaw_rate/g), which gives a free consistency check between speed, turn rate and roll. Photo 2 (phone on top of the stem/steerer) is the wrong place for the core dataset. Photo 1 (phone flat on the down tube, screen out) is the right place.

### Down tube specifics from the photos
- The tube is round and narrower than the phone. Taped directly, the phone will rock about the tube axis and rattle. Put a pad between phone and tube: a strip of foam, folded cloth, or a few layers of cardboard, so the phone back sits on a flat surface. Then tape three bands (top, middle, bottom) plus one long strip along the tube. Electrical tape over duct tape is fine; a rubber band under the tape reduces slip.
- Take the Coke can out of the bottle cage and butt the bottom edge of the phone against the top of the cage. That is a mechanical stop against sliding down under braking. If the phone is too long for the gap, mount it just above the cage and use the cage as the stop anyway.
- Keep the phone in its case. Do not cover the top edge of the phone with metal or thick tape: the GNSS antenna is at the top on Samsung flagships. Mark the phone's position on the tube with a pen or a tape flag so every session uses the same spot.
- The photo 1 ground is wet. Water on a taped phone is a risk; put the phone in a thin ziplock if it rains.
- Better than tape if a shop is open Friday: a **top-tube bag with a clear phone window** (₹300–600). It is frame-fixed, padded, and repeatable. A handlebar phone holder is NOT better; it rotates with the bar.

### Must the phone be in the same place for training and the final ride?
Yes, same case, same pad, same spot, same tape pattern, same tightness. Reasons in order of importance:
1. The learned speed model reads road vibration and pedalling signature through the mount. Change the coupling and the model sees a different sensor.
2. Within a run the phone must not move at all. Rattling shows up as high-frequency spikes that can clip the accelerometer range.
3. Angles are re-estimated automatically every session (tilt from gravity while stationary, yaw from the first straight acceleration), so a few centimetres of position change or a couple of degrees of angle change are handled by the alignment step. Position change is cheap; angle change is handled; coupling change and rattling are not.

### How much does a small change cost?
- Tilt error left uncorrected: 0.1° → 0.017 m/s² horizontal leak → ~8 m after 30 s of pure double integration; 1° → ~80 m. This is why the engine does not integrate the accelerometer for speed. With a speed model + ZUPT + NHC the accelerometer is a secondary input and tilt error matters far less.
- Yaw (heading) error: 1° over 200 m → 3.5 m cross-track; 5° → 17 m. Map matching to the corridor removes most of this; a 1-D corridor state removes all of it.
- Conclusion: the number that actually decides the demo is the speed-scale error of the model (e.g., 5% speed error over a 300 m outage → 15 m along-track drift, inside the 10% target).

## 3. Route — answers

### A→B + B→A, not a loop
Two directions as separate runs. A loop hides endpoint error (the truth ends where it started). A→B has a visibly different endpoint, so a judge can see the marker arrive at B. Recording the return direction doubles the data on the same asphalt and gives a half-honest generalisation test (train on A→B only, test on B→A).

### Shape
- Length 400–700 m, riding time 2–3 min at 12–18 km/h.
- 60–100 m straight at the start (stationary calibration + GNSS warm-up + first acceleration for yaw alignment).
- At least one clear 70–110° turn; ideally straight → turn → straight → second turn → straight, so heading is tested and the map can correct it.
- One safe place to stop for 3–5 s in some runs.
- A 50–100 m straight after the planned outage window for recovery.
- Low traffic, no need to touch the phone while moving.
- The outage window for the demo: starts after stable motion, contains the main turn, ends on the recovery straight; 100–250 m.

### Start/end distance
Auto-computed by the logger: average the stationary GNSS fixes in the 10–15 s before movement (start anchor) and after stopping (end anchor); geodesic distance between anchors; route length from the cleaned GNSS polyline. Do not aim for a centimetre; use a 5–10 m geofence and keep the actual averaged coordinates per run. Phone GNSS is 3–8 m accurate, so it cannot prove finer repeatability anyway.

### Map source
Check OpenStreetMap for the corridor first (openstreetmap.org, zoom in on campus). If the road is there, export it (osmnx / Overpass) as the road graph. If not: build a small campus road graph by hand from the pilot GNSS run plus a satellite image, label it "campus road graph (self-surveyed)", and do not call it OSM. Optionally add the road to OSM with the iD editor; it becomes public data within a day and the national proposal can then use real OSM.

### Run plan (same bicycle, same mount)
Pilots first: (P1) 2-min stationary on the mount, then rotate the bicycle through 4 headings, 20 s each; (P2) one full A→B→A ride. Inspect files before anything else.

| Split | A→B | B→A | Purpose |
|---|---:|---:|---|
| Train | 5 | 4 | speed model + filter tuning |
| Validation | 1 | 1 | choose thresholds, stop training |
| Locked test | 2 | 2 | never touched until the pipeline is frozen |

Minimum viable if time collapses: 4+3 train, 1+1 val, 1+1 test = 10 runs. Each run ≈ 3.5 min including 15 s stationary at each end, so 16 runs ≈ 1 h of riding.

Variations inside the training runs (keep ~70% "normal riding" because that is what the demo will be):
1. normal pace; 2. slow pace; 3. brisk pace; 4. accelerate–coast–brake cycles; 5. one 3–5 s full stop mid-route; 6. stop at a different spot; 7. one run with a few seconds standing on the pedals (bicycle-specific frame rocking); 8. both directions of everything.

Do the locked test runs in a separate session (Saturday daytime): different satellite geometry, different temperature, more honest. The final demo ride on Sunday is a fresh run.

### Bicycle-specific speed cues the model will exploit (why corridor adaptation works)
- Wheel frequency: a 26–27.5" wheel has ~2.1 m circumference, so 15 km/h ≈ 2 Hz of wheel-periodic vibration. A spectrogram of vertical/lateral accel shows this line moving with speed; it is a near-direct speed measurement when the road is not glass-smooth.
- Cadence: pedalling produces a 1–1.5 Hz lateral/roll oscillation; cadence × gear development = speed while pedalling.
- Road vibration energy rises monotonically with speed on a given surface.
- Lean/yaw-rate/speed consistency in turns.
A small 1-D CNN over 2–4 s windows learns all four without being told. A hand-built "wheel-line tracker" is the explainable backup.

## 4. Same-route honesty — how to say it

Do not claim a different route. The logs, timestamps and split file are the evidence and a judge can ask for them; being caught costs the whole pitch. The honest framing is stronger and the problem statement itself hands it to you: tunnels, underpasses and metro sections are fixed corridors, and a deployed system would adapt to its corridor.

Say: "Public-data pretraining (IO-VNBD) plus device-, mount-, vehicle- and corridor-specific adaptation. All reported numbers are from held-out traversals recorded after the model was frozen, with GNSS withheld from the estimator during the outage interval. We also show the direction-transfer ablation (trained A→B only, tested B→A)."

If asked "did you test on the training route?": "Yes, on fresh rides of the same corridor, the way a metro/tunnel deployment would be commissioned. Cross-corridor generalisation is the next phase and is what the IO-VNBD track is for."

## 5. Timeline (IST)

| When | What | Who |
|---|---|---|
| Fri 02:00–03:00 | This plan. Answer the open questions in §8. Install the two stop-gap loggers (Google GnssLogger + Sensor Logger, see 03_REFERENCES §I) and, if awake, run the P1 stationary test on the down tube with both running. | you |
| Fri morning | Build logger APK on the Mac (target 3–4 h). Buy tape/foam (or a top-tube bag). Confirm corridor on OSM. Magnet test on frame. | me / you |
| Fri afternoon | Install APK by USB. Sensor inventory screenshot. P1 + P2 pilots. Inspect rates, gaps, clipping, GNSS accuracy. | both |
| Fri evening | Main collection: 12–16 runs. Pull data by adb. | you |
| Sat morning | Python: QA → alignment → speed model → filter replay → metrics on validation. Export TFLite. IO-VNBD: run the same pipeline on 2–3 sequences, make plots. | me |
| Sat afternoon | Locked test runs (fresh session). Kotlin port: 1-D corridor DR + small ESKF + TFLite + map UI. Live test on corridor. | both |
| Sat 22:00–Sun 10:00 | Polish, architecture diagram, results slides, demo video, fresh demo ride at dawn. | team |

## 6. Fallback ladder (top = best; drop one rung when a step fails, never skip the data)
1. On-device: ESKF + learned speed + HMM map matching + GNSS gate. Full statement coverage.
2. On-device: 1-D corridor DR (arc-length state along the route polyline) + learned speed + turn-landmark resets. Heading error becomes irrelevant; demo is very robust.
3. On-device: 1-D corridor DR + explainable speed (wheel-line tracker / vibration-energy regression). No neural net.
4. Laptop engine: phone streams sensors over hotspot/USB to Python; phone shows the marker. Sell as "edge engine".
5. Honest replay: a fresh recorded run replayed through the causal engine with the gate; labelled REPLAY on screen.
"Sensor→GPS regression" as a last resort = rung 3's speed model trained against GPS speed; that is the plan, not a hack. Regressing position directly from IMU windows is not on the ladder; it is the same as rung 2 with a worse model and no explanation.

## 7. What the statement requires vs what the prototype shows

| Statement item | Prototype |
|---|---|
| Alignment engine (pitch/roll/yaw to vehicle) | Gravity tilt + first-acceleration yaw, per session, shown as numbers on screen. |
| AI speed + vibration filter | 1-D CNN/GRU on vehicle-frame IMU windows → speed + uncertainty; trained on GNSS speed labels. |
| Map matching + kinematic constraints | Corridor polyline; NHC (v_lat = v_up = 0), ZUPT, road-bearing prior; HMM for the general case. |
| GNSS+INS fusion with AI | ESKF whose speed and process noise come from the model; GNSS gated by accuracy/satellite count. |
| Seamless deficit handler | State machine GNSS+INS → INERTIAL → RECOVERING → GNSS+INS; software gate for simulated denial, labelled SIMULATED on screen. |
| 10 Hz UI | Marker updated at 10 Hz from the filter, GNSS only at 1 Hz. |
| Edge engine on external IMU | The Python engine run on IO-VNBD (car, 10 Hz) with the same code path. |
| IO-VNBD screening plots | Produced Saturday morning from the Python engine. |

## 8. Open questions
Answered Fri 02:30: campus = SNU Greater Noida; no magnet test (dropped); One UI 8.5 / Android 16; Mac is the build machine; 3 phones available; no rain; cellotape only.
Still open:
1. Confirm the corridor A→J→B by riding it once (is the red road open to bicycles, is J a real 90° junction, is B a safe stopping place?).
2. Demo format on Sunday: live ride with the phone showing the marker, or recorded ride + laptop replay? Can the bicycle and corridor be reached from the venue?
3. Models of phone 2 and phone 3.
4. Team size and who rides / who codes.
