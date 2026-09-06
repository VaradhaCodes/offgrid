"""Evaluation protocol (handoff: 'the harness decides'). Runs, cuts, metrics, splits shared by every engine step.

Usage (as a library):
    from evaluate import kept_runs, Run, CUTS, heading_metrics, position_metrics, loro_splits, grouped_folds
Runs: data/qa/<tag>.csv rows with verdict != FAIL. Run objects load data/processed/<session>/track_100hz.csv (anti-aliased
100 Hz phone-frame IMU + GNSS interpolation) and align.json (R_pb, stand bias), and expose bike-frame IMU.
Cuts (GNSS withheld from t_cut to the end of the session): c10/c30/c60 = motion start + 10/30/60 s; turn = inside the
sharpest turn that starts at least 10 s after motion start (cut at 25 % of the turn's duration, |yaw rate| > half its peak).
Windows scored: outage = [t_cut, ride end] (bike still moving), after-stop = [t_cut, min(ride end + 20 s, session end)].
Heading metrics are against GNSS bearing at fixes with v > 1.5 m/s, GNSS latency 0.5 s (measured in step 2, median).
"""
import sys, math, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))

GNSS_LAG = 0.5
CUTS = ('c10', 'c30', 'c60', 'turn')

def kept_runs(qa_csv='data/qa/route1.csv', sessions_root='data/route1/sessions'):
    df = pd.read_csv(qa_csv)
    df = df[df['verdict'] != 'FAIL'].copy(); df['flags_str'] = df['flags_str'].fillna('')
    df['session_dir'] = [str(Path(sessions_root) / s) for s in df['session']]
    return df.reset_index(drop=True)

def kept_runs_tags(tags):
    """'route1' or 'route1+route2' -> kept runs of every listed route concatenated, with a 'tag' column (joint sets)."""
    dfs = []
    for tag in tags.split('+'):
        d = kept_runs(f'data/qa/{tag}.csv', f'data/{tag}/sessions'); d['tag'] = tag; dfs.append(d)
    return pd.concat(dfs, ignore_index=True)

def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi

class Run:
    def __init__(self, session_name, sessions_root='data/route1/sessions', processed='data/processed'):
        self.name = session_name; p = Path(processed) / session_name
        tr = pd.read_csv(p / 'track_100hz.csv'); self.al = json.load(open(p / 'align.json')); fx = pd.read_csv(p / 'gnss_fixes.csv')
        self.run = int(self.al['run']); self.dir = self.al['dir']
        self.t = tr['t_s'].values; self.dt = float(np.median(np.diff(self.t)))
        R = np.array(self.al['R_pb']); self.R_pb = R
        self.acc = (R @ tr[['ax', 'ay', 'az']].values.T).T                # bike frame, m/s^2
        self.gyr = (R @ tr[['gx', 'gy', 'gz']].values.T).T                # bike frame, rad/s, bias NOT removed
        self.bias_b = R @ np.array(self.al['bias_rad_s'])                 # robust stand bias in the bike frame
        self.g_mag = float(self.al['g_mag'])
        st = tr['state'].values
        self.ride = (float(self.t[st == 'RIDE'].min()), float(self.t[st == 'RIDE'].max()))
        self.t_end = float(self.t[-1])
        # GNSS (raw fixes) in ENU metres from the start anchor, bearing -> ENU yaw
        self.tf = fx['t_s'].values; self.fx = fx['x_m'].values; self.fy = fx['y_m'].values; self.fv = fx['speed'].values
        br = fx['bearing'].values.astype(float); self.f_yaw = np.where(np.isfinite(br), np.pi / 2 - np.radians(br), np.nan)
        self.f_acc = fx['acc_h'].values; self.f_sats = fx['n_sats_used'].values
        # course from consecutive fix positions (backward difference over the last fix interval, centred at t - dt/2, i.e. lag 0.5 s at 1 Hz)
        dtf = np.diff(self.tf, prepend=np.nan); dx = np.diff(self.fx, prepend=np.nan); dy = np.diff(self.fy, prepend=np.nan)
        ok = (dtf > 0.5) & (dtf < 1.6) & (np.hypot(dx, dy) / np.where(dtf > 0, dtf, 1) > 1.5)
        self.f_course = np.where(ok, np.arctan2(dy, dx), np.nan)
        raw = Path(sessions_root) / session_name / 'gnss_fix.csv'
        if raw.exists():
            rf = pd.read_csv(raw).drop_duplicates('t_ns').sort_values('t_ns'); self.f_bacc = rf['bearing_acc'].values.astype(float) if len(rf) == len(fx) else np.full(len(fx), np.nan)
        else: self.f_bacc = np.full(len(fx), np.nan)
        inr = (self.tf >= self.ride[0]) & (self.tf <= self.ride[1]); mv = np.where(inr & (self.fv > 1.0))[0]
        self.t_m0 = float(self.tf[mv[0]]) if len(mv) else self.ride[0]; self.t_m1 = float(self.tf[mv[-1]]) if len(mv) else self.ride[1]
        # interpolated truth on the 100 Hz grid (PCHIP between fixes, from decode_session)
        self.gx = tr['x_m'].values; self.gy = tr['y_m'].values; self.gv = tr['speed_mps'].values
        self.cuts = self._cuts()
    def _cuts(self):
        c = {'c10': self.t_m0 + 10.0, 'c30': self.t_m0 + 30.0, 'c60': self.t_m0 + 60.0}
        n = max(1, int(round(2.0 / self.dt))); wz = np.convolve(np.abs(self.gyr[:, 2] - self.bias_b[2]), np.ones(n) / n, mode='same')
        m = (self.t >= self.t_m0 + 10.0) & (self.t <= self.t_m1 - 5.0)
        if m.any():
            k = np.argmax(np.where(m, wz, 0)); pk = wz[k]; i0 = k
            while i0 > 0 and wz[i0 - 1] > 0.5 * pk: i0 -= 1
            i1 = k
            while i1 < len(wz) - 1 and wz[i1 + 1] > 0.5 * pk: i1 += 1
            c['turn'] = float(self.t[i0] + 0.25 * (self.t[i1] - self.t[i0])); self.turn_peak_dps = math.degrees(pk); self.turn_span = (float(self.t[i0]), float(self.t[i1]))
        for k in list(c):
            if c[k] > self.t_m1 - 10.0: del c[k]                          # need >= 10 s of moving outage to score
        return c
    def windows(self, t_cut):
        return dict(outage=(t_cut, self.ride[1]), after_stop=(t_cut, min(self.ride[1] + 20.0, self.t_end)))

