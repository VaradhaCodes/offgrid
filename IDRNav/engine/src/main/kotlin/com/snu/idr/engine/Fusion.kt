package com.snu.idr.engine

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Fusion filter, spec §5 / filter.py `Filter`. General mode x = [px, py, v, k]; corridor mode x = [s, v, k].
 * 10 Hz tick: predict(t, psi) -> updateModel(v_m, sig_m, still) -> pending GNSS (updateGnss / gnssLost).
 * k is carried for parity with the Python arrays but disabled (kEst = false) on bicycle roads.
 */
class Fusion private constructor(val mode: Mode, val corridor: Corridor?, private val kEst: Boolean) {
    enum class Mode { GENERAL, CORRIDOR }

    val n = if (mode == Mode.GENERAL) 4 else 3
    val x = DoubleArray(n)
    val P = DoubleArray(n * n)
    var t = Double.NaN; private set
    var psi = 0.0; private set
    var tReturn = -1e9; private set
    var gnssOkPrev = true; private set
    var kOpen = false; private set
    var dHold = 0.0; private set
    var dTarget = 0.0; private set
    var dir = 0.0; private set
    var nRej = 0; private set
    var nReset = 0; private set
    var nGnssRejected = 0; private set
    var lastGnssApplied = false; private set

    // state history for delayed measurements: (t, a, b, v), last 40 ticks
    private val hCap = 40
    private val hT = DoubleArray(hCap); private val hA = DoubleArray(hCap); private val hB = DoubleArray(hCap); private val hV = DoubleArray(hCap)
    private var hN = 0; private var hHead = 0
    // GNSS speed history for the k gate (last 3)
    private val vgT = DoubleArray(3); private val vgV = DoubleArray(3); private var vgN = 0
    // corridor arc-length history (last 8)
    private val sT = DoubleArray(8); private val sS = DoubleArray(8); private var sN = 0
    private val proj = Corridor.Proj()
    private val tmp2 = DoubleArray(2)
    private val H = DoubleArray(4)
    private val K = DoubleArray(4)
    private val M = DoubleArray(16)
    private val Pn = DoubleArray(16)
    private val Pr = DoubleArray(16)

    companion object {
        const val SIG_A = 1.0; const val SIG_K0 = 0.05; const val T_K = 600.0; const val SIG_M_FLOOR = 0.15; const val SIG_VG = 0.3
        const val SIG_ZUPT = 0.05; const val LAG_POS = 0.5; const val LAG_V = 0.2; const val REC_INFL = 4.0; const val REC_S = 3.0
        const val K_VMIN = 2.0; const val K_AMAX = 0.3; const val N_REJECT = 5; const val GATE_SIG = 5.0

        fun general(x0: Double, y0: Double, kEst: Boolean = false): Fusion {
            val f = Fusion(Mode.GENERAL, null, kEst)
            f.x[0] = x0; f.x[1] = y0; f.x[2] = 0.0; f.x[3] = 1.0
            f.setDiag(9.0, 9.0, 1.0, SIG_K0 * SIG_K0)
            return f
        }

        fun corridor(cor: Corridor, s0: Double, d0: Double, kEst: Boolean = false): Fusion {
            val f = Fusion(Mode.CORRIDOR, cor, kEst)
            f.x[0] = s0; f.x[1] = 0.0; f.x[2] = 1.0
            f.setDiag(9.0, 1.0, SIG_K0 * SIG_K0)
            f.dHold = d0; f.dTarget = d0
            return f
        }
    }

    private fun setDiag(vararg d: Double) { java.util.Arrays.fill(P, 0.0); for (i in d.indices) P[i * n + i] = d[i] }

    /** The index of v in x. */
    val iv: Int get() = if (mode == Mode.GENERAL) 2 else 1
    val v: Double get() = x[iv]
    val k: Double get() = x[n - 1]
    val sigmaPos: Double get() = sqrt(max(P[0], 0.0))

