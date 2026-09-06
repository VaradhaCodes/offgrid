package com.snu.idr.engine

import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.sqrt

/** One inference: normalised window [256][6] row-major -> out[0] = mu, out[1] = log sigma^2. */
interface SpeedModel {
    val name: String
    fun infer(xn: FloatArray, out: FloatArray)
    fun close() {}
}

/** The model pack: model.json + weights.bin (float32 LE, BN folded) written by tools/export_weights.py. */
class ModelPack(val json: JSONObject, val weights: FloatArray) {
    val version: String = json.getString("version")
    val window: Int = json.getInt("window")
    val channels = 6
    val mean = FloatArray(6) { json.getJSONArray("norm_mean").getDouble(it).toFloat() }
    val std = FloatArray(6) { json.getJSONArray("norm_std").getDouble(it).toFloat() }

    companion object {
        fun load(jsonText: String, weightBytes: ByteArray): ModelPack {
            val bb = ByteBuffer.wrap(weightBytes).order(ByteOrder.LITTLE_ENDIAN)
            val n = weightBytes.size / 4
            val w = FloatArray(n); bb.asFloatBuffer().get(w)
            val j = JSONObject(jsonText)
            require(j.getInt("n_floats") == n) { "weights.bin has $n floats, model.json says ${j.getInt("n_floats")}" }
            return ModelPack(j, w)
        }
    }

    /** Fills xn (window*6) with the z-scored window given raw samples in [t][c] layout. */
    fun normalise(raw: FloatArray, xn: FloatArray) {
        val w = window
        for (t in 0 until w) {
            val o = t * 6
            for (c in 0 until 6) xn[o + c] = (raw[o + c] - mean[c]) / std[c]
        }
    }
}

/**
 * Pure-Kotlin forward pass of the deployment CNN (spec §8): four Conv1d (k7 s2, k5 s2, k5 s2, k3 s2, symmetric zero padding
 * k//2, BN folded, ReLU), global average pool, Dense 96->64 ReLU, Dense 64->2. Float32 like PyTorch. No allocation per call.
 */
class KotlinCnn(private val pack: ModelPack) : SpeedModel {
    override val name = "kotlin-cnn"
    private class Conv(val ci: Int, val co: Int, val k: Int, val s: Int, val p: Int, val bOff: Int)
    private class Dense(val di: Int, val dout: Int, val relu: Boolean, val wOff: Int, val bOff: Int)
    private val convs = ArrayList<Conv>(); private val denses = ArrayList<Dense>()
    private val w = pack.weights
    /** Conv weights transposed to [ci][k][co] so the innermost loop is a contiguous saxpy over output channels. */
    private val wT: Array<FloatArray>
    /** Zero-padded inputs per layer, [ci][nIn + 2p]. */
    private val padded: Array<FloatArray>
    private val bufs: Array<FloatArray>   // outputs per layer, [co][nOut]
    private val lens: IntArray
    private val acc: FloatArray
    private val pooled: FloatArray
    private val d1: FloatArray

    init {
        val layers = pack.json.getJSONArray("layers")
        val wOffs = ArrayList<Int>()
        for (i in 0 until layers.length()) {
            val L = layers.getJSONObject(i)
            if (L.getString("type") == "conv1d") { convs.add(Conv(L.getInt("in_ch"), L.getInt("out_ch"), L.getInt("kernel"), L.getInt("stride"), L.getInt("pad"), L.getInt("b_offset"))); wOffs.add(L.getInt("w_offset")) }
            else denses.add(Dense(L.getInt("in_features"), L.getInt("out_features"), L.getString("activation") == "relu", L.getInt("w_offset"), L.getInt("b_offset")))
        }
        lens = IntArray(convs.size + 1); lens[0] = pack.window
        for (i in convs.indices) { val c = convs[i]; lens[i + 1] = (lens[i] + 2 * c.p - c.k) / c.s + 1 }
        wT = Array(convs.size) { li ->
            val c = convs[li]; val t = FloatArray(c.ci * c.k * c.co); val o = wOffs[li]
            for (co in 0 until c.co) for (ci in 0 until c.ci) for (kk in 0 until c.k) t[(ci * c.k + kk) * c.co + co] = w[o + (co * c.ci + ci) * c.k + kk]
            t
        }
        padded = Array(convs.size) { li -> val c = convs[li]; FloatArray(c.ci * (lens[li] + 2 * c.p)) }
        bufs = Array(convs.size + 1) { i -> FloatArray((if (i == 0) 6 else convs[i - 1].co) * lens[i]) }
        acc = FloatArray(convs.maxOf { it.co }); pooled = FloatArray(convs.last().co); d1 = FloatArray(denses[0].dout)
    }

