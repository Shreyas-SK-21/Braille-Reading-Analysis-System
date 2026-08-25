import pandas as pd
import glob
import numpy as np

r1 = pd.read_csv(glob.glob("Firmware/RUN1/*touch_events.csv")[0])
r2 = pd.read_csv(glob.glob("Firmware/RUN2/*touch_events.csv")[0])

print("=== WPM DATA ===")
for name, df in [("RUN1", r1), ("RUN2", r2)]:
    wpm = df["wpm"].dropna()
    print(f"{name}: min={wpm.min():.1f} max={wpm.max():.1f} mean={wpm.mean():.1f} final={wpm.iloc[-1]:.1f}")

print()
print("=== PER-WORD REGRESSIONS (combined) ===")
combined = pd.concat([r1, r2])
word_reg = combined.groupby("word")["is_regression"].sum().sort_values(ascending=False)
word_total = combined.groupby("word").size()
for w in word_reg.index:
    print(f"  {w}: {int(word_reg[w])} regressions / {word_total[w]} touches")

print()
print("=== PER-WORD TIME-ON-TASK (ms) ===")
tot = combined.groupby("word")["duration_ms"].mean().sort_values(ascending=False)
for w, v in tot.items():
    print(f"  {w}: {v:.1f}")

print()
print("=== PER-WORD DIFFICULTY ===")
diff = combined.groupby("word")["difficulty"].mean().sort_values(ascending=False)
for w, v in diff.items():
    print(f"  {w}: {v:.3f}")

print()
print("=== PATH EFFICIENCY ===")
for name, df in [("RUN1", r1), ("RUN2", r2)]:
    eff = df["path_efficiency"].dropna()
    gt08 = (eff >= 0.8).sum()
    mid = ((eff >= 0.5) & (eff < 0.8)).sum()
    low = (eff < 0.5).sum()
    print(f"{name}: proficient={gt08} ({gt08/len(eff)*100:.0f}%) developing={mid} ({mid/len(eff)*100:.0f}%) struggling={low} ({low/len(eff)*100:.0f}%)")

print()
print("=== REPEATABILITY: word D rank across runs ===")
r1d = r1.groupby("word")["difficulty"].mean()
r2d = r2.groupby("word")["difficulty"].mean()
common = sorted(set(r1d.index) & set(r2d.index))
r1rank = r1d.rank(ascending=False)
r2rank = r2d.rank(ascending=False)
for w in common:
    rk1 = r1rank.get(w, float("nan"))
    rk2 = r2rank.get(w, float("nan"))
    flag = "[CONSISTENT]" if abs(rk1-rk2) <= 3 else ""
    print(f"  {w}: R1_rank={rk1:.0f}  R2_rank={rk2:.0f}  {flag}")

print()
print("=== VELOCITY IQR ===")
for name, df in [("RUN1", r1), ("RUN2", r2)]:
    vel = df["vel_mean"].dropna()
    q1, q3 = np.percentile(vel, 25), np.percentile(vel, 75)
    print(f"{name}: mean={vel.mean():.3f}  IQR={q3-q1:.3f}  Q1={q1:.3f}  Q3={q3:.3f}")

print()
print("=== UNIQUE WORDS TOUCHED (skip rate) ===")
for name, df in [("RUN1", r1), ("RUN2", r2)]:
    print(f"{name}: {df['word'].nunique()} unique words, {len(df)} total events")
