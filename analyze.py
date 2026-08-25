import pandas as pd
import glob
import os

runs = {
    'RUN1': glob.glob('Firmware/RUN1/*touch_events.csv')[0],
    'RUN2': glob.glob('Firmware/RUN2/*touch_events.csv')[0],
    'RUN3 (Sweep)': glob.glob('Firmware/session_data/*touch_events.csv')[0]
}

for run_name, file_path in runs.items():
    df = pd.read_csv(file_path)
    print(f'=== {run_name} ===')
    print(f'Total Touches: {len(df)}')
    
    col_counts = df['col'].value_counts()
    regressions = df[df['is_regression'] == True]['col'].value_counts()
    
    print('Error/Regression rate per column:')
    for col in range(7):
        total = col_counts.get(col, 0)
        regs = regressions.get(col, 0)
        rate = (regs / total * 100) if total > 0 else 0
        print(f'  C{col}: {rate:.1f}% ({regs}/{total})')
    
    print(f'Average WPM: {df["wpm"].mean():.1f}')
    print(f'Average ToT (duration): {df["duration_ms"].mean():.1f} ms')
    if len(df) > 0:
        print(f'Average Path Efficiency: {df["path_efficiency"].mean():.3f}')
    
    # Let's get the top 5 difficult words based on difficulty score
    print('Top 5 Difficult Words (by mean difficulty score):')
    diff = df.groupby('word')['difficulty'].mean().sort_values(ascending=False).head(5)
    for word, score in diff.items():
        print(f'  {word}: {score:.3f}')
        
    print('-'*30)
