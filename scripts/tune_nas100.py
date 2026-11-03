from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd
from v17.common.types import TF, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing

SYMBOL = Symbol("USATECHIDXUSD")
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2017, 12, 31, tzinfo=UTC)

s = get_settings()
p = ParquetBarProvider(s.parquet_root)
bars_list = [b.model_dump() for b in p.bars(SYMBOL, TF.M1, START, END)]
df = pd.DataFrame(bars_list)
for col in ("open", "high", "low", "close", "spread_pips"):
    df[col] = df[col].astype(float)
df["ts"] = pd.to_datetime(df["ts"], utc=True)
df["volume"] = df["volume"].astype("int64")

print(f"Loaded {len(df):,} bars for {SYMBOL} 2015-2017")
pre = precompute(df, SYMBOL)

# Test various TP settings in cost.py or setups
from v17.backtest import cost

print("\n--- Testing TP levels for NAS100 (2015-2017) ---")
for tp in [20, 25, 30, 40, 50, 60, 80]:
    cost.TP_FALLBACK_PIPS_BY_SYMBOL["USATECHIDXUSD"] = Decimal(str(tp))
    loop = EventLoop(
        SYMBOL,
        [SilverBullet(), JudasSwing()],
        DefaultRiskEngine(),
        pre,
    )
    trades, equity_curve = loop.run(START, END, Decimal("10000"))
    if not trades:
        print(f"TP {tp:2d} pts: 0 trades")
        continue
    
    wins = sum(1 for t in trades if t.pnl and t.pnl > 0)
    total = len(trades)
    wr = wins / total * 100
    gross_win = sum(t.pnl for t in trades if t.pnl and t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl and t.pnl < 0))
    pf = float(gross_win / gross_loss) if gross_loss > 0 else 999.0
    net_pnl = sum(t.pnl for t in trades if t.pnl is not None)
    
    # Calculate max drawdown
    max_dd = loop.max_floating_dd_pct
    print(f"TP {tp:2d} pts | Trades: {total:2d} | WR: {wr:4.1f}% ({wins}W/{total-wins}L) | PF: {pf:5.2f} | MaxDD: {max_dd:5.2f}% | NetPnL: ${float(net_pnl):>+8.2f}")
