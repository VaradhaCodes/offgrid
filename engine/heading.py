"""Heading and gyro bias (step 3). Runtime maths in plain numpy/math; evaluation over the kept runs at every cut.

Usage: .venv/bin/python engine/heading.py [--tag route1] [--plot]
Writes data/qa/heading_<tag>.csv (run x cut x variant) and prints the distributions.

Attitude: quaternion q (bike -> world ENU), initialised level (R_pb levels the bike; yaw from the first GNSS bearing),
propagated with (omega_b - b) at the IMU rate; accelerometer tilt correction (Mahony-style proportional term, time
constant TAU_TILT) gated to quasi-steady riding so turns do not pull 'up' toward the leaned specific force.
Bias: b = stand estimate (3-D, robust); the z component is a Kalman state [psi, b_z] refined by GNSS bearing while GNSS is
healthy (v > 1.5 m/s, not withheld): measurement z = bearing_enu at t_fix, modelled as h = psi - I_tau + tau*b_z where
I_tau is the raw gyro-z integral over the last tau = 0.5 s (GNSS latency), H = [1, tau]; sigma^2 = (sig_v/v)^2 +
(sig_tau*wz)^2 + max(bearing_acc, SIG_B0)^2. A KF heading correction rotates q about world z. After the cut: propagation only.
Variants scored: static = stand mean bias, no refinement (baseline_dr); robust = robust stand bias, no refinement (loro_cv);
kf = robust init + GNSS refinement (engine); kf2d = same bias filter but 2-D yaw integration of bike z (no attitude).
"""
import sys, math, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from evaluate import kept_runs, Run, CUTS, heading_metrics, wrap, summarize

TAU = 0.5; SIG_V = 0.3; SIG_TAU = 0.2; SIG_B0 = math.radians(2.0); TAU_TILT = 10.0; W_STRAIGHT = 0.10; T_AFTER_TURN = 1.5
V_BIAS = 2.0; B_CLAMP = math.radians(0.3); B_CLAMP_MOVED = math.radians(1.5)     # bias refinement: fixes faster than V_BIAS only; |b - b_stand| <= B_CLAMP (a gyro bias does not move more within a session)
Q_B = math.radians(0.002) ** 2; Q_PSI = math.radians(0.1) ** 2; N_REJECT = 5; P_B_QUIET = math.radians(0.2) ** 2; P_B_MOVED = math.radians(0.3) ** 2

def qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return (w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2, w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2)
def qnorm(q):
    n = math.sqrt(sum(c * c for c in q)); return tuple(c / n for c in q)
def q_from_rotvec(v):
    a = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if a < 1e-12: return (1.0, 0.0, 0.0, 0.0)
    s = math.sin(a / 2) / a; return (math.cos(a / 2), v[0]*s, v[1]*s, v[2]*s)
def q_yaw(q):
    w, x, y, z = q; return math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
def q_up_body(q):
    """World +z expressed in the body frame = third row of R(q)^T... = R^T e_z."""
    w, x, y, z = q; return (2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y))