    /** Carry the state of another filter into this one (mode switch); the position is re-initialised by the caller. */
    fun adoptFrom(o: Fusion) {
        x[iv] = o.x[o.iv]; x[n - 1] = o.x[o.n - 1]
        P[iv * n + iv] = o.P[o.iv * o.n + o.iv]
        t = o.t; psi = o.psi; tReturn = o.tReturn; gnssOkPrev = o.gnssOkPrev; kOpen = o.kOpen
        hN = 0; hHead = 0; vgN = o.vgN; System.arraycopy(o.vgT, 0, vgT, 0, 3); System.arraycopy(o.vgV, 0, vgV, 0, 3)
    }

    private fun hPush(t: Double, a: Double, b: Double, v: Double) {
        if (hN < hCap) { val i = (hHead + hN) % hCap; hT[i] = t; hA[i] = a; hB[i] = b; hV[i] = v; hN++ }
        else { hT[hHead] = t; hA[hHead] = a; hB[hHead] = b; hV[hHead] = v; hHead = (hHead + 1) % hCap }
    }

    fun predict(t: Double, psi: Double) {
        if (this.t.isNaN()) { this.t = t; this.psi = psi; return }
        val dt = t - this.t; this.t = t; this.psi = psi
        if (mode == Mode.GENERAL) {
            val c = cos(psi); val s = sin(psi)
            x[0] += x[2] * c * dt; x[1] += x[2] * s * dt
            // F = I + [F02 = c dt, F12 = s dt]; P = F P F^T + diag(0, 0, (SIG_A dt)^2, 0)
            val f02 = c * dt; val f12 = s * dt
            // compute P' = F P F^T explicitly
            // rows 0,1 change: P'[0][j] = P[0][j] + f02 P[2][j]; P'[1][j] = P[1][j] + f12 P[2][j]; then columns similarly
            for (j in 0 until 4) { Pn[0 * 4 + j] = P[0 * 4 + j] + f02 * P[2 * 4 + j]; Pn[1 * 4 + j] = P[1 * 4 + j] + f12 * P[2 * 4 + j]; Pn[2 * 4 + j] = P[2 * 4 + j]; Pn[3 * 4 + j] = P[3 * 4 + j] }
            for (i in 0 until 4) { val p0 = Pn[i * 4 + 0] + f02 * Pn[i * 4 + 2]; val p1 = Pn[i * 4 + 1] + f12 * Pn[i * 4 + 2]; Pn[i * 4 + 0] = p0; Pn[i * 4 + 1] = p1 }
            System.arraycopy(Pn, 0, P, 0, 16)
            P[2 * 4 + 2] += (SIG_A * dt) * (SIG_A * dt)
            hPush(t, x[0], x[1], x[2])
        } else {
            val f01 = dir * dt
            x[0] += dir * x[1] * dt
            for (j in 0 until 3) { Pn[0 * 3 + j] = P[0 * 3 + j] + f01 * P[1 * 3 + j]; Pn[1 * 3 + j] = P[1 * 3 + j]; Pn[2 * 3 + j] = P[2 * 3 + j] }
            for (i in 0 until 3) { Pn[i * 3 + 0] = Pn[i * 3 + 0] + f01 * Pn[i * 3 + 1] }
            System.arraycopy(Pn, 0, P, 0, 9)
            P[1 * 3 + 1] += (SIG_A * dt) * (SIG_A * dt)
            hPush(t, x[0], 0.0, x[1])
        }
        if (kEst && gnssOkPrev) P[(n - 1) * n + (n - 1)] += 2 * SIG_K0 * SIG_K0 / T_K * dt
    }

