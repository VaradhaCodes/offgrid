package com.snu.idr.engine

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.max

enum class Phase { IDLE, STAND, RIDE, STOP_STAND, DONE }
enum class Mode { GNSS_INS, INERTIAL, RECOVERING }

/** Simulated denial (spec §3.3/§3.4). Band = metres from the ride's own start along the recognised corridor. */
data class Scenario(val kind: Kind = Kind.NONE, val bandFromM: Double = 200.0, val bandToM: Double? = null, val timerStartS: Double = 40.0, val timerHoldS: Double = 90.0) {
    enum class Kind { NONE, BAND, TIMER, MANUAL }
    companion object { val NONE = Scenario() }
}

/** Offline alignment for the conformance harness (align.json): R_pb, phone-frame bias, |g|, stand quiet flag. */
class AlignmentOverride(val rPb: DoubleArray, val biasP: DoubleArray, val gMag: Double, val quiet: Boolean)

class EngineConfig(
    val corridors: List<CorridorDef> = emptyList(),
    val roadGraph: RoadGraph? = null,
    /** Start in corridor mode on this corridor at the first fix (conformance = replay.py --mode corridor). */
    val forcedCorridorId: String? = null,
    /** Recognise library corridors from healthy fixes (8 consecutive within 15 m). */
    val corridorAuto: Boolean = true,
    val mapMatch: Boolean = true,
    val alignmentOverride: AlignmentOverride? = null,
    /** ENU origin [lat, lon]; default = the first fix. */
    val originLatLon: DoubleArray? = null,
    val scenario: Scenario = Scenario.NONE,
    val kEst: Boolean = false,
    val applyCn0Rule: Boolean = true,
    /** Detect a real gap at the tick when no fix arrived for 1.5 s (the phone path); replay.py only judges gaps at fix arrival. */
    val gapAtTick: Boolean = true,
    /** Causal anti-alias filter passes: 1 = one 4th-order Butterworth (spec §2); 2 = the same filter twice, whose magnitude response equals the zero-phase filtfilt used in training. */
    val resamplerPasses: Int = 1
)

class RevealInfo(val pathLatLon: List<DoubleArray>, val distanceM: Double, val durationS: Double, val endErrorM: Double, val maxErrorM: Double, val tReturn: Double, val sim: Boolean, val armedAtEntry: Boolean)

class OutageSummary(val tStart: Double, val tEnd: Double, val distanceM: Double, val durationS: Double, val endErrorM: Double, val maxErrorM: Double, var recoveryStepM: Double, val sim: Boolean, val armedAtEntry: Boolean, val corridorId: String?)

/** One 10 Hz snapshot. Everything the UI and the logger need. */
class EngineState(
    val t: Double, val k: Long, val phase: Phase, val mode: Mode, val sim: Boolean, val scenarioArmed: Boolean, val withheld: Boolean, val realOutage: Boolean,
    val hasPosition: Boolean, val lat: Double, val lon: Double, val x: Double, val y: Double, val v: Double,
    val headingDeg: Double, val headingSigmaDeg: Double, val headingInit: Boolean, val scale: Double, val sigmaPos: Double,
    val vModel: Double, val sigmaModel: Double, val stop: Boolean, val modelValid: Boolean, val tickMs: Double, val modelMs: Double,
    val corridorId: String?, val corridorName: String?, val s: Double, val d: Double, val dir: Int, val fusionMode: String,
    val dispLat: Double, val dispLon: Double, val dispX: Double, val dispY: Double, val matched: Boolean, val mmConf: Double,
    val sats: Int, val cn0: Double, val gnssAgeS: Double, val gnssAcc: Double, val fixLat: Double, val fixLon: Double, val nFixes: Int,
    val armed: Boolean, val armedMissing: String, val standQuiet: Boolean, val psiSource: String, val psiDeg: Double, val pitchDeg: Double, val rollDeg: Double,
    val biasDps: DoubleArray, val gMag: Double, val gravityBlocks: Int, val movedAtS: Double, val swayRatio: Double, val tMotionStart: Double,
    val drMeters: Double, val drSeconds: Double, val bandDistM: Double, val bandKnown: Boolean, val bandFromM: Double, val bandToM: Double?, val sStart: Double,
    val reveal: RevealInfo?, val outages: List<OutageSummary>, val vib: Double, val gyrRms: Double, val speedSource: String, val nRejectedFixes: Int
) {
    /** engine_out.csv row (header in [CSV_HEADER]). */
    fun csvRow(): String = buildString(200) {
        append(fmt(t, 3)).append(',').append(fmt(lat, 8)).append(',').append(fmt(lon, 8)).append(',').append(fmt(x, 3)).append(',').append(fmt(y, 3)).append(',')
        append(fmt(v, 3)).append(',').append(fmt(headingDeg, 3)).append(',').append(mode.name).append(',').append(if (sim) 1 else 0).append(',').append(fmt(scale, 4)).append(',')
        append(fmt(sigmaPos, 3)).append(',').append(fmt(vModel, 3)).append(',').append(fmt(sigmaModel, 3)).append(',').append(if (stop) 1 else 0).append(',')
        append(fmt(tickMs, 3)).append(',').append(fmt(modelMs, 3)).append(',').append(corridorId ?: "").append(',').append(fmt(s, 2)).append(',').append(fmt(d, 2))
    }
    companion object {
        const val CSV_HEADER = "t_s,lat,lon,x_m,y_m,v,heading_deg,mode,sim,k,sigma_pos,v_model,sigma_model,stop,tick_ms,model_ms,corridor_id,s_m,d_m"
        fun fmt(v: Double, dec: Int): String = if (v.isNaN()) "" else String.format(java.util.Locale.US, "%.${dec}f", v)
    }
}

