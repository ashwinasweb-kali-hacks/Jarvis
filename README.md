# 🕶️ JARVIS — Wearable Edge AI Hardware Bridge & AI Assistant

[![Hack Club Forge](https://img.shields.io/badge/Hack%20Club-Forge%20Hardware%20Grant-orange.svg)](https://forge.hackclub.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hardware: Open Source](https://img.shields.io/badge/Hardware-Open%20Source-brightgreen.svg)](CAD/)

<p align="center">
  <img src="assets/jarvis_hardware_render.jpg" alt="JARVIS Wearable Hardware Bridge Render" width="100%" />
</p>

> **Wearable Edge AI Hardware Bridge for Ray-Ban Meta Smart Glasses & Pixel Phone**  
> Custom 3D-printed snap-fit hardware pod with ESP32-S3, dual MEMS beamforming mics, bone conduction acoustic transducer, I2C environmental sensor telemetry, and distributed tensor inference.

## 🛠️ Hardware & Edge Architecture

```
┌─────────────────────┐     BLE/WiFi     ┌─────────────────────┐
│  Ray-Ban Meta Glass  │◄───────────────►│   Google Pixel Phone │
│  - Camera Feed       │                  │  - JARVIS Core       │
│  - Microphone        │                  │  - Local Inference   │
│  - Speaker           │                  │  - Model Sharding    │
│  - Display (HUD)     │                  │  - Edge Computing    │
└─────────────────────┘                  └──────────┬──────────┘
                                                     │
                                              gRPC / WebSocket
                                                     │
                                          ┌──────────▼──────────┐
                                          │   Cloud Inference    │
                                          │  - Model Shards      │
                                          │  - RAG Pipeline      │
                                          │  - Tool Execution    │
                                          └─────────────────────┘
```

## Key Features

- 🧠 **Trillion-Parameter Inference** — Hybrid edge + cloud model sharding
- 🕶️ **Glasses Integration** — Camera, mic, speaker, HUD overlay
- 📱 **Pixel Phone Core** — Local inference engine with Tensor G4 NPU
- 🎤 **Voice Activation** — "Hey JARVIS" wake word detection
- 👁️ **Vision Processing** — Real-time scene understanding from glasses camera
- 🔧 **Tool Use** — Execute system commands, search, browse, hack tools
- 🔐 **Security** — End-to-end encrypted inference pipeline
- 🌐 **Offline Mode** — Quantized local models for no-connectivity scenarios

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Mobile App | Kotlin / Android (Pixel optimized) |
| Glasses SDK | Meta Glasses SDK / BLE |
| Local Inference | ONNX Runtime / TensorFlow Lite / llama.cpp |
| Cloud Inference | vLLM / TensorRT-LLM |
| Communication | gRPC + Protobuf |
| Voice | Whisper (local) + Piper TTS |
| Vision | YOLOv8 + CLIP |
| RAG | ChromaDB + LangChain |

## Project Structure

```
JARVIS/
├── android-app/          # Kotlin Android application
│   ├── app/
│   ├── build.gradle.kts
│   └── settings.gradle.kts
├── glasses-bridge/       # Ray-Ban Meta glasses BLE bridge
├── inference-engine/     # Local + distributed inference
│   ├── local/            # On-device inference (llama.cpp, ONNX)
│   ├── distributed/      # Model sharding & distributed compute
│   └── cloud/            # Cloud inference server
├── voice-pipeline/       # Wake word + STT + TTS
├── vision-pipeline/      # Camera feed processing
├── tools/                # Tool execution framework
├── rag/                  # RAG pipeline & knowledge base
├── proto/                # Protobuf definitions
├── config/               # Configuration files
├── scripts/              # Build & deployment scripts
└── docs/                 # Documentation
```

## Quick Start

```bash
# Clone and setup
git clone https://github.com/your-org/jarvis.git
cd jarvis

# Install dependencies
./scripts/setup.sh

# Build Android app
./scripts/build-android.sh

# Start cloud inference server
./scripts/start-cloud.sh

# Deploy to Pixel phone
./scripts/deploy.sh
```

## License

MIT License — Built with ❤️ for the future of wearable AI.
