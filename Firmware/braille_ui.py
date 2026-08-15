"""
Braille Touch Performance Monitor
==================================
Reads a 7x7 capacitive matrix from ESP32 over serial and quantifies
a reader's Braille performance in real-time.

Hardware notes
--------------
* ESP32 drives TX rows via a 3-bit mux (pins 4,5,18 → S0,S1,S2)
* RX columns are read on ADC pins [32,33,34,35,25,36,39]
* Serial output: 7 rows × 7 tab-separated ADC values, blank line separator
* TX_SHIFT corrects mux wiring in detection logic ONLY.
  The heatmap always shows the raw matrix layout so touching physical
  cell (row=0, col=0) always glows at the top-left of the display.

FIXES vs previous version
--------------------------
1. text_grid normalised to exactly GRID (7) words per row so every column
   maps to exactly one word with no fractional/overlapping boundaries.
2. _build_word_boundaries rewritten to use integer column-range slicing
   (numpy-style) so boundaries never overlap or leave gaps.
3. TX_SHIFT application audited end-to-end:
   - Detection / metrics:  map_tx_col() applied once, consistently.
   - Heatmap label cache:  same map_tx_col() applied, coord string shows
                           logical col so display matches side-panel.
   - word_stats.register() receives already-corrected logical coords.
4. CAL_FRAMES raised to 30 for a stable baseline.
5. WordBoundaryEditor._apply() no longer re-imports from the stale
   text_grid constant for extra rows; it uses the live word_boundaries.
6. count_backtracks, difficulty helpers unchanged (were correct).
7. Minor: removed duplicate 'Tree' in row 0 text_grid entry.

8. [KEY FIX] Mid-touch slide detection:
   - PeakLock.update() now returns (locked_cell, jumped: bool).
   - A confirmed jump >= NEW_BLOCK_JUMP_THRESHOLD cells (Manhattan)
     finalises the current TouchEvent and immediately starts a new one
     at the new cell — without requiring a lift-off between blocks.
   - live_word display is driven from the RAW analysis peak (no lock lag)
     so the "Word now" panel updates instantly when finger moves.

9. [WPM FIX] Sliding Window WPM Counter (O(1) circular bucket algorithm):
   - Replaces the naive deque-scan WPM calculation in PerformanceMetrics.
   - SlidingWindowWPM uses 60 integer buckets (one per second) arranged
     as a circular buffer. A running total is maintained so get_wpm()
     costs exactly one integer read — no loops, no eviction scans.
   - record_touch() is called inside metrics_thread every time a
     TouchEvent is finalised, giving true per-word WPM tracking.
   - Memory is fixed at 60 integers regardless of reading speed.
   - All other PerformanceMetrics fields (duration, efficiency, etc.)
     are unchanged; only the wpm field now comes from SlidingWindowWPM.

10. [M-H1] Seen-Set Regression Tracker:
    - WordStatsTracker now maintains a `seen` set for O(1) session-scoped
      regression detection.
    - `regression_count` maps word → regression hit count.
    - `total_regressions` is a running integer counter.
    - register() performs a single hash-set membership check per touch:
        * Word already in seen → regression; increment counters.
        * Word not in seen    → first touch; insert into seen.
    - snapshot() now exposes:
        * hesitation_rate  = total_regressions / total_touches
        * top_regressed    = top-5 words by regression count
        * flagged_words    = words with regression_count > REGRESSION_FLAG_THRESHOLD
    - Memory: O(V) where V = unique vocabulary, regardless of total touches.
    - Thread safety: all mutations guarded by the existing self._lock.
    - UI: regression metrics surfaced in the Word Stats panel and a new
      Regression Alerts section below the top-words list.

11. [M-D2] EWIQR Per-Word Difficulty Tracker:
     - EWIQRPerWordTracker maintains a sorted window of (duration, weight)
       pairs per word with exponential decay (lambda=0.85) per new touch.
     - Computes weighted Q1/Q3/IQR to answer: "which cells are genuinely
       hard right now?" -- robust to frequency, outliers, and bimodality.
     - WelfordPerWord provides session-wide per-word n/mean/std bookkeeping.
     - snapshot() produces: ewiqr_per_word, Q1/Q3, confidence, top5_hardest,
       session_avg, and a 7x7 masked Z_tot difficulty surface.
     - Cold start returns null until min_window (5) touches per word.
     - Thread safety: per-word locking via the tracker's self._lock.

12. [M-D3] Skip Statistics Engine:
     - Layer 1: Single-Pass Accumulator sweeps word_boundaries once,
       producing skip_rate, skipped_words, partially_visited_rows,
       and a 7×7 boolean skip_mask — all from one dict lookup per cell.
       Stale keys in word_count are structurally unreachable.
     - Layer 2: BFS Cluster Analysis takes skip_mask as sole input.
       Finds 4-connected components of skipped cells, classifies each
       by bounding-box geometry: row_sweep_failure, column_alignment,
       boundary_avoidance, saccade_drift, singleton_noise, scattered_gap.
       Clusters < 4 cells suppressed as noise. Runs at session end only.

13. [V-4] Median Pre-filter → EMA Live WPM Trend:
      - Two-stage noise separation pipeline for live WPM monitoring.
      - Stage 1: Median pre-filter (window=3) kills impulsive spikes
        (hesitation, stumbles) via 50% breakdown point.  Isolated
        outliers are absorbed; sustained slowdowns pass through.
      - Stage 2: EMA (α=0.15) smooths residual variance.  Half-life
        ~0.9s at 5fps — fast enough for flow-state feedback, slow
        enough to ignore sub-second stumbles.
      - WPMTrendTracker.on_frame() is called in metrics_thread at 5fps.
      - get_plot_data() recomputes the full EMA series from raw buffer
        with the median pre-filter applied for plot-line correctness.
      - Separate matplotlib figure shows raw WPM (faded) and EMA trend
        (bright green) with auto-scaling axes.  Updated at ~2fps.
      - Thread safety: all state guarded by self._lock.

14. [V-5] Inter-Word Regression Bar Chart:
      - Horizontal bar chart showing which words the reader regresses
        to most, driven from WordStatsTracker regression_count.
      - Two-layer architecture at different frequencies:
        Layer 1 (60fps): Copies regression snapshot, checks 500ms throttle.
        Layer 2 (2fps):  Full cla() redraw — filter → sort → colour →
        clear → empty guard → barh() → annotations → draw_idle().
      - cla() clears only the axes content, leaving the GridSpec slot
        intact.  Adjacent panels (heatmap, text) are untouched.
      - Bars are red for flagged words (>REGRESSION_FLAG_THRESHOLD),
        blue otherwise.  Colour assignment runs fresh every redraw.
      - Annotations placed inside the bar for long bars, outside for
        short bars, to avoid text overflow.
      - Total cost at 20 bars ≈ 5ms; budget at 2fps = 500ms (1%).
      - Thread safety: snapshot is a cheap dict copy from the UI loop.

15. [V-6] 3D Surface Monitor:
      - Interactive 3D surface plot (matplotlib Axes3D) visualising
        per-cell metrics on a 7×7 meshgrid.
      - Two selectable Z-surfaces via RadioButtons widget:
          * Time-on-Task: mean touch duration per word from Welford tracker
          * Mean Difficulty: EWIQR difficulty score per word
      - Surface replacement algorithm removes only the PolyCollection
        artist, preserving the Axes3D object, wireframe overlay, base
        labels, and view angle across toggles.
      - Throttled at 2fps (0.5s interval) to avoid overloading the
        matplotlib rendering pipeline.
      - Base-plane labels (Z=0) show the word grid for spatial reference.

16. [V-7] Velocity Profile Overlay:
       - Overlays the last 20 touch-event velocity arrays on a single
         axes, with the most recent event drawn bold blue, past events
         as faint gray lines, and an exponentially weighted mean as an
         orange dashed line.
       - Exponential decay (alpha=0.15) ensures recent events dominate
         the mean while older events fade gracefully.
       - on_frame() is called in _finalise_touch() with each new
         velocity array; update throttled at 5fps (0.2s interval).
       - Auto-scales Y to max velocity × 1.1 across all stored events.

17. [V-8] Path Efficiency Plot:
       - Colour-coded scatter plot of per-event path efficiency
         (η = straight_line / path_length) with a LOWESS trend line.
       - Three efficiency tiers: green (η≥0.8 proficient), orange
         (0.5≤η<0.8 developing), red (η<0.5 struggling).
       - LOWESS trend recomputed every 10 events; falls back to
         degree-2 polynomial if statsmodels is not installed.
       - Proficiency target reference line at η=0.8.
       - Throttled at 2fps (0.5s interval).
       - on_event_recorded() called in _finalise_touch() with each
         event's path efficiency value.
"""

import sys
import serial
import numpy as np
from typing import Optional
import threading
import queue
import time
from collections import deque, defaultdict
import bisect
import warnings
warnings.filterwarnings("ignore")

# ─── Weight preset CLI flag ──────────────────────────────────
_PRESET = next((a for a in sys.argv if a.startswith("--weight-preset=")), None)
_WEIGHT_PRESET = _PRESET.split("=", 1)[1] if _PRESET else "default"
# Presets: default | speed_focused | accuracy_focused
# default:          W1=1.0 W2=0.5 W3=2.0 (original)
# speed_focused:    W1=0.5 W2=0.3 W3=3.0 (penalise slow more)
# accuracy_focused: W1=2.0 W2=1.0 W3=1.0 (penalise reversals/jitter more)
_PRESET_MAP = {
    "default":          (1.0, 0.5, 2.0),
    "speed_focused":    (0.5, 0.3, 3.0),
    "accuracy_focused": (2.0, 1.0, 1.0),
}
if _WEIGHT_PRESET not in _PRESET_MAP:
    print(f"[WARNING] Unknown weight preset '{_WEIGHT_PRESET}', using 'default'.")
    _WEIGHT_PRESET = "default"

# ═══════════════════════════ MODE FLAG ═════════════════════════
# Run with --legacy to use the original Matplotlib/Tkinter UI.
# Default (no flag) uses the new PyQtGraph/PyQt5 real-time UI.
_LEGACY_MODE = "--legacy" in sys.argv

if _LEGACY_MODE:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.colors import LinearSegmentedColormap
    import matplotlib.widgets as mwidgets
    from matplotlib.widgets import RadioButtons
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    import tkinter as tk
    from tkinter import ttk, messagebox
else:
    # ── Headless matplotlib for class definitions that reference it ──
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.colors import LinearSegmentedColormap
    import matplotlib.widgets as mwidgets
    from matplotlib.widgets import RadioButtons
    # ── PyQtGraph + PyQt5 ──
    import pyqtgraph as pg
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QSlider, QPushButton, QDialog, QScrollArea, QSpinBox,
        QLineEdit, QStackedWidget, QListWidget, QListWidgetItem,
        QMessageBox, QSplitter, QFrame, QApplication, QGroupBox,
        QTableWidget, QTableWidgetItem, QHeaderView,
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QFont, QColor, QPalette

# ═══════════════════════════ CONFIG ═══════════════════════════
PORT        = "COM5"   # adjust for your OS
BAUD        = 115200
GRID        = 7
CAL_FRAMES  = 10

# Wiring correction applied in detection logic only (NOT in heatmap display)
TX_SHIFT    = -1          # logical_col = (raw_col + TX_SHIFT) % GRID

# Per-row ADC-delta thresholds — tune until idle noise stays below them
ROW_THRESHOLDS = np.array([30, 25, 30, 30, 30, 30, 30], dtype=float)

# Re-trigger dead-time: minimum seconds before the SAME cell can register
# a new touch event. Derived from 5-run CSV analysis: false re-triggers
# during a sustained ~1600ms hold occur every ~300ms on average, so 400ms
# suppresses all in-hold phantom events while still allowing genuine
# intentional revisits (backtracking users return after >500ms away).
RETRIGGER_DEAD_TIME_S = 0.40

MIN_PRESSED_CELLS    = 1
BOLD_PEAK_POWER      = 2.0

# EMA alpha = fraction of NEW data blended per frame
DETECT_SMOOTH_ALPHA  = 0.90     # ↑ from 0.80 — less smoothing lag, faster response
PEAK_HISTORY_LEN     = 1        # ↓ from 2 — lock resolves cell in 1 consistent frame

# Wobble filter: movements <= this many cells are ignored inside a block
MAX_ACCEPTABLE_JUMP  = 1

# Slide detector: a confirmed jump >= this triggers a NEW touch event
# without needing a lift-off. Set to 2 so a 1-cell wobble is absorbed
# but any real slide to a different block registers immediately.
NEW_BLOCK_JUMP_THRESHOLD = 2

RELEASE_FRAMES_NEEDED = 2       # ↓ from 4 — 100ms post-touch silence (was 200ms at 20fps)
MAX_TOUCH_DURATION_S  = 10.0   # force-finalise any touch stuck longer than this

ROLL_WINDOW     = 60
UI_FPS          = 30            # ↑ from 20 — ~33ms/frame (was 50ms), 17ms less display lag
FRAME_QUEUE_MAX = 1

# ── Difficulty Score weights (set by --weight-preset flag) ────
W1, W2, W3 = _PRESET_MAP[_WEIGHT_PRESET]
_WEIGHT_NOTE = f"Weight preset: {_WEIGHT_PRESET}  W1={W1} W2={W2} W3={W3}"
print(f"[CONFIG] {_WEIGHT_NOTE}")

# ── M-H1: Regression flag threshold ──────────────────────────
# Words touched more than this many times as regressions are "flagged"
REGRESSION_FLAG_THRESHOLD = 3

# ── M-D2: EWIQR per-word difficulty tracker ──────────────────
EWIQR_D2_LAMBDA       = 0.85   # decay factor per new touch (≠ velocity λ)
EWIQR_D2_WEIGHT_FLOOR = 0.01   # prune threshold
EWIQR_D2_MIN_WINDOW   = 3      # ↓ from 5 — show data after 3 touches/word

# ── V-4: Median Pre-filter → EMA WPM trend ────────────────────
WPM_TREND_ALPHA           = 0.15    # EMA blend ratio (higher = more responsive)
WPM_TREND_MEDIAN_WINDOW   = 3       # pre-filter window (odd; absorbs 1 outlier)
WPM_TREND_BUFFER_MAXLEN   = 720     # raw buffer capacity (120s × 6fps)
WPM_TREND_UPDATE_INTERVAL = 0.2     # seconds (5fps sampling inside 60fps loop)

# ── V-5: Inter-Word Regression Bar Chart ───────────────────────
REGRESSION_CHART_UPDATE_INTERVAL = 0.5   # seconds — chart updates at ~2fps

# ── V-6: 3D Surface Monitor ───────────────────────────────────
SURFACE_3D_UPDATE_INTERVAL = 0.5         # seconds — 2fps throttle

# ── V-7: Velocity Profile Overlay ─────────────────────────────
VEL_PROFILE_N_OVERLAY       = 20         # how many events to overlay
VEL_PROFILE_ALPHA_WEIGHT    = 0.15       # exponential decay factor for weighted mean
VEL_PROFILE_UPDATE_INTERVAL = 0.2        # seconds — 5fps throttle

# ── V-8: Path Efficiency Plot ─────────────────────────────────
EFFICIENCY_LOWESS_RECOMPUTE_INTERVAL = 10   # events between LOWESS recomputes
EFFICIENCY_PLOT_UPDATE_INTERVAL      = 0.5  # seconds — 2fps throttle
EFFICIENCY_LOWESS_FRAC               = 0.3  # LOWESS local window fraction
# ══════════════════════════════════════════════════════════════

# ═══════════════════════ UI THEME ═════════════════════════════
_BG_DARK       = "#0d1117"   # main background
_BG_CARD       = "#161b22"   # card/axes background
_BG_BORDER     = "#30363d"   # card borders
_FG_PRIMARY    = "#e6edf3"   # bright text
_FG_MUTED      = "#8b949e"   # muted text
_ACCENT_BLUE   = "#58a6ff"   # speed metrics
_ACCENT_GREEN  = "#3fb950"   # accuracy/good
_ACCENT_ORANGE = "#f0883e"   # difficulty/warning
_ACCENT_RED    = "#f85149"   # errors/danger
_GRID_COLOR    = "#21262d"   # grid lines

# ── Bill of Materials — cost breakdown (validates 'low-cost' claim) ──────
HARDWARE_COST_USD = {
    "ESP32 dev board":          4.00,   # e.g. ESP32-WROOM-38-pin
    "Copper tape (1m roll)":    2.50,   # conductive grid electrodes
    "Multiplexer IC (2x CD4051)": 0.80, # 8:1 analog mux for rows+cols
    "Resistors + capacitors":   0.30,   # passive components
    "USB cable":                0.50,
    "Braille overlay sheet":    1.00,   # printed or embossed
    "PCB / perfboard":          1.50,   # optional; breadboard = $0
    "Misc (wire, headers)": 0.50,
}
_TOTAL_COST_USD = sum(HARDWARE_COST_USD.values())
print(f"[CONFIG] Estimated hardware cost: ${_TOTAL_COST_USD:.2f} USD")
print(f"[CONFIG] BOM: {list(HARDWARE_COST_USD.keys())}")

# Font stack — first available is used
if _LEGACY_MODE:
    plt.rcParams['font.family'] = ['Inter', 'Segoe UI', 'SF Pro Display',
                                    'Helvetica Neue', 'sans-serif']

# Active finger view for plot menu: 0 = finger 0, 1 = finger 1, 2 = combined
_active_finger_view = 2
# ══════════════════════════════════════════════════════════════

# ═══════════════════════ WORD MAPPING ═════════════════════════
#
# Each entry is a (word_label, num_blocks) tuple.
#   word_label  = the word name displayed and used for metrics
#   num_blocks  = how many sensor columns this word's copper tape spans
#
# Per-row rule: the num_blocks values MUST sum to GRID (7).
#
# Setting all widths to 1 gives backward-compatible single-block
# per-word behavior.  Increase width to match the physical braille
# sheet copper-tape layout.
#
# Examples:
#   3 words:  [("Ant", 3), ("Apple", 2), ("Star", 2)]      → 3+2+2 = 7
#   2 words:  [("Snail", 4), ("Boat", 3)]                   → 4+3   = 7
#   7 words:  all (word, 1)                                  → 1×7   = 7

text_grid = [
    # (word, num_blocks)  — num_blocks per row must sum to GRID (7)
    [("Ant", 2),    ("Socks", 3),  ("Alligator", 2)  ],  # row 0
    [("Snail", 2),  ("Turtle", 3), ("Pen", 2)   ],  # row 1
    [("Fifth", 2),  ("Switch", 4), ("Knot", 1)    ],  # row 2
    [("Cow", 2),    ("Egg", 2),    ("Elephant", 3)   ],  # row 3
    [("Hen", 2),    ("Moon", 3),   ("House", 2)   ],  # row 4
    [("Mango", 3),  ("Mat", 2),    ("Scissors", 2)   ],  # row 5
    [("Grape", 3),  ("Fog", 2),    ("Frog", 2)],  # row 6
]

# ══════════════════════════════════════════════════════════════
# M-T2: EWIQR VELOCITY CONSISTENCY TRACKER
# ══════════════════════════════════════════════════════════════
#
# Algorithm: Exponentially Weighted IQR (EWIQR)
#
# Each touch event contributes a velocity array (cells/s between
# consecutive sensor cells).  Values are stored with a weight that
# decays by λ per event so recent events dominate without a hard
# cliff.  IQR is computed as a weighted percentile difference
# (P75 − P25).  A consistency score 1 − IQR/mean maps the spread
# onto [0, 1] where 1 = perfectly uniform speed.
#
# Complexity
# ──────────
# record()   : O(T log T) where T = stored value count (bounded by
#              pruning + effective horizon K × N_eff)
# snapshot() : O(1) — reads only the pre-computed cache; never
#              blocks the UI thread on a sort.
# Memory     : O(N_eff × K), fixed; independent of session length.
#
# Hyperparameter
# ──────────────
# λ (EWIQR_LAMBDA) ∈ (0,1).  Effective memory horizon:
#   N_eff ≈ 1 / (1 − λ)
# λ=0.95 → ~20 events dominate.  λ=0.98 → ~50 events.

EWIQR_LAMBDA     = 0.95   # decay factor — tune for faster/slower memory
EWIQR_PRUNE_THR  = 1e-6   # normalized weight below which a value is dropped
EWIQR_RENORM_INT = 50     # renormalize every N events for float stability
EWIQR_MEAN_FLOOR = 0.5    # ε-floor on mean to protect slow/consistent readers


class VelocityTracker:
    """
    M-T2: Thread-safe EWIQR velocity consistency tracker.

    Usage
    ─────
    velocity_tracker.record(vels)    # called in _finalise_touch()
    snap = velocity_tracker.snapshot()
    # snap keys: mean_vel, iqr, consistency, n_events
    """

    def __init__(self, lam: float = EWIQR_LAMBDA):
        self._lam              = lam
        self._values: list     = []   # [[velocity: float, weight: float], …]
        self._decay_acc: float = 1.0  # global aging multiplier
        self._event_count: int = 0
        self._lock             = threading.Lock()
        self._cache: dict      = dict(mean_vel=0.0, iqr=0.0,
                                      consistency=0.0, n_events=0)

    # ── public API ────────────────────────────────────────────

    def record(self, velocity_array: np.ndarray) -> None:
        """
        Register one touch event's velocity array and recompute stats.

        Steps (all performed with lock held):
          1. Multiply decay_accumulator by λ  → ages all existing weights
             without touching them individually (O(1) aging trick).
          2. Append each new velocity with effective_weight = 1/decay_acc
             so incoming values appear at weight 1 in the decayed frame.
          3. Prune values whose normalized weight drops below EWIQR_PRUNE_THR.
          4. Every EWIQR_RENORM_INT events, divide all weights by max_weight
             and reset decay_acc to 1.0 — prevents float overflow/underflow.
          5. Recompute and cache stats atomically.
        """
        if len(velocity_array) == 0:
            return

        with self._lock:
            # Step 1: age existing weights
            self._decay_acc *= self._lam

            # Step 2: insert new values
            ew = 1.0 / self._decay_acc
            for v in velocity_array:
                self._values.append([float(v), ew])

            # Step 3: prune negligible-weight values
            if self._values:
                total_w = sum(row[1] for row in self._values)
                if total_w > 0:
                    self._values = [
                        row for row in self._values
                        if row[1] / total_w > EWIQR_PRUNE_THR
                    ]

            self._event_count += 1

            # Step 4: periodic renormalization for numerical stability
            if self._event_count % EWIQR_RENORM_INT == 0 and self._values:
                max_w = max(row[1] for row in self._values)
                if max_w > 0:
                    for row in self._values:
                        row[1] /= max_w
                    self._decay_acc = 1.0

            # Step 5: recompute + atomically replace cache
            self._cache = self._compute_stats()

    def snapshot(self) -> dict:
        """
        Return a copy of the pre-computed stats cache.
        O(1) — the UI thread is never blocked by a sort.
        """
        with self._lock:
            return dict(self._cache)

    def reset(self) -> None:
        with self._lock:
            self._values      = []
            self._decay_acc   = 1.0
            self._event_count = 0
            self._cache       = dict(mean_vel=0.0, iqr=0.0,
                                     consistency=0.0, n_events=0)

    # ── internal ─────────────────────────────────────────────

    def _compute_stats(self) -> dict:
        """
        Compute weighted mean, IQR, and consistency score.
        Must be called with self._lock held.

        Percentile method: sort by value, walk cumulative normalized
        weight, record value when cumsum first crosses 0.25 and 0.75.
        Uses np.searchsorted for efficiency.
        """
        EMPTY = dict(mean_vel=0.0, iqr=0.0, consistency=0.0,
                     n_events=self._event_count)
        if not self._values:
            return EMPTY

        vals    = np.array([row[0] for row in self._values], dtype=float)
        weights = np.array([row[1] for row in self._values], dtype=float)

        total        = weights.sum()
        norm_weights = weights / total

        # Weighted mean
        mean_vel = float(np.dot(vals, norm_weights))

        # Weighted percentiles via sorted cumulative walk
        order       = np.argsort(vals)
        sorted_vals = vals[order]
        sorted_w    = norm_weights[order]
        cumsum      = np.cumsum(sorted_w)

        p25_idx = int(np.searchsorted(cumsum, 0.25))
        p75_idx = int(np.searchsorted(cumsum, 0.75))
        p25_idx = min(p25_idx, len(sorted_vals) - 1)
        p75_idx = min(p75_idx, len(sorted_vals) - 1)

        p25 = float(sorted_vals[p25_idx])
        p75 = float(sorted_vals[p75_idx])
        iqr = p75 - p25

        # Consistency score — floor mean at ε to protect slow readers
        consistency = 1.0 - (iqr / max(mean_vel, EWIQR_MEAN_FLOOR))
        consistency = float(np.clip(consistency, 0.0, 1.0))

        return dict(
            mean_vel    = mean_vel,
            iqr         = iqr,
            consistency = consistency,
            n_events    = self._event_count,
        )

def _build_word_boundaries(tgrid: list, total_cols: int) -> dict:
    """
    Returns {row_idx: [{"word", "start", "end"}, …]} where start/end
    are inclusive column indices, covering 0 … total_cols-1 with no
    gaps or overlaps.

    Supports two entry formats per row:
      - (word_label, num_blocks) tuple → explicit width
      - plain string                   → width = 1 (legacy)

    The num_blocks values per row MUST sum to total_cols.
    """
    boundaries: dict = {}
    for row_idx, row in enumerate(tgrid):
        entries = []
        col = 0
        for item in row:
            if isinstance(item, (tuple, list)):
                word, width = item[0], int(item[1])
            else:
                # Legacy plain-string format → single-block word
                word, width = item, 1
            entries.append({
                "word":  word,
                "start": col,
                "end":   col + width - 1,
            })
            col += width
        if col != total_cols:
            print(f"WARNING: Row {row_idx} block widths sum to {col}, "
                  f"expected {total_cols}. Boundary mapping may be incorrect.")
        boundaries[row_idx] = entries
    return boundaries


# Global mutable boundary table — edited live by the word editor.
word_boundaries_lock = threading.Lock()
word_boundaries = _build_word_boundaries(text_grid, GRID)


def get_word_from_touch(row: int, col: int) -> Optional[str]:
    """Return the word label for sensor logical (row, col), or None."""
    if not (0 <= row < GRID and 0 <= col < GRID):
        return None
    with word_boundaries_lock:
        if row not in word_boundaries:
            return None
        for entry in word_boundaries[row]:
            if entry["start"] <= col <= entry["end"]:
                return entry["word"]
    return None


# ── Cell label cache ───────────────────────────────────────────
_cell_word_cache: dict[tuple, str] = {}
_cell_word_cache_lock = threading.Lock()


_cell_labels_dirty = True   # set True whenever word boundaries change

def _rebuild_cell_word_cache() -> None:
    """Recompute heatmap overlay labels from current word_boundaries."""
    global _cell_labels_dirty
    new_cache: dict[tuple, str] = {}
    for r in range(GRID):
        for raw_c in range(GRID):
            w = get_word_from_touch(r, raw_c)
            new_cache[(r, raw_c)] = w if w else ""
    with _cell_word_cache_lock:
        _cell_word_cache.clear()
        _cell_word_cache.update(new_cache)
    _cell_labels_dirty = True


_rebuild_cell_word_cache()


# ══════════════ MANUAL WORD BOUNDARY EDITOR ═══════════════════

class WordBoundaryEditor:
    """Tkinter dialog to inspect and edit word→column-range mappings."""

    def __init__(self, master=None):
        self._root = tk.Tk() if master is None else tk.Toplevel(master)
        self._root.title("Word Boundary Editor")
        self._root.configure(bg="#1a1a2e")
        self._root.resizable(True, True)
        self._build_ui()

    def _build_ui(self):
        root = self._root
        DARK_BG  = "#1a1a2e"
        MID_BG   = "#16213e"
        ENTRY_BG = "#0f3460"
        FG       = "#e0e0e0"
        ACCENT   = "#e94560"
        GRID_FG  = "#a0c4ff"

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel",    background=DARK_BG, foreground=FG,
                        font=("Courier New", 10))
        style.configure("TFrame",    background=DARK_BG)
        style.configure("TSpinbox",  fieldbackground=ENTRY_BG,
                        background=MID_BG, foreground=FG,
                        arrowcolor=FG, font=("Courier New", 10))
        style.configure("TButton",   background=ACCENT, foreground="white",
                        font=("Courier New", 10, "bold"), relief="flat")
        style.map("TButton",
                  background=[("active", "#c73652"), ("pressed", "#a02840")])

        header = ttk.Label(root,
            text="✎  WORD BOUNDARY EDITOR\n"
                 "Edit word labels. Boundaries are spread evenly per row.",
            font=("Courier New", 11, "bold"), foreground=ACCENT,
            background=DARK_BG, justify="center")
        header.pack(pady=(14, 8), padx=16)

        note = ttk.Label(root,
            text=(f"Grid has {GRID} columns (0–{GRID-1}).  "
                  "Add/remove words by changing the word count spinbox, "
                  "then click Apply."),
            font=("Courier New", 9), foreground=_FG_MUTED,
            background=DARK_BG, wraplength=740, justify="left")
        note.pack(padx=16, pady=(0, 8))

        canvas_frame = tk.Frame(root, bg=DARK_BG)
        canvas_frame.pack(fill="both", expand=True, padx=16, pady=4)

        canvas = tk.Canvas(canvas_frame, bg=DARK_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                  command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=DARK_BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(evt):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_configure)

        self._rows: list[dict] = []

        tk.Label(inner, text="", bg=DARK_BG, fg=FG,
                 font=("Courier New", 9, "bold"),
                 width=6, anchor="center").grid(row=0, column=0, padx=4, pady=2)
        tk.Label(inner, text="# Words", bg=DARK_BG, fg=GRID_FG,
                 font=("Courier New", 9, "bold")).grid(row=0, column=1, padx=4)
        tk.Label(inner,
                 text="Word labels & block widths  →  (widths must sum to 7)",
                 bg=DARK_BG, fg=GRID_FG,
                 font=("Courier New", 9, "bold")).grid(
            row=0, column=2, columnspan=GRID, sticky="w", padx=4)

        with word_boundaries_lock:
            current_boundaries = {k: list(v) for k, v in word_boundaries.items()}

        for row_idx in range(GRID):
            entries = current_boundaries.get(row_idx, [])
            words   = [e["word"] for e in entries]
            widths  = [e["end"] - e["start"] + 1 for e in entries]

            count_var  = tk.IntVar(value=len(words))
            word_vars  = [tk.StringVar(value=w) for w in words]
            width_vars = [tk.IntVar(value=w) for w in widths]

            row_state = {"count_var": count_var, "word_vars": word_vars,
                         "width_vars": width_vars,
                         "frame": None, "row_idx": row_idx}
            self._rows.append(row_state)

            tk.Label(inner, text=f" Row {row_idx}",
                     bg=MID_BG, fg=ACCENT,
                     font=("Courier New", 10, "bold"),
                     width=6, relief="flat").grid(
                row=row_idx + 1, column=0, padx=(4, 2), pady=3, sticky="ew")

            sp = tk.Spinbox(inner, from_=1, to=GRID,
                            textvariable=count_var, width=4,
                            bg=ENTRY_BG, fg=FG,
                            buttonbackground=MID_BG,
                            font=("Courier New", 10),
                            command=lambda idx=row_idx: self._on_count_change(idx))
            sp.grid(row=row_idx + 1, column=1, padx=(2, 8), pady=3)

            wframe = tk.Frame(inner, bg=DARK_BG)
            wframe.grid(row=row_idx + 1, column=2, columnspan=GRID,
                        sticky="w", pady=3)
            row_state["frame"] = wframe
            row_state["entry_bg"] = ENTRY_BG
            row_state["fg"] = FG
            row_state["grid_fg"] = GRID_FG
            self._rebuild_word_entries(row_idx, current_boundaries)

        btn_frame = tk.Frame(root, bg=DARK_BG)
        btn_frame.pack(pady=12)

        tk.Button(btn_frame, text="✔  Apply Changes",
                  bg=ACCENT, fg="white",
                  font=("Courier New", 11, "bold"),
                  relief="flat", padx=16, pady=6,
                  cursor="hand2",
                  command=self._apply).pack(side="left", padx=10)

        tk.Button(btn_frame, text="✖  Close",
                  bg="#333355", fg="#aaaacc",
                  font=("Courier New", 11),
                  relief="flat", padx=16, pady=6,
                  cursor="hand2",
                  command=self._root.destroy).pack(side="left", padx=10)

        root.update_idletasks()
        root.minsize(800, 420)

    def _rebuild_word_entries(self, row_idx: int,
                              boundaries: Optional[dict] = None):
        row_state = self._rows[row_idx]
        wframe    = row_state["frame"]
        ENTRY_BG  = row_state["entry_bg"]
        FG        = row_state["fg"]
        GRID_FG   = row_state["grid_fg"]
        DARK_BG   = "#1a1a2e"

        for child in wframe.winfo_children():
            child.destroy()

        n = row_state["count_var"].get()

        # Rebuild word_vars — preserve existing, pad with empty
        current_words = [v.get() for v in row_state["word_vars"]]
        while len(current_words) < n:
            current_words.append("")
        current_words = current_words[:n]
        row_state["word_vars"] = [tk.StringVar(value=w) for w in current_words]

        # Rebuild width_vars — preserve existing, auto-distribute remainder
        current_widths = [v.get() for v in row_state.get("width_vars", [])]
        while len(current_widths) < n:
            current_widths.append(1)
        current_widths = current_widths[:n]
        # Auto-redistribute if sum doesn't match GRID
        total_w = sum(current_widths)
        if total_w != GRID:
            base, extra = divmod(GRID, n)
            current_widths = [base + (1 if i < extra else 0) for i in range(n)]
        row_state["width_vars"] = [tk.IntVar(value=w) for w in current_widths]

        # Compute column ranges from explicit widths
        ranges = []
        col = 0
        for i in range(n):
            w = current_widths[i]
            ranges.append((col, col + w - 1))
            col += w

        for i, (wvar, wdvar, (s, e)) in enumerate(zip(
                row_state["word_vars"], row_state["width_vars"], ranges)):
            tk.Label(wframe, text=f"[{s}-{e}]",
                     bg=DARK_BG, fg=GRID_FG,
                     font=("Courier New", 8)).grid(
                row=0, column=i * 3, padx=(6, 1), sticky="e")

            tk.Entry(wframe, textvariable=wvar,
                     bg=ENTRY_BG, fg=FG,
                     insertbackground=FG,
                     relief="flat",
                     font=("Courier New", 10),
                     width=max(8, len(wvar.get()) + 2)).grid(
                row=0, column=i * 3 + 1, padx=(1, 1))

            # Width spinbox
            tk.Spinbox(wframe, from_=1, to=GRID,
                       textvariable=wdvar, width=3,
                       bg="#2a2a4e", fg="#ffcc66",
                       buttonbackground=DARK_BG,
                       font=("Courier New", 9)).grid(
                row=0, column=i * 3 + 2, padx=(1, 4))

    def _on_count_change(self, row_idx: int):
        self._rebuild_word_entries(row_idx)

    def _apply(self):
        global word_boundaries

        # Build new text_grid as list of (word, width) tuples
        new_tgrid: list[list[tuple]] = []
        for row_state in self._rows:
            words  = [v.get().strip() for v in row_state["word_vars"]]
            widths = [v.get() for v in row_state.get("width_vars", [])]
            # Fallback: if no width_vars, default all to 1
            while len(widths) < len(words):
                widths.append(1)
            entries = []
            for i, w in enumerate(words):
                label = w if w else f"?{i}"
                entries.append((label, widths[i]))
            # Validate widths sum to GRID
            total_w = sum(widths[:len(words)])
            if total_w != GRID:
                messagebox.showerror(
                    "Invalid widths",
                    f"Row {row_state['row_idx']}: block widths sum to "
                    f"{total_w}, must equal {GRID}.",
                    parent=self._root,
                )
                return
            new_tgrid.append(entries)

        # Preserve extra rows (beyond GRID) from current boundaries
        with word_boundaries_lock:
            all_row_keys = sorted(word_boundaries.keys())
        extra_keys = [k for k in all_row_keys if k >= GRID]
        for k in extra_keys:
            with word_boundaries_lock:
                extra_entries = [(e["word"], e["end"] - e["start"] + 1)
                                 for e in word_boundaries[k]]
            new_tgrid.append(extra_entries)

        new_boundaries = _build_word_boundaries(new_tgrid, GRID)

        with word_boundaries_lock:
            word_boundaries.clear()
            word_boundaries.update(new_boundaries)

        _rebuild_cell_word_cache()

        messagebox.showinfo(
            "Applied",
            "Word boundaries updated!\n"
            "The heatmap overlay and detection logic now use the new mapping.",
            parent=self._root,
        )

    def run(self):
        self._root.mainloop()


