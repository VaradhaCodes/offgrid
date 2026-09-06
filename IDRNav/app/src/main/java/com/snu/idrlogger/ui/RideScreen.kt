package com.snu.idrlogger.ui

import android.view.MotionEvent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInteropFilter
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.snu.idr.engine.EngineState
import com.snu.idr.engine.Mode
import com.snu.idr.engine.Phase
import com.snu.idrlogger.LogService
import com.snu.idrlogger.map.MapAssets
import com.snu.idrlogger.map.MapController
import com.snu.idrlogger.service.EngineAssets
import com.snu.idrlogger.service.NavLive
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.maplibre.android.MapLibre
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import java.util.Locale
import kotlin.math.cos

/** Everything the ride screen needs from the activity. */
class RideDeps(val prefs: AppPrefs, val controller: RideController, val sync: SyncSignal, val onOpenSummary: () -> Unit)

/** Snapshot of the service's polled state for Compose. */
class LoggerSnap(val running: Boolean, val state: LogService.State, val countdown: Int, val elapsedSec: Long, val sessionName: String, val summary: String?, val lastError: String?, val accHz: Double, val gyrHz: Double, val sats: Int)

fun snapLogger(): LoggerSnap { val L = LogService.Live; return LoggerSnap(L.running, L.state, L.countdown, L.elapsedSec, L.sessionName, L.summary, L.lastError, L.accHz, L.gyrHz, L.satsUsed) }

fun stateColor(m: Mode?): Color = when (m) { Mode.INERTIAL -> Tok.DeadReckoning; Mode.RECOVERING -> Tok.Relocking; else -> Tok.Locked }

fun fmtClock(sec: Double): String { val s = sec.toInt().coerceAtLeast(0); return String.format(Locale.US, "%d:%02d", s / 60, s % 60) }

