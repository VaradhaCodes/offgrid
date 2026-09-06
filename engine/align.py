"""Phone -> bike alignment (step 2). Runtime maths in plain numpy; offline validation over sessions.

Usage: .venv/bin/python engine/align.py data/route1/sessions --tag route1 [--plot]
Writes data/processed/<session>/align.json per run and data/qa/align_<tag>.csv; prints the validation table.

Frames: phone = Android (x right, y up/top, z out of the screen); bike = x forward, y left, z up (right-handed).
R_pb maps phone vectors to bike vectors: v_b = R_pb @ v_p.
  R1  levelling: rotates the measured gravity direction (accelerometer at rest points UP) onto +z. Two sources are
      evaluated: the start stand (bike leaning at rest) and ride-time gravity = mean of the 0.5 s low-passed accelerometer
      over quasi-steady riding (|w_lp| < 0.15 rad/s, | |a_lp| - g | < 1.0 m/s^2, v > 1.5 m/s, |GNSS accel| < 0.3 m/s^2). The runtime starts from the stand and
      switches to the ride-time estimate (slow EMA) as soon as it exists.
  psi forward axis in the levelled frame, three estimators (all reported, cross-run spread selects the engine's):
      init  direction of the MEAN horizontal specific force over the first speed-up window (accelerometer; +-15 deg:
            gravity leaking through pitch/roll motion is as large as the 0.5 m/s^2 forward acceleration on a bicycle,
            and PCA is wrong outright because 1 Hz pedalling sway dominates).
      sway  pedalling sway is a roll about the bike's longitudinal axis: principal axis of the band-passed
            (0.25 s minus 2 s trailing means) horizontal gyro over the moving ride; sign from init.
      lean  a bicycle leans into turns, phi = -atan(v*wz/g): psi maximising corr(roll rate(psi), d phi/dt) over
            turns; gyro + GNSS speed only, sign resolved physically.
      fit   (diagnostic) velocity-integral least squares on straight segments, I - I0 = dv*e + dt*c.
  R_pb = Rz(-psi) @ R1.
Moved-phone monitor: 10 s blocks of gated ride-time gravity; angle to the reference > MOVE_DEG for two consecutive
blocks => re-level from the blocks after the move, keep psi.
Validation per run: gyro yaw rate vs GNSS bearing rate (slope, corr, RMS, best lag) for both levellings; forward
specific force vs GNSS acceleration (sign at the start, corr, slope); roll rate vs d/dt(-atan(v*wz/g)) inside turns.
"""
import sys, math, json, argparse
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from session import Session, find_sessions, robust_gyro_bias

MOVE_DEG = 3.0; BLOCK_S = 10.0; LP_S = 0.5; GATE_W = 0.15; GATE_A = 1.0; STRAIGHT_W = 0.10; MIN_SEG_S = 4.0

# ------------------------------------------------------------------ runtime maths (port line by line)
def skew(k): return np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
def rot_from_gravity(g):
    """Rotation taking the unit vector g/|g| onto +z (Rodrigues about their cross product)."""
    u = g / np.linalg.norm(g); z = np.array([0.0, 0.0, 1.0]); k = np.cross(u, z); s = np.linalg.norm(k); c = float(np.dot(u, z))
    if s < 1e-9: return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    K = skew(k / s); th = math.atan2(s, c)
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)
def rot_z(psi):
    c, s = math.cos(psi), math.sin(psi); return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
def euler_from_R(R):
    """pitch/roll/yaw (deg) for reporting, R = Rz(yaw) Ry(pitch) Rx(roll)."""
    yaw = math.atan2(R[1, 0], R[0, 0]); pitch = math.asin(max(-1.0, min(1.0, -R[2, 0]))); roll = math.atan2(R[2, 1], R[2, 2])
    return math.degrees(pitch), math.degrees(roll), math.degrees(yaw)
def trailing_mean(x, n):
    """Causal moving average over the last n samples (1-D or (N,k))."""
    x = np.asarray(x, dtype=float); c = np.cumsum(np.concatenate([np.zeros((1,) + x.shape[1:]), x], axis=0), axis=0)
    idx = np.arange(len(x)); lo = np.maximum(idx - n + 1, 0); cnt = (idx - lo + 1).astype(float)
    return (c[idx + 1] - c[lo]) / cnt[(...,) + (None,) * (x.ndim - 1)]
