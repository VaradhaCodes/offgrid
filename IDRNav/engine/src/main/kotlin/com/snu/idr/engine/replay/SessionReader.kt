package com.snu.idr.engine.replay

import com.snu.idr.engine.Engine
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.FileReader

/**
 * Reads a raw IDR Logger session folder (acc.csv, gyr.csv, gnss_fix.csv, gnss_status.csv, events.csv, session.json) and drives an
 * [Engine] in time order through the same path the phone uses (native IMU -> resampler). Times are seconds since SESSION_START.
 */
class SessionReader(val dir: File) {
    val name: String = dir.name
    val meta: JSONObject = JSONObject(File(dir, "session.json").readText())
    val t0Ns: Long
    val events: List<Pair<Double, String>>
    val anchorLat: Double; val anchorLon: Double
    val routeId: String = meta.optString("route_id", "")
    val direction: String = meta.optString("direction", "")

    // raw arrays
    val accT: DoubleArray; val accX: DoubleArray; val accY: DoubleArray; val accZ: DoubleArray
    val gyrT: DoubleArray; val gyrX: DoubleArray; val gyrY: DoubleArray; val gyrZ: DoubleArray
    val fixT: DoubleArray; val fixLat: DoubleArray; val fixLon: DoubleArray; val fixAcc: DoubleArray; val fixV: DoubleArray; val fixBrg: DoubleArray; val fixSats: IntArray
    val stT: DoubleArray; val stUsed: IntArray; val stCn0: DoubleArray
    val tEnd: Double

    init {
        val ev = ArrayList<Pair<Double, String>>()
        var t0 = 0L
        readCsv(File(dir, "events.csv")) { h, c -> if (c[h["type"]!!] == "SESSION_START" && t0 == 0L) t0 = c[h["t_ns"]!!].toLong() }
        t0Ns = t0
        readCsv(File(dir, "events.csv")) { h, c -> ev.add(Pair((c[h["t_ns"]!!].toLong() - t0Ns) / 1e9, c[h["type"]!!])) }
        events = ev
        val a = meta.optJSONObject("start_anchor")
        anchorLat = a?.optDouble("lat", Double.NaN) ?: Double.NaN; anchorLon = a?.optDouble("lon", Double.NaN) ?: Double.NaN
        // IMU
        val at = DoubleArrayList(); val ax = DoubleArrayList(); val ay = DoubleArrayList(); val az = DoubleArrayList()
        var last = Long.MIN_VALUE
        readCsv(File(dir, "acc.csv")) { h, c -> val tn = c[h["t_ns"]!!].toLong(); if (tn > last) { last = tn; at.add((tn - t0Ns) / 1e9); ax.add(c[h["ax"]!!].toDouble()); ay.add(c[h["ay"]!!].toDouble()); az.add(c[h["az"]!!].toDouble()) } }
        accT = at.toArray(); accX = ax.toArray(); accY = ay.toArray(); accZ = az.toArray()
        val gt = DoubleArrayList(); val gx = DoubleArrayList(); val gy = DoubleArrayList(); val gz = DoubleArrayList(); last = Long.MIN_VALUE
        readCsv(File(dir, "gyr.csv")) { h, c -> val tn = c[h["t_ns"]!!].toLong(); if (tn > last) { last = tn; gt.add((tn - t0Ns) / 1e9); gx.add(c[h["gx"]!!].toDouble()); gy.add(c[h["gy"]!!].toDouble()); gz.add(c[h["gz"]!!].toDouble()) } }
        gyrT = gt.toArray(); gyrX = gx.toArray(); gyrY = gy.toArray(); gyrZ = gz.toArray()
        // fixes
        val ft = DoubleArrayList(); val fla = DoubleArrayList(); val flo = DoubleArrayList(); val fac = DoubleArrayList(); val fv = DoubleArrayList(); val fb = DoubleArrayList(); val fs = ArrayList<Int>(); last = Long.MIN_VALUE
        readCsv(File(dir, "gnss_fix.csv")) { h, c ->
            val tn = c[h["t_ns"]!!].toLong(); if (tn > last) { last = tn
                ft.add((tn - t0Ns) / 1e9); fla.add(c[h["lat"]!!].toDouble()); flo.add(c[h["lon"]!!].toDouble()); fac.add(c[h["acc_h"]!!].toDoubleOrNan())
                fv.add(c[h["speed"]!!].toDoubleOrNan()); fb.add(c[h["bearing"]!!].toDoubleOrNan()); fs.add(c[h["n_sats_used"]!!].toIntOrNull() ?: 0) }
        }
        fixT = ft.toArray(); fixLat = fla.toArray(); fixLon = flo.toArray(); fixAcc = fac.toArray(); fixV = fv.toArray(); fixBrg = fb.toArray(); fixSats = fs.toIntArray()
        // status epochs: group rows by t_ns
        val st = DoubleArrayList(); val su = ArrayList<Int>(); val sc = DoubleArrayList()
        val f = File(dir, "gnss_status.csv")
        if (f.exists()) {
            var curT = Long.MIN_VALUE; var used = 0; var cn0Sum = 0.0; var cn0N = 0
            fun flush() { if (curT != Long.MIN_VALUE) { st.add((curT - t0Ns) / 1e9); su.add(used); sc.add(if (cn0N > 0) cn0Sum / cn0N else Double.NaN) } }
            readCsv(f) { h, c ->
                val tn = c[h["t_ns"]!!].toLong()
                if (tn != curT) { flush(); curT = tn; used = 0; cn0Sum = 0.0; cn0N = 0 }
                val inFix = c[h["used_in_fix"]!!].equals("true", true)
                if (inFix) { used++; val v = c[h["cn0"]!!].toDoubleOrNan(); if (!v.isNaN() && v > 0) { cn0Sum += v; cn0N++ } }
            }
            flush()
        }
        stT = st.toArray(); stUsed = su.toIntArray(); stCn0 = sc.toArray()
        tEnd = maxOf(accT.lastOrNull() ?: 0.0, events.lastOrNull()?.first ?: 0.0)
    }