@Composable
fun RideScreen(deps: RideDeps, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val prefs = deps.prefs
    val engineState by NavLive.state.collectAsStateWithLifecycle()
    var logger by remember { mutableStateOf(snapLogger()) }
    LaunchedEffect(Unit) { while (true) { logger = snapLogger(); delay(250) } }
    var sheetOpen by remember { mutableStateOf(false) }
    var flash by remember { mutableIntStateOf(0) }   // > 0 while the white frame is up
    val scope = rememberCoroutineScope()
    var controllerRef by remember { mutableStateOf<MapController?>(null) }
    var puckPos by remember { mutableStateOf(Offset(0f, 0f)) }
    var puckRot by remember { mutableFloatStateOf(0f) }
    var puckOnScreen by remember { mutableStateOf(true) }
    var camTilt by remember { mutableFloatStateOf(50f) }
    var following by remember { mutableStateOf(true) }
    var mpp by remember { mutableStateOf(0.2) }
    var revealAlpha by remember { mutableFloatStateOf(0f) }
    var revealText by remember { mutableStateOf<String?>(null) }
    var stoppedSince by remember { mutableStateOf(-1L) }
    var summaryShown by remember { mutableStateOf(false) }

    // ---- flash + tones on START, band entry, band exit
    fun sync() {
        deps.sync.beeps()
        if (prefs.syncFlash) scope.launch { for (i in 0 until 3) { flash = 1; delay(120); flash = 0; delay(120) } }
    }
    LaunchedEffect(Unit) {
        NavLive.events.collect { e -> when (e.type) { "BAND_ENTER", "BAND_EXIT" -> sync() } }
    }
    // the re-lock reveal is driven by the state (the REVEAL event precedes the tick that carries the figures)
    val revealKey = engineState?.reveal?.tReturn
    LaunchedEffect(revealKey) {
        val r = engineState?.reveal ?: return@LaunchedEffect
        if (!prefs.revealOn) return@LaunchedEffect
        revealText = if (r.endErrorM.isNaN()) null else "Off by ${String.format(Locale.US, "%.1f", r.endErrorM)} m after ${r.distanceM.toInt()} m without GNSS" + (if (!r.armedAtEntry) " · estimating, not yet aligned" else "")
        val t0 = System.nanoTime()
        while (true) {
            val dt = (System.nanoTime() - t0) / 1e9
            val a = when { dt < 0.6 -> (dt / 0.6).toFloat(); dt < 4.5 -> 1f; dt < 6.0 -> (1 - (dt - 4.5) / 1.5).toFloat(); else -> 0f } * 0.72f
            revealAlpha = a; controllerRef?.setRevealOpacity(a)
            if (dt >= 6.0) break
            delay(40)
        }
        revealText = null
    }
    // a new session (live or replay) restarts the engine clock: reset the trail
    var lastT by remember { mutableStateOf(-1.0) }
    // START flash: when the service enters CALIB
    var lastLoggerState by remember { mutableStateOf(LogService.State.IDLE) }
    LaunchedEffect(logger.state) {
        if (logger.state == LogService.State.CALIB && lastLoggerState != LogService.State.CALIB && logger.running) { sync(); controllerRef?.resetTrail(); summaryShown = false }
        if (logger.state == LogService.State.DONE && lastLoggerState != LogService.State.DONE && !summaryShown) { summaryShown = true; deps.onOpenSummary() }
        lastLoggerState = logger.state
    }
    // the puck rides the camera, not the engine tick: every gesture, fling and ease frame moves it with the map
    DisposableEffect(controllerRef) {
        val c = controllerRef
        c?.onCamera = {
            puckPos = Offset(c.puckScreen.x, c.puckScreen.y)
            puckRot = c.puckRotationDeg.toFloat()
            puckOnScreen = c.puckOnScreen
            camTilt = c.cameraTilt.toFloat()
            following = c.tracking
        }
        c?.syncPuck()
        onDispose { c?.release() }
    }
    // feed the map at 10 Hz (never through AndroidView.update)
    LaunchedEffect(controllerRef) {
        val c = controllerRef ?: return@LaunchedEffect
        NavLive.state.collect { s ->
            if (s != null) {
                if (s.t < lastT - 5.0 || s.k < 12L && lastT > 10.0) { c.resetTrail(); stoppedSince = -1L }
                lastT = s.t
                c.update(s, System.nanoTime())
                if (s.hasPosition) mpp = c.map.projection.getMetersPerPixelAtLatitude(s.lat)
                DistanceTracker.km = c.trailMeters / 1000.0
                if (s.v < 0.05 && s.stop) { if (stoppedSince < 0) stoppedSince = System.nanoTime() } else stoppedSince = -1L
            }
        }
    }
    LaunchedEffect(prefs.satellite, controllerRef) { controllerRef?.setSatellite(prefs.satellite) }
    LaunchedEffect(prefs.reduceMotion, controllerRef) { controllerRef?.reduceMotion = prefs.reduceMotion }

    BoxWithConstraints(modifier.fillMaxSize().background(Tok.Ground)) {
        val density = LocalDensity.current
        val hPx = with(density) { maxHeight.toPx() }; val wPx = with(density) { maxWidth.toPx() }
        MapHost(onReady = { c -> c.viewW = wPx.toInt(); c.viewH = hPx.toInt(); controllerRef = c }, controller = { controllerRef }, modifier = Modifier.fillMaxSize())
        LaunchedEffect(controllerRef, wPx, hPx) { controllerRef?.let { it.viewW = wPx.toInt(); it.viewH = hPx.toInt(); it.syncPuck() } }
        val s = engineState
        val stopped = stoppedSince > 0 && System.nanoTime() - stoppedSince > 2_000_000_000L
        if (s != null && s.hasPosition && puckOnScreen) {
            if (prefs.puckGallery) PuckGallery(puckPos, camTilt, stateColor(s.mode), prefs.reduceMotion)
            else PuckOverlay(puckPos.x, puckPos.y, puckRot, camTilt, stateColor(s.mode), stopped, s.sigmaPos, mpp, PuckVariant.valueOf(prefs.puckVariant), prefs.reduceMotion, Modifier.fillMaxSize())
        }
        // ---- top-left chip + SIM tag
        Row(Modifier.align(Alignment.TopStart).windowInsetsPadding(WindowInsets.safeDrawing).padding(start = 12.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            StateChip(s, logger)
            if (s?.scenarioArmed == true) { Spacer(Modifier.width(8.dp)); SimTag() }
        }
        // ---- top-right compass / follow
        CompassButton(Modifier.align(Alignment.TopEnd).windowInsetsPadding(WindowInsets.safeDrawing).padding(end = 12.dp, top = 8.dp), controllerRef, following)
        // ---- reveal figure
        AnimatedVisibility(visible = revealText != null, modifier = Modifier.align(Alignment.Center).padding(top = 120.dp), enter = fadeIn(tween(400)) + slideInVertically { it / 4 }, exit = fadeOut(tween(600))) {
            Surface(color = Tok.Card.copy(alpha = 0.92f), shape = RoundedCornerShape(12.dp), tonalElevation = 2.dp) {
                Text(revealText ?: "", Modifier.padding(horizontal = 16.dp, vertical = 10.dp), style = MaterialTheme.typography.titleMedium, color = Tok.Text)
            }
        }
        // ---- bottom card
        BottomCard(s, logger, prefs, deps, Modifier.align(Alignment.BottomCenter).heightIn(max = maxHeight * 0.28f), onOpenSheet = { if (prefs.engineSheetOn) sheetOpen = true })
        // ---- sync flash
        if (flash > 0) Box(Modifier.fillMaxSize().background(Color.White))
    }
    if (sheetOpen) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        val replay by NavLive.replay.collectAsStateWithLifecycle()
        ModalBottomSheet(onDismissRequest = { sheetOpen = false }, sheetState = sheetState, containerColor = Tok.Card) {
            EngineSheetContent(engineState, NavLive.speedModelName, replay?.let { "${it.session} · ${fmtClock(it.tNow)} / ${fmtClock(it.tEnd)} · ${if (it.speed <= 0) "max" else "${it.speed}×"}" + (if (!it.running) " · done" else "") })
        }
    }
}

