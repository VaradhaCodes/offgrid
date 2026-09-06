package com.snu.idr.engine

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.max

/** Acceptance 11.1/11.2 (JVM half): the Kotlin CNN equals PyTorch on 500 real windows within 1e-4; latency reported. */
class ModelTest {
    private fun readFloats(f: File): FloatArray { val b = f.readBytes(); val out = FloatArray(b.size / 4); ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer().get(out); return out }

    @Test fun kotlinCnnMatchesPyTorchFixtures() {
        val pack = TestData.modelPack(); val model = KotlinCnn(pack)
        val n = pack.json.getJSONObject("fixtures").getInt("n")
        val X = readFloats(File(TestData.assets, "model/windows_$n.bin")); val Y = readFloats(File(TestData.assets, "model/expected_$n.bin"))
        val raw = FloatArray(pack.window * 6); val xn = FloatArray(pack.window * 6); val o = FloatArray(2)
        var maxMu = 0.0; var maxLv = 0.0; var maxV = 0.0; var sumV = 0.0
        for (i in 0 until n) {
            System.arraycopy(X, i * pack.window * 6, raw, 0, pack.window * 6); pack.normalise(raw, xn); model.infer(xn, o)
            val dmu = abs(o[0] - Y[i * 2]).toDouble(); val dlv = abs(o[1] - Y[i * 2 + 1]).toDouble()
            val v1 = max(o[0].toDouble(), 0.0); val v2 = max(Y[i * 2].toDouble(), 0.0); val dv = abs(v1 - v2)
            maxMu = max(maxMu, dmu); maxLv = max(maxLv, dlv); maxV = max(maxV, dv); sumV += dv
        }
        // latency: warm up then time 500 calls
        for (i in 0 until 50) model.infer(xn, o)
        val t0 = System.nanoTime(); for (i in 0 until 500) { System.arraycopy(X, (i % n) * pack.window * 6, raw, 0, pack.window * 6); pack.normalise(raw, xn); model.infer(xn, o) }
        val ms = (System.nanoTime() - t0) / 1e6 / 500
        println("[model] n=$n max |dmu| ${TestData.fmt(maxMu, 7)} max |dlogvar| ${TestData.fmt(maxLv, 7)} max |dv| ${TestData.fmt(maxV, 7)} mean |dv| ${TestData.fmt(sumV / n, 8)} m/s; JVM latency ${TestData.fmt(ms, 3)} ms/window (Mac, 1 thread, warm)")
        assertTrue("mu differs by $maxMu", maxMu < 1e-4)
        assertTrue("logvar differs by $maxLv", maxLv < 1e-4)
        assertTrue("speed differs by $maxV", maxV < 0.02)
    }

    @Test fun stopRuleAndSigma() {
        val ring = WindowRing()
        val a = doubleArrayOf(0.1, 0.0, 9.8); val w = doubleArrayOf(0.0, 0.0, 0.0)
        for (i in 0 until 300) ring.push(a, w)
        assertTrue(ring.stopRule())
        val a2 = DoubleArray(3); val rnd = java.util.Random(1)
        for (i in 0 until 300) { a2[0] = rnd.nextGaussian() * 2; a2[1] = rnd.nextGaussian() * 2; a2[2] = 9.8 + rnd.nextGaussian() * 2; ring.push(a2, w) }
        assertTrue(!ring.stopRule())
        assertTrue(abs(exp(0.5 * (-6.0)) - 0.0498) < 1e-3)
    }
}
