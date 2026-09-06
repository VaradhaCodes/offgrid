package com.snu.idr.engine

import com.snu.idr.engine.replay.ProcessedTrackReader
import com.snu.idr.engine.replay.SessionReader
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs
import kotlin.math.hypot

/**
 * Spec §9 conformance against data/qa/replay/<session>_corridor_mm0.csv (outage from motion start + 30 s to the end, corridor mode,
 * k off). Level A isolates the maths (offline alignment from align.json, speed from the Python prediction file, the processed 100 Hz
 * track). Level C runs the phone path (raw 420 Hz files -> causal resampler -> online alignment -> Kotlin CNN) and reports.
 */
class ConformanceTest {
    private fun compare(label: String, rec: TestData.Recorder, ref: List<TestData.RefRow>, headingFrom: Double = 0.0): DoubleArray {
        val byT = HashMap<Long, TestData.RefRow>(); for (r in ref) byT[Math.round(r.t * 10)] = r
        var maxPos = 0.0; var tMaxPos = 0.0; var maxHead = 0.0; var tMaxHead = 0.0; var n = 0; var sumPos = 0.0; var maxV = 0.0
        var endPos = 0.0
        for (s in rec.ticks) {
            if (!s.hasPosition) continue
            val r = byT[Math.round(s.t * 10)] ?: continue
            val dp = hypot(s.x - r.x, s.y - r.y); n++; sumPos += dp; endPos = dp
            if (dp > maxPos) { maxPos = dp; tMaxPos = s.t }
            if (s.t >= headingFrom) { val dh = abs(Geo.deg(Geo.wrap(Geo.rad(s.headingDeg - r.headingDeg)))); if (dh > maxHead) { maxHead = dh; tMaxHead = s.t } }
            maxV = maxOf(maxV, abs(s.v - r.v))
        }
        val tr = rec.modeTransitions(); val rt = TestData.refTransitions(ref)
        var maxDt = 0.0
        val trS = tr.joinToString(" ") { "${it.second}@${TestData.fmt(it.first, 1)}" }; val rtS = rt.joinToString(" ") { "${it.second}@${TestData.fmt(it.first, 1)}" }
        if (tr.size == rt.size) for (i in tr.indices) maxDt = maxOf(maxDt, abs(tr[i].first - rt[i].first)) else maxDt = Double.NaN
        println("[$label] ticks compared $n | max |dpos| ${TestData.fmt(maxPos)} m at t=${TestData.fmt(tMaxPos, 1)} | mean ${TestData.fmt(sumPos / maxOf(n, 1))} | end ${TestData.fmt(endPos)} | max |dheading| ${TestData.fmt(maxHead)} deg at t=${TestData.fmt(tMaxHead, 1)} | max |dv| ${TestData.fmt(maxV)} | modes engine: $trS | ref: $rtS | max mode dt ${TestData.fmt(maxDt, 2)} s")
        return doubleArrayOf(maxPos, maxHead, maxDt, maxV, n.toDouble())
    }

