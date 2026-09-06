# Proposed solution: full-slide visual

- `00_proposed_solution_content.png` removes only the outer margins. The primary deliverable is the full-slide PNG.
- `00_proposed_solution.png` is the full white 16:9 canvas at 3840 × 2160.
- `00_proposed_solution.html` is self-contained, with embedded Barlow fonts.
- `00_proposed_solution_content.md` contains the exact editable copy.

There is no visible project name, slide title, SIH identifier, page number or footer. The full canvas uses a large solution panel and two supporting panels for the problem and distinctive implementation choices. Ten short bullets, a prominent central explanation and the 10 Hz output identify what the system does.

## Evidence

The problem framing comes from the supplied ISRO problem statement. The smartphone drift issue is also documented in `docs/06_BASELINE_run3.md`.

AI speed estimation, corridor geometry, GNSS gating, and the model uncertainty used in Kalman updates are described in `docs/12_ENGINE_SPEC_for_kotlin.md` and implemented in `IDRNav/engine/src/main/kotlin/com/snu/idr/engine/`. The on-phone runtime and replay demonstration are documented in `docs/16_APP_RESULTS.md`. “AI confidence” is the plain-language label for the speed model's learned uncertainty, which weights its measurement update. It is not a claim that the model supplies certified or universally calibrated confidence.

Phone-only operation refers to runtime sensing and inference. Model training was performed separately. No speedometer, wheel sensor or vehicle computer connection is needed for the bicycle implementation. The slide states no unique-in-the-world, lane-level accuracy or completed car field-test claim.

Design reference: [Microsoft's presentation guidance](https://support.microsoft.com/en-us/powerpoint/tips-for-creating-and-delivering-an-effective-presentation) recommends simple wording, minimal text and short bullets. The visual retains the previously agreed white background, restrained borders and Barlow typography. Headings range from 35–49 px. Supporting bullets use 29–33 px on the 1600 × 900 design canvas.

Browser audit: fonts load and no panels overflow. The layout uses the full slide, with 60 px outer margins. Inspected at 1280 × 720 before delivery.

## Additional solution capabilities

The five solution bullets follow the implemented processing sequence. Automatic alignment uses gravity, the initial stationary gyro-bias estimate and riding motion to estimate the phone-to-bike frame (`Aligner.kt`, `docs/12` §3). The stop rule checks accelerometer vibration and gyro RMS over a 0.5-second window (`SpeedModel.kt`), then triggers zero-velocity updates (`Fusion.kt`). The slide says this limits stationary drift; it does not promise zero drift, instantaneous calibration or perfect stop detection.


## Wide content revision

The approved text and three-box arrangement are unchanged. The design canvas is now 1600 × 660, exported at 3840 × 1584, for placement between the existing PPT header and footer. Outer margins are 20 pixels. Preserve aspect ratio when inserting. Inspected at 1280 × 528: no clipping and 56 design pixels between the final solution bullet and the metric footer. Previous tall version preserved in previous/00_before_wide_revision/.
