package com.snu.idrlogger

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.display.DisplayManager
import android.location.GnssMeasurementRequest
import android.location.GnssMeasurementsEvent
import android.location.GnssStatus
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.location.OnNmeaMessageListener
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import android.os.StatFs
import android.os.SystemClock
import android.util.Log
import android.view.Display
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.snu.idr.engine.EngineConfig
import com.snu.idr.engine.Scenario
import com.snu.idrlogger.service.EngineAssets
import com.snu.idrlogger.service.EngineRunner
import com.snu.idrlogger.service.NavLive
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicLong

class LogService : Service() {

    // ------------------------------------------------------------------ state
    enum class State { IDLE, CALIB, RIDE, STOP_CALIB, FINISHING, DONE }

    /** Everything the UI reads. Written by the service, polled by the activity. */
    object Live {
        @Volatile var running = false
        @Volatile var state: State = State.IDLE
        @Volatile var countdown = 0
        @Volatile var sessionName = ""
        @Volatile var sessionDir = ""
        @Volatile var statsText = ""
        @Volatile var summary: String? = null
        @Volatile var outage = false
        @Volatile var lastError: String? = null
        @Volatile var elapsedSec = 0L
        // headline numbers the activity colours
        @Volatile var accHz = 0.0
        @Volatile var gyrHz = 0.0
        @Volatile var magHz = 0.0
        @Volatile var gnssAgeS = Double.NaN
        @Volatile var gnssAccM = Double.NaN
        @Volatile var satsUsed = 0
        @Volatile var satsVisible = 0
        @Volatile var meanCn0 = Double.NaN
        @Volatile var gaps = 0L
        @Volatile var dropped = 0L
    }

    companion object {
        const val TAG = "IDR"
        const val ACTION_START = "com.snu.idrlogger.START"
        const val ACTION_STOP = "com.snu.idrlogger.STOP"
        const val ACTION_NOTE = "com.snu.idrlogger.NOTE"
        const val ACTION_OUTAGE = "com.snu.idrlogger.OUTAGE"
        const val ACTION_ABORT = "com.snu.idrlogger.ABORT"
        const val ACTION_REPLAY = "com.snu.idrlogger.REPLAY"
        const val ACTION_REPLAY_STOP = "com.snu.idrlogger.REPLAY_STOP"
        const val ACTION_MANUAL_DENIAL = "com.snu.idrlogger.MANUAL_DENIAL"

        // nav extras
        const val EX_NAV = "nav"                     // boolean: run the engine and write engine_out/engine_events
        const val EX_SCENARIO = "scenario"           // none | band | timer | manual
        const val EX_BAND_FROM = "band_from"         // metres from the ride start
        const val EX_BAND_TO = "band_to"             // metres, <= 0 = to the stop
        const val EX_TIMER_START = "timer_start"     // s after motion start
        const val EX_TIMER_HOLD = "timer_hold"       // s
        const val EX_MODEL = "model"                 // litert | kotlin
        const val EX_LOGGING = "logging"             // boolean: write the 22 sensor streams (nav rides always log the engine)
        const val EX_FORCED_CORRIDOR = "forced_corridor"
        const val EX_REPLAY_DIR = "replay_dir"
        const val EX_REPLAY_SPEED = "replay_speed"   // 0 = as fast as possible

        const val EX_ROUTE = "route"
        const val EX_DIR = "dir"
        const val EX_RUN = "run"
        const val EX_PURPOSE = "purpose"
        const val EX_RIDER = "rider"
        const val EX_NOTES = "notes"
        const val EX_VARIATION = "variation"
        const val EX_TEXT = "text"
        const val EX_ON = "on"

        const val CALIB_SEC = 15
        const val STOP_CALIB_SEC = 15

        private const val CHANNEL = "idr_logging"
        private const val NOTIF_ID = 1
        private const val SAMPLING_US = 2000        // 500 Hz request; HAL clamps to minDelay

        /**
         * Streams that report continuously at a fixed cadence. The "gaps > 50 ms" metric is
         * only meaningful for these: a 1 Hz GNSS fix or an on-change light reading has a dt
         * above 50 ms by definition, and counting those as gaps hides the number that matters.
         */
        val CONTINUOUS = setOf(
            "acc", "acc_unc", "gyr", "gyr_unc", "mag", "mag_unc",
            "grav", "linacc", "rotvec", "gamerot", "geomagrot", "baro"
        )
    }

    // ------------------------------------------------------------------ plumbing
    private lateinit var sensorManager: SensorManager
    private lateinit var locationManager: LocationManager
    private lateinit var powerManager: PowerManager

    private var sensorThread: HandlerThread? = null
    private var sensorHandler: Handler? = null
    private var gnssThread: HandlerThread? = null
    private var gnssHandler: Handler? = null
    private lateinit var main: Handler

    private var wakeLock: PowerManager.WakeLock? = null

    private var streams: StreamSet? = null
    private var sessionDir: File? = null
    private var sessionUuid: String = ""
    private var sessionStartWallMs = 0L
    private var sessionStartElapsedNs = 0L
    private var rideStartElapsedNs = 0L

    private val meta = HashMap<String, String>()

    // ---- nav engine
    private var runner: EngineRunner? = null
    private var navMode = false
    private var sensorLogging = true
    private var wEngine: StreamWriter? = null
    private var wEngineEvents: StreamWriter? = null
    private var replayStreams: StreamSet? = null
    private var replayRunner: EngineRunner? = null

    // per-stream shortcuts (hot path)
    private var wAcc: StreamWriter? = null
    private var wAccU: StreamWriter? = null
    private var wGyr: StreamWriter? = null
    private var wGyrU: StreamWriter? = null
    private var wMag: StreamWriter? = null
    private var wMagU: StreamWriter? = null
    private var wGrav: StreamWriter? = null
    private var wLin: StreamWriter? = null
    private var wRot: StreamWriter? = null
    private var wGame: StreamWriter? = null
    private var wGeo: StreamWriter? = null
    private var wBaro: StreamWriter? = null
    private var wLight: StreamWriter? = null
    private var wProx: StreamWriter? = null
    private var wFix: StreamWriter? = null
    private var wFused: StreamWriter? = null
    private var wSat: StreamWriter? = null
    private var wRaw: StreamWriter? = null
    private var wNmea: StreamWriter? = null
    private var wSys: StreamWriter? = null
    private var wClock: StreamWriter? = null
    private var wEvents: StreamWriter? = null

    private val registered = ArrayList<Sensor>()
    private var missing = ArrayList<String>()

    // anchors / geometry
    private var startAnchor = Anchor()
    private var endAnchor = Anchor()
    private var polyline = PolylineLength()