interface EngineListener {
    fun onTick(s: EngineState)
    fun onEvent(t: Double, type: String, text: String)
}

/**
 * The 100 Hz step + 10 Hz tick orchestration (spec §1–§7, replay.py ordering): fixes with t_f <= t are gated and fed to the heading
 * filter before the IMU step; the fusion filter consumes them at the next tick after predict + model update.
 */
class Engine(val cfg: EngineConfig, private val speedSource: SpeedSource, private val listener: EngineListener? = null) {
    val aligner = Aligner()
    val ring = WindowRing()
    var heading: HeadingFilter? = null; private set
    var fusion: Fusion? = null; private set
    var origin: Origin? = null; private set
    private var corridorsEnu: List<Corridor> = emptyList()
    private var mapMatcher: MapMatcher? = null
    val resampler = Resampler(Array(2 * cfg.resamplerPasses.coerceIn(1, 3)) { Resampler.SOS_40HZ_420[it % 2] }, 0.01) { k, t, v -> onImu100(k, t, v) }

    var phase = Phase.IDLE; private set
    var mode = Mode.GNSS_INS; private set
    var state: EngineState? = null; private set
    var manualDenial = false
    private var tRideStart = Double.NaN; private var tStopStart = Double.NaN
    private var tMotionStart = Double.NaN

    // ---- fixes
    private val fixCap = 256
    private val fqT = DoubleArray(fixCap); private val fqLat = DoubleArray(fixCap); private val fqLon = DoubleArray(fixCap); private val fqAcc = DoubleArray(fixCap)
    private val fqV = DoubleArray(fixCap); private val fqBrg = DoubleArray(fixCap); private val fqSats = IntArray(fixCap); private var fqHead = 0; private var fqN = 0
    private var tPrevFix = Double.NaN; private var xPrevFix = 0.0; private var yPrevFix = 0.0; private var prevSatsBad = false
    private var lastFixT = Double.NaN; private var lastHealthyT = Double.NaN; private var lastFixLat = Double.NaN; private var lastFixLon = Double.NaN; private var lastFixAcc = Double.NaN
    private var lastFixX = 0.0; private var lastFixY = 0.0
    private var nFixes = 0
    private var withheldNow = false; private var simNow = false; private var realBadNow = false
    private var statusSats = 0; private var statusCn0 = Double.NaN
    private var healthySince = Double.NaN
    // pending for the fusion filter
    private val pCap = 64
    private val pT = DoubleArray(pCap); private val pX = DoubleArray(pCap); private val pY = DoubleArray(pCap); private val pV = DoubleArray(pCap); private val pAcc = DoubleArray(pCap); private val pW = BooleanArray(pCap); private var pN = 0

    // ---- corridor
    private var corridorIdx = -1
    private val recogCount: IntArray = IntArray(cfg.corridors.size)
    private var offCount = 0
    private var sStart = Double.NaN
    private val proj = Corridor.Proj()
    private var dirAnnounced = 0

