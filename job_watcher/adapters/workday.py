"""Workday list-only fetches, safe row skipping and explicit cap failures."""

import json
import re
from urllib.parse import unquote, urlsplit

from .base import (AdapterError, converted, count, object_payload, required,
                   text, unique_rows, public_url)

WORKDAY_PAGE_SIZE = 20
# The audit's tiny limit bounded reconnaissance; it is not a production limit.


def _valid_path(value):
    if not isinstance(value, str) or not value.startswith('/job/'):
        return None
    if any(ord(c) <= 32 for c in value) or any(c in value for c in ('?', '#', '\\')):
        return None
    decoded = unquote(value)
    if (not decoded.removeprefix('/job/').strip('/') or decoded.endswith('/') or
            any(ord(c) < 32 for c in decoded) or '\\' in decoded or
            any(part in ('.', '..') for part in decoded.split('/'))):
        return None
    return value


def _configuration(source):
    parts = source.endpoint.split('/wday/cxs/')[1].split('/')
    return urlsplit(source.endpoint).hostname, parts[0], parts[1]


def _provided_url(source, value):
    """Accept a literal response URL only within this board's known URL family."""
    if not value:
        return None, None
    try:
        value = public_url(value)
        parsed = urlsplit(value)
        host, tenant, site = _configuration(source)
        if parsed.port not in (None, 443) or parsed.query or parsed.fragment:
            return None, None
        prefixes = []
        if parsed.hostname == host or re.fullmatch(re.escape(tenant) + r'\.wd\d+\.myworkdayjobs\.com', parsed.hostname or ''):
            prefixes = [f'/{site}']
            match = re.match(r'/[a-z]{2}(?:-[A-Z]{2})?/', parsed.path)
            if match:
                prefixes.append(match.group(0).rstrip('/') + '/' + site)
        elif re.fullmatch(r'wd\d+\.myworkdaysite\.com', parsed.hostname or ''):
            prefixes = [f'/recruiting/{tenant}/{site}']
        for prefix in prefixes:
            if parsed.path.startswith(prefix + '/job/'):
                path = _valid_path(parsed.path[len(prefix):])
                if path:
                    return value, path
    except (ValueError, AdapterError):
        pass
    return None, None


def listing_identity(job):
    """A real requisition ID, optionally qualified by a real posting suffix."""
    if not isinstance(job, dict):
        raise AdapterError('missing Workday stable source ID')
    bullets = job.get('bulletFields')
    core = text(bullets[0]) if isinstance(bullets, list) and bullets else ''
    core = core or text(job.get('jobReqId'))
    source_id = required(core, 'Workday stable source ID')
    path = _valid_path(job.get('externalPath'))
    if path:
        token = path.rsplit('_', 1)[-1]
        if token == core or token.startswith(core + '-'):
            source_id = token
    return source_id, path


def _batch(body):
    batch = object_payload(body).get('jobPostings')
    if not isinstance(batch, list):
        raise AdapterError('expected jobPostings array')
    return batch


def _row(source, job):
    source_id, path = listing_identity(job)
    title = required(job.get('title'), 'title')
    url, supplied_path = _provided_url(source, job.get('externalUrl'))
    if path and supplied_path != path:
        url = None  # Never attach another posting's response URL to this ID.
    if not path:
        if not url or not text(job.get('locationsText')):
            raise AdapterError('no usable externalPath or supported response job URL')
        path = supplied_path
        core, _ = listing_identity(job)
        token = path.rsplit('_', 1)[-1]
        if token == core or token.startswith(core + '-'):
            source_id = token
    if not url:
        host, _, site = _configuration(source)
        url = f'https://{host}/{site}{path}'
    return source_id, path, title, url


def _collect(source, pages):
    listings, details = {}, {}
    observed_paths = set()
    skipped, unresolved, unidentified, raw_rows = 0, set(), 0, 0
    for page in pages:
        body = object_payload(page['response'])
        if page['kind'] == 'list':
            for job in _batch(body):
                raw_rows += 1
                path = _valid_path(job.get('externalPath')) if isinstance(job, dict) else None
                if path:
                    observed_paths.add(path)
                try:
                    source_id, path, title, url = _row(source, job)
                except AdapterError:
                    skipped += 1
                    try:
                        missing_id, _ = listing_identity(job)
                        unresolved.add(missing_id)
                    except AdapterError:
                        unidentified += 1
                    continue
                listings.setdefault(source_id, (path, job, title, url))
                observed_paths.add(path)
        elif page['kind'] == 'detail':
            info = object_payload(body.get('jobPostingInfo'))
            path = page['request']['url'].removeprefix(source.endpoint.removesuffix('/jobs'))
            if path in details:
                raise AdapterError('duplicate Workday detail')
            details[path] = info
        else:
            raise AdapterError('unexpected Workday page kind')
    if set(details) - observed_paths:
        raise AdapterError('orphan Workday detail responses')
    diagnostics = {'skipped_malformed': skipped, 'unresolved_source_ids': sorted(unresolved),
                   'removals_safe': unidentified == 0, 'unidentified_malformed': unidentified}
    return listings, details, diagnostics, raw_rows


