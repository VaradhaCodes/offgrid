import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from core import load, all_seqs, masks_of, integrate, row, summary
from heading2 import fit_heading2
cfgs = {}
for Wb in (10, 15, 20, 30, 45):
    for Ws in (0, 300, 900, 3000):
        cfgs[f'b{Wb}_s{Ws}'] = dict(Wb=Wb, Ws=Ws)
for lat in (-0.2, 0.2, 0.4): cfgs[f'b20_s900_lat{lat}'] = dict(Wb=20, Ws=900, lat=lat)
cfgs['b20_s900_last'] = dict(Wb=20, Ws=900, th0_src='last')
rows = []; D = [load(s) for s in all_seqs()]
for d in D:
    for m in masks_of(d):
        rows.append(row(d, m, 'engine_psi', integrate(d, m, d['gv'], d['psi'])[0]))
        for n, c in cfgs.items():
            r = fit_heading2(d, m, **c); e = integrate(d, m, d['gv'], d['psi'] if r is None else r[0])[0]; rows.append(row(d, m, n, e))
df = pd.DataFrame(rows)
a = summary(df[df.fam != 'Vf'], 'oracle speed: selection set'); b = summary(df[df.v_mean * 3.6 >= 54], '>= 54 km/h')
