package com.snu.idr.engine

import org.json.JSONObject
import java.util.PriorityQueue
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.ln
import kotlin.math.min

/** The campus road graph: node ids with lat/lon, ways as node-id sequences (from assets/map/graph.json or an Overpass JSON). */
class RoadGraph(val nodeIds: LongArray, val lat: DoubleArray, val lon: DoubleArray, val ways: List<IntArray>, val highway: List<String>) {
    companion object {
        /** {"nodes": [[id, lat, lon], ...], "ways": [{"id", "highway", "nodes": [...]}]} */
        fun fromCompactJson(text: String): RoadGraph {
            val o = JSONObject(text); val nodes = o.getJSONArray("nodes"); val ways = o.getJSONArray("ways")
            val ids = LongArray(nodes.length()); val la = DoubleArray(nodes.length()); val lo = DoubleArray(nodes.length()); val index = HashMap<Long, Int>()
            for (i in 0 until nodes.length()) { val n = nodes.getJSONArray(i); ids[i] = n.getLong(0); la[i] = n.getDouble(1); lo[i] = n.getDouble(2); index[ids[i]] = i }
            val w = ArrayList<IntArray>(); val hw = ArrayList<String>()
            for (i in 0 until ways.length()) {
                val wo = ways.getJSONObject(i); val ns = wo.getJSONArray("nodes")
                val arr = IntArray(ns.length()) { index[ns.getLong(it)] ?: -1 }
                if (arr.any { it < 0 }) continue
                w.add(arr); hw.add(wo.optString("highway", ""))
            }
            return RoadGraph(ids, la, lo, w, hw)
        }

        /** Overpass JSON with way elements carrying `nodes` and `geometry` (data/map/snu_osm_highways_900m.json). */
        fun fromOverpassJson(text: String): RoadGraph {
            val o = JSONObject(text); val els = o.getJSONArray("elements")
            val index = HashMap<Long, Int>(); val ids = ArrayList<Long>(); val la = ArrayList<Double>(); val lo = ArrayList<Double>()
            val w = ArrayList<IntArray>(); val hw = ArrayList<String>()
            for (i in 0 until els.length()) {
                val e = els.getJSONObject(i); if (e.getString("type") != "way") continue
                val tags = e.optJSONObject("tags"); val h = tags?.optString("highway", "") ?: ""
                if (h.isEmpty()) continue
                val ns = e.getJSONArray("nodes"); val geo = e.getJSONArray("geometry")
                val arr = IntArray(ns.length())
                for (j in 0 until ns.length()) {
                    val id = ns.getLong(j)
                    val idx = index.getOrPut(id) { ids.add(id); val g = geo.getJSONObject(j); la.add(g.getDouble("lat")); lo.add(g.getDouble("lon")); ids.size - 1 }
                    arr[j] = idx
                }
                w.add(arr); hw.add(h)
            }
            return RoadGraph(ids.toLongArray(), la.toDoubleArray(), lo.toDoubleArray(), w, hw)
        }
    }
}

/** Result of one map-matching step (display only). */
class MatchResult(val seg: Int, val x: Double, val y: Double, val bearing: Double, val conf: Double, val confident: Boolean, val straight: Boolean, val t: Double, val tx: Double, val ty: Double, val wayId: Int)

/**
 * Newson-Krumm HMM over the campus graph, spec §7 / mapmatch.py: candidates within 25 m, emission -0.5 (d/5)^2 plus ln 0.05 when
 * the heading differs from the undirected edge bearing by > 60 deg, transition -|route - travelled| / 5 with a bounded Dijkstra,
 * output = the state 3 s back on the best path, confident when the margin over the runner-up exceeds ln 20. 2 Hz.
 */