    val motionStartT: Double get() {
        val ride0 = events.firstOrNull { it.second == "RIDE_START" }?.first ?: return Double.NaN
        val ride1 = events.firstOrNull { it.second == "STOP_CALIB_START" }?.first ?: tEnd
        for (i in fixT.indices) if (fixT[i] >= ride0 && fixT[i] <= ride1 && fixV[i] > 1.0) return fixT[i]
        return Double.NaN
    }

    /**
     * Drives the engine. speedFactor 0 = as fast as possible, else wall-clock pacing at that multiple of real time.
     * [progress] is called with the session time every ~1 s; [shouldStop] polled every second.
     */
    fun run(engine: Engine, speedFactor: Double = 0.0, progress: ((Double) -> Unit)? = null, shouldStop: (() -> Boolean)? = null) {
        var ia = 0; var ig = 0; var ifx = 0; var ist = 0; var iev = 0
        val wall0 = System.nanoTime(); var nextProgress = 0.0
        while (true) {
            var tNext = Double.MAX_VALUE; var which = -1
            if (iev < events.size && events[iev].first < tNext) { tNext = events[iev].first; which = 0 }
            if (ifx < fixT.size && fixT[ifx] < tNext) { tNext = fixT[ifx]; which = 1 }
            if (ist < stT.size && stT[ist] < tNext) { tNext = stT[ist]; which = 2 }
            if (ig < gyrT.size && gyrT[ig] < tNext) { tNext = gyrT[ig]; which = 3 }
            if (ia < accT.size && accT[ia] < tNext) { tNext = accT[ia]; which = 4 }
            if (which < 0) break
            if (speedFactor > 0) {
                val wallTarget = wall0 + (tNext / speedFactor * 1e9).toLong()
                val wait = wallTarget - System.nanoTime()
                if (wait > 2_000_000L) try { Thread.sleep(wait / 1_000_000L) } catch (_: InterruptedException) { return }
            }
            when (which) {
                0 -> { engine.onEvent(tNext, events[iev].second); iev++ }
                1 -> { engine.onFix(fixT[ifx], fixLat[ifx], fixLon[ifx], fixAcc[ifx], fixV[ifx], fixBrg[ifx], fixSats[ifx]); ifx++ }
                2 -> { engine.onGnssStatus(stT[ist], stUsed[ist], stCn0[ist]); ist++ }
                3 -> { engine.onGyrNative(gyrT[ig], gyrX[ig], gyrY[ig], gyrZ[ig]); ig++ }
                4 -> { engine.onAccNative(accT[ia], accX[ia], accY[ia], accZ[ia]); ia++ }
            }
            if (tNext >= nextProgress) { nextProgress = tNext + 1.0; progress?.invoke(tNext); if (shouldStop?.invoke() == true) return }
        }
    }

    companion object {
        fun String.toDoubleOrNan(): Double = if (this.isEmpty() || this == "NaN" || this == "nan") Double.NaN else this.toDoubleOrNull() ?: Double.NaN

        /** Streams a CSV with a header; the callback gets (header index map, cells). Quoted commas are not expected in the numeric files. */
        fun readCsv(f: File, row: (Map<String, Int>, List<String>) -> Unit) {
            BufferedReader(FileReader(f), 1 shl 16).use { r ->
                val header = r.readLine() ?: return
                val h = HashMap<String, Int>(); header.split(',').forEachIndexed { i, s -> h[s.trim()] = i }
                while (true) {
                    val line = r.readLine() ?: break
                    if (line.isEmpty()) continue
                    val cells = splitCsv(line)
                    if (cells.size < h.size) continue
                    row(h, cells)
                }
            }
        }

        private fun splitCsv(line: String): List<String> {
            if (line.indexOf('"') < 0) return line.split(',')
            val out = ArrayList<String>(); val sb = StringBuilder(); var q = false
            for (ch in line) { when { ch == '"' -> q = !q; ch == ',' && !q -> { out.add(sb.toString()); sb.setLength(0) }; else -> sb.append(ch) } }
            out.add(sb.toString()); return out
        }
    }
}