class HeadingFilter:
    def __init__(self, bias_b, g_mag, p_b0=P_B_QUIET, mode3d=True, refine=True, refine_bias=True, b_clamp=None):
        self.b = [float(bias_b[0]), float(bias_b[1]), float(bias_b[2])]; self.b0 = float(bias_b[2]); self.g = g_mag; self.mode3d = mode3d; self.refine = refine; self.refine_bias = refine_bias
        self.b_clamp = B_CLAMP if b_clamp is None else b_clamp
        self.t_turn = -1e9
        self.q = (1.0, 0.0, 0.0, 0.0); self.psi = 0.0; self.P = np.array([[math.radians(30.0) ** 2, 0.0], [0.0, p_b0]]); self.init = False
        self.hist_t = []; self.hist_I = []; self.I = 0.0; self.a_lp = None; self.w_lp = None; self.t_prev = None; self.n_meas = 0
    def step(self, t, a_b, w_b):
        if self.t_prev is None: self.t_prev = t; self.a_lp = np.array(a_b, float); self.w_lp = np.array(w_b, float); return
        dt = t - self.t_prev; self.t_prev = t
        k = min(1.0, dt / 0.5); self.a_lp += k * (np.asarray(a_b) - self.a_lp); self.w_lp += k * (np.asarray(w_b) - self.w_lp)
        wz_raw = float(w_b[2]); self.I += wz_raw * dt; self.hist_t.append(t); self.hist_I.append(self.I)
        if abs(self.w_lp[2] - self.b[2]) > W_STRAIGHT: self.t_turn = t                 # last time the bike was turning
        if len(self.hist_t) > 400: self.hist_t = self.hist_t[-400:]; self.hist_I = self.hist_I[-400:]
        w = (w_b[0] - self.b[0], w_b[1] - self.b[1], w_b[2] - self.b[2])
        if self.mode3d:
            self.q = qnorm(qmul(self.q, q_from_rotvec((w[0]*dt, w[1]*dt, w[2]*dt))))
            # gated accelerometer tilt correction: rotate q so that body 'up' moves toward the low-passed specific force
            if getattr(self, 'tilt', True) and np.linalg.norm(self.w_lp) < 0.15 and abs(np.linalg.norm(self.a_lp) - self.g) < 1.0:
                u_meas = self.a_lp / np.linalg.norm(self.a_lp); u_pred = np.array(q_up_body(self.q))
                e = np.cross(u_meas, u_pred)                       # body-frame small rotation +e moves u_pred toward u_meas
                self.q = qnorm(qmul(self.q, q_from_rotvec(tuple(e * (dt / TAU_TILT)))))
            self.psi = q_yaw(self.q)
        else:
            self.psi += w[2] * dt
        p00, p01, p11 = self.P[0, 0], self.P[0, 1], self.P[1, 1]
        self.P[0, 0] = p00 - 2 * dt * p01 + dt * dt * p11 + Q_PSI * dt; self.P[0, 1] = p01 - dt * p11; self.P[1, 0] = self.P[0, 1]; self.P[1, 1] = p11 + Q_B * dt
    def _rotate_yaw(self, dpsi):
        if self.mode3d: self.q = qnorm(qmul(q_from_rotvec((0.0, 0.0, dpsi)), self.q)); self.psi = q_yaw(self.q)
        else: self.psi += dpsi
    def gnss_bearing(self, t_fix, yaw_enu, v, wz, bearing_acc_rad=np.nan):
        if not np.isfinite(yaw_enu) or v <= 1.5 or self.t_prev is None: return
        if not self.init:
            self._rotate_yaw(wrap(yaw_enu - self.psi)); self.init = True; self.P = np.diag([math.radians(10.0) ** 2, self.P[1, 1]]); return   # alignment: reset psi variance AND the cross term
        if not self.refine: return
        if t_fix - self.t_turn < T_AFTER_TURN: return                              # straight segments only: the receiver's course lags in turns
        I_tau = self.I - float(np.interp(t_fix - TAU, self.hist_t, self.hist_I)) if len(self.hist_t) > 2 else 0.0
        h = self.psi - I_tau + TAU * self.b[2]; nu = float(wrap(yaw_enu - h))
        s0 = max(bearing_acc_rad, SIG_B0) if np.isfinite(bearing_acc_rad) else SIG_B0
        r = (SIG_V / v) ** 2 + (SIG_TAU * wz) ** 2 + s0 ** 2
        H = np.array([1.0, TAU]); S = float(H @ self.P @ H) + r
        if S <= 0: self.P = np.diag([max(self.P[0, 0], 1e-8), max(self.P[1, 1], 1e-10)]); S = float(H @ self.P @ H) + r
        K = self.P @ H / S
        if abs(nu) > 5 * math.sqrt(S):                                     # gate, with a consecutive-rejection reset (R3 §6)
            self.n_rej = getattr(self, 'n_rej', 0) + 1
            if self.n_rej >= N_REJECT: self._rotate_yaw(nu); self.P[0, 0] = math.radians(10.0) ** 2; self.P[0, 1] = self.P[1, 0] = 0.0; self.n_rej = 0; self.n_reset = getattr(self, 'n_reset', 0) + 1
            return
        self.n_rej = 0
        if not self.refine_bias or v < V_BIAS: K[1] = 0.0
        self._rotate_yaw(float(K[0] * nu)); self.b[2] = float(min(self.b0 + self.b_clamp, max(self.b0 - self.b_clamp, self.b[2] + K[1] * nu)))
        IKH = np.eye(2) - np.outer(K, H); self.P = IKH @ self.P @ IKH.T + np.outer(K, K) * r      # Joseph form
        self.P = 0.5 * (self.P + self.P.T); self.n_meas += 1
    def snapshot(self):
        import copy; return copy.deepcopy(self.__dict__)
    def restore(self, snap):
        import copy; self.__dict__.update(copy.deepcopy(snap))

