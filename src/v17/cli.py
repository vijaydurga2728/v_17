from __future__ import annotations

import typer

from v17.backtest.cli import backtest, montecarlo_cmd, walkforward_cmd
from v17.data.cli import ingest, ingest_calendar
from v17.live.cli import live, paper
from v17.obs.cli import report
from v17.validation.cli import validate

app = typer.Typer(no_args_is_help=True)
app.command("ingest")(ingest)
app.command("ingest-calendar")(ingest_calendar)
app.command("backtest")(backtest)
app.command("walkforward")(walkforward_cmd)
app.command("montecarlo")(montecarlo_cmd)
app.command("validate")(validate)
app.command("paper")(paper)
app.command("live")(live)
app.command("report")(report)


@app.command("kill")
def kill() -> None:
    from v17.config import get_settings
    from v17.live.kill_switch import write_kill

    s = get_settings()
    s.ensure_dirs()
    write_kill(s.state_root)
    typer.echo(f"KILL sentinel written: {s.state_root / 'KILL'}")


if __name__ == "__main__":
    app()
