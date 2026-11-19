# Version 1 assignment audit

Local implementation review, 2026-11-14; editorial visual refinement, 2026-11-15. This is an implementation and offline-test
audit, **not a browser visual review or evidence of deployment**. GitHub Pages has
not been enabled. All current production data is read-only for this work.

| Rubric area | Evidence | Verification / limits |
|---|---|---|
| Pipeline — 25 | Existing pipeline, source adapters, daily workflow, issue upsert, same-day replacement and source failure protections | Full existing pytest suite; no production infrastructure edits or live run in this pass |
| Data — 20 | Existing compressed raw snapshots, fixed history/status files, raw-only rebuilding | Pre/post SHA-256 comparison of production files; read-only `build_history --verify`; frontend reconciliation of actual history/status |
| Site — 25 | Three required pages, source health, all four status counts, full Browse controls, local shortlist, PWA/offline | Static HTML checks, executed JavaScript unit tests, mocked service-worker lifecycle; actual browser/install/offline manual review pending |
| Market — 10 | Six exact sections, each with dynamic finding, explanation, SVG chart or explicit unavailable visualization | Tested exact calculations; baseline and denominator-zero cases; no invented history |
| Tests — 10 | Existing backend tests plus frontend CSV/date/filter/shortlist/analysis/cache/static checks | Pure JavaScript runs via macOS JavaScriptCore or Node; no browser automation or live requests |
| Repository — 10 | README retains source/ATS plan, title rule, rebuild command and Actions badge; file map extended | No staging, commits, pushes, Pages activation, or deployment |

## Today — index.html

- [x] Last run: `status.run_time`, displayed in America/Chicago with its actual CST/CDT label; original UTC ISO timestamp below it.
- [x] Every source: iterate `status.sources`; human name, OK/FAILED text, LED, count. No inferred live source health.
- [x] Exact four labels: DAYS WITH SUCCESSFUL RUN, OPEN, NEW TODAY, REMOVED TODAY, all read from status.
- [x] Latest new list: `first_seen == run_time UTC date && !first_run`.
- [x] Latest removed list: `removed_date == run_time UTC date`.
- [x] Lists show title, employer, location and the supplied public link; removals include removal date. Lists paginate at 25 records if needed.
- [x] Baseline explanation appears for an initial successful observation date with zero changes; normal zero-change states remain clear later.

## Browse — browse.html

- [x] Only `status == open` postings. Role radio is checked by default on every page load; `in_role` comes from the CSV, never a new frontend title classifier.
- [x] Employer options derive from open rows. Location datalist derives from source strings and supports case-insensitive substring search; only whitespace is trimmed for display/grouping.
- [x] Days-open buckets: all, 0–7, 8–14, 15–30, 31–60, 61+, baseline/unknown. Non-baseline age uses UTC calendar-day difference between `first_seen` and latest run date. Baseline age is null, never treated as zero or as a known true opening date.
- [x] Debounced, case-insensitive **title-only** search.
- [x] First-seen sorting: newest/oldest, stable posting-ID tie break.
- [x] Each rendered row/card has a star and direct HTTPS public apply link with `target=_blank`, `rel=noopener noreferrer`. Unsafe URLs are visibly unavailable rather than invented.
- [x] Shortlist stored as sorted stable posting IDs under `job-watcher.shortlist.v1`. Star/unstar, reload/session persistence, saved-only view, cross-tab updates. Storage failure is disclosed; no login.
- [x] Full filtering/sorting in memory, only 25 job rows/cards rendered at a time; match/employer/location counts and saved-ID count visible. Saved-only view intersects current open matches; closed/disappeared IDs remain stored without being presented as current openings.

## Market — market.html

All six sections have a category label, **result-bearing h2**, explanatory paragraph,
and SVG chart, chart-data table, or intentional unavailable-state visualization.
All source numbers are calculated in JavaScript from the fetched CSV.

| Section | Exact calculation | Empty / one-day behavior |
|---|---|---|
| New postings per day | Group `first_seen`, exclude `first_run`; both all and `in_role` series | Baseline excluded; zero observed additions shown, with explanation |
| Removed postings per day | Count by nonblank `removed_date` | Zero removals shown truthfully |
| Open postings per employer | Group rows with `status == open`; configured zero-count employers included | All configured employers remain represented |
| Median days open | For removed rows with `first_run == false`, `removed_date - first_seen`; sorted middle value / average of two middles | Unavailable when no eligible rows, not “0 days” |
| Share removed within seven days | Denominator: non-baseline rows first seen ≥7 UTC days before latest run. Numerator: eligible rows with a removal and duration ≤7. Percent = numerator / denominator ×100 | Unavailable for zero denominator; not “0%” |
| Top open locations | Rank top ten nonblank source strings excluding numeric location-count summaries; disclose all summary groups and missing values separately | No rows discarded, no geography invented; partition totals reconcile to all open rows |

History is current state, not an event ledger: reappearance clears the backend
removal date. Failed-source inventory remains last observed. Calendar dates with
zero observed changes are not proof of successful collection on every source/date.
JPMorgan coverage is explicitly limited to the required `analyst` search.

