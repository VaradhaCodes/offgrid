package com.snu.idrlogger

import android.location.Location
import org.json.JSONObject
import kotlin.math.sqrt

/**
 * Averages the stationary GNSS fixes collected during a calibration window.
 * Only fixes with horizontal accuracy below [maxAccM] are used; the spread is
 * reported in metres so a bad anchor is visible in the summary.
 */
class Anchor(private val maxAccM: Float = 15f) {
    private var n = 0
    private var sumLat = 0.0
    private var sumLon = 0.0
    private var sumAlt = 0.0
    private var sumAcc = 0.0
    private val lats = ArrayList<Double>(64)
    private val lons = ArrayList<Double>(64)

    var rejected = 0; private set

    @Synchronized
    fun add(loc: Location) {
        if (!loc.hasAccuracy() || loc.accuracy > maxAccM) { rejected++; return }
        n++
        sumLat += loc.latitude
        sumLon += loc.longitude
        sumAlt += loc.altitude
        sumAcc += loc.accuracy
        lats.add(loc.latitude)
        lons.add(loc.longitude)
    }

    @Synchronized fun count(): Int = n
    @Synchronized fun lat(): Double = if (n == 0) Double.NaN else sumLat / n
    @Synchronized fun lon(): Double = if (n == 0) Double.NaN else sumLon / n
    @Synchronized fun alt(): Double = if (n == 0) Double.NaN else sumAlt / n
    @Synchronized fun meanAcc(): Double = if (n == 0) Double.NaN else sumAcc / n

    /** RMS distance of the individual fixes from the mean position, in metres. */
    @Synchronized
    fun stdMeters(): Double {
        if (n < 2) return Double.NaN
        val mLat = sumLat / n
        val mLon = sumLon / n
        var ss = 0.0
        val out = FloatArray(3)
        for (i in 0 until n) {
            Location.distanceBetween(mLat, mLon, lats[i], lons[i], out)
            ss += out[0].toDouble() * out[0].toDouble()
        }
        return sqrt(ss / n)
    }

    @Synchronized
    fun toJson(): JSONObject = JSONObject().apply {
        put("n_fixes", n)
        put("n_rejected", rejected)
        put("max_acc_m_filter", maxAccM.toDouble())
        if (n > 0) {
            put("lat", lat()); put("lon", lon()); put("alt", alt())
            put("mean_acc_m", meanAcc())
            put("std_m", stdMeters().let { if (it.isNaN()) JSONObject.NULL else it })
        }
    }

    companion object {
        /** WGS84 geodesic distance between two anchors, metres; NaN if either is empty. */
        fun distance(a: Anchor, b: Anchor): Double {
            if (a.count() == 0 || b.count() == 0) return Double.NaN
            val out = FloatArray(3)
            Location.distanceBetween(a.lat(), a.lon(), b.lat(), b.lon(), out)
            return out[0].toDouble()
        }
    }
}

/** Accumulates the ridden path length from consecutive fixes. */
class PolylineLength {
    private var lastLat = Double.NaN
    private var lastLon = Double.NaN
    var meters = 0.0; private set

    @Synchronized
    fun add(lat: Double, lon: Double) {
        if (!lastLat.isNaN()) {
            val out = FloatArray(3)
            Location.distanceBetween(lastLat, lastLon, lat, lon, out)
            meters += out[0].toDouble()
        }
        lastLat = lat; lastLon = lon
    }
}
