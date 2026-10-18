package com.jarvis.ai.tools

import android.util.Log

/**
 * ToolRegistry — Registry of all available tools for JARVIS
 *
 * Tools are functions that JARVIS can call to interact with the real world:
 * - Network scanning (nmap, masscan)
 * - Web search & browsing
 * - File system operations
 * - Device control
 * - Security analysis
 * - Code execution
 */
class ToolRegistry {

    companion object {
        const val TAG = "ToolRegistry"
    }

    private val tools = mutableMapOf<String, Tool>()

    init {
        registerDefaultTools()
    }

    private fun registerDefaultTools() {
        // Network & Security Tools
        register(Tool(
            name = "network_scan",
            description = "Scan a network for hosts and open ports using nmap",
            parameters = mapOf(
                "target" to "string: IP address or CIDR range",
                "scan_type" to "string: quick|full|stealth|vuln"
            )
        ))

        register(Tool(
            name = "wifi_analyze",
            description = "Analyze nearby WiFi networks, signal strength, and security",
            parameters = mapOf(
                "mode" to "string: scan|monitor|deauth_detect"
            )
        ))

        register(Tool(
            name = "vulnerability_scan",
            description = "Scan a target for known vulnerabilities",
            parameters = mapOf(
                "target" to "string: URL or IP",
                "depth" to "string: shallow|medium|deep"
            )
        ))

        // Web Tools
        register(Tool(
            name = "web_search",
            description = "Search the web for information",
            parameters = mapOf(
                "query" to "string: search query",
                "num_results" to "int: number of results (default 5)"
            )
        ))

        register(Tool(
            name = "web_browse",
            description = "Browse a web page and extract its content",
            parameters = mapOf(
                "url" to "string: URL to browse"
            )
        ))

        // System Tools
        register(Tool(
            name = "execute_command",
            description = "Execute a shell command on the connected device",
            parameters = mapOf(
                "command" to "string: shell command to execute",
                "device" to "string: phone|pi|remote"
            )
        ))

        register(Tool(
            name = "file_read",
            description = "Read a file from the filesystem",
            parameters = mapOf(
                "path" to "string: file path"
            )
        ))

        register(Tool(
            name = "file_write",
            description = "Write content to a file",
            parameters = mapOf(
                "path" to "string: file path",
                "content" to "string: file content"
            )
        ))

        // Device Control
        register(Tool(
            name = "take_photo",
            description = "Take a photo using glasses camera",
            parameters = mapOf(
                "resolution" to "string: low|medium|high|max"
            )
        ))

        register(Tool(
            name = "record_video",
            description = "Record video using glasses camera",
            parameters = mapOf(
                "duration" to "int: duration in seconds",
                "resolution" to "string: 720p|1080p|4k"
            )
        ))

        register(Tool(
            name = "send_notification",
            description = "Send a notification to the user's devices",
            parameters = mapOf(
                "title" to "string: notification title",
                "body" to "string: notification body",
                "target" to "string: phone|glasses|both"
            )
        ))

        // Code Tools
        register(Tool(
            name = "python_execute",
            description = "Execute Python code (via Termux or cloud)",
            parameters = mapOf(
                "code" to "string: Python code to execute"
            )
        ))

        Log.i(TAG, "Registered ${tools.size} tools")
    }

    fun register(tool: Tool) {
        tools[tool.name] = tool
    }

    fun getTool(name: String): Tool? = tools[name]

    fun getAvailableTools(): List<com.jarvis.ai.inference.ToolDefinition> {
        return tools.values.map {
            com.jarvis.ai.inference.ToolDefinition(
                name = it.name,
                description = it.description,
                parameters = it.parameters
            )
        }
    }
}

data class Tool(
    val name: String,
    val description: String,
    val parameters: Map<String, String>
)

/**
 * ToolExecutor — Executes tool calls from the LLM
 */
class ToolExecutor(private val registry: ToolRegistry) {

    companion object {
        const val TAG = "ToolExecutor"
    }

    suspend fun execute(toolCall: com.jarvis.ai.inference.ToolCall): ToolResult {
        val tool = registry.getTool(toolCall.name)
            ?: return ToolResult(toolCall.name, "Error: Unknown tool '${toolCall.name}'", false)

        Log.i(TAG, "Executing tool: ${toolCall.name} with args: ${toolCall.arguments}")

        return try {
            val result = when (toolCall.name) {
                "network_scan" -> executeNetworkScan(toolCall.arguments)
                "wifi_analyze" -> executeWifiAnalyze(toolCall.arguments)
                "vulnerability_scan" -> executeVulnScan(toolCall.arguments)
                "web_search" -> executeWebSearch(toolCall.arguments)
                "web_browse" -> executeWebBrowse(toolCall.arguments)
                "execute_command" -> executeCommand(toolCall.arguments)
                "file_read" -> executeFileRead(toolCall.arguments)
                "file_write" -> executeFileWrite(toolCall.arguments)
                "take_photo" -> executeTakePhoto(toolCall.arguments)
                "python_execute" -> executePython(toolCall.arguments)
                else -> "Tool '${toolCall.name}' not yet implemented"
            }
            ToolResult(toolCall.name, result, true)
        } catch (e: Exception) {
            Log.e(TAG, "Tool execution failed: ${toolCall.name}", e)
            ToolResult(toolCall.name, "Error: ${e.message}", false)
        }
    }

    // Tool implementations (stubs — connect to actual system APIs)
    private suspend fun executeNetworkScan(args: Map<String, Any>): String = "Network scan results placeholder"
    private suspend fun executeWifiAnalyze(args: Map<String, Any>): String = "WiFi analysis placeholder"
    private suspend fun executeVulnScan(args: Map<String, Any>): String = "Vulnerability scan placeholder"
    private suspend fun executeWebSearch(args: Map<String, Any>): String = "Web search results placeholder"
    private suspend fun executeWebBrowse(args: Map<String, Any>): String = "Web page content placeholder"
    private suspend fun executeCommand(args: Map<String, Any>): String = "Command output placeholder"
    private suspend fun executeFileRead(args: Map<String, Any>): String = "File content placeholder"
    private suspend fun executeFileWrite(args: Map<String, Any>): String = "File written successfully"
    private suspend fun executeTakePhoto(args: Map<String, Any>): String = "Photo captured"
    private suspend fun executePython(args: Map<String, Any>): String = "Python execution result placeholder"
}

data class ToolResult(
    val toolName: String,
    val output: String,
    val success: Boolean
) {
    fun toMessage(): Map<String, String> = mapOf(
        "role" to "tool",
        "content" to "[$toolName] $output"
    )
}
