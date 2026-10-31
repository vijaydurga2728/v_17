from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import String, select
from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from v17.common.dtos import AccountState, Trade
from v17.common.types import Ticket


class _Base(DeclarativeBase):
    pass


class TradeRow(_Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket: Mapped[int] = mapped_column(unique=True)
    signal_id: Mapped[str]
    symbol: Mapped[str]
    side: Mapped[str]
    size_lots: Mapped[str]
    entry: Mapped[str]
    sl: Mapped[str]
    tp: Mapped[str]
    opened_at: Mapped[str]
    closed_at: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    close_price: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    pnl: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    reason: Mapped[str] = mapped_column(default="")


class EquityDailyRow(_Base):
    __tablename__ = "equity_daily"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(unique=True)
    equity: Mapped[str]
    balance: Mapped[str]
    daily_pnl: Mapped[str]
    total_pnl: Mapped[str]
    dd_pct: Mapped[str]
    open_positions: Mapped[int]


class SignalRow(_Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(unique=True)
    symbol: Mapped[str]
    setup: Mapped[str]
    side: Mapped[str]
    at: Mapped[str]
    entry: Mapped[str]
    sl: Mapped[str]
    tp: Mapped[str]
    rr: Mapped[str]
    fired: Mapped[bool]
    reject_reason: Mapped[str] = mapped_column(default="")


class ErrorRow(_Base):
    __tablename__ = "errors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    level: Mapped[str]
    message: Mapped[str]
    ctx: Mapped[str] = mapped_column(default="{}")
    at: Mapped[str]


def create_engine_for_path(db_path: Path) -> object:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return _sa_create_engine(f"sqlite:///{db_path}", echo=False)


class TradeStore:
    def __init__(self, engine: object) -> None:
        self._engine = engine

    def create_tables(self) -> None:
        _Base.metadata.create_all(self._engine)  # type: ignore[arg-type]

    def record_trade(self, trade: Trade) -> None:
        with Session(self._engine) as session:  # type: ignore[arg-type]
            row = session.scalar(select(TradeRow).where(TradeRow.ticket == int(trade.ticket)))
            if row is not None:
                return
            session.add(TradeRow(
                ticket=int(trade.ticket),
                signal_id=str(trade.signal_id),
                symbol=str(trade.symbol),
                side=trade.side.value,
                size_lots=str(trade.size_lots),
                entry=str(trade.entry),
                sl=str(trade.sl),
                tp=str(trade.tp),
                opened_at=trade.opened_at.isoformat(),
            ))
            session.commit()

    def update_close(
        self,
        ticket: Ticket,
        closed_at: datetime,
        close_price: Decimal | None,
        pnl: Decimal | None,
        reason: str,
    ) -> None:
        with Session(self._engine) as session:  # type: ignore[arg-type]
            row = session.scalar(select(TradeRow).where(TradeRow.ticket == int(ticket)))
            if row is None:
                return
            row.closed_at = closed_at.isoformat()
            row.close_price = str(close_price) if close_price is not None else None
            row.pnl = str(pnl) if pnl is not None else None
            row.reason = reason
            session.commit()

    def record_equity(self, date: str, account: AccountState) -> None:
        starting = account.starting_equity
        dd_pct = (
            (starting - account.equity) / starting * Decimal("100")
            if starting > 0
            else Decimal("0")
        )
        with Session(self._engine) as session:  # type: ignore[arg-type]
            row = session.scalar(select(EquityDailyRow).where(EquityDailyRow.date == date))
            if row is None:
                row = EquityDailyRow(date=date)
                session.add(row)
            row.equity = str(account.equity)
            row.balance = str(account.balance)
            row.daily_pnl = str(account.daily_realized_pnl)
            row.total_pnl = str(account.total_realized_pnl)
            row.dd_pct = str(dd_pct)
            row.open_positions = account.open_positions
            session.commit()

    def record_error(self, level: str, message: str, ctx: dict[str, object]) -> None:
        with Session(self._engine) as session:  # type: ignore[arg-type]
            session.add(ErrorRow(
                level=level,
                message=message,
                ctx=json.dumps(ctx),
                at=datetime.now(UTC).isoformat(),
            ))
            session.commit()

    def trades_for_date(self, date: str) -> list[TradeRow]:
        with Session(self._engine) as session:  # type: ignore[arg-type]
            rows = session.scalars(
                select(TradeRow).where(TradeRow.opened_at.like(f"{date}%"))
            ).all()
            return list(rows)

    def equity_history(self) -> list[EquityDailyRow]:
        with Session(self._engine) as session:  # type: ignore[arg-type]
            return list(session.scalars(select(EquityDailyRow).order_by(EquityDailyRow.date)).all())

    def open_trades(self) -> list[TradeRow]:
        with Session(self._engine) as session:  # type: ignore[arg-type]
            return list(session.scalars(
                select(TradeRow).where(TradeRow.closed_at.is_(None))
            ).all())

    def load_account(self, starting_equity: Decimal) -> AccountState:
        open_rows = self.open_trades()
        all_history = self.equity_history()
        if all_history:
            last = all_history[-1]
            equity = Decimal(last.equity)
            balance = Decimal(last.balance)
            daily_pnl = Decimal(last.daily_pnl)
            total_pnl = Decimal(last.total_pnl)
        else:
            equity = starting_equity
            balance = starting_equity
            daily_pnl = Decimal("0")
            total_pnl = Decimal("0")
        return AccountState(
            equity=equity,
            balance=balance,
            starting_equity=starting_equity,
            peak_equity=equity,
            daily_realized_pnl=daily_pnl,
            total_realized_pnl=total_pnl,
            best_day_pnl=Decimal("0"),
            open_positions=len(open_rows),
            trading_days_count=len(all_history),
            is_locked_today=False,
            kill_active=False,
        )
