"""Report: does conda-forge still publish what this repo said it published?

``conda-forge/remote-store-feedstock``'s ``recipe/recipe.yaml`` is the recipe
conda users actually get, and it lives in a repository this project does not
own. ``gen_conda_feedstock.py`` makes the copy-out mechanical; this script is
the other half -- it fetches the published file weekly and compares it against
the generated copy **this repo committed at the tag the published version
names**.

That is the claim worth making. Comparing against ``master`` would report every
legitimate floor change between releases as drift: the recipe took four commits
between v0.31.0 and v0.32.0, one of them correcting six dependency floors, and
the feedstock was rightly carrying none of them yet.

Findings land on the drift-guard rolling issue via ``drift_report.py``. This
script writes a JSON report and **never raises** -- see Statuses.

Advisory, and why (DRIFT-RULES Rule 5)
======================================

The artefact this watches is in a third-party repository. Nothing in a pull
request here can fix a difference, so a red job would be a permanently
filterable X asserting something no contributor is able to act on -- the signal
``sdd/CI-OPERATIONS.md`` Rule 1 says not to rely on. The finding belongs on the
rolling issue, where it sits beside a runbook that names the remedy: a pull
request against the feedstock, per ``sdd/CONDA-FORGE.md``.

Authority (DRIFT-RULES Rule 4)
==============================

``sdd/CONDA-FORGE.md`` Rule 1 declares it, and it is not restated here: ours
governs, and a difference is always the feedstock's to fix. This script never
edits anything and never opens a pull request.

Statuses
========

Every run ends in exactly one, and **a failure of this script's own is never
reported as a failure of the other repository**. That split is the whole design:
folding "the tag does not resolve" into "the network is down" would let a broken
watch look exactly like normal operation, forever, because only one of them is
something this repo can fix.

============== ============================================= ==============
Status         Meaning                                       Holds the issue
============== ============================================= ==============
``match``      Identical below the header                    no
``drift``      Any other difference from the tag's copy      **yes**
``ahead-of``   Differs from the tag but matches ``master``   no
``-tag``
``no-baseline`` The tag carries no generated copy            no
``missing``    404 on the published recipe                   **yes**
``unreachable`` The fetch failed                             no
``error``      Something here is broken                      **yes**
============== ============================================= ==============

``ahead-of-tag`` exists because the release procedure puts a gap between the tag
and the copy-out: ``CONTRIBUTING.md`` Phase 5 fetches ``source.sha256`` from
PyPI after the tag and lands it separately, and anything else merged in that
window is carried out with it. Without this status such a copy-out would read as
drift for a whole release cycle.

``no-baseline`` is where this watch is **inert**, and the bound is worth stating
plainly: a feedstock pinned to a tag cut before this mechanism existed has no
committed copy to compare against and never will, so it reports ``no-baseline``
every week. The current feedstock is at 0.32.0, so the next copy-out puts a tag
with a committed copy in place and ends the inert window; a feedstock left
behind for longer than that shows up as ``trailing`` instead, which the release
checklist owns.

Bounds (DRIFT-RULES Rule 7)
===========================

* **One file, one branch, one repository.** The feedstock's other files --
  ``conda-forge.yml``, the generated ``README.md``, the CI configuration a
  rerender writes -- are not read, and neither is any branch but the default.
* **Two fields are excluded and therefore unwatched**: ``build.number``, which
  conda-forge owns, and ``source.sha256``, which is fetched after the tag is
  cut. A wrong ``sha256`` fails the feedstock's own build immediately and
  loudly, so this weekly report is not the mechanism that would catch it.
* **Comment-only differences are reported as drift.** The comparison is
  byte-level below ``context:``, so a reflow counts. That is deliberate --
  after ``gen_conda_feedstock.py`` the copy is byte-identical by construction,
  so a comment difference means somebody hand-edited the far side, which
  ``sdd/CONDA-FORGE.md`` Rule 1 forbids.
* **The newest-tag lookup reads the first 100 tags**, which is one page. It is
  used only for the informational ``trailing`` row, so a repository with more
  tags than that loses the row rather than the comparison.
* **No register.** A feedstock difference is fixed by a feedstock pull request,
  never tolerated, so DRIFT-RULES Rule 6 has nothing to register rather than a
  waiver. The one case that would need one is an upstream conda-forge
  **migrator** editing the recipe in a way this project would not revert; if
  that ever happens the answer is a register, not a widened exclusion.

Exit codes
==========

* ``0`` -- a report was written, whatever it says.
* ``1`` -- the report could not be written at all (an unusable argument, or an
  output path that cannot be created). Never a finding about the feedstock.

Drift-gate::

    kind:       pair
    compares:   the recipe conda-forge/remote-store-feedstock publishes at recipe/recipe.yaml ↔
        the generated copy this repo committed at packaging/conda-forge/feedstock/recipe.yaml at
        the tag the published `context.version` names, excluding `build.number` and
        `source.sha256`; advisory, so nothing it finds makes it exit non-zero
    domain:     process
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

FEEDSTOCK_URL = "https://raw.githubusercontent.com/conda-forge/remote-store-feedstock/main/recipe/recipe.yaml"
BASELINE_PATH = "packaging/conda-forge/feedstock/recipe.yaml"
LOCAL_BASELINE = _REPO_ROOT / BASELINE_PATH
REPO = "haalfi/remote-store"

BODY_MARKER = "context:"

# `context:` block, then a `version:` key under it. Read textually rather than
# with a YAML parser for the reason `check_conda_recipe_pins.py` gives about the
# same file: the recipe carries `${{ }}` templating, and one key is all that is
# needed.
_VERSION_RE = re.compile(r"^context:\s*$\n(?:^[ \t]+.*$\n)*?^[ \t]+version:\s*[\"']?([^\"'\s]+)", re.MULTILINE)

# The two fields the far copy may legitimately differ on. Matched on the key so
# the value is irrelevant; see the module docstring for why each is here.
_EXCLUDED_KEYS = ("number:", "sha256:")

_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Comparison:
    """One run's verdict, and everything the rendered section needs.

    ``trailing`` is a separate field rather than a status because it is
    orthogonal to the comparison: a feedstock a release behind can still carry
    exactly what this repo published for the version it *is* on, which is a
    ``match`` with a ``trailing`` row beside it. Collapsing the two would make
    the commonest healthy state unrepresentable.
    """

    status: str
    remote_version: str | None = None
    newest_tag: str | None = None
    trailing: bool = False
    reason: str = ""
    diff: str = ""
    keys: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #


def body(text: str) -> str:
    """Everything from ``context:`` down, or the whole text if there is no marker.

    The header above the marker is the generator's and differs by design, so it
    is never compared. A file with no marker is compared whole: that is a
    difference worth reporting rather than one to silently normalize away.
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(BODY_MARKER):
            return "".join(lines[index:])
    return text