    // live GNSS bookkeeping
    @Volatile private var lastFixElapsedNs = 0L
    @Volatile private var lastFixAcc = Float.NaN
    @Volatile private var satsUsed = 0
    @Volatile private var satsVisible = 0
    @Volatile private var meanCn0 = Double.NaN
    @Volatile private var agcBroken = false
    private val nGnssRawEvents = AtomicLong(0)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        main = Handler(mainLooper)
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ensureForeground()
        when (intent?.action) {
            ACTION_START -> if (Live.state == State.IDLE || Live.state == State.DONE) startSession(intent)
            ACTION_STOP -> beginStopCalib()
            ACTION_NOTE -> writeEvent("NOTE", intent.getStringExtra(EX_TEXT) ?: "")
            ACTION_OUTAGE -> {
                val on = intent.getBooleanExtra(EX_ON, false)
                Live.outage = on
                writeEvent(if (on) "OUTAGE_ON" else "OUTAGE_OFF", "")
            }
            ACTION_ABORT -> finishSession(aborted = true)
            ACTION_REPLAY -> startReplay(intent)
            ACTION_REPLAY_STOP -> stopReplay()
            ACTION_MANUAL_DENIAL -> {
                val on = intent.getBooleanExtra(EX_ON, false)
                runner?.manualDenial = on; replayRunner?.manualDenial = on
                Live.outage = on
                writeEvent(if (on) "OUTAGE_ON" else "OUTAGE_OFF", "manual denial")
            }
            else -> {}
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        if (Live.running) finishSession(aborted = true)
        stopReplay()
        stopTickers()
        unregisterAll()
        releaseWakeLock()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ session lifecycle
    @SuppressLint("MissingPermission")
    private fun startSession(intent: Intent) {
        try {
            navMode = intent.getBooleanExtra(EX_NAV, false)
            sensorLogging = intent.getBooleanExtra(EX_LOGGING, true)
            val route = if (navMode) "FREE" else (intent.getStringExtra(EX_ROUTE) ?: "SNU_AJB")
            val dir = if (navMode) "NA" else (intent.getStringExtra(EX_DIR) ?: "AB")
            val run = intent.getIntExtra(EX_RUN, 1)
            meta["route_id"] = route
            meta["direction"] = dir
            meta["run_no"] = run.toString()
            meta["purpose"] = intent.getStringExtra(EX_PURPOSE) ?: "pilot"
            meta["rider_id"] = intent.getStringExtra(EX_RIDER) ?: "rider_1"
            meta["notes"] = intent.getStringExtra(EX_NOTES) ?: ""
            meta["variation"] = intent.getStringExtra(EX_VARIATION) ?: "normal"

            val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
            val name = if (navMode) "${stamp}_NAV_run${run}" else "${stamp}_${route}_${dir}_run${run}"
            val root = File(getExternalFilesDir(null), "sessions")
            val d = File(root, name)
            if (!d.mkdirs() && !d.isDirectory) throw IllegalStateException("cannot create $d")
            sessionDir = d
            sessionUuid = UUID.randomUUID().toString()

            // reset state
            startAnchor = Anchor(); endAnchor = Anchor(); polyline = PolylineLength()
            lastFixElapsedNs = 0L; lastFixAcc = Float.NaN
            satsUsed = 0; satsVisible = 0; meanCn0 = Double.NaN
            agcBroken = false; nGnssRawEvents.set(0)
            registered.clear(); missing = ArrayList()
            Live.summary = null; Live.lastError = null; Live.outage = false

            openStreams(d)

            sessionStartWallMs = System.currentTimeMillis()
            sessionStartElapsedNs = SystemClock.elapsedRealtimeNanos()

            if (navMode) startEngine(intent, d)

            Live.sessionName = name
            Live.sessionDir = d.absolutePath
            Live.running = true
            setState(State.CALIB)
            Live.countdown = CALIB_SEC

            acquireWakeLock()
            startThreads()
            registerSensors()
            registerLocation()
            writeClockLine()
            writeEvent("SESSION_START", name)
            writeEvent("CALIB_START", "stand still ${CALIB_SEC}s")
            armTransition(CALIB_SEC) {
                writeEvent("CALIB_END", "n_fixes=${startAnchor.count()}")
                writeEvent("RIDE_START", "")
                rideStartElapsedNs = SystemClock.elapsedRealtimeNanos()
                setState(State.RIDE)
            }

            writeSessionJsonAtStart(d)
            streams?.start()
            startTickers()
            Log.i(TAG, "session started: $name  dir=${d.absolutePath}")
        } catch (t: Throwable) {
            Log.e(TAG, "startSession failed", t)
            Live.lastError = "start failed: ${t.message}"
            Live.running = false
            setState(State.IDLE)
        }
    }

    private fun beginStopCalib() {
        if (Live.state != State.RIDE && Live.state != State.CALIB) return
        cancelTransition()
        setState(State.STOP_CALIB)
        Live.countdown = STOP_CALIB_SEC
        writeEvent("STOP_CALIB_START", "stand still ${STOP_CALIB_SEC}s")
        armTransition(STOP_CALIB_SEC) {
            writeEvent("STOP_CALIB_END", "n_fixes=${endAnchor.count()}")
            finishSession(aborted = false)
        }
    }

    private fun finishSession(aborted: Boolean) {
        if (!Live.running) return
        Live.running = false
        setState(State.FINISHING)
        writeEvent(if (aborted) "SESSION_ABORT" else "SESSION_END", "")
        writeClockLine()

        stopTickers()
        unregisterAll()

        runner?.let { r ->
            r.stop()
            val cid = r.engine.corridorId
            meta["route_id"] = cid ?: "FREE"
            val dirState = NavLive.state.value?.dir ?: 0
            meta["direction"] = if (dirState > 0) "AB" else if (dirState < 0) "BA" else "NA"
            meta["speed_model"] = r.speedModel.name
        }
        runner = null

        val st = streams
        val d = sessionDir
        st?.stopAndClose()

        val summary = try {
            if (d != null) patchSessionJson(d, aborted) else "no session dir"
        } catch (t: Throwable) {
            Log.e(TAG, "patch failed", t); "summary failed: ${t.message}"
        }

        streams = null
        releaseWakeLock()
        Live.summary = summary
        setState(State.DONE)
        Live.countdown = 0
        Log.i(TAG, "session finished\n$summary")
        stopForeground(STOP_FOREGROUND_REMOVE)
        isForeground = false
        stopSelf()
    }

    private fun setState(s: State) {
        Live.state = s
        updateNotification()
    }

    // ------------------------------------------------------------------ nav engine
    private fun engineConfig(intent: Intent, forReplay: Boolean): EngineConfig {
        val scenario = EngineRunner.scenarioFrom(intent.getStringExtra(EX_SCENARIO) ?: "none",
            intent.getDoubleExtra(EX_BAND_FROM, 200.0), intent.getDoubleExtra(EX_BAND_TO, 0.0),
            intent.getDoubleExtra(EX_TIMER_START, 40.0), intent.getDoubleExtra(EX_TIMER_HOLD, 90.0))
        val forced = intent.getStringExtra(EX_FORCED_CORRIDOR)?.takeIf { it.isNotEmpty() }
        return EngineConfig(corridors = EngineAssets.corridors(this), roadGraph = EngineAssets.roadGraph(this), forcedCorridorId = forced,
            corridorAuto = forced == null, mapMatch = true, scenario = scenario, gapAtTick = !forReplay || true)
    }

    private fun startEngine(intent: Intent, d: File) {
        val st = streams ?: return
        wEngine = st.create("engine_out", com.snu.idr.engine.EngineState.CSV_HEADER, 20_000)
        wEngineEvents = st.create("engine_events", EngineRunner.EVENTS_HEADER, 4096)
        val r = EngineRunner(this, engineConfig(intent, false), intent.getStringExtra(EX_MODEL) ?: "litert", sessionStartElapsedNs, wEngine, wEngineEvents)
        runner = r
        r.startLive()
        NavLive.replay.value = null
        Log.i(TAG, "engine started: model=${r.speedModel.name} scenario=${intent.getStringExtra(EX_SCENARIO)}")
    }

    private fun startReplay(intent: Intent) {
        if (Live.running) { Live.lastError = "stop the ride first"; return }
        if (replayRunner != null) stopReplay()
        val dir = File(intent.getStringExtra(EX_REPLAY_DIR) ?: return)
        if (!File(dir, "acc.csv").exists()) { Live.lastError = "no acc.csv in ${dir.name}"; return }
        val speed = intent.getDoubleExtra(EX_REPLAY_SPEED, 0.0)
        val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val out = File(File(getExternalFilesDir(null), "replay_out"), "${dir.name}__$stamp"); out.mkdirs()
        val rs = StreamSet(out); replayStreams = rs
        val we = rs.create("engine_out", com.snu.idr.engine.EngineState.CSV_HEADER, 20_000)
        val wv = rs.create("engine_events", EngineRunner.EVENTS_HEADER, 4096)
        rs.start()
        val baseCfg = engineConfig(intent, true)
        val anchor = try { JSONObject(File(dir, "session.json").readText()).optJSONObject("start_anchor")?.let { a -> if (a.has("lat")) doubleArrayOf(a.getDouble("lat"), a.getDouble("lon")) else null } } catch (_: Throwable) { null }
        val cfg = EngineConfig(corridors = baseCfg.corridors, roadGraph = baseCfg.roadGraph, forcedCorridorId = baseCfg.forcedCorridorId, corridorAuto = baseCfg.corridorAuto, mapMatch = baseCfg.mapMatch,
            originLatLon = anchor, scenario = baseCfg.scenario, gapAtTick = baseCfg.gapAtTick)
        val r = EngineRunner(this, cfg, intent.getStringExtra(EX_MODEL) ?: "litert", 0L, we, wv)
        replayRunner = r
        acquireWakeLock()
        r.startReplay(dir, speed) { err ->
            main.post {
                rs.stopAndClose(); replayStreams = null
                try { File(out, "replay.json").writeText(JSONObject().apply {
                    put("session", dir.name); put("speed", speed); put("model", r.speedModel.name); put("error", err?.message ?: JSONObject.NULL)
                    put("tick_ms_mean", r.engine.tickMsMean); put("tick_ms_max", r.engine.tickMsMax); put("rows", r.wroteRows)
                    put("outages", JSONArray().apply { for (o in r.engine.outageSummaries) put(JSONObject().apply { put("t_start", o.tStart); put("t_end", o.tEnd); put("distance_m", o.distanceM); put("duration_s", o.durationS); put("end_error_m", o.endErrorM); put("max_error_m", o.maxErrorM); put("recovery_step_m", o.recoveryStepM); put("sim", o.sim); put("armed", o.armedAtEntry) }) })
                }.toString(2)) } catch (_: Throwable) {}
                if (replayRunner === r) { replayRunner = null; releaseWakeLock() }
                NavLive.engineInfo.value = "replay ${dir.name} done: ${r.wroteRows} rows, tick ${String.format(Locale.US, "%.2f", r.engine.tickMsMean)} ms mean / ${String.format(Locale.US, "%.1f", r.engine.tickMsMax)} max, model ${r.speedModel.name}" + (err?.let { " ERROR ${it.message}" } ?: "")
                if (!Live.running) { stopForeground(STOP_FOREGROUND_REMOVE); isForeground = false; stopSelf() }
            }
        }
    }

    private fun stopReplay() {
        replayRunner?.stop(); replayRunner = null
        replayStreams?.stopAndClose(); replayStreams = null
        NavLive.replay.value = NavLive.replay.value?.let { com.snu.idrlogger.service.ReplayStatus(it.session, it.tNow, it.tEnd, it.speed, false, it.outDir) }
        if (!Live.running) releaseWakeLock()
    }

    // ------------------------------------------------------------------ streams
    private fun openStreams(d: File) {
        val s = StreamSet(d)
        streams = s
        wEvents = s.create("events", "t_ns,wall_ms,type,text", 4096)
        wClock = s.create("clock", "t_ns,wall_ms", 4096)

        val sm = sensorManager
        fun ifPresent(type: Int, name: String, header: String): StreamWriter? {
            return if (sm.getDefaultSensor(type) != null) s.create(name, header)
            else { missing.add(name); null }
        }
        wAcc = ifPresent(Sensor.TYPE_ACCELEROMETER, "acc", "t_ns,ax,ay,az,accuracy")
        wAccU = ifPresent(Sensor.TYPE_ACCELEROMETER_UNCALIBRATED, "acc_unc", "t_ns,ax,ay,az,bx,by,bz")
        wGyr = ifPresent(Sensor.TYPE_GYROSCOPE, "gyr", "t_ns,gx,gy,gz,accuracy")
        wGyrU = ifPresent(Sensor.TYPE_GYROSCOPE_UNCALIBRATED, "gyr_unc", "t_ns,gx,gy,gz,bx,by,bz")
        wMag = ifPresent(Sensor.TYPE_MAGNETIC_FIELD, "mag", "t_ns,mx,my,mz,accuracy")
        wMagU = ifPresent(Sensor.TYPE_MAGNETIC_FIELD_UNCALIBRATED, "mag_unc", "t_ns,mx,my,mz,bx,by,bz")
        wGrav = ifPresent(Sensor.TYPE_GRAVITY, "grav", "t_ns,gx,gy,gz")
        wLin = ifPresent(Sensor.TYPE_LINEAR_ACCELERATION, "linacc", "t_ns,ax,ay,az")
        wRot = ifPresent(Sensor.TYPE_ROTATION_VECTOR, "rotvec", "t_ns,qx,qy,qz,qw,heading_acc_rad")
        wGame = ifPresent(Sensor.TYPE_GAME_ROTATION_VECTOR, "gamerot", "t_ns,qx,qy,qz,qw")
        wGeo = ifPresent(Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR, "geomagrot", "t_ns,qx,qy,qz,qw")
        wBaro = ifPresent(Sensor.TYPE_PRESSURE, "baro", "t_ns,hPa")
        wLight = ifPresent(Sensor.TYPE_LIGHT, "light", "t_ns,value")
        wProx = ifPresent(Sensor.TYPE_PROXIMITY, "prox", "t_ns,value")

        val fixHeader = "t_ns,wall_ms,lat,lon,alt,acc_h,acc_v,speed,has_speed,speed_acc," +
                "bearing,has_bearing,bearing_acc,provider,elapsed_unc_ns,is_mock,n_sats_used"
        wFix = s.create("gnss_fix", fixHeader, 20_000)
        wFused = s.create("fused_fix", fixHeader, 20_000)
        wSat = s.create("gnss_status",
            "t_ns,constellation,svid,cn0,baseband_cn0,elev,azim,used_in_fix,has_ephemeris,has_almanac,carrier_freq_hz",
            200_000)
        wRaw = s.create("gnss_raw",
            "t_ns,clk_time_ns,full_bias_ns,bias_ns,drift_nps,hw_clock_disc,leap_s,time_unc_ns,bias_unc_ns,drift_unc_nps," +
                    "constellation,svid,cn0,baseband_cn0,pr_rate_mps,pr_rate_unc,adr_state,adr_m,adr_unc_m," +
                    "carrier_freq_hz,multipath,received_sv_time_ns,state,agc_db,code_type",
            200_000)
        wNmea = s.create("nmea", "t_ns,wall_ms,sentence", 100_000)
        wSys = s.create("sys",
            "t_ns,wall_ms,batt_pct,charging,batt_temp_c,thermal_status,rotation,free_bytes", 4096)
    }

    // ------------------------------------------------------------------ threads
    private fun startThreads() {
        val st = HandlerThread("idr-sensors", android.os.Process.THREAD_PRIORITY_URGENT_AUDIO)
        st.start(); sensorThread = st; sensorHandler = Handler(st.looper)
        val gt = HandlerThread("idr-gnss", android.os.Process.THREAD_PRIORITY_FOREGROUND)
        gt.start(); gnssThread = gt; gnssHandler = Handler(gt.looper)
    }

    private fun stopThreads() {
        sensorThread?.quitSafely(); sensorThread = null; sensorHandler = null
        gnssThread?.quitSafely(); gnssThread = null; gnssHandler = null
    }

    // ------------------------------------------------------------------ sensors
    private val sb = StringBuilder(160)   // sensor thread only

    private val sensorListener = object : SensorEventListener {
        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
        override fun onSensorChanged(e: SensorEvent) {
            val t = e.timestamp
            val v = e.values
            when (e.sensor.type) {
                Sensor.TYPE_ACCELEROMETER -> { runner?.pushAcc(t, v[0], v[1], v[2]); wAcc?.add(t, r3a(t, v, e.accuracy)) }
                Sensor.TYPE_GYROSCOPE -> { runner?.pushGyr(t, v[0], v[1], v[2]); wGyr?.add(t, r3a(t, v, e.accuracy)) }
                Sensor.TYPE_MAGNETIC_FIELD -> wMag?.add(t, r3a(t, v, e.accuracy))
                Sensor.TYPE_ACCELEROMETER_UNCALIBRATED -> wAccU?.add(t, r6(t, v))
                Sensor.TYPE_GYROSCOPE_UNCALIBRATED -> wGyrU?.add(t, r6(t, v))
                Sensor.TYPE_MAGNETIC_FIELD_UNCALIBRATED -> wMagU?.add(t, r6(t, v))
                Sensor.TYPE_GRAVITY -> wGrav?.add(t, r3(t, v))
                Sensor.TYPE_LINEAR_ACCELERATION -> wLin?.add(t, r3(t, v))
                Sensor.TYPE_ROTATION_VECTOR -> wRot?.add(t, rRot(t, v))
                Sensor.TYPE_GAME_ROTATION_VECTOR -> wGame?.add(t, rQuat(t, v))
                Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR -> wGeo?.add(t, rQuat(t, v))
                Sensor.TYPE_PRESSURE -> wBaro?.add(t, r1(t, v))
                Sensor.TYPE_LIGHT -> wLight?.add(t, r1(t, v))
                Sensor.TYPE_PROXIMITY -> wProx?.add(t, r1(t, v))
            }
        }
    }

    private fun r1(t: Long, v: FloatArray): String {
        sb.setLength(0); sb.append(t).append(',').append(v[0]); return sb.toString()
    }
    private fun r3(t: Long, v: FloatArray): String {
        sb.setLength(0); sb.append(t).append(',').append(v[0]).append(',').append(v[1]).append(',').append(v[2])
        return sb.toString()
    }
    private fun r3a(t: Long, v: FloatArray, acc: Int): String {
        sb.setLength(0); sb.append(t).append(',').append(v[0]).append(',').append(v[1]).append(',').append(v[2])
            .append(',').append(acc)
        return sb.toString()
    }
    private fun r6(t: Long, v: FloatArray): String {
        sb.setLength(0); sb.append(t)
        for (i in 0 until 6) sb.append(',').append(if (i < v.size) v[i] else Float.NaN)
        return sb.toString()
    }
    private fun rQuat(t: Long, v: FloatArray): String {
        sb.setLength(0); sb.append(t)
            .append(',').append(v[0]).append(',').append(v[1]).append(',').append(v[2])
            .append(',').append(if (v.size > 3) v[3] else Float.NaN)
        return sb.toString()
    }
    private fun rRot(t: Long, v: FloatArray): String {
        sb.setLength(0); sb.append(t)
            .append(',').append(v[0]).append(',').append(v[1]).append(',').append(v[2])
            .append(',').append(if (v.size > 3) v[3] else Float.NaN)
            .append(',').append(if (v.size > 4) v[4] else Float.NaN)
        return sb.toString()
    }

    private fun registerSensors() {
        val h = sensorHandler ?: return
        for ((stream, type) in SensorInventory.WANTED) {
            if (navMode && !sensorLogging && stream != "acc" && stream != "gyr") continue   // engine needs only acc + gyr
            val s = sensorManager.getDefaultSensor(type)
            if (s == null) { Log.w(TAG, "sensor MISSING for stream $stream (type $type)"); continue }
            val ok = sensorManager.registerListener(sensorListener, s, SAMPLING_US, 0, h)
            if (ok) registered.add(s) else Log.w(TAG, "registerListener refused for $stream")
        }
        Log.i(TAG, "registered ${registered.size} sensors, missing=$missing")
    }

    // ------------------------------------------------------------------ location / GNSS
    private val gsb = StringBuilder(512)   // gnss thread only

    private fun fixRow(loc: Location, provider: String): String {
        gsb.setLength(0)
        gsb.append(loc.elapsedRealtimeNanos).append(',').append(loc.time).append(',')
            .append(loc.latitude).append(',').append(loc.longitude).append(',').append(loc.altitude).append(',')
            .append(if (loc.hasAccuracy()) loc.accuracy else Float.NaN).append(',')
            .append(if (loc.hasVerticalAccuracy()) loc.verticalAccuracyMeters else Float.NaN).append(',')
            .append(if (loc.hasSpeed()) loc.speed else Float.NaN).append(',').append(loc.hasSpeed()).append(',')
            .append(if (loc.hasSpeedAccuracy()) loc.speedAccuracyMetersPerSecond else Float.NaN).append(',')
            .append(if (loc.hasBearing()) loc.bearing else Float.NaN).append(',').append(loc.hasBearing()).append(',')
            .append(if (loc.hasBearingAccuracy()) loc.bearingAccuracyDegrees else Float.NaN).append(',')
            .append(provider).append(',')
            .append(if (loc.hasElapsedRealtimeUncertaintyNanos()) loc.elapsedRealtimeUncertaintyNanos else Double.NaN)
            .append(',')
            .append(if (Build.VERSION.SDK_INT >= 31) loc.isMock else @Suppress("DEPRECATION") loc.isFromMockProvider)
            .append(',').append(satsUsed)
        return gsb.toString()
    }

    private val gpsListener = LocationListener { loc ->
        try {
            lastFixElapsedNs = loc.elapsedRealtimeNanos
            lastFixAcc = if (loc.hasAccuracy()) loc.accuracy else Float.NaN
            wFix?.add(loc.elapsedRealtimeNanos, fixRow(loc, loc.provider ?: "gps"))
            runner?.postFix(loc.elapsedRealtimeNanos, loc.latitude, loc.longitude,
                if (loc.hasAccuracy()) loc.accuracy.toDouble() else Double.NaN,
                if (loc.hasSpeed()) loc.speed.toDouble() else Double.NaN,
                if (loc.hasBearing()) loc.bearing.toDouble() else Double.NaN, satsUsed)
            when (Live.state) {
                State.CALIB -> startAnchor.add(loc)
                State.STOP_CALIB -> endAnchor.add(loc)
                State.RIDE -> polyline.add(loc.latitude, loc.longitude)
                else -> {}
            }
        } catch (t: Throwable) { Log.e(TAG, "gps listener", t) }
    }

    private val fusedListener = LocationListener { loc ->
        try { wFused?.add(loc.elapsedRealtimeNanos, fixRow(loc, "fused")) }
        catch (t: Throwable) { Log.e(TAG, "fused listener", t) }
    }

    private val statusCb = object : GnssStatus.Callback() {
        override fun onSatelliteStatusChanged(status: GnssStatus) {
            try {
                val t = SystemClock.elapsedRealtimeNanos()
                val n = status.satelliteCount
                var used = 0
                var cn0Sum = 0.0
                var cn0N = 0
                val w = wSat
                for (i in 0 until n) {
                    val inFix = status.usedInFix(i)
                    if (inFix) used++
                    val cn0 = status.getCn0DbHz(i)
                    if (inFix && cn0 > 0f) { cn0Sum += cn0; cn0N++ }
                    if (w != null) {
                        gsb.setLength(0)
                        gsb.append(t).append(',')
                            .append(status.getConstellationType(i)).append(',')
                            .append(status.getSvid(i)).append(',')
                            .append(cn0).append(',')
                            .append(if (Build.VERSION.SDK_INT >= 30 && status.hasBasebandCn0DbHz(i))
                                status.getBasebandCn0DbHz(i) else Float.NaN).append(',')
                            .append(status.getElevationDegrees(i)).append(',')
                            .append(status.getAzimuthDegrees(i)).append(',')
                            .append(inFix).append(',')
                            .append(status.hasEphemerisData(i)).append(',')
                            .append(status.hasAlmanacData(i)).append(',')
                            .append(if (status.hasCarrierFrequencyHz(i)) status.getCarrierFrequencyHz(i) else Float.NaN)
                        w.add(0L, gsb.toString())
                    }
                }
                satsUsed = used
                satsVisible = n
                meanCn0 = if (cn0N > 0) cn0Sum / cn0N else Double.NaN
                runner?.postStatus(used, meanCn0)
            } catch (t: Throwable) { Log.e(TAG, "status cb", t) }
        }
    }

    private val measCb = object : GnssMeasurementsEvent.Callback() {
        override fun onGnssMeasurementsReceived(ev: GnssMeasurementsEvent) {
            try {
                nGnssRawEvents.incrementAndGet()
                val c = ev.clock
                val t = if (Build.VERSION.SDK_INT >= 29 && c.hasElapsedRealtimeNanos())
                    c.elapsedRealtimeNanos else SystemClock.elapsedRealtimeNanos()
                val clkPrefix = StringBuilder(200).apply {
                    append(t).append(',')
                        .append(c.timeNanos).append(',')
                        .append(if (c.hasFullBiasNanos()) c.fullBiasNanos else Long.MIN_VALUE).append(',')
                        .append(if (c.hasBiasNanos()) c.biasNanos else Double.NaN).append(',')
                        .append(if (c.hasDriftNanosPerSecond()) c.driftNanosPerSecond else Double.NaN).append(',')
                        .append(c.hardwareClockDiscontinuityCount).append(',')
                        .append(if (c.hasLeapSecond()) c.leapSecond else Int.MIN_VALUE).append(',')
                        .append(if (c.hasTimeUncertaintyNanos()) c.timeUncertaintyNanos else Double.NaN).append(',')
                        .append(if (c.hasBiasUncertaintyNanos()) c.biasUncertaintyNanos else Double.NaN).append(',')
                        .append(if (c.hasDriftUncertaintyNanosPerSecond()) c.driftUncertaintyNanosPerSecond else Double.NaN)
                        .append(',')
                }.toString()

                val w = wRaw ?: return
                for (m in ev.measurements) {
                    gsb.setLength(0)
                    gsb.append(clkPrefix)
                        .append(m.constellationType).append(',')
                        .append(m.svid).append(',')
                        .append(m.cn0DbHz).append(',')
                        .append(if (Build.VERSION.SDK_INT >= 30 && m.hasBasebandCn0DbHz())
                            m.basebandCn0DbHz else Double.NaN).append(',')
                        .append(m.pseudorangeRateMetersPerSecond).append(',')
                        .append(m.pseudorangeRateUncertaintyMetersPerSecond).append(',')
                        .append(m.accumulatedDeltaRangeState).append(',')
                        .append(m.accumulatedDeltaRangeMeters).append(',')
                        .append(m.accumulatedDeltaRangeUncertaintyMeters).append(',')
                        .append(if (m.hasCarrierFrequencyHz()) m.carrierFrequencyHz else Float.NaN).append(',')
                        .append(m.multipathIndicator).append(',')
                        .append(m.receivedSvTimeNanos).append(',')
                        .append(m.state).append(',')
                        .append(agcOf(m)).append(',')
                        .append(if (m.hasCodeType()) m.codeType else "")
                    w.add(0L, gsb.toString())
                }
            } catch (t: Throwable) { Log.e(TAG, "meas cb", t) }
        }

        override fun onStatusChanged(status: Int) {
            Log.i(TAG, "GnssMeasurements status=$status")
        }
    }

    @Suppress("DEPRECATION")
    private fun agcOf(m: android.location.GnssMeasurement): Double {
        if (agcBroken) return Double.NaN
        return try {
            if (m.hasAutomaticGainControlLevelDb()) m.automaticGainControlLevelDb else Double.NaN
        } catch (t: Throwable) { agcBroken = true; Double.NaN }
    }

    private val nmeaListener = OnNmeaMessageListener { message, timestamp ->
        try {
            val t = SystemClock.elapsedRealtimeNanos()
            val clean = message.replace('\n', ' ').replace('\r', ' ').replace("\"", "'")
            wNmea?.add(0L, "$t,$timestamp,\"$clean\"")
        } catch (t: Throwable) { Log.e(TAG, "nmea", t) }
    }

    @SuppressLint("MissingPermission")
    private fun registerLocation() {
        val looper = gnssThread?.looper ?: return
        val exec = Executor { r -> gnssHandler?.post(r) ?: r.run() }

        try {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, 0L, 0f, gpsListener, looper)
        } catch (t: Throwable) { Log.e(TAG, "GPS_PROVIDER register failed", t); Live.lastError = "GPS: ${t.message}" }

        if (Build.VERSION.SDK_INT >= 31) {
            try {
                locationManager.requestLocationUpdates(
                    LocationManager.FUSED_PROVIDER, 1000L, 0f, fusedListener, looper)
            } catch (t: Throwable) { Log.w(TAG, "FUSED_PROVIDER unavailable: ${t.message}") }
        }

        try {
            if (Build.VERSION.SDK_INT >= 30)
                locationManager.registerGnssStatusCallback(exec, statusCb)
            else
                @Suppress("DEPRECATION") locationManager.registerGnssStatusCallback(statusCb, gnssHandler)
        } catch (t: Throwable) { Log.e(TAG, "gnss status register failed", t) }

        try {
            if (Build.VERSION.SDK_INT >= 31) {
                val b = GnssMeasurementRequest.Builder().setFullTracking(true)
                if (Build.VERSION.SDK_INT >= 33) b.setIntervalMillis(0)
                locationManager.registerGnssMeasurementsCallback(b.build(), exec, measCb)
            } else {
                locationManager.registerGnssMeasurementsCallback(exec, measCb)
            }
        } catch (t: Throwable) { Log.w(TAG, "gnss measurements unsupported: ${t.message}") }

        try {
            if (Build.VERSION.SDK_INT >= 30) locationManager.addNmeaListener(exec, nmeaListener)
            else @Suppress("DEPRECATION") locationManager.addNmeaListener(nmeaListener, gnssHandler)
        } catch (t: Throwable) { Log.w(TAG, "nmea unsupported: ${t.message}") }
    }

