"""Daily issue formatting and explicit gh publishing; no import-time network."""

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote

from .raw import utc_timestamp
from .schema import HISTORY_COLUMNS, HistoryRow, validate_date

MARKER_PREFIX = "<!-- job-watcher:daily:v1 date="


def marker(day):
    return MARKER_PREFIX + validate_date(day) + " -->"


def _text(value):
    value = " ".join(value.split())
    return re.sub(r"([\\`*_{}\[\]()#+.!<>|])", r"\\\1", value)


def format_issue(rows, day):
    """Latest rebuilt changes only; baseline first_run rows are not new."""
    validate_date(day)
    rows = sorted(rows, key=lambda row: row.posting_id)
    new = [r for r in rows if r.first_seen == day and not r.first_run]
    removed = [r for r in rows if r.removed_date == day and r.status == "removed"]
    lines = [marker(day), "", f"Job Watcher daily changes for {day} (UTC).", "", "## NEW POSTINGS", ""]
    for group, none, title in ((new, "No new postings.", ""),
                              (removed, "No removed postings.", "## REMOVED POSTINGS")):
        if title:
            lines += ["", title, ""]
        if not group:
            lines.append(none)
        for row in group:
            url = quote(row.url, safe=":/?&=%#@+;,~!$*()-._")
            lines.append(f"- [{_text(row.title)}](<{url}>) — {_text(row.employer)}")
    return "\n".join(lines) + "\n"


def owned_day(issue):
    """Only exact titled, marked project issues; never PRs or unrelated issues."""
    if "pull_request" in issue:
        return None
    title = issue.get("title")
    try:
        validate_date(title)
    except (ValueError, TypeError):
        return None
    body = issue.get("body") or ""
    if not isinstance(body, str) or body.splitlines()[:1] != [marker(title)]:
        return None
    return title


def select_previous(issues, day):
    eligible = [(owned_day(issue), issue) for issue in issues]
    eligible = [(date, issue) for date, issue in eligible if date and date < day]
    return max(eligible, key=lambda pair: (pair[0], pair[1]["number"]))[1] if eligible else None


def publish_daily(client, day, body):
    """Upsert today's owned issue, then close only the previous run's issue.

    Workflow concurrency serializes callers. If a previous close fails, a rerun
    updates the same current issue and retries the close without duplicating it.
    """
    if body.splitlines()[:1] != [marker(day)]:
        raise ValueError("daily issue body must begin with the project ownership marker")
    issues = client.list_issues()
    today = [issue for issue in issues if owned_day(issue) == day]
    if len(today) > 1:
        raise ValueError("multiple owned issues for this date; reconcile before publishing")
    if today:
        number = today[0]["number"]
        client.update_issue(number, body)  # Also reopens a closed current issue.
    else:
        number = client.create_issue(day, body)
    previous = select_previous(issues, day)
    if previous and previous.get("state") == "open":
        client.close_issue(previous["number"])
    return number


class GhIssues:
    """Use the workflow's GH_TOKEN/GITHUB_TOKEN; no PAT or tokens in raw files."""

    def __init__(self, repo):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("repo must be owner/repository")
        self.endpoint = f"repos/{repo}/issues"

    def _call(self, command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("GitHub CLI request failed; check workflow permissions/run logs") from exc
        return json.loads(result.stdout)

    def _write(self, method, endpoint, payload):
        # Structured JSON input preserves newlines literally; no shell expansion.
        with tempfile.TemporaryDirectory(prefix="job-watcher-issue-") as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return self._call(["gh", "api", "--method", method, endpoint, "--input", str(path)])

    def list_issues(self):
        pages = self._call(["gh", "api", "--paginate", "--slurp",
                            self.endpoint + "?state=all&per_page=100"])
        return [issue for page in pages for issue in page]

    def create_issue(self, title, body):
        return self._write("POST", self.endpoint, {"title": title, "body": body})["number"]

    def update_issue(self, number, body):
        self._write("PATCH", f"{self.endpoint}/{int(number)}", {"body": body, "state": "open"})

    def close_issue(self, number):
        self._write("PATCH", f"{self.endpoint}/{int(number)}", {"state": "closed"})


def load_issue_content(data_dir):
    """Read latest derived outputs for publishing, never for history rebuilding."""
    data_dir = Path(data_dir)
    status = json.loads((data_dir / "status.json").read_text(encoding="utf-8"))
    instant = datetime.fromisoformat(status["run_time"].replace("Z", "+00:00"))
    day = utc_timestamp(instant)[:10]
    rows = []
    with (data_dir / "history.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(HISTORY_COLUMNS):
            raise ValueError("unexpected history.csv columns")
        for record in reader:
            for name in ("in_role", "first_run"):
                if record[name] not in ("true", "false"):
                    raise ValueError("unexpected history boolean")
                record[name] = record[name] == "true"
            rows.append(HistoryRow(**record))
    return day, format_issue(rows, day)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish the latest pipeline run's dated GitHub Issue")
    parser.add_argument("--repo", help="owner/repository; required when publishing")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--preview", action="store_true", help="print prepared issue content without contacting GitHub")
    args = parser.parse_args(argv)
    if not args.preview and not args.repo:
        parser.error("--repo is required unless --preview is used")
    day, body = load_issue_content(args.data_dir)
    if args.preview:
        print(f"Title: {day}\n\n{body}", end="")
        return 0
    number = publish_daily(GhIssues(args.repo), day, body)
    print(f"Daily issue {day}: #{number} updated; previous project run closed if open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
