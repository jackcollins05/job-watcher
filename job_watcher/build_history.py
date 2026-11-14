"""Raw-archive discovery and reproducible standalone history rebuild."""

import argparse
from pathlib import Path

from .history import build_history, history_csv
from .raw import as_snapshot, read_raw
from .schema import validate_date
from .storage import atomic_write


def load_archive(raw_root):
    """Reject corrupt/misfiled evidence rather than silently omitting it."""
    snapshots = []
    for path in sorted(Path(raw_root).glob("*/*.json.gz")):
        validate_date(path.parent.name)
        snapshot = as_snapshot(read_raw(path))
        if snapshot.date != path.parent.name or path.name != snapshot.source + ".json.gz":
            raise ValueError(f"raw snapshot identity/date does not match path: {path}")
        snapshots.append(snapshot)
    return sorted(snapshots, key=lambda s: (s.date, s.source))


def rebuild_history(data_dir=Path("data"), *, verify=False):
    data_dir = Path(data_dir)
    rows = build_history(load_archive(data_dir / "raw"))
    content = history_csv(rows).encode("utf-8")
    target = data_dir / "history.csv"
    if verify:
        if not target.exists() or target.read_bytes() != content:
            raise ValueError("history.csv differs from the raw-only rebuild (or is missing)")
    else:
        atomic_write(target, content)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rebuild history solely from data/raw")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--verify", action="store_true", help="compare without rewriting")
    args = parser.parse_args(argv)
    rows = rebuild_history(args.data_dir, verify=args.verify)
    print(f"history {'verified' if args.verify else 'rebuilt'}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
