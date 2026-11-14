# Job Watcher — source audit

**Evidence:** [audit/results.json](audit/results.json), successful normal macOS Terminal run, 2026-11-13T19:38:15.850653+00:00 to 2026-11-13T19:40:09.326497+00:00. This report supersedes the earlier sandbox DNS-failure assessment. This update used local files only; no network request or probe rerun was performed.

**Current approved plan: 15 primary sources, no backups, 5 excluded sources.** Huntington Bank replaces Citi, and KeyBank replaces Walmart, because neither capped board has a proven complete traversal. The original reconnaissance confirmed anonymous JSON access for 17 employers, including Citi; access alone does not prove complete board coverage. The measurements below are unchanged historical audit evidence. Current production classification and source-plan sections incorporate the approved replacement. Walmart’s full live traversal repeated 20 jobs with zero new IDs at page 101. Walmart and Citi are excluded; their cap detection remains intact for regression tests.

The user confirms that the saved probe ran anonymously without credentials, cookies, API keys, authentication tokens, or login. The local probe utility uses direct curl requests without HTML bootstrapping or browser state. Every usable source has multiple HTTP 200 JSON responses containing actual job records. All 15 successful Workday sources additionally return `userAuthenticated: false` and have successful JSON detail requests. PepsiCo and Oracle do not expose that flag; their anonymous access is established by the supplied run context and direct request evidence. No application was submitted.

Counts and field flags below come from the saved response bodies, not just the probe summary fields. In particular, PepsiCo’s summary count is null, but its raw JSON contains `totalCount: 2622`. Regions returns a JSON error envelope, which is not a usable job source.

## Employer audit

Employer links preserve the previously identified official careers entries; they were not fetched in this pass. Field flags describe the sampled records, not a guarantee for every future posting. “Detail URL” satisfies the requested application/job-detail URL requirement; submitting an application may separately require login.

