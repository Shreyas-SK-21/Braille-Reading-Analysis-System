# Braille Reading Analysis System

A low-cost conductive grid-based platform for real-time Braille reading behavior analysis.

The system combines a custom conductive sensing grid, an ESP32-based acquisition unit, and a Python analytics pipeline to capture touch interactions and compute multiple Braille reading performance metrics in real time.

For complete system design, algorithms, hardware architecture, and experimental evaluation, refer to the accompanying research paper.

---

## Features

### Hardware
- Low-cost conductive sensing grid
- ESP32-based data acquisition
- Multiplexed row-column scanning
- Real-time touch localization
- Non-invasive and vision-free operation

### Software
- Real-time touch processing
- Multi-threaded analytics pipeline
- Live visualization dashboard
- Word-level interaction tracking
- Session performance monitoring

---

## Metrics

The system computes multiple Braille reading performance indicators:

- Rolling Words Per Minute (WPM)
- Velocity Consistency Analysis
- Hesitation & Regression Detection
- Word-Level Time-on-Task (ToT)
- Skip Rate & Coverage Analysis
- Path Efficiency
- Composite Difficulty Score

---

## System Architecture

```
Braille Sheet
      ↓
Conductive Grid
      ↓
ESP32 Scanner
      ↓
USB Serial
      ↓
Python Analytics Engine
      ↓
Live Metrics & Visualizations
```

---

## Hardware Components

- ESP32 Development Board
- Conductive Copper Tape Grid
- Multiplexing Circuitry
- Braille Overlay Sheet
- USB Interface

---

## Software Stack

- Python
- NumPy
- SciPy
- Matplotlib
- PySerial
- Threading

---

## Applications

- Braille Reading Assessment
- Accessibility Research
- Assistive Education
- Tactile Interaction Studies
- Adaptive Braille Tutoring

---

## Repository Structure

```text
.
├── Docs/           # Project documentation, paper, and supporting material
├── Firmware/       # ESP32 firmware and hardware-side code
├── .gitignore
└── README.md
```

---

## Future Work

- Larger sensing grids
- Wireless connectivity
- Multi-user studies
- ML-based proficiency assessment
- Adaptive tutoring integration

---

## Authors

**Shreyas S. Kulkarni**  
iMTech ECE, IIIT Bangalore

**Heer**  
iMTech ECE, IIIT Bangalore

---

## Documentation

Additional documentation, figures, and the accompanying research paper can be found in the `Docs/` directory.

**Paper:**  
*A Low-Cost Conductive Grid System for Real-Time Multi-Metric Braille Reading Performance Analysis* :contentReference[oaicite:0]{index=0}

## Paper

The full technical details, algorithms, hardware design, and experimental results are available in:

**"A Low-Cost Conductive Grid System for Real-Time Multi-Metric Braille Reading Performance Analysis"** :contentReference[oaicite:1]{index=1}

---
