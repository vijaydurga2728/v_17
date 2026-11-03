import sys
import importlib.metadata as md

def test_python_version_floor():
    assert sys.version_info >= (3, 11), f"Need Python 3.11+, got {sys.version}"

def test_required_packages_present():
    required = [
        "pyarrow", "pandas", "polars", "pytest",
        "hypothesis", "structlog", "numpy", "scipy",
        "typer", "zoneinfo",
    ]
    missing = []
    for pkg in required:
        if pkg == "zoneinfo":
            try:
                import zoneinfo  # noqa: F401
            except ImportError:
                missing.append(pkg)
            continue
        try:
            md.version(pkg)
        except md.PackageNotFoundError:
            missing.append(pkg)
    assert not missing, f"Missing required packages: {missing}"

def test_finnhub_available():
    try:
        md.version("finnhub-python")
    except md.PackageNotFoundError:
        import pytest
        pytest.fail("finnhub-python required for calendar backfill (M2)")