## Shared, responsive and accessible

- [x] One navigation design, exact TODAY/BROWSE/MARKET labels, active `aria-current` page; shared system fonts, stylesheet and utility JS.
- [x] No external fonts, chart CDN, framework, build system or stock imagery.
- [x] Skip link, semantic landmarks, labeled controls, native radio/keyboard behavior, visible focus, polite result/storage announcements, alert on data failure.
- [x] Color is supplemented by source-state text, chart legends/line patterns, exact chart data tables and explanatory copy.
- [x] Reduced-motion override; only a restrained cursor blink is continuously animated.
- [x] Layout breakpoints at 1400, 1150, 900, 700, 480px; editorial layouts adapt, Browse becomes cards, time-series redraw to container width and SVG ranking labels remain readable; exact data tables remain accessible. No essential data intentionally hidden on mobile.
- [ ] Manual visual checks at desktop/mobile widths, keyboard traversal, contrast in actual rendering, screen-reader behavior and zoom. Static intent is not a completed accessibility certification.

## PWA and offline

- [x] Relative manifest ID/start/scope, standalone display, theme colors, local SVG favicon and valid 192/512 PNG icons.
- [x] Service worker registers relative to the project directory; HTTPS deployment or localhost required, not file URLs.
- [x] All three pages and local assets precached. Shell network-first with exact cached-page fallback; no employer APIs contacted by the website.
- [x] Fixed status/history pair is network-first with a 12-second worker timeout. Both are parsed/validated/reconciled before publishing a new cached-generation pointer. No extra analytics JSON is created.
- [x] Failed/malformed/mismatched refresh keeps the last valid complete pair. Failed writes cannot publish a partial pair. Old successful timestamp remains visible. Cached/offline mode is labeled; reconnect asks for reload.
- [x] Install button appears only for a real `beforeinstallprompt`; browser/iOS install instructions remain in methodology. Does not pretend installation is universally supported.
- [ ] Actual first-load/reload/offline navigation, install prompt and standalone launch require manual browser review. Storage quotas/private sessions/eviction can disable offline availability and persistence.

## Manual acceptance before publishing

1. Serve repository root with `python3 -m http.server 8000` and inspect all three pages.
2. Check current status reconciles; all sources shown. On the first date, no baseline jobs appear as new and unavailable mature-history analytics remain unavailable.
3. Test role/all, all filters, date buckets, sorting, pagination, star/unstar, reload, saved-only view and keyboard focus at desktop/mobile widths.
4. After a successful controlled load, use browser DevTools Offline and navigate to all three pages. Verify cached timestamp and offline banner. Restore network and reload.
5. Install in a supporting browser and launch the installed app. Verify maskable icon, navigation and cached data.
6. Enable GitHub Pages only in a later approved publishing phase; verify the project-prefixed URL. This pass does not publish.

## Editorial refinement invariants

- Today retains all four required status counts, timestamps, every source and both
  latest-run change feeds. Daily additions/removals now precede the source roster.
- Browse preserves the existing filter/sort/age functions, default role, direct
  URL behavior and persistent stable-ID shortlist; only presentation/copy changes.
- All original Market aggregation/median/seven-day functions remain unchanged.
  `locationPresentation()` is an additional display partition, not a replacement
  data model. The pattern `^\d+\s+locations?$` (trimmed/case-insensitive) identifies
  numeric count summaries. All groups, including missing locations, are counted.
- Source labels remain complete in HTML, hover titles and exact data tables;
  truncation is CSS-only. No chart finding treats “2 Locations” as a place.
- Removed means absent from a later successful scan, not necessarily filled;
  both Today help and Market copy state this distinction.
- Only the shell-cache release name changes to v2. Data cache identity and
  offline/install functionality are preserved and regression-tested.
- Backend/workflow/data hashes are checked against the start of this pass,
  including pre-existing uncommitted Day 2 history/status changes.
- Actual visual, keyboard and install acceptance in a real browser remains
  pending. Tests/static intent are not a completed visual/accessibility review.

Refinement QA: 376 tests pass, including 56 frontend/static cases; JS syntax, HTML
structure, manifest/local assets, shortlist and mocked offline-cache lifecycle
checks pass. All 36 protected backend/workflow/data files (17 production files)
match their starting SHA-256 hashes. The unqualified Git whitespace check flags
CRLF endings in the pre-existing Day 2 `data/history.csv` diff; the authored-file
check and transient CRLF-aware check pass. No production line endings were changed.

## Focused role-emphasis refinement

Today highlights open in-role postings and relevant latest-run changes using the
CSV `in_role` flag. Required all-market OPEN / NEW TODAY / REMOVED TODAY and
successful-date counts remain visible and unchanged. Feed scope defaults to
Finance & Banking; All Openings exposes non-role additions/removals. Browse's
existing role-first filtering/sorting/persistence logic is retained. All six Market
analyses retain their original definitions; only series labels become explicit.
Tests cover exact relevant-count predicates, baseline exclusion for new records,
baseline inclusion for removals, default scope, real feed switching and real-data
reconciliation. Production data/backend/workflow hashes are checked against the
start of this pass. Actual browser visual review remains pending.
