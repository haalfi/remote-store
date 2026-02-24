#!/usr/bin/env python3
"""Gather and display statistics for the remote-store project.

Pulls data from three sources:
  1. GitHub API  – repo metadata, stars, forks, issues, contributors
  2. PyPI JSON API – releases, package sizes, Python classifiers
  3. PyPI Stats / pepy.tech – download counts

Usage::

    python scripts/repo_stats.py            # print to stdout
    python scripts/repo_stats.py --json     # machine-readable JSON
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

GITHUB_OWNER = "haalfi"
GITHUB_REPO = "remote-store"
PYPI_PACKAGE = "remote-store"
RTD_PROJECT = "remote-store"

GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
PYPI_API = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"
PYPISTATS_API = f"https://pypistats.org/api/packages/{PYPI_PACKAGE}/recent"
RTD_API = f"https://readthedocs.org/api/v3/projects/{RTD_PROJECT}/"
RTD_BUILDS_URL = f"https://readthedocs.org/api/v3/projects/{RTD_PROJECT}/builds/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, *, token: str | None = None) -> dict[str, Any] | None:
    """Fetch JSON from *url*, returning ``None`` on any HTTP error."""
    headers = {"Accept": "application/json", "User-Agent": "remote-store-stats/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"  [warn] {url}: {exc}", file=sys.stderr)
        return None


def _iso(dt_str: str | None) -> str:
    """Return a human-friendly date or '—'."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return dt_str


