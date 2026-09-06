# R2 — Mobile export path for the speed-regression model (LiteRT vs ONNX Runtime)

SIH 2026 · problem 26168 (ISRO) · bicycle dead-reckoning.
Target: 6-ch IMU windows (100–200 Hz, 128–512 samples) → speed + log-variance, on a
Samsung Galaxy S23 Ultra (Snapdragon 8 Gen 2), Kotlin, 10 Hz, single-thread CPU,
**< 5 ms/tick, < 300 KB model**.

All URLs below were fetched on **2026-09-05**. Anything I could not verify is marked
UNVERIFIED or "undocumented".

---

## 0. What is current, as of 2026-09-05

| Thing | Current version | Evidence |
|---|---|---|
| LiteRT Python (`ai-edge-litert`) | **2.2.0**, released 2026-08-12, Apache-2.0, py3.8–3.14 | https://pypi.org/project/ai-edge-litert/ |
| LiteRT Android Maven (`com.google.ai.edge.litert:litert`) | **2.2.0** (2026-08-14); quickstart snippet still shows `2.1.0`; legacy Interpreter artifact **1.4.2** (minSdk 21). CompiledModel v2.2.0 needs **minSdk 23**, NDK r26a+ | https://developers.google.com/edge/litert/android/quickstart |
| LiteRT repo | Apache-2.0, ~3.4k stars, 6,096 commits on main; stable releases every 6–8 weeks. README: "**DO NOT USE** `tflite::Interpreter`, `InterpreterBuilder`, or manual delegate creation"; TFLite packages "are in maintenance mode and only receive critical security and stability updates" | https://github.com/google-ai-edge/LiteRT |
| ONNX Runtime | **1.29.0**, GitHub release dated 12 Aug (year not rendered); Maven `onnxruntime-android:1.29.0` published ≈2026-08-13 ("23 days ago" as of fetch) → treat as **2026-08-12** | https://github.com/microsoft/onnxruntime/releases/tag/v1.29.0 , https://central.sonatype.com/artifact/com.microsoft.onnxruntime/onnxruntime-android |
| `onnxruntime-mobile` Maven artifact | stuck at **1.18.0**; the official install page no longer lists it, only `onnxruntime-android`. Treat as effectively retired | https://onnxruntime.ai/docs/install/ , https://mvnrepository.com/artifact/com.microsoft.onnxruntime/onnxruntime-mobile |
| PyTorch→LiteRT converter | `ai-edge-torch` **0.7.2** (2026-01-29) is **deprecated**, renamed to `litert-torch` **0.9.4** (2026-08-24), Apache-2.0, py≥3.10, "4 - Beta" | https://pypi.org/project/ai-edge-torch/ , https://pypi.org/project/litert-torch/ |
| ORT ↔ opset table | Official compatibility page only publishes up to **ORT 1.20 → ONNX 1.16.1, opset 21**. No row for 1.21–1.29. *(A release-notes fetch suggested "ONNX 1.22 / opset 27" for 1.28+; the opset number is internally inconsistent — **UNVERIFIED**, do not cite.)* | https://onnxruntime.ai/docs/reference/compatibility.html |

**Assumption I am making and proceeding on:** "LiteRT" and "TFLite" are the same `.tflite`
flatbuffer format; the rename does not change the file format or the converter API
(`tf.lite.TFLiteConverter`). Confirmed by the migration page being a rename/migration doc,
not a format doc.

---

## 1. Keras → LiteRT

### 1.1 Conv1D stacks — the good news
The converter does **not** emit a 1-D conv op. It rewrites `Conv1D` into
`ExpandDims → CONV_2D → Squeeze` (and `DepthwiseConv1D → DEPTHWISE_CONV_2D`). Users have
complained about exactly this: *"I still get conv2d and ds2d in tflite"*
(tensorflow#51692, opened 2021-08-26 against tf-nightly 2.7.0.dev, still labelled
`stat:awaiting tensorflower` — no maintainer fix, i.e. this is permanent behaviour).
https://github.com/tensorflow/tensorflow/issues/51692

This is **good for us**: `CONV_2D` and `DEPTHWISE_CONV_2D` are both in XNNPACK's FP32
operator list, so our whole conv stack gets the fast NEON kernels for free.

XNNPACK FP32 ops (verbatim list from the delegate README): ABS, ADD, AVERAGE_POOL_2D, CEIL,
CONCATENATION, **CONV_2D**, DEPTH_TO_SPACE, **DEPTHWISE_CONV_2D**, DIV, ELU,
**FULLY_CONNECTED**, FLOOR, HARD_SWISH, LEAKY_RELU, LOGISTIC, MAX_POOL_2D, MAXIMUM, **MEAN**,
MINIMUM, MUL, NEG, PAD, PRELU, RELU, RELU6, RELU_N1_TO_1, **RESHAPE**, RESIZE_BILINEAR,
ROUND, SLICE, SOFTMAX, SPACE_TO_DEPTH, SPLIT, SQRT, SQUARE, SQUARED_DIFFERENCE,
STRIDED_SLICE, SUB, TANH, TRANSPOSE, TRANSPOSE_CONV.
https://raw.githubusercontent.com/tensorflow/tensorflow/master/tensorflow/lite/delegates/xnnpack/README.md