class WorkdayAdapter:
    page_size = WORKDAY_PAGE_SIZE

    def diagnostics(self, source, pages):
        return _collect(source, pages)[2]

    def fetch(self, source, capture, *, max_pages=5000, **options):
        offset, seen, initial_total = 0, set(), None
        seen_pages, stable_total = set(), True

        def capped():
            return source.capped_total_risk and initial_total == 2000

        def cap_failure():
            raise AdapterError('2000-job board cap unresolved; exhaustive JSON partitions not validated',
                               failure_class='board_cap_unresolved')

        def total_reached():
            return (initial_total is not None and initial_total > 0 and stable_total
                    and not source.capped_total_risk and len(seen) >= initial_total)

        def complete():
            listings, _, diagnostics, raw_rows = _collect(source, capture.pages)
            if raw_rows and not listings:
                raise AdapterError('all Workday postings malformed: no usable stable source ID/title/public URL',
                                   failure_class='malformed_postings')
            if capture.progress:
                if diagnostics['skipped_malformed']:
                    capture.progress(f"skipped {diagnostics['skipped_malformed']} malformed postings with no usable identity/title/job URL")
                capture.progress(f'complete unique={len(seen)} reported_total={initial_total}')

        for _ in range(max_pages):
            if total_reached():
                complete()
                return
            body = capture.get('list', 'POST', source.endpoint, payload={
                'appliedFacets': {}, 'limit': self.page_size, 'offset': offset,
                'searchText': source.search_term})
            batch = _batch(body)
            total = count(body.get('total'))
            if initial_total is None:
                initial_total = total
                if total > 5000 and not source.search_term:
                    raise AdapterError('board exceeds 5000; requires audited search configuration')
            if total > 0 and total != initial_total:
                stable_total = False
            if not batch:
                if len(seen) < initial_total:
                    raise AdapterError('empty page before initial total; incomplete source')
                if capped():
                    cap_failure()
                complete()
                return
            page_ids = set()
            for job in batch:
                try:
                    key, _ = listing_identity(job)
                    page_ids.add(('source_id', key))
                except AdapterError:
                    # Only a loop fingerprint for unidentified raw rows. NEVER
                    # used as a source ID, normalized posting ID or history row.
                    page_ids.add(('unidentified_raw_row', json.dumps(job, sort_keys=True)))
            page_ids = frozenset(page_ids)
            new_ids = page_ids - seen
            duplicates = len(batch) - len(new_ids)
            if duplicates and capture.progress:
                noun = 'duplicate' if duplicates == 1 else 'duplicates'
                capture.progress(f'page {capture.list_requests} added {len(new_ids)} new, {duplicates} {noun}')
            if page_ids in seen_pages or not new_ids:
                if capped():
                    cap_failure()
                reason = 'repeated Workday page/result set' if page_ids in seen_pages else 'non-empty page added zero new unique postings'
                raise AdapterError(f'pagination stalled: {reason} (unique={len(seen)}, reported_total={initial_total}, offset={offset}, page_size={self.page_size})',
                                   failure_class='pagination_stalled')
            seen_pages.add(page_ids)
            seen.update(new_ids)
            if total_reached():
                complete()
                return
            offset += self.page_size
        raise AdapterError('page safety limit reached; incomplete source', failure_class='pagination_stalled')

    def convert(self, source, pages):
        listings, details, diagnostics, raw_rows = _collect(source, pages)
        if raw_rows and not listings:
            raise AdapterError('all Workday postings malformed: no usable stable source ID/title/public URL',
                               failure_class='malformed_postings')
        output = []
        for source_id, (path, job, title, url) in listings.items():
            info = details.get(path, {})
            locations = [text(info.get('location')) or text(job.get('locationsText'))]
            extra = info.get('additionalLocations') or []
            if not isinstance(extra, list) or any(not isinstance(x, str) for x in extra):
                extra = []
            locations += extra
            supplied_url, supplied_path = _provided_url(source, info.get('externalUrl'))
            if supplied_path != path:
                supplied_url = None
            output.append(converted(source, source_id, title,
                                    '; '.join(dict.fromkeys(x for x in locations if x)), '',
                                    info.get('startDate') or job.get('postedOn'), supplied_url or url))
        return unique_rows(output)
