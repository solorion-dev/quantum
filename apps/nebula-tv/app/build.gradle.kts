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
        versionCode = 1
        versionName = "0.1.0"
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

// Pure Android-framework WebView shell: no external dependencies in v1.
dependencies {
}
