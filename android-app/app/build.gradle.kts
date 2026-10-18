plugins {
    id("com.android.application") version "8.5.0"
    id("org.jetbrains.kotlin.android") version "2.0.0"
    id("com.google.protobuf") version "0.9.4"
}

android {
    namespace = "com.jarvis.ai"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jarvis.ai"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0-alpha"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
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

dependencies {
    // Android Core
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.0")

    // Jetpack Compose
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.0")

    // BLE for Glasses
    implementation("no.nordicsemi.android:ble:2.7.0")

    // ML / Inference
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.18.0")
    implementation("org.tensorflow:tensorflow-lite:2.16.1")
    implementation("org.tensorflow:tensorflow-lite-gpu:2.16.1")

    // gRPC
    implementation("io.grpc:grpc-kotlin-stub:1.4.1")
    implementation("io.grpc:grpc-okhttp:1.64.0")
    implementation("com.google.protobuf:protobuf-kotlin-lite:4.27.0")

    // Voice
    implementation("com.github.nicklaus:whisper-android:1.0.0")

    // Networking
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.0")

    // CameraX
    implementation("androidx.camera:camera-camera2:1.3.4")
    implementation("androidx.camera:camera-lifecycle:1.3.4")
    implementation("androidx.camera:camera-view:1.3.4")
}
