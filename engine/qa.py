"""Data QA for raw IDR Logger sessions. Flags, never silent drops.

Usage:
  .venv/bin/python engine/qa.py data/route1/sessions --tag route1
  .venv/bin/python engine/qa.py data/route2/sessions/* --tag route2
Writes data/qa/<tag>.csv (one row per run, every metric), data/qa/<tag>_flags.md (compact table + flag legend), prints both.

Per run: IMU rates/gaps/dups (recomputed from t_ns, not trusted from session.json), GNSS rate/accuracy/sats/C/N0 and the
count of epochs that would trip the real-outage detector, mount pitch/roll from both stands vs the set median, rider/bike
motion during both stands (gyro rotation with a robust bias, quiet-chunk fraction, accel RMS, game-rotation-vector check),
gyro-bias consistency between the two stands, impacts and clipping during the ride, ride statistics (motion-start lag,
speeds, path, mid-ride stops), start/end anchors vs the A/B clusters of the set and vs the app's own anchors.
Verdict: PASS / WARN / FAIL; flags prefixed 'i:' are informational and do not change the verdict.
Downstream code reads the CSV; nothing is excluded here.
"""
import sys, math, argparse
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from session import Session, find_sessions, robust_gyro_bias, local_xy, geodist_m

# ---- thresholds (documented in docs/11_ENGINE_RESULTS.md)
T = dict(rate_min_hz=100.0, gnss_gap_s=1.5, gnss_acc_outage_m=30.0, sats_min=4, cn0_min=22.0,
         pitch_outlier_deg=3.0, roll_outlier_deg=6.0, mount_change_deg=5.0,
         stand_rot_deg=2.0, stand_rot_warn_deg=5.0, stand_quiet_min=0.5, stand_acc_rms=0.30, bias_mismatch_dps=0.15,
         impact_mps2=30.0, impact_minor_max_mps2=40.0, clip_mps2=150.0, anchor_off_warn_m=10.0, anchor_off_fail_m=50.0, anchor_recompute_m=2.0,
         short_ride_frac=0.6, stand_trim_s=1.0, still_speed=0.5, moving_speed=1.0)

def gravity_angles(g):
    gx, gy, gz = g
    return math.degrees(math.atan2(gz, gy)), math.degrees(math.atan2(gx, math.hypot(gy, gz)))   # pitch, roll

def angle_between(a, b):
    c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))

def quat_rel_angle_deg(q1, q2):
    d = abs(float(np.dot(q1 / np.linalg.norm(q1), q2 / np.linalg.norm(q2))))
    return math.degrees(2 * math.acos(min(1.0, d)))

def stand_metrics(s, w, bias_ref):
    """Metrics of one stationary window w=(t0,t1) trimmed by T['stand_trim_s'] on both sides."""
    out = {}
    if not (np.isfinite(w[0]) and np.isfinite(w[1])) or w[1] - w[0] < 3.0:
        return dict(ok=False)
    ma = Session.in_window(s.acc['t_s'].values, w, T['stand_trim_s']); mg = Session.in_window(s.gyr['t_s'].values, w, T['stand_trim_s'])
    A = s.acc.loc[ma, ['ax', 'ay', 'az']].values; G = s.gyr.loc[mg, ['gx', 'gy', 'gz']].values; tg = s.gyr.loc[mg, 't_s'].values
    if len(A) < 100 or len(G) < 100: return dict(ok=False)
    g = A.mean(0); pitch, roll = gravity_angles(g)
    amag = np.linalg.norm(A, axis=1)
    bias, qfrac, nch = robust_gyro_bias(tg, G)
    dt = np.diff(tg, prepend=tg[0])
    rotvec = ((G - bias_ref) * dt[:, None]).sum(0)                     # net rotation vector during the stand (small-angle)
    out.update(ok=True, g=g, g_mag=float(np.linalg.norm(g)), pitch=pitch, roll=roll,
               acc_rms=float(np.sqrt(np.mean((amag - amag.mean()) ** 2))), acc_maxdev=float(np.abs(amag - amag.mean()).max()),
               bias=bias, quiet_frac=qfrac, n_chunks=nch, rot_deg=math.degrees(float(np.linalg.norm(rotvec))), rot_z_deg=math.degrees(float(rotvec[2])),
               gyro_max_dps=math.degrees(float(np.abs(G - bias_ref).max())))
    if s.gamerot is not None:
        mq = Session.in_window(s.gamerot['t_s'].values, w, T['stand_trim_s'])
        Q = s.gamerot.loc[mq, ['qx', 'qy', 'qz', 'qw']].values
        if len(Q) > 20:
            q0 = Q[:10].mean(0); q1 = Q[-10:].mean(0); out['gamerot_rot_deg'] = quat_rel_angle_deg(q0, q1)
    f = s.fix; mf = Session.in_window(f['t_s'].values, w, 0.0)
    if mf.sum() >= 3:
        out['gnss_speed_max'] = float(f.loc[mf, 'speed'].max()); out['gnss_pos_std_m'] = float(np.sqrt(f.loc[mf, 'x_m'].var() + f.loc[mf, 'y_m'].var()))
        good = mf & (f['acc_h'].values <= 15.0)
        if good.sum() >= 3: out['anchor_lat'] = float(f.loc[good, 'lat'].mean()); out['anchor_lon'] = float(f.loc[good, 'lon'].mean()); out['anchor_n'] = int(good.sum())
    return out