    private fun unregisterAll() {
        try { sensorManager.unregisterListener(sensorListener) } catch (_: Throwable) {}
        try { locationManager.removeUpdates(gpsListener) } catch (_: Throwable) {}
        try { locationManager.removeUpdates(fusedListener) } catch (_: Throwable) {}
        try { locationManager.unregisterGnssStatusCallback(statusCb) } catch (_: Throwable) {}
        try { locationManager.unregisterGnssMeasurementsCallback(measCb) } catch (_: Throwable) {}
        try { locationManager.removeNmeaListener(nmeaListener) } catch (_: Throwable) {}
        stopThreads()
    }

    // ------------------------------------------------------------------ tickers
    private var tickerRunning = false
    private var pendingTransition: Runnable? = null
    private var stateDeadlineMs = 0L

    /**
     * Schedules a state change on an absolute deadline. Counting down on the 1 Hz stats
     * ticker made the stand-still window up to a second short of the requested 15 s.
     */
    private fun armTransition(seconds: Int, action: () -> Unit) {
        cancelTransition()
        stateDeadlineMs = SystemClock.elapsedRealtime() + seconds * 1000L
        val r = Runnable { pendingTransition = null; action() }
        pendingTransition = r
        main.postDelayed(r, seconds * 1000L)
    }

