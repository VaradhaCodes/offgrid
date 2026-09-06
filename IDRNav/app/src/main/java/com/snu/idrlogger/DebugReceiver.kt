package com.snu.idrlogger

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Test entry point for adb (debug builds only): forwards the extras of a `com.snu.idrlogger.DEBUG` broadcast to LogService with
 * the action named in the `cmd` extra (REPLAY, REPLAY_STOP, START, STOP, ABORT, MANUAL_DENIAL). Example:
 *   adb shell am broadcast -a com.snu.idrlogger.DEBUG -n com.snu.idrlogger/.DebugReceiver --es cmd REPLAY --es replay_dir <dir> --ed replay_speed 0 ...
 */
class DebugReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!BuildConfig.DEBUG) return
        val cmd = intent.getStringExtra("cmd") ?: return
        if (cmd == "MODELBENCH") { Thread { Log.i("IDR", "MODELBENCH " + com.snu.idrlogger.ui.ModelBench.run(context).replace('\n', ' ')) }.start(); return }
        if (cmd == "SCREENSHOT_PREP") { Log.i("IDR", "noop"); return }
        val i = Intent(context, LogService::class.java)
        i.action = "com.snu.idrlogger.$cmd"
        intent.extras?.let { i.putExtras(it) }
        i.removeExtra("cmd")
        if (cmd == "START") i.putExtra(LogService.EX_NAV, intent.getBooleanExtra(LogService.EX_NAV, true))
        Log.i("IDR", "debug broadcast -> ${i.action} ${i.extras?.keySet()?.joinToString()}")
        ContextCompat.startForegroundService(context, i)
    }
}