    private fun levelA(ref: TestData.Ref): DoubleArray {
        val lib = TestData.corridorLibrary()
        val cfg = EngineConfig(corridors = lib, forcedCorridorId = ref.corridorId, corridorAuto = false, mapMatch = false, alignmentOverride = TestData.alignment(ref),
            originLatLon = TestData.anchor(ref), scenario = Scenario(Scenario.Kind.TIMER, timerStartS = 30.0, timerHoldS = 1e9), gapAtTick = false)
        val rec = TestData.Recorder()
        val engine = Engine(cfg, TestData.predSource(ref), rec)
        val t0 = System.nanoTime()
        ProcessedTrackReader(ref.processedDir, ref.rawDir).run(engine)
        val ms = (System.nanoTime() - t0) / 1e6
        val outDir = File(TestData.root, "docs/qa_app"); outDir.mkdirs()
        File(outDir, "jvmA_${ref.session}.csv").bufferedWriter().use { w -> w.write("t_s,x_m,y_m,v,heading_deg,mode,sigma_pos,s_m,d_m,v_model,stop"); w.newLine(); for (st in rec.ticks) { w.write("${TestData.fmt(st.t,3)},${TestData.fmt(st.x,4)},${TestData.fmt(st.y,4)},${TestData.fmt(st.v,4)},${TestData.fmt(st.headingDeg,4)},${st.mode},${TestData.fmt(st.sigmaPos,4)},${TestData.fmt(st.s,3)},${TestData.fmt(st.d,3)},${TestData.fmt(st.vModel,4)},${if (st.stop) 1 else 0}"); w.newLine() } }
        println("[A ${ref.session}] ${rec.ticks.size} ticks in ${TestData.fmt(ms, 0)} ms (tick mean ${TestData.fmt(engine.tickMsMean)} ms, max ${TestData.fmt(engine.tickMsMax)} ms); events: " + rec.events.filter { it.second in setOf("MODE", "CORRIDOR", "MOTION_START", "REVEAL", "OUTAGE_END", "REAL_OUTAGE") }.joinToString(" | ") { "${it.second}@${TestData.fmt(it.first, 1)} ${it.third}" })
        return compare("A ${ref.corridorId}", rec, TestData.reference(ref))
    }

    @Test fun levelA_route2_run4_mathsMatchReference() {
        val r = levelA(TestData.R2)
        assertTrue("max |dpos| ${r[0]} >= 1.0 m", r[0] < 1.0)
        assertTrue("heading ${r[1]} >= 1 deg", r[1] < 1.0)
        assertTrue("mode transitions differ by ${r[2]} s", !r[2].isNaN() && r[2] <= 0.2)
    }

    @Test fun levelA_route1_run1_mathsMatchReference() {
        val r = levelA(TestData.R1)
        assertTrue("max |dpos| ${r[0]} >= 1.0 m", r[0] < 1.0)
        assertTrue("heading ${r[1]} >= 1 deg", r[1] < 1.0)
        assertTrue("mode transitions differ by ${r[2]} s", !r[2].isNaN() && r[2] <= 0.2)
    }

    /** The phone path on the raw files with the Kotlin CNN and the online alignment; numbers reported for docs/16. */
    private fun levelC(ref: TestData.Ref, forced: Boolean, passes: Int = 1): TestData.Recorder {
        val lib = TestData.corridorLibrary(); val pack = TestData.modelPack()
        val cfg = EngineConfig(corridors = lib, forcedCorridorId = if (forced) ref.corridorId else null, corridorAuto = !forced, mapMatch = true, roadGraph = TestData.roadGraph(),
            alignmentOverride = null, originLatLon = TestData.anchor(ref), scenario = Scenario(Scenario.Kind.TIMER, timerStartS = 30.0, timerHoldS = 1e9), resamplerPasses = passes)
        val rec = TestData.Recorder()
        val src = CnnSpeedSource(pack, KotlinCnn(pack))
        val engine = Engine(cfg, src, rec)
        val reader = SessionReader(ref.rawDir)
        val t0 = System.nanoTime()
        reader.run(engine, 0.0)
        val ms = (System.nanoTime() - t0) / 1e6
        println("[C ${ref.session} forced=$forced] native ${engine.resampler.nativeCount} grid ${engine.resampler.gridCount} ticks ${rec.ticks.size} in ${TestData.fmt(ms, 0)} ms; tick mean ${TestData.fmt(engine.tickMsMean)} max ${TestData.fmt(engine.tickMsMax)} ms; model mean ${TestData.fmt(src.sumMs / maxOf(src.nCalls, 1))} max ${TestData.fmt(src.maxMs)} ms over ${src.nCalls} calls")
        println("[C events] " + rec.events.filter { it.second in setOf("ALIGN", "MODE", "CORRIDOR", "DIRECTION", "MOTION_START", "ARMED", "REVEAL", "REAL_OUTAGE", "OUTAGE_END") }.joinToString(" | ") { "${it.second}@${TestData.fmt(it.first, 1)} ${it.third}" })
        return rec
    }

