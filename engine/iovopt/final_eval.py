"""Final IO-VNBD evaluation of the step-10c engine (car track): learned outage speed (ensemble of held-out GRU runs) + bias-fitted
yaw heading + OSM road lock, on the exact step-10b protocol. Writes the per-mask table, the summaries and the position plot.

Usage: .venv/Scripts/python engine/iovopt/final_eval.py --pred gru_x,gru_x_s1,gru_x_s2 --tag final
Outputs (repo): data/qa/iovnbd_opt_<tag>.csv (seq, family, t0, distance, end error, drift per variant), data/qa/iovnbd_opt_<tag>_summary.csv,
data/qa/iovnbd_opt_<tag>.png (median-level drive at >= 54 km/h, the PS position plot). Big intermediates stay on D:.
Every speed prediction comes from a model that never saw the drive's family (leave-one-family-out); the road-lock and heading
settings were chosen on the six non-Vf families only (selection set); Vf is reported as the untouched check.
"""
import sys, argparse, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from multiprocessing import Pool
from core import load, all_seqs, masks_of, integrate, row, put_speed, summary

OSM = Path(r'D:\offgrid_iov\osm'); RUNS = Path(r'D:\offgrid_iov\runs'); REPO = Path(__file__).resolve().parents[2]
PF = dict(n=4000, sig_psi=8.0, sig_scale=0.03, sig_rel=8.0, walk=2.5, lost='free')

def job(args):
    seq, preds, cfg = args
    import roadpf; from heading2 import fit_heading2
    d = load(seq); P = [np.load(RUNS / f'{p}_pred.npz') for p in preds]; rows = []; tracks = {}
    for m in masks_of(d):
        key = f"{seq}|{m['m0']:.0f}"
        if key not in P[0].files: continue
        p = np.mean([x[key] for x in P], 0); v = put_speed(d, m, p)
        hh = fit_heading2(d, m, Wb=45, Ws=0); psi = d['psi'] if hh is None else hh[0]
        ks = np.arange(m['k0'], m['ke'] + 1); dt = d['t'][ks] - d['t'][ks - 1]
        v0 = np.full(len(v), d['fv'][m['i_cut']]); e_hold, xh, yh = integrate(d, m, v0, d['psi'])
        e_free, xf, yf = integrate(d, m, v, psi); fn = OSM / f"{seq}_{int(m['m0'])}.json"; status = 'no_osm'; out = None
        if fn.exists():
            g = roadpf.load_graph(fn)
            out, st = roadpf.run_pf(g, np.array(m['p0']), psi[ks], v[ks], dt, n=cfg['n'], sig_psi=cfg['sig_psi'], sig_scale=cfg['sig_scale'], sig_rel=cfg['sig_rel'],
                                    walk=cfg['walk'], rng=np.random.default_rng(int(m['m0']))); status = st['status']
        if out is None or status == 'lost': out = np.column_stack([xf, yf])                   # no road lock: the free dead-reckoning track
        e = float(np.hypot(out[-1, 0] - d['gx'][m['ke']], out[-1, 1] - d['gy'][m['ke']]))
        rows.append(row(d, m, 'offgrid', e, lock=status)); rows.append(row(d, m, 'offgrid_nomap', e_free)); rows.append(row(d, m, 'keep_last_speed', e_hold))
        tracks[key] = dict(truth=np.column_stack([d['gx'][ks], d['gy'][ks]]), offgrid=out, nomap=np.column_stack([xf, yf]), hold=np.column_stack([xh, yh]),
                           pre=np.column_stack([d['gx'][max(0, m['k0'] - 600):m['k0']], d['gy'][max(0, m['k0'] - 600):m['k0']]]),
                           post=np.column_stack([d['gx'][m['ke']:m['ke'] + 300], d['gy'][m['ke']:m['ke'] + 300]]), osm=str(fn))
    return rows, tracks

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pred', required=True); ap.add_argument('--tag', default='final'); ap.add_argument('--jobs', type=int, default=12)
    a = ap.parse_args(); preds = a.pred.split(','); T0 = time.time()
    with Pool(a.jobs) as pool: res = pool.map(job, [(s, preds, PF) for s in all_seqs()])
    rows = sum((r for r, _ in res), []); tracks = {}
    for _, t in res: tracks.update(t)
    df = pd.DataFrame(rows); df['m_per_km'] = (1000 * df.end_m / df.dist_m).round(1)
    out = REPO / 'data' / 'qa'; df.to_csv(out / f'iovnbd_opt_{a.tag}.csv', index=False)
    views = {'selection set (6 non-Vf families)': df[df.fam != 'Vf'], 'Vf (held-out check)': df[df.fam == 'Vf'], 'all masks': df, '>= 54 km/h': df[df.v_mean * 3.6 >= 54]}
    S = []
    for k, x in views.items():
        s = summary(x, k); s['m_per_km_median'] = x.groupby('variant').m_per_km.median(); s['view'] = k; S.append(s.reset_index())
    for f in sorted(df.fam.unique()):
        s = summary(df[df.fam == f], None); s['m_per_km_median'] = df[df.fam == f].groupby('variant').m_per_km.median(); s['view'] = f'family {f}'; S.append(s.reset_index())
    S = pd.concat(S); S.to_csv(out / f'iovnbd_opt_{a.tag}_summary.csv', index=False)
    print(S[S.variant == 'offgrid'][['view', 'masks', 'med', 'p90', 'u10', 'pooled', 'm_per_km_median']].to_string(index=False))
    print('road lock status:', df[df.variant == 'offgrid'].lock.value_counts().to_dict(), f'({time.time() - T0:.0f} s)')
    np.save(RUNS / f'final_{a.tag}_tracks.npy', tracks, allow_pickle=True); json.dump(dict(pred=preds, pf=PF), open(out / f'iovnbd_opt_{a.tag}.json', 'w'))

if __name__ == '__main__':
    main()
