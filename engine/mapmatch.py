"""Map matching for the general mode (step 7): Newson-Krumm HMM over the campus OSM graph, heading-gated, fixed-lag Viterbi.

    mm = MapMatcher('data/map/snu_osm_highways_900m.json', lat0, lon0)
    res = mm.step(t, x, y, psi)      # every MM_DT seconds; returns None or dict(seg, x, y, bearing, conf, lag_s, straight)
Emission: N(perpendicular distance; SIG_Z) x heading gate (|psi - edge bearing| < HEAD_GATE, else x HEAD_PEN); candidates within
R_CAND m. Transition: exp(-|route distance - DR displacement| / BETA) with the route distance from a bounded Dijkstra over the
node graph (segments of one way share nodes; junction nodes are shared between ways). Output = the state LAG_S seconds ago on the
current best path (causal, <= 3 s lag), with the confidence = log-probability margin of the best path over the runner-up.
Feedback hooks used by replay.py: the matched edge bearing (oriented by travel) as a soft heading prior when confident and the
edge is straight, and cross-track = 0 to the matched edge as a delayed position pseudo-measurement.
"""
import json, math, heapq
import numpy as np
from session import local_xy

SIG_Z = 5.0; R_CAND = 25.0; HEAD_GATE = math.radians(60.0); HEAD_PEN = 0.05; BETA = 5.0; LAG_S = 3.0; MM_DT = 0.5; CONF_MIN = math.log(20.0)

