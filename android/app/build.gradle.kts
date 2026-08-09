plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "la.aipnicmp.collector"
    compileSdk = 35

    defaultConfig {
        applicationId = "la.aipnicmp.collector"
        // API 26 is the floor because CellSignalStrengthLte.getRsrp() arrives
        // there. Below it, the only signal metric available is the coarse 0-4
        // bar level, which is too blunt to distinguish "weak but usable" from
        // "unusable" — the distinction the whole project rests on.
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        // Where the collector uploads. HTTPS is not a preference here: Android
        // 9+ refuses cleartext, so an http:// endpoint cannot be used from a
        // real handset at all. Cloudflare terminates TLS in front of the stack,
        // so there is no certificate to manage on the server.
        buildConfigField("String", "API_BASE_URL", "\"https://aipn.chax.site\"")
    }

    buildTypes {
        debug {
            // Also the live server, so a debug build works anywhere — including
            // over mobile data — rather than only on one wifi. The address stays
            // editable in the app for pointing at a laptop during development;
            // the debug network config permits cleartext to private addresses
            // for exactly that case.
            buildConfigField("String", "API_BASE_URL", "\"https://aipn.chax.site\"")
        }
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures {
        buildConfig = true
        viewBinding = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.2.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")

    // Deferred upload with a NetworkType.CONNECTED constraint — the mechanism
    // proposal 2.3 names for store-and-forward.
    implementation("androidx.work:work-runtime-ktx:2.10.0")

    // Fused location: GPS without a network fix, which is the entire premise.
    implementation("com.google.android.gms:play-services-location:21.3.0")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    testImplementation("junit:junit:4.13.2")
}
