"""Daily lifecycle tests use synthetic API envelopes in tmp_path only."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from job_watcher.build_history import load_archive, rebuild_history
from job_watcher.fetch import FetchResult
from job_watcher.issues import load_issue_content, main as issues_main
from job_watcher.pipeline import run_pipeline
from job_watcher.raw import convert_raw, envelope, read_raw, write_raw
from job_watcher.schema import HISTORY_COLUMNS
from job_watcher.sources import PRIMARY_SOURCES, Source

A = Source("alpha", "Example A", "Workday CXS", "https://example.test/wday/cxs/a/External/jobs", "POST")
B = Source("beta", "Example B", "Workday CXS", "https://example.test/wday/cxs/b/External/jobs", "POST")
SOURCES = (A, B)


def instant(day, hour=12):
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def raw_for(source, date, ids):
    body = {"total": len(ids), "jobPostings": [
        {"title": "Finance Analyst", "externalPath": f"/job/Test/Finance-Analyst_{key}",
         "locationsText": "Test City", "bulletFields": [key], "postedOn": "Posted Today"}
        for key in ids], "userAuthenticated": False}
    pages = [{"kind": "list", "request": {"method": "POST", "url": source.endpoint,
              "params": None, "payload": {"limit": 20, "offset": 0}}, "response": body}]
    return envelope(source, date, pages, complete=True)


def fetcher_for(mapping, calls=None):
    def fetch(source, **kwargs):
        if calls is not None:
            calls.append((source.key, kwargs))
        value = mapping[source.key]
        if isinstance(value, Exception):
            raise value
        raw = raw_for(source, kwargs["fetched_at"], value)
        rows = convert_raw(raw)
        return FetchResult(source.key, source.employer, True, len(rows), rows, raw)
    return fetch


def run(tmp_path, day, mapping, **kwargs):
    return run_pipeline(tmp_path, sources=SOURCES, started_at=instant(day),
                        fetcher=fetcher_for(mapping), **kwargs)


def index(result):
    return {row.posting_id: row for row in result.history}


def test_first_production_day_baselines_and_zero_change_issue(tmp_path):
    result = run(tmp_path, 1, {"alpha": ["001", "002"], "beta": ["101"]})
    assert all(r.first_run and r.status == "open" and not r.removed_date for r in result.history)
    assert (result.status["open"], result.status["new_today"], result.status["removed_today"]) == (3, 0, 0)
    assert result.status["first_run_date"] == "2026-01-01"
    assert result.status["days_with_success"] == 1
    assert result.status["sources"] == [{"name": "alpha", "ok": True, "count": 2},
                                        {"name": "beta", "ok": True, "count": 1}]
    assert "No new postings." in result.issue_body and "No removed postings." in result.issue_body
    assert result.issue_title == "2026-01-01"
    assert set(json.loads((tmp_path / "status.json").read_text())) == {
        "run_time", "first_run_date", "days_with_success", "open", "new_today", "removed_today", "sources"}
    assert (tmp_path / "history.csv").read_text().splitlines()[0] == ",".join(HISTORY_COLUMNS)
    for source in SOURCES:
        path = tmp_path / "raw" / "2026-01-01" / (source.key + ".json.gz")
        assert read_raw(path)["complete"]


def test_day_two_failure_new_removal_and_reappearance(tmp_path):
    run(tmp_path, 1, {"alpha": ["001", "002"], "beta": ["101"]})
    calls = []
    second = run_pipeline(tmp_path, sources=SOURCES, started_at=instant(2),
                          fetcher=fetcher_for({"alpha": ["002", "003"], "beta": RuntimeError("offline fixture")}, calls))
    rows = index(second)
    assert rows["alpha:001"].status == "removed" and rows["alpha:001"].removed_date == "2026-01-02"
    assert rows["alpha:002"].first_seen == "2026-01-01" and rows["alpha:002"].last_seen == "2026-01-02"
    assert not rows["alpha:003"].first_run and rows["alpha:003"].first_seen == "2026-01-02"
    assert rows["beta:101"].status == "open" and rows["beta:101"].last_seen == "2026-01-01"
    assert second.status["new_today"] == second.status["removed_today"] == 1
    assert second.outcomes[1].ok is False and "offline fixture" in second.outcomes[1].error
    assert second.status["sources"][1] == {"name": "beta", "ok": False, "count": 0}
    assert not (tmp_path / "raw/2026-01-02/beta.json.gz").exists()
    assert len(calls) == 2
    third = run(tmp_path, 3, {"alpha": ["001", "003"], "beta": ["101"]})
    row = index(third)["alpha:001"]
    assert row.status == "open" and row.first_seen == "2026-01-01" and row.first_run
    assert row.last_seen == "2026-01-03" and row.removed_date == ""
    assert third.status["new_today"] == 0 and third.status["removed_today"] == 1
    assert third.status["days_with_success"] == 3
    assert [r.posting_id for r in third.history] == sorted(r.posting_id for r in third.history)


def test_same_day_success_to_failure_removes_stale_raw_and_rebuilds(tmp_path):
    run(tmp_path, 1, {"alpha": ["001"], "beta": ["101"]})
    run(tmp_path, 2, {"alpha": ["001", "002"], "beta": []})
    stale = tmp_path / "raw/2026-01-02/beta.json.gz"
    assert stale.exists()
    second = run(tmp_path, 2, {"alpha": ["001"], "beta": RuntimeError("rerun failed")})
    assert not stale.exists()
    rows = index(second)
    assert "alpha:002" not in rows  # Superseded raw was replaced, not appended.
    assert rows["beta:101"].status == "open" and rows["beta:101"].removed_date == ""
    assert rows["beta:101"].last_seen == "2026-01-01"
    assert second.status["days_with_success"] == 2
    assert second.status["sources"][1] == {"name": "beta", "ok": False, "count": 0}
    assert "No removed postings." in second.issue_body
    # A further successful rerun replaces the source/date and its daily changes.
    third = run(tmp_path, 2, {"alpha": ["003"], "beta": ["102"]})
    assert stale.exists() and third.status["days_with_success"] == 2
    assert third.status["new_today"] == third.status["removed_today"] == 2
    assert index(third)["beta:101"].removed_date == "2026-01-02"
    assert not index(third)["beta:102"].first_run


def test_all_failed_rerun_removes_date_from_success_days(tmp_path):
    run(tmp_path, 1, {"alpha": ["001"], "beta": ["101"]})
    run(tmp_path, 2, {"alpha": ["002"], "beta": ["102"]})
    result = run(tmp_path, 2, {"alpha": RuntimeError("a"), "beta": RuntimeError("b")})
    assert result.status["days_with_success"] == 1 and result.status["open"] == 2
    assert result.status["removed_today"] == 0
    assert not list((tmp_path / "raw/2026-01-02").glob("*.json.gz"))
    assert all(not s["ok"] and s["count"] == 0 for s in result.status["sources"])


def test_source_first_success_is_independent_of_global_first_day(tmp_path):
    run(tmp_path, 1, {"alpha": ["001"], "beta": RuntimeError("not available")})
    result = run(tmp_path, 2, {"alpha": ["001", "002"], "beta": ["101"]})
    assert index(result)["beta:101"].first_run
    assert result.status["new_today"] == 1  # Alpha 002 only.
    assert result.status["first_run_date"] == "2026-01-01"


def test_raw_only_rebuild_is_byte_identical_after_deleting_history(tmp_path):
    run(tmp_path, 1, {"alpha": ["003", "001"], "beta": ["101"]})
    run(tmp_path, 2, {"alpha": ["002"], "beta": RuntimeError("failed")})
    run(tmp_path, 3, {"alpha": ["001", "002"], "beta": []})
    target = tmp_path / "history.csv"
    original = target.read_bytes()
    target.unlink()
    rebuilt = rebuild_history(tmp_path)
    assert target.read_bytes() == original
    assert [r.posting_id for r in rebuilt] == sorted(r.posting_id for r in rebuilt)
    rebuild_history(tmp_path, verify=True)
    target.write_text("not authoritative")
    with pytest.raises(ValueError, match="differs"):
        rebuild_history(tmp_path, verify=True)
    rebuild_history(tmp_path)
    assert target.read_bytes() == original


def test_archive_rejects_corrupt_or_misfiled_raw(tmp_path):
    raw = raw_for(A, instant(1), ["001"])
    path = write_raw(raw, tmp_path / "raw")
    wrong_day = tmp_path / "raw/2026-01-02"
    wrong_day.mkdir()
    path.rename(wrong_day / path.name)
    with pytest.raises(ValueError, match="does not match"):
        load_archive(tmp_path / "raw")


def test_pipeline_continues_when_first_source_raises(tmp_path):
    result = run(tmp_path, 1, {"alpha": RuntimeError("first source failed"), "beta": ["101"]})
    assert [s.ok for s in result.outcomes] == [False, True]
    assert len(result.history) == 1


def test_pipeline_rejects_partial_success_and_removes_stale_file(tmp_path):
    run(tmp_path, 1, {"alpha": ["001"], "beta": ["101"]})
    def partial(source, **kwargs):
        raw = raw_for(source, kwargs["fetched_at"], ["001"])
        return FetchResult(source.key, source.employer, True, 1, [], raw, truncated=True)
    result = run_pipeline(tmp_path, sources=SOURCES, started_at=instant(1), fetcher=partial)
    assert all(not o.ok for o in result.outcomes)
    assert result.history == [] and result.status["days_with_success"] == 0
    assert result.status["first_run_date"] is None
    assert not list((tmp_path / "raw/2026-01-01").glob("*.json.gz"))


def test_utc_start_date_and_production_fetch_options(tmp_path):
    calls = []
    local_start = datetime(2026, 1, 1, 23, 59, tzinfo=timezone(timedelta(hours=-6)))
    result = run_pipeline(tmp_path, sources=SOURCES, started_at=local_start,
                          fetcher=fetcher_for({"alpha": ["001"], "beta": []}, calls))
    assert result.date == "2026-01-02" and result.status["run_time"] == "2026-01-02T05:59:00Z"
    assert all(kwargs["fetched_at"] == calls[0][1]["fetched_at"] for _, kwargs in calls)
    assert all(kwargs["dry_run"] is False and kwargs["validate_pepsico_pagination"] is True for _, kwargs in calls)
    assert all("max_pages" not in kwargs for _, kwargs in calls)


def test_successful_empty_snapshot_counts_as_a_success_day(tmp_path):
    result = run(tmp_path, 1, {"alpha": [], "beta": RuntimeError("failed")})
    assert result.status["days_with_success"] == 1
    assert result.status["sources"][0] == {"name": "alpha", "ok": True, "count": 0}


def test_prepared_issue_roundtrips_from_derived_outputs_and_preview_is_offline(tmp_path, monkeypatch, capsys):
    run(tmp_path, 1, {"alpha": ["001"], "beta": ["101"]})
    result = run(tmp_path, 2, {"alpha": ["002"], "beta": []})
    day, body = load_issue_content(tmp_path)
    assert day == result.date and body == result.issue_body
    def blocked(*args):
        raise AssertionError("preview cannot create a GitHub client")
    monkeypatch.setattr("job_watcher.issues.GhIssues", blocked)
    assert issues_main(["--data-dir", str(tmp_path), "--preview"]) == 0
    assert capsys.readouterr().out == f"Title: {day}\n\n{body}"


def test_default_pipeline_attempts_every_primary_even_if_all_fail(tmp_path):
    attempted = []
    def failing(source, **kwargs):
        attempted.append(source.key)
        raise RuntimeError("offline fixture failure")
    result = run_pipeline(tmp_path, started_at=instant(1), fetcher=failing)
    assert attempted == [source.key for source in PRIMARY_SOURCES]
    assert len(result.outcomes) == len(result.status["sources"]) == 15
    assert result.status["first_run_date"] is None and result.status["days_with_success"] == 0
    assert all(not source["ok"] and source["count"] == 0 for source in result.status["sources"])
    assert not list((tmp_path / "raw").glob("*/*.json.gz"))


def test_primary_backup_runs_share_one_success_raw_date_and_issue(tmp_path):
    from test_issues import FakeIssues
    from job_watcher.issues import owned_day, publish_daily
    client = FakeIssues()
    for hour, ids in ((12, ['001']), (19, ['002'])):
        result = run_pipeline(tmp_path, sources=SOURCES, started_at=instant(1, hour),
                              fetcher=fetcher_for({'alpha': ids, 'beta': ['101']}))
        publish_daily(client, result.issue_title, result.issue_body)
        assert result.status['days_with_success'] == 1
        assert [p.name for p in (tmp_path / 'raw').iterdir()] == ['2026-01-01']
        assert len(list((tmp_path / 'raw/2026-01-01').glob('*.json.gz'))) == 2
        assert [owned_day(i) for i in client.issues] == ['2026-01-01']
        rebuild_history(tmp_path, verify=True)
    assert [call[0] for call in client.calls] == ['create', 'update']
    assert set(index(result)) == {'alpha:002', 'beta:101'}


def test_daily_workflow_redundant_schedules_and_manual_dispatch():
    from pathlib import Path
    import re
    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/daily.yml').read_text()
    assert re.findall(r"^    - cron: '([^']+)'$", workflow, re.M) == ['17 12 * * *', '47 19 * * *']
    assert re.search(r'^  workflow_dispatch:\s*$', workflow, re.M)
    assert 'group: job-watcher-daily' in workflow and 'cancel-in-progress: false' in workflow
    assert 'issues: write' in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow


def test_oversized_pipeline_issue_keeps_complete_history(tmp_path):
    import csv
    from job_watcher.issues import MAX_ISSUE_BYTES
    run(tmp_path, 1, {'alpha': [], 'beta': []})
    result = run(tmp_path, 2, {'alpha': [f'{i:04}' for i in range(1000)], 'beta': []})
    assert 'Report shortened' in result.issue_body
    assert len(result.issue_body.encode('utf-8')) <= MAX_ISSUE_BYTES
    assert 'New postings: 1000; removed postings: 0.' in result.issue_body
    with (tmp_path / 'history.csv').open(newline='') as handle:
        assert len(list(csv.DictReader(handle))) == 1000
    assert len(result.history) == 1000
    rebuild_history(tmp_path, verify=True)