    private fun cancelTransition() {
        pendingTransition?.let { main.removeCallbacks(it) }
        pendingTransition = null
    }

    private val secondTick = object : Runnable {
        override fun run() {
            if (!tickerRunning) return
            try { onSecond() } catch (t: Throwable) { Log.e(TAG, "tick", t) }
            main.postDelayed(this, 1000)
        }
    }

    private var lastRateTickNs = 0L
    private var secondsSinceStart = 0L

    private fun startTickers() {
        tickerRunning = true
        lastRateTickNs = System.nanoTime()
        secondsSinceStart = 0
        main.postDelayed(secondTick, 1000)
    }

    private fun stopTickers() {
        tickerRunning = false
        main.removeCallbacks(secondTick)
        cancelTransition()
    }

    private fun onSecond() {
        val now = System.nanoTime()
        val dt = (now - lastRateTickNs) / 1e9
        lastRateTickNs = now
        streams?.tickRates(dt)
        secondsSinceStart++
        Live.elapsedSec = secondsSinceStart

        if (secondsSinceStart % 5L == 0L) writeSysLine()
        if (secondsSinceStart % 60L == 0L) writeClockLine()

        // countdown display; the transition itself fires on its own absolute deadline
        if (Live.state == State.CALIB || Live.state == State.STOP_CALIB) {
            val remain = stateDeadlineMs - SystemClock.elapsedRealtime()
            Live.countdown = if (remain <= 0) 0 else ((remain + 999) / 1000).toInt()
        }

        publishLive()
        if (secondsSinceStart % 5L == 0L) updateNotification()
    }

