# Slide figures for the SIH 26168 deck

Two figures, one per slide. Both are 3840 × 1600 px (2.4 : 1), sized for the content band of a
16:9 slide under a title. Insert the PNG file itself into PowerPoint (Insert → Pictures), stretch it
to the full slide width, and turn off "Compress pictures" on save. Do not paste a screenshot of it.

Font is **Calibri** (the deck's own font), so the figure and the slide text match.

| File | Slide |
|---|---|
| `01_technologies_methodology.png` | **Current slide 1.** Technologies + methodology, rebuilt for a 15-second read: one headline, a 5-box spine, GNSS and road data feeding the filter from below, then a build-process strip and a tech-stack panel. Source `src/slide_c.py` → `src/render2.sh C_tech_method`. |
| `01_architecture.png` | *Superseded by the above.*  Technical approach. Inputs → estimation (resample/align, speed CNN, heading filter, GNSS quality gate, corridor recognition) → fusion filter → navigation screen and logs. Tech stack bottom right. |
| `02_working_prototype.png` | Working prototype. Left: Ride, Log, 30 rides, Train and test. Right: three real app screens — locked with the test band ahead, dead reckoning through the 120° turn, re-lock reveal with the miss distance. |
| `phone/*.png` | Clean app screenshots (status bar cropped) from an on-device replay of route-2 run 4, plus the engine sheet and the logger tab. |
| `old/` | The 5 Sep versions (different font and layout), kept for reference only. |

## Numbers on the figures, and what they are

- **drift 1.52 % median · 5.73 % worst · 10 of 10 under 10 %** — held out on road 2, 10 rides,
  road-2 model under leave-one-ride-out, corridor mode, GNSS withheld from 30 s after motion start
  (600–850 m outages). Source: `docs/11_ENGINE_RESULTS.md`, step 11.
- **off by 17.3 m after 569 m** — the on-device replay of route-2 run 4 (a training run) with the
  200→780 m band, live alignment. A demonstration figure, not a held-out result (`docs/16`, §4).
- **matches the Python reference to 7 mm** — the Kotlin engine on the maths path with the same inputs
  (`docs/16`, §3.1). The raw phone path differs by a few metres because the phone aligns online.
- 419 Hz IMU, 0.07 ms model, 0.16 ms tick, 57 k parameters, 240 KB: `docs/12`, `docs/16`.

## Editing

`src/slides.py` generates both HTML files; `src/render2.sh A_architecture` (or `B_prototype`) renders
the PNG with headless Chrome at 2×. Add `audit` as the second argument to outline any box whose text
overflows in red before you render the final. Drop a photo at `src/img/bike.jpg` and the Ride tile
uses it instead of the pictogram.
