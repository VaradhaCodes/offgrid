"""Road-network particle filter for the outage (PS capability 3: map matching with kinematic constraints), car track step 10c.

Graph: OSM drivable ways around the cut point (downloaded with only the cut position, radius 2.5 km), split into directed
segments (one-way tags and motorways/roundabouts honoured). Particle = (segment, arc length on it, speed scale); at a node the
particle continues onto a random outgoing segment (no U-turn unless dead end). Every tick it advances by v_model * scale * dt;
every second its weight is multiplied by the heading likelihood (gyro heading from the bias-fitted yaw integration against the
segment heading, sigma SIG_PSI). Systematic resampling at ESS < N/2 with scale jitter. Output = weighted mean position (plus
the lateral offset measured at the cut). If the road lock is lost (no candidate at the cut, or the best particle's heading
disagrees for LOST_S seconds) the output falls back to free dead reckoning from the last road-locked position.
"""
import json, math
import numpy as np

M_PER_DEG_LAT = 111320.0

class Graph:
    def __init__(self, osm_json, lat0, lon0):
        mlon = M_PER_DEG_LAT * math.cos(math.radians(lat0)); nodes = {}; segs = []
        for w in osm_json['elements']:
            if w.get('type') != 'way' or 'geometry' not in w: continue
            tg = w.get('tags', {}); hw = tg.get('highway', ''); ow = tg.get('oneway', 'no')
            if tg.get('service') in ('parking_aisle', 'driveway') or tg.get('access') in ('private', 'no'): continue
            one = ow in ('yes', 'true', '1') or hw in ('motorway', 'motorway_link') or tg.get('junction') in ('roundabout', 'circular'); rev_only = ow == '-1'
            ids = w['nodes']; geo = w['geometry']
            for nid, g in zip(ids, geo): nodes[nid] = ((g['lon'] - lon0) * mlon, (g['lat'] - lat0) * M_PER_DEG_LAT)
            for a, b in zip(ids[:-1], ids[1:]):
                if a == b: continue
                if not rev_only: segs.append((a, b, hw))
                if not one or rev_only: segs.append((b, a, hw))
        self.nid = {n: i for i, n in enumerate(nodes)}; self.P = np.array([nodes[n] for n in nodes], float).reshape(-1, 2)
        A = np.array([self.nid[s[0]] for s in segs], int); B = np.array([self.nid[s[1]] for s in segs], int)
        self.A, self.B = A, B; d = self.P[B] - self.P[A]; self.L = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-3); self.U = d / self.L[:, None]
        self.H = np.arctan2(d[:, 1], d[:, 0]); self.hw = np.array([s[2] for s in segs])
        order = np.argsort(A, kind='stable'); self.out = order; cnt = np.bincount(A, minlength=len(self.P)); self.out_start = np.concatenate([[0], np.cumsum(cnt)]); self.out_cnt = cnt
        key = {(a, b): i for i, (a, b) in enumerate(zip(A, B))}; self.rev = np.array([key.get((b, a), -1) for a, b in zip(A, B)])
    def candidates(self, p, psi, r=25.0, dpsi=math.radians(50)):
        ap = p[None, :] - self.P[self.A]; u = np.clip((ap * self.U).sum(1), 0, self.L); c = self.P[self.A] + u[:, None] * self.U
        dist = np.hypot(*(c - p[None, :]).T); dh = np.abs((self.H - psi + np.pi) % (2 * np.pi) - np.pi)
        ok = (dist < r) & (dh < dpsi); return np.where(ok)[0], u[ok], dist[ok], dh[ok], (self.U[ok, 0] * (p[1] - c[ok, 1]) - self.U[ok, 1] * (p[0] - c[ok, 0]))

