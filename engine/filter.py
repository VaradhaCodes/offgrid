"""Fusion filter (steps 5 + 6): one engine, always running; GNSS is a measurement that may stop.

Usage: .venv/bin/python engine/filter.py --pred gbr_r100_w256 [--tag route1] [--variants plain,gen_k1,gen,cor,cor_lm]
Writes data/qa/filter_<pred>.csv (run x cut x variant) and a summary; the 10 Hz tracks for the replay/plots go to data/qa/tracks/<pred>/.

Inputs per 10 Hz tick: model speed v_m and sigma_m (raw, from data/speed_model/pred/<pred>/<session>.csv), the physical
stop flag, the heading psi from the step-3 filter (variant kfc), and GNSS fixes (t, x, y, v, acc_h) while healthy.
General mode state x = [px, py, v, k]:  p += v [cos psi, sin psi] dt; v random walk (SIG_A); k Gauss-Markov (SIG_K0, T_K),
  measurements: model speed z = v_m, h = v / k (R = max(sigma_m, SIG_M_FLOOR)^2; applied to the CURRENT v: a delayed-state
  form makes a delay loop because the model is the only driver of v in the outage, measured 2x worse); GNSS position (R = max(acc_h, 3 m)^2,
  latency LAG_POS via stored states); GNSS speed (R = SIG_VG^2, latency LAG_V); ZUPT z = 0 on v (R = 0.05^2) when the stop
  flag is set; NHC is structural (velocity along psi). k observes only while GNSS speed is healthy; Q_k frozen in the outage.
Corridor mode state x = [s, v, k]: s += dir * v dt on the polyline (dir = travel direction learned from the GNSS arc-length
  progression while healthy); GNSS enters as arc length only (position projected, lateral offset held from the last healthy
  fix); optional turn-landmark reset: heading change > LM_DEG within LM_WIN s snaps s to the nearest bend of matching sign
  within LM_RANGE m (R = LM_R^2). Output position = point(s) + d_hold * normal(s).
Outage handling (rule 1): the simulated flag (t >= t_cut) or the real-outage detector withholds GNSS; on return the GNSS
  sigma is inflated x REC_INFL for REC_S seconds; the displayed track is never rewritten.
"""
import sys, math, json, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from evaluate import kept_runs, Run, position_metrics, summarize
from heading import run_variant, ENGINE_HEADING
from corridor import load_corridor

SIG_A = 1.0; SIG_K0 = 0.05; T_K = 600.0; SIG_M_FLOOR = 0.15; SIG_VG = 0.3; SIG_ZUPT = 0.05; LAG_POS = 0.5; LAG_V = 0.2   # LAG_V: measured Doppler-speed latency vs the position-derived speed (0.2 s on both routes, 5 Sep 2026; was 0.7 from the mis-signed label-lag estimate)
REC_INFL = 4.0; REC_S = 3.0; K_VMIN = 2.0; K_AMAX = 0.3; N_REJECT = 5; LM_DEG = 40.0; LM_WIN = 3.0; LM_RANGE = 40.0; LM_R = 8.0; GATE_SIG = 5.0

