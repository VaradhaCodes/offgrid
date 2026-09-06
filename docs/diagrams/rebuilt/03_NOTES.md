# Feasibility and impact — final wide revision

Export: 3840 × 1584 PNG, 1600 × 660 design canvas. This is a wide content panel for placement beneath a PowerPoint heading. Preserve its aspect ratio when inserting it. Font: embedded Barlow. Previous tall version preserved in previous/03_before_wide_revision/.

## Evidence

- **Runs on the phone:** docs/16_APP_RESULTS.md and the deployed model export document approximately 240 KB and 10 Hz execution. The app replays recorded sessions on-device; the indoor live benchmark establishes runtime frequency rather than field positioning accuracy.
- **Corridor replay evidence:** docs/11_ENGINE_RESULTS.md, joint model grouped five-fold evaluation, holds out round-trip pairs. At the 30-second GNSS cut, route-2 corridor mode with fixed scale achieves 2.33% median and 6.26% worst drift; all 10 held-out runs are below 10%. This is simulated GNSS blackout evaluation on recorded rides, not new completed-app field validation. The slide explicitly identifies corridor replay and route 2.
- **Works offline:** docs/16_APP_RESULTS.md documents local LiteRT inference and the bundled PMTiles base map. The online satellite view is optional and distinct from the offline base map.
- **Next steps:** broader vehicle/phone training and further refinement of calibration and road constraints are future work addressing domain transfer and accumulated drift. No completed cross-vehicle phone deployment is implied.
- **Potential benefits:** continuity, delivery reliability, emergency position awareness, adoption cost and environmental outcomes are intended benefits inferred from the problem statement and prototype capabilities. Operational savings and emissions effects have not been measured.

## Visual review

Inspected the wide render at 1280 × 528. No clipping or overlapping text. Minimal outer margins. Five points per box, with measured capability and future work separated on the left; potential benefits labelled on the right.
