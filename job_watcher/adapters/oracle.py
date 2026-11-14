"""Public Candidate Experience search envelope, never employee/private REST."""

from urllib.parse import quote, urlsplit

from .base import AdapterError, converted, count, object_payload, records, required, text, unique_rows

# The saved finder requested 2, and the outer collection limit=200 belongs to
# search envelopes, not jobs. No job-page maximum is proven; use conservative 25.
ORACLE_PAGE_SIZE = 25
ORACLE_DRIFT_MIN_JOBS = 2


def drift_tolerance(reported_total):
    """Secondary raw-row shortfall/metadata tolerance, never a unique-ID cap."""
    return max(ORACLE_DRIFT_MIN_JOBS, reported_total // 200)


def unpack(body):
    items = records(object_payload(body).get("items"), "items")
    if len(items) != 1:
        raise AdapterError("expected one Oracle search envelope")
    root = items[0]
    return root, records(root.get("requisitionList"), "requisitionList")


class OracleAdapter:
    page_size = ORACLE_PAGE_SIZE

    def fetch(self, source, capture, *, max_pages=5000, **options):
        if source.key == "jpmorgan_chase" and source.search_term != "analyst":
            raise AdapterError("JPMorgan requires audited analyst search")
        if not source.site_number:
            raise AdapterError("missing Oracle public site number")
        offset, seen, expected, raw_fetched = 0, set(), None, 0
        for _ in range(max_pages):
            finder = f"findReqs;siteNumber={source.site_number},limit={self.page_size},offset={offset}"
            if source.search_term:
                finder += f",keyword={source.search_term}"
            body = capture.get("list", "GET", source.endpoint, params={
                "onlyData": "true", "expand": "requisitionList", "finder": finder})
            root, batch = unpack(body)
            total = count(root.get("TotalJobsCount"))
            if expected is None:
                expected = total
            elif abs(total - expected) > drift_tolerance(expected):
                raise AdapterError("Oracle total changed materially during pagination; retry source later")
            if root.get("Keyword") != source.search_term:
                raise AdapterError("Oracle response did not honor configured keyword")
            if root.get("Offset") != offset:
                raise AdapterError("Oracle response offset mismatch")
            effective_limit = count(root.get("Limit", self.page_size))
            if not 0 < effective_limit <= self.page_size:
                raise AdapterError("invalid Oracle job-page Limit")
            if len(batch) > effective_limit:
                raise AdapterError("Oracle returned more jobs than its job-page Limit")
            page_ids = {required(job.get("Id"), "Oracle Id") for job in batch}
            new_ids = page_ids - seen
            duplicates = len(batch) - len(new_ids)
            if duplicates and capture.progress:
                noun = "duplicate" if duplicates == 1 else "duplicates"
                capture.progress(f"page {capture.list_requests} added {len(new_ids)} new, {duplicates} {noun}")
            seen.update(new_ids)
            raw_fetched += len(batch)
            # Outer count/hasMore/limit/links paginate the search-envelope
            # collection, not requisitionList. The audited outer hasMore=False
            # coexists with 2 of 1003 jobs, so it cannot terminate this loop.
            if batch and not new_ids:
                raise AdapterError("Oracle pagination stalled: non-empty page added zero new unique IDs "
                                   f"(unique={len(seen)}, reported_total={expected}, offset={offset})")
            # Use inner job-page metadata, including a smaller server limit if
            # supplied. Raw/unique counts must not change the requested offset.
            next_offset = offset + effective_limit
            # Offsets start at zero and advance only after successful, validated
            # responses, so this proves every slot implied by the starting total
            # has been requested. Never use tolerance to stop a page early.
            if next_offset >= expected:
                shortfall = max(0, expected - raw_fetched)
                tolerance = drift_tolerance(expected)
                # TotalJobsCount counts result rows/slots, not necessarily unique
                # IDs. Overlaps explain raw-vs-normalized differences and never
                # consume churn tolerance. Only an actual raw shortfall needs
                # the small fallback, after every expected offset succeeded.
                raw_complete = raw_fetched >= expected
                churn_fallback = 0 < shortfall <= tolerance
                if (raw_complete or churn_fallback) and (seen or expected == 0):
                    if capture.progress:
                        message = (f"complete raw={raw_fetched} unique={len(seen)} "
                                   f"duplicates={raw_fetched - len(seen)} reported_total={expected}")
                        if raw_fetched != expected:
                            message += f" raw_drift={abs(raw_fetched - expected)}"
                        capture.progress(message)
                    return
                raise AdapterError("Oracle pagination count mismatch after complete offset traversal "
                                   f"(raw={raw_fetched}, unique={len(seen)}, "
                                   f"duplicates={raw_fetched - len(seen)}, reported_total={expected}, "
                                   f"raw_shortfall={shortfall}, tolerance={tolerance})")
            if not batch:
                raise AdapterError("Oracle pagination count mismatch: empty page before expected offsets covered "
                                   f"(unique={len(seen)}, reported_total={expected}, offset={offset})")
            offset = next_offset
        raise AdapterError("page safety limit reached; incomplete source")

    def convert(self, source, pages):
        by_id = {}
        for page in pages:
            if page["kind"] != "list":
                raise AdapterError("unexpected Oracle page kind")
            _, batch = unpack(page["response"])
            for job in batch:
                key = required(job.get("Id"), "Oracle Id")
                by_id.setdefault(key, job)
        output = []
        for key, job in by_id.items():
            category = text(job.get("JobFamily")) or text(job.get("JobFunction"))
            url = ("https://" + urlsplit(source.endpoint).netloc +
                   f"/hcmUI/CandidateExperience/en/sites/{source.site_number}/job/{quote(key, safe='')}")
            output.append(converted(source, key, job.get("Title"), job.get("PrimaryLocation"),
                                    category, job.get("PostedDate"), url))
        return unique_rows(output)
