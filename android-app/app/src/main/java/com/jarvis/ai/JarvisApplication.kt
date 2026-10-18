package com.jarvis.ai

import android.app.Application
import android.util.Log
import com.jarvis.ai.core.JarvisEngine
import com.jarvis.ai.glasses.GlassesBridge
import com.jarvis.ai.inference.InferenceManager
import com.jarvis.ai.voice.VoicePipeline

/**
 * JARVIS Application Entry Point
 *
 * Initializes all core subsystems:
 * - Inference Engine (local + cloud hybrid)
 * - Voice Pipeline (wake word + STT + TTS)
 * - Glasses Bridge (BLE connection to Ray-Ban Meta)
 * - Tool Execution Framework
 */
class JarvisApplication : Application() {

    companion object {
        const val TAG = "JARVIS"
        lateinit var instance: JarvisApplication
            private set
    }

    lateinit var engine: JarvisEngine
        private set
    lateinit var glassesBridge: GlassesBridge
        private set
    lateinit var voicePipeline: VoicePipeline
        private set
    lateinit var inferenceManager: InferenceManager
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.i(TAG, "🤖 JARVIS Initializing...")

        initializeSubsystems()

        Log.i(TAG, "🤖 JARVIS Online. All systems operational.")
    }

    private fun initializeSubsystems() {
        // Initialize inference engine (supports up to 1T param models via sharding)
        inferenceManager = InferenceManager(this).apply {
            initialize(
                localModelPath = "models/jarvis-7b-q4.onnx",
                cloudEndpoint = getCloudEndpoint(),
                useNPU = true,        // Tensor G4 NPU acceleration
                useGPU = true,        // GPU delegate for TFLite
                enableSharding = true // Distributed model sharding
            )
        }

        // Initialize voice pipeline
        voicePipeline = VoicePipeline(this).apply {
            setWakeWord("hey jarvis")
            enableContinuousListening(true)
            setSTTModel("whisper-small")
            setTTSModel("piper-en-high")
        }

        // Initialize glasses bridge
        glassesBridge = GlassesBridge(this).apply {
            enableCamera(true)
            enableMicrophone(true)
            enableHUD(true)
            setStreamQuality(GlassesBridge.Quality.HIGH)
        }

        // Initialize core engine
        engine = JarvisEngine(
            context = this,
            inference = inferenceManager,
            voice = voicePipeline,
            glasses = glassesBridge
        )
    }

    private fun getCloudEndpoint(): String {
        return getString(R.string.cloud_inference_endpoint)
    }
}