def run_pf(g, p0, psi_g, v, dt, n=1000, sig_psi=12.0, sig_scale=0.06, upd=10, lost_s=6.0, lost_deg=35.0, rng=None, keep_offset=True, sig_d=6.0, sig_h0=15.0, walk=0.0, psi_grow=0.0, out_mode='mean', sig_rel=0.0, w_rel=30, vwalk=0.0):
    """p0: position at the cut; psi_g[k], v[k], dt[k] for the outage ticks. Returns (n_ticks, 2) positions and a status dict."""
    rng = rng or np.random.default_rng(0); T = len(v)
    cs, us, ds, dhs, offs = g.candidates(np.asarray(p0, float), psi_g[0])
    if len(cs) == 0: return None, dict(status='no_candidate')
    lw = -0.5 * (ds / sig_d) ** 2 - 0.5 * (np.degrees(dhs) / sig_h0) ** 2; pw = np.exp(lw - lw.max()); pw /= pw.sum()
    pick = rng.choice(len(cs), n, p=pw); seg = cs[pick].copy(); s = us[pick].copy(); off = offs[pick].copy() if keep_offset else np.zeros(n)
    scale = 1.0 + sig_scale * rng.standard_normal(n); w = np.full(n, 1.0 / n); acc = np.zeros(n); bv = np.zeros(n)
    out = np.zeros((T, 2)); bad = 0.0; lost_at = None; sig = math.radians(sig_psi); rh = np.zeros((n, w_rel)); srel = math.radians(sig_rel) if sig_rel > 0 else 0.0
    for k in range(T):
        if vwalk > 0: bv += vwalk * math.sqrt(dt[k]) * rng.standard_normal(n)       # slowly varying speed error of the model
        s += np.maximum(v[k] * scale + bv, 0.0) * dt[k]
        if walk > 0: s += walk * math.sqrt(dt[k]) * rng.standard_normal(n)
        s = np.maximum(s, 0.0)
        for _ in range(50):
            over = s > g.L[seg]
            if not over.any(): break
            idx = np.where(over)[0]; s[idx] -= g.L[seg[idx]]; node = g.B[seg[idx]]; cnt = g.out_cnt[node]; st = g.out_start[node]
            r = rng.integers(0, np.maximum(cnt, 1)); nxt = np.where(cnt > 0, g.out[st + np.minimum(r, np.maximum(cnt - 1, 0))], seg[idx])
            uturn = (nxt == g.rev[seg[idx]]) & (cnt > 1)
            if uturn.any():                                             # avoid U-turns: take the next outgoing segment instead
                r2 = (r[uturn] + 1) % cnt[uturn]; nxt[uturn] = g.out[st[uturn] + r2]
            dead = cnt == 0; s[idx[dead]] = g.L[seg[idx[dead]]]; seg[idx] = nxt
        dh = (g.H[seg] - psi_g[k] + np.pi) % (2 * np.pi) - np.pi; acc += dh ** 2
        if srel: rh[:, k % w_rel] = g.H[seg]
        if (k + 1) % upd == 0:
            sg2 = sig ** 2 + (math.radians(psi_grow) * (k + 1) / 600.0) ** 2; lw = np.log(w + 1e-300) - 0.5 * acc / upd / sg2
            if srel and k >= w_rel:                                    # turn timing: road heading change over the last w_rel ticks vs the gyro's
                dr = (rh[:, k % w_rel] - rh[:, (k + 1) % w_rel] + np.pi) % (2 * np.pi) - np.pi; dg = (psi_g[k] - psi_g[k - w_rel + 1] + np.pi) % (2 * np.pi) - np.pi
                lw = lw - 0.5 * ((dr - dg) / srel) ** 2
            lw -= lw.max(); w = np.exp(lw); w /= w.sum(); acc[:] = 0.0
            best = np.degrees(np.sqrt(np.sum(w * dh ** 2)))
            bad = bad + upd * dt[k] if best > lost_deg else 0.0
            if bad >= lost_s and lost_at is None: lost_at = k
            ess = 1.0 / np.sum(w ** 2)
            if ess < n / 2:
                pos = (rng.random() + np.arange(n)) / n; i = np.searchsorted(np.cumsum(w), pos); i = np.minimum(i, n - 1)
                seg, s, off, scale, rh, bv = seg[i], s[i], off[i], scale[i] * (1.0 + 0.01 * rng.standard_normal(n)), rh[i], bv[i]; w = np.full(n, 1.0 / n)
        pts = g.P[g.A[seg]] + np.minimum(s, g.L[seg])[:, None] * g.U[seg]
        if keep_offset: pts = pts + off[:, None] * np.column_stack([-g.U[seg, 1], g.U[seg, 0]])
        out[k] = (w[:, None] * pts).sum(0) if out_mode == 'mean' else pts[np.argmax(w)]
    return out, dict(status='ok' if lost_at is None else 'lost', lost_at=lost_at, scale=float(np.sum(w * scale)), seg=seg, s=s, w=w)

def load_graph(fn):
    j = json.load(open(fn)); c = j['cut']; return Graph(j, c['lat0'], c['lon0'])
