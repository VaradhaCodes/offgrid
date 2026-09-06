"""Corridor polyline utilities (runtime, plain numpy) and the route-1 corridor builder.

Usage: .venv/bin/python engine/corridor.py --build route1        # OSM ways 547215901 + 547215900 -> data/map/corridor_route1.geojson
       .venv/bin/python engine/corridor.py --validate route1     # lateral distance of every kept run's fixes to the polyline

class Corridor: built from lat/lon vertices; local ENU metres about a reference (lat0, lon0) supplied per session so that the
corridor lives in the same frame as the session's GNSS track. project(x, y) -> (s, d, seg) arc length, signed lateral offset
(positive = left of travel direction), segment; point(s) -> (x, y); tangent(s) -> unit vector; heading(s) -> ENU yaw.
"""
import sys, json, math, argparse
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from session import local_xy

class Corridor:
    def __init__(self, latlon, lat0, lon0):
        self.latlon = np.asarray(latlon, float); x, y = local_xy(self.latlon[:, 0], self.latlon[:, 1], lat0, lon0)
        self.P = np.column_stack([x, y]); d = np.diff(self.P, axis=0); self.L = np.hypot(d[:, 0], d[:, 1])
        self.S = np.concatenate([[0.0], np.cumsum(self.L)]); self.T = d / np.maximum(self.L, 1e-9)[:, None]; self.length = float(self.S[-1])
    def project(self, x, y):
        """Nearest point on the polyline: returns (s, d_signed, k). Vectorised over points."""
        x = np.atleast_1d(x).astype(float); y = np.atleast_1d(y).astype(float)
        px = x[:, None] - self.P[:-1, 0][None, :]; py = y[:, None] - self.P[:-1, 1][None, :]
        u = np.clip((px * self.T[:, 0][None, :] + py * self.T[:, 1][None, :]) / np.maximum(self.L, 1e-9)[None, :], 0.0, 1.0)
        cx = self.P[:-1, 0][None, :] + u * self.L[None, :] * self.T[:, 0][None, :]; cy = self.P[:-1, 1][None, :] + u * self.L[None, :] * self.T[:, 1][None, :]
        dist = np.hypot(x[:, None] - cx, y[:, None] - cy); k = np.argmin(dist, axis=1); i = np.arange(len(x))
        s = self.S[k] + u[i, k] * self.L[k]; cross = self.T[k, 0] * (y - cy[i, k]) - self.T[k, 1] * (x - cx[i, k])
        return s, np.sign(cross) * dist[i, k], k
    def point(self, s):
        s = np.clip(np.atleast_1d(s).astype(float), 0.0, self.length); k = np.clip(np.searchsorted(self.S, s, side='right') - 1, 0, len(self.L) - 1)
        u = (s - self.S[k]); return np.column_stack([self.P[k, 0] + u * self.T[k, 0], self.P[k, 1] + u * self.T[k, 1]])
    def tangent(self, s):
        s = np.clip(np.atleast_1d(s).astype(float), 0.0, self.length); k = np.clip(np.searchsorted(self.S, s, side='right') - 1, 0, len(self.L) - 1); return self.T[k]
    def heading(self, s):
        t = self.tangent(s); return np.arctan2(t[:, 1], t[:, 0])
    def bends(self, min_deg=25.0, window_m=25.0):
        """Landmark bends: arc length of turning points where the tangent rotates by >= min_deg within window_m (signed)."""
        out = []; sm = np.arange(0, self.length, 2.0); h = np.unwrap(self.heading(sm))
        for i in range(len(sm)):
            j = np.searchsorted(sm, sm[i] + window_m); j = min(j, len(sm) - 1)
            dh = math.degrees(h[j] - h[i])
            if abs(dh) >= min_deg: out.append((float(sm[i] + window_m / 2), float(dh)))
        # merge consecutive
        merged = []
        for s, dh in out:
            if merged and s - merged[-1][0] < window_m: merged[-1] = (merged[-1][0], merged[-1][1] if abs(merged[-1][1]) > abs(dh) else dh)
            else: merged.append((s, dh))
        return merged

def load_corridor(path, lat0, lon0):
    g = json.load(open(path)); coords = g['features'][0]['geometry']['coordinates']
    return Corridor([(c[1], c[0]) for c in coords], lat0, lon0), g['features'][0]['properties']

