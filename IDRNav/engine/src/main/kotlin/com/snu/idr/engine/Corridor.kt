package com.snu.idr.engine

import org.json.JSONObject
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.max

/** A learned corridor from the library (assets/corridors/<id>.json + its GeoJSON). */
class CorridorDef(
    val id: String,
    val name: String,
    /** [lat, lon] vertices in order of increasing arc length. */
    val latLon: Array<DoubleArray>,
    val anchorA: DoubleArray?, val anchorB: DoubleArray?,
    /** per direction ("AB"/"BA"): band start/end in metres from the ride's own start; end null = to the stop */
    val scenarios: Map<String, Pair<Double, Double?>>
) {
    companion object {
        /** Parses the library entry; [geojsonText] is the LineString FeatureCollection it names. */
        fun fromJson(configText: String, geojsonText: String): CorridorDef {
            val o = JSONObject(configText)
            val g = JSONObject(geojsonText)
            val f = g.getJSONArray("features").getJSONObject(0)
            val coords = f.getJSONObject("geometry").getJSONArray("coordinates")
            val pts = Array(coords.length()) { i -> val c = coords.getJSONArray(i); doubleArrayOf(c.getDouble(1), c.getDouble(0)) }
            val anchors = o.optJSONObject("anchors")
            fun anc(k: String): DoubleArray? = anchors?.optJSONArray(k)?.let { doubleArrayOf(it.getDouble(0), it.getDouble(1)) }
            val sc = HashMap<String, Pair<Double, Double?>>()
            o.optJSONObject("scenarios")?.let { s ->
                for (key in s.keys()) {
                    val e = s.getJSONObject(key)
                    val to = if (e.isNull("band_to_m")) null else e.getDouble("band_to_m")
                    sc[key] = Pair(e.getDouble("band_from_m"), to)
                }
            }
            return CorridorDef(o.getString("id"), o.optString("name", o.getString("id")), pts, anc("A"), anc("B"), sc)
        }
    }
}

/**
 * Polyline in local ENU metres (corridor.py `Corridor`): cumulative arc length S, unit tangents T;
 * project(x, y) -> (s, d signed left-positive, segment), point(s), tangent(s), heading(s).
 */
class Corridor(val def: CorridorDef, origin: Origin) {
    val n = def.latLon.size
    val px = DoubleArray(n) { origin.x(def.latLon[it][1]) }
    val py = DoubleArray(n) { origin.y(def.latLon[it][0]) }
    val nSeg = n - 1
    val len = DoubleArray(nSeg)
    val tx = DoubleArray(nSeg); val ty = DoubleArray(nSeg)
    val s0 = DoubleArray(n)
    val length: Double

    init {
        for (i in 0 until nSeg) {
            val dx = px[i + 1] - px[i]; val dy = py[i + 1] - py[i]
            len[i] = hypot(dx, dy)
            val l = max(len[i], 1e-9)
            tx[i] = dx / l; ty[i] = dy / l
            s0[i + 1] = s0[i] + len[i]
        }
        length = s0[n - 1]
    }

    /** Result of a projection; reused by the caller. */
    class Proj { var s = 0.0; var d = 0.0; var seg = 0; var dist = 0.0 }

    fun project(x: Double, y: Double, out: Proj): Proj {
        var best = Double.MAX_VALUE; var bk = 0; var bu = 0.0; var bcx = 0.0; var bcy = 0.0
        for (k in 0 until nSeg) {
            val l = max(len[k], 1e-9)
            val u = (((x - px[k]) * tx[k] + (y - py[k]) * ty[k]) / l).coerceIn(0.0, 1.0)
            val cx = px[k] + u * len[k] * tx[k]; val cy = py[k] + u * len[k] * ty[k]
            val dd = hypot(x - cx, y - cy)
            if (dd < best) { best = dd; bk = k; bu = u; bcx = cx; bcy = cy }
        }
        val cross = tx[bk] * (y - bcy) - ty[bk] * (x - bcx)
        out.s = s0[bk] + bu * len[bk]
        out.d = (if (cross > 0) 1.0 else if (cross < 0) -1.0 else 0.0) * best
        out.seg = bk; out.dist = best
        return out
    }

    /** searchsorted(S, s, 'right') - 1 clipped to [0, nSeg - 1]. */
    fun segmentOf(sIn: Double): Int {
        val s = sIn.coerceIn(0.0, length)
        var lo = 0; var hi = n   // first index with S[idx] > s
        while (lo < hi) { val mid = (lo + hi) ushr 1; if (s0[mid] <= s) lo = mid + 1 else hi = mid }
        return (lo - 1).coerceIn(0, nSeg - 1)
    }

    fun point(sIn: Double, out: DoubleArray) {
        val s = sIn.coerceIn(0.0, length); val k = segmentOf(s); val u = s - s0[k]
        out[0] = px[k] + u * tx[k]; out[1] = py[k] + u * ty[k]
    }

    fun tangent(sIn: Double, out: DoubleArray) { val k = segmentOf(sIn); out[0] = tx[k]; out[1] = ty[k] }

    fun heading(s: Double): Double { val k = segmentOf(s); return atan2(ty[k], tx[k]) }
}