    private fun modelVsPred(ref: TestData.Ref, rec: TestData.Recorder, label: String) {
        val pred = TestData.predSource(ref); val mo = ModelOut(); var n = 0; var sum = 0.0; var mx = 0.0; var signed = 0.0; val ring = WindowRing()
        for (s in rec.ticks) { if (!s.modelValid || s.stop) continue; pred.speedAt(s.t, ring, mo); if (mo.still) continue; val d = s.vModel - mo.vRaw; n++; sum += abs(d); signed += d; if (abs(d) > mx) mx = abs(d) }
        println("[$label model vs deploy pred] n=$n mean |dv| ${TestData.fmt(sum / maxOf(n, 1))} signed mean ${TestData.fmt(signed / maxOf(n, 1))} max ${TestData.fmt(mx)} m/s")
    }

    @Test fun resamplerPassesExperiment() {
        for (ref in listOf(TestData.R2, TestData.R1)) for (passes in intArrayOf(1, 2)) {
            val rec = levelC(ref, forced = true, passes = passes)
            compare("X ${ref.corridorId} passes=$passes", rec, TestData.reference(ref), headingFrom = 40.0)
            modelVsPred(ref, rec, "X ${ref.corridorId} passes=$passes")
        }
    }

    @Test fun levelC_route2_phonePath_report() {
        val ref = TestData.R2; val rec = levelC(ref, forced = true)
        val r = compare("C ${ref.corridorId} raw+online-align+kotlin-cnn", rec, TestData.reference(ref), headingFrom = 40.0)
        // model speed vs the Python predictions on the same session (different resampler and grid offset: report only)
        val pred = TestData.predSource(ref); val mo = ModelOut(); var n = 0; var sum = 0.0; var mx = 0.0; val ring = WindowRing()
        for (s in rec.ticks) { if (!s.modelValid || s.stop) continue; pred.speedAt(s.t, ring, mo); val d = abs(s.vModel - mo.vRaw); n++; sum += d; if (d > mx) mx = d }
        println("[C model vs pred csv] n=$n mean |dv| ${TestData.fmt(sum / maxOf(n, 1))} max ${TestData.fmt(mx)} m/s (causal resampler vs zero-phase, grid offset)")
        assertTrue(r[4] > 1000)
    }

    @Test fun levelC_route1_phonePath_report() {
        val ref = TestData.R1; val rec = levelC(ref, forced = true)
        compare("C ${ref.corridorId} raw+online-align+kotlin-cnn", rec, TestData.reference(ref), headingFrom = 40.0)
        assertTrue(rec.ticks.size > 1000)
    }

    /** Acceptance 11.6: recognition within 10 s of motion start with the right direction; a session outside the library stays general. */
    @Test fun corridorRecognition() {
        val ref = TestData.R2; val rec = levelC(ref, forced = false)
        val reader = SessionReader(ref.rawDir); val tm0 = reader.motionStartT
        val cor = rec.events.firstOrNull { it.second == "CORRIDOR" }; val dir = rec.events.firstOrNull { it.second == "DIRECTION" }
        println("[recognition] motion start ${TestData.fmt(tm0, 1)} s; corridor event: $cor; direction event: $dir")
        assertTrue("no corridor recognised", cor != null && cor.third.contains("SNU_R2"))
        assertTrue("direction not AB within 10 s of motion start: $dir", dir != null && dir.third == "AB" && dir.first - tm0 <= 10.0)
        val r = compare("C recognised-vs-reference", rec, TestData.reference(ref), headingFrom = 40.0)
        assertTrue(r[4] > 1000)
        // outside the library: route-1 session with only the route-2 corridor available
        val lib = TestData.corridorLibrary().filter { it.id == "SNU_R2" }; val pack = TestData.modelPack()
        val cfg = EngineConfig(corridors = lib, corridorAuto = true, mapMatch = true, roadGraph = TestData.roadGraph(), originLatLon = TestData.anchor(TestData.R1), scenario = Scenario(Scenario.Kind.TIMER, 0.0, null, 30.0, 1e9))
        val rec1 = TestData.Recorder(); val e1 = Engine(cfg, CnnSpeedSource(pack, KotlinCnn(pack)), rec1)
        SessionReader(TestData.R1.rawDir).run(e1, 0.0)
        val modes = rec1.ticks.map { it.fusionMode }.toSet(); val matchedFrac = rec1.ticks.count { it.matched }.toDouble() / maxOf(rec1.ticks.size, 1)
        println("[outside library] fusion modes seen: $modes; corridor events: ${rec1.events.filter { it.second == "CORRIDOR" }}; map-matched ticks ${TestData.fmt(100 * matchedFrac, 1)} %")
        assertTrue("engine left general mode on a road outside the library", modes == setOf("general") || modes == setOf("none", "general"))
    }

