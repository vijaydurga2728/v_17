"""Report row counts per symbol/partition for the ingested parquet corpus."""
from pathlib import Path
import pyarrow.parquet as pq


def main() -> None:
    root = Path("data/bars")
    if not root.exists():
        print("data/bars/ does not exist")
        return
    for sym_dir in sorted(root.iterdir()):
        if not sym_dir.is_dir():
            continue
        for partition_dir in sorted(sym_dir.iterdir()):
            files = list(partition_dir.rglob("data.parquet"))
            total = sum(pq.read_metadata(f).num_rows for f in files)
            print(f"{sym_dir.name}/{partition_dir.name}: {len(files)} files, {total:,} rows")


if __name__ == "__main__":
    main()