VARIANTS = {  # name: (mode3d, refine psi, refine bias, measurement source, tilt correction)
    'static':   dict(mode3d=True, refine=False, refine_bias=False, src='bearing', tilt=True),
    'robust':   dict(mode3d=True, refine=False, refine_bias=False, src='bearing', tilt=True),
    'kfpsi':    dict(mode3d=True, refine=True, refine_bias=False, src='bearing', tilt=True),
    'kf':       dict(mode3d=True, refine=True, refine_bias=True, src='bearing', tilt=True),
    'kfpsic':   dict(mode3d=True, refine=True, refine_bias=False, src='course', tilt=True),
    'kfc':      dict(mode3d=True, refine=True, refine_bias=True, src='course', tilt=True),
    'kfpsic2d': dict(mode3d=False, refine=True, refine_bias=False, src='course', tilt=True),
    'kfpsic_notilt': dict(mode3d=True, refine=True, refine_bias=False, src='course', tilt=False),
    'kfct':     dict(mode3d=True, refine=True, refine_bias=True, src='course', tilt=True, tight=True),   # bias prior matched to the measured stand accuracy (0.05 / 0.1 deg/s)
    'kfc_loose': dict(mode3d=True, refine=True, refine_bias=True, src='course', tilt=True, bias_src='start', loose=True),   # causal worst case: start-stand mean bias only (no end stand), prior 2 deg/s, clamp 3 deg/s
}
P_B_LOOSE = math.radians(2.0) ** 2; B_CLAMP_LOOSE = math.radians(3.0)
P_B_TIGHT = math.radians(0.05) ** 2; P_B_TIGHT_MOVED = math.radians(0.1) ** 2
ENGINE_HEADING = 'kfpsic'   # harness choice over 30 runs of both routes at the 30 s cut (5 Sep 2026): psi refined from the position course, robust stand bias held (no bias state)

def run_variant(run, variant, t_cuts):
    """Returns dict cut -> psi array on run.t (GNSS withheld from the cut)."""
    from session import Session
    V = VARIANTS[variant]
    if variant == 'static' or V.get('bias_src') == 'start':                 # start stand only, plain mean (what a causal engine has at RIDE_START)
        sess = Session(Path('data/route1/sessions') / run.name if (Path('data/route1/sessions') / run.name).exists() else Path('data/route2/sessions') / run.name, load_status=False, load_extra=False)
        m = (sess.gyr['t_s'].values > 1.0) & (sess.gyr['t_s'].values < sess.calib[1] - 1.0); bias = run.R_pb @ sess.gyr.loc[m, ['gx', 'gy', 'gz']].values.mean(0)
    else: bias = run.bias_b
    quiet = ('STAND_MOTION_START' not in run.flags) if hasattr(run, 'flags') else True
    p_b0 = (P_B_TIGHT if quiet else P_B_TIGHT_MOVED) if V.get('tight') else (P_B_QUIET if quiet else P_B_MOVED)
    clamp = B_CLAMP if quiet else B_CLAMP_MOVED
    if V.get('loose'): p_b0 = P_B_LOOSE; clamp = B_CLAMP_LOOSE
    hf = HeadingFilter(bias, run.g_mag, p_b0=p_b0, mode3d=V['mode3d'], refine=V['refine'], refine_bias=V['refine_bias'], b_clamp=clamp); hf.tilt = V['tilt']
    src = run.f_course if V['src'] == 'course' else run.f_yaw
    t = run.t; n = len(t); out = {c: np.zeros(n) for c in t_cuts}; snaps = {}; fi = 0; order = sorted(t_cuts.items(), key=lambda kv: kv[1])
    psi_full = np.zeros(n)
    for k in range(n):
        while fi < len(run.tf) and run.tf[fi] <= t[k]:
            hf.gnss_bearing(run.tf[fi], src[fi], run.fv[fi], hf.w_lp[2] if hf.w_lp is not None else 0.0, math.radians(run.f_bacc[fi]) if (hasattr(run, 'f_bacc') and V['src'] == 'bearing') else np.nan); fi += 1
        hf.step(t[k], run.acc[k], run.gyr[k]); psi_full[k] = hf.psi
        for c, tc in order:
            if c not in snaps and t[k] >= tc: snaps[c] = (k, hf.snapshot())
    bias_at_cut = {}
    for c, (k0, snap) in snaps.items():
        h2 = HeadingFilter(bias, run.g_mag); h2.restore(snap); out[c][:k0 + 1] = psi_full[:k0 + 1]; bias_at_cut[c] = h2.b[2]
        for k in range(k0 + 1, n): h2.step(t[k], run.acc[k], run.gyr[k]); out[c][k] = h2.psi
    return out, psi_full, bias_at_cut

