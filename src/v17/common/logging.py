from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import structlog


def configure(level: str = "INFO", log_dir: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            log_dir / "v17.jsonl",
            when="midnight",
            utc=True,
            encoding="utf-8",
            backupCount=30,
        )
        handlers.append(fh)
    logging.basicConfig(level=level, format="%(message)s", handlers=handlers, force=True)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    log: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return log
