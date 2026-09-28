import sys, itertools; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from core import load, all_seqs, masks_of, integrate, along_cross, row, summary
from heading2 import fit_heading
cfgs = []
for W in (30, 60, 120, 200, 280):
    for src in ('bearing', 'course'):
        for fs in (False, True):
            cfgs.append(dict(W=W, src=src, fit_scale=fs))
rows = []; D = [load(s) for s in all_seqs()]
for d in D:
    for m in masks_of(d):
        rows.append(row(d, m, 'engine_psi', integrate(d, m, d['gv'], d['psi'])[0]))
        for c in cfgs:
            r = fit_heading(d, m, **c)
            if r is None: e = integrate(d, m, d['gv'], d['psi'])[0]
            else: e = integrate(d, m, d['gv'], r[0])[0]
            rows.append(row(d, m, f"W{c['W']}_{c['src']}_{'s' if c['fit_scale'] else 'b'}", e))
df = pd.DataFrame(rows)
a = summary(df[df.fam != 'Vf'], 'oracle speed, heading variants: selection set')
b = summary(df[df.v_mean * 3.6 >= 54], 'oracle speed, heading variants: >= 54 km/h')
