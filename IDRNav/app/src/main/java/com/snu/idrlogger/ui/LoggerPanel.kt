package com.snu.idrlogger.ui

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.widget.AppCompatButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.snu.idrlogger.InventoryActivity
import com.snu.idrlogger.LogService
import com.snu.idrlogger.R
import java.io.File

/** The Logger tab: the field-proven IDR Logger screen hosted as a View inside Compose, behaviour unchanged. */
@Composable
fun LoggerTab(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val activity = ctx as Activity
    val panel = remember { LoggerPanel(activity) }
    DisposableEffect(Unit) { panel.start(); onDispose { panel.stop() } }
    AndroidView(factory = { panel.view }, modifier = modifier)
}

/**
 * The old MainActivity, verbatim in behaviour, as a controller over an inflated activity_main.xml. Dialogs still clamp to the
 * middle band (the layout was built for the taped down-tube mount and is kept as is for data collection).
 */
class LoggerPanel(private val activity: Activity) {
    val view: View = LayoutInflater.from(activity).inflate(R.layout.activity_main, null)
    private val band: View = view.findViewById(R.id.band)
    private val idlePanel: View = view.findViewById(R.id.idlePanel)
    private val ridePanel: View = view.findViewById(R.id.ridePanel)
    private val setupPanel: View = view.findViewById(R.id.setupPanel)
    private val btnDirAB: AppCompatButton = view.findViewById(R.id.btnDirAB)
    private val btnDirBA: AppCompatButton = view.findViewById(R.id.btnDirBA)
    private val btnRunMinus: AppCompatButton = view.findViewById(R.id.btnRunMinus)
    private val btnRunPlus: AppCompatButton = view.findViewById(R.id.btnRunPlus)
    private val btnStart: AppCompatButton = view.findViewById(R.id.btnStart)
    private val btnStop: AppCompatButton = view.findViewById(R.id.btnStop)
    private val btnNote: AppCompatButton = view.findViewById(R.id.btnNote)
    private val btnOutage: AppCompatButton = view.findViewById(R.id.btnOutage)
    private val btnSetup: AppCompatButton = view.findViewById(R.id.btnSetup)
    private val btnSensors: AppCompatButton = view.findViewById(R.id.btnSensors)
    private val btnSessions: AppCompatButton = view.findViewById(R.id.btnSessions)
    private val btnSetupDone: AppCompatButton = view.findViewById(R.id.btnSetupDone)
    private val btnPurpose: AppCompatButton = view.findViewById(R.id.btnPurpose)
    private val btnVariation: AppCompatButton = view.findViewById(R.id.btnVariation)
    private val btnPerms: AppCompatButton = view.findViewById(R.id.btnPerms)
    private val etRoute: EditText = view.findViewById(R.id.etRoute)
    private val etRider: EditText = view.findViewById(R.id.etRider)
    private val tvDirLabel: TextView = view.findViewById(R.id.tvDirLabel)
    private val tvRunNo: TextView = view.findViewById(R.id.tvRunNo)
    private val tvPerms: TextView = view.findViewById(R.id.tvPerms)
    private val tvState: TextView = view.findViewById(R.id.tvState)
    private val tvTimer: TextView = view.findViewById(R.id.tvTimer)
    private val tvCountdown: TextView = view.findViewById(R.id.tvCountdown)
    private val tvStats: TextView = view.findViewById(R.id.tvStats)

    private var direction = "AB"; private var runNo = 1; private var purposeIx = 0; private var variationIx = 0
    private var inSetup = false; private var summaryShown = false; private var permTick = 0
    private val ui = Handler(Looper.getMainLooper())
    private val prefs by lazy { activity.getSharedPreferences("idr", Context.MODE_PRIVATE) }
    private val purposes = arrayOf("pilot", "train", "val", "test", "demo")
    private val variations = arrayOf("normal", "slow", "brisk", "coast_brake", "mid_stop", "standing_pedal", "stationary")
    private val notePresets = arrayOf("swerve", "obstacle", "unplanned stop", "big bump", "pedestrian", "wind gust", "wrong turn", "mount shifted", "other")
    private companion object { const val HOLD_MS = 800L }

