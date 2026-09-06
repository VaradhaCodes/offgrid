package com.snu.idr.engine

import kotlin.math.ceil

/** Receives 100 Hz phone-frame samples on the 10 ms grid: k = grid index (t = k * 0.01 s since session start). */
fun interface ImuSink {
    fun onSample(k: Long, t: Double, v: DoubleArray)   // v = [ax, ay, az, gx, gy, gz], reused buffer
}

/**
 * Native (~420 Hz) accelerometer + gyroscope -> 100 Hz grid (spec §2).
 * 1. gyro linearly interpolated onto accelerometer timestamps (session.imu_native);
 * 2. causal 4th-order Butterworth low-pass at 40 Hz as two second-order sections (direct form II transposed),
 *    coefficients from engine/export/resample_constants.json (fs 420 Hz); filter state started at the DC steady state of
 *    the first sample so the stand does not begin with a step transient;
 * 3. linear sampling at every grid time k * gridDt between the last two filtered native samples.
 * No allocation after construction.
 */
class Resampler(sos: Array<DoubleArray>, private val gridDt: Double = 0.01, private val sink: ImuSink) {
    private val nSec = sos.size
    private val b0 = DoubleArray(nSec) { sos[it][0] / sos[it][3] }
    private val b1 = DoubleArray(nSec) { sos[it][1] / sos[it][3] }
    private val b2 = DoubleArray(nSec) { sos[it][2] / sos[it][3] }
    private val a1 = DoubleArray(nSec) { sos[it][4] / sos[it][3] }
    private val a2 = DoubleArray(nSec) { sos[it][5] / sos[it][3] }
    private val z1 = Array(6) { DoubleArray(nSec) }
    private val z2 = Array(6) { DoubleArray(nSec) }
    private var filterInit = false

    // gyro ring (time-ordered)
    private val gCap = 4096
    private val gT = DoubleArray(gCap); private val gX = DoubleArray(gCap); private val gY = DoubleArray(gCap); private val gZ = DoubleArray(gCap)
    private var gHead = 0; private var gCount = 0   // oldest index, count
    // accel queue awaiting gyro coverage
    private val aCap = 4096
    private val aT = DoubleArray(aCap); private val aX = DoubleArray(aCap); private val aY = DoubleArray(aCap); private val aZ = DoubleArray(aCap)
    private var aHead = 0; private var aCount = 0
    private var lastAccT = Double.NEGATIVE_INFINITY
    private var lastGyrT = Double.NEGATIVE_INFINITY

    // last two filtered native samples
    private val prevY = DoubleArray(6); private var prevT = Double.NaN
    private val curY = DoubleArray(6); private var curT = Double.NaN
    private val out = DoubleArray(6)
    private var nextK = Long.MIN_VALUE
    var nativeCount = 0L; private set
    var gridCount = 0L; private set
    var droppedNonMonotonic = 0L; private set

    fun reset() {
        filterInit = false; gHead = 0; gCount = 0; aHead = 0; aCount = 0
        lastAccT = Double.NEGATIVE_INFINITY; lastGyrT = Double.NEGATIVE_INFINITY
        prevT = Double.NaN; curT = Double.NaN; nextK = Long.MIN_VALUE; nativeCount = 0; gridCount = 0; droppedNonMonotonic = 0
    }

    fun addGyro(t: Double, gx: Double, gy: Double, gz: Double) {
        if (t <= lastGyrT) { droppedNonMonotonic++; return }
        lastGyrT = t
        if (gCount == gCap) { gHead = (gHead + 1) % gCap; gCount-- }   // drop the oldest
        val i = (gHead + gCount) % gCap
        gT[i] = t; gX[i] = gx; gY[i] = gy; gZ[i] = gz; gCount++
        drain()
    }

    fun addAcc(t: Double, ax: Double, ay: Double, az: Double) {
        if (t <= lastAccT) { droppedNonMonotonic++; return }
        lastAccT = t
        if (aCount == aCap) { aHead = (aHead + 1) % aCap; aCount-- }
        val i = (aHead + aCount) % aCap
        aT[i] = t; aX[i] = ax; aY[i] = ay; aZ[i] = az; aCount++
        drain()
    }

