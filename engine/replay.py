"""Replay harness (step 8): any session + denial zone -> 10 Hz engine output, metrics, plot. Also the app's conformance test.

Usage:
  .venv/bin/python engine/replay.py --session data/route1/sessions/<name> --pred gbr_r100_w256 --outage 30,999 [--mode corridor|general] [--mm 1] [--plot]
  .venv/bin/python engine/replay.py --all --pred gbr_r100_w256 --mode general --mm 1          # evaluation over kept runs and cuts
Denial zone: --outage t0,t1 (seconds after motion start; GNSS withheld while t0 <= t < t1) or --polygon file.geojson (lon/lat ring;
withheld while inside). The real-outage detector of rule 1 applies as well (no fix > 1.5 s, accuracy > 30 m, sats < 4 with a
2-epoch debounce, C/N0 < 22 dB-Hz). Output CSV columns: t_s, x_m, y_m, lat, lon, v, heading_deg, mode, gnss_age_s, k, sigma_pos.
Engine loop: IMU at 100 Hz -> heading filter (kfc); every 0.1 s: model speed (from the prediction CSV for now, the exported model
later) -> fusion filter; every 0.5 s in general mode: map matcher, whose confident straight-edge bearing is fed back to the heading
filter (sigma MM_SIG_HEAD) and whose cross-track = 0 is fed to the filter as a delayed position pseudo-measurement (sigma MM_SIG_XT).
"""
import sys, math, json, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from evaluate import kept_runs, Run, position_metrics, wrap
from heading import HeadingFilter, P_B_QUIET, P_B_MOVED, B_CLAMP, B_CLAMP_MOVED, ENGINE_HEADING
from filter import Filter, REC_S
from corridor import load_corridor
from mapmatch import MapMatcher, LAG_S

MM_SIG_HEAD = math.radians(10.0); MM_SIG_XT = 3.0

def real_outage(run, i, prev_bad):
    """Rule-1 detector at fix i: gap > 1.5 s, accuracy > 30 m, sats < 4 (debounced over 2 epochs), C/N0 < 22 (not in the fixes table: skipped)."""
    gap = (run.tf[i] - run.tf[i - 1]) > 1.5 if i > 0 else False; acc = run.f_acc[i] > 30.0; sats = run.f_sats[i] < 4
    return gap or acc or (sats and prev_bad), sats

def in_polygon(x, y, poly):
    inside = False; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1: inside = not inside
    return inside

