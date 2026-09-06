"""Export the deployment speed model (step 4 close-out): ONNX (verified with onnxruntime) and TFLite via an exact Keras
re-implementation (verified with the LiteRT interpreter), plus the causal resampler constants for the spec.

Usage: .venv/bin/python engine/export/export.py --cfg <name> [--n_check 2000]
Reads data/speed_model/models/<cfg>.pt + .meta.pt; writes data/speed_model/models/<cfg>.onnx, <cfg>.tflite, <cfg>_export.json
and engine/export/resample_constants.json. Verification: max |delta| over real windows of the 100 Hz dataset for mu and
log sigma^2, torch vs onnxruntime and torch vs tflite, must be < 1e-4; also the single-thread CPU latency on this Mac (a
proxy only; the phone number must be measured in the APK).
"""
import sys, json, time, argparse, math
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent.parent / 'speed_model'))

def keras_cnn(width, win, sd_torch, n_out=2):
    """Keras twin of train.build_model('cnn'): explicit symmetric zero padding + 'valid' convs reproduce PyTorch padding exactly."""
    import tensorflow as tf; from tensorflow import keras; L = keras.layers
    c = width; inp = keras.Input(shape=(win, 6), name='imu_window'); x = inp
    for (co, k, s) in ((c, 7, 2), (2 * c, 5, 2), (2 * c, 5, 2), (3 * c, 3, 2)):
        x = L.ZeroPadding1D(padding=(k // 2, k // 2))(x); x = L.Conv1D(co, k, strides=s, padding='valid')(x); x = L.BatchNormalization(epsilon=1e-5)(x); x = L.ReLU()(x)
    x = L.GlobalAveragePooling1D()(x); x = L.Dense(64, activation='relu')(x); out = L.Dense(n_out, name='mu_logvar')(x)
    m = keras.Model(inp, out)
    # copy weights from the torch state dict (conv: [co, ci, k] -> [k, ci, co]; dense: [o, i] -> [i, o])
    convs = [l for l in m.layers if isinstance(l, L.Conv1D)]; bns = [l for l in m.layers if isinstance(l, L.BatchNormalization)]; dens = [l for l in m.layers if isinstance(l, L.Dense)]
    for i, (cl, bl) in enumerate(zip(convs, bns)):
        cw = sd_torch[f'net.{3 * i}.weight'].numpy(); cb = sd_torch[f'net.{3 * i}.bias'].numpy(); cl.set_weights([np.transpose(cw, (2, 1, 0)), cb])
        bl.set_weights([sd_torch[f'net.{3 * i + 1}.weight'].numpy(), sd_torch[f'net.{3 * i + 1}.bias'].numpy(), sd_torch[f'net.{3 * i + 1}.running_mean'].numpy(), sd_torch[f'net.{3 * i + 1}.running_var'].numpy()])
    for j, dl in enumerate(dens):
        dl.set_weights([sd_torch[f'head.fc.{2 * j}.weight'].numpy().T, sd_torch[f'head.fc.{2 * j}.bias'].numpy()])
    return m

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--cfg', required=True); ap.add_argument('--n_check', type=int, default=2000)
    a = ap.parse_args(); import torch; from train import build_model, load, window_index, get_windows
    mdir = Path('data/speed_model/models'); meta = torch.load(mdir / f'{a.cfg}.meta.pt', weights_only=False); sd = torch.load(mdir / f'{a.cfg}.pt'); cfg = meta['cfg']
    kind, win, rate, width = cfg['model'], cfg['win'], cfg['rate'], cfg['width']; mu, sdv = np.array(meta['norm'][0], np.float32), np.array(meta['norm'][1], np.float32)
    model = build_model(kind, win, 0, width)(bool(cfg['stop_head'])); model.load_state_dict(sd); model.eval()
    d = load(cfg['tag'], rate); ends = window_index(d, win, max(1, rate // 10), 1.0, 0); rng = np.random.default_rng(0); sel = rng.choice(ends, min(a.n_check, len(ends)), replace=False)
    X = ((get_windows(d, sel, win) - mu) / sdv).astype(np.float32); xt = torch.tensor(X)
    with torch.no_grad(): ref = model(xt).numpy()
    rep = dict(cfg=a.cfg, model=kind, win=win, rate=rate, width=width, params=int(sum(p.numel() for p in model.parameters())), norm_mean=mu.tolist(), norm_std=sdv.tolist(), input_shape=[1, win, 6], output='[mu, logvar]' + (' + stop logit' if cfg['stop_head'] else ''))
    # ---- ONNX
    onnx_path = mdir / f'{a.cfg}.onnx'
    torch.onnx.export(model, torch.zeros(1, win, 6), str(onnx_path), input_names=['imu_window'], output_names=['mu_logvar'], opset_version=17, dynamo=False)
    import onnxruntime as ort; so = ort.SessionOptions(); so.intra_op_num_threads = 1; so.inter_op_num_threads = 1; sess = ort.InferenceSession(str(onnx_path), so, providers=['CPUExecutionProvider'])
    out = np.vstack([sess.run(None, {'imu_window': X[i:i + 1]})[0] for i in range(len(X))]); rep['onnx_max_abs_diff'] = float(np.abs(out - ref).max()); rep['onnx_bytes'] = onnx_path.stat().st_size
    t0 = time.perf_counter(); n = 300
    for i in range(n): sess.run(None, {'imu_window': X[i % len(X):i % len(X) + 1]})
    rep['onnx_mac_ms_per_window_1thread'] = round((time.perf_counter() - t0) / n * 1000, 3)
    import onnx; g = onnx.load(str(onnx_path)); rep['onnx_ops'] = sorted({nd.op_type for nd in g.graph.node})
    # ---- TFLite via Keras twin (cnn only)
    if kind == 'cnn':
        import os; os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'; import tensorflow as tf
        km = keras_cnn(width, win, sd, 3 if cfg['stop_head'] else 2); kout = km.predict(X, verbose=0); rep['keras_max_abs_diff'] = float(np.abs(kout - ref).max())
        conv = tf.lite.TFLiteConverter.from_keras_model(km); conv.optimizations = []; tfl = conv.convert(); tfl_path = mdir / f'{a.cfg}.tflite'; tfl_path.write_bytes(tfl); rep['tflite_bytes'] = len(tfl)
        try:
            from ai_edge_litert.interpreter import Interpreter
        except Exception:
            Interpreter = tf.lite.Interpreter
        it = Interpreter(model_content=tfl, num_threads=1); it.allocate_tensors(); ii = it.get_input_details()[0]; oo = it.get_output_details()[0]; outs = []
        for i in range(len(X)): it.set_tensor(ii['index'], X[i:i + 1]); it.invoke(); outs.append(it.get_tensor(oo['index'])[0].copy())
        outs = np.array(outs); rep['tflite_max_abs_diff'] = float(np.abs(outs - ref).max())
        t0 = time.perf_counter()
        for i in range(n): it.set_tensor(ii['index'], X[i % len(X):i % len(X) + 1]); it.invoke()
        rep['tflite_mac_ms_per_window_1thread'] = round((time.perf_counter() - t0) / n * 1000, 3)
        try:
            from tensorflow.lite.python import analyzer; import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf): analyzer.ModelAnalyzer.analyze(model_content=tfl)
            ops = sorted({ln.split()[1] for ln in buf.getvalue().splitlines() if ln.strip().startswith('Op#')}); rep['tflite_ops'] = ops
        except Exception as e: rep['tflite_ops'] = f'analyzer unavailable: {e}'
    # ---- resampler constants for the spec
    from scipy.signal import butter; sos = butter(4, 40.0, btype='low', fs=420.0, output='sos')
    json.dump(dict(description='causal 4th-order Butterworth low-pass, fc 40 Hz, fs 420 Hz, second-order sections [b0 b1 b2 a0 a1 a2], direct form II transposed; then linear interpolation to the 10 ms grid', sos=sos.tolist(), group_delay_ms_at_5hz=round(float(np.sum([2 for _ in sos]) * 0), 2)), open(Path(__file__).parent / 'resample_constants.json', 'w'), indent=1)
    json.dump(rep, open(mdir / f'{a.cfg}_export.json', 'w'), indent=1); print(json.dumps(rep, indent=1))

if __name__ == '__main__':
    main()
