"""Road-lock (OSM particle filter) on the protocol masks, with a learned speed from a saved LOFO run.

Usage: .venv/Scripts/python engine/iovopt/run_pf.py --pred gru_e25 [--name pf_a --n 1000 --sig_psi 12 --jobs 10]
For every mask: speed = the held-out model's outage speed (<pred>_pred.npz), heading = bias-fitted yaw integration (heading2),
graph = D:/offgrid_iov/osm/<seq>_<m0>.json. Variants: free DR (no map) and the road-locked track; if the lock is lost the
track continues as free DR from the lock-loss point.
"""
import sys, argparse, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from multiprocessing import Pool
from core import load, all_seqs, masks_of, integrate, row, put_speed, report

OSM = Path(r'D:\offgrid_iov\osm'); RUNS = Path(r'D:\offgrid_iov\runs')

def job(args):
    seq, pred, cfg = args
    import roadpf; from heading2 import fit_heading2
    d = load(seq); P = np.load(RUNS / f'{pred}_pred.npz'); rows = []
    for m in masks_of(d):
        key = f"{seq}|{m['m0']:.0f}"; fn = OSM / f"{seq}_{int(m['m0'])}.json"
        if key not in P.files: continue
        p = P[key]; v = put_speed(d, m, p)
        hh = fit_heading2(d, m, Wb=cfg.get('head_wb', 45.0), Ws=0); psi = d['psi'] if hh is None else hh[0]
        e_free, xf, yf = integrate(d, m, v, psi); rows.append(row(d, m, 'free', e_free))
        if not fn.exists(): rows.append(row(d, m, 'road', e_free, status='no_osm')); continue
        g = roadpf.load_graph(fn); ks = np.arange(m['k0'], m['ke'] + 1); dt = d['t'][ks] - d['t'][ks - 1]
        out, st = roadpf.run_pf(g, np.array(m['p0']), psi[ks], v[ks], dt, n=cfg['n'], sig_psi=cfg['sig_psi'], sig_scale=cfg['sig_scale'], lost_s=cfg['lost_s'],
                                lost_deg=cfg['lost_deg'], rng=np.random.default_rng(int(m['m0'])), keep_offset=cfg['offset'], walk=cfg['walk'], psi_grow=cfg['psi_grow'], out_mode=cfg['out_mode'], sig_d=cfg['sig_d'], sig_rel=cfg['sig_rel'], w_rel=cfg['w_rel'])
        if out is None: rows.append(row(d, m, 'road', e_free, status=st['status'])); continue
        if st['lost_at'] is not None:                                       # continue as free DR from the last locked point
            k = st['lost_at']; x, y = out[k]; ph = np.cumsum(np.cos(psi[ks]) * v[ks] * dt); qh = np.cumsum(np.sin(psi[ks]) * v[ks] * dt)
            out[k + 1:, 0] = x + ph[k + 1:] - ph[k]; out[k + 1:, 1] = y + qh[k + 1:] - qh[k]
        e = float(np.hypot(out[-1, 0] - d['gx'][m['ke']], out[-1, 1] - d['gy'][m['ke']])); rows.append(row(d, m, 'road', e, status=st['status'], scale=round(st.get('scale', 1.0), 3)))
    return rows

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pred', default='gru_e25'); ap.add_argument('--name', default='pf'); ap.add_argument('--n', type=int, default=1000)
    ap.add_argument('--sig_psi', type=float, default=12.0); ap.add_argument('--sig_scale', type=float, default=0.06); ap.add_argument('--lost_s', type=float, default=6.0)
    ap.add_argument('--lost_deg', type=float, default=35.0); ap.add_argument('--offset', type=int, default=1); ap.add_argument('--jobs', type=int, default=10); ap.add_argument('--seqs', default=''); ap.add_argument('--walk', type=float, default=0.0); ap.add_argument('--psi_grow', type=float, default=0.0); ap.add_argument('--out_mode', default='mean'); ap.add_argument('--sig_d', type=float, default=6.0); ap.add_argument('--head_wb', type=float, default=45.0); ap.add_argument('--sig_rel', type=float, default=0.0); ap.add_argument('--w_rel', type=int, default=30)
    a = ap.parse_args(); cfg = vars(a); cfg['offset'] = bool(a.offset); T0 = time.time()
    seqs = a.seqs.split(',') if a.seqs else all_seqs()
    with Pool(a.jobs) as pool: rows = sum(pool.map(job, [(s, a.pred, cfg) for s in seqs]), [])
    df = pd.DataFrame(rows); df.to_csv(RUNS / f'{a.name}.csv', index=False)
    r = df[df.variant == 'road']; print(r.status.value_counts().to_dict(), f'{time.time() - T0:.0f} s')
    report(df, a.name)

if __name__ == '__main__':
    main()
