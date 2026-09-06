package com.snu.idrlogger

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.snu.idrlogger.ui.AppPrefs
import com.snu.idrlogger.ui.FieldTestScreen
import com.snu.idrlogger.ui.IdrTheme
import com.snu.idrlogger.ui.LoggerTab
import com.snu.idrlogger.ui.RideController
import com.snu.idrlogger.ui.RideDeps
import com.snu.idrlogger.ui.RideScreen
import com.snu.idrlogger.ui.SettingsScreen
import com.snu.idrlogger.ui.SummaryScreen
import com.snu.idrlogger.ui.SyncSignal
import com.snu.idrlogger.ui.Tok
import kotlinx.coroutines.delay

enum class Screen { RIDE, LOGGER, SETTINGS, FIELD_TEST, SUMMARY }

class NavActivity : ComponentActivity() {
    private lateinit var prefs: AppPrefs
    private lateinit var controller: RideController
    private val sync = SyncSignal()

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        prefs = AppPrefs(this); controller = RideController(this, prefs)
        requestPermissions()
        setContent { IdrTheme { App() } }
    }

    /** Debug-only: `adb shell am broadcast -a com.snu.idrlogger.PREFS --es satellite true --es puck TEARDROP --es gallery true ...` */
    private val prefsReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(c: android.content.Context?, i: Intent?) {
            if (!BuildConfig.DEBUG || i == null) return
            i.getStringExtra("satellite")?.let { prefs.satellite = it == "true" }
            i.getStringExtra("gallery")?.let { prefs.puckGallery = it == "true" }
            i.getStringExtra("puck")?.let { prefs.puckVariant = it }
            i.getStringExtra("units")?.let { prefs.units = it }
            i.getStringExtra("scenario")?.let { prefs.scenarioKind = it }
            i.getStringExtra("band_from")?.toDoubleOrNull()?.let { prefs.bandFrom = it }
            i.getStringExtra("band_to")?.toDoubleOrNull()?.let { prefs.bandTo = it }
            i.getStringExtra("timer_start")?.toDoubleOrNull()?.let { prefs.timerStart = it }
            i.getStringExtra("timer_hold")?.toDoubleOrNull()?.let { prefs.timerHold = it }
            i.getStringExtra("model")?.let { prefs.model = it }
            i.getStringExtra("reduce_motion")?.let { prefs.reduceMotion = it == "true" }
            i.getStringExtra("screen")?.let { screenRequest.value = it }
            prefs.save()
        }
    }
    val screenRequest = androidx.compose.runtime.mutableStateOf("")

    override fun onStart() {
        super.onStart()
        if (BuildConfig.DEBUG) ContextCompat.registerReceiver(this, prefsReceiver, android.content.IntentFilter("com.snu.idrlogger.PREFS"), ContextCompat.RECEIVER_EXPORTED)
    }

    override fun onStop() { if (BuildConfig.DEBUG) try { unregisterReceiver(prefsReceiver) } catch (_: Throwable) {}; super.onStop() }

    override fun onDestroy() { sync.release(); super.onDestroy() }

    private fun requestPermissions() {
        val need = ArrayList<String>()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) { need.add(Manifest.permission.ACCESS_FINE_LOCATION); need.add(Manifest.permission.ACCESS_COARSE_LOCATION) }
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) need.add(Manifest.permission.POST_NOTIFICATIONS)
        if (need.isNotEmpty()) ActivityCompat.requestPermissions(this, need.toTypedArray(), 42)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 42 && permissions.contains(Manifest.permission.ACCESS_FINE_LOCATION)) {
            val pm = getSystemService(POWER_SERVICE) as android.os.PowerManager
            if (!pm.isIgnoringBatteryOptimizations(packageName)) try { startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName"))) } catch (_: Throwable) {}
        }
    }

    @Composable
    private fun App() {
        var screen by remember { mutableStateOf(Screen.RIDE) }
        var riding by remember { mutableStateOf(LogService.Live.running) }
        LaunchedEffect(Unit) { while (true) { riding = LogService.Live.running || LogService.Live.state == LogService.State.FINISHING; delay(300) } }
        val deps = remember { RideDeps(prefs, controller, sync, onOpenSummary = { screen = Screen.SUMMARY }) }
        val req by screenRequest
        LaunchedEffect(req) { if (req.isNotEmpty()) { runCatching { Screen.valueOf(req) }.getOrNull()?.let { screen = it }; screenRequest.value = "" } }
        BackHandler(enabled = screen != Screen.RIDE) { screen = if (screen == Screen.FIELD_TEST) Screen.SETTINGS else Screen.RIDE }
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f).fillMaxWidth()) {
                // the map stays alive underneath every screen (no re-init on tab switches); other screens draw over it
                RideScreen(deps, Modifier.fillMaxSize())
                when (screen) {
                    Screen.LOGGER -> LoggerTab(Modifier.fillMaxSize())
                    Screen.SETTINGS -> SettingsScreen(prefs, onFieldTest = { screen = Screen.FIELD_TEST })
                    Screen.FIELD_TEST -> FieldTestScreen(prefs, controller, onBack = { screen = Screen.SETTINGS })
                    Screen.SUMMARY -> SummaryScreen(prefs, onDone = { screen = Screen.RIDE })
                    Screen.RIDE -> {}
                }
            }
            if (!riding && screen != Screen.SUMMARY) {
                NavigationBar(containerColor = Tok.Card, tonalElevation = 0.dp) {
                    val colors = NavigationBarItemDefaults.colors(selectedIconColor = Tok.Locked, selectedTextColor = Tok.Text, indicatorColor = Tok.Raised, unselectedIconColor = Tok.TextDim, unselectedTextColor = Tok.TextDim)
                    NavigationBarItem(selected = screen == Screen.RIDE, onClick = { screen = Screen.RIDE }, icon = { Icon(Glyphs.ride, "Ride") }, label = { Text("Ride") }, colors = colors)
                    NavigationBarItem(selected = screen == Screen.LOGGER, onClick = { screen = Screen.LOGGER }, icon = { Icon(Glyphs.logger, "Logger") }, label = { Text("Logger") }, colors = colors)
                    NavigationBarItem(selected = screen == Screen.SETTINGS || screen == Screen.FIELD_TEST, onClick = { screen = Screen.SETTINGS }, icon = { Icon(Glyphs.settings, "Settings") }, label = { Text("Settings") }, colors = colors)
                }
            }
        }
    }
}

