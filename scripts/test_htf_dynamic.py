from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd

from v17.common.types import Symbol, Side
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor
from v17.setups.sessions import asian_high_low

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

# Check real-time intraday PDH / PDL sweep filter
class HTFJudasSwing(JudasSwing):
    def evaluate(self, snap, now, bars_1m):
        sig = super().evaluate(snap, now, bars_1m)
        if sig is None:
            return None
        try:
            asian_hi, asian_lo = asian_high_low(bars_1m, now)
        except Exception:
            return sig
        
        entry = sig.entry
        sl = sig.sl
        side = sig.side
        
        if side == Side.BUY:
            risk = entry - sl
            if risk <= 0:
                return None
            target = Decimal(str(asian_hi))
            rr_target = (target - entry) / risk
            tp = target if rr_target >= Decimal("1.5") else entry + (risk * Decimal("2.0"))
        else:
            risk = sl - entry
            if risk <= 0:
                return None
            target = Decimal(str(asian_lo))
            rr_target = (entry - target) / risk
            tp = target if rr_target >= Decimal("1.5") else entry - (risk * Decimal("2.0"))
                
        actual_rr = (tp - entry) / risk if side == Side.BUY else (entry - tp) / risk
        if actual_rr < Decimal("1.5"):
            return None
            
        return sig.model_copy(update={"tp": tp, "rr": actual_rr.quantize(Decimal("0.01"))})

class HTFSilverBullet(SilverBullet):
    def evaluate(self, snap, now, bars_1m):
        sig = super().evaluate(snap, now, bars_1m)
        if sig is None:
            return None
        entry = sig.entry
        sl = sig.sl
        side = sig.side
        risk = entry - sl if side == Side.BUY else sl - entry
        if risk <= 0:
            return None
            
        # Target 2.0x Risk
        tp = entry + (risk * Decimal("2.0")) if side == Side.BUY else entry - (risk * Decimal("2.0"))
        actual_rr = Decimal("2.00")
        return sig.model_copy(update={"tp": tp, "rr": actual_rr})

for sym_str in ["GBPUSD", "USATECHIDXUSD"]:
    sym = Symbol(sym_str)
    df = read_1m(sym, START, END, s.parquet_root)
    pre = precompute(df, sym)
    setups = [HTFJudasSwing(), HTFSilverBullet()]
    loop = EventLoop(sym, setups, DefaultRiskEngine(), pre)
    trades, equity = loop.run(START, END, Decimal("10000"))
    pnls = [t.pnl for t in trades if t.pnl is not None]
    pf = profit_factor(pnls) if pnls else 0.0
    wins = sum(1 for p in pnls if p > 0)
    wr = (wins / len(pnls) * 100) if pnls else 0.0
    net = sum(pnls) if pnls else Decimal("0")
    print(f"[{sym_str} HTF+DYNAMIC] Trades: {len(trades)}, Wins: {wins}, WR: {wr:.1f}%, PF: {pf:.2f}, MaxDD: {loop.max_floating_dd_pct:.2f}%, Net: ${net:+.2f}")