def angle_deg(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b))))))

def fit_forward_axis(segments):
    """segments: list of arrays (n_i, 4) with columns [dv, dt, Ix, Iy] relative to the segment's first fix.
    Solves I = dv*e + dt*c for e, c (2-vectors) by least squares. Returns psi, |e|, c, rms residual, n."""
    X = np.vstack([s[:, :2] for s in segments]); Y = np.vstack([s[:, 2:] for s in segments])
    if len(X) < 6: return np.nan, np.nan, np.zeros(2), np.nan, len(X)
    sol, *_ = np.linalg.lstsq(X, Y, rcond=None); e = sol[0]; c = sol[1]; res = Y - X @ sol
    return math.atan2(e[1], e[0]), float(np.linalg.norm(e)), c, float(np.sqrt(np.mean(res ** 2))), len(X)

class Aligner:
    """R1 (levelling) from a gravity vector; psi (forward yaw); R_pb = Rz(-psi) @ R1."""
    def __init__(self, g_ref):
        self.set_gravity(g_ref); self.psi = 0.0
    def set_gravity(self, g_ref):
        self.g_ref = np.array(g_ref, float); self.g_mag = float(np.linalg.norm(self.g_ref)); self.R1 = rot_from_gravity(self.g_ref)
    @property
    def R(self): return rot_z(-self.psi) @ self.R1
    def level(self, a_p): return (self.R1 @ np.asarray(a_p, float).T).T
    def specific_force(self, a_p):
        f = self.level(a_p); f[..., 2] -= self.g_mag; return f
    def psi_from_mean_force(self, f_h):
        m = f_h.mean(0); self.psi = math.atan2(m[1], m[0]); return float(np.linalg.norm(m))

# ------------------------------------------------------------------ offline procedure over one session
def yaw_rate_check(t, wz, tf, br, v, inride, lags=np.arange(0.0, 2.01, 0.1)):
    """Gyro yaw rate (bike z) vs GNSS bearing rate over consecutive fixes with v > 1.5 m/s, best lag by correlation."""
    head = np.concatenate([[0.0], np.cumsum(0.5 * (wz[1:] + wz[:-1]) * np.diff(t))])
    good = inride & (v > 1.5) & np.isfinite(br); idx = np.where(good)[0]
    pairs = [(idx[i - 1], idx[i]) for i in range(1, len(idx)) if idx[i] == idx[i - 1] + 1 and tf[idx[i]] - tf[idx[i - 1]] < 1.6]
    if len(pairs) < 10: return None
    db = np.array([-(((br[j] - br[i]) + 180) % 360 - 180) for i, j in pairs]); dtp = np.array([tf[j] - tf[i] for i, j in pairs]); rate_g = db / dtp
    best = None
    for lag in lags:
        hg = np.interp(np.array([tf[j] - lag for i, j in pairs]), t, head) - np.interp(np.array([tf[i] - lag for i, j in pairs]), t, head); rate_i = np.degrees(hg) / dtp
        c = float(np.corrcoef(rate_i, rate_g)[0, 1]) if np.std(rate_i) > 0 and np.std(rate_g) > 0 else 0.0
        if best is None or c > best['corr']:
            slope = float(np.sum(rate_i * rate_g) / max(np.sum(rate_i ** 2), 1e-9)); res = rate_g - slope * rate_i
            best = dict(lag=float(lag), corr=c, slope=slope, rms=float(np.sqrt(np.mean(res ** 2))), n=len(pairs), rate_max=float(np.abs(rate_g).max()))
    return best