class Filter:
    def __init__(self, mode='general', corridor=None, k_est=True, zupt=True, landmarks=False, x0=(0.0, 0.0), s0=0.0, d0=0.0):
        self.mode = mode; self.cor = corridor; self.k_est = k_est; self.zupt = zupt; self.landmarks = landmarks
        if mode == 'general': self.x = np.array([x0[0], x0[1], 0.0, 1.0]); self.P = np.diag([9.0, 9.0, 1.0, SIG_K0 ** 2])
        else: self.x = np.array([s0, 0.0, 1.0]); self.P = np.diag([9.0, 1.0, SIG_K0 ** 2]); self.d_hold = d0; self.dir = 0.0; self.s_hist = []
        self.hist = []; self.t = None; self.psi = 0.0; self.t_return = -1e9; self.gnss_ok_prev = True; self.psi_hist = []; self.k_open = False; self.v_g_hist = []; self.d_target = d0 if mode != 'general' else 0.0
        self.bends = corridor.bends() if (corridor is not None and landmarks) else []; self.t_last_lm = -1e9
    # ---- propagation at every tick
    def predict(self, t, psi):
        if self.t is None: self.t = t; self.psi = psi; return
        dt = t - self.t; self.t = t; self.psi = psi; x, P = self.x, self.P
        if self.mode == 'general':
            c, s = math.cos(psi), math.sin(psi); F = np.eye(4); F[0, 2] = c * dt; F[1, 2] = s * dt
            x[0] += x[2] * c * dt; x[1] += x[2] * s * dt
            Q = np.diag([0.0, 0.0, (SIG_A * dt) ** 2, 0.0]); P[:] = F @ P @ F.T + Q
            self.hist.append((t, x[0], x[1], x[2]))
        else:
            F = np.eye(3); F[0, 1] = self.dir * dt; x[0] += self.dir * x[1] * dt
            Q = np.diag([0.0, (SIG_A * dt) ** 2, 0.0]); P[:] = F @ P @ F.T + Q
            self.hist.append((t, x[0], 0.0, x[1]))
        if self.k_est and self.gnss_ok_prev: P[-1, -1] += 2 * SIG_K0 ** 2 / T_K * dt        # Gauss-Markov drive, frozen in the outage
        if len(self.hist) > 40: self.hist = self.hist[-40:]
        self.psi_hist.append((t, psi)); self.psi_hist = [h for h in self.psi_hist if t - h[0] <= LM_WIN + 0.2]
    def _update(self, nu, H, R):
        S = float(H @ self.P @ H) + R
        if abs(nu) > GATE_SIG * math.sqrt(S): return False
        K = self.P @ H / S; self.x += K * nu; I = np.eye(len(self.x)); self.P = (I - np.outer(K, H)) @ self.P @ (I - np.outer(K, H)).T + np.outer(K, K) * R; self.P = 0.5 * (self.P + self.P.T); return True
    # ---- model speed + stop rule (every tick)
    def update_model(self, v_m, sig_m, still):
        iv = 2 if self.mode == 'general' else 1; k = self.x[-1]
        if not self.k_est or not self.k_open: 
            Pk = self.P[-1, -1]; self.P[-1, :] = 0.0; self.P[:, -1] = 0.0; self.P[-1, -1] = Pk               # k decoupled outside its observation gate
        if still and self.zupt:
            H = np.zeros(len(self.x)); H[iv] = 1.0; self._update(0.0 - self.x[iv], H, SIG_ZUPT ** 2); self.x[iv] = max(0.0, self.x[iv]); return
        H = np.zeros(len(self.x)); H[iv] = 1.0 / k; H[-1] = -self.x[iv] / k ** 2
        if not self.k_est or not self.k_open: H[-1] = 0.0
        self._update(v_m - self.x[iv] / k, H, max(sig_m, SIG_M_FLOOR) ** 2); self.x[iv] = max(0.0, self.x[iv]); self.x[-1] = min(1.5, max(0.5, self.x[-1]))
    def _delayed(self, t_meas):
        """State (px/s, py, v) at t_meas from the stored history (linear interpolation)."""
        if len(self.hist) < 2: return None
        ts = np.array([h[0] for h in self.hist]); a = np.array([h[1] for h in self.hist]); b = np.array([h[2] for h in self.hist]); v = np.array([h[3] for h in self.hist])
        if t_meas < ts[0]: return None
        return float(np.interp(t_meas, ts, a)), float(np.interp(t_meas, ts, b)), float(np.interp(t_meas, ts, v))
    # ---- GNSS (only called while healthy; the caller applies the outage flag)
    def update_gnss(self, t_fix, x, y, v, acc_h, cor_dir_hint=0.0):
        infl = REC_INFL if (self.t - self.t_return) < REC_S else 1.0
        if not self.gnss_ok_prev: self.t_return = self.t; infl = REC_INFL; self.v_g_hist = []
        self.gnss_ok_prev = True; Rp = (max(acc_h, 3.0) * infl) ** 2; Rv = (SIG_VG * infl) ** 2
        self.v_g_hist.append((t_fix, v)); self.v_g_hist = self.v_g_hist[-3:]
        steady = len(self.v_g_hist) == 3 and abs(self.v_g_hist[-1][1] - self.v_g_hist[0][1]) / max(self.v_g_hist[-1][0] - self.v_g_hist[0][0], 0.5) < K_AMAX
        self.k_open = bool(steady and v > K_VMIN and infl == 1.0)
        if self.mode == 'general':
            d = self._delayed(t_fix - LAG_POS)
            if d is not None:
                acc_ok = 0
                for i, (z, est) in enumerate(((x, d[0]), (y, d[1]))):
                    H = np.zeros(4); H[i] = 1.0; acc_ok += int(self._update(z - est, H, Rp))
                if acc_ok < 2:
                    self.n_rej = getattr(self, 'n_rej', 0) + 1
                    if self.n_rej >= N_REJECT:                                   # R3 §6: reset to GNSS after N consecutive rejections
                        self.x[0] = x + (self.x[0] - d[0]); self.x[1] = y + (self.x[1] - d[1]); self.P[0, 0] = self.P[1, 1] = Rp; self.P[0, 1] = self.P[1, 0] = 0.0; self.n_rej = 0; self.n_reset = getattr(self, 'n_reset', 0) + 1
                else: self.n_rej = 0
            d = self._delayed(t_fix - LAG_V)
            if d is not None and v > 0.3: H = np.zeros(4); H[2] = 1.0; self._update(v - d[2], H, Rv)
        else:
            s_g, d_g, _ = self.cor.project(x, y); s_g = float(s_g[0]); self.d_target = float(d_g[0])
            self.d_hold += (self.d_target - self.d_hold) * (1.0 if infl == 1.0 else 0.3)
            self.s_hist.append((t_fix, s_g)); self.s_hist = self.s_hist[-8:]
            if len(self.s_hist) >= 4 and v > 1.0:
                ds = self.s_hist[-1][1] - self.s_hist[0][1]
                if abs(ds) > 3.0: self.dir = 1.0 if ds > 0 else -1.0
            d = self._delayed(t_fix - LAG_POS)
            if d is not None: H = np.zeros(3); H[0] = 1.0; self._update(s_g - d[0], H, Rp)
            d = self._delayed(t_fix - LAG_V)
            if d is not None and v > 0.3: H = np.zeros(3); H[1] = 1.0; self._update(v - d[2], H, Rv)
    def gnss_lost(self): self.gnss_ok_prev = False; self.k_open = False
    # ---- turn landmark (corridor mode, outage or not)
    def landmark(self):
        if not self.landmarks or len(self.psi_hist) < 5 or self.t - self.t_last_lm < 15.0: return
        dpsi = math.degrees(self.psi_hist[-1][1] - self.psi_hist[0][1])
        if abs(dpsi) < LM_DEG: return
        sign = math.copysign(1.0, dpsi * self.dir) if self.dir != 0 else math.copysign(1.0, dpsi)
        cands = [b for b in self.bends if math.copysign(1.0, b[1]) == sign and abs(b[0] - self.x[0]) < LM_RANGE]
        if not cands: return
        b = min(cands, key=lambda b: abs(b[0] - self.x[0])); H = np.array([1.0, 0.0, 0.0]); self._update(b[0] - self.x[0], H, LM_R ** 2); self.t_last_lm = self.t
    def position(self):
        if self.mode == 'general': return float(self.x[0]), float(self.x[1])
        p = self.cor.point(self.x[0])[0]; tg = self.cor.tangent(self.x[0])[0]; n = np.array([-tg[1], tg[0]])
        q = p + self.d_hold * n; return float(q[0]), float(q[1])

