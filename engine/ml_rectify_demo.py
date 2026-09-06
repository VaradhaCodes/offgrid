"""Per-timestamp IMU error vs GNSS, and how an ML speed model rectifies it.

Usage: .venv/bin/python engine/ml_rectify_demo.py <train_processed_dir> <test_processed_dir> [--model gbr|ridge] [--tau 1.0]

Proxy speed model (stand-in for the CNN/GRU until the full dataset exists): 2 s windows of phone-frame IMU features
(vibration RMS, band energies, spectral peaks, gyro stats) -> forward speed, trained on the train session only.
Physical stop rule (ZUPT): vibration RMS < 0.6 m/s^2 AND gyro RMS < 0.06 rad/s over the window -> speed 0.
Filter proxy: exponential smoothing (tau) + rate limit 3 m/s^2 on the model output (the ESKF does this with sigma).
Simulated GNSS cut 10 s after motion starts. After the cut:
   IMU-accel  : speed = integral of forward specific force (raw INS)
   last-speed : speed frozen at the cut value
   ML         : proxy model output (+ZUPT +smoothing)
Heading for all three = gyro, initialised from GNSS bearing over the 10 s before the cut. Position at the cut = GNSS.
Outputs in the test folder: ml_timeline_10hz.csv, ml_rectify.png, ml_rectify_summary.json
"""
import sys, json, math, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from baseline_dr import qmul, qrot, q_from_two_vectors

FS = 100.0; WIN = 200; STRIDE = 10
BANDS = [(0.5, 2), (2, 5), (5, 12), (12, 25), (25, 49)]
STILL_RMS = 0.6; STILL_GYRO = 0.06

def features(tr):
    a = tr[['ax','ay','az']].values; g = tr[['gx','gy','gz']].values; t = tr['t_s'].values
    amag = np.linalg.norm(a, axis=1); freqs = np.fft.rfftfreq(WIN, 1/FS)
    rows = []; ts = []
    for end in range(WIN, len(tr)+1, STRIDE):
        wa = a[end-WIN:end]; wg = g[end-WIN:end]; wm = amag[end-WIN:end]
        d = wa - wa.mean(0); rms = np.sqrt((d**2).mean(0)); tot = float(np.sqrt((d**2).sum(1).mean()))
        spec = np.abs(np.fft.rfft(wm - wm.mean()))**2 / WIN
        bands = [np.log10(spec[(freqs>=lo)&(freqs<hi)].sum() + 1e-6) for lo, hi in BANDS]
        sel = (freqs>=0.5)&(freqs<=8); pk = freqs[sel][np.argmax(spec[sel])]; pkp = np.log10(spec[sel].max()+1e-6)
        specz = np.abs(np.fft.rfft(d[:,2]))**2 / WIN; pkz = freqs[sel][np.argmax(specz[sel])]
        grms = np.sqrt((wg**2).mean(0)); gmag = float(np.linalg.norm(wg, axis=1).mean())
        rows.append([*rms, tot, np.log10(tot+1e-6), *bands, pk, pkp, pkz, *grms, gmag, float(np.abs(wg[:,2]).mean())])
        ts.append(t[end-1])
    names = ['rms_x','rms_y','rms_z','rms_tot','log_rms_tot'] + [f'band_{lo}_{hi}' for lo,hi in BANDS] + ['pk_hz','pk_pow','pkz_hz','grms_x','grms_y','grms_z','gmag','gz_abs']
    return np.array(ts), np.array(rows), names

class Ridge:
    def fit(self, X, y, lam=3.0):
        self.mu = X.mean(0); self.sd = X.std(0)+1e-9; Xs = (X-self.mu)/self.sd; Xb = np.hstack([Xs, np.ones((len(Xs),1))])
        I = np.eye(Xb.shape[1]); I[-1,-1] = 0; self.w = np.linalg.solve(Xb.T@Xb + lam*I, Xb.T@y); return self
    def predict(self, X): Xs = (X-self.mu)/self.sd; return np.hstack([Xs, np.ones((len(Xs),1))]) @ self.w
    def importance(self, names): return sorted(zip(names, np.abs(self.w[:-1])), key=lambda z: -z[1])[:6]

def make_model(kind):
    if kind == 'ridge': return Ridge()
    from sklearn.ensemble import GradientBoostingRegressor
    m = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=0)
    m.importance = lambda names: sorted(zip(names, m.feature_importances_), key=lambda z: -z[1])[:6]
    return m

