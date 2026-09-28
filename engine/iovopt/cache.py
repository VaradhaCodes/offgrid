"""Build the per-drive cache for the IO-VNBD optimisation track (step 10c).

Usage: .venv/Scripts/python engine/iovopt/cache.py [--jobs 28]
One npz per drive in D:/offgrid_iov/cache: the step-10b prep (alignment from other families only, 1 Hz GNSS, 60 s masks every
300 s, the engine heading filter fed by healthy fixes only) plus the VBOX truth heading. Same drives and masks as iovnbd_cv.py.
"""
import sys, argparse, time
from pathlib import Path
import numpy as np
from multiprocessing import Pool
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / 'speed_model'))
CACHE = Path(r'D:\offgrid_iov\cache')

def work(args):
    import os; os.chdir(HERE.parent.parent)
    from iovnbd_cv import prep
    seq, cal, mask, every = args; d = prep(seq, cal, mask, every)
    keep = {k: v for k, v in d.items() if isinstance(v, np.ndarray)}
    keep['masks'] = np.array(d['masks'], float).reshape(-1, 2); keep['fam'] = np.array(d['fam']); keep['seq'] = np.array(seq)
    keep['cal'] = np.array([cal['yaw_scale'], cal['ax_scale']])
    np.savez(CACHE / f'{seq}.npz', **keep); return seq, len(d['t']), len(d['masks'])

def main():
    import os; os.chdir(HERE.parent.parent)
    from iovnbd_cv import EXCLUDE, family
    from iovnbd import ROOT, load, calibrate
    ap = argparse.ArgumentParser(); ap.add_argument('--jobs', type=int, default=28); ap.add_argument('--mask', type=float, default=60.0); ap.add_argument('--every', type=float, default=300.0)
    a = ap.parse_args(); T0 = time.time()
    seqs = sorted(p.stem[2:] for p in (ROOT / 'V-Dataset').glob('V-*.csv') if p.stem[2:] not in EXCLUDE)
    with Pool(a.jobs) as pool: cals = dict(zip(seqs, pool.map(_cal, seqs)))
    jobs = []
    for s in seqs:
        others = [cals[o] for o in seqs if family(o) != family(s) and np.isfinite(cals[o]['yaw_corr'])]
        cal = dict(yaw_scale=float(np.median([c['yaw_scale'] for c in others])), ax_scale=float(np.median([c['ax_scale'] for c in others])))
        jobs.append((s, cal, a.mask, a.every))
    with Pool(a.jobs) as pool:
        for r in pool.imap_unordered(work, jobs): print(r, flush=True)
    print(f'{len(seqs)} drives cached in {time.time() - T0:.0f} s')

def _cal(s):
    import os; os.chdir(HERE.parent.parent)
    from iovnbd import load, calibrate
    return calibrate(load(s))

if __name__ == '__main__':
    main()
