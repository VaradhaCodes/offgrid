"""Shared protocol for the IO-VNBD optimisation track (step 10c): cached drives, the exact step-10b outage masks, a vectorised
outage integrator and the summaries.

Protocol (unchanged from engine/iovnbd_cv.py): 60 s GNSS masks every 300 s from t = 300 s, GNSS input = VBOX subsampled to 1 Hz,
inertial input = CAN yaw rate + indicated longitudinal/lateral acceleration (10 Hz), never wheel/indicated speed, rpm or gear;
a mask counts if it has >= 10 ticks and >= 50 m of true travel; drift = endpoint error / true distance in the mask; families are
held out whole (leave-one-family-out), Vf is never used for selection.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path(r'D:\offgrid_iov\cache')
FAMS = ['M', 'S', 'Vf', 'Vta', 'Vtb', 'Vw', 'Y']

CACHE_EXTRA = Path(r'D:\offgrid_iov\cache_extra')

def load(seq, extra=False):
    z = np.load((CACHE_EXTRA if extra else CACHE) / f'{seq}.npz', allow_pickle=False); d = {k: z[k] for k in z.files}
    d['fam'] = str(d['fam']); d['seq'] = str(d['seq']); return d

def all_seqs(extra=False):
    return sorted(p.stem for p in (CACHE_EXTRA if extra else CACHE).glob('*.npz'))

def masks_of(d):
    """Per mask: (m0, m1, k0 = first outage tick, ke = last tick in [m0, m1), p0 = position the engine holds at k0-1, dist)."""
    t, tf, wh = d['t'], d['tf'], d['withheld']; out = []
    last_fix = np.searchsorted(tf, t, side='right') - 1; o = (last_fix >= 0) & wh[np.maximum(last_fix, 0)]
    gxi, gyi = np.interp(t, tf, d['fx']), np.interp(t, tf, d['fy'])
    for m0, m1 in d['masks']:
        w = np.where((t >= m0) & (t < m1))[0]
        if len(w) < 10: continue
        dist = float(np.sum(np.hypot(np.diff(d['gx'][w]), np.diff(d['gy'][w]))))
        if dist < 50: continue
        ks = np.where(o & (t >= m0 - 1.0) & (t < m1 + 1.0))[0]; k0 = int(ks[0]); ke = int(w[-1])
        out.append(dict(m0=float(m0), m1=float(m1), k0=k0, ke=ke, p0=(float(gxi[k0 - 1]), float(gyi[k0 - 1])), dist=dist,
                        v_mean=float(d['gv'][w].mean()), i_cut=int(np.searchsorted(tf, m0) - 1)))
    return out

def put_speed(d, m, p):
    """Speed array with the outage prediction p inserted from k0; ticks past the prediction (a 601-tick mask) hold its last value."""
    v = d['gv'].copy(); n = min(len(p), len(v) - m['k0']); v[m['k0']:m['k0'] + n] = p[:n]
    if m['ke'] >= m['k0'] + n: v[m['k0'] + n:m['ke'] + 1] = p[n - 1]
    return v

def integrate(d, m, v, psi):
    """Dead-reckon from the held position with speed v[k] and heading psi[k] over ticks k0..ke; returns (end error m, path x, y)."""
    k0, ke = m['k0'], m['ke']; t = d['t']; ks = np.arange(k0, ke + 1); dt = t[ks] - t[ks - 1]
    x = m['p0'][0] + np.cumsum(np.cos(psi[ks]) * v[ks] * dt); y = m['p0'][1] + np.cumsum(np.sin(psi[ks]) * v[ks] * dt)
    return float(np.hypot(x[-1] - d['gx'][ke], y[-1] - d['gy'][ke])), x, y

def along_cross(d, m, x, y):
    """End error split into along-track and cross-track components w.r.t. the true heading at the end."""
    ke = m['ke']; ex, ey = x[-1] - d['gx'][ke], y[-1] - d['gy'][ke]; h = d['gh'][ke]
    return float(ex * np.cos(h) + ey * np.sin(h)), float(-ex * np.sin(h) + ey * np.cos(h))

def row(d, m, variant, err, **kw):
    return dict(seq=d['seq'], fam=d['fam'], variant=variant, t0=m['m0'], dist_m=round(m['dist'], 1), end_m=round(err, 1),
                drift_pct=round(100 * err / m['dist'], 2), v_mean=round(m['v_mean'], 2), **kw)

def summary(df, label=None, sort=True):
    g = df.groupby('variant')
    s = pd.DataFrame(dict(masks=g.size(), med=g.drift_pct.median(), p90=g.drift_pct.quantile(0.9),
                          u10=g.drift_pct.apply(lambda x: (x < 10).mean() * 100),
                          pooled=g.apply(lambda x: 100 * x.end_m.sum() / x.dist_m.sum(), include_groups=False)))
    s = s.round(2)
    if sort: s = s.sort_values('med')
    if label: print(f'\n--- {label}'); print(s.to_string())
    return s

def report(df, title=''):
    """The three views used in the deck: selection set (6 non-Vf families), all 307 masks, the >= 54 km/h subset."""
    a = summary(df[df.fam != 'Vf'], f'{title} selection set (non-Vf)'); b = summary(df, f'{title} all masks')
    c = summary(df[df.v_mean * 3.6 >= 54], f'{title} >= 54 km/h'); return a, b, c
