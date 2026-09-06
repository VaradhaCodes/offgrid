# The football-ground road — QA of the 00:36/00:39 runs and the collection plan

*(Surveyed as a candidate second road; it became **road 1**, the main training corridor. The road called route 2 elsewhere in these documents is the longer Circular Road corridor surveyed in `13_ROUTE2_as_ridden_QA.md`.)*

Route: OSM ways 547215901 + 547215900, south edge of the Football Ground between Hostel 2B (A, 28.52268, 77.57398) and the Indoor Sports Complex junction (B, 28.52154, 77.57159). Path 316 m, straight-line 266 m, ~100–115 s at 3 m/s. Shape: short straight from A, a right-hand S-bend near Hostel 2C, then a long left arc (~110° of heading change over ~180 m) into B. Both directions sit on the OSM road. Map: docs/figures/route2_tracks.png.

## QA (both runs PASS)
| | AB run1 (00:36) | BA run2 (00:39) |
|---|---|---|
| acc/gyr | 420 Hz, 0 gaps | 420 Hz, 0 gaps |
| mag / baro | 100 / 25 Hz | 100 / 25 Hz |
| GNSS | 145 fixes, acc 3.8 m, ≥ 29 sats | 127 fixes, one 1.5 s gap, acc 3.8 m |
| ride / mean speed | 115 s / 3.0 m/s | 98 s / 3.3 m/s |
| max |a| | **93.9 m/s² at t = 81 s (42 samples > 30 m/s²): a hard impact** | 22 m/s² |
| gravity at start calib | (−1.29, 8.89, 4.11): ~6° roll off the earlier runs | (0.51, 8.99, 4.06) |
| start→end gravity change | 4.4° | 2.8° (2–2.5° in the earlier runs: mostly the bike leaning differently at rest) |
| battery | 52 → 51 % | 51 % |
geomagrot is absent on this phone (expected). Anchor distances agree to 0.1 m between directions.

Actions: check the tape after the 81 s impact of run1 and re-seat the phone once, then do not touch it for the rest of the session. Keep run1 in training only if the model's per-run alignment absorbs the roll offset (it should); mark it "impact" in the notes. Charge the phone.

## How many runs on this route
Target 16 runs = 8 round trips (~55 min incl. calib and turnaround). Minimum 12 = 6 round trips. The two runs already done count as 2 training runs if the mount is not re-taped; if it is re-taped, they become extra pilots.

| Round trip | A→B | B→A | Purpose |
|---|---|---|---|
| 1 | normal | normal | train |
| 2 | normal | slow | train |
| 3 | brisk | brisk | train |
| 4 | accelerate–coast–brake twice | normal with a 3–5 s full stop mid-route | train |
| 5 | normal with a stop at a different spot | slow | train |
| 6 | normal, stand on the pedals for 5 s once | normal | validation (both) |
| 7 | normal | normal | **locked test** |
| 8 | normal | normal | **locked test** |
Then Sunday dawn: 1–2 fresh demo rides at normal pace with the outage zone armed.

Rules: toggle AB/BA before every run; 15 s still at both ends, feet down, no touching; ride the pace you will use in the video for "normal"; note anything odd (dog, pedestrian, bump) in the notes field or on paper.
