# Route 1 — SNU_AJB corridor (A <-> B)

Collected 2026-09-05 00:36–01:28 IST. Bicycle (roadeo_1), down-tube mount
(`downtube_tape_v1`), rider_1, Samsung SM-S918B / Android 16, IDR Logger v1.0.0.

Pulled from device via adb from
`/sdcard/Android/data/com.snu.idrlogger/files/sessions/`.

## Layout

    sessions/        all 21 raw session folders (engine reads these)
    manifest.csv     per-run QC table
    qc_route1.py     regenerates the table below
    README.md

The phone-exported zips of the same sessions are not tracked in git: `run1`/`run2`
are the app's own exports, byte-identical originals, and `run3`–`run21` were
rebuilt locally from the pulled folders in the same format. All 21 were verified
CRC OK, 22 files each, byte-identical to the device before the folders here were
taken as canonical.

## Kept set — 10 pairs, 20 runs

| pair | A->B | B->A |
|---|---|---|
| 1 | run1 | run2 |
| 2 | run3 | run4 |
| 3 | run5 | run6 |
| 4 | run7 | run9 |
| 5 | run10 | run11 |
| 6 | run12 | run13 |
| 7 | run14 | run15 |
| 8 | run16 | run17 |
| 9 | run18 | run19 |
| 10 | run20 | run21 |

## Excluded

**run8 (B->A)** — aborted. 31.1 s of riding vs ~85 s typical; last GNSS fix
218.9 m short of endpoint A. Retaken as **run9**, which is clean.

## Data quality (all 21)

- `status = COMPLETE`, no truncated files
- acc + gyr at **418.8 Hz**, **0 dropped samples**, **0 gaps > 50 ms**,
  max inter-sample dt 2–3 ms
- GNSS ~1 Hz, mean horizontal accuracy 3.79 m, 60–145 fixes/run
- `geomagrot` absent on this device (expected; `rotvec` + `gamerot` present)
- 15 s static calibration at both start and end of every run

## Mount-stability check

Mean gravity vector over the 15 s start calibration, split into
**pitch** (phone angle along the down tube — the real mount geometry) and
**roll** (lateral bike lean while standing still — not a mount property).

Pitch across runs 3–21 excluding 8: mean **25.49°**, sd **0.91°**, range 23.01–27.14°.

- run1 = 24.84° (−0.72 sd), run2 = 24.31° (−1.30 sd) — both inside the normal
  band; run3 (23.01°) sits further from the mean than either. No detectable
  remount between run2 and run3.
- run8 = 27.52° (+2.23 sd), the largest outlier, matching the reported
  mid-run reposition. run9 returns to 25.92°.

Endpoint offsets are 0.1–4.6 m for every kept run (A<->B straight line 265.7 m).

Regenerate the table with `qc_route1.py`.
