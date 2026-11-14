"""Workday list-only fetches; optional saved details remain replayable."""

from urllib.parse import urlsplit

from .base import (AdapterError, converted, count, object_payload, records,
                   required, text, unique_rows)

# The audit's limit=2 bounded reconnaissance, not production throughput.
# No maximum was established there; 20 is a conservative CXS production choice.
WORKDAY_PAGE_SIZE = 20


def listing_identity(job):
    """Use the same stable source identity for pagination and conversion."""
    path = required(job.get("externalPath"), "externalPath")
    if not path.startswith("/job/") or "?" in path or "#" in path or "/../" in path:
        raise AdapterError("invalid Workday externalPath")
    bullets = job.get("bulletFields")
    if not isinstance(bullets, list) or not bullets:
        raise AdapterError("missing Workday stable source ID (bulletFields[0])")
    source_id = required(bullets[0], "Workday stable source ID")
    token = path.rsplit("_", 1)[-1]
    if token == source_id or token.startswith(source_id + "-"):
        source_id = token
    return source_id, path


class WorkdayAdapter:
    page_size = WORKDAY_PAGE_SIZE

    def fetch(self, source, capture, *, max_pages=5000, **options):
        offset, seen, initial_total = 0, set(), None
        seen_pages = set()
        stable_total = True

        def total_reached():
            # Public CXS puts the real count on offset=0; later zero totals are
            # placeholders, not contradictory board counts. Known capped boards
            # and changing positive totals cannot prove completion this way.
            return (initial_total is not None and initial_total > 0 and stable_total
                    and not source.capped_total_risk and len(seen) >= initial_total)

        def complete():
            if capture.progress:
                capture.progress(f"complete unique={len(seen)} reported_total={initial_total}")

        for _ in range(max_pages):
            if total_reached():
                complete()
                return
            body = capture.get("list", "POST", source.endpoint, payload={
                "appliedFacets": {}, "limit": self.page_size, "offset": offset,
                "searchText": source.search_term})
            batch = records(body.get("jobPostings"), "jobPostings")
            total = count(body.get("total"))
            if initial_total is None:
                initial_total = total
                if total > 5000 and not source.search_term:
                    raise AdapterError("board exceeds 5000; requires audited search configuration")
            if total > 0:
                if total != initial_total:
                    stable_total = False
            # Offset pages often report zero total despite returning real jobs.
            if not batch:
                if len(seen) < initial_total:
                    raise AdapterError("empty page before initial total; incomplete source")
                if source.capped_total_risk and initial_total == 2000:
                    raise AdapterError("2000 total may be capped; complete board coverage unvalidated")
                complete()
                return
            page_ids = frozenset(listing_identity(job)[0] for job in batch)
            new_ids = page_ids - seen
            duplicates = len(batch) - len(new_ids)
            if duplicates and capture.progress:
                noun = "duplicate" if duplicates == 1 else "duplicates"
                capture.progress(f"page {capture.list_requests} added {len(new_ids)} new, {duplicates} {noun}")
            if page_ids in seen_pages:
                raise AdapterError("pagination stalled: repeated Workday page/result set "
                                   f"(unique={len(seen)}, reported_total={initial_total}, "
                                   f"offset={offset}, page_size={self.page_size})")
            if not new_ids:
                raise AdapterError("pagination stalled: non-empty page added zero new unique postings "
                                   f"(unique={len(seen)}, reported_total={initial_total}, "
                                   f"offset={offset}, page_size={self.page_size})")
            seen_pages.add(page_ids)
            seen.update(new_ids)
            # Includes a final partial page consistent with the first-page total.
            # Check before requesting another page, so boundary repeats do not
            # turn an already complete board into a false stall.
            if total_reached():
                complete()
                return
            offset += self.page_size
        else:
            raise AdapterError("page safety limit reached; incomplete source")
        # Required IDs, titles, locations and URL paths are already in the list.
        # Do not make one detail request per job for optional dates/enrichment.

    def convert(self, source, pages):
        listings, details, all_paths = {}, {}, set()
        for page in pages:
            body = object_payload(page["response"])
            if page["kind"] == "list":
                for job in records(body.get("jobPostings"), "jobPostings"):
                    source_id, path = listing_identity(job)
                    all_paths.add(path)
                    # First observed record wins deterministically. Preserve
                    # every raw page, but produce only one row per stable ID.
                    listings.setdefault(source_id, (path, job))
            elif page["kind"] == "detail":
                info = object_payload(body.get("jobPostingInfo"))
                path = page["request"]["url"].removeprefix(source.endpoint.removesuffix("/jobs"))
                if path in details:
                    raise AdapterError("duplicate Workday detail")
                details[path] = info
            else:
                raise AdapterError("unexpected Workday page kind")
        if set(details) - all_paths:
            raise AdapterError("orphan Workday detail responses")
        output = []
        for source_id, (path, job) in listings.items():
            info = details.get(path, {})
            locations = [text(info.get("location")) or text(job.get("locationsText"))]
            extra = info.get("additionalLocations") or []
            if not isinstance(extra, list) or any(not isinstance(x, str) for x in extra):
                raise AdapterError("invalid additionalLocations")
            locations += extra
            locations = list(dict.fromkeys(x for x in locations if x))
            url = info.get("externalUrl")
            if not url:
                parts = source.endpoint.split("/wday/cxs/")[1].split("/")
                url = "https://" + urlsplit(source.endpoint).netloc + "/" + parts[1] + path
            # No audited structured category; do not interpret positional bullets.
            output.append(converted(source, source_id, job.get("title"),
                                    "; ".join(locations), "",
                                    info.get("startDate") or job.get("postedOn"), url))
        return unique_rows(output)
