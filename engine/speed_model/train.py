"""Speed-model sweep (step 4). Trains one configuration under leave-one-run-out or grouped 5-fold and scores every held-out run:
speed MAE (moving), bias, NLL, 1-sigma coverage, stop latency / false stops under the physical stop rule, and the replay drift
at every cut with the step-3 heading (variant kfc). Results are appended to data/speed_model/results.csv; predictions at 10 Hz
are written to data/speed_model/pred/<config>/<session>.csv for the filter step.

Usage: .venv/bin/python engine/speed_model/train.py --model cnn --rate 100 --win 256 --split gk5 [--epochs 40 --aug 1 --seed 0 --stands 0.3 --stop_head 0]
Models: gbr (hand features + GradientBoosting, the bar to beat), cnn (strided Conv1d stack), resnet (residual 1-D), tcn (dilated
causal), cnnfeat (cnn embedding + hand features), cnngru (conv front-end + GRU over the window, stateless), all with a Gaussian
head (mu, logvar) trained by NLL (+ MSE warm-up weight). Inputs: bike-frame 6-ch window, per-channel z-score from the training
runs only. Augmentation (train only): rotation +-5 deg about a random axis applied to accel and gyro alike, gain +-5 %, white
noise, time-warp +-5 %, random window offset inside the stride. Physical stop rule (hard override): vibration RMS < STILL_RMS
and gyro RMS < STILL_GYR over the last 0.5 s => speed 0. Smoothing: 1 s exponential + 3 m/s^2 rate limit (the filter does this
with sigma later). Nothing from a held-out run is used for any choice: early stopping uses 2 inner-validation runs.
"""
import sys, math, json, argparse, time
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent))
from evaluate import kept_runs, kept_runs_tags, Run, position_metrics, loro_splits, grouped_folds
from heading import run_variant

STILL_RMS = 0.6; STILL_GYR = 0.06; BANDS = [(0.5, 2), (2, 5), (5, 12), (12, 25), (25, 49), (49, 95)]

# ------------------------------------------------------------------ data
def load(tag, rate):
    """One route ('route2') or a joint set ('route1+route2': arrays concatenated, run ids offset, each run dict carries its 'tag')."""
    if '+' in tag:
        parts = [load(t, rate) for t in tag.split('+')]; off = 0; cat = dict(imu=[], t=[], run_id=[], v=[], phase=[]); runs = []
        for part in parts:
            for key in ('imu', 't', 'v', 'phase'): cat[key].append(part[key])
            cat['run_id'].append(part['run_id'].astype(np.int32) + off); runs += part['runs']; off += len(part['runs'])
        return dict(imu=np.vstack(cat['imu']), t=np.concatenate(cat['t']), run_id=np.concatenate(cat['run_id']), v=np.concatenate(cat['v']), phase=np.concatenate(cat['phase']), runs=runs, rate=parts[0]['rate'], lag=[p['lag'] for p in parts])
    z = np.load(f'data/speed_model/{tag}_{rate}hz.npz', allow_pickle=True); runs = list(z['runs'])
    for rd in runs: rd['tag'] = tag
    return dict(imu=z['imu'], t=z['t'], run_id=z['run_id'], v=z['v'], phase=z['phase'], runs=runs, rate=int(z['rate']), lag=float(z['lag']))

def window_index(d, win, stride, stands=0.3, seed=0):
    """End indices of valid windows: all samples in one phase, label finite; stands subsampled by `stands`."""
    rng = np.random.default_rng(seed); ends = []; rid = d['run_id']; ph = d['phase']; v = d['v']
    for r in np.unique(rid):
        idx = np.where(rid == r)[0]; i0 = idx[0]; n = len(idx)
        for e in range(win, n + 1, stride):
            k = i0 + e - 1; p = ph[i0 + e - win:k + 1]
            if p[0] < 0 or (p != p[0]).any() or not np.isfinite(v[k]): continue
            if p[0] != 1 and rng.random() > stands: continue
            ends.append(k)
    return np.array(ends)

def get_windows(d, ends, win):
    X = np.stack([d['imu'][e - win + 1:e + 1] for e in ends]); return X

