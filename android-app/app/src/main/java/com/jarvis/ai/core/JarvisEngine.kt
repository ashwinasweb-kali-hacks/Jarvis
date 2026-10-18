package com.jarvis.ai.core

import android.content.Context
import android.util.Log
import com.jarvis.ai.glasses.GlassesBridge
import com.jarvis.ai.inference.InferenceManager
import com.jarvis.ai.inference.InferenceRequest
import com.jarvis.ai.inference.InferenceResponse
import com.jarvis.ai.tools.ToolExecutor
import com.jarvis.ai.tools.ToolRegistry
import com.jarvis.ai.voice.VoicePipeline
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * JARVIS Core Engine
 *
 * The brain of JARVIS. Orchestrates:
 * - Voice input → LLM inference → Voice output
 * - Vision input → Scene understanding → Context enrichment
 * - Tool calling → Execution → Result integration
 * - Glasses HUD → Status display
 *
 * Supports trillion-parameter models via distributed inference:
 * - Local: Quantized models on Tensor G4 NPU (7B-13B params)
 * - Hybrid: Model sharding across device + edge servers
 * - Cloud: Full model inference via gRPC to cloud cluster
 */
class JarvisEngine(
    private val context: Context,
    private val inference: InferenceManager,
    private val voice: VoicePipeline,
    private val glasses: GlassesBridge
) {
    companion object {
        const val TAG = "JarvisEngine"
    }

    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private val toolRegistry = ToolRegistry()
    private val toolExecutor = ToolExecutor(toolRegistry)
    private val conversationHistory = mutableListOf<ConversationTurn>()

    private val _state = MutableStateFlow(JarvisState.IDLE)
    val state: StateFlow<JarvisState> = _state.asStateFlow()

    /**
     * Start the JARVIS engine and begin listening
     */
    fun start() {
        Log.i(TAG, "Starting JARVIS Engine...")

        scope.launch {
            // Listen for voice input
            voice.transcriptions.collect { transcript ->
                handleUserInput(transcript)
            }
        }

        scope.launch {
            // Process camera feed from glasses
            glasses.cameraFrames.collect { frame ->
                handleVisionInput(frame)
            }
        }

        _state.value = JarvisState.LISTENING
        updateHUD("JARVIS Online")
    }

    /**
     * Process user voice input through the full pipeline
     */
    private suspend fun handleUserInput(transcript: String) {
        if (transcript.isBlank()) return

        Log.i(TAG, "User: $transcript")
        _state.value = JarvisState.THINKING

        updateHUD("Processing...")

        // Add to conversation history
        conversationHistory.add(ConversationTurn(Role.USER, transcript))

        // Build inference request with context
        val request = InferenceRequest(
            messages = conversationHistory.map { it.toMessage() },
            systemPrompt = getSystemPrompt(),
            tools = toolRegistry.getAvailableTools(),
            maxTokens = 4096,
            temperature = 0.7f,
            inferenceMode = selectInferenceMode(transcript)
        )

        try {
            // Run inference (automatically routes to local/hybrid/cloud)
            val response = inference.infer(request)

            // Handle tool calls if any
            val finalResponse = if (response.toolCalls.isNotEmpty()) {
                handleToolCalls(response)
            } else {
                response
            }

            // Add assistant response to history
            conversationHistory.add(
                ConversationTurn(Role.ASSISTANT, finalResponse.text)
            )

            // Speak the response
            _state.value = JarvisState.SPEAKING
            voice.speak(finalResponse.text)
            updateHUD(finalResponse.text.take(100))

            Log.i(TAG, "JARVIS: ${finalResponse.text}")

        } catch (e: Exception) {
            Log.e(TAG, "Inference failed", e)
            voice.speak("I encountered an error. Please try again.")
            updateHUD("Error — Retrying...")
        }

        _state.value = JarvisState.LISTENING
    }

    /**
     * Process vision input from glasses camera
     */
    private suspend fun handleVisionInput(frame: ByteArray) {
        // Run scene understanding on the frame
        val sceneDescription = inference.analyzeScene(frame)

        // Update context with current visual scene
        updateVisualContext(sceneDescription)
    }

    /**
     * Execute tool calls from the LLM and return enriched response
     */
    private suspend fun handleToolCalls(response: InferenceResponse): InferenceResponse {
        val toolResults = response.toolCalls.map { toolCall ->
            Log.i(TAG, "Executing tool: ${toolCall.name}")
            updateHUD("Running: ${toolCall.name}")
            toolExecutor.execute(toolCall)
        }

        // Re-run inference with tool results
        val followUpRequest = InferenceRequest(
            messages = conversationHistory.map { it.toMessage() } + toolResults.map { it.toMessage() },
            systemPrompt = getSystemPrompt(),
            tools = toolRegistry.getAvailableTools(),
            maxTokens = 4096,
            temperature = 0.7f
        )

        return inference.infer(followUpRequest)
    }

    /**
     * Select inference mode based on query complexity
     */
    private fun selectInferenceMode(query: String): InferenceMode {
        return when {
            // Simple queries → local inference (fast, private)
            query.length < 50 && !query.contains("analyze") -> InferenceMode.LOCAL
            // Medium complexity → hybrid (edge + device)
            query.length < 200 -> InferenceMode.HYBRID
            // Complex queries → full cloud inference (1T params)
            else -> InferenceMode.CLOUD
        }
    }

    private fun getSystemPrompt(): String {
        return """
            You are JARVIS, an advanced AI assistant running on Ray-Ban Meta Smart Glasses 
            and a Google Pixel phone. You have access to:
            - Real-time camera feed from the user's glasses
            - Voice interaction (always respond conversationally)
            - System tools (file management, web search, device control)
            - Hacking/security tools (network scanning, vulnerability assessment)
            
            Be concise, helpful, and proactive. You can see what the user sees.
            Current visual context: ${currentVisualContext}
        """.trimIndent()
    }

    private var currentVisualContext: String = "No visual context available"

    private fun updateVisualContext(description: String) {
        currentVisualContext = description
    }

    private fun updateHUD(message: String) {
        scope.launch {
            glasses.updateHUD(message)
        }
    }

    fun stop() {
        scope.cancel()
        _state.value = JarvisState.OFFLINE
    }
}

enum class JarvisState {
    IDLE, LISTENING, THINKING, SPEAKING, OFFLINE
}

enum class InferenceMode {
    LOCAL,   // On-device only (7B-13B quantized)
    HYBRID,  // Device + edge servers (70B-405B)
    CLOUD    // Full cloud cluster (up to 1T params)
}

enum class Role {
    USER, ASSISTANT, SYSTEM, TOOL
}

data class ConversationTurn(
    val role: Role,
    val content: String,
    val timestamp: Long = System.currentTimeMillis()
) {
    fun toMessage(): Map<String, String> = mapOf(
        "role" to role.name.lowercase(),
        "content" to content
    )
}
