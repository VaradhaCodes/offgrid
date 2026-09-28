"""Error budget: which part of the drift is heading and which is speed (oracle swaps), on the exact step-10b masks."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from core import load, all_seqs, masks_of, integrate, along_cross, row, report

rows = []
for s in all_seqs():
    d = load(s); psi_e = d['psi']; psi_t = d['gh']; gv = d['gv']
    for m in masks_of(d):
        v0 = d['fv'][m['i_cut']]; vh = np.full(len(gv), v0)
        for name, v, psi in (('oracle_v+engine_psi', gv, psi_e), ('oracle_v+true_psi', gv, psi_t), ('hold_v+true_psi', vh, psi_t), ('hold_v+engine_psi', vh, psi_e)):
            e, x, y = integrate(d, m, v, psi); al, cr = along_cross(d, m, x, y)
            rows.append(row(d, m, name, e, along=round(al, 1), cross=round(cr, 1)))
df = pd.DataFrame(rows); report(df, 'decompose')
old = pd.read_csv('data/qa/iovnbd_cv_m60.csv'); print('\nmask count check: old', old[old.variant == 'oracle'].shape[0], 'new', df[df.variant == 'hold_v+engine_psi'].shape[0])
o = old[old.variant.isin(['oracle', 'hold'])].pivot_table(index=['seq', 't0'], columns='variant', values='drift_pct'); n = df.pivot_table(index=['seq', 't0'], columns='variant', values='drift_pct')
j = o.join(n, how='inner'); print('match oracle', np.corrcoef(j['oracle'], j['oracle_v+engine_psi'])[0, 1].round(4), 'med', j['oracle'].median(), j['oracle_v+engine_psi'].median(), '| hold', j['hold'].median(), j['hold_v+engine_psi'].median())
hi = df[df.v_mean * 3.6 >= 54]
for v in ('oracle_v+engine_psi', 'hold_v+true_psi'):
    x = hi[hi.variant == v]; print(v, '>=54 median |along| m', x.along.abs().median(), '|cross| m', x.cross.abs().median())
