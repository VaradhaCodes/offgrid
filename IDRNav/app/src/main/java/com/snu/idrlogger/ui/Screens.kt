package com.snu.idrlogger.ui

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.snu.idrlogger.BuildConfig
import com.snu.idrlogger.InventoryActivity
import com.snu.idrlogger.LogService
import com.snu.idrlogger.service.EngineAssets
import com.snu.idrlogger.service.NavLive
import kotlinx.coroutines.delay
import java.io.File
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

private fun f(v: Double, d: Int = 1): String = if (v.isNaN()) "–" else String.format(Locale.US, "%.${d}f", v)

@Composable
private fun Screen(title: String, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().background(Tok.Ground).windowInsetsPadding(WindowInsets.safeDrawing).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 12.dp)) {
        Text(title, style = MaterialTheme.typography.headlineMedium, color = Tok.Text)
        Spacer(Modifier.height(12.dp))
        content()
        Spacer(Modifier.height(96.dp))
    }
}

@Composable
private fun Section(title: String) { Spacer(Modifier.height(14.dp)); Text(title, style = MaterialTheme.typography.titleSmall, color = Tok.Locked); HorizontalDivider(Modifier.padding(vertical = 6.dp), color = Tok.Outline) }

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit, sub: String? = null) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
        Column(Modifier.weight(1f)) { Text(label, style = MaterialTheme.typography.bodyLarge, color = Tok.Text); if (sub != null) Text(sub, style = MaterialTheme.typography.bodySmall, color = Tok.TextDim) }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun Choice(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        options.forEachIndexed { i, (key, label) ->
            SegmentedButton(selected = selected == key, onClick = { onSelect(key) }, shape = SegmentedButtonDefaults.itemShape(i, options.size), colors = SegmentedButtonDefaults.colors(activeContainerColor = Tok.Raised, activeContentColor = Tok.Locked, inactiveContainerColor = Tok.Card, inactiveContentColor = Tok.TextDim)) { Text(label, style = MaterialTheme.typography.labelLarge) }
        }
    }
}

@Composable
private fun NumField(label: String, value: Double, onChange: (Double) -> Unit, modifier: Modifier = Modifier) {
    var text by remember(value) { mutableStateOf(if (value == Math.floor(value)) value.toInt().toString() else value.toString()) }
    OutlinedTextField(value = text, onValueChange = { text = it; it.toDoubleOrNull()?.let(onChange) }, label = { Text(label) }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = modifier)
}