def qa_run(s):
    r = dict(session=s.name, run=s.run_no, dir=s.direction, rider=s.rider, route=s.route, status=s.meta.get('status', '?'),
             purpose=s.meta.get('purpose', ''), variation=s.meta.get('variation', ''), notes=s.meta.get('notes', ''),
             duration_s=float(s.meta.get('duration_s', s.t_end)), missing_streams=','.join(s.meta.get('missing_streams', [])))
    flags = []
    if r['status'] != 'COMPLETE': flags.append(f"STATUS_{r['status']}")
    for k in ('CALIB_START', 'CALIB_END', 'RIDE_START', 'STOP_CALIB_START', 'STOP_CALIB_END'):
        if k not in s.events: flags.append(f'NO_EVENT_{k}')
    # ---- IMU rates (recomputed)
    for nm, st in (('acc', s.acc_stats), ('gyr', s.gyr_stats)):
        r[f'{nm}_hz'] = round(st['median_hz'], 1); r[f'{nm}_p99_dt_ms'] = round(st['p99_dt_ms'], 2); r[f'{nm}_max_dt_ms'] = round(st['max_dt_ms'], 1)
        r[f'{nm}_gaps50'] = st['gaps_over_50ms']; r[f'{nm}_dups'] = st['dups']; r[f'{nm}_nonmono'] = st['nonmono']
        app = s.meta.get('streams', {}).get(nm, {}); r[f'{nm}_dropped_app'] = app.get('dropped', -1)
        if st['median_hz'] < T['rate_min_hz']: flags.append(f"RATE_LOW_{nm}({st['median_hz']:.0f}Hz)")
        if st['gaps_over_50ms'] > 0: flags.append(f"GAPS_{nm}({st['gaps_over_50ms']},max {st['max_dt_ms']:.0f}ms)")
        if app.get('dropped', 0) > 0: flags.append(f"DROPPED_{nm}({app['dropped']})")
        if st['dups'] > 0 or st['nonmono'] > 0: flags.append(f"TIMESTAMPS_{nm}(dups {st['dups']}, nonmono {st['nonmono']})")
    r['imu_start_lag_s'] = round(max(s.acc_stats['t_first'], s.gyr_stats['t_first']), 3); r['imu_end_lag_s'] = round(s.t_end - min(s.acc_stats['t_last'], s.gyr_stats['t_last']), 3)
    if r['imu_end_lag_s'] > 1.0: flags.append(f"IMU_ENDS_EARLY({r['imu_end_lag_s']:.1f}s)")
    # ---- GNSS
    f = s.fix; ride = s.ride; mr = Session.in_window(f['t_s'].values, ride)
    r['n_fix'] = len(f); r['n_fix_ride'] = int(mr.sum())
    tf = f['t_s'].values; dtf = np.diff(tf)
    r['fix_dt_median_s'] = round(float(np.median(dtf)), 2) if len(dtf) else np.nan
    dtr = np.diff(tf[mr]) if mr.sum() > 1 else np.array([])
    r['fix_max_dt_ride_s'] = round(float(dtr.max()), 2) if len(dtr) else np.nan
    r['acc_h_mean'] = round(float(f['acc_h'].mean()), 2); r['acc_h_max_ride'] = round(float(f.loc[mr, 'acc_h'].max()), 1) if mr.any() else np.nan
    r['sats_min_ride'] = int(f.loc[mr, 'n_sats_used'].min()) if mr.any() else -1
    r['mock'] = bool(f['is_mock'].any()) if 'is_mock' in f else False
    r['has_speed_frac'] = round(float(f['has_speed'].mean()), 3) if 'has_speed' in f else np.nan
    n_gap = int(np.sum(dtr > T['gnss_gap_s'])); n_acc = int(np.sum(f.loc[mr, 'acc_h'] > T['gnss_acc_outage_m'])); n_sat = int(np.sum(f.loc[mr, 'n_sats_used'] < T['sats_min']))
    r['cn0_min_ride'] = np.nan; n_cn0 = 0
    if s.epochs is not None:
        me = Session.in_window(s.epochs['t_s'].values, ride)
        if me.any():
            r['cn0_min_ride'] = round(float(s.epochs.loc[me, 'cn0_used_mean'].min()), 1); r['cn0_mean_ride'] = round(float(s.epochs.loc[me, 'cn0_used_mean'].mean()), 1)
            r['used_min_ride'] = int(s.epochs.loc[me, 'n_used'].min()); n_cn0 = int(np.sum(s.epochs.loc[me, 'cn0_used_mean'] < T['cn0_min']))
    r['real_outage_epochs'] = n_gap + n_acc + n_sat + n_cn0
    if n_gap: flags.append(f"GNSS_GAP({n_gap}x>{T['gnss_gap_s']}s, max {dtr.max():.1f}s)")
    if n_acc: flags.append(f"GNSS_ACC({n_acc} epochs >{T['gnss_acc_outage_m']:.0f}m)")
    if n_sat: flags.append(f"SATS_LOW({n_sat} epochs <{T['sats_min']})")
    if n_cn0: flags.append(f"CN0_LOW({n_cn0} epochs <{T['cn0_min']:.0f}dBHz)")
    if r['mock']: flags.append('MOCK_LOCATION')
    # ---- stands: robust reference bias from both stands together
    Gs = []; ts = []
    for w in (s.calib, s.stop):
        if np.isfinite(w[0]) and np.isfinite(w[1]):
            m = Session.in_window(s.gyr['t_s'].values, w, T['stand_trim_s']); Gs.append(s.gyr.loc[m, ['gx', 'gy', 'gz']].values); ts.append(s.gyr.loc[m, 't_s'].values)
    bias_ref = robust_gyro_bias(np.concatenate(ts), np.vstack(Gs))[0] if Gs else np.zeros(3)
    st = stand_metrics(s, s.calib, bias_ref); en = stand_metrics(s, s.stop, bias_ref)
    for lab, m in (('start', st), ('end', en)):
        if not m.get('ok'):
            r[f'stand_{lab}_ok'] = False; flags.append(f'NO_STAND_{lab.upper()}'); continue
        r[f'stand_{lab}_ok'] = True
        r[f'pitch_{lab}'] = round(m['pitch'], 2); r[f'roll_{lab}'] = round(m['roll'], 2); r[f'g_mag_{lab}'] = round(m['g_mag'], 3)
        r[f'stand_rot_{lab}_deg'] = round(m['rot_deg'], 2); r[f'stand_rotz_{lab}_deg'] = round(m['rot_z_deg'], 2); r[f'stand_quiet_{lab}'] = round(m['quiet_frac'], 2)
        r[f'stand_accrms_{lab}'] = round(m['acc_rms'], 3); r[f'stand_gyromax_{lab}_dps'] = round(m['gyro_max_dps'], 1)
        r[f'gamerot_{lab}_deg'] = round(m.get('gamerot_rot_deg', np.nan), 2)
        r[f'bias_{lab}_dps'] = tuple(np.round(np.degrees(m['bias']), 3)); r[f'biasz_{lab}_dps'] = round(math.degrees(m['bias'][2]), 3)
        r[f'gnss_vmax_{lab}'] = round(m.get('gnss_speed_max', np.nan), 2); r[f'gnss_std_{lab}_m'] = round(m.get('gnss_pos_std_m', np.nan), 2)
        why = []
        if m['rot_deg'] > T['stand_rot_warn_deg']: why.append(f"rot {m['rot_deg']:.1f}deg")
        if m['quiet_frac'] < T['stand_quiet_min']: why.append(f"quiet {m['quiet_frac']:.0%}")
        if m['acc_rms'] > T['stand_acc_rms']: why.append(f"acc rms {m['acc_rms']:.2f}")
        if why: flags.append(f"STAND_MOTION_{lab.upper()}({', '.join(why)})")
        elif m['rot_deg'] > T['stand_rot_deg']: flags.append(f"i:STAND_SLOW_ROT_{lab.upper()}({m['rot_deg']:.1f}deg)")   # info tier: does not change the verdict
    if st.get('ok') and en.get('ok'):
        r['mount_change_deg'] = round(angle_between(st['g'], en['g']), 2)
        r['bias_mismatch_dps'] = round(float(np.degrees(np.abs(st['bias'] - en['bias']).max())), 3)
        if r['mount_change_deg'] > T['mount_change_deg']: flags.append(f"MOUNT_CHANGE({r['mount_change_deg']:.1f}deg start->end)")
        if r['bias_mismatch_dps'] > T['bias_mismatch_dps']: flags.append(f"BIAS_MISMATCH({r['bias_mismatch_dps']:.2f}dps)")
    # ---- impacts / clipping during the ride
    ma = Session.in_window(s.acc['t_s'].values, ride); A = s.acc.loc[ma, ['ax', 'ay', 'az']].values; ta = s.acc.loc[ma, 't_s'].values
    amag = np.linalg.norm(A, axis=1); hi = amag > T['impact_mps2']
    if len(amag) == 0:                                                   # no ride window at all (false start: no RIDE_START event)
        r['a_max'] = np.nan; r['impact_samples'] = 0; r['t_amax_ride_s'] = np.nan; r['impact_events'] = 0; r['clip'] = False; ev = 0; flags.append('NO_RIDE_WINDOW')
    else:
        r['a_max'] = round(float(amag.max()), 1); r['impact_samples'] = int(hi.sum()); r['t_amax_ride_s'] = round(float(ta[np.argmax(amag)] - ride[0]), 1)
        ev = 0
        if hi.any():
            th = ta[hi]; ev = 1 + int(np.sum(np.diff(th) > 0.5))
        r['impact_events'] = ev; r['clip'] = bool(np.abs(A).max() > T['clip_mps2'])
    if ev:
        minor = amag.max() < T['impact_minor_max_mps2'] and hi.sum() <= 2
        flags.append(f"{'i:IMPACT_MINOR' if minor else 'IMPACT'}({ev} events, {hi.sum()} samples, max {amag.max():.0f} m/s2 at {r['t_amax_ride_s']:.0f}s)")
    if r['clip']: flags.append('CLIPPING')
    # ---- ride statistics from GNSS
    fr = f.loc[mr]; sp = fr['speed'].values; tr_ = fr['t_s'].values
    r['ride_s'] = round(float(ride[1] - ride[0]), 1)
    mv = sp > T['moving_speed']
    if mv.sum() >= 2:
        t_m0 = float(tr_[mv][0]); t_m1 = float(tr_[mv][-1])
        r['motion_start_lag_s'] = round(t_m0 - ride[0], 1); r['motion_end_lead_s'] = round(ride[1] - t_m1, 1); r['moving_s'] = round(t_m1 - t_m0, 1)
        r['v_mean_moving'] = round(float(sp[mv].mean()), 2); r['v_max'] = round(float(sp.max()), 2); r['slow_frac'] = round(float(np.mean(sp[(tr_ >= t_m0) & (tr_ <= t_m1)] < 2.0)), 2)
        inside = (tr_ >= t_m0) & (tr_ <= t_m1); still = inside & (sp < T['still_speed'])
        r['still_s_midride'] = round(float(still.sum() * np.median(dtf)), 1)
        # mid-ride stops: runs of still fixes >= 2 s
        runs = 0; k = 0; idx = np.where(inside)[0]
        while k < len(idx):
            if sp[idx[k]] < T['still_speed']:
                j = k
                while j + 1 < len(idx) and sp[idx[j + 1]] < T['still_speed']: j += 1
                if tr_[idx[j]] - tr_[idx[k]] >= 2.0: runs += 1
                k = j + 1
            else: k += 1
        r['mid_stops'] = runs
    else:
        r['moving_s'] = 0.0; r['v_mean_moving'] = np.nan; r['v_max'] = round(float(sp.max()), 2) if len(sp) else np.nan; r['mid_stops'] = 0
        flags.append('NO_MOTION')
    good = fr['acc_h'].values <= 15.0
    r['path_m'] = round(float(np.sum(np.hypot(np.diff(fr.loc[good, 'x_m'].values), np.diff(fr.loc[good, 'y_m'].values)))), 1) if good.sum() > 1 else np.nan
    r['baro_ok'] = (s.dir / 'baro.csv').exists()
    # ---- anchors (app) and recomputed
    a0 = s.meta.get('start_anchor') or {}; a1 = s.meta.get('end_anchor') or {}
    r['anchor_start_lat'] = a0.get('lat', np.nan); r['anchor_start_lon'] = a0.get('lon', np.nan); r['anchor_end_lat'] = a1.get('lat', np.nan); r['anchor_end_lon'] = a1.get('lon', np.nan)
    r['anchor_dist_app_m'] = round(float(s.meta.get('anchor_distance_m', np.nan)), 1); r['polyline_app_m'] = round(float(s.meta.get('polyline_length_m', np.nan)), 1)
    for lab, m, a in (('start', st, a0), ('end', en, a1)):
        if m.get('ok') and 'anchor_lat' in m and 'lat' in a:
            d = geodist_m(a['lat'], a['lon'], m['anchor_lat'], m['anchor_lon']); r[f'anchor_{lab}_recompute_m'] = round(d, 2)
            if d > T['anchor_recompute_m']: flags.append(f"ANCHOR_RECOMPUTE_{lab.upper()}({d:.1f}m)")
        elif 'lat' not in a: flags.append(f'NO_ANCHOR_{lab.upper()}')
    # ---- power / thermal
    if s.sys is not None and len(s.sys):
        r['batt_start'] = int(s.sys['batt_pct'].iloc[0]); r['batt_end'] = int(s.sys['batt_pct'].iloc[-1]); r['thermal_max'] = int(s.sys['thermal_status'].max()); r['batt_temp_max'] = float(s.sys['batt_temp_c'].max())
        if r['thermal_max'] >= 2: flags.append(f"THERMAL({r['thermal_max']})")
    r['flags'] = flags
    return r