| Employer | ATS | JSON Endpoint / Pattern | Method | Anonymous JSON Confirmed? | Approx. Posting Count | Search Term Needed? | Stable Job ID? | Title? | Location? | Department? | Posted Date? | Apply URL? | Classification | HTTP / Content Type | Pagination / Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [Tyson Foods](https://www.tysonfoods.com/careers) | Workday CXS | `https://tysonfoods.wd5.myworkdayjobs.com/wday/cxs/tysonfoods/TSN/jobs` | POST | Yes | 735 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Walmart](https://careers.walmart.com/us/en/home) | Workday CXS | `https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs` | POST | Yes | 2,000 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | DROP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200; 2,000 cap unresolved; excluded after full live traversal |
| [Nestlé](https://www.nestle.com/jobs) | Unvalidated | Not identified | Unknown | No validated endpoint | Unknown | Undetermined | Unverified | Unverified | Unverified | Unverified | Unverified | Unverified | DROP | Not tested; `Not observed` | No validated anonymous JSON endpoint; probe skipped |
| [Arvest Bank](https://www.arvest.com/careers) | Unvalidated | Not identified | Unknown | No validated endpoint | Unknown | Undetermined | Unverified | Unverified | Unverified | Unverified | Unverified | Unverified | DROP | Not tested; `Not observed` | No validated anonymous JSON endpoint; probe skipped |
| [PepsiCo](https://www.pepsicojobs.com/main/jobs) | iCIMS / Jibe career site | `https://www.pepsicojobs.com/api/jobs` | GET | Yes | 2,622 | No observed total >5,000 | Yes | Yes | Yes | Yes: categories | Yes: posted_date | Yes: apply + canonical URL | KEEP | 200; `application/json; charset=utf-8` | Same page 1 repeated; next page untested |
| [J.B. Hunt](https://careers.jbhunt.com/jobs) | Workday CXS | `https://jbhunt.wd501.myworkdayjobs.com/wday/cxs/jbhunt/Careers/jobs` | POST | Yes | 436 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Simmons Bank](https://www.simmonsbank.com/about/careers) | Workday CXS | `https://simmonsbank.wd5.myworkdayjobs.com/wday/cxs/simmonsbank/SimmonsCareers/jobs` | POST | Yes | 155 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Bank of America](https://careers.bankofamerica.com/) | Workday CXS | `https://ghr.wd1.myworkdayjobs.com/wday/cxs/ghr/Lateral-US/jobs` | POST | Yes | 1,979 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [JPMorgan Chase](https://www.jpmorganchase.com/careers) | Oracle Recruiting CE | `https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions` | GET | Yes | 7,008 | Yes: analyst → 1,003; README required | Yes | Yes | Yes | Yes: JobFamily / JobFunction | Yes: PostedDate | Constructible from Id; untested destination | KEEP | 200; `application/json` | Filtered offsets 0 → 2; distinct IDs |
| [Wells Fargo](https://www.wellsfargojobs.com/) | Workday CXS | `https://wf.wd1.myworkdayjobs.com/wday/cxs/wf/WellsFargoJobs/jobs` | POST | Yes | 1,474 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Citi](https://jobs.citi.com/) | Workday CXS | `https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs` | POST | Yes | 2,000 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | DROP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200; 2,000 cap unresolved; excluded from production after cloud run |
| [Truist](https://careers.truist.com/us/en) | Workday CXS | `https://truist.wd1.myworkdayjobs.com/wday/cxs/truist/Careers/jobs` | POST | Yes | 1,381 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [PNC](https://careers.pnc.com/global/en) | Workday CXS | `https://pnc.wd5.myworkdayjobs.com/wday/cxs/pnc/External/jobs` | POST | Yes | 1,889 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [U.S. Bank](https://careers.usbank.com/global/en) | Workday CXS | `https://usbank.wd1.myworkdayjobs.com/wday/cxs/usbank/US_Bank_Careers/jobs` | POST | Yes | 1,201 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Capital One](https://www.capitalonecareers.com/) | Workday CXS | `https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs` | POST | Yes | 2,055 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Regions Bank](https://careers.regions.com/us/en) | Workday CXS | `https://regions.wd5.myworkdayjobs.com/wday/cxs/regions/Regions/jobs` | POST | No usable jobs (JSON error) | Unknown | Undetermined | Unverified | Unverified | Unverified | Unverified | Unverified | Unverified | DROP | 404; `application/json;charset=ISO-8859-1` | Current endpoint HTTP 404; JSON error, no jobs |
| [Fifth Third Bank](https://www.53.com/content/fifth-third/en/careers.html/) | Workday CXS | `https://fifththird.wd5.myworkdayjobs.com/wday/cxs/fifththird/53careers/jobs` | POST | Yes | 993 | No observed total >5,000 | Yes | Yes | Yes | Category-like bullet only | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [Huntington Bank](https://www.huntington.com/careers) | Workday CXS | `https://huntington.wd12.myworkdayjobs.com/wday/cxs/huntington/HNBcareers/jobs` | POST | Yes | 710 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [KeyBank](https://www.key.com/about/careers.html) | Workday CXS | `https://keybank.wd5.myworkdayjobs.com/wday/cxs/keybank/External_Career_Site/jobs` | POST | Yes | 569 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |
| [BMO](https://jobs.bmo.com/global/en/home) | Workday CXS | `https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/jobs` | POST | Yes | 1,052 | No observed total >5,000 | Yes | Yes | Yes | Not exposed in sample | Yes: startDate + postedOn | Yes: externalUrl | KEEP | 200; `application/json` | Offsets 0 → 2; distinct IDs; detail GET 200 |

## Request specifications and field mappings

### Workday CXS — 15 usable employers

The exact successful search endpoint for each employer is in the table. Search method: **POST**; `Accept: application/json` and `Content-Type: application/json`. Tested first-page payload:

```json
{"appliedFacets":{},"limit":2,"offset":0,"searchText":""}
```

Second-page payload changes only `offset` to `2`. Each usable Workday employer returned two different job records on each page, with no overlap of sampled external paths. Successful detail **GET** pattern: search endpoint without its final `/jobs`, followed by the JSON `externalPath` (`/job/...`). Search and detail responses were HTTP 200, `application/json`.

| Required field | Observed JSON mapping | Treatment |
|---|---|---|
| Stable ID | `jobPostings[].bulletFields[0]`; detail `jobPostingInfo.jobReqId` and `id` | Preserve strings, including leading zeros. Retain `externalPath` / `jobPostingId` for distinct postings of a requisition. |
| Title | `jobPostings[].title`; detail `jobPostingInfo.title` | Use current JSON title, not the slug text. |
| Location | `locationsText`; detail `jobPostingInfo.location`, optional `additionalLocations`, `jobRequisitionLocation` | Prefer detail when list says “2 Locations”. |
| Department/category | Generally absent from sampled structured job/detail fields | Leave blank; board-level facets and hiring organization are not per-job departments. |
| Posted date | Detail `jobPostingInfo.startDate`; list/detail `postedOn` | Preserve absolute startDate and relative label separately; startDate may reflect reposting, not the original requisition date. |
| Public job-detail URL | `jobPostingInfo.externalUrl` | Returned directly by JSON; destination was not separately fetched. Application submission/login is outside this audit. |

Fifth Third’s samples contain `bulletFields[1] = "Consumer Banking"`, a category-like label. It is available without HTML parsing, but lacks an explicit field name establishing category semantics. Preserve the raw label; leave a normalized department/category blank until that mapping is agreed. Wells Fargo’s second bullet is a posting-end date, so a global rule treating the second bullet as department would be wrong.

On 13 of the 15 usable Workday sources, the offset-2 response reports `total: 0` while returning two jobs. Bank of America and Capital One retain their positive totals. Use the initial offset-0 total as the observed count; do not interpret a later zero total as an empty page or zero jobs. Only two pages were inspected, so full traversal, server page-size limits and completeness are not established.

### JPMorgan Chase — Oracle Recruiting Candidate Experience

Method: **GET**, `Accept: application/json`. Successful endpoint:

`https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions`

Decoded query parameters from the saved requests:

```text
onlyData=true
expand=requisitionList
finder=findReqs;siteNumber=CX_1001,limit=2,offset=0
```

**Unfiltered count: 7,008** from `items[0].TotalJobsCount`. The root `count` counts search-envelope items, not job postings. The filtered request uses:

```text
finder=findReqs;siteNumber=CX_1001,limit=2,offset=0,keyword=analyst
```

**Tested search term: `analyst`; reduced count: 1,003. The eventual README MUST disclose this server-side search term**, the 7,008 → 1,003 observed reduction, date, site CX_1001, and coverage limitation. The response confirms `Keyword: "analyst"`, with `UseExactKeywordFlag: false`. This searches more broadly than an exact title match; the offset-2 sample includes “Early Careers Recruiter, Associate”. Do not equate the result set with a final title rule.

The filtered next page uses `offset=2`; both filtered calls return HTTP 200 `application/json`, two jobs each, different IDs, and total 1,003. Unfiltered search also returned HTTP 200 with two job records. `siteNumber` is public configuration, not a token.

| Field | Observed mapping |
|---|---|
| Stable ID | `items[0].requisitionList[].Id` (string) |
| Title | `Title` |
| Location | `PrimaryLocation`, `PrimaryLocationCountry` |
| Category | `JobFamily`, `JobFunction` are populated; `Department`, `BusinessUnit`, `Organization` are null in samples |
| Posted date | `PostedDate` (absolute YYYY-MM-DD) |
| Job-detail URL | Construct `https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/{Id}` from returned Id and request siteNumber. URL destination/redirect behavior is not verified in this local-only pass. No literal apply URL field appears in the samples. |

### PepsiCo — iCIMS / Jibe career-site JSON

Both saved requests are **GET** to the same URL:

`https://www.pepsicojobs.com/api/jobs?lang=en-us&limit=2&page=1`

Both return HTTP 200, `application/json; charset=utf-8`, two `jobs[].data` records with the same IDs. JSON `ats_code: "icims"` and Jibe asset metadata support the platform identification.

**Observed counts:** `totalCount = 2622`; `count = 1997`, matching `languageCounts["en-us"].count`. These counts have different apparent language scopes; the exact semantics are not established. Despite `lang=en-us`, the two returned records are Portuguese (`pt-br`) and English (`en-us`), so that parameter does not establish English-only coverage. No observed count exceeds 5,000.

The saved `pagination_or_repeat` request repeats **page=1**, not page=2. Therefore repeatability is confirmed but next-page behavior is **unverified**. `limit=2` produced two records. A future pagination validation must establish the next-page parameter and language/count semantics before claiming complete ingestion; no extra requests were made here.

| Field | Observed mapping |
|---|---|
| Stable ID | `jobs[].data.req_id` and `slug`; retain ID strings and language |
| Title | `title` |
| Location | `full_location`, `city`, `state`, `country`, `location_name` |
| Department/category | `categories[].name`, `category` |
| Posted date | `posted_date` with timezone; distinguish `create_date` and `update_date` |
| Apply URL | `apply_url`, which may point to an iCIMS `/login` page; browsing postings still requires no login |
| Public detail URL | `meta_data.canonical_url`, returned directly in JSON |

## Per-employer saved evidence

Each entry names the source record and its request purposes so the exact evidence can be located in `audit/results.json`. Pagination counts below are observed sample sizes, not full-board downloads.

### Tyson Foods

Search endpoint/method: **POST** `https://tysonfoods.wd5.myworkdayjobs.com/wday/cxs/tysonfoods/TSN/jobs`.
- `unfiltered` at 2026-11-13T19:38:15.851028+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Houston-Portwall-St-Plant---Houston-Texas/General-Labor---2nd-Shift---Houston--TX_R0497068-1", "/job/Corporate-412-West---Springdale-Arkansas/Claims-Coordinator---Logistics--Corporate-412-West-_R0495599-2"]; reported total 735; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:38:19.234219+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/RVI-Scranton---Scranton-Arkansas/Electrician-Maintenance-Project-Crew-EC01-to-EC08---A-Shift--Days----RVI-Scranton_R0497060-1", "/job/Corporate-Meadow---Springdale-Arkansas/Principal-Engineer--Onsite-_R0495412-2"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:38:22.671575+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R0497068`, date `2026-11-13`, location "Houston Portwall St Plant - Houston, Texas", public URL `https://tysonfoods.wd5.myworkdayjobs.com/TSN/job/Houston-Portwall-St-Plant---Houston-Texas/General-Labor---2nd-Shift---Houston--TX_R0497068-1`.

Classification: **KEEP** (primary).

### Walmart

Search endpoint/method: **POST** `https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs`.
- `unfiltered` at 2026-11-13T19:38:24.851778+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/USA-CO-LITTLETON-06635-SAMS-CLUB/Pharmacy-Tech-Certified-Sam-s--Part-Time-_R-2708862", "/job/USA-PA-WAYNESBORO-03633-WM-SUPERCENTER/Staff-Pharmacist_R-2705836-1"]; reported total 2000; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:38:28.076519+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Watertown-NY/XMLNAME--USA--Senior-Technician--Facility-Services--HVAC-Refrigeration_R-2680267", "/job/USA-VA-KING-GEORGE-05779-WM-SUPERCENTER/Pharmacy-Manager_R-2523684"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:38:30.382384+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R-2708862`, date `2026-11-13`, location "(USA) CO LITTLETON 06635 SAM'S CLUB", public URL `https://walmart.wd504.myworkdayjobs.com/WalmartExternal/job/USA-CO-LITTLETON-06635-SAMS-CLUB/Pharmacy-Tech-Certified-Sam-s--Part-Time-_R-2708862`.

Current classification: **DROP / excluded from production**. Full live traversal reached 2,000 unique postings, then page 101 repeated 20 postings with no new IDs. Complete board coverage cannot be proven; KeyBank replaces Walmart.

### Nestlé

No JSON endpoint identified; no request fabricated. Classification: **DROP**.

### Arvest Bank

No JSON endpoint identified; no request fabricated. Classification: **DROP**.

### PepsiCo

Search endpoint/method: **GET** `https://www.pepsicojobs.com/api/jobs?lang=en-us&limit=2&page=1`.
- `unfiltered` at 2026-11-13T19:38:32.421457+00:00: HTTP 200, `application/json; charset=utf-8`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["483243", "483177"]; reported total 2622.
- `pagination_or_repeat` at 2026-11-13T19:38:35.082326+00:00: HTTP 200, `application/json; charset=utf-8`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["483243", "483177"]; reported total 2622.

Classification: **KEEP** (primary).

### J.B. Hunt

Search endpoint/method: **POST** `https://jbhunt.wd501.myworkdayjobs.com/wday/cxs/jbhunt/Careers/jobs`.
- `unfiltered` at 2026-11-13T19:38:36.670429+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Pico-Rivera-CA---8400-Slauson-Ave/Operations-Internship--Spring-2027_00643399", "/job/Lowell-AR---JB-Hunt-Corporate-B--C/Call-Center-Support-I_00652490"]; reported total 436; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:38:38.678757+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Stockton-CA---Loomis-Road/Manager-Trainee_00652645", "/job/Stone-Mountain-GA---Sarr-Pkwy/Manager-Trainee_00652556"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:38:40.518089+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `00643399`, date `2026-11-13`, location "Pico Rivera, CA - 8400 Slauson Ave", public URL `https://jbhunt.wd501.myworkdayjobs.com/Careers/job/Pico-Rivera-CA---8400-Slauson-Ave/Operations-Internship--Spring-2027_00643399`.

Classification: **KEEP** (primary).

### Simmons Bank

Search endpoint/method: **POST** `https://simmonsbank.wd5.myworkdayjobs.com/wday/cxs/simmonsbank/SimmonsCareers/jobs`.
- `unfiltered` at 2026-11-13T19:38:41.953782+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Russellville-AR/Relationship-Banker-II_R115514", "/job/Memphis-TN/Relationship-Banker-II_R115611"]; reported total 155; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:38:43.878524+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Maumelle-AR/Relationship-Banker-II_R115759-1", "/job/Little-Rock-AR/Relationship-Banker-I_R115751"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:38:45.741080+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R115514`, date `2026-11-13`, location "Russellville, AR", public URL `https://simmonsbank.wd5.myworkdayjobs.com/SimmonsCareers/job/Russellville-AR/Relationship-Banker-II_R115514`.

Classification: **KEEP** (primary).

### Bank of America

Search endpoint/method: **POST** `https://ghr.wd1.myworkdayjobs.com/wday/cxs/ghr/Lateral-US/jobs`.
- `unfiltered` at 2026-11-13T19:38:47.419533+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Lake-Oswego/Business-Solutions-Advisor---Lake-Grove-Financial-Center_26042240", "/job/Charlotte/Special-Asset-Group-Credit-Officer-II_26041930"]; reported total 1979; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:38:49.166882+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Charlotte/Process-Design-Consultant-II---Enterprise-Credit_26040481", "/job/Hayward/Business-Solutions-Advisor---Hesperian-La-Playa-Financial-Center---Bilingual-Spanish-Required_26041847"]; reported total 1979; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:38:50.800516+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `26042240`, date `2026-11-12`, location "Lake Oswego", public URL `https://ghr.wd1.myworkdayjobs.com/Lateral-US/job/Lake-Oswego/Business-Solutions-Advisor---Lake-Grove-Financial-Center_26042240`.

Classification: **KEEP** (primary).

### JPMorgan Chase

Search endpoint/method: **GET** `https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs%3BsiteNumber%3DCX_1001%2Climit%3D2%2Coffset%3D0`.
- `unfiltered` at 2026-11-13T19:38:52.446888+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["210616021", "210690282"]; reported total 7008.
- `search` at 2026-11-13T19:38:54.433024+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["210783447", "210793803"]; reported total 1003.
- `pagination_or_repeat` at 2026-11-13T19:38:56.344313+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["210808075", "210808565"]; reported total 1003.

Classification: **KEEP** (primary).

### Wells Fargo

Search endpoint/method: **POST** `https://wf.wd1.myworkdayjobs.com/wday/cxs/wf/WellsFargoJobs/jobs`.
- `unfiltered` at 2026-11-13T19:38:58.114302+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/BLUE-BELL-PA/Senior-Branch-Premier-Banker-Blue-Bell_R-578333-1", "/job/CUMMING-GA/Senior-Premier-Banker-Sharon-Greens_R-587550"]; reported total 1474; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:00.438870+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/STEAMBOAT-SPRINGS-CO/Senior-Branch-Premier-Banker-Steamboat-Springs-CO_R-586553", "/job/WEST-CHESTER-PA/Senior-Branch-Premier-Banker---Brandywine-District_R-587452"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:02.743369+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R-578333`, date `2026-11-13`, location "BLUE BELL, PA", public URL `https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs/job/BLUE-BELL-PA/Senior-Branch-Premier-Banker-Blue-Bell_R-578333-1`.

Classification: **KEEP** (primary).

### Citi

Search endpoint/method: **POST** `https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs`.
- `unfiltered` at 2026-11-13T19:39:04.150867+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Monterrey-Nuevo-Leon-Mexico/Banamex-Norte-Distrito-Monterrey-Oriente-Ejecutivo-de-cuenta-Pyme-Jr_261008893-1", "/job/New-York-New-York-United-States/Senior-Executive-Assistant_261007677-1"]; reported total 2000; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:09.106958+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Ciudad-De-Mexico-Distrito-Federal-Mexico/Banamex-Director-de-Desarrollo-de-Productos-Seguros_25919247", "/job/Chatsworth-California-United-States/Part-Time-Teller--20-Hours----Chatsworth-Branch_261007717"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:12.489570+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `261008893`, date `2026-11-13`, location "Monterrey Nuevo Leon Mexico", public URL `https://citi.wd5.myworkdayjobs.com/2/job/Monterrey-Nuevo-Leon-Mexico/Banamex-Norte-Distrito-Monterrey-Oriente-Ejecutivo-de-cuenta-Pyme-Jr_261008893-1`.

Current classification: **DROP / excluded from production**. Anonymous JSON access succeeded in reconnaissance, but the live 2,000-result cap prevents proven complete traversal. Huntington Bank replaces Citi; no unvalidated partitions are used.

### Truist

Search endpoint/method: **POST** `https://truist.wd1.myworkdayjobs.com/wday/cxs/truist/Careers/jobs`.
- `unfiltered` at 2026-11-13T19:39:15.950994+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Charlotte-NC/Liquidity-Risk-Analyst-II_R0121072", "/job/Atlanta-GA/Software-Engineer---Java---AWS_R0121814"]; reported total 1381; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:18.377559+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Beckley-WV/Relationship-Banker--Beckley--Saturday-Required-_R0121807", "/job/Lexington-KY/Branch-Leader---Lexington-Downtown_R0121805"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:20.659223+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R0121072`, date `2026-11-13`, location "Charlotte, NC", public URL `https://truist.wd1.myworkdayjobs.com/Careers/job/Charlotte-NC/Liquidity-Risk-Analyst-II_R0121072`.

Classification: **KEEP** (primary).

### PNC

Search endpoint/method: **POST** `https://pnc.wd5.myworkdayjobs.com/wday/cxs/pnc/External/jobs`.
- `unfiltered` at 2026-11-13T19:39:22.298971+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/FL---Tampa/Merchant-Services-Account-Executive---Business-Banking_R232143-1", "/job/IL---Chicago-60606/Construction-Project-Lead_R240228-1"]; reported total 1889; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:26.492326+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/VA---Centreville/Corporate-Facilities-Manager-I_R240205-1", "/job/Home-Location-CO-COH01/Virtual-Financial-Advisor---PNC-Wealth-Management_R226870-1"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:29.157791+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R232143`, date `2026-11-13`, location "FL - Tampa", public URL `https://pnc.wd5.myworkdayjobs.com/External/job/FL---Tampa/Merchant-Services-Account-Executive---Business-Banking_R232143-1`.

Classification: **KEEP** (primary).

### U.S. Bank

Search endpoint/method: **POST** `https://usbank.wd1.myworkdayjobs.com/wday/cxs/usbank/US_Bank_Careers/jobs`.
- `unfiltered` at 2026-11-13T19:39:31.108836+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Gresham-OR/Commercial-Bkg-Client-Rep-5_2026-0033560-1", "/job/Scottsdale-AZ/Middle-Market-Relationship-Manager_2026-0030994"]; reported total 1201; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:33.787031+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Denver-CO/Credit-Portfolio-Manager---Energy-Industries---Denver-or-Dallas--Institutional-Client-Group_2026-0025741", "/job/Alexandria-MN/Relationship-Banker-I---Alexandria--MN_2026-0035706"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:35.859232+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `2026-0033560`, date `2026-11-13`, location "Gresham, OR", public URL `https://usbank.wd1.myworkdayjobs.com/US_Bank_Careers/job/Gresham-OR/Commercial-Bkg-Client-Rep-5_2026-0033560-1`.

Classification: **KEEP** (primary).

### Capital One

Search endpoint/method: **POST** `https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs`.
- `unfiltered` at 2026-11-13T19:39:37.322441+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Gainesville-VA/Full-Time-Branch-Ambassador---Madison-Crescent_R1005808", "/job/New-York-NY/Full-stack-Engineer-5--Senior-Manager--IC--EDT_R1005828-1"]; reported total 2055; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:38.731719+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/McLean-VA/Business-Director--People-Analytics_R1005827-1", "/job/Plano-TX/Senior-Manager--Full-Stack-Engineer_R1005818-1"]; reported total 2055; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:40.073267+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R1005808`, date `2026-11-13`, location "Gainesville, VA", public URL `https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/Gainesville-VA/Full-Time-Branch-Ambassador---Madison-Crescent_R1005808`.

Classification: **KEEP** (primary).

### Regions Bank

Search endpoint/method: **POST** `https://regions.wd5.myworkdayjobs.com/wday/cxs/regions/Regions/jobs`.
- `unfiltered` at 2026-11-13T19:39:41.396484+00:00: HTTP 404, `application/json;charset=ISO-8859-1`, JSON decoded = True; curl exit 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`; error envelope only, no job list.

Classification: **DROP** (current endpoint returned HTTP 404).

### Fifth Third Bank

Search endpoint/method: **POST** `https://fifththird.wd5.myworkdayjobs.com/wday/cxs/fifththird/53careers/jobs`.
- `unfiltered` at 2026-11-13T19:39:43.188103+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Hurricane-WV/Personal-Banker-Assocate-I_R74156", "/job/Chillicothe-OH/Personal-Banker-Associate-I_R74158"]; reported total 993; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:45.648090+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Wilmington-OH/CSR-Teller--Wilmington--OH--Full-Time_R74907", "/job/Columbus-OH/Licensed-Investment-Support-Specialist-II_R75138"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:47.730177+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R74156`, date `2026-10-20`, location "Hurricane, WV", public URL `https://fifththird.wd5.myworkdayjobs.com/53careers/job/Hurricane-WV/Personal-Banker-Assocate-I_R74156`.

Classification: **KEEP** (primary).

### Huntington Bank

Search endpoint/method: **POST** `https://huntington.wd12.myworkdayjobs.com/wday/cxs/huntington/HNBcareers/jobs`.
- `unfiltered` at 2026-11-13T19:39:49.538193+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Columbus-OH/Small-Business-Lending-Consultant_R0074760-1", "/job/Memphis-TN/Financial-Relationship-Banker---Memphis-Southwind_R0074891"]; reported total 710; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:51.534589+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Columbus-OH/Senior-HR-Case-Manager_R0077362-1", "/job/Easton-Ops-Cols-C-Oh/Mac-OS-Platform-Engineer-III_R0075433"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:53.223381+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R0074760`, date `2026-10-14`, location "Columbus, OH", public URL `https://huntington.wd12.myworkdayjobs.com/HNBcareers/job/Columbus-OH/Small-Business-Lending-Consultant_R0074760-1`.

Current classification: **KEEP** (promoted from backup to primary, replacing Citi).

### KeyBank

Search endpoint/method: **POST** `https://keybank.wd5.myworkdayjobs.com/wday/cxs/keybank/External_Career_Site/jobs`.
- `unfiltered` at 2026-11-13T19:39:54.584736+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Overland-Park-KS/Finance-Compliance-Manager_R-39912", "/job/Cleveland-OH/Part-time-Teller_R-43244-1"]; reported total 569; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:39:57.424501+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Brooklyn-OH/Lead-Closing-Officer-or-Senior-Closing-Officer---Commercial-Real-Estate-and-Syndications_R-39276", "/job/Willoughby-OH/Branch-Manager_R-43231"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:39:59.880149+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R-39912`, date `2026-11-13`, location "Overland Park, KS", public URL `https://keybank.wd5.myworkdayjobs.com/External_Career_Site/job/Overland-Park-KS/Finance-Compliance-Manager_R-39912`.

Current classification: **KEEP** (promoted from backup to primary, replacing Walmart).

### BMO

Search endpoint/method: **POST** `https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/jobs`.
- `unfiltered` at 2026-11-13T19:40:02.441616+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Virtual-AZ-USA/Premier-Client-Specialist_R260031334", "/job/San-Francisco-CA-USA/Director--Not-for-Profit-and-Healthcare-Banking_R260031034"]; reported total 1052; payload `{"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": ""}`.
- `pagination_or_repeat` at 2026-11-13T19:40:04.797489+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; 2 jobs, source IDs/paths ["/job/Toronto-ON-CAN/Manager--Operational-Risk--Canadian-Business-Banking_R260031333", "/job/Vancouver-BC-CAN/Credit-Analyst--Commercial-Banking_R260028657"]; reported total 0; payload `{"appliedFacets": {}, "limit": 2, "offset": 2, "searchText": ""}`.
- `detail` at 2026-11-13T19:40:07.254627+00:00: HTTP 200, `application/json`, JSON decoded = True; curl exit 0; structured ID `R260031334`, date `2026-11-13`, location "Virtual, AZ, USA", public URL `https://bmo.wd3.myworkdayjobs.com/External/job/Virtual-AZ-USA/Premier-Client-Specialist_R260031334`.

Classification: **KEEP** (primary).

## PRIMARY SOURCES

Use the approved revised 15 employers below. Huntington Bank replaces Citi and KeyBank replaces Walmart because complete traversal cannot be proven beyond either board’s 2,000-result cap. The original audit measurements remain evidence of anonymous JSON access; they do not prove complete production traversal. Oracle’s detail URL is constructed rather than returned.

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

## BACKUPS

None remain. Huntington Bank and KeyBank are both primary sources.

## DROPS

- **Walmart:** full live pagination reached the 2,000-result cap and repeated a page. Complete safe traversal cannot be proven; replaced by KeyBank.
- **Citi:** anonymous JSON works, but the live board reaches a 2,000-result cap and exhaustive safe partitioning is not established. Excluded from production; replaced by Huntington Bank.
- **Regions Bank:** current POST endpoint returned HTTP **404** with a JSON error envelope, not postings. This rejects the tested endpoint, not all possible Regions interfaces.
- **Nestlé:** no validated anonymous JSON endpoint; no request present in this run.
- **Arvest Bank:** no validated anonymous JSON endpoint; no request present in this run.

## ATS SUMMARY

| Platform | Primary KEEP | BACKUP | Usable total | DROP |
|---|---:|---:|---:|---:|
| Workday CXS | 13 | 0 | 13 | 3 (Walmart/Citi caps, Regions endpoint) |
| Oracle Recruiting Candidate Experience | 1 | 0 | 1 | 0 |
| iCIMS / Jibe career site | 1 | 0 | 1 | 0 |
| No validated interface | 0 | 0 | 0 | 2 |
| **Total** | **15** | **0** | **15** | **5** |

## TECHNICAL RISKS

- **Bounded evidence:** 51 saved requests across 18 attempted employers: 50 HTTP 200 and one HTTP 404. Two employers were skipped. Multiple successful requests establish short-term repeatability, not a long-term reliability guarantee. No rate-limit failure is recorded; actual quotas remain unknown.
- **Pagination:** only offsets 0 and 2 were checked for usable Workday boards and filtered Oracle; PepsiCo page 1 was repeated. Full traversal and maximum supported limit are untested. Jobs can move during pagination; deduplicate by employer, source ID and where needed posting/language.
- **Totals:** retain offset-0 Workday totals because many subsequent totals are zero. Walmart and Citi each report exactly 2,000; this could represent a cap. Their complete board sizes and whether they exceed 5,000 cannot be determined from this snapshot. Do not invent larger counts or claim their full boards were enumerated.
- **Large board:** only JPMorgan Chase is observed over 5,000. Its tested `analyst` search reduces 7,008 to 1,003. The README must disclose the term. It is not exact-title filtering and can include irrelevant jobs or miss finance jobs without that keyword.
- **Missing fields:** most Workday samples do not expose a structured department/category. Do not parse embedded jobDescription HTML, infer department from facets, or substitute hiring organization. Fifth Third has an unlabeled category-like bullet. Oracle Department/BusinessUnit/Organization are null; JobFamily/JobFunction remain usable categories.
- **Locations and dates:** Workday detail calls are needed for absolute `startDate` and meaningful locations when summary says “N Locations”. Retain additionalLocations where present. Date availability is sampled, not guaranteed; leave missing future values blank. Do not treat closing date as posting date.
- **URL scope:** Workday externalUrl is returned in JSON; Wells Fargo uses a `myworkdaysite.com` destination. PepsiCo returns an apply URL that can require login for submission, plus a public canonical detail URL. Oracle URLs can be constructed; their destinations were not fetched. Application submission is outside the anonymous listing requirement.
- **Employer/board scope:** Bank of America is Lateral-US; J.B. Hunt corporate and driving boards differ. Walmart includes Sam’s Club and Citi includes Banamex in these samples. PepsiCo includes non-English international postings. Document the monitored board scope rather than implying every role in every geography is covered.
- **Changing endpoints:** successful hosts/site slugs are the exact ones in the evidence; prior candidate manifest labels may still say unverified and are historical discovery metadata. This updated report and saved results supersede those labels. No manifest or probe code was changed in this pass.
- **No HTML dependency:** all required job data is read from structured JSON; HTML-containing description strings need not be parsed. Keep optional unavailable fields null. No authenticated endpoint or bot bypass is needed by the demonstrated requests.

## FINAL SOURCE PLAN

**15 primary employers (KEEP):** Tyson Foods, KeyBank, PepsiCo, J.B. Hunt, Simmons Bank, Bank of America, JPMorgan Chase, Wells Fargo, Huntington Bank, Truist, PNC, U.S. Bank, Capital One, Fifth Third Bank, BMO.

**No backups remain:** Huntington Bank (audited total 710) and KeyBank (audited total 569) are primary.

**5 excluded sources:** Walmart (unresolved 2,000-result cap), Citi (unresolved 2,000-result cap), Regions Bank (tested endpoint 404), Nestlé (no validated endpoint), Arvest Bank (no validated endpoint).

**Primary ATS distribution:** 13 Workday CXS, 1 Oracle Recruiting Candidate Experience, 1 iCIMS/Jibe. Total: 13 Workday + 1 Oracle + 1 iCIMS/Jibe = 15 primary sources. Citi and Walmart’s original anonymous JSON access remains validated, but production completeness is not.

**Required search term:** JPMorgan Chase — `analyst`, observed 7,008 unfiltered / 1,003 filtered; **README disclosure required**. No other observed count exceeds 5,000. Walmart/Citi’s possible count caps remain an explicit uncertainty, not proof their boards are below that threshold.

**Fields to leave blank:** department/category for Tyson Foods, KeyBank, J.B. Hunt, Simmons Bank, Bank of America, Wells Fargo, Huntington Bank, Truist, PNC, U.S. Bank, Capital One and BMO. Fifth Third’s normalized department/category stays blank pending interpretation of its category-like bullet. Oracle Department is null, but JobFamily/JobFunction can populate a separate category field; literal apply URL is absent, so use its constructed job-detail URL and leave any separate application-only URL blank. Any optional field absent in a future record stays null rather than being recovered from HTML.

**Assignment verification:** all 15 primaries have HTTP 200 decoded JSON with real job IDs, titles and locations; structured date and job-detail/apply URL data are available or constructible. The supplied run is anonymous and has no token/login/HTML bootstrap dependency. The 15-employer anonymous JSON source requirement is met. This does not claim full-board pagination has been verified for PepsiCo or that all employers’ totals are uncapped.

## RECOMMENDED NEXT STEP

Use the revised registry for future production runs: Huntington Bank replaces Citi and KeyBank replaces Walmart; both capped boards are excluded and no backups remain. Validate KeyBank’s full dry-run from normal Terminal before the next production workflow. Cap failure guards remain in regression tests for both excluded boards. Existing Day 1 production files must remain unchanged during this registry-only pass. No network request, staging, commit or push was performed for this update. The original reconnaissance request records above remain unchanged.
