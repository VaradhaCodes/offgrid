package com.snu.idrlogger.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.snu.idr.engine.EngineState
import com.snu.idr.engine.Mode
import com.snu.idrlogger.LogService
import com.snu.idrlogger.service.NavLive
import java.util.Locale

private fun f(v: Double, d: Int = 1): String = if (v.isNaN()) "–" else String.format(Locale.US, "%.${d}f", v)

@Composable
private fun Row2(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = Tok.TextDim, modifier = Modifier.padding(end = 12.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Tok.Text, textAlign = androidx.compose.ui.text.style.TextAlign.End, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun Section(title: String) {
    Spacer(Modifier.height(10.dp)); Text(title, style = MaterialTheme.typography.titleSmall, color = Tok.Locked); HorizontalDivider(Modifier.padding(vertical = 4.dp), color = Tok.Outline)
}

/** The engine sheet (handoff §5.1): everything the engineers need, in the engine's own words. */
@Composable
fun EngineSheetContent(s: EngineState?, modelName: String, replayLabel: String?) {
    val live = LogService.Live
    Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 28.dp).verticalScroll(rememberScrollState())) {
        Text("Engine", style = MaterialTheme.typography.headlineSmall, color = Tok.Text)
        if (s == null) { Text("No engine state yet.", color = Tok.TextDim); return }
        val posLine = when {
            s.corridorId != null -> "corridor · ${s.corridorName} (learned)" + (if (s.dir != 0) " · " + (if (s.dir > 0) "A→B" else "B→A") else "")
            s.fusionMode == "general" -> "general · campus graph" + (if (s.matched) " · map-matched (display)" else "")
            else -> "waiting for the first fix"
        }
        Row2("Positioning", posLine)
        Row2("Mode", when (s.mode) { Mode.GNSS_INS -> "GNSS + INS"; Mode.INERTIAL -> "inertial (GNSS withheld)"; Mode.RECOVERING -> "recovering" } + (if (s.sim) " · simulated" else "") + (if (s.realOutage) " · real outage" else ""))
        Row2("Fix source", "GNSS chipset (GPS_PROVIDER)")
        Row2("Satellites · C/N0", "${s.sats} used · ${f(s.cn0, 0)} dB-Hz · acc ${f(s.gnssAcc)} m · age ${f(s.gnssAgeS)} s")
        Row2("Readiness", if (s.armed) "armed" else "not armed: ${s.armedMissing.ifEmpty { "–" }}")
        if (replayLabel != null) Row2("Replay", replayLabel)

        Section("Alignment")
        Row2("Pitch · roll", "${f(s.pitchDeg)}° · ${f(s.rollDeg)}°")
        Row2("Forward axis ψ", "${f(s.psiDeg)}° (${s.psiSource})" + (if (!s.swayRatio.isNaN()) " · sway ratio ${f(s.swayRatio)}" else ""))
        Row2("Gyro bias", "${f(s.biasDps[0], 3)} ${f(s.biasDps[1], 3)} ${f(s.biasDps[2], 3)} °/s")
        Row2("Gravity", "${f(s.gMag, 3)} m/s² · ${s.gravityBlocks} ride blocks" + (if (!s.movedAtS.isNaN()) " · moved at ${f(s.movedAtS, 0)} s" else ""))
        Row2("Stand", if (s.standQuiet) "quiet" else "not quiet → bias state on, trust after 60 s")

        Section("Heading")
        Row2("ψ · σψ", "${f(s.headingDeg)}° · ${f(s.headingSigmaDeg, 2)}°" + (if (!s.headingInit) " · not initialised" else ""))

        Section("Speed model")
        Row2("Model", modelName.ifEmpty { s.speedSource })
        Row2("μ · σ", "${f(s.vModel, 2)} m/s · ${f(s.sigmaModel, 2)}" + (if (s.stop) " · stop rule" else ""))
        Row2("Vibration · gyro RMS", "${f(s.vib, 2)} m/s² · ${f(s.gyrRms, 3)} rad/s")
        Row2("Filter v · σpos", "${f(s.v, 2)} m/s · ${f(s.sigmaPos, 2)} m")
        if (s.corridorId != null) Row2("s · d", "${f(s.s)} m · ${f(s.d)} m")

        Section("Timing")
        Row2("Tick · model (last)", "${f(s.tickMs, 2)} ms · ${f(s.modelMs, 2)} ms")
        Row2("Tick mean · max", "${f(NavLive.tickMsMean, 2)} · ${f(NavLive.tickMsMax, 1)} ms")
        Row2("Model mean · max", "${f(NavLive.modelMsMean, 2)} · ${f(NavLive.modelMsMax, 1)} ms")
        Row2("IMU", "${f(live.accHz, 0)} Hz acc · ${f(live.gyrHz, 0)} Hz gyr · grid ${NavLive.imuGridCount} · dropped ${NavLive.droppedSamples}")
        Row2("Logging", "gaps ${live.gaps} · dropped rows ${live.dropped}")

        Section("Outages")
        if (s.outages.isEmpty()) Row2("None yet", "–")
        for ((i, o) in s.outages.withIndex()) Row2("#${i + 1} ${if (o.sim) "simulated" else "real"}", "${f(o.distanceM, 0)} m · ${f(o.durationS, 0)} s · off ${f(o.endErrorM)} m · max ${f(o.maxErrorM)} m · step ${f(o.recoveryStepM)} m" + (if (!o.armedAtEntry) " · not aligned" else ""))
        if (s.scenarioArmed) { Section("Scenario"); Row2("Band", if (s.bandKnown) "from ${f(s.bandFromM, 0)} m" + (s.bandToM?.let { " to ${f(it, 0)} m" } ?: " to the stop") + " · ahead ${f(s.bandDistM, 0)} m" else "waiting for the direction") }
    }
}