    // ---- scenario / outage bookkeeping
    private var inBandPrev = false
    private var outage: Outage? = null
    private val outages = ArrayList<OutageSummary>()
    private var reveal: RevealInfo? = null
    private var drMeters = 0.0; private var drStartT = Double.NaN
    private var lastPosX = Double.NaN; private var lastPosY = Double.NaN
    private class Outage(val tStart: Double, val sim: Boolean, val armedAtEntry: Boolean, x0: Double, y0: Double) {
        val path = ArrayList<DoubleArray>(); var dist = 0.0; var maxErr = 0.0; var lastX = x0; var lastY = y0
        init { path.add(doubleArrayOf(x0, y0)) }
    }
    private var lastMode = Mode.GNSS_INS
    private var recoveryWatchUntil = Double.NEGATIVE_INFINITY; private var recoveryStepMax = 0.0

    // ---- per-tick scratch
    private val aP = DoubleArray(3); private val wP = DoubleArray(3); private val aB = DoubleArray(3); private val wB = DoubleArray(3)
    private val pos = DoubleArray(2); private val biasB = DoubleArray(3)
    private val mo = ModelOut()
    private var lastPsiAligner = 0.0
    private var lastTick = Double.NaN
    private var armedWas = false
    private var tickCount = 0L
    var tickMsMean = 0.0; private set
    var tickMsMax = 0.0; private set
    private var tickMsSum = 0.0

    init {
        cfg.alignmentOverride?.let { ov ->
            aligner.setOverride(ov.rPb, ov.biasP, ov.gMag, ov.quiet)
            createHeading()
        }
        cfg.originLatLon?.let { setOrigin(it[0], it[1]) }
    }

    private fun event(t: Double, type: String, text: String) { listener?.onEvent(t, type, text) }

    private fun setOrigin(lat: Double, lon: Double) {
        val o = Origin(lat, lon); origin = o
        corridorsEnu = cfg.corridors.map { Corridor(it, o) }
        mapMatcher = cfg.roadGraph?.let { MapMatcher(it, o) }
    }

    private fun createHeading() {
        Mat3.apply(aligner.rPb, aligner.biasP[0], aligner.biasP[1], aligner.biasP[2], biasB)
        val quiet = aligner.standQuiet
        heading = if (quiet) HeadingFilter(biasB, aligner.gMag, HeadingFilter.P_B_QUIET, refine = true, refineBias = false, bClamp = HeadingFilter.B_CLAMP)
        else HeadingFilter(biasB, aligner.gMag, HeadingFilter.P_B_LOOSE, refine = true, refineBias = true, bClamp = HeadingFilter.B_CLAMP_LOOSE)
        lastPsiAligner = aligner.psi
    }

    // ------------------------------------------------------------------ inputs
    fun onEvent(t: Double, type: String, text: String = "") {
        when (type) {
            "SESSION_START", "CALIB_START" -> { if (phase == Phase.IDLE) { phase = Phase.STAND; aligner.standStart(t); event(t, "PHASE", "STAND") } }
            "CALIB_END" -> {
                if (cfg.alignmentOverride == null) {
                    aligner.standEnd(t)
                    if (aligner.standValid) {
                        createHeading()
                        val e = aligner.pitchRollYawDeg
                        event(t, "ALIGN", String.format(java.util.Locale.US, "stand g=%.3f pitch=%.2f roll=%.2f bias_dps=[%.3f %.3f %.3f] quiet=%b qfrac=%.2f rot=%.2fdeg",
                            aligner.gMag, e[0], e[1], Geo.deg(aligner.biasP[0]), Geo.deg(aligner.biasP[1]), Geo.deg(aligner.biasP[2]), aligner.standQuiet, aligner.standQuietFrac, aligner.standNetRotDeg))
                    } else event(t, "ALIGN", "stand too short: no alignment")
                }
            }
            "RIDE_START" -> { phase = Phase.RIDE; tRideStart = t; aligner.rideStart(t); if (corridorIdx >= 0 && sStart.isNaN() && !lastFixT.isNaN()) setSStart(lastFixX, lastFixY); event(t, "PHASE", "RIDE") }
            "STOP_CALIB_START" -> { phase = Phase.STOP_STAND; tStopStart = t; event(t, "PHASE", "STOP_STAND") }
            "STOP_CALIB_END", "SESSION_END", "SESSION_ABORT" -> { if (phase != Phase.DONE) { phase = Phase.DONE; closeOutage(t, null); event(t, "PHASE", "DONE") } }
        }
    }

    fun onGnssStatus(t: Double, nUsed: Int, cn0Mean: Double) { statusSats = nUsed; statusCn0 = cn0Mean }

