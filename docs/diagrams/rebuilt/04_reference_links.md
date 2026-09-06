# Research and references — hyperlink list

Numbers and labels match the slide. Research references informed design decisions; they are not a claim that the published architectures or reported accuracies were reproduced. Software and map sources describe the shipped prototype.

## Learned motion

### 01. Bicycle inertial odometry (MoE)

Qiao et al., 2025/26 preprint. Learned velocity for bicycle motion.

- [Paper](https://arxiv.org/abs/2510.17604)

### 02. DeepOdo

Wang et al., IEEE TIM, 2023. Smartphone IMU to forward speed.

- [Paper](https://ira.lib.polyu.edu.hk/handle/10397/99370)

### 03. DVSE

Xiao et al., 2025 preprint. GNSS supervision and phone alignment.

- [Paper](https://arxiv.org/abs/2505.18490)

### 04. OdoNet

Tang et al., 2021 preprint. CNN speed aiding without wheel sensors.

- [Paper](https://arxiv.org/abs/2109.03091)

### 05. AI-IMU Dead-Reckoning

Brossard et al., 2019 preprint. Learned noise adaptation in fusion.

- [Paper](https://arxiv.org/abs/1904.06064)
- [Code](https://github.com/mbrossar/ai-imu-dr)

### 06. TLIO

Liu et al., IEEE RA-L, 2020. Learned uncertainty as a filter input.

- [Paper](https://arxiv.org/abs/2007.01867)
- [Code](https://github.com/CathIAS/TLIO)

## Fusion and evaluation

### 07. IO-VNBD

Onyekpe et al., Data in Brief, 2021. External vehicle benchmark dataset.

- [Paper](https://arxiv.org/abs/2005.01701)
- [Dataset](https://github.com/onyekpeu/IO-VNBD)

### 08. KF-GINS

i2Nav, Wuhan University. GNSS/INS error-state filter reference.

- [Repository](https://github.com/i2Nav-WHU/KF-GINS)

### 09. Wheel-INS

Niu et al., IEEE TVT, 2021. Vehicle constraints and calibration.

- [Repository](https://github.com/i2Nav-WHU/Wheel-INS)

### 10. Zero-velocity detection

Wagstaff et al., 2019 preprint. Foot-mounted stop-detection methods.

- [Paper](https://arxiv.org/abs/1910.00529)

### 11. Hidden Markov map matching

Newson & Krumm, ACM GIS, 2009. Probabilistic matching to road networks.

- [Paper](https://www.microsoft.com/en-us/research/publication/hidden-markov-map-matching-noise-sparseness/)

### 12. Route-constrained fusion

Cui et al., 2026 preprint. Known-route geometry to limit drift.

- [Paper](https://arxiv.org/abs/2606.19687)

## Software and map data

### 13. PyTorch / TensorFlow–Keras

Training and model conversion. CNN training and matching model export.

- [PyTorch](https://docs.pytorch.org/docs/stable/)
- [TensorFlow/Keras](https://www.tensorflow.org/guide/keras)

### 14. Android / Kotlin / Compose

Sensor logger and navigation app. IMU and GNSS capture, services and UI.

- [Android sensors](https://developer.android.com/develop/sensors-and-location/sensors/sensors_overview)
- [GNSS](https://developer.android.com/develop/sensors-and-location/sensors/gnss)
- [Kotlin](https://kotlinlang.org/docs/home.html)
- [Compose](https://developer.android.com/compose)

### 15. Google LiteRT

Local model execution. Android inference for the speed model.

- [Documentation](https://developers.google.com/edge/litert)

### 16. MapLibre Native

Map rendering. Offline map display and camera control.

- [Repository](https://github.com/maplibre/maplibre-native)

### 17. OpenStreetMap / Protomaps

Road data and offline basemap. Campus roads and bundled PMTiles.

- [OpenStreetMap](https://www.openstreetmap.org/copyright)
- [Protomaps](https://docs.protomaps.com/basemaps/downloads)
- [PMTiles](https://docs.protomaps.com/pmtiles/)

### 18. Microsoft footprints / Esri

Buildings and satellite view. Buildings and online satellite imagery.

- [Microsoft footprints](https://github.com/microsoft/GlobalMLBuildingFootprints)
- [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9)

## Our experimental evidence

The bicycle speed model was trained on our own recordings, not on all datasets mentioned in the research survey. The final joint export uses 30 kept rides across two campus routes. See [engine results](../../11_ENGINE_RESULTS.md), [engine specification](../../12_ENGINE_SPEC_for_kotlin.md), and [app results](../../16_APP_RESULTS.md). IO-VNBD is a separate external vehicle evaluation.

## Research provenance

The core sources above are documented in `docs/03_REFERENCES.md`, `docs/research/R1_training_recipes.md`, `R2_mobile_export.md`, `R3_eskf_scale.md`, `R4_stop_detection.md`, `R6_map_stack_android.md`, and `R7_campus_map_data.md`. Actual dependency use was checked against `IDRNav/app/build.gradle.kts`, `engine/speed_model/train.py`, `engine/export/export.py`, and `docs/16_APP_RESULTS.md`.
