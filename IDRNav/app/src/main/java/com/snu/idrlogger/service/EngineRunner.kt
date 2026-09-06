package com.snu.idrlogger.service

import android.content.Context
import android.os.Process
import android.util.Log
import com.snu.idr.engine.CnnSpeedSource
import com.snu.idr.engine.CorridorDef
import com.snu.idr.engine.Engine
import com.snu.idr.engine.EngineConfig
import com.snu.idr.engine.EngineListener
import com.snu.idr.engine.EngineState
import com.snu.idr.engine.KotlinCnn
import com.snu.idr.engine.ModelPack
import com.snu.idr.engine.RoadGraph
import com.snu.idr.engine.Scenario
import com.snu.idr.engine.SpeedModel
import com.snu.idr.engine.replay.SessionReader
import com.snu.idrlogger.StreamWriter
import com.snu.idrlogger.model.LiteRtSpeedModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject
import java.io.File
import java.util.concurrent.locks.LockSupport

/** One engine event for the UI (sync tones, chips) and the events log. */
class EngineEvent(val t: Double, val type: String, val text: String)

class ReplayStatus(val session: String, val tNow: Double, val tEnd: Double, val speed: Double, val running: Boolean, val outDir: String?)

/** Everything the Compose UI observes from the engine, whatever drives it (live sensors or a replay). */
object NavLive {
    val state = MutableStateFlow<EngineState?>(null)
    val events = MutableSharedFlow<EngineEvent>(extraBufferCapacity = 256)
    val replay = MutableStateFlow<ReplayStatus?>(null)
    val engineInfo = MutableStateFlow("")
    @Volatile var speedModelName = ""
    @Volatile var tickMsMean = 0.0
    @Volatile var tickMsMax = 0.0
    @Volatile var modelMsMean = 0.0
    @Volatile var modelMsMax = 0.0
    @Volatile var imuGridCount = 0L
    @Volatile var imuNativeCount = 0L
    @Volatile var droppedSamples = 0L
}

/** Loads the assets the engine needs (corridor library, model pack, road graph). Cheap; call off the main thread once. */
object EngineAssets {
    fun corridors(ctx: Context): List<CorridorDef> {
        val lib = JSONObject(ctx.assets.open("corridors/library.json").bufferedReader().readText()).getJSONArray("corridors")
        val out = ArrayList<CorridorDef>()
        for (i in 0 until lib.length()) {
            val id = lib.getString(i)
            val cfgText = ctx.assets.open("corridors/$id.json").bufferedReader().readText()
            val geo = JSONObject(cfgText).getString("geojson")
            out.add(CorridorDef.fromJson(cfgText, ctx.assets.open("corridors/$geo").bufferedReader().readText()))
        }
        return out
    }

    fun modelPack(ctx: Context): ModelPack = ModelPack.load(ctx.assets.open("model/model.json").bufferedReader().readText(), ctx.assets.open("model/weights.bin").readBytes())

    fun roadGraph(ctx: Context): RoadGraph? = try { RoadGraph.fromCompactJson(ctx.assets.open("map/graph.json").bufferedReader().readText()) } catch (t: Throwable) { Log.w("IDR", "graph.json: ${t.message}"); null }

    fun speedModel(ctx: Context, pack: ModelPack, kind: String): SpeedModel = when (kind) {
        "kotlin" -> KotlinCnn(pack)
        else -> try { LiteRtSpeedModel(ctx) } catch (t: Throwable) { Log.e("IDR", "LiteRT unavailable, falling back to the Kotlin CNN", t); KotlinCnn(pack) }
    }
}

/** Lock-free single-producer / single-consumer ring of (t, x, y, z) samples. */
class SampleRing(private val cap: Int) {
    private val t = DoubleArray(cap); private val x = DoubleArray(cap); private val y = DoubleArray(cap); private val z = DoubleArray(cap)
    @Volatile private var head = 0L   // next read
    @Volatile private var tail = 0L   // next write
    @Volatile var dropped = 0L; private set