def mask_excluded(text: str) -> str:
    """Blank the value of every excluded key, keeping the line count.

    Replacing rather than deleting keeps line numbers aligned between the two
    sides, so ``_key_path`` reports the position a reader will find in the file.
    """
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if any(stripped.startswith(key) for key in _EXCLUDED_KEYS):
            indent = line[: len(line) - len(line.lstrip())]
            key = stripped.split(":", 1)[0]
            out.append(f"{indent}{key}: <excluded>\n")
        else:
            out.append(line)
    return "".join(out)


def comparable(text: str) -> str:
    """The form two recipes are compared in."""
    return mask_excluded(body(text))


# --------------------------------------------------------------------------- #
# Localization (DRIFT-RULES Rule 2)
# --------------------------------------------------------------------------- #


def _key_path(lines: list[str], index: int) -> str:
    """The YAML key path of ``lines[index]``, as a reader would cite it.

    A unified diff over a file that is mostly comments localizes to a line
    number, which is not what changed. Rule 2 asks a mechanism to name the
    element, so a finding leads with ``requirements.run_constraints[pyarrow]``
    and carries the diff as detail.

    Walks back over strictly decreasing indentation, which is all a recipe's
    shape needs; it does not model YAML in general, and a line inside a block
    scalar (the ``about.description`` text) reports that block's own path,
    which is the right answer for a reader anyway.

    A **comment** reports the block that encloses it rather than the key above
    it. The lines that differ in practice are as often comments as values, and
    naming the preceding sibling would point a reader at a key that did not
    change.
    """
    if index >= len(lines):
        return "?"
    line = lines[index]
    stripped = line.strip()
    indent = len(line) - len(line.lstrip())
    parts: list[str] = []
    item = ""
    if stripped.startswith("- "):
        # `- pyarrow >=14.0.0` -- the package is the identifier a reader wants.
        name = stripped[2:].split()[0]
        if name:
            item = f"[{name}]"
    elif stripped and not stripped.startswith("#") and ":" in stripped:
        # A `key: value` line names itself; everything else names its enclosing
        # block, reached by the strictly-decreasing walk below.
        parts.append(stripped.split(":", 1)[0].strip())
    for candidate in reversed(lines[:index]):
        text = candidate.strip()
        if not text or text.startswith("#") or text.startswith("- ") or ":" not in text:
            continue
        candidate_indent = len(candidate) - len(candidate.lstrip())
        if candidate_indent < indent:
            key = text.split(":", 1)[0].strip()
            if key:
                parts.append(key)
                indent = candidate_indent
            if indent == 0:
                break
    return ".".join(reversed(parts)) + item if parts else (item or "?")