    override fun infer(xn: FloatArray, out: FloatArray) {
        // input [t][c] -> [c][t]
        val n0 = lens[0]; val h0 = bufs[0]
        for (t in 0 until n0) { val o = t * 6; for (c in 0 until 6) h0[c * n0 + t] = xn[o + c] }
        for (li in convs.indices) {
            val c = convs[li]; val nIn = lens[li]; val nOut = lens[li + 1]; val hin = bufs[li]; val hout = bufs[li + 1]
            val wl = wT[li]; val hp = padded[li]; val row = nIn + 2 * c.p; val co = c.co; val k = c.k; val s = c.s
            for (ci in 0 until c.ci) System.arraycopy(hin, ci * nIn, hp, ci * row + c.p, nIn)
            val a = acc
            for (t in 0 until nOut) {
                for (j in 0 until co) a[j] = w[c.bOff + j]
                val base = t * s
                for (ci in 0 until c.ci) {
                    val hb = ci * row + base; val wb = ci * k * co
                    for (kk in 0 until k) {
                        val x = hp[hb + kk]
                        if (x == 0f) continue
                        val wo = wb + kk * co
                        for (j in 0 until co) a[j] += x * wl[wo + j]
                    }
                }
                for (j in 0 until co) hout[j * nOut + t] = if (a[j] > 0f) a[j] else 0f
            }
        }
        val last = convs.last(); val nL = lens[convs.size]; val hl = bufs[convs.size]
        for (j in 0 until last.co) { var sum = 0f; val o = j * nL; for (t in 0 until nL) sum += hl[o + t]; pooled[j] = sum / nL }
        val dA = denses[0]
        for (o in 0 until dA.dout) { var sum = w[dA.bOff + o]; val wb = dA.wOff + o * dA.di; for (i in 0 until dA.di) sum += w[wb + i] * pooled[i]; d1[o] = if (dA.relu && sum < 0f) 0f else sum }
        val dB = denses[1]
        for (o in 0 until dB.dout) { var sum = w[dB.bOff + o]; val wb = dB.wOff + o * dB.di; for (i in 0 until dB.di) sum += w[wb + i] * d1[i]; out[o] = if (dB.relu && sum < 0f) 0f else sum }
    }
}

/** Ring buffer of the last `window` bike-frame samples with gravity and gyro bias left in, plus the physical stop rule (spec §5.3). */
class WindowRing(val window: Int = 256, val channels: Int = 6) {
    private val buf = FloatArray(window * channels)
    private var head = 0   // index of the oldest sample
    var count = 0; private set
    val full: Boolean get() = count >= window

    fun reset() { head = 0; count = 0 }

    fun push(a: DoubleArray, wv: DoubleArray) {
        val i = if (count < window) (head + count) else head
        val o = i * channels
        buf[o] = a[0].toFloat(); buf[o + 1] = a[1].toFloat(); buf[o + 2] = a[2].toFloat()
        buf[o + 3] = wv[0].toFloat(); buf[o + 4] = wv[1].toFloat(); buf[o + 5] = wv[2].toFloat()
        if (count < window) count++ else head = (head + 1) % window
    }

