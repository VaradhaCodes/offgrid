"""Raw IDR Logger session loader shared by qa.py, align.py, heading.py, evaluate.py.

All times are seconds since the SESSION_START event. This is offline tooling (pandas is fine here);
runtime code lives in the numpy-only modules.

    from session import Session
    s = Session('data/route1/sessions/20260905_003612_SNU_AJB_AB_run1')
    s.acc / s.gyr        DataFrames: t_s, ax..az / gx..gz  (deduplicated, sorted)
    s.fix                GNSS fixes: t_s, lat, lon, alt, acc_h, speed, speed_acc, bearing, bearing_acc, n_sats_used, is_mock, x_m, y_m
    s.epochs             per-fix satellite summary from gnss_status: t_s, n_used, n_vis, cn0_used_mean
    s.calib / s.ride / s.stop   (t_start, t_end) windows in seconds
    s.imu_native()       gyro linearly interpolated onto accel timestamps: t_s, ax..gz
"""
import json, math
from pathlib import Path
import numpy as np, pandas as pd

M_PER_DEG_LAT = 111320.0

def local_xy(lat, lon, lat0, lon0):
    mlon = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    return (np.asarray(lon, dtype=float) - lon0) * mlon, (np.asarray(lat, dtype=float) - lat0) * M_PER_DEG_LAT

def geodist_m(lat1, lon1, lat2, lon2):
    x, y = local_xy(lat2, lon2, lat1, lon1)
    return float(np.hypot(x, y))