    /** A raw GNSS fix (GPS_PROVIDER). bearingDeg NaN when absent. Queued and consumed at the next IMU sample with t >= tFix. */
    fun onFix(tFix: Double, lat: Double, lon: Double, accH: Double, speed: Double, bearingDeg: Double, nSats: Int) {
        if (fqN == fixCap) { fqHead = (fqHead + 1) % fixCap; fqN-- }
        val i = (fqHead + fqN) % fixCap
        fqT[i] = tFix; fqLat[i] = lat; fqLon[i] = lon; fqAcc[i] = accH; fqV[i] = speed; fqBrg[i] = bearingDeg; fqSats[i] = nSats; fqN++
    }

    /** Native IMU samples (accelerometer / gyroscope timestamps in seconds since session start). */
    fun onAccNative(t: Double, ax: Double, ay: Double, az: Double) = resampler.addAcc(t, ax, ay, az)
    fun onGyrNative(t: Double, gx: Double, gy: Double, gz: Double) = resampler.addGyro(t, gx, gy, gz)

    private fun setSStart(x: Double, y: Double) {
        val cor = corridorsEnu[corridorIdx]; cor.project(x, y, proj); sStart = proj.s
        event(lastFixT, "BAND_ORIGIN", String.format(java.util.Locale.US, "s_start=%.1f", sStart))
    }

    // ------------------------------------------------------------------ fixes
    private fun processFixesUpTo(t: Double) {
        while (fqN > 0 && fqT[fqHead] <= t) {
            val i = fqHead; fqHead = (fqHead + 1) % fixCap; fqN--
            processFix(fqT[i], fqLat[i], fqLon[i], fqAcc[i], fqV[i], fqBrg[i], fqSats[i], t)
        }
    }

    private fun processFix(tf: Double, lat: Double, lon: Double, accH: Double, v: Double, brg: Double, nSats: Int, tNow: Double) {
        if (origin == null) setOrigin(lat, lon)
        val o = origin!!
        val x = o.x(lon); val y = o.y(lat)
        nFixes++
        // ---- rule-1 real-outage detector
        val gap = !tPrevFix.isNaN() && (tf - tPrevFix) > 1.5
        val accBad = accH > 30.0
        val satsBad = nSats < 4
        val cn0Bad = cfg.applyCn0Rule && !statusCn0.isNaN() && statusCn0 < 22.0
        val realBad = gap || accBad || (satsBad && prevSatsBad) || cn0Bad
        prevSatsBad = satsBad
        // ---- course from consecutive fixes (Run.f_course)
        var course = Double.NaN
        if (!tPrevFix.isNaN()) {
            val dtf = tf - tPrevFix; val dx = x - xPrevFix; val dy = y - yPrevFix
            if (dtf > 0.5 && dtf < 1.6 && hypot(dx, dy) / dtf > 1.5) course = atan2(dy, dx)
        }
        // ---- motion start (first fix in the ride with v > 1)
        if (tMotionStart.isNaN() && phase == Phase.RIDE && v > 1.0) { tMotionStart = tf; event(tf, "MOTION_START", String.format(java.util.Locale.US, "v=%.2f", v)) }
        // ---- fusion init at the first fix
        if (fusion == null) { initFusion(x, y); fusion?.seedHistory(tf) }
        // ---- scenario gate on the raw fix
        val sim = simulatedDenial(tf, x, y)
        val withheld = sim || realBad
        if (realBad && !realBadNow) event(tf, "REAL_OUTAGE", "gap=$gap acc=$accBad sats=${satsBad && prevSatsBad} cn0=$cn0Bad")
        realBadNow = realBad
        aligner.onFix(tf, v, !withheld)
        if (!withheld) heading?.let { h -> h.gnssCourse(tf, course, v, h.wLp[2]) }
        // ---- pending for the fusion filter
        if (pN < pCap) { pT[pN] = tf; pX[pN] = x; pY[pN] = y; pV[pN] = v; pAcc[pN] = accH; pW[pN] = withheld; pN++ }
        // ---- outage bookkeeping (the gate knows the truth; the engine does not)
        if (withheld) {
            if (outage == null) {
                val ox = if (tPrevFix.isNaN()) x else xPrevFix; val oy = if (tPrevFix.isNaN()) y else yPrevFix
                outage = Outage(if (tPrevFix.isNaN()) tf else tPrevFix, sim, armedNow(), ox, oy)
                event(tf, if (sim) "SIM_ENTER" else "OUTAGE_ENTER", String.format(java.util.Locale.US, "armed=%b", armedNow()))
            }
            val og = outage!!
            og.dist += hypot(x - og.lastX, y - og.lastY); og.lastX = x; og.lastY = y; og.path.add(doubleArrayOf(x, y))
            if (!lastPosX.isNaN()) og.maxErr = max(og.maxErr, hypot(lastPosX - x, lastPosY - y))
            healthySince = Double.NaN
        } else {
            if (healthySince.isNaN()) healthySince = tf
            closeOutage(tf, doubleArrayOf(x, y))
            lastHealthyT = tf
            corridorLogic(x, y, v)
        }
        withheldNow = withheld; simNow = sim
        lastFixT = tf; lastFixLat = lat; lastFixLon = lon; lastFixAcc = accH; lastFixX = x; lastFixY = y
        tPrevFix = tf; xPrevFix = x; yPrevFix = y
    }

