# ADR-0008: Pydantic BaseModel for All DTOs with Branded ID Types

## Status
Accepted

## Date
2026-10-28

## Context
The system has a well-defined domain model (`docs/API.md` §1–4): `Bar`, `Tick`, `Zone`, `Swing`, `Sweep`, `StructureSnapshot`, `Signal`, `CalendarEvent`, `AccountState`, `Decision`, `OrderRequest`, `OrderResult`, `Position`, and more. These DTOs cross module boundaries (M1→M2→M3→M4→M5/M8→M7) and are serialized to Parquet, SQLite, JSONL logs, and Telegram payloads.

ID types (`Symbol`, `Ticket`, `SignalId`, `RunId`) are easy to mix up because they are all strings or ints at runtime. A `SignalId` passed where a `Ticket` is expected is a silent logic bug that only surfaces at MT5.

The project is already type-hinted strictly (`mypy --strict`, SPEC §9).

## Decision
Model every DTO as a `pydantic.BaseModel` v2+ with:

- `model_config = ConfigDict(frozen=True, extra="forbid")` by default.
- `Decimal` for prices and lot sizes.
- `datetime` with `tzinfo=UTC` enforced via validator.
- Explicit `Literal[...]` and `Enum` types for finite choice fields.

Model every ID as a `typing.NewType`:

```python
Symbol = NewType("Symbol", str)
Ticket = NewType("Ticket", int)
SignalId = NewType("SignalId", str)
RunId = NewType("RunId", str)
```

`mypy --strict` enforces that these ID types cannot be interchanged with their underlying primitive or with each other without an explicit cast.

## Alternatives Considered

### `dataclasses.dataclass`
- **Pros**: Standard library; zero dependency; fast.
- **Cons**: No runtime validation; no serialization helpers; harder to enforce `extra="forbid"`; `frozen=True` works but validators are manual.
- **Rejected**: validation is cheap, bugs are expensive. Trading rejects "it type-checks but blows up at the broker".

### `attrs`
- **Pros**: Mature, flexible, performant.
- **Cons**: Validators available but less idiomatic than pydantic; smaller ecosystem for serialization and schema generation; team familiarity leans pydantic.
- **Rejected**: pydantic is the dominant modern choice and matches the surrounding stack (FastAPI, LangChain-ish ecosystem) if we ever add adjacent tooling.

### `msgspec`
- **Pros**: Extremely fast serialization; typed; small.
- **Cons**: Smaller ecosystem; fewer integrations with downstream tools; team unfamiliar; validation model is less expressive for custom constraints.
- **Rejected**: performance is not the bottleneck (we trade minutes, not microseconds).

### Plain `dict` with TypedDict
- **Pros**: Minimal.
- **Cons**: No validation; typos pass silently; nesting is painful; serialization is manual.
- **Rejected**: unsafe for the problem domain.

### Plain `str` / `int` for IDs
- **Pros**: Simpler.
- **Cons**: Nothing stops `submit(order_request_with_ticket_as_signal_id)`. Trading mistakes caused by argument-order bugs are a well-known failure mode; branding is cheap insurance.
- **Rejected**: branded types pay for themselves on the first argument-order mix-up they prevent.

## Consequences
- `pydantic>=2.7` is a required dependency.
- All DTOs validate at construction. Boundary validation (SPEC §9 §6.9) uses pydantic by default; internal callers trust the types.
- Serialization to JSON, Parquet (via `model_dump`), and SQLite (via a small adapter) is uniform.
- Branded IDs show up in signatures (`def submit(req: OrderRequest) -> OrderResult`) and in error messages, which aids debugging.
- Frozen models force any state transition to produce a new object; this fits the pure/deterministic bias of M1–M6.
- The `extra="forbid"` default fails loudly on schema drift. New fields require an explicit model edit and are additive-only per `docs/API.md` §8.
