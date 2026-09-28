"""Road-lock parameter sweep: every config on every mask in one pass (graph loaded once per mask), parallel over drives.

Usage: .venv/Scripts/python engine/iovopt/exp_pf.py --pred gru_x --name pfsweep_a [--grid default]
Choice rule for the final config: lowest median on the six non-Vf families (the selection set).
"""
import sys, argparse, itertools, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from multiprocessing import Pool
from core import load, all_seqs, masks_of, integrate, row, put_speed, summary

OSM = Path(r'D:\offgrid_iov\osm'); RUNS = Path(r'D:\offgrid_iov\runs')
GRIDS = {
    'default': dict(sig_psi=[8, 12, 18], sig_scale=[0.02, 0.05], sig_rel=[0, 6, 12], walk=[0.0, 0.5]),
    'small': dict(sig_psi=[12], sig_scale=[0.03], sig_rel=[0, 8], walk=[0.0]),
    'best': dict(sig_psi=[8], sig_scale=[0.05], sig_rel=[0], walk=[0.5]),
    'b3': dict(sig_psi=[8], sig_scale=[0.03, 0.05], sig_rel=[0, 8], walk=[1.0, 1.5, 2.5], n=[1000], lost=['free']),
    'b4': dict(sig_psi=[8, 6], sig_scale=[0.03], sig_rel=[8], walk=[2.5, 3.5, 5.0, 8.0], n=[1000, 2000], lost=['free']),
    'b5': dict(sig_psi=[8], sig_scale=[0.03], sig_rel=[8], walk=[0.0, 1.5, 3.5], vwalk=[0.0, 0.1, 0.2, 0.4], n=[2000], lost=['free']),
    'b6': dict(sig_psi=[8], sig_scale=[0.02, 0.03], sig_rel=[0, 8], walk=[1.0, 2.5, 3.5, 5.0], n=[2000], lost=['free']),
    'fin': dict(sig_psi=[8], sig_scale=[0.03], sig_rel=[8], walk=[2.5], n=[2000], lost=['free']),
    'b7': dict(sig_psi=[8], sig_scale=[0.03], sig_rel=[8], walk=[2.5], n=[2000], lost=['free'], lost_deg=[25.0, 35.0, 50.0], lost_s=[4.0, 6.0, 10.0]),
    'fin4': dict(sig_psi=[8], sig_scale=[0.03], sig_rel=[8], walk=[2.5], n=[4000], lost=['free']),
    'b2': dict(sig_psi=[8, 10], sig_scale=[0.05, 0.08], sig_rel=[0], walk=[0.5, 1.0], n=[1000, 2000], lost=['cont', 'free', 'none']),
    'oracle': dict(sig_psi=[8, 12], sig_scale=[0.0, 0.02], sig_rel=[0], walk=[0.0, 0.5]),
}

def speeds(d, m, preds):
    p = np.mean([P[f"{d['seq']}|{m['m0']:.0f}"] for P in preds], 0); return put_speed(d, m, p)

def job(args):
    seq, pred_names, cfgs, head_wb = args
    import roadpf; from heading2 import fit_heading2
    d = load(seq); preds = [np.load(RUNS / f'{p}_pred.npz') for p in pred_names]; rows = []
    for m in masks_of(d):
        if f"{seq}|{m['m0']:.0f}" not in preds[0].files: continue
        v = speeds(d, m, preds); hh = fit_heading2(d, m, Wb=head_wb, Ws=0); psi = d['psi'] if hh is None else hh[0]
        e_free, xf, yf = integrate(d, m, v, psi); rows.append(row(d, m, 'free', e_free))
        fn = OSM / f"{seq}_{int(m['m0'])}.json"; g = roadpf.load_graph(fn) if fn.exists() else None
        ks = np.arange(m['k0'], m['ke'] + 1); dt = d['t'][ks] - d['t'][ks - 1]
        for name, c in cfgs:
            if g is None: rows.append(row(d, m, name, e_free, status='no_osm')); continue
            out, st = roadpf.run_pf(g, np.array(m['p0']), psi[ks], v[ks], dt, n=c.get('n', 1000), sig_psi=c['sig_psi'], sig_scale=c['sig_scale'], sig_rel=c['sig_rel'],
                                    walk=c['walk'], vwalk=c.get('vwalk', 0.0), lost_s=c.get('lost_s', 6.0), lost_deg=c.get('lost_deg', 35.0), rng=np.random.default_rng(int(m['m0'])))
            if out is None: rows.append(row(d, m, name, e_free, status=st['status'])); continue
            if st['lost_at'] is not None and c.get('lost', 'cont') == 'free': rows.append(row(d, m, name, e_free, status=st['status'])); continue
            if st['lost_at'] is not None and c.get('lost', 'cont') == 'cont':
                k = st['lost_at']; ph = np.cumsum(np.cos(psi[ks]) * v[ks] * dt); qh = np.cumsum(np.sin(psi[ks]) * v[ks] * dt)
                out[k + 1:, 0] = out[k, 0] + ph[k + 1:] - ph[k]; out[k + 1:, 1] = out[k, 1] + qh[k + 1:] - qh[k]
            e = float(np.hypot(out[-1, 0] - d['gx'][m['ke']], out[-1, 1] - d['gy'][m['ke']])); rows.append(row(d, m, name, e, status=st['status']))
    return rows

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pred', default='gru_x'); ap.add_argument('--name', default='pfsweep'); ap.add_argument('--grid', default='default')
    ap.add_argument('--jobs', type=int, default=12); ap.add_argument('--head_wb', type=float, default=45.0)
    a = ap.parse_args(); G = GRIDS[a.grid]; keys = list(G); T0 = time.time()
    cfgs = [('pf_' + '_'.join(f'{k[:4]}{v}' for k, v in zip(keys, vals)), dict(zip(keys, vals))) for vals in itertools.product(*[G[k] for k in keys])]
    with Pool(a.jobs) as pool: rows = sum(pool.map(job, [(s, a.pred.split(','), cfgs, a.head_wb) for s in all_seqs()]), [])
    df = pd.DataFrame(rows); df.to_csv(RUNS / f'{a.name}.csv', index=False); print(f'{len(cfgs)} configs, {time.time() - T0:.0f} s')
    if 'status' in df: print(df[df.variant != 'free'].groupby('status').size().to_dict())
    pd.set_option('display.max_rows', 200)
    s = summary(df[df.fam != 'Vf'], 'selection set (non-Vf)'); b = summary(df, 'all masks'); c = summary(df[df.v_mean * 3.6 >= 54], '>= 54 km/h')

if __name__ == '__main__':
    main()