- `GlobalAveragePooling1D` lowers to **MEAN** → XNNPACK-accelerated. ✅
- BatchNorm is folded away: the op-compatibility page lists `tf.nn.bias_add` and
  `tf.nn.fused_batch_norm` among ops "removed from the graph" during conversion, i.e. folded
  into the preceding conv weights. No BN op survives in the flatbuffer.
  https://developers.google.com/edge/litert/models/ops_compatibility
- **No RNN op is in the XNNPACK list.** A GRU/LSTM will run on TFLite's own kernels, not
  XNNPACK, and will split the graph into XNNPACK / non-XNNPACK partitions.

### 1.2 Dilated causal convolutions (TCN) — the trap
Dilated `Conv1D` converts to `SPACE_TO_BATCH_ND → CONV_2D → BATCH_TO_SPACE_ND`. That path
was outright broken at one point: tensorflow#39823 (opened 2020-05-23, TF 2.2.0) failed at
`AllocateTensors` with `NumDimensions(op_context.input) != kInputDimensionNum (3 != 4)`;
marked "Fixed in Nightly".
https://github.com/tensorflow/tensorflow/issues/39823

It converts today, but **`SPACE_TO_BATCH_ND` and `BATCH_TO_SPACE_ND` are not in the XNNPACK
FP32 list above**. A dilated TCN will therefore fragment the delegated graph and pay
delegate-boundary costs on every dilated layer. Practical guidance: prefer a **strided /
stacked 1-D CNN over a dilated TCN** for v1, or implement the dilation by an explicit
reshape you control. If you do build a TCN, verify partitioning with
`benchmark_model --enable_op_profiling=true` before believing any latency estimate.

### 1.3 GRU / LSTM with carried state — the real limitation
The official RNN conversion doc covers **LSTM only** and states verbatim:

> "Currently there is support only for converting stateless Keras LSTM (default behavior in
> Keras). Stateful Keras LSTM conversion is future work."

and recommends you "model a stateful Keras LSTM layer using the underlying stateless Keras
LSTM layer and managing the state explicitly in the user program."
https://developers.google.com/edge/litert/models/convert/rnn

Key points from that page and around it:
- Fused kernel is `UnidirectionalSequenceLSTM`; bidirectional becomes two of them. A
  `unidirectional_sequence_gru` kernel exists in the TF source tree, but **GRU is not
  mentioned anywhere on the conversion page** — there is no documented fused-GRU converter
  path. UNVERIFIED whether the converter ever targets it.
- tensorflow#97941 (opened 2025-07-31, TF 2.12) reports Keras **GRU converting into
  `While` ops** rather than decomposed math; the reporter found `unroll=True` removes the
  while loops. Closed stale, no maintainer answer.
  https://github.com/tensorflow/tensorflow/issues/97941

**What forces the Flex / SELECT_TF_OPS delegate:** while-loop RNN lowering drags in
`TensorList*` ops, and genuinely stateful models need resource variables
(`VarHandleOp` / `ReadVariableOp` / `AssignVariableOp`), which require
`converter.experimental_enable_resource_variables = True` and typically
`SELECT_TF_OPS` as well. The cost is brutal for us:

| Android build | APK size | Source |
|---|---|---|
| builtin ops only | **561 KB** | https://developers.google.com/edge/litert/models/ops_select |
| builtin + Select TF ops (Flex) | **8.0 MB** | same |
| selectively built for one model | **1.8 MB** | same |

Runtime overhead of Flex is small (MobileNet, Pixel 2, 100-run avg: 260.7 ms builtin vs
264.5 ms with SELECT_TF_OPS, ≈1.5%) — but a **14× binary increase to ship a 300 KB model is
unacceptable.** Rule for this project: **the exported model must contain zero Flex ops.**
Check with `interpreter.get_signature_list()` / a flatbuffer op dump before shipping.

### 1.4 The pattern that actually works for carried state
Since stateful conversion is unsupported, do exactly what the doc tells you — carry the
state yourself. Build a **functional Keras model with the state as a second input**:

- `x = Input(shape=(W, 6))`, `h_in = Input(shape=(H,))`
- `y, h_out = GRU(H, return_state=True, unroll=True)(x, initial_state=h_in)`
- outputs `[speed, logvar, h_out]`, inputs `[x, h_in]`

