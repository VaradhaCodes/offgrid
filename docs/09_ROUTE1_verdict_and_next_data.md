# Route 1 verdict (20 runs, 5 Sep 00:36–01:28) and what to collect next

## Verdict: route 1 is a good training and demo road
Evidence from the 20 kept runs (`data/route1`, manifest `data/route1/manifest.csv`; engine outputs in `data/processed/`):
- Speed diversity came naturally: run means 3.0–5.0 m/s, peaks to 7.4 m/s, rides 65–115 s. Vibration RMS scales cleanly with speed across runs (2.1–2.7 m/s² at ~3.3 m/s, 3.2–4.0 at ~4.6 m/s).
- No speed-breaker signature: impacts > 30 m/s² only in run1 (3 places) and run3 (1 place) at inconsistent positions, i.e. the mount settling in the first rides, not a fixed bump. Runs 4–21 peak at 20–30 m/s².
- Heading content: S-bend (~50°) plus a ~110° arc; net heading change is near zero, so an uncorrected heading error shows up clearly in the path. Both directions lie on the OSM road (ways 547215901 + 547215900).
- Learnability: leave-one-run-out proxy model (gradient boosting on hand features, no CNN yet), GNSS cut 10 s after the start, ~280 m outage covering the S-bend and the arc:

| Metric (20 held-out runs) | ML speed + gyro heading | last speed held |
|---|---:|---:|
| speed MAE while moving, median | 0.26 m/s | 0.24 m/s at the cut only |
| endpoint drift, median | 5.7 % (15.6 m) | 11.7 % (32.5 m) |
| runs under the 10 % target | 16 of 20 | 8 of 20 |
| worst run | 16.9 % (run17) | 43 % (run13) |
| error after the bike stops, median | 16 m | 96 m |

The four runs above 10 % (run13, 17, 19, 21, all B→A) share one cause found afterwards: **the gyro bias taken from the 15 s "stand still" window was contaminated by the rider slowly turning the bike (up to 7° in 15 s)**. That mis-estimated bias by 0.2–0.5°/s, which is 12–30° of heading over a 60 s outage. The gyro itself is fine (end-of-ride windows agree to < 0.1°/s where the rider held still). Fixes: (1) protocol: during both 15 s windows hold the brakes and do not rotate the bike or handlebar at all; (2) engine: motion-rejecting bias estimate (added to `engine/ml_rectify_demo.py`), and in the real filter the bias is estimated continuously from GNSS bearing while GNSS is healthy, so the demo cut should come 30–40 s into the ride, not 10 s. Re-run of the CV with the robust bias at 10 s and 30 s cuts: `data/processed/_loro_cv_cut10.png`, `_loro_cv_cut30.png` (pending at the time of writing).

Weaknesses of route 1 for the demo: no junction (no map-matching decision), no mid-route stop in any run (the ZUPT behaviour is never exercised), and the arc begins immediately at the B end, so B→A starts are harder for heading initialisation. Demo direction should be A→B (straight first, then S-bend, then arc).

## Next data, in priority order
1. **Route 1, daytime fresh session (Sat afternoon): 2 round trips = 4 runs**, normal pace, both windows truly still. These are the locked test set and the demo rehearsal at a different time of day and satellite geometry.
2. **Route 1 behaviour runs: 2 round trips = 4 runs** with (a) one full 5 s stop mid-route at different spots, (b) one slow crawl at 1–2 m/s, (c) one accelerate-coast-brake run. The current data has no stops and thin coverage below 2 m/s; the demo's "marker stops when the bike stops" moment needs (a).
3. **Route 2, a different road: 3–4 round trips = 6–8 runs**, used as an unseen-road test (train on route 1, test on route 2) and optionally 2 of them for fine-tuning. Preferred candidates, pending the speed-breaker check by the rider: (i) the A→J→B academic corridor, 487 m straight + 90° junction turn + 325 m, which adds the junction decision the video lacks; (ii) the Circular Road arc round Blocks A–D, ~590 m with three ~45° bends. Avoid roads with breakers; one breaker at a fixed position is tolerable if it is annotated.
4. Optional stress runs, never in training: one run with the phone deliberately re-taped ~10° off, one run with the phone in a handlebar holder. These back the "mount-agnostic alignment" claim in the writeup.
Total additional riding: ~1 h.

## Update: CV re-run with the motion-rejecting bias (5 Sep 03:00)
| Cut point | Outage (median) | ML runs under 10 % | ML drift median / worst | last-speed under 10 % / median | heading err median / worst | after-stop ML vs last |
|---|---|---|---|---|---|---|
| 10 s after start | 280 m / 73 s | 16 / 20 | 3.7 % / 21.2 % (run12) | 7 / 20, 13.5 % | 2.0° / 14.5° | 10.9 m vs 101.6 m |
| 30 s after start | 194 m / 53 s | 17 / 20 | 5.5 % / 19.1 % (run15) | 3 / 20, 18.7 % | 2.7° / 10.1° | 11.2 m vs 97.1 m |
The remaining bad runs (12, 15, 17) are the ones where the rider moved during the whole 15 s stand, so no static estimate can recover the bias; the replay does not yet estimate bias from GNSS bearing before the cut (next engine step, `engine/loro_cv.py replay()`), which is what the real filter does. Files: `data/processed/_loro_cv_cut10.png`, `_loro_cv_cut30.png`, `_loro_cv_summary_cut{10,30}.csv`.
