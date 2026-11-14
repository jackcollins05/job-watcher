# Job Watcher

[![Tests](https://github.com/jackcollins05/job-watcher/actions/workflows/tests.yml/badge.svg)](https://github.com/jackcollins05/job-watcher/actions/workflows/tests.yml)

A Financial Data Analytics project for tracking **Finance & Banking Analyst**
postings over time. It fetches anonymous public JSON from 15 configured employers,
retains daily raw snapshots, rebuilds posting history, summarizes source health,
and prepares daily change issues. Phase 3 adds the production pipeline and
GitHub Actions definitions. **The website and GitHub Pages are not built.**

The current foundation contains normalized snapshot models, a title rule, history
replay, status calculation, an approved source registry, JSON fetch/conversion
adapters, raw gzip read/write helpers, dry-run and production CLIs, raw-archive
rebuilds, issue formatting/upserts, and offline tests. **No first production run
was performed during this Codex pass; no production raw/history/status files were
fabricated.** Synthetic postings exist only in tests using temporary directories.
The workflows and badge have been added as definitions; no successful GitHub
workflow execution is claimed yet.

## Approved sources

The approved evidence is [source_audit.md](source_audit.md) and
[audit/results.json](audit/results.json), captured on November 13, 2026.
The registry in [job_watcher/sources.py](job_watcher/sources.py) transcribes the
successful endpoints without fetching anything at import time.

Primary employers, in configured order:

1. Tyson Foods
2. KeyBank
3. PepsiCo
4. J.B. Hunt
5. Simmons Bank
6. Bank of America
7. JPMorgan Chase
8. Wells Fargo
9. Huntington Bank
10. Truist
11. PNC
12. U.S. Bank
13. Capital One
14. Fifth Third Bank
15. BMO

No backups remain in the approved list. **Huntington Bank** replaces Citi and
**KeyBank** replaces Walmart, using their previously audited Workday configurations.

Dropped sources: **Regions Bank** (tested endpoint returned HTTP 404), **Nestlé**
and **Arvest Bank** (no validated anonymous JSON endpoint). **Citi and Walmart**
are excluded from production because their 2,000-result caps prevent proven
complete traversal. Their configurations and cap regression tests are retained
for historical replay and testing; neither is a backup or a production selection.

The 15 primaries comprise **13 Workday CXS**, **1 Oracle Recruiting Candidate
Experience**, and **1 iCIMS/Jibe** source, totaling 15 currently eligible
production sources. The original audit confirmed anonymous JSON access
for 17 employers, including the now-excluded Citi and Walmart. Only anonymous public requests are permitted; no HTML scraping,
browser automation, credentials, cookies, private APIs or employer login.
Application submission may require login; reading postings does not.

**JPMorgan Chase must use the tested server-side search term `analyst`.** Its
Oracle board reported **7,008** jobs, exceeding 5,000; that search returned
**1,003**. This restricts coverage and is not an exact-title filter. Future
documentation must retain this disclosure. Registry endpoints, method and term
are implemented in the Oracle adapter; every production request retains that term.

Outstanding adapter concerns from the audit:

- PepsiCo's second call repeated page 1; next-page and language semantics need
  validation. Its JSON reports 2,622 total jobs and 1,997 for another apparent
  language scope; `lang=en-us` still returned mixed-language records.
- Walmart and Citi each reported exactly 2,000; counts may be capped.
- Most Workday records have no structured department/category; leave it blank.
  Fifth Third has a category-like bullet whose semantics need confirmation.
  Oracle has JobFamily/JobFunction but null Department in samples.
- Workday list-only fetching leaves optional dates blank when only relative labels
  exist and retains location summaries such as “2 Locations”. Oracle job-detail
  URLs are constructible from source IDs; destination behavior
  was not verified by the local-only audit update.
- Adapters must normalize source dates to YYYY-MM-DD, preserve opaque stable ID
  strings, and deliver **complete**, valid snapshots before enabling removals.

## Exact title rule

The single rule is `job_watcher.role.in_role(title)`. It uses **only the title**:

1. Apply Unicode NFKC normalization and case folding. Expand `FP&A` (including
   `FP & A`) to a dedicated token, replace `&` by `and`, replace punctuation with
   spaces, and collapse whitespace.
2. Require a whole-word `analyst` immediately before or after an approved family
   phrase, allowing **zero to two** intervening seniority/level tokens:
   `senior`, `sr`, `lead`, `principal`, `junior`, `jr`, `i`, `ii`, `iii`, `iv`,
   `1`, `2`, `3`, `4`.
3. Approved families are `financial`, `finance`, `FP&A`,
   `financial planning and analysis`, `treasury`, `credit`, `commercial banking`,
   `corporate banking`, `capital markets`, `investment banking`, `banking`, and
   these explicit financial risk phrases: `financial risk`, `banking risk`,
   `credit risk`, `market risk`, `liquidity risk`, `treasury risk`, `capital risk`,
   `investment risk`, `counterparty risk`.

Examples: `Financial Analyst II`, `Senior Financial Analyst`, `Analyst, Finance`,
`FP&A Analyst`, `Senior FP&A Analyst`, `Treasury Analyst`, `Credit Analyst`,
`Investment Banking Analyst`, and `Financial Risk Analyst` match. Bare
`Risk Analyst`, operational/cyber/clinical risk, `Data Analyst`, `Business Analyst`,
`Marketing Analyst`, `Supply Chain Analyst`, `Operations Analyst`, and `HR Analyst`
do not match unless the title also contains an approved phrase. `Finance Manager`
and `FP&A Director` do not match: this is an analyst rule. False negatives from
unlisted or nonadjacent wording are a deliberate consequence of this bounded rule.
No employer, description, department or job location affects `in_role`.

## Snapshots and history

`Posting` holds normalized posting fields; `Snapshot(source, date, postings, ok)`
represents one source's daily observation. Source keys are lowercase snake_case.
Dates are canonical UTC YYYY-MM-DD strings; snapshot producers are responsible
for UTC conversion. Optional missing department/posted_date values are blank.
`ok=True` certifies a complete snapshot, including a legitimately empty board.
Partial/invalid fetches must be failures (`ok=False`, no postings). A failure is
not a successful raw file. Reject duplicate source IDs and duplicate source/day
snapshots; adapters must reconcile retries before replay.

`build_history(snapshots)` sorts and replays the complete archive from scratch.
It never reads yesterday's history. The CSV columns are exactly:

```text
posting_id,source,source_id,employer,title,location,department,posted_date,url,in_role,first_run,first_seen,last_seen,status,removed_date
```

`posting_id` is `source + ":" + percent_encoded(source_id)` with no safe ID
punctuation; encoding prevents delimiter collisions. IDs stay strings, preserving
leading zeros. Choose a stable posting identity in each adapter, retaining distinct
postings of a shared requisition where appropriate.

- First observation sets first_seen/last_seen to that snapshot date, status=open,
  and blank removed_date. `first_run` means present in that source's earliest
  **successful** snapshot, not merely the project's earliest global date. An empty
  successful first snapshot still establishes the source's first run.
- Continued presence preserves first_seen/first_run, updates last_seen and current
  descriptive fields, and recalculates in_role from the current title.
- Only a valid snapshot for that source can remove absent open postings.
  Removed rows retain last_seen and descriptive fields; removed_date is the first
  valid absence date and does not move on repeated absence.
- Failed or missing source observations never remove its postings.
- Reappearance reopens, clears removed_date, updates last_seen, and preserves
  original first_seen/first_run. It does not become a newly first-seen posting.

Rows are sorted by posting_id. Explicit `write_history(rows, path)` exports the
exact schema, lowercase `true`/`false`, blank optional values and UTF-8 CSV.
No export has been run against `data/`.

## Status contract

`build_status(snapshots, run_time)` replays the same snapshots and returns:

| Key | Meaning |
|---|---|
| run_time | Caller-provided timezone-aware latest run instant converted to UTC ISO timestamp ending Z |
| first_run_date | Earliest successful raw snapshot date; null if no raw files exist |
| days_with_success | Distinct UTC dates with at least one successful source snapshot, including empty successful snapshots |
| open | All currently open postings, including out-of-role rows |
| new_today | First seen on the UTC run date, excluding all first_run rows |
| removed_today | Currently removed rows whose removed_date is the UTC run date |
| sources | One entry per configured primary, in registry order: stable key in name, boolean ok, integer count |

Source ok/count describe the **run date**, never a stale previous successful day.
Failure or missing snapshot means false/0; a successful empty snapshot means true/0.
Source counts include all normalized postings. In-role flags remain available for
later presentation. Future-dated snapshots and naive run timestamps are rejected.
This helper returns data only; it does not write `data/status.json`.

## Structure and checks

```text
audit/                 existing reconnaissance evidence and bounded probe utility
data/                  real raw/history/status outputs after the first run
job_watcher/
  __init__.py
  schema.py            normalized models and CSV columns
  role.py              single title rule
  history.py           deterministic replay and explicit CSV export
  status.py            status calculation
  sources.py           approved primary/backup/drop registry
  pipeline.py          daily production runner
  build_history.py     raw-archive rebuild and verification CLI
  issues.py            pure issue formatting + explicit gh publishing
  storage.py           atomic local derived-output writes
tests/
  test_role.py
  test_history.py
  test_status.py
  test_pipeline.py
  test_issues.py
.github/workflows/
  daily.yml
  tests.yml
README.md
pyproject.toml
.gitignore
source_audit.md
```

Python **>=3.11** is the supported target; runtime dependencies are standard
library only. The optional `test` extra declares pytest. In a suitable prepared
environment, run:

```sh
python3 -m pytest
python3 -m compileall job_watcher tests
git diff --check
git status --short
```

The system `python3` is 3.9.6 without pytest. The existing `.venv/bin/python`
provides Python 3.14 and pytest, so offline tests can run as:

```sh
.venv/bin/python -m pytest
```

No packages were downloaded or installed in the adapter implementation pass.
The existing audit probe was **not rerun**; no live fetch command was executed.

## Adapter layer and source keys

| Primary employer | Source key | Adapter |
|---|---|---|
| Tyson Foods | tyson_foods | Workday CXS |
| KeyBank | keybank | Workday CXS |
| PepsiCo | pepsico | iCIMS/Jibe |
| J.B. Hunt | jb_hunt | Workday CXS |
| Simmons Bank | simmons_bank | Workday CXS |
| Bank of America | bank_of_america | Workday CXS |
| JPMorgan Chase | jpmorgan_chase | Oracle Candidate Experience |
| Wells Fargo | wells_fargo | Workday CXS |
| Huntington Bank | huntington_bank | Workday CXS |
| Truist | truist | Workday CXS |
| PNC | pnc | Workday CXS |
| U.S. Bank | us_bank | Workday CXS |
| Capital One | capital_one | Workday CXS |
| Fifth Third Bank | fifth_third_bank | Workday CXS |
| BMO | bmo | Workday CXS |

Excluded sources remain outside the CLI's production selection; no backups remain. Source endpoints, methods,
Oracle site number, required term, and capped-total flags live in `sources.py`.
No additional speculative ATS adapters exist.

- `adapters/base.py`: transport protocol, anonymous curl implementation,
  controlled errors, and common conversion helpers. Tests inject fake transports.
- `adapters/workday.py`: CXS POST search and direct list conversion. No per-job
  detail requests; existing envelopes containing saved details remain replayable.
- `adapters/oracle.py`: public GET search envelope and stable `Id` conversion.
- `adapters/jibe.py`: PepsiCo's `jobs[].data` layout; no customer/private iCIMS API.
- `fetch.py`: per-source `FetchResult`, continuation after source failures, dry-run
  CLI. Results expose source, employer, ok, raw record count, converted postings,
  raw envelope, and error. Partial failures return no authoritative postings.
- `raw.py`: versioned envelope, deterministic gzip, explicit read/write, offline
  conversion, and bridging to the existing normalized `Snapshot`/history contract.

HTTP uses **curl**, matching the successful audit probe's TLS/HTTP implementation,
with an explicit `JobWatcher/0.1` User-Agent and JSON MIME/decoding checks.
Each attempt has an **8-second connection limit**, a **20-second total transfer
deadline**, and a **23-second subprocess guard**. The response cap is 16 MiB;
requests have a 0.25-second delay, with at most one retry for selected transient
curl errors or HTTP 429/502/503/504. A process-deadline failure is not retried.
Retry-After values above 10 seconds or unparseable values fail for later retry.
No cookies, login, auth headers, proxy credentials, HTML bootstrap,
HTML parsing, or browser automation are used. A per-source transport budget of
15,000 attempts and page budget of 5,000 bound a run; reaching either is failure.
Those ceilings are guards, not targets. Workday uses **20 records per page**;
the audit's limit of 2 was for bounded reconnaissance, not production throughput.
The saved audit does not establish a maximum CXS page size. Twenty is a
conservative standard CXS choice, pending confirmation by the normal-Terminal
smoke test; it is not claimed to be the maximum validated by the saved audit.
Oracle uses a conservative 25 jobs per finder request, and PepsiCo/Jibe uses
20 jobs per page, as documented below. Neither production setting is inherited
from the audit's two-record reconnaissance limit.

The curl command uses `-q`, `--retry 0`, `--proto =https`, the audit's environment
allowlist, `Accept: application/json`, and the same `json.dumps` POST encoding with
`Content-Type: application/json`. Query encoding also matches the audit. Curl is
invoked directly without a shell. No `--compressed`/Accept-Encoding override or
automatic curl redirect following is enabled. Safe redirects are followed explicitly
under the policy below. Compared with the audit, the production transport
retains its explicit User-Agent, larger response cap, and bounded outer retry;
response headers used for Retry-After are temporary and are not saved in raw data.
No additional Python HTTP dependency is needed; curl must be available on PATH,
as it already is for `audit/probe_sources.py`.

This replaces urllib's per-socket timeout, which did not provide the audit's
end-to-end transfer deadline. The exact reason the observed urllib response read
stalled has not been isolated with a live comparison; no TLS or server-specific
cause is asserted. A complete Workday run still traverses all list pages, unlike
the audit's few probes, so a bounded manual smoke test is useful.

### Pagination and completeness

Workday advances POST `offset` by its configured page size (20 by default:
0, 20, 40, ...). For an uncapped board, the positive `total` on the first
offset-0 response is the reported completion target. Later zero totals are
placeholders and do not erase it. Once unique IDs reach that target, fetching
stops successfully **without an extra page request**. A final short page is
complete when it satisfies that target; a short page alone does not prove
completion. Pagination and conversion share
the same stable source ID rule. Occasional overlapping postings are deduplicated;
a page with duplicates **and new IDs** continues normally. Raw responses retain
all records, while normalized output keeps the first observed record per stable
ID, sorted by posting_id. Changed title/location slugs do not create a second row
for the same source ID.

Progress counts new unique IDs, not raw records. A nonempty page adding zero new
IDs or a repeated page/result-ID set (including reordered results) before
trustworthy completion fails with a controlled pagination-stalled error. Errors
include unique count, reported total, offset and page size. A repeated boundary
page after completion is avoided altogether by stopping on the preceding page.
Such a failure cannot produce a complete
snapshot. On pages with overlap, the CLI prints a summary such as
`tyson_foods: page 12 added 19 new, 1 duplicate`; ordinary pages get only the
existing fetching-page line.

No second positive confirmation is required: the saved Tyson response reports
735 initially and zero on the next page despite containing jobs. A contradictory
later positive total disables early completion; known cap-risk boards never use
this rule. Without a trustworthy reached target, normal empty-page completion
still applies subject to the initial count/completeness and cap guards. A zero
progress page below the target still fails, rather than being treated as success.
Successful completion prints `source: complete unique=<n> reported_total=<n>`
and preserves all deduplicated rows for the final OK summary. List responses provide
the required IDs, titles, location summaries and public URL paths; no detail
requests are made for optional dates or richer locations. Workday later-page
zero totals do not erase the initial advertised total. A page/safety failure
cannot create a successful empty source or trigger history removals.

At the audited Tyson total of 735, the original adapter made roughly 369 list
requests (two records each, including a final empty page) plus 735 detail requests.
The current list-only adapter requests 20 records per page: approximately **37
requests**, with a final 15-record page and no detail or empty-probe requests
when the trusted reported total is 735. It still checks the initial total before claiming a complete source;
if a server returns fewer records than expected across the requested offsets,
the source fails rather than silently dropping postings.

`--max-pages N` limits **only explicit manual dry-runs** and fetches at most N
list pages. For example, N=1 fetches just page 1, without a completion probe or
detail calls. Partial results print **TRUNCATED (dry-run)** and include converted
sample counts; their raw envelope stays `complete=false` and cannot be written
as a successful raw snapshot or passed into history. An explicitly truncated
smoke test exits 0 when conversion succeeds, but is not evidence of full-board
completion. Real errors still exit 1. If completion is proven within the budget,
the result may instead be OK. The library rejects max_pages unless dry_run=True.
Without that option, normal fetches paginate fully, retaining the failure-only
safety guards; no default production truncation is introduced.
The option changes only the number of pages fetched, never Workday's configured
20-record page size. A one-page Workday smoke test therefore requests up to 20
jobs rather than 2.

**Excluded Walmart and Citi (regression configurations only):** if the initial
reported total is exactly 2,000, traversal
still runs but the result is marked **FAIL**, even after an empty page, because
the audit cannot establish complete coverage at that possible cap. No silent
truncation, hidden search change, or invented partitioning is implemented. They
need a validated completeness strategy before successful production snapshots.
Any unfiltered Workday board reporting over 5,000 similarly fails pending audited
search configuration. No unapproved title/search filter is silently introduced.

Oracle uses **25 jobs per finder request**, replacing the audit's reconnaissance
limit of 2. The audit does not establish a maximum job-page size; 25 is a
conservative production choice pending the normal-Terminal retry. The outer
`limit: 200` is not evidence of a supported 200-job page size.

Job pagination metadata is inside `items[0]`: `TotalJobsCount`, `Offset`, `Limit`,
and `requisitionList`. The finder offset advances by the inner returned `Limit`
(25 normally, or a smaller positive server-provided value), independently of raw
or unique job counts. The returned keyword and offset are checked on every page;
invalid page limits and materially changing totals fail explicitly.

The starting inner `TotalJobsCount` anchors the full traversal. Every expected
offset must return successfully before count reconciliation is allowed: the
current offset plus its validated inner Limit must reach/past that starting
total. Tolerance never shortens the offset traversal. With starting total 1,003
and limit 25, that requires all 41 offsets 0, 25, ..., 1,000, regardless of whether
the count is already close on page 40. No extra empty-page probe is required.

Oracle's `TotalJobsCount` is reconciled against **raw result rows/slots**, not
against deduplicated posting IDs. The adapter tracks reported starting total,
raw rows fetched, unique stable IDs, and duplicates (`raw - unique`) separately.
After the full successful offset traversal, raw rows reaching the reported total
prove the reported result set was fetched. Duplicate overlaps do not consume a
percentage tolerance or cause a final count failure. All unique rows are retained.

For example, **reported=1,003 / raw=1,003 / unique=995 / duplicates=8 is success**.
The complete reported set of rows was fetched, while stable-ID deduplication
correctly produces 995 normalized postings. Both quantities are disclosed:

```text
jpmorgan_chase: complete raw=1003 unique=995 duplicates=8 reported_total=1003
jpmorgan_chase: OK raw=1003 normalized=995
```

A small tolerance remains **only as a secondary fallback for genuine raw-row
shortfall**, after all expected offsets succeeded: max(2 rows,
floor(starting_total × 0.5%)). For 1,003 reported rows that permits at most 5
missing raw rows; 950 raw rows still fails even if every expected offset was
requested. It never limits the number of duplicates or replaces full traversal.
An accepted raw-row discrepancy is explicitly labeled `raw_drift=<difference>`
in the completion summary; surplus raw rows are also disclosed with this label.
Small metadata-total changes within that same tolerance leave the starting target
unchanged, while material metadata changes fail for later retry. An initially
positive board yielding no jobs is never accepted as churn. This is not a claim
that a changing board's responses form an atomic snapshot of one instant.

Raw pages retain all duplicates; conversion keeps the first record per stable Id.
Pages with duplicates plus new IDs continue. A nonempty page with zero new IDs
is still a controlled stall, even if its count is close. An empty page before
all expected offsets, a transport/page failure, wrong keyword/offset, page safety
limit, or final raw-row shortfall outside tolerance fails and cannot write a successful raw
snapshot. A final partial/empty page can reconcile only after all expected offsets
are covered, using the raw-row completion rule or its bounded shortfall fallback.
Manual `--max-pages` samples remain
TRUNCATED when that traversal has not finished, even if their count is close.
Duplicate summaries are printed only on affected pages.

The **outer** `count`, `hasMore`, `offset`, `limit`, and `links` describe the search
envelope collection. The saved response has `count: 1`, `hasMore: false`, and
outer `offset: 0` even when the inner job search returns only 2 of 1,003 postings
at inner offsets 0 and 2. Its links expose self/actions, not a job-next link.
Using that hasMore flag to stop jobs would silently truncate the source. A final
response with `hasMore: false` succeeds when the inner total is satisfied; that
flag alone never overrides an incomplete nested job result.

JPMorgan always uses `keyword=analyst` and public site `CX_1001`; it cannot be
configured to fetch the unfiltered board. `--max-pages` still applies only to
explicit manual dry-runs, never changes the page size, and marks unfinished
samples TRUNCATED rather than allowing successful daily snapshots.

**PepsiCo:** only page 1 was observed in the saved audit. Default dry-run fetches
that page and reports **FAIL** when incomplete, explaining the validation gate.
An explicit `--validate-pepsico-pagination` flag permits candidate incrementing
`page=2,3,...` in a normal Terminal live dry-run. The production limit is **20**,
independent of manual `--max-pages`. The audit proves no maximum page size, so
20 is a conservative choice that the normal-Terminal validation run must confirm.

Observed request fields are `lang`, `limit`, and `page`. Observed JSON contains
`jobs[].data`, `totalCount`, `count`, and `languageCounts`, with **no** total-page,
next-page or has-more field. The saved `totalCount` was 2,622; `count` was 1,997,
matching the English-language count even though returned records had mixed
languages. Neither that smaller count nor any invented next-page field is used
to truncate the global board. `lang=en-us` does not establish English-only scope.

During traversal, the adapter records first/latest/minimum/maximum `totalCount`,
raw rows, unique req_id/language identities, duplicates, and successful page count.
A changed total alone does not fail. New IDs keep pagination progressing; mixed
duplicate/new pages are valid and conversion emits one row per stable identity,
keeping the first observed record. Exact repeated result sets or nonempty pages
with zero new IDs are controlled stalls. No detail calls are added.

Completion requires **both** an end signal and count/coverage consistency:

- End signal: an empty page, a partial page near the reported end, or raw rows
  reaching the maximum observed total with the implied page slots covered.
- All observed totals must span at most `max(2, floor(first_total × 0.5%))` jobs.
  The successful page range must cover the maximum observed total minus that
  small tolerance. A larger total range cannot become an automatic success.
- Raw rows must reach at least the minimum observed total. Only an explicit
  multipage validation run can accept a raw shortfall within the same tolerance.
  Unique IDs cannot exceed the maximum observed total plus that tolerance;
  raw rows above it must be explainable by duplicates. A positively reported board
  yielding no jobs cannot be accepted as churn.

A partial page earlier in the implied range does not itself prove completion;
validation continues while new results arrive. An empty page that cannot pass
the reconciliation checks fails, as do material shortfalls, ambiguous language
scope, inconsistent page sizes, transport errors, or exhausted safety budgets.
The validation flag permits testing additional pages, not bypassing these guards.
Manual bounded samples remain explicitly TRUNCATED and cannot be daily snapshots.

For the saved total 2,622, the small count-range/shortfall tolerance is 13 rows;
it is a documented live-churn policy, not an observed API guarantee. Completion
prints every count, for example:

```text
pepsico: complete raw=31 unique=30 duplicates=1 total_start=30 total_end=31 total_min=30 total_max=31 pages=2 drift=1
pepsico: OK raw=31 normalized=30
```

`drift` is latest minus first total (signed). The full live validation still
needs normal-Terminal confirmation; saved audit data alone does not prove
global language/count semantics or the new page size.

### Raw snapshots and conversion

The explicit `write_raw()` helper can write a **successful** envelope to:

```text
data/raw/<YYYY-MM-DD>/<source>.json.gz
```

It is **not called by the dry-run CLI**; the production pipeline calls it.
An envelope includes format version, source and
employer, the actual source configuration, UTC fetched_at, complete/error flags,
and ordered response entries. Each entry retains the complete decoded response
JSON plus kind (`list`/`detail`) and safe request method/URL/query/body. JSON
objects and embedded description strings are preserved without HTML parsing;
whitespace and original wire encoding are not preserved. Headers/cookies are
not stored, and authentication-material keys cause the writer to reject the raw
payload. The format stores source responses rather than replacing them with
normalized rows. New Workday fetches retain list pages only; old envelopes may
also contain previously saved details, which conversion can optionally use.

UTF-8 JSON uses sorted keys and fixed separators; gzip has an empty filename and
mtime=0. Identical envelopes produce identical bytes. Timestamp changes naturally
change the content. Writing is atomic and refuses to overwrite an existing daily
file by default. The production pipeline explicitly enables atomic replacement
for same-day reruns. Failed/partial envelopes are rejected before any directory is created.
`read_raw`, `convert_raw`, and `as_snapshot` can replay a saved file using its
embedded configuration without the audit file, current registry, or network.
Converters/title rules remain versioned project code needed for any rebuild.

Conversion yields exactly these pre-history fields:

```text
posting_id,source,source_id,employer,title,location,department,posted_date,url,in_role
```

`in_role` calls the existing title rule. Employer comes from the approved source
configuration. No first/last-seen, first_run, status or removal fields are set.

- Workday uses the real ID in `bulletFields[0]`, preserving an observed posting
  suffix from `externalPath` when it matches that ID (e.g. `R0497068-1` instead of
  requisition-only `R0497068`). This distinguishes postings without depending on
  changing title/location slug text. No internal UUID lookup or ID hash is needed.
  This replaces the pre-production detail-UUID identity choice; no production raw
  files/history exist to migrate. Titles use list `title`, locations use
  `locationsText`, and the public URL is constructed as `https://{host}/{site}`
  plus `externalPath`. No required list field is dropped. Location summaries may
  be less precise than detail data. `postedOn` is used only if parseable as an
  absolute date; relative labels become blank. Department is blank for all 13
  Workday primaries, including Fifth Third's unlabeled bullet. If an old raw file
  already includes details, its location/date/externalUrl may enrich conversion
  without another request; identity still follows the same list-ID rule.
- Oracle uses real `Id`; `Title`, `PrimaryLocation`, and `PostedDate` map directly.
  Category uses `JobFamily`, falling back to `JobFunction`; missing values are
  blank. The public CX_1001 detail URL is constructed from returned Id. There is
  no separate observed application-only URL field.
- PepsiCo uses real `req_id` **plus language** as a stable translation identity:
  `length(req_id):req_id:language` (e.g. `6:REQ001:en-us`). This avoids merging
  translations without inventing a replacement source ID. It uses `title`,
  `full_location` (or city/state/country, then location_name), `categories[].name`,
  and `posted_date`. Public canonical URL is preferred, then `apply_url`. Missing
  categories/dates are blank; no department inference from title is performed.

Parseable timestamp dates are normalized to UTC YYYY-MM-DD; timezone-free dates
are retained as source calendar dates. Malformed JSON structures fail conversion
explicitly. Workday skips individual malformed postings with diagnostics and
removal protection as documented below; other adapters retain strict validation. All three adapters deduplicate
overlaps by stable source identity and retain their pagination-stall safeguards.

### Live smoke tests — normal macOS Terminal only

The following commands make real requests; they were **not run in Codex**:

```sh
cd ~/job-watcher
.venv/bin/python -m job_watcher.fetch --all --dry-run
.venv/bin/python -m job_watcher.fetch --source tyson_foods --dry-run
# Bounded, one-page manual smoke test:
.venv/bin/python -u -m job_watcher.fetch --source tyson_foods --dry-run --max-pages 1
# Full JPMorgan search, retaining the mandatory analyst filter:
.venv/bin/python -u -m job_watcher.fetch --source jpmorgan_chase --dry-run
# Explicit candidate-pagination validation for PepsiCo:
.venv/bin/python -m job_watcher.fetch --source pepsico --dry-run --validate-pepsico-pagination
```

Use `--all --dry-run --validate-pepsico-pagination` to include the explicit
PepsiCo experiment in an all-source live test. Before starting each source, the
CLI immediately prints and flushes `source: fetching...`. Completion is flushed
as `source: OK raw=<n> normalized=<n>` or `source: FAIL <short reason>` followed
by raw/normalized counts.
Before each list request it also flushes `source: fetching page N...`; there is
no per-job output. Truncated manual runs receive their own explicit completion
label and cannot masquerade as full successful snapshots.
Raw count counts received list records, not advertised totals, and includes
overlaps. Successful runs can therefore show raw count greater than their
deduplicated normalized count. Exit code is 1 if any source fails, else 0.
The CLI requires `--dry-run`, continues after a source failure, and never writes
raw/history/status files or creates Issues. Backups and excluded sources cannot be selected by this CLI.

Tests include every primary source's ten conversion fields and missing optional
values, platform pagination, capped/repeated/empty/malformed responses, failure
representation, raw replay/gzip, mandatory Oracle term, and CLI continuation.
Small fictional fixtures under `tests/fixtures/` reproduce the saved real JSON
layouts. Tests never load or require the ignored giant audit response file;
an autouse network guard blocks DNS and socket connections.

## Daily production pipeline (Phase 3)

Run from **normal macOS Terminal**, where source networking is available:

```sh
cd ~/job-watcher
.venv/bin/python -m job_watcher.pipeline
```

This is a real production fetch command, not a smoke test. It has **no manual
page limit**, attempts every primary source in registry order, and enables the
approved PepsiCo multipage validation path. The adapter's completeness/stall
checks still apply. Walmart and Citi are excluded from production, with their
cap regressions retained. Source failures
are reported rather than misrepresented as successful snapshots. It never fetches
backups or dropped employers. It performs no Git or GitHub operations itself.

The pipeline captures its start instant once, converts it to UTC, and uses that
date for **every source**, even if fetching crosses midnight. It saves each
complete successful source envelope at:

```text
data/raw/YYYY-MM-DD/<source>.json.gz
```

For each failed source it writes no raw file and records a failed outcome with
an error in the run result/log. Unexpected per-source exceptions also become
failures, and remaining sources are still attempted. After fetching it loads
**all raw files**, replays them chronologically by date/source, atomically writes
`data/history.csv` and `data/status.json`, and prepares that date's issue body.
Old history.csv is never an input to that rebuild. Corrupt, misdated or misnamed
archive files fail the build rather than being silently ignored.

A source failure does not fail the overall pipeline when derived outputs can be
built correctly. Even an all-source-failure run writes truthful latest health and
preserves earlier history, but creates no successful raw date or success-day
increment. A filesystem/archive/derived-output error that prevents truthful
outputs is fatal. In particular, failure to delete a stale failed-source snapshot
cannot be silently treated as a completed run.

### Same-day reruns and failure semantics

- A later successful run on the same UTC date **atomically replaces** that
  source/date gzip file. It does not append another daily observation.
- If that source fails on the rerun, its earlier same-day raw file is **deleted**.
  A stale success therefore cannot leak into latest status or history.
- History and status are then rebuilt from the resulting archive. Successful raw
  dates count once. Empty dated directories without raw files count zero times.
- With no source raw file on a date, that source's previously open postings retain
  their prior status/last_seen. Only a successful raw snapshot, including a truly
  empty one, can remove absent jobs from that source.
- Reappearance preserves first_seen/first_run, updates last_seen, reopens, and
  clears removed_date. Each source establishes its own earliest successful raw
  snapshot: those baseline jobs have first_run=true and are excluded from new_today.
  No removals or new-job alerts are invented on the first production day.

The fixed history column order and lowercase CSV booleans are documented above.
The fixed status keys remain exactly `run_time`, `first_run_date`,
`days_with_success`, `open`, `new_today`, `removed_today`, `sources`. Source entries
are in primary registry order with `name`, `ok`, `count`. Counts are **unique
normalized postings** in that source's latest successful raw snapshot; raw API
result rows may include overlaps. A failed latest attempt is false/0, even when
the source has previously open jobs. All tracked postings contribute to these
counts; in_role is preserved separately for later presentation.

### Raw-only rebuild and verification

```sh
# Recreates data/history.csv, including after deleting it:
.venv/bin/python -m job_watcher.build_history
# Rebuilds in memory and compares bytes without rewriting history.csv:
.venv/bin/python -m job_watcher.build_history --verify
```

`--data-dir PATH` is available for the pipeline, rebuild and issue commands.
Unit tests write synthetic gzip snapshots under pytest temporary directories,
delete history.csv, rebuild again, and assert identical bytes. The reproducibility
check needs no employer/GitHub requests and does not need audit/results.json.
The CSV can be rebuilt from raw files alone; status additionally takes the latest
run timestamp and configured source list. The production pipeline writes status
on each attempt, so failure-only days remain visible even without new raw files.

## Daily GitHub Issues

Issue publishing is explicit and separate from fetching; the daily workflow runs
it after a successful pipeline/reproducibility check:

```sh
# Local, offline preview of the latest prepared issue:
.venv/bin/python -m job_watcher.issues --preview
# Contacts GitHub; use only when ready to publish:
.venv/bin/python -m job_watcher.issues --repo jackcollins05/job-watcher
```

The title is the pipeline's **UTC start date**, taken from status.json rather than
the clock at issue-publishing time. The body lists NEW POSTINGS and REMOVED
POSTINGS for that date from the latest rebuilt history, with title, employer and
job link. Baseline first_run rows are excluded from new postings; absent changes
are explicitly `No new postings.` / `No removed postings.`. An issue exists on
every completed run day even if there are zero changes or failed sources.

A hidden first-line ownership marker identifies this project's daily issues.
The publisher paginates all issues, ignores PRs/unrelated issues, and updates or
reopens the marked issue for the same date rather than duplicating it. It then
closes only the latest earlier **project run** issue, which may be several days
old rather than literally yesterday. It never closes unrelated date-titled issues.
If today's create/update fails, previous issues remain open. If the previous close
fails, a rerun safely updates today's existing issue and retries. Duplicate marked
issues for the same date cause an explicit error for review.

The implementation invokes `gh api` with structured temporary JSON files, never
shell-interpolated issue bodies. The workflow passes the default Actions token as
GH_TOKEN, with issues write permission; a personal access token is not required.
Manual publishing requires an already authenticated gh environment. Preview and
pure formatting/selection tests never contact GitHub.

## GitHub Actions

**Daily workflow:** [.github/workflows/daily.yml](.github/workflows/daily.yml).

- Cron **`17 12 * * *`** means once daily at **12:17 UTC**, approximately **06:17
  Central Standard Time / 07:17 Central Daylight Time**. GitHub scheduling may be
  delayed; manual workflow_dispatch is also supported.
- Runs only for main, checks out current main, and uses Python **3.13**. It installs
  `.[test]`, runs pytest **before** production fetching, executes the pipeline,
  verifies raw-only CSV reproducibility, then upserts today's issue and closes
  the previous project's run issue.
- Permissions are only `contents: write` and `issues: write`. A fixed concurrency
  group prevents overlapping daily executions and does not cancel the active run.
- Only `data/raw/`, `data/history.csv`, and `data/status.json` are staged, including
  same-day raw deletions. It commits as `Daily job watcher run YYYY-MM-DD` using
  the pipeline date and pushes main. No-change staging is handled without error;
  the issue is still updated before that check. No force push is used.
- If tests, archive validation, publishing or committing fails, subsequent steps
  stop. Per-source fetch failures alone do not prevent correctly rebuilt outputs
  from being committed. Review the status source entries and run logs.

**Tests workflow:** [.github/workflows/tests.yml](.github/workflows/tests.yml)
runs pytest on **push** and **pull_request**, with Python **3.13** and read-only
contents permission. Its real repository status badge is at the top of this README;
adding the definition does not imply a completed successful run. The daily job
also runs its own tests before fetching; default-token automated pushes do not
normally trigger a second GitHub Actions run.

Neither workflow deploys a website or GitHub Pages. **The first real production
run has not been performed during this implementation pass.** All production
paths were left empty; synthetic data was restricted to test temporary directories.

### First real run after reviewing these changes

1. In normal Terminal, run `.venv/bin/python -m pytest` and inspect these changes.
2. Run `.venv/bin/python -m job_watcher.pipeline` once; this writes real raw,
   history and status data but does not stage, commit, push or publish an issue.
3. Run `.venv/bin/python -m job_watcher.build_history --verify`, inspect
   data/status.json (including failures), and preview the dated issue with
   `.venv/bin/python -m job_watcher.issues --preview`.
4. Publish the prepared issue explicitly when ready, or later enable the reviewed
   workflow on main. The workflow itself publishes issues and commits/pushes data;
   a manual local pipeline run does neither. Avoid overlapping local and Actions
   production runs. Repository Issues and Actions write permissions must be enabled.

### GitHub-hosted runner failures and safe retries

Workday list entries with a missing/invalid `externalPath` are handled individually.
The adapter uses a real requisition/posting ID, never a hash or a title-derived ID.
A valid list path constructs the public URL using the configured board. If that
path is absent, only a literal `externalUrl` returned by the API in the same
board's supported Workday public job URL family can supply the path. Requisition
ID and title alone do not establish a public URL. Unusable rows are skipped and
counted in `skipped_malformed`; valid rows are retained. An entirely malformed
nonempty result is a source failure, not an empty successful snapshot. No job
detail requests are added.

Raw responses retain skipped rows. During raw-only history rebuilding, a skipped
row's exact known stable ID protects an existing posting from false removal and
preserves its known metadata. An ambiguous requisition/posting suffix preserves
prior state; a row with no usable ID suppresses removals for that source snapshot.
New unusable rows create no incomplete history rows. If a later usable row has the
same exact ID, its original observation date/baseline is retained. This safety can
delay removal detection until a later clean snapshot. Source status counts remain
normalized usable postings; logs distinguish raw rows and skipped malformed rows.

Redirects are explicitly validated, with at most **three hops** and loop detection.
Only anonymous HTTPS URLs preserving the original JSON endpoint path (a trailing
slash may differ) and query parameters are allowed. Workday may change its wdN
cluster host within the same tenant, or use a Workday `myworkdaysite.com` host
while preserving the exact CXS tenant/site path. Unrelated domains, another
board's path, credentials, login/landing paths and changed query filters are
rejected before another request. Standard semantics apply: 303 becomes GET,
301/302 changes POST to GET, and 307/308 preserves the method/body. Every hop keeps
the existing timeouts, request budget and JSON validation; cookies and credentials
are never carried. Accepted redirect metadata is retained in the raw envelope.
Neither the successful audit curl command nor the previous production transport
used `-L`. The old transport rejected all 3xx responses. The failing Wells Fargo
and Truist runs did not retain Location headers, so their exact destinations and
whether they meet this policy still require validation in Actions. HTML is never
parsed, even after a permitted redirect.

**Citi and Walmart remain subject to `board_cap_unresolved`.** The saved responses
include real facets, but do not prove exhaustive partitions. Citi's 55 country
facet counts sum to 4,224 despite `total=2000`; Walmart's three country facet
counts sum to 20,238. Other facet sums differ, some facet lists contain exactly
55 entries, and the saved requests do not validate applied-facet pagination or
coverage of jobs with missing facet values. Consequently no untested filter,
search term or partition strategy is introduced. A repeated/terminal page at the
2,000 cap remains a controlled failure and produces no authoritative raw file.
Fixing Walmart's malformed rows does not resolve its cap risk.

Approved production policy: **Huntington Bank replaces Citi** and **KeyBank
replaces Walmart** in the 15-primary registry. Neither capped board is a production
source or backup; no backups remain. Walmart’s live page 101 repeated 20 rows with
zero new IDs after the 2,000-result cap, confirming the completeness limitation.
Both excluded configurations retain their cap safeguards and regression tests.
The assignment still needs 15 complete usable production sources; a successful
workflow with failed sources alone does not establish that coverage. Historical
Day 1 raw, history and status files are unchanged. Future runs enumerate Huntington
and KeyBank instead of Citi and Walmart; each promoted source’s earliest successful
snapshot is its own baseline.

After reviewing and publishing the code fixes, dispatch **Daily Job Watcher** on
`main`. To replace the first day's outputs, the run must start while the UTC date
is still **2026-11-14**; rerunning an old workflow later uses the actual new UTC
date, not the old run date. Use a new dispatch after publishing, rather than
rerunning jobs pinned to an older code revision. Review failure classes
(`redirect_validation`, `response_validation`, `malformed_postings`,
`board_cap_unresolved`) and skip counts. Successful same-day raw files replace
prior files; failed sources lose stale same-day files. History/status rebuild
from raw alone, the date counts once, and the same managed daily issue is updated.
These fixes were tested offline; existing committed Day 1 data was not rewritten.