def build_route1():
    """Shortest path between the A and B anchors over the graph formed by OSM ways 547215901 + 547215900 (shared node ids)."""
    import heapq
    j = json.load(open('data/map/snu_osm_highways_900m.json')); ways = {w['id']: w for w in j['elements'] if w['type'] == 'way'}
    A = (28.522683, 77.573990); B = (28.521553, 77.571598)          # cluster endpoints from QA
    nodes = {}; adj = {}
    def d(p, q): return math.hypot(*local_xy(q[0], q[1], p[0], p[1]))
    for wid in (547215901, 547215900):
        w = ways[wid]; ids = w['nodes']; geo = [(g['lat'], g['lon']) for g in w['geometry']]
        for nid, ll in zip(ids, geo): nodes[nid] = ll
        for a, b in zip(ids[:-1], ids[1:]):
            L = d(nodes[a], nodes[b]); adj.setdefault(a, []).append((b, L)); adj.setdefault(b, []).append((a, L))
    shared = set(ways[547215901]['nodes']) & set(ways[547215900]['nodes']); print(f"nodes {len(nodes)}, shared between the two ways: {len(shared)}")
    # virtual nodes for A and B: connect to the two endpoints of the nearest segment (split point)
    def attach(name, P):
        best = None
        for a in adj:
            for b, L in adj[a]:
                pa, pb = nodes[a], nodes[b]; ax, ay = local_xy(pa[0], pa[1], P[0], P[1]); bx, by = local_xy(pb[0], pb[1], P[0], P[1])
                ax, ay, bx, by = float(ax), float(ay), float(bx), float(by); vx, vy = bx - ax, by - ay; L2 = vx * vx + vy * vy
                u = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, -(ax * vx + ay * vy) / L2)); cx, cy = ax + u * vx, ay + u * vy; dist = math.hypot(cx, cy)
                if best is None or dist < best[0]: best = (dist, a, b, u)
        dist, a, b, u = best; pa, pb = nodes[a], nodes[b]; c = (pa[0] + u * (pb[0] - pa[0]), pa[1] + u * (pb[1] - pa[1])); nodes[name] = c
        adj.setdefault(name, []); adj[name] += [(a, d(c, pa)), (b, d(c, pb))]; adj[a].append((name, d(c, pa))); adj[b].append((name, d(c, pb)))
        print(f"{name}: nearest segment at {dist:.1f} m, split at u={u:.2f}")
    attach('A', A); attach('B', B)
    dist = {'A': 0.0}; prev = {}; pq = [(0.0, 'A')]
    while pq:
        dd, n = heapq.heappop(pq)
        if dd > dist.get(n, 1e18): continue
        for m, L in adj[n]:
            nd = dd + L
            if nd < dist.get(m, 1e18): dist[m] = nd; prev[m] = n; heapq.heappush(pq, (nd, m))
    if 'B' not in dist: raise SystemExit('A and B are not connected through the two ways')
    path = ['B']
    while path[-1] != 'A': path.append(prev[path[-1]])
    path = path[::-1]; pts = [nodes[n] for n in path]; print(f"shortest path A->B: {dist['B']:.1f} m over {len(path)} nodes")
    cor = Corridor(pts, A[0], A[1])
    # 15 m overhang at both ends along the way beyond A and B (continue along the graph edge if it exists), else none
    mlon = 111320.0 * math.cos(math.radians(A[0]))
    def extend(end_node, other_node, want=15.0):
        cands = [(m, L) for m, L in adj[end_node] if m != other_node and m not in ('A', 'B')]
        if not cands: return []
        m, L = max(cands, key=lambda c: c[1]); pm = nodes[m]; pe = nodes[end_node]; f = min(1.0, want / max(L, 1e-9))
        return [(pe[0] + f * (pm[0] - pe[0]), pe[1] + f * (pm[1] - pe[1]))]
    pre = extend('A', path[1]); post = extend('B', path[-2]); pts2 = pre + pts + post
    cor2 = Corridor(pts2, A[0], A[1]); sA = cor2.project(0.0, 0.0)[0][0]; xb, yb = local_xy(B[0], B[1], A[0], A[1]); sB = cor2.project(xb, yb)[0][0]
    coords = [[ll[1], ll[0]] for ll in pts2]
    gj = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'route_id': 'SNU_R1', 'name': 'route 1: football-ground road, Hostel 2B (A) -> Indoor Sports Complex junction (B)', 'osm_ways': [547215901, 547215900], 'length_m': round(cor2.length), 'overhang_m': 15, 'anchor_A': list(A), 'anchor_B': list(B), 's_A': round(float(sA), 1), 's_B': round(float(sB), 1)}, 'geometry': {'type': 'LineString', 'coordinates': coords}}]}
    json.dump(gj, open('data/map/corridor_route1.geojson', 'w'), indent=1)
    print(f"wrote data/map/corridor_route1.geojson: {len(coords)} vertices, {cor2.length:.0f} m, A at s={sA:.1f}, B at s={sB:.1f}; bends (s, deg): {[(round(s), round(a)) for s, a in cor2.bends()]}")

def validate(tag):
    import pandas as pd
    from evaluate import kept_runs, Run
    qa = kept_runs(f'data/qa/{tag}.csv', f'data/{tag}/sessions'); rows = []
    for _, r in qa.iterrows():
        run = Run(r['session'], f'data/{tag}/sessions'); sess = json.load(open(Path(f'data/{tag}/sessions') / r['session'] / 'session.json'))
        cor, props = load_corridor(f'data/map/corridor_{tag}.geojson', sess['start_anchor']['lat'], sess['start_anchor']['lon'])
        m = (run.tf >= run.ride[0]) & (run.tf <= run.ride[1]); s, dd, _ = cor.project(run.fx[m], run.fy[m])
        rows.append(dict(run=run.run, dir=run.dir, n=int(m.sum()), d_median=float(np.median(np.abs(dd))), d_p95=float(np.percentile(np.abs(dd), 95)), d_max=float(np.abs(dd).max()), s_start=float(s[0]), s_end=float(s[-1]), monotone_frac=float(np.mean(np.diff(s) * (1 if run.dir == 'AB' else -1) >= -0.5))))
    df = pd.DataFrame(rows); print(df.round(2).to_string(index=False)); print(f"median of run medians {df.d_median.median():.2f} m, worst p95 {df.d_p95.max():.1f} m, worst max {df.d_max.max():.1f} m")

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--build', default=''); ap.add_argument('--validate', default='')
    a = ap.parse_args()
    if a.build == 'route1': build_route1()
    if a.validate: validate(a.validate)