def heading_metrics(run, t, psi, t_cut, lag=GNSS_LAG, ref='course'):
    """psi: ENU heading (rad) on grid t. Error vs the GNSS reference at fixes with v > 1.5 inside the outage.
    ref='course': course from consecutive fix positions (primary; the receiver's reported bearing shows 3-6 deg offsets for
    tens of seconds after sharp turns); ref='bearing': the receiver's reported bearing. Both lag the IMU by ~0.5 s."""
    w = run.windows(t_cut)['outage']; y = run.f_course if ref == 'course' else run.f_yaw
    m = (run.tf >= w[0]) & (run.tf <= w[1]) & (run.fv > 1.5) & np.isfinite(y)
    if m.sum() < 5: return dict(n=int(m.sum()))
    e = np.degrees(wrap(np.interp(run.tf[m] - lag, t, np.unwrap(psi)) - np.unwrap(y[m])))
    e = np.degrees(wrap(np.radians(e)))
    tt = run.tf[m]; first = tt <= tt[0] + 5.0; last = tt >= tt[-1] - 5.0
    return dict(n=int(m.sum()), mean_deg=float(e.mean()), rms_deg=float(np.sqrt(np.mean(e ** 2))), max_abs_deg=float(np.abs(e).max()),
                drift_deg=float(e[last].mean() - e[first].mean()), start_err_deg=float(e[first].mean()), end_err_deg=float(e[last].mean()), outage_s=float(w[1] - w[0]))

def position_metrics(run, t, x, y, t_cut):
    """x, y: estimated ENU position on grid t. Scores the outage and the after-stop window; drift % of outage distance."""
    out = {}
    for lab, w in run.windows(t_cut).items():
        m = (t >= w[0]) & (t <= w[1]); e = np.hypot(np.interp(t[m], run.t, run.gx) - x[m], np.interp(t[m], run.t, run.gy) - y[m])
        if lab == 'outage':
            mg = (run.t >= w[0]) & (run.t <= w[1]); dist = float(np.sum(np.hypot(np.diff(run.gx[mg]), np.diff(run.gy[mg]))))
            out.update(outage_m=dist, outage_s=float(w[1] - w[0]), end_m=float(e[-1]), drift_pct=100.0 * float(e[-1]) / max(dist, 1e-6), rmse_m=float(np.sqrt(np.mean(e ** 2))), max_m=float(e.max()))
        else: out.update(after_stop_m=float(e[-1]), after_stop_s=float(w[1] - run.ride[1]))
    return out

def summarize(df, col, thr=None, lower_is_better=True):
    v = df[col].dropna(); s = dict(median=float(v.median()), worst=float(v.max() if lower_is_better else v.min()), n=int(len(v)))
    if thr is not None: s['n_under'] = int((v.abs() < thr).sum()) if lower_is_better else int((v > thr).sum())
    return s

def loro_splits(runs):
    for i in range(len(runs)): yield [j for j in range(len(runs)) if j != i], [i]

def grouped_folds(runs, k=5, group_col='run', tag='route1'):
    """Grouped k-fold by round-trip pair: pair = the AB run and the BA run that followed it, read from data/<tag>/manifest.csv
    (pair column). Runs may carry a 'tag' column (joint sets): groups are (tag, pair), sorted by tag then pair number, so the
    route-1 folds are unchanged and a joint fold holds pairs of every route."""
    tags = list(runs['tag'].values) if 'tag' in runs else [tag] * len(runs); pairs = {}
    for tg in sorted(set(tags)):
        mf = pd.read_csv(f'data/{tg}/manifest.csv')
        for r in mf.itertuples(): pairs[(tg, int(r.run))] = (tg, int(r.pair) if pd.notna(r.pair) else 1000 + int(r.run))
    g = [pairs.get((tg, int(r)), (tg, 1000 + int(r))) for tg, r in zip(tags, runs[group_col])]; ug = sorted(set(g))
    for f in range(k):
        test_groups = set(ug[f::k]); te = [i for i in range(len(g)) if g[i] in test_groups]; tr = [i for i in range(len(g)) if g[i] not in test_groups]
        yield tr, te
