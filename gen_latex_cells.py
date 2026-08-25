import pandas as pd
import glob
import numpy as np

r1 = pd.read_csv(glob.glob("Firmware/RUN1/*touch_events.csv")[0])
r2 = pd.read_csv(glob.glob("Firmware/RUN2/*touch_events.csv")[0])
tot1 = pd.read_csv(glob.glob("Firmware/RUN1/*tot_heatmap.csv")[0])
tot2 = pd.read_csv(glob.glob("Firmware/RUN2/*tot_heatmap.csv")[0])
cov1 = pd.read_csv(glob.glob("Firmware/RUN1/*coverage_heatmap.csv")[0])
cov2 = pd.read_csv(glob.glob("Firmware/RUN2/*coverage_heatmap.csv")[0])
diff1 = pd.read_csv(glob.glob("Firmware/RUN1/*difficulty_heatmap.csv")[0])
diff2 = pd.read_csv(glob.glob("Firmware/RUN2/*difficulty_heatmap.csv")[0])

tot_avg = tot1.copy(); tot_avg["value"] = (tot1["value"] + tot2["value"]) / 2
cov_sum = cov1.copy(); cov_sum["value"] = cov1["value"] + cov2["value"]
diff_avg = diff1.copy(); diff_avg["value"] = (diff1["value"].fillna(0) + diff2["value"].fillna(0)) / 2

def get(df, r, c, col="value"):
    cell = df[(df["row"]==r) & (df["col"]==c)]
    return cell.iloc[0][col] if len(cell) > 0 else 0.0

# ---------- TOT heatmap ----------
# Scale: max is ~4127ms -> blue!100; 0 -> blue!10
max_tot = max(get(tot_avg,r,c) for r in range(7) for c in range(7))

def tot_cell(r, c):
    v = get(tot_avg, r, c)
    if v == 0: return r"{\cellcolor{gray!15}\,---\,}"
    pct = max(10, int(v / max_tot * 90))
    return r"\cellcolor{blue!" + str(pct) + r"}" + str(int(v))

print("=== TOT HEATMAP ROWS ===")
for r in range(7):
    cells = " & ".join(tot_cell(r, c) for c in range(7))
    print(f"    \\textbf{{R{r}}} &\n      {cells} \\\\")

# ---------- DIFFICULTY heatmap ----------
# thresholds: D>=0.9 -> red!60, D>=0.7 -> yellow!60, else white
def diff_cell(r, c):
    v = get(diff_avg, r, c)
    if v == 0.0: return r"\cellcolor{white}---"
    if v >= 0.90: return r"\cellcolor{red!55}" + f"{v:.2f}"
    if v >= 0.70: return r"\cellcolor{yellow!60}" + f"{v:.2f}"
    if v >= 0.50: return r"\cellcolor{yellow!30}" + f"{v:.2f}"
    return r"\cellcolor{white}" + f"{v:.2f}"

print()
print("=== DIFFICULTY HEATMAP ROWS ===")
for r in range(7):
    cells = " & ".join(diff_cell(r, c) for c in range(7))
    print(f"    \\textbf{{R{r}}} &\n      {cells} \\\\")

# ---------- COVERAGE heatmap ----------
max_cov = max(get(cov_sum,r,c) for r in range(7) for c in range(7))

def cov_cell(r, c):
    v = int(get(cov_sum, r, c))
    if v == 0: return r"\cellcolor{gray!20}0"
    if v <= 4: return r"\cellcolor{green!30}" + str(v)
    if v <= 7: return r"\cellcolor{green!55}" + str(v)
    return r"\cellcolor{orange!55}" + str(v)  # heavy revisit

print()
print("=== COVERAGE HEATMAP ROWS ===")
for r in range(7):
    cells = " & ".join(cov_cell(r, c) for c in range(7))
    print(f"    \\textbf{{R{r}}} &\n      {cells} \\\\")

# ---------- Sensitivity analysis ----------
presets = {
    "Default":   (1.0, 0.5, 2.0, 1.5),
    "Speed":     (0.5, 0.3, 3.0, 1.5),
    "Accuracy":  (2.0, 1.0, 1.0, 1.5),
}
combined = pd.concat([r1, r2])

def score_words(W1, W2, W3, W4):
    scores = {}
    for word, grp in combined.groupby("word"):
        rev = grp["reversals"].mean()
        zc  = grp["zero_crossings"].mean()
        vel = grp["vel_mean"].mean()
        vt  = min(1.0/(vel+1e-6), 5.0) if vel > 0 else 0
        wr  = grp["is_regression"].mean()
        scores[word] = W1*rev + W2*zc + W3*vt + W4*wr
    return sorted(scores.items(), key=lambda x: -x[1])

print()
print("=== SENSITIVITY TABLE ===")
results = {p: score_words(*w) for p, w in presets.items()}
words_by_default = [w for w,_ in results["Default"]]
print(f"{'Word':<14} {'Default':>8} {'Speed':>8} {'Accuracy':>10}")
print("-"*44)
for w in words_by_default:
    def rank(lst, word):
        for i,(ww,_) in enumerate(lst):
            if ww==word: return i+1
        return "-"
    dr = rank(results["Default"], w)
    sp = rank(results["Speed"], w)
    ac = rank(results["Accuracy"], w)
    d_score = dict(results["Default"])[w]
    s_score = dict(results["Speed"])[w]
    a_score = dict(results["Accuracy"])[w]
    print(f"  {w:<12} #{dr:>2} ({d_score:.2f})  #{sp:>2} ({s_score:.2f})  #{ac:>2} ({a_score:.2f})")
