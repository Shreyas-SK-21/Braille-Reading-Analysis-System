import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import glob
import numpy as np

# Load RUN1 CSVs
cov = pd.read_csv(glob.glob("Firmware/RUN1/*coverage_heatmap.csv")[0])
tot = pd.read_csv(glob.glob("Firmware/RUN1/*tot_heatmap.csv")[0])
diff = pd.read_csv(glob.glob("Firmware/RUN1/*difficulty_heatmap.csv")[0])

def make_heatmap(df, val_col, cmap, fmt, cbar_label, out_name):
    # Pivot to 7x7
    grid_val = np.zeros((7, 7))
    grid_annot = np.full((7, 7), "", dtype=object)
    
    for _, r in df.iterrows():
        row, col = int(r['row']), int(r['col'])
        if pd.isna(r['word']) or not str(r['word']).strip():
            continue
        val = r[val_col]
        word = r['word']
        grid_val[row, col] = val
        if fmt == ".0f":
            annot_str = f"{word}\n{val:.0f}"
        elif fmt == ".2f":
            annot_str = f"{word}\n{val:.2f}"
        else:
            annot_str = f"{word}\n{val}"
        grid_annot[row, col] = annot_str
        
    plt.figure(figsize=(7, 6))
    sns.set_theme(style="white")
    ax = sns.heatmap(grid_val, annot=grid_annot, fmt="", cmap=cmap,
                     cbar_kws={'label': cbar_label}, 
                     linewidths=1, linecolor='white')
    ax.set_xticks([])
    ax.set_yticks([])
    plt.tight_layout()
    plt.savefig("Manuscript_Draft/" + out_name, format="pdf", bbox_inches='tight')
    plt.close()

make_heatmap(tot, "value", "Blues", ".0f", "Dwell Time (ms)", "tot_heatmap.pdf")
make_heatmap(diff, "value", "YlOrRd", ".2f", "Composite Difficulty (D)", "diff_heatmap.pdf")
make_heatmap(cov, "value", "Greens", ".0f", "Touch Count", "skip_heatmap.pdf")

print("Generated heatmaps.")