class MapMatcher:
    def __init__(self, osm_json, lat0, lon0, keep_types=None):
        j = json.load(open(osm_json)); ways = [w for w in j['elements'] if w['type'] == 'way' and (keep_types is None or w.get('tags', {}).get('highway') in keep_types)]
        self.nodes = {}; self.adj = {}; segs = []
        for w in ways:
            ids = w['nodes']; geo = w['geometry']
            for nid, g in zip(ids, geo):
                if nid not in self.nodes:
                    x, y = local_xy(g['lat'], g['lon'], lat0, lon0); self.nodes[nid] = (float(x), float(y))
            for a, b in zip(ids[:-1], ids[1:]):
                pa, pb = self.nodes[a], self.nodes[b]; L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
                if L < 0.1: continue
                segs.append((a, b, pa[0], pa[1], pb[0], pb[1], L, w['id'])); self.adj.setdefault(a, []).append((b, L)); self.adj.setdefault(b, []).append((a, L))
        self.seg = segs; A = np.array([[s[2], s[3], s[4], s[5], s[6]] for s in segs]); self.ax, self.ay, self.bx, self.by, self.L = A.T
        self.tx = (self.bx - self.ax) / self.L; self.ty = (self.by - self.ay) / self.L
        self.reset()
    def reset(self): self.trellis = []; self.t_last = None; self.last_xy = None
    def _project(self, x, y):
        u = np.clip(((x - self.ax) * self.tx + (y - self.ay) * self.ty) / self.L, 0.0, 1.0); cx = self.ax + u * self.L * self.tx; cy = self.ay + u * self.L * self.ty
        return u, cx, cy, np.hypot(x - cx, y - cy)
    def _route_dist(self, i, ui, j, uj, bound):
        """Graph distance between point ui on segment i and point uj on segment j, capped at bound."""
        if i == j: return abs(ui - uj) * self.L[i]
        si, sj = self.seg[i], self.seg[j]
        starts = [(si[0], ui * self.L[i]), (si[1], (1 - ui) * self.L[i])]; ends = {sj[0]: uj * self.L[j], sj[1]: (1 - uj) * self.L[j]}
        best = bound; pq = [(d, n) for n, d in starts]; heapq.heapify(pq); dist = {n: d for n, d in starts}
        while pq:
            d, n = heapq.heappop(pq)
            if d > best or d > dist.get(n, 1e18): continue
            if n in ends: best = min(best, d + ends[n]); continue
            for m, L in self.adj.get(n, []):
                nd = d + L
                if nd < dist.get(m, 1e18) and nd < best: dist[m] = nd; heapq.heappush(pq, (nd, m))
        return best
    def step(self, t, x, y, psi):
        if self.t_last is not None and t - self.t_last < MM_DT - 1e-6: return self.current()
        u, cx, cy, d = self._project(x, y); cand = np.where(d < R_CAND)[0]
        if len(cand) == 0: self.t_last = t; self.last_xy = (x, y); return None
        bear = np.arctan2(self.ty[cand], self.tx[cand]); dh = np.abs((bear - psi + np.pi) % (2 * np.pi) - np.pi); dh = np.minimum(dh, np.pi - dh)   # undirected edge
        logem = -0.5 * (d[cand] / SIG_Z) ** 2 + np.where(dh < HEAD_GATE, 0.0, math.log(HEAD_PEN))
        if not self.trellis:
            col = [dict(seg=int(c), u=float(u[c]), x=float(cx[c]), y=float(cy[c]), lp=float(le), back=None) for c, le in zip(cand, logem)]
        else:
            prev = self.trellis[-1]; disp = math.hypot(x - self.last_xy[0], y - self.last_xy[1]); col = []
            for c, le in zip(cand, logem):
                best = (-1e18, None)
                for pi, p in enumerate(prev):
                    rd = self._route_dist(p['seg'], p['u'], int(c), float(u[c]), disp + 3 * BETA * 6)
                    lp = p['lp'] - abs(rd - disp) / BETA
                    if lp > best[0]: best = (lp, pi)
                col.append(dict(seg=int(c), u=float(u[c]), x=float(cx[c]), y=float(cy[c]), lp=float(best[0] + le), back=best[1]))
        self.trellis.append(col); self.times = getattr(self, 'times', []) + [t]
        if len(self.trellis) > int(LAG_S / MM_DT) + 20: self.trellis = self.trellis[-(int(LAG_S / MM_DT) + 20):]; self.times = self.times[-(int(LAG_S / MM_DT) + 20):]
        self.t_last = t; self.last_xy = (x, y); return self.current()
    def current(self):
        """State LAG_S ago on the best current path; bearing oriented by the path's travel; confidence = margin over the runner-up."""
        if not self.trellis: return None
        col = self.trellis[-1]; lps = sorted([c['lp'] for c in col], reverse=True); conf = (lps[0] - lps[1]) if len(lps) > 1 else 10.0
        k = max(0, len(self.trellis) - 1 - int(round(LAG_S / MM_DT))); i = int(np.argmax([c['lp'] for c in col])); path = []
        for step in range(len(self.trellis) - 1, -1, -1):
            node = self.trellis[step][i]; path.append(node)
            if node['back'] is None or step == 0: break
            i = node['back']
        path = path[::-1]; idx = k - (len(self.trellis) - len(path))
        if idx < 0 or idx >= len(path): return None
        n = path[idx]; s = self.seg[n['seg']]; tx, ty = self.tx[n['seg']], self.ty[n['seg']]
        # orientation from the path's progress along the segment (or across segments)
        sgn = 1.0
        if idx + 1 < len(path):
            m = path[idx + 1]; sgn = 1.0 if (m['x'] - n['x']) * tx + (m['y'] - n['y']) * ty >= 0 else -1.0
        elif idx > 0:
            m = path[idx - 1]; sgn = 1.0 if (n['x'] - m['x']) * tx + (n['y'] - m['y']) * ty >= 0 else -1.0
        bearing = math.atan2(sgn * ty, sgn * tx)
        straight = all(path[j]['seg'] == n['seg'] for j in range(max(0, idx - 2), min(len(path), idx + 3))) and self.L[n['seg']] > 20.0
        return dict(seg=n['seg'], x=n['x'], y=n['y'], bearing=bearing, conf=float(conf), confident=bool(conf > CONF_MIN), straight=bool(straight), t=self.times[max(0, len(self.times) - 1 - int(round(LAG_S / MM_DT)))], tx=float(sgn * tx), ty=float(sgn * ty))