def oracle_bias(run):
    """Batch diagnostic (not an engine variant): slope of (raw gyro-z heading - GNSS bearing) vs time over the whole ride at v > 1.5,
    i.e. the constant bias that best explains the ride; also the robust stand bias for comparison. Both in deg/s."""
    I = np.concatenate([[0.0], np.cumsum(0.5 * (run.gyr[1:, 2] + run.gyr[:-1, 2]) * np.diff(run.t))])
    m = (run.tf >= run.ride[0]) & (run.tf <= run.ride[1]) & (run.fv > 1.5) & np.isfinite(run.f_course)
    r = np.unwrap(np.interp(run.tf[m] - 0.5, run.t, I) - np.unwrap(run.f_course[m])); tt = run.tf[m]
    A = np.column_stack([tt - tt[0], np.ones(len(tt))]); sol, *_ = np.linalg.lstsq(A, r, rcond=None)
    return math.degrees(sol[0]), math.degrees(run.bias_b[2])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tag', default='route1'); ap.add_argument('--plot', action='store_true'); ap.add_argument('--variants', default='robust,kfpsi,kfpsic,kfc,kfpsic2d,kfpsic_notilt')
    a = ap.parse_args(); qa = kept_runs(f'data/qa/{a.tag}.csv', f'data/{a.tag}/sessions'); rows = []; series = {}
    for _, r in qa.iterrows():
        run = Run(r['session'], f'data/{a.tag}/sessions'); run.flags = r['flags_str']
        b_or, b_st = oracle_bias(run)
        for variant in a.variants.split(','):
            out, psi_full, b_cut = run_variant(run, variant, run.cuts)
            for c, tc in run.cuts.items():
                m = heading_metrics(run, run.t, out[c], tc, ref='course'); mb = heading_metrics(run, run.t, out[c], tc, ref='bearing')
                rows.append(dict(run=run.run, dir=run.dir, variant=variant, cut=c, t_cut=round(tc - run.t_m0, 1), bias_cut_dps=round(math.degrees(b_cut[c]), 3), bias_oracle_dps=round(b_or, 3), bias_stand_dps=round(b_st, 3),
                                 **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()}, **{'brg_' + k: (round(v, 2) if isinstance(v, float) else v) for k, v in mb.items() if k in ('mean_deg', 'rms_deg', 'drift_deg')}))
                if variant == 'kfpsic' and c == 'c30': series[run.run] = (run, out[c], tc)
        bk = next((x['bias_cut_dps'] for x in rows if x['run'] == run.run and x['variant'] == 'kf' and x['cut'] == 'c30'), float('nan'))
        print(f"run{run.run} {run.dir}: cuts {{{', '.join(f'{c}: +{tc - run.t_m0:.0f}s' for c, tc in run.cuts.items())}}}  " + '  '.join(f"{v}: {next((x['mean_deg'] for x in rows if x['run'] == run.run and x['variant'] == v and x['cut'] == 'c30'), float('nan')):+.1f}" for v in a.variants.split(',')) + f' (mean err @c30) | bias dps: stand {b_st:+.3f} oracle {b_or:+.3f} kf@c30 {bk:+.3f}', flush=True)
    df = pd.DataFrame(rows); fn = Path(f'data/qa/heading_{a.tag}.csv')
    if fn.exists():                                                        # merge: replace the rows of the variants just run, keep every other variant
        old = pd.read_csv(fn); df = pd.concat([old[~old.variant.isin(df.variant.unique())], df], ignore_index=True)
    df.to_csv(fn, index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
    print('\n=== heading error during the outage vs the POSITION COURSE, |mean| over fixes with v > 1.5 m/s (deg): median / worst / runs under 3 deg; brg_* = vs the reported bearing ===')
    summ = []
    for c in CUTS:
        for v in a.variants.split(','):
            d = df[(df.cut == c) & (df.variant == v)].copy()
            if d.empty: continue
            d['abs_mean'] = d['mean_deg'].abs(); d['abs_drift'] = d['drift_deg'].abs()
            s1 = summarize(d, 'abs_mean', 3.0); s2 = summarize(d, 'rms_deg'); s3 = summarize(d, 'abs_drift', 3.0); s4 = summarize(d, 'max_abs_deg')
            d['brg_abs_mean'] = d['brg_mean_deg'].abs(); s5 = summarize(d, 'brg_abs_mean', 3.0)
            summ.append(dict(cut=c, variant=v, n=s1['n'], mean_med=round(s1['median'], 2), mean_worst=round(s1['worst'], 2), n_under3=s1['n_under'], rms_med=round(s2['median'], 2), rms_worst=round(s2['worst'], 2), drift_med=round(s3['median'], 2), drift_worst=round(s3['worst'], 2), drift_under3=s3['n_under'], max_med=round(s4['median'], 2), max_worst=round(s4['worst'], 2), worst_run=int(d.loc[d['abs_mean'].idxmax(), 'run']), brg_mean_med=round(s5['median'], 2), brg_mean_worst=round(s5['worst'], 2), brg_under3=s5['n_under']))
    sd = pd.DataFrame(summ); print(sd.to_string(index=False)); sd.to_csv(f'data/qa/heading_{a.tag}_summary.csv', index=False)
    if a.plot:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(16, 5))
        for rn, (run, psi, tc) in series.items():
            m = (run.tf >= tc) & (run.fv > 1.5) & np.isfinite(run.f_course)
            e = np.degrees(wrap(np.interp(run.tf[m] - 0.5, run.t, np.unwrap(psi)) - np.unwrap(run.f_course[m])))
            ax[0].plot(run.tf[m] - tc, e, lw=1, label=f'run{rn}')
        ax[0].axhline(3, color='r', ls='--'); ax[0].axhline(-3, color='r', ls='--'); ax[0].set_xlabel('s since cut (c30)'); ax[0].set_ylabel('heading error vs GNSS bearing [deg]'); ax[0].set_title('kfpsic variant vs position course, cut 30 s after motion start, all kept runs'); ax[0].legend(fontsize=6, ncol=4); ax[0].set_ylim(-15, 15); ax[0].grid(alpha=.3)
        d = df[df.cut == 'c30']; x = np.arange(len(a.variants.split(',')))
        for i, v in enumerate(a.variants.split(',')):
            vals = d[d.variant == v]['mean_deg'].abs().values; ax[1].scatter(np.full(len(vals), i) + np.random.uniform(-0.15, 0.15, len(vals)), vals, s=14)
        ax[1].set_xticks(x); ax[1].set_xticklabels(a.variants.split(',')); ax[1].axhline(3, color='r', ls='--'); ax[1].set_ylabel('|mean heading error| during outage [deg]'); ax[1].set_title('per run, cut c30'); ax[1].grid(alpha=.3)
        fig.tight_layout(); fig.savefig(f'data/qa/heading_{a.tag}.png', dpi=110); print('plot', f'data/qa/heading_{a.tag}.png')

if __name__ == '__main__':
    main()
