from __future__ import annotations

import typer


def report(day: str = typer.Option("today", "--day")) -> None:
    from datetime import date

    from v17.config import get_settings
    from v17.obs.report import ReportGenerator
    from v17.obs.store import TradeStore, create_engine_for_path

    s = get_settings()
    s.ensure_dirs()

    date_str = date.today().strftime("%Y-%m-%d") if day == "today" else day

    engine = create_engine_for_path(s.db)
    store = TradeStore(engine)
    store.create_tables()
    account = store.load_account(starting_equity=s.starting_equity)
    rg = ReportGenerator(store)

    md = rg.daily_markdown(date_str, account)
    typer.echo(md)

    s.logs_root.mkdir(parents=True, exist_ok=True)
    out_md = s.logs_root / f"report-{date_str}.md"
    out_md.write_text(md)
    out_png = s.logs_root / f"equity-{date_str}.png"
    rg.equity_png(out_png)
    typer.echo(f"saved: {out_md}  equity: {out_png}")
