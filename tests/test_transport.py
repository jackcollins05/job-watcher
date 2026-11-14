"""curl transport tests mock subprocesses: no sockets, DNS or real curl calls."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from job_watcher.adapters.base import AdapterError, JsonTransport
from job_watcher.fetch import fetch_source, main
from job_watcher.sources import PRIMARY_SOURCES

SOURCES = {source.key: source for source in PRIMARY_SOURCES}


class Runner:
    def __init__(self, *events):
        self.events = list(events)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if not self.events:
            raise AssertionError("unexpected curl attempt")
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        code, status, mime, body, retry_after = event
        Path(command[command.index('--output') + 1]).write_bytes(body)
        headers = f'HTTP/1.1 {status} Fixture\r\n'
        if retry_after is not None:
            headers += f'Retry-After: {retry_after}\r\n'
        Path(command[command.index('--dump-header') + 1]).write_text(headers + '\r\n')
        return subprocess.CompletedProcess(command, code,
            f'{status:03d}\n{mime}\n{command[-1]}', 'fixture stderr (never logged)')


def response(body=b'{"jobs": []}', *, status=200, code=0,
             mime='application/json', retry_after=None):
    return code, status, mime, body, retry_after


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr('job_watcher.adapters.base.time.sleep', lambda seconds: None)
    return JsonTransport()


def install(monkeypatch, *events):
    runner = Runner(*events)
    monkeypatch.setattr('job_watcher.adapters.base.subprocess.run', runner)
    return runner


def test_workday_matches_audit_json_post_and_deadlines(transport, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'https://fixture-user:fixture-secret@example.test')
    runner = install(monkeypatch, response())
    payload = {'appliedFacets': {}, 'limit': 2, 'offset': 0, 'searchText': ''}
    endpoint = SOURCES['tyson_foods'].endpoint
    assert transport.request('POST', endpoint, payload=payload) == {'jobs': []}
    command, kwargs = runner.calls[0]
    assert command[:2] == ['curl', '-q']
    assert command[-1] == endpoint
    assert command[command.index('--request') + 1] == 'POST'
    assert command[command.index('--data') + 1] == json.dumps(payload)
    headers = [command[i+1] for i, value in enumerate(command) if value == '--header']
    assert headers == ['Accept: application/json', 'Content-Type: application/json']
    assert command[command.index('--connect-timeout') + 1] == '8'
    assert command[command.index('--max-time') + 1] == '20'
    assert command[command.index('--retry') + 1] == '0'
    assert kwargs['timeout'] == 23 and kwargs['check'] is False
    assert kwargs['capture_output'] and kwargs['text']
    assert 'shell' not in kwargs
    assert 'HTTPS_PROXY' not in kwargs['env']
    assert 'HOME' not in kwargs['env']
    assert command[command.index('--user-agent') + 1].startswith('JobWatcher/')
    assert not {'--location', '-L', '--compressed', '--cookie', '--netrc', '--user'} & set(command)


def test_get_query_json_charset_and_no_post_body(transport, monkeypatch):
    runner = install(monkeypatch, response(mime='application/json; charset=utf-8'))
    transport.request('GET', 'https://example.test/jobs', params={'keyword': 'analyst'})
    command, _ = runner.calls[0]
    assert command[-1] == 'https://example.test/jobs?keyword=analyst'
    assert '--data' not in command and command[command.index('--request') + 1] == 'GET'


@pytest.mark.parametrize('event', [response(b'<html>fixture</html>', mime='text/html'),
    response(b'broken'), response(b'{"errorCode":"denied"}')])
def test_non_json_invalid_json_and_error_envelopes_fail(transport, monkeypatch, event):
    runner = install(monkeypatch, event)
    with pytest.raises(AdapterError):
        transport.request('GET', 'https://example.test/jobs')
    assert len(runner.calls) == 1


def test_one_transient_retry(transport, monkeypatch):
    runner = install(monkeypatch, response(status=503, retry_after='0'), response())
    transport.request('GET', 'https://example.test/jobs')
    assert len(runner.calls) == 2


@pytest.mark.parametrize('events', [(response(status=404),),
    (response(status=302),), (response(status=429, retry_after='3600'),),
    (response(status=503, retry_after='0'), response(status=503, retry_after='0'))])
def test_bounded_or_deferred_http_errors(transport, monkeypatch, events):
    runner = install(monkeypatch, *events)
    with pytest.raises(AdapterError, match='HTTP'):
        transport.request('GET', 'https://example.test/jobs')
    assert len(runner.calls) == len(events)


@pytest.mark.parametrize('events,reason', [
    ((response(code=28, status=0), response(code=28, status=0)), 'timed out'),
    ((subprocess.TimeoutExpired('curl', 23),), 'process deadline'),
    ((response(status=404),), 'HTTP 404'),
    ((response(b'malformed JSON'),), 'invalid JSON'),
    ((FileNotFoundError('curl unavailable'),), 'could not execute curl'),
])
def test_transport_failures_produce_controlled_fetch_result(transport, monkeypatch, events, reason):
    runner = install(monkeypatch, *events)
    result = fetch_source(SOURCES['tyson_foods'], transport)
    assert not result.ok and reason in result.error
    assert not result.postings and not result.raw['complete']
    assert len(runner.calls) == len(events)


def test_timeout_does_not_crash_subsequent_source(transport, monkeypatch):
    empty = json.dumps({'items': [{'TotalJobsCount': 0, 'Keyword': 'analyst',
                                  'Offset': 0, 'requisitionList': []}]}).encode()
    install(monkeypatch, subprocess.TimeoutExpired('curl', 23), response(empty))
    failed = fetch_source(SOURCES['tyson_foods'], transport)
    succeeded = fetch_source(SOURCES['jpmorgan_chase'], transport)
    assert not failed.ok and succeeded.ok and succeeded.count == 0


def test_request_budget_and_credentials_rejected_before_io(transport):
    transport.remaining = 0
    with pytest.raises(AdapterError, match='limit'):
        transport.request('GET', 'https://example.test/jobs')
    with pytest.raises(AdapterError, match='anonymous'):
        transport.request('GET', 'https://user:password@example.test/jobs')


def test_cli_progress_is_flushed_before_transport_starts(monkeypatch, capsys):
    import builtins
    printed = []
    original_print = builtins.print

    def checked_print(*args, **kwargs):
        printed.append((args, kwargs))
        original_print(*args, **kwargs)

    class EmptyTransport:
        def request(self, *args, **kwargs):
            assert capsys.readouterr().out == 'tyson_foods: fetching...\ntyson_foods: fetching page 1...\n'
            assert printed[0][1]['flush'] is True
            return {'total': 0, 'jobPostings': []}

    monkeypatch.setattr(builtins, 'print', checked_print)
    assert main(['--source', 'tyson_foods', '--dry-run'], transport_factory=EmptyTransport) == 0
    assert capsys.readouterr().out == ('tyson_foods: complete unique=0 reported_total=0\n'
                                       'tyson_foods: OK raw=0 normalized=0\n')
    assert printed[-1][1]['flush'] is True
