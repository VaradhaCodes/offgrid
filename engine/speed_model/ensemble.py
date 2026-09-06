"""Seed-ensemble scorer: average the 10 Hz predictions of several configs (same windows) and re-score every held-out run
with the same metrics and replay as train.py. Usage: .venv/bin/python engine/speed_model/ensemble.py --cfgs a,b,c --name ens3
"""
import sys, json, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent))
from evaluate import kept_runs
from train import load, score_run

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--cfgs', required=True); ap.add_argument('--name', required=True); ap.add_argument('--tag', default='route1'); ap.add_argument('--rate', type=int, default=100); ap.add_argument('--win', type=int, default=256)
    a = ap.parse_args(); cfgs = a.cfgs.split(','); qa = kept_runs(f'data/qa/{a.tag}.csv', f'data/{a.tag}/sessions'); d = load(a.tag, a.rate); rows = []
    for ri, r in qa.iterrows():
        dfs = [pd.read_csv(f'data/speed_model/pred/{c}/{r["session"]}.csv').round({'t_s': 4}) for c in cfgs]
        common = dfs[0][['t_s']]
        for x in dfs[1:]: common = common.merge(x[['t_s']], on='t_s')
        dfs = [x.merge(common, on='t_s').sort_values('t_s').reset_index(drop=True) for x in dfs]; t = dfs[0].t_s.values   # ride windows are identical across seeds; stand windows are the seed-dependent subsample -> intersection
        mu = np.mean([x.v_raw.values for x in dfs], axis=0); sig = np.sqrt(np.maximum(np.mean([x.sigma.values ** 2 + x.v_raw.values ** 2 for x in dfs], axis=0) - mu ** 2, 1e-6))   # mixture variance
        idx = d['run_id'] == ri; tt = np.round(d['t'][idx], 4); ends = np.where(idx)[0][np.searchsorted(tt, t)]
        rr = score_run(d, ri, ends, mu, sig, a.win, a.rate, a.tag, a.name); rr.update(cfg=a.name, model='ensemble', rate=a.rate, win=a.win, split='gk5', aug=1, seed=-1, params=0, epochs=0, val_nll=np.nan, fold=-1); rows.append(rr)
        print(f"run{rr['run']}: MAE {rr.get('mae', np.nan):.3f} cov68 {rr.get('cov68', np.nan):.2f} | c30 {rr.get('c30_drift_pct', np.nan):.1f}% c10 {rr.get('c10_drift_pct', np.nan):.1f}%", flush=True)
    df = pd.DataFrame(rows); out = Path('data/speed_model/results.csv'); df.to_csv(out, mode='a', header=not out.exists(), index=False)
    s = dict(cfg=a.name, n=len(df), mae_med=df.mae.median(), mae_worst=df.mae.max(), bias_med=df.bias.median(), cov68_med=df.cov68.median(), c30_med=df.c30_drift_pct.median(), c30_worst=df.c30_drift_pct.max(), c30_under10=int((df.c30_drift_pct < 10).sum()), c10_med=df.c10_drift_pct.median(), c10_under10=int((df.c10_drift_pct < 10).sum()), turn_med=df.turn_drift_pct.median(), turn_under10=int((df.turn_drift_pct < 10).sum()), after_stop_c30_med=df.c30_after_stop_m.median(), false_stops=int(df.false_stops.sum()), stop_lat_med=df.stop_latency_s.median(), params=0, secs=0)
    print('SUMMARY ' + json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})); so = Path('data/speed_model/summary.csv'); pd.DataFrame([s]).to_csv(so, mode='a', header=not so.exists(), index=False)

if __name__ == '__main__':
    main()