class MapMatcher(graph: RoadGraph, origin: Origin, keepTypes: Set<String>? = null) {
    private class Seg(val a: Int, val b: Int, val ax: Double, val ay: Double, val bx: Double, val by: Double, val l: Double, val way: Int)
    private val segs = ArrayList<Seg>()
    private val adj = HashMap<Int, ArrayList<Pair<Int, Double>>>()
    private val nx: DoubleArray; private val ny: DoubleArray
    private val ax: DoubleArray; private val ay: DoubleArray; private val bx: DoubleArray; private val by: DoubleArray; private val L: DoubleArray; private val tx: DoubleArray; private val ty: DoubleArray

    private class Node(val seg: Int, val u: Double, val x: Double, val y: Double, val lp: Double, val back: Int)
    private val trellis = ArrayList<Array<Node>>(); private val times = ArrayList<Double>()
    private var tLast = Double.NaN; private var lastX = 0.0; private var lastY = 0.0
    private var current: MatchResult? = null

    init {
        nx = DoubleArray(graph.nodeIds.size) { origin.x(graph.lon[it]) }; ny = DoubleArray(graph.nodeIds.size) { origin.y(graph.lat[it]) }
        for ((wi, wnodes) in graph.ways.withIndex()) {
            if (keepTypes != null && graph.highway[wi] !in keepTypes) continue
            for (j in 0 until wnodes.size - 1) {
                val a = wnodes[j]; val b = wnodes[j + 1]
                val l = hypot(nx[b] - nx[a], ny[b] - ny[a]); if (l < 0.1) continue
                segs.add(Seg(a, b, nx[a], ny[a], nx[b], ny[b], l, wi))
                adj.getOrPut(a) { ArrayList() }.add(Pair(b, l)); adj.getOrPut(b) { ArrayList() }.add(Pair(a, l))
            }
        }
        ax = DoubleArray(segs.size) { segs[it].ax }; ay = DoubleArray(segs.size) { segs[it].ay }; bx = DoubleArray(segs.size) { segs[it].bx }; by = DoubleArray(segs.size) { segs[it].by }
        L = DoubleArray(segs.size) { segs[it].l }; tx = DoubleArray(segs.size) { (bx[it] - ax[it]) / L[it] }; ty = DoubleArray(segs.size) { (by[it] - ay[it]) / L[it] }
    }

    val nSegments: Int get() = segs.size

    fun reset() { trellis.clear(); times.clear(); tLast = Double.NaN; current = null }

    private fun routeDist(i: Int, ui: Double, j: Int, uj: Double, bound: Double): Double {
        if (i == j) return abs(ui - uj) * L[i]
        val si = segs[i]; val sj = segs[j]
        val ends = HashMap<Int, Double>(); ends[sj.a] = uj * L[j]; ends[sj.b] = (1 - uj) * L[j]
        var best = bound
        val dist = HashMap<Int, Double>(); val pq = PriorityQueue<Pair<Double, Int>>(compareBy { it.first })
        dist[si.a] = ui * L[i]; pq.add(Pair(ui * L[i], si.a)); dist[si.b] = (1 - ui) * L[i]; pq.add(Pair((1 - ui) * L[i], si.b))
        while (pq.isNotEmpty()) {
            val (d, n) = pq.poll()
            if (d > best || d > (dist[n] ?: 1e18)) continue
            val e = ends[n]
            if (e != null) { best = min(best, d + e); continue }
            for ((m, l) in adj[n] ?: continue) {
                val nd = d + l
                if (nd < (dist[m] ?: 1e18) && nd < best) { dist[m] = nd; pq.add(Pair(nd, m)) }
            }
        }
        return best
    }

