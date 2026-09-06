package com.snu.idr.engine

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sqrt

/** Small geometry helpers shared by the engine (spec §1). All angles in radians unless the name says deg. */
object Geo {
    const val M_PER_DEG_LAT = 111320.0
    const val TWO_PI = 2.0 * PI

    /** Python `(a + pi) % (2 pi) - pi` with a non-negative modulo. */
    fun wrap(a: Double): Double {
        var x = (a + PI) % TWO_PI
        if (x < 0.0) x += TWO_PI
        return x - PI
    }

    fun deg(rad: Double): Double = rad * 180.0 / PI
    fun rad(deg: Double): Double = deg * PI / 180.0

    /** GNSS bearing (clockwise from north, degrees) to ENU yaw (counter-clockwise from east, radians). */
    fun bearingToYaw(bearingDeg: Double): Double = PI / 2.0 - rad(bearingDeg)

    /** ENU yaw (radians) to a compass bearing in degrees [0, 360). */
    fun yawToBearingDeg(yaw: Double): Double {
        var b = 90.0 - deg(yaw)
        b %= 360.0
        if (b < 0) b += 360.0
        return b
    }

    fun norm3(x: Double, y: Double, z: Double): Double = sqrt(x * x + y * y + z * z)
}

/** Local ENU metres about a reference point: x = (lon - lon0) * 111320 cos(lat0), y = (lat - lat0) * 111320. */
class Origin(val lat0: Double, val lon0: Double) {
    val mLon: Double = Geo.M_PER_DEG_LAT * cos(Geo.rad(lat0))
    val mLat: Double = Geo.M_PER_DEG_LAT
    fun x(lon: Double): Double = (lon - lon0) * mLon
    fun y(lat: Double): Double = (lat - lat0) * mLat
    fun lat(y: Double): Double = lat0 + y / mLat
    fun lon(x: Double): Double = lon0 + x / mLon
}

/** 3x3 rotation matrices as flat row-major DoubleArray(9). */
object Mat3 {
    fun identity(): DoubleArray = doubleArrayOf(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    fun mul(a: DoubleArray, b: DoubleArray, out: DoubleArray): DoubleArray {
        val r = DoubleArray(9)
        for (i in 0 until 3) for (j in 0 until 3) {
            var s = 0.0
            for (k in 0 until 3) s += a[i * 3 + k] * b[k * 3 + j]
            r[i * 3 + j] = s
        }
        System.arraycopy(r, 0, out, 0, 9)
        return out
    }

    /** out = R v (v and out may alias). */
    fun apply(r: DoubleArray, vx: Double, vy: Double, vz: Double, out: DoubleArray) {
        val x = r[0] * vx + r[1] * vy + r[2] * vz
        val y = r[3] * vx + r[4] * vy + r[5] * vz
        val z = r[6] * vx + r[7] * vy + r[8] * vz
        out[0] = x; out[1] = y; out[2] = z
    }

    /** Rz(psi). */
    fun rotZ(psi: Double): DoubleArray {
        val c = cos(psi); val s = kotlin.math.sin(psi)
        return doubleArrayOf(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0)
    }

    /** Rotation taking the unit vector g/|g| onto +z (Rodrigues about their cross product), align.py `rot_from_gravity`. */
    fun fromGravity(gx: Double, gy: Double, gz: Double): DoubleArray {
        val n = Geo.norm3(gx, gy, gz)
        val ux = gx / n; val uy = gy / n; val uz = gz / n
        // k = u x z = (uy, -ux, 0); s = |k|; c = u . z = uz
        val kx = uy; val ky = -ux; val kz = 0.0
        val s = sqrt(kx * kx + ky * ky + kz * kz); val c = uz
        if (s < 1e-9) return if (c > 0) identity() else doubleArrayOf(1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0)
        val ax = kx / s; val ay = ky / s; val az = kz / s
        val th = kotlin.math.atan2(s, c); val st = kotlin.math.sin(th); val ct = 1.0 - cos(th)
        // K = skew(a); R = I + sin(th) K + (1 - cos th) K^2
        val k = doubleArrayOf(0.0, -az, ay, az, 0.0, -ax, -ay, ax, 0.0)
        val k2 = DoubleArray(9); mul(k, k, k2)
        val r = identity()
        for (i in 0 until 9) r[i] += st * k[i] + ct * k2[i]
        return r
    }

    /** pitch/roll/yaw in degrees for reporting, R = Rz(yaw) Ry(pitch) Rx(roll) (align.py euler_from_R). */
    fun euler(r: DoubleArray): DoubleArray {
        val yaw = kotlin.math.atan2(r[3], r[0])
        val pitch = kotlin.math.asin((-r[6]).coerceIn(-1.0, 1.0))
        val roll = kotlin.math.atan2(r[7], r[8])
        return doubleArrayOf(Geo.deg(pitch), Geo.deg(roll), Geo.deg(yaw))
    }

    fun angleDeg(ax: Double, ay: Double, az: Double, bx: Double, by: Double, bz: Double): Double {
        val d = (ax * bx + ay * by + az * bz) / (Geo.norm3(ax, ay, az) * Geo.norm3(bx, by, bz))
        return Geo.deg(kotlin.math.acos(d.coerceIn(-1.0, 1.0)))
    }
}