def align_session(s):
    nat = s.imu_native(); t = nat['t_s'].values; A = nat[['ax', 'ay', 'az']].values; Gy = nat[['gx', 'gy', 'gz']].values
    fs = 1.0 / np.median(np.diff(t)); n_lp = max(1, int(round(LP_S * fs))); dt_s = np.diff(t, prepend=t[0])
    ms = Session.in_window(t, s.calib, 1.0); g0 = A[ms].mean(0); g_mag = float(np.linalg.norm(g0))
    Gs, ts = [], []
    for w in (s.calib, s.stop):
        if np.isfinite(w[0]) and np.isfinite(w[1]): m = Session.in_window(t, w, 1.0); Gs.append(Gy[m]); ts.append(t[m])
    bias = robust_gyro_bias(np.concatenate(ts), np.vstack(Gs))[0]; W_p = Gy - bias
    A_lp = trailing_mean(A, n_lp); W_lp = trailing_mean(W_p, n_lp)
    # ---- GNSS
    fx = s.fix; tf = fx['t_s'].values; v = fx['speed'].values; br = fx['bearing'].values.astype(float)
    ride = s.ride; inride = (tf >= ride[0]) & (tf <= ride[1]); a_g = np.gradient(v, tf)
    mv = np.where(inride & (v > 1.0))[0]
    if len(mv) < 5: return dict(session=s.name, run=s.run_no, dir=s.direction, error='no motion')
    t_m0 = tf[mv[0]]
    # ---- ride-time gravity (levelling-independent gate on low-passed norms) and the moved-phone monitor
    v_imu = np.interp(t - 0.5, tf, v)
    a_imu = np.interp(t - 0.5, tf, trailing_mean(a_g, 3))
    gate = Session.in_window(t, ride) & (np.linalg.norm(W_lp, axis=1) < GATE_W) & (np.abs(np.linalg.norm(A_lp, axis=1) - g_mag) < GATE_A) & (v_imu > 1.5) & (np.abs(a_imu) < 0.3)
    blocks = []; tb = ride[0]; consecutive = 0; moved_at = None; max_block = 0.0; g_run = None
    while tb + BLOCK_S <= ride[1]:
        m = gate & (t >= tb) & (t < tb + BLOCK_S)
        if m.sum() > 0.2 * BLOCK_S * fs:
            gb = A_lp[m].mean(0)
            if g_run is None: g_run = gb.copy()
            ang = angle_deg(gb, g_run); blocks.append((tb - ride[0], ang, gb)); max_block = max(max_block, ang)
            consecutive = consecutive + 1 if ang > MOVE_DEG else 0
            if consecutive >= 2:
                if moved_at is None: moved_at = tb - ride[0]
                g_run = gb.copy(); consecutive = 0                                   # re-level on the new attitude
            else: g_run = 0.8 * g_run + 0.2 * gb                                      # slow EMA of ride-time gravity
        tb += BLOCK_S
    g_ride = A_lp[gate].mean(0) if gate.sum() > fs else g0.copy()
    if moved_at is not None: g_ride = np.mean([b[2] for b in blocks if b[0] >= moved_at], axis=0)
    out = dict(session=s.name, run=s.run_no, dir=s.direction, rider=s.rider, g_rest=g0.round(4).tolist(), g_ride=g_ride.round(4).tolist(), g_mag=round(g_mag, 4),
               bias_rad_s=bias.round(6).tolist(), gate_frac=round(float(gate.sum() / max(Session.in_window(t, ride).sum(), 1)), 3),
               tilt_stand_vs_ride_deg=round(angle_deg(g0, g_ride), 2), max_block_angle_deg=round(max_block, 2), moved_at_s=moved_at, blocks=[(round(b[0], 1), round(b[1], 2)) for b in blocks])
    # ---- per levelling: psi initial (mean force over the speed-up), psi refined (velocity-integral fit), checks
    results = {}
    for lab, gref in (('stand', g0), ('ride', g_ride)):
        al = Aligner(gref); f = al.specific_force(A); w = al.level(W_p); f_lp = trailing_mean(f, n_lp); w_lp = trailing_mean(w, n_lp)
        Wm = (t >= t_m0 - 2.0) & (t <= t_m0 + 6.0) & (np.interp(t, tf, a_g) > 0.15)
        if Wm.sum() < 0.5 * fs: Wm = (t >= t_m0 - 2.0) & (t <= t_m0 + 6.0)
        mean_force = al.psi_from_mean_force(f_lp[Wm][:, :2]); psi_init = al.psi
        vi0 = np.interp(t - 0.5, tf, v); moving = Session.in_window(t, ride) & (vi0 > 1.5)
        # sway: band-passed horizontal gyro (0.25 s minus 2 s trailing means), principal axis, sign from init
        w_bp = trailing_mean(w[:, :2], max(1, int(round(0.25 * fs)))) - trailing_mean(w[:, :2], int(round(2.0 * fs)))
        Msw = w_bp[moving].T @ w_bp[moving]; ang_sw = 0.5 * math.atan2(2 * Msw[0, 1], Msw[0, 0] - Msw[1, 1]); e_sw = np.array([math.cos(ang_sw), math.sin(ang_sw)])
        l1 = float(e_sw @ Msw @ e_sw); sway_ratio = l1 / max(float(np.trace(Msw)) - l1, 1e-12)
        if math.cos(ang_sw - psi_init) < 0: ang_sw += math.pi
        psi_sway = math.atan2(math.sin(ang_sw), math.cos(ang_sw))
        # lean: scan psi, maximise corr(roll rate(psi), d/dt(-atan(v wz/g))) over turns, 2 s smoothing
        n2 = int(round(2.0 * fs)); phi0 = -np.arctan(vi0 * w_lp[:, 2] / g_mag); dphi0 = trailing_mean(np.gradient(phi0, t), n2)
        turn0 = moving & (np.abs(w_lp[:, 2]) > 0.10); wxl = trailing_mean(w[:, 0], n2)[turn0]; wyl = trailing_mean(w[:, 1], n2)[turn0]; dph = dphi0[turn0]
        psi_lean, lean_best = psi_init, -2.0
        if turn0.sum() > fs:
            dph_c = dph - dph.mean(); sd_d = float(np.std(dph))
            for pdeg in np.arange(-180, 180, 1.0):
                pr = math.radians(pdeg); rr0 = math.cos(pr) * wxl + math.sin(pr) * wyl
                c = float(np.mean((rr0 - rr0.mean()) * dph_c) / (max(np.std(rr0), 1e-9) * max(sd_d, 1e-9)))
                if c > lean_best: lean_best, psi_lean = c, pr
        # straight segments of consecutive 1 s fix intervals: |wz| small, GNSS healthy, inside the ride
        I = np.cumsum(f[:, :2] * dt_s[:, None], axis=0)                      # integral of horizontal specific force (levelled)
        fi = np.where(inride)[0]; seg = []; cur = []
        for k in range(1, len(fi)):
            i0, i1 = fi[k - 1], fi[k]; m = (t > tf[i0]) & (t <= tf[i1])
            straight = m.sum() > 5 and abs(float(w[m, 2].mean())) < STRAIGHT_W and tf[i1] - tf[i0] < 1.6
            if straight: cur.append(i1) if cur else cur.extend([i0, i1])
            else:
                if len(cur) >= 2 and tf[cur[-1]] - tf[cur[0]] >= MIN_SEG_S: seg.append(cur)
                cur = []
        if len(cur) >= 2 and tf[cur[-1]] - tf[cur[0]] >= MIN_SEG_S: seg.append(cur)
        best = None
        for lag in np.arange(0.0, 1.51, 0.1):
            S = []
            for sg in seg:
                tt = tf[sg] - lag; Ii = np.stack([np.interp(tt, t, I[:, 0]), np.interp(tt, t, I[:, 1])], 1)
                S.append(np.column_stack([v[sg] - v[sg[0]], tf[sg] - tf[sg[0]], Ii - Ii[0]])[1:])
            if not S: break
            psi_r, scale, c, rms, n = fit_forward_axis(S)
            if np.isfinite(rms) and (best is None or rms < best['rms']): best = dict(lag=float(lag), psi=psi_r, scale=scale, c=c, rms=rms, n=n, nseg=len(seg))
        if best is None: best = dict(lag=np.nan, psi=psi_init, scale=np.nan, c=np.zeros(2), rms=np.nan, n=0, nseg=0)
        psi_fit = best['psi']; al.psi = psi_sway; R = al.R                     # engine choice: sway axis (2.1 deg cross-run spread), sign from the start force
        ab = (R @ A.T).T; wb = (R @ W_p.T).T; fb = ab.copy(); fb[:, 2] -= g_mag; fb_lp = trailing_mean(fb, n_lp); wb_lp = trailing_mean(wb, n_lp)
        yr = yaw_rate_check(t, wb[:, 2], tf, br, v, inride)
        lag = yr['lag'] if yr else 0.5
        ends = tf[inride]; fwd_int, ag_int = [], []
        for i in range(1, len(ends)):
            m = (t > ends[i - 1] - lag) & (t <= ends[i] - lag)
            if m.sum() > 5: fwd_int.append(fb[m, 0].mean()); ag_int.append(float(np.interp(ends[i], tf, a_g)))
        fwd_int = np.array(fwd_int); ag_int = np.array(ag_int)
        corr_f = float(np.corrcoef(fwd_int, ag_int)[0, 1]) if len(fwd_int) > 5 else np.nan
        slope_f = float(np.sum(fwd_int * ag_int) / max(np.sum(ag_int ** 2), 1e-9)) if len(fwd_int) > 5 else np.nan
        vi = np.interp(t - lag, tf, v); phi = -np.arctan(vi * wb_lp[:, 2] / g_mag); n2 = int(round(2.0 * fs))
        dphi = trailing_mean(np.gradient(phi, t), n2); rr = trailing_mean(wb[:, 0], n2)
        turn = Session.in_window(t, ride) & (np.abs(wb_lp[:, 2]) > 0.10) & (vi > 1.5)
        corr_lean = float(np.corrcoef(rr[turn], dphi[turn])[0, 1]) if turn.sum() > fs else np.nan
        straight_m = Session.in_window(t, ride) & (np.abs(wb_lp[:, 2]) < 0.1) & (vi > 1.5)
        pitch_p, roll_p, yaw_p = euler_from_R(R)
        results[lab] = dict(psi_init_deg=round(math.degrees(psi_init), 2), mean_force_mps2=round(mean_force, 3), psi_sway_deg=round(math.degrees(psi_sway), 2), sway_ratio=round(sway_ratio, 1),
                            psi_lean_deg=round(math.degrees(psi_lean), 2), lean_best_corr=round(lean_best, 3), psi_fit_deg=round(math.degrees(psi_fit), 2), psi_deg=round(math.degrees(psi_sway), 2),
                            fit_scale=round(best['scale'], 3), fit_rms_mps=round(best['rms'], 3),
                            fit_lag_s=best['lag'], fit_n=best['n'], fit_nseg=best['nseg'], fit_leak_mps2=[round(float(x), 3) for x in best['c']],
                            yaw_lag_s=yr['lag'] if yr else np.nan, yaw_corr=round(yr['corr'], 4) if yr else np.nan, yaw_slope=round(yr['slope'], 4) if yr else np.nan, yaw_rms_dps=round(yr['rms'], 2) if yr else np.nan,
                            fwd_start_mps2=round(float(fb_lp[Wm, 0].mean()), 3), lat_start_mps2=round(float(fb_lp[Wm, 1].mean()), 3), fwd_corr=round(corr_f, 3), fwd_slope=round(slope_f, 3), lean_corr=round(corr_lean, 3),
                            mean_fx_straight=round(float(fb[straight_m, 0].mean()), 3) if straight_m.any() else np.nan, mean_fy_straight=round(float(fb[straight_m, 1].mean()), 3) if straight_m.any() else np.nan,
                            euler_pitch_roll_yaw_deg=[round(pitch_p, 2), round(roll_p, 2), round(yaw_p, 2)], R_pb=R.round(6).tolist())
    out['stand'] = results['stand']; out['ride'] = results['ride']
    out['R_pb'] = results['ride']['R_pb']; out['psi_deg'] = results['ride']['psi_deg']              # engine choice: ride-time levelling + refined psi
    return out

