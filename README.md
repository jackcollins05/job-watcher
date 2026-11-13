# Job Watcher

A Financial Data Analytics project for tracking **Finance & Banking Analyst**
postings over time. It will eventually fetch anonymous public JSON from 15
employers, retain daily raw snapshots, rebuild posting history, summarize source
health, and publish a website. Fetch adapters, production orchestration, raw-file
loading, scheduling, GitHub workflows/issues, and the website are **not implemented**.

The current foundation contains normalized snapshot models, a title rule, history
replay, status calculation, an approved source registry, and offline unit tests.
No production history or status files have been generated. Synthetic postings
exist only in unit-test fixtures; the audit contains real saved source responses.

## Approved sources

The approved evidence is [source_audit.md](source_audit.md) and
[audit/results.json](audit/results.json), captured on November 13, 2026.
The registry in [job_watcher/sources.py](job_watcher/sources.py) transcribes the
successful endpoints without fetching anything at import time.

Primary employers, in configured order:

1. Tyson Foods
2. Walmart
3. PepsiCo
4. J.B. Hunt
5. Simmons Bank
6. Bank of America
7. JPMorgan Chase
8. Wells Fargo
9. Citi
10. Truist
11. PNC
12. U.S. Bank
13. Capital One
14. Fifth Third Bank
15. BMO

Backups: **Huntington Bank** and **KeyBank**, both validated Workday sources.

Dropped sources: **Regions Bank** (tested endpoint returned HTTP 404), **Nestlé**
and **Arvest Bank** (no validated anonymous JSON endpoint).

The 15 primaries comprise **13 Workday CXS**, **1 Oracle Recruiting Candidate
Experience**, and **1 iCIMS/Jibe** source. With backups, 17 usable sources were
confirmed. Only anonymous public requests are permitted; no HTML scraping,
browser automation, credentials, cookies, private APIs or employer login.
Application submission may require login; reading postings does not.

**JPMorgan Chase must use the tested server-side search term `analyst`.** Its
Oracle board reported **7,008** jobs, exceeding 5,000; that search returned
**1,003**. This restricts coverage and is not an exact-title filter. Future
documentation must retain this disclosure. Registry endpoints, method and term
are configuration only; pagination/request construction belongs to later adapters.

Outstanding adapter concerns from the audit:

- PepsiCo's second call repeated page 1; next-page and language semantics need
  validation. Its JSON reports 2,622 total jobs and 1,997 for another apparent
  language scope; `lang=en-us` still returned mixed-language records.
- Walmart and Citi each reported exactly 2,000; counts may be capped.
- Most Workday records have no structured department/category; leave it blank.
  Fifth Third has a category-like bullet whose semantics need confirmation.
  Oracle has JobFamily/JobFunction but null Department in samples.
- Detail calls may be needed for Workday dates and multi-location listings.
  Oracle job-detail URLs are constructible from source IDs; destination behavior
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
data/                  empty; reserved for real production artifacts
job_watcher/
  __init__.py
  schema.py            normalized models and CSV columns
  role.py              single title rule
  history.py           deterministic replay and explicit CSV export
  status.py            status calculation
  sources.py           approved primary/backup/drop registry
tests/
  test_role.py
  test_history.py
  test_status.py
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

The implementation environment currently exposes Python 3.9.6 without pytest;
no packages were downloaded or installed. Tests require a prepared environment
with the supported Python and pytest. The existing audit probe was **not rerun**.

Foundation validation: offline lifecycle/title/status/registry smoke checks passed.
Compilation passed with `PYTHONPYCACHEPREFIX` set to the workspace's ignored
`__pycache__/` directory (the default system cache location was not writable).
Pytest could not run because it is absent. Git initialization was denied while
creating `.git`; therefore the requested Git diff/status checks could not complete.
No repository, staging, commit or push was created by this pass.
