from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd
from v17.common.types import Symbol
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor
from v17.backtest import cost

s = get_settings()
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2017, 12, 31, tzinfo=UTC)
sym = Symbol("EURGBP")

df = read_1m(sym, START, END, s.parquet_root)
pre = precompute(df, sym)

print(f"Loaded {len(df):,} bars for {sym}")

tp_candidates = [10, 12, 13, 14, 15, 16, 18, 20, 22]

results = []
for tp_val in tp_candidates:
    cost.TP_FALLBACK_PIPS_BY_SYMBOL["EURGBP"] = Decimal(str(tp_val))
    
    # Test 1: Both setups
    loop_both = EventLoop(sym, [JudasSwing(), SilverBullet()], DefaultRiskEngine(), pre)
    trades_b, _ = loop_both.run(START, END, Decimal("10000"))
    pnls_b = [t.pnl for t in trades_b if t.pnl is not None]
    pf_b = profit_factor(pnls_b) if pnls_b else 0.0
    wins_b = sum(1 for p in pnls_b if p > 0)
    wr_b = (wins_b / len(pnls_b) * 100) if pnls_b else 0.0
    dd_b = loop_both.max_floating_dd_pct
    net_b = sum(pnls_b) if pnls_b else Decimal("0")
    
    # Test 2: Judas Swing only (London Open)
    loop_j = EventLoop(sym, [JudasSwing()], DefaultRiskEngine(), pre)
    trades_j, _ = loop_j.run(START, END, Decimal("10000"))
    pnls_j = [t.pnl for t in trades_j if t.pnl is not None]
    pf_j = profit_factor(pnls_j) if pnls_j else 0.0
    wins_j = sum(1 for p in pnls_j if p > 0)
    wr_j = (wins_j / len(pnls_j) * 100) if pnls_j else 0.0
    dd_j = loop_j.max_floating_dd_pct
    net_j = sum(pnls_j) if pnls_j else Decimal("0")

    # Test 3: Silver Bullet only
    loop_sb = EventLoop(sym, [SilverBullet()], DefaultRiskEngine(), pre)
    trades_sb, _ = loop_sb.run(START, END, Decimal("10000"))
    pnls_sb = [t.pnl for t in trades_sb if t.pnl is not None]
    pf_sb = profit_factor(pnls_sb) if pnls_sb else 0.0
    wins_sb = sum(1 for p in pnls_sb if p > 0)
    wr_sb = (wins_sb / len(pnls_sb) * 100) if pnls_sb else 0.0
    dd_sb = loop_sb.max_floating_dd_pct
    net_sb = sum(pnls_sb) if pnls_sb else Decimal("0")

    results.append({
        "tp": tp_val,
        "both_n": len(trades_b), "both_wr": wr_b, "both_pf": pf_b, "both_dd": dd_b, "both_net": float(net_b),
        "j_n": len(trades_j), "j_wr": wr_j, "j_pf": pf_j, "j_dd": dd_j, "j_net": float(net_j),
        "sb_n": len(trades_sb), "sb_wr": wr_sb, "sb_pf": pf_sb, "sb_dd": dd_sb, "sb_net": float(net_sb),
    })

res_df = pd.DataFrame(results)
print(res_df.to_string())