# ── Thread-safe signal: background → main thread to open editor ──────────────
# Tkinter windows MUST be created on the main thread.  We use a simple
# threading.Event flag that the main UI loop polls; when set, the loop
# opens the editor on the main thread and clears the flag.
_editor_requested = threading.Event()


def open_word_boundary_editor():
    """Signal the main thread to open the Word Boundary Editor."""
    _editor_requested.set()


def _open_editor_on_main_thread():
    """Actually open the editor — MUST be called from the main thread."""
    _editor_requested.clear()
    editor = WordBoundaryEditor()
    editor.run()  # blocks until the Tk window is closed


# ══════════════════════════════════════════════════════════════
# M-H1: SEEN-SET REGRESSION TRACKER — integrated into WordStatsTracker
# ══════════════════════════════════════════════════════════════
#
# Algorithm summary (from spec M-H1):
#
#   State
#   ─────
#   seen              : set of str   — every unique word touched this session
#   regression_count  : dict[str,int]— how many times each word was re-touched
#   total_regressions : int          — running total of all regression events
#   total_touches     : int          — every touch (new + regression)
#
#   register(word)  — called on every finalised TouchEvent
#   ──────────────
#     total_touches += 1
#     append word to _touch_seq
#     _word_count[word] += 1
#     IF word IN seen:                    ← O(1) hash-set lookup
#         regression_count[word] += 1
#         total_regressions      += 1
#     ELSE:
#         seen.add(word)                  ← O(1) hash-set insert
#
#   snapshot()  — fields added
#   ──────────────────────────
#     hesitation_rate  = total_regressions / total_touches   (0.0 if no touches)
#     top_regressed    = top-5 (word, count) by count desc
#     flagged_words    = words where regression_count > REGRESSION_FLAG_THRESHOLD
#
#   Complexity
#   ──────────
#   Time per touch : O(1)  — single hash lookup + possible insert
#   Memory         : O(V)  — V = unique vocabulary; never grows with total touches

