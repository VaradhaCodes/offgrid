"""IO-VNBD track (step 10): the engine on an EXTERNAL 10 Hz vehicle IMU (CAN yaw rate + longitudinal/lateral acceleration)
with the VBOX GNSS masked. The phone file of the same drive is unusable for this purpose (measured: its GPS updates every
9 s and its 10 Hz gyro z correlates at -0.14 with the vehicle yaw rate), so the V-file is the inertial source.

Usage: .venv/bin/python engine/iovnbd.py --train Vfa01 --test Vfa02 [--mask 120 --every 300 --gnss_hz 1]
Inputs (V-<seq>.csv, 10 Hz): VBOX lat/lon/velocity/heading (truth, and the GNSS input subsampled to --gnss_hz), CAN yaw rate,
indicated longitudinal/lateral acceleration, wheel speeds (reference only). Steps:
  2 alignment: sign and scale of the yaw rate against the GNSS course rate, sign of the longitudinal acceleration against the
    GNSS speed derivative, both from the training sequence (a vehicle IMU has no gravity levelling to do);
  3 heading: the step-3 filter (yaw-rate integration + [psi, bias] KF fed by the GNSS course, latency-compensated);
  4 speed: GBR on 5.12 s windows of (a_long, a_lat, yaw rate) plus the window's integrated a_long and a_lat/yaw-rate cue,
    trained on the other sequence, and the classical alternative 'INS speed' = speed at the cut + integral of a_long with the
    bias estimated while GNSS is healthy; stop rule = |yaw| and |a| quiet;
  5/6 filter: general mode with and without the scale state, GNSS masked --mask s every --every s; plain integration baseline.
Outputs: data/qa/iovnbd_<test>.csv, data/qa/iovnbd_<test>.png.
"""
import sys, math, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent / 'speed_model'))
from session import local_xy
from heading import HeadingFilter, wrap
from filter import Filter

ROOT = Path('data/external/IO-VNBD/Synchronised V abd S datasets/Uncategorised IOVNB Dataset')

def load(seq, gnss_hz=1.0):
    V = pd.read_csv(ROOT / 'V-Dataset' / f'V-{seq}.csv'); V.columns = [c.strip() for c in V.columns]
    t = V.iloc[:, 1].values.astype(float); t = t - t[0]; ok = np.concatenate([[True], np.diff(t) > 0]); V = V[ok]; t = t[ok]
    lat = V.iloc[:, 2].values; lon = V.iloc[:, 3].values; v = V.iloc[:, 4].values / 3.6; head = np.pi / 2 - np.radians(V.iloc[:, 5].values)
    yaw = np.radians(V.iloc[:, 14].values); ax = V.iloc[:, 16].values * 9.80665; ay = V.iloc[:, 17].values * 9.80665
    lat0, lon0 = float(lat[0]), float(lon[0]); gx, gy = local_xy(lat, lon, lat0, lon0); gx = np.asarray(gx); gy = np.asarray(gy)
    step = max(1, int(round(10.0 / gnss_hz))); fi = np.arange(0, len(t), step)
    fx, fy, tf, fv = gx[fi], gy[fi], t[fi], v[fi]
    dtf = np.diff(tf, prepend=np.nan); dx = np.diff(fx, prepend=np.nan); dy = np.diff(fy, prepend=np.nan); okc = (dtf > 0.05) & (np.hypot(dx, dy) / np.where(dtf > 0, dtf, 1) > 2.0)
    course = np.where(okc, np.arctan2(dy, dx), np.nan)
    return dict(seq=seq, t=t, yaw=yaw, ax=ax, ay=ay, gx=gx, gy=gy, gv=v, gh=np.unwrap(head), tf=tf, fx=fx, fy=fy, fv=fv, fcourse=course, facc=np.full(len(fi), 3.0), lat0=lat0, lon0=lon0)

