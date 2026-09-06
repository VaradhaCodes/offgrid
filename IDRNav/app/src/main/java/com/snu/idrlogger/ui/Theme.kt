package com.snu.idrlogger.ui

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.snu.idrlogger.R

/** Design tokens (handoff §4). One dark world; every colour painted explicitly. */
object Tok {
    val Ground = Color(0xFF101010)
    val Card = Color(0xFF1A1A1A)
    val Raised = Color(0xFF242424)
    val Text = Color(0xFFF2F2F2)
    val TextDim = Color(0xFFA9A9A9)
    val TextFaint = Color(0xFF8C8C8C)
    val Locked = Color(0xFF9BE8C4)
    val DeadReckoning = Color(0xFFFFB454)
    val Relocking = Color(0xFF7FD3FF)
    val Band = Color(0xFFFF5A5F)
    val Reveal = Color(0xFFFFFFFF)
    val Outline = Color(0xFF2E2E2E)
    val Danger = Color(0xFFFF5A5F)
}

val Barlow = FontFamily(
    Font(R.font.barlow_regular, FontWeight.Normal),
    Font(R.font.barlow_medium, FontWeight.Medium)
)
val BarlowSemiCondensed = FontFamily(Font(R.font.barlow_semicondensed_semibold, FontWeight.SemiBold))

val IdrTypography = Typography(
    displayLarge = TextStyle(fontFamily = BarlowSemiCondensed, fontWeight = FontWeight.SemiBold, fontSize = 68.sp, lineHeight = 68.sp, fontFeatureSettings = "tnum"),
    displayMedium = TextStyle(fontFamily = BarlowSemiCondensed, fontWeight = FontWeight.SemiBold, fontSize = 44.sp, lineHeight = 46.sp, fontFeatureSettings = "tnum"),
    headlineMedium = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 24.sp, lineHeight = 30.sp),
    headlineSmall = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 20.sp, lineHeight = 26.sp),
    titleLarge = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 20.sp, lineHeight = 26.sp),
    titleMedium = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 16.sp, lineHeight = 22.sp),
    titleSmall = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 22.sp),
    bodyMedium = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 20.sp, fontFeatureSettings = "tnum"),
    bodySmall = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal, fontSize = 12.sp, lineHeight = 16.sp, fontFeatureSettings = "tnum"),
    labelLarge = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 20.sp, fontFeatureSettings = "tnum"),
    labelMedium = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp, fontFeatureSettings = "tnum"),
    labelSmall = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 11.sp, lineHeight = 14.sp, fontFeatureSettings = "tnum")
)

val IdrColors: ColorScheme = darkColorScheme(
    primary = Tok.Locked, onPrimary = Color(0xFF0B1F17),
    secondary = Tok.Relocking, onSecondary = Color(0xFF07202B),
    tertiary = Tok.DeadReckoning, onTertiary = Color(0xFF2A1B03),
    background = Tok.Ground, onBackground = Tok.Text,
    surface = Tok.Card, onSurface = Tok.Text,
    surfaceVariant = Tok.Raised, onSurfaceVariant = Tok.TextDim,
    surfaceContainer = Tok.Card, surfaceContainerHigh = Tok.Raised, surfaceContainerHighest = Color(0xFF2C2C2C), surfaceContainerLow = Color(0xFF151515), surfaceContainerLowest = Tok.Ground,
    outline = Color(0xFF3A3A3A), outlineVariant = Tok.Outline,
    error = Tok.Danger, onError = Color(0xFF2B0A0B),
    inverseSurface = Tok.Text, inverseOnSurface = Tok.Ground, scrim = Color(0xCC000000)
)

@Composable
fun IdrTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = IdrColors, typography = IdrTypography, content = content)
}
