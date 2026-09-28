"""Learned outage speed for the car track (step 10c): a causal GRU over [60 s before the cut, 60 s outage] at 10 Hz.

Inputs per tick (all causal, no wheel/indicated speed, rpm or gear): CAN yaw rate, longitudinal and lateral acceleration (aligned
with other-family calibration), the held 1 Hz GNSS speed (before the cut: the latest fix; in the outage: the last healthy fix),
a GNSS-healthy flag and the time since the last healthy fix. Output: speed at every outage tick, as a change from the last fix.
Loss: speed MSE + the squared distance error at 20/40/60 s relative to the true distance (the protocol scores the endpoint).
Training cuts: every CUT_STEP fixes of every drive of the training families (windows with a time gap are skipped).
"""
import math, time
import numpy as np, torch, torch.nn as nn

PRE = 600; POST = 600; NCH = 6; USE_ALT = False; BIDIR = False

def drive_arrays(d):
    t = d['t']; tf = d['tf']; fv = d['fv']; li = np.searchsorted(tf, t, side='right') - 1; li = np.maximum(li, 0)
    held = fv[li].astype(np.float32); tsf = (t - tf[li]).astype(np.float32)
    cols = [d['yaw_b'] * 5.0, d['ax_b'] / 2.0, d['ay_b'] / 2.0, held / 30.0, np.ones(len(t)), tsf / 60.0]
    if USE_ALT:                                             # GNSS climb rate over the last 5 fixes (1 Hz altitude), held between fixes
        fk = np.clip(np.searchsorted(t, tf), 0, len(t) - 1); af = d['alt'][fk]; cl = np.zeros(len(tf)); cl[5:] = (af[5:] - af[:-5]) / np.maximum(tf[5:] - tf[:-5], 0.5)
        cols.append(np.clip(cl[li], -5, 5) / 2.0)
    X = np.stack(cols, 1).astype(np.float32)
    ok = np.concatenate([[True], np.diff(t) < 0.5])
    return X, d['gv'].astype(np.float32), t.astype(np.float64), ok

