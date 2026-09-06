package com.snu.idrlogger.ui

import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.media.AudioManager
import android.media.ToneGenerator
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.snu.idrlogger.LogService
import java.io.File

/** Persistent settings (SharedPreferences "idr_nav"); Compose state mirrors so screens recompose on change. */
class AppPrefs(ctx: Context) {
    private val p: SharedPreferences = ctx.getSharedPreferences("idr_nav", Context.MODE_PRIVATE)
    var units by mutableStateOf(p.getString("units", "kmh")!!)                 // kmh | ms
    var satellite by mutableStateOf(p.getBoolean("satellite", false))
    var rider by mutableStateOf(p.getString("rider", "rider_1")!!)
    var syncFlash by mutableStateOf(p.getBoolean("sync_flash", true))
    var insetBottomDp by mutableStateOf(p.getInt("inset_bottom", 0))
    var reduceMotion by mutableStateOf(p.getBoolean("reduce_motion", false))
    // field test
    var scenarioKind by mutableStateOf(p.getString("scenario", "none")!!)     // none | band | timer | manual
    var bandFrom by mutableStateOf(p.getFloat("band_from", 200f).toDouble())
    var bandTo by mutableStateOf(p.getFloat("band_to", 0f).toDouble())         // <= 0 = to the stop
    var timerStart by mutableStateOf(p.getFloat("timer_start", 40f).toDouble())
    var timerHold by mutableStateOf(p.getFloat("timer_hold", 90f).toDouble())
    var forcedCorridor by mutableStateOf(p.getString("forced_corridor", "")!!)
    var model by mutableStateOf(p.getString("model", "litert")!!)               // litert | kotlin
    var revealOn by mutableStateOf(p.getBoolean("reveal", true))
    var engineSheetOn by mutableStateOf(p.getBoolean("engine_sheet", true))
    var loggingOn by mutableStateOf(p.getBoolean("logging", true))
    var replaySpeed by mutableStateOf(p.getFloat("replay_speed", 0f).toDouble())
    var puckVariant by mutableStateOf(p.getString("puck", "BLADE")!!)
    var puckGallery by mutableStateOf(false)
    var runNo by mutableStateOf(p.getInt("nav_run", 1))

    fun save() {
        p.edit().putString("units", units).putBoolean("satellite", satellite).putString("rider", rider).putBoolean("sync_flash", syncFlash)
            .putInt("inset_bottom", insetBottomDp).putBoolean("reduce_motion", reduceMotion)
            .putString("scenario", scenarioKind).putFloat("band_from", bandFrom.toFloat()).putFloat("band_to", bandTo.toFloat())
            .putFloat("timer_start", timerStart.toFloat()).putFloat("timer_hold", timerHold.toFloat()).putString("forced_corridor", forcedCorridor)
            .putString("model", model).putBoolean("reveal", revealOn).putBoolean("engine_sheet", engineSheetOn).putBoolean("logging", loggingOn)
            .putFloat("replay_speed", replaySpeed.toFloat()).putString("puck", puckVariant).putInt("nav_run", runNo).apply()
    }

    val scenarioArmed: Boolean get() = scenarioKind != "none"
}

/** Talks to the service. */
class RideController(private val ctx: Context, private val prefs: AppPrefs) {
    private fun intent(action: String) = Intent(ctx, LogService::class.java).apply { this.action = action }
    private fun send(i: Intent) { if (LogService.Live.running) ctx.startService(i) else ContextCompat.startForegroundService(ctx, i) }

    private fun putScenario(i: Intent) {
        i.putExtra(LogService.EX_SCENARIO, prefs.scenarioKind)
        i.putExtra(LogService.EX_BAND_FROM, prefs.bandFrom); i.putExtra(LogService.EX_BAND_TO, prefs.bandTo)
        i.putExtra(LogService.EX_TIMER_START, prefs.timerStart); i.putExtra(LogService.EX_TIMER_HOLD, prefs.timerHold)
        i.putExtra(LogService.EX_MODEL, prefs.model); i.putExtra(LogService.EX_FORCED_CORRIDOR, prefs.forcedCorridor)
    }

    fun startRide() {
        val i = intent(LogService.ACTION_START)
        i.putExtra(LogService.EX_NAV, true); i.putExtra(LogService.EX_LOGGING, prefs.loggingOn)
        i.putExtra(LogService.EX_RUN, prefs.runNo); i.putExtra(LogService.EX_RIDER, prefs.rider); i.putExtra(LogService.EX_PURPOSE, "demo")
        putScenario(i)
        ContextCompat.startForegroundService(ctx, i)
    }

    fun stopRide() { send(intent(LogService.ACTION_STOP)) }
    fun abort() { send(intent(LogService.ACTION_ABORT)) }
    fun manualDenial(on: Boolean) { send(intent(LogService.ACTION_MANUAL_DENIAL).putExtra(LogService.EX_ON, on)) }

    fun startReplay(dir: File, speed: Double) {
        val i = intent(LogService.ACTION_REPLAY)
        i.putExtra(LogService.EX_REPLAY_DIR, dir.absolutePath); i.putExtra(LogService.EX_REPLAY_SPEED, speed)
        putScenario(i)
        ContextCompat.startForegroundService(ctx, i)
    }

    fun stopReplay() { ContextCompat.startForegroundService(ctx, intent(LogService.ACTION_REPLAY_STOP)) }

    fun sessionsRoot(): File = File(ctx.getExternalFilesDir(null), "sessions")
    fun replayRoot(): File = File(ctx.getExternalFilesDir(null), "replay")
    fun replayOutRoot(): File = File(ctx.getExternalFilesDir(null), "replay_out")
}

/** The SYNC signal for the video: three tones (and the UI flashes three 120 ms white frames) at START, band entry and band exit. */
class SyncSignal {
    private var tone: ToneGenerator? = try { ToneGenerator(AudioManager.STREAM_MUSIC, 90) } catch (t: Throwable) { null }
    fun beeps() {
        val tg = tone ?: return
        Thread {
            for (i in 0 until 3) { try { tg.startTone(ToneGenerator.TONE_PROP_BEEP2, 120) } catch (_: Throwable) {}; try { Thread.sleep(240) } catch (_: InterruptedException) {} }
        }.start()
    }
    fun release() { try { tone?.release() } catch (_: Throwable) {}; tone = null }
}
