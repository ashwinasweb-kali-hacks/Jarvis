# JARVIS-OS smart glasses - component list

Own build, not a headset mod. Target: 4K60 camera, on-device NPU, ~91 g, 8 h
runtime, ₹50,000 all-in (₹25,454 of parts plus buffer).

## Specs

| Item | Value |
|---|---|
| Video | 4K60 (IMX415, locked) |
| AI | 6 TOPS NPU on the RK3576 (Llama 1B + Whisper + YOLO on-device) |
| Sensors | 9-axis IMU, NFC, ambient light, ToF proximity, 2x PDM mic |
| Audio | Bluetooth 5.0 transmitter to your own earbuds |
| Battery | 5000 mAh total (2x 2500 mAh, one per temple), ~8 h |
| Storage | 64 GB eMMC on board (no SD card) |
| Board | 38x38 mm SBC inside a normal temple |
| Weight | ~91 g |
| Frame | PETG, matte black, 32 mm bridge, curved temples |

## Compute

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 1 | Firefly CAM-3576Q38 (RK3576, 6 TOPS NPU, 4 GB, 64 GB eMMC, 38x38 mm) | ₹13,000 | [firefly.store](https://www.firefly.store/products/cam-3576q38-38mm-mini-single-board-computer) | Smallest SBC that does 4K60; 6 TOPS runs Llama 1B + Whisper + YOLO at once; 64 GB eMMC means no SD card and a faster boot; 10 g |

## Camera

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 2 | Arducam IMX415 12.3 MP MIPI (4-lane CSI, M12 lens included) | ₹2,919 | [robu.in](https://robu.in/product/arducam-b0569-imx415-mipi-open-source-camera-module-for-raspberry-pi-with-rich-resources-for-development/) | 4K60 locked, Sony sensor, low noise, 120° FOV |
| 3 | CSI FPC cable (22-pin, 150 mm) | ₹150 | [evelta.com](https://evelta.com/) - search "CSI FPC 22-pin" | Runs inside the temple, no external wires |
| 4 | M12 bezel (3D printed, flush) | ₹30 | print in house | Camera hidden, no forehead protrusion |

## Battery and power

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 5 | 2x 2500 mAh ultra-thin LiPo (4 mm, 55x14 mm, with tabs) | ₹1,000 | [makerbazar.in](https://www.makerbazar.in/) - search "2500mAh LiPo thin" | One per temple, balanced weight, ~8 h runtime |
| 6 | TP4056 charge board x2 | ₹80 | [zbotic.in](https://www.zbotic.in/) - search "TP4056" | Overcharge, over-discharge and short protection |
| 7 | MT3608 5 V boost module (2 A) | ₹45 | [zbotic.in](https://www.zbotic.in/) - search "MT3608" | No brownout under load |
| 8 | 4P magnetic pogo pin connector (2.54 mm, male + female) | ₹180 | [probots.co.in](https://probots.co.in/) - search "pogo pin" | No visible charging port |
| 9 | USB-C cable (30 cm, thin, braided) | ₹200 | [amazon.in](https://www.amazon.in/s?k=USB-C+cable+30cm) | Pogo dock charging |

## Sensors

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 10 | BNO085 9-axis IMU (I2C) | ₹999 | [amazon.in](https://www.amazon.in/Punoscho-BNO085-9-axis-IMU-Sensor/dp/B0FCFQZ4LD) | Head tracking and gesture detection, no drift |
| 11 | PN532 NFC module (I2C/SPI, 13.56 MHz) | ₹284 | [ktron.in](https://www.ktron.in/product/pn532-nfc-rfid-read-write-module-kit-v3/) | Tap-to-pair, payments, access, data exchange |
| 12 | BH1750 ambient light sensor (I2C) | ₹180 | [robu.in](https://robu.in/) - search "BH1750" | Auto brightness, night mode |
| 13 | VL53L0X ToF proximity sensor (I2C) | ₹127 | [ktron.in](https://www.ktron.in/product/vl53l0x-tof-based-lidar-laser-distance-sensor/) | Face detection for auto on/off, privacy mode |
| 14 | INMP441 PDM mic x2 | ₹249 | [amazon.in](https://www.amazon.in/s?k=inmp441) | Stereo audio, noise reduction, wake word |

## Audio

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 15 | 3.5 mm to Bluetooth 5.0 TX dongle (15 mm) | ₹350 | [amazon.in](https://www.amazon.in/s?k=Bluetooth+5.0+3.5mm+transmitter) | Audio to your earbuds, no weight added to the face |
| 16 | 3.5 mm female jack (SMD) | ₹15 | [robu.in](https://robu.in/) - search "3.5mm jack" | Flush mount, no protruding cable |

## PCB and connectors

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 17 | Custom daughter PCB (JLCPCB, 4-layer, 40x20 mm, 5 pcs + DHL) | ₹2,000 | [jlcpcb.com](https://jlcpcb.com/) | Sensors, mics and BT on one board, no visible wires |
| 18 | JST-PH 4-pin connector (male x4) | ₹70 | [sharvielectronics.com](https://www.sharvielectronics.com/) - search "JST-PH 4-pin" | Hot-swap, no soldering for assembly |
| 19 | JST-PH 4-pin connector (female, 200 mm wire x4) | ₹136 | [robomart.in](https://robomart.in/) - search "JST-PH female" | Clean routing inside the temple |
| 20 | 22-pin FPC connector (0.5 mm pitch) | ₹80 | [robu.in](https://robu.in/) - search "FPC connector 22-pin" | Camera plugs in, no soldering |
| 21 | 24 AWG silicone wire (red, black, white, green, 1 m each) | ₹150 | [amazon.in](https://www.amazon.in/s?k=24AWG+silicone+wire) | Flexible, no kink, safe in a hollow temple |
| 22 | 22 AWG silicone wire (red, black, 1 m each) | ₹100 | [amazon.in](https://www.amazon.in/s?k=22AWG+silicone+wire) | Handles 2 A without voltage drop |
| 23 | Heat shrink tubing (3 mm, 5 mm, 8 mm) | ₹80 | [amazon.in](https://www.amazon.in/s?k=heat+shrink+tubing) | Clean joints, no exposed copper |
| 24 | Kapton tape (10 mm) | ₹120 | [amazon.in](https://www.amazon.in/s?k=kapton+tape) | Heat-resistant insulation near the SoC |

## Frame and comfort

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 25 | PETG filament (matte black, 1 kg) | ₹800 | [amazon.in](https://www.amazon.in/s?k=PETG+filament+matte+black) | Stronger than PLA, matte finish, 0.12 mm detail |
| 26 | Silicone nose pads (adjustable, S/M/L) | ₹150 | [amazon.in](https://www.amazon.in/s?k=silicone+nose+pads+glasses) | No pressure, hypoallergenic, replaceable |
| 27 | TPU filament (flexible, 250 g) | ₹500 | [amazon.in](https://www.amazon.in/s?k=TPU+filament+flexible) | Flexible temple tips, no ear pressure |
| 28 | 3M VHB double-sided tape (10 mm) | ₹150 | [amazon.in](https://www.amazon.in/s?k=3M+VHB+tape) | Holds PCB and battery without screws, removable |
| 29 | M2x4 mm screws and standoffs | ₹80 | [amazon.in](https://www.amazon.in/s?k=M2+screws+standoffs) | Removable for service |
| 30 | M3x6 mm screws (x4) | ₹20 | [amazon.in](https://www.amazon.in/s?k=M3+screws) | Flush camera bezel mount |

## Thermal

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 31 | Copper shim (1 mm, 30x20 mm) | ₹50 | [amazon.in](https://www.amazon.in/s?k=copper+sheet+1mm) | Spreads SoC heat across the frame, no hot spot on skin |
| 32 | Thermal pad (1 mm, 30x20 mm, 6 W/mK) | ₹60 | [amazon.in](https://www.amazon.in/s?k=thermal+pad+1mm) | No air gap, maximum heat transfer |
| 33 | Thermal paste | ₹100 | [amazon.in](https://www.amazon.in/s?k=thermal+paste) | Fills micro-gaps |

## Assembly and tools

| # | Part | Price | Link | Why |
|---|---|---|---|---|
| 34 | Solder wire (0.8 mm, 50 g) + flux pen | ₹300 | [amazon.in](https://www.amazon.in/s?k=solder+wire+0.8mm) | Clean joints, no cold solder |
| 35 | Hot glue gun + sticks | ₹300 | [amazon.in](https://www.amazon.in/s?k=hot+glue+gun) | Cable strain relief |
| 36 | Silicone grommets (6 mm ID, x6) | ₹50 | [amazon.in](https://www.amazon.in/s?k=silicone+grommets) | Wires pass through the frame without chafing |
| 37 | Electrical tape (thin, black) | ₹50 | local shop | Extra insulation |
| 38 | Isopropyl alcohol 99% (100 ml) | ₹150 | [amazon.in](https://www.amazon.in/s?k=isopropyl+alcohol+99) | Clean PCBs before assembly |
| 39 | ESD-safe tweezers (curved) | ₹100 | [amazon.in](https://www.amazon.in/s?k=ESD+tweezers) | Safe SMD handling |
| 40 | WS2812B addressable LED | ₹15 | [robu.in](https://robu.in/) - search "WS2812B" | Hidden status light (blue = on, red = low battery) |
| 41 | 10 kΩ resistors (SMD 0805, x4) | ₹20 | [robu.in](https://robu.in/) - search "10k resistor SMD" | I2C pull-ups, stable bus |
| 42 | 0.1 µF ceramic capacitors (SMD 0805, x4) | ₹15 | [robu.in](https://robu.in/) - search "0.1uF SMD" | Decoupling, clean power |

## Cost

| Line | Amount |
|---|---|
| Parts (42 items) | ₹25,454 |
| Buffer (spares, shipping, failed prints) | ₹24,546 |
| Total | ₹50,000 |

## Order order

1. Day 1 - JLCPCB PCB (5-day lead) and the two long-lead imports:
   [Firefly CAM-3576Q38](https://www.firefly.store/products/cam-3576q38-38mm-mini-single-board-computer),
   [Arducam IMX415](https://robu.in/product/arducam-b0569-imx415-mipi-open-source-camera-module-for-raspberry-pi-with-rich-resources-for-development/).
2. Day 2 - BNO085, PN532, VL53L0X, 2x INMP441 (Amazon + Ktron); batteries,
   TP4056, MT3608, pogo pins (Makerbazar + Zbotic + Probots).
3. Day 3 - everything else as one Amazon batch.

42 parts, ~2 weeks to build.
