"""Compare engine tracks: device engine_out.csv vs the JVM engine_out.csv vs the Python reference (spec §9 / acceptance 11.3).

Usage: .venv/bin/python tools/compare_engine_out.py <device_engine_out.csv> [--jvm docs/qa_app/jvm_<session>_engine_out.csv] [--ref data/qa/replay/<session>_corridor_mm0.csv]
Joins on t_s rounded to 0.1 s; prints max/mean |dpos|, heading, speed, mode transition times and per-tick latency stats of the device run.
"""
import sys, argparse, math
import numpy as np, pandas as pd

def load(p):
    d = pd.read_csv(p); d['k'] = (d['t_s'] * 10).round().astype(int); return d.set_index('k')

def compare(a, b, la, lb):
    m = a.join(b, how='inner', lsuffix='_a', rsuffix='_b')
    if 'x_m_a' in m: xa, ya, xb, yb = m.x_m_a, m.y_m_a, m.x_m_b, m.y_m_b
    else: xa, ya, xb, yb = m.x_m, m.y_m, m['x_m'], m['y_m']
    m = m[np.isfinite(xa) & np.isfinite(xb)]
    dp = np.hypot(m.x_m_a - m.x_m_b, m.y_m_a - m.y_m_b)
    dh = np.abs(((m.heading_deg_a - m.heading_deg_b) + 180) % 360 - 180)
    dv = np.abs(m.v_a - m.v_b)
    ta = a[a['mode'].ne(a['mode'].shift())][['t_s', 'mode']].values.tolist(); tb = b[b['mode'].ne(b['mode'].shift())][['t_s', 'mode']].values.tolist()
    print(f"{la} vs {lb}: n={len(m)} | max |dpos| {dp.max():.3f} m at t={m.t_s_a[dp.idxmax()]:.1f} | mean {dp.mean():.3f} | end {dp.iloc[-1]:.3f} | max |dheading| {dh.max():.3f} deg | max |dv| {dv.max():.3f} m/s")
    print(f"   modes {la}: {[(round(t,1), s) for t, s in ta]}\n   modes {lb}: {[(round(t,1), s) for t, s in tb]}")
    return dp.max()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('device'); ap.add_argument('--jvm', default=''); ap.add_argument('--ref', default='')
    a = ap.parse_args(); dev = load(a.device)
    print(f"device: {len(dev)} ticks, t {dev.t_s.min():.1f}..{dev.t_s.max():.1f} s; tick_ms mean {dev.tick_ms.mean():.3f} p95 {dev.tick_ms.quantile(.95):.3f} max {dev.tick_ms.max():.2f}; model_ms mean {dev.model_ms[dev.model_ms>0].mean():.3f} p95 {dev.model_ms[dev.model_ms>0].quantile(.95):.3f} max {dev.model_ms.max():.2f}")
    if a.jvm: compare(dev, load(a.jvm), 'device', 'jvm')
    if a.ref: compare(dev, load(a.ref), 'device', 'reference')

if __name__ == '__main__':
    main()
