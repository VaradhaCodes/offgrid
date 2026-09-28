"""IO-VNBD, every drive (step 10b): leave-one-family-out evaluation of the engine on the external 10 Hz vehicle IMU, and the
learned speed-change model.

Usage: .venv/Scripts/python engine/iovnbd_cv.py [--mask 60 --every 300] [--tag m60]

Why a second script: engine/iovnbd.py (step 10) trained one GBR on 46 min of drives and tested on two; its motorway speed model
read 5.6 m/s slow at 24.5 m/s because the training drives were slow. This track uses all 70 moving drives (29.9 h, 1341 km) and
never tests a drive with a model that saw its family (dataset categories: M = driver B, S = driver A, Y = driver D; Vf, Vta, Vtb,
Vw = driver E on separate campaigns). Inputs are the three IMU channels only (CAN yaw rate, longitudinal and lateral
acceleration): the wheel speeds, indicated speed, engine rpm and gear are an odometer by another name and the problem statement
rules out a speedometer feed, so they are never read.

Speed sources compared inside the same heading and filter code as step 10:
  abs   GBR-style absolute speed from 5.1 s IMU windows (HistGradientBoosting, all training families);
  delta the learned speed change: at the cut the last healthy GNSS speed v0 is known; the model predicts v(t) - v0 from the time
        since the cut, the bias-corrected integrated longitudinal acceleration, the since-cut turn/lateral statistics and the
        same window features. Trained on synthetic cuts every 30 s of every training drive, horizon 130 s.
Variants: hold (v0 held), ins (v0 + integrated a_long, bias from healthy 1 Hz GNSS), plain_abs, gen_abs (filter + abs model +
scale state: the step-10 best), delta (v0 + model change, no filter), gen_delta (filter, model = v0 + change, sigma by horizon),
gen_fuse (filter with both: the abs model through the scale state and the delta model as a second speed measurement on v),
oracle (true VBOX speed with the engine heading: the heading-only floor, reported, never selectable).
Tried and dropped: an online a_long scale/offset fit from the last 180 s of healthy GNSS as extra delta features (selection-set
median 10.22 -> 10.74 %, worse). Selection rule, fixed before any result: the variant with the lowest median drift pooled over the six non-Vf families; Vf
(Vfa01, Vfa02, the two drives reported in step 10) is only read after that choice.
Outputs: data/qa/iovnbd_cv_<tag>.csv (one row per drive x mask x variant) and the printed summaries.
"""
import sys, math, re, argparse, time
from pathlib import Path
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent / 'speed_model'))
from iovnbd import ROOT, load, calibrate, still_ext
from heading import HeadingFilter
from filter import Filter
from sklearn.ensemble import HistGradientBoostingRegressor as HGB

EXCLUDE = {'Vw1', 'Vw15'}                 # parked for the whole file (v_max 0.1 / 0.2 m/s)
WIN = 51; CUT_EVERY = 30.0; HORIZON = 130.0; B_ALPHA = 0.05; VARIANTS = ('hold', 'ins', 'plain_abs', 'gen_abs', 'delta', 'gen_delta', 'gen_fuse', 'oracle')

def family(seq): return re.match(r'[A-Za-z]+', seq).group(0).capitalize().replace('Vfa', 'Vf')

def win_feats(yaw, ax, ay):
    """The step-10 window features, vectorised, causal (window ends at the tick); NaN for the first WIN-1 ticks."""
    n = len(yaw); F = np.full((n, 16), np.nan, np.float32)
    if n < WIN: return F
    Y, A1, A2 = swv(yaw, WIN), swv(ax, WIN), swv(ay, WIN)
    turn = np.abs(Y) > 0.05; ratio = np.where(turn, np.abs(A2) / np.maximum(np.abs(Y), 1e-6), np.nan)
    with np.errstate(all='ignore'): med = np.nanmedian(ratio, axis=1)
    med = np.where(turn.sum(1) > 5, med, 0.0)
    F[WIN - 1:] = np.stack([A1.mean(1), A1.std(1), A1.min(1), A1.max(1), A2.mean(1), A2.std(1), np.abs(A2).max(1), Y.mean(1), Y.std(1), np.abs(Y).max(1),
                            A1.sum(1) * 0.1, A1[:, -20:].sum(1) * 0.1, med, np.log1p(np.abs(A2).mean(1) / (np.abs(Y).mean(1) + 1e-3)),
                            np.sqrt(np.mean(np.diff(A1, axis=1) ** 2, 1)), np.sqrt(np.mean(np.diff(A2, axis=1) ** 2, 1))], 1)
    return F

