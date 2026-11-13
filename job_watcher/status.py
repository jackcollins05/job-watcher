"""Compute status from raw-snapshot evidence; never fabricate persisted status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from .history import build_history, ordered_snapshots
from .schema import Snapshot
from .sources import PRIMARY_SOURCES


def build_status(
    snapshots: Iterable[Snapshot], run_time: datetime,
    source_names: Sequence[str] = tuple(s.key for s in PRIMARY_SOURCES),
) -> dict:
    """Counts cover all tracked postings, including titles outside the role.

    source name is the stable source key. Failure/missing on the run date is
    ok=False,count=0 (not a successful empty snapshot and not a removal).
    An entirely unsuccessful/empty archive has first_run_date=None.
    """
    if run_time.tzinfo is None or run_time.utcoffset() is None:
        raise ValueError("run_time must be timezone-aware")
    instant = run_time.astimezone(timezone.utc)
    today = instant.date().isoformat()
    if len(source_names) != len(set(source_names)):
        raise ValueError("source names must be unique")
    ordered = ordered_snapshots(snapshots)
    if any(s.date > today for s in ordered):
        raise ValueError("snapshots cannot be later than run_time")
    rows = build_history(ordered)
    dates = {s.date for s in ordered if s.ok}
    current = {s.source: s for s in ordered if s.date == today}
    return {
        "run_time": instant.isoformat().replace("+00:00", "Z"),
        "first_run_date": min(dates) if dates else None,
        "days_with_success": len(dates),
        "open": sum(row.status == "open" for row in rows),
        "new_today": sum(row.first_seen == today and not row.first_run for row in rows),
        "removed_today": sum(row.removed_date == today and row.status == "removed" for row in rows),
        "sources": [
            {"name": name, "ok": name in current and current[name].ok,
             "count": len(current[name].postings) if name in current and current[name].ok else 0}
            for name in source_names
        ],
    }
