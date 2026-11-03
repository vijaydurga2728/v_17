import json, pandas as pd
from pathlib import Path

runs = sorted(Path('runs').iterdir(), key=lambda p: p.stat().st_mtime)
print('All runs (oldest -> newest):')
for r in runs:
    try:
        m = json.load(open(r / 'metrics.json'))
        t = pd.read_parquet(r / 'trades.parquet')
        sym = t.symbol.iloc[0] if len(t) > 0 else '?'
        wins = (t.reason == 'tp').sum() if 'reason' in t.columns else '?'
        trades = m['trades']
        wr = m['winrate'] * 100
        pf = m['pf']
        dd = m['max_dd_pct']
        print(f"  {r.name}  sym={sym}  trades={trades}  wins={wins}  wr={wr:.1f}%  pf={pf:.3f}  dd={dd:.2f}%")
    except Exception as e:
        print(f"  {r.name}  ERROR: {e}")
