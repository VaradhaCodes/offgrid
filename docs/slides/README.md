# SIH 2026 idea submission

Six slides, submitted 6 September 2026.

**[SIH2026_OFFGRID_26168.pdf](SIH2026_OFFGRID_26168.pdf)** — the deck as submitted.

| Page | |
|---|---|
| 1 | [Title](pages/1_title.png) — Problem Statement 26168, "AI-ML based Intelligent Dead Reckoning System for seamless navigation", Smart Vehicles, Software, Team OFFGRID |
| 2 | [Proposed solution](pages/2_proposed_solution.png) — the problem, what we do about it, what makes it different |
| 3 | [Architecture](pages/3_architecture.png) — IMU to filter and alignment to speed CNN and heading, fused under a GNSS quality gate |
| 4 | [Working prototype](pages/4_working_prototype.png) — record, prepare, train, validate, and the app running a real outage |
| 5 | [Viability and impact](pages/5_viability_and_impact.png) — feasibility, next steps, benefits |
| 6 | [Research and references](pages/6_research_and_references.png) — the eighteen sources behind the design |

## Where the slide artwork comes from

Slides 2–6 are full-slide figures generated from this repository, not drawn by hand. The source is in [`../diagrams/rebuilt/`](../diagrams/rebuilt/): `build_*.mjs` writes self-contained HTML with the fonts embedded, `render_*.mjs` exports it at 3840 px wide through headless Chrome, and the `*_NOTES.md` files record, claim by claim, which document or source file each number on each figure comes from and what it does *not* assert.

Full-resolution copies of the five figures are in [`../figures/`](../figures/).

`../diagrams/OFFGRID_technical_approach_slide.pptx` is a separate single-slide technical-approach deck built earlier from the same material; it is kept for the record and is not part of the six-slide submission.

## A note on the numbers

The figures state held-out results, and the notes files say which split produced each one. Two figures carry demonstration numbers rather than held-out ones and label them as such:

- **17.3 m after 569 m** is an on-device replay of road-2 run 4 — a *training* ride, replayed with live online alignment through a declared outage band. It shows what the app does, not what it generalises to.
- The held-out results are the ones in the [main README](../../README.md) and in [`../11_ENGINE_RESULTS.md`](../11_ENGINE_RESULTS.md).
