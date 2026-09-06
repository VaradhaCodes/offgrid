# Route 2 — SNU corridor (A <-> B), longer loop

Collected 2026-09-05 03:03–04:30 IST. Bicycle (roadeo_1), down-tube mount,
rider_1, Samsung SM-S918B / Android 16, IDR Logger v1.0.0.
Pulled from device via adb from
`/sdcard/Android/data/com.snu.idrlogger/files/sessions/` — 12 sessions.

## Layout

    sessions/        all 12 raw session folders (engine reads these)
    manifest.csv     per-run QC table
    qc_route2.py     regenerates the table below
    README.md

The phone-exported zips of the same sessions are not tracked in git: `run2`/`run3`
are the app's own exports and the other 10 were rebuilt locally from the pulled
folders in the same format. All 12 were verified CRC OK, 22 files each,
byte-identical to the device. `run2`/`run3` were already present locally before
the pull and were confirmed byte-identical, so nothing was overwritten and the
existing `data/speed_model/pred/xfer_r1_to_r2_*` outputs built on them remain
valid.

## Kept set — 5 pairs, 10 runs

| pair | A->B | B->A |
|---|---|---|
| 1 | run2 | run3 |
| 2 | run4 | run5 |
| 3 | run6 | run8 |
| 4 | run9 | run10 |
| 5 | run11 | run12 |

## Excluded — both false starts, neither ever rode

- **run1 (AB)** — stopped 6.1 s into the opening 15 s calibration.
- **run7 (BA)** — stopped 4.3 s into the opening 15 s calibration.

Both jump straight from `CALIB_START` to `STOP_CALIB_START` with **no
`CALIB_END` and no `RIDE_START`**; ride duration 0.0 s. run1 was retaken as
run2, run7 as run8.

## Corridor

    route 2:  A = 28.525931, 77.570662    B = 28.527136, 77.577254   657.8 m
    route 1:  A = 28.522682, 77.573993    B = 28.521544, 77.571602   265.7 m

Distinct corridor — route-2 A is 486 m from route-1 A, route-2 B is 832 m from
route-1 B, and the leg is 2.5x longer. **Caveat:** `route_id` inside
`session.json` still reads `SNU_AJB` for both routes; the app was not
reconfigured between collections. Separate them by folder or by date/time
(route 1 = 00:36–01:28, route 2 = 03:03–04:30), never by `route_id`.

Rides are 207–291 s (vs 65–115 s on route 1), so route 2 gives ~2.5x the
free-running dead-reckoning time per run.

## Data quality (all 12)

- `status = COMPLETE`, no truncated files
- acc + gyr at **418.8 Hz**, **0 dropped samples**, **0 gaps > 50 ms**,
  max inter-sample dt 2–3 ms
- GNSS ~1 Hz, mean horizontal accuracy 3.79 m, 236–320 fixes per kept run
- `geomagrot` absent on this device (expected; `rotvec` + `gamerot` present)
- Endpoint offsets 0.0–5.9 m on every kept run except the first pair
  (run2 end 22.7 m, run3 start 26.4 m — that pair's B turnaround was ~25 m
  short of where the later pairs stopped)

## Mount stability — one caveat on run2

Mount pitch from the mean gravity vector over each static calibration window.
Runs 3–12 are exceptionally stable: start calib 22.26–22.98°, end calib
21.49–23.41°, start-to-end drift under 1.1° on every run.

**run2 is the exception.** Its *start* calib reads **43.05°**, ~20° off every
other run. But its end calib reads 26.10° and its pitch through the ride is a
steady 24.6–26.8°, so **the ride itself is good** — only the opening 15 s
static window is contaminated, i.e. the phone/bike was not yet settled when
logging began. Use run2's ride, but **do not use its start-calib window for
gyro-bias or initial-attitude estimation**; fall back to its stop-calib window.

Note run2 still rode ~3° steeper than runs 3–12 (~26° vs ~22.5°), so it is a
mildly different mount pose regardless.

Regenerate the base table with `qc_route2.py`.