// ------------------------------------------------------------------ Settings
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun SettingsScreen(prefs: AppPrefs, onFieldTest: () -> Unit) {
    val ctx = LocalContext.current
    Screen("Settings") {
        Section("Units")
        Choice(listOf("kmh" to "km/h", "ms" to "m/s"), prefs.units) { prefs.units = it; prefs.save() }
        Section("Map")
        Choice(listOf("night" to "Night", "sat" to "Satellite (online)"), if (prefs.satellite) "sat" else "night") { prefs.satellite = it == "sat"; prefs.save() }
        Text(if (prefs.satellite) "Imagery: Esri, Maxar, Earthstar Geographics · loaded live, never stored" else "Map data © OpenStreetMap contributors (ODbL) · Building footprints © Microsoft (CDLA-Permissive-2.0) · works offline", style = MaterialTheme.typography.bodySmall, color = Tok.TextDim, modifier = Modifier.padding(top = 6.dp))
        Section("Rider")
        OutlinedTextField(value = prefs.rider, onValueChange = { prefs.rider = it; prefs.save() }, label = { Text("Rider name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Section("Video")
        SwitchRow("Sync flash", prefs.syncFlash, { prefs.syncFlash = it; prefs.save() }, "Three white frames and three tones at START, band entry and band exit")
        Section("Screen")
        Text("Bottom inset · ${prefs.insetBottomDp} dp", style = MaterialTheme.typography.bodyLarge, color = Tok.Text)
        Slider(value = prefs.insetBottomDp.toFloat(), onValueChange = { prefs.insetBottomDp = it.toInt() }, onValueChangeFinished = { prefs.save() }, valueRange = 0f..120f, steps = 11)
        SwitchRow("Reduce motion", prefs.reduceMotion, { prefs.reduceMotion = it; prefs.save() }, "Camera and puck snap instead of easing")
        Section("Data sources")
        Text("Map data © OpenStreetMap contributors, ODbL (openstreetmap.org/copyright)\nBuilding footprints © Microsoft, CDLA-Permissive-2.0\nBasemap tiles: Protomaps build 2026-09-05\nSatellite (when on): Esri, Maxar, Earthstar Geographics", style = MaterialTheme.typography.bodySmall, color = Tok.TextDim)
        Spacer(Modifier.height(24.dp))
        Text("IDR Nav ${BuildConfig.VERSION_NAME} · engine spec v2 · cnn_r100_w256_joint_deploy · MapLibre 13.6.0 · LiteRT 2.2.0",
            style = MaterialTheme.typography.bodySmall, color = Tok.TextFaint,
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).combinedClickable(onClick = { }, onLongClick = { onFieldTest() }))
    }
}

// ------------------------------------------------------------------ Field test (hidden)
@Composable
fun FieldTestScreen(prefs: AppPrefs, controller: RideController, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val replay by NavLive.replay.collectAsStateWithLifecycle()
    val info by NavLive.engineInfo.collectAsStateWithLifecycle()
    var folders by remember { mutableStateOf(listOf<File>()) }
    var selected by remember { mutableStateOf<File?>(null) }
    var bench by remember { mutableStateOf("") }
    var conformance by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        while (true) {
            val a = (controller.replayRoot().listFiles() ?: emptyArray()).filter { File(it, "acc.csv").exists() }
            val b = (controller.sessionsRoot().listFiles() ?: emptyArray()).filter { File(it, "acc.csv").exists() }
            folders = (a + b).sortedByDescending { it.name }
            delay(3000)
        }
    }
    Screen("Field test") {
        TextButton(onClick = onBack) { Text("← Back") }
        Section("Scenario (hidden from the ride screen; a SIM tag shows when armed)")
        Choice(listOf("none" to "None", "band" to "Band", "timer" to "Timer", "manual" to "Manual"), prefs.scenarioKind) { prefs.scenarioKind = it; prefs.save() }
        if (prefs.scenarioKind == "band") {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                NumField("Band from (m from start)", prefs.bandFrom, { prefs.bandFrom = it; prefs.save() }, Modifier.weight(1f))
                NumField("Band to (m, 0 = stop)", prefs.bandTo, { prefs.bandTo = it; prefs.save() }, Modifier.weight(1f))
            }
            Text("Route 2 A→B demo take: 200 → stop. Route 1: 110 → stop. Direction is detected from the first fixes; the band is drawn once known.", style = MaterialTheme.typography.bodySmall, color = Tok.TextDim, modifier = Modifier.padding(top = 4.dp))
        }
        if (prefs.scenarioKind == "timer") {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                NumField("Start (s after motion)", prefs.timerStart, { prefs.timerStart = it; prefs.save() }, Modifier.weight(1f))
                NumField("Hold (s)", prefs.timerHold, { prefs.timerHold = it; prefs.save() }, Modifier.weight(1f))
            }
        }
        if (prefs.scenarioKind == "manual") {
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { controller.manualDenial(true) }, colors = ButtonDefaults.buttonColors(containerColor = Tok.Band)) { Text("Deny GNSS now") }
                OutlinedButton(onClick = { controller.manualDenial(false) }) { Text("Restore") }
            }
        }
        Spacer(Modifier.height(8.dp))
        Text("Corridor", style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim)
        Choice(listOf("" to "Auto (library)", "SNU_R1" to "Force R1", "SNU_R2" to "Force R2"), prefs.forcedCorridor) { prefs.forcedCorridor = it; prefs.save() }

        Section("Engine")
        Text("Speed model", style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim)
        Choice(listOf("litert" to "LiteRT (XNNPACK, 1 thread)", "kotlin" to "Kotlin CNN"), prefs.model) { prefs.model = it; prefs.save() }
        SwitchRow("Re-lock reveal", prefs.revealOn, { prefs.revealOn = it; prefs.save() })
        SwitchRow("Engine sheet", prefs.engineSheetOn, { prefs.engineSheetOn = it; prefs.save() })
        SwitchRow("Log the 22 sensor streams", prefs.loggingOn, { prefs.loggingOn = it; prefs.save() }, "engine_out.csv and engine_events.csv are always written")
        Text("Puck", style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim)
        Choice(PuckVariant.values().map { it.name to it.label }, prefs.puckVariant) { prefs.puckVariant = it; prefs.save() }
        SwitchRow("Puck gallery over the map", prefs.puckGallery, { prefs.puckGallery = it }, "All four variants side by side for the screenshot")
        Row(Modifier.padding(top = 4.dp)) { OutlinedButton(onClick = { ctx.startActivity(Intent(ctx, InventoryActivity::class.java)) }) { Text("Sensor inventory") } }

        Section("Replay a recorded session")
        Text("Folders under Android/data/com.snu.idrlogger/files/replay and …/sessions (${folders.size})", style = MaterialTheme.typography.bodySmall, color = Tok.TextDim)
        for (fdir in folders.take(12)) {
            Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).combinedClickable(onClick = { selected = fdir }), verticalAlignment = Alignment.CenterVertically) {
                Text(if (selected == fdir) "● " else "○ ", color = Tok.Locked); Text(fdir.name, style = MaterialTheme.typography.bodyMedium, color = Tok.Text)
            }
        }
        Text("Speed", style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim)
        Choice(listOf("1" to "1×", "4" to "4×", "0" to "max"), if (prefs.replaySpeed <= 0) "0" else prefs.replaySpeed.toInt().toString()) { prefs.replaySpeed = it.toDouble(); prefs.save() }
        Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { selected?.let { controller.startReplay(it, prefs.replaySpeed) } }, enabled = selected != null && replay?.running != true) { Text("Start replay") }
            OutlinedButton(onClick = { controller.stopReplay() }, enabled = replay?.running == true) { Text("Stop") }
        }
        replay?.let { r -> Text("${r.session} · ${fmtClock(r.tNow)} / ${fmtClock(r.tEnd)} · ${if (r.speed <= 0) "max" else "${r.speed.toInt()}×"} · ${if (r.running) "running" else "done"}" + (r.outDir?.let { "\nout: $it" } ?: ""), style = MaterialTheme.typography.bodySmall, color = Tok.TextDim, modifier = Modifier.padding(top = 6.dp)) }
        if (info.isNotEmpty()) Text(info, style = MaterialTheme.typography.bodySmall, color = Tok.Text, modifier = Modifier.padding(top = 4.dp))

        Section("Conformance self-test")
        Text("Needs a folder with conformance.json + reference.csv beside the session files (pushed from the Mac). Runs it at max speed with the reference scenario and prints max |Δpos| against the reference CSV.", style = MaterialTheme.typography.bodySmall, color = Tok.TextDim)
        Button(onClick = {
            val dir = selected ?: return@Button
            val cj = File(dir, "conformance.json")
            if (!cj.exists()) { conformance = "no conformance.json in ${dir.name}"; return@Button }
            val c = org.json.JSONObject(cj.readText())
            prefs.scenarioKind = "timer"; prefs.timerStart = c.optDouble("outage_start_s", 30.0); prefs.timerHold = 1e9; prefs.forcedCorridor = c.optString("corridor", ""); prefs.save()
            conformance = "running ${dir.name}…"
            controller.startReplay(dir, 0.0)
        }, enabled = selected != null && replay?.running != true, modifier = Modifier.padding(top = 8.dp)) { Text("Run conformance on the selected folder") }
        LaunchedEffect(replay?.running, replay?.outDir) {
            val r = replay ?: return@LaunchedEffect
            if (!r.running && conformance.startsWith("running") && r.outDir != null) {
                val sel = folders.firstOrNull { it.name == r.session }
                val ref = sel?.let { File(it, "reference.csv") }
                conformance = if (ref != null && ref.exists()) ConformanceCheck.compare(File(r.outDir, "engine_out.csv"), ref) else "done (no reference.csv to compare)"
            }
        }
        if (conformance.isNotEmpty()) Text(conformance, style = MaterialTheme.typography.bodySmall, color = Tok.Text, modifier = Modifier.padding(top = 6.dp))

        Section("Model check: LiteRT vs Kotlin CNN on 500 real windows")
        Button(onClick = { bench = "running…"; Thread { bench = ModelBench.run(ctx) }.start() }, modifier = Modifier.padding(top = 4.dp)) { Text("Run model check") }
        if (bench.isNotEmpty()) Text(bench, style = MaterialTheme.typography.bodySmall, color = Tok.Text, modifier = Modifier.padding(top = 6.dp))
    }
}

