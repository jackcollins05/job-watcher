"""PepsiCo's observed iCIMS/Jibe jobs[].data JSON, not authenticated iCIMS."""

from .base import AdapterError, converted, count, object_payload, records, required, text, unique_rows

# The audit validated limit=2 only, not a maximum. Use a conservative production
# limit of 20; page>1 still requires explicit validation against the live board.
JIBE_PAGE_SIZE = 20


def unpack(body):
    body = object_payload(body)
    return [object_payload(x.get("data")) for x in records(body.get("jobs"), "jobs")]


class JibeAdapter:
    page_size = JIBE_PAGE_SIZE

    def fetch(self, source, capture, *, max_pages=5000, validate_pepsico_pagination=False, **options):
        seen, seen_pages = set(), set()
        first_total = minimum = maximum = None
        raw_fetched = 0
        for page_number in range(1, max_pages + 1):
            body = capture.get("list", "GET", source.endpoint, params={
                "lang": "en-us", "limit": self.page_size, "page": page_number})
            batch = unpack(body)
            if len(batch) > self.page_size:
                raise AdapterError("PepsiCo returned more jobs than requested limit")
            total = count(body.get("totalCount"))
            if first_total is None:
                first_total = minimum = maximum = total
            minimum, maximum = min(minimum, total), max(maximum, total)
            page_ids = frozenset(self.identity(job) for job in batch)
            new_ids = page_ids - seen
            duplicates = len(batch) - len(new_ids)
            if duplicates and capture.progress:
                noun = "duplicate" if duplicates == 1 else "duplicates"
                capture.progress(f"page {page_number} added {len(new_ids)} new, {duplicates} {noun}")
            if batch and page_ids in seen_pages:
                raise AdapterError("PepsiCo repeated result set; pagination stalled")
            if batch and not new_ids:
                raise AdapterError("PepsiCo pagination stalled: zero new stable IDs")
            seen_pages.add(page_ids)
            seen.update(new_ids)
            raw_fetched += len(batch)
            # No next/total-pages flag is present in the audit. Reconcile global
            # totalCount, never the differently scoped count/languageCounts.
            tolerance = max(2, first_total // 200)  # 0.5%, integer rows.
            slots_covered = page_number * self.page_size >= maximum - tolerance
            counts_reached = raw_fetched >= maximum and slots_covered
            end_signal = not batch or (len(batch) < self.page_size and slots_covered) or counts_reached
            if end_signal:
                # Raw rows can exceed the total by deduplicated overlaps; do not
                # mistake explained duplicates for growth in unique postings.
                lower_ok = raw_fetched >= minimum or (
                    validate_pepsico_pagination and page_number > 1 and
                    minimum - raw_fetched <= tolerance)
                consistent = (maximum - minimum <= tolerance and lower_ok and
                              len(seen) <= maximum + tolerance and slots_covered and
                              (seen or maximum == 0))
                if consistent:
                    if capture.progress:
                        capture.progress(
                            f"complete raw={raw_fetched} unique={len(seen)} "
                            f"duplicates={raw_fetched-len(seen)} total_start={first_total} "
                            f"total_end={total} total_min={minimum} total_max={maximum} "
                            f"pages={page_number} drift={total-first_total}")
                    return
                raise AdapterError(
                    "PepsiCo end/count metadata inconsistent; incomplete source "
                    f"(raw={raw_fetched}, unique={len(seen)}, pages={page_number}, "
                    f"total_start={first_total}, total_end={total}, "
                    f"total_min={minimum}, total_max={maximum}, tolerance={tolerance})")
            capture.check_smoke_limit()
            if not validate_pepsico_pagination:
                raise AdapterError("PepsiCo page>1 unvalidated in audit; use explicit dry-run validation flag")
        raise AdapterError("page safety limit reached; incomplete source")

    @staticmethod
    def identity(job):
        key = required(job.get("req_id"), "PepsiCo req_id")
        language = required(job.get("language"), "PepsiCo language")
        # Length prefix avoids ambiguity without replacing the real source ID.
        return f"{len(key)}:{key}:{language}"

    def convert(self, source, pages):
        by_id = {}
        for page in pages:
            if page["kind"] != "list":
                raise AdapterError("unexpected PepsiCo page kind")
            for job in unpack(page["response"]):
                by_id.setdefault(self.identity(job), job)
        output = []
        for key, job in by_id.items():
            cats = job.get("categories") or []
            categories = records(cats, "categories")
            category = "; ".join(text(x.get("name")) for x in categories if text(x.get("name")))
            location = text(job.get("full_location")) or ", ".join(
                text(job.get(k)) for k in ("city", "state", "country") if text(job.get(k)))
            location = location or text(job.get("location_name"))
            meta = job.get("meta_data") or {}
            meta = object_payload(meta)
            output.append(converted(source, key, job.get("title"), location,
                                    category, job.get("posted_date"),
                                    meta.get("canonical_url") or job.get("apply_url")))
        return unique_rows(output)