class WordStatsTracker:
    """
    Thread-safe tracker for touch counts, difficulty scores, and
    session-scoped regression detection (M-H1 Seen-Set algorithm).
    """

    def __init__(self):
        self._lock          = threading.Lock()
        self._word_count    = defaultdict(int)
        self._row_count     = defaultdict(int)
        self._word_diff_sum = defaultdict(float)
        self._touch_seq: list[str] = []

        # ── M-H1 regression state ─────────────────────────────
        self._seen              : set            = set()
        self._regression_count  : dict[str, int] = defaultdict(int)
        self._total_regressions : int            = 0
        self._total_touches     : int            = 0

    def register(self, logical_row: int, logical_col: int,
                 difficulty: float = 0.0) -> Optional[str]:
        """
        Record a touch at (logical_row, logical_col).

        Regression detection (M-H1):
          - If the resolved word is already in self._seen → regression.
          - Otherwise → first touch of this word; add to seen.

        Returns the word label (or None if out of bounds).
        """
        word = get_word_from_touch(logical_row, logical_col)
        with self._lock:
            # ── existing tracking ──────────────────────────────
            if word:
                self._word_count[word]       += 1
                self._row_count[logical_row] += 1
                self._word_diff_sum[word]    += difficulty
                self._touch_seq.append(word)

            # ── M-H1: regression check ─────────────────────────
            # Increment total_touches for every resolved word touch.
            if word:
                self._total_touches += 1
                if word in self._seen:
                    # Regression: reader returned to a previously seen word
                    self._regression_count[word] += 1
                    self._total_regressions      += 1
                else:
                    # First encounter: add to the seen set
                    self._seen.add(word)

        return word

    def snapshot(self) -> dict:
        """
        Return a point-in-time snapshot of all tracking state,
        including M-H1 regression metrics.
        """
        with self._lock:
            wc  = dict(self._word_count)
            rc  = dict(self._row_count)
            wds = dict(self._word_diff_sum)
            seq = list(self._touch_seq[-20:])

            # ── M-H1 regression snapshot ───────────────────────
            reg_count        = dict(self._regression_count)
            total_regressions = self._total_regressions
            total_touches     = self._total_touches

        most_touched = max(wc, key=wc.get) if wc else None
        avg_diff = {w: wds[w] / wc[w] for w in wc if wc[w] > 0}
        hardest_word = max(avg_diff, key=avg_diff.get) if avg_diff else None

        # ── M-H1 derived fields ────────────────────────────────
        hesitation_rate = (total_regressions / total_touches
                           if total_touches > 0 else 0.0)

        # Top-5 regressed words, sorted by regression count descending
        top_regressed = sorted(
            reg_count.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Words that have been regressed to more than the flag threshold
        flagged_words = [
            w for w, cnt in reg_count.items()
            if cnt > REGRESSION_FLAG_THRESHOLD
        ]

        return dict(
            word_count=wc,
            row_count=rc,
            most_touched=most_touched,
            hardest_word=hardest_word,
            hardest_word_d=avg_diff.get(hardest_word, 0.0),
            touch_sequence=seq,
            total_registered=sum(wc.values()),
            # ── M-H1 regression fields ─────────────────────────
            hesitation_rate=hesitation_rate,
            total_regressions=total_regressions,
            top_regressed=top_regressed,
            flagged_words=flagged_words,
        )


word_stats = WordStatsTracker()


# ══════════════════════════════════════════════════════════════
# WORD GROUP ACCUMULATOR — multi-block word completion gate
# ══════════════════════════════════════════════════════════════
#
# For multi-block braille words (copper tape spanning 2+ sensor
# columns), this class checks whether all blocks of a word have
# been detected in the touch path before registering the word.
#
# With single-block words (width=1), every touch trivially
# satisfies the check — no behavioral change.
#
# Thread safety: uses word_boundaries_lock (read-only access).

class WordGroupAccumulator:
    """
    Gates word registration until all blocks of a multi-block word
    have been detected in the touch path.

    Usage
    ─────
    accum = WordGroupAccumulator()
    cols_needed = accum.get_required_cols(row, word_label)
    is_complete = accum.check_complete(row, word_label, logical_seq)
    """

    def get_required_cols(self, row: int, word: str) -> set:
        """
        Return the set of columns that must be touched for this word.

        Looks up the word's column range in word_boundaries and returns
        {start, start+1, ..., end}.  Returns empty set if not found.
        """
        with word_boundaries_lock:
            if row not in word_boundaries:
                return set()
            for entry in word_boundaries[row]:
                if entry["word"] == word:
                    return set(range(entry["start"], entry["end"] + 1))
        return set()

    def check_complete(self, row: int, word: str,
                       logical_seq: list) -> bool:
        """
        Check if all required columns for this word appear in logical_seq.

        Parameters
        ----------
        row         : sensor row of the word
        word        : word label
        logical_seq : list of (row, col) tuples from the touch path

        Returns True if every column in the word's range was visited,
        or if the word is a single-block word (trivially complete).
        """
        required = self.get_required_cols(row, word)
        if not required or len(required) <= 1:
            return True  # single-block or not found → always complete

        visited_cols = {col for r, col in logical_seq if r == row}
        return visited_cols >= required


word_group_accum = WordGroupAccumulator()


# ─────────────────────── Geometry helpers ─────────────────────

def map_tx_col(raw_col: int) -> int:
    """Mux wiring correction — used in detection/metrics ONLY."""
    return (raw_col + TX_SHIFT) % GRID


def manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def euclid(a, b) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def path_length(pts) -> float:
    if len(pts) < 2:
        return 0.0
    return float(sum(euclid(pts[i - 1], pts[i]) for i in range(1, len(pts))))


def straight_line(pts) -> float:
    return euclid(pts[0], pts[-1]) if len(pts) >= 2 else 0.0


def count_backtracks(seq) -> int:
    """Count every step that revisits a previously seen cell."""
    if len(seq) < 2:
        return 0
    seen = {seq[0]}
    backtracks = 0
    for cell in seq[1:]:
        if cell in seen:
            backtracks += 1
        else:
            seen.add(cell)
    return backtracks


# ─────────────────────── Serial I/O ───────────────────────────

def read_frame(ser: serial.Serial) -> np.ndarray:
    rows: list = []
    while len(rows) < GRID:
        try:
            line = ser.readline().decode(errors="ignore").strip()
        except serial.SerialException:
            time.sleep(0.01)
            continue
        if not line:
            continue
        parts = line.split()
        # Firmware now appends a CHK{byte} token after the 7 ADC values.
        # Accept rows of length GRID (legacy, no checksum) or GRID+1 (with checksum).
        if len(parts) == GRID + 1 and parts[-1].startswith("CHK"):
            # Validate XOR checksum
            try:
                chk_received = int(parts[-1][3:])
            except ValueError:
                continue  # malformed checksum token — discard
            data_parts = parts[:GRID]
            try:
                vals = list(map(int, data_parts))
            except ValueError:
                continue
            chk_computed = 0
            for v in vals:
                chk_computed ^= (v & 0xFF)
            if chk_computed != chk_received:
                # Checksum mismatch — discard corrupted frame row
                continue
            rows.append(vals)
        elif len(parts) == GRID:
            # Legacy firmware (no checksum) — accept as-is
            try:
                rows.append(list(map(int, parts)))
            except ValueError:
                continue
        else:
            continue
    return np.array(rows, dtype=float)


# ─────────────────────── Touch analysis ───────────────────────

def threshold_mask(delta: np.ndarray) -> np.ndarray:
    return delta >= ROW_THRESHOLDS[:, np.newaxis]


def connected_components_4(mask: np.ndarray):
    visited = np.zeros_like(mask, dtype=bool)
    comps: list = []
    R, C = mask.shape
    for r in range(R):
        for c in range(C):
            if not mask[r, c] or visited[r, c]:
                continue
            stack, comp = [(r, c)], []
            visited[r, c] = True
            while stack:
                rr, cc = stack.pop()
                comp.append((rr, cc))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = rr + dr, cc + dc
                    if (0 <= nr < R and 0 <= nc < C
                            and mask[nr, nc] and not visited[nr, nc]):
                        visited[nr, nc] = True
                        stack.append((nr, nc))
            comps.append(comp)
    return comps


def analyse_touch(delta: np.ndarray) -> dict:
    EMPTY = dict(active=False, peak_rc=None, pressed_count=0,
                 peak_value=0.0, spread_ratio=0.0, confidence=0.0,
                 peaks=[])
    mask = threshold_mask(delta)
    if mask.sum() < MIN_PRESSED_CELLS:
        return EMPTY
    comps = connected_components_4(mask)
    if not comps:
        return EMPTY

    # Score every component and build a peak info dict for each
    scored: list = []
    for comp in comps:
        vals     = np.array([delta[r, c] for r, c in comp], dtype=float)
        peak_idx = int(np.argmax(vals))
        peak_val = float(vals[peak_idx])
        total    = float(vals.sum())
        spread   = total / (peak_val + 1e-9)
        score    = peak_val * 2.0 + total * 0.5 - (spread - 1.0) * 2.5
        scored.append((score, dict(
            peak_rc=comp[peak_idx],
            pressed_count=len(comp),
            peak_value=peak_val,
            spread_ratio=spread,
            confidence=min(1.0, 1.0 / (spread + 1e-9)),
        )))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Hardware Crosstalk Suppression:
    # Multiplexer/ADC capacitance causes phantom signals on the same row or col,
    # especially during lift-off. If a weaker peak shares a row or col with a 
    # stronger peak AND is < 60% of its value, we classify it as a ghost and drop it.
    filtered_scored = []
    for score, info in scored:
        is_ghost = False
        r, c = info["peak_rc"]
        v = info["peak_value"]
        for _, stronger_info in filtered_scored:
            sr, sc = stronger_info["peak_rc"]
            sv = stronger_info["peak_value"]
            if (r == sr or c == sc) and v < 0.6 * sv:
                is_ghost = True
                break
        if not is_ghost:
            filtered_scored.append((score, info))

    # Keep top 2 valid peaks
    peaks = [info for _score, info in filtered_scored[:2]]

    if not peaks:
        return EMPTY

    # Legacy single-peak fields from the best component (backward compat)
    result = dict(peaks[0])
    result["active"] = True
    result["peaks"]  = peaks
    return result


# ─────────────────────── Peak lock ────────────────────────────

class PeakLock:
    """
    Stabilises the detected peak cell across frames.

    update() now returns a (locked_cell, jumped) tuple:
      - jumped=False  → normal intra-block movement or wobble, no action needed
      - jumped=True   → finger has confirmed moved to a far cell (>= NEW_BLOCK_JUMP_THRESHOLD);
                        caller should finalise the old event and start a new one
    """

    def __init__(self):
        self._hist   = deque(maxlen=PEAK_HISTORY_LEN)
        self._locked = None

    def reset(self, seed=None):
        self._hist.clear()
        self._locked = seed
        if seed is not None:
            self._hist.append(seed)

    def update(self, new_peak):
        """
        Returns (locked_cell, jumped: bool).

        jumped=True means the newly confirmed cell is >= NEW_BLOCK_JUMP_THRESHOLD
        Manhattan units from the previous lock — the caller must treat this as
        a brand-new touch on a different block.
        """
        if new_peak is None:
            return self._locked, False

        self._hist.append(new_peak)
        if len(self._hist) < PEAK_HISTORY_LEN:
            return self._locked, False

        candidate = self._hist[-1]
        consensus = sum(1 for p in self._hist if p == candidate)

        if consensus >= max(1, PEAK_HISTORY_LEN - 1):
            jump = manhattan(candidate, self._locked) if self._locked else 0

            if jump >= NEW_BLOCK_JUMP_THRESHOLD:
                # Large confirmed jump → accept the new cell and signal caller
                self._locked = candidate
                return self._locked, True
            elif jump <= MAX_ACCEPTABLE_JUMP:
                # Small movement within same block → accept silently
                self._locked = candidate

        return self._locked, False

    @property
    def cell(self):
        return self._locked


# ─────────────────────── Difficulty helpers ───────────────────

def compute_velocity_profile(path_pts: list, duration: float) -> np.ndarray:
    if len(path_pts) < 2:
        return np.array([], dtype=float)
    n_steps = len(path_pts) - 1
    dt_per_step = duration / n_steps if n_steps > 0 else 1e-9
    speeds = np.array(
        [euclid(path_pts[i], path_pts[i + 1]) / dt_per_step
         for i in range(n_steps)],
        dtype=float,
    )
    return speeds


def count_zero_crossings(signal: np.ndarray) -> int:
    if len(signal) < 2:
        return 0
    diff = np.diff(signal)
    diff[np.abs(diff) < 1e-9] = 0.0
    signs = np.sign(diff)
    nonzero = signs[signs != 0]
    if len(nonzero) < 2:
        return 0
    return int(np.sum(nonzero[:-1] != nonzero[1:]))


def count_reversals(logical_seq: list) -> int:
    """
    Count direction reversals within a single touch's cell path.
    Requires at least 3 cells (A→B→C where B→C reverses A→B direction).
    Returns 0 for single-cell taps (no path).
    """
    if len(logical_seq) < 3:
        return 0
    col_deltas = [logical_seq[i + 1][1] - logical_seq[i][1]
                  for i in range(len(logical_seq) - 1)]
    reversals = 0
    for i in range(1, len(col_deltas)):
        if col_deltas[i - 1] != 0 and col_deltas[i] != 0:
            if np.sign(col_deltas[i]) != np.sign(col_deltas[i - 1]):
                reversals += 1
    return reversals


def count_word_reversals(word_sequence: list, current_word: str) -> int:
    """
    Detect A→B→A session-level word reversals.

    A word reversal occurs when the current word matches the word touched
    2 events ago, AND differs from the immediately previous event — i.e.
    the user went back to a word they had just left:

        ...→ Word_A → Word_B → Word_A  ← reversal detected here

    Each such reversal adds 1 to the difficulty of the word being returned
    to.  Multiple successive reversals (A→B→A→B→A) each count.

    Args:
        word_sequence: The session touch sequence SO FAR (before appending
                       current_word).  Must have at least 2 entries.
        current_word:  The word being finalised right now.

    Returns: 1 if this event is a word-level reversal, else 0.
    """
    if len(word_sequence) < 2:
        return 0
    prev1 = word_sequence[-1]   # word immediately before this
    prev2 = word_sequence[-2]   # word before that
    # Pattern: prev2 → prev1 → current, where current == prev2 != prev1
    if current_word and current_word == prev2 and current_word != prev1:
        return 1
    return 0


def difficulty_score(reversals: int, zero_crossings: int,
                     velocities: np.ndarray,
                     word_reversals: int = 0) -> float:
    """
    Composite difficulty score in the range [0, ~10].

    Four components:
      REV      : within-touch path direction reversals (finger zigzag)
      ZC       : zero-crossings in velocity (hesitation / jitter)
      VEL      : speed term  — sigmoid(mean_vel); 0 for no movement
      WREV     : session-level word reversals (A→B→A pattern, W4 weight)

    Formula: D = W1*REV + W2*ZC + W3*vel_term + W4*WREV

    Single-cell taps: velocities=[], REV=0, ZC=0 → D = W4*WREV only
    (D=0 if no session reversal, D=W4 if the user reversed back to this word)

    Interpretation:
      0.0 – 1.0  : effortless direct touches
      1.0 – 3.0  : moderate effort, some hesitation or reversals
      3.0+       : high reversal / jitter rate (genuinely hard)
    """
    W4 = 1.5   # weight for session-level word reversal

    if len(velocities) == 0:
        return float(W1 * reversals + W2 * zero_crossings + W4 * word_reversals)

    mean_vel = float(velocities.mean())
    vel_term = mean_vel / (mean_vel + 1.0) if mean_vel > 0 else 0.0
    return float(
        W1 * reversals
        + W2 * zero_crossings
        + W3 * vel_term
        + W4 * word_reversals
    )


# ─────────────────────── Per-cell difficulty tracker ──────────

class CellDifficultyTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = {}  # (row, col) → [sum_D, count]

    def record(self, peak_rc_logical, d_score: float):
        if peak_rc_logical is None:
            return
        cell = tuple(peak_rc_logical)
        with self._lock:
            if cell not in self._data:
                self._data[cell] = [0.0, 0]
            self._data[cell][0] += d_score
            self._data[cell][1] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {k: v[0] / v[1] for k, v in self._data.items() if v[1] > 0}


# ══════════════════════════════════════════════════════════════
# M-D2: PER-WORD WELFORD BOOKKEEPER
# ══════════════════════════════════════════════════════════════
#
# Tracks per-word n, mean, M2 (for variance) using Welford's online
# algorithm.  Provides session-wide averages and counts that EWIQR
# cannot.  EWIQR is the diagnostician; Welford is the bookkeeper.
#
# Complexity: O(1) per record.  Memory: O(V) where V = unique words.

class WelfordPerWord:
    """Per-word Welford online mean/variance tracker for touch durations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, list] = {}  # word → [n, mean, M2]

    def record(self, word: str, duration: float) -> None:
        """Update running statistics for *word* with a new *duration*."""
        with self._lock:
            if word not in self._data:
                self._data[word] = [0, 0.0, 0.0]
            rec = self._data[word]
            rec[0] += 1
            delta = duration - rec[1]
            rec[1] += delta / rec[0]
            delta2 = duration - rec[1]
            rec[2] += delta * delta2

    def snapshot(self) -> dict:
        """Return {word: {n, mean, std}} for every tracked word."""
        with self._lock:
            result = {}
            for w, (n, mean, m2) in self._data.items():
                std = (m2 / (n - 1)) ** 0.5 if n > 1 else 0.0
                result[w] = dict(n=n, mean=mean, std=std)
            return result


# ══════════════════════════════════════════════════════════════
# M-D2: EWIQR PER-WORD DIFFICULTY TRACKER
# ══════════════════════════════════════════════════════════════
#
# Algorithm: Exponentially Weighted Interquartile Range (EWIQR)
#
# For each word, maintains a sorted window of (duration, weight) pairs.
# On every new touch:
#   1. All existing weights *= λ  (exponential decay)
#   2. Entries with weight < weight_floor are pruned
#   3. New (duration, 1.0) is inserted maintaining sort order
#
# Weighted percentiles Q1/Q3 are computed by walking cumulative
# weight and recording the duration where cumsum crosses 25%/75%.
# EWIQR = Q3 − Q1 measures *current* inconsistency in the middle
# 50% of touch durations — robust to frequency, outliers, and
# bimodality simultaneously.
#
# Complexity
# ──────────
# record()   : O(m) per word where m = window size (bounded by pruning)
# snapshot() : O(W × m) where W = unique words (sorts are per-word)
# Memory     : O(W × m_avg), independent of session length.

class EWIQRPerWordTracker:
    """
    M-D2: Thread-safe EWIQR per-word difficulty tracker.

    Usage
    ─────
    ewiqr_tracker.record(word, duration)   # called in _finalise_touch()
    snap = ewiqr_tracker.snapshot()        # called in UI loop
    """

    def __init__(self, lam: float = EWIQR_D2_LAMBDA,
                 weight_floor: float = EWIQR_D2_WEIGHT_FLOOR,
                 min_window: int = EWIQR_D2_MIN_WINDOW):
        self._lam          = lam
        self._weight_floor = weight_floor
        self._min_window   = min_window
        self._lock         = threading.Lock()
        # word → sorted list of [duration, weight], sorted ascending by duration
        self._windows: dict[str, list] = defaultdict(list)

    # ── public API ────────────────────────────────────────────

    def record(self, word: str, duration: float) -> None:
        """
        Record a touch duration for *word*.

        Steps (all with lock held):
          1. Decay all existing weights in this word's window by λ
          2. Prune entries below weight_floor
          3. Insert (duration, 1.0) maintaining sort order by duration
        """
        with self._lock:
            window = self._windows[word]

            # Step 1: decay existing weights
            for entry in window:
                entry[1] *= self._lam

            # Step 2: prune below floor
            self._windows[word] = [
                e for e in window if e[1] >= self._weight_floor
            ]
            window = self._windows[word]

            # Step 3: insert new touch maintaining sort order
            # bisect on the duration (index 0 of each [duration, weight] pair)
            durations = [e[0] for e in window]
            pos = bisect.bisect_left(durations, duration)
            window.insert(pos, [duration, 1.0])

    def compute_ewiqr(self, word: str) -> tuple:
        """
        Compute (Q1, Q3, EWIQR, confidence) for a single word.
        Must be called with self._lock held.

        Returns (None, None, None, "cold") if fewer than min_window entries.
        """
        window = self._windows.get(word, [])
        n = len(window)

        if n < self._min_window:
            return (None, None, None, "cold")

        # Compute total weight
        total_weight = sum(e[1] for e in window)
        if total_weight <= 0:
            return (None, None, None, "cold")

        # Find Q1: walk from lowest to highest duration
        q1_threshold = total_weight * 0.25
        q3_threshold = total_weight * 0.75
        accumulated = 0.0
        q1 = None
        q3 = None

        for entry in window:  # already sorted ascending by duration
            accumulated += entry[1]
            if q1 is None and accumulated >= q1_threshold:
                q1 = entry[0]
            if q3 is None and accumulated >= q3_threshold:
                q3 = entry[0]
                break  # both found

        # Fallbacks for edge cases
        if q1 is None:
            q1 = window[0][0]
        if q3 is None:
            q3 = window[-1][0]

        ewiqr = q3 - q1

        # Determine confidence
        if n >= 30:
            confidence = "reliable"
        elif n >= 10:
            confidence = "warming"
        else:
            confidence = "cold"

        return (q1, q3, ewiqr, confidence)

    def snapshot(self) -> dict:
        """
        Full diagnostic snapshot combining EWIQR and Welford data.

        Returns dict with:
          ewiqr_per_word      : {word: ewiqr_value}
          Q1_per_word         : {word: q1_value}
          Q3_per_word         : {word: q3_value}
          confidence_per_word : {word: "cold"/"warming"/"reliable"}
          top5_hardest        : [(word, ewiqr), …]  (max 5, warming+reliable only)
          touch_count_per_word: {word: window_entry_count}
        """
        with self._lock:
            ewiqr_per_word      = {}
            q1_per_word         = {}
            q3_per_word         = {}
            confidence_per_word = {}
            touch_count_per_word = {}

            for word in self._windows:
                q1, q3, ewiqr, conf = self.compute_ewiqr(word)
                touch_count_per_word[word] = len(self._windows[word])
                confidence_per_word[word] = conf
                if ewiqr is not None:
                    ewiqr_per_word[word]  = ewiqr
                    q1_per_word[word]     = q1
                    q3_per_word[word]     = q3

        # Top 5 hardest: rank by EWIQR descending, filter to warming+reliable
        ranked = [
            (w, ewiqr_per_word[w])
            for w in ewiqr_per_word
            if confidence_per_word.get(w) in ("reliable", "warming")
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        top5 = ranked[:5]

        # Build Z_tot: 7×7 masked array of EWIQR mapped to grid positions
        z_tot = np.ma.masked_all((GRID, GRID))
        with word_boundaries_lock:
            for row_idx in range(GRID):
                if row_idx not in word_boundaries:
                    continue
                for entry in word_boundaries[row_idx]:
                    w = entry["word"]
                    if w in ewiqr_per_word:
                        # Fill all columns this word spans
                        for c in range(entry["start"], entry["end"] + 1):
                            if 0 <= c < GRID:
                                z_tot[row_idx, c] = ewiqr_per_word[w]

        return dict(
            ewiqr_per_word=ewiqr_per_word,
            Q1_per_word=q1_per_word,
            Q3_per_word=q3_per_word,
            confidence_per_word=confidence_per_word,
            touch_count_per_word=touch_count_per_word,
            top5_hardest=top5,
            Z_tot=z_tot,
        )


# ══════════════════════════════════════════════════════════════
# M-D3: SKIP STATISTICS ENGINE
# ══════════════════════════════════════════════════════════════
#
# Two-layer architecture with a numpy boolean mask as interface.
#
# Layer 1 — Single-Pass Accumulator
# ──────────────────────────────────
# One sweep across word_boundaries produces four outputs atomically:
#   skip_rate, skipped_words, partially_visited_rows, skip_mask
# Stale keys in word_count are structurally unreachable because
# labels are sourced exclusively from word_boundaries.
#
# Layer 2 — BFS Cluster Analysis
# ──────────────────────────────
# Takes skip_mask as sole input.  Finds connected components of
# True cells via 4-connected BFS.  Classifies each cluster's
# spatial morphology (row-sweep, column-alignment, boundary
# avoidance, saccade drift, singleton noise, scattered gap).
# Clusters with < 4 cells are suppressed as noise.

SKIP_CLUSTER_MIN_SIZE = 4   # clusters smaller than this are noise


def compute_skip_stats(wb: dict, wc: dict) -> dict:
    """
    M-D3 Layer 1 — Single-Pass Accumulator.

    Parameters
    ----------
    wb : dict  — word_boundaries  {row_idx: [{word, start, end}, …]}
    wc : dict  — word_count       {word_label: touch_count}

    Returns
    -------
    dict with keys:
        skip_rate              : float   (percentage 0–100)
        skipped_words          : list[str]  (row-major order)
        partially_visited_rows : list[int]
        skip_mask              : np.ndarray  (7×7 bool)
    """
    # Count total WORDS (not raw cells) — depends on user config
    TOTAL_WORDS = sum(len(wb.get(r, [])) for r in range(GRID))

    skip_count        = 0
    skipped_words     = []
    partially_visited = []
    skip_mask         = np.zeros((GRID, GRID), dtype=bool)

    for row_idx in range(GRID):
        words_in_row      = wb.get(row_idx, [])
        row_total         = len(words_in_row)
        row_touched_count = 0

        for entry in words_in_row:
            label       = entry["word"]
            touch_count = wc.get(label, 0)
            was_touched = (touch_count > 0)

            if not was_touched:
                skipped_words.append(label)
                skip_count += 1
                # Mark ALL columns spanned by this word in skip_mask
                for c in range(entry["start"], entry["end"] + 1):
                    if 0 <= c < GRID:
                        skip_mask[row_idx][c] = True
            else:
                row_touched_count += 1

        # Row is partially visited only if SOME but NOT ALL words touched
        if row_touched_count > 0 and row_touched_count < row_total:
            partially_visited.append(row_idx)

    skip_rate = (skip_count / TOTAL_WORDS) * 100.0 if TOTAL_WORDS > 0 else 0.0

    return dict(
        skip_rate=skip_rate,
        skipped_words=skipped_words,
        partially_visited_rows=partially_visited,
        skip_mask=skip_mask,
        total_words=TOTAL_WORDS,
    )


def _classify_cluster(cells: list) -> dict:
    """
    Classify a single skip cluster by its bounding-box geometry.

    Returns dict with: cells, size, bounding_box, pattern, is_noise.
    """
    size    = len(cells)
    rows    = [r for r, c in cells]
    cols    = [c for r, c in cells]
    min_row, max_row = min(rows), max(rows)
    min_col, max_col = min(cols), max(cols)
    row_span = max_row - min_row + 1
    col_span = max_col - min_col + 1

    if size < SKIP_CLUSTER_MIN_SIZE:
        pattern  = "singleton_noise"
        is_noise = True

    elif row_span == 1 and col_span == GRID:
        pattern  = "row_sweep_failure"
        is_noise = False

    elif row_span == GRID and col_span == 1:
        pattern  = "column_alignment_failure"
        is_noise = False

    elif (min_row <= 1 or max_row >= 5) and (min_col <= 1 or max_col >= 5):
        pattern  = "boundary_avoidance"
        is_noise = False

    elif abs(row_span - col_span) <= 1:
        pattern  = "saccade_drift"
        is_noise = False

    else:
        pattern  = "scattered_attentional_gap"
        is_noise = False

    return dict(
        cells=cells,
        size=size,
        bounding_box=(min_row, min_col, max_row, max_col),
        pattern=pattern,
        is_noise=is_noise,
    )


def compute_skip_clusters(skip_mask: np.ndarray) -> list:
    """
    M-D3 Layer 2 — BFS Cluster Analysis.

    Parameters
    ----------
    skip_mask : np.ndarray  — 7×7 boolean array from compute_skip_stats

    Returns
    -------
    list of cluster dicts, each with:
        cells, size, bounding_box, pattern, is_noise
    """
    DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    visited  = np.zeros((GRID, GRID), dtype=bool)
    clusters = []

    for row in range(GRID):
        for col in range(GRID):
            if skip_mask[row, col] and not visited[row, col]:
                # Seed of a new cluster — BFS
                current_cells = []
                q = deque()
                q.append((row, col))
                visited[row, col] = True

                while q:
                    r, c = q.popleft()
                    current_cells.append((r, c))

                    for dr, dc in DIRECTIONS:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < GRID and 0 <= nc < GRID:
                            if skip_mask[nr, nc] and not visited[nr, nc]:
                                visited[nr, nc] = True
                                q.append((nr, nc))

                clusters.append(_classify_cluster(current_cells))

    return clusters


# ══════════════════════════════════════════════════════════════
# LIVE DUAL-AXIS BAR CHART — Persistent Artist Blit
# ══════════════════════════════════════════════════════════════
#
# Algorithm: PersistentArtistBlit
#
# Allocates every matplotlib artist exactly once during setup.
# On every subsequent update, only the numerical properties of
# those existing objects are mutated — never destroyed, never
# recreated.  Then only the pixels that actually changed are
# repainted via the blit pipeline.
#
# Phase 1 (Setup):  Runs exactly once.  Creates 49 primary bars
#   (Time-on-Task, left axis), 49 count bars (touch count, right
#   axis), error bar stems + caps, 49 asterisk text artists for
#   difficulty annotation, and one horizontal dashed session-avg
#   line.  A full draw is performed and a background pixel-buffer
#   snapshot is captured.
#
# Phase 2 (Update):  Called every UI frame but short-circuits if
#   < 500ms since last update (~2fps).  Mutates bar heights, error
#   bar geometry, axis limits (with hysteresis), asterisk visibility,
#   and h-line y-data.  Then restores the background snapshot, draws
#   all mutated artists on top, and blits only the changed bbox.
#
# Complexity
# ──────────
# Per UI frame (no-op) : O(1) — one timestamp comparison
# Per chart update     : O(W) — W=49 words, property writes
# Memory               : O(W) — fixed artist pool, no GC churn
# ══════════════════════════════════════════════════════════════

BAR_CHART_UPDATE_INTERVAL = 0.5   # seconds — chart updates at ~2fps


class BarChartBlit:
    """
    Persistent Artist Blit dual-axis bar chart.

    Shows per-word Time-on-Task (left Y-axis) and touch counts
    (right Y-axis) with error bars, difficulty asterisks for the
    top-5 hardest words, and a session average h-line.

    All artists are allocated once in setup().  update() mutates
    only numerical properties and blits only changed pixels.
    """

    def __init__(self):
        # ── Data structures from pseudocode ────────────────────
        self.word_list       = []        # ordered array[49] of word labels
        self.primary_bars    = []        # Rectangle artists (left axis, ToT)
        self.count_bars      = []        # Rectangle artists (right axis, count)
        self.error_stems     = None      # LineCollection (49 segments)
        self.error_caps_lo   = None      # Line2D (bottom caps)
        self.error_caps_hi   = None      # Line2D (top caps)
        self.asterisk_texts  = []        # Text artists (all initially invisible)
        self.hline           = None      # Line2D artist (session avg)
        self.background_snap = None      # pixel buffer
        self.last_chart_time = -1e9      # initially −∞
        self.prev_top5       = set()     # set of word indices
        self.left_limit_max  = 0.0
        self.right_limit_max = 0.0
        self.fig             = None
        self.ax_left         = None
        self.ax_right        = None
        self._setup_done     = False

    def setup(self, word_boundaries_dict: dict) -> None:
        """
        Phase 1: Create all artists exactly once.

        Extracts word list in row-major order from word_boundaries,
        creates dual-axis bar chart with error bars, asterisks, and
        h-line, then captures background pixel buffer.
        """
        # ── Extract word list in row-major order ──────────────
        self.word_list = []
        for row_idx in range(GRID):
            entries = word_boundaries_dict.get(row_idx, [])
            for entry in entries:
                self.word_list.append(entry["word"])
        # Word count is dynamic — depends on user block-width config

        n_words = len(self.word_list)
        x_pos   = np.arange(n_words)

        # ── Create figure and axes ────────────────────────────
        self.fig = plt.figure(figsize=(14, 5), facecolor=_BG_DARK)
        self.ax_left  = self.fig.add_subplot(111)
        self.ax_right = self.ax_left.twinx()

        self.ax_left.set_facecolor(_BG_DARK)
        self.fig.patch.set_facecolor(_BG_DARK)

        # ── tab10 palette by row ──────────────────────────────
        tab10 = plt.cm.tab10

        # ── Build per-word row mapping for color assignment ─────
        self._word_row = []   # word_row[i] = sensor row of word i
        for row_idx in range(GRID):
            entries = word_boundaries_dict.get(row_idx, [])
            for _ in entries:
                self._word_row.append(row_idx)

        # ── Create primary bars (ToT, left axis) ──────────────
        self.primary_bars = []
        self.count_bars   = []
        bar_width = 0.35

        for i in range(n_words):
            row = self._word_row[i] if i < len(self._word_row) else 0
            color = tab10(row)

            bar_p = self.ax_left.bar(
                i - bar_width / 2, 0, bar_width,
                color=color, alpha=1.0, edgecolor='none'
            )[0]
            self.primary_bars.append(bar_p)

            bar_c = self.ax_right.bar(
                i + bar_width / 2, 0, bar_width,
                color=color, alpha=0.3, edgecolor='none'
            )[0]
            self.count_bars.append(bar_c)

        # ── Create error bars ─────────────────────────────────
        # Use errorbar() with zero values to create the artists
        err_container = self.ax_left.errorbar(
            x_pos, np.zeros(n_words), yerr=np.zeros(n_words),
            fmt='none', ecolor='#ffffff', elinewidth=0.8,
            capsize=2, capthick=0.6, alpha=0.5
        )
        # err_container is an ErrorbarContainer:
        #   [0] = data line (Line2D, 'none' format → may be empty)
        #   [1] = cap lines tuple of Line2D
        #   [2] = bar lines tuple of LineCollection
        self.error_caps_lo = err_container[1][0] if len(err_container[1]) > 0 else None
        self.error_caps_hi = err_container[1][1] if len(err_container[1]) > 1 else None
        self.error_stems   = err_container[2][0] if len(err_container[2]) > 0 else None

        # ── Create asterisk Text artists ──────────────────────
        self.asterisk_texts = []
        for i in range(n_words):
            txt = self.ax_left.text(
                i, 0, "*",
                ha='center', va='bottom',
                fontsize=14, fontweight='bold',
                color='#ff4444', visible=False
            )
            self.asterisk_texts.append(txt)

        # ── Create h-line (session average) ───────────────────
        self.hline = self.ax_left.axhline(
            y=0, color='#00ffaa', linestyle='--',
            linewidth=1.2, alpha=0.7
        )

        # ── Axis labels and ticks ─────────────────────────────
        self.ax_left.set_xticks(x_pos)
        self.ax_left.set_xticklabels(
            self.word_list, rotation=45, ha='right',
            fontsize=7, color=_FG_MUTED
        )
        self.ax_left.set_ylabel('Time-on-Task (s)', color=_FG_PRIMARY, fontsize=9)
        self.ax_right.set_ylabel('Touch Count', color=_FG_PRIMARY, fontsize=9)
        self.ax_left.tick_params(axis='y', colors=_FG_MUTED)
        self.ax_right.tick_params(axis='y', colors=_FG_MUTED)
        self.ax_left.set_title(
            'Per-Word Performance  (Time-on-Task & Touch Counts)',
            color='white', fontsize=11, fontweight='bold', pad=10
        )
        self.ax_left.set_xlim(-0.5, n_words - 0.5)
        self.ax_left.set_ylim(0, 1.0)
        self.ax_right.set_ylim(0, 1.0)

        # Grid
        self.ax_left.grid(axis='y', color=_GRID_COLOR, linewidth=0.5, alpha=0.5)

        # Spines
        for sp in self.ax_left.spines.values():
            sp.set_edgecolor(_GRID_COLOR)
        for sp in self.ax_right.spines.values():
            sp.set_edgecolor(_GRID_COLOR)

        self.fig.tight_layout()

        # ── Full draw + capture background snapshot ───────────
        self.fig.canvas.draw()
        self.background_snap = self.fig.canvas.copy_from_bbox(
            self.ax_left.bbox
        )

        # ── Register resize handler ───────────────────────────
        self.fig.canvas.mpl_connect('resize_event', self._on_resize)

        self._setup_done = True

    def _on_resize(self, event=None):
        """Resize invalidates the pixel buffer — must recapture."""
        if self._setup_done:
            self.fig.canvas.draw()
            self.background_snap = self.fig.canvas.copy_from_bbox(
                self.ax_left.bbox
            )

    def update(self, tot_per_word: dict, std_per_word: dict,
               word_count: dict, mean_D_per_word: dict,
               session_avg_duration: float) -> None:
        """
        Phase 2: Throttled update (~2fps).

        Mutates existing artist properties and blits only the changed
        bounding box.  Returns immediately if < 500ms since last update.
        """
        if not self._setup_done:
            return

        # ── Step A: Throttle gate ─────────────────────────────
        now = time.time()
        if (now - self.last_chart_time) < BAR_CHART_UPDATE_INTERVAL:
            return
        self.last_chart_time = now

        n_words = len(self.word_list)

        # ── Step B: Mutate primary and count bar heights ──────
        for i in range(n_words):
            word = self.word_list[i]
            self.primary_bars[i].set_height(
                tot_per_word.get(word, 0.0)
            )
            self.count_bars[i].set_height(
                word_count.get(word, 0)
            )

        # ── Step C: Mutate error bar geometry ─────────────────
        if self.error_stems is not None:
            new_segments = []
            cap_lo_y = []
            cap_hi_y = []
            for i in range(n_words):
                word  = self.word_list[i]
                mid   = tot_per_word.get(word, 0.0)
                sigma = std_per_word.get(word, 0.0)
                lo = max(0, mid - sigma)
                hi = mid + sigma
                new_segments.append([(i, lo), (i, hi)])
                cap_lo_y.append(lo)
                cap_hi_y.append(hi)

            self.error_stems.set_segments(new_segments)

            if self.error_caps_lo is not None:
                self.error_caps_lo.set_ydata(cap_lo_y)
            if self.error_caps_hi is not None:
                self.error_caps_hi.set_ydata(cap_hi_y)

        # ── Step D: Axis limit guard (hysteresis) ─────────────
        all_tot = [tot_per_word.get(w, 0.0) for w in self.word_list]
        all_cnt = [word_count.get(w, 0) for w in self.word_list]
        new_left_max  = max(all_tot)  if all_tot else 0.0
        new_right_max = max(all_cnt)  if all_cnt else 0.0

        needs_full_redraw = False

        if (self.left_limit_max == 0 and new_left_max > 0) or \
           (self.left_limit_max > 0 and
            (new_left_max > self.left_limit_max * 1.1 or
             new_left_max < self.left_limit_max * 0.6)):
            self.ax_left.set_ylim(0, max(0.1, new_left_max * 1.15))
            self.left_limit_max = new_left_max
            needs_full_redraw = True

        if (self.right_limit_max == 0 and new_right_max > 0) or \
           (self.right_limit_max > 0 and
            (new_right_max > self.right_limit_max * 1.1 or
             new_right_max < self.right_limit_max * 0.6)):
            self.ax_right.set_ylim(0, max(1.0, new_right_max * 1.15))
            self.right_limit_max = new_right_max
            needs_full_redraw = True

        if needs_full_redraw:
            self.fig.canvas.draw()
            self.background_snap = self.fig.canvas.copy_from_bbox(
                self.ax_left.bbox
            )

        # ── Step E: Asterisk visibility delta ─────────────────
        # Find top 5 words by mean difficulty score
        valid_diff = [
            (i, mean_D_per_word.get(self.word_list[i], 0.0))
            for i in range(n_words)
            if mean_D_per_word.get(self.word_list[i], 0.0) > 0
        ]
        valid_diff.sort(key=lambda x: x[1], reverse=True)
        current_top5 = set(idx for idx, _ in valid_diff[:5])

        entered = current_top5 - self.prev_top5
        exited  = self.prev_top5 - current_top5

        for i in entered:
            word = self.word_list[i]
            y_pos = (tot_per_word.get(word, 0.0)
                     + std_per_word.get(word, 0.0) + 0.05)
            self.asterisk_texts[i].set_y(y_pos)
            self.asterisk_texts[i].set_visible(True)

        for i in exited:
            self.asterisk_texts[i].set_visible(False)

        # Update positions for existing top5 (bar heights may have changed)
        for i in (current_top5 & self.prev_top5):
            word = self.word_list[i]
            y_pos = (tot_per_word.get(word, 0.0)
                     + std_per_word.get(word, 0.0) + 0.05)
            self.asterisk_texts[i].set_y(y_pos)

        self.prev_top5 = current_top5

        # ── Step F: H-line update ─────────────────────────────
        self.hline.set_ydata([session_avg_duration, session_avg_duration])

        # ── Step G: Blit repaint ──────────────────────────────
        if self.background_snap is not None:
            self.fig.canvas.restore_region(self.background_snap)

            # Draw all mutated artists onto restored background
            for bar in self.primary_bars:
                self.ax_left.draw_artist(bar)
            for bar in self.count_bars:
                self.ax_right.draw_artist(bar)

            if self.error_stems is not None:
                self.ax_left.draw_artist(self.error_stems)
            if self.error_caps_lo is not None:
                self.ax_left.draw_artist(self.error_caps_lo)
            if self.error_caps_hi is not None:
                self.ax_left.draw_artist(self.error_caps_hi)

            for txt in self.asterisk_texts:
                if txt.get_visible():
                    self.ax_left.draw_artist(txt)

            self.ax_left.draw_artist(self.hline)

            self.fig.canvas.blit(self.ax_left.bbox)


# ══════════════════════════════════════════════════════════════
# V-4: MEDIAN PRE-FILTER → EMA  —  LIVE WPM TREND
# ══════════════════════════════════════════════════════════════
#
# Two-stage pipeline for producing a smooth WPM trend line:
#
#   Stage 1 — Median Pre-filter (window=3)
#   ───────────────────────────────────────
#   Raw WPM is pathologically noisy: a mixture of genuine typing
#   speed and impulsive event noise (pauses, stumbles, backspaces).
#   The median of the last 3 samples has a 50% breakdown point —
#   it ignores the single most extreme value entirely.  This kills
#   isolated spikes while passing through sustained speed changes.
#
#   Stage 2 — EMA (α=0.15)
#   ───────────────────────
#   Because the pre-filter already removed impulsive noise, the
#   EMA only needs to smooth residual variance.  α=0.15 gives
#   a half-life of ~0.9s at 5fps — fast enough for timely feedback
#   during flow states, slow enough to ignore sub-second stumbles.
#
# Complexity
# ──────────
# on_frame()  : O(1) — sort 3 numbers + one multiply-add
# get_plot_data() : O(N) — one pass over raw_buffer to recompute
#                   the EMA series for the full plot line
# Memory      : O(N) where N ≤ 720 (2 minutes at 6fps)

class WPMTrendTracker:
    """
    V-4: Median Pre-filter → EMA for live WPM trend.

    Produces a smooth, responsive trend line from noisy raw WPM
    samples by separating impulsive noise (median) from sustained
    variance (EMA).

    Usage
    ─────
    wpm_trend.on_frame(current_wpm, timestamp)
    x_raw, y_raw, y_ema, y_max = wpm_trend.get_plot_data()
    """

    def __init__(self, alpha: float = WPM_TREND_ALPHA,
                 median_window: int = WPM_TREND_MEDIAN_WINDOW,
                 buffer_maxlen: int = WPM_TREND_BUFFER_MAXLEN,
                 update_interval: float = WPM_TREND_UPDATE_INTERVAL):
        self._alpha           = alpha
        self._median_window   = median_window
        self._update_interval = update_interval

        self._raw_buffer: deque   = deque(maxlen=buffer_maxlen)   # (timestamp, wpm)
        self._med_window: deque   = deque(maxlen=median_window)   # last N raw WPM values
        self._ema_state: float    = None                          # None until first sample
        self._last_update: float  = 0.0
        self._lock                = threading.Lock()

    # ── public API ────────────────────────────────────────────

    def on_frame(self, current_wpm: float, timestamp: float) -> float:
        """
        Process one raw WPM sample through the two-stage pipeline.

        Throttled to ~5fps (UPDATE_INTERVAL = 0.2s).  Returns the
        current EMA state, or None if throttled / cold-start.
        """
        with self._lock:
            # Throttle to 5fps inside the 60fps render loop
            if (timestamp - self._last_update) < self._update_interval:
                return self._ema_state

            self._last_update = timestamp

            # --- Stage 0: Buffer the raw sample ---
            self._raw_buffer.append((timestamp, current_wpm))

            # --- Stage 1: Median Pre-filter ---
            self._med_window.append(current_wpm)
            sorted_window = sorted(self._med_window)
            pre_filtered  = sorted_window[len(sorted_window) // 2]  # true median

            # --- Stage 2: EMA on pre-filtered value ---
            if self._ema_state is None:
                self._ema_state = pre_filtered              # cold-start: no lag
            else:
                self._ema_state = (self._alpha * pre_filtered
                                   + (1.0 - self._alpha) * self._ema_state)

            return self._ema_state

    def get_plot_data(self) -> tuple:
        """
        Return (x_raw, y_raw, y_ema, y_max) for plotting.

        x_raw : relative timestamps (seconds from session start)
        y_raw : raw WPM samples
        y_ema : EMA series recomputed over the full raw buffer
        y_max : auto-scale ceiling for Y-axis

        Returns ([], [], [], 0) if no data yet.
        """
        with self._lock:
            if not self._raw_buffer:
                return [], [], [], 0

            buf = list(self._raw_buffer)

        session_start = buf[0][0]
        x_raw = [t - session_start for t, _ in buf]
        y_raw = [wpm for _, wpm in buf]

        # Recompute EMA series from pre-filtered values over full history
        y_ema = self._recompute_ema_series(y_raw)

        y_max = max(y_raw) + 10 if y_raw else 10

        return x_raw, y_raw, y_ema, y_max

    def get_current_ema(self) -> float:
        """Return the current EMA value (thread-safe)."""
        with self._lock:
            return self._ema_state if self._ema_state is not None else 0.0

    def reset(self) -> None:
        with self._lock:
            self._raw_buffer.clear()
            self._med_window.clear()
            self._ema_state   = None
            self._last_update = 0.0

    # ── internal ─────────────────────────────────────────────

    def _recompute_ema_series(self, values: list) -> list:
        """
        Recompute the full EMA series over raw values for plot display.

        NOTE: For strict correctness the series should be computed over
        pre-filtered (median) values.  We apply the median pre-filter
        here as well so the plot line matches the live EMA state.
        """
        if not values:
            return []

        result = []
        med_win = deque(maxlen=self._median_window)
        state = None

        for v in values:
            med_win.append(v)
            sorted_w = sorted(med_win)
            pre_filtered = sorted_w[len(sorted_w) // 2]

            if state is None:
                state = pre_filtered
            else:
                state = self._alpha * pre_filtered + (1.0 - self._alpha) * state
            result.append(state)

        return result


# ══════════════════════════════════════════════════════════════
# V-5: INTER-WORD REGRESSION BAR CHART — cla() Full Redraw
# ══════════════════════════════════════════════════════════════
#
# Algorithm: cla()-based stateless redraw at ~2fps
#
# Two layers running at different frequencies share a snapshot:
#
# Layer 1 — Data Capture (60fps, inside UI loop)
# ──────────────────────────────────────────────
# Copies regression_count + flagged_words into snapshot.
# Checks elapsed time; if ≥ 500ms, hands snapshot to Layer 2.
#
# Layer 2 — Chart Redraw (~2fps)
# ──────────────────────────────
# 7-step stateless reconstruction:
#   1. Filter:  discard words with zero regressions
#   2. Sort:    descending by regression count
#   3. Colour:  red if flagged, blue otherwise
#   4. Clear:   ax.cla() — destroys all artists, preserves GridSpec
#   5. Empty:   guard against empty filtered list
#   6. Draw:    barh() + annotations (inside/outside placement)
#   7. Render:  title, xlabel, draw_idle()
#
# Complexity
# ──────────
# Per UI frame (no-op) : O(1) — timestamp comparison
# Per chart update     : O(W log W) — sort ≤20 words + barh()
# Memory               : O(W) — one dict snapshot per update
# ══════════════════════════════════════════════════════════════


class RegressionBarChart:
    """
    V-5: Inter-Word Regression Bar Chart.

    Horizontal bar chart showing which words the reader regresses to
    most.  Uses cla() full-redraw at ~2fps for simplicity and
    correctness — every update is stateless.

    Usage
    ─────
    reg_chart.setup()                       # once, creates figure
    reg_chart.update(regression_count,      # called every UI frame
                     flagged_words)         # (throttled internally)
    """

    # ── Colour palette ────────────────────────────────────────
    COLOR_FLAGGED = "#ff4444"     # red — word exceeded threshold
    COLOR_NORMAL  = "#4488ff"     # blue — below threshold
    COLOR_BG      = _BG_DARK     # figure/axes background
    COLOR_TEXT    = _FG_PRIMARY     # annotation text
    COLOR_EMPTY   = "#666666"     # placeholder text when no data

    def __init__(self):
        self.fig             = None
        self.ax              = None
        self._last_draw_time = 0.0
        self._setup_done     = False

    def setup(self) -> None:
        """
        Create the figure and axes.  Called once before the UI loop.
        The axes content is intentionally left empty — the first
        update() call will populate it.
        """
        self.fig = plt.figure(figsize=(8, 5), facecolor=self.COLOR_BG)
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_facecolor(self.COLOR_BG)
        self.fig.patch.set_facecolor(self.COLOR_BG)

        # Initial placeholder
        self.ax.set_title(
            "Most-Regressed Words  (inter-word regressions)",
            color="white", fontsize=11, fontweight="bold", pad=10
        )
        self.ax.set_xlabel("Regression count", color=_FG_MUTED, fontsize=9)
        self.ax.text(
            0.5, 0.5, "No regressions recorded yet",
            transform=self.ax.transAxes,
            ha="center", va="center",
            fontsize=12, color=self.COLOR_EMPTY,
            fontstyle="italic"
        )
        self.ax.tick_params(colors="#777777")
        for sp in self.ax.spines.values():
            sp.set_edgecolor(_GRID_COLOR)

        self.fig.tight_layout()
        self._setup_done = True

    def update(self, regression_count: dict, flagged_words: list) -> None:
        """
        Layer 1 + Layer 2 combined.

        Called every UI frame (~60fps).  Checks the throttle gate;
        if ≥ REGRESSION_CHART_UPDATE_INTERVAL has elapsed, performs
        the full 7-step cla() redraw.

        Parameters
        ----------
        regression_count : dict[str, int]
            Word → regression count, from WordStatsTracker.
        flagged_words : list[str]
            Words exceeding REGRESSION_FLAG_THRESHOLD.
        """
        if not self._setup_done:
            return

        # ── Layer 1: Throttle gate ────────────────────────────
        now = time.time()
        if (now - self._last_draw_time) < REGRESSION_CHART_UPDATE_INTERVAL:
            return
        self._last_draw_time = now

        # ── Layer 2: Full chart redraw ────────────────────────
        self._redraw(regression_count, flagged_words)

    def _redraw(self, regression_count: dict, flagged_words: list) -> None:
        """
        7-step stateless chart reconstruction.

        Every call produces a complete, consistent chart from the
        current data.  No state from previous draws is referenced.
        """
        ax = self.ax

        # ── Step 1: Filter — keep only words with count > 0 ──
        visible = {
            word: count
            for word, count in regression_count.items()
            if count > 0
        }

        # ── Step 2: Sort — descending by count ────────────────
        sorted_items  = sorted(visible.items(),
                               key=lambda x: x[1], reverse=True)
        sorted_words  = [item[0] for item in sorted_items]
        sorted_counts = [item[1] for item in sorted_items]

        # ── Step 3: Colour assignment ─────────────────────────
        flagged_set = set(flagged_words)
        colours = [
            self.COLOR_FLAGGED if word in flagged_set
            else self.COLOR_NORMAL
            for word in sorted_words
        ]

        # ── Step 4: Clear axes ────────────────────────────────
        ax.cla()

        # ── Step 5: Empty state guard ─────────────────────────
        if not sorted_words:
            ax.text(
                0.5, 0.5, "No regressions recorded yet",
                transform=ax.transAxes,
                ha="center", va="center",
                fontsize=12, color=self.COLOR_EMPTY,
                fontstyle="italic"
            )
            # Skip to Step 7
            self._apply_labels(ax)
            return

        # ── Step 6: Draw bars + annotations ───────────────────
        bars = ax.barh(
            range(len(sorted_words)), sorted_counts,
            color=colours, edgecolor="none", height=0.65,
            alpha=0.9
        )
        ax.set_yticks(range(len(sorted_words)))
        ax.set_yticklabels(sorted_words, fontsize=9, color=self.COLOR_TEXT)
        ax.invert_yaxis()  # highest count at top

        # Annotations: count label placed inside or outside bar
        max_count = max(sorted_counts) if sorted_counts else 1
        threshold = max_count * 0.3  # bars shorter than 30% of max → label outside

        for i, count in enumerate(sorted_counts):
            if count > threshold and count >= 2:
                # Inside the bar, right-aligned
                x_pos = count - max_count * 0.02
                ax.text(
                    x_pos, i, str(count),
                    ha="right", va="center",
                    fontsize=9, fontweight="bold",
                    color="white"
                )
            else:
                # Outside the bar, left-aligned
                x_pos = count + max_count * 0.02
                ax.text(
                    x_pos, i, str(count),
                    ha="left", va="center",
                    fontsize=9, fontweight="bold",
                    color=self.COLOR_TEXT
                )

        # X-axis styling
        ax.set_xlim(0, max(1, max_count * 1.15))
        ax.grid(axis="x", color=_GRID_COLOR, linewidth=0.5, alpha=0.5)

        # ── Step 7: Labels + render ───────────────────────────
        self._apply_labels(ax)

    def _apply_labels(self, ax) -> None:
        """Set title, xlabel, spine colours, and post draw_idle()."""
        ax.set_title(
            "Most-Regressed Words  (inter-word regressions)",
            color="white", fontsize=11, fontweight="bold", pad=10
        )
        ax.set_xlabel("Regression count", color=_FG_MUTED, fontsize=9)
        ax.tick_params(colors="#777777")
        for sp in ax.spines.values():
            sp.set_edgecolor(_GRID_COLOR)
        ax.set_facecolor(self.COLOR_BG)

        self.fig.canvas.draw_idle()


# ══════════════════════════════════════════════════════════════
# V-6: 3D SURFACE MONITOR — Interactive Surface Replacement
# ══════════════════════════════════════════════════════════════
#
# Algorithm: Surface Replacement
#
# The 3D view plots per-cell metrics as a surface over the 7×7
# sensor grid.  Two Z-surfaces are selectable via RadioButtons:
#   - Time-on-Task (Z_tot): mean touch duration from Welford
#   - Mean Difficulty (Z_diff): EWIQR difficulty score per word
#
# Toggling replaces ONLY the PolyCollection surface artist.
# The Axes3D object, wireframe, base labels, and camera view
# angle are preserved across toggles — no flicker, no reset.
#
# Throttled at 2fps to match other chart update cadences.
#
# Complexity
# ──────────
# init    : O(W)   — one surface plot + W text labels
# toggle  : O(1)   — remove one artist + plot one surface
# Memory  : O(W)   — two 7×7 arrays, W text artists
# ══════════════════════════════════════════════════════════════


class Monitor3D:
    """
    V-6: Interactive 3D Surface Monitor with RadioButtons toggle.

    Visualises per-cell Time-on-Task or Mean Difficulty as a
    3D surface over the 7×7 sensor grid.  Surface replacement
    preserves the axes, wireframe, base labels, and view angle.

    Usage
    ─────
    monitor_3d.init_3d_monitor(word_grid)
    monitor_3d.update_data(Z_tot_new, Z_diff_new)   # each UI frame
    """

    def __init__(self):
        self.figure        = None
        self.axes_3d       = None
        self.X             = None
        self.Y             = None
        self.Z_tot         = np.zeros((GRID, GRID))
        self.Z_diff        = np.zeros((GRID, GRID))
        self.current_surf  = None
        self.current_mode  = 'tot'
        self.last_update   = 0.0
        self._radio        = None
        self._setup_done   = False

    def init_3d_monitor(self, word_grid: list) -> None:
        """
        PROCEDURE: init_3d_monitor

        Creates the 3D figure, plots the initial surface (ToT),
        adds wireframe overlay, base labels, and RadioButtons.
        """
        # Build meshgrid
        x = np.arange(GRID)
        y = np.arange(GRID)
        self.X, self.Y = np.meshgrid(x, y)

        # Create figure and 3D axes
        self.figure = plt.figure(figsize=(10, 7), facecolor=_BG_DARK)
        self.axes_3d = self.figure.add_subplot(111, projection='3d')
        self.axes_3d.set_facecolor(_BG_DARK)
        self.figure.patch.set_facecolor(_BG_DARK)

        # Plot initial surface (ToT)
        self.current_surf = self.axes_3d.plot_surface(
            self.X, self.Y, self.Z_tot,
            cmap='hot_r', alpha=0.9, edgecolor='none'
        )
        self.current_mode = 'tot'

        # Add wireframe overlay (persistent across toggles)
        self.axes_3d.plot_wireframe(
            self.X, self.Y, self.Z_tot,
            alpha=0.3, color='gray', linewidth=0.5
        )

        # Add base-plane labels (Z=0 plane, bottom of grid)
        self._add_base_labels(word_grid)

        # Configure axes
        self.axes_3d.set_xlabel('Column (0-6)', fontsize=10, color=_FG_PRIMARY)
        self.axes_3d.set_ylabel('Row (0-6)', fontsize=10, color=_FG_PRIMARY)
        self.axes_3d.set_zlabel('Time-on-Task (sec)', fontsize=10, color=_FG_PRIMARY)
        self.axes_3d.set_xlim(0, 6)
        self.axes_3d.set_ylim(0, 6)

        # Style 3D axes panes and tick labels
        self.axes_3d.tick_params(colors=_FG_MUTED)
        self.axes_3d.set_title(
            '3D Surface Monitor  [V-6]',
            color='white', fontsize=12, fontweight='bold', pad=15
        )

        # Set view angle (persistent across surface replacements)
        self.axes_3d.view_init(elev=35, azim=225)

        # Create RadioButtons widget
        radio_ax = self.figure.add_axes([0.7, 0.1, 0.15, 0.15])
        radio_ax.set_facecolor('#1a1a2e')
        self._radio = RadioButtons(
            ax=radio_ax,
            labels=['Time-on-Task', 'Mean Difficulty'],
            active=0
        )
        # Style the radio button labels
        for label in self._radio.labels:
            label.set_color(_FG_PRIMARY)
            label.set_fontsize(9)

        # Bind callback to toggle_z
        self._radio.on_clicked(self._on_radio_click)

        self.figure.canvas.draw_idle()
        self._setup_done = True

    def _add_base_labels(self, word_grid: list) -> None:
        """
        PROCEDURE: add_base_labels

        Place word labels on Z=0 base plane, slightly below zero.
        """
        label_z = 0 - 0.5  # slightly below zero

        for i in range(min(GRID, len(word_grid))):
            for j in range(min(GRID, len(word_grid[i]))):
                item = word_grid[i][j]
                # Handle (word, width) tuples and plain strings
                word = item[0] if isinstance(item, (tuple, list)) else item

                if word and word != "":
                    self.axes_3d.text(
                        x=j, y=i, z=label_z,
                        s=word,
                        fontsize=6, ha='center', va='top',
                        color='gray', alpha=0.7
                    )

    def _toggle_z(self, label_str: str) -> None:
        """
        PROCEDURE: toggle_z

        Core Algorithm: Surface Replacement

        Steps:
          1. Remove old surface (only the PolyCollection)
          2. Update Z-axis label
          3. Plot new surface
          4. Redraw
          5. Update state
        """
        # Throttle to 2fps (SURFACE_3D_UPDATE_INTERVAL = 0.5s)
        now = time.time()
        if (now - self.last_update) < SURFACE_3D_UPDATE_INTERVAL:
            return
        self.last_update = now

        # Determine mode from radio button label
        if label_str == 'Time-on-Task':
            new_mode = 'tot'
            Z_new = self.Z_tot
            zlabel = 'Time-on-Task (sec)'
        elif label_str == 'Mean Difficulty':
            new_mode = 'diff'
            Z_new = self.Z_diff
            zlabel = 'Mean Difficulty (D score)'
        else:
            return

        # Early exit if mode unchanged
        if new_mode == self.current_mode:
            return

        # --- Core Algorithm: Surface Replacement ---

        # STEP 1: Remove old surface (only the PolyCollection)
        if self.current_surf is not None:
            try:
                if self.current_surf in self.axes_3d.collections:
                    self.current_surf.remove()
            except (ValueError, AttributeError):
                pass  # already removed or stale reference
            # AXES OBJECT AND VIEW ANGLE PRESERVED ✓

        # STEP 2: Update Z-axis label
        self.axes_3d.set_zlabel(zlabel, fontsize=10, color=_FG_PRIMARY)

        # STEP 3: Plot new surface
        self.current_surf = self.axes_3d.plot_surface(
            self.X, self.Y, Z_new,
            cmap='hot_r', alpha=0.9, edgecolor='none'
        )
        # wireframe persists from init; keep old grid overlay

        # STEP 4: Redraw
        self.figure.canvas.draw_idle()

        # STEP 5: Update state
        self.current_mode = new_mode

        print("Toggled to: " + new_mode)

    def _on_radio_click(self, label: str) -> None:
        """
        PROCEDURE: on_radio_click

        Callback from RadioButtons.on_clicked().
        """
        self._toggle_z(label)

    def update_data(self, Z_tot_new: np.ndarray, Z_diff_new: np.ndarray) -> None:
        """
        Update the stored Z arrays with fresh data from Welford / EWIQR.

        If the current mode's data has changed, re-plot the surface.
        Throttled to 2fps.
        """
        if not self._setup_done:
            return

        self.Z_tot  = Z_tot_new.copy()
        self.Z_diff = Z_diff_new.copy()

        # Throttle surface re-plot to 2fps
        now = time.time()
        if (now - self.last_update) < SURFACE_3D_UPDATE_INTERVAL:
            return
        self.last_update = now

        # Re-plot the currently active surface with new data
        Z_active = self.Z_tot if self.current_mode == 'tot' else self.Z_diff

        if self.current_surf is not None:
            try:
                if self.current_surf in self.axes_3d.collections:
                    self.current_surf.remove()
            except (ValueError, AttributeError):
                pass

        self.current_surf = self.axes_3d.plot_surface(
            self.X, self.Y, Z_active,
            cmap='hot_r', alpha=0.9, edgecolor='none'
        )

        self.figure.canvas.draw_idle()


# ══════════════════════════════════════════════════════════════
# V-7: VELOCITY PROFILE OVERLAY — Last-N Touch Velocity Monitor
# ══════════════════════════════════════════════════════════════
#
# Algorithm: Overlay + Exponentially Weighted Mean
#
# Stores the last N (20) velocity arrays in a deque.  Each UI
# update draws:
#   - Past events as light gray lines (alpha=0.15)
#   - Most recent event as bold blue line (alpha=1.0)
#   - Weighted mean velocity as orange dashed line
#
# The weighted mean uses exponential decay (alpha_weight=0.15)
# so recent events dominate without a hard cliff.  Shorter
# arrays are zero-padded on the right to the length of the
# longest event in the window.
#
# Complexity
# ──────────
# on_frame()           : O(1) — deque append + timestamp check
# update_velocity_plot : O(N × L) — N events × max event length
# Memory               : O(N × L_avg)
# ══════════════════════════════════════════════════════════════


class VelocityProfileMonitor:
    """
    V-7: Velocity Profile Overlay.

    Overlays the last 20 touch velocity arrays on a single axes
    with an exponentially weighted mean.  Throttled at 5fps.

    Usage
    ─────
    vel_profile.init_velocity_plot()     # once, creates figure + axes
    vel_profile.on_frame(vel_array, ts)  # called per touch event
    # (the monitor updates its own plot internally)
    """

    def __init__(self,
                 n_overlay: int = VEL_PROFILE_N_OVERLAY,
                 alpha_weight: float = VEL_PROFILE_ALPHA_WEIGHT,
                 update_interval: float = VEL_PROFILE_UPDATE_INTERVAL):
        self._n_overlay       = n_overlay
        self._alpha_weight    = alpha_weight
        self._update_interval = update_interval

        self._velocity_history: deque = deque(maxlen=n_overlay)
        self._lock            = threading.Lock()

        # matplotlib objects (set up in init_velocity_plot)
        self.figure       = None
        self.axes         = None
        self.lines_past   = []       # list of Line2D (gray, alpha=0.15)
        self.line_recent  = None     # Line2D (bold blue)
        self.line_mean    = None     # Line2D (orange dashed)
        self._last_update = 0.0
        self._setup_done  = False
        self._pending_render = False  # set by metrics_thread, consumed by UI loop

    # ── setup ─────────────────────────────────────────────────

    def init_velocity_plot(self) -> None:
        """
        PROCEDURE: init_velocity_plot

        Creates the figure, axes, and all persistent Line2D artists.
        Past-event lines are pre-allocated for efficiency.
        """
        self.figure = plt.figure(figsize=(8, 5), facecolor=_BG_DARK)
        self.axes   = self.figure.add_subplot(111)
        self.axes.set_facecolor(_BG_DARK)
        self.figure.patch.set_facecolor(_BG_DARK)

        # Placeholder lines — most recent event (bold blue)
        self.line_recent, = self.axes.plot(
            [], [], color='#1f77b4', linewidth=2.5, alpha=1.0,
            label='Most recent'
        )

        # Weighted mean (orange dashed)
        self.line_mean, = self.axes.plot(
            [], [], color='#ff7f0e', linewidth=2, alpha=0.8,
            linestyle='--', label='Weighted mean'
        )

        # Pre-allocate past-event lines (N-1 gray lines)
        self.lines_past = []
        for _ in range(self._n_overlay - 1):
            line, = self.axes.plot(
                [], [], color='gray', linewidth=0.8, alpha=0.15
            )
            self.lines_past.append(line)

        # Zero reference line
        self.axes.axhline(
            y=0, color='white', linewidth=0.5, linestyle='-', alpha=0.3
        )

        # Labels and styling
        self.axes.set_xlabel('Step index', fontsize=9, color=_FG_MUTED)
        self.axes.set_ylabel('Velocity (cells/sec)', fontsize=9,
                             color=_FG_MUTED)
        self.axes.set_title(
            'Velocity Profile — last 20 touches  [V-7]',
            fontsize=11, fontweight='bold', color='white', pad=10
        )
        self.axes.legend(loc='upper right', fontsize=8, framealpha=0.3,
                         facecolor=_BG_DARK, edgecolor=_BG_BORDER,
                         labelcolor=_FG_PRIMARY)
        self.axes.grid(True, alpha=0.3, color=_GRID_COLOR)
        self.axes.tick_params(colors='#777777')
        for sp in self.axes.spines.values():
            sp.set_edgecolor(_GRID_COLOR)

        self.figure.tight_layout()
        self._setup_done = True

    # ── data ingestion ────────────────────────────────────────

    def on_frame(self, new_velocity_array: np.ndarray,
                 timestamp: float) -> None:
        """
        PROCEDURE: on_frame

        Called when a new touch event's velocity array is computed.
        Appends to the deque (auto-pops oldest if len > N) and
        triggers a throttled plot update.
        """
        if len(new_velocity_array) < 1:
            return  # skip events with no velocity information

        with self._lock:
            self._velocity_history.append(np.array(new_velocity_array))

        # Mark that new data is available for the main thread to render.
        # Do NOT call _update_velocity_plot here — this method runs in
        # metrics_thread.  Any matplotlib artist access from a background
        # thread crashes with RuntimeError: main thread is not in main loop.
        self._pending_render = True

    # ── weighted mean computation ─────────────────────────────

    @staticmethod
    def _compute_weighted_mean_velocity(
        vels: list, alpha_weight: float
    ) -> tuple:
        """
        PROCEDURE: compute_weighted_mean_velocity

        Aggregate velocity arrays with exponential decay: recent
        events (high index) have weight exp(alpha × (i − N)).
        Shorter arrays are zero-padded on the right.

        Returns (mean_vel, weights) or (None, None) if no valid data.
        """
        # Filter out events that are too short for velocity
        vels_valid = [v for v in vels if len(v) >= 2]
        if not vels_valid:
            return None, None

        max_len = max(len(v) for v in vels_valid)

        padded  = []
        weights = []

        for i, v in enumerate(vels_valid):
            # Pad shorter arrays with 0 on the right
            v_padded = np.pad(v, (0, max_len - len(v)),
                              mode='constant', constant_values=0)
            padded.append(v_padded)

            # Weight: recent events (high i) have exp(alpha × i)
            weight = np.exp(alpha_weight * (i - len(vels_valid)))
            weights.append(weight)

        # Normalize weights to sum=1
        weights_sum = sum(weights)
        if weights_sum <= 0:
            return None, None
        weights = [w / weights_sum for w in weights]

        # Weighted mean: sum(w_i × v_i) per step
        mean_vel = np.zeros(max_len)
        for i, v_pad in enumerate(padded):
            mean_vel += weights[i] * v_pad

        return mean_vel, weights

    # ── plot update ───────────────────────────────────────────

    def _update_velocity_plot(self, timestamp: float) -> None:
        """
        PROCEDURE: update_velocity_plot

        5-stage update:
          1. Plot all past events (light gray lines)
          2. Plot most recent event (bold blue)
          3. Plot weighted mean velocity (orange dashed)
          4. Auto-scale axes
          5. Redraw (draw_idle)
        """
        if not self._setup_done:
            return

        self._last_update = timestamp

        with self._lock:
            if len(self._velocity_history) == 0:
                return
            vels = list(self._velocity_history)  # snapshot

        N = len(vels)

        # --- Stage 1: Plot all past events (light gray lines) ---
        for i in range(N - 1):
            v = vels[i]
            if len(v) < 2:
                self.lines_past[i].set_data([], [])
                continue
            x = np.arange(len(v))
            self.lines_past[i].set_data(x, v)

        # Clear unused line slots if N < n_overlay
        for i in range(max(0, N - 1), len(self.lines_past)):
            self.lines_past[i].set_data([], [])

        # --- Stage 2: Plot most recent event (bold blue line) ---
        v_recent = vels[-1]
        if len(v_recent) >= 2:
            x_recent = np.arange(len(v_recent))
            self.line_recent.set_data(x_recent, v_recent)
        else:
            self.line_recent.set_data([], [])

        # --- Stage 3: Plot weighted mean velocity (orange dashed) ---
        mean_vel, _ = self._compute_weighted_mean_velocity(
            vels, self._alpha_weight
        )
        if mean_vel is not None:
            x_mean = np.arange(len(mean_vel))
            self.line_mean.set_data(x_mean, mean_vel)
        else:
            self.line_mean.set_data([], [])

        # --- Stage 4: Auto-scale axes ---
        all_vels = []
        for vel_arr in vels:
            if len(vel_arr) >= 2:
                all_vels.extend(vel_arr.tolist())

        if all_vels:
            v_max = max(all_vels)
            self.axes.set_ylim(-0.1, max(0.5, v_max * 1.1))

        max_step = max(len(v) for v in vels)
        self.axes.set_xlim(-1, max(2, max_step))

        # --- Stage 5: Trigger redraw ---
        # Skip draw_idle() here — the UI loop calls fig_menu.canvas.draw_idle()
        # unconditionally at the end of every frame.  Calling it here too
        # would cause a double-render and increase latency.
        # (Setting stale=True is enough for the main-loop draw_idle to pick up.)
        if self.axes is not None:
            self.axes.stale = True



# ══════════════════════════════════════════════════════════════
# V-8: PATH EFFICIENCY PLOT — Scatter + LOWESS Trend
# ══════════════════════════════════════════════════════════════
#
# Algorithm: Colour-coded scatter plot of per-event path efficiency
# (η = straight_line / path_length) with a LOWESS trend line
# recomputed every LOWESS_RECOMPUTE_INTERVAL events, plus a
# proficiency target reference at η=0.8.
#
# LOWESS (LOcally WEighted Scatterplot Smoothing) is a non-parametric
# smoother from statsmodels.  If statsmodels is not installed, a
# degree-2 polynomial fallback is used instead.
#
# Colour tiers:
#   green  (η ≥ 0.8)  — proficient
#   orange (η ≥ 0.5)  — developing
#   red    (η < 0.5)  — struggling
#
# Complexity
# ──────────
# on_event_recorded : O(1) — append + timestamp check
# update_efficiency_plot : O(N) — rebuild scatter + conditional LOWESS
# LOWESS recompute : O(N) — every LOWESS_RECOMPUTE_INTERVAL events
# Memory : O(N) — one float per event
# ══════════════════════════════════════════════════════════════

# Detect statsmodels availability at import time
_USE_LOWESS = False
try:
    # pyrefly: ignore [missing-import]
    from statsmodels.nonparametric.smoothers_lowess import lowess as _sm_lowess
    _USE_LOWESS = True
except ImportError:
    print("Warning: statsmodels not available. Using polynomial fallback for efficiency trend.")
    _USE_LOWESS = False


class EfficiencyPlot:
    """
    V-8: Path Efficiency Scatter Plot with LOWESS/Polynomial trend.

    Plots per-event path efficiency (η) as colour-coded scatter points
    overlaid with a non-parametric trend line and a proficiency target
    reference at η=0.8.

    Usage
    ─────
    eff_plot.init_efficiency_plot()               # once, creates figure
    eff_plot.on_event_recorded(η, event_count, t) # called per touch event
    """

    # ── Colour palette ─────────────────────────────────────────
    COLOR_PROFICIENT  = '#2ca02c'   # green   η ≥ 0.8
    COLOR_DEVELOPING  = '#ff7f0e'   # orange  η ≥ 0.5
    COLOR_STRUGGLING  = '#d62728'   # red     η < 0.5
    COLOR_BG          = _BG_DARK

    def __init__(self,
                 lowess_interval: int = EFFICIENCY_LOWESS_RECOMPUTE_INTERVAL,
                 update_interval: float = EFFICIENCY_PLOT_UPDATE_INTERVAL,
                 lowess_frac: float = EFFICIENCY_LOWESS_FRAC):
        # Data
        self.efficiency_history: list = []   # η per event
        self.event_indices: list      = []   # 0, 1, 2, …

        # matplotlib objects (created in init_efficiency_plot)
        self.figure      = None
        self.axes        = None
        self.scatter     = None       # PathCollection
        self.trend_line  = None       # Line2D
        self.conn_line   = None       # Line2D (connecting line)

        # LOWESS cache
        self._lowess_interval    = lowess_interval
        self._lowess_frac        = lowess_frac
        self._last_lowess_compute = 0
        self._cached_trend_x     = None
        self._cached_trend_y     = None

        # Throttle
        self._update_interval = update_interval
        self._last_update     = 0.0
        self._setup_done      = False
        self._lock            = threading.Lock()
        self._pending_render  = False  # set by metrics_thread, consumed by UI loop

        # Running average for main-window display
        self._eff_sum  = 0.0
        self._eff_count = 0

    # ── setup ─────────────────────────────────────────────────

    def init_efficiency_plot(self) -> None:
        """
        PROCEDURE: init_efficiency_plot

        Creates figure, axes, placeholder scatter + trend line,
        proficiency reference at η=0.8, and grid styling.
        """
        self.figure = plt.figure(figsize=(8, 5), facecolor=self.COLOR_BG)
        self.axes   = self.figure.add_subplot(111)
        self.axes.set_facecolor(self.COLOR_BG)
        self.figure.patch.set_facecolor(self.COLOR_BG)

        # Placeholder scatter (empty)
        self.scatter = self.axes.scatter(
            [], [], s=30, alpha=0.6, zorder=3
        )

        # Placeholder trend line (empty)
        self.trend_line, = self.axes.plot(
            [], [], color='orange', linewidth=2.5, alpha=0.9,
            label='Trend (LOWESS)', zorder=4
        )

        # Reference line at η=0.8 (proficiency target)
        self.axes.axhline(
            y=0.8, color='green', linewidth=1.5, linestyle='--',
            alpha=0.5, label='Proficiency target (η=0.8)', zorder=2
        )

        # Labels and styling
        self.axes.set_xlabel('Event index', fontsize=9, color=_FG_MUTED)
        self.axes.set_ylabel('Path efficiency (η)', fontsize=9,
                             color=_FG_MUTED)
        self.axes.set_title(
            'Path Efficiency Over Session  [V-8]',
            fontsize=11, fontweight='bold', color='white', pad=10
        )
        self.axes.set_ylim([0, 1.05])
        self.axes.set_xlim([0, 10])
        self.axes.legend(
            loc='lower right', fontsize=8, framealpha=0.3,
            facecolor=self.COLOR_BG, edgecolor=_BG_BORDER,
            labelcolor=_FG_PRIMARY
        )
        self.axes.grid(True, alpha=0.3, color=_GRID_COLOR)
        self.axes.tick_params(colors='#777777')
        for sp in self.axes.spines.values():
            sp.set_edgecolor(_GRID_COLOR)

        self.figure.tight_layout()
        self._setup_done = True

    # ── trend computation ─────────────────────────────────────

    @staticmethod
    def _compute_lowess_trend(eff_history, evt_indices, frac=0.3):
        """
        PROCEDURE: compute_lowess_trend

        Non-parametric LOWESS smoothing via statsmodels.
        Falls back to polynomial degree-2 if statsmodels missing.

        Returns (trend_x, trend_y) as numpy arrays.
        """
        eff_arr = np.array(eff_history, dtype=float)
        idx_arr = np.array(evt_indices, dtype=float)

        if _USE_LOWESS:
            try:
                trend_data = _sm_lowess(
                    endog=eff_arr,
                    exog=idx_arr,
                    frac=frac,
                    it=3
                )
                return trend_data[:, 0], trend_data[:, 1]
            except Exception:
                # Fall through to polynomial
                pass

        # Fallback: polynomial degree 2
        return EfficiencyPlot._compute_poly_trend(eff_arr, idx_arr, deg=2)

    @staticmethod
    def _compute_poly_trend(eff_arr, idx_arr, deg=2):
        """
        PROCEDURE: compute_poly_trend

        Fallback: simple polynomial fit (no statsmodels).
        Returns (trend_x, trend_y) as numpy arrays.
        """
        coeffs  = np.polyfit(idx_arr, eff_arr, deg=deg)
        poly_fn = np.poly1d(coeffs)
        trend_y = poly_fn(idx_arr)
        # Clip to [0, 1] for visual sanity
        trend_y = np.clip(trend_y, 0.0, 1.0)
        return idx_arr, trend_y

    # ── event ingestion ───────────────────────────────────────

    def on_event_recorded(self, eta_efficiency: float,
                          event_count: int,
                          timestamp: float) -> None:
        """
        PROCEDURE: on_event_recorded

        Called after each touch event computes path efficiency.
        Appends to history and triggers throttled plot update.
        """
        with self._lock:
            self.efficiency_history.append(eta_efficiency)
            self.event_indices.append(event_count)
            self._eff_sum   += eta_efficiency
            self._eff_count += 1

        # Mark that new data is available for the main thread to render.
        self._pending_render = True

    def get_avg_efficiency(self) -> float:
        """Return the session-average continuous-contact path efficiency."""
        with self._lock:
            if self._eff_count == 0:
                return 1.0
            return self._eff_sum / self._eff_count

    # ── plot update ───────────────────────────────────────────

    def _update_efficiency_plot(self, event_count: int,
                                timestamp: float) -> None:
        """
        Full redraw: connected line + scatter dots + trend + fill bands.
        """
        if not self._setup_done:
            return

        self._last_update = timestamp

        with self._lock:
            if len(self.efficiency_history) < 2:
                return
            eff_hist = list(self.efficiency_history)
            evt_idx  = list(self.event_indices)

        # --- Stage 1: Update scatter points ---
        colors = []
        for eta in eff_hist:
            if eta >= 0.8:
                colors.append(self.COLOR_PROFICIENT)
            elif eta >= 0.5:
                colors.append(self.COLOR_DEVELOPING)
            else:
                colors.append(self.COLOR_STRUGGLING)

        self.scatter.set_offsets(
            np.column_stack([evt_idx, eff_hist])
        )
        self.scatter.set_facecolor(colors)

        # --- Stage 1b: Update connecting line ---
        if self.conn_line is not None:
            self.conn_line.set_data(evt_idx, eff_hist)

        # --- Stage 2: Recompute LOWESS trend every N events ---
        if (event_count - self._last_lowess_compute) >= self._lowess_interval:
            self._cached_trend_x, self._cached_trend_y = \
                self._compute_lowess_trend(
                    eff_hist, evt_idx, frac=self._lowess_frac
                )
            self._last_lowess_compute = event_count

        # --- Stage 3: Plot cached trend line ---
        if self._cached_trend_y is not None:
            self.trend_line.set_data(
                self._cached_trend_x, self._cached_trend_y
            )
        else:
            self.trend_line.set_data([], [])

        # --- Stage 4: Auto-scale x-axis ---
        if evt_idx:
            x_max = max(evt_idx) + 5
            self.axes.set_xlim([0, x_max])

        # --- Stage 5: Trigger redraw ---
        try:
            if self.figure is not None:
                self.figure.canvas.draw_idle()
        except Exception:
            pass


# ═══════════════ SLIDING WINDOW WPM COUNTER ═══════════════════
#
# O(1) circular bucket implementation as specified in M-S1.
#
# The 60-second window is divided into 60 integer buckets — one
# per wall-clock second.  A single running total is kept so that
# get_wpm() is a pure integer read with zero loops or eviction.
#
# Thread safety: a single threading.Lock guards all mutations.
# The lock is held for at most ~4 arithmetic ops so contention
# is negligible even at high touch rates.
#
# Bucket lifecycle
# ────────────────
#   record_touch()
#     now_slot  = int(time.time()) % 60
#     if slot changed → subtract old bucket value from total,
#                        zero the bucket, update last_slot
#     buckets[now_slot] += 1
#     total             += 1
#
#   get_wpm()
#     now_slot  = int(time.time()) % 60
#     if slot changed → same expiry step as above
#     return total          # touches in the last 60 s = WPM
#
# Why total == WPM directly
# ─────────────────────────
# Each finalised TouchEvent represents one word read.  The total
# is the count of words whose touch completed within the last 60
# seconds, which is exactly words-per-minute by definition.
# ══════════════════════════════════════════════════════════════

class SlidingWindowWPM:
    """
    Exact, O(1) words-per-minute counter using a 60-bucket circular
    buffer.  One bucket per second; a running total avoids any loop
    on read.  Memory is fixed at 60 integers for all time.
    """

    WINDOW = 60  # seconds — must equal ROLL_WINDOW for consistency

    def __init__(self):
        self._lock      = threading.Lock()
        self._buckets   = [0] * self.WINDOW   # circular buffer
        self._total     = 0                    # always == sum(buckets)
        self._last_slot = int(time.time()) % self.WINDOW

    # ── internal: expire stale slots when seconds have ticked ──
    def _maybe_expire(self, now_slot: int) -> None:
        """
        Called with the lock held.
        If one or more seconds have elapsed, every intervening slot
        holds data from ≥60 seconds ago and must be zeroed.  A simple
        forward walk from last_slot+1 to now_slot (wrapping) clears
        them all and maintains the running total invariant.
        """
        if now_slot != self._last_slot:
            # How many slots have elapsed (wrapping around the ring)
            steps = (now_slot - self._last_slot) % self.WINDOW
            if steps >= self.WINDOW:
                # More than 60s passed — everything is stale
                self._total   = 0
                self._buckets = [0] * self.WINDOW
            else:
                for i in range(1, steps + 1):
                    idx = (self._last_slot + i) % self.WINDOW
                    self._total        -= self._buckets[idx]
                    self._buckets[idx]  = 0
            self._last_slot = now_slot

    def record_touch(self) -> None:
        """
        Register one completed word touch.
        Cost: 1 mod + 1 comparison + ≤1 subtraction + 1 addition = O(1).
        """
        now_slot = int(time.time()) % self.WINDOW
        with self._lock:
            self._maybe_expire(now_slot)
            self._buckets[now_slot] += 1
            self._total             += 1

    def get_wpm(self) -> int:
        """
        Return words read in the last 60 seconds.
        Cost: 1 mod + 1 comparison + ≤1 subtraction + 1 read = O(1).
        """
        now_slot = int(time.time()) % self.WINDOW
        with self._lock:
            self._maybe_expire(now_slot)
            return self._total

    def reset(self) -> None:
        with self._lock:
            self._buckets   = [0] * self.WINDOW
            self._total     = 0
            self._last_slot = int(time.time()) % self.WINDOW


# ─────────────────────── Performance metrics ──────────────────

class TouchEvent:
    __slots__ = ("timestamp", "duration", "path_length_val",
                 "efficiency", "backtracks", "peak_value", "cells_visited",
                 "reversals", "zero_crossings", "difficulty", "word_label",
                 "blocks_complete")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class PerformanceMetrics:
    """
    Tracks per-touch metrics and exposes a thread-safe snapshot dict.

    WPM is now sourced exclusively from SlidingWindowWPM (the O(1)
    circular bucket counter).  The internal _events deque is still
    maintained for computing avg_duration, avg_efficiency, backtracks,
    avg_peak, avg_difficulty, and avg_reversals — none of those metrics
    require the old event-count-based WPM formula.

    Backtracks are tracked per continuous contact (press→release):
    during a single press, if the finger slides from cell A to cell B
    then back to cell A, that counts as 1 backtrack.  The cumulative
    session total is displayed.  Uses the continuous-contact logical
    cell sequence (which survives word-boundary sub-splits) so that
    sliding Star→Boat→Star correctly registers as a backtrack.
    """

    def __init__(self, window_sec: int = ROLL_WINDOW):
        self._lock    = threading.Lock()
        self._window  = window_sec
        self._events: deque = deque()
        self._total   = 0
        # Dedicated O(1) WPM counter — replaces naive n/window*60 formula
        self._wpm_counter = SlidingWindowWPM()
        self.snapshot = dict(
            wpm=0.0, chars_total=0, chars_window=0,
            avg_duration=0.0, avg_efficiency=0.0,
            total_backtracks=0, avg_peak=0.0,
            pressed_cells=0, peak_value=0.0,
            spread_ratio=0.0, confidence=0.0,
            max_delta=0.0, is_touching=False,
            avg_difficulty=0.0, avg_reversals=0.0,
            word_reversals_total=0,   # session-level A→B→A word reversals
            current_word="",
        )
        self._word_reversals_total = 0   # cumulative session counter
        # Cumulative backtrack counter: sum of per-contact cell revisits
        self._cumulative_backtracks: int = 0

    def record(self, evt: TouchEvent, word_reversal: int = 0) -> None:
        """
        Store a completed TouchEvent.
        word_reversal=1 means this event was an A→B→A session-level reversal.
        """
        with self._lock:
            self._events.append(evt)
            self._total += 1
            self._word_reversals_total += word_reversal
        self._wpm_counter.record_touch()

    def add_contact_backtracks(self, n: int) -> None:
        """Add backtracks from one completed continuous contact (press→release)."""
        if n > 0:
            with self._lock:
                self._cumulative_backtracks += n

    def update_live(self, live: dict) -> None:
        """
        Recompute the snapshot from the rolling event window.

        WPM comes from SlidingWindowWPM.get_wpm() — one integer read.
        All other fields are derived from the deque as before.
        """
        # ── O(1) WPM read — no loop, no eviction scan ─────────
        wpm = float(self._wpm_counter.get_wpm())

        with self._lock:
            now = time.time()
            # Evict events older than the rolling window from the deque.
            # This deque is used only for quality-metric averaging, NOT
            # for WPM — so eviction here does not affect the WPM value.
            while (self._events
                   and now - self._events[0].timestamp > self._window):
                self._events.popleft()

            evts = list(self._events)
            n    = len(evts)
            total_chars = self._total

        with self._lock:
            wr_total = self._word_reversals_total
            cumulative_backtracks = self._cumulative_backtracks

        if n:
            avg_dur  = float(np.mean([e.duration   for e in evts]))
            avg_eff  = float(np.mean([e.efficiency for e in evts]))
            avg_pk   = float(np.mean([e.peak_value for e in evts]))
            avg_diff = float(np.mean([e.difficulty for e in evts]))
            avg_rev  = float(np.mean([e.reversals  for e in evts]))
        else:
            avg_dur = avg_eff = avg_pk = avg_diff = avg_rev = 0.0

        self.snapshot.update(
            wpm=wpm,
            chars_total=total_chars,
            chars_window=n,
            avg_duration=avg_dur,
            avg_efficiency=avg_eff,
            total_backtracks=cumulative_backtracks,
            avg_peak=avg_pk,
            avg_difficulty=avg_diff,
            avg_reversals=avg_rev,
            word_reversals_total=wr_total,
            **live,
        )


# ══════════════════════════════════════════════════════════════
# ADAPTIVE DEAD-TIME — EMA-based per-session false-trigger suppressor
# ══════════════════════════════════════════════════════════════

class AdaptiveDeadTime:
    """
    Lightweight adaptive re-trigger dead-time estimator.

    Problem: during a sustained finger press (~1600ms), ADC signal
    fluctuates across the touch threshold, generating phantom re-fires
    on the same cell every ~300ms.  A fixed dead-time blocks those but
    may be too conservative or too loose as conditions change.

    Solution: observe every inter-touch interval on the same cell.
    Feed *short* intervals (below 2×current dead-time) into an EMA
    that tracks the session’s actual false-trigger speed.  A second
    EMA smooths the dead-time output itself so changes are gradual.

      dead_time = clamp(ema_interval × SAFETY_MARGIN, MIN, MAX)

    Both EMA alphas are intentionally small (slow learner) so a single
    outlier interval has minimal effect.
    """

    # Tuning knobs—change only these to tune behaviour:
    MIN_DT        = 0.15   # s — hard floor (very responsive hardware)
    MAX_DT        = 0.75   # s — hard ceiling (very slow hardware)
    SAFETY_MARGIN = 1.40   # dead_time target = learned_interval × this
    INTERVAL_ALPHA = 0.12  # EMA rate for false-trigger interval estimate
    SMOOTH_ALPHA   = 0.08  # EMA rate for dead_time output (anti-jitter)
    # Only intervals below (current dead_time × CLASSIFY_RATIO) are treated
    # as false re-triggers and fed into the interval EMA.
    CLASSIFY_RATIO = 2.0

    def __init__(self, initial_dt: float = RETRIGGER_DEAD_TIME_S):
        self._dt            = float(initial_dt)
        # Initialise interval estimate by back-calculating from initial_dt
        self._ema_interval  = initial_dt / self.SAFETY_MARGIN
        self._n_obs         = 0        # count of intervals that updated the EMA
        self._lock          = threading.Lock()

    # ------------------------------------------------------------------ #
    @property
    def value(self) -> float:
        """Current dead-time in seconds (thread-safe snapshot)."""
        with self._lock:
            return self._dt

    # ------------------------------------------------------------------ #
    def observe(self, interval_s: float) -> bool:
        """
        Feed the time elapsed since the last *accepted* touch on this cell.

        Returns True  → block this touch (within dead-time).
        Returns False → accept this touch.

        Side-effect: updates the EMA if the interval looks like a
        false re-trigger (interval < current_dt × CLASSIFY_RATIO).
        """
        with self._lock:
            blocked = interval_s < self._dt

            # Feed short intervals into the learner
            if interval_s < self._dt * self.CLASSIFY_RATIO:
                self._n_obs += 1
                # EMA update on the interval estimate
                self._ema_interval = (
                    (1.0 - self.INTERVAL_ALPHA) * self._ema_interval
                    + self.INTERVAL_ALPHA * interval_s
                )
                # Target dead-time from learned interval
                target = self._ema_interval * self.SAFETY_MARGIN
                target = max(self.MIN_DT, min(self.MAX_DT, target))
                # Smooth the dead-time output (prevents jitter from single outlier)
                self._dt = (
                    (1.0 - self.SMOOTH_ALPHA) * self._dt
                    + self.SMOOTH_ALPHA * target
                )

            return blocked

    # ------------------------------------------------------------------ #
    def status(self) -> str:
        """One-line human-readable summary for logging."""
        with self._lock:
            return (
                f"AdaptDT: dt={self._dt*1000:.0f}ms  "
                f"learned={self._ema_interval*1000:.0f}ms  "
                f"n_obs={self._n_obs}"
            )


# ══════════════════════════════════════════════════════════════
# DATA LOGGER — Session CSV export + Publication-quality PNGs
# ══════════════════════════════════════════════════════════════

import csv
import os
from datetime import datetime

class DataLogger:
    """
    Thread-safe session data logger.

    Opens two CSVs in session_data/ at startup:
      - touch_events.csv  : one row per finalised touch
      - metrics_snapshots.csv : periodic metric snapshots

    At session end, generate_figures() saves publication-quality
    PNG plots (white background, dpi=150) for paper use.
    """

    TOUCH_HEADERS = [
        "timestamp", "word", "row", "col",
        "duration_ms", "vel_mean", "reversals", "zero_crossings",
        "difficulty", "is_regression", "wpm", "path_efficiency",
    ]
    SNAPSHOT_HEADERS = [
        "timestamp", "wpm", "consistency", "regression_rate",
        "skip_rate", "path_efficiency", "composite_difficulty",
    ]

    def __init__(self):
        self._lock = threading.Lock()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Always write next to the script itself, regardless of launch CWD
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        _data_dir   = os.path.join(_script_dir, "session_data")
        os.makedirs(_data_dir, exist_ok=True)
        self._session_dir = _data_dir
        self._ts = ts

        touch_path = os.path.join(self._session_dir, f"{ts}_touch_events.csv")
        snap_path  = os.path.join(self._session_dir, f"{ts}_metrics_snapshots.csv")

        self._touch_file = open(touch_path, "w", newline="", encoding="utf-8")
        self._snap_file  = open(snap_path,  "w", newline="", encoding="utf-8")

        self._touch_writer = csv.DictWriter(self._touch_file,
                                             fieldnames=self.TOUCH_HEADERS)
        self._snap_writer  = csv.DictWriter(self._snap_file,
                                             fieldnames=self.SNAPSHOT_HEADERS)
        self._touch_writer.writeheader()
        self._snap_writer.writeheader()

        self._touch_file.flush()
        self._snap_file.flush()

        print(f"[DataLogger] Session CSVs: {touch_path}, {snap_path}")

    def log_touch(self, timestamp, word, row, col, duration_ms,
                  vel_mean, reversals, zero_crossings, difficulty,
                  is_regression, wpm, path_efficiency):
        """Log one finalised touch event."""
        with self._lock:
            try:
                self._touch_writer.writerow({
                    "timestamp":      f"{timestamp:.3f}",
                    "word":           word or "",
                    "row":            row,
                    "col":            col,
                    "duration_ms":    f"{duration_ms:.1f}",
                    "vel_mean":       f"{vel_mean:.3f}",
                    "reversals":      reversals,
                    "zero_crossings": zero_crossings,
                    "difficulty":     f"{difficulty:.3f}",
                    "is_regression":  int(is_regression),
                    "wpm":            f"{wpm:.1f}",
                    "path_efficiency": f"{path_efficiency:.3f}",
                })
                self._touch_file.flush()
            except Exception:
                pass

    def log_snapshot(self, timestamp, wpm, consistency, regression_rate,
                     skip_rate, path_efficiency, composite_difficulty):
        """Log a periodic metrics snapshot."""
        with self._lock:
            try:
                self._snap_writer.writerow({
                    "timestamp":           f"{timestamp:.3f}",
                    "wpm":                 f"{wpm:.1f}",
                    "consistency":         f"{consistency:.3f}",
                    "regression_rate":     f"{regression_rate:.3f}",
                    "skip_rate":           f"{skip_rate:.1f}",
                    "path_efficiency":     f"{path_efficiency:.3f}",
                    "composite_difficulty": f"{composite_difficulty:.3f}",
                })
                self._snap_file.flush()
            except Exception:
                pass

    def close(self):
        """Flush and close both CSV files."""
        with self._lock:
            try:
                self._touch_file.flush()
                self._touch_file.close()
            except Exception:
                pass
            try:
                self._snap_file.flush()
                self._snap_file.close()
            except Exception:
                pass

    def generate_figures(self, wpm_x, wpm_raw, wpm_ema,
                         regression_count, flagged_words,
                         vel_history, eff_history, eff_indices,
                         diff_z, wb_snap, weight_note=""):
        """
        Generate and save publication-quality PNG figures.
        All figures: white background, dpi=150, proper labels.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np

        style = {
            "figure.facecolor": "white",
            "axes.facecolor":   "white",
            "axes.edgecolor":   "#333333",
            "axes.grid":        True,
            "grid.color":       "#dddddd",
            "text.color":       "#222222",
            "axes.labelcolor":  "#222222",
            "xtick.color":      "#444444",
            "ytick.color":      "#444444",
            "font.family":      "sans-serif",
        }

        def _savefig(fig, name):
            path = os.path.join(self._session_dir, f"{self._ts}_{name}")
            fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            print(f"[DataLogger] Saved figure: {path}")

        with plt.style.context(style):

            # ── 1. WPM Trend ───────────────────────────────────────
            if wpm_x and wpm_raw:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(wpm_x, wpm_raw, color="#bbbbbb", linewidth=1.0,
                        label="Raw WPM", alpha=0.7)
                if wpm_ema:
                    ax.plot(wpm_x, wpm_ema, color="#1a6fcc", linewidth=2.2,
                            label="EMA Trend")
                ax.axhline(50,  color="#e67e22", linestyle="--", linewidth=1,
                           alpha=0.7, label="50 WPM (beginner)")
                ax.axhline(100, color="#27ae60", linestyle="--", linewidth=1,
                           alpha=0.7, label="100 WPM (intermediate)")
                ax.set_xlabel("Session Time (s)", fontsize=11)
                ax.set_ylabel("Words Per Minute", fontsize=11)
                ax.set_title("Live WPM Trend — Median Pre-filter → EMA", fontsize=13, pad=10)
                ax.legend(frameon=True, fontsize=9)
                if weight_note:
                    ax.text(0.01, 0.01, weight_note, transform=ax.transAxes,
                            fontsize=7, color="gray", va="bottom")
                fig.tight_layout()
                _savefig(fig, "wpm_trend.png")

            # ── 2. Regression Bar Chart ─────────────────────────────
            visible = {w: c for w, c in regression_count.items() if c > 0}
            if visible:
                sorted_items = sorted(visible.items(), key=lambda x: x[1], reverse=True)
                words_r  = [i[0] for i in sorted_items]
                counts_r = [i[1] for i in sorted_items]
                flagged_set = set(flagged_words)
                colors_r = ["#e74c3c" if w in flagged_set else "#3498db" for w in words_r]

                fig, ax = plt.subplots(figsize=(8, max(3, len(words_r) * 0.4 + 1)))
                bars = ax.barh(range(len(words_r)), counts_r, color=colors_r, height=0.6)
                ax.set_yticks(range(len(words_r)))
                ax.set_yticklabels(words_r, fontsize=9)
                ax.invert_yaxis()
                ax.set_xlabel("Regression Count", fontsize=11)
                ax.set_title("Inter-Word Regressions", fontsize=13, pad=10)
                # Legend
                red_patch  = mpatches.Patch(color="#e74c3c",
                                            label=f"Flagged (>{REGRESSION_FLAG_THRESHOLD} regressions)")
                blue_patch = mpatches.Patch(color="#3498db", label="Normal")
                ax.legend(handles=[red_patch, blue_patch], loc="lower right", fontsize=9)
                # Count labels
                for bar, cnt in zip(bars, counts_r):
                    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                            str(cnt), va="center", fontsize=8)
                fig.tight_layout()
                _savefig(fig, "regression_chart.png")

            # ── 3. Velocity Profile Overlay ─────────────────────────
            if vel_history:
                fig, ax = plt.subplots(figsize=(10, 4))
                for i, v in enumerate(vel_history[:-1]):
                    if len(v) >= 2:
                        ax.plot(np.arange(len(v)), v, color="#888888",
                                linewidth=0.8, alpha=0.2)
                if len(vel_history[-1]) >= 2:
                    ax.plot(np.arange(len(vel_history[-1])), vel_history[-1],
                            color="#1a6fcc", linewidth=2.2, label="Most recent")
                # Weighted mean
                try:
                    from VelocityProfileMonitor import _compute_weighted_mean_velocity
                except Exception:
                    pass
                # Simple unweighted mean as fallback
                max_len = max(len(v) for v in vel_history)
                mean_arr = np.zeros(max_len)
                cnt_arr  = np.zeros(max_len)
                for v in vel_history:
                    for i, val in enumerate(v):
                        mean_arr[i] += val
                        cnt_arr[i]  += 1
                cnt_arr = np.where(cnt_arr == 0, 1, cnt_arr)
                mean_v = mean_arr / cnt_arr
                ax.plot(np.arange(max_len), mean_v, color="#e67e22",
                        linewidth=2, linestyle="--", label="Mean velocity")
                ax.set_xlabel("Step Index", fontsize=11)
                ax.set_ylabel("Velocity (cells/sec)", fontsize=11)
                ax.set_title("Velocity Profile — Last 20 Touch Events", fontsize=13, pad=10)
                ax.legend(fontsize=9)
                fig.tight_layout()
                _savefig(fig, "velocity_profile.png")

            # ── 4. Path Efficiency ──────────────────────────────────
            if len(eff_history) >= 2:
                fig, ax = plt.subplots(figsize=(10, 4))
                colors_e = ["#27ae60" if e >= 0.8
                             else ("#e67e22" if e >= 0.5 else "#e74c3c")
                             for e in eff_history]
                ax.scatter(eff_indices, eff_history, c=colors_e, s=40,
                           zorder=3, edgecolors="white", linewidths=0.5)
                # Trend line (polyfit fallback)
                try:
                    z = np.polyfit(eff_indices, eff_history, 2)
                    p = np.poly1d(z)
                    xs = np.linspace(min(eff_indices), max(eff_indices), 200)
                    ax.plot(xs, p(xs), color="#e67e22", linewidth=2.5, label="Trend")
                except Exception:
                    pass
                ax.axhline(0.8, color="#27ae60", linestyle="--", linewidth=1.5,
                           label="Proficiency target (η=0.8)")
                ax.set_ylim(0, 1.05)
                ax.set_xlabel("Contact # (press→release)", fontsize=11)
                ax.set_ylabel("Path Efficiency (η)", fontsize=11)
                ax.set_title("Path Efficiency Over Session", fontsize=13, pad=10)
                g_patch = mpatches.Patch(color="#27ae60", label="Proficient (η≥0.8)")
                o_patch = mpatches.Patch(color="#e67e22", label="Developing (0.5≤η<0.8)")
                r_patch = mpatches.Patch(color="#e74c3c", label="Struggling (η<0.5)")
                ax.legend(handles=[g_patch, o_patch, r_patch], fontsize=9, loc="lower right")
                fig.tight_layout()
                _savefig(fig, "path_efficiency.png")

            # ── 5. Difficulty Heatmap ───────────────────────────────
            if diff_z is not None:
                fig, ax = plt.subplots(figsize=(7, 6))
                # Build display matrix
                Z_display = np.zeros((GRID, GRID))
                if hasattr(diff_z, 'filled'):
                    Z_display = np.array(diff_z.filled(0), dtype=float)
                else:
                    Z_display = np.array(diff_z, dtype=float)
                im = ax.imshow(Z_display, cmap="YlOrRd", aspect="equal",
                               interpolation="nearest")
                plt.colorbar(im, ax=ax, shrink=0.8, label="Composite Difficulty Score")
                # Word labels
                if wb_snap:
                    for r in range(GRID):
                        for entry in wb_snap.get(r, []):
                            mid_c = (entry["start"] + entry["end"]) / 2
                            val = Z_display[r, int(round(mid_c))]
                            ax.text(mid_c, r, entry["word"],
                                    ha="center", va="center",
                                    fontsize=7, color="black",
                                    fontweight="bold")
                ax.set_xticks(range(GRID))
                ax.set_yticks(range(GRID))
                ax.set_xticklabels([f"C{i}" for i in range(GRID)])
                ax.set_yticklabels([f"R{i}" for i in range(GRID)])
                ax.set_title("Per-Word Composite Difficulty Heatmap", fontsize=13, pad=10)
                fig.tight_layout()
                _savefig(fig, "difficulty_heatmap.png")

        print("[DataLogger] All session figures saved.")