def differing_keys(expected: str, actual: str) -> tuple[str, ...]:
    """The distinct key paths a diff between two comparable bodies touches."""
    expected_lines = expected.splitlines(keepends=True)
    actual_lines = actual.splitlines(keepends=True)
    found: list[str] = []
    matcher = difflib.SequenceMatcher(None, expected_lines, actual_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for index in range(i1, i2):
            found.append(_key_path(expected_lines, index))
        for index in range(j1, j2):
            found.append(_key_path(actual_lines, index))
    seen: list[str] = []
    for key in found:
        if key not in seen and key != "?":
            seen.append(key)
    return tuple(seen)


def unified(expected: str, actual: str) -> str:
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="this repo, at the tag the feedstock names",
            tofile="conda-forge/remote-store-feedstock",
        )
    )


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #


class RemoteMissingError(Exception):
    """The published recipe returned 404 -- repo, branch or path moved."""


class RemoteUnreachableError(Exception):
    """The published recipe could not be fetched at all."""


def fetch_remote(url: str = FEEDSTOCK_URL) -> str:
    """The published recipe.

    Raises:
        RemoteMissingError: On 404. A finding: the path this repo publishes to
            has moved, which nothing else here would notice.
        RemoteUnreachableError: On anything else. Not a finding about the
            feedstock's contents, so it never holds the issue open.
    """
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 -- fixed https URL
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RemoteMissingError(f"{url} returned 404") from exc
        raise RemoteUnreachableError(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        raise RemoteUnreachableError(f"{url}: {exc}") from exc


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)


def tag_exists(tag: str, repo: str = REPO) -> bool:
    """Whether ``tag`` resolves in ``repo``.

    Asked **before** the file is fetched, and that order is the point: the
    contents endpoint answers 404 both for a tag that does not exist and for a
    file absent at a tag that does, and those are a broken watch and normal
    operation respectively.
    """
    return _gh("api", f"repos/{repo}/git/ref/tags/{tag}").returncode == 0


def baseline_at(tag: str, repo: str = REPO, path: str = BASELINE_PATH) -> str | None:
    """The generated copy committed at ``tag``, or ``None`` if there is none."""
    result = _gh("api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}?ref={tag}")
    return result.stdout if result.returncode == 0 else None


