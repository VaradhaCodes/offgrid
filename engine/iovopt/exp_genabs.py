"""Step-10b gen_abs (GBR speed + filter with scale state) with the new heading substituted inside every mask: a like-for-like
comparison for the GRU. Folds run in parallel."""
import sys, os; from pathlib import Path; HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / 'speed_model'))
import numpy as np, pandas as pd
from multiprocessing import Pool
from core import load, all_seqs, masks_of, FAMS, report

def with_head(d):
    from heading2 import fit_heading2
    psi = d['psi'].copy()
    for m in masks_of(d):
        r = fit_heading2(d, m, Wb=45, Ws=0)
        if r is not None: sl = slice(m['k0'] - 1, m['ke'] + 1); psi[sl] = r[0][sl]
    e = dict(d); e['psi'] = psi; e['masks'] = [tuple(x) for x in d['masks']]; return e

def fold(fam):
    os.chdir(HERE.parent.parent); import iovnbd_cv as cv; cv.VARIANTS = ('plain_abs', 'gen_abs', 'gen_fuse')
    D = [load(s) for s in all_seqs()]
    for d in D: d['masks'] = [tuple(x) for x in d['masks']]
    M = cv.fit([d for d in D if d['fam'] != fam]); rows = []
    for d in [d for d in D if d['fam'] == fam]:
        r, _ = cv.run_drive(d, M); rows += [dict(x, variant=x['variant'] + '_old') for x in r]
        r, _ = cv.run_drive(with_head(d), M); rows += [dict(x, variant=x['variant'] + '+head') for x in r]
    return rows

if __name__ == '__main__':
    with Pool(7) as p: rows = sum(p.map(fold, FAMS), [])
    df = pd.DataFrame(rows); df.to_csv(r'D:\offgrid_iov\runs\genabs_head.csv', index=False); report(df, 'gen_abs old vs +head')
