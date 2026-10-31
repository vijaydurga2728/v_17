from __future__ import annotations
from v17.live.state_machine import RunnerState


def test_all_states_defined() -> None:
    required = {"idle", "pre_flight", "armed", "in_trade", "managed", "closed"}
    actual = {s.value for s in RunnerState}
    assert required == actual


def test_states_are_str() -> None:
    for s in RunnerState:
        assert isinstance(s.value, str)
