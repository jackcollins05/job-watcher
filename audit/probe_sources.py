#!/usr/bin/env python3
"""Bounded source reconnaissance using curl; no harvesting or HTML parsing.

Run from the project root: python3 audit/probe_sources.py
Only the endpoints in sources.json are contacted. Results are overwritten.
"""

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parent
MAX_CALLS_PER_SOURCE = 4
DELAY_SECONDS = 1.0


def request(source, purpose, *, term="", offset=0, url=None, method=None):
    method = method or source["method"]
    endpoint = url or source["endpoint"]
    params = None
    payload = None
    if purpose != "detail":
        if source["family"] == "workday":
            payload = {"appliedFacets": {}, "limit": 2,
                       "offset": offset, "searchText": term}
        elif source["family"] == "oracle":
            finder = f"findReqs;siteNumber=CX_1001,limit=2,offset={offset}"
            if term:
                finder += f",keyword={term}"
            params = {"onlyData": "true", "expand": "requisitionList",
                      "finder": finder}
        elif source["family"] == "jibe_candidate":
            params = {"lang": "en-us", "limit": 2,
                      "page": offset // 2 + 1}
            if term:
                params["keywords"] = term
    if params:
        endpoint += "?" + urlencode(params)
    record = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": purpose, "method": method, "url": endpoint,
        "payload": payload, "search_term": term,
        "http_status": None, "content_type": None,
        "json_confirmed": False,
    }
    with tempfile.TemporaryDirectory(prefix="job-watcher-audit-") as temp:
        body_path = Path(temp) / "body"
        command = [
            "curl", "-q", "--silent", "--show-error",
            "--connect-timeout", "8", "--max-time", "20", "--retry", "0",
            "--max-filesize", "1048576", "--proto", "=https",
            "--request", method, "--header", "Accept: application/json",
            "--output", str(body_path),
            "--write-out", "%{http_code}\n%{content_type}\n%{url_effective}",
        ]
        if payload is not None:
            command += ["--header", "Content-Type: application/json",
                        "--data", json.dumps(payload)]
        command.append(endpoint)
        # Do not inherit proxy credentials or user configuration.
        env = {key: os.environ[key] for key in
               ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE",
                "SSL_CERT_DIR", "CURL_CA_BUNDLE") if key in os.environ}
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=23, env=env, check=False)
            record["curl_exit_code"] = completed.returncode
            record["error"] = completed.stderr.strip() or None
            metadata = completed.stdout.splitlines()
            if metadata and metadata[0].isdigit() and metadata[0] != "000":
                record["http_status"] = int(metadata[0])
            if len(metadata) > 1:
                record["content_type"] = metadata[1] or None
            data = body_path.read_bytes() if body_path.exists() else b""
            record["response_bytes"] = len(data)
            media_type = (record["content_type"] or "").split(";")[0].lower()
            if media_type == "application/json" or media_type.endswith("+json"):
                try:
                    document = json.loads(data)
                    record["json_confirmed"] = True
                    record["json_response"] = document
                except (ValueError, UnicodeError) as error:
                    record["json_error"] = str(error)
            # Non-JSON bodies are discarded, never parsed or persisted.
        except (OSError, subprocess.TimeoutExpired) as error:
            record["error"] = str(error)
    print(f"{source['employer']}: {purpose}: HTTP {record['http_status']} "
          f"JSON={record['json_confirmed']} {record.get('error') or ''}", flush=True)
    time.sleep(DELAY_SECONDS)
    return record


def extract(source, result):
    document = result.get("json_response")
    if not isinstance(document, dict):
        return None, []
    if source["family"] == "workday":
        return document.get("total"), document.get("jobPostings", [])
    if source["family"] == "oracle":
        items = document.get("items", [])
        root = items[0] if items and isinstance(items[0], dict) else {}
        return root.get("TotalJobsCount"), root.get("requisitionList", [])
    # Jibe schema is deliberately not assumed: inspect the retained JSON.
    return None, []


def main():
    sources = json.loads((ROOT / "sources.json").read_text())
    report = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "limits": {"max_requests_per_source": MAX_CALLS_PER_SOURCE,
                         "timeout_seconds": 20, "delay_seconds": DELAY_SECONDS,
                         "max_response_bytes": 1048576}, "sources": []}
    for source in sources:
        entry = {"employer": source["employer"], "requests": []}
        report["sources"].append(entry)
        if not source.get("endpoint"):
            entry["skipped"] = "No JSON endpoint identified; no request fabricated."
            continue
        base = request(source, "unfiltered")
        entry["requests"].append(base)
        if base["http_status"] != 200 or not base["json_confirmed"]:
            continue
        count, jobs = extract(source, base)
        entry["unfiltered_count"] = count
        entry["sample_keys"] = sorted(jobs[0]) if jobs and isinstance(jobs[0], dict) else []
        term = ""
        if isinstance(count, (int, float)) and count > 5000:
            term = "analyst"
            searched = request(source, "search", term=term)
            entry["requests"].append(searched)
            if searched["http_status"] != 200 or not searched["json_confirmed"]:
                continue
            entry["search_count"], jobs = extract(source, searched)
        scoped_count = entry.get("search_count") if term else count
        next_offset = 2 if isinstance(scoped_count, (int, float)) and scoped_count > 2 else 0
        repeated = request(source, "pagination_or_repeat", term=term, offset=next_offset)
        entry["requests"].append(repeated)
        if repeated["http_status"] != 200 or not repeated["json_confirmed"]:
            continue
        if source["family"] == "workday" and jobs:
            path = jobs[0].get("externalPath")
            if isinstance(path, str) and path.startswith("/job/"):
                detail_url = source["endpoint"].removesuffix("/jobs") + path
                entry["requests"].append(request(source, "detail", url=detail_url, method="GET"))
        assert len(entry["requests"]) <= MAX_CALLS_PER_SOURCE
    report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {ROOT / 'results.json'}")


if __name__ == "__main__":
    main()
