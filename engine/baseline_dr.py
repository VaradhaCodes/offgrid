"""Classical dead-reckoning baselines on one decoded session, scored against GNSS.

Usage: .venv/bin/python engine/baseline_dr.py data/processed/<session>

Variants (all causal, GNSS withheld after RIDE_START except where stated):
  A  pure INS          : strapdown integration of accel+gyro (tilt from stationary gravity, gyro bias from calib,
                         yaw aligned to GNSS over the first 8 s of motion). No constraints. Shows raw IMU drift.
  B  INS + fwd-only    : same attitude, but speed = integral of forward (horizontal-along-heading) specific force,
                         lateral/vertical velocity forced to zero (non-holonomic). Isolates accelerometer speed drift.
  C  gyro heading + last GNSS speed held : heading from gyro, speed frozen at the value when GNSS was cut.
  D  gyro heading + true GNSS speed      : heading from gyro, speed from GNSS Doppler (cheating on speed only).
                         Isolates heading (gyro) error = what a perfect speed model would give.
Outputs: baseline_dr.png, baseline_dr_errors.csv (per-time errors), baseline_dr_summary.json
"""
import sys, json, math
from pathlib import Path
import numpy as np, pandas as pd

def qmul(a, b):
    w1,x1,y1,z1 = a; w2,x2,y2,z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def qrot(q, v):  # rotate v by q (body->nav)
    w,x,y,z = q
    R = np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],[2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],[2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
    return R @ v
def q_from_two_vectors(a, b):  # quaternion rotating unit a onto unit b
    c = np.cross(a, b); d = float(np.dot(a, b))
    if d < -0.999999: return np.array([0.0, 1.0, 0.0, 0.0])
    q = np.array([1.0 + d, *c]); return q / np.linalg.norm(q)

def main():
    pdir = Path(sys.argv[1]); nat = pd.read_csv(pdir / 'imu_native.csv'); tr = pd.read_csv(pdir / 'track_100hz.csv'); fx = pd.read_csv(pdir / 'gnss_fixes.csv')
    t = nat['t_s'].values; acc = nat[['ax','ay','az']].values; gyr = nat[['gx','gy','gz']].values
    calib_end = tr.loc[tr['state']=='CALIB','t_s'].max(); ride_start = tr.loc[tr['state']=='RIDE','t_s'].min(); ride_end = tr.loc[tr['state']=='RIDE','t_s'].max()
    cal = (t > 1.0) & (t < calib_end - 1.0)            # trim 1 s each side of the calib window
    g_b = acc[cal].mean(0); g_mag = float(np.linalg.norm(g_b)); gyro_bias = gyr[cal].mean(0)
    print(f"calib: |g|={g_mag:.4f}  gravity_body={np.round(g_b,3)}  gyro_bias={np.round(gyro_bias,5)} rad/s  ({np.round(np.degrees(gyro_bias)*60,2)} deg/min)")
    # initial attitude: body 'up' -> nav z; yaw free (0)
    q = q_from_two_vectors(g_b / g_mag, np.array([0.0, 0.0, 1.0]))
    n = len(t); pos = np.zeros((n,3)); vel = np.zeros(3); f_nav = np.zeros((n,3)); w_up = np.zeros(n); q_hist = np.zeros((n,4))
    gvec = np.array([0.0, 0.0, g_mag])
    moving_from = ride_start
    for k in range(1, n):
        dt = t[k] - t[k-1]
        w = gyr[k] - gyro_bias; ang = np.linalg.norm(w) * dt
        if ang > 0:
            dq = np.array([math.cos(ang/2), *(w / np.linalg.norm(w) * math.sin(ang/2))]); q = qmul(q, dq); q /= np.linalg.norm(q)
        q_hist[k] = q
        fn = qrot(q, acc[k]) - gvec; f_nav[k] = fn; w_up[k] = qrot(q, w)[2]
        if t[k] < moving_from:  # ZUPT while stationary before the ride
            vel[:] = 0; pos[k] = pos[k-1]
        else:
            vel = vel + fn * dt; pos[k] = pos[k-1] + vel * dt
    # ---- GNSS reference on the IMU timeline (from the 100 Hz track)
    gx = np.interp(t, tr['t_s'], tr['x_m']); gy = np.interp(t, tr['t_s'], tr['y_m']); gs = np.interp(t, tr['t_s'], tr['speed_mps'])
    gb = np.interp(t, tr['t_s'], np.unwrap(np.radians(tr['bearing_deg'].ffill().bfill().values)))
    # ---- yaw alignment of variant A using the first 8 s of motion (GNSS speed > 1 m/s)
    mv = np.where((t >= ride_start) & (gs > 1.0))[0]; t_mv0 = t[mv[0]]; win = (t >= t_mv0) & (t <= t_mv0 + 8.0)
    d_ins = pos[win][-1,:2] - pos[win][0,:2]; d_gn = np.array([gx[win][-1]-gx[win][0], gy[win][-1]-gy[win][0]])
    th = math.atan2(d_gn[1], d_gn[0]) - math.atan2(d_ins[1], d_ins[0]); c, s = math.cos(th), math.sin(th); Rz = np.array([[c,-s],[s,c]])
    A = (Rz @ pos[:, :2].T).T; A += np.array([gx[0], gy[0]]) - A[0]
    fA = (Rz @ f_nav[:, :2].T).T
    # ---- heading from gyro (variant B/C/D): psi ENU, initialised so that it matches GNSS bearing over the first moving 3 s
    psi = np.zeros(n); dtv = np.diff(t, prepend=t[0]); psi = np.cumsum(w_up * dtv)
    enu_gnss = np.pi/2 - gb   # bearing (cw from N) -> ENU angle (ccw from E)
    w3 = (t >= t_mv0) & (t <= t_mv0 + 3.0); psi += np.mean(enu_gnss[w3] - psi[w3])
    hd = np.stack([np.cos(psi), np.sin(psi)], 1)
    # B: forward-axis accel integration with NHC, ZUPT before the ride
    vB = np.zeros(n); 
    for k in range(1, n):
        if t[k] < ride_start: vB[k] = 0
        else: vB[k] = vB[k-1] + float(np.dot(fA[k], hd[k])) * (t[k]-t[k-1])
    B = np.cumsum(hd * (vB * dtv)[:, None], 0); B += np.array([gx[0], gy[0]]) - B[0]
    # C: last speed held (speed at ride start ~ 0 would be silly: hold the speed 5 s after motion start, i.e. simulate cut at t_mv0+5)
    t_cut = t_mv0 + 5.0; v_hold = float(np.interp(t_cut, t, gs))
    vC = np.where(t < t_cut, gs, v_hold); C_ = np.cumsum(hd * (vC * dtv)[:, None], 0); C_ += np.array([gx[0], gy[0]]) - C_[0]
    D = np.cumsum(hd * (gs * dtv)[:, None], 0); D += np.array([gx[0], gy[0]]) - D[0]
    # ---- errors
    ride = (t >= ride_start) & (t <= ride_end)
    def metrics(P, name):
        e = np.hypot(P[:,0]-gx, P[:,1]-gy); er = e[ride]
        path = float(np.sum(np.hypot(np.diff(P[ride,0]), np.diff(P[ride,1])))); gpath = float(np.sum(np.hypot(np.diff(gx[ride]), np.diff(gy[ride]))))
        return dict(variant=name, endpoint_err_m=round(float(e[ride][-1]),1), rmse_m=round(float(np.sqrt(np.mean(er**2))),1), max_err_m=round(float(er.max()),1),
                    err_at_10s=round(float(np.interp(ride_start+10, t, e)),1), err_at_30s=round(float(np.interp(ride_start+30, t, e)),1), err_at_60s=round(float(np.interp(ride_start+60, t, e)),1),
                    gnss_path_m=round(gpath,1), variant_path_m=round(path,1), path_len_err_pct=round(100*(path-gpath)/gpath,1), endpoint_drift_pct_of_dist=round(100*float(e[ride][-1])/gpath,1)), e
    res = []; errs = {}
    for P, name in ((A,'A_pure_INS'), (B,'B_INS_fwd_only_NHC'), (C_,'C_gyro_heading_last_speed_held'), (D,'D_gyro_heading_true_speed')):
        m, e = metrics(P, name); res.append(m); errs[name] = e
    summ = dict(session=pdir.name, ride_seconds=round(float(ride_end-ride_start),1), gravity_mag=g_mag, gyro_bias_rad_s=gyro_bias.tolist(), yaw_align_deg=round(math.degrees(th),1),
                heading_err_end_deg=round(float(np.degrees((psi[ride][-1]-enu_gnss[ride][-1]+np.pi)%(2*np.pi)-np.pi)),1), results=res)
    json.dump(summ, open(pdir/'baseline_dr_summary.json','w'), indent=1)
    pd.DataFrame({'t_s': t, **{k: v for k, v in errs.items()}, 'gyro_heading_deg': (90-np.degrees(psi))%360, 'gnss_bearing_deg': np.degrees(gb)%360, 'ins_fwd_speed_B': vB, 'gnss_speed': gs}).iloc[::4].to_csv(pdir/'baseline_dr_errors.csv', index=False, float_format='%.3f')
    print(pd.DataFrame(res).to_string(index=False))
    print("heading error at end of ride (gyro vs GNSS):", summ['heading_err_end_deg'], "deg")
    # ---- plot
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, 2, figsize=(17, 12))
    ax = axs[0,0]; ax.plot(gx[ride], gy[ride], 'k', lw=3, label='GNSS reference')
    for P, name, col in ((A,'A pure INS','C3'), (B,'B INS fwd-only (NHC)','C1'), (C_,'C gyro heading + last speed held','C2'), (D,'D gyro heading + true speed','C0')):
        ax.plot(P[ride,0], P[ride,1], col, lw=1.5, label=name)
    ax.set_aspect('equal'); ax.grid(alpha=.3); ax.legend(fontsize=8); ax.set_title('paths during the ride (GNSS withheld from all variants)'); ax.set_xlabel('east [m]'); ax.set_ylabel('north [m]')
    lim = 1.3*max(abs(gx[ride]).max(), abs(gy[ride]).max()); ax.set_xlim(-lim-20, 40); ax.set_ylim(-lim/2-20, lim/2+40)
    ax = axs[0,1]
    for name, col in (('A_pure_INS','C3'),('B_INS_fwd_only_NHC','C1'),('C_gyro_heading_last_speed_held','C2'),('D_gyro_heading_true_speed','C0')):
        ax.plot(t[ride]-ride_start, errs[name][ride], col, label=name)
    ax.set_yscale('log'); ax.grid(alpha=.3, which='both'); ax.legend(fontsize=8); ax.set_xlabel('s since ride start'); ax.set_ylabel('position error vs GNSS [m] (log)'); ax.set_title('position error over time')
    ax.axhline(0.1*float(np.sum(np.hypot(np.diff(gx[ride]), np.diff(gy[ride])))), color='grey', ls='--'); ax.text(1, 0.1*float(np.sum(np.hypot(np.diff(gx[ride]), np.diff(gy[ride]))))*1.1, '10 % of distance', fontsize=8)
    ax = axs[1,0]; ax.plot(t[ride]-ride_start, np.degrees(gb[ride])%360, 'k', label='GNSS bearing'); ax.plot(t[ride]-ride_start, (90-np.degrees(psi[ride]))%360, 'C0', label='gyro-integrated heading'); ax.grid(alpha=.3); ax.legend(); ax.set_ylabel('heading [deg, cw from N]'); ax.set_xlabel('s since ride start'); ax.set_title('heading: gyro vs GNSS')
    ax = axs[1,1]; ax.plot(t[ride]-ride_start, gs[ride], 'k', label='GNSS speed'); ax.plot(t[ride]-ride_start, vB[ride], 'C1', label='B: integrated forward accel'); ax.plot(t[ride]-ride_start, np.hypot(*(np.gradient(A[:,0], t), np.gradient(A[:,1], t)))[ride], 'C3', lw=.5, alpha=.7, label='A: pure INS horizontal speed'); ax.set_ylim(-2, 15); ax.grid(alpha=.3); ax.legend(fontsize=8); ax.set_ylabel('speed [m/s]'); ax.set_xlabel('s since ride start'); ax.set_title('speed: accelerometer integration vs GNSS')
    fig.suptitle(f"{pdir.name} — classical dead-reckoning baselines vs GNSS"); fig.tight_layout(); fig.savefig(pdir/'baseline_dr.png', dpi=110)

if __name__ == '__main__':
    main()
