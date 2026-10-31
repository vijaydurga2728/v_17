from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import matplotlib

matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt

from v17.common.dtos import AccountState
from v17.obs.store import TradeStore


class ReportGenerator:
    def __init__(self, store: TradeStore) -> None:
        self._store = store

    def daily_markdown(self, date_str: str, account: AccountState) -> str:
        trades = self._store.trades_for_date(date_str)
        starting = account.starting_equity
        dd_pct = (
            (starting - account.equity) / starting * Decimal("100")
            if starting > 0
            else Decimal("0")
        )
        rows = "\n".join(
            f"| {t.ticket} | {t.symbol} | {t.side} | {t.entry} "
            f"| {t.close_price or '-'} | {t.pnl or '-'} | {t.reason or '-'} |"
            for t in trades
        )
        table = (
            "| Ticket | Symbol | Side | Entry | Close | PnL | Reason |\n"
            "|--------|--------|------|-------|-------|-----|--------|\n"
            + (rows if rows else "| — | — | — | — | — | — | — |")
        )
        return dedent(f"""\
            # Daily Report — {date_str}

            ## Account
            | Metric | Value |
            |--------|-------|
            | Equity | {account.equity} |
            | Balance | {account.balance} |
            | Daily P&L | {account.daily_realized_pnl} |
            | Total P&L | {account.total_realized_pnl} |
            | DD % | {dd_pct:.2f}% |

            ## Trades ({len(trades)})
            {table}
        """)

    def equity_png(self, output_path: Path) -> None:
        history = self._store.equity_history()
        dates = [r.date for r in history]
        equities = [float(r.equity) for r in history]
        fig, ax = plt.subplots(figsize=(10, 4))
        if dates:
            ax.plot(dates, equities, marker="o", linewidth=2)
            ax.set_title("Equity Curve")
            ax.set_xlabel("Date")
            ax.set_ylabel("Equity (USD)")
            plt.xticks(rotation=45)
            plt.tight_layout()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path)
        plt.close(fig)