def run_filter(run, pred, psi100, t_cut, variant, corridor, t_restore=None):
    """Replay one run: GNSS withheld for t in [t_cut, t_restore). Returns 10 Hz (t, x, y, v, k)."""
    tp = pred['t_s'].values; vm = pred['v_raw'].values; sg = pred['sigma'].values; still = pred['still'].values.astype(bool)
    ticks = tp[(tp >= run.ride[0] - 2.0)]; psi = np.interp(ticks, run.t, np.unwrap(psi100))
    mode = 'corridor' if variant.startswith('cor') else 'general'
    x0 = (float(run.gx[0]), float(run.gy[0]))
    if mode == 'corridor':
        s0, d0, _ = corridor.project(x0[0], x0[1]); f = Filter(mode, corridor, k_est=(variant != 'cor_k1'), zupt=True, landmarks=(variant == 'cor_lm'), s0=float(s0[0]), d0=float(d0[0]))
    else: f = Filter(mode, k_est=(variant != 'gen_k1'), zupt=True, x0=x0)
    fi = 0; out = np.zeros((len(ticks), 5)); i_p = 0
    for k, t in enumerate(ticks):
        f.predict(t, psi[k])
        while i_p < len(tp) and tp[i_p] <= t: i_p += 1
        j = max(0, i_p - 1); f.update_model(float(vm[j]), float(sg[j]), bool(still[j]))
        while fi < len(run.tf) and run.tf[fi] <= t:
            withheld = (run.tf[fi] >= t_cut) and (t_restore is None or run.tf[fi] < t_restore)
            if withheld or run.f_acc[fi] > 30.0: f.gnss_lost()
            else: f.update_gnss(run.tf[fi], run.fx[fi], run.fy[fi], run.fv[fi], run.f_acc[fi])
            fi += 1
        if mode == 'corridor': f.landmark()
        px, py = f.position(); out[k] = (t, px, py, f.x[2] if mode == 'general' else f.x[1], f.x[-1])
    return out

