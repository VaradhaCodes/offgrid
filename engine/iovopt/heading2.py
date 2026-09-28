"""Heading for the car track: least-squares yaw-rate bias (+ optional scale) from the healthy 1 Hz GNSS before the cut.

psi(t) = th0 + s * I(t) - b * t, I = integral of the (other-family aligned) CAN yaw rate. Fit on fixes in the last W s before
the cut with v > VMIN, measurement = GNSS course (from 1 Hz positions, centred 0.5 s back) or the receiver's 1 Hz bearing
(VBOX heading subsampled at the fix times: what a GNSS chip reports as course over ground). Weighted by speed.
"""
import numpy as np

def unwrap_near(a, ref):
    return ref + (a - ref + np.pi) % (2 * np.pi) - np.pi

def fit_heading(d, m, W=120.0, vmin=3.0, src='bearing', fit_scale=False, lam_s=50.0, lat=0.0, tau=0.5, wpow=1.0, t_skip=0.0):
    t, tf = d['t'], d['tf']; i1 = m['i_cut']; t_cut = tf[i1]
    I = np.concatenate([[0.0], np.cumsum(0.5 * (d['yaw_b'][1:] + d['yaw_b'][:-1]) * np.diff(t))])
    sel = np.arange(max(0, i1 - int(W)), i1 + 1); sel = sel[(~d['withheld'][sel]) & (d['fv'][sel] > vmin) & (tf[sel] <= t_cut - t_skip)]
    if src == 'bearing':
        k = np.clip(np.searchsorted(t, tf[sel]), 0, len(t) - 1); z = d['gh'][k]; tz = tf[sel]           # 1 Hz receiver bearing (sampled at the fix)
    else:
        z = d['fcourse'][sel]; ok = np.isfinite(z); sel = sel[ok]; z = z[ok]; tz = tf[sel] - tau
    if len(sel) < 5: return None
    Iz = np.interp(tz - lat, t, I); z = np.unwrap(z)
    # unwrap the measurements against the integrated gyro so a full turn stays continuous
    z = Iz + np.unwrap(z - Iz)
    w = np.maximum(d['fv'][sel], 0.1) ** wpow; tt = tz - t_cut
    if fit_scale:
        A = np.column_stack([np.ones(len(tt)), Iz - Iz[-1], -tt]); prior = np.array([0.0, 1.0, 0.0])
        R = np.diag([0.0, lam_s, 0.0])
        Aw = A * w[:, None]; x = np.linalg.solve(A.T @ Aw + R, A.T @ (w * z) + R @ prior); th0, s, b = x
    else:
        A = np.column_stack([np.ones(len(tt)), -tt]); y = z - (Iz - Iz[-1]); Aw = A * w[:, None]; th0, b = np.linalg.solve(A.T @ Aw + 1e-9 * np.eye(2), A.T @ (w * y)); s = 1.0
    # heading at every tick: th0 is psi at the last used fix time reference (I relative to Iz[-1])
    psi = th0 + s * (np.interp(t - lat, t, I) - Iz[-1]) - b * (t - t_cut)
    return psi, dict(b=b, s=s, n=len(sel))

def fit_heading2(d, m, Wb=30.0, Ws=600.0, seg=60.0, vmin=3.0, lam_s=20.0, lat=0.0, th0_src='fit', n_th0=3, bias_prior=None, lam_b=0.0):
    """Two time scales: yaw scale s from the long healthy history (piecewise-constant bias per seg-second block, common s, ridge to 1),
    then bias b (and th0) from the last Wb s with s fixed. Measurement = 1 Hz receiver bearing at the fix times."""
    t, tf = d['t'], d['tf']; i1 = m['i_cut']; t_cut = tf[i1]
    I = np.concatenate([[0.0], np.cumsum(0.5 * (d['yaw_b'][1:] + d['yaw_b'][:-1]) * np.diff(t))])
    k = np.clip(np.searchsorted(t, tf), 0, len(t) - 1); zall = d['gh'][k]
    ok = (~d['withheld']) & (d['fv'] > vmin)
    s = 1.0
    if Ws > 0:
        sel = np.arange(max(0, i1 - int(Ws)), i1 + 1); sel = sel[ok[sel]]
        if len(sel) > 30:
            tz = tf[sel]; Iz = np.interp(tz - lat, t, I); z = Iz + np.unwrap(zall[sel] - Iz); blk = ((tz - tz[0]) // seg).astype(int); nb = blk.max() + 1
            # z = th_blk + s*Iz - b_blk*(tz - t_blk0): unknowns th_blk (nb), b_blk (nb), s
            A = np.zeros((len(sel), 2 * nb + 1)); A[np.arange(len(sel)), blk] = 1.0; t0b = np.array([tz[blk == j][0] if (blk == j).any() else 0 for j in range(nb)])
            A[np.arange(len(sel)), nb + blk] = -(tz - t0b[blk]); A[:, -1] = Iz - Iz[-1]
            R = np.zeros(2 * nb + 1); R[-1] = lam_s; w = np.maximum(d['fv'][sel], 0.1)
            x = np.linalg.solve(A.T @ (A * w[:, None]) + np.diag(R) + 1e-9 * np.eye(2 * nb + 1), A.T @ (w * z) + R * np.r_[np.zeros(2 * nb), 1.0]); s = float(x[-1])
    sel = np.arange(max(0, i1 - int(Wb)), i1 + 1); sel = sel[ok[sel]]
    if len(sel) < 3: return None
    tz = tf[sel]; Iz = np.interp(tz - lat, t, I); z = Iz + np.unwrap(zall[sel] - Iz); tt = tz - t_cut; w = np.maximum(d['fv'][sel], 0.1)
    y = z - s * (Iz - Iz[-1]); A = np.column_stack([np.ones(len(tt)), -tt]); P = np.diag([0.0, lam_b]); pr = np.array([0.0, bias_prior if bias_prior is not None else 0.0])
    th0, b = np.linalg.solve(A.T @ (A * w[:, None]) + P + 1e-9 * np.eye(2), A.T @ (w * y) + P @ pr)
    if th0_src == 'last':                                            # heading at the last fix(es) directly, bias from the fit
        th0 = float(np.mean(y[-n_th0:] + b * (-tt[-n_th0:]) * 0 - (-b) * tt[-n_th0:] * 0)) if False else float(np.mean(y[-n_th0:] + (-b) * (-tt[-n_th0:]) * 0 + b * tt[-n_th0:]))
    psi = th0 + s * (np.interp(t - lat, t, I) - Iz[-1]) - b * (t - t_cut)
    return psi, dict(b=b, s=s)
