from __future__ import annotations

from dataclasses import dataclass

import typer

from v17.config import Settings


@dataclass
class _LiveComponents:
    runner: object  # LiveRunner — avoid circular import at module level
    store: object   # TradeStore
    bot: object | None  # TelegramCommandBot | None


def _build_components(s: Settings, dry_run: bool) -> _LiveComponents:
    from v17.common.clock import SystemClock
    from v17.common.logging import configure
    from v17.common.types import Symbol
    from v17.data.calendar.providers import FFCalendarProvider
    from v17.live.alerter import Alerter, NullAlerter
    from v17.live.runner import LiveRunner
    from v17.obs.store import TradeStore, create_engine_for_path
    from v17.risk.engine import DefaultRiskEngine
    from v17.setups.judas_swing import JudasSwing
    from v17.setups.silver_bullet import SilverBullet
    from v17.structure.engine import DefaultStructureEngine

    configure(level=s.log_level, log_dir=s.logs_root)

    engine = create_engine_for_path(s.db)
    store = TradeStore(engine)
    store.create_tables()
    account = store.load_account(starting_equity=s.starting_equity)

    alerter: Alerter
    if s.telegram_token and s.telegram_chat_id:
        from v17.obs.alerter import TelegramAlerter
        alerter = TelegramAlerter(token=s.telegram_token, chat_id=s.telegram_chat_id)
    else:
        alerter = NullAlerter()

    from v17.mt5.protocol import TradeGateway
    gateway: TradeGateway
    if dry_run:
        from v17.mt5.fake import FakeMT5
        gw = FakeMT5()
        gw.connect()
        gateway = gw
    else:
        from v17.mt5.gateway import MT5Gateway
        gw2 = MT5Gateway(login=s.mt5_login, password=s.mt5_password, server=s.mt5_server)
        gw2.connect()
        gateway = gw2

    clock = SystemClock()
    calendar = FFCalendarProvider(s.calendar_root)
    symbols = [Symbol("EURUSD"), Symbol("GBPUSD")]

    runner = LiveRunner(
        gateway=gateway,
        structure_engine=DefaultStructureEngine(symbols[0]),
        setup_engines=[SilverBullet(), JudasSwing()],
        risk_engine=DefaultRiskEngine(),
        calendar=calendar,
        alerter=alerter,
        state_root=s.state_root,
        symbols=symbols,
        clock=clock,
        initial_account=account,
    )

    bot = None
    if s.telegram_token and s.telegram_chat_id:
        from v17.obs.bot import TelegramCommandBot
        from v17.obs.report import ReportGenerator
        report_gen = ReportGenerator(store)
        bot = TelegramCommandBot(
            token=s.telegram_token,
            chat_id=s.telegram_chat_id,
            state_root=s.state_root,
            report_generator=report_gen,
            clock=clock,
        )
        bot.wire_runner(runner)

    return _LiveComponents(runner=runner, store=store, bot=bot)


def paper() -> None:
    from v17.config import get_settings
    s = get_settings()
    s.ensure_dirs()
    c = _build_components(s, dry_run=True)
    if c.bot is not None:
        c.bot.start()  # type: ignore[attr-defined]
    c.runner.start()  # type: ignore[attr-defined]


def live(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    from v17.config import get_settings
    s = get_settings()
    s.ensure_dirs()
    if not dry_run:
        gate = s.state_root / "GATE_PASSED"
        if not gate.exists():
            raise typer.BadParameter("GATE_PASSED sentinel missing — run 'v17 validate' first")
    c = _build_components(s, dry_run=dry_run)
    if c.bot is not None:
        c.bot.start()  # type: ignore[attr-defined]
    c.runner.start()  # type: ignore[attr-defined]
