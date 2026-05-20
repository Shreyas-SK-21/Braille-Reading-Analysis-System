# Braille Reading Analysis System

A low-cost conductive grid-based tactile sensing and analytics platform for real-time Braille reading behavior analysis.

This project combines a custom copper-tape touch sensing matrix with a Python-based analytics pipeline to capture and analyze Braille reading interaction patterns in real time. The system computes multiple behavioral metrics including reading speed, motor consistency, hesitation patterns, path efficiency, and word-level interaction statistics.

Unlike camera-based or wearable approaches, the system is completely non-invasive and operates without optical tracking or body-mounted sensors.

---

# Project Overview

The system consists of:

- A conductive copper-tape sensing grid
- Analog multiplexing circuitry
- A microcontroller-based scanning unit
- A Python analytics and visualization pipeline
- A calibrated Braille-sheet-to-grid mapping system

The platform detects touch events on a physical Braille reading surface and transforms them into measurable reading-behavior metrics.

---

# Key Features

## Hardware Features

- Custom copper-tape conductive sensing matrix
- Multi-touch capable architecture
- Real-time row-column multiplexed scanning
- Passive conductive touch detection
- Low-cost scalable design
- No camera or vision dependency
- No wearable sensors required

---

## Software Features

- Real-time touch localization
- Rolling WPM computation
- Velocity consistency analysis
- Hesitation and regression tracking
- Word-level Time-on-Task analysis
- Skip-rate and coverage statistics
- Path efficiency analysis
- Multi-threaded processing pipeline
- Live visualization dashboard

---

# Hardware Architecture

The sensing system is built using a custom conductive copper-tape matrix architecture designed specifically for tactile Braille interaction tracking.

Each sensing cell in the matrix consists of four copper tape patches arranged to form a touch-sensitive region. Every conductive patch is soldered to row and column wiring traces, forming a multiplexed sensing grid.

When a user touches a conductive patch with their finger, the analog multiplexing circuitry detects the resulting signal variation and determines the activated row-column intersection. Using this localization process, the system identifies the exact matrix cell being touched.

A calibrated mapping layer associates each matrix coordinate with a corresponding word position on the physical Braille sheet. Once the touched word is identified, the Python analytics pipeline updates all associated reading metrics in real time.

---

# Touch Localization Workflow

1. User touches conductive copper patch
2. Analog multiplexers scan row and column lines
3. Activated intersection is detected
4. Matrix coordinates are localized
5. Coordinates are mapped to Braille word positions
6. Touch event is sent to the Python analytics engine
7. Metrics and live visualizations are updated

---

# Conductive Grid Design

## Grid Characteristics

- Copper tape-based sensing surface
- Passive conductive touch detection
- Multiplexed row-column architecture
- Real-time touch localization
- Multi-touch sensing support
- Low-cost scalable construction

---

# Hardware Components

- Copper tape sensing patches
- Analog multiplexers
- Microcontroller board
- Row-column wiring matrix
- USB serial communication interface
- Physical Braille overlay sheet

---

# Mapping Mechanism

The physical Braille reading sheet is aligned with the conductive sensing matrix using a predefined calibration mapping.

Each grid coordinate corresponds to:

- A Braille word position
- A Braille cell location
- A metric tracking entry inside the analytics software

This mapping enables the system to transform raw touch coordinates into meaningful reading-behavior data.

---

# Hardware Setup

## Components Required

- Microcontroller board
- Analog multiplexers
- Copper tape
- Wiring connections
- Braille reading sheet
- USB cable
- Host PC running Python analytics software

---

## Setup Procedure

1. Assemble the conductive copper-tape matrix
2. Connect row and column traces to the analog multiplexers
3. Upload firmware to the microcontroller
4. Connect the microcontroller to the host PC via USB
5. Align the Braille sheet with the sensing grid
6. Launch the Python analytics software
7. Begin real-time scanning and visualization

---

# Reference Setup Video

[Reference Vid](https://www.youtube.com/watch?v=u8s9hpjN25Y)
12:25 - 13:00

---

# Python Analytics Pipeline

The Python backend performs all major computation, event processing, metric extraction, and visualization tasks.

The pipeline operates using a multi-threaded architecture consisting primarily of:

| Thread | Responsibility |
|---|---|
| Metrics Thread | Processes incoming sensor frames and updates metric trackers |
| UI Thread | Renders live visualizations and dashboards |

Thread synchronization is handled using thread-safe snapshot mechanisms protected using locks.

---

# Metrics Implemented

## 1. Rolling Words Per Minute (WPM)

Calculates reading speed over a rolling time window.

### Features

- Real-time computation
- EMA smoothing
- Noise reduction
- Stable trend estimation

---

## 2. Velocity Profile Analysis

Tracks finger movement velocity across touch trajectories.

### Computed Metrics

- Mean velocity
- Velocity distribution
- Interquartile Range (IQR)
- Motor consistency score

### Purpose

- Analyze tactile motor stability
- Detect learning progression
- Measure reading smoothness

---

## 3. Hesitation and Regression Analysis

Tracks:

- Repeated word visits
- Backtracking behavior
- Hesitation frequency

### Features

- O(1) regression detection
- Difficulty-word flagging
- Session-level tracking

---

## 4. Word-Level Time-on-Task (ToT)

Measures cumulative interaction duration for each word.

### Outputs

- Rolling ToT
- Session ToT
- 7 × 7 heatmap arrays
- Difficulty hotspot visualization

---

## 5. Skip Rate and Coverage Analysis

Computes:

- Unvisited words
- Partial row coverage
- Reading coverage percentage

### Purpose

- Detect incomplete reading patterns
- Analyze fatigue-related skipping behavior

---

## 6. Path Efficiency

Measures trajectory efficiency using:

```math
\eta = \frac{d_{straight}}{d_{actual}}
```

where:

- \( d_{straight} \) = straight-line distance
- \( d_{actual} \) = total traversed path distance

### Purpose

- Analyze movement efficiency
- Study motor learning progression
- Measure reading optimization

---

# Visualization Suite

The system includes multiple live visualization panels built using matplotlib.

## Included Visualizations

- WPM trend graphs
- Velocity profile overlays
- Regression frequency charts
- ToT bar plots
- 3D ToT surfaces
- Path efficiency scatter plots
- Skip heatmaps

---

# Technologies Used

## Software Stack

- Python
- NumPy
- Matplotlib
- SciPy
- StatsModels
- PySerial
- Threading

---

## Hardware Stack

- Copper tape sensing matrix
- Analog multiplexers
- Microcontroller platform
- USB serial communication

---

# Applications

- Braille reading analysis
- Accessibility research
- Tactile interaction studies
- Reading proficiency assessment
- Assistive education systems
- Adaptive Braille tutoring
- Human-computer interaction research

---

# Future Improvements

- Multi-hand tracking
- Wireless communication
- Larger sensing matrices
- ML-based proficiency classification
- Cross-session analytics
- Adaptive tutoring integration
- Embedded standalone deployment

---

# Authors

## Shreyas S Kulkarni
iMTech ECE  
IIIT Bangalore

## Heer
iMTech ECE  
IIIT Bangalore

# Citation

[ Add Citation Information Here ]

---

# Acknowledgements

[ Add Acknowledgements Here ]
