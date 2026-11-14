"""Rebuild all history from complete daily normalized snapshots, never a CSV."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable

from .role import in_role
from .schema import HISTORY_COLUMNS, HistoryRow, Snapshot, posting_id
from .storage import atomic_write


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
    unresolved_seen = {}
    for snapshot in ordered_snapshots(snapshots):
        if not snapshot.ok:
            continue
        first = snapshot.source not in initialized
        for source_id in snapshot.unresolved_source_ids:
            unresolved_seen.setdefault(posting_id(snapshot.source, source_id), (snapshot.date, first))
        present = set()
        for posting in snapshot.postings:
            key = posting_id(snapshot.source, posting.source_id)
            present.add(key)
            previous = rows.get(key)
            earlier_unresolved = unresolved_seen.get(key)
            rows[key] = HistoryRow(
                posting_id=key, source=snapshot.source, **asdict(posting),
                in_role=in_role(posting.title),
                first_run=previous.first_run if previous else (earlier_unresolved[1] if earlier_unresolved else first),
                first_seen=previous.first_seen if previous else (earlier_unresolved[0] if earlier_unresolved else snapshot.date),
                last_seen=snapshot.date, status="open", removed_date="",
            )
        for key, row in list(rows.items()):
            if row.source != snapshot.source or key in present:
                continue
            if row.source_id in snapshot.unresolved_source_ids:
                # The real ID is present, even though a new usable URL/title was
                # unavailable. Reuse known metadata; never invent a posting row.
                rows[key] = replace(row, last_seen=snapshot.date, status="open", removed_date="")
            elif any(row.source_id.startswith(source_id + "-") for source_id in snapshot.unresolved_source_ids):
                continue  # Ambiguous requisition/posting suffix: preserve state.
            elif snapshot.removals_safe and row.status == "open":
                rows[key] = replace(row, status="removed", removed_date=snapshot.date)
        initialized.add(snapshot.source)
    return [rows[key] for key in sorted(rows)]


def history_csv(rows: Iterable[HistoryRow]) -> str:
    """Deterministic CSV with exact columns and lowercase booleans."""
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
    writer.writeheader()
    for row in sorted(rows, key=lambda r: r.posting_id):
        record = asdict(row)
        for name in ("in_role", "first_run"):
            record[name] = str(record[name]).lower()
        writer.writerow(record)
    return handle.getvalue()


def write_history(rows: Iterable[HistoryRow], path: Path) -> None:
    """Atomic explicit CSV export."""
    atomic_write(path, history_csv(rows).encode("utf-8"))
