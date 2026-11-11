import os

HOLDOUT_START_UTC_NS = 1735689600000000000  # 2025-01-01 00:00:00 UTC
UNSEAL_ENV_VAR = "V17_HOLDOUT_UNSEAL"


class PartitionGuardError(RuntimeError):
    pass


def is_holdout_ts(ts_utc_ns: int) -> bool:
    return ts_utc_ns >= HOLDOUT_START_UTC_NS


def assert_dev_only(partition: str) -> None:
    if partition != "dev":
        if os.environ.get(UNSEAL_ENV_VAR) == "1":
            return
        raise PartitionGuardError(
            f"Dev-only context attempted to access partition={partition!r}. "
            f"Set {UNSEAL_ENV_VAR}=1 only inside the holdout runner."
        )
