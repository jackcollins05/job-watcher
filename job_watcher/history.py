"""Rebuild all history from complete daily normalized snapshots, never a CSV."""

from __future__ import annotations

import csv
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable

from .role import in_role
from .schema import HISTORY_COLUMNS, HistoryRow, Snapshot, posting_id


def ordered_snapshots(snapshots: Iterable[Snapshot]) -> list[Snapshot]:
    ordered = sorted(snapshots, key=lambda s: (s.date, s.source))
    keys = [(s.source, s.date) for s in ordered]
    if len(keys) != len(set(keys)):
        raise ValueError("at most one snapshot per source/UTC date is allowed")
    return ordered


def build_history(snapshots: Iterable[Snapshot]) -> list[HistoryRow]:
    """Replay observations; absent/failed sources cannot close any postings."""
    rows: dict[str, HistoryRow] = {}
    initialized: set[str] = set()
    for snapshot in ordered_snapshots(snapshots):
        if not snapshot.ok:
            continue
        first = snapshot.source not in initialized
        present = set()
        for posting in snapshot.postings:
            key = posting_id(snapshot.source, posting.source_id)
            present.add(key)
            previous = rows.get(key)
            rows[key] = HistoryRow(
                posting_id=key, source=snapshot.source, **asdict(posting),
                in_role=in_role(posting.title),
                first_run=previous.first_run if previous else first,
                first_seen=previous.first_seen if previous else snapshot.date,
                last_seen=snapshot.date, status="open", removed_date="",
            )
        for key, row in list(rows.items()):
            if row.source == snapshot.source and row.status == "open" and key not in present:
                rows[key] = replace(row, status="removed", removed_date=snapshot.date)
        initialized.add(snapshot.source)
    return [rows[key] for key in sorted(rows)]


def write_history(rows: Iterable[HistoryRow], path: Path) -> None:
    """Explicit CSV export with exact columns, sorted IDs, lowercase booleans."""
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r.posting_id):
            record = asdict(row)
            for name in ("in_role", "first_run"):
                record[name] = str(record[name]).lower()
            writer.writerow(record)