def set_level(rows):
    """Cross-run checks: pitch/roll vs set median, A/B endpoint clusters, short rides, direction labels."""
    df = pd.DataFrame(rows)
    pm = df['pitch_start'].median(); rm = df['roll_start'].median()
    df['d_pitch_median'] = (df['pitch_start'] - pm).round(2); df['d_roll_median'] = (df['roll_start'] - rm).round(2)
    # endpoint clusters: A = {AB starts, BA ends}, B = {AB ends, BA starts}
    A_lat = pd.concat([df.loc[df.dir == 'AB', 'anchor_start_lat'], df.loc[df.dir == 'BA', 'anchor_end_lat']]).median()
    A_lon = pd.concat([df.loc[df.dir == 'AB', 'anchor_start_lon'], df.loc[df.dir == 'BA', 'anchor_end_lon']]).median()
    B_lat = pd.concat([df.loc[df.dir == 'AB', 'anchor_end_lat'], df.loc[df.dir == 'BA', 'anchor_start_lat']]).median()
    B_lon = pd.concat([df.loc[df.dir == 'AB', 'anchor_end_lon'], df.loc[df.dir == 'BA', 'anchor_start_lon']]).median()
    ride_med = df['ride_s'].median(); path_med = df['path_m'].median()
    for i, r in df.iterrows():
        fl = list(r['flags'])
        if abs(r['d_pitch_median']) > T['pitch_outlier_deg']: fl.append(f"PITCH_OUTLIER({r['d_pitch_median']:+.1f}deg vs median {pm:.1f})")
        if abs(r['d_roll_median']) > T['roll_outlier_deg']: fl.append(f"ROLL_OUTLIER({r['d_roll_median']:+.1f}deg vs median {rm:.1f})")
        if np.isfinite(r['anchor_start_lat']) and np.isfinite(A_lat):
            exp_s, exp_e = ((A_lat, A_lon), (B_lat, B_lon)) if r['dir'] == 'AB' else ((B_lat, B_lon), (A_lat, A_lon))
            ds = geodist_m(exp_s[0], exp_s[1], r['anchor_start_lat'], r['anchor_start_lon']); de = geodist_m(exp_e[0], exp_e[1], r['anchor_end_lat'], r['anchor_end_lon'])
            ds_other = geodist_m(exp_e[0], exp_e[1], r['anchor_start_lat'], r['anchor_start_lon'])
            df.loc[i, 'start_off_m'] = round(ds, 1); df.loc[i, 'end_off_m'] = round(de, 1)
            if ds_other < ds: fl.append(f"DIRECTION_MISLABELLED(start is {ds_other:.0f}m from the other end)")
            else:
                for lab, d in (('START', ds), ('END', de)):
                    if d > T['anchor_off_fail_m']: fl.append(f"ANCHOR_OFF_{lab}({d:.0f}m)")
                    elif d > T['anchor_off_warn_m']: fl.append(f"ANCHOR_DRIFT_{lab}({d:.0f}m)")
        if np.isfinite(ride_med) and (r['ride_s'] < T['short_ride_frac'] * ride_med or (np.isfinite(r['path_m']) and r['path_m'] < T['short_ride_frac'] * path_med)):
            fl.append(f"SHORT_RIDE({r['ride_s']:.0f}s, {r['path_m']:.0f}m vs median {ride_med:.0f}s, {path_med:.0f}m)")
        df.at[i, 'flags'] = fl
    FAIL = ('STATUS_', 'RATE_LOW', 'GAPS_', 'DROPPED_', 'ANCHOR_OFF', 'SHORT_RIDE', 'DIRECTION_MISLABELLED', 'MOCK', 'NO_MOTION', 'NO_EVENT', 'CLIPPING', 'NO_ANCHOR', 'NO_STAND', 'NO_RIDE')
    df['verdict'] = ['FAIL' if any(f.startswith(FAIL) for f in fl) else ('WARN' if any(not f.startswith('i:') for f in fl) else 'PASS') for fl in df['flags']]
    df['flags_str'] = ['; '.join(fl) for fl in df['flags']]
    df.attrs.update(A=(A_lat, A_lon), B=(B_lat, B_lon), pitch_median=pm, roll_median=rm, ride_median=ride_med, path_median=path_med)
    return df