    /** Generic scalar update; H is length n. Returns false when gated out. */
    private fun update(nu: Double, R: Double): Boolean {
        // S = H P H^T + R
        var s = R
        for (i in 0 until n) { var acc = 0.0; for (j in 0 until n) acc += P[i * n + j] * H[j]; s += H[i] * acc }
        if (abs(nu) > GATE_SIG * sqrt(s)) return false
        for (i in 0 until n) { var acc = 0.0; for (j in 0 until n) acc += P[i * n + j] * H[j]; K[i] = acc / s }
        for (i in 0 until n) x[i] += K[i] * nu
        // M = I - K H
        for (i in 0 until n) for (j in 0 until n) M[i * n + j] = (if (i == j) 1.0 else 0.0) - K[i] * H[j]
        // Pr = M P M^T + K K^T R, then symmetrise into P
        for (i in 0 until n) for (j in 0 until n) { var acc = 0.0; for (l in 0 until n) acc += M[i * n + l] * P[l * n + j]; Pn[i * n + j] = acc }   // Pn = M P
        for (i in 0 until n) for (j in 0 until n) { var acc = 0.0; for (l in 0 until n) acc += Pn[i * n + l] * M[j * n + l]; Pr[i * n + j] = acc + K[i] * K[j] * R }
        for (i in 0 until n) for (j in 0 until n) P[i * n + j] = 0.5 * (Pr[i * n + j] + Pr[j * n + i])
        return true
    }

    private fun clearH() { for (i in 0 until 4) H[i] = 0.0 }

    fun updateModel(vM: Double, sigM: Double, still: Boolean) {
        val ik = n - 1; val kk = x[ik]
        if (!kEst || !kOpen) {
            val pk = P[ik * n + ik]
            for (j in 0 until n) { P[ik * n + j] = 0.0; P[j * n + ik] = 0.0 }
            P[ik * n + ik] = pk
        }
        clearH()
        if (still) {
            H[iv] = 1.0
            update(0.0 - x[iv], SIG_ZUPT * SIG_ZUPT)
            x[iv] = max(0.0, x[iv]); return
        }
        H[iv] = 1.0 / kk; H[ik] = -x[iv] / (kk * kk)
        if (!kEst || !kOpen) H[ik] = 0.0
        val sm = max(sigM, SIG_M_FLOOR)
        update(vM - x[iv] / kk, sm * sm)
        x[iv] = max(0.0, x[iv]); x[ik] = min(1.5, max(0.5, x[ik]))
    }

    /** State (a, b, v) at tMeas from the history, linear interpolation (np.interp clamps at the end). */
    private fun delayed(tMeas: Double, out: DoubleArray): Boolean {
        if (hN < 2) return false
        val first = hHead; val last = (hHead + hN - 1) % hCap
        if (tMeas < hT[first]) return false
        if (tMeas >= hT[last]) { out[0] = hA[last]; out[1] = hB[last]; out[2] = hV[last]; return true }
        var lo = 0; var hi = hN - 1
        while (hi - lo > 1) { val mid = (lo + hi) ushr 1; if (hT[(hHead + mid) % hCap] <= tMeas) lo = mid else hi = mid }
        val i0 = (hHead + lo) % hCap; val i1 = (hHead + hi) % hCap
        val f = (tMeas - hT[i0]) / (hT[i1] - hT[i0])
        out[0] = hA[i0] + f * (hA[i1] - hA[i0]); out[1] = hB[i0] + f * (hB[i1] - hB[i0]); out[2] = hV[i0] + f * (hV[i1] - hV[i0])
        return true
    }

    private val dl = DoubleArray(3)