COLS = [('run', ''), ('dir', ''), ('tilt_stand_vs_ride_deg', ''), ('max_block_angle_deg', ''), ('moved_at_s', ''), ('gate_frac', ''),
        ('psi_init_deg', 'ride'), ('psi_sway_deg', 'ride'), ('sway_ratio', 'ride'), ('psi_lean_deg', 'ride'), ('lean_best_corr', 'ride'), ('psi_fit_deg', 'ride'), ('fit_scale', 'ride'), ('fit_rms_mps', 'ride'), ('fit_n', 'ride'),
        ('yaw_slope', 'stand'), ('yaw_rms_dps', 'stand'), ('yaw_slope', 'ride'), ('yaw_corr', 'ride'), ('yaw_rms_dps', 'ride'), ('yaw_lag_s', 'ride'),
        ('fwd_start_mps2', 'ride'), ('lat_start_mps2', 'ride'), ('fwd_corr', 'ride'), ('fwd_slope', 'ride'), ('lean_corr', 'ride'), ('mean_fx_straight', 'ride'), ('mean_fy_straight', 'ride')]

def flatten(r):
    row = {}
    for k, grp in COLS:
        row[(f'{grp}_{k}' if grp else k)] = (r.get(grp, {}).get(k, np.nan) if grp else r.get(k, np.nan))
    row['error'] = r.get('error', '')
    return row