COMPACT = ['run', 'dir', 'rider', 'verdict', 'ride_s', 'acc_hz', 'gyr_hz', 'acc_gaps50', 'n_fix', 'fix_max_dt_ride_s', 'acc_h_mean', 'sats_min_ride', 'cn0_min_ride',
           'pitch_start', 'roll_start', 'd_pitch_median', 'mount_change_deg', 'stand_rot_start_deg', 'stand_quiet_start', 'stand_rot_end_deg', 'stand_quiet_end', 'bias_mismatch_dps',
           'impact_events', 'a_max', 'v_mean_moving', 'v_max', 'path_m', 'mid_stops', 'start_off_m', 'end_off_m', 'flags_str']

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('paths', nargs='+'); ap.add_argument('--tag', default='qa'); ap.add_argument('--outdir', default='data/qa')
    a = ap.parse_args(); dirs = find_sessions(a.paths)
    if not dirs: sys.exit('no sessions found')
    rows = []
    for d in dirs:
        s = Session(d); r = qa_run(s); rows.append(r)
        print(f"{s.name}: {'; '.join(r['flags']) or 'clean'}", flush=True)
    df = set_level(rows)
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    df.drop(columns=['flags']).to_csv(out / f'{a.tag}.csv', index=False)
    cols = [c for c in COMPACT if c in df.columns]
    md = [f"# QA {a.tag}: {len(df)} runs — {int((df.verdict=='PASS').sum())} PASS, {int((df.verdict=='WARN').sum())} WARN, {int((df.verdict=='FAIL').sum())} FAIL",
          f"A = ({df.attrs['A'][0]:.6f}, {df.attrs['A'][1]:.6f}), B = ({df.attrs['B'][0]:.6f}, {df.attrs['B'][1]:.6f}); pitch median {df.attrs['pitch_median']:.2f} deg, roll median {df.attrs['roll_median']:.2f} deg; ride median {df.attrs['ride_median']:.0f} s, path median {df.attrs['path_median']:.0f} m", '',
          '| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for _, r in df.iterrows(): md.append('| ' + ' | '.join(str(r[c]) for c in cols) + ' |')
    md += ['', 'Thresholds: ' + ', '.join(f'{k}={v}' for k, v in T.items())]
    (out / f'{a.tag}_flags.md').write_text('\n'.join(md) + '\n')
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
    print(df[cols[:-1]].to_string(index=False)); print('\n'.join(md[:2]))
    for _, r in df.iterrows():
        if r['flags_str']: print(f"  run{r['run']} {r['dir']} [{r['verdict']}]: {r['flags_str']}")
    print('wrote', out / f'{a.tag}.csv', out / f'{a.tag}_flags.md')

if __name__ == '__main__':
    main()
