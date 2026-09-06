"""Summarise a nav ride session for docs/16 §7 (acceptance 11.4 / 11.7): stream rates and gaps from session.json, engine tick
statistics and GNSS age from engine_out.csv, mode transitions from engine_events.csv, and an optional wall-clock window
(e.g. airplane mode) expressed in session seconds.

Usage: .venv/bin/python tools/bench_report.py <session_dir> [--window HH:MM:SS HH:MM:SS] [--log bench.log]
"""
import sys, json, argparse, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('session'); ap.add_argument('--window', nargs=2); ap.add_argument('--log', default='')
    a = ap.parse_args(); d = Path(a.session); meta = json.load(open(d / 'session.json'))
    print(f"session {d.name}: status {meta.get('status')} duration {meta.get('duration_s')} s route_id {meta.get('route_id')} direction {meta.get('direction')} nav_mode {meta.get('nav_mode')} speed_model {meta.get('speed_model')}")
    st = meta.get('streams', {})
    print(f"streams written: {len(st)} -> {sorted(st)}")
    for s in ('acc', 'gyr', 'mag', 'gnss_fix', 'gnss_status', 'engine_out', 'engine_events'):
        if s in st: r = st[s]; print(f"  {s:13s} rows {r['rows']:8d} dropped {r['dropped']} median_hz {r.get('median_hz')} p99_dt_ms {r.get('p99_dt_ms')} max_dt_ms {r.get('max_dt_ms')} gaps>50ms {r.get('gaps_over_50ms')}")
    print(f"gaps_over_50ms_continuous {meta.get('gaps_over_50ms_continuous')}  total dropped {sum(r['dropped'] for r in st.values())}")
    sa = meta.get('start_anchor', {}); ea = meta.get('end_anchor', {})
    print(f"anchors: start n={sa.get('n_fixes')} std={sa.get('std_m')} acc={sa.get('mean_acc_m')} | end n={ea.get('n_fixes')} std={ea.get('std_m')} | distance {meta.get('anchor_distance_m')} m")
    eo = pd.read_csv(d / 'engine_out.csv')
    print(f"engine_out: {len(eo)} rows, t {eo.t_s.min():.1f}..{eo.t_s.max():.1f} s; tick_ms mean {eo.tick_ms.mean():.3f} p95 {eo.tick_ms.quantile(.95):.3f} p99 {eo.tick_ms.quantile(.99):.3f} max {eo.tick_ms.max():.2f}; model_ms mean {eo.model_ms[eo.model_ms > 0].mean():.3f} p95 {eo.model_ms[eo.model_ms > 0].quantile(.95):.3f} max {eo.model_ms.max():.2f}")
    print(f"modes: {eo['mode'].value_counts().to_dict()}; sim ticks {int(eo.sim.sum())}; corridor ids {eo.corridor_id.dropna().unique().tolist()}")
    print(f"position sigma: median {eo.sigma_pos.median():.2f} m; speed max {eo.v.max():.2f} m/s; stop flag fraction {eo.stop.mean():.2f}")
    ev = pd.read_csv(d / 'engine_events.csv')
    keep = ev[ev.type.isin(['PHASE', 'MODE', 'ARMED', 'DISARMED', 'CORRIDOR', 'REAL_OUTAGE', 'OUTAGE_ENTER', 'OUTAGE_END', 'REVEAL', 'MOTION_START', 'ALIGN'])]
    for r in keep.head(25).itertuples(): print(f"  {r.t_s:8.1f} {r.type:12s} {str(r.text)[:110]}")
    if a.window:
        t0w = meta['wall_clock_at_start_ms'] / 1000.0
        day = dt.datetime.fromtimestamp(t0w).date()
        def sess(hms): h, m, s = map(int, hms.split(':')); return dt.datetime.combine(day, dt.time(h, m, s)).timestamp() - t0w
        w0, w1 = sess(a.window[0]), sess(a.window[1])
        fx = pd.read_csv(d / 'gnss_fix.csv'); t0ns = meta['elapsed_realtime_ns_at_start']; ft = (fx.t_ns - t0ns) / 1e9
        inw = fx[(ft >= w0) & (ft <= w1)]; before = fx[(ft >= w0 - 60) & (ft < w0)]
        print(f"window {a.window[0]}-{a.window[1]} = session {w0:.0f}-{w1:.0f} s: GPS fixes {len(inw)} in {w1 - w0:.0f} s (before: {len(before)} in 60 s); acc_h mean {inw.acc_h.mean():.1f} m (before {before.acc_h.mean():.1f}); sats used {inw.n_sats_used.mean():.0f} (before {before.n_sats_used.mean():.0f})")
        m = eo[(eo.t_s >= w0) & (eo.t_s <= w1)]; print(f"  engine in window: modes {m['mode'].value_counts().to_dict()}, max gnss age not logged directly; sim {int(m.sim.sum())}")
    if a.log:
        L = open(a.log).read().splitlines()
        g = [l for l in L if any(k in l for k in ('Total frames', 'Janky frames', '50th', '90th', '95th', '99th'))]
        print("gfxinfo (whole bench, map live under the ride screen):"); [print("  " + x.strip()) for x in g]
        temps = [l for l in L if 'temperature' in l and 'level' in l]; print(f"battery/thermal samples: {len(temps)}")

if __name__ == '__main__':
    main()