def plain_track(run, pred, psi100, t_cut):
    """The step-4 replay: smoothed model speed x heading integrated from the GNSS position at the cut (no filter)."""
    tp = pred['t_s'].values; vs = pred['v_model'].values; v10 = np.interp(run.t, tp, vs); v10[run.t < tp[0]] = 0.0
    k0 = int(np.searchsorted(run.t, t_cut)); x = run.gx.copy(); y = run.gy.copy(); dt = np.diff(run.t, prepend=run.t[0])
    for i in range(k0, len(run.t)): x[i] = x[i - 1] + math.cos(psi100[i]) * v10[i] * dt[i]; y[i] = y[i - 1] + math.sin(psi100[i]) * v10[i] * dt[i]
    return np.column_stack([run.t, x, y, v10, np.ones(len(run.t))])

HEADING_VARIANT = ENGINE_HEADING

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pred', required=True); ap.add_argument('--heading', default=ENGINE_HEADING); ap.add_argument('--tag', default='route1'); ap.add_argument('--variants', default='plain,gen_k1,gen,cor_k1,cor,cor_lm'); ap.add_argument('--save_tracks', type=int, default=1)
    a = ap.parse_args(); globals()['HEADING_VARIANT'] = a.heading; qa = kept_runs(f'data/qa/{a.tag}.csv', f'data/{a.tag}/sessions'); rows = []; variants = a.variants.split(',')
    for _, r in qa.iterrows():
        run = Run(r['session'], f'data/{a.tag}/sessions'); run.flags = r['flags_str']; pred = pd.read_csv(f'data/speed_model/pred/{a.pred}/{r["session"]}.csv')
        sess = json.load(open(Path(f'data/{a.tag}/sessions') / r['session'] / 'session.json')); cor, _ = load_corridor(f'data/map/corridor_{a.tag}.geojson', sess['start_anchor']['lat'], sess['start_anchor']['lon'])
        scen = dict(run.cuts)
        if 'c30' in run.cuts and run.cuts['c30'] + 30.0 < run.t_m1 - 5.0: scen['c30r'] = run.cuts['c30']           # restore 30 s later: recovery scenario
        outs, _, _ = run_variant(run, HEADING_VARIANT, {c: tc for c, tc in scen.items()})
        for c, tc in scen.items():
            t_restore = tc + 30.0 if c == 'c30r' else None
            for v in variants:
                tr = plain_track(run, pred, outs[c], tc) if v == 'plain' else run_filter(run, pred, outs[c], tc, v, cor, t_restore)
                if c == 'c30r':
                    if v == 'plain': continue
                    m = (tr[:, 0] >= t_restore - 0.05) & (tr[:, 0] <= t_restore + REC_S + 0.5); e = np.hypot(np.interp(tr[m, 0], run.t, run.gx) - tr[m, 1], np.interp(tr[m, 0], run.t, run.gy) - tr[m, 2])
                    jump = float(np.max(np.hypot(np.diff(tr[m, 1]), np.diff(tr[m, 2])))) if m.sum() > 2 else np.nan
                    rows.append(dict(run=run.run, dir=run.dir, cut=c, variant=v, err_at_return_m=float(e[0]), err_3s_after_m=float(e[-1]), max_step_m=jump)); continue
                pm = position_metrics(run, tr[:, 0], tr[:, 1], tr[:, 2], tc); k_end = float(tr[-1, 4])
                rows.append(dict(run=run.run, dir=run.dir, cut=c, variant=v, **{k: round(val, 2) for k, val in pm.items()}, k_end=round(k_end, 3)))
                if a.save_tracks and c == 'c30':
                    d = Path('data/qa/tracks') / a.pred; d.mkdir(parents=True, exist_ok=True); pd.DataFrame(tr, columns=['t_s', 'x_m', 'y_m', 'v', 'k']).to_csv(d / f'{r["session"]}_{v}.csv', index=False, float_format='%.3f')
        print(f"run{run.run} {run.dir}: " + ' | '.join(f"{v} c30 {next((x['drift_pct'] for x in rows if x['run'] == run.run and x['cut'] == 'c30' and x['variant'] == v), float('nan')):.1f}%" for v in variants), flush=True)
    suffix = '' if a.tag == 'route1' else f'_{a.tag}'                                   # route-1 files keep their historical names
    df = pd.DataFrame(rows); df.to_csv(f'data/qa/filter_{a.pred}{suffix}.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30); summ = []
    for c in ('c10', 'c30', 'c60', 'turn'):
        for v in variants:
            d = df[(df.cut == c) & (df.variant == v)]
            if d.empty: continue
            summ.append(dict(cut=c, variant=v, n=len(d), drift_med=round(d.drift_pct.median(), 2), drift_worst=round(d.drift_pct.max(), 2), under10=int((d.drift_pct < 10).sum()), end_med=round(d.end_m.median(), 1), end_worst=round(d.end_m.max(), 1), rmse_med=round(d.rmse_m.median(), 1), max_med=round(d.max_m.median(), 1), after_stop_med=round(d.after_stop_m.median(), 1), after_stop_worst=round(d.after_stop_m.max(), 1), k_end_med=round(d.k_end.median(), 3), worst_run=int(d.loc[d.drift_pct.idxmax(), 'run'])))
    sd = pd.DataFrame(summ); print(sd.to_string(index=False)); sd.to_csv(f'data/qa/filter_{a.pred}{suffix}_summary.csv', index=False)
    rec = df[df.cut == 'c30r']
    if len(rec): print('\nrecovery (cut +30 s, GNSS back +60 s): ' + rec.groupby('variant')[['err_at_return_m', 'err_3s_after_m', 'max_step_m']].median().round(2).to_string())

if __name__ == '__main__':
    main()
