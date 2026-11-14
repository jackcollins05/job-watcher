"""Shared offline conversion contracts and bounded anonymous JSON transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, date
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Protocol
from urllib.parse import urlencode, urlsplit

from ..role import in_role
from ..schema import Posting, posting_id


class AdapterError(ValueError):
    """Invalid response or incomplete pagination; never a successful snapshot."""


class SmokeLimitReached(Exception):
    """Explicit manual dry-run page budget, never production completeness."""


@dataclass(frozen=True)
class ConvertedPosting:
    posting_id: str
    source: str
    source_id: str
    employer: str
    title: str
    location: str
    department: str
    posted_date: str
    url: str
    in_role: bool

    def as_posting(self) -> Posting:
        return Posting(self.source_id, self.employer, self.title, self.location,
                       self.url, self.department, self.posted_date)


def text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def required(value, name: str) -> str:
    result = text(value)
    if not result:
        raise AdapterError(f"missing/invalid {name}")
    return result


def public_url(value) -> str:
    value = required(value, "public URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AdapterError("public URL must be anonymous HTTPS")
    return value


def normalized_date(value) -> str:
    value = text(value)
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo:
            instant = instant.astimezone(timezone.utc)
        return instant.date().isoformat()
    except ValueError:
        return ""


def converted(source, source_id, title, location, department, posted_date, url):
    source_id = required(source_id, "stable source ID")
    title = required(title, "title")
    return ConvertedPosting(posting_id(source.key, source_id), source.key, source_id,
                            source.employer, title, text(location), text(department),
                            normalized_date(posted_date), public_url(url), in_role(title))


def object_payload(payload):
    if not isinstance(payload, dict):
        raise AdapterError("expected JSON object")
    if "errorCode" in payload or "error" in payload:
        raise AdapterError("API returned an error envelope")
    return payload


def records(value, name):
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise AdapterError(f"expected {name} array of objects")
    return value


def count(value):
    if type(value) is not int or value < 0:
        raise AdapterError("missing/invalid total count")
    return value


def unique_rows(rows):
    rows = sorted(rows, key=lambda p: p.posting_id)
    if len({p.posting_id for p in rows}) != len(rows):
        raise AdapterError("duplicate posting IDs; refusing ambiguous snapshot")
    return rows


class Transport(Protocol):
    def request(self, method, url, *, params=None, payload=None) -> dict: ...


class JsonTransport:
    """Use the audit probe's curl/TLS stack and hard wall-clock deadlines.

    Anonymous standalone GET/POST: no curlrc, proxy credentials, cookie jar,
    redirects or compression negotiation. One bounded retry for transient curl
    errors or HTTP 429/502/503/504. Never reuse employer session state.
    """

    def __init__(self, timeout=20, delay=0.25, max_requests=15000, connect_timeout=8):
        if timeout <= 0 or connect_timeout <= 0 or delay < 0 or max_requests < 1:
            raise ValueError("transport limits must be positive (delay may be zero)")
        self.timeout, self.delay, self.remaining = timeout, delay, max_requests
        self.connect_timeout = connect_timeout

    def _attempt(self, method, url, payload):
        with tempfile.TemporaryDirectory(prefix="job-watcher-http-") as temp:
            body_path = Path(temp) / "body"
            header_path = Path(temp) / "headers"
            command = [
                "curl", "-q", "--silent", "--show-error",
                "--connect-timeout", str(self.connect_timeout),
                "--max-time", str(self.timeout), "--retry", "0",
                "--max-filesize", "16777216", "--proto", "=https",
                "--request", method, "--header", "Accept: application/json",
                "--user-agent", "JobWatcher/0.1 (public job source audit)",
                "--output", str(body_path), "--dump-header", str(header_path),
                "--write-out", "%{http_code}\n%{content_type}\n%{url_effective}",
            ]
            if payload is not None:
                command += ["--header", "Content-Type: application/json",
                            "--data", json.dumps(payload)]
            command.append(url)
            # Same environment allowlist as the working audit probe. Do not
            # inherit proxy URLs/credentials, curl config or a cookie store.
            env = {key: os.environ[key] for key in
                   ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE",
                    "SSL_CERT_DIR", "CURL_CA_BUNDLE") if key in os.environ}
            try:
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=self.timeout + 3, env=env, check=False)
            except subprocess.TimeoutExpired as exc:
                raise AdapterError(f"request timed out (process deadline {self.timeout + 3}s)") from exc
            except OSError as exc:
                raise AdapterError(f"could not execute curl ({type(exc).__name__})") from exc
            metadata = completed.stdout.splitlines()
            status = int(metadata[0]) if metadata and metadata[0].isdigit() else 0
            mime = metadata[1].split(";", 1)[0].strip().lower() if len(metadata) > 1 else ""
            retry_after = "1"
            if header_path.exists():
                # Headers are temporary and never enter raw snapshots or errors.
                for line in header_path.read_text(encoding="iso-8859-1").splitlines():
                    if line.lower().startswith("retry-after:"):
                        retry_after = line.split(":", 1)[1].strip()
            # curl's max-filesize also bounds downloads; guard independently
            # when reading the file, including with older curl versions.
            body = b""
            if body_path.exists():
                with body_path.open("rb") as handle:
                    body = handle.read(16777217)
            if len(body) > 16777216:
                raise AdapterError("response exceeded size limit")
            return completed.returncode, status, mime, retry_after, body

    def request(self, method, url, *, params=None, payload=None):
        public_url(url)
        if method not in ("GET", "POST"):
            raise AdapterError("unsupported request method")
        if params:
            url += "?" + urlencode(params)
        for attempt in range(2):
            if self.remaining <= 0:
                raise AdapterError("request safety limit reached; incomplete source")
            self.remaining -= 1
            time.sleep(self.delay)
            code, status, mime, retry_after, body = self._attempt(method, url, payload)
            if code:
                if code == 28:
                    reason = f"request timed out (curl total deadline {self.timeout}s)"
                else:
                    reason = f"curl transport failure (exit {code})"
                if not attempt and code in (5, 6, 7, 28, 52, 56):
                    time.sleep(1)
                    continue
                raise AdapterError(reason)
            if not 200 <= status < 300:
                if not attempt and status in (429, 502, 503, 504):
                    if not retry_after.isdigit() or int(retry_after) > 10:
                        raise AdapterError(f"HTTP {status}; retry deferred")
                    time.sleep(int(retry_after))
                    continue
                raise AdapterError(f"HTTP {status}")
            if mime != "application/json" and not mime.endswith("+json"):
                raise AdapterError("response is not JSON")
            try:
                document = json.loads(body)
            except (ValueError, UnicodeError) as exc:
                raise AdapterError("invalid JSON response") from exc
            return object_payload(document)


class Capture:
    """Keep every successful JSON response and its safe request metadata."""

    def __init__(self, transport, pages, *, smoke_max_pages=None, progress=None):
        self.transport, self.pages = transport, pages
        self.smoke_max_pages, self.progress = smoke_max_pages, progress
        self.list_requests = 0
        self.detail_requests = 0

    def check_smoke_limit(self):
        if self.smoke_max_pages is not None and self.list_requests >= self.smoke_max_pages:
            raise SmokeLimitReached()

    def get(self, kind, method, url, *, params=None, payload=None):
        if kind == "list":
            self.check_smoke_limit()
            self.list_requests += 1
            if self.progress:
                self.progress(f"fetching page {self.list_requests}...")
        elif kind == "detail":
            self.detail_requests += 1
            if self.progress and (self.detail_requests == 1 or self.detail_requests % 25 == 0):
                self.progress(f"fetching detail {self.detail_requests}...")
        response = self.transport.request(method, url, params=params, payload=payload)
        self.pages.append({"kind": kind, "request": {"method": method, "url": url,
                           "params": params, "payload": payload}, "response": response})
        return object_payload(response)
