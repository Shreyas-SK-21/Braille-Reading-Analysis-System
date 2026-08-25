import pandas as pd
import glob

print('=== COVERAGE (SKIP RATE) ===')
for run in ['RUN1', 'RUN2']:
    csv = glob.glob(f'Firmware/{run}/*coverage_heatmap.csv')[0]
    df = pd.read_csv(csv)
    skipped = len(df[df['value'] == 0])
    total = len(df)
    print(f'{run}: {skipped} skipped cells out of {total} ({(skipped/total)*100:.1f}%)')

print('\n=== TIME ON TASK (HEATMAP) ===')
for run in ['RUN1', 'RUN2']:
    csv = glob.glob(f'Firmware/{run}/*tot_heatmap.csv')[0]
    df = pd.read_csv(csv)
    max_tot = df['value'].max()
    print(f'{run}: Max ToT cell is {df.loc[df["value"].idxmax()]["word"]} at {max_tot:.1f} ms')
