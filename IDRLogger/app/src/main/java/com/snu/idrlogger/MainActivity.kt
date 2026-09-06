package com.snu.idrlogger

import android.Manifest
import android.annotation.SuppressLint
import android.app.Dialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.AppCompatButton
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.view.WindowCompat
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * Single screen, driven entirely from the middle 50% of the display.
 *
 * The phone is taped to the down tube across its top and bottom quarters, so every
 * control and every dialog has to land inside that band. Two consequences run through
 * this file: no popup that anchors outside the band (spinners are replaced by
 * tap-to-cycle buttons, the run number by +/- buttons), and every dialog is clamped by
 * [clampToBand] to 48% of the screen height, centred.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var band: View
    private lateinit var idlePanel: View
    private lateinit var ridePanel: View
    private lateinit var setupPanel: View

    private lateinit var btnDirAB: AppCompatButton
    private lateinit var btnDirBA: AppCompatButton
    private lateinit var btnRunMinus: AppCompatButton
    private lateinit var btnRunPlus: AppCompatButton
    private lateinit var btnStart: AppCompatButton
    private lateinit var btnStop: AppCompatButton
    private lateinit var btnNote: AppCompatButton
    private lateinit var btnOutage: AppCompatButton
    private lateinit var btnSetup: AppCompatButton
    private lateinit var btnSensors: AppCompatButton
    private lateinit var btnSessions: AppCompatButton
    private lateinit var btnSetupDone: AppCompatButton
    private lateinit var btnPurpose: AppCompatButton
    private lateinit var btnVariation: AppCompatButton
    private lateinit var btnPerms: AppCompatButton

    private lateinit var etRoute: EditText
    private lateinit var etRider: EditText
    private lateinit var tvDirLabel: TextView
    private lateinit var tvRunNo: TextView
    private lateinit var tvPerms: TextView
    private lateinit var tvState: TextView
    private lateinit var tvTimer: TextView
    private lateinit var tvCountdown: TextView
    private lateinit var tvStats: TextView

    private var direction = "AB"
    private var runNo = 1
    private var purposeIx = 0
    private var variationIx = 0
    private var inSetup = false
    private var summaryShown = false
    private var permTick = 0

    private val ui = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("idr", Context.MODE_PRIVATE) }

    private val purposes = arrayOf("pilot", "train", "val", "test", "demo")
    private val variations = arrayOf(
        "normal", "slow", "brisk", "coast_brake", "mid_stop", "standing_pedal", "stationary"
    )
    private val notePresets = arrayOf(
        "swerve", "obstacle", "unplanned stop", "big bump", "pedestrian",
        "wind gust", "wrong turn", "mount shifted", "other"
    )

    private companion object {
        const val HOLD_MS = 800L      // deliberate hold to stop; a knee brush must not end a run
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Draw behind the system bars so the 1:2:1 weight split maps onto physical
        // screen quarters rather than quarters of an inset content area.
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.activity_main)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        band = findViewById(R.id.band)
        idlePanel = findViewById(R.id.idlePanel)
        ridePanel = findViewById(R.id.ridePanel)
        setupPanel = findViewById(R.id.setupPanel)

        btnDirAB = findViewById(R.id.btnDirAB)
        btnDirBA = findViewById(R.id.btnDirBA)
        btnRunMinus = findViewById(R.id.btnRunMinus)
        btnRunPlus = findViewById(R.id.btnRunPlus)
        btnStart = findViewById(R.id.btnStart)
        btnStop = findViewById(R.id.btnStop)
        btnNote = findViewById(R.id.btnNote)
        btnOutage = findViewById(R.id.btnOutage)
        btnSetup = findViewById(R.id.btnSetup)
        btnSensors = findViewById(R.id.btnSensors)
        btnSessions = findViewById(R.id.btnSessions)
        btnSetupDone = findViewById(R.id.btnSetupDone)
        btnPurpose = findViewById(R.id.btnPurpose)
        btnVariation = findViewById(R.id.btnVariation)
        btnPerms = findViewById(R.id.btnPerms)

        etRoute = findViewById(R.id.etRoute)
        etRider = findViewById(R.id.etRider)
        tvDirLabel = findViewById(R.id.tvDirLabel)
        tvRunNo = findViewById(R.id.tvRunNo)
        tvPerms = findViewById(R.id.tvPerms)
        tvState = findViewById(R.id.tvState)
        tvTimer = findViewById(R.id.tvTimer)
        tvCountdown = findViewById(R.id.tvCountdown)
        tvStats = findViewById(R.id.tvStats)

        etRoute.setText(prefs.getString("route", "SNU_AJB"))
        etRider.setText(prefs.getString("rider", "rider_1"))
        runNo = prefs.getInt("run_no", 1)
        direction = prefs.getString("dir", "AB") ?: "AB"
        purposeIx = purposes.indexOf(prefs.getString("purpose", "pilot")).coerceAtLeast(0)
        variationIx = variations.indexOf(prefs.getString("variation", "normal")).coerceAtLeast(0)

        btnDirAB.setOnClickListener { direction = "AB"; paintDirection(); saveSetup() }
        btnDirBA.setOnClickListener { direction = "BA"; paintDirection(); saveSetup() }
        btnRunMinus.setOnClickListener { runNo = (runNo - 1).coerceAtLeast(1); paintRun(); saveSetup() }
        btnRunPlus.setOnClickListener { runNo += 1; paintRun(); saveSetup() }
        btnStart.setOnClickListener { onStart_() }
        btnNote.setOnClickListener { onNote() }
        btnSetup.setOnClickListener { inSetup = true; render() }
        btnSetupDone.setOnClickListener { inSetup = false; saveSetup(); hideKeyboard(); render() }
        btnSensors.setOnClickListener { startActivity(Intent(this, InventoryActivity::class.java)) }
        btnSessions.setOnClickListener { showSessions() }
        btnPerms.setOnClickListener { requestEverything() }
        btnPurpose.setOnClickListener {
            purposeIx = (purposeIx + 1) % purposes.size; paintCycles(); saveSetup()
        }
        btnVariation.setOnClickListener {
            variationIx = (variationIx + 1) % variations.size; paintCycles(); saveSetup()
        }

        // A stray knee on the down tube must not end a run: STOP and the outage toggle
        // both need a deliberate hold.
        holdToConfirm(btnStop, "HOLD TO STOP", "RELEASE = STOP") { onStop_() }
        holdToConfirm(btnOutage, null, null) { onOutage() }

        paintDirection(); paintRun(); paintCycles()
        requestEverything()
    }

    override fun onResume() { super.onResume(); ui.post(poll) }
    override fun onPause() { super.onPause(); ui.removeCallbacks(poll); saveSetup() }

    // ------------------------------------------------------------------ hold-to-confirm
    @SuppressLint("ClickableViewAccessibility")
    private fun holdToConfirm(
        b: AppCompatButton, idleText: String?, heldText: String?, action: () -> Unit
    ) {
        var fired = false
        val fire = Runnable {
            fired = true
            b.text = heldText ?: b.text
            action()
        }
        b.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    fired = false
                    v.alpha = 0.6f
                    if (heldText != null) b.text = heldText
                    ui.postDelayed(fire, HOLD_MS)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    ui.removeCallbacks(fire)
                    v.alpha = 1f
                    if (!fired && idleText != null) {
                        b.text = idleText
                        toast("hold it for a moment")
                    }
                    true
                }
                else -> false
            }
        }
    }

    // ------------------------------------------------------------------ UI loop
    private val poll = object : Runnable {
        override fun run() { render(); ui.postDelayed(this, 250) }
    }

    private fun render() {
        val L = LogService.Live
        val active = L.running || L.state == LogService.State.FINISHING

        idlePanel.visibility = if (!active && !inSetup) View.VISIBLE else View.GONE
        setupPanel.visibility = if (!active && inSetup) View.VISIBLE else View.GONE
        ridePanel.visibility = if (active) View.VISIBLE else View.GONE

        if (active) {
            tvState.text = L.state.name
            tvState.setTextColor(
                when (L.state) {
                    LogService.State.RIDE -> Color.parseColor("#00E676")
                    LogService.State.CALIB, LogService.State.STOP_CALIB -> Color.parseColor("#FFC400")
                    LogService.State.FINISHING -> Color.parseColor("#40C4FF")
                    else -> Color.WHITE
                }
            )
            tvTimer.text = "${L.elapsedSec / 60}:${String.format("%02d", L.elapsedSec % 60)}"

            val counting = L.state == LogService.State.CALIB || L.state == LogService.State.STOP_CALIB
            tvCountdown.visibility = if (counting) View.VISIBLE else View.GONE
            tvStats.visibility = if (counting) View.GONE else View.VISIBLE
            if (counting) tvCountdown.text = "STAND\nSTILL\n${L.countdown}"
            else tvStats.text = L.statsText

            btnOutage.text = if (L.outage) "DENIAL: ON" else "DENIAL: OFF"
            btnOutage.setTextColor(if (L.outage) Color.parseColor("#FF5252") else Color.WHITE)
        } else if (!inSetup && ++permTick % 4 == 0) {
            updatePermLine()
        }

        L.lastError?.let { L.lastError = null; Toast.makeText(this, it, Toast.LENGTH_LONG).show() }

        val s = L.summary
        if (s != null && !summaryShown) {
            summaryShown = true
            L.summary = null
            bumpRunNo()
            showSummary(s)
        }
        if (s == null && !active) summaryShown = false
    }

    // ------------------------------------------------------------------ actions
    private fun onStart_() {
        if (!hasLocation()) { toast("Grant Location first"); requestEverything(); return }
        if (Build.VERSION.SDK_INT >= 33 && !hasNotif()) { toast("Grant Notifications"); requestEverything(); return }
        if (!gpsEnabled()) {
            toast("Turn Location ON")
            startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)); return
        }
        saveSetup()
        summaryShown = false
        btnStop.text = "HOLD TO STOP"
        val i = Intent(this, LogService::class.java).apply {
            action = LogService.ACTION_START
            putExtra(LogService.EX_ROUTE, etRoute.text.toString().trim().ifEmpty { "SNU_AJB" })
            putExtra(LogService.EX_DIR, direction)
            putExtra(LogService.EX_RUN, runNo)
            putExtra(LogService.EX_PURPOSE, purposes[purposeIx])
            putExtra(LogService.EX_RIDER, etRider.text.toString().trim().ifEmpty { "rider_1" })
            putExtra(LogService.EX_NOTES, "")
            putExtra(LogService.EX_VARIATION, variations[variationIx])
        }
        ContextCompat.startForegroundService(this, i)
    }

    private fun onStop_() {
        if (LogService.Live.state == LogService.State.STOP_CALIB) { toast("already stopping"); return }
        send(Intent(this, LogService::class.java).apply { action = LogService.ACTION_STOP })
    }

    /** Preset tags only — a keyboard would open over the dead bottom quarter. */
    private fun onNote() {
        val d = AlertDialog.Builder(this)
            .setTitle("Mark a note")
            .setItems(notePresets) { _, which ->
                send(Intent(this, LogService::class.java).apply {
                    action = LogService.ACTION_NOTE
                    putExtra(LogService.EX_TEXT, notePresets[which])
                })
                toast("noted: ${notePresets[which]}")
            }
            .setNegativeButton("Cancel", null)
            .create()
        d.show(); clampToBand(d)
    }

    private fun onOutage() {
        val next = !LogService.Live.outage
        send(Intent(this, LogService::class.java).apply {
            action = LogService.ACTION_OUTAGE
            putExtra(LogService.EX_ON, next)
        })
    }

    private fun send(i: Intent) {
        if (LogService.Live.running) startService(i) else ContextCompat.startForegroundService(this, i)
    }

    /** Every dialog must sit inside the untaped middle band. */
    private fun clampToBand(d: Dialog) {
        d.window?.let { w ->
            val dm = resources.displayMetrics
            val lp = w.attributes
            lp.height = (dm.heightPixels * 0.48f).toInt()
            lp.width = (dm.widthPixels * 0.94f).toInt()
            lp.gravity = Gravity.CENTER
            w.attributes = lp
        }
        if (d is AlertDialog) {
            for (which in intArrayOf(
                AlertDialog.BUTTON_POSITIVE, AlertDialog.BUTTON_NEGATIVE, AlertDialog.BUTTON_NEUTRAL
            )) d.getButton(which)?.apply {
                setTextColor(Color.WHITE)
                textSize = 19f
                setTypeface(typeface, Typeface.BOLD)
            }
        }
    }

    private fun showSummary(text: String) {
        val tv = TextView(this).apply {
            setTextColor(Color.WHITE); textSize = 12f
            typeface = Typeface.MONOSPACE
            setPadding(24, 12, 24, 12)
            this.text = text
            setTextIsSelectable(true)
        }
        val sv = android.widget.ScrollView(this).apply { addView(tv) }
        val d = AlertDialog.Builder(this)
            .setTitle("Summary")
            .setView(sv)
            .setPositiveButton("OK", null)
            .setCancelable(false)
            .create()
        d.show(); clampToBand(d)
    }

    // ------------------------------------------------------------------ sessions
    private fun sessionsRoot(): File = File(getExternalFilesDir(null), "sessions")

    private fun showSessions() {
        val items = (sessionsRoot().listFiles() ?: emptyArray())
            .filter { it.isDirectory }.sortedByDescending { it.name }
        if (items.isEmpty()) { toast("no sessions yet"); return }
        val labels = items.map { "${it.name}\n   ${humanBytes(dirSize(it))}" }.toTypedArray()
        val d = AlertDialog.Builder(this)
            .setTitle("Sessions (${items.size})")
            .setItems(labels) { _, which -> sessionActions(items[which]) }
            .setNegativeButton("Close", null)
            .create()
        d.show(); clampToBand(d)
    }

    private fun sessionActions(f: File) {
        val d = AlertDialog.Builder(this)
            .setTitle(f.name)
            .setItems(arrayOf("Zip", "Zip + share", "Delete")) { _, which ->
                when (which) {
                    0 -> zipAsync(f, share = false)
                    1 -> zipAsync(f, share = true)
                    2 -> confirmDelete(f)
                }
            }
            .setNegativeButton("Cancel", null)
            .create()
        d.show(); clampToBand(d)
    }

    private fun confirmDelete(f: File) {
        val d = AlertDialog.Builder(this)
            .setTitle("Delete ${f.name}?")
            .setMessage("${humanBytes(dirSize(f))} removed permanently.")
            .setPositiveButton("DELETE") { _, _ ->
                f.deleteRecursively(); File(sessionsRoot(), "${f.name}.zip").delete(); toast("deleted")
            }
            .setNegativeButton("Cancel", null)
            .create()
        d.show(); clampToBand(d)
    }

    private fun zipAsync(f: File, share: Boolean) {
        val dlg = AlertDialog.Builder(this)
            .setTitle("Zipping…").setMessage(f.name).setCancelable(false).create()
        dlg.show(); clampToBand(dlg)
        Thread {
            var out: File? = null
            var err: String? = null
            try { out = zipDir(f) } catch (t: Throwable) { err = t.message }
            ui.post {
                dlg.dismiss()
                if (out == null) { toast("zip failed: $err"); return@post }
                toast("${out.name}  ${humanBytes(out.length())}")
                if (share) shareFile(out)
            }
        }.start()
    }

    private fun zipDir(d: File): File {
        val out = File(sessionsRoot(), "${d.name}.zip")
        ZipOutputStream(out.outputStream().buffered(1 shl 16)).use { zos ->
            for (f in d.listFiles() ?: emptyArray()) {
                if (!f.isFile) continue
                zos.putNextEntry(ZipEntry("${d.name}/${f.name}"))
                f.inputStream().buffered(1 shl 16).use { it.copyTo(zos) }
                zos.closeEntry()
            }
        }
        return out
    }

    private fun shareFile(f: File) {
        try {
            val uri: Uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", f)
            startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                type = "application/zip"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }, "Share ${f.name}"))
        } catch (t: Throwable) { toast("share failed: ${t.message}") }
    }

    private fun dirSize(d: File): Long =
        (d.listFiles() ?: emptyArray()).sumOf { if (it.isDirectory) dirSize(it) else it.length() }

    private fun humanBytes(n: Long): String = when {
        n >= 1L shl 30 -> String.format("%.2f GB", n / (1L shl 30).toDouble())
        n >= 1L shl 20 -> String.format("%.1f MB", n / (1L shl 20).toDouble())
        n >= 1L shl 10 -> String.format("%.0f kB", n / 1024.0)
        else -> "$n B"
    }

    // ------------------------------------------------------------------ permissions
    private fun hasLocation() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun hasNotif() = Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(
        this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun gpsEnabled(): Boolean = try {
        (getSystemService(Context.LOCATION_SERVICE) as LocationManager)
            .isProviderEnabled(LocationManager.GPS_PROVIDER)
    } catch (t: Throwable) { false }

    private fun batteryUnrestricted(): Boolean = try {
        (getSystemService(Context.POWER_SERVICE) as PowerManager).isIgnoringBatteryOptimizations(packageName)
    } catch (t: Throwable) { false }

    private fun requestEverything() {
        val need = ArrayList<String>()
        if (!hasLocation()) {
            need.add(Manifest.permission.ACCESS_FINE_LOCATION)
            need.add(Manifest.permission.ACCESS_COARSE_LOCATION)
        }
        if (Build.VERSION.SDK_INT >= 33 && !hasNotif()) need.add(Manifest.permission.POST_NOTIFICATIONS)
        if (need.isNotEmpty()) { ActivityCompat.requestPermissions(this, need.toTypedArray(), 42); return }
        if (!batteryUnrestricted()) askBattery()
        else if (!gpsEnabled()) startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
        updatePermLine()
    }

    @SuppressLint("BatteryLife")
    private fun askBattery() {
        try {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:$packageName")))
        } catch (t: Throwable) {
            try { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
            catch (_: Throwable) { toast("set Battery → Unrestricted manually") }
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        updatePermLine()
        if (requestCode == 42 && hasLocation() && !batteryUnrestricted()) askBattery()
    }

    /** One compact line: the band has no room for a six-line checklist. */
    private fun updatePermLine() {
        val loc = hasLocation(); val nt = hasNotif(); val gps = gpsEnabled(); val bat = batteryUnrestricted()
        val allOk = loc && nt && gps && bat
        tvPerms.text = if (allOk) "perms OK  ·  keep MIC toggle ON"
        else "CHECK: " + listOfNotNull(
            if (!loc) "location" else null,
            if (!nt) "notif" else null,
            if (!gps) "gps-off" else null,
            if (!bat) "battery" else null
        ).joinToString(" ") + "  → SETUP"
        tvPerms.setTextColor(if (allOk) Color.parseColor("#00E676") else Color.parseColor("#FF5252"))
    }

    // ------------------------------------------------------------------ painting
    private fun paintDirection() {
        val ab = direction == "AB"
        val dim = Color.parseColor("#78909C")
        btnDirAB.setBackgroundResource(if (ab) R.drawable.dir_on else R.drawable.dir_off)
        btnDirBA.setBackgroundResource(if (ab) R.drawable.dir_off else R.drawable.dir_on)
        btnDirAB.setTextColor(if (ab) Color.BLACK else dim)
        btnDirBA.setTextColor(if (ab) dim else Color.BLACK)
        btnDirAB.text = if (ab) "● A → B" else "A → B"
        btnDirBA.text = if (ab) "B → A" else "● B → A"
        tvDirLabel.text = if (ab) "DIRECTION:  A → B" else "DIRECTION:  B → A"
    }

    private fun paintRun() { tvRunNo.text = "RUN $runNo" }

    private fun paintCycles() {
        btnPurpose.text = "PURPOSE: ${purposes[purposeIx]}"
        btnVariation.text = "VARIATION: ${variations[variationIx]}"
    }

    private fun saveSetup() {
        prefs.edit()
            .putString("route", etRoute.text.toString())
            .putString("rider", etRider.text.toString())
            .putString("dir", direction)
            .putString("purpose", purposes[purposeIx])
            .putString("variation", variations[variationIx])
            .putInt("run_no", runNo)
            .apply()
    }

    private fun bumpRunNo() {
        runNo += 1
        direction = if (direction == "AB") "BA" else "AB"
        paintRun(); paintDirection(); saveSetup()
    }

    private fun hideKeyboard() {
        try {
            val imm = getSystemService(Context.INPUT_METHOD_SERVICE)
                    as android.view.inputmethod.InputMethodManager
            imm.hideSoftInputFromWindow(band.windowToken, 0)
        } catch (_: Throwable) {}
    }

    private fun toast(s: String) {
        val t = Toast.makeText(this, s, Toast.LENGTH_SHORT)
        t.setGravity(Gravity.CENTER, 0, 0)   // toasts default to the taped bottom edge
        t.show()
    }
}
