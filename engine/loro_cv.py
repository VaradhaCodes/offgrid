"""Leave-one-run-out cross-validation of the proxy speed model + outage replay, over a set of processed sessions.
Usage: .venv/bin/python engine/loro_cv.py data/processed/20260905_*  (list of processed session dirs)
Writes data/processed/_loro_cv_summary.csv and _loro_cv.png
"""
import sys, math, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from ml_rectify_demo import features, make_model, still_mask, smooth, gyro_heading

def replay(tst, tr_b, tb, pred, cut_after=10.0):
    nat = pd.read_csv(tst/'imu_native.csv'); t, w_up, f_nav = gyro_heading(nat, tr_b)
    grid = tb; gx = np.interp(grid, tr_b['t_s'], tr_b['x_m']); gy = np.interp(grid, tr_b['t_s'], tr_b['y_m']); gs = np.interp(grid, tr_b['t_s'], tr_b['speed_mps'])
    gb = np.interp(grid, tr_b['t_s'], np.unwrap(np.radians(tr_b['bearing_deg'].ffill().bfill().values)))
    psi = np.interp(grid, t, np.cumsum(w_up*np.diff(t, prepend=t[0])))
    ride_start = tr_b.loc[tr_b['state']=='RIDE','t_s'].min(); ride_end = tr_b.loc[tr_b['state']=='RIDE','t_s'].max()
    t_mv0 = grid[np.where((grid>=ride_start)&(gs>1.0))[0][0]]; t_cut = t_mv0 + cut_after
    enu = np.pi/2 - gb; w_al = (grid>=t_cut-10)&(grid<=t_cut)&(gs>1.5); psi = psi + np.mean((enu[w_al]-psi[w_al]+np.pi)%(2*np.pi)-np.pi)
    hd = np.stack([np.cos(psi), np.sin(psi)], 1); dt = np.diff(grid, prepend=grid[0]); after = grid >= t_cut; k0 = int(np.argmax(after))
    def integrate(v):
        P = np.stack([gx, gy], 1).copy()
        for k in range(k0, len(grid)): P[k] = P[k-1] + hd[k]*v[k]*dt[k]
        return np.hypot(P[:,0]-gx, P[:,1]-gy)
    v_last = gs.copy(); v_last[after] = gs[k0-1]; v_ml = gs.copy(); v_ml[after] = pred[after]
    og = (grid>=t_cut)&(grid<=ride_end); dist = float(np.sum(np.hypot(np.diff(gx[og]), np.diff(gy[og]))))
    e_last = integrate(v_last); e_ml = integrate(v_ml)
    hd_err = float(np.mean(((90-np.degrees(psi)) - np.degrees(gb) + 180)%360-180) if False else np.mean((((np.pi/2-psi)-gb+np.pi)%(2*np.pi)-np.pi)[og]))
    return dict(outage_m=round(dist,0), outage_s=round(float(ride_end-t_cut),0), last_end_m=round(float(e_last[og][-1]),1), ml_end_m=round(float(e_ml[og][-1]),1), ml_rmse_m=round(float(np.sqrt(np.mean(e_ml[og]**2))),1), ml_drift_pct=round(100*float(e_ml[og][-1])/dist,1), last_drift_pct=round(100*float(e_last[og][-1])/dist,1), ml_after_stop_m=round(float(e_ml[-1]),1), last_after_stop_m=round(float(e_last[-1]),1), heading_err_deg=round(math.degrees(hd_err),1))

def main():
    cut = 10.0; args = sys.argv[1:]
    if '--cut' in args:
        i = args.index('--cut'); cut = float(args[i+1]); args = args[:i] + args[i+2:]
    dirs = [Path(p) for p in args if (Path(p)/'track_100hz.csv').exists()]; suf = f'_cut{int(cut)}'
    data = {}
    for d in dirs:
        tr = pd.read_csv(d/'track_100hz.csv'); t, X, names = features(tr); y = np.interp(t, tr['t_s'], tr['speed_mps']); data[d] = (tr, t, X, y, names)
    rows = []
    for d in dirs:
        Xa = np.vstack([data[o][2] for o in dirs if o != d]); ya = np.concatenate([data[o][3] for o in dirs if o != d])
        tr_b, tb, Xb, yb, names = data[d]
        model = make_model('gbr').fit(Xa, ya); raw = np.clip(model.predict(Xb), 0, None); raw[still_mask(Xb, names)] = 0.0; pb = smooth(raw, tb, 1.0)
        mv = yb > 1.0; r = dict(run=d.name.split('_')[-1], dir=d.name.split('_')[-2], n_train=len(ya), speed_mae=round(float(np.mean(np.abs(pb-yb))),3), speed_mae_moving=round(float(np.mean(np.abs(pb-yb)[mv])),3), speed_bias_moving=round(float(np.mean((pb-yb)[mv])),3), v_mean=round(float(yb[mv].mean()),2))
        r.update(replay(d, tr_b, tb, pb, cut_after=cut)); rows.append(r); print(r, flush=True)
    df = pd.DataFrame(rows); df.to_csv(f'data/processed/_loro_cv_summary{suf}.csv', index=False)
    print(df.to_string(index=False))
    print("\nMEDIAN speed MAE moving %.3f m/s | ML endpoint median %.1f m (drift %.1f%%), worst %.1f m | last-speed endpoint median %.1f m (drift %.1f%%), worst %.1f m | after-stop: ML %.1f m vs last %.1f m (median) | heading err median %.1f deg" % (
        df.speed_mae_moving.median(), df.ml_end_m.median(), df.ml_drift_pct.median(), df.ml_end_m.max(), df.last_end_m.median(), df.last_drift_pct.median(), df.last_end_m.max(), df.ml_after_stop_m.median(), df.last_after_stop_m.median(), df.heading_err_deg.abs().median()))
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 3, figsize=(18, 5)); x = np.arange(len(df))
    axs[0].bar(x-0.2, df.last_drift_pct, 0.4, label='last speed held', color='C2'); axs[0].bar(x+0.2, df.ml_drift_pct, 0.4, label='ML speed (leave-one-run-out)', color='C0'); axs[0].axhline(10, color='r', ls='--', label='10 % target'); axs[0].set_xticks(x); axs[0].set_xticklabels(df.run, rotation=60, fontsize=8); axs[0].set_ylabel('endpoint drift, % of outage distance'); axs[0].legend(fontsize=8); axs[0].set_title(f'outage drift per held-out run (GNSS cut {int(cut)} s after start)')
    axs[1].bar(x, df.speed_mae_moving, color='C0'); axs[1].set_xticks(x); axs[1].set_xticklabels(df.run, rotation=60, fontsize=8); axs[1].set_ylabel('speed MAE while moving [m/s]'); axs[1].set_title('proxy speed model error per held-out run'); axs[1].axhline(df.speed_mae_moving.median(), color='k', ls=':')
    axs[2].scatter(df.v_mean, df.speed_bias_moving, c='C0'); 
    for _, r in df.iterrows(): axs[2].annotate(r.run.replace('run',''), (r.v_mean, r.speed_bias_moving), fontsize=7)
    axs[2].axhline(0, color='k', lw=.5); axs[2].set_xlabel('mean ride speed [m/s]'); axs[2].set_ylabel('speed bias [m/s]'); axs[2].set_title('bias vs ride speed (does the model cover slow and fast rides?)'); axs[2].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(f'data/processed/_loro_cv{suf}.png', dpi=110)

if __name__ == '__main__':
    main()