    /** gaps > 50 ms summed over the fixed-cadence streams only — the acceptance number. */
    private fun continuousGaps(st: StreamSet): Long =
        st.all().filter { it.name in CONTINUOUS }.sumOf { it.gapsOver50ms() }

    private fun publishLive() {
        val st = streams ?: return
        val nowNs = SystemClock.elapsedRealtimeNanos()
        val age = if (lastFixElapsedNs == 0L) Double.NaN else (nowNs - lastFixElapsedNs) / 1e9

        Live.accHz = st["acc"]?.hz ?: 0.0
        Live.gyrHz = st["gyr"]?.hz ?: 0.0
        Live.magHz = st["mag"]?.hz ?: 0.0
        Live.gnssAgeS = age
        Live.gnssAccM = lastFixAcc.toDouble()
        Live.satsUsed = satsUsed
        Live.satsVisible = satsVisible
        Live.meanCn0 = meanCn0
        Live.dropped = st.totalDropped()
        Live.gaps = continuousGaps(st)

        // The visible band is only ~441 dp tall and the STOP button owns a third of it,
        // so this has to say everything in five monospace lines.
        val b = StringBuilder(320)
        val acc = st["acc"]; val gyr = st["gyr"]; val mag = st["mag"]
        val imuOk = (acc?.hz ?: 0.0) >= 100 && (gyr?.hz ?: 0.0) >= 100 && (mag?.hz ?: 0.0) >= 50
        b.append(String.format("acc%4.0f gyr%4.0f mag%3.0f %s\n",
            acc?.hz ?: 0.0, gyr?.hz ?: 0.0, mag?.hz ?: 0.0, if (imuOk) "OK" else "!!"))
        b.append(String.format("sats %2d/%-2d  acc_h %5s %s\n",
            satsUsed, satsVisible,
            if (lastFixAcc.isNaN()) "--" else String.format("%.1f", lastFixAcc),
            if (!lastFixAcc.isNaN() && lastFixAcc < 10f && satsUsed >= 8) "OK" else "  "))
        b.append(String.format("age %4ss  cn0 %4s  raw %d\n",
            if (age.isNaN()) "--" else String.format("%.1f", age),
            if (meanCn0.isNaN()) "--" else String.format("%.0f", meanCn0),
            nGnssRawEvents.get()))
        b.append(String.format("gaps %d  drop %d  rows %s\n",
            continuousGaps(st), st.totalDropped(), human(st.totalRows())))
        val bat = batteryInfo()
        b.append(String.format("bat %d%% %.0fC %s  free %s\n",
            bat.pct, bat.tempC, thermalName(), humanBytes(freeBytes())))
        if (Live.outage) b.append("*** GNSS DENIAL ON ***\n")
        if (missing.isNotEmpty()) b.append("missing ").append(missing.joinToString(",")).append('\n')
        Live.statsText = b.toString()
    }

