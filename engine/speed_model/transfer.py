"""Cross-road / rider-held-out transfer: apply a model trained on one route to every kept run of another and score it.
Usage: .venv/bin/python engine/speed_model/transfer.py --train_tag route1 --test_tag route2 (--gbr | --cfg cnn_r100_w256_deploy) [--name xfer_gbr]
Writes predictions to data/speed_model/pred/<name>/ (for filter.py --pred <name> --tag <test_tag>) and appends to results/summary.
"""
import sys, json, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent))
from evaluate import kept_runs
from train import load, window_index, get_windows, features, train_gbr, score_run, build_model

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--train_tag', default='route1'); ap.add_argument('--test_tag', default='route2'); ap.add_argument('--gbr', action='store_true'); ap.add_argument('--cfg', default=''); ap.add_argument('--name', default=''); ap.add_argument('--rate', type=int, default=100); ap.add_argument('--win', type=int, default=256)
    a = ap.parse_args(); name = a.name or (f'xfer_{a.train_tag}_to_{a.test_tag}_' + ('gbr' if a.gbr else a.cfg)); stride = a.rate // 10
    dte = load(a.test_tag, a.rate); qa_te = kept_runs(f'data/qa/{a.test_tag}.csv', f'data/{a.test_tag}/sessions'); ends_te = window_index(dte, a.win, stride, 1.0, 0); rid_te = dte['run_id'][ends_te]
    if a.gbr:
        dtr = load(a.train_tag, a.rate); ends_tr = window_index(dtr, a.win, stride, 0.3, 0); Xtr = get_windows(dtr, ends_tr, a.win); Ftr = features(Xtr, a.rate); ytr = dtr['v'][ends_tr]
        class A: pass
        predict, info = train_gbr(Xtr, ytr, Ftr, Xtr[:200], ytr[:200], Ftr[:200], a.rate, A(), 0); need_feat = True
    else:
        import torch; mdir = Path('data/speed_model/models'); meta = torch.load(mdir / f'{a.cfg}.meta.pt', weights_only=False); sd = torch.load(mdir / f'{a.cfg}.pt'); cfg = meta['cfg']
        model = build_model(cfg['model'], cfg['win'], 0, cfg['width'])(bool(cfg['stop_head'])); model.load_state_dict(sd); model.eval(); mu = np.array(meta['norm'][0], np.float32); sdv = np.array(meta['norm'][1], np.float32)
        def predict(X, F):
            with torch.no_grad(): o = model(torch.tensor((X - mu) / sdv, dtype=torch.float32)).numpy()
            return o[:, 0], np.exp(0.5 * np.clip(o[:, 1], -6, 4))
        need_feat = False
    rows = []
    for ri in range(len(qa_te)):
        m = rid_te == ri; Xte = get_windows(dte, ends_te[m], a.win); Fte = features(Xte, a.rate) if need_feat else None; mu_, sig_ = predict(Xte, Fte)
        r = score_run(dte, ri, ends_te[m], mu_, sig_, a.win, a.rate, a.test_tag, name); r.update(fold=-1, cfg=name, model='gbr' if a.gbr else a.cfg, rate=a.rate, win=a.win, split='transfer', aug=1, seed=0, params=0, epochs=0, val_nll=np.nan); rows.append(r)
        print(f"[{name}] run{r['run']} {r['dir']}: MAE {r.get('mae', np.nan):.3f} bias {r.get('bias', np.nan):+.3f} cov68 {r.get('cov68', np.nan):.2f} | drift c30 {r.get('c30_drift_pct', np.nan):.1f}% c60 {r.get('c60_drift_pct', np.nan):.1f}% turn {r.get('turn_drift_pct', np.nan):.1f}% | false stops {r['false_stops']}", flush=True)
    df = pd.DataFrame(rows); out = Path('data/speed_model/results.csv'); df.to_csv(out, mode='a', header=not out.exists(), index=False)
    print('SUMMARY ' + json.dumps(dict(cfg=name, n=len(df), mae_med=round(df.mae.median(), 3), mae_worst=round(df.mae.max(), 3), bias_med=round(df.bias.median(), 3), c30_med=round(df.c30_drift_pct.median(), 2), c30_worst=round(df.c30_drift_pct.max(), 2), c60_med=round(df.c60_drift_pct.median(), 2) if 'c60_drift_pct' in df else None)))

if __name__ == '__main__':
    main()