    fun step(t: Double, x: Double, y: Double, psi: Double): MatchResult? {
        if (!tLast.isNaN() && t - tLast < MM_DT - 1e-6) return current
        val cand = ArrayList<Int>(); val cu = ArrayList<Double>(); val ccx = ArrayList<Double>(); val ccy = ArrayList<Double>(); val cd = ArrayList<Double>()
        for (k in segs.indices) {
            val u = (((x - ax[k]) * tx[k] + (y - ay[k]) * ty[k]) / L[k]).coerceIn(0.0, 1.0)
            val cx = ax[k] + u * L[k] * tx[k]; val cy = ay[k] + u * L[k] * ty[k]; val d = hypot(x - cx, y - cy)
            if (d < R_CAND) { cand.add(k); cu.add(u); ccx.add(cx); ccy.add(cy); cd.add(d) }
        }
        if (cand.isEmpty()) { tLast = t; lastX = x; lastY = y; return null }
        val logem = DoubleArray(cand.size) { i ->
            val k = cand[i]; val bear = atan2(ty[k], tx[k])
            var dh = abs(Geo.wrap(bear - psi)); dh = min(dh, Math.PI - dh)
            -0.5 * (cd[i] / SIG_Z) * (cd[i] / SIG_Z) + (if (dh < HEAD_GATE) 0.0 else ln(HEAD_PEN))
        }
        val col: Array<Node>
        if (trellis.isEmpty()) {
            col = Array(cand.size) { i -> Node(cand[i], cu[i], ccx[i], ccy[i], logem[i], -1) }
        } else {
            val prev = trellis.last(); val disp = hypot(x - lastX, y - lastY)
            col = Array(cand.size) { i ->
                var bestLp = -1e18; var bestPi = -1
                for ((pi, p) in prev.withIndex()) {
                    val rd = routeDist(p.seg, p.u, cand[i], cu[i], disp + 3 * BETA * 6)
                    val lp = p.lp - abs(rd - disp) / BETA
                    if (lp > bestLp) { bestLp = lp; bestPi = pi }
                }
                Node(cand[i], cu[i], ccx[i], ccy[i], bestLp + logem[i], bestPi)
            }
        }
        trellis.add(col); times.add(t)
        val keep = (LAG_S / MM_DT).toInt() + 20
        while (trellis.size > keep) { trellis.removeAt(0); times.removeAt(0) }
        tLast = t; lastX = x; lastY = y
        current = computeCurrent()
        return current
    }

    private fun computeCurrent(): MatchResult? {
        if (trellis.isEmpty()) return null
        val col = trellis.last()
        val lps = col.map { it.lp }.sortedDescending()
        val conf = if (lps.size > 1) lps[0] - lps[1] else 10.0
        val lag = Math.round(LAG_S / MM_DT).toInt()
        val k = maxOf(0, trellis.size - 1 - lag)
        var i = col.indices.maxByOrNull { col[it].lp } ?: return null
        val path = ArrayList<Node>()
        var step = trellis.size - 1
        while (step >= 0) {
            val node = trellis[step][i]; path.add(node)
            if (node.back < 0 || step == 0) break
            i = node.back; step--
        }
        path.reverse()
        val idx = k - (trellis.size - path.size)
        if (idx < 0 || idx >= path.size) return null
        val n = path[idx]; val sx = tx[n.seg]; val sy = ty[n.seg]
        var sgn = 1.0
        if (idx + 1 < path.size) { val m = path[idx + 1]; sgn = if ((m.x - n.x) * sx + (m.y - n.y) * sy >= 0) 1.0 else -1.0 }
        else if (idx > 0) { val m = path[idx - 1]; sgn = if ((n.x - m.x) * sx + (n.y - m.y) * sy >= 0) 1.0 else -1.0 }
        val bearing = atan2(sgn * sy, sgn * sx)
        var straight = L[n.seg] > 20.0
        for (j in maxOf(0, idx - 2) until minOf(path.size, idx + 3)) if (path[j].seg != n.seg) straight = false
        val tOut = times[maxOf(0, times.size - 1 - lag)]
        return MatchResult(n.seg, n.x, n.y, bearing, conf, conf > CONF_MIN, straight, tOut, sgn * sx, sgn * sy, segs[n.seg].way)
    }

    companion object {
        const val SIG_Z = 5.0; const val R_CAND = 25.0; val HEAD_GATE = Geo.rad(60.0); const val HEAD_PEN = 0.05; const val BETA = 5.0
        const val LAG_S = 3.0; const val MM_DT = 0.5; val CONF_MIN = ln(20.0)
        @Suppress("unused") private fun unused() = exp(0.0)
    }
}
