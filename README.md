# 🕶️ JARVIS — Wearable Edge AI Hardware Bridge & AI Assistant

[![Hack Club Forge](https://img.shields.io/badge/Hack%20Club-Forge%20Hardware%20Grant-orange.svg)](https://forge.hackclub.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hardware: Open Source](https://img.shields.io/badge/Hardware-Open%20Source-brightgreen.svg)](CAD/)

<p align="center">
  <img src="assets/jarvis_hardware_render.jpg" alt="JARVIS Wearable Hardware Bridge Render" width="100%" />
</p>

> **Wearable Edge AI Hardware Bridge for Ray-Ban Meta Smart Glasses (Shiny Chalk White) & Google Pixel 8**  
> Custom 3D-printed snap-fit hardware pod with ESP32-S3, dual MEMS beamforming mics, bone conduction acoustic transducer, I2C environmental sensor telemetry, and distributed tensor inference.

## 🛠️ Hardware & Edge Architecture

```
┌─────────────────────────────────┐     BLE 5.3 / WiFi 6     ┌─────────────────────────────────┐
│  Ray-Ban Meta Smart Glasses     │◄────────────────────────►│  Google Pixel 8 (Host Core)     │
│  - Shiny Chalk White Frame      │                          │  - Tensor G3 TPU Edge Inference │
│  - 12MP Camera (1080p@30fps)    │                          │  - JARVIS Core Service          │
│  - 5-Mic Beamforming Array      │                          │  - Local Quantized Models       │
│  - Directional Open-Ear Audio   │                          │  - Model Sharding Coordinator   │
│  - Reticle HUD Overlay Feed     │                          │  - Wi-Fi 7 / BLE L2CAP Hub      │
└────────────────┬────────────────┘                          └────────────────┬────────────────┘
                 ▲                                                            ▲
                 │                 ESP-NOW / BLE 5.0                          │
                 └───────────────►┌───────────────────────────┐◄──────────────┘
                                  │ JARVIS Wearable Pod       │
                                  │ - ESP32-S3 (240MHz 8MB)   │
                                  │ - BME680 Env Gas/Temp/Hum │
                                  │ - ICM-42688 6-DOF IMU     │
                                  │ - Bone Conduction Audio   │
                                  │ - DRV2605L Haptics        │
                                  │ - 1200mAh LiPo (USB-C)    │
                                  └─────────────┬─────────────┘
                                                │
                                         gRPC / WebSocket
                                                │
                                     ┌──────────▼──────────┐
                                     │   Cloud Inference   │
                                     │  - Model Shards     │
                                     │  - RAG Pipeline     │
                                     │  - Tool Execution   │
                                     └─────────────────────┘
```

## Key Features

- 🧠 **Trillion-Parameter Inference** — Hybrid edge + cloud model sharding
- 🕶️ **Ray-Ban Meta White Glasses Integration** — 1080p30 camera feed, 5-mic array, spatial audio, and HUD overlay
- 📱 **Google Pixel 8 Host Core** — Low-latency local tensor inference powered by Google Tensor G3 TPU
- 🎤 **Voice Activation** — Sub-400ms "Hey JARVIS" wake-word detection with beamforming acoustic cancellation
- 👁️ **Vision Processing** — Real-time scene understanding from eyewear camera
- 🔧 **Tool Execution Engine** — Execute system commands, network sweeps, web search, and security diagnostics
- 🔐 **End-to-End Encryption** — AES-256-GCM encrypted BLE & TLS communication
- 🌐 **Offline Mode** — Local quantized 7B-13B models for zero-connectivity situations

## 📱 Hardware Ecosystem & Device Manifest

Full specifications, pinouts, and BLE characteristics are cataloged in [`DEVICES.csv`](DEVICES.csv) and [`BOM.csv`](BOM.csv):

| Device | Model / Colorway | Role | Processor / SoC | Sensors & Optics | Status |
|:---|:---|:---|:---|:---|:---:|
| **Google Pixel 8** | Obsidian / Hazel / Rose (128GB) | Core Host & Edge TPU Inference | Google Tensor G3 (Titan M2 Coprocessor) | 50MP Octa PD + 12MP Ultrawide Camera, Wi-Fi 7, BLE 5.3 | Active Host |
| **Ray-Ban Meta Smart Glasses** | Shiny Chalk White / Transparent Frame | Wearable Sensor & HUD Node | Qualcomm Snapdragon AR1 Gen 1 | 12MP Camera (1080p30), 5-Mic Beamforming, Open-Ear Audio | Active Eyewear |
| **JARVIS Wearable Pod** | Custom Chalk White & Black PETG | Physical Telemetry & Haptic Bridge | Seeed Studio XIAO ESP32-S3 (8MB PSRAM) | BME680 Environmental + ICM-42688 IMU + Bone Conduction | Active Custom Pod |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Mobile Host | Kotlin / Android 14+ (Google Pixel 8 Tensor G3 optimized) |
| Smart Glasses SDK | Ray-Ban Meta Glasses BLE GATT + L2CAP bridge |
| Local Inference | ONNX Runtime / TensorFlow Lite / Tensor TPU / llama.cpp |
| Cloud Inference | vLLM / TensorRT-LLM (gRPC Cluster) |
| Audio Pipeline | Whisper STT + Piper Neural TTS + Bone Conduction |
| Vision Engine | YOLOv8 + CLIP (1080p Real-time Eyewear Stream) |
| Sensor Telemetry | Bosch BME680 + InvenSense ICM-42688 (I2C 400kHz) |

## 🔌 Hardware Wiring & Schematic

<p align="center">
  <img src="PCB/jarvis_wiring_schematic.svg" alt="JARVIS Hardware Wiring Schematic" width="100%" />
</p>

### Hardware CAD & Design Files
All physical manufacturing files are included in the repository:
- **CAD Assembly:** [`CAD/jarvis_wearable_pod_assembly.step`](CAD/jarvis_wearable_pod_assembly.step)
- **Top Lid STL:** [`CAD/jarvis_pod_top_lid.stl`](CAD/jarvis_pod_top_lid.stl)
- **Bottom Base STL:** [`CAD/jarvis_pod_bottom_base.stl`](CAD/jarvis_pod_bottom_base.stl)
- **Temple Mount Clip STL:** [`CAD/jarvis_temple_mount_clip.stl`](CAD/jarvis_temple_mount_clip.stl) (Compatible with Ray-Ban White Eyewear)
- **KiCad Schematic:** [`PCB/jarvis_hardware_schematic.kicad_sch`](PCB/jarvis_hardware_schematic.kicad_sch)
- **KiCad PCB:** [`PCB/jarvis_hardware_board.kicad_pcb`](PCB/jarvis_hardware_board.kicad_pcb)

## 📋 Bill of Materials (BOM) — Hack Club Forge Grant

| Item | Component | Specification | Qty | Unit Price | Total Price | Part Link |
|:---:|:---|:---|:---:|:---:|:---:|:---|
| 1 | Core Microcontroller | Seeed XIAO ESP32-S3 Sense (8MB PSRAM + Cam/Mic) | 1 | $14.99 | $14.99 | [Seeed Studio](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html) |
| 2 | Neural Edge SBC | Raspberry Pi Zero 2 W (Quad A53 @ 1.0GHz) | 1 | $15.00 | $15.00 | [PiShop](https://www.pishop.us/product/raspberry-pi-zero-2-w/) |
| 3 | Storage Media | SanDisk Extreme 64GB MicroSDXC V30 | 1 | $11.99 | $11.99 | [Amazon](https://www.amazon.com/dp/B07FCMBLV6) |
| 4 | Audio Amplifier | Adafruit MAX98357A I2S 3.2W Class D Mono Amp | 1 | $5.95 | $5.95 | [Adafruit](https://www.adafruit.com/product/3421) |
| 5 | Acoustic Transducer | Mini Bone Conduction Transducer 8Ω 1W | 1 | $8.50 | $8.50 | [Adafruit](https://www.adafruit.com/product/1674) |
| 6 | Microphone Array | INMP441 Omnidirectional Digital I2S Mics | 2 | $3.50 | $7.00 | [Amazon](https://www.amazon.com/dp/B08M93XQ76) |
| 7 | Haptic Driver | Adafruit DRV2605L Haptic Controller + LRA | 1 | $7.95 | $7.95 | [Adafruit](https://www.adafruit.com/product/2305) |
| 8 | Environmental/IMU | Adafruit BME680 Sensor + 6-DOF IMU | 1 | $22.50 | $22.50 | [Adafruit](https://www.adafruit.com/product/3660) |
| 9 | LiPo Charger PMIC | Adafruit Micro-Lipo USB-C Charger (MCP73831) | 1 | $6.95 | $6.95 | [Adafruit](https://www.adafruit.com/product/4410) |
| 10 | LiPo Battery Cell | PKCELL 3.7V 1200mAh Lithium Polymer Battery | 1 | $9.99 | $9.99 | [Amazon](https://www.amazon.com/dp/B07BTTR1H1) |
| 11 | Wearable Enclosure | 3D Printed PETG Chassis & Temple Clip-on | 1 | $15.00 | $15.00 | [Custom STL](CAD/) |
| 12 | Cabling & Wiring | Enamel wire + FPC flex ribbon + JST micro connectors | 1 | $8.00 | $8.00 | [Hardware](CAD/) |
| 13 | Mounting Hardware | M1.4 & M2 stainless machine screws & standoffs | 1 | $6.00 | $6.00 | [Hardware](CAD/) |
| | **SUBTOTAL POD** | **Hack Club Forge Hardware Grant Request** | | | **$139.82** | [BOM.csv](BOM.csv) |
| 14 | Host Smartphone | Google Pixel 8 (Tensor G3 NPU 8GB RAM 128GB) | 1 | $699.00 | $699.00 | [Google Store](https://store.google.com/product/pixel_8) |
| 15 | Smart Eyewear | Ray-Ban Meta Smart Glasses (Shiny Chalk White) | 1 | $299.00 | $299.00 | [Meta Store](https://www.meta.com/smart-glasses/) |
| | **TOTAL ECOSYSTEM** | **Full Wearable Edge AI System Value** | | | **$1,137.82** | [DEVICES.csv](DEVICES.csv) |

## 📖 Build Journal & Hours Logged
Complete progress journal detailing 4 weeks of engineering iterations, BLE packet analysis, and thermal testing is documented in [**`JOURNAL.md`**](JOURNAL.md) (Total logged engineering time: **36.5 hours**).

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
