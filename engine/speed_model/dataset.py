"""Speed-model dataset builder (step 4). Windows of bike-frame IMU with GNSS speed labels, causal, never straddling stands.

Usage: .venv/bin/python engine/speed_model/dataset.py --tag route1 --rates 50,100,200 [--lag auto|0.5]
Writes data/speed_model/<tag>_<rate>hz.npz with:
  imu    float32 [n_samples_total, 6]  bike-frame ax ay az gx gy gz (gravity NOT removed, gyro bias NOT removed) per run, concatenated
  t      float64 [n_samples_total]     seconds since SESSION_START
  run_id int16   [n_samples_total]     index into runs
  v      float32 [n_samples_total]     GNSS Doppler speed interpolated to the sample time, shifted by the label lag (NaN where invalid)
  phase  int8    [n_samples_total]     0 = start stand, 1 = ride, 2 = end stand, -1 = other
  runs   object  list of dicts (session, run, dir, rider, flags, ride window, motion start/end, lag)
Windows are cut at training time from these arrays (window length and stride are sweep parameters); a window is valid when all
its samples share one phase and its label is finite. Resampling: 4th-order Butterworth at 0.4*rate on the 420 Hz native table,
then linear interpolation to the uniform grid (offline only; the phone requests the rate directly).
Label lag: the receiver's Doppler speed is reported late relative to the true speed. Estimated per run as the lag that maximises
the correlation between the Doppler speed and the position-derived speed (distance between consecutive fixes over their
interval, placed at the mid-point), then the MEDIAN across runs is applied to all runs (one constant, no per-run leak):
label(t) = v_doppler(t + lag). (The first build used a vibration-RMS proxy and applied the lag with the wrong sign, so the
labels lagged the true speed by ~0.9 s and the model output by 0.8 s; measured and corrected on 5 Sep 2026, see docs/11.)
"""
import sys, json, argparse, math
from pathlib import Path
import numpy as np, pandas as pd
from scipy.signal import butter, sosfiltfilt
sys.path.insert(0, str(Path(__file__).parent.parent))
from session import Session, find_sessions
from evaluate import kept_runs

def resample(nat, rate):
    t = nat['t_s'].values; fs = 1.0 / np.median(np.diff(t)); sos = butter(4, 0.4 * rate, btype='low', fs=fs, output='sos')
    grid = np.arange(t[0], t[-1], 1.0 / rate); out = np.empty((len(grid), 6), np.float32)
    for i, c in enumerate(('ax', 'ay', 'az', 'gx', 'gy', 'gz')): out[:, i] = np.interp(grid, t, sosfiltfilt(sos, nat[c].values))
    return grid, out

