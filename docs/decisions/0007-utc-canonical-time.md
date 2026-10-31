# ADR-0007: UTC-Canonical Timestamps Everywhere

## Status
Accepted

## Date
2026-10-28

## Context
The system touches three timezones that routinely trip bots:

- **UTC** — the only unambiguous reference.
- **America/New_York** — ICT killzone definitions (London killzone = 02:00–05:00 NY) and FTMO server reference.
- **Europe/London** — operator's trading day and the human-readable killzone label (07:00–10:00 London).

Daylight Saving Time offsets shift twice a year, and the US and UK transition on different dates in March and October. A naive datetime in one zone silently represents a different instant in another, which can push a trade from inside the killzone to outside and flip bias calculations.

Historical CSVs from Dukascopy are UTC. MT5 broker servers report in their own server timezone, which varies per broker. Logs across machines must be comparable.

Python 3.9+ ships `zoneinfo` with IANA data; `pytz` is deprecated and should be avoided.

## Decision
All stored, logged, and in-memory timestamps are **UTC** with `tzinfo=datetime.timezone.utc` set. Naive datetimes are banned by lint rule (`ruff` rule set, custom check).

Timezone conversion happens at exactly three boundaries:

1. **Scheduler boundary** — APScheduler cron fires on Europe/London time; the dispatcher converts the fire time to UTC immediately.
2. **Killzone filter boundary** — the London killzone filter converts the UTC bar timestamp to America/New_York, checks `02:00 <= local.time() < 05:00`, discards the local value.
3. **Display boundary** — Telegram alerts and the daily report format timestamps in Europe/London for human readability.

Internally, everything stays UTC. All DTOs (`Bar.ts`, `Tick.ts`, `Signal.at`, etc.) are UTC. All Parquet files are UTC. All SQLite rows are UTC. All logs are UTC.

Conversion helpers live in `src/v17/common/clock.py`:

```python
def to_ny(dt: datetime) -> datetime: ...
def to_london(dt: datetime) -> datetime: ...
def in_london_killzone_utc(ts_utc: datetime) -> bool: ...
```

The `Clock` Protocol (`docs/API.md` §5 M9) returns UTC `datetime` objects.

## Alternatives Considered

### Broker-server timezone as canonical
- **Pros**: No conversion when reading/writing to MT5.
- **Cons**: Broker TZ varies per broker and sometimes mid-year (GMT+2/+3); invalidates stored timestamps on any broker switch; comparing historical runs across broker changes becomes a nightmare.
- **Rejected**: fragile and non-portable.

### London (Europe/London) as canonical
- **Pros**: Matches the human-facing killzone label; fewer conversions at the display boundary.
- **Cons**: DST transitions still bite; a 02:30 bar during the spring-forward hour either does not exist or is ambiguous; cross-system log comparison requires converting back to UTC anyway.
- **Rejected**: moves the DST problem around rather than solving it.

### America/New_York as canonical
- **Pros**: ICT setups are defined in NY time; killzone filter needs no conversion.
- **Cons**: Same DST ambiguity as London; harder for log correlation with external services (which almost all use UTC).
- **Rejected**: internal convenience is not worth losing UTC's universality.

### Naive datetimes (no tzinfo)
- **Pros**: Simpler types; faster.
- **Cons**: Already the number-one cause of silent bugs in trading systems; strongly discouraged by the Python community; impossible to safely combine with any dated external data.
- **Rejected**: banned.

## Consequences
- `datetime.now()` without `tz=UTC` is forbidden in the codebase; use `clock.now()` which always returns `datetime(..., tzinfo=UTC)`.
- All CSV ingestion paths parse to UTC and assert `tzinfo is UTC` before writing Parquet.
- MT5 Gateway converts broker timestamps to UTC on the read side and converts UTC order times to broker TZ only inside the final `MetaTrader5` call.
- Tests use `FrozenClock(tz=UTC)` for determinism.
- Operator-facing output (Telegram, report) is in Europe/London for familiarity.