def bias_track(d, ax, healthy_fix):
    """a_long bias per fix from 1 Hz GNSS only: EMA of mean(a_long between fixes) - dv/dt(fixes), updated on healthy pairs."""
    tf, fv, t = d['tf'], d['fv'], d['t']; b = np.zeros(len(tf)); cur = 0.0; ki = np.searchsorted(t, tf, side='right')
    for i in range(1, len(tf)):
        dt = tf[i] - tf[i - 1]
        if healthy_fix[i] and healthy_fix[i - 1] and 0.5 < dt < 1.5 and ki[i] > ki[i - 1]:
            cur = (1 - B_ALPHA) * cur + B_ALPHA * (float(ax[ki[i - 1]:ki[i]].mean()) - (fv[i] - fv[i - 1]) / dt)
        b[i] = cur
    return b

def delta_feats(d, ax, ay, yaw, Fw, i0, k0, k1, b0):
    """Features for ticks k0..k1-1 after a cut at healthy fix i0 (time t0, speed v0, a_long bias b0 frozen at the cut)."""
    t = d['t']; t0 = d['tf'][i0]; v0 = d['fv'][i0]; ks = np.arange(k0, k1); tau = t[ks] - t0
    Iax = np.cumsum((ax[k0:k1] - b0) * 0.1); n = np.arange(1, len(ks) + 1)
    m_ay = np.cumsum(np.abs(ay[k0:k1])) / n; m_yaw = np.cumsum(np.abs(yaw[k0:k1])) / n; m_ax = np.cumsum(ax[k0:k1]) / n
    X = np.column_stack([tau, np.full(len(ks), v0), Iax, np.full(len(ks), b0), b0 * tau, v0 + Iax, m_ay, m_yaw, m_ax, Fw[ks]]).astype(np.float32)
    return ks, X

def prep(seq, cal, mask, every):
    d = load(seq); t, tf = d['t'], d['tf']
    yaw = d['yaw'] * cal['yaw_scale']; ax = d['ax'] * np.sign(cal['ax_scale']); ay = d['ay']
    masks = [(t0, t0 + mask) for t0 in np.arange(every, t[-1] - mask, every)]
    wh = np.array([any(m0 <= x < m1 for m0, m1 in masks) for x in tf])
    d.update(yaw_b=yaw, ax_b=ax, ay_b=ay, masks=masks, withheld=wh, Fw=win_feats(yaw, ax, ay), fam=family(seq))
    d['b_all'] = bias_track(d, ax, np.ones(len(tf), bool)); d['b_test'] = bias_track(d, ax, ~wh)
    hf = HeadingFilter([0.0, 0.0, 0.0], 9.80665, mode3d=False, refine=True, refine_bias=True); psi = np.zeros(len(t)); fi = 0
    for k in range(len(t)):                                            # heading is independent of the speed source: run once
        while fi < len(tf) and tf[fi] <= t[k]:
            if not wh[fi]: hf.gnss_bearing(tf[fi], d['fcourse'][fi], d['fv'][fi], hf.w_lp[2] if hf.w_lp is not None else 0.0)
            fi += 1
        hf.step(t[k], [0.0, 0.0, 9.80665], [0.0, 0.0, yaw[k]]); psi[k] = hf.psi
    d['psi'] = psi; return d

def train_sets(drives):
    Xa, ya, Xd, yd = [], [], [], []
    for d in drives:
        t, tf = d['t'], d['tf']; ok = ~np.isnan(d['Fw'][:, 0]); ka = np.where(ok)[0][::3]; Xa.append(d['Fw'][ka]); ya.append(d['gv'][ka])
        for i0 in range(0, len(tf), int(CUT_EVERY)):
            k0 = int(np.searchsorted(t, tf[i0], side='right')); k1 = int(np.searchsorted(t, tf[i0] + HORIZON))
            if k1 - k0 < 20: continue
            ks, X = delta_feats(d, d['ax_b'], d['ay_b'], d['yaw_b'], d['Fw'], i0, k0, k1, d['b_all'][i0])
            sel = slice(0, None, 5); Xd.append(X[sel]); yd.append(d['gv'][ks][sel] - d['fv'][i0])
    return np.vstack(Xa), np.concatenate(ya), np.vstack(Xd), np.concatenate(yd)

