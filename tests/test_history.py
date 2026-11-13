import csv

import pytest

from job_watcher.history import build_history, write_history
from job_watcher.schema import HISTORY_COLUMNS, Posting, Snapshot, posting_id


def job(key="001", **changes):
    return Posting(**dict(dict(source_id=key, employer="Test Employer", title="Finance Analyst",
                               location="Chicago", url="https://example.test/job/" + key), **changes))


def snap(day, *postings, source="alpha", ok=True):
    return Snapshot(source, f"2026-01-{day:02d}", postings, ok)


def test_first_and_still_open_updates_metadata_and_title_rule():
    first = build_history([snap(1, job())])[0]
    assert (first.first_seen, first.last_seen, first.first_run, first.status, first.removed_date) == (
        "2026-01-01", "2026-01-01", True, "open", "")
    row = build_history([snap(1, job()), snap(3, job(title="Data Analyst", department="Data"))])[0]
    assert (row.first_seen, row.last_seen, row.status) == ("2026-01-01", "2026-01-03", "open")
    assert not row.in_role and row.department == "Data"


def test_new_after_first_and_first_is_per_source():
    rows = build_history([snap(1, job()), snap(2, job(), job("002")), snap(3, job(), source="beta")])
    assert [r.first_run for r in rows] == [True, False, True]
    assert rows[1].first_seen == "2026-01-02"


def test_removal_and_repeated_absence_preserve_last_seen_and_removal_date():
    row = build_history([snap(1, job()), snap(2), snap(3)])[0]
    assert (row.status, row.last_seen, row.removed_date) == ("removed", "2026-01-01", "2026-01-02")


def test_failure_and_missing_source_never_remove():
    rows = build_history([snap(1, job()), snap(2, ok=False), snap(3, job(), source="beta")])
    assert rows[0].status == "open" and rows[0].last_seen == "2026-01-01"
    assert rows[0].removed_date == ""


def test_reappearance_preserves_original_first_seen_and_first_run():
    rows = build_history([snap(1), snap(2, job()), snap(3), snap(4, job())])
    row = rows[0]
    assert (row.status, row.first_seen, row.last_seen, row.first_run, row.removed_date) == (
        "open", "2026-01-02", "2026-01-04", False, "")
    row = build_history([snap(1, job()), snap(2), snap(4, job())])[0]
    assert row.first_run and row.first_seen == "2026-01-01"


def test_failed_earliest_attempt_does_not_define_first_raw_file():
    row = build_history([snap(1, ok=False), snap(2, job())])[0]
    assert row.first_run and row.first_seen == "2026-01-02"


def test_removal_is_source_scoped():
    rows = build_history([snap(1, job()), snap(1, job(), source="beta"), snap(2)])
    assert [r.status for r in rows] == ["removed", "open"]


def test_rebuild_is_order_independent_and_ids_sorted():
    snapshots = [snap(1, job("z"), job("a")), snap(2, job("z")), snap(3, job("b"), source="beta")]
    rows = build_history(snapshots)
    assert rows == build_history(reversed(snapshots))
    assert [r.posting_id for r in rows] == sorted(r.posting_id for r in rows)
    assert posting_id("alpha", "001") == "alpha:001"
    assert posting_id("alpha", "x:y") != posting_id("alpha", "x%3Ay")


def test_csv_exact_schema_and_boolean_format(tmp_path):
    expected = "posting_id source source_id employer title location department posted_date url in_role first_run first_seen last_seen status removed_date".split()
    assert list(HISTORY_COLUMNS) == expected
    path = tmp_path / "history.csv"
    write_history(reversed(build_history([snap(1, job("z"), job("a"))])), path)
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        records = list(reader)
        assert reader.fieldnames == expected
    assert [x["source_id"] for x in records] == ["a", "z"]
    assert records[0]["in_role"] == records[0]["first_run"] == "true"
    assert records[0]["posted_date"] == records[0]["department"] == ""


def test_invalid_or_ambiguous_snapshots_rejected():
    with pytest.raises(ValueError):
        build_history([snap(1), snap(1)])
    with pytest.raises(ValueError):
        snap(1, job(), job())
    with pytest.raises(ValueError):
        snap(1, job(), ok=False)
    with pytest.raises(ValueError):
        Snapshot("alpha", "2026-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        job(posted_date="Posted Today")