    /** Copies the window in time order into raw ([t][c]); the oldest sample first. */
    fun copyOrdered(raw: FloatArray) {
        val first = window - head
        System.arraycopy(buf, head * channels, raw, 0, first * channels)
        if (head > 0) System.arraycopy(buf, 0, raw, first * channels, head * channels)
    }

    /** vib RMS < 0.6 m/s^2 and gyro RMS < 0.06 rad/s over the last m samples (0.5 s). */
    fun stopRule(m: Int = 50, vibThr: Double = 0.6, gyrThr: Double = 0.06): Boolean {
        if (count < m) return true
        var mx = 0.0; var my = 0.0; var mz = 0.0
        for (j in 0 until m) { val i = ((head + count - m + j) % window) * channels; mx += buf[i]; my += buf[i + 1]; mz += buf[i + 2] }
        mx /= m; my /= m; mz /= m
        var vib = 0.0; var gg = 0.0
        for (j in 0 until m) {
            val i = ((head + count - m + j) % window) * channels
            val dx = buf[i] - mx; val dy = buf[i + 1] - my; val dz = buf[i + 2] - mz
            vib += dx * dx + dy * dy + dz * dz
            gg += buf[i + 3] * buf[i + 3] + buf[i + 4] * buf[i + 4] + buf[i + 5] * buf[i + 5]
        }
        lastVib = sqrt(vib / m); lastGyr = sqrt(gg / m)
        return lastVib < vibThr && lastGyr < gyrThr
    }
    var lastVib = 0.0; private set
    var lastGyr = 0.0; private set
}

/** Per-tick model output. */
class ModelOut { var vRaw = 0.0; var sigma = 0.05; var still = true; var mu = 0.0; var logvar = -6.0; var modelMs = 0.0; var valid = false }

/** Where the speed comes from each tick: the CNN on the live window, or a recorded prediction file (conformance). */
interface SpeedSource {
    fun speedAt(t: Double, ring: WindowRing, out: ModelOut)
    val name: String
}

class CnnSpeedSource(private val pack: ModelPack, private val model: SpeedModel) : SpeedSource {
    override val name get() = model.name
    private val raw = FloatArray(pack.window * 6); private val xn = FloatArray(pack.window * 6); private val o = FloatArray(2)
    var lastMs = 0.0; private set
    var nCalls = 0L; private set
    var sumMs = 0.0; private set
    var maxMs = 0.0; private set

    override fun speedAt(t: Double, ring: WindowRing, out: ModelOut) {
        val still = ring.stopRule()
        if (!ring.full) { out.vRaw = 0.0; out.sigma = 0.05; out.still = true; out.valid = false; out.modelMs = 0.0; return }
        val t0 = System.nanoTime()
        ring.copyOrdered(raw); pack.normalise(raw, xn); model.infer(xn, o)
        val ms = (System.nanoTime() - t0) / 1e6
        lastMs = ms; nCalls++; sumMs += ms; if (ms > maxMs) maxMs = ms
        out.mu = o[0].toDouble(); out.logvar = o[1].toDouble()
        out.vRaw = max(out.mu, 0.0); out.sigma = exp(0.5 * out.logvar.coerceIn(-6.0, 4.0)); out.still = still; out.valid = true; out.modelMs = ms
    }
}

/** Recorded predictions (data/speed_model/pred/<cfg>/<session>.csv): the row with the latest t_s <= t (row 0 before that). */
class PredCsvSpeedSource(private val t: DoubleArray, private val vRaw: DoubleArray, private val sigma: DoubleArray, private val still: BooleanArray) : SpeedSource {
    override val name = "pred-csv"
    private var ip = 0
    override fun speedAt(t: Double, ring: WindowRing, out: ModelOut) {
        while (ip < this.t.size && this.t[ip] <= t) ip++
        val j = max(0, ip - 1)
        out.vRaw = vRaw[j]; out.sigma = sigma[j]; out.still = still[j]; out.valid = true; out.modelMs = 0.0; out.mu = vRaw[j]
    }
}
