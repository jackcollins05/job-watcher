"""Versioned raw envelopes: replay needs no network, audit or current registry."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import tempfile

from .adapters import adapter_for
from .adapters.base import AdapterError
from .schema import Snapshot
from .sources import Source

FORMAT_VERSION = 1


def utc_timestamp(instant):
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise AdapterError("fetched_at must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def envelope(source, fetched_at, pages, *, complete, error=None):
    return {"format_version": FORMAT_VERSION, "source": source.key,
            "employer": source.employer, "configuration": asdict(source),
            "fetched_at": utc_timestamp(fetched_at), "complete": complete,
            "error": error, "pages": pages}


def convert_raw(raw):
    """Reconvert complete saved responses into sorted pre-history postings."""
    if not isinstance(raw, dict) or raw.get("format_version") != FORMAT_VERSION:
        raise AdapterError("unsupported raw format")
    if raw.get("complete") is not True or raw.get("error") is not None:
        raise AdapterError("failed/incomplete raw envelope is not a valid snapshot")
    try:
        source = Source(**raw["configuration"])
        if raw["source"] != source.key or raw["employer"] != source.employer:
            raise AdapterError("raw identity/configuration mismatch")
        if not isinstance(raw["pages"], list) or not raw["pages"]:
            raise AdapterError("raw snapshot must preserve response pages")
        return adapter_for(source).convert(source, raw["pages"])
    except (KeyError, TypeError) as exc:
        raise AdapterError("malformed raw envelope/page structure") from exc


def as_snapshot(raw):
    rows = convert_raw(raw)
    try:
        instant = datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00"))
        day = utc_timestamp(instant)[:10]
    except (ValueError, TypeError, AttributeError) as exc:
        raise AdapterError("invalid raw fetched_at") from exc
    source = Source(**raw["configuration"])
    adapter = adapter_for(source)
    diagnostics = adapter.diagnostics(source, raw["pages"]) if hasattr(adapter, "diagnostics") else {}
    return Snapshot(raw["source"], day, tuple(row.as_posting() for row in rows),
                    unresolved_source_ids=tuple(diagnostics.get("unresolved_source_ids", ())),
                    removals_safe=diagnostics.get("removals_safe", True))


def _no_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            compact = key.lower().replace("_", "").replace("-", "")
            if compact in {"authorization", "cookie", "setcookie", "accesstoken",
                           "refreshtoken", "csrftoken", "password", "apikey"}:
                raise AdapterError("refusing raw payload containing authentication material")
            _no_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _no_secrets(item)


def write_raw(raw, root=Path("data/raw"), *, replace=False) -> Path:
    """Atomic writer; explicit replace=True supports daily production reruns.

    Response JSON objects are preserved, not just converted rows. JSON key order
    and gzip headers are deterministic for a given envelope. Request and response
    headers are never stored. A failed/partial fetch cannot write a daily file.
    """
    snapshot = as_snapshot(raw)
    _no_secrets(raw)
    body = json.dumps(raw, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as zipped:
        zipped.write(body)
    target = Path(root) / snapshot.date / (snapshot.source + ".json.gz")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temp_name = handle.name
            handle.write(buffer.getvalue())
        if replace:
            os.replace(temp_name, target)
            temp_name = None
        else:
            os.link(temp_name, target)  # Default refuses an existing daily file.
    finally:
        if temp_name is not None:
            os.unlink(temp_name)
    return target


def read_raw(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        raw = json.load(handle)
    as_snapshot(raw)
    return raw