    // ------------------------------------------------------------------ side files
    private fun writeEvent(type: String, text: String) {
        val t = SystemClock.elapsedRealtimeNanos()
        val wall = System.currentTimeMillis()
        val clean = text.replace('\n', ' ').replace("\"", "'")
        wEvents?.add(0L, "$t,$wall,$type,\"$clean\"")
        runner?.postEvent(t, type)
        Log.i(TAG, "EVENT $type $clean")
    }

    private fun writeClockLine() {
        val t = SystemClock.elapsedRealtimeNanos()
        val wall = System.currentTimeMillis()
        wClock?.add(0L, "$t,$wall")
    }

    private data class Batt(val pct: Int, val charging: Boolean, val tempC: Double)

    private fun batteryInfo(): Batt {
        return try {
            val i = registerReceiver(null as BroadcastReceiver?, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if (i == null) Batt(-1, false, Double.NaN) else {
                val level = i.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                val scale = i.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
                val status = i.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
                val temp = i.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
                Batt(
                    if (level >= 0 && scale > 0) level * 100 / scale else -1,
                    status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL,
                    if (temp == Int.MIN_VALUE) Double.NaN else temp / 10.0
                )
            }
        } catch (t: Throwable) { Batt(-1, false, Double.NaN) }
    }

    private fun thermalStatus(): Int =
        try { powerManager.currentThermalStatus } catch (t: Throwable) { -1 }

    private fun thermalName(): String = when (thermalStatus()) {
        0 -> "NONE"; 1 -> "LIGHT"; 2 -> "MOD"; 3 -> "SEVERE"
        4 -> "CRIT"; 5 -> "EMERG"; 6 -> "SHUTDOWN"; else -> "?"
    }

    private fun rotation(): Int = try {
        val dm = getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
        dm.getDisplay(Display.DEFAULT_DISPLAY)?.rotation ?: -1
    } catch (t: Throwable) { -1 }

    private fun freeBytes(): Long = try {
        val d = sessionDir ?: getExternalFilesDir(null)
        val s = StatFs(d!!.absolutePath)
        s.availableBlocksLong * s.blockSizeLong
    } catch (t: Throwable) { -1L }

    private fun writeSysLine() {
        val t = SystemClock.elapsedRealtimeNanos()
        val wall = System.currentTimeMillis()
        val b = batteryInfo()
        wSys?.add(0L, "$t,$wall,${b.pct},${b.charging},${b.tempC},${thermalStatus()},${rotation()},${freeBytes()}")
    }

    // ------------------------------------------------------------------ session.json
    private fun deviceJson(): JSONObject = JSONObject().apply {
        put("manufacturer", Build.MANUFACTURER)
        put("brand", Build.BRAND)
        put("model", Build.MODEL)
        put("device", Build.DEVICE)
        put("hardware", Build.HARDWARE)
        put("android_release", Build.VERSION.RELEASE)
        put("sdk_int", Build.VERSION.SDK_INT)
        put("build_display_id", Build.DISPLAY)
        put("fingerprint", Build.FINGERPRINT)
        put("one_ui_version", try {
            val c = Class.forName("android.os.SemSystemProperties")
            c.getMethod("get", String::class.java).invoke(null, "ro.build.version.oneui") as? String ?: ""
        } catch (t: Throwable) {
            try { System.getProperty("ro.build.version.oneui") ?: "" } catch (t2: Throwable) { "" }
        })
    }

    private fun appVersion(): String = try {
        packageManager.getPackageInfo(packageName, 0).versionName ?: "?"
    } catch (t: Throwable) { "?" }

    private fun baseSessionJson(): JSONObject = JSONObject().apply {
        put("session_uuid", sessionUuid)
        put("session_name", Live.sessionName)
        put("route_id", meta["route_id"])
        put("direction", meta["direction"])
        put("run_no", meta["run_no"]?.toIntOrNull() ?: -1)
        put("purpose", meta["purpose"])
        put("rider_id", meta["rider_id"])
        put("variation", meta["variation"])
        put("notes", meta["notes"])
        put("vehicle_id", "roadeo_1")
        put("mount_id", "downtube_tape_v1")
        put("mount_photo_ref", "")
        put("app_version", appVersion())
        put("device", deviceJson())
        put("requested_sampling_period_us", SAMPLING_US)
        put("requested_max_report_latency_us", 0)
        put("wall_clock_at_start_ms", sessionStartWallMs)
        put("elapsed_realtime_ns_at_start", sessionStartElapsedNs)
        put("start_time_iso",
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.US).format(Date(sessionStartWallMs)))
        put("timezone", java.util.TimeZone.getDefault().id)
        put("calib_seconds", CALIB_SEC)
        put("stop_calib_seconds", STOP_CALIB_SEC)
        put("sensor_inventory_requested", SensorInventory.requestedList(sensorManager))
        put("sensor_inventory_all", SensorInventory.fullList(sensorManager))
        put("missing_streams", JSONArray(missing))
        put("nav_mode", navMode)
        put("sensor_logging", sensorLogging)
        meta["speed_model"]?.let { put("speed_model", it) }
    }