def robust_gyro_bias(t, G, chunk_s=1.0, max_mean=0.01, min_quiet=3):
    """Gyro bias from a 'stationary' window while rejecting slow rider/bike movements.
    1 s chunks; keep the quietest half by variance; drop chunks whose |mean| > max_mean rad/s; average the rest.
    Returns (bias[3], quiet_fraction, n_chunks)."""
    chunks = []; t0 = t[0]
    while t0 + chunk_s <= t[-1]:
        m = (t >= t0) & (t < t0 + chunk_s)
        if m.sum() > 20: chunks.append((G[m].var(axis=0).sum(), np.abs(G[m].mean(0)).max(), G[m].mean(0)))
        t0 += chunk_s
    if not chunks: return G.mean(0), 0.0, 0
    chunks.sort(key=lambda c: c[0])
    quiet = [c for c in chunks[:max(6, len(chunks) // 2)] if c[1] < max_mean]
    qfrac = sum(1 for c in chunks if c[1] < max_mean) / len(chunks)
    if len(quiet) < min_quiet: return np.median(np.array([c[2] for c in chunks]), axis=0), qfrac, len(chunks)
    return np.mean([c[2] for c in quiet], axis=0), qfrac, len(chunks)

class Session:
    def __init__(self, path, load_status=True, load_extra=True):
        self.dir = Path(path); self.name = self.dir.name
        self.meta = json.load(open(self.dir / 'session.json'))
        ev = pd.read_csv(self.dir / 'events.csv')
        self.t0_ns = int(ev.loc[ev['type'] == 'SESSION_START', 't_ns'].iloc[0])
        self.event_list = [(r.type, (int(r.t_ns) - self.t0_ns) / 1e9, str(r.text)) for r in ev.itertuples()]
        self.events = {}
        for typ, t, _ in self.event_list: self.events.setdefault(typ, t)
        e = self.events
        self.t_end = e.get('SESSION_END', self.event_list[-1][1])
        self.calib = (e.get('CALIB_START', 0.0), e.get('CALIB_END', np.nan))
        self.ride = (e.get('RIDE_START', e.get('CALIB_END', np.nan)), e.get('STOP_CALIB_START', self.t_end))
        self.stop = (e.get('STOP_CALIB_START', np.nan), e.get('STOP_CALIB_END', self.t_end))
        self.acc, self.acc_stats = self._load_imu('acc.csv', ['ax', 'ay', 'az'])
        self.gyr, self.gyr_stats = self._load_imu('gyr.csv', ['gx', 'gy', 'gz'])
        self.fix = self._load_fix()
        self.epochs = self._load_status() if load_status and (self.dir / 'gnss_status.csv').exists() else None
        self.sys = self.gamerot = None
        if load_extra:
            if (self.dir / 'sys.csv').exists():
                self.sys = pd.read_csv(self.dir / 'sys.csv'); self.sys['t_s'] = (self.sys['t_ns'] - self.t0_ns) / 1e9
            if (self.dir / 'gamerot.csv').exists():
                self.gamerot = pd.read_csv(self.dir / 'gamerot.csv'); self.gamerot['t_s'] = (self.gamerot['t_ns'] - self.t0_ns) / 1e9

    # ---- metadata shortcuts
    @property
    def direction(self): return self.meta.get('direction', '?')
    @property
    def run_no(self): return int(self.meta.get('run_no', -1))
    @property
    def rider(self): return self.meta.get('rider_id', '?')
    @property
    def route(self): return self.meta.get('route_id', '?')

    def _load_imu(self, fn, cols):
        df = pd.read_csv(self.dir / fn, usecols=['t_ns'] + cols)
        tn = df['t_ns'].values.astype(np.int64)
        stats = dict(rows=len(df), dups=int(len(df) - len(np.unique(tn))), nonmono=int(np.sum(np.diff(tn) < 0)))
        df = df.drop_duplicates('t_ns').sort_values('t_ns').reset_index(drop=True)
        df.insert(0, 't_s', (df['t_ns'].values - self.t0_ns) / 1e9)
        dt = np.diff(df['t_ns'].values) / 1e6
        stats.update(median_dt_ms=float(np.median(dt)), p99_dt_ms=float(np.percentile(dt, 99)), max_dt_ms=float(dt.max()),
                     gaps_over_50ms=int(np.sum(dt > 50)), median_hz=float(1000.0 / np.median(dt)),
                     t_first=float(df['t_s'].iloc[0]), t_last=float(df['t_s'].iloc[-1]))
        return df, stats

    def _load_fix(self):
        f = pd.read_csv(self.dir / 'gnss_fix.csv')
        f = f.drop_duplicates('t_ns').sort_values('t_ns').reset_index(drop=True)
        f.insert(0, 't_s', (f['t_ns'].values - self.t0_ns) / 1e9)
        a = self.meta.get('start_anchor') or {}
        lat0 = a.get('lat', float(f['lat'].iloc[0])); lon0 = a.get('lon', float(f['lon'].iloc[0]))
        f['x_m'], f['y_m'] = local_xy(f['lat'].values, f['lon'].values, lat0, lon0)
        self.lat0, self.lon0 = lat0, lon0
        for c in ('is_mock', 'has_speed', 'has_bearing'):
            if c in f: f[c] = f[c].astype(str).str.lower().eq('true')
        return f

    def _load_status(self):
        st = pd.read_csv(self.dir / 'gnss_status.csv', usecols=['t_ns', 'cn0', 'used_in_fix'])
        st['used'] = st['used_in_fix'].astype(str).str.lower().eq('true')
        g = st.groupby('t_ns')
        ep = pd.DataFrame({'n_vis': g.size(), 'n_used': g['used'].sum(),
                           'cn0_used_mean': g.apply(lambda d: d.loc[d['used'], 'cn0'].mean() if d['used'].any() else np.nan, include_groups=False)}).reset_index()
        ep.insert(0, 't_s', (ep['t_ns'].values - self.t0_ns) / 1e9)
        return ep

    def imu_native(self):
        """Gyro linearly interpolated onto accelerometer timestamps (same as decode_session.py)."""
        ta = self.acc['t_s'].values; tg = self.gyr['t_s'].values
        out = pd.DataFrame({'t_s': ta, 'ax': self.acc['ax'].values, 'ay': self.acc['ay'].values, 'az': self.acc['az'].values})
        for c in ('gx', 'gy', 'gz'): out[c] = np.interp(ta, tg, self.gyr[c].values)
        return out

    @staticmethod
    def in_window(t, w, trim=0.0):
        return (t >= w[0] + trim) & (t <= w[1] - trim)

def find_sessions(paths):
    """Expand a list of paths (session dirs, or dirs of session dirs) into session dirs with session.json."""
    out = []
    for p in paths:
        p = Path(p)
        if (p / 'session.json').exists(): out.append(p)
        elif p.is_dir():
            out += sorted(q for q in p.iterdir() if (q / 'session.json').exists())
    return out
