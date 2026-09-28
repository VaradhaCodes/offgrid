"""Leave-one-family-out run of the GRU outage-speed model on the step-10b protocol masks.

Usage: .venv/Scripts/python engine/iovopt/run_seq.py --name gru_a [--epochs 25 --h 128 --seeds 1 --w_dist 1 --folds all]
Writes D:/offgrid_iov/runs/<name>.csv (rows per mask x variant) and <name>_pred.npz (outage speeds per mask), prints the report.
"""
import sys, argparse, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd, torch
from core import load, all_seqs, masks_of, integrate, row, put_speed, report, FAMS
from heading2 import fit_heading2
import seqmodel as sm

RUNS = Path(r'D:\offgrid_iov\runs'); RUNS.mkdir(exist_ok=True, parents=True)
HEAD = dict(Wb=45, Ws=0)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True); ap.add_argument('--epochs', type=int, default=25); ap.add_argument('--h', type=int, default=128)
    ap.add_argument('--layers', type=int, default=2); ap.add_argument('--seeds', type=int, default=1); ap.add_argument('--w_dist', type=float, default=1.0); ap.add_argument('--lr', type=float, default=2e-3)
    ap.add_argument('--step', type=int, default=3); ap.add_argument('--folds', default='all'); ap.add_argument('--aug', type=float, default=0.0); ap.add_argument('--extra', default=''); ap.add_argument('--alt', type=int, default=0); ap.add_argument('--seed0', type=int, default=0); ap.add_argument('--bidir', type=int, default=0); ap.add_argument('--mirror', type=int, default=0); ap.add_argument('--memfrac', type=float, default=0.0)
    a = ap.parse_args(); dev = 'cuda'; T0 = time.time(); sm.USE_ALT = bool(a.alt); sm.BIDIR = bool(a.bidir)
    if a.memfrac > 0: torch.cuda.set_per_process_memory_fraction(a.memfrac)          # stay inside dedicated VRAM when jobs share the GPU
    D = [load(s) for s in all_seqs()]; extra = [load(s, extra=True) for s in all_seqs(extra=True)] if a.extra == 'all' else []
    bank = sm.Bank(D + extra, dev)
    folds = FAMS if a.folds == 'all' else a.folds.split(',')
    rows = []; preds = {}
    for fam in folds:
        tr = [d for d in D + extra if d['fam'] != fam]; te = [d for d in D if d['fam'] == fam]
        cuts = sum((bank.cuts_for(d, a.step) for d in tr), [])
        masks = [(d, m) for d in te for m in masks_of(d)]
        k0s = np.array([bank.off[d['seq']] + m['k0'] for d, m in masks])
        P = np.zeros((len(masks), sm.POST), np.float32)
        for sd in range(a.seeds):
            net = sm.train(bank, cuts, epochs=a.epochs, seed=a.seed0 + sd, h=a.h, layers=a.layers, w_dist=a.w_dist, lr=a.lr, aug_warp=a.aug, mirror=bool(a.mirror),
                           log=None); P += sm.predict(net, bank, k0s) / a.seeds
        for (d, m), p in zip(masks, P):
            v = put_speed(d, m, p)
            hh = fit_heading2(d, m, **HEAD); psi_h = d['psi'] if hh is None else hh[0]
            rows.append(row(d, m, 'gru+head', integrate(d, m, v, psi_h)[0])); rows.append(row(d, m, 'gru+engine_psi', integrate(d, m, v, d['psi'])[0]))
            rows.append(row(d, m, 'gru+true_psi', integrate(d, m, v, d['gh'])[0]))
            v0 = np.full(len(v), d['fv'][m['i_cut']]); rows.append(row(d, m, 'hold+head', integrate(d, m, v0, psi_h)[0]))
            rows.append(row(d, m, 'oracle_v+head', integrate(d, m, d['gv'], psi_h)[0]))
            preds[f"{d['seq']}|{m['m0']:.0f}"] = p
        dd = pd.DataFrame([r for r in rows if r['fam'] == fam]); g = dd[dd.variant == 'gru+head']
        print(f"fold {fam}: {len(cuts)} train cuts, {len(masks)} masks, gru+head median {g.drift_pct.median():.2f} %, hold+head {dd[dd.variant == 'hold+head'].drift_pct.median():.2f} % ({time.time() - T0:.0f} s)", flush=True)
    df = pd.DataFrame(rows); df.to_csv(RUNS / f'{a.name}.csv', index=False); np.savez(RUNS / f'{a.name}_pred.npz', **preds)
    json.dump(vars(a), open(RUNS / f'{a.name}.json', 'w'))
    if a.folds == 'all': report(df, a.name)
    else: from core import summary; summary(df, a.name)

if __name__ == '__main__':
    main()
