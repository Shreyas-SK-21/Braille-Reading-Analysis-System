"""
session_analysis.py
===================
Reads session_data/ CSVs produced by DataLogger and computes
paper statistics needed for the IEEE BHI 2026 revision:

  L4: Spearman rank correlation of per-word difficulty across weight presets
  L5: Coefficient of variation (CV) for each primary metric across sessions

USAGE
-----
  1. Run braille_ui.py for 5+ sessions (optionally use --weight-preset for L4).
  2. Make sure session_data/ folder is in the same directory as this script.
  3. Run:  python session_analysis.py

OUTPUT
------
  Prints CV table and Spearman values ready to paste into the paper.
"""

import os
import glob
import csv
from collections import defaultdict
import numpy as np

SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_data")


def load_snapshots(pattern="*_metrics_snapshots.csv"):
    """Load all snapshot CSVs, grouped by session (timestamp prefix)."""
    files = glob.glob(os.path.join(SESSION_DIR, pattern))
    sessions = {}
    for f in sorted(files):
        key = os.path.basename(f)[:15]  # YYYYMMDD_HHMMSS
        rows = []
        with open(f, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append({k: float(v) for k, v in row.items()
                             if k != "timestamp"})
        if rows:
            sessions[key] = rows
    return sessions


def load_touches(pattern="*_touch_events.csv"):
    """Load all touch event CSVs, grouped by session."""
    files = glob.glob(os.path.join(SESSION_DIR, pattern))
    sessions = {}
    for f in sorted(files):
        key = os.path.basename(f)[:15]
        rows = []
        with open(f, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(row)
        if rows:
            sessions[key] = rows
    return sessions


# ── L5: Coefficient of Variation ──────────────────────────────────────────────

def compute_cv_table(snapshot_sessions):
    """For each metric, compute CV across all sessions."""
    metric_keys = ["wpm", "consistency", "regression_rate",
                   "skip_rate", "path_efficiency", "composite_difficulty"]
    metric_labels = {
        "wpm":                  "Sliding-window WPM",
        "consistency":          "Velocity consistency",
        "regression_rate":      "Regression rate",
        "skip_rate":            "Skip rate (%)",
        "path_efficiency":      "Path efficiency eta",
        "composite_difficulty": "Composite difficulty score",
    }

    session_means = defaultdict(list)
    for session_key, rows in snapshot_sessions.items():
        for k in metric_keys:
            vals = [r[k] for r in rows if k in r]
            if vals:
                session_means[k].append(np.mean(vals))

    print("\n== L5: Metric Repeatability (CV across sessions) ==")
    print(f"{'Metric':<40} {'N':>5} {'Mean':>10} {'Std':>10} {'CV (%)':>10}")
    print("-" * 78)
    for k in metric_keys:
        vals = np.array(session_means[k])
        if len(vals) < 2:
            print(f"{metric_labels[k]:<40} {'<2':>5}")
            continue
        mean_v = vals.mean()
        std_v  = vals.std(ddof=1)
        cv     = (std_v / mean_v * 100) if mean_v != 0 else float("nan")
        print(f"{metric_labels[k]:<40} {len(vals):>5} {mean_v:>10.3f} "
              f"{std_v:>10.3f} {cv:>10.1f}")


# ── L4: Spearman rank correlation between weight presets ──────────────────────

def compute_difficulty_per_word(touch_rows, w1=1.0, w2=0.5, w3=2.0):
    """Re-compute composite difficulty per word with given weights."""
    word_scores = defaultdict(list)
    for row in touch_rows:
        word = row.get("word", "")
        if not word:
            continue
        try:
            rev = float(row["reversals"])
            zc  = float(row["zero_crossings"])
            vel = float(row["vel_mean"])
            inv_vel = 1.0 / vel if vel > 1e-6 else 0.0
            d = w1 * rev + w2 * zc + w3 * inv_vel
            word_scores[word].append(d)
        except (KeyError, ValueError):
            continue
    return {w: np.mean(v) for w, v in word_scores.items() if v}


def compute_spearman(x_dict, y_dict):
    from scipy.stats import spearmanr
    words = sorted(set(x_dict) & set(y_dict))
    if len(words) < 3:
        return float("nan"), float("nan"), len(words)
    x = [x_dict[w] for w in words]
    y = [y_dict[w] for w in words]
    rho, p = spearmanr(x, y)
    return rho, p, len(words)


def compute_weight_sensitivity(touch_sessions):
    presets = {
        "default":          (1.0, 0.5, 2.0),
        "speed_focused":    (0.5, 0.3, 3.0),
        "accuracy_focused": (2.0, 1.0, 1.0),
    }
    all_rhos_speed = []
    all_rhos_accu  = []
    for session_key, rows in touch_sessions.items():
        scores = {name: compute_difficulty_per_word(rows, *w)
                  for name, w in presets.items()}
        rho_s, p_s, n_s = compute_spearman(scores["default"], scores["speed_focused"])
        rho_a, p_a, n_a = compute_spearman(scores["default"], scores["accuracy_focused"])
        all_rhos_speed.append(rho_s)
        all_rhos_accu.append(rho_a)

    print("\n== L4: Weight Sensitivity (Spearman rho) ==")
    if all_rhos_speed:
        print(f"  Default vs. speed_focused:    "
              f"rho = {np.nanmean(all_rhos_speed):.3f}  "
              f"({len(all_rhos_speed)} sessions)")
        print(f"  Default vs. accuracy_focused: "
              f"rho = {np.nanmean(all_rhos_accu):.3f}  "
              f"({len(all_rhos_accu)} sessions)")
    else:
        print("  No sessions found.")


if __name__ == "__main__":
    snap_sessions  = load_snapshots()
    touch_sessions = load_touches()

    if not snap_sessions and not touch_sessions:
        print(f"[ERROR] No CSV files found in: {SESSION_DIR}")
        print("  Run braille_ui.py for at least 2 sessions first.")
    else:
        print(f"[INFO] {len(snap_sessions)} snapshot CSVs, "
              f"{len(touch_sessions)} touch event CSVs in {SESSION_DIR}")
        if snap_sessions:
            compute_cv_table(snap_sessions)
        if touch_sessions:
            try:
                compute_weight_sensitivity(touch_sessions)
            except ImportError:
                print("\n[L4] scipy not installed -> run: pip install scipy")

    print("\n[DONE] Copy values above into paper_revision_text.md")
