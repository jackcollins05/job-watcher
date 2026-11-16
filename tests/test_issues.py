"""No real GitHub operations: pure format/selection and an in-memory client."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest

from job_watcher.issues import (GhIssues, format_issue, load_issue_content,
                                marker, owned_day, publish_daily, select_previous)
from job_watcher.schema import HistoryRow


def row(key="a:001", **changes):
    data = dict(posting_id=key, source="a", source_id=key.split(":")[1],
                employer="Test Employer", title="Finance Analyst", location="Test City",
                department="", posted_date="", url="https://example.test/job/001",
                in_role=True, first_run=False, first_seen="2026-01-02",
                last_seen="2026-01-02", status="open", removed_date="")
    return HistoryRow(**dict(data, **changes))


def issue(number, day, state="open", **changes):
    return dict(dict(number=number, title=day, body=marker(day), state=state), **changes)


class FakeIssues:
    def __init__(self, issues=()):
        self.issues = list(deepcopy(issues))
        self.calls = []

    def list_issues(self):
        return deepcopy(self.issues)

    def create_issue(self, title, body):
        self.calls.append(("create", title, body))
        number = max([i["number"] for i in self.issues] + [0]) + 1
        self.issues.append(dict(number=number, title=title, body=body, state="open"))
        return number

    def update_issue(self, number, body):
        self.calls.append(("update", number, body))
        self.issues = [dict(i, body=body, state="open") if i["number"] == number else i for i in self.issues]

    def close_issue(self, number):
        self.calls.append(("close", number))
        self.issues = [dict(i, state="closed") if i["number"] == number else i for i in self.issues]


def test_issue_lists_current_new_and_removed_and_excludes_baseline():
    rows = [row("a:002", first_run=True), row(),
            row("a:003", status="removed", first_seen="2026-01-01", removed_date="2026-01-02"),
            row("a:004", first_seen="2026-01-01"),
            row("a:005", first_seen="2026-01-01", status="removed", removed_date="2026-01-01")]
    body = format_issue(rows, "2026-01-02")
    assert body.startswith(marker("2026-01-02"))
    assert "## NEW POSTINGS" in body and "## REMOVED POSTINGS" in body
    assert body.count("[Finance Analyst]") == 2
    assert "Test Employer" in body and "https://example.test/job/001" in body
    assert body == format_issue(reversed(rows), "2026-01-02")


def test_issue_zero_changes_is_explicit_and_first_day_has_no_new():
    body = format_issue([row(first_run=True)], "2026-01-02")
    assert "No new postings." in body and "No removed postings." in body
    assert body == format_issue([], "2026-01-02")


def test_issue_escapes_titles_without_interpreting_shell_or_markdown():
    body = format_issue([row(title="Finance [Analyst]\n$(echo test)")], "2026-01-02")
    assert "Finance \\[Analyst\\]" in body
    assert "$(echo test)" not in body  # Parentheses escaped; always literal file data.
    assert "Finance [Analyst]\n" not in body


def test_issue_rerun_updates_same_issue_and_closes_only_previous_run():
    client = FakeIssues([issue(1, "2026-01-01"), issue(2, "2025-12-30"),
                         issue(3, "2026-01-02", body="unrelated dated issue"),
                         issue(4, "2026-01-03"),
                         issue(5, "2026-01-01", pull_request={})])
    day = "2026-01-02"
    number = publish_daily(client, day, format_issue([], day))
    assert [c[0] for c in client.calls] == ["create", "close"]
    assert client.calls[1] == ("close", 1)
    changed = format_issue([row()], day)
    assert publish_daily(client, day, changed) == number
    assert client.calls[-1] == ("update", number, changed)
    assert len([i for i in client.issues if owned_day(i) == day]) == 1
    assert all(i["state"] == "open" for i in client.issues if i["number"] in (2, 3, 4, 5))


def test_previous_run_selection_uses_latest_project_date_not_yesterday():
    issues = [issue(9, "2026-01-01"), issue(2, "2026-01-04", state="closed"),
              issue(10, "2026-01-03", body="unrelated"), issue(11, "2026-01-07")]
    assert select_previous(issues, "2026-01-06")["number"] == 2
    assert select_previous(issues, "2025-01-01") is None


def test_upsert_failure_never_closes_previous_issue():
    client = FakeIssues([issue(1, "2026-01-01")])
    def failed(title, body):
        raise RuntimeError("fixture API failed")
    client.create_issue = failed
    with pytest.raises(RuntimeError):
        publish_daily(client, "2026-01-02", format_issue([], "2026-01-02"))
    assert client.calls == [] and client.issues[0]["state"] == "open"


def test_closed_current_issue_is_updated_not_duplicated():
    client = FakeIssues([issue(1, "2026-01-02", state="closed")])
    publish_daily(client, "2026-01-02", format_issue([], "2026-01-02"))
    assert client.calls[0][0] == "update" and client.issues[0]["state"] == "open"


def test_duplicate_owned_issues_fail_without_creating_or_closing():
    client = FakeIssues([issue(1, "2026-01-02"), issue(2, "2026-01-02")])
    with pytest.raises(ValueError, match="multiple owned"):
        publish_daily(client, "2026-01-02", format_issue([], "2026-01-02"))
    assert client.calls == []


def test_ownership_rejects_unrelated_invalid_dates_and_wrong_markers():
    assert owned_day({"title": None}) is None
    assert owned_day({"title": "2026-02-30", "body": ""}) is None
    assert owned_day(issue(1, "2026-01-02", body=marker("2026-01-01"))) is None
    with pytest.raises(ValueError, match="ownership marker"):
        publish_daily(FakeIssues(), "2026-01-02", "unmarked body")


def test_gh_client_preserves_multiline_json_and_paginates_offline(monkeypatch):
    calls = []
    def runner(command, **kwargs):
        payload = None
        if "--input" in command:
            payload = json.loads(Path(command[command.index("--input") + 1]).read_text())
        calls.append((command, kwargs, payload))
        output = [[issue(1, "2026-01-01")], [issue(2, "2026-01-02")]] if "--paginate" in command else {"number": 3}
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")
    monkeypatch.setattr("job_watcher.issues.subprocess.run", runner)
    client = GhIssues("jackcollins05/job-watcher")
    assert len(client.list_issues()) == 2
    body = "line one\nline two $(literal) `literal`\n"
    assert client.create_issue("2026-01-03", body) == 3
    assert calls[-1][2] == {"title": "2026-01-03", "body": body}
    client.update_issue(3, body)
    assert calls[-1][2] == {"body": body, "state": "open"}
    client.close_issue(2)
    assert calls[-1][2] == {"state": "closed"}
    assert all(call[1]["check"] and call[1]["timeout"] == 120 and "shell" not in call[1] for call in calls)


def test_gh_error_surfaces_stderr_and_exit_without_payload_or_secrets(monkeypatch):
    import traceback
    token = 'fixture-private-token'
    monkeypatch.setenv('GH_TOKEN', token)
    body = 'private report\nwith secret details'
    def runner(command, **kwargs):
        payload = Path(command[-1]).read_text()
        raise subprocess.CalledProcessError(1, command, output='private stdout',
            stderr=f'gh: Validation Failed (HTTP 422) {token} ghp_abcdef123 '
                   f'Authorization: Bearer unknown-secret {payload}')
    monkeypatch.setattr('job_watcher.issues.subprocess.run', runner)
    with pytest.raises(RuntimeError) as caught:
        GhIssues('owner/repo').create_issue('2026-01-02', body)
    message = ''.join(traceback.format_exception(caught.type, caught.value, caught.tb))
    assert 'exit code 1' in message and 'Validation Failed (HTTP 422)' in message
    for secret in (token, 'ghp_abcdef123', 'unknown-secret', 'private report',
                   'secret details', 'private stdout'):
        assert secret not in message


def test_gh_diagnostic_truncated(monkeypatch):
    from job_watcher.issues import MAX_DIAGNOSTIC_CHARS
    def runner(command, **kwargs):
        raise subprocess.CalledProcessError(7, command, stderr='failure ' * 1000)
    monkeypatch.setattr('job_watcher.issues.subprocess.run', runner)
    with pytest.raises(RuntimeError) as caught:
        GhIssues('owner/repo').list_issues()
    assert 'exit code 7' in str(caught.value)
    assert str(caught.value).endswith('...[truncated]')
    assert len(str(caught.value).split(': ', 1)[1]) <= MAX_DIAGNOSTIC_CHARS


def test_gh_timeout_handles_bytes_and_sanitizes(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'timeout-secret')
    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 120, stderr=b'network stalled timeout-secret')
    monkeypatch.setattr('job_watcher.issues.subprocess.run', runner)
    with pytest.raises(RuntimeError, match='timed out after 120s: network stalled') as caught:
        GhIssues('owner/repo').list_issues()
    assert 'timeout-secret' not in str(caught.value)
    assert caught.value.__suppress_context__


def test_gh_oserror_does_not_dump_command_or_filename(monkeypatch):
    def runner(command, **kwargs):
        raise OSError(2, 'private details', 'private filename')
    monkeypatch.setattr('job_watcher.issues.subprocess.run', runner)
    with pytest.raises(RuntimeError, match='could not start.*errno=2') as caught:
        GhIssues('owner/repo').list_issues()
    assert 'private' not in str(caught.value)


def test_oversized_issue_preserves_counts_both_movements_and_whole_rows():
    from job_watcher.issues import MAX_ISSUE_BYTES
    rows = [row(f'a:{i:04}', title='分析員 ' * 25) for i in range(400)]
    rows += [row(f'b:{i:04}', title='Removed Analyst', first_seen='2026-01-01',
                 status='removed', removed_date='2026-01-02') for i in range(400)]
    before = deepcopy(rows)
    body = format_issue(rows, '2026-01-02')
    assert len(body.encode('utf-8')) <= MAX_ISSUE_BYTES
    assert 'New postings: 400; removed postings: 400.' in body
    assert 'Report shortened' in body and 'data/history.csv' in body
    assert '分析員' in body and 'Removed Analyst' in body
    import re
    sections = body.split('## ')[1:]
    for section in sections:
        shown = sum(line.startswith('- [') for line in section.splitlines())
        omitted = re.search(r'(\d+) posting\(s\) omitted', section)
        assert shown + (int(omitted[1]) if omitted else 0) == 400
        assert all(line.endswith('Test Employer') for line in section.splitlines() if line.startswith('- '))
    assert rows == before
    assert body == format_issue(reversed(rows), '2026-01-02')


def test_single_oversized_row_is_disclosed_and_does_not_block_later_rows():
    body = format_issue([row(title='x' * 100_000), row('a:002', title='Later Analyst')], '2026-01-02')
    assert 'Later Analyst' in body
    assert '1 posting(s) omitted' in body and 'New postings: 2' in body


def test_close_failure_rerun_updates_existing_issue_then_retries_close():
    client = FakeIssues([issue(1, '2026-01-01')])
    original_close = client.close_issue
    def fail(number):
        raise RuntimeError('close failed')
    client.close_issue = fail
    body = format_issue([], '2026-01-02')
    with pytest.raises(RuntimeError, match='close failed'):
        publish_daily(client, '2026-01-02', body)
    client.close_issue = original_close
    publish_daily(client, '2026-01-02', body)
    assert [call[0] for call in client.calls] == ['create', 'update', 'close']
    assert len([i for i in client.issues if owned_day(i) == '2026-01-02']) == 1
    assert client.issues[0]['state'] == 'closed'


@pytest.mark.parametrize('stderr', [None, '', 'token=other-secret https://user:pass@example.test'])
def test_gh_empty_stderr_and_other_credentials(monkeypatch, stderr):
    def runner(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr=stderr)
    monkeypatch.setattr('job_watcher.issues.subprocess.run', runner)
    with pytest.raises(RuntimeError) as caught:
        GhIssues('owner/repo').create_issue('2026-01-02', '')
    message = str(caught.value)
    assert 'exit code 1' in message
    assert 'other-secret' not in message and 'user:pass' not in message
    if not stderr:
        assert 'no stderr supplied' in message