    private fun armedNow(): Boolean = state?.armed ?: false

    private fun closeOutage(t: Double, retXY: DoubleArray?) {
        val og = outage ?: return
        outage = null
        if (retXY != null) { og.dist += hypot(retXY[0] - og.lastX, retXY[1] - og.lastY); og.path.add(retXY) }
        val endErr = if (retXY != null && !lastPosX.isNaN()) hypot(lastPosX - retXY[0], lastPosY - retXY[1]) else Double.NaN
        val o = origin!!
        val summary = OutageSummary(og.tStart, t, og.dist, t - og.tStart, endErr, max(og.maxErr, if (endErr.isNaN()) 0.0 else endErr), Double.NaN, og.sim, og.armedAtEntry, corridorsEnu.getOrNull(corridorIdx)?.def?.id)
        outages.add(summary)
        recoveryWatchUntil = t + Fusion.REC_S + 0.5; recoveryStepMax = 0.0
        if (retXY != null) {
            reveal = RevealInfo(og.path.map { doubleArrayOf(o.lat(it[1]), o.lon(it[0])) }, og.dist, t - og.tStart, endErr, summary.maxErrorM, t, og.sim, og.armedAtEntry)
            event(t, "REVEAL", String.format(java.util.Locale.US, "off_by_m=%.1f distance_m=%.0f duration_s=%.0f max_err_m=%.1f sim=%b armed=%b", endErr, og.dist, t - og.tStart, summary.maxErrorM, og.sim, og.armedAtEntry))
        } else event(t, "OUTAGE_END", String.format(java.util.Locale.US, "distance_m=%.0f duration_s=%.0f (no return fix)", og.dist, t - og.tStart))
    }

    /** A forced corridor id that is not in the library falls back to automatic recognition (logged once). */
    private val autoRecognition: Boolean = cfg.corridorAuto || (cfg.forcedCorridorId != null && cfg.corridors.none { it.id == cfg.forcedCorridorId })

    private fun initFusion(x: Double, y: Double) {
        val forced = cfg.forcedCorridorId?.let { id -> corridorsEnu.indexOfFirst { it.def.id == id } } ?: -1
        if (cfg.forcedCorridorId != null && forced < 0) event(lastFixT.takeIf { !it.isNaN() } ?: 0.0, "CORRIDOR", "forced id '${cfg.forcedCorridorId}' not in the library: automatic recognition")
        if (forced >= 0) {
            val cor = corridorsEnu[forced]; cor.project(x, y, proj)
            fusion = Fusion.corridor(cor, proj.s, proj.d, cfg.kEst); corridorIdx = forced
            event(lastFixT.takeIf { !it.isNaN() } ?: 0.0, "CORRIDOR", "forced ${cor.def.id} s=${"%.1f".format(proj.s)} d=${"%.1f".format(proj.d)}")
            if (sStart.isNaN()) sStart = proj.s
        } else fusion = Fusion.general(x, y, cfg.kEst)
    }

