package com.snu.idr.engine

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Heading and gyro bias, spec §4 / heading.py `HeadingFilter`, variant `kfpsic` (psi refined from the GNSS position course,
 * robust stand bias held). Runs at 100 Hz on bike-frame samples. The optional non-quiet-stand mode (spec §4.2) refines b_z.
 */
class HeadingFilter(
    biasB: DoubleArray, private val g: Double,
    pB0: Double = P_B_QUIET,
    private val refine: Boolean = true,
    private val refineBias: Boolean = false,
    private val bClamp: Double = B_CLAMP,
    var tilt: Boolean = true
) {
    val b = doubleArrayOf(biasB[0], biasB[1], biasB[2])
    private var b0 = biasB[2]
    var tTurn = -1e9; private set
    // quaternion bike -> world (w, x, y, z)
    var qw = 1.0; var qx = 0.0; var qy = 0.0; var qz = 0.0
    var psi = 0.0; private set
    val P = doubleArrayOf(Geo.rad(30.0) * Geo.rad(30.0), 0.0, 0.0, pB0)   // [P00, P01, P10, P11]
    var init = false; private set
    val aLp = DoubleArray(3); val wLp = DoubleArray(3)
    private var tPrev = Double.NaN
    private var I = 0.0
    private val histCap = 400
    private val histT = DoubleArray(histCap); private val histI = DoubleArray(histCap); private var histN = 0; private var histHead = 0
    var nMeas = 0; private set
    var nRej = 0; private set
    var nReset = 0; private set
    var lastNu = 0.0; private set
    var lastAccepted = false; private set
    val sigmaPsi: Double get() = sqrt(max(P[0], 0.0))
    val tPrevSample: Double get() = tPrev

    /** Replace the bias (bike frame) when the alignment changes; keeps the refined delta of b_z relative to the stand value. */
    fun setBias(biasB: DoubleArray) {
        val dz = b[2] - b0
        b[0] = biasB[0]; b[1] = biasB[1]; b0 = biasB[2]; b[2] = biasB[2] + dz
    }

    /** Rotate the low-pass states into a new bike frame (yaw by -dpsi about z) when psi changes. */
    fun rotateFrameZ(dpsi: Double) {
        val c = cos(-dpsi); val s = sin(-dpsi)
        var x = aLp[0]; var y = aLp[1]; aLp[0] = c * x - s * y; aLp[1] = s * x + c * y
        x = wLp[0]; y = wLp[1]; wLp[0] = c * x - s * y; wLp[1] = s * x + c * y
    }

    private fun qmulInPlace(bw: Double, bx: Double, by: Double, bz: Double) {   // q = q (x) b
        val w1 = qw; val x1 = qx; val y1 = qy; val z1 = qz
        qw = w1 * bw - x1 * bx - y1 * by - z1 * bz
        qx = w1 * bx + x1 * bw + y1 * bz - z1 * by
        qy = w1 * by - x1 * bz + y1 * bw + z1 * bx
        qz = w1 * bz + x1 * by - y1 * bx + z1 * bw
    }

    private fun qpremul(aw: Double, ax: Double, ay: Double, az: Double) {   // q = a (x) q
        val w2 = qw; val x2 = qx; val y2 = qy; val z2 = qz
        qw = aw * w2 - ax * x2 - ay * y2 - az * z2
        qx = aw * x2 + ax * w2 + ay * z2 - az * y2
        qy = aw * y2 - ax * z2 + ay * w2 + az * x2
        qz = aw * z2 + ax * y2 - ay * x2 + az * w2
    }

    private fun qnorm() {
        val n = sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
        qw /= n; qx /= n; qy /= n; qz /= n
    }

    /** q = q (x) exp(v) with exp(v) = (cos(|v|/2), v/|v| sin(|v|/2)). */
    private fun qmulRotvec(vx: Double, vy: Double, vz: Double) {
        val a = sqrt(vx * vx + vy * vy + vz * vz)
        if (a < 1e-12) return
        val s = sin(a / 2) / a
        qmulInPlace(cos(a / 2), vx * s, vy * s, vz * s)
        qnorm()
    }

    private fun yawOfQ(): Double = atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))

    fun step(t: Double, aB: DoubleArray, wB: DoubleArray) {
        if (tPrev.isNaN()) {
            tPrev = t
            aLp[0] = aB[0]; aLp[1] = aB[1]; aLp[2] = aB[2]; wLp[0] = wB[0]; wLp[1] = wB[1]; wLp[2] = wB[2]
            return
        }
        val dt = t - tPrev; tPrev = t
        val k = min(1.0, dt / 0.5)
        for (i in 0 until 3) { aLp[i] += k * (aB[i] - aLp[i]); wLp[i] += k * (wB[i] - wLp[i]) }
        val wzRaw = wB[2]; I += wzRaw * dt
        // ring of (t, I), keep last 400
        val idx = (histHead + histN) % histCap
        if (histN < histCap) { histT[idx] = t; histI[idx] = I; histN++ } else { histT[histHead] = t; histI[histHead] = I; histHead = (histHead + 1) % histCap }
        if (abs(wLp[2] - b[2]) > W_STRAIGHT) tTurn = t
        val w0 = wB[0] - b[0]; val w1 = wB[1] - b[1]; val w2 = wB[2] - b[2]
        qmulRotvec(w0 * dt, w1 * dt, w2 * dt)
        if (tilt) {
            val wn = Geo.norm3(wLp[0], wLp[1], wLp[2]); val an = Geo.norm3(aLp[0], aLp[1], aLp[2])
            if (wn < 0.15 && abs(an - g) < 1.0) {
                val ux = aLp[0] / an; val uy = aLp[1] / an; val uz = aLp[2] / an
                // u_pred = R^T e_z = (2(xz - wy), 2(yz + wx), 1 - 2(x^2 + y^2))
                val px = 2 * (qx * qz - qw * qy); val py = 2 * (qy * qz + qw * qx); val pz = 1 - 2 * (qx * qx + qy * qy)
                val ex = uy * pz - uz * py; val ey = uz * px - ux * pz; val ez = ux * py - uy * px
                val f = dt / TAU_TILT
                qmulRotvec(ex * f, ey * f, ez * f)
            }
        }
        psi = yawOfQ()
        val p00 = P[0]; val p01 = P[1]; val p11 = P[3]
        P[0] = p00 - 2 * dt * p01 + dt * dt * p11 + Q_PSI * dt
        P[1] = p01 - dt * p11; P[2] = P[1]
        P[3] = p11 + Q_B * dt
    }

    fun rotateYaw(dpsi: Double) {
        val h = dpsi / 2
        qpremul(cos(h), 0.0, 0.0, sin(h))
        qnorm()
        psi = yawOfQ()
    }

    private fun interpI(tq: Double): Double {
        if (histN == 0) return I
        val first = histHead; val last = (histHead + histN - 1) % histCap
        if (tq <= histT[first]) return histI[first]
        if (tq >= histT[last]) return histI[last]
        // binary search over the ring by logical index
        var lo = 0; var hi = histN - 1
        while (hi - lo > 1) {
            val mid = (lo + hi) ushr 1
            if (histT[(histHead + mid) % histCap] <= tq) lo = mid else hi = mid
        }
        val i0 = (histHead + lo) % histCap; val i1 = (histHead + hi) % histCap
        val f = (tq - histT[i0]) / (histT[i1] - histT[i0])
        return histI[i0] + f * (histI[i1] - histI[i0])
    }

    /**
     * GNSS course measurement (radians ENU, NaN = none) at fix time; v = ground speed; wz = the low-passed bike-frame gyro z
     * at the time the fix is processed. Returns true when the measurement was applied.
     */
    fun gnssCourse(tFix: Double, yawEnu: Double, v: Double, wz: Double): Boolean {
        lastAccepted = false
        if (yawEnu.isNaN() || v <= 1.5 || tPrev.isNaN()) return false
        if (!init) {
            rotateYaw(Geo.wrap(yawEnu - psi)); init = true
            P[0] = Geo.rad(10.0) * Geo.rad(10.0); P[1] = 0.0; P[2] = 0.0
            lastAccepted = true
            return true
        }
        if (!refine) return false
        if (tFix - tTurn < T_AFTER_TURN) return false
        val iTau = if (histN > 2) I - interpI(tFix - TAU) else 0.0
        val h = psi - iTau + TAU * b[2]
        val nu = Geo.wrap(yawEnu - h); lastNu = nu
        val r = (SIG_V / v) * (SIG_V / v) + (SIG_TAU * wz) * (SIG_TAU * wz) + SIG_B0 * SIG_B0
        // H = [1, TAU]
        var s = P[0] + 2 * TAU * P[1] + TAU * TAU * P[3] + r
        if (s <= 0) {
            P[0] = max(P[0], 1e-8); P[1] = 0.0; P[2] = 0.0; P[3] = max(P[3], 1e-10)
            s = P[0] + 2 * TAU * P[1] + TAU * TAU * P[3] + r
        }
        var k0 = (P[0] + TAU * P[1]) / s
        var k1 = (P[2] + TAU * P[3]) / s
        if (abs(nu) > 5 * sqrt(s)) {
            nRej++
            if (nRej >= N_REJECT) {
                rotateYaw(nu); P[0] = Geo.rad(10.0) * Geo.rad(10.0); P[1] = 0.0; P[2] = 0.0; nRej = 0; nReset++
            }
            return false
        }
        nRej = 0
        if (!refineBias || v < V_BIAS) k1 = 0.0
        rotateYaw(k0 * nu)
        b[2] = min(b0 + bClamp, max(b0 - bClamp, b[2] + k1 * nu))
        // Joseph form: P = (I - K H) P (I - K H)^T + K K^T r, H = [1, TAU]
        val m00 = 1 - k0; val m01 = -k0 * TAU; val m10 = -k1; val m11 = 1 - k1 * TAU
        val p00 = P[0]; val p01 = P[1]; val p10 = P[2]; val p11 = P[3]
        // A = M P
        val a00 = m00 * p00 + m01 * p10; val a01 = m00 * p01 + m01 * p11
        val a10 = m10 * p00 + m11 * p10; val a11 = m10 * p01 + m11 * p11
        // P' = A M^T + K K^T r
        val n00 = a00 * m00 + a01 * m01 + k0 * k0 * r
        val n01 = a00 * m10 + a01 * m11 + k0 * k1 * r
        val n10 = a10 * m00 + a11 * m01 + k1 * k0 * r
        val n11 = a10 * m10 + a11 * m11 + k1 * k1 * r
        P[0] = n00; P[1] = 0.5 * (n01 + n10); P[2] = P[1]; P[3] = n11
        nMeas++; lastAccepted = true
        return true
    }

    companion object {
        const val TAU = 0.5; const val SIG_V = 0.3; const val SIG_TAU = 0.2; val SIG_B0 = Geo.rad(2.0); const val TAU_TILT = 10.0
        const val W_STRAIGHT = 0.10; const val T_AFTER_TURN = 1.5; const val V_BIAS = 2.0
        val B_CLAMP = Geo.rad(0.3); val B_CLAMP_MOVED = Geo.rad(1.5); val B_CLAMP_LOOSE = Geo.rad(3.0)
        val Q_B = Geo.rad(0.002) * Geo.rad(0.002); val Q_PSI = Geo.rad(0.1) * Geo.rad(0.1); const val N_REJECT = 5
        val P_B_QUIET = Geo.rad(0.2) * Geo.rad(0.2); val P_B_MOVED = Geo.rad(0.3) * Geo.rad(0.3); val P_B_LOOSE = Geo.rad(2.0) * Geo.rad(2.0)
    }
}
