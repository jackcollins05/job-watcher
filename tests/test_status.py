from datetime import datetime, timedelta, timezone

import pytest

from job_watcher.schema import Posting, Snapshot
from job_watcher.sources import PRIMARY_SOURCES, BACKUP_SOURCES, DROPPED_SOURCES
from job_watcher.status import build_status


def job(key):
    return Posting(key, "Test Employer", "Finance Analyst", "Chicago", "https://example.test/" + key)


def test_counts_dates_and_source_structure():
    snapshots = [
        Snapshot("alpha", "2026-01-01", (job("a"), job("b"))),
        Snapshot("beta", "2026-01-01", (job("c"),)),
        Snapshot("alpha", "2026-01-02", ok=False),
        Snapshot("alpha", "2026-01-03", (job("a"), job("new"))),
        Snapshot("beta", "2026-01-03", ok=False),
        Snapshot("gamma", "2026-01-03", (job("first"),)),
    ]
    status = build_status(snapshots, datetime(2026, 1, 3, 12, tzinfo=timezone.utc), ["alpha", "beta", "gamma", "missing"])
    assert set(status) == {"run_time", "first_run_date", "days_with_success", "open", "new_today", "removed_today", "sources"}
    assert status["run_time"] == "2026-01-03T12:00:00Z"
    assert status["first_run_date"] == "2026-01-01" and status["days_with_success"] == 2
    assert (status["open"], status["new_today"], status["removed_today"]) == (4, 1, 1)
    assert status["sources"] == [
        {"name": "alpha", "ok": True, "count": 2},
        {"name": "beta", "ok": False, "count": 0},
        {"name": "gamma", "ok": True, "count": 1},
        {"name": "missing", "ok": False, "count": 0},
    ]


def test_empty_success_counts_as_raw_day_and_first_run():
    snapshots = [Snapshot("alpha", "2026-01-01", ok=False), Snapshot("alpha", "2026-01-02")]
    s = build_status(snapshots, datetime(2026, 1, 2, tzinfo=timezone.utc), ["alpha"])
    assert s["first_run_date"] == "2026-01-02" and s["days_with_success"] == 1
    assert s["sources"] == [{"name": "alpha", "ok": True, "count": 0}]


def test_timezone_conversion_and_failure_only_run():
    s = build_status([Snapshot("alpha", "2026-01-01", (job("a"),))],
                     datetime(2026, 1, 1, 23, tzinfo=timezone(timedelta(hours=-6))), ["alpha"])
    assert s["run_time"] == "2026-01-02T05:00:00Z"
    assert s["open"] == 1 and s["new_today"] == s["removed_today"] == 0
    assert not s["sources"][0]["ok"]


def test_no_raw_files_has_no_invented_first_date():
    s = build_status([], datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert s["first_run_date"] is None and s["days_with_success"] == 0
    assert len(s["sources"]) == 15
    assert s["open"] == s["new_today"] == s["removed_today"] == 0


def test_reappearance_is_not_new_today():
    snapshots = [Snapshot("alpha", "2026-01-01", (job("a"),)),
                 Snapshot("alpha", "2026-01-02"), Snapshot("alpha", "2026-01-03", (job("a"),))]
    s = build_status(snapshots, datetime(2026, 1, 3, tzinfo=timezone.utc), ["alpha"])
    assert s["new_today"] == s["removed_today"] == 0 and s["open"] == 1


def test_invalid_time_and_future_snapshots_rejected():
    with pytest.raises(ValueError):
        build_status([], datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        build_status([Snapshot("alpha", "2026-01-02")], datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_registry_plan():
    assert (len(PRIMARY_SOURCES), len(BACKUP_SOURCES), len(DROPPED_SOURCES)) == (15, 2, 3)
    assert len({s.key for s in PRIMARY_SOURCES + BACKUP_SOURCES + DROPPED_SOURCES}) == 20
    assert [s.employer for s in PRIMARY_SOURCES if s.search_term] == ["JPMorgan Chase"]
    assert next(s for s in PRIMARY_SOURCES if s.search_term).search_term == "analyst"