def still_mask(X, names):
    i = names.index('rms_tot'); ig = [names.index(k) for k in ('grms_x','grms_y','grms_z')]
    return (X[:, i] < STILL_RMS) & (np.sqrt((X[:, ig]**2).sum(1)) < STILL_GYRO)

def smooth(v, t, tau, amax=3.0):
    out = v.copy()
    for k in range(1, len(v)):
        dt = t[k]-t[k-1]; a = 1 - math.exp(-dt/tau) if tau > 0 else 1.0
        target = out[k-1] + a*(v[k]-out[k-1]); out[k] = np.clip(target, out[k-1]-amax*dt, out[k-1]+amax*dt)
    return np.clip(out, 0, None)

def robust_gyro_bias(t, G):
    """Gyro bias from a 'stationary' window while rejecting slow rider/bike movements:
    split into 1 s chunks, keep the quietest half by variance, drop chunks whose |mean| > 0.01 rad/s, average the rest."""
    chunks = []; t0 = t[0]
    while t0 + 1.0 <= t[-1]:
        m = (t >= t0) & (t < t0 + 1.0)
        if m.sum() > 50: chunks.append((G[m].var(axis=0).sum(), np.abs(G[m].mean(0)).max(), G[m].mean(0)))
        t0 += 1.0
    if not chunks: return G.mean(0)
    chunks.sort(key=lambda c: c[0]); quiet = [c for c in chunks[:max(6, len(chunks)//2)] if c[1] < 0.01]
    if len(quiet) < 3: return np.median(np.array([c[2] for c in chunks]), axis=0)
    return np.mean([c[2] for c in quiet], axis=0)

def gyro_heading(nat, tr):
    t = nat['t_s'].values; acc = nat[['ax','ay','az']].values; gyr = nat[['gx','gy','gz']].values
    calib_end = tr.loc[tr['state']=='CALIB','t_s'].max(); cal = (t>1.0)&(t<calib_end-1.0)
    g_b = acc[cal].mean(0); gm = np.linalg.norm(g_b); bias = robust_gyro_bias(t[cal], gyr[cal])
    q = q_from_two_vectors(g_b/gm, np.array([0,0,1.0])); n = len(t); w_up = np.zeros(n); f_nav = np.zeros((n,3))
    for k in range(1, n):
        dt = t[k]-t[k-1]; w = gyr[k]-bias; ang = np.linalg.norm(w)*dt
        if ang > 0:
            q = qmul(q, np.array([math.cos(ang/2), *(w/np.linalg.norm(w)*math.sin(ang/2))])); q /= np.linalg.norm(q)
        w_up[k] = qrot(q, w)[2]; f_nav[k] = qrot(q, acc[k]) - np.array([0,0,gm])
    return t, w_up, f_nav

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('train'); ap.add_argument('test'); ap.add_argument('--model', default='gbr'); ap.add_argument('--tau', type=float, default=1.0); ap.add_argument('--tag', default='')
    a = ap.parse_args(); trn = Path(a.train); tst = Path(a.test)
    tr_a = pd.read_csv(trn/'track_100hz.csv'); tr_b = pd.read_csv(tst/'track_100hz.csv')
    ta, Xa, names = features(tr_a); tb, Xb, _ = features(tr_b)
    ya = np.interp(ta, tr_a['t_s'], tr_a['speed_mps']); yb = np.interp(tb, tr_b['t_s'], tr_b['speed_mps'])
    model = make_model(a.model).fit(Xa, ya)
    raw = np.clip(model.predict(Xb), 0, None); raw[still_mask(Xb, names)] = 0.0
    pb = smooth(raw, tb, a.tau)
    mv = yb > 1.0
    print(f"[{a.model}] train {trn.name} ({len(ya)} win) -> test {tst.name} ({len(yb)} win): speed MAE raw {np.mean(np.abs(raw-yb)):.3f} | smoothed {np.mean(np.abs(pb-yb)):.3f} m/s (moving: {np.mean(np.abs(pb-yb)[mv]):.3f}); bias moving {np.mean((pb-yb)[mv]):+.3f} m/s; still-rule hits while moving: {int((still_mask(Xb,names)&mv).sum())}")
    imp = model.importance(names); print("top features:", [(n, round(float(v),3)) for n, v in imp])

    nat = pd.read_csv(tst/'imu_native.csv'); t, w_up, f_nav = gyro_heading(nat, tr_b)
    grid = tb; gx = np.interp(grid, tr_b['t_s'], tr_b['x_m']); gy = np.interp(grid, tr_b['t_s'], tr_b['y_m']); gs = yb
    gb = np.interp(grid, tr_b['t_s'], np.unwrap(np.radians(tr_b['bearing_deg'].ffill().bfill().values)))
    psi = np.interp(grid, t, np.cumsum(w_up*np.diff(t, prepend=t[0])))
    ride_start = tr_b.loc[tr_b['state']=='RIDE','t_s'].min(); ride_end = tr_b.loc[tr_b['state']=='RIDE','t_s'].max()
    t_mv0 = grid[np.where((grid>=ride_start)&(gs>1.0))[0][0]]; t_cut = t_mv0 + 10.0
    enu = np.pi/2 - gb; w_al = (grid>=t_cut-10)&(grid<=t_cut)&(gs>1.5); psi = psi + np.mean((enu[w_al]-psi[w_al]+np.pi)%(2*np.pi)-np.pi)
    hd = np.stack([np.cos(psi), np.sin(psi)], 1); dt = np.diff(grid, prepend=grid[0])
    f_h = np.stack([np.interp(grid, t, f_nav[:,0]), np.interp(grid, t, f_nav[:,1])], 1); fwd = np.einsum('ij,ij->i', f_h, hd)
    after = grid >= t_cut; k0 = int(np.argmax(after))
    v_imu = gs.copy(); v_last = gs.copy(); v_ml = gs.copy()
    for k in range(k0, len(grid)):
        v_imu[k] = v_imu[k-1] + fwd[k]*dt[k]; v_last[k] = gs[k0-1]; v_ml[k] = pb[k]
    def integrate(v):
        P = np.stack([gx, gy], 1).copy()
        for k in range(k0, len(grid)): P[k] = P[k-1] + hd[k]*v[k]*dt[k]
        return P
    P_imu, P_last, P_ml = integrate(v_imu), integrate(v_last), integrate(v_ml)
    e_imu = np.hypot(P_imu[:,0]-gx, P_imu[:,1]-gy); e_last = np.hypot(P_last[:,0]-gx, P_last[:,1]-gy); e_ml = np.hypot(P_ml[:,0]-gx, P_ml[:,1]-gy)
    phase = np.where(grid<ride_start,'CALIB',np.where(grid<t_cut,'GNSS_OK',np.where(grid<=ride_end,'OUTAGE','STOP')))
    out = pd.DataFrame({'t_s': grid, 'phase': phase, 'gnss_x_m': gx, 'gnss_y_m': gy, 'gnss_speed': gs, 'gnss_bearing_deg': np.degrees(gb)%360, 'gyro_heading_deg': (90-np.degrees(psi))%360,
        'heading_err_deg': ((90-np.degrees(psi)) - np.degrees(gb) + 180)%360-180, 'imu_accel_speed': v_imu, 'imu_accel_speed_err': v_imu-gs, 'last_speed': v_last, 'last_speed_err': v_last-gs,
        'ml_speed_raw': raw, 'ml_speed': v_ml, 'ml_speed_err': v_ml-gs, 'imu_x_m': P_imu[:,0], 'imu_y_m': P_imu[:,1], 'imu_pos_err_m': e_imu, 'last_x_m': P_last[:,0], 'last_y_m': P_last[:,1], 'last_pos_err_m': e_last,
        'ml_x_m': P_ml[:,0], 'ml_y_m': P_ml[:,1], 'ml_pos_err_m': e_ml, 'ml_correction_vs_imu_m': np.hypot(P_ml[:,0]-P_imu[:,0], P_ml[:,1]-P_imu[:,1])})
    tag = f"_{a.tag}" if a.tag else ""
    out.to_csv(tst/f'ml_timeline_10hz{tag}.csv', index=False, float_format='%.4f')
    og = (grid>=t_cut)&(grid<=ride_end); dist = float(np.sum(np.hypot(np.diff(gx[og]), np.diff(gy[og])))); end_all = grid <= grid[-1]
    def m(e, v): return dict(endpoint_m=round(float(e[og][-1]),1), rmse_m=round(float(np.sqrt(np.mean(e[og]**2))),1), max_m=round(float(e[og].max()),1), drift_pct=round(100*float(e[og][-1])/dist,1), speed_mae=round(float(np.mean(np.abs(v[og]-gs[og]))),3), err_after_stop_m=round(float(e[-1]),1))
    summ = dict(model=a.model, tau=a.tau, train=trn.name, test=tst.name, cut_s_into_ride=round(float(t_cut-ride_start),1), outage_seconds=round(float(ride_end-t_cut),1), outage_distance_m=round(dist,1),
                heading_err_mean_deg=round(float(out.loc[og,'heading_err_deg'].mean()),2), imu_accel=m(e_imu, v_imu), last_speed=m(e_last, v_last), ml=m(e_ml, v_ml), top_features=[(n, round(float(v),3)) for n,v in imp])
    json.dump(summ, open(tst/f'ml_rectify_summary{tag}.json','w'), indent=1)
    print(pd.DataFrame({k: summ[k] for k in ('imu_accel','last_speed','ml')}).T.to_string())
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, 2, figsize=(17, 11)); tt = grid - t_cut
    ax = axs[0,0]; ax.plot(tt, gs, 'k', lw=2, label='GNSS speed (truth)'); ax.plot(tt, v_imu, 'C3', label='IMU accelerometer integrated'); ax.plot(tt, v_last, 'C2', label='last speed held'); ax.plot(tt, raw, 'C0', lw=.6, alpha=.5, label='ML raw (10 Hz)'); ax.plot(tt, pb, 'C0', lw=1.8, label='ML + ZUPT + filter smoothing')
    ax.axvline(0, color='grey', ls='--'); ax.set_ylim(-1, 8); ax.grid(alpha=.3); ax.legend(fontsize=8); ax.set_ylabel('speed [m/s]'); ax.set_title('speed at each timestamp (GNSS cut at t=0)')
    ax = axs[0,1]; ax.plot(tt, v_imu-gs, 'C3', label='IMU accel speed error'); ax.plot(tt, v_last-gs, 'C2', label='last-speed error'); ax.plot(tt, pb-gs, 'C0', label='ML speed error'); ax.axhline(0,color='k',lw=.5); ax.axvline(0, color='grey', ls='--'); ax.set_ylim(-4, 6); ax.grid(alpha=.3); ax.legend(fontsize=8); ax.set_ylabel('speed error [m/s]'); ax.set_title('speed error at each timestamp')
    ax = axs[1,0]; ax.plot(tt[after], e_imu[after], 'C3', label='IMU accel'); ax.plot(tt[after], e_last[after], 'C2', label='last speed held'); ax.plot(tt[after], e_ml[after], 'C0', lw=2, label='ML speed'); ax.axhline(0.1*dist, color='grey', ls='--'); ax.text(1, 0.1*dist*1.05, f'10% of {dist:.0f} m', fontsize=8); ax.axvline(ride_end-t_cut, color='k', ls=':', lw=1); ax.text(ride_end-t_cut+0.5, 0.02, 'bike stops', fontsize=8)
    ax.set_yscale('log'); ax.grid(alpha=.3, which='both'); ax.legend(fontsize=8); ax.set_xlabel('s since GNSS cut'); ax.set_ylabel('position error [m] (log)'); ax.set_title('position error at each timestamp during the outage')
    ax = axs[1,1]; ax.plot(gx, gy, 'k', lw=3, label='GNSS truth'); ax.plot(P_imu[after,0], P_imu[after,1], 'C3', label='IMU accel'); ax.plot(P_last[after,0], P_last[after,1], 'C2', label='last speed'); ax.plot(P_ml[after,0], P_ml[after,1], 'C0', lw=2, label='ML speed'); ax.plot(gx[k0], gy[k0], 'mo', ms=9, label='cut point')
    ax.set_aspect('equal'); ax.set_xlim(gx.min()-40, gx.max()+20); ax.set_ylim(gy.min()-30, gy.max()+40); ax.grid(alpha=.3); ax.legend(fontsize=8); ax.set_xlabel('east [m]'); ax.set_ylabel('north [m]'); ax.set_title('paths after the cut (gyro heading for all three)')
    fig.suptitle(f'{tst.name}: GNSS cut {t_cut-ride_start:.0f} s into the ride, {dist:.0f} m outage — proxy {a.model} speed model trained on {trn.name} only'); fig.tight_layout(); fig.savefig(tst/f'ml_rectify{tag}.png', dpi=110)

if __name__ == '__main__':
    main()
