package com.snu.idr.engine

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Phone -> bike alignment, spec §3 / align.py, causal version for the app.
 *   stand: gravity mean (trimmed 1 s each side) -> R1; robust gyro bias (1 s chunks, quietest half, |mean| < 0.01 rad/s);
 *          quiet check (quiet-chunk fraction >= 0.5 and net rotation <= 5 deg).
 *   ride:  psi_init from the mean horizontal specific force over the first speed-up window (t_m0 - 2 .. t_m0 + 6 s, samples with
 *          GNSS acceleration > 0.15 m/s^2); sway-axis psi from the band-passed horizontal levelled gyro over moving samples
 *          (first after 20 s of motion, then every 10 s; sign from psi_init); ride-time gravity in gated 10 s blocks (first block
 *          replaces the stand estimate, then EMA 0.8/0.2, moved-phone rule 3 deg on two consecutive blocks).
 * R_pb = Rz(-psi) R1. The engine reads [rPb], [biasP] and [gMag]; [version] increments when R_pb changes.
 */
class Aligner(private val fs: Double = 100.0) {
    // ---- outputs
    val rPb: DoubleArray = Mat3.identity()
    val r1: DoubleArray = Mat3.identity()
    val gRef = doubleArrayOf(0.0, 0.0, 9.81)
    var gMag = 9.81; private set
    val biasP = DoubleArray(3)
    var psi = 0.0; private set
    var psiInit = Double.NaN; private set
    var psiSway = Double.NaN; private set
    var psiSource = "none"; private set
    var standQuiet = true; private set
    var standQuietFrac = Double.NaN; private set
    var standNetRotDeg = Double.NaN; private set
    var standValid = false; private set
    var version = 0; private set
    var rideGravityBlocks = 0; private set
    var movedAtS = Double.NaN; private set
    var lastBlockAngleDeg = Double.NaN; private set
    var swayRatio = Double.NaN; private set
    var nMovingSamples = 0L; private set
    var tMotionStart = Double.NaN; private set
    val pitchRollYawDeg: DoubleArray get() = Mat3.euler(rPb)

    /** Override everything from an offline alignment (conformance mode). */
    fun setOverride(rPbIn: DoubleArray, biasPIn: DoubleArray, gMagIn: Double, quiet: Boolean) {
        System.arraycopy(rPbIn, 0, rPb, 0, 9); System.arraycopy(biasPIn, 0, biasP, 0, 3); gMag = gMagIn
        standQuiet = quiet; standValid = true; psiSource = "override"; overridden = true; version++
    }
    private var overridden = false

    // ---- stand accumulation
    private var standT0 = Double.NaN; private var standT1 = Double.NaN
    private var gSum = DoubleArray(3); private var gN = 0L
    private val chunkSum = DoubleArray(3); private val chunkSq = DoubleArray(3); private var chunkN = 0; private var chunkStart = Double.NaN
    private val chunks = ArrayList<DoubleArray>()   // [var_sum, |mean|max, mx, my, mz]
    private val rotSum = DoubleArray(3); private var rotT = 0.0; private var lastStandT = Double.NaN
    private var standWindowKnown = false

    fun standStart(t: Double) {
        standT0 = t; standT1 = Double.NaN; standWindowKnown = false
        gSum = DoubleArray(3); gN = 0; chunks.clear(); chunkN = 0; chunkStart = Double.NaN
        rotSum.fill(0.0); rotT = 0.0; lastStandT = Double.NaN
    }

    /** Called at CALIB_END: finalises gravity and bias from the samples seen so far. */
    fun standEnd(t: Double) {
        standT1 = t; standWindowKnown = true
        finishChunk()
        if (gN < 10) { standValid = false; return }
        gRef[0] = gSum[0] / gN; gRef[1] = gSum[1] / gN; gRef[2] = gSum[2] / gN
        gMag = Geo.norm3(gRef[0], gRef[1], gRef[2])
        val b = robustBias(); biasP[0] = b[0]; biasP[1] = b[1]; biasP[2] = b[2]
        // net rotation over the stand after bias removal
        val rx = rotSum[0] - biasP[0] * rotT; val ry = rotSum[1] - biasP[1] * rotT; val rz = rotSum[2] - biasP[2] * rotT
        standNetRotDeg = Geo.deg(Geo.norm3(rx, ry, rz))
        standQuiet = standQuietFrac >= 0.5 && standNetRotDeg <= 5.0
        standValid = true
        rebuild()
        psiSource = "none"
    }