# ═══════════════════════════ SETUP ════════════════════════════

print("Opening serial port…")
ser = serial.Serial(PORT, BAUD, timeout=0.05)
time.sleep(2.0)

print(f"Calibrating ({CAL_FRAMES} frames) — keep sensor untouched…")
cal = []
for i in range(CAL_FRAMES):
    cal.append(read_frame(ser))
    print(f"  {i + 1}/{CAL_FRAMES}", end="\r")
print()
baseline = np.median(np.array(cal), axis=0)
print("Calibration done.")

print("\n═══ WORD MAP (logical row, col → word) ═══")
for r in range(GRID):
    row_words = [get_word_from_touch(r, c) or "?" for c in range(GRID)]
    print(f"  Row {r}: {row_words}")
print()

# ═══════════════════════════ THREADS ══════════════════════════

frame_q         = queue.Queue(maxsize=FRAME_QUEUE_MAX)
latest_frame_lk = threading.Lock()
latest_frame    = baseline.copy()
_frame_gen      = 0                           # B4: generation counter
perf            = PerformanceMetrics()
cell_diff        = CellDifficultyTracker()
velocity_tracker = VelocityTracker()
ewiqr_tracker    = EWIQRPerWordTracker()
welford_per_word = WelfordPerWord()
bar_chart        = BarChartBlit()
wpm_trend        = WPMTrendTracker()
reg_chart        = RegressionBarChart()       # V-5
monitor_3d       = Monitor3D()                # V-6
vel_profile      = VelocityProfileMonitor()    # V-7
eff_plot         = EfficiencyPlot()             # V-8

data_logger          = DataLogger()
adaptive_dead_time   = AdaptiveDeadTime()   # learns false-trigger speed during session
_last_snapshot_log_time = time.time()
print(f"[AdaptDT] Initial: {adaptive_dead_time.status()}")

