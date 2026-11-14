"""Approved production registry; source selection is checked without live IO."""
from datetime import datetime, timezone

import pytest

from job_watcher.adapters import adapter_for
from job_watcher.adapters.workday import WorkdayAdapter
from job_watcher.fetch import main
from job_watcher.pipeline import run_pipeline
from job_watcher.sources import PRIMARY_SOURCES, BACKUP_SOURCES, DROPPED_SOURCES

EXPECTED = (
    'tyson_foods', 'keybank', 'pepsico', 'jb_hunt', 'simmons_bank',
    'bank_of_america', 'jpmorgan_chase', 'wells_fargo', 'huntington_bank',
    'truist', 'pnc', 'us_bank', 'capital_one', 'fifth_third_bank', 'bmo',
)


def test_exact_approved_fifteen_and_no_remaining_backups():
    assert tuple(s.key for s in PRIMARY_SOURCES) == EXPECTED
    assert len(PRIMARY_SOURCES) == len(set(EXPECTED)) == 15
    assert not BACKUP_SOURCES
    citi = next(s for s in DROPPED_SOURCES if s.key == 'citi')
    assert citi.capped_total_risk and 'cap' in citi.notes
    huntington = next(s for s in PRIMARY_SOURCES if s.key == 'huntington_bank')
    assert huntington.endpoint == 'https://huntington.wd12.myworkdayjobs.com/wday/cxs/huntington/HNBcareers/jobs'
    assert isinstance(adapter_for(huntington), WorkdayAdapter)
    assert next(s for s in DROPPED_SOURCES if s.key == 'walmart').capped_total_risk
    assert not {'walmart', 'citi'} & {s.key for s in PRIMARY_SOURCES}
    keybank = next(s for s in PRIMARY_SOURCES if s.key == 'keybank')
    assert keybank.endpoint == 'https://keybank.wd5.myworkdayjobs.com/wday/cxs/keybank/External_Career_Site/jobs'
    assert isinstance(adapter_for(keybank), WorkdayAdapter)


@pytest.mark.parametrize('source', PRIMARY_SOURCES, ids=lambda s: s.key)
def test_every_current_primary_has_config_and_adapter(source):
    assert source.endpoint.startswith('https://')
    assert source.method in ('GET', 'POST')
    adapter = adapter_for(source)
    assert callable(adapter.fetch) and callable(adapter.convert)


def test_default_pipeline_fetches_huntington_and_keybank_not_capped_boards(tmp_path):
    attempted = []
    def failed(source, **kwargs):
        attempted.append(source.key)
        raise RuntimeError('offline fixture')
    result = run_pipeline(tmp_path, fetcher=failed,
                          started_at=datetime(2026, 11, 14, tzinfo=timezone.utc))
    assert tuple(attempted) == EXPECTED
    assert tuple(s['name'] for s in result.status['sources']) == EXPECTED
    assert len(result.outcomes) == 15


@pytest.mark.parametrize('source_key', ['huntington_bank', 'keybank'])
def test_cli_accepts_promoted_sources_and_rejects_excluded_sources(capsys, source_key):
    class Empty:
        def request(self, method, url, **kwargs):
            assert source_key.split('_')[0] in url and method == 'POST'
            return {'total': 0, 'jobPostings': []}
    assert main(['--source', source_key, '--dry-run'], transport_factory=Empty) == 0
    assert f'{source_key}: OK raw=0 normalized=0' in capsys.readouterr().out
    for key in ('citi', 'walmart'):
        with pytest.raises(SystemExit) as exc:
            main(['--source', key, '--dry-run'], transport_factory=Empty)
        assert exc.value.code == 2
