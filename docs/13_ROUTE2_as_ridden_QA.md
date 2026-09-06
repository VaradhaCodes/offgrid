# Route 2 as ridden (teammates, Sat 5 Sep 03:09 / 03:17) — QA and green light

Ridden route differs from the A→J→B card: B (Shivaji park end, 28.52591, 77.57071) → Cricket Ground road east → library junction J → 2011 Street → ~105° left onto Circular Road → north ~480 m → the ring's top curve → C (28.52711, 77.57702). Path 853 m, straight-line 632 m, 250–290 s at 3.4–4.0 m/s. OSM ways: 547215917 + 369149867 (2011 Street) + 369151490 (Circular Road). Engine polyline: `data/map/corridor_route2.geojson` (906 m incl. small overhang); both tracks within median 1.1–1.6 m, max 8 m of it. Map: `docs/figures/route2_as_ridden.png`.

Verdict: GREEN. Better demo road than route 1: 440 m straight, one sharp junction turn, 480 m straight, a gentle arc at the end. Outage can be 400–500 m.

| | AB run2 (03:09) | BA run3 (03:17) |
|---|---|---|
| IMU / GNSS | 420 Hz, 0 gaps / 320 fixes, 3.8 m, ≥ 28 sats | 420 Hz, 0 gaps / 281 fixes, 3.8 m, ≥ 26 sats |
| ride | 291 s, mean 3.4 m/s, max 5.3 | 251 s, mean 4.0, max 5.3 |
| impacts > 30 m/s² | 0 (max 26) | 7 samples (max 34) |
| **mount pitch in the cage** | **43.8° (route 1 was 25.5 ± 0.9°)** — phone seated very differently | 23.2°, roll 11° (route 1 roll ≈ 0 ± 4°) |
| **bike rotation during the start stand** | **+22.7° (rider turned the bike)** | −0.1° (perfect) |
| end stand rotation | −2.1° | −0.2° |

Mount: the phone is wedged in the bottle cage (photo, KROSS bike). It held route 1 to ±1° because one person seated it the same way every time. Run2 shows what happens otherwise: 18° of pitch difference. Per-run alignment absorbs a fixed offset, but seat it the same way every run: push it fully down until it stops against the cage bottom, screen facing the same side, and do not touch it during the session. Confirm the same bike and cage are used for route 1 and route 2.
Stand: brakes held, no turning the bike or bars, for all 15 s at both ends (run2's +22.7° is exactly the failure mode that produced the bad route-1 runs).
Session metadata still says vehicle roadeo_1 / mount downtube_tape_v1 / rider_1: set the rider field per rider; the vehicle/mount labels are wrong but harmless (fix in the app defaults later).