def _size_human(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class GitHubStats:
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    size_kb: int = 0
    language: str = "—"
    license: str = "—"
    default_branch: str = "—"
    created_at: str = "—"
    updated_at: str = "—"
    pushed_at: str = "—"
    description: str = "—"
    topics: list[str] = field(default_factory=list)
    archived: bool = False
    contributors: int = 0


@dataclass
class PyPIStats:
    version: str = "—"
    summary: str = "—"
    author: str = "—"
    license: str = "—"
    requires_python: str = "—"
    python_versions: list[str] = field(default_factory=list)
    releases: list[dict[str, Any]] = field(default_factory=list)
    total_releases: int = 0
    package_size: str = "—"
    keywords: list[str] = field(default_factory=list)
    project_urls: dict[str, str] = field(default_factory=dict)


@dataclass
class DownloadStats:
    last_day: int | None = None
    last_week: int | None = None
    last_month: int | None = None


@dataclass
class RTDStats:
    name: str = "—"
    default_version: str = "—"
    default_branch: str = "—"
    language: str = "—"
    programming_language: str = "—"
    created: str = "—"
    modified: str = "—"
    url: str = "—"
    last_build_status: str = "—"
    last_build_date: str = "—"
    total_builds: int | None = None


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_github(token: str | None = None) -> GitHubStats:
    stats = GitHubStats()
    data = _get_json(GITHUB_API, token=token)
    if data:
        stats.stars = data.get("stargazers_count", 0)
        stats.forks = data.get("forks_count", 0)
        stats.watchers = data.get("subscribers_count", 0)
        stats.open_issues = data.get("open_issues_count", 0)
        stats.size_kb = data.get("size", 0)
        stats.language = data.get("language", "—") or "—"
        lic = data.get("license") or {}
        stats.license = lic.get("spdx_id", "—") if isinstance(lic, dict) else "—"
        stats.default_branch = data.get("default_branch", "—")
        stats.created_at = _iso(data.get("created_at"))
        stats.updated_at = _iso(data.get("updated_at"))
        stats.pushed_at = _iso(data.get("pushed_at"))
        stats.description = data.get("description", "—") or "—"
        stats.topics = data.get("topics", [])
        stats.archived = data.get("archived", False)

    contribs = _get_json(f"{GITHUB_API}/contributors?per_page=1&anon=true", token=token)
    if isinstance(contribs, list):
        stats.contributors = len(contribs)
        # GitHub paginates — check the Link header for the real count
        # For simplicity we just count what we get; full count needs header parsing.
    return stats


def fetch_pypi() -> PyPIStats:
    stats = PyPIStats()
    data = _get_json(PYPI_API)
    if not data:
        return stats
    info = data.get("info", {})
    stats.version = info.get("version", "—")
    stats.summary = info.get("summary", "—")
    stats.author = info.get("author", "—") or info.get("maintainer", "—") or "—"
    raw_license = info.get("license", "—") or "—"
    # PyPI may embed the full license text; extract just the first line.
    stats.license = raw_license.split("\n", 1)[0].strip() if raw_license != "—" else "—"
    stats.requires_python = info.get("requires_python", "—") or "—"
    stats.keywords = [k.strip() for k in (info.get("keywords") or "").split(",") if k.strip()]
    stats.project_urls = info.get("project_urls") or {}

    # Python version classifiers
    classifiers = info.get("classifiers", [])
    stats.python_versions = sorted(
        c.split("::")[-1].strip()
        for c in classifiers
        if "Programming Language :: Python ::" in c and c.split("::")[-1].strip()[0].isdigit()
    )

    # Releases
    releases_raw = data.get("releases", {})
    stats.total_releases = len(releases_raw)
    for version, files in sorted(releases_raw.items()):
        if not files:
            continue
        upload_time = files[0].get("upload_time_iso_8601") or files[0].get("upload_time", "")
        size = sum(f.get("size", 0) for f in files)
        stats.releases.append({
            "version": version,
            "date": _iso(upload_time),
            "size": _size_human(size),
            "files": len(files),
        })

    # Latest wheel size
    latest_files = releases_raw.get(stats.version, [])
    if latest_files:
        wheel = next((f for f in latest_files if f["filename"].endswith(".whl")), latest_files[0])
        stats.package_size = _size_human(wheel.get("size", 0))

    return stats


def fetch_downloads() -> DownloadStats:
    stats = DownloadStats()
    data = _get_json(PYPISTATS_API)
    if data and "data" in data:
        d = data["data"]
        stats.last_day = d.get("last_day")
        stats.last_week = d.get("last_week")
        stats.last_month = d.get("last_month")
    return stats


def fetch_rtd(token: str | None = None) -> RTDStats:
    stats = RTDStats()
    headers_extra = {}
    if token:
        headers_extra["Authorization"] = f"Token {token}"

    data = _get_json(RTD_API, token=token)
    if data:
        stats.name = data.get("name", "—")
        stats.default_version = data.get("default_version", "—")
        stats.default_branch = data.get("default_branch", "—")
        lang = data.get("language", {})
        stats.language = lang.get("name", "—") if isinstance(lang, dict) else str(lang)
        prog = data.get("programming_language", {})
        stats.programming_language = prog.get("name", "—") if isinstance(prog, dict) else str(prog)
        stats.created = _iso(data.get("created"))
        stats.modified = _iso(data.get("modified"))
        urls = data.get("urls", {})
        stats.url = urls.get("documentation", f"https://{RTD_PROJECT}.readthedocs.io/")

    builds = _get_json(f"{RTD_BUILDS_URL}?limit=1", token=token)
    if builds and "results" in builds:
        results = builds["results"]
        if results:
            latest = results[0]
            state = latest.get("state", {})
            stats.last_build_status = state.get("name", "—") if isinstance(state, dict) else str(state)
            stats.last_build_date = _iso(latest.get("finished"))
        stats.total_builds = builds.get("count")
    return stats


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _sep(title: str) -> str:
    return f"\n{'=' * 60}\n  {title}\n{'=' * 60}"


def print_report(
    gh: GitHubStats,
    pypi: PyPIStats,
    dl: DownloadStats,
    rtd: RTDStats,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\nremote-store — Project Statistics  ({now})")
    print("=" * 60)

    # GitHub
    print(_sep("GitHub  —  github.com/haalfi/remote-store"))
    print(f"  Description      : {gh.description}")
    print(f"  Stars            : {gh.stars}")
    print(f"  Forks            : {gh.forks}")
    print(f"  Watchers         : {gh.watchers}")
    print(f"  Open issues      : {gh.open_issues}")
    print(f"  Language         : {gh.language}")
    print(f"  License          : {gh.license}")
    print(f"  Size             : {_size_human(gh.size_kb * 1024)}")
    print(f"  Default branch   : {gh.default_branch}")
    print(f"  Archived         : {gh.archived}")
    print(f"  Created          : {gh.created_at}")
    print(f"  Last updated     : {gh.updated_at}")
    print(f"  Last push        : {gh.pushed_at}")
    if gh.topics:
        print(f"  Topics           : {', '.join(gh.topics)}")

    # PyPI
    print(_sep("PyPI  —  pypi.org/project/remote-store"))
    print(f"  Latest version   : {pypi.version}")
    print(f"  Summary          : {pypi.summary}")
    print(f"  Author           : {pypi.author}")
    print(f"  License          : {pypi.license}")
    print(f"  Requires Python  : {pypi.requires_python}")
    print(f"  Python versions  : {', '.join(pypi.python_versions) or '—'}")
    print(f"  Wheel size       : {pypi.package_size}")
    print(f"  Total releases   : {pypi.total_releases}")
    if pypi.releases:
        print(f"  Release history  :")
        for r in pypi.releases:
            print(f"    {r['version']:>8s}  {r['date']}  ({r['size']}, {r['files']} file(s))")
    if pypi.keywords:
        print(f"  Keywords         : {', '.join(pypi.keywords)}")

    # Downloads
    print(_sep("PyPI Downloads  (via pypistats.org)"))
    if dl.last_day is not None:
        print(f"  Last day         : {dl.last_day:,}")
        print(f"  Last week        : {dl.last_week:,}")
        print(f"  Last month       : {dl.last_month:,}")
    else:
        print("  (download stats unavailable — try again later or visit")
        print("   https://pypistats.org/packages/remote-store )")
        print("   https://pepy.tech/projects/remote-store )")

    # Read the Docs
    print(_sep("Read the Docs  —  remote-store.readthedocs.io"))
    print(f"  Project          : {rtd.name}")
    print(f"  URL              : {rtd.url}")
    print(f"  Default version  : {rtd.default_version}")
    print(f"  Default branch   : {rtd.default_branch}")
    print(f"  Language         : {rtd.language}")
    print(f"  Programming lang : {rtd.programming_language}")
    print(f"  Created          : {rtd.created}")
    print(f"  Last modified    : {rtd.modified}")
    if rtd.total_builds is not None:
        print(f"  Total builds     : {rtd.total_builds}")
    print(f"  Last build status: {rtd.last_build_status}")
    print(f"  Last build date  : {rtd.last_build_date}")

    print("\n" + "=" * 60)


def to_dict(
    gh: GitHubStats,
    pypi: PyPIStats,
    dl: DownloadStats,
    rtd: RTDStats,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "github": {
            "url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}",
            "description": gh.description,
            "stars": gh.stars,
            "forks": gh.forks,
            "watchers": gh.watchers,
            "open_issues": gh.open_issues,
            "language": gh.language,
            "license": gh.license,
            "size_kb": gh.size_kb,
            "default_branch": gh.default_branch,
            "archived": gh.archived,
            "created_at": gh.created_at,
            "updated_at": gh.updated_at,
            "pushed_at": gh.pushed_at,
            "topics": gh.topics,
        },
        "pypi": {
            "url": f"https://pypi.org/project/{PYPI_PACKAGE}/",
            "version": pypi.version,
            "summary": pypi.summary,
            "author": pypi.author,
            "license": pypi.license,
            "requires_python": pypi.requires_python,
            "python_versions": pypi.python_versions,
            "package_size": pypi.package_size,
            "total_releases": pypi.total_releases,
            "releases": pypi.releases,
            "keywords": pypi.keywords,
        },
        "downloads": {
            "source": "pypistats.org",
            "last_day": dl.last_day,
            "last_week": dl.last_week,
            "last_month": dl.last_month,
        },
        "readthedocs": {
            "url": rtd.url,
            "name": rtd.name,
            "default_version": rtd.default_version,
            "default_branch": rtd.default_branch,
            "language": rtd.language,
            "programming_language": rtd.programming_language,
            "created": rtd.created,
            "modified": rtd.modified,
            "total_builds": rtd.total_builds,
            "last_build_status": rtd.last_build_status,
            "last_build_date": rtd.last_build_date,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Gather remote-store project statistics.")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of a table.")
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub personal access token (raises rate limit from 60 to 5 000 req/h).",
    )
    parser.add_argument(
        "--rtd-token",
        default=None,
        help="Read the Docs API token (required for RTD v3 API access).",
    )
    args = parser.parse_args()

    print("Fetching statistics …", file=sys.stderr)

    gh = fetch_github(token=args.github_token)
    pypi = fetch_pypi()
    dl = fetch_downloads()
    rtd = fetch_rtd(token=args.rtd_token)

    if args.json:
        print(json.dumps(to_dict(gh, pypi, dl, rtd), indent=2))
    else:
        print_report(gh, pypi, dl, rtd)


if __name__ == "__main__":
    main()
