"""One daily production run. Invoke explicitly; tests inject offline fetchers."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from .build_history import load_archive
from .fetch import fetch_source
from .history import build_history, history_csv
from .issues import format_issue
from .raw import as_snapshot, utc_timestamp, write_raw
from .sources import PRIMARY_SOURCES
from .status import build_status
from .storage import atomic_write
from .adapters.base import AdapterError


@dataclass(frozen=True)
class SourceOutcome:
    name: str
    ok: bool
    count: int
    error: str = ""
    failure_class: str = ""
    raw_count: int = 0
    skipped_malformed: int = 0


@dataclass
class RunResult:
    date: str
    outcomes: list[SourceOutcome]
    history: list
    status: dict
    issue_title: str
    issue_body: str


def run_pipeline(data_dir=Path("data"), *, started_at=None,
                 sources=PRIMARY_SOURCES, fetcher=fetch_source, progress=None):
    """Fetch independently, replace today's raw state, then derive all outputs.

    Source failures are nonfatal. Archive corruption/derived-output write failures
    are fatal: never silently commit misleading output. Status counts are unique
    normalized postings, consistent with history (raw result counts may be larger).
    """
    instant = started_at if started_at is not None else datetime.now(timezone.utc)
    timestamp = utc_timestamp(instant)
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    day = timestamp[:10]
    sources = tuple(sources)
    keys = [s.key for s in sources]
    if len(keys) != len(set(keys)):
        raise ValueError("configured sources must be unique")
    data_dir = Path(data_dir)
    outcomes = []
    for source in sources:
        target = data_dir / "raw" / day / (source.key + ".json.gz")
        if progress:
            progress(f"{source.key}: fetching...")
        try:
            result = fetcher(source, fetched_at=instant, dry_run=False,
                             validate_pepsico_pagination=True,
                             progress=(lambda msg, key=source.key: progress(f"{key}: {msg}")) if progress else None)
            if not result.ok or result.truncated:
                raise AdapterError(result.error or "source returned an incomplete snapshot",
                                   failure_class=result.failure_class or "source_validation")
            snapshot = as_snapshot(result.raw)
            if (result.source != source.key or snapshot.source != source.key or
                    snapshot.date != day or result.raw["employer"] != source.employer):
                raise ValueError("fetched raw identity/date mismatch")
            write_raw(result.raw, data_dir / "raw", replace=True)
            outcome = SourceOutcome(source.key, True, len(snapshot.postings), raw_count=result.count,
                                    skipped_malformed=result.diagnostics.get("skipped_malformed", 0))
        except Exception as exc:
            # Failure MUST remove an earlier successful raw file for this day.
            # If unlink itself fails, abort: stale evidence cannot be called failed.
            target.unlink(missing_ok=True)
            reason = " ".join(str(exc).split())[:240]
            outcome = SourceOutcome(source.key, False, 0, reason,
                                    failure_class=getattr(exc, "failure_class", "unexpected_error"))
        outcomes.append(outcome)
        if progress:
            if outcome.ok:
                progress(f"{source.key}: OK raw={outcome.raw_count} normalized={outcome.count} "
                         f"skipped_malformed={outcome.skipped_malformed}")
            else:
                progress(f"{source.key}: FAIL {outcome.failure_class} {outcome.error}")

    snapshots = load_archive(data_dir / "raw")
    rows = build_history(snapshots)
    status = build_status(snapshots, instant, keys)
    body = format_issue(rows, day)
    # Compute/validate everything before replacing either derived output.
    atomic_write(data_dir / "history.csv", history_csv(rows).encode("utf-8"))
    atomic_write(data_dir / "status.json", (json.dumps(status, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return RunResult(day, outcomes, rows, status, day, body)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daily production fetch + raw-only history/status rebuild")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    result = run_pipeline(args.data_dir, progress=lambda msg: print(msg, flush=True))
    successes = sum(s.ok for s in result.outcomes)
    print(f"Daily run {result.date}: {successes}/{len(result.outcomes)} sources successful; "
          "history/status written; dated issue content prepared", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
