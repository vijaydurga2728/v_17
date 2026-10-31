from decimal import Decimal

from v17.backtest.montecarlo import hybrid_mc


def _pnls() -> list[Decimal]:
    return [Decimal(x) for x in ("150", "-100", "200", "-50", "100", "-80", "300", "-120", "50", "-30")]


def test_mc_deterministic_same_seed() -> None:
    a = hybrid_mc(_pnls(), seed=42, perm_runs=100, boot_runs=100, block=3)
    b = hybrid_mc(_pnls(), seed=42, perm_runs=100, boot_runs=100, block=3)
    assert a == b


def test_mc_different_seed_differs() -> None:
    a = hybrid_mc(_pnls(), seed=1, perm_runs=100, boot_runs=100, block=3)
    b = hybrid_mc(_pnls(), seed=2, perm_runs=100, boot_runs=100, block=3)
    assert a != b


def test_mc_run_count() -> None:
    r = hybrid_mc(_pnls(), seed=0, perm_runs=50, boot_runs=50, block=3)
    assert r["n"] == 100


def test_mc_empty_trades() -> None:
    r = hybrid_mc([], seed=0)
    assert r["n"] == 0
