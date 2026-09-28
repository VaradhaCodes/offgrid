"""Add the GNSS altitude (VBOX 'Height', metres) on the cached tick grid, for the grade feature (1 Hz GNSS input before the cut only)."""
import sys, os
from pathlib import Path; HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import numpy as np, pandas as pd
from core import CACHE, CACHE_EXTRA
SRC = {CACHE: Path('data/external/IO-VNBD/Synchronised V abd S datasets/Uncategorised IOVNB Dataset/V-Dataset'), CACHE_EXTRA: Path(r'D:\offgrid_iov\extraV\V-Dataset')}
os.chdir(HERE.parent.parent)
for C, R in SRC.items():
    for p in C.glob('*.npz'):
        z = dict(np.load(p)); s = str(z['seq']); V = pd.read_csv(R / f'V-{s}.csv'); V.columns = [c.strip() for c in V.columns]
        t = V.iloc[:, 1].values.astype(float); t = t - t[0]; ok = np.concatenate([[True], np.diff(t) > 0]); h = V['Height (km)'].values[ok].astype(float)
        assert len(h) == len(z['t']), (s, len(h), len(z['t']))
        z['alt'] = h; np.savez(p, **z)
    print(C, 'done')
