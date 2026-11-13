"""Normalized snapshot and exact assignment CSV schema."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
import re
from urllib.parse import quote


def validate_date(value: str) -> str:
    """Require canonical YYYY-MM-DD, rejecting timestamps and relative dates."""
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return value


def posting_id(source: str, source_id: str) -> str:
    """Collision-free deterministic source namespace plus opaque source ID."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", source):
        raise ValueError("source must be a stable lowercase snake_case key")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be a nonblank string")
    return source + ":" + quote(source_id, safe="")


@dataclass(frozen=True)
class Posting:
    source_id: str
    employer: str
    title: str
    location: str
    url: str
    department: str = ""
    posted_date: str = ""

    def __post_init__(self):
        for field in fields(self):
            if not isinstance(getattr(self, field.name), str):
                raise ValueError(f"{field.name} must be a string; use blank for missing fields")
        for name in ("source_id", "employer", "title", "url"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be blank")
        if self.posted_date:
            validate_date(self.posted_date)


@dataclass(frozen=True)
class Snapshot:
    """One complete source/day: ok=True is removal-authoritative, even if empty.

    Failures are run observations, not raw files. Partial/invalid fetches must
    become ok=False; never pass a partial successful snapshot to the builder.
    """

    source: str
    date: str
    postings: tuple[Posting, ...] = ()
    ok: bool = True

    def __post_init__(self):
        validate_date(self.date)
        posting_id(self.source, "validate")
        if type(self.ok) is not bool:
            raise ValueError("ok must be a bool")
        object.__setattr__(self, "postings", tuple(self.postings))
        if not self.ok and self.postings:
            raise ValueError("failed snapshots cannot contain postings")
        ids = [p.source_id for p in self.postings]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source_id in source snapshot")


@dataclass(frozen=True)
class HistoryRow:
    posting_id: str
    source: str
    source_id: str
    employer: str
    title: str
    location: str
    department: str
    posted_date: str
    url: str
    in_role: bool
    first_run: bool
    first_seen: str
    last_seen: str
    status: str
    removed_date: str


HISTORY_COLUMNS = tuple(field.name for field in fields(HistoryRow))
