package com.snu.idrlogger.ui

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.PaintingStyle
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import kotlin.math.cos

enum class PuckVariant(val label: String) { BLADE("Blade"), TEARDROP("Teardrop"), CHEVRON_DISC("Chevron"), BEAM_DOT("Beam") }

/**
 * The position marker (handoff §4): a beveled arrowhead blade 30 x 22 dp with three facets, a 2 dp #F4F4F4 outline, a real
 * offset shadow, squashed by cos(pitch) so it lies on the road, rotated by a critically damped spring; after 2 s stopped it morphs
 * into a 14 dp disc. The accuracy ring (1 dp dashed) appears only when sigma_pos > 3 m. Drawn in Compose at the map's tracking point.
 */
@Composable
fun PuckOverlay(
    x: Float, y: Float, rotationDeg: Float, tiltDeg: Float, stateColor: Color, stopped: Boolean,
    sigmaPosM: Double, metersPerPixel: Double, variant: PuckVariant, reduceMotion: Boolean, modifier: Modifier = Modifier
) {
    // unwrap the rotation so the spring never spins the long way round
    var unwrapped by remember { mutableFloatStateOf(rotationDeg) }
    val delta = ((rotationDeg - unwrapped) % 360f + 540f) % 360f - 180f
    unwrapped += delta
    val rot by animateFloatAsState(unwrapped, if (reduceMotion) tween(0) else spring(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = 380f), label = "puckRot")
    val morph by animateFloatAsState(if (stopped) 1f else 0f, tween(if (reduceMotion) 0 else 320), label = "puckMorph")
    val squash = cos(Math.toRadians(tiltDeg.toDouble())).toFloat().coerceIn(0.55f, 1f)
    val density = LocalDensity.current
    Canvas(modifier) {
        val dp = density.density
        // accuracy ring: sigma in pixels, only when sigma > 3 m, dashed 1 dp, never filled
        if (sigmaPosM > 3.0 && metersPerPixel > 0) {
            val r = (sigmaPosM / metersPerPixel).toFloat().coerceIn(12f * dp, 400f * dp)
            withTransform({ translate(x, y); scale(1f, squash, Offset.Zero) }) {
                drawCircle(stateColor.copy(alpha = 0.55f), r, Offset.Zero, style = Stroke(width = 1f * dp, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f * dp, 4f * dp))))
            }
        }
        withTransform({ translate(x, y); scale(1f, squash, Offset.Zero); rotate(rot, Offset.Zero) }) {
            drawPuck(this, variant, stateColor, morph, dp)
        }
    }
}

private fun DrawScope.shadowPath(path: Path, dp: Float, blur: Float, alpha: Float) {
    drawIntoCanvas { c ->
        val p = Paint().apply { color = Color.Black.copy(alpha = alpha); style = PaintingStyle.Fill }
        p.asFrameworkPaint().maskFilter = android.graphics.BlurMaskFilter(blur, android.graphics.BlurMaskFilter.Blur.NORMAL)
        c.save(); c.translate(0f, 3f * dp); c.drawPath(path, p); c.restore()
    }
}