def main():
    import pandas as pd
    ap = argparse.ArgumentParser(); ap.add_argument('paths', nargs='+'); ap.add_argument('--tag', default='align'); ap.add_argument('--plot', action='store_true')
    a = ap.parse_args(); rows = []
    for d in find_sessions(a.paths):
        s = Session(d, load_status=False, load_extra=False); r = align_session(s); rows.append(flatten(r))
        out = Path('data/processed') / s.name; out.mkdir(parents=True, exist_ok=True); json.dump(r, open(out / 'align.json', 'w'), indent=1)
        rr = r.get('ride', {}); print(f"{s.name}: tilt stand-vs-ride {r.get('tilt_stand_vs_ride_deg')} moved {r.get('moved_at_s')} | psi init {rr.get('psi_init_deg')} sway {rr.get('psi_sway_deg')} (ratio {rr.get('sway_ratio')}) lean {rr.get('psi_lean_deg')} (corr {rr.get('lean_best_corr')}) fit {rr.get('psi_fit_deg')} | yaw slope {rr.get('yaw_slope')} rms {rr.get('yaw_rms_dps')} lag {rr.get('yaw_lag_s')} | fwd start {rr.get('fwd_start_mps2')} corr {rr.get('fwd_corr')}", flush=True)
    df = pd.DataFrame(rows); Path('data/qa').mkdir(exist_ok=True); df.to_csv(f'data/qa/align_{a.tag}.csv', index=False)
    pd.set_option('display.width', 320); pd.set_option('display.max_columns', 60); print(df.drop(columns=['error']).to_string(index=False))
    def circ_spread(deg):
        a = np.radians(np.asarray(deg, float)); a = a[np.isfinite(a)]; m = math.atan2(np.sin(a).mean(), np.cos(a).mean())
        d = np.degrees((a - m + np.pi) % (2 * np.pi) - np.pi); return math.degrees(m), float(np.sqrt(np.mean(d ** 2))), float(np.abs(d).max())
    ok = df.run != 8
    for c in ('ride_psi_init_deg', 'ride_psi_sway_deg', 'ride_psi_lean_deg', 'ride_psi_fit_deg'):
        m, rms, mx = circ_spread(df.loc[ok, c]); print(f"{c:22s} circular mean {m:7.1f} deg  rms spread {rms:5.1f} deg  max |dev| {mx:5.1f} deg  (runs excluding run8)")
    if a.plot:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 2, figsize=(15, 8)); x = df.run.astype(str)
        ax[0, 0].plot(x, df.ride_psi_lean_deg, 'bo', label='lean (gyro+GNSS speed)'); ax[0, 0].plot(x, df.ride_psi_sway_deg, 'gs', label='sway axis (gyro)'); ax[0, 0].plot(x, df.ride_psi_init_deg, 'r.', label='first speed-up mean force (accel)'); ax[0, 0].plot(x, df.ride_psi_fit_deg, 'kx', label='velocity-integral fit (accel)'); ax[0, 0].set_ylim(-180, 180); ax[0, 0].set_title('forward-axis yaw psi in the levelled frame [deg]'); ax[0, 0].legend(fontsize=8)
        ax[0, 1].bar(x, df.ride_yaw_slope, label='ride-time levelling'); ax[0, 1].plot(x, df.stand_yaw_slope, 'r.', label='stand levelling'); ax[0, 1].axhline(1, color='k', ls='--'); ax[0, 1].set_ylim(0.85, 1.15); ax[0, 1].set_title('gyro-z vs GNSS bearing-rate slope (1 = aligned)'); ax[0, 1].legend(fontsize=8)
        ax[1, 0].bar(x, df.tilt_stand_vs_ride_deg); ax[1, 0].plot(x, df.max_block_angle_deg, 'r.'); ax[1, 0].axhline(MOVE_DEG, color='r', ls='--'); ax[1, 0].set_title('stand vs ride-time gravity angle [deg] (bars) and max 10 s block (dots)')
        ax[1, 1].bar(x, df.ride_fwd_corr); ax[1, 1].set_title('corr(forward specific force, GNSS acceleration), 1 s intervals')
        for r_ in ax.flat: r_.tick_params(axis='x', labelsize=7)
        fig.tight_layout(); fig.savefig(f'data/qa/align_{a.tag}.png', dpi=110); print('plot', f'data/qa/align_{a.tag}.png')

if __name__ == '__main__':
    main()