    private fun finishChunk() {
        if (chunkN > 20) {
            var vs = 0.0; var mmax = 0.0; val m = DoubleArray(3)
            for (i in 0 until 3) { m[i] = chunkSum[i] / chunkN; val v = chunkSq[i] / chunkN - m[i] * m[i]; vs += v; mmax = max(mmax, abs(m[i])) }
            chunks.add(doubleArrayOf(vs, mmax, m[0], m[1], m[2]))
        }
        chunkN = 0; chunkSum.fill(0.0); chunkSq.fill(0.0)
    }

    /** session.robust_gyro_bias: quietest half by variance (at least 6), drop |mean| > 0.01, median of all if fewer than 3 remain. */
    private fun robustBias(): DoubleArray {
        if (chunks.isEmpty()) { standQuietFrac = 0.0; return doubleArrayOf(rotSum[0] / max(rotT, 1e-9), rotSum[1] / max(rotT, 1e-9), rotSum[2] / max(rotT, 1e-9)) }
        val sorted = chunks.sortedBy { it[0] }
        val keep = sorted.take(max(6, sorted.size / 2)).filter { it[1] < 0.01 }
        standQuietFrac = chunks.count { it[1] < 0.01 }.toDouble() / chunks.size
        if (keep.size < 3) {
            val out = DoubleArray(3)
            for (i in 0 until 3) { val vals = chunks.map { it[2 + i] }.sorted(); out[i] = if (vals.size % 2 == 1) vals[vals.size / 2] else 0.5 * (vals[vals.size / 2 - 1] + vals[vals.size / 2]) }
            return out
        }
        val out = DoubleArray(3)
        for (c in keep) for (i in 0 until 3) out[i] += c[2 + i] / keep.size
        return out
    }

    /** Phone-frame sample during the stand (called for every 100 Hz sample between standStart and standEnd). */
    fun standSample(t: Double, a: DoubleArray, w: DoubleArray) {
        if (standT0.isNaN()) return
        // trimmed window: 1 s after CALIB_START; the end trim is applied by ignoring the last second at standEnd is impossible
        // causally, so the gravity mean uses t >= t0 + 1 and the chunking simply stops at CALIB_END (the last partial chunk is dropped).
        if (t < standT0 + 1.0) return
        gSum[0] += a[0]; gSum[1] += a[1]; gSum[2] += a[2]; gN++
        if (chunkStart.isNaN()) chunkStart = t
        if (t >= chunkStart + 1.0) { finishChunk(); chunkStart += 1.0; while (t >= chunkStart + 1.0) chunkStart += 1.0 }
        for (i in 0 until 3) { chunkSum[i] += w[i]; chunkSq[i] += w[i] * w[i] }
        chunkN++
        if (!lastStandT.isNaN()) { val dt = t - lastStandT; for (i in 0 until 3) rotSum[i] += w[i] * dt; rotT += dt }
        lastStandT = t
    }

    private fun rebuild() {
        val nr = Mat3.fromGravity(gRef[0], gRef[1], gRef[2]); System.arraycopy(nr, 0, r1, 0, 9)
        Mat3.mul(Mat3.rotZ(-psi), r1, rPb)
        version++
    }

    // ---- ride
    private var rideT0 = Double.NaN
    private val nLp = max(1, Math.round(0.5 * fs).toInt())
    private val aLpRing = Array(3) { DoubleArray(nLp) }; private val wLpRing = Array(3) { DoubleArray(nLp) }; private var lpIdx = 0; private var lpN = 0
    private val aLpSum = DoubleArray(3); private val wLpSum = DoubleArray(3)
    val aLp = DoubleArray(3); val wLp = DoubleArray(3)
    // levelled horizontal gyro rings for the sway band-pass: 0.25 s and 2 s trailing means
    private val n25 = max(1, Math.round(0.25 * fs).toInt()); private val n200 = Math.round(2.0 * fs).toInt()
    private val wlRing = Array(2) { DoubleArray(n200) }; private var wlIdx = 0; private var wlN = 0
    private val s25 = DoubleArray(2); private val s200 = DoubleArray(2)
    private var m00 = 0.0; private var m01 = 0.0; private var m11 = 0.0
    private var nextSwayAt = Math.round(20.0 * fs)
    // first speed-up window: mean levelled horizontal specific force, low-passed; ring of the last 2 s for the pre-window
    private val fRing = Array(2) { DoubleArray(n200) }; private val fRingT = DoubleArray(n200); private var fIdx = 0; private var fN = 0
    private var fGateRing = BooleanArray(n200)
    private var fxSum = 0.0; private var fySum = 0.0; private var fCnt = 0; private var fxAll = 0.0; private var fyAll = 0.0; private var fAll = 0
    private var speedUpOpen = false; private var speedUpClosed = false
    // GNSS-derived gates
    private var vGnss = 0.0; private var aGnss = 0.0; private var tFixLast = Double.NaN; private var vFixLast = Double.NaN
    private val aG3 = DoubleArray(3); private var aG3n = 0
    private var vFilter = 0.0
    // ride-time gravity blocks
    private var blockStart = Double.NaN; private val blockSum = DoubleArray(3); private var blockN = 0
    private val gRun = DoubleArray(3); private var gRunValid = false; private var consecutiveMoved = 0
    private val lvl = DoubleArray(3)