def features(X, rate):
    """Hand features per window (rate-agnostic): RMS per axis, |a| band energies, spectral peaks, gyro stats."""
    a = X[:, :, :3]; g = X[:, :, 3:]; n = X.shape[1]; freqs = np.fft.rfftfreq(n, 1 / rate)
    d = a - a.mean(1, keepdims=True); rms = np.sqrt((d ** 2).mean(1)); tot = np.sqrt((d ** 2).sum(2).mean(1))
    am = np.linalg.norm(a, axis=2); spec = np.abs(np.fft.rfft(am - am.mean(1, keepdims=True), axis=1)) ** 2 / n
    bands = [np.log10(spec[:, (freqs >= lo) & (freqs < hi)].sum(1) + 1e-6) for lo, hi in BANDS if lo < rate / 2]
    sel = (freqs >= 0.5) & (freqs <= 8); pk = freqs[sel][np.argmax(spec[:, sel], axis=1)]; pkp = np.log10(spec[:, sel].max(1) + 1e-6)
    specz = np.abs(np.fft.rfft(d[:, :, 2], axis=1)) ** 2 / n; pkz = freqs[sel][np.argmax(specz[:, sel], axis=1)]
    grms = np.sqrt((g ** 2).mean(1)); gmag = np.linalg.norm(g, axis=2).mean(1); gz = np.abs(g[:, :, 2]).mean(1)
    F = np.column_stack([rms, tot, np.log10(tot + 1e-6), *bands, pk, pkp, pkz, grms, gmag, gz]); return F.astype(np.float32)

def still_flags(X, rate):
    """Physical stop rule on the last 0.5 s of each window."""
    m = max(2, int(0.5 * rate)); a = X[:, -m:, :3]; g = X[:, -m:, 3:]
    d = a - a.mean(1, keepdims=True); vib = np.sqrt((d ** 2).sum(2).mean(1)); grms = np.sqrt((g ** 2).sum(2).mean(1))
    return (vib < STILL_RMS) & (grms < STILL_GYR)

def smooth(v, t, tau=1.0, amax=3.0):
    out = v.copy()
    for k in range(1, len(v)):
        dt = t[k] - t[k - 1]; a = 1 - math.exp(-dt / tau); target = out[k - 1] + a * (v[k] - out[k - 1]); out[k] = np.clip(target, out[k - 1] - amax * dt, out[k - 1] + amax * dt)
    return np.clip(out, 0, None)

# ------------------------------------------------------------------ augmentation
def rotmat(axis, ang):
    axis = axis / np.linalg.norm(axis); K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K
def augment(X, rng, rot_deg=5.0, gain=0.05, noise=(0.05, 0.002), warp=0.05):
    X = X.copy(); n, w, _ = X.shape
    for i in range(n):
        R = rotmat(rng.normal(size=3), math.radians(rng.uniform(-rot_deg, rot_deg)))
        X[i, :, :3] = X[i, :, :3] @ R.T; X[i, :, 3:] = X[i, :, 3:] @ R.T
        if warp > 0:
            f = 1 + rng.uniform(-warp, warp); src = np.clip(np.arange(w) * f, 0, w - 1); X[i] = np.stack([np.interp(src, np.arange(w), X[i, :, c]) for c in range(6)], 1)
    X[:, :, :3] *= (1 + rng.uniform(-gain, gain, (n, 1, 1))); X[:, :, 3:] *= (1 + rng.uniform(-gain, gain, (n, 1, 1)))
    X[:, :, :3] += rng.normal(0, noise[0], (n, w, 3)); X[:, :, 3:] += rng.normal(0, noise[1], (n, w, 3)); return X

