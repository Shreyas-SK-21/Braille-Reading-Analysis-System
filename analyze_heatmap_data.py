import pandas as pd
import glob
import numpy as np

r1 = pd.read_csv(glob.glob("Firmware/RUN1/*touch_events.csv")[0])
r2 = pd.read_csv(glob.glob("Firmware/RUN2/*touch_events.csv")[0])

# Load the word-to-grid-position mapping from the coverage heatmap CSVs
cov1 = pd.read_csv(glob.glob("Firmware/RUN1/*coverage_heatmap.csv")[0])
cov2 = pd.read_csv(glob.glob("Firmware/RUN2/*coverage_heatmap.csv")[0])
tot1 = pd.read_csv(glob.glob("Firmware/RUN1/*tot_heatmap.csv")[0])
tot2 = pd.read_csv(glob.glob("Firmware/RUN2/*tot_heatmap.csv")[0])
diff1 = pd.read_csv(glob.glob("Firmware/RUN1/*difficulty_heatmap.csv")[0])
diff2 = pd.read_csv(glob.glob("Firmware/RUN2/*difficulty_heatmap.csv")[0])

print("=== GRID WORD MAP (row, col -> word) ===")
for _, row in cov1.iterrows():
    if row["word"]:
        print(f"  R{int(row['row'])},C{int(row['col'])}: {row['word']}")

print()
print("=== TOT HEATMAP (mean ms, averaged across RUN1+RUN2) ===")
# Average the two runs
tot_avg = tot1.copy()
tot_avg["value"] = (tot1["value"] + tot2["value"]) / 2
for r in range(7):
    row_vals = []
    for c in range(7):
        cell = tot_avg[(tot_avg["row"]==r) & (tot_avg["col"]==c)]
        if len(cell) > 0:
            v = cell.iloc[0]["value"]
            w = cell.iloc[0]["word"]
            row_vals.append(f"R{r}C{c}={v:.0f}({w})")
    print("  " + "  ".join(row_vals))

print()
print("=== COVERAGE HEATMAP (touch count, sum across RUN1+RUN2) ===")
cov_sum = cov1.copy()
cov_sum["value"] = cov1["value"] + cov2["value"]
for r in range(7):
    row_vals = []
    for c in range(7):
        cell = cov_sum[(cov_sum["row"]==r) & (cov_sum["col"]==c)]
        if len(cell) > 0:
            v = cell.iloc[0]["value"]
            w = cell.iloc[0]["word"]
            row_vals.append(f"R{r}C{c}={v:.0f}({w})")
    print("  " + "  ".join(row_vals))

print()
print("=== DIFFICULTY HEATMAP (mean D, averaged across RUN1+RUN2) ===")
diff_avg = diff1.copy()
diff_avg["value"] = (diff1["value"].fillna(0) + diff2["value"].fillna(0)) / 2
for r in range(7):
    row_vals = []
    for c in range(7):
        cell = diff_avg[(diff_avg["row"]==r) & (diff_avg["col"]==c)]
        if len(cell) > 0:
            v = cell.iloc[0]["value"]
            w = cell.iloc[0]["word"]
            row_vals.append(f"R{r}C{c}={v:.3f}({w})")
    print("  " + "  ".join(row_vals))

print()
print("=== SENSITIVITY ANALYSIS ===")
# Default weights: W1=1.0, W2=0.5, W3=2.0, W4=1.5
# Speed-focused:   W1=0.5, W2=0.3, W3=3.0, W4=1.5
# Accuracy-focused: W1=2.0, W2=1.0, W3=1.0, W4=1.5
combined = pd.concat([r1, r2])
word_groups = combined.groupby("word")

presets = {
    "default":          (1.0, 0.5, 2.0, 1.5),
    "speed_focused":    (0.5, 0.3, 3.0, 1.5),
    "accuracy_focused": (2.0, 1.0, 1.0, 1.5),
}

results = {}
for preset, (W1, W2, W3, W4) in presets.items():
    scores = {}
    for word, grp in word_groups:
        rev = grp["reversals"].mean()
        zc  = grp["zero_crossings"].mean()
        vel = grp["vel_mean"].mean()
        vel_term = 1.0 / (vel + 1e-6) if vel > 0 else 0.0
        # cap vel_term at 5
        vel_term = min(vel_term, 5.0)
        wr = grp["is_regression"].mean()
        D = W1*rev + W2*zc + W3*vel_term + W4*wr
        scores[word] = round(D, 3)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    results[preset] = [w for w, _ in ranked[:7]]

# Print comparison table
all_words = sorted(set(w for lst in results.values() for w in lst))
print(f"{'Word':<14} {'Default':>10} {'Speed':>10} {'Accuracy':>12}")
print("-" * 50)
for word in [r[0] for r in sorted(combined.groupby("word")["difficulty"].mean().items(), key=lambda x: -x[1])]:
    dr = results["default"].index(word)+1 if word in results["default"] else "-"
    sp = results["speed_focused"].index(word)+1 if word in results["speed_focused"] else "-"
    ac = results["accuracy_focused"].index(word)+1 if word in results["accuracy_focused"] else "-"
    print(f"  {word:<12} {str(dr):>10} {str(sp):>10} {str(ac):>12}")