def fit(drives):
    Xa, ya, Xd, yd = train_sets(drives)
    ma = HGB(max_iter=300, learning_rate=0.1, max_leaf_nodes=31, l2_regularization=1.0, random_state=0).fit(Xa, ya)
    md = HGB(max_iter=300, learning_rate=0.1, max_leaf_nodes=31, l2_regularization=1.0, random_state=0).fit(Xd, yd)
    sig_a = float(np.std(ya - ma.predict(Xa))) * 1.5
    rd = yd - md.predict(Xd); edges = np.arange(0, HORIZON + 10, 10.0); tb = np.digitize(Xd[:, 0], edges)
    sig_d = np.array([max(0.3, float(np.std(rd[tb == j])) if (tb == j).sum() > 50 else 0.3) for j in range(len(edges) + 1)])
    return dict(ma=ma, md=md, sig_a=sig_a, sig_d=sig_d, edges=edges, n_abs=len(ya), n_delta=len(yd))

def run_drive(d, M):
    t, tf = d['t'], d['tf']; wh = d['withheld']; n = len(t)
    ok = ~np.isnan(d['Fw'][:, 0]); raw_a = np.zeros(n); raw_a[ok] = np.clip(M['ma'].predict(d['Fw'][ok]), 0, None)
    still = np.zeros(n, bool); ks_all = np.arange(WIN - 1, n); still[ks_all] = still_ext(d, {'yaw_scale': 1.0}, ks_all); raw_a[still] = 0.0
    # outage bookkeeping per tick: index of the last arrived fix and of the last healthy fix
    last_fix = np.searchsorted(tf, t, side='right') - 1; hidx = np.where(~wh)[0]
    last_h = hidx[np.clip(np.searchsorted(hidx, np.maximum(last_fix, 0), side='right') - 1, 0, None)]
    out = (last_fix >= 0) & wh[np.maximum(last_fix, 0)]
    v0 = np.where(out, d['fv'][last_h], np.nan); v_delta = np.full(n, np.nan); s_delta = np.full(n, np.nan); v_ins = np.full(n, np.nan)
    for i0 in np.unique(last_h[out]):
        kk = np.where(out & (last_h == i0))[0]; k1 = kk[-1] + 1; b0 = d['b_test'][i0]
        k0 = int(np.searchsorted(t, tf[i0], side='right'))                 # integrate from the cut itself, as in training
        ks, X = delta_feats(d, d['ax_b'], d['ay_b'], d['yaw_b'], d['Fw'], i0, k0, k1, b0); keep = out[ks]; ks, X = ks[keep], X[keep]
        v_delta[ks] = np.clip(d['fv'][i0] + M['md'].predict(X), 0, None); s_delta[ks] = M['sig_d'][np.digitize(X[:, 0], M['edges'])]
        v_ins[ks] = np.clip(X[:, 5], 0, None)
    v_delta[still & out] = 0.0; v_ins[still & out] = 0.0
    tracks = {}
    for var in VARIANTS:
        xs = np.zeros((n, 2))
        if var.startswith('gen'):
            f = Filter('general', k_est=(var in ('gen_abs', 'gen_fuse')), zupt=True, x0=(float(d['gx'][0]), float(d['gy'][0]))); fi = 0; pend = []; H = np.zeros(4); H[2] = 1.0
            for k in range(n):
                while fi < len(tf) and tf[fi] <= t[k]: pend.append(fi); fi += 1
                f.predict(t[k], d['psi'][k])
                if var == 'gen_delta' and out[k]: f.update_model(float(v_delta[k]), float(s_delta[k]), bool(still[k]))
                else: f.update_model(float(raw_a[k]), M['sig_a'], bool(still[k]))
                if var == 'gen_fuse' and out[k] and not still[k]:                   # second, independent speed measurement: v itself (no scale)
                    f._update(float(v_delta[k]) - f.x[2], H, max(float(s_delta[k]), 0.15) ** 2); f.x[2] = max(0.0, f.x[2])
                for i in pend:
                    if wh[i]: f.gnss_lost()
                    else: f.update_gnss(tf[i], d['fx'][i], d['fy'][i], d['fv'][i], 3.0)
                pend = []; xs[k] = f.x[:2]
        else:
            vv = {'hold': v0, 'ins': v_ins, 'plain_abs': raw_a, 'delta': v_delta, 'oracle': d['gv']}[var]      # oracle = true speed: the heading-only floor
            px, py = float(d['gx'][0]), float(d['gy'][0]); c, s = np.cos(d['psi']), np.sin(d['psi'])
            gxi, gyi = np.interp(t, tf, d['fx']), np.interp(t, tf, d['fy'])
            for k in range(n):
                if not out[k]: px, py = gxi[k], gyi[k]
                else: dt = t[k] - t[k - 1]; v = 0.0 if still[k] else float(vv[k]); px += c[k] * v * dt; py += s[k] * v * dt
                xs[k] = (px, py)
        tracks[var] = xs
    rows = []
    for var, xs in tracks.items():
        e = np.hypot(xs[:, 0] - d['gx'], xs[:, 1] - d['gy'])
        for (m0, m1) in d['masks']:
            w = (t >= m0) & (t < m1)
            if w.sum() < 10: continue
            dist = float(np.sum(np.hypot(np.diff(d['gx'][w]), np.diff(d['gy'][w]))))
            if dist < 50: continue
            rows.append(dict(seq=d['seq'], fam=d['fam'], variant=var, t0=m0, dist_m=round(dist, 1), end_m=round(float(e[w][-1]), 1), drift_pct=round(100 * float(e[w][-1]) / dist, 2),
                             max_m=round(float(e[w].max()), 1), v_mean=round(float(d['gv'][w].mean()), 2)))
    return rows, tracks

