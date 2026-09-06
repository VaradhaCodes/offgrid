"""Export the deployment speed model as a model pack for the Kotlin forward pass, plus conformance fixtures.

Usage: .venv/bin/python tools/export_weights.py [--cfg cnn_r100_w256_joint_deploy] [--n_check 500]

Reads  data/speed_model/models/<cfg>.pt + <cfg>.meta.pt (read-only; nothing under data/ is written).
Writes IDRNav/app/src/main/assets/model/weights.bin   float32 little-endian, layers in order, BatchNorm folded into the conv
       IDRNav/app/src/main/assets/model/model.json    shapes, order, offsets, normalisation, version, sha256 of weights.bin
       IDRNav/app/src/main/assets/model/windows_500.bin   float32 LE [n, 256, 6] RAW (un-normalised) bike-frame windows from the
                                                          100 Hz training set (both roads, stands included)
       IDRNav/app/src/main/assets/model/expected_500.bin  float32 LE [n, 2] = PyTorch [mu, logvar] on the normalised windows
       IDRNav/app/src/main/assets/model/windows_500.json  sidecar: t_s, run_id, session, v_gnss, phase per window
The engine's JVM tests read the same files (../app/src/main/assets/model relative to the engine module).

Layer order in weights.bin (all float32, row-major):
  conv i: W[co][ci][k] (PyTorch layout, BN folded: W' = W * gamma / sqrt(var + eps)), then b'[co] = (b - mean) * gamma / sqrt(var + eps) + beta
  dense j: W[out][in], then b[out]
"""
import sys, json, argparse, hashlib, struct
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine')); sys.path.insert(0, str(ROOT / 'engine' / 'speed_model'))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--cfg', default='cnn_r100_w256_joint_deploy'); ap.add_argument('--n_check', type=int, default=500)
    ap.add_argument('--out', default=str(ROOT / 'IDRNav/app/src/main/assets/model'))
    a = ap.parse_args(); import torch; from train import build_model, load, window_index, get_windows
    mdir = ROOT / 'data/speed_model/models'; meta = torch.load(mdir / f'{a.cfg}.meta.pt', weights_only=False); sd = torch.load(mdir / f'{a.cfg}.pt'); cfg = meta['cfg']
    kind, win, rate, width = cfg['model'], cfg['win'], cfg['rate'], cfg['width']; assert kind == 'cnn' and not cfg['stop_head']
    mu, sdv = np.array(meta['norm'][0], np.float32), np.array(meta['norm'][1], np.float32)
    model = build_model(kind, win, 0, width)(False); model.load_state_dict(sd); model.eval()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    # ---- flatten with BN folded
    blobs = []; layers = []; off = 0
    def push(arr):
        nonlocal off; arr = np.ascontiguousarray(arr, dtype=np.float32); blobs.append(arr); o = off; off += arr.size; return o
    convs = [(6, width, 7, 2), (width, 2 * width, 5, 2), (2 * width, 2 * width, 5, 2), (2 * width, 3 * width, 3, 2)]
    for i, (ci, co, k, s) in enumerate(convs):
        W = sd[f'net.{3 * i}.weight'].numpy().astype(np.float64); b = sd[f'net.{3 * i}.bias'].numpy().astype(np.float64)
        g = sd[f'net.{3 * i + 1}.weight'].numpy().astype(np.float64); beta = sd[f'net.{3 * i + 1}.bias'].numpy().astype(np.float64)
        rm = sd[f'net.{3 * i + 1}.running_mean'].numpy().astype(np.float64); rv = sd[f'net.{3 * i + 1}.running_var'].numpy().astype(np.float64)
        scale = g / np.sqrt(rv + 1e-5); Wf = W * scale[:, None, None]; bf = (b - rm) * scale + beta
        assert W.shape == (co, ci, k)
        wo = push(Wf); bo = push(bf)
        layers.append(dict(type='conv1d', index=i, in_ch=ci, out_ch=co, kernel=k, stride=s, pad=k // 2, activation='relu', bn_folded=True, w_offset=wo, w_shape=[co, ci, k], b_offset=bo))
    for j, (di, do, act) in enumerate(((3 * width, 64, 'relu'), (64, 2, 'linear'))):
        W = sd[f'head.fc.{2 * j}.weight'].numpy(); b = sd[f'head.fc.{2 * j}.bias'].numpy(); assert W.shape == (do, di)
        wo = push(W); bo = push(b)
        layers.append(dict(type='dense', index=j, in_features=di, out_features=do, activation=act, w_offset=wo, w_shape=[do, di], b_offset=bo))
    flat = np.concatenate([x.ravel() for x in blobs]).astype('<f4'); wb = flat.tobytes(); (out / 'weights.bin').write_bytes(wb)
    n_params = int(sum(p.numel() for p in model.parameters())); n_bn = sum(2 * co for (_, co, _, _) in convs)   # gamma+beta per channel are folded away
    # ---- fixtures: real windows from the 100 Hz dataset of both roads (stands included), PyTorch outputs as the truth
    d = load(cfg['tag'], rate); ends = window_index(d, win, max(1, rate // 10), 1.0, 0); rng = np.random.default_rng(1); sel = np.sort(rng.choice(ends, min(a.n_check, len(ends)), replace=False))
    X = get_windows(d, sel, win).astype(np.float32); Xn = ((X - mu) / sdv).astype(np.float32)
    with torch.no_grad(): ref = model(torch.tensor(Xn)).numpy().astype(np.float32)
    (out / f'windows_{len(sel)}.bin').write_bytes(X.astype('<f4').tobytes()); (out / f'expected_{len(sel)}.bin').write_bytes(ref.astype('<f4').tobytes())
    side = dict(n=int(len(sel)), window=win, channels=6, layout='[n][window][channel] raw m/s2 and rad/s, gravity and gyro bias left in',
                t_s=[float(x) for x in d['t'][sel]], run_id=[int(x) for x in d['run_id'][sel]], session=[d['runs'][int(r)]['session'] for r in d['run_id'][sel]],
                v_gnss=[None if not np.isfinite(v) else float(v) for v in d['v'][sel]], phase=[int(p) for p in d['phase'][sel]])
    (out / f'windows_{len(sel)}.json').write_text(json.dumps(side))
    # ---- verify the folded weights reproduce the model in numpy (float32) before trusting the pack
    def fwd(xn):
        h = xn.T.astype(np.float32)   # [6, 256]
        for L in layers:
            if L['type'] == 'conv1d':
                co, ci, k = L['w_shape']; W = flat[L['w_offset']:L['w_offset'] + co * ci * k].reshape(co, ci, k); b = flat[L['b_offset']:L['b_offset'] + co]
                s, p = L['stride'], L['pad']; n_in = h.shape[1]; n_out = (n_in + 2 * p - k) // s + 1; hp = np.zeros((ci, n_in + 2 * p), np.float32); hp[:, p:p + n_in] = h
                o = np.zeros((co, n_out), np.float32)
                for t in range(n_out): o[:, t] = np.tensordot(W, hp[:, t * s:t * s + k], axes=([1, 2], [0, 1])) + b
                h = np.maximum(o, 0)
            else:
                do, di = L['w_shape']; W = flat[L['w_offset']:L['w_offset'] + do * di].reshape(do, di); b = flat[L['b_offset']:L['b_offset'] + do]
                if h.ndim == 2: h = h.mean(1)
                h = W @ h + b
                if L['activation'] == 'relu': h = np.maximum(h, 0)
        return h
    chk = np.stack([fwd(Xn[i]) for i in range(min(50, len(Xn)))]); err = float(np.abs(chk - ref[:len(chk)]).max())
    mj = dict(version=a.cfg, source_pt=f'data/speed_model/models/{a.cfg}.pt', window=win, rate_hz=rate, channels=['ax', 'ay', 'az', 'gx', 'gy', 'gz'], input_layout='[window][channel], z-scored per channel',
              norm_mean=mu.tolist(), norm_std=sdv.tolist(), output='[mu, logvar]; v = max(mu, 0); sigma = exp(0.5 * clamp(logvar, -6, 4))',
              dtype='float32 little-endian', n_floats=int(flat.size), n_params_pytorch=n_params, n_params_folded=int(flat.size), bn_eps=1e-5, layers=layers,
              weights_sha256=hashlib.sha256(wb).hexdigest(), numpy_fold_check_max_abs_diff=err,
              fixtures=dict(windows=f'windows_{len(sel)}.bin', expected=f'expected_{len(sel)}.bin', sidecar=f'windows_{len(sel)}.json', n=int(len(sel)), tolerance_abs=1e-4))
    (out / 'model.json').write_text(json.dumps(mj, indent=1))
    print(json.dumps(dict(weights_bytes=len(wb), n_floats=int(flat.size), n_params=n_params, fold_check=err, fixtures=int(len(sel)), out=str(out)), indent=1))
    assert err < 1e-4, f'folded numpy forward pass disagrees with PyTorch: {err}'

if __name__ == '__main__':
    main()