`unroll=True` with a fixed window length removes the `While`/`TensorList` lowering
(tensorflow#97941) and leaves plain MatMul/Add/Sigmoid/Tanh, all builtin. Kotlin then holds
`h` in a `FloatArray` between the 10 Hz ticks and resets it on session start / long GPS gap.
Cost: unrolling a 128–512-step window inflates the graph hugely — **only viable if you feed
the GRU a short downsampled sequence (e.g. 16–32 steps after the conv stack), not the raw
window.** Design the CNN to stride the sequence down before the GRU.

Expose the two entry points cleanly with **signatures**:
`tf.saved_model.save(model, path, signatures={'step': fn.get_concrete_function()})`, then in
Kotlin/Java `interpreter.runSignature(inputs, outputs, "step")` with named maps.
Documented caveat: "signature runners from the same interpreter must not be executed
concurrently." https://developers.google.com/edge/litert/conversion/tensorflow/signatures

Conversion API: `from_saved_model()` is the recommended entry point (over
`from_keras_model()`).
https://developers.google.com/edge/litert/conversion/tensorflow/convert_tf

---

## 2. PyTorch → ONNX Runtime Mobile

### 2.1 GRU state — ONNX wins outright here
The ONNX `GRU` op takes `initial_h` (input 6, shape `[num_directions, batch, hidden]`) and
returns `Y_h` (output 2, same shape). Explicit hidden state in/out is **native, documented,
first-class** — no unrolling trick, no Flex risk. Attributes include `hidden_size`,
`direction`, `layout`, `linear_before_reset` (PyTorch's GRU semantics correspond to
`linear_before_reset=1`; the exporter sets this — verify it in Netron). GRU op versions: 1,
3, 7, 14, 22.
https://onnx.ai/onnx/operators/onnx__GRU.html

### 2.2 Conv1d — ONNX loses here
`nn.Conv1d` exports as ONNX `Conv` with one spatial dim. The **XNNPACK execution provider
supports only 2-D convolution**: *"Only 2D Conv is supported. Weights and bias should be
constant."* So our 1-D conv stack gets **no XNNPACK acceleration** under ORT; it falls back
to the default CPU EP (MLAS). Also supported by the XNNPACK EP: AveragePool/MaxPool (2D),
Gemm, MatMul (2D, since v1.14), ConvTranspose (2D, v1.14+), Softmax, Resize (bilinear),
QLinearConv/QLinearAveragePool/QLinearSoftmax.
https://onnxruntime.ai/docs/execution-providers/Xnnpack-ExecutionProvider.html

The NNAPI EP is the same story (`ai.onnx:Conv` — "Only 2D Conv is supported") and lists
**no GRU/RNN op at all** — and NNAPI is deprecated anyway (§5).
https://onnxruntime.ai/docs/execution-providers/NNAPI-ExecutionProvider.html

Dilated conv: `dilations` is a standard `Conv` attribute; no documented ORT problem. The
absolute performance of ORT's CPU-EP 1-D conv is **undocumented** — no published numbers.

### 2.3 Export, fixed shapes, opset
`torch.onnx.export(model, args=(), f=None, *, opset_version=None, dynamo=True,
dynamic_shapes=None, verify=..., ...)`. Docs: *"Setting `dynamo=True` enables the new ONNX
export logic ... This is the recommended and default way to export models to ONNX."* Leave
`dynamic_shapes=None` → **all dims are fixed to the example-input shapes**, which is exactly
what we want. `verify` (bool) — "Whether to verify the exported model using ONNX Runtime.
This option is only valid when dynamo is True."
https://docs.pytorch.org/docs/main/onnx_export.html

**Opset recommendation: pin `opset_version=17`.** Rationale: `Conv` has been stable since
opset 11 and `GRU` since opset 14, so 17 covers everything we need with margin, and every
ORT ≥ 1.10 supports it — no dependence on the unpublished 1.21–1.29 opset rows.

### 2.4 ORT format / minimal build / APK cost
- Convert: `python -m onnxruntime.tools.convert_onnx_models_to_ort <onnx model file or dir>`
  (ORT ≥ 1.8). Two optimisation styles since 1.11: **"Fixed"** (platform-specific
  optimisations baked in — recommended when *not* using NNAPI/CoreML, i.e. **ours**) and
  **"Runtime"**. https://onnxruntime.ai/docs/performance/model-optimizations/ort-format-models.html
- `--minimal_build` (basic): *"No support for ONNX format models. The model must be
  converted to ORT format."* Disables RTTI, no runtime optimisations.
  `--minimal_build extended` keeps limited runtime partitioning for compiling EPs.
  `--include_ops_by_config <config>` strips unused kernels;
  `--enable_reduced_operator_type_support` strips unused dtypes (**ORT-format models only** —
  "ONNX format models are not guaranteed to include the required per-node type information").
  `--config=MinSizeRel` for smallest binary.
  https://onnxruntime.ai/docs/build/custom.html , https://github.com/microsoft/onnxruntime/blob/main/docs/Reduced_Operator_Kernel_build.md
- **Size numbers are essentially undocumented by Microsoft.** No before/after table exists in
  the custom-build or reduced-kernel docs. Data points I could find:
  - `onnxruntime-android` **1.16.0-rc1 AAR = 21.6 MB** (all ABIs) — mvnrepository listing.
  - A third-party arm64 app (sherpa-onnx) reports `libonnxruntime.so` ≈ **5.8 MB** of a
    7.2 MB runtime. Third-party, approximate — treat as an order-of-magnitude only.
  - Building your own minimal AAR requires Android SDK+NDK and `./build.sh --android ...`
    (default ABI arm64-v8a, default API level 27); output lands in
    `build_dir/java/build/android/outputs/aar`. Also required for R8/minified builds:
    `-keep class ai.onnxruntime.** { *; }` in `proguard-rules.pro` "to avoid runtime crashes".
    https://onnxruntime.ai/docs/build/android.html
- Threading: `intra_op_num_threads` defaults to the **number of physical CPU cores** — must be
  overridden. For our duty cycle also disable busy-wait:
  `sess_opt.add_session_config_entry("session.intra_op.allow_spinning", "0")`.
  https://onnxruntime.ai/docs/performance/tune-performance/threading.html

---

## 3. Quantisation for a regression model with a log-variance head

Official LiteRT table (https://developers.google.com/edge/litert/models/post_training_quantization):

| Technique | Size | Latency | Hardware | Data needed |
|---|---|---|---|---|
| Dynamic-range int8 | 4× smaller | 2–3× speedup | CPU | none |
| Full integer int8 | 4× smaller | 3×+ speedup | CPU, EdgeTPU, MCU | representative dataset |
| Float16 | 2× smaller | GPU accel. | CPU, GPU | none |

Float16 detail: *"The float16 weights are upsampled to float32 prior to the first
inference"* — so on CPU it is a **file-size** optimisation with essentially no latency
change; accuracy in Google's own example was unchanged (97.0% both).
https://developers.google.com/edge/litert/models/post_training_float16_quant

Accuracy/latency evidence that int8 is NOT free
(https://developers.google.com/edge/litert/models/model_optimization):

| Model | fp32 acc | PTQ int8 acc | QAT acc | fp32 lat. (Pixel 2, 1 core) | PTQ lat. | QAT lat. |
|---|---|---|---|---|---|---|
| MobileNet-v1-1-224 | 70.9% | **65.7%** | 70.0% | 124 ms | 112 ms | 64 ms |
| MobileNet-v2-1-224 | 71.9% | **63.7%** | 70.9% | 89 ms | **98 ms (slower!)** | 54 ms |
| Inception_v3 | 78.0% | 77.2% | 77.5% | 1130 ms | 845 ms | 543 ms |
| ResNet_v2_101 | 77.0% | 76.8% | — | 3973 ms | 2868 ms | — |

Note MobileNet-v2 got **slower** after post-training int8. Post-training int8 cost MobileNet
5.2 and 8.2 accuracy points respectively. These are classification models; a regression head
has no argmax to hide error behind.

LiteRT int8 spec: weights **symmetric int8, zero_point == 0, range [-127,127]**, per-axis for
CONV_2D/DEPTHWISE_CONV_2D; activations **asymmetric int8 per-tensor**, `real = (q - zp)·scale`.
https://developers.google.com/edge/litert/conversion/tensorflow/quantization/quantization_spec

XNNPACK interaction (the killer argument): the delegate README states *"post-training dynamic
range quantization is not supported"*, and quantised inference is off unless built with
`--define tflite_with_xnnpack_qs8=true` / `qu8=true`. So **dynamic-range int8 risks falling
off XNNPACK entirely onto reference kernels — i.e. quantising could make us slower.**

ONNX Runtime's guidance: *"dynamic quantization for RNNs and transformer-based models, and
static quantization for CNN models"*; S8S8 QDQ is the default; and explicitly *"It is not
rare to get worse performance on old devices."* No numbers published.
https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html

### Recommendation
**Ship float32. Do not quantise for v1.**
1. The 300 KB budget is already met in fp32: 300 KB / 4 B = **75,000 parameters**, which is a
   comfortable 1-D CNN (e.g. 4 conv blocks of 32–64 channels + a small head). Quantisation
   buys nothing we need.
2. fp32 keeps us on the XNNPACK fast path with zero build-flag risk.
3. The **log-variance head is the fragile output**. σ² = exp(logvar), so a quantisation error
   of ε in logvar becomes a multiplicative factor e^ε on the variance the EKF consumes. An
   int8 activation scale sized for the speed output will be badly sized for logvar. If you
   ever must quantise, keep the logvar branch in float and validate **NLL / calibration**
   (e.g. fraction of residuals inside ±1σ, ±2σ), not just speed RMSE.
4. If size ever becomes binding, **float16 weight quantisation is the safe step** (2× smaller,
   weights re-expanded to fp32 before inference → numerically identical up to fp16 weight
   rounding). Full int8 only as a last resort, with a re-run of the whole trajectory
   evaluation, not a unit test.

---

## 4. Measured latency — what is actually published

**The single most relevant number for this project.** IMUNet, Zeinali, Zandizari & Chang —
arXiv:2208.00068 (submitted 2022-07-29), published as *"IMUNet: Efficient Regression
Architecture for Inertial IMU Navigation and Positioning"*, **IEEE Trans. Instrum. Meas.
(2024)**, DOI 10.1109/TIM.2024.3374300 (IEEE Xplore doc 10480886). Table III, "Latency
inference on an actual edge device", measured on a **Samsung Galaxy S10**, models converted
to TensorFlow Lite, 1-D CNN regressors on RoNIN-style IMU windows:

| Model | TFLite size (MB) | Latency (µs) |
|---|---|---|
| ResNet18-1D | 4.5 | 1044 |
| MobileNet-1D | 3.5 | 907 |
| MobileNetV2-1D | 2.7 | 645 |
| MnasNet-1D | 3.1 | 654 |
| EfficientNet-1D | 3.8 | 967 |
| **IMUNet** | **1.4** | **387** |

Accuracy context from the same paper (ATE, RTE in metres, RoNIN/OXIOD trajectories): IMUNet
(1.23, 2.02) and (1.66, 2.14) vs ResNet18 (3.33, 2.53), MobileNetV2 (5.02, 4.27).

**Why this settles the < 5 ms question.** A 1.4 MB 1-D CNN IMU regressor ran in **0.387 ms**
on a 2019 Exynos 9820 / SD855-class phone. Our S23 Ultra's Cortex-X3 is roughly 2× that in
single-thread. Our model is smaller (< 300 KB). We have **~13× headroom** against the 5 ms
budget before we even start optimising. Use this table in the judging document.

Supporting anchors:

- LiteRT benchmark tool page, Android 10, **Pixel 4**: MobileNet v1 1.0 224 float **14.0 ms**
  @ 4 threads (GPU 9.0 ms); quantised **5.0 ms**; Inception V4 **324.1 ms** (GPU 97.6 ms).
  https://developers.google.com/edge/litert/models/measurement
- XNNPACK README, **single-threaded** mobile table:
  Pixel 3a — MobileNet v1 **88 ms**, v2 **55 ms**, v3-Large **44 ms**, v3-Small **14 ms**;
  Pixel 2 — 86/53/42/14 ms; Pixel — 82/49/39/12 ms. (No Snapdragon 8-series rows.)
  https://github.com/google/XNNPACK
- **Galaxy S23 Ultra data point, and a warning** — tensorflow#62615: same PoseNet model,
  same device, bundled TFLite: **12.28 ms (2.11.0) → 25.93 ms (2.12.0) → 26.03 ms (2.13.0)
  → 25.86 ms (2.14.0)**, but **12.12 ms** with TFLite 2.15 via Google Play services. Closed
  as "not planned"; root cause never published. A runtime-version bump silently doubled
  latency on our exact device class.
  https://github.com/tensorflow/tensorflow/issues/62615
- Google AI Edge blog, 2025-11-24, Snapdragon 8 Elite Gen 5, relative to CPU baseline: GPU
  "~5–70%" of CPU latency, NPU "~1–20%". Absolute ms not published; chart is normalised.
  https://developers.googleblog.com/unlocking-peak-performance-on-qualcomm-npu-with-litert/

**Gap, stated honestly: there is no published single-thread TFLite CPU latency table for
Snapdragon 8 Gen 2.** The academic mobile-latency benchmark corpus (Li, Paolieri &
Golubchik, EdgeSys '24, https://qed.usc.edu/paolieri/papers/2024_edgesys_mobile_inference_benchmark.pdf —
102 real CNNs + 1000 synthetic CNNs across 174 environments, TFLite 2.15 and PyTorch Mobile)
tops out at Snapdragon 855 / Exynos 9820; their 2025 ViT follow-up (arXiv:2510.25166,
VALUETOOLS) uses the same six devices. Qualcomm AI Hub *can* profile TFLite on a real Galaxy
S23, but its published model cards report NPU figures (e.g. MobileNet-v3-Large-Quantized
**0.3 ms**, all 137 ops on NPU), not single-thread CPU. **Action: the team must produce this
number themselves** with `benchmark_model --num_threads=1 --use_xnnpack=true
--warmup_runs=20 --num_runs=200 --enable_op_profiling=true` on the S23 Ultra, and report it —
it will be an original measurement in the submission.

---

## 5. Practical pitfalls

1. **NNAPI is dead. Do not use the NNAPI delegate.** *"The Neural Networks API (NNAPI) is
   deprecated. It was introduced in Android 8.1 ... and deprecated in Android 15."* Drivers /
   HAL are unaffected; the NDK API is what is deprecated. Recommended migration: LiteRT /
   TFLite in Google Play services, or AICore, optionally the GPU delegate. Page last updated
   2026-03-06. https://developer.android.com/ndk/guides/neuralnetworks/migration-guide
   (Also: a Snapdragon 8 Gen 2 tablet couldn't even run TFLite NNAPI — tensorflow#61854.)
2. **XNNPACK default status is contradictory in the docs — set it explicitly.**
   `InterpreterApi.java` on TF master: *"Enable or disable an optimized set of CPU kernels
   (provided by XNNPACK). **Enabled by default.**"* But the XNNPACK delegate README still
   says pre-built Android binaries have it *"disabled by default"*. Resolution: call
   `setUseXNNPACK(true)` yourself and prove it with `benchmark_model --use_xnnpack=true` vs
   `false` plus op profiling. Never rely on the default.
   https://raw.githubusercontent.com/tensorflow/tensorflow/master/tensorflow/lite/java/src/main/java/org/tensorflow/lite/InterpreterApi.java
3. **Threads.** `setNumThreads`: *"numThreads should be >= -1. Setting numThreads to 0 has the
   effect of disabling multithreading, which is equivalent to setting numThreads to 1. If
   unspecified, or set to the value -1, the number of threads used will be
   implementation-defined and platform-dependent."* → **set `setNumThreads(1)` explicitly.**
   On ORT: `intra_op_num_threads = 1` and `session.intra_op.allow_spinning = "0"` (default
   spinning would burn a core busy-waiting through our 100 ms idle gaps → battery + thermal).
4. **Benchmark-binary numbers do not transfer into the app.** tensorflow#53179 (2021-11-24,
   TF r2.7, LG Stylo 5 / SD450): the *same* LSTM model ran **11,459.1 µs inside an APK vs
   5,396.75 µs as a compiled binary** — ~2× slower in-app, reproduced on three more devices,
   unaffected by thread affinity, present even single-threaded. MobileNet-class CNNs did
   **not** show it — it was LSTM-specific. Two lessons: (a) always report in-app latency;
   (b) another reason to avoid recurrence. https://github.com/tensorflow/tensorflow/issues/53179
5. **Warm-up.** Benchmark tool's documented pattern is `--warmup_runs=1 --num_runs=50`; that
   is far too little for a 10 Hz app. At app start, run ≥20 dummy invocations with
   representative data. XNNPACK repacks weights on the first inference, and at 10 Hz the
   little cores will be idle-clocked between ticks, so the *first* tick after a pause is the
   worst case. Log p50/p95/p99 per tick, not the mean.
6. **Zero per-inference allocation.** Fixed shapes → call `allocateTensors()` exactly once and
   never resize. Allocate one direct `ByteBuffer` (`order(ByteOrder.nativeOrder())`) for the
   input window and one for each output, plus a persistent `FloatArray` for the GRU state,
   at engine construction. Reuse the same `HashMap` objects for `runSignature`. Any `new
   float[...]` inside the 10 Hz loop is a GC pause waiting to happen during a ride.
7. **Concurrency.** "Signature runners from the same interpreter must not be executed
   concurrently." One interpreter, one dedicated inference thread, an SPSC queue from the
   sensor thread.

### Verification procedure: exported == Python to 1e-4 (float32)
PyTorch's own docs give the tolerance bar we should adopt: **atol 1e-4 for float32** (1e-2
for float16). Procedure:

1. Freeze a fixed eval set of ≥200 real windows to `.npy` — deliberately include standstill,
   hard braking, max speed, and a pothole/vibration window.
2. Run the training-framework model in float32 → save `y_ref`, `logvar_ref` (float64 on disk).
3. Run the **exported artefact on the desktop first**, same fixed shapes, same runtime family
   (`ai_edge_litert.interpreter.Interpreter`, or `onnxruntime.InferenceSession` with
   `CPUExecutionProvider`).
4. `np.testing.assert_allclose(y_out, y_ref, rtol=1e-4, atol=1e-5)` and log
   `np.max(np.abs(y_out - y_ref))`. Expect ~1e-6 typical; treat >1e-4 as a bug, not noise.
   For ORT you get this free: `torch.onnx.export(..., dynamo=True, verify=True)`.
5. **Then repeat on-device.** Ship the same `.npy` in `assets/`, add a debug screen that runs
   the model over it and writes a CSV, pull it with `adb pull`, diff against `y_ref`. This is
   the step that catches byte-order, NHWC/NCHW, and normalisation-constant mismatches — the
   desktop check will not.
6. Compare **XNNPACK on vs XNNPACK off** on desktop too. They use different accumulation
   orders, so a 1e-6-scale difference between them is expected and is not an export bug —
   knowing that in advance saves a day of debugging.
7. **For the stateful GRU, verify the rolled-out trace, not one window.** Feed 300 consecutive
   windows carrying `h` and compare the entire output sequence. A transposed / stale /
   never-reset hidden state produces a *correct first frame* and drifts afterwards; a
   single-window test passes and the road test fails.

---

## 6. Recommendation

**Primary path: Keras → LiteRT, float32, XNNPACK on, 1 thread, no recurrence in v1.**

1. **Op coverage decides it.** LiteRT rewrites `Conv1D → CONV_2D`, which is on XNNPACK's FP32
   fast path; ORT's XNNPACK EP explicitly supports "only 2D Conv", so an identical PyTorch
   1-D stack gets **no** XNNPACK acceleration under ORT and falls back to the generic CPU EP.
   For a Conv1D-dominated model this is the whole ballgame.
2. **Binary cost.** LiteRT via Google Play services adds essentially nothing to the APK and is
   the documented recommended Android path; the maintained `onnxruntime-android` AAR is a
   multi-MB native dependency (21.6 MB AAR at 1.16.0-rc1, all ABIs) unless we invest days in
   a `--minimal_build` + `--include_ops_by_config` custom NDK build on the Mac. Shipping a
   300 KB model behind a 6 MB runtime is a bad look in a size-constrained demo.
3. **Evidence we will hit the target.** IMUNet's 1-D CNN inertial regressor: **387 µs at
   1.4 MB on a Galaxy S10.** Our model is smaller on a device ~2× faster single-thread. The
   5 ms budget is not the binding constraint — feature extraction and the EKF will be.
4. **Where the ecosystem is going.** `ai-edge-litert` 2.2.0 (2026-08-12) and the Android
   artifact 2.2.0 (2026-08-14) are actively released; classic TFLite is in maintenance mode.
   If we later want the S23's Hexagon NPU there is a first-party Qualcomm SDK
   (`ai-edge-litert-sdk-qualcomm`), whereas ORT would need the QNN EP plus the Qualcomm AI
   Engine Direct SDK and a custom build.
5. **The honest counterweight — ONNX is genuinely better for a GRU.** ONNX `GRU` takes
   `initial_h` and returns `Y_h` natively; LiteRT has *no* documented stateful-GRU path
   ("Stateful Keras LSTM conversion is future work"; GRU isn't mentioned on that page at
   all). If carried recurrent state turns out to be essential, LiteRT costs us an
   `unroll=True` functional-model workaround.

**Decision rule for the lead.** Build the plain 1-D CNN (+ optional strided TCN) on
Keras → LiteRT now. Run the R1 architecture ablation. *Only if* the carried-state GRU beats
the stateless CNN by a margin worth defending (my suggested bar: **>10% relative speed-RMSE
reduction, or a materially better NLL/σ calibration**) do we spend effort on state — and then
prefer the unrolled-GRU-in-Keras route (short post-conv sequence, 16–32 steps) over adding a
second toolchain. **Do not build both toolchains up front.**

**De-risker worth knowing:** choosing PyTorch for *training* does not lock us out of LiteRT —
`litert-torch` 0.9.4 (2026-08-24, Apache-2.0, the rename of the now-deprecated
`ai-edge-torch` 0.7.2) converts PyTorch models straight to `.tflite`. It is labelled
"4 - Beta", so treat it as a fallback and validate per §5, not as the plan of record.

---

## Source ledger (all fetched 2026-09-05)

| # | Source | What it gave us |
|---|---|---|
| 1 | https://github.com/google-ai-edge/LiteRT | LiteRT status, Apache-2.0, ~3.4k stars, TFLite in maintenance mode |
| 2 | https://pypi.org/project/ai-edge-litert/ | 2.2.0, 2026-08-12 |
| 3 | https://developers.google.com/edge/litert/android/quickstart | Maven coords, minSdk 23, CompiledModel vs Interpreter |
| 4 | https://developers.google.com/edge/litert/models/convert/rnn | "Stateful Keras LSTM conversion is future work"; GRU absent |
| 5 | https://developers.google.com/edge/litert/models/ops_select | Flex APK cost 561 KB → 8.0 MB → 1.8 MB; 260.7 vs 264.5 ms |
| 6 | https://developers.google.com/edge/litert/models/ops_compatibility | BatchNorm/bias_add folded out |
| 7 | https://raw.githubusercontent.com/tensorflow/tensorflow/master/tensorflow/lite/delegates/xnnpack/README.md | XNNPACK FP32 op list; no RNN; dynamic-range int8 unsupported |
| 8 | https://raw.githubusercontent.com/.../lite/java/.../InterpreterApi.java | setUseXNNPACK "Enabled by default"; setNumThreads semantics |
| 9 | https://github.com/tensorflow/tensorflow/issues/51692 | Conv1D → Conv2D rewrite (2021-08-26, unresolved) |
| 10 | https://github.com/tensorflow/tensorflow/issues/39823 | Dilated Conv1D → SPACE_TO_BATCH_ND breakage (2020-05-23) |
| 11 | https://github.com/tensorflow/tensorflow/issues/97941 | Keras GRU → While ops; `unroll=True` fix (2025-07-31, stale) |
| 12 | https://github.com/tensorflow/tensorflow/issues/62615 | Galaxy S23 Ultra 12.28 → 25.93 ms regression, 2.11 → 2.12 |
| 13 | https://github.com/tensorflow/tensorflow/issues/53179 | LSTM 2× slower in APK than binary (11459 vs 5397 µs) |
| 14 | https://developers.google.com/edge/litert/models/post_training_quantization | 4×/2× size, 2–3×/3×+ speedup table |
| 15 | https://developers.google.com/edge/litert/models/post_training_float16_quant | fp16 weights upsampled to fp32 before first inference |
| 16 | https://developers.google.com/edge/litert/models/model_optimization | int8 accuracy/latency table incl. MNv2 89 → 98 ms |
| 17 | https://developers.google.com/edge/litert/conversion/tensorflow/quantization/quantization_spec | int8 symmetric weights / asymmetric activations |
| 18 | https://developers.google.com/edge/litert/models/measurement | benchmark_model flags; Pixel 4 numbers |
| 19 | https://developers.google.com/edge/litert/conversion/tensorflow/signatures | runSignature API; no concurrent signature runners |
| 20 | https://developers.google.com/edge/litert/android/play_services | Play-services runtime, caveats |
| 21 | https://github.com/google/XNNPACK | single-thread Pixel/Pixel 2/Pixel 3a MobileNet table |
| 22 | https://arxiv.org/abs/2208.00068 + PDF (arXiv:2208.00068 / IEEE TIM 2024) | **IMUNet Table III: 387 µs, 1.4 MB on Galaxy S10** |
| 23 | https://central.sonatype.com/artifact/com.microsoft.onnxruntime/onnxruntime-android | ORT Android 1.29.0 |
| 24 | https://github.com/microsoft/onnxruntime/releases/tag/v1.29.0 | 1.29.0 release |
| 25 | https://onnxruntime.ai/docs/install/ | only `onnxruntime-android` listed |
| 26 | https://onnxruntime.ai/docs/build/custom.html | `--minimal_build`, `--include_ops_by_config` |
| 27 | https://github.com/microsoft/onnxruntime/blob/main/docs/Reduced_Operator_Kernel_build.md | reduced-kernel build; **no size numbers published** |
| 28 | https://onnxruntime.ai/docs/performance/model-optimizations/ort-format-models.html | ORT format, Fixed vs Runtime optimisation |
| 29 | https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html | dynamic for RNN / static for CNN; S8S8 default |
| 30 | https://onnxruntime.ai/docs/execution-providers/Xnnpack-ExecutionProvider.html | **"Only 2D Conv is supported"** |
| 31 | https://onnxruntime.ai/docs/execution-providers/NNAPI-ExecutionProvider.html | 2D Conv only; no GRU |
| 32 | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | intra_op defaults to physical cores; spinning config |
| 33 | https://onnxruntime.ai/docs/build/android.html | AAR build, ABIs, proguard rule |
| 34 | https://onnxruntime.ai/docs/reference/compatibility.html | opset table ends at ORT 1.20 / opset 21 |
| 35 | https://onnx.ai/onnx/operators/onnx__GRU.html | `initial_h` / `Y_h`, `linear_before_reset` |
| 36 | https://docs.pytorch.org/docs/main/onnx_export.html | `dynamo=True` default; `verify`; atol 1e-4 for float |
| 37 | https://developer.android.com/ndk/guides/neuralnetworks/migration-guide | NNAPI deprecated in Android 15 (page updated 2026-03-06) |
| 38 | https://developers.googleblog.com/unlocking-peak-performance-on-qualcomm-npu-with-litert/ | GPU ~5–70%, NPU ~1–20% of CPU latency (2025-11-24) |
| 39 | https://qed.usc.edu/paolieri/papers/2024_edgesys_mobile_inference_benchmark.pdf | EdgeSys '24 corpus; devices top out at SD855 |
| 40 | https://arxiv.org/html/2510.25166v1 | VALUETOOLS ViT latency study; same six devices, no SD8G2 |
| 41 | https://pypi.org/project/ai-edge-torch/ + https://pypi.org/project/litert-torch/ | ai-edge-torch deprecated → litert-torch 0.9.4 (2026-08-24) |

**Failed / partial fetches, disclosed:** `developers.google.com/edge/litert/models/convert_rnn`
(404 — correct path is `.../models/convert/rnn`);
`developers.google.com/edge/litert/android/nnapi` (404 — page appears removed, consistent with
NNAPI deprecation); `developers.google.com/edge/litert/android/acceleration` (404);
`mvnrepository.com/.../onnxruntime-android` (403, size figure for 1.16.0-rc1 came via search
snippet — **treat the 21.6 MB as approximate**); the ORT release-notes opset claim
("ONNX 1.22 / opset 27") is internally inconsistent and is marked **UNVERIFIED**;
GNIO (arXiv:2603.15281, 2026-03-17, Feng et al.) fetched but its numeric tables were not
text-extractable — noted for R1, not used here.