@Composable
private fun MapHost(onReady: (MapController) -> Unit, controller: () -> MapController?, modifier: Modifier) {
    val ctx = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val mapView = remember {
        MapLibre.getInstance(ctx)
        MapView(ctx).apply { onCreate(null) }
    }
    DisposableEffect(lifecycleOwner) {
        val obs = LifecycleEventObserver { _, e ->
            when (e) {
                Lifecycle.Event.ON_START -> mapView.onStart(); Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause(); Lifecycle.Event.ON_STOP -> mapView.onStop(); else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs); mapView.onDestroy() }
    }
    AndroidView(factory = {
        // map render rate for the bench: MapLibre frames per second, logged every 5 s
        var frames = 0; var t0 = System.nanoTime()
        mapView.addOnDidFinishRenderingFrameListener { _, _, _ ->
            controller()?.syncPuck()   // belt and braces: no rendered frame leaves the puck behind
            frames++
            val dt = (System.nanoTime() - t0) / 1e9
            if (dt >= 5.0) { android.util.Log.i("IDR", String.format(java.util.Locale.US, "map fps %.1f over %.1f s", frames / dt, dt)); frames = 0; t0 = System.nanoTime() }
        }
        mapView.getMapAsync { map: MapLibreMap ->
            val meta = MapAssets.styleMeta(ctx)
            val json = MapAssets.buildStyle(ctx, meta)
            map.setStyle(Style.Builder().fromJson(json)) { style ->
                val c = MapController(ctx, map, style, meta, EngineAssets.corridors(ctx))
                c.jumpTo(28.5244, 77.5738, 16.0)
                onReady(c)
            }
        }
        mapView
    }, modifier = modifier, update = { })
}

@Composable
private fun StateChip(s: EngineState?, logger: LoggerSnap) {
    val (color, text) = chipText(s, logger)
    Surface(color = Tok.Card.copy(alpha = 0.92f), shape = RoundedCornerShape(20.dp), tonalElevation = 2.dp, modifier = Modifier.heightIn(min = 40.dp)) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(8.dp))
            Text(text, style = MaterialTheme.typography.labelLarge, color = Tok.Text)
        }
    }
}

fun chipText(s: EngineState?, logger: LoggerSnap): Pair<Color, String> {
    val stand = logger.running && (logger.state == LogService.State.CALIB || logger.state == LogService.State.STOP_CALIB)
    if (stand) return Tok.Locked to "Hold still, brakes on · ${logger.countdown} s"
    if (s == null || !s.hasPosition) return Tok.TextDim to (if (logger.running) "Waiting for GNSS" else "Ready")
    return when (s.mode) {
        Mode.GNSS_INS -> Tok.Locked to "GNSS locked · ${s.sats} satellites"
        Mode.INERTIAL -> Tok.DeadReckoning to "Dead reckoning · ${s.drMeters.toInt()} m · ${fmtClock(s.drSeconds)}"
        Mode.RECOVERING -> Tok.Relocking to "Re-locking · ${s.sats} satellites"
    }
}

