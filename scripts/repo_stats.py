#!/usr/bin/env python3
"""Gather and display statistics for the remote-store project.

Pulls data from three sources:
  1. GitHub API  – repo metadata, stars, forks, issues, traffic & clones
  2. PyPI JSON API + pypistats + pepy.tech – releases, downloads, usage
  3. Read the Docs API – build status, versions

Usage::

    python scripts/repo_stats.py            # print to stdout
    python scripts/repo_stats.py --json     # machine-readable JSON

For full traffic data supply a GitHub token with push access::

    python scripts/repo_stats.py --github-token ghp_…
"""

from __future__ import annotations

import argparse
import json
import sys
import time
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
PYPISTATS_API = f"https://pypistats.org/api/packages/{PYPI_PACKAGE}"
PEPY_API = f"https://api.pepy.tech/api/v2/projects/{PYPI_PACKAGE}"
RTD_API = f"https://readthedocs.org/api/v3/projects/{RTD_PROJECT}/"
RTD_BUILDS_URL = f"https://readthedocs.org/api/v3/projects/{RTD_PROJECT}/builds/"

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, *, token: str | None = None) -> dict[str, Any] | None:
    """Fetch JSON from *url* with retry on 429, returning ``None`` on failure."""
    headers = {"Accept": "application/json", "User-Agent": "remote-store-stats/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** (attempt + 1)
                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = max(wait, int(retry_after))
                print(f"  [429] {url} — retrying in {wait}s …", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  [warn] {url}: {exc}", file=sys.stderr)
            return None
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  [warn] {url}: {exc}", file=sys.stderr)
            return None
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
    # Traffic (requires push-access token)
    views_14d: int | None = None
    unique_visitors_14d: int | None = None
    clones_14d: int | None = None
    unique_cloners_14d: int | None = None
    referrers: list[dict[str, Any]] = field(default_factory=list)
    popular_paths: list[dict[str, Any]] = field(default_factory=list)


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
    # pypistats.org
    last_day: int | None = None
    last_week: int | None = None
    last_month: int | None = None
    # pepy.tech
    pepy_total: int | None = None
    pepy_versions: dict[str, int] = field(default_factory=dict)
    # pypistats per-system breakdown
    by_system: dict[str, int] = field(default_factory=dict)
    # pypistats per-version breakdown
    by_version: dict[str, int] = field(default_factory=dict)
    source: str = "—"


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

    # Traffic endpoints (require push access)
    views = _get_json(f"{GITHUB_API}/traffic/views", token=token)
    if views:
        stats.views_14d = views.get("count")
        stats.unique_visitors_14d = views.get("uniques")

    clones = _get_json(f"{GITHUB_API}/traffic/clones", token=token)
    if clones:
        stats.clones_14d = clones.get("count")
        stats.unique_cloners_14d = clones.get("uniques")

    referrers = _get_json(f"{GITHUB_API}/traffic/popular/referrers", token=token)
    if isinstance(referrers, list):
        stats.referrers = [
            {"source": r.get("referrer", "?"), "count": r.get("count", 0), "uniques": r.get("uniques", 0)}
            for r in referrers[:10]
        ]

    paths = _get_json(f"{GITHUB_API}/traffic/popular/paths", token=token)
    if isinstance(paths, list):
        stats.popular_paths = [
            {"path": p.get("path", "?"), "count": p.get("count", 0), "uniques": p.get("uniques", 0)}
            for p in paths[:10]
        ]

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

    # --- pypistats.org  (recent totals) ---
    recent = _get_json(f"{PYPISTATS_API}/recent")
    if recent and "data" in recent:
        d = recent["data"]
        stats.last_day = d.get("last_day")
        stats.last_week = d.get("last_week")
        stats.last_month = d.get("last_month")
        stats.source = "pypistats.org"

    # --- pypistats.org  (per Python version, last month) ---
    by_ver = _get_json(f"{PYPISTATS_API}/python_minor?period=month")
    if by_ver and "data" in by_ver:
        agg: dict[str, int] = {}
        for row in by_ver["data"]:
            cat = row.get("category", "null")
            agg[cat] = agg.get(cat, 0) + row.get("downloads", 0)
        stats.by_version = dict(sorted(agg.items(), key=lambda kv: -kv[1]))

    # --- pypistats.org  (per OS, last month) ---
    by_sys = _get_json(f"{PYPISTATS_API}/system?period=month")
    if by_sys and "data" in by_sys:
        agg2: dict[str, int] = {}
        for row in by_sys["data"]:
            cat = row.get("category", "null")
            agg2[cat] = agg2.get(cat, 0) + row.get("downloads", 0)
        stats.by_system = dict(sorted(agg2.items(), key=lambda kv: -kv[1]))

    # --- pepy.tech  (total + per-version totals, fallback) ---
    pepy = _get_json(PEPY_API)
    if pepy:
        stats.pepy_total = pepy.get("total_downloads")
        versions = pepy.get("versions", {})
        if isinstance(versions, dict):
            stats.pepy_versions = {v: sum(d.values()) if isinstance(d, dict) else 0 for v, d in versions.items()}
        if stats.source == "—":
            stats.source = "pepy.tech"

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

    # GitHub Traffic
    if gh.views_14d is not None:
        print(_sep("GitHub Traffic  (last 14 days)"))
        print(f"  Page views       : {gh.views_14d:,}  ({gh.unique_visitors_14d:,} unique visitors)")
        print(f"  Git clones       : {gh.clones_14d:,}  ({gh.unique_cloners_14d:,} unique cloners)")
        if gh.referrers:
            print(f"  Top referrers    :")
            for r in gh.referrers:
                print(f"    {r['source']:<25s}  {r['count']:>5,} views  ({r['uniques']:,} unique)")
        if gh.popular_paths:
            print(f"  Popular pages    :")
            for p in gh.popular_paths:
                print(f"    {p['path']:<45s}  {p['count']:>5,} views  ({p['uniques']:,} unique)")
    else:
        print(_sep("GitHub Traffic  (last 14 days)"))
        print("  (unavailable — supply --github-token with push access)")

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
    print(_sep("PyPI Downloads"))
    if dl.last_day is not None:
        print(f"  Last day         : {dl.last_day:,}")
        print(f"  Last week        : {dl.last_week:,}")
        print(f"  Last month       : {dl.last_month:,}")
    if dl.pepy_total is not None:
        print(f"  Total (all time) : {dl.pepy_total:,}  (via pepy.tech)")
    if dl.by_system:
        print(f"  By operating system :")
        for os_name, count in dl.by_system.items():
            print(f"    {os_name or 'null':<20s}  {count:>8,}")
    if dl.by_version:
        print(f"  By Python version   :")
        for ver, count in dl.by_version.items():
            print(f"    {ver or 'null':<20s}  {count:>8,}")
    if dl.pepy_versions:
        print(f"  By package version  :")
        for ver, count in sorted(dl.pepy_versions.items()):
            if count > 0:
                print(f"    {ver:<20s}  {count:>8,}")
    if dl.last_day is None and dl.pepy_total is None:
        print("  (download stats unavailable — try again later or visit")
        print("   https://pypistats.org/packages/remote-store")
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
            "traffic": {
                "views_14d": gh.views_14d,
                "unique_visitors_14d": gh.unique_visitors_14d,
                "clones_14d": gh.clones_14d,
                "unique_cloners_14d": gh.unique_cloners_14d,
                "referrers": gh.referrers,
                "popular_paths": gh.popular_paths,
            },
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
            "source": dl.source,
            "last_day": dl.last_day,
            "last_week": dl.last_week,
            "last_month": dl.last_month,
            "pepy_total": dl.pepy_total,
            "by_system": dl.by_system,
            "by_python_version": dl.by_version,
            "by_package_version": dl.pepy_versions,
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