// ------------------------------------------------------------------ Summary
@Composable
fun SummaryScreen(prefs: AppPrefs, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val s by NavLive.state.collectAsStateWithLifecycle()
    val replay by NavLive.replay.collectAsStateWithLifecycle()
    val live = LogService.Live
    val isReplay = live.sessionDir.isEmpty() && replay != null
    val name = if (isReplay) "Replay · ${replay?.session}" else live.sessionName
    val dir = File(if (isReplay) (replay?.outDir ?: "") else live.sessionDir)
    val rideS = s?.let { st -> if (!st.tMotionStart.isNaN()) (st.t - st.tMotionStart).coerceAtLeast(0.0) else st.t } ?: live.elapsedSec.toDouble()
    Screen("Ride summary") {
        Text(name, style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim)
        Section("Ride")
        Text("${f(DistanceTracker.km, 2)} km · ${fmtClock(rideS)} since motion start · ${s?.corridorName ?: "free ride"}" + (s?.let { st -> if (st.dir != 0) " · " + (if (st.dir > 0) "A→B" else "B→A") else "" } ?: ""), style = MaterialTheme.typography.bodyLarge, color = Tok.Text)
        Text((if (isReplay) "replayed file · " else "acc ${f(live.accHz, 0)} Hz · gyr ${f(live.gyrHz, 0)} Hz · gaps ${live.gaps} · dropped ${live.dropped} · ") + "${NavLive.speedModelName} · tick ${f(NavLive.tickMsMean, 2)} ms mean", style = MaterialTheme.typography.bodySmall, color = Tok.TextDim)
        Section("Outages")
        val outs = s?.outages ?: emptyList()
        if (outs.isEmpty()) Text("No outage in this ride.", color = Tok.TextDim)
        for ((i, o) in outs.withIndex()) {
            Text("#${i + 1} · ${if (o.sim) "simulated" else "real"}${if (!o.armedAtEntry) " · entered before alignment" else ""}", style = MaterialTheme.typography.titleSmall, color = if (o.sim) Tok.Band else Tok.DeadReckoning)
            Text(if (o.endErrorM.isNaN()) "${o.distanceM.toInt()} m without GNSS (${fmtClock(o.durationS)}) · GNSS did not return before the end · max error while withheld ${f(o.maxErrorM)} m"
                 else "Off by ${f(o.endErrorM)} m after ${o.distanceM.toInt()} m without GNSS (${fmtClock(o.durationS)}) · max ${f(o.maxErrorM)} m · recovery step ${f(o.recoveryStepM)} m", style = MaterialTheme.typography.bodyMedium, color = Tok.Text)
            Spacer(Modifier.height(6.dp))
        }
        Section("Files")
        Text(if (dir.path.isEmpty()) "no files (nothing was recorded)" else dir.absolutePath, style = MaterialTheme.typography.bodySmall, color = Tok.TextDim)
        val files = if (dir.path.isEmpty()) emptyList() else (dir.listFiles() ?: emptyArray()).sortedBy { it.name }
        Text(files.joinToString("  ") { "${it.name} (${it.length() / 1024} kB)" }, style = MaterialTheme.typography.bodySmall, color = Tok.TextDim)
        live.summary?.let { Section("Logger summary"); Text(it, style = MaterialTheme.typography.bodySmall.copy(fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace), color = Tok.Text) }
        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { Thread { try { val z = zipDir(dir); (ctx as? android.app.Activity)?.runOnUiThread { shareFile(ctx, z) } } catch (t: Throwable) { (ctx as? android.app.Activity)?.runOnUiThread { Toast.makeText(ctx, "zip failed: ${t.message}", Toast.LENGTH_LONG).show() } } }.start() }, enabled = dir.path.isNotEmpty() && dir.exists()) { Text("Zip + share") }
            OutlinedButton(onClick = { prefs.runNo += 1; prefs.save(); LogService.Live.summary = null; onDone() }) { Text("Done") }
        }
    }
}