# ── Per-finger tracker sets (butterfly dual-finger tracking) ──
finger_trackers = [
    {  # finger 0
        "perf": PerformanceMetrics(),
        "word_stats": WordStatsTracker(),
        "velocity": VelocityTracker(),
        "ewiqr": EWIQRPerWordTracker(),
        "welford": WelfordPerWord(),
        "wpm_trend": WPMTrendTracker(),
        "cell_diff": CellDifficultyTracker(),
    },
    {  # finger 1
        "perf": PerformanceMetrics(),
        "word_stats": WordStatsTracker(),
        "velocity": VelocityTracker(),
        "ewiqr": EWIQRPerWordTracker(),
        "welford": WelfordPerWord(),
        "wpm_trend": WPMTrendTracker(),
        "cell_diff": CellDifficultyTracker(),
    },
]

# ── B4: Pre-allocated numpy buffers for in-place ops ──────────
_raw_delta_buf = np.zeros((GRID, GRID), dtype=float)
_thresh_buf    = np.zeros((GRID, GRID), dtype=float)

# ── B1: Snapshot cache — heavy snapshots computed at 2fps ─────
_SNAPSHOT_INTERVAL = 0.5   # seconds — same as chart throttle
_last_snapshot_time = 0.0
_cached_ws          = None  # word_stats.snapshot()
_cached_ewiqr_snap  = None  # ewiqr_tracker.snapshot()
_cached_welford_snap = None # welford_per_word.snapshot()
_cached_vt          = None  # velocity_tracker.snapshot()
_cached_skip_snap   = None  # compute_skip_stats()
_cached_diff_snap   = None  # cell_diff.snapshot()
_cached_wb_snap     = None  # word_boundaries deep copy

# Per-finger snapshot caches
_cached_finger_snaps = [None, None]  # per-finger perf snapshots
_cached_finger_vt    = [None, None]  # per-finger velocity snapshots
_cached_finger_wpm   = [0.0, 0.0]   # per-finger WPM readings

# ── B3: Cached metrics text to avoid rebuild every frame ──────
_prev_metrics_text  = ""
_prev_words_text    = ""


def reader_thread():
    global latest_frame, _frame_gen
    while True:
        try:
            # ── Phase 1: Flush stale serial data ─────────────────
            # The OS serial buffer accumulates frames faster than the
            # app processes them, causing ~1.3s of latency.  Flushing
            # before each read discards all queued-but-unread bytes,
            # ensuring we always read the MOST RECENT frame.
            ser.reset_input_buffer()
            f = read_frame(ser)
        except Exception as e:
            print("Serial error:", e)
            time.sleep(0.05)
            continue
        with latest_frame_lk:
            latest_frame = f.copy()
            _frame_gen += 1               # B4: signal new frame
        while not frame_q.empty():
            try:
                frame_q.get_nowait()
            except queue.Empty:
                break
        try:
            frame_q.put_nowait(f)
        except queue.Full:
            pass


class FingerState:
    """Per-finger touch tracking state for butterfly dual-finger reading."""
    __slots__ = (
        "fid", "touching", "touch_start", "release_streak",
        "path_pts", "logical_seq", "first_peak_val", "first_peak_logic",
        "current_word", "lock",
        "cont_path_pts", "cont_logical_seq", "cont_touch_start",
    )

    def __init__(self, fid: int):
        self.fid              = fid
        self.touching         = False
        self.touch_start      = 0.0
        self.release_streak   = 0
        self.path_pts: list   = []
        self.logical_seq: list = []
        self.first_peak_val   = 0.0
        self.first_peak_logic = None
        self.current_word     = ""
        self.lock             = PeakLock()
        self.cont_path_pts: list    = []
        self.cont_logical_seq: list = []
        self.cont_touch_start       = 0.0

    def reset_touch(self):
        self.touching         = False
        self.release_streak   = 0
        self.lock.reset()
        self.first_peak_logic = None
        self.current_word     = ""


def _assign_peaks_to_fingers(peaks: list, fingers: list) -> list:
    """
    Assign up to 2 detected peaks to finger states by proximity.

    Returns a list of (finger_index, peak_info) tuples.
    Unmatched fingers get no entry (they should increment release_streak).
    """
    if not peaks:
        return []

    n_peaks   = len(peaks)
    n_fingers = len(fingers)

    if n_peaks == 1:
        # Single peak → assign to nearest active finger, or finger 0 if none active
        best_f = 0
        best_d = float("inf")
        for fi, f in enumerate(fingers):
            if f.touching and f.lock.cell is not None:
                d = manhattan(peaks[0]["peak_rc"], f.lock.cell)
                if d < best_d:
                    best_d = d
                    best_f = fi
        return [(best_f, peaks[0])]

    # 2+ peaks → greedy nearest-lock assignment
    assignments = []
    used_fingers = set()
    used_peaks   = set()

    # First pass: assign peaks to active fingers by nearest distance
    for fi, f in enumerate(fingers):
        if not f.touching or f.lock.cell is None:
            continue
        best_pi, best_d = -1, float("inf")
        for pi, pk in enumerate(peaks[:2]):
            if pi in used_peaks:
                continue
            d = manhattan(pk["peak_rc"], f.lock.cell)
            if d < best_d:
                best_d = d
                best_pi = pi
        if best_pi >= 0:
            assignments.append((fi, peaks[best_pi]))
            used_fingers.add(fi)
            used_peaks.add(best_pi)

    # Second pass: assign remaining peaks to unused fingers
    for pi, pk in enumerate(peaks[:2]):
        if pi in used_peaks:
            continue
        for fi in range(n_fingers):
            if fi not in used_fingers:
                assignments.append((fi, pk))
                used_fingers.add(fi)
                used_peaks.add(pi)
                break

    return assignments


def metrics_thread():
    """
    Dual-finger touch state machine for butterfly braille reading.

    Two independent FingerState objects track separate touch points.
    Each finger has its own PeakLock, path tracking, and touch lifecycle.
    Detected peaks are assigned to fingers by proximity each frame.

    Both per-finger AND combined metric trackers are updated on each
    touch finalisation, enabling per-finger and session-level analysis.

    Single-finger usage: finger 1 stays permanently idle — behavior
    is identical to the original single-finger implementation.
    """
    global _last_snapshot_log_time
    det_smooth   = np.zeros((GRID, GRID))
    initialized  = False

    # Per-cell re-trigger dead-time tracker: maps (row, col) -> last accepted time
    _cell_last_fired: dict = {}

    fingers = [FingerState(0), FingerState(1)]

    # ── helper: build and record a completed TouchEvent for finger fi ──
    def _finalise_touch(fi: int, touch_end: float):
        f = fingers[fi]
        ft = finger_trackers[fi]

        # ── Adaptive dead-time gate ──────────────────────────────────
        # Feed the interval to AdaptiveDeadTime.observe().
        # It updates its EMA internally and returns True to block.
        # Only update _cell_last_fired on accepted touches so the next
        # interval is measured from the last *genuine* fire.
        _gate_rc = f.first_peak_logic  # (row, col) in logical space
        if _gate_rc is not None:
            _last_t   = _cell_last_fired.get(_gate_rc, 0.0)
            _interval = touch_end - _last_t
            if adaptive_dead_time.observe(_interval):
                # Dead-time active — silently drop this touch
                return
            _cell_last_fired[_gate_rc] = touch_end

        duration = touch_end - f.touch_start
        pl  = path_length(f.path_pts)
        sl  = straight_line(f.path_pts)
        eff = (sl / pl) if pl > 1e-6 else 1.0
        bt  = count_backtracks(f.logical_seq)

        vels = compute_velocity_profile(f.path_pts, duration)

        # Record to per-finger AND combined velocity trackers
        ft["velocity"].record(vels)
        velocity_tracker.record(vels)

        rev  = count_reversals(f.logical_seq)
        zc   = count_zero_crossings(vels)

        # Session-level word reversal from combined word_stats
        with word_stats._lock:
            _seq_snap = list(word_stats._touch_seq)
        _current_word_str = (
            get_word_from_touch(f.first_peak_logic[0], f.first_peak_logic[1])
            if f.first_peak_logic else ""
        ) or ""
        wrev = count_word_reversals(_seq_snap, _current_word_str)

        # Word group completion check
        _row = f.first_peak_logic[0] if f.first_peak_logic else -1
        blocks_complete = word_group_accum.check_complete(
            _row, _current_word_str, f.logical_seq)

        d = difficulty_score(rev, zc, vels, word_reversals=wrev)

        # Register in BOTH per-finger and combined word_stats
        _r = f.first_peak_logic[0] if f.first_peak_logic else -1
        _c = f.first_peak_logic[1] if f.first_peak_logic else -1
        registered_word = word_stats.register(_r, _c, difficulty=d)
        ft["word_stats"].register(_r, _c, difficulty=d)

        evt = TouchEvent(
            timestamp=touch_end,
            duration=duration,
            path_length_val=pl,
            efficiency=eff,
            backtracks=bt,
            peak_value=f.first_peak_val,
            cells_visited=len(f.logical_seq),
            reversals=rev,
            zero_crossings=zc,
            difficulty=d,
            word_label=registered_word or "",
            blocks_complete=blocks_complete,
        )

        # Record to BOTH per-finger and combined perf trackers
        perf.record(evt, word_reversal=wrev)
        ft["perf"].record(TouchEvent(
            timestamp=touch_end, duration=duration,
            path_length_val=pl, efficiency=eff, backtracks=bt,
            peak_value=f.first_peak_val, cells_visited=len(f.logical_seq),
            reversals=rev, zero_crossings=zc, difficulty=d,
            word_label=registered_word or "", blocks_complete=blocks_complete,
        ), word_reversal=wrev)

        cell_diff.record(f.first_peak_logic, d)
        ft["cell_diff"].record(f.first_peak_logic, d)

        # ── DataLogger: log this touch event ──────────────────────────
        _r_log = f.first_peak_logic[0] if f.first_peak_logic else -1
        _c_log = f.first_peak_logic[1] if f.first_peak_logic else -1
        _vel_mean_log = float(vels.mean()) if len(vels) > 0 else 0.0
        _is_reg = registered_word in word_stats._seen if registered_word else False
        _wpm_now = float(perf._wpm_counter.get_wpm())
        data_logger.log_touch(
            timestamp=touch_end,
            word=registered_word or "",
            row=_r_log, col=_c_log,
            duration_ms=duration * 1000,
            vel_mean=_vel_mean_log,
            reversals=rev,
            zero_crossings=zc,
            difficulty=d,
            is_regression=(registered_word in word_stats._regression_count and
                           word_stats._regression_count[registered_word] > 0
                           and registered_word in word_stats._seen),
            wpm=_wpm_now,
            path_efficiency=eff,
        )

        # EWIQR + Welford per-word tracking (both per-finger and combined)
        if registered_word:
            ewiqr_tracker.record(registered_word, duration)
            welford_per_word.record(registered_word, duration)
            ft["ewiqr"].record(registered_word, duration)
            ft["welford"].record(registered_word, duration)

    # ── helper: finalise continuous-contact path on actual lift-off ──
    def _finalise_continuous_path(fi: int, touch_end: float):
        f = fingers[fi]

        bt = count_backtracks(f.cont_logical_seq)
        perf.add_contact_backtracks(bt)
        finger_trackers[fi]["perf"].add_contact_backtracks(bt)

        cont_duration = touch_end - f.cont_touch_start
        if cont_duration < 1e-9:
            cont_duration = 1e-9

        if len(f.cont_path_pts) >= 3:
            cont_pl  = path_length(f.cont_path_pts)
            cont_sl  = straight_line(f.cont_path_pts)
            cont_eff = (cont_sl / cont_pl) if cont_pl > 1e-6 else 1.0
            cont_vels = compute_velocity_profile(f.cont_path_pts, cont_duration)
            eff_plot.on_event_recorded(cont_eff, perf._total, touch_end)
            vel_profile.on_frame(cont_vels, touch_end)
        elif len(f.cont_path_pts) == 2:
            cont_vels = compute_velocity_profile(f.cont_path_pts, cont_duration)
            vel_profile.on_frame(cont_vels, touch_end)

        f.cont_path_pts    = []
        f.cont_logical_seq = []
        f.cont_touch_start = 0.0

    # ── helper: initialise state for a fresh touch event ──────
    def _start_touch(fi: int, peak_rc, peak_value: float,
                     is_new_contact: bool = True):
        f = fingers[fi]

        f.touching         = True
        f.touch_start      = time.time()
        f.release_streak   = 0
        f.path_pts         = []
        f.logical_seq      = []
        f.first_peak_val   = peak_value
        f.first_peak_logic = None
        f.current_word     = ""

        if is_new_contact:
            f.cont_path_pts    = []
            f.cont_logical_seq = []
            f.cont_touch_start = time.time()

        f.lock.reset(peak_rc)
        if f.lock.cell is not None:
            raw_r, raw_c     = f.lock.cell
            lr, lc           = raw_r, map_tx_col(raw_c)
            f.first_peak_logic = (lr, lc)
            f.logical_seq.append((lr, lc))
            f.path_pts.append((lc + 0.5, lr + 0.5))
            _pt = (lc + 0.5, lr + 0.5)
            if not f.cont_path_pts or f.cont_path_pts[-1] != _pt:
                f.cont_path_pts.append(_pt)
            if not f.cont_logical_seq or f.cont_logical_seq[-1] != (lr, lc):
                f.cont_logical_seq.append((lr, lc))
            f.current_word = get_word_from_touch(lr, lc) or ""

    # ── helper: process one frame for a specific finger ───────
    def _process_finger(fi: int, peak_info: dict):
        """Handle touch state machine for one finger given its assigned peak."""
        f = fingers[fi]

        if not f.touching:
            # IDLE → start new touch
            _start_touch(fi, peak_info["peak_rc"], peak_info["peak_value"],
                         is_new_contact=True)
        else:
            # TOUCHING → update with new peak
            f.release_streak = 0
            locked, jumped = f.lock.update(peak_info["peak_rc"])

            if locked is not None:
                raw_r, raw_c = locked
                lr, lc       = raw_r, map_tx_col(raw_c)

                if jumped:
                    _old_word = (get_word_from_touch(
                        f.first_peak_logic[0], f.first_peak_logic[1])
                        if f.first_peak_logic else "")
                    _new_word = get_word_from_touch(lr, lc) or ""
                    if _new_word and _new_word != _old_word:
                        _finalise_touch(fi, time.time())
                        _start_touch(fi, locked, peak_info["peak_value"],
                                     is_new_contact=False)
                    else:
                        if not f.logical_seq or f.logical_seq[-1] != (lr, lc):
                            f.logical_seq.append((lr, lc))
                            f.path_pts.append((lc + 0.5, lr + 0.5))
                            _pt = (lc + 0.5, lr + 0.5)
                            if not f.cont_path_pts or f.cont_path_pts[-1] != _pt:
                                f.cont_path_pts.append(_pt)
                            if not f.cont_logical_seq or f.cont_logical_seq[-1] != (lr, lc):
                                f.cont_logical_seq.append((lr, lc))
                else:
                    if not f.logical_seq or f.logical_seq[-1] != (lr, lc):
                        f.logical_seq.append((lr, lc))
                        f.path_pts.append((lc + 0.5, lr + 0.5))
                        _pt = (lc + 0.5, lr + 0.5)
                        if not f.cont_path_pts or f.cont_path_pts[-1] != _pt:
                            f.cont_path_pts.append(_pt)
                        if not f.cont_logical_seq or f.cont_logical_seq[-1] != (lr, lc):
                            f.cont_logical_seq.append((lr, lc))
                    new_word = get_word_from_touch(lr, lc) or ""
                    if (f.first_peak_logic is not None and new_word
                            and new_word != (
                                get_word_from_touch(
                                    f.first_peak_logic[0],
                                    f.first_peak_logic[1]) or "")):
                        _finalise_touch(fi, time.time())
                        _start_touch(fi, locked, peak_info["peak_value"],
                                     is_new_contact=False)
                    else:
                        f.current_word = new_word

    # ── main loop ─────────────────────────────────────────────
    live_word = ""   # initialised before loop to avoid UnboundLocalError on first frame
    while True:
        try:
            frame = frame_q.get(timeout=0.05)
        except queue.Empty:
            continue

        raw_delta = np.maximum(frame - baseline, 0.0)
        if not initialized:
            det_smooth  = raw_delta.copy()
            initialized = True
        else:
            det_smooth = ((1.0 - DETECT_SMOOTH_ALPHA) * det_smooth
                          + DETECT_SMOOTH_ALPHA * raw_delta)

        info  = analyse_touch(det_smooth)
        peaks = info.get("peaks", [])

        # ── Assign detected peaks to fingers by proximity ─────
        assignments = _assign_peaks_to_fingers(peaks, fingers)
        assigned_fingers = {fi for fi, _ in assignments}

        # ── Drive live_word from raw peaks ────────────────────
        # Build a combined live_word string showing both fingers
        _live_words = ["", ""]
        for fi, pk in assignments:
            _rr, _rc = pk["peak_rc"]
            _live_words[fi] = get_word_from_touch(_rr, map_tx_col(_rc)) or ""
            # Track raw peak in continuous path
            f = fingers[fi]
            if f.touching:
                _raw_lc = map_tx_col(_rc)
                _raw_pt = (_raw_lc + 0.5, _rr + 0.5)
                if not f.cont_path_pts or f.cont_path_pts[-1] != _raw_pt:
                    f.cont_path_pts.append(_raw_pt)
                if not f.cont_logical_seq or f.cont_logical_seq[-1] != (_rr, _raw_lc):
                    f.cont_logical_seq.append((_rr, _raw_lc))

        # Build display string
        if _live_words[0] and _live_words[1]:
            live_word = f"{_live_words[0]} | {_live_words[1]}"
        elif _live_words[0]:
            live_word = _live_words[0]
        elif _live_words[1]:
            live_word = _live_words[1]
        elif not any(f.touching for f in fingers):
            live_word = ""
        # else: keep previous live_word (touching but no clear peak)

        # ── Process assigned peaks ────────────────────────────
        for fi, pk in assignments:
            _process_finger(fi, pk)

        # ── Handle unassigned fingers (release streak) ────────
        for fi, f in enumerate(fingers):
            if fi not in assigned_fingers and f.touching:
                f.release_streak += 1

            # Finalise on sufficient silence or stuck
            if f.touching:
                stuck = (time.time() - f.touch_start) > MAX_TOUCH_DURATION_S
                if f.release_streak >= RELEASE_FRAMES_NEEDED or stuck:
                    f.touching = False
                    _now = time.time()
                    _finalise_touch(fi, _now)
                    _finalise_continuous_path(fi, _now)
                    f.reset_touch()

        # ── Update live status (aggregated across fingers) ────
        any_touching    = any(f.touching for f in fingers)
        total_pressed   = sum(pk.get("pressed_count", 0) for _, pk in assignments)
        best_peak_value = max((pk.get("peak_value", 0.0) for _, pk in assignments), default=0.0)

        perf.update_live(dict(
            is_touching=any_touching,
            pressed_cells=total_pressed if assignments else info["pressed_count"],
            peak_value=best_peak_value if assignments else info["peak_value"],
            spread_ratio=info["spread_ratio"],
            confidence=info["confidence"],
            max_delta=float(det_smooth.max()),
            current_word=live_word,
        ))

        # ── V-4: Feed current WPM into trend trackers ─────────
        current_wpm = float(perf._wpm_counter.get_wpm())
        wpm_trend.on_frame(current_wpm, time.time())

        # Per-finger WPM trend
        for fi in range(2):
            _fi_wpm = float(finger_trackers[fi]["perf"]._wpm_counter.get_wpm())
            finger_trackers[fi]["wpm_trend"].on_frame(_fi_wpm, time.time())
            _cached_finger_wpm[fi] = _fi_wpm


threading.Thread(target=reader_thread,  daemon=True, name="reader").start()
threading.Thread(target=metrics_thread, daemon=True, name="metrics").start()