def summary(df, label):
    g = df.groupby('variant'); s = pd.DataFrame(dict(masks=g.size(), km_median=g.dist_m.median() / 1000, drift_median=g.drift_pct.median(), drift_p90=g.drift_pct.quantile(0.9),
                                                    under10=g.drift_pct.apply(lambda x: (x < 10).mean() * 100), pooled=g.apply(lambda x: 100 * x.end_m.sum() / x.dist_m.sum(), include_groups=False)))
    print(f"\n--- {label}"); print(s.round(2).sort_values('drift_median').to_string()); return s

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--mask', type=float, default=60.0); ap.add_argument('--every', type=float, default=300.0); ap.add_argument('--tag', default=None)
    a = ap.parse_args(); tag = a.tag or f"m{int(a.mask)}"; T0 = time.time()
    seqs = sorted(p.stem[2:] for p in (ROOT / 'V-Dataset').glob('V-*.csv') if p.stem[2:] not in EXCLUDE)
    cals = {s: calibrate(load(s)) for s in seqs}
    drives = []
    for s in seqs:
        others = [cals[o] for o in seqs if family(o) != family(s) and np.isfinite(cals[o]['yaw_corr'])]
        cal = dict(yaw_scale=float(np.median([c['yaw_scale'] for c in others])), ax_scale=float(np.median([c['ax_scale'] for c in others])))   # alignment from other families only
        drives.append(prep(s, cal, a.mask, a.every))
    fams = sorted({d['fam'] for d in drives}); print(f"{len(drives)} drives, families {fams}, {sum(d['t'][-1] for d in drives) / 3600:.1f} h, prep {time.time() - T0:.0f} s")
    rows = []
    for fam in fams:
        tr = [d for d in drives if d['fam'] != fam]; te = [d for d in drives if d['fam'] == fam]; M = fit(tr)
        n_before = len(rows)
        for d in te: r, _ = run_drive(d, M); rows += r
        dd = pd.DataFrame(rows[n_before:])
        print(f"fold {fam}: train {sum(x['t'][-1] for x in tr) / 3600:.1f} h ({M['n_abs']} abs / {M['n_delta']} delta samples), test {len(te)} drives, {dd.t0.nunique() if len(dd) else 0} masks, {time.time() - T0:.0f} s")
    df = pd.DataFrame(rows); Path('data/qa').mkdir(exist_ok=True); df.to_csv(f'data/qa/iovnbd_cv_{tag}.csv', index=False)
    s6 = summary(df[df.fam != 'Vf'], f'six non-Vf families pooled ({a.mask:.0f} s masks) -- selection set')
    best = s6.drop(index='oracle', errors='ignore').drift_median.idxmin(); print(f"\nselected by the pre-set rule: {best}")
    for fam in fams: summary(df[df.fam == fam], f'family {fam}')
    for seq in ('Vfa01', 'Vfa02'): summary(df[df.seq == seq], f'{seq} (held out, family Vf)')
    summary(df, 'all 70 drives, every drive held out by family')

if __name__ == '__main__':
    main()