def replay(run, pred, mode='corridor', outage=(1e9, 1e9), polygon=None, mm=0, corridor=None, osm='data/map/snu_osm_highways_900m.json', k_est=False, feedback=True):
    from heading import VARIANTS, P_B_TIGHT, P_B_TIGHT_MOVED
    quiet = 'STAND_MOTION_START' not in getattr(run, 'flags', ''); V = VARIANTS[HEADING_VARIANT]
    p_b0 = (P_B_TIGHT if quiet else P_B_TIGHT_MOVED) if V.get('tight') else (P_B_QUIET if quiet else P_B_MOVED)
    hf = HeadingFilter(run.bias_b, run.g_mag, p_b0=p_b0, mode3d=V['mode3d'], refine=V['refine'], refine_bias=V['refine_bias'], b_clamp=(B_CLAMP if quiet else B_CLAMP_MOVED)); hf.tilt = V['tilt']
    tp = pred['t_s'].values; vm = pred['v_raw'].values; sg = pred['sigma'].values; still = pred['still'].values.astype(bool)
    x0 = (float(run.gx[0]), float(run.gy[0]))
    if mode == 'corridor':
        s0, d0, _ = corridor.project(x0[0], x0[1]); f = Filter('corridor', corridor, k_est=k_est, zupt=True, landmarks=False, s0=float(s0[0]), d0=float(d0[0]))
    else: f = Filter('general', k_est=k_est, zupt=True, x0=x0)
    keep = ('service', 'residential', 'track', 'pedestrian', 'unclassified', 'tertiary', 'secondary', 'primary') if mm == 2 else None   # mm=2: rideable ways only (no footway/path)
    matcher = MapMatcher(osm, run_lat0(run), run_lon0(run), keep_types=keep) if (mm and mode == 'general') else None
    rows = []; fi = 0; ip = 0; next_tick = run.t[0]; prev_bad = False; last_fix_t = -1e9; withheld_now = False; mm_res = None
    for k in range(len(run.t)):
        t = run.t[k]
        while fi < len(run.tf) and run.tf[fi] <= t:                   # GNSS fixes up to now
            tf = run.tf[fi]; sim = (outage[0] <= tf - run.t_m0 < outage[1]) or (polygon is not None and in_polygon(run.fx[fi], run.fy[fi], polygon))
            bad, prev_bad = real_outage(run, fi, prev_bad); withheld_now = sim or bad
            if not withheld_now: hf.gnss_bearing(tf, run.f_course[fi], run.fv[fi], hf.w_lp[2] if hf.w_lp is not None else 0.0)
            fi += 1; last_fix_t = tf; pending = (tf, fi - 1, withheld_now)
            rows_gnss = pending
            # the fusion filter consumes fixes at its own tick below
            if not hasattr(f, 'pending'): f.pending = []
            f.pending.append(pending)
        hf.step(t, run.acc[k], run.gyr[k])
        if t + 1e-9 >= next_tick:                                        # 10 Hz engine tick
            next_tick += 0.1; f.predict(t, hf.psi)
            while ip < len(tp) and tp[ip] <= t: ip += 1
            j = max(0, ip - 1); f.update_model(float(vm[j]), float(sg[j]), bool(still[j]))
            for (tf, i, wh) in getattr(f, 'pending', []):
                if wh: f.gnss_lost()
                else: f.update_gnss(tf, run.fx[i], run.fy[i], run.fv[i], run.f_acc[i])
            f.pending = []
            px, py = f.position()
            if matcher is not None:
                mm_res = matcher.step(t, px, py, hf.psi)
                if feedback and mm_res is not None and mm_res['confident']:
                    if mm_res['straight']:
                        nu = float(wrap(mm_res['bearing'] - hf.psi)); S = hf.P[0, 0] + MM_SIG_HEAD ** 2; K = hf.P[0, 0] / S
                        if abs(nu) < math.radians(45.0): hf._rotate_yaw(K * nu); hf.P[0, 0] *= (1 - K)
                    d = f._delayed(mm_res['t'])
                    if d is not None and withheld_now:
                        nx, ny = -mm_res['ty'], mm_res['tx']; xt = (d[0] - mm_res['x']) * nx + (d[1] - mm_res['y']) * ny      # cross-track of the delayed state
                        H = np.array([nx, ny, 0.0, 0.0]); f._update(0.0 - xt, H, MM_SIG_XT ** 2)
                    px, py = f.position()
            gnss_age = t - last_fix_t if not withheld_now else t - max([tf for (tf, i, wh) in [] ] + [-1e9])
            state = 'GNSS_INS' if not withheld_now else 'INERTIAL'
            if not withheld_now and (t - f.t_return) < REC_S: state = 'RECOVERING'
            rows.append((t, px, py, f.x[2] if mode == 'general' else f.x[1], math.degrees(hf.psi), state, f.x[-1], math.sqrt(max(f.P[0, 0], 0.0)), mm_res['seg'] if mm_res else -1, mm_res['conf'] if mm_res else np.nan))
    return pd.DataFrame(rows, columns=['t_s', 'x_m', 'y_m', 'v', 'heading_deg', 'mode', 'k', 'sigma_pos', 'mm_seg', 'mm_conf'])

def run_lat0(run): return json.load(open(Path('data/processed') / run.name / 'align.json')).get('lat0', None) or _anchor(run)[0]
def run_lon0(run): return _anchor(run)[1]
def _anchor(run):
    for root in ('data/route1/sessions', 'data/route2/sessions'):
        p = Path(root) / run.name / 'session.json'
        if p.exists(): a = json.load(open(p))['start_anchor']; return a['lat'], a['lon']
    raise FileNotFoundError(run.name)