/** Icons drawn as vectors (no emoji, no glyph fonts). */
object Glyphs {
    val ride: ImageVector by lazy {
        ImageVector.Builder("ride", 24.dp, 24.dp, 24f, 24f).apply {
            path(fill = SolidColor(Color.White)) { moveTo(12f, 2f); lineTo(19f, 21f); lineTo(12f, 17f); lineTo(5f, 21f); close() }
        }.build()
    }
    val logger: ImageVector by lazy {
        ImageVector.Builder("logger", 24.dp, 24.dp, 24f, 24f).apply {
            path(fill = SolidColor(Color.White)) { moveTo(4f, 4f); lineTo(20f, 4f); lineTo(20f, 7f); lineTo(4f, 7f); close(); moveTo(4f, 10f); lineTo(20f, 10f); lineTo(20f, 13f); lineTo(4f, 13f); close(); moveTo(4f, 16f); lineTo(14f, 16f); lineTo(14f, 19f); lineTo(4f, 19f); close() }
        }.build()
    }
    val settings: ImageVector by lazy {
        ImageVector.Builder("settings", 24.dp, 24.dp, 24f, 24f).apply {
            path(fill = SolidColor(Color.White)) { moveTo(3f, 6f); lineTo(21f, 6f); lineTo(21f, 8f); lineTo(3f, 8f); close(); moveTo(3f, 11f); lineTo(21f, 11f); lineTo(21f, 13f); lineTo(3f, 13f); close(); moveTo(3f, 16f); lineTo(21f, 16f); lineTo(21f, 18f); lineTo(3f, 18f); close(); moveTo(7f, 4f); lineTo(10f, 4f); lineTo(10f, 10f); lineTo(7f, 10f); close(); moveTo(14f, 9f); lineTo(17f, 9f); lineTo(17f, 15f); lineTo(14f, 15f); close(); moveTo(9f, 14f); lineTo(12f, 14f); lineTo(12f, 20f); lineTo(9f, 20f); close() }
        }.build()
    }
}
