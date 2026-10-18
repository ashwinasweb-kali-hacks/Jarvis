package com.jarvis.ai.voice

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * VoicePipeline — Wake Word Detection + STT + TTS
 *
 * Full voice processing pipeline:
 * 1. Continuous audio capture from microphone
 * 2. Wake word detection ("Hey JARVIS")
 * 3. Speech-to-Text via Whisper (on-device)
 * 4. Text-to-Speech via Piper (on-device)
 *
 * All processing runs on-device for privacy and low latency.
 */
class VoicePipeline(private val context: Context) {

    companion object {
        const val TAG = "VoicePipeline"
        const val SAMPLE_RATE = 16000
        const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
    }

    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    private var wakeWord: String = "hey jarvis"
    private var continuousListening: Boolean = true
    private var sttModel: String = "whisper-small"
    private var ttsModel: String = "piper-en-high"
    private var isListening: Boolean = false

    // Emits transcribed text when user finishes speaking
    private val _transcriptions = MutableSharedFlow<String>(extraBufferCapacity = 10)
    val transcriptions: SharedFlow<String> = _transcriptions.asSharedFlow()

    private val _isProcessing = MutableStateFlow(false)
    val isProcessing: StateFlow<Boolean> = _isProcessing.asStateFlow()

    // Wake word detector (Porcupine or custom)
    private var wakeWordDetector: WakeWordDetector? = null

    // Whisper STT engine
    private var whisperEngine: WhisperEngine? = null

    // Piper TTS engine
    private var piperEngine: PiperTTSEngine? = null

    fun setWakeWord(word: String) {
        wakeWord = word
        Log.i(TAG, "Wake word set to: '$word'")
    }

    fun enableContinuousListening(enabled: Boolean) {
        continuousListening = enabled
    }

    fun setSTTModel(model: String) {
        sttModel = model
        Log.i(TAG, "STT model: $model")
    }

    fun setTTSModel(model: String) {
        ttsModel = model
        Log.i(TAG, "TTS model: $model")
    }

    /**
     * Initialize and start the voice pipeline
     */
    fun start() {
        Log.i(TAG, "Starting voice pipeline...")

        // Initialize wake word detector
        wakeWordDetector = WakeWordDetector(context, wakeWord).apply {
            initialize()
        }

        // Initialize Whisper STT
        whisperEngine = WhisperEngine(context, sttModel).apply {
            initialize()
        }

        // Initialize Piper TTS
        piperEngine = PiperTTSEngine(context, ttsModel).apply {
            initialize()
        }

        // Start listening loop
        isListening = true
        scope.launch {
            listenLoop()
        }

        Log.i(TAG, "Voice pipeline active. Listening for '$wakeWord'...")
    }

    /**
     * Main listening loop
     */
    private suspend fun listenLoop() {
        val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        val audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            CHANNEL_CONFIG,
            AUDIO_FORMAT,
            bufferSize * 2
        )

        audioRecord.startRecording()
        val buffer = ShortArray(bufferSize)

        while (isListening) {
            val readCount = audioRecord.read(buffer, 0, buffer.size)
            if (readCount <= 0) continue

            val audioData = buffer.copyOf(readCount)

            // Check for wake word
            if (wakeWordDetector?.detect(audioData) == true) {
                Log.i(TAG, "🎤 Wake word detected!")

                // Record until silence detected
                val utterance = recordUntilSilence(audioRecord)

                // Transcribe with Whisper
                _isProcessing.value = true
                val transcript = whisperEngine?.transcribe(utterance) ?: ""
                _isProcessing.value = false

                if (transcript.isNotBlank()) {
                    Log.i(TAG, "Transcription: $transcript")
                    _transcriptions.emit(transcript)
                }
            }
        }

        audioRecord.stop()
        audioRecord.release()
    }

    /**
     * Record audio until silence is detected (VAD)
     */
    private suspend fun recordUntilSilence(audioRecord: AudioRecord): ShortArray {
        val chunks = mutableListOf<ShortArray>()
        val bufferSize = 1600 // 100ms at 16kHz
        val buffer = ShortArray(bufferSize)
        var silenceFrames = 0
        val maxSilenceFrames = 15 // 1.5 seconds of silence = end of utterance
        val maxRecordingFrames = 300 // 30 seconds max recording

        var frameCount = 0
        while (frameCount < maxRecordingFrames) {
            val readCount = audioRecord.read(buffer, 0, buffer.size)
            if (readCount <= 0) continue

            chunks.add(buffer.copyOf(readCount))
            frameCount++

            // Simple VAD: check RMS energy
            val rms = calculateRMS(buffer, readCount)
            if (rms < 500) { // Silence threshold
                silenceFrames++
                if (silenceFrames >= maxSilenceFrames) break
            } else {
                silenceFrames = 0
            }
        }

        // Concatenate all chunks
        return chunks.flatMap { it.toList() }.toShortArray()
    }

    /**
     * Calculate RMS energy of audio buffer
     */
    private fun calculateRMS(buffer: ShortArray, length: Int): Double {
        var sum = 0.0
        for (i in 0 until length) {
            sum += buffer[i] * buffer[i]
        }
        return Math.sqrt(sum / length)
    }

    /**
     * Speak text using Piper TTS
     */
    suspend fun speak(text: String) {
        Log.i(TAG, "Speaking: ${text.take(50)}...")
        piperEngine?.speak(text)
    }

    fun stop() {
        isListening = false
        scope.cancel()
    }
}

// Stub implementations
class WakeWordDetector(context: Context, wakeWord: String) {
    fun initialize() { /* Load wake word model */ }
    fun detect(audio: ShortArray): Boolean {
        // TODO: Implement with Porcupine or custom model
        return false
    }
}

class WhisperEngine(context: Context, model: String) {
    fun initialize() { /* Load Whisper ONNX model */ }
    suspend fun transcribe(audio: ShortArray): String {
        // TODO: Implement with Whisper ONNX
        return ""
    }
}

class PiperTTSEngine(context: Context, model: String) {
    fun initialize() { /* Load Piper ONNX model */ }
    suspend fun speak(text: String) {
        // TODO: Implement with Piper TTS
    }
}