    /** Corridor recognition (8 consecutive healthy fixes within 15 m) and the off-corridor fallback (3 consecutive > 15 m). */
    private fun corridorLogic(x: Double, y: Double, v: Double) {
        val f = fusion ?: return
        if (corridorIdx < 0) {
            if (!autoRecognition) return
            for ((ci, cor) in corridorsEnu.withIndex()) {
                cor.project(x, y, proj)
                recogCount[ci] = if (abs(proj.d) < 15.0) recogCount[ci] + 1 else 0
                if (nFixes <= 9) event(lastFixT, "RECOG", "${cor.def.id} fix=$nFixes d=${"%.1f".format(proj.d)} s=${"%.1f".format(proj.s)} count=${recogCount[ci]} corridors=${corridorsEnu.size}")
                if (recogCount[ci] >= 8) {
                    f.position(pos); cor.project(pos[0], pos[1], proj)
                    val nf = Fusion.corridor(cor, proj.s, proj.d, cfg.kEst); nf.adoptFrom(f); fusion = nf; corridorIdx = ci
                    for (j in recogCount.indices) recogCount[j] = 0
                    if (phase == Phase.RIDE || phase == Phase.STOP_STAND) setSStart(lastFixX.takeIf { nFixes > 0 } ?: x, lastFixY) else sStart = Double.NaN
                    if (sStart.isNaN()) { cor.project(x, y, proj); sStart = proj.s }
                    event(lastFixT, "CORRIDOR", "recognised ${cor.def.id} (${cor.def.name}) s=${"%.1f".format(proj.s)} d=${"%.1f".format(proj.d)} s_start=${"%.1f".format(sStart)}")
                    return
                }
            }
        } else if (f.mode == Fusion.Mode.CORRIDOR) {
            val cor = corridorsEnu[corridorIdx]; cor.project(x, y, proj)
            offCount = if (abs(proj.d) > 15.0) offCount + 1 else 0
            if (offCount >= 3 && cfg.forcedCorridorId == null) {
                val nf = Fusion.general(x, y, cfg.kEst); nf.adoptFrom(f); fusion = nf
                event(lastFixT, "CORRIDOR", "left ${cor.def.id}: |d|>15 m on 3 fixes -> general mode at the fix")
                corridorIdx = -1; offCount = 0; sStart = Double.NaN; dirAnnounced = 0
            }
        }
    }

    private fun simulatedDenial(tf: Double, x: Double, y: Double): Boolean {
        val sc = cfg.scenario
        return when (sc.kind) {
            Scenario.Kind.NONE -> false
            Scenario.Kind.MANUAL -> manualDenial
            Scenario.Kind.TIMER -> !tMotionStart.isNaN() && tf >= tMotionStart + sc.timerStartS && tf < tMotionStart + sc.timerStartS + sc.timerHoldS
            Scenario.Kind.BAND -> {
                val f = fusion ?: return false
                if (corridorIdx < 0 || f.mode != Fusion.Mode.CORRIDOR || f.dir == 0.0 || sStart.isNaN()) return false
                val cor = corridorsEnu[corridorIdx]; cor.project(x, y, proj)
                val dist = f.dir * (proj.s - sStart)
                dist >= sc.bandFromM && (sc.bandToM == null || dist < sc.bandToM)
            }
        } || (sc.kind != Scenario.Kind.MANUAL && manualDenial)
    }

    // ------------------------------------------------------------------ 100 Hz step
    /** A 100 Hz phone-frame sample on the grid (k = round(t / 0.01)); v = [ax, ay, az, gx, gy, gz]. */
    fun onImu100(k: Long, t: Double, v: DoubleArray) {
        processFixesUpTo(t)
        aP[0] = v[0]; aP[1] = v[1]; aP[2] = v[2]; wP[0] = v[3]; wP[1] = v[4]; wP[2] = v[5]
        if (cfg.alignmentOverride == null) {
            when (phase) {
                Phase.IDLE, Phase.STAND -> aligner.standSample(t, aP, wP)
                Phase.RIDE, Phase.STOP_STAND -> if (aligner.rideSample(t, aP, wP, !withheldNow && !lastFixT.isNaN() && t - lastFixT < 1.5)) onAlignmentChanged(t)
                Phase.DONE -> {}
            }
        }
        Mat3.apply(aligner.rPb, aP[0], aP[1], aP[2], aB); Mat3.apply(aligner.rPb, wP[0], wP[1], wP[2], wB)
        ring.push(aB, wB)
        heading?.step(t, aB, wB)
        if (k % 10L == 0L) tick(t, k)
    }

