"""
data_logger.py -- Session data logging and figure export.

This module acts as a documented namespace stub for the DataLogger class
used in the braille_ui pipeline. The full implementation lives in braille_ui.py.

DataLogger responsibilities:
    - Opens session_data/{timestamp}_touch_events.csv at startup
    - Opens session_data/{timestamp}_metrics_snapshots.csv at startup
    - Exports session_data/{timestamp}_tot_heatmap.csv at shutdown
    - Exports session_data/{timestamp}_coverage_heatmap.csv at shutdown
    - Exports session_data/{timestamp}_difficulty_heatmap.csv at shutdown
    - Generates 5 PNG summary figures on session close
"""

__all__ = ['DataLogger']