/** Growable double list without boxing. */
class DoubleArrayList(cap: Int = 1024) {
    private var a = DoubleArray(cap); var size = 0; private set
    fun add(v: Double) { if (size == a.size) a = a.copyOf(a.size * 2); a[size++] = v }
    fun toArray(): DoubleArray = a.copyOf(size)
}

/**
 * The processed-track path for the conformance test: data/processed/<session>/track_100hz.csv (phone-frame 100 Hz grid from
 * SESSION_START) + gnss_fixes.csv, fed directly to Engine.onImu100 / onFix, events from the raw session.
 */
class ProcessedTrackReader(val processedDir: File, val rawDir: File) {
    val t: DoubleArray; val imu: Array<DoubleArray>   // [n][6]
    val fixT: DoubleArray; val fixLat: DoubleArray; val fixLon: DoubleArray; val fixAcc: DoubleArray; val fixV: DoubleArray; val fixBrg: DoubleArray; val fixSats: IntArray
    val events: List<Pair<Double, String>>
    val truthX: DoubleArray; val truthY: DoubleArray

    init {
        val tl = DoubleArrayList(); val rows = ArrayList<DoubleArray>(); val tx = DoubleArrayList(); val ty = DoubleArrayList()
        SessionReader.readCsv(File(processedDir, "track_100hz.csv")) { h, c ->
            tl.add(c[h["t_s"]!!].toDouble())
            rows.add(doubleArrayOf(c[h["ax"]!!].toDouble(), c[h["ay"]!!].toDouble(), c[h["az"]!!].toDouble(), c[h["gx"]!!].toDouble(), c[h["gy"]!!].toDouble(), c[h["gz"]!!].toDouble()))
            tx.add(c[h["x_m"]!!].toDouble()); ty.add(c[h["y_m"]!!].toDouble())
        }
        t = tl.toArray(); imu = rows.toTypedArray(); truthX = tx.toArray(); truthY = ty.toArray()
        val ft = DoubleArrayList(); val fla = DoubleArrayList(); val flo = DoubleArrayList(); val fac = DoubleArrayList(); val fv = DoubleArrayList(); val fb = DoubleArrayList(); val fs = ArrayList<Int>()
        SessionReader.readCsv(File(processedDir, "gnss_fixes.csv")) { h, c ->
            ft.add(c[h["t_s"]!!].toDouble()); fla.add(c[h["lat"]!!].toDouble()); flo.add(c[h["lon"]!!].toDouble()); fac.add(c[h["acc_h"]!!].toDouble())
            fv.add(c[h["speed"]!!].toDouble()); fb.add(with(SessionReader) { c[h["bearing"]!!].toDoubleOrNan() }); fs.add(c[h["n_sats_used"]!!].toDouble().toInt())
        }
        fixT = ft.toArray(); fixLat = fla.toArray(); fixLon = flo.toArray(); fixAcc = fac.toArray(); fixV = fv.toArray(); fixBrg = fb.toArray(); fixSats = fs.toIntArray()
        var t0 = 0L; val ev = ArrayList<Pair<Double, String>>()
        SessionReader.readCsv(File(rawDir, "events.csv")) { h, c -> if (c[h["type"]!!] == "SESSION_START" && t0 == 0L) t0 = c[h["t_ns"]!!].toLong() }
        SessionReader.readCsv(File(rawDir, "events.csv")) { h, c -> ev.add(Pair((c[h["t_ns"]!!].toLong() - t0) / 1e9, c[h["type"]!!])) }
        events = ev
    }

    fun run(engine: Engine) {
        var ifx = 0; var iev = 0
        for (i in t.indices) {
            val ti = t[i]
            while (iev < events.size && events[iev].first <= ti) { engine.onEvent(events[iev].first, events[iev].second); iev++ }
            while (ifx < fixT.size && fixT[ifx] <= ti) { engine.onFix(fixT[ifx], fixLat[ifx], fixLon[ifx], fixAcc[ifx], fixV[ifx], fixBrg[ifx], fixSats[ifx]); ifx++ }
            engine.onImu100(Math.round(ti / 0.01), ti, imu[i])
        }
        while (iev < events.size) { engine.onEvent(events[iev].first, events[iev].second); iev++ }
    }
}
