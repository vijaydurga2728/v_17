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

# Custom JudasSwing with Dynamic Asian Range / Dynamic Risk Target
class DynamicJudasSwing(JudasSwing):
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
            if rr_target >= Decimal("1.5"):
                tp = target
            else:
                tp = entry + (risk * Decimal("2.0"))
        else:
            risk = sl - entry
            if risk <= 0:
                return None
            target = Decimal(str(asian_lo))
            rr_target = (entry - target) / risk
            if rr_target >= Decimal("1.5"):
                tp = target
            else:
                tp = entry - (risk * Decimal("2.0"))
                
        actual_rr = (tp - entry) / risk if side == Side.BUY else (entry - tp) / risk
        if actual_rr < Decimal("1.5"):
            return None
            
        return sig.model_copy(update={"tp": tp, "rr": actual_rr.quantize(Decimal("0.01"))})

# Custom SilverBullet with Dynamic Liquidity / 2.0 RR Target
class DynamicSilverBullet(SilverBullet):
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
            
        try:
            asian_hi, asian_lo = asian_high_low(bars_1m, now)
            has_asian = True
        except Exception:
            has_asian = False
            
        if side == Side.BUY:
            if has_asian and Decimal(str(asian_hi)) > entry:
                target = Decimal(str(asian_hi))
                if (target - entry) / risk >= Decimal("1.5"):
                    tp = target
                else:
                    tp = entry + (risk * Decimal("2.0"))
            else:
                tp = entry + (risk * Decimal("2.0"))
        else:
            if has_asian and Decimal(str(asian_lo)) < entry:
                target = Decimal(str(asian_lo))
                if (entry - target) / risk >= Decimal("1.5"):
                    tp = target
                else:
                    tp = entry - (risk * Decimal("2.0"))
            else:
                tp = entry - (risk * Decimal("2.0"))
                
        actual_rr = (tp - entry) / risk if side == Side.BUY else (entry - tp) / risk
        return sig.model_copy(update={"tp": tp, "rr": actual_rr.quantize(Decimal("0.01"))})

all_trades = []
for sym_str in ["GBPUSD", "USATECHIDXUSD"]:
    sym = Symbol(sym_str)
    df = read_1m(sym, START, END, s.parquet_root)
    pre = precompute(df, sym)
    setups = [DynamicJudasSwing(), DynamicSilverBullet()]
    loop = EventLoop(sym, setups, DefaultRiskEngine(), pre)
    trades, equity = loop.run(START, END, Decimal("10000"))
    pnls = [t.pnl for t in trades if t.pnl is not None]
    pf = profit_factor(pnls) if pnls else 0.0
    wins = sum(1 for p in pnls if p > 0)
    wr = (wins / len(pnls) * 100) if pnls else 0.0
    net = sum(pnls) if pnls else Decimal("0")
    print(f"[{sym_str} DYNAMIC TP] Trades: {len(trades)}, Wins: {wins}, WR: {wr:.1f}%, PF: {pf:.2f}, MaxDD: {loop.max_floating_dd_pct:.2f}%, Net: ${net:+.2f}")
    for t in trades:
        all_trades.append({
            "symbol": sym_str,
            "closed_at": t.closed_at,
            "pnl": float(t.pnl) if t.pnl is not None else 0.0,
        })

trades_sorted = sorted(all_trades, key=lambda x: x["closed_at"])
bal = 10000.0
peak = 10000.0
max_dd = 0.0
step = 1
step1_passed = False
step2_passed = False
step1_date = None
step2_date = None

for tr in trades_sorted:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > max_dd:
        max_dd = dd
    if step == 1 and bal >= 11000.0:
        step1_passed = True
        step1_date = str(tr["closed_at"])[:10]
        step = 2
        bal = 10000.0
        peak = 10000.0
    elif step == 2 and bal >= 10500.0:
        step2_passed = True
        step2_date = str(tr["closed_at"])[:10]
        step = 3

print("\n=== COMBINED DYNAMIC TP RESULTS ===")
print(f"Total Trades: {len(trades_sorted)}")
print(f"Total Net PnL: ${sum(t['pnl'] for t in trades_sorted):+.2f}")
print(f"Max DD: {max_dd:.2f}%")
print(f"Step 1 Passed: {step1_passed} ({step1_date})")
print(f"Step 2 Passed: {step2_passed} ({step2_date})")
