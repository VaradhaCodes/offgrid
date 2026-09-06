package com.snu.idr.engine

import com.snu.idr.engine.replay.SessionReader
import org.json.JSONObject
import java.io.File

/** Paths and loaders shared by the engine tests. The repo root is found by walking up from the module directory. */
object TestData {
    val root: File by lazy {
        var d = File(System.getProperty("user.dir")).absoluteFile
        while (!File(d, "data").isDirectory || !File(d, "engine").isDirectory) { d = d.parentFile ?: error("repo root not found from ${System.getProperty("user.dir")}") }
        d
    }
    val assets: File get() = File(root, "IDRNav/app/src/main/assets")

    /** predDir: the deployed joint model's own predictions (pred/deploy_joint_r*), which is what produced the reference CSVs. */
    class Ref(val tag: String, val session: String, val corridorId: String, val predDir: String) {
        val rawDir get() = File(root, "data/$tag/sessions/$session")
        val processedDir get() = File(root, "data/processed/$session")
        val refCsv get() = File(root, "data/qa/replay/${session}_corridor_mm0.csv")
        val predCsv get() = File(root, "data/speed_model/pred/$predDir/$session.csv")
    }
    val R1 = Ref("route1", "20260905_003612_SNU_AJB_AB_run1", "SNU_R1", "deploy_joint_r1")
    val R2 = Ref("route2", "20260905_033817_SNU_AJB_AB_run4", "SNU_R2", "deploy_joint_r2")

    fun corridorLibrary(): List<CorridorDef> {
        val dir = File(assets, "corridors")
        val lib = JSONObject(File(dir, "library.json").readText()).getJSONArray("corridors")
        return (0 until lib.length()).map { i ->
            val id = lib.getString(i); val cfg = JSONObject(File(dir, "$id.json").readText())
            CorridorDef.fromJson(File(dir, "$id.json").readText(), File(dir, cfg.getString("geojson")).readText())
        }
    }

    fun modelPack(): ModelPack = ModelPack.load(File(assets, "model/model.json").readText(), File(assets, "model/weights.bin").readBytes())

    fun roadGraph(): RoadGraph? {
        val f = File(assets, "map/graph.json"); if (f.exists()) return RoadGraph.fromCompactJson(f.readText())
        val g = File(root, "data/map/snu_osm_highways_900m.json"); return if (g.exists()) RoadGraph.fromOverpassJson(g.readText()) else null
    }

    /** align.json -> AlignmentOverride (R_pb, phone-frame bias, |g|), quiet from data/qa/<tag>.csv flags. */
    fun alignment(ref: Ref): AlignmentOverride {
        val a = JSONObject(File(ref.processedDir, "align.json").readText())
        val r = a.getJSONArray("R_pb"); val rPb = DoubleArray(9) { r.getJSONArray(it / 3).getDouble(it % 3) }
        val b = a.getJSONArray("bias_rad_s"); val bias = DoubleArray(3) { b.getDouble(it) }
        var quiet = true
        SessionReader.readCsv(File(root, "data/qa/${ref.tag}.csv")) { h, c -> if (c[h["session"]!!] == ref.session) quiet = !c[h["flags_str"]!!].contains("STAND_MOTION_START") }
        return AlignmentOverride(rPb, bias, a.getDouble("g_mag"), quiet)
    }

    fun anchor(ref: Ref): DoubleArray {
        val s = JSONObject(File(ref.rawDir, "session.json").readText()).getJSONObject("start_anchor")
        return doubleArrayOf(s.getDouble("lat"), s.getDouble("lon"))
    }

    fun predSource(ref: Ref): PredCsvSpeedSource {
        val t = ArrayList<Double>(); val v = ArrayList<Double>(); val s = ArrayList<Double>(); val st = ArrayList<Boolean>()
        SessionReader.readCsv(ref.predCsv) { h, c -> t.add(c[h["t_s"]!!].toDouble()); v.add(c[h["v_raw"]!!].toDouble()); s.add(c[h["sigma"]!!].toDouble()); st.add(c[h["still"]!!].toDouble() != 0.0) }
        return PredCsvSpeedSource(t.toDoubleArray(), v.toDoubleArray(), s.toDoubleArray(), st.toBooleanArray())
    }

    class RefRow(val t: Double, val x: Double, val y: Double, val v: Double, val headingDeg: Double, val mode: String, val sigmaPos: Double)

    fun reference(ref: Ref): List<RefRow> {
        val out = ArrayList<RefRow>()
        SessionReader.readCsv(ref.refCsv) { h, c -> out.add(RefRow(c[h["t_s"]!!].toDouble(), c[h["x_m"]!!].toDouble(), c[h["y_m"]!!].toDouble(), c[h["v"]!!].toDouble(), c[h["heading_deg"]!!].toDouble(), c[h["mode"]!!], c[h["sigma_pos"]!!].toDouble())) }
        return out
    }

    /** Collects every tick and event. */
    class Recorder : EngineListener {
        val ticks = ArrayList<EngineState>(); val events = ArrayList<Triple<Double, String, String>>()
        override fun onTick(s: EngineState) { ticks.add(s) }
        override fun onEvent(t: Double, type: String, text: String) { events.add(Triple(t, type, text)) }
        fun modeTransitions(): List<Pair<Double, String>> {
            val out = ArrayList<Pair<Double, String>>(); var last = ""
            for (s in ticks) { if (s.mode.name != last) { out.add(Pair(s.t, s.mode.name)); last = s.mode.name } }
            return out
        }
    }

    fun refTransitions(rows: List<RefRow>): List<Pair<Double, String>> {
        val out = ArrayList<Pair<Double, String>>(); var last = ""
        for (r in rows) { if (r.mode != last) { out.add(Pair(r.t, r.mode)); last = r.mode } }
        return out
    }

    fun fmt(v: Double, d: Int = 3) = String.format(java.util.Locale.US, "%.${d}f", v)
}