if _LEGACY_MODE:
    # ═══════════════════════════════════════════════════════════════
    # LEGACY MATPLOTLIB UI — original visualization layer
    # Run with: python braille_ui.py --legacy
    # ═══════════════════════════════════════════════════════════════

    # ═══════════════════════════ VISUALISATION ════════════════════

    _cmap = LinearSegmentedColormap.from_list(
        "touch_modern",
        [_BG_DARK, "#1a1040", "#4c1d95", "#dc2626", "#f97316", "#fbbf24", "#fef3c7"],
        N=256,
    )

    plt.ion()

    # ══════════════════════════════════════════════════════════════
    # PLOT MENU — Single secondary window, one plot at a time
    # ══════════════════════════════════════════════════════════════
    # Instead of 6 separate windows, we create ONE secondary figure
    # with a RadioButtons panel on the left.  Only the selected plot
    # is built and rendered each frame — all others are skipped.
    #
    # Plot IDs (indices into PLOT_LABELS):
    #   0  Per-Word Bar Chart        (BarChartBlit)
    #   1  Live WPM Trend            (WPMTrendTracker)
    #   2  Regression Bar Chart      (RegressionBarChart)
    #   3  3D Surface Monitor        (Monitor3D)
    #   4  Velocity Profile          (VelocityProfileMonitor)
    #   5  Path Efficiency           (EfficiencyPlot)
    # ══════════════════════════════════════════════════════════════

    PLOT_LABELS = [
        "Per-Word Bars",
        "WPM Trend",
        "Regression Chart",
        "Perf. Heatmap",
        "Velocity Profile",
        "Path Efficiency",
    ]

    # Active plot index (0-5). Only this plot receives updates.
    _active_plot_idx = 0

    # ── Create the single secondary figure ────────────────────────
    _MENU_FIG_W  = 14   # figure width  (inches)
    _MENU_FIG_H  = 7    # figure height (inches)
    _RADIO_LEFT  = 0.01
    _RADIO_BOTTOM = 0.35
    _RADIO_WIDTH  = 0.11
    _RADIO_HEIGHT = 0.55
    _PLOT_LEFT    = 0.14   # plot axes start x (leaves room for radio panel)

    fig_menu = plt.figure(figsize=(_MENU_FIG_W, _MENU_FIG_H), facecolor="#0d1117")
    fig_menu.patch.set_facecolor("#0d1117")

    # Radio button panel
    _ax_radio = fig_menu.add_axes(
        [_RADIO_LEFT, _RADIO_BOTTOM, _RADIO_WIDTH, _RADIO_HEIGHT],
        facecolor="#161b22",
    )
    _radio_sel = RadioButtons(
        ax=_ax_radio,
        labels=PLOT_LABELS,
        active=_active_plot_idx,
    )
    for lbl in _radio_sel.labels:
        lbl.set_fontsize(8.5)
        lbl.set_color("#c9d1d9")
        lbl.set_fontfamily("monospace")
    _ax_radio.set_title("PLOT\nMENU", color="#58a6ff", fontsize=8,
                        fontweight="bold", pad=4)
    for sp in _ax_radio.spines.values():
        sp.set_edgecolor("#30363d")

    # ── Helper: create a fresh plot-area axes inside fig_menu ─────
    def _make_plot_ax(rect=None):
        """Add (or replace) the main plot axes in fig_menu."""
        if rect is None:
            rect = [_PLOT_LEFT, 0.08, 1.0 - _PLOT_LEFT - 0.02, 0.88]
        ax = fig_menu.add_axes(rect, facecolor=_BG_DARK)
        ax.tick_params(colors="#777777")
        for sp in ax.spines.values():
            sp.set_edgecolor(_GRID_COLOR)
        return ax

    # ── lazy-init flags — each plot is set up ONCE on first selection
    _plot_inited = [False] * len(PLOT_LABELS)

    # References shared across setup and UI loop
    ax_wpm        = None
    line_wpm_raw  = None
    line_wpm_ema  = None

    # Throttles
    _wpm_plot_last_update    = 0.0
    _WPM_PLOT_UPDATE_INTERVAL = 0.5

    # ── Alias the secondary-figure references expected by existing code ──
    # bar_chart.fig, reg_chart.fig, monitor_3d.figure, vel_profile.figure,
    # eff_plot.figure will each be pointed at fig_menu after their lazy init.
    # The classes themselves are unchanged; we just set their .fig / .figure.

    def _teardown_menu_plot_axes():
        """
        Remove all non-radio axes from fig_menu safely.
        Does NOT call clf() — that would destroy the RadioButtons internal
        PathCollection artists and leave self.figure=None, crashing on draw.
        Instead we delaxes each plot axis individually and rebuild the
        RadioButtons widget fresh on a new axes object.
        """
        global _ax_radio, _radio_sel

        # Release any active mouse grab from the old RadioButtons widget before
        # destroying its axes — otherwise the new widget raises:
        # RuntimeError: Another Axes already grabs mouse input
        try:
            fig_menu.canvas.release_mouse(_ax_radio)
        except Exception:
            pass
        # ── Reset ALL plot-object state before wiping axes ────────────
        # This is critical: background metrics_thread may still call
        # _update_velocity_plot / _update_efficiency_plot after a plot switch.
        # If _setup_done stays True but axes is deleted, the update writes to
        # a detached artist (wrong) or crashes.  Resetting here makes every
        # _update_* method return immediately via the `if not self._setup_done`
        # guard until the next _init_plot rebuilds them.
        vel_profile._setup_done  = False
        vel_profile.axes         = None
        eff_plot._setup_done     = False
        eff_plot.axes            = None
        bar_chart._setup_done    = False
        reg_chart._setup_done    = False
        monitor_3d._setup_done   = False

        # Remove every axes (all are stale after the resets above)
        for _ax in list(fig_menu.get_axes()):
            fig_menu.delaxes(_ax)   # remove ALL — we'll re-add radio below

        # Re-create the radio panel axes (fresh, no stale artists)
        _ax_radio = fig_menu.add_axes(
            [_RADIO_LEFT, _RADIO_BOTTOM, _RADIO_WIDTH, _RADIO_HEIGHT],
            facecolor="#161b22",
        )
        _ax_radio.set_title("PLOT\nMENU", color="#58a6ff",
                             fontsize=9, fontweight="bold", pad=6)
        for _sp in _ax_radio.spines.values():
            _sp.set_edgecolor("#30363d")

        # Recreate the RadioButtons widget — the old one's artists are detached
        _radio_sel = RadioButtons(
            ax=_ax_radio,
            labels=PLOT_LABELS,
            active=_active_plot_idx,
        )
        for _lbl in _radio_sel.labels:
            _lbl.set_fontsize(8.5)
            _lbl.set_color("#c9d1d9")
            _lbl.set_fontfamily("monospace")
        _radio_sel.on_clicked(_on_plot_select)


    def _init_plot(idx: int):
        """Lazy-init the selected plot inside fig_menu (called once per plot)."""
        global ax_wpm, line_wpm_raw, line_wpm_ema
        _teardown_menu_plot_axes()

        if idx == 0:   # ── Per-Word Bar Chart ──────────────────────
            # BarChartBlit.setup() creates its own fig; we redirect it
            # to use axes inside fig_menu instead.
            with word_boundaries_lock:
                _wb_for_chart = {k: list(v) for k, v in word_boundaries.items()}
            # Build word list — dynamic count based on user block-width config
            bar_chart.word_list = []
            for _ri in range(GRID):
                for _e in _wb_for_chart.get(_ri, []):
                    bar_chart.word_list.append(_e["word"])
            n_words = len(bar_chart.word_list)
            x_pos   = np.arange(n_words)
            bar_width = 0.35
            tab10 = plt.cm.tab10
            # Use a wide axes for the bar chart
            _ax_l = fig_menu.add_axes(
                [_PLOT_LEFT, 0.18, 1.0-_PLOT_LEFT-0.10, 0.75],
                facecolor=_BG_DARK)
            _ax_r = _ax_l.twinx()
            bar_chart.fig        = fig_menu
            bar_chart.ax_left    = _ax_l
            bar_chart.ax_right   = _ax_r
            # Build per-word row mapping for color assignment
            _word_row_map = []
            for _ri in range(GRID):
                for _e in _wb_for_chart.get(_ri, []):
                    _word_row_map.append(_ri)
            bar_chart.primary_bars = []
            bar_chart.count_bars   = []
            for _i in range(n_words):
                _row = _word_row_map[_i] if _i < len(_word_row_map) else 0
                _col = tab10(_row)
                bar_chart.primary_bars.append(
                    _ax_l.bar(_i - bar_width/2, 0, bar_width,
                              color=_col, alpha=1.0, edgecolor='none')[0])
                bar_chart.count_bars.append(
                    _ax_r.bar(_i + bar_width/2, 0, bar_width,
                              color=_col, alpha=0.3, edgecolor='none')[0])
            _ec = _ax_l.errorbar(x_pos, np.zeros(n_words), yerr=np.zeros(n_words),
                                 fmt='none', ecolor='#ffffff', elinewidth=0.8,
                                 capsize=2, capthick=0.6, alpha=0.5)
            bar_chart.error_caps_lo = _ec[1][0] if len(_ec[1]) > 0 else None
            bar_chart.error_caps_hi = _ec[1][1] if len(_ec[1]) > 1 else None
            bar_chart.error_stems   = _ec[2][0] if len(_ec[2]) > 0 else None
            bar_chart.asterisk_texts = []
            for _i in range(n_words):
                bar_chart.asterisk_texts.append(
                    _ax_l.text(_i, 0, "*", ha='center', va='bottom',
                               fontsize=14, fontweight='bold',
                               color='#ff4444', visible=False))
            bar_chart.hline = _ax_l.axhline(
                y=0, color='#00ffaa', linestyle='--', linewidth=1.2, alpha=0.7)
            _ax_l.set_xticks(x_pos)
            _ax_l.set_xticklabels(bar_chart.word_list, rotation=45, ha='right',
                                   fontsize=7, color=_FG_MUTED)
            _ax_l.set_ylabel('Time-on-Task (s)', color=_FG_PRIMARY, fontsize=9)
            _ax_r.set_ylabel('Touch Count',      color=_FG_PRIMARY, fontsize=9)
            _ax_l.tick_params(axis='y', colors=_FG_MUTED)
            _ax_r.tick_params(axis='y', colors=_FG_MUTED)
            _ax_l.set_title('Per-Word Performance  (Time-on-Task & Touch Counts)',
                            color='white', fontsize=11, fontweight='bold', pad=10)
            _ax_l.set_xlim(-0.5, n_words - 0.5)
            _ax_l.set_ylim(0, 1.0)
            _ax_r.set_ylim(0, 1.0)
            _ax_l.grid(axis='y', color=_GRID_COLOR, linewidth=0.5, alpha=0.5)
            for _sp in _ax_l.spines.values(): _sp.set_edgecolor(_GRID_COLOR)
            for _sp in _ax_r.spines.values(): _sp.set_edgecolor(_GRID_COLOR)
            fig_menu.canvas.draw()
            bar_chart.background_snap = fig_menu.canvas.copy_from_bbox(_ax_l.bbox)
            bar_chart.left_limit_max  = 0.0
            bar_chart.right_limit_max = 0.0
            bar_chart.prev_top5       = set()
            bar_chart.last_chart_time = -1e9
            bar_chart._setup_done     = True

        elif idx == 1:   # ── WPM Trend ───────────────────────────────
            ax_wpm = _make_plot_ax()
            ax_wpm.set_title("Live WPM Trend  (Median Pre-filter → EMA)",
                             color="white", fontsize=11, fontweight="bold", pad=10)
            ax_wpm.set_xlabel("Session Time (s)", color=_FG_MUTED, fontsize=9)
            ax_wpm.set_ylabel("Words Per Minute", color=_FG_MUTED, fontsize=9)
            ax_wpm.grid(axis='y', color=_GRID_COLOR, linewidth=0.5, alpha=0.5)
            ax_wpm.axhline(y=50,  color='#ffaa00', linestyle='--',
                           linewidth=0.9, alpha=0.5)
            ax_wpm.text(0.99, 50,  ' 50 WPM (beginner)',
                        transform=ax_wpm.get_yaxis_transform(),
                        va='bottom', ha='right', fontsize=7,
                        color='#ffaa00', alpha=0.6)
            ax_wpm.axhline(y=100, color='#00aaff', linestyle='--',
                           linewidth=0.9, alpha=0.5)
            ax_wpm.text(0.99, 100, ' 100 WPM (intermediate)',
                        transform=ax_wpm.get_yaxis_transform(),
                        va='bottom', ha='right', fontsize=7,
                        color='#00aaff', alpha=0.6)
            line_wpm_raw, = ax_wpm.plot([], [], color="#334466", alpha=0.35,
                                        linewidth=0.8, label="Raw WPM")
            line_wpm_ema, = ax_wpm.plot([], [], color="#00ffaa", alpha=0.95,
                                        linewidth=2.2, label="EMA Trend")
            ax_wpm.legend(loc="upper left", fontsize=8, framealpha=0.3,
                          facecolor=_BG_DARK, edgecolor=_BG_BORDER,
                          labelcolor=_FG_PRIMARY)
            ax_wpm.set_xlim(0, 10)
            ax_wpm.set_ylim(0, 10)

        elif idx == 2:   # ── Regression Bar Chart ─────────────────────
            reg_chart.fig = fig_menu
            reg_chart.ax  = _make_plot_ax()
            reg_chart.ax.set_facecolor(reg_chart.COLOR_BG)
            reg_chart.ax.set_title(
                "Most-Regressed Words  (inter-word regressions)",
                color="white", fontsize=11, fontweight="bold", pad=10)
            reg_chart.ax.set_xlabel("Regression count",
                                    color=_FG_MUTED, fontsize=9)
            reg_chart.ax.text(0.5, 0.5, "No regressions recorded yet",
                              transform=reg_chart.ax.transAxes,
                              ha="center", va="center", fontsize=12,
                              color=reg_chart.COLOR_EMPTY, fontstyle="italic")
            reg_chart.ax.tick_params(colors="#777777")
            for _sp in reg_chart.ax.spines.values():
                _sp.set_edgecolor(_GRID_COLOR)
            reg_chart._last_draw_time = -1e9   # force immediate redraw
            reg_chart._setup_done = True

        elif idx == 3:   # ── 2D Annotated Heatmap (replaces 3D Surface) ──
            monitor_3d.figure = fig_menu
            monitor_3d.Z_tot  = np.zeros((GRID, GRID))
            monitor_3d.Z_diff = np.zeros((GRID, GRID))
            monitor_3d.current_mode = 'tot'
            # Main heatmap axes
            _ax_hm = fig_menu.add_axes(
                [_PLOT_LEFT, 0.08, 0.72 - _PLOT_LEFT, 0.84],
                facecolor=_BG_DARK)
            monitor_3d._heatmap_ax = _ax_hm
            monitor_3d._heatmap_img = _ax_hm.imshow(
                monitor_3d.Z_tot, cmap='YlOrRd', vmin=0, vmax=1.0,
                interpolation='nearest', aspect='equal', origin='upper')
            # Colorbar
            _cbar = fig_menu.colorbar(monitor_3d._heatmap_img, ax=_ax_hm,
                                       fraction=0.046, pad=0.04)
            _cbar.ax.tick_params(colors=_FG_MUTED, labelsize=8)
            _cbar.set_label('Time-on-Task (s)', color=_FG_PRIMARY, fontsize=9)
            monitor_3d._heatmap_cbar = _cbar
            # Cell text annotations
            monitor_3d._heatmap_texts = {}
            for _hr in range(GRID):
                for _hc in range(GRID):
                    _word = get_word_from_touch(_hr, _hc) or '?'
                    _txt = _ax_hm.text(_hc, _hr, f'{_word}\n—',
                                       ha='center', va='center',
                                       fontsize=7, color='white',
                                       fontweight='bold',
                                       multialignment='center')
                    monitor_3d._heatmap_texts[(_hr, _hc)] = _txt
            _ax_hm.set_xticks(range(GRID))
            _ax_hm.set_xticklabels([f'C{i}' for i in range(GRID)],
                                    fontsize=8, color=_FG_MUTED)
            _ax_hm.set_yticks(range(GRID))
            _ax_hm.set_yticklabels([f'R{i}' for i in range(GRID)],
                                    fontsize=8, color=_FG_MUTED)
            _ax_hm.set_title('Performance Heatmap  [V-6]',
                             color='white', fontsize=11,
                             fontweight='bold', pad=10)
            _ax_hm.grid(False)
            for _sp in _ax_hm.spines.values():
                _sp.set_edgecolor(_GRID_COLOR)
            # RadioButtons for mode toggle
            _radio_ax_hm = fig_menu.add_axes([0.80, 0.35, 0.17, 0.20],
                                              facecolor='#1a1a2e')
            monitor_3d._radio = RadioButtons(
                ax=_radio_ax_hm,
                labels=['Time-on-Task', 'Mean Difficulty'], active=0)
            for _lbl in monitor_3d._radio.labels:
                _lbl.set_color(_FG_PRIMARY); _lbl.set_fontsize(8)
            def _on_hm_mode(label):
                monitor_3d.current_mode = 'tot' if 'Time' in label else 'diff'
                monitor_3d.last_update = -1e9  # force redraw
            monitor_3d._radio.on_clicked(_on_hm_mode)
            monitor_3d.last_update = -1e9
            monitor_3d._setup_done = True

        elif idx == 4:   # ── Velocity Profile ─────────────────────────
            vel_profile.figure = fig_menu
            vel_profile.axes   = _make_plot_ax()
            _ax_vp = vel_profile.axes
            vel_profile.line_recent, = _ax_vp.plot(
                [], [], color='#1f77b4', linewidth=2.5, alpha=1.0,
                label='Most recent')
            vel_profile.line_mean, = _ax_vp.plot(
                [], [], color='#ff7f0e', linewidth=2, alpha=0.8,
                linestyle='--', label='Weighted mean')
            vel_profile.lines_past = []
            for _ in range(vel_profile._n_overlay - 1):
                _ln, = _ax_vp.plot([], [], color='gray',
                                   linewidth=0.8, alpha=0.15)
                vel_profile.lines_past.append(_ln)
            _ax_vp.axhline(y=0, color='white', linewidth=0.5,
                           linestyle='-', alpha=0.3)
            _ax_vp.set_xlabel('Step index', fontsize=9, color=_FG_MUTED)
            _ax_vp.set_ylabel('Velocity (cells/sec)', fontsize=9,
                              color=_FG_MUTED)
            _ax_vp.set_title('Velocity Profile — last 20 touches  [V-7]',
                             fontsize=11, fontweight='bold',
                             color='white', pad=10)
            _ax_vp.legend(loc='upper right', fontsize=8, framealpha=0.3,
                          facecolor=_BG_DARK, edgecolor=_BG_BORDER,
                          labelcolor=_FG_PRIMARY)
            _ax_vp.grid(True, alpha=0.3, color=_GRID_COLOR)
            vel_profile._last_update = -1e9
            vel_profile._setup_done  = True

        elif idx == 5:   # ── Path Efficiency ──────────────────────────
            eff_plot.figure = fig_menu
            eff_plot.axes   = _make_plot_ax()
            _ax_ep = eff_plot.axes
            # Connecting line (thin, shows progression between dots)
            eff_plot.conn_line, = _ax_ep.plot(
                [], [], color='#66aaff', linewidth=1.2, alpha=0.5,
                zorder=2, label='Path')
            # Scatter dots (larger, color-coded by tier, white edge)
            eff_plot.scatter = _ax_ep.scatter(
                [], [], s=50, alpha=0.85, zorder=5, edgecolors='white',
                linewidths=0.3)
            eff_plot.trend_line, = _ax_ep.plot(
                [], [], color='#ff7f0e', linewidth=3.0, alpha=0.9,
                label='Trend', zorder=6)
            _ax_ep.axhline(y=0.8, color='#2ca02c', linewidth=1.5,
                           linestyle='--', alpha=0.5,
                           label='Proficiency target (η=0.8)', zorder=1)
            # Colour-coded fill bands for efficiency tiers
            _ax_ep.axhspan(0.8, 1.05, color='#2ca02c', alpha=0.06, zorder=0)
            _ax_ep.axhspan(0.5, 0.8,  color='#ff7f0e', alpha=0.06, zorder=0)
            _ax_ep.axhspan(0.0, 0.5,  color='#d62728', alpha=0.06, zorder=0)
            # Tier labels on right edge
            _ax_ep.text(0.99, 0.90, 'Proficient', transform=_ax_ep.transAxes,
                        ha='right', va='center', fontsize=7, color='#2ca02c', alpha=0.7)
            _ax_ep.text(0.99, 0.62, 'Developing', transform=_ax_ep.transAxes,
                        ha='right', va='center', fontsize=7, color='#ff7f0e', alpha=0.7)
            _ax_ep.text(0.99, 0.23, 'Struggling', transform=_ax_ep.transAxes,
                        ha='right', va='center', fontsize=7, color='#d62728', alpha=0.7)
            _ax_ep.set_xlabel('Contact # (press→release)', fontsize=9, color=_FG_MUTED)
            _ax_ep.set_ylabel('Path efficiency (η)', fontsize=9,
                              color=_FG_MUTED)
            _ax_ep.set_title('Path Efficiency Over Session  [V-8]',
                             fontsize=11, fontweight='bold',
                             color='white', pad=10)
            _ax_ep.set_ylim([0, 1.05])
            _ax_ep.set_xlim([0, 10])
            _ax_ep.legend(loc='lower right', fontsize=8, framealpha=0.3,
                          facecolor=eff_plot.COLOR_BG, edgecolor=_BG_BORDER,
                          labelcolor=_FG_PRIMARY)
            _ax_ep.grid(True, alpha=0.3, color=_GRID_COLOR)
            eff_plot._last_update = -1e9
            eff_plot._setup_done  = True

        # FIX 2: Render any already-accumulated data immediately on plot switch
        if idx == 4 and vel_profile._setup_done:
            with vel_profile._lock:
                _has_vel_data = len(vel_profile._velocity_history) > 0
            if _has_vel_data:
                vel_profile._update_velocity_plot(time.time())

        elif idx == 5 and eff_plot._setup_done:
            with eff_plot._lock:
                _has_eff_data = len(eff_plot.efficiency_history) >= 2
            if _has_eff_data:
                eff_plot._update_efficiency_plot(
                    len(eff_plot.event_indices), time.time())

        _plot_inited[idx] = True
        try:
            fig_menu.canvas.draw_idle()
        except Exception:
            pass


    def _on_plot_select(label: str):
        """RadioButtons callback — switch active plot."""
        global _active_plot_idx
        new_idx = PLOT_LABELS.index(label)
        if new_idx == _active_plot_idx:
            return  # already showing this plot
        _active_plot_idx = new_idx
        # Force re-init so axes are rebuilt cleanly
        _plot_inited[_active_plot_idx] = False

    # Initialise the default plot (index 0) immediately.
    # _teardown_menu_plot_axes (called inside _init_plot) recreates the
    # RadioButtons widget and registers _on_plot_select automatically.
    _init_plot(_active_plot_idx)

    # Throttle for WPM trend plot updates (~2fps, separate from chart blit)
    _wpm_plot_last_update    = 0.0
    _WPM_PLOT_UPDATE_INTERVAL = 0.5

    fig = plt.figure(figsize=(16, 10), facecolor=_BG_DARK)
    # Leave bottom 18% of figure for threshold sliders + button
    gs  = gridspec.GridSpec(1, 3, width_ratios=[1.1, 0.85, 0.85], wspace=0.05,
                            bottom=0.22, top=0.96)
    ax_heat    = fig.add_subplot(gs[0])
    ax_metrics = fig.add_subplot(gs[1])
    ax_words   = fig.add_subplot(gs[2])
    for ax in (ax_heat, ax_metrics, ax_words):
        ax.set_facecolor(_BG_CARD)
    ax_metrics.axis("off")
    ax_words.axis("off")
    fig.patch.set_facecolor(_BG_DARK)

    # ── [Edit Words] button ────────────────────────────────────────
    ax_btn   = fig.add_axes([0.01, 0.005, 0.12, 0.035])
    btn_edit = mwidgets.Button(ax_btn, "✎ Edit Words",
                               color="#161b22", hovercolor="#21262d")
    btn_edit.label.set_color(_ACCENT_BLUE)
    btn_edit.label.set_fontsize(9)
    btn_edit.label.set_fontfamily("sans-serif")
    btn_edit.on_clicked(lambda _: open_word_boundary_editor())

    # ── Threshold sliders (one per sensor row) ─────────────────────
    # Placed below the heatmap in the bottom margin of the figure.
    # Each slider adjusts ROW_THRESHOLDS[row] in real-time so both
    # the detection logic (analyse_touch → threshold_mask) and the
    # heatmap display threshold update instantly.
    from matplotlib.widgets import Slider as _Slider

    _thresh_slider_label = fig.text(
        0.22, 0.195, "  ROW TOUCH THRESHOLDS  (drag to adjust live)",
        fontsize=9, fontweight="bold", color=_ACCENT_ORANGE,
        fontfamily="sans-serif", ha="center",
    )

    _threshold_sliders: list = []
    _slider_left   = 0.06          # left edge (figure fraction)
    _slider_width  = 0.32          # slider width
    _slider_height = 0.018         # per-slider height
    _slider_gap    = 0.004         # vertical gap between sliders
    _slider_base   = 0.015         # bottom of lowest slider

    for _i_sl in range(GRID):
        _y_sl = _slider_base + (GRID - 1 - _i_sl) * (_slider_height + _slider_gap)
        _ax_sl = fig.add_axes(
            [_slider_left, _y_sl, _slider_width, _slider_height],
            facecolor="#1a1a2e",
        )
        _init_val = float(ROW_THRESHOLDS[_i_sl])
        _sl = _Slider(
            _ax_sl,
            f"R{_i_sl}",
            valmin=0.0,
            valmax=50.0,
            valinit=_init_val,
            valstep=0.5,
            color="#e94560",
            initcolor="none",
        )
        _sl.label.set_color("#a0c4ff")
        _sl.label.set_fontsize(8)
        _sl.label.set_fontfamily("monospace")
        _sl.valtext.set_color(_FG_PRIMARY)
        _sl.valtext.set_fontsize(8)

        # Closure: capture _i_sl by default arg
        def _on_thresh_change(val, row=_i_sl):
            ROW_THRESHOLDS[row] = val
        _sl.on_changed(_on_thresh_change)
        _threshold_sliders.append(_sl)

    # ── Heatmap ────────────────────────────────────────────────────
    Z    = np.zeros((GRID, GRID))
    hmap = ax_heat.imshow(Z, cmap=_cmap, vmin=0, vmax=150,
                          interpolation="nearest", aspect="equal")

    ax_heat.set_title(
        "Touch Pressure Map  (raw sensor layout)\n"
        "Cell labels show word at logical (TX-shifted) position",
        color="white", fontsize=11, fontweight="bold", pad=10)
    ax_heat.set_xlabel("Column →   C0 … C6   (RX)", color=_FG_MUTED, fontsize=9)
    ax_heat.set_ylabel("Row ↓   R0 … R6   (TX mux)", color=_FG_MUTED, fontsize=9)
    ax_heat.tick_params(colors="#777777")
    for sp in ax_heat.spines.values():
        sp.set_edgecolor(_GRID_COLOR)

    ax_heat.set_xticks(np.arange(-0.5, GRID, 1), minor=True)
    ax_heat.set_yticks(np.arange(-0.5, GRID, 1), minor=True)
    ax_heat.grid(which="minor", color=_GRID_COLOR, linewidth=0.8)
    ax_heat.tick_params(which="minor", length=0)

    ax_heat.set_xticks(range(GRID))
    ax_heat.set_xticklabels([f"C{i}" for i in range(GRID)],
                            color=_FG_MUTED, fontsize=8)
    ax_heat.set_yticks(range(GRID))
    ax_heat.set_yticklabels([f"R{i}" for i in range(GRID)],
                            color=_FG_MUTED, fontsize=8)

    # ── Cell label text objects ────────────────────────────────────
    _cell_texts: dict = {}
    for r in range(GRID):
        for raw_c in range(GRID):
            coord_str = f"{r},{raw_c}"
            with _cell_word_cache_lock:
                word_str = _cell_word_cache.get((r, raw_c), "")
            label = f"{coord_str}\n{word_str}" if word_str else coord_str
            txt = ax_heat.text(raw_c, r, label,
                               ha="center", va="center",
                               fontsize=5.5, color="#5a8a5a",
                               multialignment="center")
            _cell_texts[(r, raw_c)] = txt

    # ── Metrics text ───────────────────────────────────────────────
    metrics_txt = ax_metrics.text(
        0.05, 0.97, "Loading…",
        transform=ax_metrics.transAxes,
        fontsize=10.5, va="top", ha="left",
        family="sans-serif", color=_FG_PRIMARY, linespacing=1.85,
    )

    # ── Word-stats text ────────────────────────────────────────────
    words_txt = ax_words.text(
        0.05, 0.97, "Loading…",
        transform=ax_words.transAxes,
        fontsize=10.0, va="top", ha="left",
        family="sans-serif", color=_FG_PRIMARY, linespacing=1.75,
    )

    disp_Z  = np.zeros((GRID, GRID))
    last_ui = time.time()
    ui_dt   = 1.0 / UI_FPS

    # ── Blit infrastructure for fast heatmap rendering ─────────────
    # Instead of calling fig.canvas.draw_idle() every frame (which triggers
    # a full ~500ms canvas redraw), we use blitting:
    #   Fast path (~3ms):  restore background → draw heatmap artist → blit region
    #   Slow path (~50ms): full draw() at 2fps when text/snapshot data changes
    fig.canvas.draw()
    _main_bg = fig.canvas.copy_from_bbox(ax_heat.bbox)
    _needs_full_redraw = False

    def _on_main_resize(event=None):
        global _main_bg
        fig.canvas.draw()
        _main_bg = fig.canvas.copy_from_bbox(ax_heat.bbox)

    fig.canvas.mpl_connect('resize_event', _on_main_resize)

    # ── Fix 3: Stop flag — set when either window is closed ───────
    _ui_stop = threading.Event()

    def _on_fig_close(event):
        """Close either window → signal the UI loop to exit."""
        _ui_stop.set()

    fig.canvas.mpl_connect("close_event", _on_fig_close)
    fig_menu.canvas.mpl_connect("close_event", _on_fig_close)

    # ─────────────────────── UI loop ──────────────────────────────
    try:
        while not _ui_stop.is_set():
            now = time.time()
            if now - last_ui < ui_dt:
                time.sleep(max(0.0, ui_dt - (now - last_ui)))
                continue
            last_ui = now

            # ── B4: Only copy frame if reader delivered a new one ──
            with latest_frame_lk:
                _cur_gen = _frame_gen
                frame = latest_frame.copy()

            # ── C2: Vectorised numpy ops — no Python loops ────────
            np.subtract(frame, baseline, out=_raw_delta_buf)
            np.clip(_raw_delta_buf, 0.0, None, out=_raw_delta_buf)
            np.multiply(_raw_delta_buf,
                         _raw_delta_buf >= ROW_THRESHOLDS[:, np.newaxis],
                         out=_thresh_buf)

            hmap.set_data(_thresh_buf)
            pk = float(_thresh_buf.max())
            hmap.set_clim(0, max(30.0, pk * 1.15))

            # ── A3: Refresh cell labels ONLY when boundaries change ─
            if _cell_labels_dirty:
                _cell_labels_dirty = False
                _needs_full_redraw = True
                with _cell_word_cache_lock:
                    cache_snap = dict(_cell_word_cache)
                for r in range(GRID):
                    for raw_c in range(GRID):
                        logical_c = (raw_c + TX_SHIFT) % GRID
                        coord_str = f"{r},{logical_c}"
                        word_str  = cache_snap.get((r, raw_c), "")
                        label = f"{coord_str}\n{word_str}" if word_str else coord_str
                        _cell_texts[(r, raw_c)].set_text(label)

            # ── B1: Throttled snapshot cache — heavy ops at 2fps ────
            _snap_now = time.time()
            if _cached_ws is None or (_snap_now - _last_snapshot_time) >= _SNAPSHOT_INTERVAL:
                _last_snapshot_time = _snap_now
                _cached_diff_snap   = cell_diff.snapshot()
                _cached_ws          = word_stats.snapshot()
                _cached_ewiqr_snap  = ewiqr_tracker.snapshot()
                _cached_welford_snap = welford_per_word.snapshot()
                _cached_vt          = velocity_tracker.snapshot()
                with word_boundaries_lock:
                    _cached_wb_snap = {k: list(v) for k, v in word_boundaries.items()}
                _cached_skip_snap = compute_skip_stats(_cached_wb_snap, _cached_ws["word_count"])
                _needs_full_redraw = True   # snapshot data changed → schedule full redraw for text panels

                # ── DataLogger: periodic snapshot every 5 seconds ────────
                if time.time() - _last_snapshot_log_time >= 5.0:
                    _last_snapshot_log_time = time.time()
                    try:
                        _vt_snap = velocity_tracker.snapshot()
                        # Reuse _cached_wb_snap (already locked above) — no second lock needed
                        _skip_snap_log = compute_skip_stats(
                            _cached_wb_snap,
                            _cached_ws.get("word_count", {}),
                        )
                        data_logger.log_snapshot(
                            timestamp=time.time(),
                            wpm=perf.snapshot["wpm"],
                            consistency=_vt_snap["consistency"],
                            regression_rate=_cached_ws.get("hesitation_rate", 0.0),
                            skip_rate=_skip_snap_log["skip_rate"],
                            path_efficiency=eff_plot.get_avg_efficiency(),
                            composite_difficulty=perf.snapshot["avg_difficulty"],
                        )
                    except Exception:
                        pass

            # ── A4: Chart updates — only update the ACTIVE plot ─────────────
            # Skipping all chart work for hidden plots eliminates the biggest
            # source of frame-drop latency in the original design.
            _chart_now = time.time()

            if (_active_plot_idx == 0 and bar_chart._setup_done
                    and _cached_welford_snap is not None
                    and _cached_ws is not None):
                # ── Per-Word Bar Chart (only when selected) ────────────
                if (_chart_now - bar_chart.last_chart_time) >= BAR_CHART_UPDATE_INTERVAL:
                    _tot_per_word = {}
                    _std_per_word = {}
                    for _w, _wf in _cached_welford_snap.items():
                        _tot_per_word[_w] = _wf["mean"]
                        _std_per_word[_w] = _wf["std"]
                    _mean_D_per_word = {}
                    _wc = _cached_ws["word_count"]
                    _ewiqr_pw = _cached_ewiqr_snap.get("ewiqr_per_word", {})
                    for _w in _wc:
                        _mean_D_per_word[_w] = _ewiqr_pw.get(_w, 0.0)
                    _session_avg = 0.0
                    if _cached_welford_snap:
                        _total_n = sum(v["n"] for v in _cached_welford_snap.values())
                        if _total_n > 0:
                            _session_avg = sum(
                                v["mean"] * v["n"]
                                for v in _cached_welford_snap.values()) / _total_n
                    bar_chart.update(
                        tot_per_word=_tot_per_word,
                        std_per_word=_std_per_word,
                        word_count=_wc,
                        mean_D_per_word=_mean_D_per_word,
                        session_avg_duration=_session_avg,
                    )

            elif _active_plot_idx == 2 and reg_chart._setup_done:
                # ── Regression Bar Chart (only when selected) ──────────
                if (_chart_now - reg_chart._last_draw_time) >= REGRESSION_CHART_UPDATE_INTERVAL:
                    with word_stats._lock:
                        _full_reg_count = dict(word_stats._regression_count)
                    reg_chart.update(_full_reg_count, _cached_ws["flagged_words"])

            elif _active_plot_idx == 3 and monitor_3d._setup_done:
                # ── 2D Annotated Heatmap (replaces old 3D surface) ──────
                if (_chart_now - monitor_3d.last_update) >= SURFACE_3D_UPDATE_INTERVAL:
                    monitor_3d.last_update = _chart_now
                    _wb_hm    = _cached_wb_snap
                    _Z_tot_hm = np.zeros((GRID, GRID))
                    for _r_hm in range(GRID):
                        for _e_hm in _wb_hm.get(_r_hm, []):
                            _w_hm  = _e_hm["word"]
                            _wf_hm = _cached_welford_snap.get(_w_hm)
                            if _wf_hm:
                                for _c_hm in range(_e_hm["start"], _e_hm["end"] + 1):
                                    if 0 <= _c_hm < GRID:
                                        _Z_tot_hm[_r_hm, _c_hm] = _wf_hm["mean"]
                    _Z_diff_hm = np.zeros((GRID, GRID))
                    _ewiqr_hm  = _cached_ewiqr_snap.get("ewiqr_per_word", {})
                    for _r_hm in range(GRID):
                        for _e_hm in _wb_hm.get(_r_hm, []):
                            _w_hm = _e_hm["word"]
                            if _w_hm in _ewiqr_hm:
                                for _c_hm in range(_e_hm["start"], _e_hm["end"] + 1):
                                    if 0 <= _c_hm < GRID:
                                        _Z_diff_hm[_r_hm, _c_hm] = _ewiqr_hm[_w_hm]
                    monitor_3d.Z_tot  = _Z_tot_hm
                    monitor_3d.Z_diff = _Z_diff_hm
                    # Pick data based on mode toggle
                    _Z_show = _Z_tot_hm if monitor_3d.current_mode == 'tot' else _Z_diff_hm
                    _z_max = float(_Z_show.max()) if _Z_show.max() > 0 else 1.0
                    monitor_3d._heatmap_img.set_data(_Z_show)
                    monitor_3d._heatmap_img.set_clim(0, _z_max)
                    _mode_label = 'Time-on-Task (s)' if monitor_3d.current_mode == 'tot' else 'EWIQR Difficulty'
                    monitor_3d._heatmap_cbar.set_label(_mode_label, color=_FG_PRIMARY, fontsize=9)
                    # Update cell annotations
                    for _r_hm in range(GRID):
                        for _c_hm in range(GRID):
                            _word = get_word_from_touch(_r_hm, _c_hm) or '?'
                            _val = _Z_show[_r_hm, _c_hm]
                            _val_str = f'{_val:.2f}' if _val > 0 else '—'
                            # High-value cells get dark text for contrast
                            _txt_color = _BG_DARK if _val > _z_max * 0.6 else 'white'
                            _t = monitor_3d._heatmap_texts[(_r_hm, _c_hm)]
                            _t.set_text(f'{_word}\n{_val_str}')
                            _t.set_color(_txt_color)
                    monitor_3d._heatmap_ax.set_title(
                        f'Performance Heatmap — {_mode_label}  [V-6]',
                        color='white', fontsize=11, fontweight='bold', pad=10)

            elif _active_plot_idx == 1 and ax_wpm is not None and line_wpm_raw is not None:
                # ── V-4: WPM Trend plot (only when that plot is selected) ──
                _now_wpm_plot = time.time()
                if (_now_wpm_plot - _wpm_plot_last_update) >= _WPM_PLOT_UPDATE_INTERVAL:
                    _wpm_plot_last_update = _now_wpm_plot
                    x_raw_wpm, y_raw_wpm, y_ema_wpm, y_max_wpm = wpm_trend.get_plot_data()
                    if x_raw_wpm:
                        line_wpm_raw.set_data(x_raw_wpm, y_raw_wpm)
                        line_wpm_ema.set_data(x_raw_wpm, y_ema_wpm)
                        ax_wpm.set_ylim(0, max(10, y_max_wpm))
                        ax_wpm.set_xlim(x_raw_wpm[0], max(x_raw_wpm[-1], 10))
                        fig_menu.canvas.draw_idle()

            # ── Plots 4 & 5: rendered exclusively from the main thread ────────
            # Background thread (metrics_thread) sets _pending_render=True when
            # new data arrives.  We pick it up here, safely on the main thread.
            # We also do a throttled periodic redraw so switching TO these plots
            # after events have already been recorded still shows the data.
            elif _active_plot_idx == 4 and vel_profile._setup_done:
                _vel_needs_render = vel_profile._pending_render
                # Also re-render periodically (every 0.5s) to catch data already in the buffer
                if not _vel_needs_render:
                    _vel_needs_render = (time.time() - vel_profile._last_update) >= VEL_PROFILE_UPDATE_INTERVAL
                    with vel_profile._lock:
                        _vel_needs_render = _vel_needs_render and len(vel_profile._velocity_history) > 0
                if _vel_needs_render:
                    vel_profile._pending_render = False
                    vel_profile._update_velocity_plot(time.time())

            elif _active_plot_idx == 5 and eff_plot._setup_done:
                _eff_needs_render = eff_plot._pending_render
                # Also re-render periodically (every 0.5s) to catch data already in the buffer
                if not _eff_needs_render:
                    _eff_needs_render = (time.time() - eff_plot._last_update) >= EFFICIENCY_PLOT_UPDATE_INTERVAL
                    with eff_plot._lock:
                        _eff_needs_render = _eff_needs_render and len(eff_plot.efficiency_history) >= 2
                if _eff_needs_render:
                    eff_plot._pending_render = False
                    with eff_plot._lock:
                        _ec = len(eff_plot.event_indices)
                    eff_plot._update_efficiency_plot(_ec, time.time())

            # Use cached values for everything below
            diff_snap    = _cached_diff_snap
            ws           = _cached_ws
            ewiqr_snap   = _cached_ewiqr_snap
            welford_snap = _cached_welford_snap
            vt           = _cached_vt
            skip_snap    = _cached_skip_snap

            # ── Hardest sensor cell ───────────────────────────────
            if diff_snap:
                hardest_cell = max(diff_snap, key=diff_snap.get)
                hardest_d    = diff_snap[hardest_cell]
                hardest_str  = f"({hardest_cell[0]},{hardest_cell[1]})  D={hardest_d:.2f}"
            else:
                hardest_str = "n/a"

            # ── Metrics panel (simplified grouped cards) ────────────
            m  = perf.snapshot
            cw = m.get("current_word", "")
            cw_str = cw if cw else "—"

            # Per-finger WPM (from cached values)
            _f0_wpm = _cached_finger_wpm[0]
            _f1_wpm = _cached_finger_wpm[1]

            # Determine finger activity from perf live state
            _is_touching = m["is_touching"]
            st_icon = "●" if _is_touching else "○"

            # Traffic-light indicators
            _wpm = m['wpm']
            _wpm_dot = "🟢" if _wpm >= 50 else ("🟡" if _wpm >= 20 else "🔴")
            _eff = eff_plot.get_avg_efficiency()
            _eff_dot = "🟢" if _eff >= 0.8 else ("🟡" if _eff >= 0.5 else "🔴")
            _diff = m['avg_difficulty']
            _diff_dot = "🟢" if _diff < 1.0 else ("🟡" if _diff < 2.0 else "🔴")

            lines = [
                f"  {st_icon} {cw_str:^18s}  {m['pressed_cells']} cells",
                "",
                "  ── SPEED ────────────────────",
                f"  {_wpm_dot} {_wpm:.0f} WPM  (trend {wpm_trend.get_current_ema():.0f})",
                f"    F0: {_f0_wpm:.0f} WPM   F1: {_f1_wpm:.0f} WPM",
                f"    {m['chars_total']} chars  {m['chars_window']} in window",
                f"    {m['avg_duration']*1000:.0f} ms/touch",
                "",
                "  ── ACCURACY ─────────────────",
                f"  {_eff_dot} Path η={_eff:.2f}",
                f"    Backtracks: {m['total_backtracks']}",
                f"    Regressions: {ws['total_regressions']}",
                f"    Hesitation: {ws['hesitation_rate']*100:.0f}%",
                "",
                "  ── DIFFICULTY ────────────────",
                f"  {_diff_dot} Avg D={_diff:.2f}",
                f"    Reversals: {m['avg_reversals']:.1f}",
                f"    Word rev: {m['word_reversals_total']}",
                f"    Hardest: {hardest_str}",
                "",
                "  ── VELOCITY ─────────────────",
                f"    Speed: {vt['mean_vel']:.1f} cells/s",
                f"    IQR: {vt['iqr']:.2f}  ({vt['n_events']} events)",
                f"    Consistency: {vt['consistency']:.2f}",
            ]

            # Top EWIQR hardest word (just 1 line summary)
            top5 = ewiqr_snap.get("top5_hardest", [])
            if top5:
                _tw, _tiq = top5[0]
                lines.append(f"\n  Hardest word: {_tw} (IQR={_tiq:.2f}s)")

            metrics_txt.set_text("\n".join(lines))

            # ── Word-stats panel (simplified) ─────────────────────
            wc = ws["word_count"]
            top_words = sorted(wc.items(), key=lambda x: x[1], reverse=True)[:5]
            seq_display = " → ".join(ws["touch_sequence"][-5:]) \
                          if ws["touch_sequence"] else "—"

            flagged = ws["flagged_words"]
            flagged_str = (", ".join(flagged[:3]) if flagged else "none")

            word_lines = [
                "  ┌─ WORDS ────────────────────┐",
                f"  │  Touches: {ws['total_registered']}",
                f"  │  Most: {ws['most_touched'] or '—'}",
                f"  │  Hardest: {ws['hardest_word'] or '—'}",
                "  └────────────────────────────┘",
                "",
                "  ┌─ TOP WORDS ────────────────┐",
            ]
            for w, n in top_words:
                word_lines.append(f"  │  {w:<10s} {n}")
            if not top_words:
                word_lines.append("  │  (no touches yet)")
            word_lines += [
                "  └────────────────────────────┘",
                "",
                "  ┌─ REGRESSIONS ──────────────┐",
                f"  │  Total: {ws['total_regressions']}",
                f"  │  Flagged: {flagged_str}",
                "  └────────────────────────────┘",
                "",
                "  ┌─ COVERAGE ────────────────┐",
                f"  │  Skip rate: {skip_snap['skip_rate']:.0f}%",
                f"  │  Missing: {len(skip_snap['skipped_words'])}/{skip_snap.get('total_words', GRID*GRID)}",
                "  └────────────────────────────┘",
                "",
                f"  Seq: {seq_display[:28]}",
            ]

            words_txt.set_fontsize(9.5)
            words_txt.set_text("\n".join(word_lines))

            # ── Handle editor open request from button (main-thread Tkinter) ──
            if _editor_requested.is_set():
                _open_editor_on_main_thread()  # blocks until editor window closed

            # ── Fast blit path: only redraw heatmap pixels ────────
            # Full draw (~50ms) only when text/snapshot changed (2fps).
            # Blit path (~3ms) on all other frames — only the heatmap.
            if _needs_full_redraw:
                _needs_full_redraw = False
                fig.canvas.draw()
                _main_bg = fig.canvas.copy_from_bbox(ax_heat.bbox)
            else:
                fig.canvas.restore_region(_main_bg)
                ax_heat.draw_artist(hmap)
                fig.canvas.blit(ax_heat.bbox)
            fig.canvas.flush_events()

            # ── Flush the plot-menu figure (one window, one active plot) ──
            # Lazy-init on first selection, then render only the active plot.
            # draw_idle() is called here — on the MAIN thread — so TkAgg can
            # safely schedule the idle callback.  Background threads only set
            # axes.stale=True; we pick that up here.
            if not _plot_inited[_active_plot_idx]:
                _init_plot(_active_plot_idx)
            try:
                # draw_idle() removed — chart update functions already call it
                # when their data changes.  Only flush input events here.
                fig_menu.canvas.flush_events()
            except Exception:
                pass

    except KeyboardInterrupt:
        print("\nExiting.")
        ws = word_stats.snapshot()
        print("\n═══ FINAL WORD STATS ═══")
        print(f"Total registered touches : {ws['total_registered']}")
        print(f"Most touched word        : {ws['most_touched']}")
        print(f"Hardest word             : {ws['hardest_word']}  "
              f"(avg D={ws['hardest_word_d']:.3f})")
        print(f"Final WPM (sliding window): {perf._wpm_counter.get_wpm()}")
        print(f"Final WPM trend (EMA)    : {wpm_trend.get_current_ema():.1f}")

        # ── Per-finger summary ─────────────────────────────────────
        print("\n═══ PER-FINGER STATS (Butterfly) ═══")
        for fi in range(2):
            ft = finger_trackers[fi]
            fi_ws = ft["word_stats"].snapshot()
            fi_wpm = ft["perf"]._wpm_counter.get_wpm()
            fi_trend = ft["wpm_trend"].get_current_ema()
            fi_vt = ft["velocity"].snapshot()
            print(f"\n── Finger {fi} ──")
            print(f"  Touches: {fi_ws['total_registered']}")
            print(f"  WPM: {fi_wpm:.0f}  (EMA trend: {fi_trend:.1f})")
            print(f"  Regressions: {fi_ws['total_regressions']}")
            print(f"  Velocity: {fi_vt['mean_vel']:.1f} cells/s  "
                  f"consistency: {fi_vt['consistency']:.2f}")

        # ── V-4 final WPM trend report ────────────────────────────
        _, y_raw_final, y_ema_final, _ = wpm_trend.get_plot_data()
        if y_ema_final:
            print(f"\n═══ WPM TREND REPORT  [V-4] ═══")
            print(f"Raw WPM samples          : {len(y_raw_final)}")
            print(f"Peak raw WPM             : {max(y_raw_final):.0f}")
            print(f"Min raw WPM              : {min(y_raw_final):.0f}")
            print(f"Final EMA WPM            : {y_ema_final[-1]:.1f}")
            if len(y_ema_final) > 10:
                avg_ema = sum(y_ema_final) / len(y_ema_final)
                print(f"Session avg EMA WPM      : {avg_ema:.1f}")
                # Peak sustained WPM (max of EMA, which filters spikes)
                print(f"Peak sustained WPM (EMA) : {max(y_ema_final):.1f}")

        # ── M-H1 final regression report ──────────────────────────
        print("\n═══ REGRESSION REPORT  [M-H1] ═══")
        print(f"Total regressions        : {ws['total_regressions']}")
        print(f"Hesitation rate          : {ws['hesitation_rate']*100:.1f}%  "
              f"({ws['total_regressions']} regressions / "
              f"{ws['total_registered']} touches)")
        if ws["top_regressed"]:
            print("\n── Top regressed words ──")
            for word, cnt in ws["top_regressed"]:
                flag = "  ⚠ FLAGGED" if word in ws["flagged_words"] else ""
                print(f"  {word:<14}: {cnt} regression(s){flag}")
        if ws["flagged_words"]:
            print(f"\n── Flagged words (>{REGRESSION_FLAG_THRESHOLD} regressions) ──")
            for w in ws["flagged_words"]:
                print(f"  {w}")
        else:
            print("\nNo words flagged for excessive regressions.")

        # ── M-D2 final EWIQR difficulty report ────────────────────
        final_ewiqr = ewiqr_tracker.snapshot()
        final_welf  = welford_per_word.snapshot()
        print("\n═══ EWIQR DIFFICULTY REPORT  [M-D2] ═══")
        top5_final = final_ewiqr.get("top5_hardest", [])
        if top5_final:
            print("\n── Top 5 hardest (by EWIQR) ──")
            for rank, (tw, tewiqr) in enumerate(top5_final, 1):
                tconf = final_ewiqr["confidence_per_word"].get(tw, "?")
                tq1   = final_ewiqr["Q1_per_word"].get(tw, 0)
                tq3   = final_ewiqr["Q3_per_word"].get(tw, 0)
                print(f"  {rank}. {tw:<14}: EWIQR={tewiqr:.3f}s  "
                      f"Q1={tq1:.2f}s  Q3={tq3:.2f}s  [{tconf}]")
        else:
            print("  (not enough data for EWIQR ranking)")

        # Session average from Welford
        if final_welf:
            total_n = sum(v["n"] for v in final_welf.values())
            if total_n > 0:
                session_avg = sum(
                    v["mean"] * v["n"] for v in final_welf.values()
                ) / total_n
                print(f"\nSession avg duration     : {session_avg:.3f}s")

            print("\n── Per-word Welford stats ──")
            for w_name in sorted(final_welf.keys()):
                wf = final_welf[w_name]
                print(f"  {w_name:<14}: n={wf['n']:>3}  "
                      f"mean={wf['mean']:.3f}s  std={wf['std']:.3f}s")

        # All EWIQR values
        all_ewiqr = final_ewiqr.get("ewiqr_per_word", {})
        if all_ewiqr:
            print("\n── All EWIQR values ──")
            for w_name, ew_val in sorted(all_ewiqr.items(),
                                         key=lambda x: x[1], reverse=True):
                conf = final_ewiqr["confidence_per_word"].get(w_name, "?")
                print(f"  {w_name:<14}: EWIQR={ew_val:.3f}s  [{conf}]")

        # ── M-D3 final skip statistics report ─────────────────────
        with word_boundaries_lock:
            wb_final = {k: list(v) for k, v in word_boundaries.items()}
        skip_final    = compute_skip_stats(wb_final, ws["word_count"])
        skip_clusters = compute_skip_clusters(skip_final["skip_mask"])

        print("\n═══ SKIP STATISTICS REPORT  [M-D3] ═══")
        print(f"Skip rate                : {skip_final['skip_rate']:.1f}%")
        print(f"Skipped words            : {len(skip_final['skipped_words'])} / {skip_final.get('total_words', GRID*GRID)}")
        print(f"Partially visited rows   : {skip_final['partially_visited_rows'] or 'none'}")

        if skip_final["skipped_words"]:
            print("\n── Skipped words (row-major order) ──")
            for i, sw in enumerate(skip_final["skipped_words"]):
                print(f"  {i+1:>2}. {sw}")

        if skip_clusters:
            sig_clusters = [c for c in skip_clusters if not c["is_noise"]]
            noise_clusters = [c for c in skip_clusters if c["is_noise"]]
            print(f"\n── Skip clusters: {len(skip_clusters)} total "
                  f"({len(sig_clusters)} significant, "
                  f"{len(noise_clusters)} noise) ──")
            for i, cl in enumerate(skip_clusters):
                bbox = cl["bounding_box"]
                noise_tag = " [noise]" if cl["is_noise"] else ""
                print(f"  Cluster {i+1}: size={cl['size']}  "
                      f"bbox=({bbox[0]},{bbox[1]})-({bbox[2]},{bbox[3]})  "
                      f"pattern={cl['pattern']}{noise_tag}")
        else:
            print("\n  No skip clusters (full grid coverage).")

        # ── V-5 final regression chart summary ────────────────────
        with word_stats._lock:
            final_reg_count = dict(word_stats._regression_count)
        visible_reg = {w: c for w, c in final_reg_count.items() if c > 0}
        if visible_reg:
            print("\n═══ REGRESSION BAR CHART DATA  [V-5] ═══")
            sorted_reg = sorted(visible_reg.items(),
                                key=lambda x: x[1], reverse=True)
            for rank, (w, c) in enumerate(sorted_reg, 1):
                flag = "  ⚠ FLAGGED" if c > REGRESSION_FLAG_THRESHOLD else ""
                print(f"  {rank:>2}. {w:<14}: {c} regression(s){flag}")
            print(f"\n  Total words with regressions: {len(visible_reg)}")
            print(f"  Flagged words (>{REGRESSION_FLAG_THRESHOLD}): "
                  f"{len(ws['flagged_words'])}")

        # ── V-7 final velocity profile report ─────────────────────
        print("\n═══ VELOCITY PROFILE REPORT  [V-7] ═══")
        with vel_profile._lock:
            _vp_history = list(vel_profile._velocity_history)
        print(f"Events stored            : {len(_vp_history)}")
        if _vp_history:
            _all_vp = []
            for _va in _vp_history:
                if len(_va) >= 2:
                    _all_vp.extend(_va.tolist())
            if _all_vp:
                print(f"Max velocity             : {max(_all_vp):.2f} cells/s")
                print(f"Min velocity             : {min(_all_vp):.2f} cells/s")
                print(f"Mean velocity (all)      : {sum(_all_vp)/len(_all_vp):.2f} cells/s")
            _mean_vel, _weights = VelocityProfileMonitor._compute_weighted_mean_velocity(
                _vp_history, VEL_PROFILE_ALPHA_WEIGHT
            )
            if _mean_vel is not None:
                print(f"Weighted mean peak       : {float(_mean_vel.max()):.2f} cells/s")
                print(f"Weighted mean length     : {len(_mean_vel)} steps")
        else:
            print("  (no velocity data recorded)")

        # ── V-8 final efficiency plot report ──────────────────────
        print("\n═══ PATH EFFICIENCY REPORT  [V-8] ═══")
        with eff_plot._lock:
            _eff_hist = list(eff_plot.efficiency_history)
        print(f"Events recorded          : {len(_eff_hist)}")
        if _eff_hist:
            _eff_arr = np.array(_eff_hist)
            print(f"Mean efficiency          : {_eff_arr.mean():.3f}")
            print(f"Median efficiency        : {np.median(_eff_arr):.3f}")
            print(f"Std efficiency           : {_eff_arr.std():.3f}")
            print(f"Min efficiency           : {_eff_arr.min():.3f}")
            print(f"Max efficiency           : {_eff_arr.max():.3f}")
            _proficient = np.sum(_eff_arr >= 0.8)
            _developing = np.sum((_eff_arr >= 0.5) & (_eff_arr < 0.8))
            _struggling = np.sum(_eff_arr < 0.5)
            print(f"Proficient (η≥0.8)      : {_proficient} ({_proficient/len(_eff_hist)*100:.0f}%)")
            print(f"Developing (0.5≤η<0.8)  : {_developing} ({_developing/len(_eff_hist)*100:.0f}%)")
            print(f"Struggling (η<0.5)      : {_struggling} ({_struggling/len(_eff_hist)*100:.0f}%)")
        else:
            print("  (no efficiency data recorded)")

        print("\n── Skip mask ──")
        for r in range(GRID):
            row_str = "  "
            for c in range(GRID):
                row_str += "█ " if skip_final["skip_mask"][r, c] else "· "
            print(row_str)

        print("\n── Word counts ──")
        for word, count in sorted(ws["word_count"].items(),
                                   key=lambda x: x[1], reverse=True):
            print(f"  {word:<14}: {count}")
        print("\n── Touch sequence (last 20) ──")
        print("  " + " → ".join(ws["touch_sequence"]))
    finally:
        # Graceful shutdown: suppress Tkinter destroy errors on Ctrl+C
        try:
            plt.close('all')
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass

else:
    # ═══════════════════════════════════════════════════════════════
    # PyQtGraph / PyQt5 REAL-TIME UI — default mode
    # ═══════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    # PyQtGraph / PyQt5 REAL-TIME UI
    # ══════════════════════════════════════════════════════════════
    #
    # This section replaces the entire Matplotlib visualization layer
    # with a PyQtGraph-based dashboard for sub-50ms, 30fps rendering.
    # All data model classes (trackers, metrics, state machines) are
    # shared with the legacy Matplotlib path.
    #
    # Architecture:
    #   BrailleMainWindow (QMainWindow)
    #     ├─ HeatmapWidget      — 7×7 touch pressure heatmap
    #     ├─ MetricsPanel        — live speed/accuracy/difficulty metrics
    #     ├─ WordStatsPanel      — word counts, regressions, coverage
    #     ├─ ThresholdSliders    — per-row ADC threshold adjustment
    #     └─ PlotWindow (QMainWindow)
    #          ├─ PlotSelector   — QListWidget for plot switching
    #          └─ QStackedWidget
    #               ├─ BarChartWidget         — per-word bar chart
    #               ├─ WPMTrendWidget         — live WPM trend
    #               ├─ RegressionChartWidget  — regression bars
    #               ├─ PerfHeatmapWidget      — performance heatmap
    #               ├─ VelocityProfileWidget  — velocity overlay
    #               └─ EfficiencyWidget       — path efficiency scatter
    # ══════════════════════════════════════════════════════════════


    class WordBoundaryEditorQt(QDialog):
        """PyQt5 port of the Tkinter WordBoundaryEditor dialog."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("✎ Word Boundary Editor")
            self.setMinimumSize(820, 480)
            self.setStyleSheet("""
                QDialog { background: #1a1a2e; }
                QLabel { color: #e0e0e0; font-family: 'Courier New'; font-size: 10pt; }
                QLineEdit { background: #0f3460; color: #e0e0e0; border: 1px solid #30363d;
                            font-family: 'Courier New'; font-size: 10pt; padding: 3px; }
                QSpinBox { background: #0f3460; color: #e0e0e0; border: 1px solid #30363d;
                           font-family: 'Courier New'; font-size: 10pt; }
                QPushButton { font-family: 'Courier New'; font-size: 11pt; font-weight: bold;
                              padding: 8px 18px; border: none; border-radius: 4px; }
                QScrollArea { border: none; }
            """)
            self._rows_data = []
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 12)

            # Header
            header = QLabel("✎  WORD BOUNDARY EDITOR\n"
                            "Edit word labels. Boundaries are spread evenly per row.")
            header.setStyleSheet("color: #e94560; font-size: 11pt; font-weight: bold;")
            header.setAlignment(Qt.AlignCenter)
            layout.addWidget(header)

            note = QLabel(f"Grid has {GRID} columns (0–{GRID-1}).  "
                          "Add/remove words by changing the word count spinbox, then click Apply.")
            note.setStyleSheet(f"color: {_FG_MUTED}; font-size: 9pt;")
            note.setWordWrap(True)
            layout.addWidget(note)

            # Scrollable content
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_widget = QWidget()
            scroll_widget.setStyleSheet("background: #1a1a2e;")
            self._grid_layout = QGridLayout(scroll_widget)
            self._grid_layout.setSpacing(6)

            # Column headers
            self._grid_layout.addWidget(QLabel(""), 0, 0)
            lbl_count = QLabel("# Words")
            lbl_count.setStyleSheet("color: #a0c4ff; font-weight: bold; font-size: 9pt;")
            self._grid_layout.addWidget(lbl_count, 0, 1)
            lbl_words = QLabel("Word labels & block widths → (widths must sum to 7)")
            lbl_words.setStyleSheet("color: #a0c4ff; font-weight: bold; font-size: 9pt;")
            self._grid_layout.addWidget(lbl_words, 0, 2, 1, GRID * 3)

            with word_boundaries_lock:
                current_boundaries = {k: list(v) for k, v in word_boundaries.items()}

            for row_idx in range(GRID):
                entries = current_boundaries.get(row_idx, [])
                words = [e["word"] for e in entries]
                widths = [e["end"] - e["start"] + 1 for e in entries]

                row_data = {"row_idx": row_idx, "words": list(words),
                            "widths": list(widths), "widgets_frame": None}
                self._rows_data.append(row_data)

                # Row label
                rlbl = QLabel(f" Row {row_idx}")
                rlbl.setStyleSheet("background: #16213e; color: #e94560; font-weight: bold; padding: 4px;")
                self._grid_layout.addWidget(rlbl, row_idx + 1, 0)

                # Word count spinbox
                sp = QSpinBox()
                sp.setRange(1, GRID)
                sp.setValue(len(words))
                sp.valueChanged.connect(lambda val, ri=row_idx: self._on_count_change(ri, val))
                row_data["count_spin"] = sp
                self._grid_layout.addWidget(sp, row_idx + 1, 1)

                # Container for word entries
                container = QWidget()
                container.setStyleSheet("background: #1a1a2e;")
                container_layout = QHBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(4)
                row_data["widgets_frame"] = container
                row_data["container_layout"] = container_layout
                self._grid_layout.addWidget(container, row_idx + 1, 2, 1, GRID * 3)
                self._rebuild_row_widgets(row_idx)

            scroll.setWidget(scroll_widget)
            layout.addWidget(scroll, 1)

            # Buttons
            btn_layout = QHBoxLayout()
            btn_apply = QPushButton("✔  Apply Changes")
            btn_apply.setStyleSheet("background: #e94560; color: white;")
            btn_apply.setCursor(Qt.PointingHandCursor)
            btn_apply.clicked.connect(self._apply)
            btn_layout.addWidget(btn_apply)

            btn_close = QPushButton("✖  Close")
            btn_close.setStyleSheet("background: #333355; color: #aaaacc;")
            btn_close.setCursor(Qt.PointingHandCursor)
            btn_close.clicked.connect(self.reject)
            btn_layout.addWidget(btn_close)
            layout.addLayout(btn_layout)

        def _rebuild_row_widgets(self, row_idx):
            rd = self._rows_data[row_idx]
            layout = rd["container_layout"]
            # Clear existing
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            n = rd["count_spin"].value()
            words = rd["words"]
            widths = rd["widths"]
            while len(words) < n:
                words.append("")
            words = words[:n]
            while len(widths) < n:
                widths.append(1)
            widths = widths[:n]
            if sum(widths) != GRID:
                base, extra = divmod(GRID, n)
                widths = [base + (1 if i < extra else 0) for i in range(n)]
            rd["words"] = words
            rd["widths"] = widths

            # Compute ranges
            col = 0
            rd["word_edits"] = []
            rd["width_spins"] = []
            for i in range(n):
                w = widths[i]
                s, e = col, col + w - 1
                col += w
                rlbl = QLabel(f"[{s}-{e}]")
                rlbl.setStyleSheet("color: #a0c4ff; font-size: 8pt;")
                layout.addWidget(rlbl)
                we = QLineEdit(words[i])
                we.setMinimumWidth(70)
                rd["word_edits"].append(we)
                layout.addWidget(we)
                ws = QSpinBox()
                ws.setRange(1, GRID)
                ws.setValue(w)
                ws.setMaximumWidth(50)
                ws.setStyleSheet("background: #2a2a4e; color: #ffcc66;")
                rd["width_spins"].append(ws)
                layout.addWidget(ws)
            layout.addStretch()

        def _on_count_change(self, row_idx, val):
            self._rebuild_row_widgets(row_idx)

        def _apply(self):
            global word_boundaries
            new_tgrid = []
            for rd in self._rows_data:
                words = [e.text().strip() for e in rd.get("word_edits", [])]
                widths = [s.value() for s in rd.get("width_spins", [])]
                while len(widths) < len(words):
                    widths.append(1)
                entries = []
                for i, w in enumerate(words):
                    label = w if w else f"?{i}"
                    entries.append((label, widths[i]))
                total_w = sum(widths[:len(words)])
                if total_w != GRID:
                    QMessageBox.critical(self, "Invalid widths",
                        f"Row {rd['row_idx']}: block widths sum to {total_w}, must equal {GRID}.")
                    return
                new_tgrid.append(entries)

            # Preserve extra rows beyond GRID
            with word_boundaries_lock:
                all_row_keys = sorted(word_boundaries.keys())
            extra_keys = [k for k in all_row_keys if k >= GRID]
            for k in extra_keys:
                with word_boundaries_lock:
                    extra_entries = [(e["word"], e["end"] - e["start"] + 1)
                                     for e in word_boundaries[k]]
                new_tgrid.append(extra_entries)

            new_boundaries = _build_word_boundaries(new_tgrid, GRID)
            with word_boundaries_lock:
                word_boundaries.clear()
                word_boundaries.update(new_boundaries)
            _rebuild_cell_word_cache()

            QMessageBox.information(self, "Applied",
                "Word boundaries updated!\nThe heatmap and detection logic now use the new mapping.")
            self.accept()


    # ── PyQtGraph color LUT matching the matplotlib _cmap ──────────
    def _build_touch_lut():
        """Build a 256-entry RGBA LUT for the heatmap colormap."""
        colors = [
            (0.0,   QColor("#0d1117")),
            (0.15,  QColor("#1a1040")),
            (0.35,  QColor("#4c1d95")),
            (0.55,  QColor("#dc2626")),
            (0.70,  QColor("#f97316")),
            (0.85,  QColor("#fbbf24")),
            (1.0,   QColor("#fef3c7")),
        ]
        lut = np.zeros((256, 4), dtype=np.ubyte)
        for i in range(256):
            t = i / 255.0
            # Find segment
            for j in range(len(colors) - 1):
                t0, c0 = colors[j]
                t1, c1 = colors[j + 1]
                if t0 <= t <= t1:
                    f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                    r = int(c0.red()   + f * (c1.red()   - c0.red()))
                    g = int(c0.green() + f * (c1.green() - c0.green()))
                    b = int(c0.blue()  + f * (c1.blue()  - c0.blue()))
                    lut[i] = [r, g, b, 255]
                    break
        return lut


    class HeatmapWidget(pg.GraphicsLayoutWidget):
        """7×7 touch pressure heatmap using pyqtgraph ImageItem."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setBackground("#0d1117")
            self.setMinimumSize(420, 380)

            self._plot = self.addPlot(title="Touch Pressure Map (raw sensor layout)")
            self._plot.setLabel('bottom', "Column → C0…C6 (RX)")
            self._plot.setLabel('left', "Row ↓ R0…R6 (TX mux)")
            self._plot.invertY(True)
            self._plot.setRange(xRange=[-0.5, GRID - 0.5], yRange=[-0.5, GRID - 0.5])
            self._plot.setAspectLocked(True)
            self._plot.hideButtons()

            self._img = pg.ImageItem()
            self._lut = _build_touch_lut()
            self._img.setLookupTable(self._lut)
            self._plot.addItem(self._img)

            # Axes ticks
            x_ticks = [(i, f"C{i}") for i in range(GRID)]
            y_ticks = [(i, f"R{i}") for i in range(GRID)]
            self._plot.getAxis('bottom').setTicks([x_ticks])
            self._plot.getAxis('left').setTicks([y_ticks])

            # Cell text labels
            self._cell_texts = {}
            for r in range(GRID):
                for c in range(GRID):
                    word = get_word_from_touch(r, c) or ""
                    coord = f"{r},{c}"
                    label = f"{coord}\n{word}" if word else coord
                    txt = pg.TextItem(label, color="#5a8a5a", anchor=(0.5, 0.5))
                    txt.setFont(QFont("Courier New", 7))
                    txt.setPos(c, r)
                    self._plot.addItem(txt)
                    self._cell_texts[(r, c)] = txt

            # Grid lines
            for i in range(GRID + 1):
                pos = i - 0.5
                self._plot.addLine(x=pos, pen=pg.mkPen("#21262d", width=1))
                self._plot.addLine(y=pos, pen=pg.mkPen("#21262d", width=1))

        def update_data(self, delta):
            """Update heatmap with new 7x7 delta array."""
            pk = float(delta.max())
            # Normalize to 0-255 for LUT
            vmax = max(30.0, pk * 1.15)
            normalized = np.clip(delta / vmax * 255, 0, 255).astype(np.ubyte)
            # ImageItem expects (width, height) so transpose
            self._img.setImage(normalized.T, levels=[0, 255])
            self._img.setRect(-0.5, -0.5, GRID, GRID)

        def refresh_labels(self):
            """Rebuild cell labels after word boundary changes."""
            for r in range(GRID):
                for c in range(GRID):
                    word = get_word_from_touch(r, c) or ""
                    coord = f"{r},{c}"
                    label = f"{coord}\n{word}" if word else coord
                    self._cell_texts[(r, c)].setText(label)


    # ══════════════════════════════════════════════════════════════
    # METRIC CARD WIDGET
    # ══════════════════════════════════════════════════════════════

    class MetricCard(QFrame):
        """A single styled metric display card with label, value, and subtitle."""

        def __init__(self, label: str, accent: str = "#58a6ff", parent=None):
            super().__init__(parent)
            self._accent = accent
            self.setMinimumHeight(80)
            self.setStyleSheet(f"""
                MetricCard {{
                    background: #161b22;
                    border: 1px solid #21262d;
                    border-left: 3px solid {accent};
                    border-radius: 6px;
                }}
            """)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(2)

            self._label_widget = QLabel(label.upper())
            self._label_widget.setStyleSheet(
                f"color: {accent}; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 1px;"
            )

            self._value_widget = QLabel("—")
            self._value_widget.setStyleSheet(
                "color: #e6edf3; font-size: 22pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif;"
            )

            self._sub_widget = QLabel("")
            self._sub_widget.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-family: 'Segoe UI', sans-serif;"
            )

            layout.addWidget(self._label_widget)
            layout.addWidget(self._value_widget)
            layout.addWidget(self._sub_widget)

        def set_value(self, value: str, subtitle: str = ""):
            self._value_widget.setText(value)
            self._sub_widget.setText(subtitle)


    # ══════════════════════════════════════════════════════════════
    # LIVE STATUS BAR
    # ══════════════════════════════════════════════════════════════

    class StatusBar(QWidget):
        """Top header bar: title, live indicator, session timer, COM port."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedHeight(44)
            self.setStyleSheet("background: #0d1117; border-bottom: 1px solid #21262d;")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(16, 0, 16, 0)

            # Title
            title = QLabel("BRAILLE PERFORMANCE MONITOR")
            title.setStyleSheet(
                "color: #e6edf3; font-size: 11pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 2px;"
            )

            # Separator
            sep = QLabel("│")
            sep.setStyleSheet("color: #30363d; font-size: 14pt; margin: 0 8px;")

            # Live indicator label
            self._live_label = QLabel("● LIVE")
            self._live_label.setStyleSheet(
                "color: #3fb950; font-size: 9pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif;"
            )

            # Timer
            self._timer_label = QLabel("00:00")
            self._timer_label.setStyleSheet(
                "color: #8b949e; font-size: 9pt; font-family: 'Segoe UI Mono', monospace;"
            )

            # COM port
            self._port_label = QLabel(f"COM: {PORT}")
            self._port_label.setStyleSheet(
                "color: #8b949e; font-size: 9pt; font-family: 'Segoe UI', sans-serif;"
            )

            # Weight preset info
            self._preset_label = QLabel(f"Preset: {_WEIGHT_PRESET}")
            self._preset_label.setStyleSheet(
                "color: #58a6ff; font-size: 8pt; font-family: 'Segoe UI', sans-serif;"
            )

            layout.addWidget(title)
            layout.addWidget(sep)
            layout.addWidget(self._live_label)
            layout.addStretch()
            layout.addWidget(self._preset_label)
            layout.addSpacing(20)
            layout.addWidget(self._timer_label)
            layout.addSpacing(20)
            layout.addWidget(self._port_label)

            # Pulse timer for the LIVE dot
            self._pulse = True
            self._pulse_timer = QTimer()
            self._pulse_timer.timeout.connect(self._pulse_tick)
            self._pulse_timer.start(800)

            self._start_time = time.time()

        def _pulse_tick(self):
            self._pulse = not self._pulse
            if self._pulse:
                self._live_label.setStyleSheet(
                    "color: #3fb950; font-size: 9pt; font-weight: bold; "
                    "font-family: 'Segoe UI', sans-serif;"
                )
            else:
                self._live_label.setStyleSheet(
                    "color: #1a3a1a; font-size: 9pt; font-weight: bold; "
                    "font-family: 'Segoe UI', sans-serif;"
                )

        def tick(self):
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            self._timer_label.setText(f"{m:02d}:{s:02d}")


    # ══════════════════════════════════════════════════════════════
    # METRICS PANEL (grid of MetricCards)
    # ══════════════════════════════════════════════════════════════

    class MetricsPanel(QWidget):
        """Grid of MetricCards showing live session metrics."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background: #0d1117;")
            grid = QGridLayout(self)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(8)

            # ── Row 0: Speed ──────────────────────────────
            self._wpm      = MetricCard("WPM",         "#58a6ff")
            self._trend    = MetricCard("EMA Trend",   "#58a6ff")
            self._chars    = MetricCard("Characters",  "#58a6ff")
            grid.addWidget(self._wpm,   0, 0)
            grid.addWidget(self._trend, 0, 1)
            grid.addWidget(self._chars, 0, 2)

            # ── Row 1: Accuracy ───────────────────────────
            self._eff      = MetricCard("Path Eff.",      "#3fb950")
            self._reg      = MetricCard("Regressions",    "#3fb950")
            self._hes      = MetricCard("Hesitation Rate","#3fb950")
            grid.addWidget(self._eff, 1, 0)
            grid.addWidget(self._reg, 1, 1)
            grid.addWidget(self._hes, 1, 2)

            # ── Row 2: Difficulty ─────────────────────────
            self._diff     = MetricCard("Avg Difficulty", "#f0883e")
            self._rev      = MetricCard("Reversals",      "#f0883e")
            self._consist  = MetricCard("Consistency",    "#f0883e")
            grid.addWidget(self._diff,    2, 0)
            grid.addWidget(self._rev,     2, 1)
            grid.addWidget(self._consist, 2, 2)

            # ── Row 3: Current touch status ───────────────
            self._word_now = MetricCard("Current Word",   "#e6edf3")
            self._skip     = MetricCard("Skip Rate",      "#f85149")
            self._touch_ms = MetricCard("Touch Duration", "#8b949e")
            grid.addWidget(self._word_now, 3, 0)
            grid.addWidget(self._skip,     3, 1)
            grid.addWidget(self._touch_ms, 3, 2)

        def update_metrics(self, m, ws, vt, ewiqr_snap, diff_snap,
                           eff_avg, wpm_ema, finger_wpms, skip_snap):
            _wpm = m["wpm"]
            _eff = eff_avg
            _diff = m["avg_difficulty"]
            _cons = vt["consistency"]

            # WPM color
            wpm_color = (
                "#3fb950" if _wpm >= 50 else
                ("#f0883e" if _wpm >= 20 else "#f85149")
            )
            self._wpm.setStyleSheet(self._wpm.styleSheet()  # keep card style
                .replace(self._wpm._accent, wpm_color))
            self._wpm._accent = wpm_color
            self._wpm.set_value(f"{_wpm:.0f}",
                                f"F0: {finger_wpms[0]:.0f}  F1: {finger_wpms[1]:.0f}")

            self._trend.set_value(f"{wpm_ema:.0f}", "EMA smoothed")
            self._chars.set_value(str(m["chars_total"]),
                                  f"{m['chars_window']} in window")

            self._eff.set_value(f"{_eff:.2f}",
                                f"Backtracks: {m['total_backtracks']}")
            self._reg.set_value(str(ws["total_regressions"]),
                                f"Flagged: {len(ws['flagged_words'])}")
            self._hes.set_value(f"{ws['hesitation_rate']*100:.0f}%",
                                "regression / total touches")

            self._diff.set_value(f"{_diff:.2f}",
                                 f"Word rev: {m['word_reversals_total']}")
            self._rev.set_value(f"{m['avg_reversals']:.1f}",
                                "avg per touch")
            self._consist.set_value(f"{_cons:.2f}",
                                    f"IQR: {vt['iqr']:.2f}")

            cw = m.get("current_word", "") or "—"
            touch_icon = "▶" if m["is_touching"] else "○"
            self._word_now.set_value(cw,
                                     f"{touch_icon} {m['pressed_cells']} cells active")
            self._skip.set_value(f"{skip_snap['skip_rate']:.0f}%",
                                 f"{len(skip_snap['skipped_words'])} words skipped")
            self._touch_ms.set_value(f"{m['avg_duration']*1000:.0f} ms",
                                     f"{vt['mean_vel']:.1f} cells/s")


    # ══════════════════════════════════════════════════════════════
    # WORD STATS TABLE
    # ══════════════════════════════════════════════════════════════

    class WordStatsPanel(QWidget):
        """Compact scoreboard table showing per-word stats."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background: #0d1117;")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            hdr = QLabel("WORD SCOREBOARD")
            hdr.setStyleSheet(
                "color: #58a6ff; font-size: 9pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 1px;"
            )
            layout.addWidget(hdr)


            self._table = QTableWidget(0, 4)
            self._table.setHorizontalHeaderLabels(["Word", "Touches", "Regress.", "Status"])
            self._table.setStyleSheet(f"""
                QTableWidget {{
                    background: #161b22;
                    color: #e6edf3;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 9pt;
                    border: 1px solid #21262d;
                    border-radius: 4px;
                    gridline-color: #21262d;
                }}
                QHeaderView::section {{
                    background: #0d1117;
                    color: #8b949e;
                    border: none;
                    border-bottom: 1px solid #30363d;
                    font-size: 8pt;
                    font-weight: bold;
                    padding: 4px 8px;
                    letter-spacing: 1px;
                }}
                QTableWidget::item {{
                    padding: 4px 8px;
                    border-bottom: 1px solid #21262d;
                }}
                QTableWidget::item:selected {{
                    background: #21262d;
                }}
            """)
            self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
            self._table.verticalHeader().setVisible(False)
            self._table.setSelectionMode(QTableWidget.NoSelection)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(self._table, 1)

            # Sequence strip
            seq_hdr = QLabel("RECENT SEQUENCE")
            seq_hdr.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI', sans-serif; letter-spacing: 1px; margin-top: 4px;"
            )
            self._seq_label = QLabel("—")
            self._seq_label.setStyleSheet(
                "color: #e6edf3; font-size: 9pt; font-family: 'Segoe UI', sans-serif;"
            )
            self._seq_label.setWordWrap(True)
            layout.addWidget(seq_hdr)
            layout.addWidget(self._seq_label)

        def update_stats(self, ws, skip_snap):
            wc   = ws["word_count"]
            rc   = ws.get("regression_count", {})
            # rc may not be directly in snapshot; rebuild from top_regressed
            reg_dict = dict(ws.get("top_regressed", []))
            flagged  = set(ws["flagged_words"])

            # Sort by touches descending
            sorted_words = sorted(wc.items(), key=lambda x: x[1], reverse=True)

            self._table.setRowCount(len(sorted_words))
            for i, (word, touches) in enumerate(sorted_words):
                regressions = reg_dict.get(word, 0)
                if word in flagged:
                    status, status_color = "FLAGGED", "#f85149"
                    row_bg = QColor("#2d0a0a")
                elif regressions > 0:
                    status, status_color = "Regression", "#f0883e"
                    row_bg = QColor("#2d1a00")
                else:
                    status, status_color = "OK", "#3fb950"
                    row_bg = QColor("#161b22")

                for col_idx, text in enumerate([word, str(touches), str(regressions), status]):
                    item = QTableWidgetItem(text)
                    item.setForeground(QColor(status_color if col_idx == 3 else "#e6edf3"))
                    item.setBackground(row_bg)
                    self._table.setItem(i, col_idx, item)

            seq_display = " → ".join(ws["touch_sequence"][-7:]) \
                          if ws["touch_sequence"] else "—"
            self._seq_label.setText(seq_display)


    # ══════════════════════════════════════════════════════════════
    # PLOT PANEL (unchanged widget classes, kept internal)
    # ══════════════════════════════════════════════════════════════

    class BarChartWidget(pg.PlotWidget):
        """Per-word dual bar chart using pyqtgraph."""

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Per-Word Performance (Time-on-Task & Touch Counts)",
                          color="#e6edf3", size="10pt")
            self.setLabel('left', "Time-on-Task (s)", color="#8b949e")
            self.setLabel('bottom', "Word", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self._last_update = 0
            self._word_list = []

            bottom_ax = self.getAxis('bottom')
            bottom_ax.setTickFont(QFont("Segoe UI", 7))
            bottom_ax.setTextPen(pg.mkPen("#8b949e"))
            bottom_ax.setStyle(tickTextOffset=6, autoExpandTextSpace=True,
                               autoReduceTextSpace=False)
            bottom_ax.setHeight(50)

        def update_chart(self, welford_snap, word_count, ewiqr_snap, wb_snap):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now

            word_list = []
            word_rows = []
            for ri in range(GRID):
                for e in wb_snap.get(ri, []):
                    word_list.append(e["word"])
                    word_rows.append(ri)

            if not word_list:
                return

            n = len(word_list)
            x = np.arange(n)
            tot_vals = np.array([welford_snap.get(w, {}).get("mean", 0.0) for w in word_list])
            cnt_vals = np.array([word_count.get(w, 0) for w in word_list], dtype=float)

            cnt_max = max(cnt_vals.max(), 1)
            tot_max = max(tot_vals.max(), 0.1)
            cnt_scaled = cnt_vals / cnt_max * tot_max if cnt_max > 0 else cnt_vals

            tab10 = plt.cm.tab10
            colors_tot = [pg.mkColor(*[int(c * 255) for c in tab10(wr)[:3]]) for wr in word_rows]
            colors_cnt = [pg.mkColor(*[int(c * 255) for c in tab10(wr)[:3]], 80) for wr in word_rows]

            self.clear()

            bw = 0.35
            bg_tot = pg.BarGraphItem(x=x - bw/2, height=tot_vals, width=bw, brushes=colors_tot)
            self.addItem(bg_tot)
            bg_cnt = pg.BarGraphItem(x=x + bw/2, height=cnt_scaled, width=bw, brushes=colors_cnt)
            self.addItem(bg_cnt)

            if welford_snap:
                total_n = sum(v.get("n", 0) for v in welford_snap.values())
                if total_n > 0:
                    session_avg = sum(v.get("mean", 0) * v.get("n", 0)
                                      for v in welford_snap.values()) / total_n
                    self.addLine(y=session_avg,
                                 pen=pg.mkPen("#3fb950", style=Qt.DashLine, width=1.5))

            ax = self.getAxis('bottom')
            ax.setTicks([[(i, w) for i, w in enumerate(word_list)]])
            ax.setTickFont(QFont("Segoe UI", 7))
            ax.setTextPen(pg.mkPen("#8b949e"))
            self._word_list = word_list


    class WPMTrendWidget(pg.PlotWidget):
        """Live WPM trend plot with raw + EMA lines."""

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Live WPM Trend", color="#e6edf3", size="10pt")
            self.setLabel('left', "Words Per Minute", color="#8b949e")
            self.setLabel('bottom', "Session Time (s)", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self.addLegend(offset=(10, 10))
            self._line_raw = self.plot([], [], pen=pg.mkPen("#334466", width=1), name="Raw WPM")
            self._line_ema = self.plot([], [], pen=pg.mkPen("#58a6ff", width=2.5), name="EMA Trend")
            self.addLine(y=50,  pen=pg.mkPen("#f0883e", style=Qt.DashLine, width=0.9))
            self.addLine(y=100, pen=pg.mkPen("#3fb950", style=Qt.DashLine, width=0.9))
            self._lbl_50 = pg.TextItem("50 WPM", color="#f0883e", anchor=(1.0, 1.0))
            self._lbl_50.setFont(QFont("Segoe UI", 7))
            self._lbl_50.setPos(10, 50)
            self.addItem(self._lbl_50)
            self._lbl_100 = pg.TextItem("100 WPM", color="#3fb950", anchor=(1.0, 1.0))
            self._lbl_100.setFont(QFont("Segoe UI", 7))
            self._lbl_100.setPos(10, 100)
            self.addItem(self._lbl_100)
            self._last_update = 0

        def update_trend(self, x_raw, y_raw, y_ema, y_max):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now
            if not x_raw:
                return
            self._line_raw.setData(x_raw, y_raw)
            self._line_ema.setData(x_raw, y_ema)
            self.setYRange(0, max(10, y_max))
            x_end = max(x_raw[-1], 10)
            self.setXRange(x_raw[0], x_end)
            self._lbl_50.setPos(x_end, 50)
            self._lbl_100.setPos(x_end, 100)


    class RegressionChartWidget(pg.PlotWidget):
        """Horizontal bar chart for inter-word regressions."""

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Most-Regressed Words", color="#e6edf3", size="10pt")
            self.setLabel('bottom', "Regression count", color="#8b949e")
            self.showGrid(x=True, alpha=0.2)
            self._last_update = 0
            self._empty_text = pg.TextItem("No regressions yet", color="#444444", anchor=(0.5, 0.5))
            self._empty_text.setFont(QFont("Segoe UI", 11))
            self.addItem(self._empty_text)
            self._empty_text.setPos(5, 0)

            # Legend note
            self._legend_red  = pg.TextItem(
                f"● Red = flagged (>{REGRESSION_FLAG_THRESHOLD}x)",
                color="#f85149", anchor=(0.0, 0.0))
            self._legend_red.setFont(QFont("Segoe UI", 7))
            self._legend_blue = pg.TextItem("● Blue = normal",
                color="#58a6ff", anchor=(0.0, 0.0))
            self._legend_blue.setFont(QFont("Segoe UI", 7))
            self.addItem(self._legend_red)
            self.addItem(self._legend_blue)

        def update_regressions(self, regression_count, flagged_words):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now

            visible = {w: c for w, c in regression_count.items() if c > 0}
            sorted_items = sorted(visible.items(), key=lambda x: x[1], reverse=True)

            self.clear()
            self._legend_red  = pg.TextItem(
                f"● Red = flagged (>{REGRESSION_FLAG_THRESHOLD}x)",
                color="#f85149", anchor=(0.0, 0.0))
            self._legend_red.setFont(QFont("Segoe UI", 7))
            self._legend_blue = pg.TextItem("● Blue = normal",
                color="#58a6ff", anchor=(0.0, 0.0))
            self._legend_blue.setFont(QFont("Segoe UI", 7))

            if not sorted_items:
                self._empty_text = pg.TextItem("No regressions yet",
                                               color="#444444", anchor=(0.5, 0.5))
                self._empty_text.setFont(QFont("Segoe UI", 11))
                self.addItem(self._empty_text)
                self._empty_text.setPos(5, 0)
                self.addItem(self._legend_red)
                self.addItem(self._legend_blue)
                return

            words = [item[0] for item in sorted_items]
            counts = [item[1] for item in sorted_items]
            flagged_set = set(flagged_words)
            y_pos = np.arange(len(words))
            colors = [pg.mkColor("#f85149") if w in flagged_set
                      else pg.mkColor("#58a6ff") for w in words]

            bg = pg.BarGraphItem(x0=0, y=y_pos, height=0.6, width=counts, brushes=colors)
            self.addItem(bg)

            ax = self.getAxis('left')
            ax.setTicks([[(i, w) for i, w in enumerate(words)]])
            self.invertY(True)
            self.setXRange(0, max(1, max(counts) * 1.15))

            for i, c in enumerate(counts):
                txt = pg.TextItem(str(c), color="#e6edf3", anchor=(0, 0.5))
                txt.setFont(QFont("Segoe UI", 9, QFont.Bold))
                txt.setPos(c + 0.1, i)
                self.addItem(txt)

            self.addItem(self._legend_red)
            self.addItem(self._legend_blue)
            n = len(words)
            self._legend_red.setPos(0, -1.2 if n > 0 else 0)
            self._legend_blue.setPos(max(counts) * 0.4, -1.2 if n > 0 else 0)


    class PerfHeatmapWidget(pg.GraphicsLayoutWidget):
        """Performance heatmap (Time-on-Task or EWIQR Difficulty)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setBackground("#0d1117")
            self._mode = 'tot'
            self._last_update = 0

            self._plot = self.addPlot(title="Performance Heatmap")
            self._plot.invertY(True)
            self._plot.setRange(xRange=[-0.5, GRID - 0.5], yRange=[-0.5, GRID - 0.5])
            self._plot.setAspectLocked(True)

            self._img = pg.ImageItem()
            ylrd_lut = self._build_ylrd_lut()
            self._img.setLookupTable(ylrd_lut)
            self._plot.addItem(self._img)

            self._texts = {}
            for r in range(GRID):
                for c in range(GRID):
                    word = get_word_from_touch(r, c) or "?"
                    txt = pg.TextItem(f"{word}\n—", color="#111111", anchor=(0.5, 0.5))
                    txt.setFont(QFont("Segoe UI", 7, QFont.Bold))
                    txt.setPos(c, r)
                    self._plot.addItem(txt)
                    self._texts[(r, c)] = txt

            for i in range(GRID + 1):
                pos = i - 0.5
                self._plot.addLine(x=pos, pen=pg.mkPen("#21262d", width=1))
                self._plot.addLine(y=pos, pen=pg.mkPen("#21262d", width=1))

            x_ticks = [(i, f"C{i}") for i in range(GRID)]
            y_ticks = [(i, f"R{i}") for i in range(GRID)]
            self._plot.getAxis('bottom').setTicks([x_ticks])
            self._plot.getAxis('left').setTicks([y_ticks])

        @staticmethod
        def _build_ylrd_lut():
            colors = [(0, 0, 0), (255, 255, 204), (254, 217, 118),
                      (254, 178, 76), (253, 141, 60), (240, 59, 32), (189, 0, 38)]
            lut = np.zeros((256, 4), dtype=np.ubyte)
            n = len(colors) - 1
            for i in range(256):
                t = i / 255.0 * n
                idx = int(t)
                f = t - idx
                if idx >= n:
                    idx, f = n - 1, 1.0
                c0, c1 = colors[idx], colors[idx + 1]
                lut[i] = [int(c0[j] + f * (c1[j] - c0[j])) for j in range(3)] + [255]
            return lut

        def set_mode(self, mode):
            self._mode = mode
            self._last_update = 0

        def update_perf(self, Z_tot, Z_diff, wb_snap):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now
            Z = Z_tot if self._mode == 'tot' else Z_diff
            z_max = float(Z.max()) if Z.max() > 0 else 1.0
            normalized = np.clip(Z / z_max * 255, 0, 255).astype(np.ubyte)
            self._img.setImage(normalized.T, levels=[0, 255])
            self._img.setRect(-0.5, -0.5, GRID, GRID)
            mode_label = "Time-on-Task" if self._mode == 'tot' else "EWIQR Difficulty"
            self._plot.setTitle(f"Performance Heatmap — {mode_label}")
            for r in range(GRID):
                for c in range(GRID):
                    word = get_word_from_touch(r, c) or "?"
                    val = Z[r, c]
                    val_str = f"{val:.2f}" if val > 0 else "—"
                    self._texts[(r, c)].setText(f"{word}\n{val_str}")


    class VelocityProfileWidget(pg.PlotWidget):
        """Last-N velocity profile overlay."""

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Velocity Profile — last 20 touches",
                          color="#e6edf3", size="10pt")
            self.setLabel('left', "Velocity (cells/sec)", color="#8b949e")
            self.setLabel('bottom', "Step index", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self.addLine(y=0, pen=pg.mkPen("#30363d", width=0.5))
            self._lines_past = []
            self.addLegend(offset=(10, 10))
            self._line_recent = self.plot([], [], pen=pg.mkPen("#58a6ff", width=2.5),
                                          name="Most recent")
            self._line_mean = self.plot([], [], pen=pg.mkPen("#f0883e", width=2,
                                             style=Qt.DashLine), name="Weighted mean")
            self._last_update = 0

        def update_velocities(self, vel_history_snapshot, alpha_weight=0.15):
            now = time.time()
            if now - self._last_update < 0.2:
                return
            self._last_update = now
            vels = vel_history_snapshot
            if not vels:
                return
            for line in self._lines_past:
                self.removeItem(line)
            self._lines_past = []
            N = len(vels)
            for i in range(N - 1):
                v = vels[i]
                if len(v) >= 2:
                    x = np.arange(len(v))
                    line = self.plot(x, v, pen=pg.mkPen("#444444", width=0.8))
                    line.setOpacity(0.2)
                    self._lines_past.append(line)
            v_recent = vels[-1]
            if len(v_recent) >= 2:
                self._line_recent.setData(np.arange(len(v_recent)), v_recent)
            else:
                self._line_recent.setData([], [])
            mean_vel, _ = VelocityProfileMonitor._compute_weighted_mean_velocity(
                vels, alpha_weight)
            if mean_vel is not None:
                self._line_mean.setData(np.arange(len(mean_vel)), mean_vel)
            else:
                self._line_mean.setData([], [])
            all_vals = []
            for va in vels:
                if len(va) >= 2:
                    all_vals.extend(va.tolist())
            if all_vals:
                self.setYRange(-0.1, max(0.5, max(all_vals) * 1.1))
            max_step = max(len(v) for v in vels)
            self.setXRange(-1, max(2, max_step))


    class EfficiencyWidget(pg.PlotWidget):
        """Path efficiency scatter + trend plot."""

        def __init__(self, parent=None):
            super().__init__(parent, background="#0d1117")
            self.setTitle("Path Efficiency Over Session", color="#e6edf3", size="10pt")
            self.setLabel('left', "Path efficiency (η)", color="#8b949e")
            self.setLabel('bottom', "Contact # (press→release)", color="#8b949e")
            self.showGrid(y=True, alpha=0.2)
            self.setYRange(0, 1.05)
            self.setXRange(0, 10)
            self.addLine(y=0.8, pen=pg.mkPen("#3fb950", width=1.5, style=Qt.DashLine))
            from pyqtgraph import LinearRegionItem
            band_g = LinearRegionItem([0.8, 1.05], orientation='horizontal',
                                       brush=pg.mkBrush(63, 185, 80, 15), movable=False)
            band_o = LinearRegionItem([0.5, 0.8],  orientation='horizontal',
                                       brush=pg.mkBrush(240, 136, 62, 15), movable=False)
            band_r = LinearRegionItem([0.0, 0.5],  orientation='horizontal',
                                       brush=pg.mkBrush(248, 81, 73, 15), movable=False)
            for b in (band_g, band_o, band_r):
                b.setZValue(-10)
                self.addItem(b)
            _lbl_p = pg.TextItem("Proficient",  color="#3fb950", anchor=(1.0, 0.5))
            _lbl_p.setFont(QFont("Segoe UI", 7))
            _lbl_p.setPos(10, 0.90)
            self.addItem(_lbl_p)
            self._lbl_p = _lbl_p
            _lbl_d = pg.TextItem("Developing", color="#f0883e", anchor=(1.0, 0.5))
            _lbl_d.setFont(QFont("Segoe UI", 7))
            _lbl_d.setPos(10, 0.65)
            self.addItem(_lbl_d)
            self._lbl_d = _lbl_d
            _lbl_s = pg.TextItem("Struggling", color="#f85149", anchor=(1.0, 0.5))
            _lbl_s.setFont(QFont("Segoe UI", 7))
            _lbl_s.setPos(10, 0.25)
            self.addItem(_lbl_s)
            self._lbl_s = _lbl_s
            self.addLegend(offset=(10, 10))
            self._scatter = pg.ScatterPlotItem(size=8, pen=pg.mkPen("#30363d", width=0.5))
            self.addItem(self._scatter)
            self._conn_line = self.plot([], [], pen=pg.mkPen("#58a6ff", width=1.2), name="Path")
            self._conn_line.setOpacity(0.4)
            self._trend_line = self.plot([], [], pen=pg.mkPen("#f0883e", width=3), name="Trend")
            self.plot([], [], pen=pg.mkPen("#3fb950", width=1.5, style=Qt.DashLine),
                      name="Proficiency target (η=0.8)")
            self._last_update = 0

        def update_efficiency(self, eff_hist, evt_idx, cached_trend_x, cached_trend_y):
            now = time.time()
            if now - self._last_update < 0.5:
                return
            self._last_update = now
            if len(eff_hist) < 2:
                return
            colors = []
            for eta in eff_hist:
                if eta >= 0.8:
                    colors.append(pg.mkBrush("#3fb950"))
                elif eta >= 0.5:
                    colors.append(pg.mkBrush("#f0883e"))
                else:
                    colors.append(pg.mkBrush("#f85149"))
            spots = [{'pos': (x, y), 'brush': b}
                     for x, y, b in zip(evt_idx, eff_hist, colors)]
            self._scatter.setData(spots)
            self._conn_line.setData(evt_idx, eff_hist)
            if cached_trend_y is not None and len(cached_trend_y) > 0:
                self._trend_line.setData(cached_trend_x, cached_trend_y)
            if evt_idx:
                x_end = max(evt_idx) + 5
                self.setXRange(0, x_end)
                self._lbl_p.setPos(x_end - 1, 0.90)
                self._lbl_d.setPos(x_end - 1, 0.65)
                self._lbl_s.setPos(x_end - 1, 0.25)


    # ── Plot selector panel ──────────────────────────────────────

    class PlotPanel(QWidget):
        """Switchable plot panel with sidebar selector and stacked plots."""

        PLOT_LABELS = [
            "Per-Word Bars",
            "WPM Trend",
            "Regression Chart",
            "Perf. Heatmap",
            "Velocity Profile",
            "Path Efficiency",
        ]

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background: #0d1117;")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Sidebar
            sidebar = QWidget()
            sidebar.setFixedWidth(120)
            sidebar.setStyleSheet("background: #161b22; border-right: 1px solid #21262d;")
            sb_layout = QVBoxLayout(sidebar)
            sb_layout.setContentsMargins(0, 8, 0, 8)
            sb_layout.setSpacing(0)

            sidebar_lbl = QLabel("CHARTS")
            sidebar_lbl.setStyleSheet(
                "color: #8b949e; font-size: 7pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 4px 12px;"
            )
            sb_layout.addWidget(sidebar_lbl)

            self._buttons = []
            for i, label in enumerate(self.PLOT_LABELS):
                btn = QPushButton(label)
                btn.setCheckable(True)
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #8b949e;
                        border: none;
                        text-align: left;
                        padding: 10px 14px;
                        font-family: 'Segoe UI';
                        font-size: 9pt;
                    }
                    QPushButton:checked {
                        background: #21262d;
                        color: #58a6ff;
                        border-left: 3px solid #58a6ff;
                    }
                    QPushButton:hover:!checked {
                        background: #1a1f26;
                        color: #c9d1d9;
                    }
                """)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda checked, idx=i: self._on_select(idx))
                sb_layout.addWidget(btn)
                self._buttons.append(btn)

            sb_layout.addStretch()
            layout.addWidget(sidebar)

            # Stacked widget
            self._stack = QStackedWidget()
            self._stack.setStyleSheet("background: #0d1117;")

            self.bar_chart   = BarChartWidget()
            self.wpm_trend   = WPMTrendWidget()
            self.regression  = RegressionChartWidget()
            self.perf_heatmap = PerfHeatmapWidget()
            self.velocity    = VelocityProfileWidget()
            self.efficiency  = EfficiencyWidget()

            # Performance heatmap with mode toggle
            perf_container = QWidget()
            perf_layout = QVBoxLayout(perf_container)
            perf_layout.setContentsMargins(0, 4, 0, 0)
            mode_bar = QHBoxLayout()
            self._btn_tot  = QPushButton("Time-on-Task")
            self._btn_diff = QPushButton("EWIQR Difficulty")
            for btn in (self._btn_tot, self._btn_diff):
                btn.setStyleSheet("""
                    QPushButton {
                        background: #161b22; color: #e6edf3;
                        font-size: 9pt; padding: 4px 14px;
                        border: 1px solid #30363d; border-radius: 4px;
                        font-family: 'Segoe UI';
                    }
                    QPushButton:hover { background: #21262d; }
                """)
                btn.setCursor(Qt.PointingHandCursor)
            self._btn_tot.clicked.connect(lambda: self.perf_heatmap.set_mode('tot'))
            self._btn_diff.clicked.connect(lambda: self.perf_heatmap.set_mode('diff'))
            mode_bar.addWidget(self._btn_tot)
            mode_bar.addWidget(self._btn_diff)
            mode_bar.addStretch()
            perf_layout.addLayout(mode_bar)
            perf_layout.addWidget(self.perf_heatmap, 1)

            self._stack.addWidget(self.bar_chart)    # 0
            self._stack.addWidget(self.wpm_trend)    # 1
            self._stack.addWidget(self.regression)   # 2
            self._stack.addWidget(perf_container)    # 3
            self._stack.addWidget(self.velocity)     # 4
            self._stack.addWidget(self.efficiency)   # 5

            layout.addWidget(self._stack, 1)

            # Select first
            self._on_select(0)

        def _on_select(self, idx):
            self._stack.setCurrentIndex(idx)
            for i, btn in enumerate(self._buttons):
                btn.setChecked(i == idx)

        @property
        def active_index(self):
            return self._stack.currentIndex()


    # ══════════════════════════════════════════════════════════════
    # MAIN WINDOW
    # ══════════════════════════════════════════════════════════════

    class BrailleMainWindow(QMainWindow):
        """Main PyQtGraph application window — full redesign."""

        def __init__(self):
            super().__init__()
            self.setWindowTitle("Braille Touch Performance Monitor")
            self.setMinimumSize(1400, 860)

            pg.setConfigOptions(background="#0d1117", foreground="#e6edf3",
                                antialias=True)

            palette = QPalette()
            palette.setColor(QPalette.Window,      QColor("#0d1117"))
            palette.setColor(QPalette.WindowText,  QColor("#e6edf3"))
            palette.setColor(QPalette.Base,        QColor("#161b22"))
            palette.setColor(QPalette.Text,        QColor("#e6edf3"))
            palette.setColor(QPalette.Button,      QColor("#161b22"))
            palette.setColor(QPalette.ButtonText,  QColor("#e6edf3"))
            palette.setColor(QPalette.Highlight,   QColor("#58a6ff"))
            palette.setColor(QPalette.HighlightedText, QColor("#0d1117"))
            self.setPalette(palette)
            self.setStyleSheet("QMainWindow { background: #0d1117; }")

            self._build_ui()

            # Snapshot cache
            self._cached_ws    = None
            self._cached_ewiqr = None
            self._cached_welford = None
            self._cached_vt    = None
            self._cached_skip  = None
            self._cached_diff  = None
            self._cached_wb    = None
            self._last_snap    = 0

            # Main update timer — 30fps
            self._timer = QTimer()
            self._timer.timeout.connect(self._update)
            self._timer.start(33)

        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # ── Header bar ──────────────────────────────────────
            self._status_bar = StatusBar()
            root_layout.addWidget(self._status_bar)

            # ── Main content area ────────────────────────────────
            content = QWidget()
            content.setStyleSheet("background: #0d1117;")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(10, 10, 10, 10)
            content_layout.setSpacing(8)

            # ── Upper split: Heatmap | Metrics | Word stats ──────
            upper_splitter = QSplitter(Qt.Horizontal)
            upper_splitter.setHandleWidth(2)
            upper_splitter.setStyleSheet("""
                QSplitter::handle { background: #21262d; }
            """)

            # Heatmap with section label
            heatmap_container = QWidget()
            heatmap_container.setStyleSheet("background: #0d1117;")
            hm_layout = QVBoxLayout(heatmap_container)
            hm_layout.setContentsMargins(0, 0, 0, 0)
            hm_layout.setSpacing(4)
            hm_lbl = QLabel("TOUCH PRESSURE MAP")
            hm_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._heatmap = HeatmapWidget()
            hm_layout.addWidget(hm_lbl)
            hm_layout.addWidget(self._heatmap, 1)
            upper_splitter.addWidget(heatmap_container)

            # Metrics panel with section label
            metrics_container = QWidget()
            metrics_container.setStyleSheet("background: #0d1117;")
            mc_layout = QVBoxLayout(metrics_container)
            mc_layout.setContentsMargins(0, 0, 0, 0)
            mc_layout.setSpacing(4)
            mc_lbl = QLabel("LIVE METRICS")
            mc_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._metrics = MetricsPanel()
            mc_layout.addWidget(mc_lbl)
            mc_layout.addWidget(self._metrics, 1)
            upper_splitter.addWidget(metrics_container)

            # Word stats with section label
            ws_container = QWidget()
            ws_container.setStyleSheet("background: #0d1117;")
            ws_layout = QVBoxLayout(ws_container)
            ws_layout.setContentsMargins(0, 0, 0, 0)
            ws_layout.setSpacing(4)
            ws_lbl = QLabel("WORD SCOREBOARD")
            ws_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._word_stats_panel = WordStatsPanel()
            ws_layout.addWidget(ws_lbl)
            ws_layout.addWidget(self._word_stats_panel, 1)
            upper_splitter.addWidget(ws_container)

            upper_splitter.setSizes([420, 520, 380])
            content_layout.addWidget(upper_splitter, 2)

            # ── Divider ──────────────────────────────────────────
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet("background: #21262d; max-height: 1px;")
            content_layout.addWidget(divider)

            # ── Lower split: Plot panel | Controls ───────────────
            lower_splitter = QSplitter(Qt.Horizontal)
            lower_splitter.setHandleWidth(2)
            lower_splitter.setStyleSheet("QSplitter::handle { background: #21262d; }")

            # Plot panel
            plot_container = QWidget()
            plot_container.setStyleSheet("background: #0d1117;")
            pc_layout = QVBoxLayout(plot_container)
            pc_layout.setContentsMargins(0, 0, 0, 0)
            pc_layout.setSpacing(4)
            pc_lbl = QLabel("CHARTS")
            pc_lbl.setStyleSheet(
                "color: #8b949e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 2px; padding: 2px 4px;"
            )
            self._plot_panel = PlotPanel()
            pc_layout.addWidget(pc_lbl)
            pc_layout.addWidget(self._plot_panel, 1)
            lower_splitter.addWidget(plot_container)

            # Controls sidebar
            controls = QWidget()
            controls.setFixedWidth(280)
            controls.setStyleSheet(
                "background: #161b22; border-left: 1px solid #21262d;"
            )
            ctrl_layout = QVBoxLayout(controls)
            ctrl_layout.setContentsMargins(12, 12, 12, 12)
            ctrl_layout.setSpacing(12)

            # Threshold group
            thr_lbl = QLabel("TOUCH THRESHOLDS")
            thr_lbl.setStyleSheet(
                "color: #f0883e; font-size: 8pt; font-weight: bold; "
                "font-family: 'Segoe UI'; letter-spacing: 1px;"
            )
            ctrl_layout.addWidget(thr_lbl)

            self._threshold_sliders = []
            for i in range(GRID):
                row_widget = QWidget()
                row_widget.setStyleSheet("background: transparent;")
                row_h = QHBoxLayout(row_widget)
                row_h.setContentsMargins(0, 0, 0, 0)
                row_h.setSpacing(6)

                lbl = QLabel(f"R{i}")
                lbl.setFixedWidth(20)
                lbl.setStyleSheet(
                    "color: #58a6ff; font-family: 'Segoe UI Mono', monospace;"
                    "font-size: 8pt;"
                )
                sl = QSlider(Qt.Horizontal)
                sl.setRange(0, 100)
                sl.setValue(int(ROW_THRESHOLDS[i] * 2))
                sl.setStyleSheet("""
                    QSlider::groove:horizontal {
                        background: #21262d; height: 4px; border-radius: 2px;
                    }
                    QSlider::handle:horizontal {
                        background: #f0883e; width: 12px; margin: -4px 0;
                        border-radius: 6px;
                    }
                    QSlider::handle:horizontal:hover {
                        background: #ff9944;
                    }
                """)
                val_lbl = QLabel(f"{ROW_THRESHOLDS[i]:.1f}")
                val_lbl.setFixedWidth(32)
                val_lbl.setStyleSheet(
                    "color: #e6edf3; font-family: 'Segoe UI Mono', monospace;"
                    "font-size: 8pt;"
                )

                def _on_slider(value, row=i, vlbl=val_lbl):
                    real_val = value / 2.0
                    ROW_THRESHOLDS[row] = real_val
                    vlbl.setText(f"{real_val:.1f}")

                sl.valueChanged.connect(_on_slider)
                row_h.addWidget(lbl)
                row_h.addWidget(sl, 1)
                row_h.addWidget(val_lbl)
                ctrl_layout.addWidget(row_widget)
                self._threshold_sliders.append(sl)

            ctrl_layout.addStretch()

            # Buttons
            btn_edit = QPushButton("✎  Edit Words")
            btn_edit.setStyleSheet("""
                QPushButton {
                    background: #161b22; color: #58a6ff;
                    font-size: 10pt; font-weight: bold;
                    padding: 10px; border: 1px solid #30363d;
                    border-radius: 6px; font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #21262d; border-color: #58a6ff; }
            """)
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.clicked.connect(self._open_editor)
            ctrl_layout.addWidget(btn_edit)

            btn_end = QPushButton("⏹  End Session")
            btn_end.setStyleSheet("""
                QPushButton {
                    background: #161b22; color: #f85149;
                    font-size: 10pt; font-weight: bold;
                    padding: 10px; border: 1px solid #30363d;
                    border-radius: 6px; font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #21262d; border-color: #f85149; }
            """)
            btn_end.setCursor(Qt.PointingHandCursor)
            btn_end.clicked.connect(self.close)
            ctrl_layout.addWidget(btn_end)

            lower_splitter.addWidget(plot_container)
            lower_splitter.addWidget(controls)

            content_layout.addWidget(lower_splitter, 3)
            root_layout.addWidget(content, 1)

        def _open_editor(self):
            dlg = WordBoundaryEditorQt(self)
            dlg.exec_()
            self._heatmap.refresh_labels()

        def _update(self):
            """Main 30fps update loop."""
            now = time.time()

            # Tick session timer
            self._status_bar.tick()

            # Read latest frame
            with latest_frame_lk:
                frame = latest_frame.copy()

            # Compute delta + threshold mask
            raw_delta = np.maximum(frame - baseline, 0.0)
            thresh_delta = raw_delta * (raw_delta >= ROW_THRESHOLDS[:, np.newaxis])

            # Update heatmap every frame
            self._heatmap.update_data(thresh_delta)

            # Check for label refresh
            global _cell_labels_dirty
            if _cell_labels_dirty:
                _cell_labels_dirty = False
                self._heatmap.refresh_labels()

            # Throttled snapshots
            if self._cached_ws is None or (now - self._last_snap) >= _SNAPSHOT_INTERVAL:
                self._last_snap = now
                self._cached_diff    = cell_diff.snapshot()
                self._cached_ws      = word_stats.snapshot()
                self._cached_ewiqr   = ewiqr_tracker.snapshot()
                self._cached_welford = welford_per_word.snapshot()
                self._cached_vt      = velocity_tracker.snapshot()
                with word_boundaries_lock:
                    self._cached_wb = {k: list(v) for k, v in word_boundaries.items()}
                self._cached_skip = compute_skip_stats(
                    self._cached_wb, self._cached_ws["word_count"])

                m = perf.snapshot
                self._metrics.update_metrics(
                    m, self._cached_ws, self._cached_vt, self._cached_ewiqr,
                    self._cached_diff, eff_plot.get_avg_efficiency(),
                    wpm_trend.get_current_ema(), list(_cached_finger_wpm),
                    self._cached_skip)

                self._word_stats_panel.update_stats(self._cached_ws, self._cached_skip)

            if self._cached_ws is None:
                return

            # Update active plot only
            idx = self._plot_panel.active_index

            if idx == 0:
                self._plot_panel.bar_chart.update_chart(
                    self._cached_welford, self._cached_ws["word_count"],
                    self._cached_ewiqr, self._cached_wb)

            elif idx == 1:
                x_raw, y_raw, y_ema, y_max = wpm_trend.get_plot_data()
                self._plot_panel.wpm_trend.update_trend(x_raw, y_raw, y_ema, y_max)

            elif idx == 2:
                with word_stats._lock:
                    reg_count = dict(word_stats._regression_count)
                self._plot_panel.regression.update_regressions(
                    reg_count, self._cached_ws["flagged_words"])

            elif idx == 3:
                Z_tot  = np.zeros((GRID, GRID))
                Z_diff = np.zeros((GRID, GRID))
                for r in range(GRID):
                    for e in self._cached_wb.get(r, []):
                        w  = e["word"]
                        wf = self._cached_welford.get(w)
                        if wf:
                            for c in range(e["start"], e["end"] + 1):
                                if 0 <= c < GRID:
                                    Z_tot[r, c] = wf["mean"]
                        ewiqr_pw = self._cached_ewiqr.get("ewiqr_per_word", {})
                        if w in ewiqr_pw:
                            for c in range(e["start"], e["end"] + 1):
                                if 0 <= c < GRID:
                                    Z_diff[r, c] = ewiqr_pw[w]
                self._plot_panel.perf_heatmap.update_perf(Z_tot, Z_diff, self._cached_wb)

            elif idx == 4:
                with vel_profile._lock:
                    vel_snap = list(vel_profile._velocity_history)
                self._plot_panel.velocity.update_velocities(vel_snap)

            elif idx == 5:
                with eff_plot._lock:
                    eff_hist = list(eff_plot.efficiency_history)
                    evt_idx  = list(eff_plot.event_indices)
                cached_tx = eff_plot._cached_trend_x
                cached_ty = eff_plot._cached_trend_y
                self._plot_panel.efficiency.update_efficiency(
                    eff_hist, evt_idx, cached_tx, cached_ty)

            # Check editor request
            if _editor_requested.is_set():
                _editor_requested.clear()
                self._open_editor()

        def closeEvent(self, event):
            """Generate session figures, close DataLogger, print report."""
            self._timer.stop()

            # ── Generate session figures ────────────────────────────
            try:
                ws_final  = word_stats.snapshot()
                with word_boundaries_lock:
                    wb_final = {k: list(v) for k, v in word_boundaries.items()}
                ewiqr_final = ewiqr_tracker.snapshot()

                x_raw_f, y_raw_f, y_ema_f, _ = wpm_trend.get_plot_data()

                with word_stats._lock:
                    reg_count_f = dict(word_stats._regression_count)

                with vel_profile._lock:
                    vel_hist_f = [np.array(v) for v in vel_profile._velocity_history]

                with eff_plot._lock:
                    eff_hist_f = list(eff_plot.efficiency_history)
                    evt_idx_f  = list(eff_plot.event_indices)

                data_logger.generate_figures(
                    wpm_x=x_raw_f, wpm_raw=y_raw_f, wpm_ema=y_ema_f,
                    regression_count=reg_count_f,
                    flagged_words=ws_final["flagged_words"],
                    vel_history=vel_hist_f if vel_hist_f else [],
                    eff_history=eff_hist_f, eff_indices=evt_idx_f,
                    diff_z=ewiqr_final.get("Z_tot"),
                    wb_snap=wb_final,
                    weight_note=_WEIGHT_NOTE,
                )
            except Exception as e:
                print(f"[DataLogger] Figure generation error: {e}")

            # ── Close DataLogger ──────────────────────────────────
            try:
                data_logger.close()
            except Exception:
                pass

            # ── Print final report ────────────────────────────────
            _print_final_report()

            # ── Session summary dialog ────────────────────────────
            try:
                self._show_summary_dialog()
            except Exception:
                pass

            event.accept()

        def _show_summary_dialog(self):
            """Show a styled session summary dialog."""
            ws  = word_stats.snapshot()
            vt  = velocity_tracker.snapshot()
            m   = perf.snapshot

            dlg = QDialog(self)
            dlg.setWindowTitle("Session Summary")
            dlg.setMinimumWidth(480)
            dlg.setStyleSheet("""
                QDialog { background: #0d1117; }
                QLabel  { color: #e6edf3; font-family: 'Segoe UI'; }
            """)
            layout = QVBoxLayout(dlg)
            layout.setSpacing(16)
            layout.setContentsMargins(24, 24, 24, 24)

            title = QLabel("Session Complete")
            title.setStyleSheet(
                "color: #e6edf3; font-size: 16pt; font-weight: bold; "
                "font-family: 'Segoe UI';"
            )
            layout.addWidget(title)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("background: #21262d;")
            layout.addWidget(sep)

            grid = QGridLayout()
            grid.setSpacing(10)

            def _stat(label, value, accent="#58a6ff"):
                l = QLabel(label)
                l.setStyleSheet("color: #8b949e; font-size: 9pt;")
                v = QLabel(str(value))
                v.setStyleSheet(f"color: {accent}; font-size: 12pt; font-weight: bold;")
                return l, v

            stats = [
                ("Final WPM",        f"{m['wpm']:.0f}",                "#58a6ff"),
                ("EMA WPM Trend",    f"{wpm_trend.get_current_ema():.1f}", "#58a6ff"),
                ("Total Touches",    str(ws['total_registered']),       "#e6edf3"),
                ("Regressions",      str(ws['total_regressions']),      "#f0883e"),
                ("Hesitation Rate",  f"{ws['hesitation_rate']*100:.0f}%", "#f0883e"),
                ("Consistency",      f"{vt['consistency']:.2f}",        "#3fb950"),
                ("Path Efficiency",  f"{eff_plot.get_avg_efficiency():.2f}", "#3fb950"),
                ("Avg Difficulty",   f"{m['avg_difficulty']:.2f}",      "#f85149"),
                ("Most Touched",     ws['most_touched'] or '—',         "#e6edf3"),
                ("Hardest Word",     ws['hardest_word'] or '—',         "#f85149"),
                ("Data saved to",    "session_data/",                   "#8b949e"),
            ]

            for row_i, (label, value, accent) in enumerate(stats):
                l_w, v_w = _stat(label, value, accent)
                grid.addWidget(l_w, row_i, 0)
                grid.addWidget(v_w, row_i, 1)

            layout.addLayout(grid)

            btn_close = QPushButton("Close")
            btn_close.setStyleSheet("""
                QPushButton {
                    background: #161b22; color: #e6edf3;
                    font-size: 10pt; padding: 8px 24px;
                    border: 1px solid #30363d; border-radius: 6px;
                    font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #21262d; }
            """)
            btn_close.clicked.connect(dlg.accept)
            layout.addWidget(btn_close, 0, Qt.AlignRight)

            dlg.exec_()


    def _print_final_report():
        """Print comprehensive session report to console."""
        ws = word_stats.snapshot()
        print("\n═══ FINAL WORD STATS ═══")
        print(f"Total registered touches : {ws['total_registered']}")
        print(f"Most touched word        : {ws['most_touched']}")
        print(f"Hardest word             : {ws['hardest_word']}  "
              f"(avg D={ws['hardest_word_d']:.3f})")
        print(f"Final WPM (sliding window): {perf._wpm_counter.get_wpm()}")
        print(f"Final WPM trend (EMA)    : {wpm_trend.get_current_ema():.1f}")

        print("\n═══ PER-FINGER STATS (Butterfly) ═══")
        for fi in range(2):
            ft = finger_trackers[fi]
            fi_ws  = ft["word_stats"].snapshot()
            fi_wpm = ft["perf"]._wpm_counter.get_wpm()
            fi_trend = ft["wpm_trend"].get_current_ema()
            fi_vt  = ft["velocity"].snapshot()
            print(f"\n── Finger {fi} ──")
            print(f"  Touches: {fi_ws['total_registered']}")
            print(f"  WPM: {fi_wpm:.0f}  (EMA trend: {fi_trend:.1f})")
            print(f"  Regressions: {fi_ws['total_regressions']}")
            print(f"  Velocity: {fi_vt['mean_vel']:.1f} cells/s  "
                  f"consistency: {fi_vt['consistency']:.2f}")

        _, y_raw_final, y_ema_final, _ = wpm_trend.get_plot_data()
        if y_ema_final:
            print(f"\n═══ WPM TREND REPORT  [V-4] ═══")
            print(f"Raw WPM samples          : {len(y_raw_final)}")
            print(f"Peak raw WPM             : {max(y_raw_final):.0f}")
            print(f"Min raw WPM              : {min(y_raw_final):.0f}")
            print(f"Final EMA WPM            : {y_ema_final[-1]:.1f}")
            if len(y_ema_final) > 10:
                avg_ema = sum(y_ema_final) / len(y_ema_final)
                print(f"Session avg EMA WPM      : {avg_ema:.1f}")
                print(f"Peak sustained WPM (EMA) : {max(y_ema_final):.1f}")

        print("\n═══ REGRESSION REPORT  [M-H1] ═══")
        print(f"Total regressions        : {ws['total_regressions']}")
        print(f"Hesitation rate          : {ws['hesitation_rate']*100:.1f}%")
        if ws["top_regressed"]:
            print("\n── Top regressed words ──")
            for word, cnt in ws["top_regressed"]:
                flag = "  ⚠ FLAGGED" if word in ws["flagged_words"] else ""
                print(f"  {word:<14}: {cnt} regression(s){flag}")

        final_ewiqr = ewiqr_tracker.snapshot()
        final_welf  = welford_per_word.snapshot()
        print("\n═══ EWIQR DIFFICULTY REPORT  [M-D2] ═══")
        top5_final = final_ewiqr.get("top5_hardest", [])
        if top5_final:
            print("\n── Top 5 hardest (by EWIQR) ──")
            for rank, (tw, tewiqr) in enumerate(top5_final, 1):
                tconf = final_ewiqr["confidence_per_word"].get(tw, "?")
                tq1 = final_ewiqr["Q1_per_word"].get(tw, 0)
                tq3 = final_ewiqr["Q3_per_word"].get(tw, 0)
                print(f"  {rank}. {tw:<14}: EWIQR={tewiqr:.3f}s  "
                      f"Q1={tq1:.2f}s  Q3={tq3:.2f}s  [{tconf}]")

        with word_boundaries_lock:
            wb_final = {k: list(v) for k, v in word_boundaries.items()}
        skip_final = compute_skip_stats(wb_final, ws["word_count"])
        print("\n═══ SKIP STATISTICS REPORT  [M-D3] ═══")
        print(f"Skip rate                : {skip_final['skip_rate']:.1f}%")
        print(f"Skipped words            : {len(skip_final['skipped_words'])} / "
              f"{skip_final.get('total_words', GRID*GRID)}")
        print("\n── Word counts ──")
        for word, count in sorted(ws["word_count"].items(), key=lambda x: x[1], reverse=True):
            print(f"  {word:<14}: {count}")
        print("\n── Touch sequence (last 20) ──")
        print("  " + " → ".join(ws["touch_sequence"]))


    def _run_pyqtgraph_ui():
        """Entry point for the PyQtGraph real-time UI."""
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        palette = QPalette()
        palette.setColor(QPalette.Window,      QColor("#0d1117"))
        palette.setColor(QPalette.WindowText,  QColor("#e6edf3"))
        palette.setColor(QPalette.Base,        QColor("#161b22"))
        palette.setColor(QPalette.AlternateBase, QColor("#21262d"))
        palette.setColor(QPalette.Text,        QColor("#e6edf3"))
        palette.setColor(QPalette.Button,      QColor("#161b22"))
        palette.setColor(QPalette.ButtonText,  QColor("#e6edf3"))
        palette.setColor(QPalette.Highlight,   QColor("#58a6ff"))
        palette.setColor(QPalette.HighlightedText, QColor("#0d1117"))
        app.setPalette(palette)

        win = BrailleMainWindow()
        win.show()

        try:
            sys.exit(app.exec_())
        except SystemExit:
            pass
        finally:
            try:
                ser.close()
            except Exception:
                pass

# ═══════════════════════════ ENTRY POINT ══════════════════════════
if not _LEGACY_MODE:
    _run_pyqtgraph_ui()