fun zipDir(d: File): File {
    val out = File(d.parentFile, "${d.name}.zip")
    ZipOutputStream(out.outputStream().buffered(1 shl 16)).use { zos ->
        for (f in d.listFiles() ?: emptyArray()) { if (!f.isFile) continue; zos.putNextEntry(ZipEntry("${d.name}/${f.name}")); f.inputStream().buffered(1 shl 16).use { it.copyTo(zos) }; zos.closeEntry() }
    }
    return out
}

fun shareFile(ctx: android.content.Context, f: File) {
    try {
        val uri: Uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", f)
        ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type = "application/zip"; putExtra(Intent.EXTRA_STREAM, uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION) }, "Share ${f.name}"))
    } catch (t: Throwable) { Toast.makeText(ctx, "share failed: ${t.message}", Toast.LENGTH_LONG).show() }
}

/** Compares an on-device engine_out.csv with a reference CSV (t_s, x_m, y_m, heading_deg, mode) joined on t_s at 0.1 s. */
object ConformanceCheck {
    private fun read(f: File): Map<Long, DoubleArray> {   // t -> [x, y, heading, modeIdx]
        val out = HashMap<Long, DoubleArray>()
        f.bufferedReader().useLines { lines ->
            val it = lines.iterator(); if (!it.hasNext()) return out
            val h = it.next().split(',').mapIndexed { i, s -> s.trim() to i }.toMap()
            val ix = h["x_m"] ?: return out; val iy = h["y_m"] ?: return out; val ih = h["heading_deg"] ?: -1; val im = h["mode"] ?: -1; val itt = h["t_s"] ?: return out
            while (it.hasNext()) {
                val c = it.next().split(','); if (c.size <= maxOf(ix, iy)) continue
                val x = c[ix].toDoubleOrNull() ?: continue; val y = c[iy].toDoubleOrNull() ?: continue
                val hd = if (ih >= 0) c[ih].toDoubleOrNull() ?: Double.NaN else Double.NaN
                val m = if (im >= 0) when (c[im]) { "GNSS_INS" -> 0.0; "INERTIAL" -> 1.0; "RECOVERING" -> 2.0; else -> -1.0 } else -1.0
                out[Math.round((c[itt].toDoubleOrNull() ?: continue) * 10)] = doubleArrayOf(x, y, hd, m)
            }
        }
        return out
    }