    @Test fun writeEngineOutCsv() {
        // a sample engine_out.csv from the raw path for docs and for the device diff
        val ref = TestData.R2; val rec = levelC(ref, forced = true)
        val out = File(TestData.root, "docs/qa_app"); out.mkdirs()
        File(out, "jvm_${ref.session}_engine_out.csv").bufferedWriter().use { w -> w.write(EngineState.CSV_HEADER); w.newLine(); for (s in rec.ticks) { w.write(s.csvRow()); w.newLine() } }
        File(out, "jvm_${ref.session}_engine_events.csv").bufferedWriter().use { w -> w.write("t_s,type,text"); w.newLine(); for (e in rec.events) { w.write("${TestData.fmt(e.first)},${e.second},\"${e.third.replace('"', '\'')}\""); w.newLine() } }
        println("[csv] wrote ${out.absolutePath}")
    }
}

class BandScenarioTest {
    /** The exact device replay configuration: auto recognition, band 200 -> 780 m, route-2 run 4. */
    @org.junit.Test fun bandScenarioAutoRecognition() {
        val ref = TestData.R2; val lib = TestData.corridorLibrary(); val pack = TestData.modelPack()
        val cfg = EngineConfig(corridors = lib, corridorAuto = true, mapMatch = true, roadGraph = TestData.roadGraph(), originLatLon = TestData.anchor(ref),
            scenario = Scenario(Scenario.Kind.BAND, bandFromM = 200.0, bandToM = 780.0))
        val rec = TestData.Recorder(); val e = Engine(cfg, CnnSpeedSource(pack, KotlinCnn(pack)), rec)
        com.snu.idr.engine.replay.SessionReader(ref.rawDir).run(e, 0.0)
        println("[band] " + rec.events.filter { it.second in setOf("CORRIDOR", "DIRECTION", "BAND_ORIGIN", "BAND_ENTER", "BAND_EXIT", "MODE", "REVEAL", "SIM_ENTER") }.joinToString(" | ") { "${it.second}@${TestData.fmt(it.first, 1)} ${it.third}" })
        val inertial = rec.ticks.count { it.mode == Mode.INERTIAL }
        println("[band] inertial ticks $inertial, reveal figures: ${rec.ticks.mapNotNull { it.reveal }.map { "off ${TestData.fmt(it.endErrorM)} m after ${TestData.fmt(it.distanceM, 0)} m / ${TestData.fmt(it.durationS, 0)} s" }.distinct()}")
        org.junit.Assert.assertTrue(inertial > 100)
    }
}


