# Review for a one-minute explanation

## Principal issues in the first version

1. The column headings, node headings, subtitles and captions repeated the same ideas.
2. The fusion block exposed implementation details before making its role clear.
3. The GPS source and gate consumed two large boxes even though the reviewer chiefly needs to understand which measurements can enter the estimator.
4. Multiple performance figures competed with the demonstration result. The measured configurations had to remain distinct.
5. Captions beneath all three phone screens restated their headings.
6. Some lower labels fitted technically but had insufficient internal margin.

## Revised reading order

Architecture: phone motion sensors, aligned samples, learned speed and gyro heading, fusion, navigation. The lower paths show trusted GNSS and the recognised offline corridor entering the engine.

Prototype: record, prepare, train, validate, deploy. Three actual app captures then show GPS lock, dead reckoning and GPS return.

## Content choices

- 77 authored words on each visual. The architecture previously had 180, the prototype 138. Counts exclude embedded app screenshots. This is a copy-density measure, not a claim that a timed audience test was conducted.
- Core headings are 32 px; supporting architecture copy is 25 px on the 1600 × 900 design canvas. Phone state labels are 28 px.
- The architecture combines the receiver and quality gate. GNSS still enters calibration, heading correction, corridor recognition and fusion through separate principal paths.
- Calibration details, model size, state-variable notation, measurement delays and HMM implementation details stay in the supporting source notes rather than the first-level diagram.
- The corridor block retains the recognition label, because trusted fixes select an existing road; GNSS does not create the offline road geometry.
- The prototype retains 10/10 held-out rides under 10% endpoint drift. It removes the redundant median and worst figures from the visual. Evaluation context remains beside the result.
- The 17.3 m after 569 m figure remains explicitly a replay demonstration. The screenshot and independent evaluation numbers are not combined into a single claimed test.
- The previous complete visuals are preserved in `previous/`.

## Verification

Rechecked the current `Engine.kt` prediction/model/GNSS update sequence, the model loaded by `EngineRunner.kt`, the joint-model corridor evaluation in `docs/11_ENGINE_RESULTS.md`, and the captured replay documented in `docs/16_APP_RESULTS.md`.

The earlier WhatsApp temporary attachment is no longer present at its original path. The prior turn's extracted content and the current repository specification/results provide the relevant evidence; no missing attachment was represented as freshly reread.

Both current HTML files load all embedded images and Barlow fonts without external requests. Browser checks report no overflowing boxes or content outside the canvas. Both were inspected at 1280 × 720 and exported at 3840 × 2160. The connectors do not cross one another or pass through text.