    private fun writeSessionJsonAtStart(d: File) {
        try {
            val o = baseSessionJson()
            o.put("status", "RUNNING")
            File(d, "session.json").writeText(o.toString(2))
        } catch (t: Throwable) { Log.e(TAG, "session.json write failed", t) }
    }

    /** Patches session.json with achieved rates + anchors and returns the on-screen summary. */
    private fun patchSessionJson(d: File, aborted: Boolean): String {
        val o = baseSessionJson()
        val endWall = System.currentTimeMillis()
        o.put("status", if (aborted) "ABORTED" else "COMPLETE")
        o.put("wall_clock_at_end_ms", endWall)
        o.put("elapsed_realtime_ns_at_end", SystemClock.elapsedRealtimeNanos())
        o.put("duration_s", (endWall - sessionStartWallMs) / 1000.0)

        val rates = JSONObject()
        val st = streams
        if (st != null) {
            for (s in st.all()) {
                rates.put(s.name, JSONObject().apply {
                    put("rows", s.rows.get())
                    put("dropped", s.dropped.get())
                    put("dt_samples", s.dtSamples())
                    put("median_dt_ms", s.medianDtMs().nan())
                    put("p99_dt_ms", s.p99DtMs().nan())
                    put("max_dt_ms", s.maxDtMs().nan())
                    put("gaps_over_50ms", s.gapsOver50ms())
                    put("continuous", s.name in CONTINUOUS)
                    put("median_hz", s.medianDtMs().let { if (it.isNaN() || it <= 0) JSONObject.NULL else 1000.0 / it })
                    put("bytes", if (s.file.exists()) s.file.length() else 0L)
                })
            }
        }
        o.put("streams", rates)
        o.put("dt_histogram_resolution_us", 25)
        o.put("continuous_streams", JSONArray(CONTINUOUS.toList()))
        o.put("gaps_over_50ms_continuous", streams?.let { continuousGaps(it) } ?: 0L)

        val sa = startAnchor.toJson()
        val ea = endAnchor.toJson()
        val dist = Anchor.distance(startAnchor, endAnchor)
        o.put("start_anchor", sa)
        o.put("end_anchor", ea)
        o.put("anchor_distance_m", dist.nan())
        o.put("polyline_length_m", polyline.meters)
        o.put("n_gnss_raw_events", nGnssRawEvents.get())

        File(d, "session.json").writeText(o.toString(2))

        // ----- human summary -----
        // Verdict first: the phone is taped to the down tube, so the rider must be able to
        // decide "keep or redo" from the top of the dialog without scrolling.
        val b = StringBuilder()
        val accHz = hzOfNum(st, "acc"); val gyrHz = hzOfNum(st, "gyr"); val magHz = hzOfNum(st, "mag")
        val gaps = st?.let { continuousGaps(it) } ?: 0L
        val drops = st?.totalDropped() ?: 0L
        val nA = startAnchor.count(); val nB = endAnchor.count()
        val pass = accHz >= 100 && gyrHz >= 100 && magHz >= 50 &&
                gaps == 0L && drops == 0L && nA >= 5 && nB >= 5 && !aborted
        b.append(if (pass) ">>>  RUN OK  <<<\n" else ">>>  REDO THIS RUN  <<<\n")
        b.append(Live.sessionName).append("\n\n")
        b.append(String.format("acc %.0f  gyr %.0f  mag %.0f Hz %s\n",
            accHz, gyrHz, magHz, if (accHz >= 100 && gyrHz >= 100 && magHz >= 50) "ok" else "LOW"))
        b.append(String.format("gaps %d   dropped %d %s\n", gaps, drops,
            if (gaps == 0L && drops == 0L) "ok" else "BAD"))
        b.append(String.format("anchors %d / %d fixes %s\n", nA, nB,
            if (nA >= 5 && nB >= 5) "ok" else "THIN"))
        b.append("anchor dist ").append(fmt(dist)).append(" m\n")
        b.append("path ").append(String.format("%.0f", polyline.meters)).append(" m\n\n")
        b.append(String.format("%-11s %8s %8s %8s %6s\n", "stream", "rows", "med_ms", "p99_ms", "gaps"))
        if (st != null) {
            for (s in st.all()) {
                if (s.rows.get() == 0L && s.name !in setOf("acc", "gyr", "mag", "gnss_fix")) continue
                b.append(String.format("%-11s %8d %8s %8s %6s\n",
                    s.name, s.rows.get(), fmt(s.medianDtMs()), fmt(s.p99DtMs()),
                    if (s.name in CONTINUOUS) s.gapsOver50ms().toString() else "-"))
            }
        }
        b.append("\nstart anchor: ").append(anchorLine(startAnchor)).append("\n")
        b.append("end anchor:   ").append(anchorLine(endAnchor)).append("\n")
        b.append("gnss raw ev:  ").append(nGnssRawEvents.get()).append("\n")
        if (missing.isNotEmpty()) b.append("MISSING: ").append(missing.joinToString(",")).append("\n")
        if (aborted) b.append("\n*** ABORTED ***\n")
        return b.toString()
    }

