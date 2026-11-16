"""Small fictional fixtures follow the audited layouts; no audit file needed."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from job_watcher.adapters import adapter_for
from job_watcher.adapters.base import AdapterError, normalized_date
from job_watcher.adapters.workday import WORKDAY_PAGE_SIZE, WorkdayAdapter
from job_watcher.adapters.oracle import ORACLE_PAGE_SIZE, OracleAdapter, drift_tolerance
from job_watcher.adapters.jibe import JIBE_PAGE_SIZE, JibeAdapter
from job_watcher.fetch import fetch_source, main
from job_watcher.raw import as_snapshot, convert_raw, envelope, read_raw, write_raw
from job_watcher.schema import posting_id
from job_watcher.sources import PRIMARY_SOURCES, DROPPED_SOURCES

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "adapters.json").read_text())
NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
SOURCES = {s.key: s for s in PRIMARY_SOURCES}
# Retain cap regressions for excluded Citi without treating it as production.
CAP_SOURCES = {s.key: s for s in PRIMARY_SOURCES + DROPPED_SOURCES}


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, deepcopy(kwargs)))
        if not self.responses:
            raise AssertionError("unexpected extra request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)


def fixture(name):
    return deepcopy(FIXTURES[name])


def page(source, kind, body, path="/job/Chicago/Finance-Analyst_REQ001"):
    url = source.endpoint if kind == "list" else source.endpoint.removesuffix("/jobs") + path
    return {"kind": kind, "request": {"method": "GET", "url": url,
            "params": None, "payload": None}, "response": body}


def sample_pages(source):
    if source.platform == "Workday CXS":
        return [page(source, "list", fixture("workday_list"))]
    if source.platform == "Oracle Recruiting CE":
        return [page(source, "list", fixture("oracle_list"))]
    return [page(source, "list", fixture("jibe_list"))]


@pytest.mark.parametrize("source", PRIMARY_SOURCES, ids=lambda s: s.key)
def test_every_primary_conversion_all_ten_fields(source):
    raw = envelope(source, NOW, sample_pages(source), complete=True)
    row, = convert_raw(raw)
    if source.platform == "Workday CXS":
        key, location, department = "REQ001", "2 Locations", ""
    elif source.platform == "Oracle Recruiting CE":
        key, location, department = "210001", "Chicago", "Analysts"
    else:
        key, location, department = "6:REQ001:en-us", "Chicago", "Finance"
    url = ("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210001"
           if source.platform == "Oracle Recruiting CE" else "https://example.test/jobs/REQ001")
    if source.platform == "Workday CXS":
        host = source.endpoint.split("/wday/cxs/")[0]
        site = source.endpoint.split("/wday/cxs/")[1].split("/")[1]
        url = host + "/" + site + "/job/Chicago/Finance-Analyst_REQ001"
    assert asdict(row) == dict(posting_id=posting_id(source.key, key), source=source.key,
                              source_id=key, employer=source.employer, title="Finance Analyst",
                              location=location, department=department, posted_date="" if source.platform == "Workday CXS" else "2026-11-01",
                              url=url, in_role=True)
    snap = as_snapshot(raw)
    assert snap.source == source.key and snap.date == "2026-11-02" and snap.ok
    assert snap.postings[0].source_id == key


@pytest.mark.parametrize("source", PRIMARY_SOURCES, ids=lambda s: s.key)
def test_every_primary_missing_optional_fields_and_false_title(source):
    pages = sample_pages(source)
    if source.platform == "Workday CXS":
        job = pages[0]["response"]["jobPostings"][0]
        job.pop("postedOn")
        job["title"] = "Data Analyst"
    elif source.platform == "Oracle Recruiting CE":
        job = pages[0]["response"]["items"][0]["requisitionList"][0]
        for key in ("PostedDate", "JobFamily", "JobFunction"):
            job.pop(key)
        job["Title"] = "Data Analyst"
    else:
        job = pages[0]["response"]["jobs"][0]["data"]
        job.pop("posted_date")
        job.pop("categories")
        job.pop("category")
        job["title"] = "Data Analyst"
    row, = adapter_for(source).convert(source, pages)
    assert row.department == row.posted_date == "" and not row.in_role


@pytest.mark.parametrize("key", ["tyson_foods", "jpmorgan_chase", "pepsico"])
@pytest.mark.parametrize("bad", [{}, {"errorCode": "FAILED"}, [], {"jobs": None}])
def test_malformed_responses_are_controlled_failures(key, bad):
    result = fetch_source(SOURCES[key], FakeTransport(bad), fetched_at=NOW)
    assert not result.ok and result.error and not result.postings
    assert result.raw["complete"] is False
    with pytest.raises(AdapterError):
        convert_raw(result.raw)


def test_workday_pagination_zero_later_total_without_detail_calls():
    source = SOURCES["tyson_foods"]
    first = fixture("workday_list")
    first["total"] = 2
    second = fixture("workday_list")
    second["total"] = 0
    second["jobPostings"][0]["externalPath"] = "/job/Dallas/Finance-Analyst_REQ002"
    empty = {"total": 0, "jobPostings": []}
    second["jobPostings"][0]["bulletFields"] = ["REQ002"]
    fake = FakeTransport(first, second, empty)
    result = fetch_source(source, fake, fetched_at=NOW)
    assert result.ok and result.count == len(result.postings) == 2
    assert [c[2]["payload"]["offset"] for c in fake.calls] == [0, WORKDAY_PAGE_SIZE]
    assert [c[0] for c in fake.calls] == ["POST"] * 2
    assert convert_raw(result.raw) == result.postings


@pytest.mark.parametrize("key", ["walmart", "citi"])
def test_capped_boards_fail_instead_of_claiming_complete(key):
    first = fixture("workday_list")
    first["total"] = 2000
    first["jobPostings"] = []
    result = fetch_source(CAP_SOURCES[key], FakeTransport(first), fetched_at=NOW)
    assert not result.ok and "incomplete" in result.error
    # Simulate arrival at the advertised cap without hundreds of fixture rows.
    first = workday_batch(0, 2000, 2000)
    result = fetch_source(CAP_SOURCES[key], FakeTransport(first, {"total": 0, "jobPostings": []}), fetched_at=NOW)
    assert not result.ok and result.failure_class == "board_cap_unresolved"


def test_repeat_pages_and_max_pages_fail_not_truncate():
    first = fixture("workday_list")
    first["total"] = 2
    result = fetch_source(SOURCES["tyson_foods"], FakeTransport(first, first), fetched_at=NOW)
    assert not result.ok and "repeated" in result.error
    result = fetch_source(SOURCES["tyson_foods"], FakeTransport(first), fetched_at=NOW, page_safety_limit=1)
    assert not result.ok and "safety limit" in result.error


def test_oracle_pagination_uses_analyst_on_every_page():
    first = fixture("oracle_list")
    first["items"][0]["TotalJobsCount"] = 2
    first["items"][0]["Limit"] = 1
    second = deepcopy(first)
    second["items"][0]["Offset"] = 1
    second["items"][0]["requisitionList"][0]["Id"] = "210002"
    fake = FakeTransport(first, second)
    result = fetch_source(SOURCES["jpmorgan_chase"], fake, fetched_at=NOW)
    assert result.ok and result.count == 2
    for i, call in enumerate(fake.calls):
        assert call[0] == "GET"
        assert call[2]["params"]["finder"] == f"findReqs;siteNumber=CX_1001,limit={ORACLE_PAGE_SIZE},offset={i},keyword=analyst"
    forbidden = replace(SOURCES["jpmorgan_chase"], search_term="")
    fake = FakeTransport()
    assert not fetch_source(forbidden, fake, fetched_at=NOW).ok and not fake.calls


@pytest.mark.parametrize("key,empty", [
    ("tyson_foods", {"total": 0, "jobPostings": []}),
    ("jpmorgan_chase", {"items": [{"TotalJobsCount": 0, "Keyword": "analyst", "Offset": 0, "requisitionList": []}]}),
    ("pepsico", {"totalCount": 0, "jobs": []}),
])
def test_valid_empty_source(key, empty):
    result = fetch_source(SOURCES[key], FakeTransport(empty), fetched_at=NOW)
    assert result.ok and result.count == 0 and result.postings == []


def test_pepsico_default_requires_validation_and_opt_in_aggregates():
    source = SOURCES["pepsico"]
    first = jibe_batch(0, 20, 40)
    result = fetch_source(source, FakeTransport(first), fetched_at=NOW)
    assert not result.ok and "unvalidated" in result.error
    second = jibe_batch(20, 20, 40)
    fake = FakeTransport(first, second)
    result = fetch_source(source, fake, fetched_at=NOW, validate_pepsico_pagination=True)
    assert result.ok and result.count == 40
    assert [c[2]["params"]["page"] for c in fake.calls] == [1, 2]
    result = fetch_source(source, FakeTransport(first, first), fetched_at=NOW, validate_pepsico_pagination=True)
    assert not result.ok and "repeated" in result.error


def test_pepsico_language_identity_and_apply_fallback():
    source = SOURCES["pepsico"]
    payload = fixture("jibe_list")
    job = payload["jobs"][0]["data"]
    job.pop("meta_data")
    job.pop("full_location")
    row, = adapter_for(source).convert(source, [page(source, "list", payload)])
    assert row.url.endswith("/login") and row.location == "Chicago, Illinois, United States"
    other = deepcopy(job)
    other["language"] = "pt-br"
    payload["jobs"].append({"data": other})
    rows = adapter_for(source).convert(source, [page(source, "list", payload)])
    assert len({r.source_id for r in rows}) == 2


def test_workday_missing_stable_id_fails_without_inventing_id():
    source = SOURCES["tyson_foods"]
    pages = sample_pages(source)
    del pages[0]["response"]["jobPostings"][0]["bulletFields"]
    with pytest.raises(AdapterError, match="stable source ID"):
        adapter_for(source).convert(source, pages)


def test_network_failure_preserves_partial_pages_and_no_authoritative_postings():
    first = fixture("workday_list")
    first["total"] = 2
    result = fetch_source(SOURCES["tyson_foods"], FakeTransport(first, AdapterError("HTTP 503")), fetched_at=NOW)
    assert not result.ok and result.count == 1 and result.postings == []
    assert len(result.raw["pages"]) == 1 and "503" in result.error


def test_raw_gzip_roundtrip_deterministic_rebuild_and_no_overwrite(tmp_path):
    raw = envelope(SOURCES["tyson_foods"], NOW, sample_pages(SOURCES["tyson_foods"]), complete=True)
    a = write_raw(raw, tmp_path / "a")
    b = write_raw(raw, tmp_path / "b")
    assert a.relative_to(tmp_path / "a").as_posix() == "2026-11-02/tyson_foods.json.gz"
    assert a.read_bytes() == b.read_bytes()
    loaded = read_raw(a)
    assert loaded == raw and convert_raw(loaded) == convert_raw(raw)
    with pytest.raises(FileExistsError):
        write_raw(raw, tmp_path / "a")


def test_raw_failure_or_secret_cannot_write(tmp_path):
    source = SOURCES["tyson_foods"]
    raw = envelope(source, NOW, sample_pages(source), complete=False)
    with pytest.raises(AdapterError):
        write_raw(raw, tmp_path)
    raw["complete"] = True
    raw["pages"][0]["response"]["access_token"] = "fictional-test-token"
    with pytest.raises(AdapterError, match="authentication"):
        write_raw(raw, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value,expected", [(None, ""), ("Posted Today", ""), ("2026-11-01", "2026-11-01"),
    ("2026-11-01T23:00:00-0600", "2026-11-02"), ("not-a-date", "")])
def test_dates(value, expected):
    assert normalized_date(value) == expected


def test_cli_all_continues_after_failure_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    status = main(["--all", "--dry-run"], transport_factory=lambda: FakeTransport(AdapterError("fixture failure")))
    assert status == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 45
    assert all("fetching..." in line for line in lines[::3])
    assert all(": FAIL " in line for line in lines[2::3])
    assert list(tmp_path.iterdir()) == []


def test_cli_requires_dry_run():
    with pytest.raises(SystemExit):
        main(["--all"])


@pytest.mark.parametrize("limit", [1, 2])
def test_manual_page_budget_is_truncated_and_cannot_write_snapshot(limit, tmp_path):
    responses = []
    for i in range(limit):
        body = fixture("workday_list")
        body["total"] = 100 if i == 0 else 0
        job = body["jobPostings"][0]
        job["externalPath"] = f"/job/Chicago/Finance-Analyst_REQ00{i}"
        job["bulletFields"] = [f"REQ00{i}"]
        responses.append(body)
    fake = FakeTransport(*responses)
    progress = []
    result = fetch_source(SOURCES["tyson_foods"], fake, fetched_at=NOW,
                          dry_run=True, max_pages=limit, progress=progress.append)
    assert result.ok and result.truncated and result.count == len(result.postings) == limit
    assert len(fake.calls) == limit and all(c[0] == "POST" for c in fake.calls)
    assert all(c[2]["payload"]["limit"] == WORKDAY_PAGE_SIZE for c in fake.calls)
    assert progress == [f"fetching page {i}..." for i in range(1, limit + 1)]
    assert result.raw["complete"] is False and result.raw["smoke_truncated"]
    with pytest.raises(AdapterError):
        write_raw(result.raw, tmp_path)
    with pytest.raises(AdapterError):
        as_snapshot(result.raw)
    assert list(tmp_path.iterdir()) == []


def test_production_rejects_manual_page_limit_before_requests():
    fake = FakeTransport()
    with pytest.raises(ValueError, match="manual dry-run"):
        fetch_source(SOURCES["tyson_foods"], fake, max_pages=1)
    assert fake.calls == []


def test_no_limit_dry_run_fetches_all_pages():
    first = fixture("workday_list")
    first["total"] = 2
    second = fixture("workday_list")
    second["jobPostings"][0]["externalPath"] = "/job/Dallas/Finance-Analyst_REQ002"
    second["jobPostings"][0]["bulletFields"] = ["REQ002"]
    fake = FakeTransport(first, second, {"total": 0, "jobPostings": []})
    result = fetch_source(SOURCES["tyson_foods"], fake, dry_run=True)
    assert result.ok and not result.truncated and result.raw["complete"]
    assert len(fake.calls) == 2 and len(result.postings) == 2


def test_cli_one_page_labels_truncation_and_progress(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    first = fixture("workday_list")
    first["total"] = 735
    fake = FakeTransport(first)
    code = main(["--source", "tyson_foods", "--dry-run", "--max-pages", "1"],
                transport_factory=lambda: fake)
    output = capsys.readouterr().out
    assert code == 0 and len(fake.calls) == 1
    assert output.splitlines()[:2] == ["tyson_foods: fetching...", "tyson_foods: fetching page 1..."]
    assert "TRUNCATED (dry-run) raw=1 normalized=1; not a complete snapshot" in output
    assert "page 2" not in output and "detail" not in output
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", ["0", "-1", "bad"])
def test_cli_rejects_invalid_max_pages(value):
    with pytest.raises(SystemExit):
        main(["--source", "tyson_foods", "--dry-run", "--max-pages", value])


def test_workday_preserves_real_posting_suffix_and_id_on_title_change():
    source = SOURCES["tyson_foods"]
    body = fixture("workday_list")
    job = body["jobPostings"][0]
    job["externalPath"] += "-1"
    duplicate_req = deepcopy(job)
    duplicate_req["externalPath"] = "/job/Elsewhere/New-Slug_REQ001-2"
    body["jobPostings"].append(duplicate_req)
    rows = adapter_for(source).convert(source, [page(source, "list", body)])
    assert [r.source_id for r in rows] == ["REQ001-1", "REQ001-2"]
    job["title"] = "Senior Finance Analyst"
    job["externalPath"] = "/job/Elsewhere/Renamed-Slug_REQ001-1"
    changed = adapter_for(source).convert(source, [page(source, "list", body)])
    assert [r.posting_id for r in changed] == [r.posting_id for r in rows]


def test_workday_optional_saved_detail_is_not_required_for_identity():
    source = SOURCES["tyson_foods"]
    pages = sample_pages(source)
    without, = adapter_for(source).convert(source, pages)
    pages.append(page(source, "detail", fixture("workday_detail")))
    enriched, = adapter_for(source).convert(source, pages)
    assert enriched.source_id == without.source_id == "REQ001"
    assert without.posted_date == "" and enriched.posted_date == "2026-11-01"
    assert without.location == "2 Locations" and enriched.location == "Chicago; Dallas"


def test_invalid_page_in_smoke_test_is_failure_not_successful_truncation():
    body = fixture("workday_list")
    del body["jobPostings"][0]["title"]
    result = fetch_source(SOURCES["tyson_foods"], FakeTransport(body), dry_run=True, max_pages=1)
    assert not result.ok and not result.truncated and "title" in result.error


def workday_batch(start, size, total):
    body = fixture("workday_list")
    template = body["jobPostings"][0]
    body["total"] = total
    body["jobPostings"] = []
    for i in range(start, start + size):
        job = deepcopy(template)
        job["externalPath"] = f"/job/Chicago/Finance-Analyst_REQ{i:04d}"
        job["bulletFields"] = [f"REQ{i:04d}"]
        body["jobPostings"].append(job)
    return body


def test_workday_production_page_size_is_twenty():
    assert WORKDAY_PAGE_SIZE == WorkdayAdapter.page_size == 20
    assert adapter_for(SOURCES["tyson_foods"]).page_size > 2


@pytest.mark.parametrize("page_size", [7, 20])
def test_workday_offsets_follow_configuration_and_stop_after_final_partial_page(monkeypatch, page_size):
    monkeypatch.setattr(WorkdayAdapter, "page_size", page_size)
    fake = FakeTransport(workday_batch(0, page_size, page_size + 3),
                         workday_batch(page_size, 3, 0),
                         {"total": 0, "jobPostings": []})
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert result.ok and not result.truncated and result.count == page_size + 3
    assert len(fake.calls) == 2
    assert [c[2]["payload"]["offset"] for c in fake.calls] == [0, page_size]
    assert all(c[2]["payload"]["limit"] == page_size for c in fake.calls)
    assert all(c[0] == "POST" and c[1].endswith("/jobs") for c in fake.calls)
    assert len(result.postings) == page_size + 3


def test_smoke_page_limit_does_not_change_workday_production_page_size():
    first = workday_batch(0, 20, 40)
    smoke_transport = FakeTransport(first)
    smoke = fetch_source(SOURCES["tyson_foods"], smoke_transport, dry_run=True, max_pages=1)
    assert smoke.ok and smoke.truncated and smoke.count == 20
    assert len(smoke_transport.calls) == 1
    assert smoke_transport.calls[0][2]["payload"]["limit"] == 20
    full_transport = FakeTransport(first, workday_batch(20, 20, 0))
    full = fetch_source(SOURCES["tyson_foods"], full_transport)
    assert full.ok and not full.truncated and full.raw["complete"]
    assert len(full_transport.calls) == 2
    assert all(c[2]["payload"]["limit"] == 20 for c in full_transport.calls)
    assert WorkdayAdapter.page_size == WORKDAY_PAGE_SIZE == 20


def test_unexpected_server_page_cap_fails_instead_of_silently_skipping_jobs():
    fake = FakeTransport(workday_batch(0, 2, 30), {"total": 0, "jobPostings": []})
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert not result.ok and "incomplete source" in result.error
    assert not result.raw["complete"] and not result.postings


@pytest.mark.parametrize("overlap", [1, 5])
def test_workday_mixed_duplicate_pages_succeed_and_preserve_all_unique_rows(overlap):
    first = workday_batch(0, 20, 25)
    second = workday_batch(20 - overlap, overlap + 5, 0)
    # Same stable ID with a changed slug must also deduplicate.
    second["jobPostings"][0]["externalPath"] = f"/job/Seattle/Renamed_REQ{20-overlap:04d}"
    fake = FakeTransport(first, second, {"total": 0, "jobPostings": []})
    progress = []
    result = fetch_source(SOURCES["tyson_foods"], fake, progress=progress.append)
    assert result.ok and not result.truncated
    assert result.count == 25 + overlap and len(result.postings) == 25
    assert [p.source_id for p in result.postings] == [f"REQ{i:04d}" for i in range(25)]
    assert convert_raw(result.raw) == result.postings
    assert len(result.raw["pages"][1]["response"]["jobPostings"]) == overlap + 5
    noun = "duplicate" if overlap == 1 else "duplicates"
    assert f"page 2 added 5 new, {overlap} {noun}" in progress
    assert sum("added" in message for message in progress) == 1
    assert [c[2]["payload"]["offset"] for c in fake.calls] == [0, 20]
    assert all(c[0] == "POST" and c[2]["payload"]["limit"] == 20 for c in fake.calls)


@pytest.mark.parametrize("reverse", [False, True])
def test_workday_exact_result_set_repeat_is_controlled_stall(reverse):
    first = workday_batch(0, 20, 60)
    repeated = deepcopy(first)
    if reverse:
        repeated["jobPostings"].reverse()
    fake = FakeTransport(first, repeated)
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert not result.ok and "pagination stalled" in result.error
    assert "repeated Workday page/result set" in result.error
    assert "unique=20, reported_total=60, offset=20, page_size=20" in result.error
    assert len(fake.calls) == 2 and result.count == 40
    assert not result.postings and not result.raw["complete"]


def test_workday_nonrepeated_page_with_zero_new_ids_is_controlled_stall():
    first = workday_batch(0, 2, 10)
    second = workday_batch(1, 2, 0)
    combined = workday_batch(0, 1, 0)
    combined["jobPostings"] += workday_batch(2, 1, 0)["jobPostings"]
    result = fetch_source(SOURCES["tyson_foods"], FakeTransport(first, second, combined))
    assert not result.ok and "zero new unique postings" in result.error
    assert not result.raw["complete"] and not result.postings


def test_workday_confirmed_total_stops_on_unique_count_not_raw_count():
    first = workday_batch(0, 20, 23)
    second = workday_batch(19, 4, 23)
    fake = FakeTransport(first, second)
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert result.ok and result.count == 24 and len(result.postings) == 23
    assert len(fake.calls) == 2  # No extra request after confirmed positive total.


def test_workday_conversion_deduplicates_inside_and_across_pages():
    source = SOURCES["tyson_foods"]
    first = workday_batch(0, 2, 3)
    first["jobPostings"].append(deepcopy(first["jobPostings"][0]))
    second = workday_batch(1, 2, 0)
    rows = adapter_for(source).convert(source, [page(source, "list", first), page(source, "list", second)])
    assert len(rows) == 3 and len({r.posting_id for r in rows}) == 3


def test_workday_overlap_smoke_result_stays_truncated_and_deduped():
    fake = FakeTransport(workday_batch(0, 20, 100), workday_batch(19, 20, 0))
    result = fetch_source(SOURCES["tyson_foods"], fake, dry_run=True, max_pages=2)
    assert result.ok and result.truncated and result.count == 40
    assert len(result.postings) == 39 and len(fake.calls) == 2
    assert not result.raw["complete"]


def test_workday_no_overlap_does_not_add_noisy_progress():
    fake = FakeTransport(workday_batch(0, 20, 25), workday_batch(20, 5, 0),
                         {"total": 0, "jobPostings": []})
    progress = []
    result = fetch_source(SOURCES["tyson_foods"], fake, progress=progress.append)
    assert result.ok
    assert progress[:2] == ["fetching page 1...", "fetching page 2..."]
    assert progress[-1].startswith("complete raw=25 unique=25 duplicates=0 reported_total=25")


@pytest.mark.parametrize("unused_boundary", ["repeat", "empty"])
def test_total_reached_exactly_does_not_fetch_boundary_page(unused_boundary):
    first = workday_batch(0, 20, 20)
    boundary = deepcopy(first) if unused_boundary == "repeat" else {"total": 0, "jobPostings": []}
    fake = FakeTransport(first, boundary)
    progress = []
    result = fetch_source(SOURCES["tyson_foods"], fake, progress=progress.append)
    assert result.ok and not result.truncated and result.raw["complete"]
    assert result.count == len(result.postings) == 20
    assert len(fake.calls) == 1 and len(fake.responses) == 1
    assert progress[-1].startswith("complete raw=20 unique=20 duplicates=0 reported_total=20")
    assert convert_raw(result.raw) == result.postings


def test_saved_tyson_total_with_later_zero_totals_completes_before_repeated_page():
    # Real saved response shape: total=735 at offset 0, then placeholder zeros.
    bodies = [workday_batch(start, min(20, 735 - start), 735 if start == 0 else 0)
              for start in range(0, 735, 20)]
    fake = FakeTransport(*bodies, deepcopy(bodies[0]))
    progress = []
    result = fetch_source(SOURCES["tyson_foods"], fake, progress=progress.append)
    assert result.ok and result.count == len(result.postings) == 735
    assert len({p.source_id for p in result.postings}) == 735
    assert len(fake.calls) == 37 and len(fake.responses) == 1
    assert progress[-1].startswith("complete raw=735 unique=735 duplicates=0 reported_total=735")
    assert fake.calls[-1][2]["payload"] == {
        "appliedFacets": {}, "limit": 20, "offset": 720, "searchText": ""}


def test_untrusted_zero_total_uses_normal_empty_page_completion():
    fake = FakeTransport(workday_batch(0, 2, 0), {"total": 0, "jobPostings": []})
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert result.ok and len(result.postings) == 2 and len(fake.calls) == 2


@pytest.mark.parametrize("key", ["walmart", "citi"])
def test_capped_total_reached_followed_by_repeat_is_not_success(key):
    first = workday_batch(0, 2000, 2000)
    fake = FakeTransport(first, deepcopy(first))
    result = fetch_source(CAP_SOURCES[key], fake)
    assert not result.ok and result.failure_class == "board_cap_unresolved"
    assert not result.raw["complete"] and result.postings == []
    assert len(fake.calls) == 2


def test_conflicting_positive_total_disables_early_completion():
    fake = FakeTransport(workday_batch(0, 20, 23), workday_batch(20, 3, 24),
                         workday_batch(23, 1, 0), {"total": 0, "jobPostings": []})
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert result.ok and len(result.postings) == 24 and len(fake.calls) == 3


def test_short_page_below_reported_total_is_not_completion():
    first = workday_batch(0, 3, 30)
    fake = FakeTransport(first, deepcopy(first))
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert not result.ok and "pagination stalled" in result.error
    assert len(fake.calls) == 2 and not result.raw["complete"]


def test_workday_raw_coverage_completes_with_fewer_unique_ids():
    first = workday_batch(0, 20, 40)
    second = workday_batch(18, 20, 40)
    fake = FakeTransport(first, second)
    progress = []
    result = fetch_source(SOURCES["tyson_foods"], fake, progress=progress.append)
    assert result.ok and result.count == 40 and len(result.postings) == 38
    assert len({p.posting_id for p in result.postings}) == 38
    assert len(fake.calls) == 2
    assert progress[-1].startswith("complete raw=40 unique=38 duplicates=2 reported_total=40")


def test_workday_duplicate_terminal_page_after_bounded_total_churn():
    first = workday_batch(0, 20, 40)
    second = workday_batch(20, 20, 42)
    repeated = deepcopy(second)
    fake = FakeTransport(first, second, repeated)
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert result.ok and result.count == 60 and len(result.postings) == 40
    assert len({p.posting_id for p in result.postings}) == 40


def test_workday_material_raw_shortfall_fails_after_expected_offsets():
    fake = FakeTransport(workday_batch(0, 20, 45), workday_batch(20, 20, 45),
                         workday_batch(40, 1, 45), {"total": 45, "jobPostings": []})
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert not result.ok and "raw result coverage" in result.error


def test_workday_large_total_drift_fails():
    fake = FakeTransport(workday_batch(0, 20, 40), workday_batch(20, 20, 50))
    result = fetch_source(SOURCES["tyson_foods"], fake)
    assert not result.ok and "total changed materially" in result.error


def oracle_batch(start, size, total, offset, limit=25, outer_has_more=False):
    body = fixture("oracle_list")
    root = body["items"][0]
    template = root["requisitionList"][0]
    root.update(TotalJobsCount=total, Offset=offset, Limit=limit)
    root["requisitionList"] = [dict(deepcopy(template), Id=f"21{i:04d}")
                               for i in range(start, start + size)]
    # These paginate ONE search-envelope item, as in the real saved response.
    body.update(count=1, hasMore=outer_has_more, offset=0, limit=200)
    return body


def test_oracle_production_page_size():
    assert OracleAdapter.page_size == ORACLE_PAGE_SIZE == 25
    assert adapter_for(SOURCES["jpmorgan_chase"]).page_size > 2


@pytest.mark.parametrize("overlap", [1, 5])
def test_oracle_mixed_duplicates_preserve_normalized_rows_and_progress(overlap):
    first = oracle_batch(0, 25, 30, 0)
    second = oracle_batch(25 - overlap, overlap + 5, 30, 25)
    fake = FakeTransport(first, second)
    progress = []
    result = fetch_source(SOURCES["jpmorgan_chase"], fake, progress=progress.append)
    assert result.ok and result.raw["complete"] and not result.truncated
    assert result.count == 30 + overlap and len(result.postings) == 30
    assert [p.source_id for p in result.postings] == [f"21{i:04d}" for i in range(30)]
    assert convert_raw(result.raw) == result.postings
    assert len(fake.calls) == 2
    assert all("keyword=analyst" in c[2]["params"]["finder"] for c in fake.calls)
    assert "limit=25,offset=0," in fake.calls[0][2]["params"]["finder"]
    assert "limit=25,offset=25," in fake.calls[1][2]["params"]["finder"]
    noun = "duplicate" if overlap == 1 else "duplicates"
    assert f"page 2 added 5 new, {overlap} {noun}" in progress
    assert progress[-1] == f"complete raw={30+overlap} unique=30 duplicates={overlap} reported_total=30 raw_drift={overlap}"


def test_oracle_zero_new_ids_before_total_is_controlled_stall():
    fake = FakeTransport(oracle_batch(0, 25, 75, 0), oracle_batch(0, 25, 75, 25))
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert not result.ok and "Oracle pagination stalled" in result.error
    assert "unique=25, reported_total=75, offset=25" in result.error
    assert result.postings == [] and not result.raw["complete"] and len(fake.calls) == 2


@pytest.mark.parametrize("outer_has_more", [False, True])
def test_oracle_total_completion_ignores_outer_envelope_has_more(outer_has_more):
    fake = FakeTransport(oracle_batch(0, 25, 50, 0, outer_has_more=outer_has_more),
                         oracle_batch(25, 25, 50, 25, outer_has_more=outer_has_more))
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert result.ok and len(result.postings) == 50 and len(fake.calls) == 2


def test_oracle_has_more_false_before_job_total_does_not_truncate():
    fake = FakeTransport(oracle_batch(0, 25, 100, 0))
    result = fetch_source(SOURCES["jpmorgan_chase"], fake, dry_run=True, max_pages=1)
    assert result.ok and result.truncated and not result.raw["complete"]
    assert len(result.postings) == 25 and len(fake.calls) == 1
    assert "limit=25" in fake.calls[0][2]["params"]["finder"]
    with pytest.raises(ValueError, match="manual dry-run"):
        fetch_source(SOURCES["jpmorgan_chase"], FakeTransport(), max_pages=1)


def test_oracle_offset_uses_inner_limit_when_server_negotiates_smaller_page():
    fake = FakeTransport(oracle_batch(0, 5, 7, 0, limit=5), oracle_batch(5, 2, 7, 5, limit=5))
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert result.ok and len(result.postings) == 7
    assert "limit=25,offset=5,keyword=analyst" in fake.calls[1][2]["params"]["finder"]


def test_oracle_empty_page_before_reported_total_is_failure():
    result = fetch_source(SOURCES["jpmorgan_chase"], FakeTransport(oracle_batch(0, 0, 25, 0)))
    assert not result.ok and "count mismatch" in result.error and not result.raw["complete"]


def test_oracle_changed_total_or_wrong_keyword_fails_safely():
    changed = fetch_source(SOURCES["jpmorgan_chase"],
                           FakeTransport(oracle_batch(0, 25, 50, 0), oracle_batch(25, 25, 53, 25)))
    assert not changed.ok and "total changed" in changed.error
    wrong = oracle_batch(0, 25, 50, 0)
    wrong["items"][0]["Keyword"] = None
    result = fetch_source(SOURCES["jpmorgan_chase"], FakeTransport(wrong))
    assert not result.ok and "configured keyword" in result.error


def oracle_churn_pages(unique_count, reported_total=1003):
    """All 41 offsets; distribute overlap without making any page stall."""
    pages = [oracle_batch(start, min(25, reported_total - start), reported_total, start)
             for start in range(0, reported_total, 25)]
    overlap = reported_total - unique_count
    for i in range(overlap):
        page_index = 1 + i % 39
        record_index = i // 39
        pages[page_index]["items"][0]["requisitionList"][record_index]["Id"] = "210000"
    return pages


@pytest.mark.parametrize("unique_count", [1003, 1002, 1001, 998, 995, 997, 850])
def test_oracle_complete_raw_traversal_deduplicates_and_retains_rows(unique_count):
    fake = FakeTransport(*oracle_churn_pages(unique_count))
    progress = []
    result = fetch_source(SOURCES["jpmorgan_chase"], fake, progress=progress.append)
    assert result.ok and result.raw["complete"] and not result.truncated
    assert len(result.postings) == len({p.source_id for p in result.postings}) == unique_count
    assert result.count == 1003
    assert len(fake.calls) == 41  # No extra empty/repeated page.
    for i, call in enumerate(fake.calls):
        assert call[2]["params"]["finder"] == f"findReqs;siteNumber=CX_1001,limit=25,offset={i * 25},keyword=analyst"
    assert progress[-1] == f"complete raw=1003 unique={unique_count} duplicates={1003-unique_count} reported_total=1003"
    assert convert_raw(result.raw) == result.postings


@pytest.mark.parametrize("raw_count", [997, 950])
def test_oracle_complete_traversal_rejects_material_raw_shortfall(raw_count):
    pages = oracle_churn_pages(1003)
    for i in range(1003 - raw_count):
        # Keep all pages nonempty and progressing, but lose real result rows.
        pages[i % 40]["items"][0]["requisitionList"].pop()
    fake = FakeTransport(*pages)
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert not result.ok and "count mismatch" in result.error
    assert f"raw={raw_count}" in result.error and "tolerance=5" in result.error
    assert result.count == raw_count and len(fake.calls) == 41
    assert not result.raw["complete"] and not result.postings


def test_oracle_close_count_does_not_complete_before_all_offsets():
    fake = FakeTransport(*oracle_churn_pages(1003)[:40])
    result = fetch_source(SOURCES["jpmorgan_chase"], fake, page_safety_limit=40)
    assert result.count == 1000  # Only 3 below expected, but final offset not fetched.
    assert not result.ok and "safety limit" in result.error and not result.raw["complete"]
    assert len(fake.calls) == 40 and result.postings == []


def test_oracle_close_count_does_not_excuse_last_request_failure():
    fake = FakeTransport(*oracle_churn_pages(1003)[:40], AdapterError("HTTP 503"))
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert not result.ok and "HTTP 503" in result.error and result.count == 1000
    assert not result.raw["complete"] and result.postings == []


def test_oracle_small_metadata_changes_keep_starting_total_as_target():
    pages = oracle_churn_pages(1002)
    for body in pages[20:]:
        body["items"][0]["TotalJobsCount"] = 1002
    fake = FakeTransport(*pages)
    progress = []
    result = fetch_source(SOURCES["jpmorgan_chase"], fake, progress=progress.append)
    assert result.ok and len(result.postings) == 1002 and len(fake.calls) == 41
    assert progress[-1] == "complete raw=1003 unique=1002 duplicates=1 reported_total=1003"


def test_oracle_tolerance_does_not_excuse_zero_progress_page():
    pages = oracle_churn_pages(1003)[:40]
    last = oracle_batch(0, 3, 1003, 1000)
    fake = FakeTransport(*pages, last)
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert not result.ok and "pagination stalled" in result.error
    assert result.count == 1003 and not result.raw["complete"] and not result.postings


@pytest.mark.parametrize("unique_count", [1002, 1001])
def test_oracle_removed_jobs_on_final_partial_page_reconcile(unique_count):
    pages = oracle_churn_pages(1003)
    pages[-1]["items"][0]["requisitionList"] = pages[-1]["items"][0]["requisitionList"][:unique_count - 1000]
    fake = FakeTransport(*pages)
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert result.ok and result.count == len(result.postings) == unique_count
    assert len(fake.calls) == 41 and result.raw["complete"]


def test_oracle_small_growth_is_also_reconciled_by_absolute_difference():
    pages = oracle_churn_pages(1003)
    pages[-1] = oracle_batch(1000, 4, 1004, 1000)
    progress = []
    result = fetch_source(SOURCES["jpmorgan_chase"], FakeTransport(*pages), progress=progress.append)
    assert result.ok and len(result.postings) == 1004
    assert progress[-1] == "complete raw=1004 unique=1004 duplicates=0 reported_total=1003 raw_drift=1"


@pytest.mark.parametrize("total,tolerance", [(0, 2), (100, 2), (400, 2), (1000, 5), (1003, 5), (1200, 6)])
def test_oracle_drift_tolerance_is_explicit_and_small(total, tolerance):
    assert drift_tolerance(total) == tolerance


def test_oracle_full_raw_rows_with_eight_duplicates_report_success_in_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake = FakeTransport(*oracle_churn_pages(995))
    code = main(["--source", "jpmorgan_chase", "--dry-run"], transport_factory=lambda: fake)
    lines = capsys.readouterr().out.splitlines()
    assert code == 0 and len(fake.calls) == 41
    assert lines[-2:] == [
        "jpmorgan_chase: complete raw=1003 unique=995 duplicates=8 reported_total=1003",
        "jpmorgan_chase: OK raw=1003 normalized=995",
    ]
    assert list(tmp_path.iterdir()) == []


def test_oracle_premature_empty_page_is_not_completed_raw_traversal():
    pages = oracle_churn_pages(1003)[:20]
    fake = FakeTransport(*pages, oracle_batch(0, 0, 1003, 500))
    result = fetch_source(SOURCES["jpmorgan_chase"], fake)
    assert not result.ok and result.count == 500
    assert "empty page before expected offsets covered" in result.error
    assert not result.raw["complete"] and not result.postings


def test_oracle_secondary_shortfall_tolerance_is_independent_of_duplicate_count():
    pages = oracle_churn_pages(996)
    pages[-1]["items"][0]["requisitionList"].pop()
    progress = []
    result = fetch_source(SOURCES["jpmorgan_chase"], FakeTransport(*pages), progress=progress.append)
    assert result.ok and result.count == 1002 and len(result.postings) == 995
    assert progress[-1] == "complete raw=1002 unique=995 duplicates=7 reported_total=1003 raw_drift=1"


def jibe_batch(start, size, total):
    body = fixture("jibe_list")
    template = body["jobs"][0]["data"]
    body["totalCount"] = total
    body["jobs"] = [{"data": dict(deepcopy(template), req_id=f"REQ{i:04d}", slug=f"REQ{i:04d}")}
                    for i in range(start, start + size)]
    return body


def test_pepsico_production_page_size_and_page_progression():
    assert JibeAdapter.page_size == JIBE_PAGE_SIZE == 20
    fake = FakeTransport(jibe_batch(0, 20, 40), jibe_batch(20, 20, 40))
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True)
    assert result.ok and len(result.postings) == 40
    assert [c[2]["params"] for c in fake.calls] == [
        {"lang": "en-us", "limit": 20, "page": 1},
        {"lang": "en-us", "limit": 20, "page": 2},
    ]
    assert all(c[0] == "GET" for c in fake.calls)


@pytest.mark.parametrize("start_total,end_total,size", [(40, 40, 20), (40, 41, 21), (40, 39, 19)])
def test_pepsico_unchanged_or_small_live_total_change_completes(start_total, end_total, size):
    bodies = [jibe_batch(0, 20, start_total), jibe_batch(20, min(size, 20), end_total)]
    if size > 20:
        bodies.append(jibe_batch(40, size - 20, end_total))
    fake = FakeTransport(*bodies)
    progress = []
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True, progress=progress.append)
    assert result.ok and result.raw["complete"] and len(result.postings) == result.count == end_total
    assert f"total_start={start_total} total_end={end_total}" in progress[-1]
    assert f"drift={end_total-start_total}" in progress[-1]
    assert f"total_min={min(start_total,end_total)} total_max={max(start_total,end_total)}" in progress[-1]


def test_pepsico_tracks_min_max_and_does_not_fail_on_change_alone():
    fake = FakeTransport(jibe_batch(0, 20, 40), jibe_batch(20, 20, 42), jibe_batch(40, 1, 41))
    progress = []
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True, progress=progress.append)
    assert result.ok and len(result.postings) == 41
    assert "total_start=40 total_end=41 total_min=40 total_max=42 pages=3 drift=1" in progress[-1]


@pytest.mark.parametrize("overlap", [1, 5])
def test_pepsico_overlaps_deduplicate_without_losing_new_postings(overlap):
    fake = FakeTransport(jibe_batch(0, 20, 30), jibe_batch(20-overlap, overlap+10, 30))
    progress = []
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True, progress=progress.append)
    assert result.ok and result.count == 30 + overlap and len(result.postings) == 30
    assert len({r.source_id for r in result.postings}) == 30
    assert convert_raw(result.raw) == result.postings
    assert f"duplicates={overlap}" in progress[-1]
    assert "page 2 added 10 new" in progress[2]


def test_pepsico_empty_terminal_page_can_confirm_small_raw_shortfall():
    fake = FakeTransport(jibe_batch(0, 20, 41), jibe_batch(20, 20, 41), jibe_batch(0, 0, 41))
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True)
    assert result.ok and len(fake.calls) == 3 and len(result.postings) == 40


@pytest.mark.parametrize("terminal_size", [0, 2])
def test_pepsico_materially_premature_end_fails(terminal_size):
    fake = FakeTransport(jibe_batch(0, 20, 100), jibe_batch(20, terminal_size, 100), jibe_batch(0, 0, 100))
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True)
    assert not result.ok and "incomplete source" in result.error
    assert not result.raw["complete"] and result.postings == []


@pytest.mark.parametrize("repeat", [True, False])
def test_pepsico_repeated_result_set_or_zero_new_ids_is_stall(repeat):
    first, second = jibe_batch(0, 20, 100), jibe_batch(20, 20, 100)
    third = deepcopy(first)
    if not repeat:
        third["jobs"] = first["jobs"][:10] + second["jobs"][:10]
    fake = FakeTransport(first, second, third)
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True)
    assert not result.ok and "stalled" in result.error and not result.postings


def test_pepsico_material_total_change_is_not_silently_accepted():
    fake = FakeTransport(jibe_batch(0, 20, 40), jibe_batch(20, 20, 70), jibe_batch(0, 0, 70))
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True)
    assert not result.ok and "metadata inconsistent" in result.error
    assert "total_start=40, total_end=70" in result.error


def test_pepsico_smoke_budget_is_independent_and_cannot_be_production_limit():
    fake = FakeTransport(jibe_batch(0, 20, 100), jibe_batch(20, 20, 101))
    result = fetch_source(SOURCES["pepsico"], fake, dry_run=True, max_pages=2,
                          validate_pepsico_pagination=True)
    assert result.ok and result.truncated and not result.raw["complete"]
    assert len(fake.calls) == 2 and all(c[2]["params"]["limit"] == 20 for c in fake.calls)
    assert JibeAdapter.page_size == 20
    with pytest.raises(ValueError, match="manual dry-run"):
        fetch_source(SOURCES["pepsico"], FakeTransport(), max_pages=1)


def test_pepsico_validation_flag_never_bypasses_end_checks_or_page_failures():
    fake = FakeTransport(jibe_batch(0, 20, 40), AdapterError("HTTP 503"))
    result = fetch_source(SOURCES["pepsico"], fake, validate_pepsico_pagination=True)
    assert not result.ok and "HTTP 503" in result.error and not result.raw["complete"]
    assert result.postings == []


def test_pepsico_language_scoped_count_cannot_replace_global_total():
    body = jibe_batch(0, 20, 100)
    body["count"] = 20
    fake = FakeTransport(body)
    result = fetch_source(SOURCES["pepsico"], fake, dry_run=True, max_pages=1,
                          validate_pepsico_pagination=True)
    assert result.ok and result.truncated and not result.raw["complete"]


def test_pepsico_cli_reports_live_drift_and_deduplicated_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake = FakeTransport(jibe_batch(0, 20, 30), jibe_batch(19, 11, 31))
    code = main(["--source", "pepsico", "--dry-run", "--validate-pepsico-pagination"],
                transport_factory=lambda: fake)
    output = capsys.readouterr().out
    assert code == 0
    assert "pepsico: complete raw=31 unique=30 duplicates=1 total_start=30 total_end=31 " in output
    assert "total_min=30 total_max=31 pages=2 drift=1" in output
    assert output.endswith("pepsico: OK raw=31 normalized=30\n")
    assert list(tmp_path.iterdir()) == []