def label_lag(tf, v, x, y):
    """Lag (s) of the receiver's Doppler speed relative to the position-derived speed: v_pos = distance between consecutive fixes
    over their interval, placed at the mid-point; argmax corr(v_dop(t_mid + lag), v_pos(t_mid)) over -0.5..1.5 s. Positive = the
    reported speed describes the state `lag` seconds earlier, so the label at IMU time t is v_dop(t + lag)."""
    dt = np.diff(tf); ok = (dt > 0.5) & (dt < 1.6); tm = (tf[1:] + tf[:-1]) / 2; vp = np.hypot(np.diff(x), np.diff(y)) / np.where(dt > 0, dt, 1.0)
    m = ok & (vp > 1.0); best = (0.0, -1)
    for lag in np.arange(-0.5, 1.51, 0.1):
        c = np.corrcoef(np.interp(tm[m] + lag, tf, v), vp[m])[0, 1]
        if c > best[1]: best = (float(lag), float(c))
    return best

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tag', default='route1'); ap.add_argument('--rates', default='50,100,200'); ap.add_argument('--lag', default='auto')
    a = ap.parse_args(); qa = kept_runs(f'data/qa/{a.tag}.csv', f'data/{a.tag}/sessions'); rates = [int(r) for r in a.rates.split(',')]
    runs = []; per_rate = {r: dict(imu=[], t=[], run_id=[], v=[], phase=[]) for r in rates}; lags = []
    for ri, row in qa.iterrows():
        s = Session(row['session_dir'], load_status=False, load_extra=False); al = json.load(open(Path('data/processed') / s.name / 'align.json'))
        R = np.array(al['R_pb']); nat = s.imu_native(); fx = s.fix; tf = fx['t_s'].values; v = fx['speed'].values
        good = (fx['acc_h'].values <= 10.0) & (fx['speed_acc'].values <= 1.0) if 'speed_acc' in fx else (fx['acc_h'].values <= 10.0)
        inr = (tf >= s.ride[0]) & (tf <= s.ride[1]); mv = np.where(inr & (v > 1.0))[0]
        t_m0 = float(tf[mv[0]]) if len(mv) else s.ride[0]; t_m1 = float(tf[mv[-1]]) if len(mv) else s.ride[1]
        lag, corr = label_lag(tf, v, fx['x_m'].values, fx['y_m'].values); lags.append(lag)
        runs.append(dict(session=s.name, run=s.run_no, dir=s.direction, rider=s.rider, flags=row['flags_str'], calib=list(s.calib), ride=list(s.ride), stop=list(s.stop), t_m0=t_m0, t_m1=t_m1, lag_est=lag, lag_corr=round(corr, 3), pitch_qa=float(row['pitch_start'])))
        for r in rates:
            grid, imu = resample(nat, r); imu = np.hstack([(R @ imu[:, :3].T).T, (R @ imu[:, 3:].T).T]).astype(np.float32)
            phase = np.full(len(grid), -1, np.int8); phase[(grid >= s.calib[0] + 1.0) & (grid <= s.calib[1] - 0.5)] = 0
            phase[(grid >= s.ride[0]) & (grid <= s.ride[1])] = 1; phase[(grid >= s.stop[0] + 0.5) & (grid <= s.stop[1] - 0.5)] = 2
            per_rate[r]['imu'].append(imu); per_rate[r]['t'].append(grid); per_rate[r]['run_id'].append(np.full(len(grid), ri, np.int16)); per_rate[r]['phase'].append(phase)
        print(f"{s.name}: ride {s.ride[1]-s.ride[0]:.0f} s, lag {lag:.1f} s (corr {corr:.2f})", flush=True)
    lag_all = float(np.median(lags)) if a.lag == 'auto' else float(a.lag); print(f"label lag applied to all runs: {lag_all:.2f} s (per-run estimates median {np.median(lags):.2f}, range {min(lags):.1f}-{max(lags):.1f})")
    for ri, rd in enumerate(runs):
        rd['lag_applied'] = lag_all; s = Session(rd['session'] if Path(rd['session']).exists() else qa.loc[ri, 'session_dir'], load_status=False, load_extra=False); fx = s.fix; tf = fx['t_s'].values; v = fx['speed'].values
        good = (fx['acc_h'].values <= 10.0) & ((fx['speed_acc'].values <= 1.0) if 'speed_acc' in fx else True)
        vv = np.where(good, v, np.nan)
        for r in rates:
            grid = per_rate[r]['t'][ri]; tq = grid + lag_all                                   # truth at t = Doppler speed reported lag s later
            lab = np.interp(tq, tf, np.nan_to_num(vv, nan=-1.0)); lab[lab < 0] = np.nan
            lab[(tq < tf[0]) | (tq > tf[-1])] = np.nan
            ph = per_rate[r]['phase'][ri]; lab[(ph == 0) | (ph == 2)] = 0.0                     # stands: speed 0 by protocol
            per_rate[r]['v'].append(lab.astype(np.float32))
    out = Path('data/speed_model'); out.mkdir(exist_ok=True)
    for r in rates:
        d = per_rate[r]; np.savez_compressed(out / f'{a.tag}_{r}hz.npz', imu=np.vstack(d['imu']), t=np.concatenate(d['t']), run_id=np.concatenate(d['run_id']), v=np.concatenate(d['v']), phase=np.concatenate(d['phase']), runs=np.array(runs, dtype=object), rate=r, lag=lag_all)
        print(f"wrote {out / f'{a.tag}_{r}hz.npz'}: {sum(len(x) for x in d['t'])} samples, {len(runs)} runs")

if __name__ == '__main__':
    main()
