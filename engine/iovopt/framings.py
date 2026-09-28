"""Every headline number the deck could use, from the final per-mask table, each with the footnote it needs.

Usage: .venv/Scripts/python engine/iovopt/framings.py --tag final
All are medians of held-out blackouts (leave-one-family-out); subsets are defined by the true mean speed or distance of the blackout.
"""
import argparse
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]

def line(name, x, foot):
    o = x[x.variant == 'offgrid']; h = x[x.variant == 'keep_last_speed']
    if not len(o): return
    print(f"{name:44s} n={len(o):3d}  median {o.drift_pct.median():5.2f} %  = {(1000 * o.end_m / o.dist_m).median():5.1f} m/km  under 10 %: {(o.drift_pct < 10).mean() * 100:5.1f} %  "
          f"p90 {o.drift_pct.quantile(.9):5.2f} %  | keep-last-speed {h.drift_pct.median():5.2f} %   [{foot}]")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tag', default='final'); a = ap.parse_args()
    df = pd.read_csv(REPO / 'data' / 'qa' / f'iovnbd_opt_{a.tag}.csv'); v = df.v_mean * 3.6
    line('all blackouts', df, 'median of all 60 s blackouts, 28 drives')
    line('>= 54 km/h (PS example: 1 km at 60 km/h)', df[v >= 54], 'blackouts averaging 54+ km/h')
    line('>= 80 km/h (motorway)', df[v >= 80], 'blackouts averaging 80+ km/h')
    line('<= 30 km/h (town)', df[v <= 30], 'blackouts averaging up to 30 km/h')
    line('>= 1 km travelled', df[df.dist_m >= 1000], 'blackouts covering at least 1 km')
    line('road lock held', df[df.lock.isin(['ok']) | (df.variant != 'offgrid')].groupby(['seq', 't0']).filter(lambda g: (g.variant == 'offgrid').any()), 'blackouts where the OSM road lock held (not lost / no road)')
    for f in sorted(df.fam.unique()): line(f'family {f}', df[df.fam == f], f'driver family {f} only')
    o = df[df.variant == 'offgrid']; print(f"\nbest single blackout: {o.drift_pct.min():.2f} % ({o.loc[o.drift_pct.idxmin(), 'seq']} t0 {o.loc[o.drift_pct.idxmin(), 't0']:.0f}) — a best case, never a headline")

if __name__ == '__main__':
    main()