@Composable
private fun SimTag() {
    Surface(color = Tok.Card.copy(alpha = 0.92f), shape = RoundedCornerShape(6.dp), modifier = Modifier.border(1.dp, Tok.Band.copy(alpha = 0.7f), RoundedCornerShape(6.dp))) {
        Text("SIM", Modifier.padding(horizontal = 6.dp, vertical = 3.dp), style = MaterialTheme.typography.labelSmall, color = Tok.Band)
    }
}

@Composable
private fun CompassButton(modifier: Modifier, c: MapController?, following: Boolean) {
    var northUp by remember { mutableStateOf(false) }
    val rot = c?.cameraBearing ?: 0.0
    val ring = if (following) Tok.TextFaint else Tok.Locked
    Surface(color = Tok.Card.copy(alpha = 0.92f), shape = CircleShape, tonalElevation = 2.dp, modifier = modifier.size(48.dp).clickable { c?.let { if (!it.tracking) it.recentre() else { it.toggleNorthUp(); northUp = it.northUp } } }.semantics { contentDescription = if (following) "compass" else "recentre" }) {
        Canvas(Modifier.fillMaxSize().padding(10.dp)) {
            val cx = size.width / 2; val cy = size.height / 2; val r = size.minDimension / 2
            val a = Math.toRadians(-rot)
            val nx = cx + (r * Math.sin(a)).toFloat(); val ny = cy - (r * Math.cos(a)).toFloat()
            val sx = cx - (r * Math.sin(a)).toFloat(); val sy = cy + (r * Math.cos(a)).toFloat()
            drawCircle(ring, r, Offset(cx, cy), style = Stroke(if (following) 1.5.dp.toPx() else 2.5.dp.toPx()))
            drawLine(Tok.Band, Offset(cx, cy), Offset(nx, ny), 3.dp.toPx(), StrokeCap.Round)
            drawLine(Tok.TextDim, Offset(cx, cy), Offset(sx, sy), 3.dp.toPx(), StrokeCap.Round)
            if (northUp) drawCircle(Tok.Locked, 2.5.dp.toPx(), Offset(cx, cy))
        }
    }
}

@Composable
private fun BottomCard(s: EngineState?, logger: LoggerSnap, prefs: AppPrefs, deps: RideDeps, modifier: Modifier, onOpenSheet: () -> Unit) {
    val kmh = prefs.units == "kmh"
    val replay by NavLive.replay.collectAsStateWithLifecycle()
    val active = logger.running || (replay?.running == true)
    val v = s?.v ?: 0.0
    val speedText = if (kmh) String.format(Locale.US, "%.0f", v * 3.6) else String.format(Locale.US, "%.1f", v)
    val unit = if (kmh) "km/h" else "m/s"
    val tRide = if (s != null && active) (s.t - (s.tMotionStart.takeIf { !it.isNaN() } ?: s.t)).coerceAtLeast(0.0) else 0.0
    Surface(color = Tok.Card, shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp), tonalElevation = 3.dp, modifier = modifier.fillMaxWidth().clickable(onClick = onOpenSheet)) {
        Column(Modifier.windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal)).padding(horizontal = 20.dp, vertical = 12.dp).padding(bottom = (prefs.insetBottomDp.coerceAtLeast(0)).dp)) {
            Row(verticalAlignment = Alignment.Bottom) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(speedText, style = MaterialTheme.typography.displayLarge, color = Tok.Text)
                        Spacer(Modifier.width(8.dp))
                        Text(unit, style = MaterialTheme.typography.titleMedium, color = Tok.TextDim, modifier = Modifier.padding(bottom = 12.dp))
                    }
                    val line1 = if (s != null && active) "${String.format(Locale.US, "%.2f", DistanceTracker.km)} km · ${fmtClock(tRide)}" else "Tap START, then hold still for 15 s"
                    Text(line1, style = MaterialTheme.typography.bodyLarge, color = Tok.Text)
                    val line2 = when {
                        s == null || !active -> if (prefs.scenarioArmed) "Scenario armed · ${prefs.scenarioKind}" else "IDR Nav"
                        replay?.running == true && s.phase == Phase.STAND -> "Replay · ${replay?.session ?: ""}"
                        s.mode == Mode.INERTIAL -> "Position from motion sensors"
                        s.corridorName != null -> s.corridorName ?: ""
                        s.sim -> "Position from motion sensors"
                        else -> "Campus road"
                    }
                    Text(line2, style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim)
                    if (s != null && s.scenarioArmed && s.bandKnown && s.bandDistM > 0 && s.mode == Mode.GNSS_INS) Text("No GNSS ahead · ${s.bandDistM.toInt()} m", style = MaterialTheme.typography.bodyMedium, color = Tok.Band)
                }
                Spacer(Modifier.width(12.dp))
                RideControl(logger, deps)
            }
        }
    }
}

