"""Runner failure regressions; fictional JSON, local temp archives, no network."""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest

from job_watcher.fetch import fetch_source
from job_watcher.history import build_history
from job_watcher.pipeline import run_pipeline
from job_watcher.raw import as_snapshot, read_raw
from job_watcher.sources import PRIMARY_SOURCES, DROPPED_SOURCES

# Excluded Walmart remains a malformed-row regression case, not production.
SOURCES = {s.key: s for s in PRIMARY_SOURCES + DROPPED_SOURCES}
SOURCE = SOURCES['pnc']
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


class Transport:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        assert self.pages, 'unexpected request (including detail call)'
        return deepcopy(self.pages.pop(0))


def job(key, *, malformed=False):
    result = {'bulletFields': [key], 'title': 'Finance Analyst', 'locationsText': 'Test City',
              'externalPath': f'/job/Test-City/Finance-Analyst_{key}'}
    if malformed:
        del result['externalPath']
    return result


def body(*jobs):
    return {'total': len(jobs), 'jobPostings': list(jobs)}


def fetched(*jobs, source=SOURCE, when=NOW):
    return fetch_source(source, Transport(body(*jobs)), fetched_at=when)


@pytest.mark.parametrize('key', ['walmart', 'bank_of_america', 'pnc'])
@pytest.mark.parametrize('number_bad', [1, 3])
def test_malformed_rows_do_not_discard_valid_postings(key, number_bad):
    notes = []
    transport = Transport(body(job('VALID'), *(job(f'BAD{i}', malformed=True) for i in range(number_bad))), body())
    result = fetch_source(SOURCES[key], transport, fetched_at=NOW, progress=notes.append)
    assert result.ok and result.raw['complete']
    assert result.count == number_bad + 1
    assert [p.source_id for p in result.postings] == ['VALID']
    assert result.diagnostics['skipped_malformed'] == number_bad
    assert len(transport.calls) <= 2
    assert all(args[0] == 'POST' and args[1] == SOURCES[key].endpoint for args, _ in transport.calls)
    assert any(f'skipped {number_bad} malformed' in note for note in notes)


def test_all_malformed_rows_fail_instead_of_successful_empty_snapshot():
    result = fetched(job('BAD1', malformed=True), job('BAD2', malformed=True))
    assert not result.ok and result.failure_class == 'malformed_postings'
    assert result.diagnostics['skipped_malformed'] == 2
    assert not result.raw['complete'] and not result.postings


def public_job_url(source, path):
    site = source.endpoint.split('/wday/cxs/')[1].split('/')[1]
    return f'https://{urlsplit(source.endpoint).hostname}/{site}{path}'


def test_literal_response_job_url_can_supply_supported_path():
    row = job('REAL', malformed=True)
    row['externalUrl'] = public_job_url(SOURCE, '/job/Test-City/Finance-Analyst_REAL')
    result = fetched(row)
    assert result.ok and result.diagnostics['skipped_malformed'] == 0
    assert result.postings[0].url == row['externalUrl']
    assert result.postings[0].source_id == 'REAL'


@pytest.mark.parametrize('path', [None, '', '/login', '//evil.test/job/REAL', '/job/../login', '/job/Test/REAL?auth=1'])
def test_no_url_is_invented_from_requisition_or_title(path):
    row = job('BAD', malformed=True)
    row['externalPath'] = path
    result = fetched(job('VALID'), row)
    assert result.ok and [p.source_id for p in result.postings] == ['VALID']
    assert result.diagnostics['unresolved_source_ids'] == ['BAD']


@pytest.mark.parametrize('url', ['https://other.test/job/REAL', 'https://pnc.wd5.myworkdayjobs.com/login',
                                'https://user:secret@example.test/job/REAL'])
def test_response_url_outside_configured_board_is_not_used(url):
    row = job('BAD', malformed=True)
    row['externalUrl'] = url
    result = fetched(job('VALID'), row)
    assert result.ok and len(result.postings) == 1
    assert result.diagnostics['skipped_malformed'] == 1


def test_missing_stable_id_never_creates_a_synthetic_posting():
    row = job('BAD')
    del row['bulletFields']
    result = fetched(job('VALID'), row)
    assert result.ok and [p.source_id for p in result.postings] == ['VALID']
    assert not result.diagnostics['removals_safe']
    assert result.diagnostics['unidentified_malformed'] == 1


