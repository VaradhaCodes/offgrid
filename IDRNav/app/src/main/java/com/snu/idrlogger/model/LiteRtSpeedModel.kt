package com.snu.idrlogger.model

import android.content.Context
import android.util.Log
import com.google.ai.edge.litert.Accelerator
import com.google.ai.edge.litert.CompiledModel
import com.google.ai.edge.litert.TensorBuffer
import com.snu.idr.engine.SpeedModel

/**
 * The edge-deployment path (spec §8, R2): LiteRT 2.2.0 CompiledModel on the CPU accelerator (XNNPACK), one thread, fixed shapes,
 * buffers allocated once. Input [1, 256, 6] float32 z-scored window in [t][c] order = the same FloatArray layout the Kotlin CNN takes.
 */
class LiteRtSpeedModel(context: Context, assetPath: String = "model/cnn_r100_w256_joint_deploy.tflite") : SpeedModel {
    override val name = "litert-2.2.0-cpu-xnnpack-1thread"
    private val model: CompiledModel
    private val inputs: List<TensorBuffer>
    private val outputs: List<TensorBuffer>
    var lastMs = 0.0; private set
    var nCalls = 0L; private set
    var sumMs = 0.0; private set
    var maxMs = 0.0; private set

    init {
        val opts = CompiledModel.Options(Accelerator.CPU)
        opts.cpuOptions = CompiledModel.CpuOptions(1, null, null)   // numThreads = 1, default XNNPACK flags, no weight cache
        model = CompiledModel.create(context.assets, assetPath, opts)
        inputs = model.createInputBuffers()
        outputs = model.createOutputBuffers()
        Log.i("IDR", "LiteRT model loaded: $assetPath inputs=${inputs.size} outputs=${outputs.size}")
        // warm-up: XNNPACK packs weights on the first run
        val z = FloatArray(256 * 6)
        val o = FloatArray(2)
        for (i in 0 until 20) infer(z, o)
        nCalls = 0; sumMs = 0.0; maxMs = 0.0
    }

    override fun infer(xn: FloatArray, out: FloatArray) {
        val t0 = System.nanoTime()
        inputs[0].writeFloat(xn)
        model.run(inputs, outputs)
        val r = outputs[0].readFloat()
        out[0] = r[0]; out[1] = r[1]
        val ms = (System.nanoTime() - t0) / 1e6
        lastMs = ms; nCalls++; sumMs += ms; if (ms > maxMs) maxMs = ms
    }

    val meanMs: Double get() = if (nCalls > 0) sumMs / nCalls else 0.0

    override fun close() {
        try { model.close() } catch (_: Throwable) {}
    }
}
