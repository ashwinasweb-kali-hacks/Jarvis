# 🛠️ JARVIS Wearable Pod — Hardware Assembly Guide

This document describes the step-by-step physical assembly of the **JARVIS Wearable Edge Hardware Bridge**.

---

## 1. Safety & Preparation
- **ESD Safety:** Work on an anti-static mat when handling the ESP32-S3 and MEMS microphone boards.
- **Soldering Equipment:** Temperature-controlled soldering iron set to 320°C (608°F), fine 0.4mm solder wire, flux pen, and tweezers.
- **PPE:** Safety glasses and adequate ventilation during soldering and 3D printing.

---

## 2. 3D Printing the Enclosure
1. **Material:** Use **PETG** or **ABS/ASA** (PLA is acceptable for prototyping, but PETG provides superior heat resistance and impact resilience against skin contact).
2. **Slicer Settings:**
   - Layer Height: 0.12mm (Fine detail for snap-fit latches).
   - Infill: 40% Gyroid.
   - Walls: 4 perimeters.
   - Supports: Tree supports on build plate only (for mounting clip overhang).
3. **Post-Processing:**
   - Gently deburr mating edges with 400-grit sandpaper.
   - Using a soldering iron with a specialized heat-set tip, insert four M1.4 brass threaded inserts into the corner standoff posts.

---

## 3. Wiring & Soldering Order

### Step A: Power Circuitry
1. Cut the LiPo leads to 35mm and solder them to the battery input terminals of the Adafruit Micro-Lipo charger board via a JST-PH 2.0 connector.
2. Solder 28 AWG silicone wires from the charger output (+ / -) to the `5V` and `GND` pins of the Seeed Studio XIAO ESP32-S3.

### Step B: I2S Audio Stack
1. Connect the **INMP441 Microphone**:
   - `VDD` -> `3V3`
   - `GND` -> `GND`
   - `SD`  -> `GPIO 6`
   - `WS`  -> `GPIO 5`
   - `SCK` -> `GPIO 4`
   - `L/R` -> `GND` (Left Channel)
2. Connect the **MAX98357A Audio DAC & Transducer**:
   - `VIN` -> `5V` (System power rail)
   - `GND` -> `GND`
   - `DIN` -> `GPIO 9`
   - `BCLK`-> `GPIO 8`
   - `LRC` -> `GPIO 7`
   - Solder transducer leads to `+` and `-` speaker terminals with 10uF decoupling capacitor.

### Step C: I2C Sensor Stack
1. Daisy-chain the **BME680** and **ICM-42688** sensors:
   - `SDA` -> `GPIO 1`
   - `SCL` -> `GPIO 2`
   - `3V3` -> `3.3V` Rail
   - `GND` -> `Common GND`

### Step D: Haptic Feedback Motor
1. Connect DRV2605L motor driver to the shared I2C bus (`GPIO 1` SDA, `GPIO 2` SCL).
2. Secure the Linear Resonant Actuator (LRA) into the dedicated molded cavity using double-sided thermally conductive tape.

---

## 4. Mechanical Enclosure Fitting
1. Place the LiPo pouch battery into the bottom recessed bay of the lower shell.
2. Insert the insulated insulating Kapton tape barrier above the battery.
3. Lay in the PCB sensor and amplifier sub-assembly, aligning the USB-C port with the casing cutout.
4. Secure the top XIAO ESP32-S3 board with four M1.4 socket-head machine screws into the heat-set brass inserts.
5. Snap the upper shell lid in place until tactile clicks are heard on all four locking tabs.
6. Install the temple clip or magnetic lanyard backplate.

---

## 5. Firmware Flashing & Validation
1. Connect USB-C cable to PC.
2. Run the flash command:
   ```bash
   cd JARVIS/inference-engine/local
   ./flash_esp32s3.sh
   ```
3. Open serial monitor at 115200 baud to observe telemetry, BLE pairing handshakes, and microphone signal levels.