    fun rideStart(t: Double) {
        rideT0 = t; blockStart = t; blockN = 0; blockSum.fill(0.0); gRunValid = false; consecutiveMoved = 0; rideGravityBlocks = 0
        lpIdx = 0; lpN = 0; aLpSum.fill(0.0); wLpSum.fill(0.0); wlIdx = 0; wlN = 0; s25.fill(0.0); s200.fill(0.0)
        m00 = 0.0; m01 = 0.0; m11 = 0.0; nMovingSamples = 0; nextSwayAt = Math.round(20.0 * fs)
        fIdx = 0; fN = 0; fxSum = 0.0; fySum = 0.0; fCnt = 0; fxAll = 0.0; fyAll = 0.0; fAll = 0; speedUpOpen = false; speedUpClosed = false
        tMotionStart = Double.NaN; tFixLast = Double.NaN; vFixLast = Double.NaN; aG3n = 0; vGnss = 0.0; aGnss = 0.0
    }

    /** A GNSS fix (healthy or not: used only for the alignment gates), speed in m/s. */
    fun onFix(t: Double, v: Double, healthy: Boolean) {
        if (!healthy) { return }
        if (!tFixLast.isNaN() && t > tFixLast) {
            val ag = (v - vFixLast) / (t - tFixLast)
            if (aG3n < 3) { aG3[aG3n] = ag; aG3n++ } else { aG3[0] = aG3[1]; aG3[1] = aG3[2]; aG3[2] = ag }
            var s = 0.0; for (i in 0 until aG3n) s += aG3[i]; aGnss = s / aG3n
            aGnssRaw = ag
        }
        tFixLast = t; vFixLast = v; vGnss = v
        if (tMotionStart.isNaN() && !rideT0.isNaN() && t >= rideT0 && v > 1.0) { tMotionStart = t; speedUpOpen = true }
    }
    private var aGnssRaw = 0.0

    /** The fusion filter's own speed, used for the gates while GNSS is withheld. */
    fun setFilterSpeed(v: Double) { vFilter = v }

    val gnssAccel: Double get() = aGnss

