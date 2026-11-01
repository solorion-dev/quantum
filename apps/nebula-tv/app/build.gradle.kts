plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "dev.solorion.nebulatv"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.solorion.nebulatv"
        // TVs lag phones: Chromecast with Google TV is API 31+, older
        // Android TV sticks go back further. API 26 (Android 8.0) is a
        // sane v1 floor for a WebView shell.
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug {
            applicationIdSuffix = ".debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

// The shell itself is pure Android framework; ZXing core is the one
// dependency, used only to render the sign-in QR code on the TV.
dependencies {
    implementation("com.google.zxing:core:3.5.3")
}
