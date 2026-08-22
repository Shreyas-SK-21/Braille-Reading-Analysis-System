"""
metrics.py -- Braille reading metric tracker classes.

This module acts as a documented namespace for the metric tracker classes
used in the braille_ui pipeline. The full implementations live in braille_ui.py.
This file is the entry point for a future full modular refactor where each
class will be moved here as a self-contained, independently testable unit.

Classes (defined in braille_ui.py, re-exported here for clarity):
    VelocityTracker         -- rolling inter-touch velocity with EWIQR smoothing
    WordStatsTracker        -- per-word touch count, regression detection (30s window)
    WordGroupAccumulator    -- groups touches into logical word events
    CellDifficultyTracker   -- aggregates difficulty signals per grid cell
    WelfordPerWord          -- per-word online mean/variance (Welford algorithm)
    EWIQRPerWordTracker     -- exponentially weighted IQR difficulty tracker
    SlidingWindowWPM        -- rolling-window words-per-minute counter
    AdaptiveDeadTime        -- two-layer EMA dead-time filter for ghost suppression
"""

__all__ = [
    'VelocityTracker',
    'WordStatsTracker',
    'WordGroupAccumulator',
    'CellDifficultyTracker',
    'WelfordPerWord',
    'EWIQRPerWordTracker',
    'SlidingWindowWPM',
    'AdaptiveDeadTime',
]