HEADING_VARIANT = ENGINE_HEADING

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--session', default=''); ap.add_argument('--all', action='store_true'); ap.add_argument('--pred', required=True); ap.add_argument('--heading', default=ENGINE_HEADING); ap.add_argument('--tag', default='route1')
    ap.add_argument('--mode', default='corridor'); ap.add_argument('--mm', type=int, default=0); ap.add_argument('--feedback', type=int, default=1); ap.add_argument('--k', type=int, default=0); ap.add_argument('--outage', default='30,1e9'); ap.add_argument('--polygon', default=''); ap.add_argument('--plot', action='store_true'); ap.add_argument('--out', default='data/qa/replay')
    a = ap.parse_args(); globals()['HEADING_VARIANT'] = a.heading; qa = kept_runs(f'data/qa/{a.tag}.csv', f'data/{a.tag}/sessions'); Path(a.out).mkdir(parents=True, exist_ok=True)
    poly = None
    if a.polygon:
        g = json.load(open(a.polygon)); ring = g['features'][0]['geometry']['coordinates'][0] if g.get('type') == 'FeatureCollection' else g['geometry']['coordinates'][0]; poly = ring
    if a.all:
        rows = []
        for _, r in qa.iterrows():
            run = Run(r['session'], f'data/{a.tag}/sessions'); run.flags = r['flags_str']; pred = pd.read_csv(f'data/speed_model/pred/{a.pred}/{r["session"]}.csv')
            lat0, lon0 = _anchor(run); cor, _ = load_corridor(f'data/map/corridor_{a.tag}.geojson', lat0, lon0)
            if poly is not None: px_, py_ = [], []
            for c, tc in run.cuts.items():
                df = replay(run, pred, a.mode, (tc - run.t_m0, 1e9), None, int(a.mm), cor, k_est=bool(a.k), feedback=bool(a.feedback))
                pm = position_metrics(run, df.t_s.values, df.x_m.values, df.y_m.values, tc); rows.append(dict(run=run.run, dir=run.dir, cut=c, mode=a.mode, mm=a.mm, **{k: round(v, 2) for k, v in pm.items()}))
            print(f"run{run.run} {run.dir}: " + ' '.join(f"{x['cut']} {x['drift_pct']:.1f}%" for x in rows if x['run'] == run.run), flush=True)
        df = pd.DataFrame(rows); name = f"{a.pred}_{a.mode}_mm{a.mm}_fb{a.feedback}_k{a.k}"; df.to_csv(f'{a.out}/all_{name}.csv', index=False)
        for c in ('c10', 'c30', 'c60', 'turn'):
            d = df[df.cut == c]
            if len(d): print(f"{name} {c}: drift median {d.drift_pct.median():.2f} worst {d.drift_pct.max():.2f} under10 {(d.drift_pct < 10).sum()}/{len(d)} | end median {d.end_m.median():.1f} | after-stop median {d.after_stop_m.median():.1f}")
        return
    sess = Path(a.session).name; run = Run(sess, f'data/{a.tag}/sessions'); r = qa[qa.session == sess].iloc[0]; run.flags = r['flags_str']
    pred = pd.read_csv(f'data/speed_model/pred/{a.pred}/{sess}.csv'); lat0, lon0 = _anchor(run); cor, _ = load_corridor(f'data/map/corridor_{a.tag}.geojson', lat0, lon0)
    o = [float(x) for x in a.outage.split(',')]; df = replay(run, pred, a.mode, (o[0], o[1]), poly, int(a.mm), cor, k_est=bool(a.k), feedback=bool(a.feedback))
    mlat = 111320.0; mlon = 111320.0 * math.cos(math.radians(lat0)); df['lat'] = lat0 + df.y_m / mlat; df['lon'] = lon0 + df.x_m / mlon
    out = Path(a.out) / f"{sess}_{a.mode}_mm{a.mm}.csv"; df.to_csv(out, index=False, float_format='%.4f')
    t_cut = run.t_m0 + o[0]; pm = position_metrics(run, df.t_s.values, df.x_m.values, df.y_m.values, t_cut) if t_cut < run.t_m1 else {}
    print(json.dumps(dict(session=sess, mode=a.mode, mm=a.mm, outage=o, **{k: round(v, 2) for k, v in pm.items()}))); print('wrote', out)
    if a.plot:
        import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(15, 6)); ax[0].plot(run.gx, run.gy, 'k', lw=3, label='GNSS truth'); m = df['mode'] != 'GNSS_INS'
        ax[0].plot(df.x_m, df.y_m, 'C0', lw=1.5, label='engine'); ax[0].plot(df.x_m[m], df.y_m[m], 'C3', lw=1.5, label='engine (GNSS withheld)'); ax[0].set_aspect('equal'); ax[0].legend(); ax[0].grid(alpha=.3); ax[0].set_title(f'{sess}: {a.mode} mode, mm={a.mm}, outage {o}')
        e = np.hypot(np.interp(df.t_s, run.t, run.gx) - df.x_m, np.interp(df.t_s, run.t, run.gy) - df.y_m); ax[1].plot(df.t_s - run.t_m0, e); ax[1].set_xlabel('s since motion start'); ax[1].set_ylabel('position error [m]'); ax[1].grid(alpha=.3)
        for x in (o[0], min(o[1], run.t_end - run.t_m0)): ax[1].axvline(x, color='r', ls='--')
        fig.tight_layout(); fig.savefig(str(out).replace('.csv', '.png'), dpi=110); print('plot', str(out).replace('.csv', '.png'))

if __name__ == '__main__':
    main()