    /**
     * Phone-frame 100 Hz sample during the ride. [gnssHealthy] selects the GNSS speed (else the filter's) for the gates.
     * Returns true when R_pb changed on this sample.
     */
    fun rideSample(t: Double, a: DoubleArray, w: DoubleArray, gnssHealthy: Boolean): Boolean {
        if (!standValid || overridden) return false
        var changed = false
        // 0.5 s trailing means (phone frame; gyro bias removed)
        for (i in 0 until 3) {
            val wb = w[i] - biasP[i]
            if (lpN < nLp) { aLpSum[i] += a[i]; wLpSum[i] += wb } else { aLpSum[i] += a[i] - aLpRing[i][lpIdx]; wLpSum[i] += wb - wLpRing[i][lpIdx] }
            aLpRing[i][lpIdx] = a[i]; wLpRing[i][lpIdx] = wb
        }
        lpIdx = (lpIdx + 1) % nLp; if (lpN < nLp) lpN++
        for (i in 0 until 3) { aLp[i] = aLpSum[i] / lpN; wLp[i] = wLpSum[i] / lpN }
        val speed = if (gnssHealthy) vGnss else vFilter
        val moving = speed > 1.5
        // ---- levelled gyro for the sway axis: w_l = R1 (w - b)
        Mat3.apply(r1, w[0] - biasP[0], w[1] - biasP[1], w[2] - biasP[2], lvl)
        for (i in 0 until 2) {
            val old200 = if (wlN < n200) 0.0 else wlRing[i][wlIdx]
            val old25 = if (wlN < n25) 0.0 else wlRing[i][(wlIdx - n25 + n200) % n200]
            s200[i] += lvl[i] - old200; s25[i] += lvl[i] - old25
            wlRing[i][wlIdx] = lvl[i]
        }
        wlIdx = (wlIdx + 1) % n200; if (wlN < n200) wlN++
        if (moving) {
            val c25 = minOf(wlN, n25).toDouble(); val c200 = minOf(wlN, n200).toDouble()
            val bx = s25[0] / c25 - s200[0] / c200; val by = s25[1] / c25 - s200[1] / c200
            m00 += bx * bx; m01 += bx * by; m11 += by * by
            nMovingSamples++
            if (nMovingSamples >= nextSwayAt) { nextSwayAt += Math.round(10.0 * fs); if (recomputeSway()) changed = true }
        }
        // ---- first speed-up window: levelled specific force, low-passed (aLp levelled), gated on GNSS acceleration > 0.15
        Mat3.apply(r1, aLp[0], aLp[1], aLp[2], lvl)
        val fx = lvl[0]; val fy = lvl[1]
        val gated = aGnssRaw > 0.15
        // keep a 2 s ring so the pre-window (t_m0 - 2) is available when motion starts
        fRing[0][fIdx] = fx; fRing[1][fIdx] = fy; fRingT[fIdx] = t; fGateRing[fIdx] = gated; fIdx = (fIdx + 1) % n200; if (fN < n200) fN++
        if (speedUpOpen && !speedUpClosed) {
            if (fCnt == 0 && fAll == 0) {   // just opened: pull the pre-window from the ring
                for (j in 0 until fN) {
                    val i = (fIdx - fN + j + n200) % n200
                    if (fRingT[i] >= tMotionStart - 2.0) { fxAll += fRing[0][i]; fyAll += fRing[1][i]; fAll++; if (fGateRing[i]) { fxSum += fRing[0][i]; fySum += fRing[1][i]; fCnt++ } }
                }
            } else {
                fxAll += fx; fyAll += fy; fAll++
                if (gated) { fxSum += fx; fySum += fy; fCnt++ }
            }
            if (t >= tMotionStart + 6.0) {
                speedUpClosed = true
                val useGated = fCnt >= 0.5 * fs
                val mx = if (useGated) fxSum / fCnt else fxAll / max(fAll, 1); val my = if (useGated) fySum / fCnt else fyAll / max(fAll, 1)
                psiInit = atan2(my, mx)
                if (psiSway.isNaN()) { psi = psiInit; psiSource = "init"; rebuild(); changed = true }
                else if (cos(psiSway - psiInit) < 0) { psiSway = Geo.wrap(psiSway + PI); psi = psiSway; rebuild(); changed = true }
            }
        }
        // ---- ride-time gravity blocks
        val wn = Geo.norm3(wLp[0], wLp[1], wLp[2]); val an = Geo.norm3(aLp[0], aLp[1], aLp[2])
        val gate = wn < GATE_W && abs(an - gMag) < GATE_A && speed > 1.5 && abs(aGnss) < 0.3 && lpN >= nLp
        if (gate) { blockSum[0] += aLp[0]; blockSum[1] += aLp[1]; blockSum[2] += aLp[2]; blockN++ }
        if (t >= blockStart + BLOCK_S) {
            if (blockN > 0.2 * BLOCK_S * fs) {
                val gb = doubleArrayOf(blockSum[0] / blockN, blockSum[1] / blockN, blockSum[2] / blockN)
                if (!gRunValid) { System.arraycopy(gb, 0, gRun, 0, 3); gRunValid = true; lastBlockAngleDeg = 0.0 }
                else {
                    val ang = Mat3.angleDeg(gb[0], gb[1], gb[2], gRun[0], gRun[1], gRun[2]); lastBlockAngleDeg = ang
                    consecutiveMoved = if (ang > MOVE_DEG) consecutiveMoved + 1 else 0
                    if (consecutiveMoved >= 2) { System.arraycopy(gb, 0, gRun, 0, 3); consecutiveMoved = 0; movedAtS = t - rideT0 }
                    else for (i in 0 until 3) gRun[i] = 0.8 * gRun[i] + 0.2 * gb[i]
                }
                gRef[0] = gRun[0]; gRef[1] = gRun[1]; gRef[2] = gRun[2]; gMag = Geo.norm3(gRef[0], gRef[1], gRef[2])
                rideGravityBlocks++
                rebuild(); changed = true
            }
            blockStart += BLOCK_S; blockN = 0; blockSum.fill(0.0)
        }
        return changed
    }

    private fun recomputeSway(): Boolean {
        var ang = 0.5 * atan2(2 * m01, m00 - m11)
        val ex = cos(ang); val ey = sin(ang)
        val l1 = ex * (m00 * ex + m01 * ey) + ey * (m01 * ex + m11 * ey)
        swayRatio = l1 / max(m00 + m11 - l1, 1e-12)
        if (!psiInit.isNaN() && cos(ang - psiInit) < 0) ang += PI
        val newPsi = Geo.wrap(ang)
        psiSway = newPsi
        if (psiInit.isNaN()) return false   // sign unknown until the first speed-up has been seen
        psi = newPsi; psiSource = "sway"; rebuild()
        return true
    }

    companion object { const val MOVE_DEG = 3.0; const val BLOCK_S = 10.0; const val GATE_W = 0.15; const val GATE_A = 1.0 }
}
