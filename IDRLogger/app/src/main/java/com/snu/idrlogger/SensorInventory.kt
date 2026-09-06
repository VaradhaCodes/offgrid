package com.snu.idrlogger

import android.hardware.Sensor
import android.hardware.SensorManager
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

/**
 * Dumps every sensor the device exposes, plus an explicit MISSING entry for any stream
 * the spec asks for that this device does not have. A stream is never dropped silently.
 */
object SensorInventory {

    /** stream name -> sensor type, in the order the spec lists them. */
    val WANTED: List<Pair<String, Int>> = listOf(
        "acc" to Sensor.TYPE_ACCELEROMETER,
        "acc_unc" to Sensor.TYPE_ACCELEROMETER_UNCALIBRATED,
        "gyr" to Sensor.TYPE_GYROSCOPE,
        "gyr_unc" to Sensor.TYPE_GYROSCOPE_UNCALIBRATED,
        "mag" to Sensor.TYPE_MAGNETIC_FIELD,
        "mag_unc" to Sensor.TYPE_MAGNETIC_FIELD_UNCALIBRATED,
        "grav" to Sensor.TYPE_GRAVITY,
        "linacc" to Sensor.TYPE_LINEAR_ACCELERATION,
        "rotvec" to Sensor.TYPE_ROTATION_VECTOR,
        "gamerot" to Sensor.TYPE_GAME_ROTATION_VECTOR,
        "geomagrot" to Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR,
        "baro" to Sensor.TYPE_PRESSURE,
        "light" to Sensor.TYPE_LIGHT,
        "prox" to Sensor.TYPE_PROXIMITY
    )

    fun sensorJson(s: Sensor): JSONObject = JSONObject().apply {
        put("name", s.name)
        put("vendor", s.vendor)
        put("version", s.version)
        put("type", s.type)
        put("string_type", s.stringType ?: "")
        put("resolution", s.resolution.toDouble())
        put("max_range", s.maximumRange.toDouble())
        put("min_delay_us", s.minDelay)
        put("max_delay_us", s.maxDelay)
        put("power_ma", s.power.toDouble())
        put("reporting_mode", s.reportingMode)
        put("is_wake_up", s.isWakeUpSensor)
        put("fifo_reserved_event_count", s.fifoReservedEventCount)
        put("fifo_max_event_count", s.fifoMaxEventCount)
        put("max_hz_from_min_delay", if (s.minDelay > 0) 1_000_000.0 / s.minDelay else 0.0)
        if (Build.VERSION.SDK_INT >= 30) {
            put("highest_direct_report_rate_level", s.highestDirectReportRateLevel)
        }
    }

    /** Every sensor on the device. */
    fun fullList(sm: SensorManager): JSONArray {
        val arr = JSONArray()
        for (s in sm.getSensorList(Sensor.TYPE_ALL)) arr.put(sensorJson(s))
        return arr
    }

    /** The requested streams: the default sensor for each, or MISSING. */
    fun requestedList(sm: SensorManager): JSONArray {
        val arr = JSONArray()
        for ((stream, type) in WANTED) {
            val s = sm.getDefaultSensor(type)
            val o = JSONObject()
            o.put("stream", stream)
            o.put("requested_type", type)
            if (s == null) {
                o.put("status", "MISSING")
            } else {
                o.put("status", "PRESENT")
                o.put("sensor", sensorJson(s))
            }
            arr.put(o)
        }
        return arr
    }

    /** Human-readable dump for the inventory screen. */
    fun humanReadable(sm: SensorManager): String {
        val sb = StringBuilder()
        sb.append("REQUESTED STREAMS\n")
        sb.append("=================\n")
        for ((stream, type) in WANTED) {
            val s = sm.getDefaultSensor(type)
            if (s == null) {
                sb.append(String.format("%-11s  *** MISSING ***\n", stream))
            } else {
                val hz = if (s.minDelay > 0) 1_000_000.0 / s.minDelay else 0.0
                sb.append(String.format("%-11s  %s\n", stream, s.name))
                sb.append(String.format("             %s v%d  max %.1f Hz  res %.6g  range %.6g\n",
                    s.vendor, s.version, hz, s.resolution, s.maximumRange))
                sb.append(String.format("             fifo %d/%d  wake=%b  power %.2f mA\n",
                    s.fifoReservedEventCount, s.fifoMaxEventCount, s.isWakeUpSensor, s.power))
            }
        }
        sb.append("\n\nALL SENSORS ON DEVICE\n")
        sb.append("=====================\n")
        val all = sm.getSensorList(Sensor.TYPE_ALL)
        sb.append("count = ").append(all.size).append("\n\n")
        for (s in all) {
            val hz = if (s.minDelay > 0) 1_000_000.0 / s.minDelay else 0.0
            sb.append(s.name).append("\n")
            sb.append(String.format("  type=%d %s\n", s.type, s.stringType ?: ""))
            sb.append(String.format("  vendor=%s v%d\n", s.vendor, s.version))
            sb.append(String.format("  minDelay=%d us (%.1f Hz)  maxDelay=%d us\n", s.minDelay, hz, s.maxDelay))
            sb.append(String.format("  res=%.6g  range=%.6g  power=%.2f mA\n", s.resolution, s.maximumRange, s.power))
            sb.append(String.format("  fifo=%d/%d  wakeUp=%b  mode=%d\n\n",
                s.fifoReservedEventCount, s.fifoMaxEventCount, s.isWakeUpSensor, s.reportingMode))
        }
        return sb.toString()
    }
}