    init {
        etRoute.setText(prefs.getString("route", "SNU_R2")); etRider.setText(prefs.getString("rider", "rider_1"))
        runNo = prefs.getInt("run_no", 1); direction = prefs.getString("dir", "AB") ?: "AB"
        purposeIx = purposes.indexOf(prefs.getString("purpose", "pilot")).coerceAtLeast(0); variationIx = variations.indexOf(prefs.getString("variation", "normal")).coerceAtLeast(0)
        btnDirAB.setOnClickListener { direction = "AB"; paintDirection(); saveSetup() }
        btnDirBA.setOnClickListener { direction = "BA"; paintDirection(); saveSetup() }
        btnRunMinus.setOnClickListener { runNo = (runNo - 1).coerceAtLeast(1); paintRun(); saveSetup() }
        btnRunPlus.setOnClickListener { runNo += 1; paintRun(); saveSetup() }
        btnStart.setOnClickListener { onStart_() }
        btnNote.setOnClickListener { onNote() }
        btnSetup.setOnClickListener { inSetup = true; render() }
        btnSetupDone.setOnClickListener { inSetup = false; saveSetup(); hideKeyboard(); render() }
        btnSensors.setOnClickListener { activity.startActivity(Intent(activity, InventoryActivity::class.java)) }
        btnSessions.setOnClickListener { showSessions() }
        btnPerms.setOnClickListener { requestEverything() }
        btnPurpose.setOnClickListener { purposeIx = (purposeIx + 1) % purposes.size; paintCycles(); saveSetup() }
        btnVariation.setOnClickListener { variationIx = (variationIx + 1) % variations.size; paintCycles(); saveSetup() }
        holdToConfirm(btnStop, "HOLD TO STOP", "RELEASE = STOP") { onStop_() }
        holdToConfirm(btnOutage, null, null) { onOutage() }
        paintDirection(); paintRun(); paintCycles(); updatePermLine()
    }

    fun start() { ui.post(poll) }
    fun stop() { ui.removeCallbacks(poll); saveSetup() }