def calibrate(d):
    """Alignment for an external IMU: yaw-rate sign/scale vs the GNSS course rate; a_long sign vs dv/dt (training sequence only)."""
    t = d['t']; n = 20; lp = lambda x: np.convolve(x, np.ones(n) / n, mode='same')
    hr = lp(np.gradient(d['gh'], t)); yw = lp(d['yaw']); m = (d['gv'] > 3.0) & (np.abs(hr) < 0.8)
    s_yaw = float(np.sum(yw[m] * hr[m]) / max(np.sum(yw[m] ** 2), 1e-9)); c_yaw = float(np.corrcoef(yw[m], hr[m])[0, 1])
    dv = lp(np.gradient(d['gv'], t)); axl = lp(d['ax']); s_ax = float(np.sum(axl[m] * dv[m]) / max(np.sum(axl[m] ** 2), 1e-9)); c_ax = float(np.corrcoef(axl[m], dv[m])[0, 1])
    return dict(yaw_scale=s_yaw, yaw_corr=c_yaw, ax_scale=s_ax, ax_corr=c_ax)

def feats(d, cal, win=51, stride=1):
    yaw = d['yaw'] * cal['yaw_scale']; ax = d['ax'] * np.sign(cal['ax_scale']); ay = d['ay']; t = d['t']; F = []; ks = []
    for k in range(win - 1, len(t), stride):
        w = slice(k - win + 1, k + 1); yw = yaw[w]; a1 = ax[w]; a2 = ay[w]
        ratio = np.abs(a2[np.abs(yw) > 0.05]) / np.abs(yw[np.abs(yw) > 0.05]) if (np.abs(yw) > 0.05).sum() > 5 else np.array([0.0])
        F.append([a1.mean(), a1.std(), a1.min(), a1.max(), a2.mean(), a2.std(), np.abs(a2).max(), yw.mean(), yw.std(), np.abs(yw).max(), np.sum(a1) * 0.1, np.sum(a1[-20:]) * 0.1,
                  np.median(ratio), np.log1p(np.abs(a2).mean() / (np.abs(yw).mean() + 1e-3)), np.sqrt(np.mean(np.diff(a1) ** 2)), np.sqrt(np.mean(np.diff(a2) ** 2))]); ks.append(k)
    return np.array(F, np.float32), np.array(ks)

