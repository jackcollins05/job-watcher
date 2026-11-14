"""Explicit live dry-run CLI; importing this module never makes requests."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .adapters import adapter_for
from .adapters.base import Capture, ConvertedPosting, JsonTransport, SmokeLimitReached
from .raw import convert_raw, envelope
from .sources import PRIMARY_SOURCES, Source


@dataclass
class FetchResult:
    source: str
    employer: str
    ok: bool
    count: int
    postings: list[ConvertedPosting]
    raw: dict
    error: Optional[str] = None
    truncated: bool = False
    diagnostics: dict = field(default_factory=dict)
    failure_class: str = ""


def raw_count(pages):
    count = 0
    for page in pages:
        if page["kind"] != "list":
            continue
        body = page["response"]
        if not isinstance(body, dict):
            continue
        batch = body.get("jobPostings", body.get("jobs"))
        if batch is None:
            items = body.get("items", [])
            batch = items[0].get("requisitionList", []) if items and isinstance(items[0], dict) else []
        if isinstance(batch, list):
            count += len(batch)
    return count


def fetch_source(source: Source, transport=None, *, fetched_at=None,
                 max_pages=None, dry_run=False, page_safety_limit=5000,
                 progress=None, validate_pepsico_pagination=False) -> FetchResult:
    """Failure returns captured partial pages but zero authoritative postings.

    count is the number of raw list records received, including cross-page overlaps;
    normalized count is deduplicated. Neither is the advertised board total.
    max_pages is an opt-in manual smoke limit and requires dry_run=True. With no
    smoke limit, paginate fully; page_safety_limit remains a failure-only guard.
    Truncated smoke results expose converted rows but raw.complete stays False.
    """
    if max_pages is not None:
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        if not dry_run:
            raise ValueError("max_pages is only permitted for manual dry-run validation")
    if page_safety_limit < 1:
        raise ValueError("page_safety_limit must be positive")
    instant = fetched_at or datetime.now(timezone.utc)
    pages = []
    diagnostics = {}
    adapter = None
    raw = envelope(source, instant, pages, complete=False)
    try:
        capture = Capture(transport if transport is not None else JsonTransport(), pages,
                          smoke_max_pages=max_pages, progress=progress)
        adapter = adapter_for(source)
        try:
            adapter.fetch(source, capture, max_pages=page_safety_limit,
                          validate_pepsico_pagination=validate_pepsico_pagination)
        except SmokeLimitReached:
            # Smoke-test rows can be inspected, but must never become successful
            # daily raw files or removal-authoritative history input.
            postings = adapter.convert(source, pages)
            if hasattr(adapter, "diagnostics"):
                diagnostics = adapter.diagnostics(source, pages)
            raw["smoke_truncated"] = True
            raw["error"] = f"manual dry-run truncated at {max_pages} list pages"
            return FetchResult(source.key, source.employer, True, raw_count(pages),
                               postings, raw, truncated=True, diagnostics=diagnostics)
        raw["complete"] = True
        if hasattr(adapter, "diagnostics"):
            diagnostics = adapter.diagnostics(source, pages)
            raw["diagnostics"] = diagnostics
        postings = convert_raw(raw)
        received = raw_count(pages)
        deduplicated_platforms = {"Workday CXS", "Oracle Recruiting CE", "iCIMS / Jibe"}
        if received < len(postings) or (received != len(postings) and source.platform not in deduplicated_platforms):
            raise ValueError("raw/normalized count mismatch")
        return FetchResult(source.key, source.employer, True, raw_count(pages), postings, raw,
                           diagnostics=diagnostics)
    except Exception as exc:
        # A source failure must not stop subsequent sources or become empty success.
        message = f"{type(exc).__name__}: {exc}"
        if adapter is not None and hasattr(adapter, "diagnostics"):
            try:
                diagnostics = adapter.diagnostics(source, pages)
            except Exception:
                pass
        raw.update(complete=False, error=message)
        return FetchResult(source.key, source.employer, False, raw_count(pages), [], raw, message,
                           diagnostics=diagnostics, failure_class=getattr(exc, "failure_class", "unexpected_error"))


def main(argv=None, *, transport_factory=JsonTransport):
    parser = argparse.ArgumentParser(description="Anonymous source smoke test; no file writes")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--source", choices=[s.key for s in PRIMARY_SOURCES])
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="required; only dry-run operation is implemented")
    parser.add_argument("--validate-pepsico-pagination", action="store_true",
                        help="explicitly try unvalidated page>1; fail on repeated IDs or count mismatch")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="manual dry-run list-page limit; partial results cannot be saved as snapshots")
    args = parser.parse_args(argv)
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be positive")
    selected = [s for s in PRIMARY_SOURCES if args.all or s.key == args.source]
    failed = False
    for source in selected:
        print(f"{source.key}: fetching...", flush=True)
        result = fetch_source(source, transport_factory(),
                              dry_run=True, max_pages=args.max_pages,
                              progress=lambda message, key=source.key: print(f"{key}: {message}", flush=True),
                              validate_pepsico_pagination=args.validate_pepsico_pagination)
        if result.truncated:
            line = (f"{result.source}: TRUNCATED (dry-run) raw={result.count} "
                    f"normalized={len(result.postings)}; not a complete snapshot")
        elif result.ok:
            line = f"{result.source}: OK raw={result.count} normalized={len(result.postings)}"
            if result.diagnostics.get("skipped_malformed"):
                line += f" skipped_malformed={result.diagnostics['skipped_malformed']}"
        else:
            reason = " ".join((result.error or "unknown error").split())[:240]
            line = f"{result.source}: FAIL {result.failure_class} {reason} raw={result.count} normalized={len(result.postings)}"
        print(line, flush=True)
        failed |= not result.ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
