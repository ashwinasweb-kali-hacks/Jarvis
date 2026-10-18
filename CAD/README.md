# 📐 JARVIS Wearable Pod — CAD & Mechanical Design Specifications

## 1. Overview
The **JARVIS Wearable Edge Hardware Bridge** is enclosed in an ultra-compact, dual-shell 3D printed enclosure designed to snap securely onto the temple arm of smart glasses (such as Ray-Ban Meta Wayfarer / Headliner) or attach to a magnetic lapel clip.

```
Dimensions: 48.0 mm (L) x 32.5 mm (W) x 16.2 mm (H)
Chassis Wall Thickness: 1.4 mm
Material: PETG or Resin (SLA Tough 2000)
Mounting: Friction-fit snap clip + 4x M1.4 Brass Heat-Set Inserts
Total Assembled Weight: ~38 grams (including 1200mAh LiPo)
```

## 2. Exploded Assembly Structure
```
       ┌────────────────────────────────────────────────────────┐
       │             Top Enclosure Lid (Snap-Fit)               │
       │   - Acoustic chamber ports for dual MEMS microphones   │
       │   - Status LED diffuser window (0.8mm frosted)         │
       └───────────────────────────┬────────────────────────────┘
                                   │
       ┌───────────────────────────▼────────────────────────────┐
       │     PCB Sub-assembly (Seeed Studio XIAO ESP32-S3)      │
       │   - 4x M1.4 machine screws into brass heat-set inserts │
       │   - I2S MAX98357A DAC daughterboard                    │
       │   - BME680 + ICM-42688 sensor array                    │
       └───────────────────────────┬────────────────────────────┘
                                   │
       ┌───────────────────────────▼────────────────────────────┐
       │            Thermal & Insulation Barrier                │
       │   - 0.1mm Kapton tape insulation                       │
       │   - 1.0mm silicone thermal pad to bottom casing        │
       └───────────────────────────┬────────────────────────────┘
                                   │
       ┌───────────────────────────▼────────────────────────────┐
       │               LiPo Battery Pocket                      │
       │   - 1200mAh 1S 3.7V Pouch Cell (50 x 34 x 6 mm)        │
       │   - Bone-conduction transducer mount pad               │
       └───────────────────────────┬────────────────────────────┘
                                   │
       ┌───────────────────────────▼────────────────────────────┐
       │             Lower Enclosure Base Shell                 │
       │   - USB-C port precision cutout                        │
       │   - Passive thermal ventilation slots                  │
       │   - Interchangeable temple clip / magnetic mount       │
       └────────────────────────────────────────────────────────┘
```

## 3. Included CAD & Manufacturing Files
- `jarvis_wearable_pod_assembly.step`: Full 3D assembly STEP file for CAD editing.
- `jarvis_pod_top_lid.stl`: 3D printable STL for top lid.
- `jarvis_pod_bottom_base.stl`: 3D printable STL for bottom chassis.
- `jarvis_temple_mount_clip.stl`: Ergonomic eyewear temple arm clip.