    fun compare(engineOut: File, reference: File): String {
        if (!engineOut.exists()) return "engine_out.csv missing"
        val a = read(engineOut); val b = read(reference)
        var n = 0; var maxP = 0.0; var tMax = 0.0; var maxH = 0.0; var sum = 0.0; var modeMismatch = 0
        for ((t, ea) in a) { val eb = b[t] ?: continue; val d = Math.hypot(ea[0] - eb[0], ea[1] - eb[1]); n++; sum += d; if (d > maxP) { maxP = d; tMax = t / 10.0 }
            if (!ea[2].isNaN() && !eb[2].isNaN()) { var dh = Math.abs(ea[2] - eb[2]) % 360.0; if (dh > 180) dh = 360 - dh; if (dh > maxH) maxH = dh }
            if (ea[3] >= 0 && eb[3] >= 0 && ea[3] != eb[3]) modeMismatch++ }
        return "compared $n ticks: max |Δpos| ${f(maxP, 3)} m at t=${f(tMax)} s · mean ${f(sum / maxOf(n, 1), 3)} m · max |Δheading| ${f(maxH, 2)}° · mode mismatches $modeMismatch ticks (${f(modeMismatch / 10.0)} s)"
    }
}

/** Acceptance 11.2 on the device: LiteRT vs the Kotlin CNN on the bundled 500 windows, plus per-window latency of both. */
object ModelBench {
    fun run(ctx: android.content.Context): String = try {
        val pack = EngineAssets.modelPack(ctx)
        val n = pack.json.getJSONObject("fixtures").getInt("n")
        val bytes = ctx.assets.open("model/windows_$n.bin").readBytes(); val exp = ctx.assets.open("model/expected_$n.bin").readBytes()
        val X = FloatArray(bytes.size / 4); java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN).asFloatBuffer().get(X)
        val Y = FloatArray(exp.size / 4); java.nio.ByteBuffer.wrap(exp).order(java.nio.ByteOrder.LITTLE_ENDIAN).asFloatBuffer().get(Y)
        val kot = com.snu.idr.engine.KotlinCnn(pack); val lite = com.snu.idrlogger.model.LiteRtSpeedModel(ctx)
        val raw = FloatArray(256 * 6); val xn = FloatArray(256 * 6); val ok = FloatArray(2); val ol = FloatArray(2)
        var maxKL = 0.0; var maxKP = 0.0; var maxLP = 0.0
        val tk = DoubleArray(n); val tl = DoubleArray(n)
        for (i in 0 until n) {
            System.arraycopy(X, i * 256 * 6, raw, 0, 256 * 6); pack.normalise(raw, xn)
            val a = System.nanoTime(); kot.infer(xn, ok); val b = System.nanoTime(); lite.infer(xn, ol); val c = System.nanoTime()
            tk[i] = (b - a) / 1e6; tl[i] = (c - b) / 1e6
            maxKL = maxOf(maxKL, Math.abs(ok[0] - ol[0]).toDouble(), Math.abs(ok[1] - ol[1]).toDouble())
            maxKP = maxOf(maxKP, Math.abs(ok[0] - Y[2 * i]).toDouble(), Math.abs(ok[1] - Y[2 * i + 1]).toDouble())
            maxLP = maxOf(maxLP, Math.abs(ol[0] - Y[2 * i]).toDouble(), Math.abs(ol[1] - Y[2 * i + 1]).toDouble())
        }
        fun stats(t: DoubleArray): String { val s = t.copyOfRange(20, t.size).sorted(); return "median ${f(s[s.size / 2], 3)} · p95 ${f(s[(s.size * 0.95).toInt()], 3)} · max ${f(s.last(), 3)} ms" }
        lite.close()
        "n=$n · max |LiteRT − Kotlin| ${String.format(Locale.US, "%.2e", maxKL)} · Kotlin vs PyTorch ${String.format(Locale.US, "%.2e", maxKP)} · LiteRT vs PyTorch ${String.format(Locale.US, "%.2e", maxLP)}\nKotlin CNN: ${stats(tk)}\nLiteRT (CPU/XNNPACK, 1 thread): ${stats(tl)}\n(${android.os.Build.MODEL}, single thread, 20 warm-up windows excluded)"
    } catch (t: Throwable) { "model check failed: $t" }
}
