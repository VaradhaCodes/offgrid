"""Position plot for the PS: one median-level IO-VNBD blackout at >= 54 km/h (never a best case), OSM roads, truth, OFFGRID,
the no-map track and 'keep last speed'. Also exports the tracks (local metres, north up) for the deck.

Usage: .venv/Scripts/python engine/iovopt/plot_final.py --tag final
Pick rule: masks >= 54 km/h with 0.8-1.6 km travelled and the road lock held; the one whose OFFGRID drift is closest to the
median of the whole >= 54 km/h subset.
"""
import sys, argparse, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import roadpf

RUNS = Path(r'D:\offgrid_iov\runs'); REPO = Path(__file__).resolve().parents[2]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tag', default='final'); ap.add_argument('--key', default='')
    a = ap.parse_args(); df = pd.read_csv(REPO / 'data' / 'qa' / f'iovnbd_opt_{a.tag}.csv'); T = np.load(RUNS / f'final_{a.tag}_tracks.npy', allow_pickle=True).item()
    o = df[df.variant == 'offgrid']; hi = o[o.v_mean * 3.6 >= 54]; med = hi.drift_pct.median()
    c = hi[(hi.dist_m.between(800, 1600)) & (hi.lock == 'ok')].copy(); c['gap'] = (c.drift_pct - med).abs(); pick = c.sort_values('gap').iloc[0]
    key = a.key or f"{pick.seq}|{pick.t0:.0f}"; r = o[(o.seq + '|' + o.t0.map(lambda x: f'{x:.0f}')) == key].iloc[0]; tr = T[key]
    hold = df[(df.variant == 'keep_last_speed') & (df.seq == r.seq) & (df.t0 == r.t0)].iloc[0]; nomap = df[(df.variant == 'offgrid_nomap') & (df.seq == r.seq) & (df.t0 == r.t0)].iloc[0]
    print(f'>= 54 km/h median {med:.2f} %; picked {key}: {r.dist_m:.0f} m at {r.v_mean * 3.6:.0f} km/h, OFFGRID {r.end_m:.1f} m ({r.drift_pct:.2f} %), no map {nomap.end_m:.1f} m, keep last speed {hold.end_m:.1f} m')
    g = roadpf.load_graph(tr['osm']); p0 = tr['truth'][0]
    allp = np.vstack([tr['pre'], tr['truth'], tr['offgrid'], tr['post'], tr['hold']]); mn, mx = allp.min(0) - 120, allp.max(0) + 120
    fig, ax = plt.subplots(figsize=(10, 10), facecolor='#171717'); ax.set_facecolor('#171717')
    for A, B in zip(g.A, g.B):
        P = g.P[[A, B]]
        if ((P >= mn) & (P <= mx)).all(1).any(): ax.plot(P[:, 0], P[:, 1], color='#3a3a3a', lw=1.2, zorder=1)
    ax.plot(*tr['pre'].T, color='#9BE8C4', lw=3, zorder=3, label='GPS on'); ax.plot(*tr['post'].T, color='#9BE8C4', lw=3, zorder=3, alpha=0.6, label='GPS back')
    ax.plot(*tr['truth'].T, color='white', lw=1.6, ls=(0, (2, 2)), zorder=7, label='real path (VBOX)')
    ax.plot(*tr['hold'].T, color='#FF5A5F', lw=1.6, zorder=4, alpha=0.9, label=f'keep last GPS speed: {hold.end_m:.0f} m off')
    ax.plot(*tr['offgrid'].T, color='#FFB454', lw=3, zorder=5, label=f'OFFGRID (1D speed net + road lock): {r.end_m:.0f} m off')
    ax.plot(*p0, 'o', color='#9BE8C4', ms=9, zorder=6); ax.plot(*tr['truth'][-1], 'o', color='white', ms=7, zorder=6); ax.plot(*tr['offgrid'][-1], 'o', color='#FFB454', ms=8, zorder=6)
    ax.set_xlim(mn[0], mx[0]); ax.set_ylim(mn[1], mx[1]); ax.set_aspect('equal'); ax.axis('off')
    ax.legend(loc='lower left', facecolor='#252B28', edgecolor='#252B28', labelcolor='white', fontsize=10)
    ax.set_title(f'IO-VNBD drive {r.seq}, GPS cut for 60 s at {r.v_mean * 3.6:.0f} km/h ({r.dist_m / 1000:.2f} km), family {r.fam} never seen in training', color='white', fontsize=11)
    out = REPO / 'data' / 'qa' / f'iovnbd_opt_{a.tag}.png'; fig.savefig(out, dpi=150, facecolor='#171717', bbox_inches='tight'); print('plot', out)
    exp = dict(seq=r.seq, t0=float(r.t0), dist_m=float(r.dist_m), v_kmh=float(r.v_mean * 3.6), offgrid_end_m=float(r.end_m), nomap_end_m=float(nomap.end_m), hold_end_m=float(hold.end_m),
               subset_median_pct=float(med), **{k: np.asarray(tr[k]).round(2).tolist() for k in ('pre', 'truth', 'offgrid', 'nomap', 'hold', 'post')})
    json.dump(exp, open(REPO / 'data' / 'qa' / f'iovnbd_opt_{a.tag}_plot.json', 'w'))

if __name__ == '__main__':
    main()
