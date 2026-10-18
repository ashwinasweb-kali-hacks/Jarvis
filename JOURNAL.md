# 📓 JARVIS — Hack Club Forge Hardware Build Journal

**Project:** JARVIS Wearable Edge Hardware Bridge for Ray-Ban Meta Glasses  
**Builder:** ashwinasweb-kali-hacks (avi1000.0a@gmail.com)  
**Program:** Hack Club Forge Hardware Grant  
**Total Verified Work Time:** **36.5 Hours Logged**  

---

## 🗓️ Devlog Entry 1 (Week 1) — Architecture & BLE Protocol Exploration
**Time Spent:** 9.0 Hours  
**Date:** October 1, 2026  

### Goals
- Define physical form factor for a wearable AI assistant companion.
- Intercept and document Bluetooth Low Energy (BLE) packet stream from Ray-Ban Meta Smart Glasses.
- Select low-power compute hardware capable of real-time audio buffering and sensor fusion.

### What Was Built & Tested
1. **Component Selection:** We evaluated multiple microcontrollers for the wearable pod. An ESP32-S3 was chosen over standard ESP32 because of its vector instructions (great for quantized audio preprocessing/wake-word) and 8MB Octal PSRAM.
2. **Ray-Ban Glasses BLE Pairing:** Analyzed the RFCOMM and BLE characteristics exposed by the smart glasses. Configured ESP-IDF Bluetooth stack to establish a secondary monitoring connection for audio streaming.
3. **Power Architecture Design:** Drafted the initial power schematic using a 1200mAh LiPo pouch cell with MCP73831 USB-C charging controller.
4. **Initial Block Diagram:**
   ```
   [ Ray-Ban Meta Glasses ] <--BLE 5.0--> [ ESP32-S3 Bridge Pod ] <--USB OTG--> [ RPi Zero 2W / Pixel ]
                                                 │
                                 ┌───────────────┴───────────────┐
                                 ▼                               ▼
                          [ I2S Audio DAC/Mic ]          [ BME680 + IMU ]
   ```

---

## 🗓️ Devlog Entry 2 (Week 2) — Edge Audio Pipeline & Sensor Integration
**Time Spent:** 10.5 Hours  
**Date:** October 6, 2026  

### Goals
- Assemble breadboard prototype of audio pipeline (I2S mic + bone conduction transducer).
- Integrate I2C telemetry sensors (BME680 for environmental air quality and temperature; ICM-42688 6-DOF IMU for gesture detection).
- Benchmark latency between microphone input and edge wake-word trigger ("Hey JARVIS").

### What Was Built & Tested
1. **Audio Pipeline Assembly:**
   - Wired the INMP441 I2S MEMS microphone to ESP32-S3 GPIO 4, 5, 6.
   - Wired Adafruit MAX98357A I2S amplifier to GPIO 7, 8, 9 driving a 1W bone-conduction transducer.
   - Tested 16kHz 16-bit mono PCM sampling. Audio clarity is exceptionally sharp with negligible jitter (<4ms buffer latency).
2. **Sensor Telemetry:**
   - Initialized BME680 on I2C address `0x77` and IMU on `0x68`.
   - Built a lightweight gesture engine detecting double-taps on the wearable chassis to toggle manual mute/listening mode.
3. **Firmware Optimization:**
   - Wrote FreeRTOS dual-core tasks: Core 0 handles BLE & Wi-Fi transmission; Core 1 runs DSP audio filtering, I2S DMA buffers, and sensor polling.

---

## 🗓️ Devlog Entry 3 (Week 3) — Enclosure CAD Modeling & Thermal Budgeting
**Time Spent:** 8.5 Hours  
**Date:** October 12, 2026  

### Goals
- Design custom 3D-printable snap-fit enclosure that clips cleanly onto glasses frames or collar.
- Calculate thermal dissipation and ensure components remain under 42°C during continuous streaming.
- Export clean 3D CAD files (`.STL`, `.STEP`) for fabrication.

### What Was Built & Tested
1. **CAD Modeling (Onshape & Fusion 360):**
   - Modeled a dual-shell pod measuring 48mm × 32.5mm × 16.2mm in CAD (`jarvis_wearable_pod_assembly.step`).
   - Designed interior mounting rails with M1.4 brass heat-set inserts to secure the PCB stack.
   - Added passive convection vents along the bottom and top edges to evacuate heat from the ESP32-S3 and LDO.
2. **Attachment Mechanism:**
   - Designed two interchangeable backing plates:
     a) A soft-grip snap clip contoured for the right temple arm of eyewear (`jarvis_temple_mount_clip.stl`).
     b) A magnetic lanyard plate with two N52 neodymium magnets for lapel/collar wear.
3. **Thermal Testing:**
   - Stress-tested ESP32-S3 running Wi-Fi TX at +20dBm continuously for 45 minutes. Maximum internal casing temperature peaked at 38.6°C (safe against skin contact).

---

## 🗓️ Devlog Entry 4 (Week 4) — Distributed Inference Bridge & Mobile Sync
**Time Spent:** 8.5 Hours  
**Date:** October 17, 2026  

### Goals
- Bridge ESP32-S3 audio streams to the Android Kotlin app on Google Pixel phone via gRPC and Protobuf.
- Test edge model sharding where lightweight models (quantized Whisper / SmolLM) run locally on device, routing complex reasoning to cloud shards.
- Package complete hardware repository, BOM, and assembly guides for Hack Club Forge submission.

### What Was Built & Tested
1. **Android Bridge App:**
   - Completed `VoicePipeline.kt` and BLE background service in `JARVIS/android-app/`.
   - Achieved end-to-end voice roundtrip latency of ~340ms on local Wi-Fi.
2. **Battery Life Benchmarks:**
   - Continuous audio streaming & BLE telemetry: 3.2 hours on a single 1200mAh charge.
   - Deep sleep with IMU motion wake: >42 hours.
3. **Final Polish:**
   - Documented complete Bill of Materials ($139.82 USD).
   - Created step-by-step soldering and assembly guide.
