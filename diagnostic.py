import pandas as pd
from pathlib import Path
from v17.data.load import load_1m_bars
from v17.backtest.precompute import precompute_all, snapshot_at
from v17.common.types import TF
import warnings
warnings.filterwarnings("ignore")

symbol = "EURUSD"
start = pd.Timestamp("2024-06-01")
end = pd.Timestamp("2024-06-30")

try:
    # Load bars
    bars_1m = load_1m_bars(symbol, start, end)
    print(f"Loaded {len(bars_1m)} 1m bars")

    # Precompute
    pre = precompute_all(symbol, bars_1m, start, end)
    print(f"Precomputed. Choches: {len(pre.choches_1m)}, Swings 1D: {len(pre.swings_1d)}, Swings 4H: {len(pre.swings_4h)}")

    # Snapshot mid-month
    mid = pd.Timestamp("2024-06-15")
    snap = snapshot_at(pre, mid)
    print(f"\nSnapshot at {mid}:")
    print(f"  Bias: {snap.bias}")
    print(f"  Zones: {len(snap.zones)}")
    print(f"  Swings: {len(snap.swings)}")
    print(f"  Sweeps: {len(snap.sweeps)}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