    fun push(ts: Double, vx: Double, vy: Double, vz: Double): Boolean {
        val tl = tail
        if (tl - head >= cap) { dropped++; return false }
        val i = (tl % cap).toInt()
        t[i] = ts; x[i] = vx; y[i] = vy; z[i] = vz
        tail = tl + 1
        return true
    }

    fun interface Sink { fun on(t: Double, x: Double, y: Double, z: Double) }

    /** Consumer: drains up to max samples into the sink; returns the count. */
    fun drain(max: Int, sink: Sink): Int {
        var n = 0; var h = head; val tl = tail
        while (h < tl && n < max) { val i = (h % cap).toInt(); sink.on(t[i], x[i], y[i], z[i]); h++; n++ }
        head = h
        return n
    }

    val size: Int get() = (tail - head).toInt()
}

/**
 * Owns the engine thread. Live mode: sensors -> rings -> resampler -> engine; GNSS and events posted in. Replay mode: a
 * SessionReader drives the same engine on this thread at the requested speed. Ticks go to NavLive and to engine_out.csv.
 */
class EngineRunner(
    private val ctx: Context,
    private val cfg: EngineConfig,
    private val modelKind: String,
    private val sessionStartElapsedNs: Long,
    private val outEngine: StreamWriter?,
    private val outEvents: StreamWriter?
) : EngineListener {
    private val pack = EngineAssets.modelPack(ctx)
    val speedModel: SpeedModel = EngineAssets.speedModel(ctx, pack, modelKind)
    private val source = CnnSpeedSource(pack, speedModel)
    val engine = Engine(cfg, source, this)
    private val acc = SampleRing(16384); private val gyr = SampleRing(16384)
    private val fixT = DoubleArray(64); private val fixLat = DoubleArray(64); private val fixLon = DoubleArray(64); private val fixAcc = DoubleArray(64); private val fixV = DoubleArray(64); private val fixB = DoubleArray(64); private val fixS = IntArray(64)
    @Volatile private var fixHead = 0L; @Volatile private var fixTail = 0L
    private val evQ = java.util.concurrent.ConcurrentLinkedQueue<Pair<Double, String>>()
    @Volatile private var statusUsed = 0; @Volatile private var statusCn0 = Double.NaN; @Volatile private var statusDirty = false
    @Volatile private var running = false
    private var thread: Thread? = null
    @Volatile var manualDenial = false
    private var lastManual = false
    var wroteRows = 0L; private set

    fun tOf(elapsedNs: Long): Double = (elapsedNs - sessionStartElapsedNs) / 1e9

    // ---- producers (sensor / gnss threads)
    fun pushAcc(elapsedNs: Long, x: Float, y: Float, z: Float) { acc.push(tOf(elapsedNs), x.toDouble(), y.toDouble(), z.toDouble()); LockSupport.unpark(thread) }
    fun pushGyr(elapsedNs: Long, x: Float, y: Float, z: Float) { gyr.push(tOf(elapsedNs), x.toDouble(), y.toDouble(), z.toDouble()) }
    fun postFix(elapsedNs: Long, lat: Double, lon: Double, accH: Double, speed: Double, bearing: Double, sats: Int) {
        val tl = fixTail; if (tl - fixHead >= 64) return
        val i = (tl % 64).toInt(); fixT[i] = tOf(elapsedNs); fixLat[i] = lat; fixLon[i] = lon; fixAcc[i] = accH; fixV[i] = speed; fixB[i] = bearing; fixS[i] = sats
        fixTail = tl + 1
    }
    fun postStatus(nUsed: Int, cn0: Double) { statusUsed = nUsed; statusCn0 = cn0; statusDirty = true }
    fun postEvent(elapsedNs: Long, type: String) { evQ.add(Pair(tOf(elapsedNs), type)); LockSupport.unpark(thread) }

    fun startLive() {
        running = true
        val th = Thread({ loop() }, "idr-engine")
        th.priority = Thread.MAX_PRIORITY
        thread = th; th.start()
    }

    private val gyrSink = SampleRing.Sink { t, x, y, z -> engine.onGyrNative(t, x, y, z) }
    private val accSink = SampleRing.Sink { t, x, y, z -> engine.onAccNative(t, x, y, z) }

    private fun loop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_DISPLAY)
        val e = engine
        while (running) {
            var did = 0
            while (true) { val p = evQ.poll() ?: break; e.onEvent(p.first, p.second); did++ }
            if (statusDirty) { statusDirty = false; e.onGnssStatus(0.0, statusUsed, statusCn0) }
            var h = fixHead; val tl = fixTail
            while (h < tl) { val i = (h % 64).toInt(); e.onFix(fixT[i], fixLat[i], fixLon[i], fixAcc[i], fixV[i], fixB[i], fixS[i]); h++; did++ }
            fixHead = h
            did += gyr.drain(4096, gyrSink)
            did += acc.drain(4096, accSink)
            if (manualDenial != lastManual) { lastManual = manualDenial; e.manualDenial = manualDenial; onEvent(e.state?.t ?: 0.0, "MANUAL_DENIAL", if (manualDenial) "on" else "off") }
            NavLive.droppedSamples = acc.dropped + gyr.dropped
            if (did == 0) LockSupport.parkNanos(2_000_000L)
        }
    }

    /** Replay: drives the engine from a recorded session folder on a dedicated thread. */
    fun startReplay(dir: File, speed: Double, onDone: (Throwable?) -> Unit) {
        running = true
        val th = Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_DISPLAY)
            var err: Throwable? = null
            try {
                val reader = SessionReader(dir)
                NavLive.replay.value = ReplayStatus(dir.name, 0.0, reader.tEnd, speed, true, outEngine?.file?.parent)
                reader.run(engine, speed, progress = { t -> NavLive.replay.value = ReplayStatus(dir.name, t, reader.tEnd, speed, true, outEngine?.file?.parent) }, shouldStop = { !running })
                engine.onEvent(reader.tEnd, "SESSION_END")
            } catch (t: Throwable) { err = t; Log.e("IDR", "replay failed", t) }
            NavLive.replay.value = NavLive.replay.value?.let { ReplayStatus(it.session, it.tEnd, it.tEnd, it.speed, false, it.outDir) }
            running = false
            onDone(err)
        }, "idr-replay")
        thread = th; th.start()
    }

    fun stop() {
        running = false
        thread?.let { LockSupport.unpark(it); try { it.join(3000) } catch (_: InterruptedException) {} }
        thread = null
        try { speedModel.close() } catch (_: Throwable) {}
    }

    // ---- EngineListener (engine thread)
    private var tickN = 0L
    override fun onTick(s: EngineState) {
        NavLive.state.value = s
        outEngine?.add(0L, s.csvRow()); wroteRows++
        tickN++
        if (tickN % 10L == 0L) {
            NavLive.tickMsMean = engine.tickMsMean; NavLive.tickMsMax = engine.tickMsMax
            NavLive.modelMsMean = if (source.nCalls > 0) source.sumMs / source.nCalls else 0.0; NavLive.modelMsMax = source.maxMs
            NavLive.imuGridCount = engine.resampler.gridCount; NavLive.imuNativeCount = engine.resampler.nativeCount
            NavLive.speedModelName = speedModel.name
        }
    }

    override fun onEvent(t: Double, type: String, text: String) {
        val clean = text.replace('\n', ' ').replace('"', '\'')
        outEvents?.add(0L, "${String.format(java.util.Locale.US, "%.3f", t)},$type,\"$clean\"")
        NavLive.events.tryEmit(EngineEvent(t, type, text))
        Log.i("IDR", "ENGINE ${String.format(java.util.Locale.US, "%.1f", t)} $type $text")
    }

    companion object {
        const val EVENTS_HEADER = "t_s,type,text"
        fun scenarioFrom(kind: String, bandFrom: Double, bandTo: Double, timerStart: Double, timerHold: Double): Scenario = when (kind) {
            "band" -> Scenario(Scenario.Kind.BAND, bandFromM = bandFrom, bandToM = if (bandTo > 0) bandTo else null)
            "timer" -> Scenario(Scenario.Kind.TIMER, timerStartS = timerStart, timerHoldS = timerHold)
            "manual" -> Scenario(Scenario.Kind.MANUAL)
            else -> Scenario.NONE
        }
    }
}