    /** Emit every accel sample that now has a gyro sample at or after it. */
    private fun drain() {
        while (aCount > 0 && gCount > 0) {
            val ta = aT[aHead]
            val gLast = (gHead + gCount - 1) % gCap
            if (gT[gLast] < ta) return
            // find bracketing gyro samples: advance gHead while the next gyro sample is still <= ta
            while (gCount > 1) {
                val n = (gHead + 1) % gCap
                if (gT[n] <= ta) { gHead = n; gCount-- } else break
            }
            val i0 = gHead
            val gx: Double; val gy: Double; val gz: Double
            if (gCount == 1 || gT[i0] >= ta) {   // clamp (before the first gyro sample) or exact hit
                gx = gX[i0]; gy = gY[i0]; gz = gZ[i0]
            } else {
                val i1 = (i0 + 1) % gCap
                val f = (ta - gT[i0]) / (gT[i1] - gT[i0])
                gx = gX[i0] + f * (gX[i1] - gX[i0]); gy = gY[i0] + f * (gY[i1] - gY[i0]); gz = gZ[i0] + f * (gZ[i1] - gZ[i0])
            }
            onNative(ta, aX[aHead], aY[aHead], aZ[aHead], gx, gy, gz)
            aHead = (aHead + 1) % aCap; aCount--
        }
    }

    private fun filterChannel(c: Int, x0: Double): Double {
        var x = x0
        val zz1 = z1[c]; val zz2 = z2[c]
        for (s in 0 until nSec) {
            val y = b0[s] * x + zz1[s]
            zz1[s] = b1[s] * x - a1[s] * y + zz2[s]
            zz2[s] = b2[s] * x - a2[s] * y
            x = y
        }
        return x
    }

    private fun initSteadyState(v: DoubleArray) {
        for (c in 0 until 6) {
            var x = v[c]
            for (s in 0 until nSec) {
                val g = (b0[s] + b1[s] + b2[s]) / (1.0 + a1[s] + a2[s])
                val y = g * x
                z2[c][s] = b2[s] * x - a2[s] * y
                z1[c][s] = (b1[s] + b2[s]) * x - (a1[s] + a2[s]) * y
                x = y
            }
        }
        filterInit = true
    }

    private val tmp = DoubleArray(6)

    private fun onNative(t: Double, ax: Double, ay: Double, az: Double, gx: Double, gy: Double, gz: Double) {
        nativeCount++
        tmp[0] = ax; tmp[1] = ay; tmp[2] = az; tmp[3] = gx; tmp[4] = gy; tmp[5] = gz
        if (!filterInit) initSteadyState(tmp)
        System.arraycopy(curY, 0, prevY, 0, 6); prevT = curT
        for (c in 0 until 6) curY[c] = filterChannel(c, tmp[c])
        curT = t
        if (prevT.isNaN()) { nextK = ceil(t / gridDt - 1e-9).toLong(); return }
        while (true) {
            val tk = nextK * gridDt
            if (tk > curT + 1e-12) break
            if (tk > prevT) {
                val f = (tk - prevT) / (curT - prevT)
                for (c in 0 until 6) out[c] = prevY[c] + f * (curY[c] - prevY[c])
                gridCount++
                sink.onSample(nextK, tk, out)
            }
            nextK++
        }
    }

    companion object {
        /** scipy.signal.butter(4, 40, fs=420, output='sos') as written to engine/export/resample_constants.json. */
        val SOS_40HZ_420: Array<DoubleArray> = arrayOf(
            doubleArrayOf(0.004084090581862278, 0.008168181163724557, 0.004084090581862278, 1.0, -1.0868417615022878, 0.3154088083097217),
            doubleArrayOf(1.0, 2.0, 1.0, 1.0, -1.3594224322488757, 0.6453142535876253)
        )
    }
}
