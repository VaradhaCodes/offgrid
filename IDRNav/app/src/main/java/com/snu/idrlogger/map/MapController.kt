package com.snu.idrlogger.map

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PointF
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.snu.idr.engine.Corridor
import com.snu.idr.engine.CorridorDef
import com.snu.idr.engine.EngineState
import com.snu.idr.engine.Geo
import com.snu.idr.engine.Mode
import com.snu.idr.engine.Origin
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Drives the MapLibre map from EngineState at 10 Hz on the main thread: course-up pitched camera (eased), trail (solid locked /
 * dashed dead-reckoning), 2-sigma ribbon, headlight cone whose half-angle encodes heading confidence, the no-GNSS band, the re-lock
 * reveal and the satellite toggle. The puck itself is drawn in Compose at [puckScreen].
 */
class MapController(private val ctx: Context, val map: MapLibreMap, private val style: Style, private val meta: MapAssets.StyleMeta, private val corridors: List<CorridorDef>) {
    // camera constants (handoff §4)
    var pitch = 50.0
    var zoomRest = 18.6; var zoomFast = 17.2; var vFast = 8.0
    var topPaddingFrac = 0.35     // puck at 32.5 % from the bottom
    var tracking = true; private set
    var northUp = false
    private var bearingSmooth = Double.NaN
    private var lastEaseNs = 0L
    var viewW = 1; var viewH = 1
    /**
     * Screen point of the estimate (px) and the rotation to apply to the puck (degrees clockwise). Both are recomputed from the
     * map's own projection on every camera change, so the puck is pinned to the position on the map, never to a screen pixel.
     */
    val puckScreen = PointF(0f, 0f)
    var puckRotationDeg = 0.0; private set
    /** False when the estimate projects far outside the viewport (panned away, or behind a pitched camera): don't draw the puck. */
    var puckOnScreen = false; private set
    /** Called on the main thread after every camera change, so the Compose overlay can follow the map frame by frame. */
    var onCamera: (() -> Unit)? = null
    private val handler = Handler(Looper.getMainLooper())
    private val autoRecentre = Runnable { if (!tracking) recentre() }
    var cameraBearing = 0.0; private set
    var cameraTilt = 0.0; private set
    var satellite = false; private set
    var reduceMotion = false

    // trail bookkeeping in lat/lon
    private class Part(val dr: Boolean) { val pts = ArrayList<DoubleArray>(); val sig = ArrayList<Double>() }
    private val parts = ArrayList<Part>()
    private var lastPushLat = Double.NaN; private var lastPushLon = Double.NaN; private var lastPushT = -1e9
    private val frozenLock = ArrayList<String>(); private val frozenDr = ArrayList<String>()
    private var ribbonTick = 0
    private var trailPushes = 0
    private var bandDrawnFor = Double.NaN
    private var revealFor = Double.NaN
    var trailMeters = 0.0; private set
    private var lastLat = Double.NaN; private var lastLon = Double.NaN

    private fun src(id: String): GeoJsonSource? = style.getSourceAs(id)

