"""Cache the IO-VNBD drives that are not in the synchronised V set (training only, never scored): St4/6/7 (driver C) and the
Vfb drives (driver E, Vf campaign: labelled family Vf so the Vf fold never trains on them). St1 = Y2 (duplicate files) is left out."""
import sys, os
from pathlib import Path; HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / 'speed_model'))
import numpy as np
os.chdir(HERE.parent.parent)
import iovnbd; iovnbd.ROOT = Path(r'D:\offgrid_iov\extraV')
import iovnbd_cv
OUT = Path(r'D:\offgrid_iov\cache_extra')
cal = dict(yaw_scale=float(np.median([np.load(p)['cal'][0] for p in Path(r'D:\offgrid_iov\cache').glob('*.npz')])), ax_scale=1.0)
for p in sorted((iovnbd.ROOT / 'V-Dataset').glob('V-*.csv')):
    s = p.stem[2:]; d = iovnbd_cv.prep(s, cal, 60.0, 300.0); fam = 'St' if s.startswith('St') else 'Vf'
    keep = {k: v for k, v in d.items() if isinstance(v, np.ndarray)}; keep['masks'] = np.array(d['masks'], float).reshape(-1, 2); keep['fam'] = np.array(fam); keep['seq'] = np.array(s); keep['cal'] = np.array([cal['yaw_scale'], 1.0])
    np.savez(OUT / f'{s}.npz', **keep); print(s, fam, len(d['t']) / 36000, 'h', flush=True)