def still_ext(d, cal, ks, win=30):
    """CAN-IMU stop rule: 3 s with |yaw| < 0.003 rad/s and |a_long|, |a_lat| < 0.05 m/s^2 (a quiet cruise on a motorway can pass a looser rule)."""
    yaw = d['yaw']; ax = d['ax']; ay = d['ay']
    return np.array([(np.abs(yaw[k - win + 1:k + 1]).max() < 0.003) and (np.abs(ax[k - win + 1:k + 1]).max() < 0.05) and (np.abs(ay[k - win + 1:k + 1]).max() < 0.05) for k in ks])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--train', default='Vfa01'); ap.add_argument('--test', default='Vfa02'); ap.add_argument('--mask', type=float, default=120.0); ap.add_argument('--every', type=float, default=300.0); ap.add_argument('--gnss_hz', type=float, default=1.0)
    a = ap.parse_args(); from sklearn.ensemble import GradientBoostingRegressor
    trains = [x for x in a.train.split(',') if x != a.test]; dtrs = [load(x, a.gnss_hz) for x in trains]; dte = load(a.test, a.gnss_hz); cal = calibrate(dtrs[0]); cal_te = calibrate(dte)
    print(f"train {trains} ({sum(x['t'][-1] for x in dtrs):.0f} s) | test {a.test}: {dte['t'][-1]:.0f} s, GNSS input {a.gnss_hz:.0f} Hz")
    print(f"alignment (from {trains[0]}): yaw-rate scale {cal['yaw_scale']:+.3f} (corr {cal['yaw_corr']:.3f}), a_long scale {cal['ax_scale']:+.3f} (corr {cal['ax_corr']:.3f}); the same on {a.test} (check only): yaw {cal_te['yaw_scale']:+.3f}/{cal_te['yaw_corr']:.3f}, a_long {cal_te['ax_scale']:+.3f}/{cal_te['ax_corr']:.3f}")
    FF = [feats(x, cal) for x in dtrs]; Ftr = np.vstack([f_ for f_, _ in FF]); ytr = np.concatenate([x['gv'][k_] for x, (_, k_) in zip(dtrs, FF)]); Fte, kte = feats(dte, cal); yte = dte['gv'][kte]
    m = GradientBoostingRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, random_state=0).fit(Ftr, ytr)
    raw = np.clip(m.predict(Fte), 0, None); sig = np.full(len(raw), float(np.std(ytr - m.predict(Ftr))) * 1.5); still = still_ext(dte, cal, kte); raw[still] = 0.0
    mv = yte > 1.0; print(f"speed model (GBR on external-IMU windows, train {a.train} -> test {a.test}): MAE moving {np.mean(np.abs(raw - yte)[mv]):.2f} m/s (mean speed {yte[mv].mean():.1f}), bias {np.mean((raw - yte)[mv]):+.2f}, false stops {int((still & mv).sum())}, sigma {sig[0]:.2f}")
    t = dte['t']; tf = dte['tf']; masks = [(t0, t0 + a.mask) for t0 in np.arange(a.every, t[-1] - a.mask, a.every)]
    yaw_b = dte['yaw'] * cal['yaw_scale']; ax_b = dte['ax'] * np.sign(cal['ax_scale']); rows = []; tracks = {}; dv_true = np.gradient(dte['gv'], t)
    for variant in ('plain', 'ins', 'gen_k1', 'gen'):
        hf = HeadingFilter([0.0, 0.0, 0.0], 9.80665, mode3d=False, refine=True, refine_bias=True)
        f = Filter('general', k_est=(variant == 'gen'), zupt=True, x0=(float(dte['gx'][0]), float(dte['gy'][0]))); fi = 0; ip = 0; xs = np.zeros((len(t), 4)); withheld = False
        px, py = float(dte['gx'][0]), float(dte['gy'][0]); psi_hist = np.zeros(len(t)); v_ins = 0.0; b_ax = 0.0; n_b = 0
        for k in range(len(t)):
            while fi < len(tf) and tf[fi] <= t[k]:
                withheld = any(m0 <= tf[fi] < m1 for m0, m1 in masks)
                if not withheld: hf.gnss_bearing(tf[fi], dte['fcourse'][fi], dte['fv'][fi], hf.w_lp[2] if hf.w_lp is not None else 0.0)
                f.pending = getattr(f, 'pending', []) + [(tf[fi], fi, withheld)]; fi += 1
            hf.step(t[k], [0.0, 0.0, 9.80665], [0.0, 0.0, yaw_b[k]]); psi_hist[k] = hf.psi; f.predict(t[k], hf.psi)
            while ip < len(kte) and kte[ip] <= k: ip += 1
            j = max(0, ip - 1); dt = t[k] - t[k - 1] if k else 0.0
            if variant in ('plain', 'ins'):
                if not withheld:
                    v_ins = float(np.interp(t[k], tf, dte['fv'])); px, py = float(np.interp(t[k], tf, dte['fx'])), float(np.interp(t[k], tf, dte['fy']))
                    b_ax = 0.98 * b_ax + 0.02 * (ax_b[k] - dv_true[k]) if k else 0.0        # a_long bias while healthy (slow EMA)
                    vv = v_ins
                else:
                    if variant == 'ins': v_ins = max(0.0, v_ins + (ax_b[k] - b_ax) * dt); vv = 0.0 if still[j] else v_ins
                    else: vv = float(raw[j])
                    px += math.cos(hf.psi) * vv * dt; py += math.sin(hf.psi) * vv * dt
                xs[k] = (px, py, vv, 1.0)
            else:
                f.update_model(float(raw[j]), float(sig[j]), bool(still[j]))
                for (tfx, i, wh) in getattr(f, 'pending', []):
                    if wh: f.gnss_lost()
                    else: f.update_gnss(tfx, dte['fx'][i], dte['fy'][i], dte['fv'][i], 3.0)
                f.pending = []; xs[k] = (f.x[0], f.x[1], f.x[2], f.x[3])
        tracks[variant] = xs; e = np.hypot(xs[:, 0] - dte['gx'], xs[:, 1] - dte['gy']); he = np.degrees(wrap(psi_hist - dte['gh']))
        for (m0, m1) in masks:
            w = (t >= m0) & (t < m1); dist = float(np.sum(np.hypot(np.diff(dte['gx'][w]), np.diff(dte['gy'][w]))))
            if dist < 50: continue
            hm = w & (dte['gv'] > 3)
            rows.append(dict(seq=a.test, variant=variant, t0=m0, mask_s=a.mask, dist_m=round(dist), end_m=round(float(e[w][-1]), 1), drift_pct=round(100 * float(e[w][-1]) / dist, 2), rmse_m=round(float(np.sqrt(np.mean(e[w] ** 2))), 1), max_m=round(float(e[w].max()), 1),
                             heading_err_mean=round(float(np.mean(he[hm])), 2) if hm.any() else np.nan, heading_err_max=round(float(np.abs(he[hm]).max()), 1) if hm.any() else np.nan, k_end=round(float(xs[w][-1, 3]), 3), v_mean=round(float(dte['gv'][w].mean()), 1)))
    df = pd.DataFrame(rows); Path('data/qa').mkdir(exist_ok=True); df.to_csv(f'data/qa/iovnbd_{a.test}.csv', index=False); pd.set_option('display.width', 220); print(df.to_string(index=False))
    for v in ('plain', 'ins', 'gen_k1', 'gen'):
        dd = df[df.variant == v]
        if len(dd): print(f"{v:7s}: {len(dd)} masks of {a.mask:.0f} s ({dd.dist_m.median():.0f} m median) | drift median {dd.drift_pct.median():.2f}% worst {dd.drift_pct.max():.2f}% under10 {(dd.drift_pct < 10).sum()}/{len(dd)} | endpoint median {dd.end_m.median():.1f} m | |heading err| median {dd.heading_err_mean.abs().median():.2f} deg | k_end median {dd.k_end.median():.3f}")
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(18, 7)); ax[0].plot(dte['gx'], dte['gy'], 'k', lw=2, label='VBOX truth')
    for v, col in (('plain', 'C2'), ('ins', 'C1'), ('gen_k1', 'C0'), ('gen', 'C3')):
        xs = tracks[v]
        for (m0, m1) in masks:
            w = (t >= m0) & (t <= m1); ax[0].plot(xs[w, 0], xs[w, 1], col, lw=1.2, label=v if (m0 == masks[0][0]) else None)
    ax[0].set_aspect('equal'); ax[0].legend(); ax[0].grid(alpha=.3); ax[0].set_title(f'IO-VNBD {a.test} (car, external 10 Hz IMU): engine during {a.mask:.0f} s GNSS masks every {a.every:.0f} s'); ax[0].set_xlabel('east [m]'); ax[0].set_ylabel('north [m]')
    for v, col in (('plain', 'C2'), ('ins', 'C1'), ('gen_k1', 'C0'), ('gen', 'C3')):
        e = np.hypot(tracks[v][:, 0] - dte['gx'], tracks[v][:, 1] - dte['gy']); ax[1].plot(t, e, col, lw=0.8, label=v)
    for (m0, m1) in masks: ax[1].axvspan(m0, m1, color='grey', alpha=0.15)
    ax[1].set_yscale('log'); ax[1].set_ylim(0.5, 2000); ax[1].set_xlabel('s'); ax[1].set_ylabel('position error [m]'); ax[1].legend(); ax[1].grid(alpha=.3, which='both')
    fig.tight_layout(); fig.savefig(f'data/qa/iovnbd_{a.test}.png', dpi=110); print('plot', f'data/qa/iovnbd_{a.test}.png')

if __name__ == '__main__':
    main()