class RealOutageTest {
    /** Acceptance 11.5: a real gap (fixes dropped 100-110 s, no scenario) fires the rule-1 detector, INERTIAL without the SIM flag,
     *  then RECOVERING for exactly 3 s with the x4 inflation, and the displayed trail is never rewritten (positions are only appended). */
    @org.junit.Test fun realGapFiresDetectorAndRecovers() {
        val ref = TestData.R2; val lib = TestData.corridorLibrary(); val pack = TestData.modelPack()
        val cfg = EngineConfig(corridors = lib, corridorAuto = true, mapMatch = false, originLatLon = TestData.anchor(ref), scenario = Scenario.NONE)
        val rec = TestData.Recorder(); val e = Engine(cfg, CnnSpeedSource(pack, KotlinCnn(pack)), rec)
        val r = com.snu.idr.engine.replay.SessionReader(ref.rawDir)
        // drive manually: drop every fix with 100 <= t < 110
        var ia = 0; var ig = 0; var ifx = 0; var ist = 0; var iev = 0
        while (true) {
            var tNext = Double.MAX_VALUE; var which = -1
            if (iev < r.events.size && r.events[iev].first < tNext) { tNext = r.events[iev].first; which = 0 }
            if (ifx < r.fixT.size && r.fixT[ifx] < tNext) { tNext = r.fixT[ifx]; which = 1 }
            if (ist < r.stT.size && r.stT[ist] < tNext) { tNext = r.stT[ist]; which = 2 }
            if (ig < r.gyrT.size && r.gyrT[ig] < tNext) { tNext = r.gyrT[ig]; which = 3 }
            if (ia < r.accT.size && r.accT[ia] < tNext) { tNext = r.accT[ia]; which = 4 }
            if (which < 0) break
            when (which) {
                0 -> { e.onEvent(tNext, r.events[iev].second); iev++ }
                1 -> { if (!(r.fixT[ifx] >= 100.0 && r.fixT[ifx] < 110.0)) e.onFix(r.fixT[ifx], r.fixLat[ifx], r.fixLon[ifx], r.fixAcc[ifx], r.fixV[ifx], r.fixBrg[ifx], r.fixSats[ifx]); ifx++ }
                2 -> { e.onGnssStatus(r.stT[ist], r.stUsed[ist], r.stCn0[ist]); ist++ }
                3 -> { e.onGyrNative(r.gyrT[ig], r.gyrX[ig], r.gyrY[ig], r.gyrZ[ig]); ig++ }
                4 -> { e.onAccNative(r.accT[ia], r.accX[ia], r.accY[ia], r.accZ[ia]); ia++ }
            }
        }
        val tr = rec.modeTransitions()
        println("[real gap] modes: " + tr.joinToString(" ") { "${it.second}@${TestData.fmt(it.first, 1)}" } + " | events: " + rec.events.filter { it.second in setOf("REAL_OUTAGE", "OUTAGE_ENTER", "REVEAL", "MODE") }.joinToString(" | ") { "${it.second}@${TestData.fmt(it.first, 1)} ${it.third}" })
        val inertial = tr.firstOrNull { it.second == "INERTIAL" }; val recov = tr.firstOrNull { it.second == "RECOVERING" }; val back = tr.lastOrNull { it.second == "GNSS_INS" }
        org.junit.Assert.assertTrue("no INERTIAL after the gap", inertial != null && inertial.first > 100.0 && inertial.first < 102.0)
        org.junit.Assert.assertTrue("no RECOVERING", recov != null && recov.first >= 110.0 && recov.first < 111.5)
        org.junit.Assert.assertTrue("RECOVERING window is not 3 s", back != null && kotlin.math.abs((back.first - recov!!.first) - 3.0) < 0.15)
        org.junit.Assert.assertTrue("sim flag set on a real outage", rec.ticks.none { it.mode == Mode.INERTIAL && it.sim })
        // the trail is never rewritten: every tick keeps its own position; the reveal carries the withheld truth separately
        org.junit.Assert.assertTrue(rec.ticks.count { it.hasPosition } > 2900)
        val rv = rec.events.firstOrNull { it.second == "REVEAL" }; org.junit.Assert.assertTrue("no reveal after a real gap", rv != null && rv.third.contains("sim=false"))
    }
}
