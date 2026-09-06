"""Decode one IDR Logger session into time-aligned vectors + a continuous position track.

Usage:  .venv/bin/python engine/decode_session.py data/raw/<session_dir> [--rate 100]

Outputs (data/processed/<session>/):
  imu_native.csv      accel timestamps (~420 Hz): t_s, t_ns, ax, ay, az, gx, gy, gz (gyro interpolated onto accel times)
  track_<rate>hz.csv  uniform grid: t_s, ax..gz (anti-aliased + resampled), lat, lon, x_m, y_m, speed_mps, bearing_deg,
                      gnss_age_s, state (CALIB / RIDE / STOP_CALIB)
  gnss_fixes.csv      the raw 1 Hz fixes with local x_m, y_m
  overview.png        accel / gyro / speed time series + the x-y track
Position between 1 Hz fixes is interpolated (PCHIP, no overshoot) in local metres relative to the session start anchor.
"""
import sys, json, argparse, math
from pathlib import Path
import numpy as np, pandas as pd
from scipy.signal import butter, sosfiltfilt
from scipy.interpolate import PchipInterpolator

def local_xy(lat, lon, lat0, lon0):
    mlat = 111320.0; mlon = 111320.0 * math.cos(math.radians(lat0))
    return (np.asarray(lon) - lon0) * mlon, (np.asarray(lat) - lat0) * mlat

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('session'); ap.add_argument('--rate', type=float, default=100.0)
    a = ap.parse_args(); sd = Path(a.session); out = Path('data/processed') / sd.name; out.mkdir(parents=True, exist_ok=True)
    meta = json.load(open(sd / 'session.json'))
    ev = pd.read_csv(sd / 'events.csv'); ev_t = dict(zip(ev['type'], ev['t_ns']))
    t0 = int(ev_t['SESSION_START'])
    acc = pd.read_csv(sd / 'acc.csv'); gyr = pd.read_csv(sd / 'gyr.csv'); fix = pd.read_csv(sd / 'gnss_fix.csv')
    acc = acc.drop_duplicates('t_ns').sort_values('t_ns'); gyr = gyr.drop_duplicates('t_ns').sort_values('t_ns')
    ta = (acc['t_ns'].values - t0) / 1e9; tg = (gyr['t_ns'].values - t0) / 1e9

    # ---- native-rate table: gyro linearly interpolated onto accel timestamps
    nat = pd.DataFrame({'t_s': ta, 't_ns': acc['t_ns'].values,
                        'ax': acc['ax'].values, 'ay': acc['ay'].values, 'az': acc['az'].values})
    for c in ('gx', 'gy', 'gz'):
        nat[c] = np.interp(ta, tg, gyr[c].values)
    nat.to_csv(out / 'imu_native.csv', index=False, float_format='%.6f')

    # ---- uniform grid: anti-alias (Butterworth 4th order, 0.4*rate) then sample
    fs_native = 1.0 / np.median(np.diff(ta))
    sos = butter(4, 0.4 * a.rate, btype='low', fs=fs_native, output='sos')
    grid = np.arange(0.0, ta[-1], 1.0 / a.rate)
    tr = pd.DataFrame({'t_s': grid})
    for c in ('ax', 'ay', 'az', 'gx', 'gy', 'gz'):
        tr[c] = np.interp(grid, ta, sosfiltfilt(sos, nat[c].values))

    # ---- GNSS: local metres from the start anchor, PCHIP interpolation between 1 Hz fixes
    lat0 = meta['start_anchor']['lat']; lon0 = meta['start_anchor']['lon']
    fix = fix.sort_values('t_ns'); tf = (fix['t_ns'].values - t0) / 1e9
    fx, fy = local_xy(fix['lat'].values, fix['lon'].values, lat0, lon0)
    fix_out = fix[['t_ns', 'lat', 'lon', 'alt', 'acc_h', 'speed', 'bearing', 'n_sats_used']].copy()
    fix_out.insert(0, 't_s', tf); fix_out['x_m'] = fx; fix_out['y_m'] = fy
    fix_out.to_csv(out / 'gnss_fixes.csv', index=False, float_format='%.7f')
    px = PchipInterpolator(tf, fx, extrapolate=False); py = PchipInterpolator(tf, fy, extrapolate=False)
    tr['x_m'] = px(grid); tr['y_m'] = py(grid)
    # hold first/last fix outside the fix span
    tr['x_m'] = tr['x_m'].ffill().bfill(); tr['y_m'] = tr['y_m'].ffill().bfill()
    mlat = 111320.0; mlon = 111320.0 * math.cos(math.radians(lat0))
    tr['lat'] = lat0 + tr['y_m'] / mlat; tr['lon'] = lon0 + tr['x_m'] / mlon
    tr['speed_mps'] = np.interp(grid, tf, fix['speed'].values)
    # bearing: interpolate unit vectors to avoid the 359->1 wrap
    br = np.radians(fix['bearing'].values)
    bx = np.interp(grid, tf, np.cos(br)); by = np.interp(grid, tf, np.sin(br))
    tr['bearing_deg'] = (np.degrees(np.arctan2(by, bx)) + 360.0) % 360.0
    idx = np.searchsorted(tf, grid, side='right') - 1
    tr['gnss_age_s'] = np.where(idx >= 0, grid - tf[np.clip(idx, 0, len(tf) - 1)], np.nan)
    state = np.full(len(grid), 'RIDE', dtype=object)
    state[grid < (ev_t['CALIB_END'] - t0) / 1e9] = 'CALIB'
    state[grid >= (ev_t['STOP_CALIB_START'] - t0) / 1e9] = 'STOP_CALIB'
    tr['state'] = state
    tr['lat'] = tr['lat'].map(lambda v: f'{v:.8f}'); tr['lon'] = tr['lon'].map(lambda v: f'{v:.8f}')
    tr.to_csv(out / f'track_{int(a.rate)}hz.csv', index=False, float_format='%.6f')

    # ---- overview plot
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(16, 12)); gs = fig.add_gridspec(3, 2, width_ratios=[1.6, 1])
    ax1 = fig.add_subplot(gs[0, 0]); ax2 = fig.add_subplot(gs[1, 0], sharex=ax1); ax3 = fig.add_subplot(gs[2, 0], sharex=ax1); axm = fig.add_subplot(gs[:, 1])
    for c, col in zip(('ax', 'ay', 'az'), ('C3', 'C2', 'C0')): ax1.plot(tr['t_s'], tr[c], col, lw=0.6, label=c)
    for c, col in zip(('gx', 'gy', 'gz'), ('C3', 'C2', 'C0')): ax2.plot(tr['t_s'], tr[c], col, lw=0.6, label=c)
    ax3.plot(tr['t_s'], tr['speed_mps'], 'k', lw=1.2, label='GNSS speed (Doppler)'); ax3.plot(tf, fix['speed'], 'k.', ms=4)
    for axx in (ax1, ax2, ax3):
        axx.axvspan(0, (ev_t['CALIB_END'] - t0) / 1e9, color='grey', alpha=0.15)
        axx.axvspan((ev_t['STOP_CALIB_START'] - t0) / 1e9, grid[-1], color='grey', alpha=0.15); axx.legend(loc='upper right', fontsize=8); axx.grid(alpha=0.3)
    ax1.set_ylabel('accel phone frame [m/s²]'); ax2.set_ylabel('gyro phone frame [rad/s]'); ax3.set_ylabel('speed [m/s]'); ax3.set_xlabel('t [s] since SESSION_START (grey = stationary calibration windows)')
    ax1.set_title(f"{sd.name}  |  {a.rate:.0f} Hz resampled from {fs_native:.0f} Hz  |  {len(fix)} GNSS fixes")
    sc = axm.scatter(tr['x_m'], tr['y_m'], c=tr['t_s'], s=3, cmap='viridis'); axm.plot(fx, fy, 'r.', ms=5, label='1 Hz GNSS fixes')
    axm.plot(fx[0], fy[0], 'go', ms=10, label='start'); axm.plot(fx[-1], fy[-1], 'rs', ms=10, label='end')
    axm.set_aspect('equal'); axm.grid(alpha=0.3); axm.set_xlabel('east [m] from start anchor'); axm.set_ylabel('north [m]'); axm.legend(fontsize=8)
    plt.colorbar(sc, ax=axm, label='t [s]'); axm.set_title('continuous position (PCHIP between fixes)')
    fig.tight_layout(); fig.savefig(out / 'overview.png', dpi=110)
    d = math.hypot(fx[-1] - fx[0], fy[-1] - fy[0]); path = float(np.sum(np.hypot(np.diff(fx), np.diff(fy))))
    print(f"native rate {fs_native:.1f} Hz, {len(nat)} IMU rows -> {len(tr)} rows at {a.rate:.0f} Hz; fixes {len(fix)}; start->end {d:.1f} m; path {path:.1f} m; max speed {fix['speed'].max():.2f} m/s")
    print("wrote", [p.name for p in sorted(out.iterdir())])

if __name__ == '__main__':
    main()