class Bank:
    """All drives concatenated on the device; a window is its cut tick k0 (first outage tick) in the concatenated timeline."""
    def __init__(self, drives, device):
        Xs, Vs, Ts, OKs, self.off = [], [], [], [], {}; o = 0
        for d in drives:
            X, v, t, ok = drive_arrays(d); self.off[d['seq']] = o; Xs.append(X); Vs.append(v); Ts.append(t); OKs.append(ok); o += len(t)
        self.X = torch.tensor(np.concatenate(Xs), device=device); self.V = torch.tensor(np.concatenate(Vs), device=device)
        self.T = torch.tensor(np.concatenate(Ts), device=device, dtype=torch.float64); self.OK = np.concatenate(OKs); self.dev = device
        self.rel = torch.arange(-PRE, POST, device=device)
    def cuts_for(self, d, step=3):
        """Training cuts: k0 = the tick of fix j+1 (fix j is the last healthy one), full window inside the drive, no gap, >= 50 m moved."""
        o = self.off[d['seq']]; t = d['t']; tf = d['tf']; n = len(t); ks = []
        cum = np.concatenate([[0.0], np.cumsum(d['gv'][1:] * np.diff(t))])
        okc = np.concatenate([[0], np.cumsum(~self.OK[o:o + n])])
        for j in range(PRE // 10 + 1, len(tf) - POST // 10 - 2, step):
            k0 = int(np.searchsorted(t, tf[j + 1]))
            if k0 - PRE < 1 or k0 + POST >= n: continue
            if okc[k0 + POST] - okc[k0 - PRE] > 0: continue
            if cum[k0 + POST - 1] - cum[k0] < 50: continue
            ks.append(o + k0)
        return ks
    def batch(self, k0s):
        k0 = torch.as_tensor(k0s, device=self.dev); idx = k0[:, None] + self.rel[None, :]
        X = self.X[idx].clone(); V = self.V[idx[:, PRE:]]; T = self.T[idx]
        v0 = self.X[k0 - 1, 3]; ts0 = self.X[k0 - 1, 5] * 60.0; t_last = T[:, PRE - 1]
        if X.shape[2] > 6: X[:, PRE:, 6] = self.X[k0 - 1, 6][:, None]
        X[:, PRE:, 3] = v0[:, None]; X[:, PRE:, 4] = 0.0; X[:, PRE:, 5] = ((T[:, PRE:] - t_last[:, None]).float() + ts0[:, None]) / 60.0
        dt = (T[:, PRE:] - T[:, PRE - 1:-1]).float()
        return X, V, dt, v0 * 30.0

class Net(nn.Module):
    def __init__(self, h=128, layers=2, conv=32, drop=0.1):
        super().__init__()
        nch = NCH + (1 if USE_ALT else 0); self.conv = nn.Sequential(nn.Conv1d(nch, conv, 5, padding=4), nn.GELU())            # causal: pad 4 left, cut the right side
        self.gru = nn.GRU(conv + nch, h, layers, batch_first=True, dropout=drop if layers > 1 else 0.0, bidirectional=BIDIR)
        self.head = nn.Sequential(nn.Linear(h * (2 if BIDIR else 1), 64), nn.GELU(), nn.Linear(64, 1))
    def forward(self, X, v0):
        c = self.conv(X.transpose(1, 2))[:, :, :X.shape[1]].transpose(1, 2)
        y, _ = self.gru(torch.cat([c, X], 2)); dv = self.head(y[:, PRE:]).squeeze(-1) * 10.0
        return torch.relu(v0[:, None] + dv)

def loss_fn(vh, V, dt, w_dist=1.0):
    e = vh - V; mse = (e ** 2).mean()
    cd = torch.cumsum(e * dt, 1); D = torch.cumsum(V * dt, 1)
    l = 0.0
    for q in (199, 399, POST - 1):
        l = l + ((cd[:, q] / (D[:, q] + 30.0)) ** 2).mean()
    return mse / 4.0 + w_dist * 100.0 * l / 3

def train(bank, cuts, epochs=25, bs=256, lr=2e-3, seed=0, h=128, layers=2, w_dist=1.0, log=None, aug_warp=0.0, mirror=False):
    torch.manual_seed(seed); np.random.seed(seed); net = Net(h, layers).to(bank.dev)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4); steps = epochs * math.ceil(len(cuts) / bs)
    sch = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.15); cuts = np.array(cuts); T0 = time.time()
    for ep in range(epochs):
        net.train(); perm = np.random.permutation(len(cuts)); tl = 0.0
        for i in range(0, len(cuts), bs):
            X, V, dt, v0 = bank.batch(cuts[perm[i:i + bs]])
            if aug_warp > 0:                                            # amplitude jitter of the inertial channels
                g = 1.0 + aug_warp * torch.randn(X.shape[0], 1, 3, device=X.device); X[:, :, :3] = X[:, :, :3] * g
            if mirror:                                                  # left/right mirror: yaw rate and lateral acceleration change sign together
                sg = torch.where(torch.rand(X.shape[0], 1, device=X.device) < 0.5, -1.0, 1.0); X[:, :, 0] = X[:, :, 0] * sg; X[:, :, 2] = X[:, :, 2] * sg
            with torch.autocast('cuda', dtype=torch.bfloat16):
                vh = net(X, v0)
            L = loss_fn(vh.float(), V, dt, w_dist); opt.zero_grad(); L.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); sch.step(); tl += float(L) * len(X)
        if log: log(f'  ep {ep + 1}/{epochs} loss {tl / len(cuts):.4f} ({time.time() - T0:.0f} s)')
    return net

@torch.no_grad()
def predict(net, bank, k0s, bs=512):
    net.eval(); out = []
    for i in range(0, len(k0s), bs):
        X, V, dt, v0 = bank.batch(k0s[i:i + bs])
        with torch.autocast('cuda', dtype=torch.bfloat16):
            out.append(net(X, v0).float().cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, POST), np.float32)
