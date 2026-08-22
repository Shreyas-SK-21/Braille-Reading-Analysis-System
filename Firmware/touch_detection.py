"""
touch_detection.py -- Touch detection FSM and finger state management.

This module acts as a documented namespace stub for the touch detection
components used in the braille_ui pipeline. Full implementations live in
braille_ui.py.

Classes:
    PeakLock              -- Per-finger peak-lock finite state machine
    TouchEvent            -- Immutable record of a completed touch event
    PerformanceMetrics    -- Rolling metric accumulator (WPM, duration, backtrack)
    FingerState           -- Per-finger state (position, start_time, assignment)

Functions:
    _assign_peaks_to_fingers -- Greedy proximity-based peak-to-finger assignment
"""

__all__ = [
    'PeakLock',
    'TouchEvent',
    'PerformanceMetrics',
    'FingerState',
    '_assign_peaks_to_fingers',
]