/** Distance ridden for the card (fed by the activity from the map controller's trail). */
object DistanceTracker { var km: Double = 0.0 }

@Composable
private fun RideControl(logger: LoggerSnap, deps: RideDeps) {
    val active = logger.running || logger.state == LogService.State.FINISHING
    val replay by NavLive.replay.collectAsStateWithLifecycle()
    if (replay?.running == true) {
        Button(onClick = { deps.controller.stopReplay() }, colors = ButtonDefaults.buttonColors(containerColor = Tok.Raised, contentColor = Tok.Text), shape = RoundedCornerShape(16.dp), modifier = Modifier.height(64.dp).width(120.dp)) {
            Text("Stop replay", style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        }
        return
    }
    if (!active) {
        Button(onClick = { deps.controller.startRide() }, colors = ButtonDefaults.buttonColors(containerColor = Tok.Locked, contentColor = Color(0xFF0B1F17)), shape = RoundedCornerShape(16.dp), modifier = Modifier.height(64.dp).width(120.dp)) {
            Text("START", style = MaterialTheme.typography.titleLarge)
        }
    } else {
        HoldToStop(onStop = { deps.controller.stopRide() }, enabled = logger.state == LogService.State.RIDE || logger.state == LogService.State.CALIB)
    }
}

@Composable
private fun HoldToStop(onStop: () -> Unit, enabled: Boolean) {
    var progress by remember { mutableFloatStateOf(0f) }
    var holding by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    var job by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    Box(Modifier.height(64.dp).width(120.dp).clip(RoundedCornerShape(16.dp)).background(if (enabled) Tok.Raised else Tok.Card)
        .pointerInteropFilter { e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { if (enabled) { holding = true; job = scope.launch { val t0 = System.nanoTime(); while (holding) { progress = ((System.nanoTime() - t0) / 8e8).toFloat().coerceAtMost(1f); if (progress >= 1f) { holding = false; onStop(); break }; delay(16) }; progress = 0f } }; true }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { holding = false; job?.cancel(); progress = 0f; true }
                else -> false
            }
        }.semantics { contentDescription = "hold to stop" }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) { drawRect(Tok.Band.copy(alpha = 0.55f), size = androidx.compose.ui.geometry.Size(size.width * progress, size.height)) }
        Text(if (enabled) "Hold to stop" else "Stopping…", style = MaterialTheme.typography.titleMedium, color = Tok.Text, textAlign = TextAlign.Center)
    }
}

/** Four puck variants side by side over the live map (Field test → puck gallery), for the arm's-length comparison screenshot. */
@Composable
private fun PuckGallery(center: Offset, tilt: Float, color: Color, reduceMotion: Boolean) {
    val density = LocalDensity.current
    val step = with(density) { 84.dp.toPx() }
    val variants = PuckVariant.values()
    for ((i, v) in variants.withIndex()) {
        val x = center.x + (i - 1.5f) * step
        PuckOverlay(x, center.y, 0f, tilt, color, false, 0.0, 0.2, v, reduceMotion, Modifier.fillMaxSize())
        Text(v.label, Modifier.offsetPx(x, center.y + with(density) { 30.dp.toPx() }), style = MaterialTheme.typography.labelSmall, color = Tok.Text)
    }
}

private fun Modifier.offsetPx(x: Float, y: Float): Modifier = this.offset { androidx.compose.ui.unit.IntOffset((x - 30).toInt(), y.toInt()) }
