import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.snu.idrlogger"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.snu.idrlogger"   // kept so the phone's permissions survive the upgrade from IDR Logger
        minSdk = 29
        targetSdk = 35
        versionCode = 2
        versionName = "2.0.0"
        // the S23 Ultra is arm64; shipping the other ABIs of MapLibre (both backends) and LiteRT triples the APK
        ndk { abiFilters.add("arm64-v8a") }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            isDebuggable = true
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    androidResources {
        // the model, the weights and the tile archive are read raw (memory-mapped or streamed); never compress them
        noCompress += listOf("tflite", "bin", "pmtiles", "pbf", "ttf")
    }

    packaging {
        jniLibs { useLegacyPackaging = false }
        resources { excludes += setOf("META-INF/LICENSE*", "META-INF/DEPENDENCIES", "META-INF/*.kotlin_module") }
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        freeCompilerArgs.add("-opt-in=androidx.compose.material3.ExperimentalMaterial3Api")
    }
}

dependencies {
    implementation(project(":engine"))

    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("com.google.android.material:material:1.13.0")
    implementation("androidx.core:core-splashscreen:1.2.0")

    val composeBom = platform("androidx.compose:compose-bom:2026.06.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-text")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.animation:animation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    // map renderer (R6): Vulkan by default with an OpenGL fallback selectable at runtime
    implementation("org.maplibre.gl:android-sdk-vulkan-opengl:13.6.0")

    // on-device inference path (R2): LiteRT, float32, XNNPACK, one thread
    implementation("com.google.ai.edge.litert:litert:2.2.0")
}