# ------------------------------------------------------------------ models (torch)
def build_model(kind, win, n_feat=0, width=32):
    import torch, torch.nn as nn
    class Head(nn.Module):
        def __init__(self, d, stop):
            super().__init__(); self.fc = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, 3 if stop else 2))
        def forward(self, h): return self.fc(h)
    class CNN(nn.Module):
        def __init__(self, stop=False, feat=0):
            super().__init__(); c = width
            self.net = nn.Sequential(nn.Conv1d(6, c, 7, stride=2, padding=3), nn.BatchNorm1d(c), nn.ReLU(), nn.Conv1d(c, 2 * c, 5, stride=2, padding=2), nn.BatchNorm1d(2 * c), nn.ReLU(),
                                     nn.Conv1d(2 * c, 2 * c, 5, stride=2, padding=2), nn.BatchNorm1d(2 * c), nn.ReLU(), nn.Conv1d(2 * c, 3 * c, 3, stride=2, padding=1), nn.BatchNorm1d(3 * c), nn.ReLU())
            self.head = Head(3 * c + feat, stop)
        def forward(self, x, f=None):
            h = self.net(x.transpose(1, 2)).mean(2); return self.head(h if f is None else torch.cat([h, f], 1))
    class ResBlock(nn.Module):
        def __init__(self, ci, co, s):
            super().__init__(); self.c1 = nn.Conv1d(ci, co, 5, stride=s, padding=2); self.b1 = nn.BatchNorm1d(co); self.c2 = nn.Conv1d(co, co, 5, padding=2); self.b2 = nn.BatchNorm1d(co)
            self.sk = nn.Sequential(nn.Conv1d(ci, co, 1, stride=s), nn.BatchNorm1d(co)) if (ci != co or s != 1) else nn.Identity()
        def forward(self, x):
            import torch.nn.functional as F; return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x))))) + self.sk(x))
    class ResNet(nn.Module):
        def __init__(self, stop=False):
            super().__init__(); c = width; self.stem = nn.Sequential(nn.Conv1d(6, c, 7, stride=2, padding=3), nn.BatchNorm1d(c), nn.ReLU())
            self.blocks = nn.Sequential(ResBlock(c, c, 1), ResBlock(c, 2 * c, 2), ResBlock(2 * c, 2 * c, 2), ResBlock(2 * c, 3 * c, 2)); self.head = Head(3 * c, stop)
        def forward(self, x, f=None): return self.head(self.blocks(self.stem(x.transpose(1, 2))).mean(2))
    class TCN(nn.Module):
        def __init__(self, stop=False):
            super().__init__(); c = width; layers = []; ci = 6
            for i, dil in enumerate((1, 2, 4, 8, 16)):
                layers += [nn.ConstantPad1d((2 * dil, 0), 0.0), nn.Conv1d(ci, 2 * c, 3, dilation=dil), nn.BatchNorm1d(2 * c), nn.ReLU()]; ci = 2 * c
            self.net = nn.Sequential(*layers); self.head = Head(2 * c, stop)
        def forward(self, x, f=None): h = self.net(x.transpose(1, 2)); return self.head(h[:, :, -max(1, h.shape[2] // 4):].mean(2))
    class CNNGRU(nn.Module):
        def __init__(self, stop=False):
            super().__init__(); c = width
            self.net = nn.Sequential(nn.Conv1d(6, c, 7, stride=2, padding=3), nn.BatchNorm1d(c), nn.ReLU(), nn.Conv1d(c, 2 * c, 5, stride=2, padding=2), nn.BatchNorm1d(2 * c), nn.ReLU(), nn.Conv1d(2 * c, 2 * c, 5, stride=2, padding=2), nn.BatchNorm1d(2 * c), nn.ReLU())
            self.gru = nn.GRU(2 * c, 2 * c, batch_first=True); self.head = Head(2 * c, stop)
        def forward(self, x, f=None): h = self.net(x.transpose(1, 2)).transpose(1, 2); _, hn = self.gru(h); return self.head(hn[0])
    return {'cnn': lambda stop: CNN(stop), 'resnet': lambda stop: ResNet(stop), 'tcn': lambda stop: TCN(stop), 'cnnfeat': lambda stop: CNN(stop, n_feat), 'cnngru': lambda stop: CNNGRU(stop)}[kind]

def nll(out, y, stop_y=None, w_mse=0.0):
    import torch, torch.nn.functional as F
    mu, lv = out[:, 0], out[:, 1].clamp(-6, 4); loss = 0.5 * (lv + (y - mu) ** 2 / torch.exp(lv)).mean() + w_mse * ((y - mu) ** 2).mean()
    if stop_y is not None and out.shape[1] > 2: loss = loss + 0.2 * F.binary_cross_entropy_with_logits(out[:, 2], stop_y)
    return loss

def train_torch(kind, Xtr, ytr, Ftr, Xva, yva, Fva, rate, args, seed):
    import torch; torch.manual_seed(seed); rng = np.random.default_rng(seed); torch.set_num_threads(max(1, args.threads))
    model = build_model(kind, Xtr.shape[1], Ftr.shape[1] if Ftr is not None else 0, args.width)(bool(args.stop_head))
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4); sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.epochs)
    mu = Xtr.reshape(-1, 6).mean(0); sd = Xtr.reshape(-1, 6).std(0) + 1e-6; fmu = Ftr.mean(0) if Ftr is not None else None; fsd = Ftr.std(0) + 1e-6 if Ftr is not None else None
    def prep(X, F): 
        xt = torch.tensor((X - mu) / sd, dtype=torch.float32); ft = torch.tensor((F - fmu) / fsd, dtype=torch.float32) if F is not None else None; return xt, ft
    Xv, Fv = prep(Xva, Fva); yv = torch.tensor(yva, dtype=torch.float32); best = (1e9, None); bad = 0; n = len(Xtr)
    for ep in range(args.epochs):
        model.train(); perm = rng.permutation(n); tot = 0.0
        for b in range(0, n, args.batch):
            idx = perm[b:b + args.batch]; Xb = augment(Xtr[idx], rng) if args.aug else Xtr[idx]; Fb = features(Xb, rate) if Ftr is not None else None
            xb, fb = prep(Xb, Fb); yb = torch.tensor(ytr[idx], dtype=torch.float32); sb = (yb < 0.3).float() if args.stop_head else None
            opt.zero_grad(); loss = nll(model(xb, fb), yb, sb, w_mse=max(0.0, 1.0 - ep / 10)); loss.backward(); opt.step(); tot += float(loss) * len(idx)
        sched.step(); model.eval()
        with torch.no_grad(): vl = float(nll(model(Xv, Fv), yv))
        if vl < best[0] - 1e-4: best = (vl, {k: v.clone() for k, v in model.state_dict().items()}); bad = 0
        else: bad += 1
        if bad >= args.patience: break
    model.load_state_dict(best[1]); model.eval(); train_torch.last_model = model
    def predict(X, F):
        with torch.no_grad(): o = model(*prep(X, F)).numpy()
        return o[:, 0], np.exp(0.5 * np.clip(o[:, 1], -6, 4))
    n_par = sum(p.numel() for p in model.parameters()); return predict, dict(val_nll=round(best[0], 4), epochs=ep + 1, params=n_par, norm=(mu.tolist(), sd.tolist()))

def train_gbr(Xtr, ytr, Ftr, Xva, yva, Fva, rate, args, seed):
    from sklearn.ensemble import GradientBoostingRegressor
    m = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed).fit(Ftr, ytr)
    res = yva - m.predict(Fva); sig = float(np.std(res)) if len(res) > 10 else 0.3
    return (lambda X, F: (np.clip(m.predict(F), 0, None), np.full(len(F), sig))), dict(val_nll=np.nan, epochs=0, params=300 * 7, norm=None)