    /** Healthy fix (the caller applies the outage gate). x, y in ENU metres; v = ground speed; accH = horizontal accuracy. */
    fun updateGnss(tFix: Double, xg: Double, yg: Double, vg: Double, accH: Double) {
        var infl = if ((t - tReturn) < REC_S) REC_INFL else 1.0
        if (!gnssOkPrev) { tReturn = t; infl = REC_INFL; vgN = 0 }
        gnssOkPrev = true
        val rp = (max(accH, 3.0) * infl) * (max(accH, 3.0) * infl)
        val rv = (SIG_VG * infl) * (SIG_VG * infl)
        if (vgN < 3) { vgT[vgN] = tFix; vgV[vgN] = vg; vgN++ } else { vgT[0] = vgT[1]; vgV[0] = vgV[1]; vgT[1] = vgT[2]; vgV[1] = vgV[2]; vgT[2] = tFix; vgV[2] = vg }
        val steady = vgN == 3 && abs(vgV[2] - vgV[0]) / max(vgT[2] - vgT[0], 0.5) < K_AMAX
        kOpen = steady && vg > K_VMIN && infl == 1.0
        lastGnssApplied = false
        if (mode == Mode.GENERAL) {
            if (delayed(tFix - LAG_POS, dl)) {
                var ok = 0
                clearH(); H[0] = 1.0; if (update(xg - dl[0], rp)) ok++
                clearH(); H[1] = 1.0; if (update(yg - dl[1], rp)) ok++
                if (ok < 2) {
                    nRej++; nGnssRejected++
                    if (nRej >= N_REJECT) {
                        x[0] = xg + (x[0] - dl[0]); x[1] = yg + (x[1] - dl[1])
                        P[0] = rp; P[1 * 4 + 1] = rp; P[1] = 0.0; P[4] = 0.0; nRej = 0; nReset++
                    }
                } else { nRej = 0; lastGnssApplied = true }
            }
            if (delayed(tFix - LAG_V, dl) && vg > 0.3) { clearH(); H[2] = 1.0; update(vg - dl[2], rv) }
        } else {
            val cor = corridor!!
            cor.project(xg, yg, proj); val sg = proj.s; dTarget = proj.d
            dHold += (dTarget - dHold) * (if (infl == 1.0) 1.0 else 0.3)
            if (sN < 8) { sT[sN] = tFix; sS[sN] = sg; sN++ } else { for (i in 0 until 7) { sT[i] = sT[i + 1]; sS[i] = sS[i + 1] }; sT[7] = tFix; sS[7] = sg }
            if (sN >= 4 && vg > 1.0) {
                val ds = sS[sN - 1] - sS[0]
                if (abs(ds) > 3.0) dir = if (ds > 0) 1.0 else -1.0
            }
            if (delayed(tFix - LAG_POS, dl)) { clearH(); H[0] = 1.0; lastGnssApplied = update(sg - dl[0], rp); if (!lastGnssApplied) nGnssRejected++ }
            if (delayed(tFix - LAG_V, dl) && vg > 0.3) { clearH(); H[1] = 1.0; update(vg - dl[2], rv) }
        }
    }

    fun gnssLost() { gnssOkPrev = false; kOpen = false }

    /** Seed the corridor direction and history (used when switching modes with known fixes). */
    fun seedDirection(d: Double) { dir = d }

    /**
     * Seed the state history with the initial (stationary) state so the first fix's delayed lookups (t_f - LAG) succeed, as they do
     * in replay.py where the filter exists from t = 0 with the same initial position.
     */
    fun seedHistory(tFix: Double) {
        if (!t.isNaN()) return
        val a = x[0]; val b = if (mode == Mode.GENERAL) x[1] else 0.0
        hPush(tFix - 4.0, a, b, 0.0); hPush(tFix, a, b, 0.0)
        t = tFix
    }

    fun position(out: DoubleArray) {
        if (mode == Mode.GENERAL) { out[0] = x[0]; out[1] = x[1]; return }
        val cor = corridor!!
        cor.point(x[0], out); cor.tangent(x[0], tmp2)
        val nx = -tmp2[1]; val ny = tmp2[0]
        out[0] += dHold * nx; out[1] += dHold * ny
    }

    /** Output heading in corridor mode: tangent direction times dir (NaN when the direction is unknown). */
    fun corridorHeading(): Double {
        val cor = corridor ?: return Double.NaN
        if (dir == 0.0) return Double.NaN
        val h = cor.heading(x[0])
        return if (dir > 0) h else Geo.wrap(h + Math.PI)
    }
}
