# ⚡ Hack Club Forge — Hardware Project Proposal

## Project: JARVIS (Wearable Edge AI Hardware Bridge)

**Applicant:** Avi (AVINASHHZ)  
**Email:** avi1000.0a@gmail.com  
**GitHub:** https://github.com/AVINASHHZ/JARVIS  
**Total BOM Request:** $139.82 USD  
**Submission Date:** October 2026  

---

## 1. What is JARVIS?
**JARVIS** is an open-source, wearable edge-AI hardware bridge designed to interface **Ray-Ban Meta Smart Glasses** with an on-body compute module and smartphone. It empowers developers and makers to run custom local AI inference, wake-word detection, environmental telemetry, and real-time audio interaction without being locked into proprietary cloud ecosystems.

While high-end wearable glasses feature great optics and microphones, their onboard compute is tightly locked down. JARVIS solves this by introducing an open-hardware wearable bridge pod (ESP32-S3 + I2S Audio + Sensors + LiPo) that intercepts audio/vision telemetry over low-latency BLE and Wi-Fi, passes it through local hardware acceleration, and returns tactile, acoustic, and visual feedback in sub-400ms latency.

---

## 2. Hardware Architecture & Schematics

```
┌────────────────────────────────────────────────────────────────────────┐
│                   JARVIS WEARABLE HARDWARE POD                         │
│                                                                        │
│   ┌─────────────────────┐               ┌──────────────────────────┐   │
│   │   Seeed XIAO        │◄── I2S Audio ─┤  Dual INMP441 MEMS Mics  │   │
│   │   ESP32-S3          │               └──────────────────────────┘   │
│   │   - Dual-Core 240MHz│               ┌──────────────────────────┐   │
│   │   - 8MB Octal PSRAM │─── I2S Audio ─►  MAX98357A + Transducer  │   │
│   │   - BLE 5.0 + Wi-Fi │               └──────────────────────────┘   │
│   │   - Vector DSP      │               ┌──────────────────────────┐   │
│   └──────────┬──────────┘─── I2C Bus ───┤  BME680 Sensor (Gas/Env) │   │
│              │                          ├──────────────────────────┤   │
│              │                          │  ICM-42688 6-DOF IMU     │   │
│              │                          ├──────────────────────────┤   │
│              │                          │  DRV2605L Haptic Driver  │   │
│              │                          └──────────────────────────┘   │
│   ┌──────────▼──────────┐                                              │
│   │  Power Subsystem    │ 3.7V LiPo 1200mAh + MCP73831 Charger (USB-C) │
│   └─────────────────────┘                                              │
└────────────────────────────────────────────────────────────────────────┘
            ▲                                      ▲
            │ BLE 5.0 Low Latency                  │ Wi-Fi 802.11 b/g/n
            ▼                                      ▼
┌──────────────────────┐               ┌─────────────────────────────────┐
│ Ray-Ban Meta Glasses │               │ Google Pixel Phone & Cloud Edge │
│ - Camera Framefeed   │               │ - Model Sharding Engine         │
│ - Ambient Mic / HUD  │               │ - gRPC Protocol Hub             │
└──────────────────────┘               └─────────────────────────────────┘
```

---

## 3. Hardware Bill of Materials (BOM) Summary

| Category | Component Description | Qty | Unit Price | Total USD |
|----------|----------------------|-----|------------|-----------|
| **Compute** | Seeed Studio XIAO ESP32-S3 Sense (8MB PSRAM) | 1 | $14.99 | $14.99 |
| **Compute** | Raspberry Pi Zero 2 W (Edge Co-Processor) | 1 | $15.00 | $15.00 |
| **Storage** | SanDisk Extreme 64GB MicroSDXC UHS-I V30 | 1 | $11.99 | $11.99 |
| **Audio** | Adafruit MAX98357A I2S 3.2W Class D Mono Amp | 1 | $5.95 | $5.95 |
| **Audio** | Mini Bone Conduction Transducer 8Ω 1W | 1 | $8.50 | $8.50 |
| **Audio** | INMP441 Omnidirectional Digital I2S Microphones | 2 | $3.50 | $7.00 |
| **Haptics** | Adafruit DRV2605L Haptic Controller + LRA Motor | 1 | $7.95 | $7.95 |
| **Sensors** | Adafruit BME680 Temp/Humidity/Gas + IMU | 1 | $22.50 | $22.50 |
| **Power** | Adafruit Micro-Lipo USB-C Charger Board | 1 | $6.95 | $6.95 |
| **Power** | PKCELL 1200mAh 3.7V Lithium Polymer Battery | 1 | $9.99 | $9.99 |
| **Enclosure**| 3D Printed PETG Chassis & Temple Mounts | 1 | $15.00 | $15.00 |
| **Wiring** | Micro silicone wiring, FPC ribbons & JST connectors | 1 | $8.00 | $8.00 |
| **Fasteners**| M1.4 & M2 brass standoffs and machine screws | 1 | $6.00 | $6.00 |
| **TOTAL** | **Hack Club Forge Hardware Grant Request** | | | **$139.82** |

---

## 4. Why Hack Club Forge?
Hack Club Forge empowers teenagers to build real-world physical electronics and hardware. JARVIS takes wearable computing into the hands of student makers by turning high-end AI concepts into a tangible, physical piece of wearable hardware that anyone can 3D print, solder, and program using open-source tools.

All designs, firmware, KiCad schematics, and 3D CAD files are 100% open-source under the MIT license.
