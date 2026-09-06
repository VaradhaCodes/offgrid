# Data

Everything the results are built on. 30 quality-controlled bicycle rides — 71 minutes, 15.0 km — on two roads at Shiv Nadar University, Greater Noida, each ridden in both directions with a Samsung Galaxy S23 Ultra in the bottle cage of the bike. GNSS was recorded throughout every ride and is the reference; the engine's outages are produced by withholding it from the estimator, never by turning it off.

This directory is about 1.4 GB. If you only want to look at the results, `qa/` and `speed_model/` are small; the bulk is raw sensor CSV under `route1/` and `route2/`.

## Layout

| | |
|---|---|
| `route1/` | 21 recorded sessions, 20 kept. The football-ground road, 316 m, ridden 00:36–01:28 on 5 Sep 2026. |
| `route2/` | 12 recorded sessions, 10 kept. The Circular Road corridor, 853 m, ridden 03:03–04:30 on 5 Sep 2026. This is the demo road. |
| `raw/` | The two pilot rides of 4 Sep and the logger acceptance test, before the routes were fixed. |
| `processed/` | Per session: the uniform 100 Hz `track_100hz.csv`, `gnss_fixes.csv`, the fitted `align.json` and an overview plot. Regenerate with `engine/decode_session.py`. |
| `qa/` | The output of the evaluation harness. Per-run QA tables and flag lists, alignment and heading tables, every `filter_*` sweep, the IO-VNBD runs, and `replay/` — the 10 Hz conformance references the Android engine is tested against. |
| `speed_model/` | Trained models (`.pt`, `.onnx`, `.tflite`, plus the export JSON with the normalisation constants), the windowed training arrays as `.npz`, per-session held-out predictions under `pred/`, and `results.csv` — every model in the sweep on the same labels. |
| `map/` | Corridor polylines, the campus road graph from OpenStreetMap, building footprints and the campus boundary. |
| `field/` | Device replays pulled off the phone, the 10-minute live bench, and video replays. |

## Session format

Each session folder is one ride and holds 21 CSV streams plus `session.json`. Every row carries `t_ns`, the phone's monotonic `elapsedRealtimeNanos`. **Join streams by `t_ns` only, never by row index.** The formats are documented in `docs/01_APP_SPEC_logger.md` and parsed by `engine/session.py`.

The ones that matter: `acc.csv` and `gyr.csv` (418.8 Hz, zero dropped samples and zero gaps > 50 ms across all 33 sessions), `gnss_fix.csv` (~1 Hz, 3.8 m mean horizontal accuracy), `gnss_status.csv` (per-satellite C/N0, used for the outage gate), and `events.csv`, which marks the protocol: `CALIB_START`, `CALIB_END`, `RIDE_START`, `RIDE_END`, `STOP_CALIB_START`, `STOP_CALIB_END`.

Every ride is bracketed by a 15-second stationary stand at each end. Those windows are where the gyro bias and the mount attitude come from, and they matter more than they look — see `docs/09_ROUTE1_verdict_and_next_data.md`.

`geomagrot` is absent because the S23 Ultra does not expose `TYPE_GEOMAGNETIC_ROTATION_VECTOR`. The magnetometer is recorded but never used: the bike frame is steel.

## What was excluded, and why

Nothing was dropped silently. `qa/route1_flags.md` and `qa/route2_flags.md` list every warning on every run with the reason attached.

- **Road 1, run 8** — aborted. 31 s of riding against ~85 s typical, last fix 219 m short of the endpoint. Retaken as run 9.
- **Road 2, runs 1 and 7** — false starts. Both stopped a few seconds into the opening calibration and never rode; 0.0 s ride duration.

Three runs carry findings rather than exclusions: road-1 runs 12, 15 and 17 had the rider slowly rotating the bike during the stand, which poisoned the static gyro-bias estimate. They stay in, and the engine was changed to cope.

## Two traps

**`route_id` inside `session.json` reads `SNU_AJB` for both roads.** The logger was not reconfigured between the two collections. Separate the roads by folder, or by time (road 1 = 00:36–01:28, road 2 = 03:03–04:30) — never by `route_id`.

**`rider_id` reads `rider_1` on every session,** because the field was never changed. A rider-held-out evaluation is therefore impossible on this data. Cross-road transfer, which also crossed an 18° change in how the phone was seated, is the held-out-condition test that could be run.

## Not in this repository

**Phone-exported zips** (`route1/zips/`, `route2/zips/`) are byte-identical archives of the same session folders and are not tracked.

**IO-VNBD**, the external vehicle benchmark used to show the engine on a non-phone IMU, is a third-party dataset and is not redistributed here:

```bash
git clone https://github.com/onyekpeu/IO-VNBD.git data/external/IO-VNBD
```

Then `.venv/bin/python engine/iovnbd.py` reproduces `qa/iovnbd_Vfa01.csv` and `qa/iovnbd_Vfa02.csv`.

**Decoded IMU tables** (`processed/*/imu_native.csv`, 178 MB) are a straight decode of the `acc.csv` and `gyr.csv` that sit right beside them in `route1/` and `route2/`. Regenerate the whole set with:

```bash
.venv/bin/python engine/decode_session.py data/route1/sessions data/route2/sessions
```

**Raw sensor streams from the desk bench** (`field/bench/*/acc.csv` and friends, ~150 MB) are excluded; the engine outputs, events and log from that bench are kept.

## Licence

Released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Use it, and cite this repository.

Road geometry under `map/` derives from OpenStreetMap (ODbL) and Microsoft Building Footprints (ODbL).
