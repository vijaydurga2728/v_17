from pathlib import Path
from v17.backtest.wf_orchestrator import run_all_engines_all_folds


def test_orchestrator_produces_six_trade_parquets_dry_run(tmp_path):
    run_all_engines_all_folds(data_root=Path("data"), out_root=tmp_path, dry_run=True)
    for engine_id in [
        "SB-LDN-CE", "SB-LDN-AG",
        "SB-NYAM-CE", "SB-NYAM-AG",
        "SB-NYPM-CE", "SB-NYPM-AG",
    ]:
        assert (tmp_path / "wf" / engine_id / "trades.parquet").exists()