fun DrawScope.drawPuck(scope: DrawScope, variant: PuckVariant, color: Color, morph: Float, dp: Float) {
    val outline = Color(0xFFF4F4F4)
    val lit = color; val litBottom = color.copy(red = color.red * 0.85f, green = color.green * 0.85f, blue = color.blue * 0.85f)
    val bevel = Color(color.red * 0.6f, color.green * 0.6f, color.blue * 0.6f)
    val L = 30f * dp; val W = 22f * dp
    // disc form (stopped): 14 dp
    if (morph > 0.999f) { drawDisc(dp, color, outline); return }
    when (variant) {
        PuckVariant.BLADE -> {
            val l = L * (1f - 0.55f * morph); val w = W * (1f - 0.35f * morph)
            val tip = Offset(0f, -l * 0.62f); val left = Offset(-w / 2, l * 0.38f); val right = Offset(w / 2, l * 0.38f); val notch = Offset(0f, l * 0.16f)
            val body = Path().apply { moveTo(tip.x, tip.y); lineTo(right.x, right.y); lineTo(notch.x, notch.y); lineTo(left.x, left.y); close() }
            shadowPath(body, dp, 6f * dp, 0.35f)
            // facets: left bevel, right bevel, top face (centre ridge)
            val leftFacet = Path().apply { moveTo(tip.x, tip.y); lineTo(notch.x, notch.y); lineTo(left.x, left.y); close() }
            val rightFacet = Path().apply { moveTo(tip.x, tip.y); lineTo(right.x, right.y); lineTo(notch.x, notch.y); close() }
            drawPath(leftFacet, bevel); drawPath(rightFacet, bevel.copy(alpha = 0.92f))
            val ridge = Path().apply { moveTo(tip.x, tip.y); lineTo(-w * 0.16f, l * 0.10f); lineTo(notch.x, notch.y); lineTo(w * 0.16f, l * 0.10f); close() }
            drawPath(ridge, Brush.verticalGradient(listOf(lit, litBottom), startY = tip.y, endY = notch.y))
            drawPath(body, outline, style = Stroke(2f * dp, join = androidx.compose.ui.graphics.StrokeJoin.Round))
        }
        PuckVariant.TEARDROP -> {
            val l = L * (1f - 0.5f * morph); val r = W * 0.42f * (1f - 0.2f * morph)
            val path = Path().apply {
                moveTo(0f, -l * 0.6f)
                cubicTo(r * 1.15f, -l * 0.15f, r * 1.05f, l * 0.25f, 0f, l * 0.4f)
                cubicTo(-r * 1.05f, l * 0.25f, -r * 1.15f, -l * 0.15f, 0f, -l * 0.6f); close()
            }
            shadowPath(path, dp, 6f * dp, 0.35f)
            drawPath(path, Brush.verticalGradient(listOf(lit, litBottom), startY = -l * 0.6f, endY = l * 0.4f))
            drawPath(Path().apply { moveTo(0f, -l * 0.6f); cubicTo(-r * 1.15f, -l * 0.15f, -r * 1.05f, l * 0.25f, 0f, l * 0.4f); lineTo(0f, -l * 0.6f); close() }, bevel.copy(alpha = 0.55f))
            drawPath(path, outline, style = Stroke(2f * dp))
        }
        PuckVariant.CHEVRON_DISC -> {
            val rDisc = 8f * dp
            drawIntoCanvas { c -> val p = Paint().apply { this.color = Color.Black.copy(alpha = 0.35f) }; p.asFrameworkPaint().maskFilter = android.graphics.BlurMaskFilter(6f * dp, android.graphics.BlurMaskFilter.Blur.NORMAL); c.drawCircle(Offset(0f, 3f * dp), rDisc, p) }
            drawCircle(outline, rDisc + 2f * dp, Offset.Zero); drawCircle(lit, rDisc, Offset.Zero)
            val a = 1f - morph
            if (a > 0.02f) {
                val chev = Path().apply { moveTo(0f, -(rDisc + 15f * dp) * a - rDisc * (1 - a)); lineTo(9f * dp * a, -(rDisc + 3f * dp)); lineTo(0f, -(rDisc + 7f * dp)); lineTo(-9f * dp * a, -(rDisc + 3f * dp)); close() }
                drawPath(chev, Brush.verticalGradient(listOf(lit, litBottom), startY = -(rDisc + 15f * dp), endY = -rDisc)); drawPath(chev, outline, style = Stroke(1.5f * dp, join = androidx.compose.ui.graphics.StrokeJoin.Round))
            }
        }
        PuckVariant.BEAM_DOT -> {
            val rDot = 7f * dp
            val a = 1f - morph
            if (a > 0.02f) {
                val beam = Path().apply { moveTo(0f, 0f); lineTo(-14f * dp * a, -30f * dp * a); lineTo(14f * dp * a, -30f * dp * a); close() }
                drawPath(beam, Brush.verticalGradient(listOf(lit.copy(alpha = 0.0f), lit.copy(alpha = 0.55f)), startY = -30f * dp, endY = 0f))
            }
            drawIntoCanvas { c -> val p = Paint().apply { this.color = Color.Black.copy(alpha = 0.35f) }; p.asFrameworkPaint().maskFilter = android.graphics.BlurMaskFilter(6f * dp, android.graphics.BlurMaskFilter.Blur.NORMAL); c.drawCircle(Offset(0f, 3f * dp), rDot + 2f * dp, p) }
            drawCircle(outline, rDot + 2.5f * dp, Offset.Zero); drawCircle(lit, rDot, Offset.Zero)
        }
    }
}

private fun DrawScope.drawDisc(dp: Float, color: Color, outline: Color) {
    val r = 7f * dp
    drawIntoCanvas { c -> val p = Paint().apply { this.color = Color.Black.copy(alpha = 0.35f) }; p.asFrameworkPaint().maskFilter = android.graphics.BlurMaskFilter(6f * dp, android.graphics.BlurMaskFilter.Blur.NORMAL); c.drawCircle(Offset(0f, 3f * dp), r, p) }
    drawCircle(outline, r + 2f * dp, Offset.Zero)
    drawCircle(Brush.verticalGradient(listOf(color, color.copy(red = color.red * 0.85f, green = color.green * 0.85f, blue = color.blue * 0.85f)), startY = -r, endY = r), r, Offset.Zero)
}