    private fun onAlignmentChanged(t: Double) {
        val h = heading ?: return
        Mat3.apply(aligner.rPb, aligner.biasP[0], aligner.biasP[1], aligner.biasP[2], biasB); h.setBias(biasB)
        val dpsi = Geo.wrap(aligner.psi - lastPsiAligner)
        if (dpsi != 0.0) h.rotateFrameZ(dpsi)
        lastPsiAligner = aligner.psi
        val e = aligner.pitchRollYawDeg
        event(t, "ALIGN", String.format(java.util.Locale.US, "psi=%.2f (%s) pitch=%.2f roll=%.2f blocks=%d moved_at=%.1f sway_ratio=%.1f", Geo.deg(aligner.psi), aligner.psiSource, e[0], e[1], aligner.rideGravityBlocks, aligner.movedAtS, aligner.swayRatio))
    }

    // ------------------------------------------------------------------ 10 Hz tick
    private fun tick(t: Double, k: Long) {
        val t0 = System.nanoTime()
        val f = fusion
        val h = heading
        val psi = h?.psi ?: 0.0
        var matched = false; var mmConf = 0.0
        var dispX = Double.NaN; var dispY = Double.NaN
        if (f != null) {
            f.predict(t, psi)
            speedSource.speedAt(t, ring, mo)
            f.updateModel(mo.vRaw, mo.sigma, mo.still)
            for (i in 0 until pN) { if (pW[i]) f.gnssLost() else f.updateGnss(pT[i], pX[i], pY[i], pV[i], pAcc[i]) }
            pN = 0
            if (cfg.gapAtTick && !withheldNow && !lastFixT.isNaN() && t - lastFixT > 1.5 && phase != Phase.DONE) {
                withheldNow = true; realBadNow = true; f.gnssLost(); healthySince = Double.NaN
                if (outage == null) { outage = Outage(lastFixT, false, armedNow(), lastFixX, lastFixY); event(t, "OUTAGE_ENTER", "no fix for 1.5 s") }
                event(t, "REAL_OUTAGE", "gap at tick")
            }
            f.position(pos)
            aligner.setFilterSpeed(f.v)
            dispX = pos[0]; dispY = pos[1]
            if (f.mode == Fusion.Mode.GENERAL && cfg.mapMatch) mapMatcher?.step(t, pos[0], pos[1], psi)?.let { r -> if (r.confident) { matched = true; dispX = r.x; dispY = r.y }; mmConf = r.conf }
        } else {
            speedSource.speedAt(t, ring, mo)
        }
        // ---- mode
        val newMode = if (!withheldNow) (if (f != null && (t - f.tReturn) < Fusion.REC_S) Mode.RECOVERING else Mode.GNSS_INS) else Mode.INERTIAL
        if (newMode != lastMode) {
            event(t, "MODE", "${lastMode.name}->${newMode.name}${if (simNow) " sim" else ""}")
            if (newMode == Mode.INERTIAL) { drMeters = 0.0; drStartT = t }
            lastMode = newMode
        }
        mode = newMode
        if (f != null && !lastPosX.isNaN()) {
            val step = hypot(pos[0] - lastPosX, pos[1] - lastPosY)
            if (mode == Mode.INERTIAL) drMeters += step
            if (t <= recoveryWatchUntil) { recoveryStepMax = max(recoveryStepMax, step); outages.lastOrNull()?.let { it.recoveryStepM = recoveryStepMax } }
        }
        if (f != null) { lastPosX = pos[0]; lastPosY = pos[1] }
        // ---- readiness
        val windowFull = ring.full
        val gnssHealthy5 = !healthySince.isNaN() && !withheldNow && (t - healthySince) >= 5.0
        val quietOk = aligner.standQuiet || (!tMotionStart.isNaN() && t - tMotionStart >= 60.0)
        val swayOk = !aligner.psiSway.isNaN() || cfg.alignmentOverride != null
        val headingOk = h?.init == true
        val armed = headingOk && swayOk && gnssHealthy5 && windowFull && quietOk && aligner.standValid
        val missing = buildString { if (!headingOk) append("heading "); if (!swayOk) append("sway "); if (!gnssHealthy5) append("gnss5s "); if (!windowFull) append("window "); if (!quietOk) append("stand60 "); if (!aligner.standValid) append("align ") }.trim()
        if (armed != armedWas) { event(t, if (armed) "ARMED" else "DISARMED", missing); armedWas = armed }
        // ---- band geometry for the UI
        var bandDist = Double.NaN; var bandKnown = false
        if (cfg.scenario.kind == Scenario.Kind.BAND && f != null && f.mode == Fusion.Mode.CORRIDOR && f.dir != 0.0 && !sStart.isNaN()) {
            bandKnown = true; bandDist = cfg.scenario.bandFromM - f.dir * (f.x[0] - sStart)
        }
        val inBand = simNow
        if (inBand != inBandPrev) { event(t, if (inBand) "BAND_ENTER" else "BAND_EXIT", ""); inBandPrev = inBand }
        // ---- direction announce
        if (f != null && f.mode == Fusion.Mode.CORRIDOR && f.dir != 0.0 && dirAnnounced != f.dir.toInt()) {
            dirAnnounced = f.dir.toInt(); event(t, "DIRECTION", if (f.dir > 0) "AB" else "BA")
            if (sStart.isNaN()) { corridorsEnu[corridorIdx].project(lastFixX, lastFixY, proj); sStart = proj.s }
        }
        val o = origin
        val tickMs = (System.nanoTime() - t0) / 1e6
        tickCount++; tickMsSum += tickMs; if (tickMs > tickMsMax) tickMsMax = tickMs; tickMsMean = tickMsSum / tickCount
        val cor = corridorsEnu.getOrNull(corridorIdx)
        val e = aligner.pitchRollYawDeg
        val st = EngineState(
            t = t, k = k, phase = phase, mode = mode, sim = simNow, scenarioArmed = cfg.scenario.kind != Scenario.Kind.NONE, withheld = withheldNow, realOutage = realBadNow,
            hasPosition = f != null && o != null, lat = if (f != null && o != null) o.lat(pos[1]) else Double.NaN, lon = if (f != null && o != null) o.lon(pos[0]) else Double.NaN,
            x = if (f != null) pos[0] else Double.NaN, y = if (f != null) pos[1] else Double.NaN, v = f?.v ?: 0.0,
            headingDeg = Geo.deg(psi), headingSigmaDeg = h?.let { Geo.deg(it.sigmaPsi) } ?: Double.NaN, headingInit = headingOk, scale = f?.k ?: 1.0, sigmaPos = f?.sigmaPos ?: Double.NaN,
            vModel = mo.vRaw, sigmaModel = mo.sigma, stop = mo.still, modelValid = mo.valid, tickMs = tickMs, modelMs = mo.modelMs,
            corridorId = cor?.def?.id, corridorName = cor?.def?.name, s = if (f?.mode == Fusion.Mode.CORRIDOR) f.x[0] else Double.NaN, d = if (f?.mode == Fusion.Mode.CORRIDOR) f.dHold else Double.NaN,
            dir = f?.dir?.toInt() ?: 0, fusionMode = f?.mode?.name?.lowercase() ?: "none",
            dispLat = if (o != null && !dispX.isNaN()) o.lat(dispY) else Double.NaN, dispLon = if (o != null && !dispX.isNaN()) o.lon(dispX) else Double.NaN, dispX = dispX, dispY = dispY, matched = matched, mmConf = mmConf,
            sats = statusSats, cn0 = statusCn0, gnssAgeS = if (lastFixT.isNaN()) Double.NaN else t - lastFixT, gnssAcc = lastFixAcc, fixLat = lastFixLat, fixLon = lastFixLon, nFixes = nFixes,
            armed = armed, armedMissing = missing, standQuiet = aligner.standQuiet, psiSource = aligner.psiSource, psiDeg = Geo.deg(aligner.psi), pitchDeg = e[0], rollDeg = e[1],
            biasDps = doubleArrayOf(Geo.deg(aligner.biasP[0]), Geo.deg(aligner.biasP[1]), Geo.deg(aligner.biasP[2])), gMag = aligner.gMag, gravityBlocks = aligner.rideGravityBlocks, movedAtS = aligner.movedAtS, swayRatio = aligner.swayRatio, tMotionStart = tMotionStart,
            drMeters = drMeters, drSeconds = if (mode == Mode.INERTIAL && !drStartT.isNaN()) t - drStartT else 0.0, bandDistM = bandDist, bandKnown = bandKnown, bandFromM = cfg.scenario.bandFromM, bandToM = cfg.scenario.bandToM, sStart = sStart,
            reveal = reveal?.takeIf { t - it.tReturn < 8.0 }, outages = outages, vib = ring.lastVib, gyrRms = ring.lastGyr, speedSource = speedSource.name, nRejectedFixes = f?.nGnssRejected ?: 0
        )
        state = st
        lastTick = t
        listener?.onTick(st)
    }

    val corridorId: String? get() = corridorsEnu.getOrNull(corridorIdx)?.def?.id
    val outageSummaries: List<OutageSummary> get() = outages
}