# ------------------------------------------------------------------ evaluation on a held-out run
def score_run(d, ri, ends, pred_mu, pred_sig, win, rate, tag, cfg, cuts=('c10', 'c30', 'c60', 'turn')):
    rd = d['runs'][ri]; k = ends; t = d['t'][k]; y = d['v'][k]; ph = d['phase'][k]
    X = get_windows(d, ends, win); still = still_flags(X, rate)
    raw = np.clip(pred_mu, 0, None); over = raw.copy(); over[still] = 0.0; sm = smooth(over, t); sm[still] = 0.0      # physical stop rule = hard override, after smoothing
    mv = (y > 1.0) & (ph == 1); out = dict(run=rd['run'], dir=rd['dir'], n_win=len(k), n_moving=int(mv.sum()))
    if mv.sum() > 10:
        out.update(mae_raw=float(np.mean(np.abs(raw - y)[mv])), mae=float(np.mean(np.abs(sm - y)[mv])), bias=float(np.mean((sm - y)[mv])), rmse=float(np.sqrt(np.mean((sm - y)[mv] ** 2))),
                   nll=float(np.mean(0.5 * (np.log(pred_sig[mv] ** 2) + (raw[mv] - y[mv]) ** 2 / pred_sig[mv] ** 2))), cov68=float(np.mean(np.abs(raw - y)[mv] < pred_sig[mv])), sig_mean=float(pred_sig[mv].mean()),
                   mae_slow=float(np.mean(np.abs(sm - y)[(y > 0.5) & (y < 2.0) & (ph == 1)])) if ((y > 0.5) & (y < 2.0) & (ph == 1)).sum() > 5 else np.nan)
    # stop behaviour at the end-of-ride stop: latency = time from the last GNSS fix with v > 0.5 to the first zeroed output; false stops = still hits while y > 1
    out['false_stops'] = int((still & (y > 1.0)).sum()); ride = ph == 1
    if ride.any():
        t_stop = float(t[ride & (y > 0.5)].max()) if (ride & (y > 0.5)).any() else np.nan
        after = (t > t_stop) & (sm < 0.2); out['stop_latency_s'] = float(t[after].min() - t_stop) if after.any() and np.isfinite(t_stop) else np.nan
    # replay: heading kfc + speed -> position; drift per cut
    run = Run(rd['session'], f"data/{rd.get('tag', tag)}/sessions"); run.flags = rd['flags']; outs, _, _ = run_variant(run, 'kfc', run.cuts)
    v10 = np.interp(run.t, t, sm); v10[run.t < t[0]] = 0.0
    for c, tc in run.cuts.items():
        psi = outs[c]; k0 = int(np.searchsorted(run.t, tc)); x = run.gx.copy(); yy = run.gy.copy(); dt = np.diff(run.t, prepend=run.t[0])
        for i in range(k0, len(run.t)): x[i] = x[i - 1] + math.cos(psi[i]) * v10[i] * dt[i]; yy[i] = yy[i - 1] + math.sin(psi[i]) * v10[i] * dt[i]
        pm = position_metrics(run, run.t, x, yy, tc); out[f'{c}_drift_pct'] = pm['drift_pct']; out[f'{c}_end_m'] = pm['end_m']; out[f'{c}_after_stop_m'] = pm['after_stop_m']; out[f'{c}_rmse_m'] = pm['rmse_m']
    pdir = Path('data/speed_model/pred') / cfg; pdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({'t_s': t, 'v_gnss': y, 'v_raw': raw, 'sigma': pred_sig, 'still': still.astype(int), 'v_model': sm, 'phase': ph}).to_csv(pdir / f"{rd['session']}.csv", index=False, float_format='%.4f')
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tag', default='route1'); ap.add_argument('--model', default='cnn'); ap.add_argument('--rate', type=int, default=100); ap.add_argument('--win', type=int, default=256)
    ap.add_argument('--split', default='gk5'); ap.add_argument('--epochs', type=int, default=40); ap.add_argument('--patience', type=int, default=8); ap.add_argument('--batch', type=int, default=256); ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--aug', type=int, default=1); ap.add_argument('--seed', type=int, default=0); ap.add_argument('--stands', type=float, default=0.3); ap.add_argument('--stop_head', type=int, default=0); ap.add_argument('--width', type=int, default=32)
    ap.add_argument('--threads', type=int, default=8); ap.add_argument('--name', default=''); ap.add_argument('--folds', default='')
    ap.add_argument('--train_all', type=int, default=0, help='train one deployment model on all kept runs (2 inner-validation runs for early stopping) and save it')
    ap.add_argument('--test_tag', default='', help='with a joint --tag and --split loro: keep only the folds whose held-out run is on this route')
    args = ap.parse_args(); d = load(args.tag, args.rate); stride = max(1, args.rate // 10); qa = kept_runs_tags(args.tag)
    assert [r['session'] for r in d['runs']] == list(qa['session']), 'dataset run order != kept-run order (rebuild the npz)'
    cfg = args.name or f"{args.model}_r{args.rate}_w{args.win}_aug{args.aug}_st{args.stands}_sh{args.stop_head}_wd{args.width}_s{args.seed}"
    ends = window_index(d, args.win, stride, args.stands, args.seed); rid = d['run_id'][ends]; y = d['v'][ends]
    splits = list(loro_splits(qa)) if args.split == 'loro' else list(grouped_folds(qa, 5))
    if args.test_tag:                                                 # 'loro on one route of a joint set': only folds whose test run belongs to that route
        splits = [(tr, te) for tr, te in splits if all(qa.loc[i, 'tag'] == args.test_tag for i in te)]
    if args.folds: splits = [splits[int(i)] for i in args.folds.split(',')]
    need_feat = args.model in ('gbr', 'cnnfeat')
    if args.train_all:
        import torch; tr = list(range(len(qa))); rng = np.random.default_rng(args.seed); inner = list(rng.choice(tr, 2, replace=False)); tr2 = [i for i in tr if i not in inner]
        mtr = np.isin(rid, tr2); mva = np.isin(rid, inner); Xtr = get_windows(d, ends[mtr], args.win); Xva = get_windows(d, ends[mva], args.win)
        Ftr = features(Xtr, args.rate) if need_feat else None; Fva = features(Xva, args.rate) if need_feat else None
        predict, info = train_torch(args.model, Xtr, y[mtr], Ftr, Xva, y[mva], Fva, args.rate, args, args.seed)
        out = Path('data/speed_model/models'); out.mkdir(parents=True, exist_ok=True)
        torch.save(dict(state=predict.__closure__ and None, cfg=vars(args), norm=info['norm'], params=info['params'], epochs=info['epochs'], val_nll=info['val_nll'], inner_runs=[int(qa.loc[i, 'run']) for i in inner]), out / f'{cfg}.meta.pt')
        torch.save(train_torch.last_model.state_dict(), out / f'{cfg}.pt'); print(f"saved deployment model {out / f'{cfg}.pt'} ({info['params']} params, {info['epochs']} epochs, inner runs {[int(qa.loc[i, 'run']) for i in inner]}, val NLL {info['val_nll']})"); return
    rows = []; t0 = time.time(); need_feat = args.model in ('gbr', 'cnnfeat')
    for fi, (tr, te) in enumerate(splits):
        rng = np.random.default_rng(args.seed + fi); inner = list(rng.choice(tr, 2, replace=False)); tr2 = [i for i in tr if i not in inner]
        mtr = np.isin(rid, tr2); mva = np.isin(rid, inner)
        Xtr = get_windows(d, ends[mtr], args.win); Xva = get_windows(d, ends[mva], args.win); ytr = y[mtr]; yva = y[mva]
        Ftr = features(Xtr, args.rate) if need_feat else None; Fva = features(Xva, args.rate) if need_feat else None
        if args.model == 'gbr': predict, info = train_gbr(Xtr, ytr, Ftr, Xva, yva, Fva, args.rate, args, args.seed)
        else: predict, info = train_torch(args.model, Xtr, ytr, Ftr, Xva, yva, Fva, args.rate, args, args.seed)
        for ri in te:
            m = rid == ri; Xte = get_windows(d, ends[m], args.win); Fte = features(Xte, args.rate) if need_feat else None
            mu, sig = predict(Xte, Fte); r = score_run(d, ri, ends[m], mu, sig, args.win, args.rate, args.tag, cfg); r.update(fold=fi, cfg=cfg, model=args.model, rate=args.rate, win=args.win, split=args.split, aug=args.aug, seed=args.seed, params=info['params'], epochs=info['epochs'], val_nll=info['val_nll'])
            rows.append(r); print(f"[{cfg}] fold {fi} run{r['run']} {r['dir']}: MAE {r.get('mae', np.nan):.3f} bias {r.get('bias', np.nan):+.3f} cov68 {r.get('cov68', np.nan):.2f} | drift c30 {r.get('c30_drift_pct', np.nan):.1f}% c10 {r.get('c10_drift_pct', np.nan):.1f}% turn {r.get('turn_drift_pct', np.nan):.1f}% | false stops {r['false_stops']} stop lat {r.get('stop_latency_s', np.nan):.1f}s | {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows); out = Path('data/speed_model/results.csv')
    df.to_csv(out, mode='a', header=not out.exists(), index=False)
    s = dict(cfg=cfg, n=len(df), mae_med=df.mae.median(), mae_worst=df.mae.max(), bias_med=df.bias.median(), cov68_med=df.cov68.median(), c30_med=df.c30_drift_pct.median(), c30_worst=df.c30_drift_pct.max(), c30_under10=int((df.c30_drift_pct < 10).sum()),
             c10_med=df.c10_drift_pct.median(), c10_under10=int((df.c10_drift_pct < 10).sum()), turn_med=df.turn_drift_pct.median(), turn_under10=int((df.turn_drift_pct < 10).sum()), after_stop_c30_med=df.c30_after_stop_m.median(), false_stops=int(df.false_stops.sum()), stop_lat_med=df.stop_latency_s.median(), params=int(df.params.iloc[0]), secs=round(time.time() - t0))
    print('SUMMARY ' + json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()}))
    so = Path('data/speed_model/summary.csv'); pd.DataFrame([s]).to_csv(so, mode='a', header=not so.exists(), index=False)

if __name__ == '__main__':
    main()