def newest_tag(repo: str = REPO) -> str | None:
    """The highest ``vX.Y.Z`` tag, by version order rather than by push order."""
    result = _gh("api", f"repos/{repo}/tags?per_page=100", "--jq", ".[].name")
    if result.returncode != 0:
        return None
    best: tuple[tuple[int, ...], str] | None = None
    for name in result.stdout.split():
        parsed = _version_tuple(name)
        if parsed is not None and (best is None or parsed > best[0]):
            best = (parsed, name)
    return best[1] if best else None


def _version_tuple(tag: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v(\d+(?:\.\d+)*)", tag.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def remote_version(text: str) -> str | None:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def compare(
    *,
    url: str = FEEDSTOCK_URL,
    repo: str = REPO,
    local_baseline: Path = LOCAL_BASELINE,
) -> Comparison:
    """Run the whole comparison. Never raises; every failure is a status."""
    try:
        remote_text = fetch_remote(url)
    except RemoteMissingError as exc:
        return Comparison(status="missing", reason=str(exc))
    except RemoteUnreachableError as exc:
        return Comparison(status="unreachable", reason=str(exc))

    version = remote_version(remote_text)
    if version is None:
        return Comparison(
            status="error",
            reason="the published recipe has no `context.version`, so there is no tag to compare it against",
        )

    tag = f"v{version}"
    latest = newest_tag(repo)
    trailing = bool(latest) and latest != tag

    if not tag_exists(tag, repo):
        return Comparison(
            status="error",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            reason=(
                f"the published recipe names version {version}, which this repository has no {tag} tag for. "
                "Either the feedstock is on a version that was never released here, or this checkout "
                "cannot resolve tags"
            ),
        )

    baseline = baseline_at(tag, repo)
    if baseline is None:
        return Comparison(
            status="no-baseline",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            reason=(
                f"{tag} carries no {BASELINE_PATH}, so this repo published no generated copy for that "
                "version and there is nothing to compare. The next copy-out ends this"
            ),
        )

    remote_body = comparable(remote_text)
    if comparable(baseline) == remote_body:
        return Comparison(
            status="match",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
        )

    # The release procedure lands `source.sha256` -- and anything else merged in
    # that window -- after the tag, so a copy-out can legitimately be ahead of
    # the tag it names. Only reached once the tag comparison has already failed.
    try:
        local_text = local_baseline.read_text(encoding="utf-8")
    except OSError:
        local_text = ""
    if local_text and comparable(local_text) == remote_body:
        return Comparison(
            status="ahead-of-tag",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            reason=(
                f"the published recipe differs from {tag} but matches this repo's current copy, so it "
                f"carries a change merged after {tag} was cut"
            ),
        )

    baseline_body = comparable(baseline)
    return Comparison(
        status="drift",
        remote_version=version,
        newest_tag=latest,
        trailing=trailing,
        reason=f"the published recipe differs from what this repo committed at {tag}",
        diff=unified(baseline_body, remote_body),
        keys=differing_keys(baseline_body, remote_body),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="Write the JSON report here (default: stdout).")
    parser.add_argument("--url", default=FEEDSTOCK_URL, help="The published recipe to fetch.")
    parser.add_argument("--repo", default=REPO, help='Repository to resolve tags against (e.g. "haalfi/remote-store").')
    args = parser.parse_args(argv)

    report = json.dumps(compare(url=args.url, repo=args.repo).as_dict(), indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(report, end="")
        return 0
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # Atomic, for the reason drift-guard.yml gives about every other report
        # it writes: a truncated JSON is an input the report job cannot read,
        # and a half-written file is worse than an absent one.
        temporary = args.out.with_suffix(args.out.suffix + ".tmp")
        temporary.write_text(report, encoding="utf-8")
        temporary.replace(args.out)
    except OSError as exc:
        print(f"::error::cannot write {args.out}: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.out}", file=sys.stderr)
    print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