    @SuppressLint("ClickableViewAccessibility")
    private fun holdToConfirm(b: AppCompatButton, idleText: String?, heldText: String?, action: () -> Unit) {
        var fired = false
        val fire = Runnable { fired = true; b.text = heldText ?: b.text; action() }
        b.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { fired = false; v.alpha = 0.6f; if (heldText != null) b.text = heldText; ui.postDelayed(fire, HOLD_MS); true }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { ui.removeCallbacks(fire); v.alpha = 1f; if (!fired && idleText != null) { b.text = idleText; toast("hold it for a moment") }; true }
                else -> false
            }
        }
    }

    private val poll = object : Runnable { override fun run() { render(); ui.postDelayed(this, 250) } }

    private fun render() {
        val L = LogService.Live
        val active = L.running || L.state == LogService.State.FINISHING
        idlePanel.visibility = if (!active && !inSetup) View.VISIBLE else View.GONE
        setupPanel.visibility = if (!active && inSetup) View.VISIBLE else View.GONE
        ridePanel.visibility = if (active) View.VISIBLE else View.GONE
        if (active) {
            tvState.text = L.state.name
            tvState.setTextColor(when (L.state) { LogService.State.RIDE -> Color.parseColor("#00E676"); LogService.State.CALIB, LogService.State.STOP_CALIB -> Color.parseColor("#FFC400"); LogService.State.FINISHING -> Color.parseColor("#40C4FF"); else -> Color.WHITE })
            tvTimer.text = "${L.elapsedSec / 60}:${String.format("%02d", L.elapsedSec % 60)}"
            val counting = L.state == LogService.State.CALIB || L.state == LogService.State.STOP_CALIB
            tvCountdown.visibility = if (counting) View.VISIBLE else View.GONE
            tvStats.visibility = if (counting) View.GONE else View.VISIBLE
            if (counting) tvCountdown.text = "STAND\nSTILL\n${L.countdown}" else tvStats.text = L.statsText
            btnOutage.text = if (L.outage) "DENIAL: ON" else "DENIAL: OFF"
            btnOutage.setTextColor(if (L.outage) Color.parseColor("#FF5252") else Color.WHITE)
        } else if (!inSetup && ++permTick % 4 == 0) updatePermLine()
        L.lastError?.let { L.lastError = null; Toast.makeText(activity, it, Toast.LENGTH_LONG).show() }
        val s = L.summary
        if (s != null && !summaryShown && !isNavSession(L.sessionName)) { summaryShown = true; L.summary = null; bumpRunNo(); showSummary(s) }
        if (s == null && !active) summaryShown = false
    }

    private fun isNavSession(name: String) = name.contains("_NAV_")

    private fun onStart_() {
        if (!hasLocation()) { toast("Grant Location first"); requestEverything(); return }
        if (Build.VERSION.SDK_INT >= 33 && !hasNotif()) { toast("Grant Notifications"); requestEverything(); return }
        if (!gpsEnabled()) { toast("Turn Location ON"); activity.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)); return }
        saveSetup(); summaryShown = false; btnStop.text = "HOLD TO STOP"
        val i = Intent(activity, LogService::class.java).apply {
            action = LogService.ACTION_START
            putExtra(LogService.EX_ROUTE, etRoute.text.toString().trim().ifEmpty { "SNU_R2" }); putExtra(LogService.EX_DIR, direction); putExtra(LogService.EX_RUN, runNo)
            putExtra(LogService.EX_PURPOSE, purposes[purposeIx]); putExtra(LogService.EX_RIDER, etRider.text.toString().trim().ifEmpty { "rider_1" })
            putExtra(LogService.EX_NOTES, ""); putExtra(LogService.EX_VARIATION, variations[variationIx]); putExtra(LogService.EX_NAV, false)
        }
        ContextCompat.startForegroundService(activity, i)
    }

    private fun onStop_() { if (LogService.Live.state == LogService.State.STOP_CALIB) { toast("already stopping"); return }; send(Intent(activity, LogService::class.java).apply { action = LogService.ACTION_STOP }) }

    private fun onNote() {
        val d = AlertDialog.Builder(activity).setTitle("Mark a note").setItems(notePresets) { _, which ->
            send(Intent(activity, LogService::class.java).apply { action = LogService.ACTION_NOTE; putExtra(LogService.EX_TEXT, notePresets[which]) }); toast("noted: ${notePresets[which]}")
        }.setNegativeButton("Cancel", null).create()
        d.show(); clampToBand(d)
    }

    private fun onOutage() { val next = !LogService.Live.outage; send(Intent(activity, LogService::class.java).apply { action = LogService.ACTION_OUTAGE; putExtra(LogService.EX_ON, next) }) }

    private fun send(i: Intent) { if (LogService.Live.running) activity.startService(i) else ContextCompat.startForegroundService(activity, i) }

    private fun clampToBand(d: Dialog) {
        d.window?.let { w -> val dm = activity.resources.displayMetrics; val lp = w.attributes; lp.height = (dm.heightPixels * 0.48f).toInt(); lp.width = (dm.widthPixels * 0.94f).toInt(); lp.gravity = Gravity.CENTER; w.attributes = lp }
        if (d is AlertDialog) for (which in intArrayOf(AlertDialog.BUTTON_POSITIVE, AlertDialog.BUTTON_NEGATIVE, AlertDialog.BUTTON_NEUTRAL)) d.getButton(which)?.apply { setTextColor(Color.WHITE); textSize = 19f; setTypeface(typeface, Typeface.BOLD) }
    }

    private fun showSummary(text: String) {
        val tv = TextView(activity).apply { setTextColor(Color.WHITE); textSize = 12f; typeface = Typeface.MONOSPACE; setPadding(24, 12, 24, 12); this.text = text; setTextIsSelectable(true) }
        val sv = android.widget.ScrollView(activity).apply { addView(tv) }
        val d = AlertDialog.Builder(activity).setTitle("Summary").setView(sv).setPositiveButton("OK", null).setCancelable(false).create()
        d.show(); clampToBand(d)
    }

    private fun sessionsRoot(): File = File(activity.getExternalFilesDir(null), "sessions")

    private fun showSessions() {
        val items = (sessionsRoot().listFiles() ?: emptyArray()).filter { it.isDirectory }.sortedByDescending { it.name }
        if (items.isEmpty()) { toast("no sessions yet"); return }
        val labels = items.map { "${it.name}\n   ${humanBytes(dirSize(it))}" }.toTypedArray()
        val d = AlertDialog.Builder(activity).setTitle("Sessions (${items.size})").setItems(labels) { _, which -> sessionActions(items[which]) }.setNegativeButton("Close", null).create()
        d.show(); clampToBand(d)
    }

    private fun sessionActions(f: File) {
        val d = AlertDialog.Builder(activity).setTitle(f.name).setItems(arrayOf("Zip", "Zip + share", "Delete")) { _, which -> when (which) { 0 -> zipAsync(f, false); 1 -> zipAsync(f, true); 2 -> confirmDelete(f) } }.setNegativeButton("Cancel", null).create()
        d.show(); clampToBand(d)
    }

    private fun confirmDelete(f: File) {
        val d = AlertDialog.Builder(activity).setTitle("Delete ${f.name}?").setMessage("${humanBytes(dirSize(f))} removed permanently.")
            .setPositiveButton("DELETE") { _, _ -> f.deleteRecursively(); File(sessionsRoot(), "${f.name}.zip").delete(); toast("deleted") }.setNegativeButton("Cancel", null).create()
        d.show(); clampToBand(d)
    }

    private fun zipAsync(f: File, share: Boolean) {
        val dlg = AlertDialog.Builder(activity).setTitle("Zipping…").setMessage(f.name).setCancelable(false).create(); dlg.show(); clampToBand(dlg)
        Thread {
            var out: File? = null; var err: String? = null
            try { out = zipDir(f) } catch (t: Throwable) { err = t.message }
            ui.post { dlg.dismiss(); if (out == null) { toast("zip failed: $err"); return@post }; toast("${out.name}  ${humanBytes(out.length())}"); if (share) shareFile(activity, out) }
        }.start()
    }

    private fun dirSize(d: File): Long = (d.listFiles() ?: emptyArray()).sumOf { if (it.isDirectory) dirSize(it) else it.length() }
    private fun humanBytes(n: Long): String = when { n >= 1L shl 30 -> String.format("%.2f GB", n / (1L shl 30).toDouble()); n >= 1L shl 20 -> String.format("%.1f MB", n / (1L shl 20).toDouble()); n >= 1L shl 10 -> String.format("%.0f kB", n / 1024.0); else -> "$n B" }

    private fun hasLocation() = ContextCompat.checkSelfPermission(activity, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
    private fun hasNotif() = Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(activity, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    private fun gpsEnabled(): Boolean = try { (activity.getSystemService(Context.LOCATION_SERVICE) as LocationManager).isProviderEnabled(LocationManager.GPS_PROVIDER) } catch (t: Throwable) { false }
    private fun batteryUnrestricted(): Boolean = try { (activity.getSystemService(Context.POWER_SERVICE) as PowerManager).isIgnoringBatteryOptimizations(activity.packageName) } catch (t: Throwable) { false }

    fun requestEverything() {
        val need = ArrayList<String>()
        if (!hasLocation()) { need.add(Manifest.permission.ACCESS_FINE_LOCATION); need.add(Manifest.permission.ACCESS_COARSE_LOCATION) }
        if (Build.VERSION.SDK_INT >= 33 && !hasNotif()) need.add(Manifest.permission.POST_NOTIFICATIONS)
        if (need.isNotEmpty()) { ActivityCompat.requestPermissions(activity, need.toTypedArray(), 42); return }
        if (!batteryUnrestricted()) askBattery() else if (!gpsEnabled()) activity.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
        updatePermLine()
    }

    @SuppressLint("BatteryLife")
    private fun askBattery() {
        try { activity.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${activity.packageName}"))) }
        catch (t: Throwable) { try { activity.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) } catch (_: Throwable) { toast("set Battery → Unrestricted manually") } }
    }

    fun onPermissionsResult() { updatePermLine(); if (hasLocation() && !batteryUnrestricted()) askBattery() }

    private fun updatePermLine() {
        val loc = hasLocation(); val nt = hasNotif(); val gps = gpsEnabled(); val bat = batteryUnrestricted(); val allOk = loc && nt && gps && bat
        tvPerms.text = if (allOk) "perms OK  ·  keep MIC toggle ON" else "CHECK: " + listOfNotNull(if (!loc) "location" else null, if (!nt) "notif" else null, if (!gps) "gps-off" else null, if (!bat) "battery" else null).joinToString(" ") + "  → SETUP"
        tvPerms.setTextColor(if (allOk) Color.parseColor("#00E676") else Color.parseColor("#FF5252"))
    }

    private fun paintDirection() {
        val ab = direction == "AB"; val dim = Color.parseColor("#78909C")
        btnDirAB.setBackgroundResource(if (ab) R.drawable.dir_on else R.drawable.dir_off); btnDirBA.setBackgroundResource(if (ab) R.drawable.dir_off else R.drawable.dir_on)
        btnDirAB.setTextColor(if (ab) Color.BLACK else dim); btnDirBA.setTextColor(if (ab) dim else Color.BLACK)
        btnDirAB.text = if (ab) "● A → B" else "A → B"; btnDirBA.text = if (ab) "B → A" else "● B → A"; tvDirLabel.text = if (ab) "DIRECTION:  A → B" else "DIRECTION:  B → A"
    }
    private fun paintRun() { tvRunNo.text = "RUN $runNo" }
    private fun paintCycles() { btnPurpose.text = "PURPOSE: ${purposes[purposeIx]}"; btnVariation.text = "VARIATION: ${variations[variationIx]}" }
    private fun saveSetup() { prefs.edit().putString("route", etRoute.text.toString()).putString("rider", etRider.text.toString()).putString("dir", direction).putString("purpose", purposes[purposeIx]).putString("variation", variations[variationIx]).putInt("run_no", runNo).apply() }
    private fun bumpRunNo() { runNo += 1; direction = if (direction == "AB") "BA" else "AB"; paintRun(); paintDirection(); saveSetup() }
    private fun hideKeyboard() { try { (activity.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).hideSoftInputFromWindow(band.windowToken, 0) } catch (_: Throwable) {} }
    private fun toast(s: String) { Toast.makeText(activity, s, Toast.LENGTH_SHORT).apply { setGravity(Gravity.CENTER, 0, 0) }.show() }
}