    private fun hzOfNum(st: StreamSet?, n: String): Double {
        val m = st?.get(n)?.medianDtMs() ?: return 0.0
        return if (m.isNaN() || m <= 0) 0.0 else 1000.0 / m
    }

    private fun anchorLine(a: Anchor): String =
        if (a.count() == 0) "none (no fix < 15 m)"
        else String.format("%.6f, %.6f  n=%d std=%.1fm", a.lat(), a.lon(), a.count(), a.stdMeters())

    private fun fmt(d: Double): String = if (d.isNaN()) "--" else String.format("%.2f", d)
    private fun Double.nan(): Any = if (this.isNaN()) JSONObject.NULL else this

    private fun human(n: Long): String = when {
        n >= 1_000_000 -> String.format("%.1fM", n / 1e6)
        n >= 1_000 -> String.format("%.0fk", n / 1e3)
        else -> n.toString()
    }

    private fun humanBytes(n: Long): String = when {
        n < 0 -> "?"
        n >= 1L shl 30 -> String.format("%.0fG", n / (1L shl 30).toDouble())
        n >= 1L shl 20 -> String.format("%.0fM", n / (1L shl 20).toDouble())
        else -> "$n"
    }

    // ------------------------------------------------------------------ wake lock + notification
    @SuppressLint("WakelockTimeout")
    private fun acquireWakeLock() {
        try {
            val wl = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "IDRLogger::session")
            wl.setReferenceCounted(false)
            wl.acquire()
            wakeLock = wl
        } catch (t: Throwable) { Log.e(TAG, "wakelock", t) }
    }

    private fun releaseWakeLock() {
        try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Throwable) {}
        wakeLock = null
    }

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        val ch = NotificationChannel(CHANNEL, "IDR logging", NotificationManager.IMPORTANCE_LOW)
        ch.setShowBadge(false)
        ch.enableVibration(false)
        nm.createNotificationChannel(ch)
    }

    private fun buildNotification(): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, NavActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val text = if (Live.running)
            String.format("%s  acc %.0fHz  sats %d  acc_h %s",
                Live.state.name, Live.accHz, satsUsed,
                if (lastFixAcc.isNaN()) "--" else String.format("%.0fm", lastFixAcc))
        else "ready"
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle(if (Live.sessionName.isEmpty()) "IDR Logger" else Live.sessionName)
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(pi)
            .build()
    }

    private var isForeground = false

    private fun ensureForeground() {
        if (isForeground) return
        try {
            ServiceCompat.startForeground(
                this, NOTIF_ID, buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            )
            isForeground = true
        } catch (t: Throwable) {
            Log.e(TAG, "startForeground failed", t)
            Live.lastError = "foreground: ${t.message}"
        }
    }

    private fun updateNotification() {
        if (!isForeground) return
        try {
            getSystemService(NotificationManager::class.java).notify(NOTIF_ID, buildNotification())
        } catch (_: Throwable) {}
    }
}