def test_malformed_url_preserves_known_history_from_raw_alone():
    first = fetched(job('VALID'), job('BAD'), when=datetime(2026, 11, 13, tzinfo=timezone.utc))
    second = fetched(job('VALID'), job('BAD', malformed=True))
    # Derive safety evidence from actual raw rows, even if stored diagnostics are absent/incorrect.
    second.raw['diagnostics'] = {}
    rows = build_history([as_snapshot(first.raw), as_snapshot(second.raw)])
    assert len(rows) == 2 and all(r.status == 'open' for r in rows)
    assert all(r.last_seen == '2026-11-14' for r in rows)
    assert all(r.first_seen == '2026-11-13' for r in rows)


def test_unidentified_malformed_row_conservatively_blocks_false_removal():
    first = fetched(job('VALID'), job('PREVIOUS'), when=datetime(2026, 11, 13, tzinfo=timezone.utc))
    bad = job('BAD', malformed=True)
    del bad['bulletFields']
    second = fetched(job('VALID'), bad)
    rows = build_history([as_snapshot(first.raw), as_snapshot(second.raw)])
    previous = next(r for r in rows if r.source_id == 'PREVIOUS')
    assert previous.status == 'open' and previous.last_seen == '2026-11-13'
    assert len(rows) == 2


def test_new_malformed_posting_does_not_create_incomplete_history_row():
    first = fetched(job('VALID'), job('LATER', malformed=True), when=datetime(2026, 11, 13, tzinfo=timezone.utc))
    assert len(build_history([as_snapshot(first.raw)])) == 1
    second = fetched(job('VALID'), job('LATER'))
    row = next(r for r in build_history([as_snapshot(first.raw), as_snapshot(second.raw)]) if r.source_id == 'LATER')
    assert row.first_seen == '2026-11-13' and row.first_run


def test_ambiguous_posting_suffix_does_not_cause_false_removal():
    first = fetched(job('VALID'), job('REQ-1'), when=datetime(2026, 11, 13, tzinfo=timezone.utc))
    second = fetched(job('VALID'), job('REQ', malformed=True))
    row = next(r for r in build_history([as_snapshot(first.raw), as_snapshot(second.raw)]) if r.source_id == 'REQ-1')
    assert row.status == 'open' and row.last_seen == '2026-11-13'


def test_same_day_rerun_removes_failed_stale_file_and_reports_class(tmp_path):
    a, b = SOURCES['pnc'], SOURCES['bank_of_america']
    def run(fail_b):
        def fetch(source, **kwargs):
            jobs = [job('VALID')]
            if source == b and fail_b:
                jobs = [job('BAD', malformed=True)]
            return fetched(*jobs, source=source, when=kwargs['fetched_at'])
        return run_pipeline(tmp_path, sources=(a, b), started_at=NOW, fetcher=fetch, progress=notes.append)
    notes = []
    run(False)
    stale = tmp_path / 'raw/2026-11-14/bank_of_america.json.gz'
    assert stale.exists()
    rerun = run(True)
    assert not stale.exists()
    assert rerun.status['days_with_success'] == 1 and rerun.issue_title == '2026-11-14'
    assert rerun.status['sources'][1] == {'name': 'bank_of_america', 'ok': False, 'count': 0}
    assert any('bank_of_america: FAIL malformed_postings' in note for note in notes)
    assert all(row.status == 'open' for row in rerun.history)
    assert 'No removed postings.' in rerun.issue_body
    assert read_raw(tmp_path / 'raw/2026-11-14/pnc.json.gz')['complete']


def test_successful_skips_are_preserved_in_raw_and_pipeline_diagnostics(tmp_path):
    notes = []
    def fetch(source, **kwargs):
        return fetched(job('VALID'), job('BAD', malformed=True), source=source, when=kwargs['fetched_at'])
    result = run_pipeline(tmp_path, sources=(SOURCE,), started_at=NOW, fetcher=fetch, progress=notes.append)
    assert result.outcomes[0].skipped_malformed == 1
    assert result.outcomes[0].raw_count == 2 and result.outcomes[0].count == 1
    assert any('pnc: OK raw=2 normalized=1 skipped_malformed=1' in line for line in notes)
    raw = read_raw(tmp_path / 'raw/2026-11-14/pnc.json.gz')
    assert len(raw['pages'][0]['response']['jobPostings']) == 2
    assert as_snapshot(raw).unresolved_source_ids == ('BAD',)
    assert [r.source_id for r in result.history] == ['VALID']


def test_response_url_for_another_job_is_not_attached_to_valid_path():
    row = job('VALID')
    row['externalUrl'] = public_job_url(SOURCE, '/job/Other/Wrong-Posting_OTHER')
    result = fetched(row)
    assert result.ok and result.postings[0].url == public_job_url(SOURCE, row['externalPath'])