    init {
        // hatch pattern for the no-GNSS band (45 degree lines in the band colour)
        val size = 24; val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888); val c = Canvas(bmp)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor(MapAssets.C_BAND); strokeWidth = 3f; alpha = 230 }
        for (k in -1..2) { val o = k * 12f; c.drawLine(o, size.toFloat(), o + size, 0f, p) }
        style.addImage("idr_hatch", bmp)
        for (id in listOf("idr_band", "idr_trail_lock", "idr_trail_dr", "idr_ribbon", "idr_reveal", "idr_cone")) src(id)?.setOverrideSynchronousUpdate(true)
        map.addOnCameraMoveStartedListener { reason ->
            if (reason == MapLibreMap.OnCameraMoveStartedListener.REASON_API_GESTURE) {
                tracking = false
                handler.removeCallbacks(autoRecentre); handler.postDelayed(autoRecentre, FREE_LOOK_MS)
            }
        }
        map.addOnCameraMoveListener { syncPuck() }
        map.addOnCameraIdleListener { syncPuck() }
        map.uiSettings.isCompassEnabled = false
        map.uiSettings.isLogoEnabled = false
        map.uiSettings.setAttributionMargins(16, 0, 0, 16)
        map.uiSettings.isRotateGesturesEnabled = true
    }

    fun recentre() {
        handler.removeCallbacks(autoRecentre)
        tracking = true; bearingSmooth = Double.NaN
        applyCamera(System.nanoTime(), 420)   // the engine may be idle: pull the camera back ourselves
        syncPuck()
    }

    fun toggleNorthUp() { northUp = !northUp; recentre() }

    private var curLat = Double.NaN; private var curLon = Double.NaN; private var curHeadingBearing = 0.0
    private var curV = 0.0

    /**
     * Re-projects the estimate to a screen point and re-reads the camera. Called on every camera change (gesture, fling, and every
     * frame of an ease) as well as after every engine tick, so the puck sits exactly over the cone and the trail at all times.
     */
    fun syncPuck() {
        val cp = map.cameraPosition; cameraBearing = cp.bearing; cameraTilt = cp.tilt
        if (curLat.isNaN()) { puckOnScreen = false } else {
            val pt = map.projection.toScreenLocation(LatLng(curLat, curLon))
            puckScreen.set(pt.x, pt.y)
            puckOnScreen = pt.x.isFinite() && pt.y.isFinite() && pt.x > -viewW && pt.x < 2 * viewW && pt.y > -viewH && pt.y < 2 * viewH
        }
        puckRotationDeg = ((curHeadingBearing - cameraBearing) % 360.0 + 360.0) % 360.0
        onCamera?.invoke()
    }

    /** Called on the main thread for every engine tick. */
    fun update(s: EngineState, nowNs: Long) {
        if (!s.hasPosition) return
        val lat = if (!s.dispLat.isNaN()) s.dispLat else s.lat; val lon = if (!s.dispLon.isNaN()) s.dispLon else s.lon
        curLat = lat; curLon = lon
        val headingBearing = Geo.yawToBearingDeg(Geo.rad(s.headingDeg)); curHeadingBearing = headingBearing; curV = s.v
        // ---- trail
        pushTrail(s, lat, lon)
        // ---- cone
        updateCone(s, lat, lon)
        // ---- band / reveal
        if (s.bandKnown && s.scenarioArmed && bandDrawnFor != s.sStart) { drawBand(s); bandDrawnFor = s.sStart }
        s.reveal?.let { r -> if (revealFor != r.tReturn) { revealFor = r.tReturn; drawReveal(r.pathLatLon) } }
        // ---- camera
        if (tracking) applyCamera(nowNs, 110)
        // the puck follows the map, not the other way round: project, every tick and every camera frame
        syncPuck()
    }

    /** Points the course-up camera at the current estimate. Safe to call with the engine idle (recentre, north-up toggle). */
    private fun applyCamera(nowNs: Long, durationMs: Int) {
        if (curLat.isNaN() || viewH <= 1) return
        val dtS = if (lastEaseNs == 0L) 0.1 else min(0.5, (nowNs - lastEaseNs) / 1e9); lastEaseNs = nowNs
        val targetBearing = if (northUp) 0.0 else curHeadingBearing
        if (bearingSmooth.isNaN()) bearingSmooth = targetBearing
        else { val d = ((targetBearing - bearingSmooth + 540.0) % 360.0) - 180.0; val a = 1.0 - exp(-dtS / 0.12); bearingSmooth = (bearingSmooth + d * a + 360.0) % 360.0 }
        val zoom = zoomRest - (zoomRest - zoomFast) * min(1.0, max(0.0, curV / vFast))
        val top = (viewH * topPaddingFrac).toInt()
        val cp = CameraPosition.Builder().target(LatLng(curLat, curLon)).bearing(bearingSmooth).tilt(if (northUp) 0.0 else pitch).zoom(zoom).padding(0.0, top.toDouble(), 0.0, 0.0).build()
        if (reduceMotion) map.moveCamera(CameraUpdateFactory.newCameraPosition(cp)) else map.easeCamera(CameraUpdateFactory.newCameraPosition(cp), durationMs, false)
    }

    // ------------------------------------------------------------------ trail + ribbon
    private fun pushTrail(s: EngineState, lat: Double, lon: Double) {
        val dr = s.mode != Mode.GNSS_INS
        if (parts.isEmpty() || parts.last().dr != dr) {
            // freeze the previous part and start the new one from its last point (no gap at the mode change)
            val prev = parts.lastOrNull()
            if (prev != null && prev.pts.size >= 2) { val js = lineJson(prev.pts); if (prev.dr) frozenDr.add(js) else frozenLock.add(js) }
            val np = Part(dr); if (prev != null && prev.pts.isNotEmpty()) { np.pts.add(prev.pts.last()); np.sig.add(prev.sig.last()) }
            parts.add(np); lastPushT = -1e9
        }
        val part = parts.last()
        if (!lastLat.isNaN()) trailMeters += hypot((lat - lastLat) * 111320.0, (lon - lastLon) * 111320.0 * cos(Geo.rad(lat)))
        lastLat = lat; lastLon = lon
        val dist = if (lastPushLat.isNaN()) 99.0 else hypot((lat - lastPushLat) * 111320.0, (lon - lastPushLon) * 111320.0 * cos(Geo.rad(lat)))
        if (dist > 0.5 || s.t - lastPushT > 1.0 || part.pts.size < 2) {
            if (part.pts.size >= 2 && dist <= 0.5 && s.t - lastPushT <= 1.0) return
            part.pts.add(doubleArrayOf(lat, lon)); part.sig.add(if (s.sigmaPos.isNaN()) 0.0 else s.sigmaPos)
            lastPushLat = lat; lastPushLon = lon; lastPushT = s.t
            val active = if (part.pts.size >= 2) lineJson(part.pts) else null   // MapLibre rejects a one-point LineString
            val js = if (dr) fc(frozenDr, active) else fc(frozenLock, active)
            val source = src(if (dr) "idr_trail_dr" else "idr_trail_lock")
            source?.setGeoJson(js)
            if (++trailPushes <= 3 || trailPushes % 200 == 0) Log.i("IDR", "trail push #$trailPushes dr=$dr source=${source != null} pts=${part.pts.size} json=${js.take(160)} layer=${style.getLayer(if (dr) "idr_trail_dr" else "idr_trail_lock")?.visibility?.value}")
            if (dr && ++ribbonTick % 5 == 0) updateRibbon()
        }
    }

    private fun lineJson(pts: List<DoubleArray>): String {
        val sb = StringBuilder(pts.size * 26 + 64)
        sb.append("{\"type\":\"Feature\",\"properties\":{},\"geometry\":{\"type\":\"LineString\",\"coordinates\":[")
        for ((i, p) in pts.withIndex()) { if (i > 0) sb.append(','); sb.append('[').append(fmt(p[1])).append(',').append(fmt(p[0])).append(']') }
        sb.append("]}}"); return sb.toString()
    }

    private fun fc(frozen: List<String>, active: String?): String {
        val sb = StringBuilder(); sb.append("{\"type\":\"FeatureCollection\",\"features\":[")
        var first = true
        for (f in frozen) { if (!first) sb.append(','); sb.append(f); first = false }
        if (active != null && active.isNotEmpty()) { if (!first) sb.append(','); sb.append(active) }
        sb.append("]}"); return sb.toString()
    }

    private fun updateRibbon() {
        val sb = StringBuilder(); sb.append("{\"type\":\"FeatureCollection\",\"features\":[")
        var first = true
        for (part in parts) {
            if (!part.dr) continue
            for (i in 1 until part.pts.size) {
                val a = part.pts[i - 1]; val b = part.pts[i]; val w = 2.0 * max(part.sig[i - 1], part.sig[i])
                if (!first) sb.append(','); first = false
                sb.append("{\"type\":\"Feature\",\"properties\":{\"w\":").append(fmt(w, 2)).append("},\"geometry\":{\"type\":\"LineString\",\"coordinates\":[[")
                    .append(fmt(a[1])).append(',').append(fmt(a[0])).append("],[").append(fmt(b[1])).append(',').append(fmt(b[0])).append("]]}}")
            }
        }
        sb.append("]}"); src("idr_ribbon")?.setGeoJson(sb.toString())
    }

    // ------------------------------------------------------------------ cone
    private fun updateCone(s: EngineState, lat: Double, lon: Double) {
        val color = when (s.mode) { Mode.GNSS_INS -> MapAssets.C_LOCKED; Mode.INERTIAL -> MapAssets.C_DR; Mode.RECOVERING -> MapAssets.C_RELOCK }
        val sig = if (s.headingSigmaDeg.isNaN()) 10.0 else s.headingSigmaDeg
        val half = when { sig <= 2.0 -> 12.0; sig >= 10.0 -> 35.0; else -> 12.0 + (sig - 2.0) / 8.0 * 23.0 }
        val dim = s.stop
        val r = 60.0; val yaw = Geo.rad(s.headingDeg)
        val mLat = 111320.0; val mLon = 111320.0 * cos(Geo.rad(lat))
        val sb = StringBuilder(); sb.append("{\"type\":\"FeatureCollection\",\"features\":[")
        for (ring in 1..4) {
            val rr = r * ring / 4.0
            if (ring > 1) sb.append(',')
            sb.append("{\"type\":\"Feature\",\"properties\":{\"ring\":").append(ring).append("},\"geometry\":{\"type\":\"Polygon\",\"coordinates\":[[")
            sb.append('[').append(fmt(lon)).append(',').append(fmt(lat)).append(']')
            val n = 10
            for (i in 0..n) {
                val a = yaw + Geo.rad(-half + 2 * half * i / n)
                val x = rr * cos(a); val y = rr * sin(a)
                sb.append(",[").append(fmt(lon + x / mLon)).append(',').append(fmt(lat + y / mLat)).append(']')
            }
            sb.append(",[").append(fmt(lon)).append(',').append(fmt(lat)).append("]]]}}")
        }
        sb.append("]}"); src("idr_cone")?.setGeoJson(sb.toString())
        val ops = doubleArrayOf(0.14, 0.12, 0.10, 0.06)
        for (ring in 1..4) style.getLayer("idr_cone_$ring")?.setProperties(PropertyFactory.fillColor(color), PropertyFactory.fillOpacity((ops[ring - 1] * (if (dim) 0.4 else 1.0)).toFloat()))
    }

    // ------------------------------------------------------------------ band + reveal
    private fun drawBand(s: EngineState) {
        val def = corridors.firstOrNull { it.id == s.corridorId } ?: return
        val o = Origin(def.latLon[0][0], def.latLon[0][1]); val cor = Corridor(def, o)
        val from = s.sStart + s.dir * s.bandFromM
        val bt = s.bandToM
        val to = if (bt != null) s.sStart + s.dir * bt else (if (s.dir > 0) cor.length else 0.0)
        val a = min(from, to).coerceIn(0.0, cor.length); val b = max(from, to).coerceIn(0.0, cor.length)
        if (b - a < 1.0) return
        val left = ArrayList<DoubleArray>(); val right = ArrayList<DoubleArray>(); val p = DoubleArray(2); val tg = DoubleArray(2); val half = 4.5
        var sPos = a
        while (true) {
            cor.point(sPos, p); cor.tangent(sPos, tg); val nx = -tg[1]; val ny = tg[0]
            left.add(doubleArrayOf(o.lat(p[1] + half * ny), o.lon(p[0] + half * nx))); right.add(doubleArrayOf(o.lat(p[1] - half * ny), o.lon(p[0] - half * nx)))
            if (sPos >= b) break
            sPos = min(b, sPos + 2.0)
        }
        val sb = StringBuilder(); sb.append("{\"type\":\"FeatureCollection\",\"features\":[{\"type\":\"Feature\",\"properties\":{},\"geometry\":{\"type\":\"Polygon\",\"coordinates\":[[")
        var first = true
        for (q in left) { if (!first) sb.append(','); first = false; sb.append('[').append(fmt(q[1])).append(',').append(fmt(q[0])).append(']') }
        for (q in right.asReversed()) { sb.append(",[").append(fmt(q[1])).append(',').append(fmt(q[0])).append(']') }
        sb.append(",[").append(fmt(left[0][1])).append(',').append(fmt(left[0][0])).append("]]]}}]}")
        src("idr_band")?.setGeoJson(sb.toString())
        Log.i("IDR", "band drawn s=[${"%.0f".format(a)}, ${"%.0f".format(b)}] on ${def.id}")
    }

    fun clearBand() { src("idr_band")?.setGeoJson(fc(emptyList(), null)); bandDrawnFor = Double.NaN }

    private fun drawReveal(path: List<DoubleArray>) {
        if (path.size < 2) return
        src("idr_reveal")?.setGeoJson(fc(emptyList(), lineJson(path)))
    }

    fun setRevealOpacity(a: Float) { style.getLayer("idr_reveal")?.setProperties(PropertyFactory.lineOpacity(a.coerceIn(0f, 1f))) }

    // ------------------------------------------------------------------ satellite
    fun setSatellite(on: Boolean) {
        satellite = on
        val vis = if (on) Property.NONE else Property.VISIBLE
        style.getLayer("idr_esri")?.setProperties(PropertyFactory.visibility(if (on) Property.VISIBLE else Property.NONE))
        // the Protomaps land fill ("earth") and every fill/line that would paint over the imagery
        val opaque = style.layers.filter { l -> l.id == "earth" || l.id.startsWith("earth_") || l.id.startsWith("boundaries") }.map { it.id }
        for (id in meta.roadIds + meta.landuseIds + meta.waterIds + MapAssets.HIDE_IN_SATELLITE_OURS + opaque) style.getLayer(id)?.setProperties(PropertyFactory.visibility(vis))
        for (id in meta.labelIds + listOf("idr_labels_major", "idr_labels_minor")) style.getLayer(id)?.setProperties(
            PropertyFactory.textHaloWidth(if (on) 1.6f else 1.2f), PropertyFactory.textHaloColor(if (on) "rgba(0,0,0,0.85)" else MapAssets.C_HALO), PropertyFactory.textColor(if (on) "#E8E8E8" else MapAssets.C_LABEL))
    }

    fun resetTrail() {
        parts.clear(); frozenLock.clear(); frozenDr.clear(); lastPushLat = Double.NaN; lastPushT = -1e9; trailMeters = 0.0; lastLat = Double.NaN
        for (id in listOf("idr_trail_lock", "idr_trail_dr", "idr_ribbon", "idr_reveal", "idr_cone", "idr_band")) src(id)?.setGeoJson(fc(emptyList(), null))
        bandDrawnFor = Double.NaN; revealFor = Double.NaN; setRevealOpacity(0f)
    }

    /** Jump the camera to a place (before the first fix). */
    fun jumpTo(lat: Double, lon: Double, zoom: Double) { map.moveCamera(CameraUpdateFactory.newCameraPosition(CameraPosition.Builder().target(LatLng(lat, lon)).zoom(zoom).tilt(0.0).bearing(0.0).build())); syncPuck() }

    /** Drop the pending auto-recentre when the screen goes away. */
    fun release() { handler.removeCallbacks(autoRecentre); onCamera = null }

    companion object {
        /** How long the map stays where the rider dragged it before it snaps back to the position. */
        const val FREE_LOOK_MS = 6_000L
        fun fmt(v: Double, d: Int = 7): String = String.format(java.util.Locale.US, "%.${d}f", v)
        const val TWO_PI = 2 * PI
    }
}
