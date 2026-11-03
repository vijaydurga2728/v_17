import pandas as pd

t = pd.read_parquet('runs/fc5e94ebb80034d3/trades.parquet')
print(f'=== NAS100 15 TRADES DETAILED AUDIT ({len(t)} trades) ===')
for i, r in t.iterrows():
    sl_dist = float(abs(r['entry'] - r['sl']))
    tp_dist = float(abs(r['tp'] - r['entry']))
    rr = tp_dist / sl_dist if sl_dist > 0 else 0
    duration = (r['closed_at'] - r['opened_at']).total_seconds() / 60
    pnl = float(r['pnl'])
    print(f"Trade #{i+1:2d} | {r['side']:4s} | lots: {float(r['size_lots']):5.2f} | Entry: {float(r['entry']):8.2f} | SL: {float(r['sl']):8.2f} ({sl_dist:5.2f} pts) | TP: {float(r['tp']):8.2f} ({tp_dist:5.2f} pts) | RR: {rr:4.1f} | Result: {r['reason']:2s} | PnL: ${pnl:>7.2f} | Dur: {duration:5.0f}m | Open: {r['opened_at']}")
