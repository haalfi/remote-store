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

Weekly, and why (DRIFT-RULES Rule 9)
====================================

The period is anchored to what can invalidate the claim, not to a calendar.
Three events can: a **copy-out here**, which happens at a release and is checked
at that moment by the release checklist rather than a week later; a **conda-forge
rerender or migrator commit**, which lands on their schedule and without notice;
and a **hand-edit on the far side**, which ``sdd/CONDA-FORGE.md`` Rule 1 forbids
and which is therefore exactly what nothing else would catch.

Only the last two fire between releases, and none of them is urgent: a wrong
published recipe misinforms readers of the package page and constrains what a
conda user can install, which is a correctness problem measured in weeks rather
than a breakage measured in hours. Seven days is short enough that a divergence
is found within one release cycle and long enough not to spend a run per day on
an artefact that usually changes a few times a year. Daily would cost 7x for no
detection this period misses; monthly could let a whole release ship and be
superseded before anyone looked.

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

**Two questions, not one.** "May this force the rolling issue open?" and "may
this let the run close it?" have different answers, and collapsing them is how a
verdict that compared nothing comes to read as a clean bill. Only the two
``CLEAR`` statuses permit a close; everything else blocks it, including the two
that force nothing, because **not knowing is not agreement**.

================= =========================================== ======== =======
Status            Meaning                                     Forces   Permits
                                                              update   close
================= =========================================== ======== =======
``match``         Identical below the header                  no       yes
``ahead-of-tag``  Differs from the tag, matches ``master``    no       yes
``drift``         Any other difference from the tag's copy    **yes**  no
``missing``       404 on the published recipe                 **yes**  no
``error``         Something on THIS side is broken            **yes**  no
``no-baseline``   The tag carries no generated copy           no       no
``unreachable``   The fetch failed                            no       no
================= =========================================== ======== =======

A ``drift`` whose published body is the exact one registered in
``infra/drift-locks/FEEDSTOCK-DIVERGENCE.md`` is the one exception: it renders
with its owner and behaves like the first two rows.

``HOLDS``, ``INCONCLUSIVE`` and ``CLEAR`` above are that table in code, and
``drift_report.py`` imports them rather than restating them, so the two cannot
disagree. A status outside ``STATUSES`` is treated there as an ``error``.

``ahead-of-tag`` exists because the release procedure puts a gap between the tag
and the copy-out, and anything merged into the recipe in that window is carried
out with the copy. **Not** ``source.sha256``, despite the shape of that story:
the digest is masked before any comparison (below), so a sha256-only gap yields
``match`` and never reaches this status. Only the other edits can produce it.

It is a **deferral, not a cure**, and the bound belongs here rather than in a
reader's surprise: ``compare`` has exactly two comparison points, the tag's copy
and ``master``'s *current* one. A legitimately-ahead copy-out is recognised only
while master's generated copy still equals the published one. The next unrelated
recipe edit on master -- a floor bump, the commonest edit this file gets -- makes
the published copy match neither side, and the run reports ``drift`` whose only
remedy is to wait for the next release.

``no-baseline`` is where this watch **compares nothing**, and the bound is worth
stating plainly: a feedstock pinned to a tag cut before this mechanism existed
has no committed copy to compare against and never will, so it reports
``no-baseline`` every week. The current feedstock is at 0.32.0, so the next
copy-out puts a tag with a committed copy in place and ends that window.

**That is the only bound.** An earlier revision claimed a second -- that a
feedstock left behind longer "shows up as ``trailing`` instead" -- which cannot
happen: ``trailing`` is not a status but an orthogonal field, so such a
feedstock reports ``no-baseline`` **and** ``trailing: true`` together. If no
copy-out happens, the window does not close on its own.

It is not inert on the rolling issue, and the difference matters to whoever is
reading one: it renders a section every week and it **stops the issue
auto-closing**, so until the next copy-out an otherwise-clean week leaves the
issue as it found it rather than closing it. That is the intended trade -- a
body is recoverable and a closed issue is not -- but it is a live behaviour
change, not a dormant one.

Bounds (DRIFT-RULES Rule 7)
===========================

* **One file, one branch, one repository.** The feedstock's other files --
  ``conda-forge.yml``, the generated ``README.md``, the CI configuration a
  rerender writes -- are not read, and neither is any branch but the default.
* **Two fields are excluded and therefore unwatched**: ``build.number``, which
  conda-forge owns, and ``source.sha256``, which is fetched after the tag is
  cut. A wrong ``sha256`` fails the feedstock's own build immediately and
  loudly, so this weekly report is not the mechanism that would catch it.
* **Comment-only differences are reported as drift, below ``context:`` only.**
  The comparison is byte-level there, so a reflow counts: after
  ``gen_conda_feedstock.py`` the copy is byte-identical by construction, so a
  comment difference means somebody hand-edited the far side, which
  ``sdd/CONDA-FORGE.md`` Rule 1 forbids.
* **The shipped header is not compared at all, and is therefore unwatched.**
  ``comparable`` drops everything above ``context:`` on *both* sides, so the
  generated header -- including its own "GENERATED FILE … Editing this copy
  directly puts it out of step with its source" notice -- can be rewritten or
  deleted on the feedstock and this watch still reports ``match``. What holds
  that text to anything is ``gen_conda_feedstock``'s tests, on this side only.
* **Line endings are normalised, so a CRLF publication is not a difference.**
  That is a deliberate blindness: if the feedstock's tooling converted the file
  wholesale, nothing here would say so.
* **The published version is the first ``version:`` at any depth below
  ``context:``.** Measured: a ``context:`` block carrying a nested
  ``build.version`` above the real key reads as that nested value. Not a shape
  conda-forge writes, and left permissive on purpose -- the regex's two earlier
  tightenings each made a legitimate reformatting read as versionless and
  report ``error``, blaming this repo for the far repository's layout. What
  this permits fails loudly instead: an unresolvable tag, or a drift against
  the wrong one, never a silent clean bill.
* **The newest-tag lookup reads the first 100 tags**, which is one page. It is
  used only for the informational ``trailing`` row, so a repository with more
  tags than that loses the row rather than the comparison.
* **A difference nobody will revert is registered, not tolerated silently.**
  ``infra/drift-locks/FEEDSTOCK-DIVERGENCE.md`` keys accepted divergences by
  ``fingerprint`` -- the sha256 of the published body in its ``comparable``
  form -- with an owner, a rationale and a ``Review by`` read by the same
  predicate the other two registers use. A row therefore accepts **one
  published file**, not a standing permission: any further edit on the far side
  changes the fingerprint and the row stops matching, so the difference is
  reported as new. It ships empty: nothing is accepted today.

  Over ``comparable`` rather than the raw bytes, because conda-forge bumps
  ``build.number`` on every rerender -- including in the very
  ``please add user @X`` commit the register exists for. A raw-byte fingerprint
  would expire its own row in the commit that made it necessary.

  The register exists because the earlier "never tolerated, so Rule 6 is
  satisfied vacuously" argument was a policy this project cannot enforce on a
  repository it does not own. conda-forge's ``please add user @X`` flow edits
  ``extra.recipe-maintainers``, ``sdd/CONDA-FORGE.md`` Rule 1 forbids the
  in-repo remedy, and a permanent ``drift`` would hold the **shared** rolling
  issue open forever -- retiring the dependency lanes' own "drift cleared"
  signal.

  Keyed on content rather than on the YAML key path ``differing_keys`` reports,
  because that reporting is allowed to be imperfect and a trust boundary is
  not. Measured on the real recipe: 3 of its 62 key paths were unwritable as a
  register row, and a difference that localized to ``?`` was dropped before the
  registration check -- so one registered key plus one unregistered column-0
  comment edit closed the rolling issue. Both derivations are in the register's
  own *Why content and not the YAML key*. ``differing_keys`` stays, for the
  finding's ``Differing keys`` list alone.

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
import hashlib
import http.client
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

# The status vocabulary, and its classification, in ONE place. `drift_report.py`
# imports these rather than restating them: it holds three readers of this set
# (two predicates and a summary table), and three hand-maintained copies of a
# vocabulary whose producer is this module is the parallel artefact
# `sdd/DRIFT-RULES.md` Rule 3 forbids. Measured before they were derived: a
# status this file could emit but `drift_report` did not classify read as
# "the copies agree" and let the run close the rolling issue.
HOLDS: frozenset[str] = frozenset({"drift", "missing", "error"})
"""A finding. Forces an issue update on an unnarrowed run, and blocks a close."""

INCONCLUSIVE: frozenset[str] = frozenset({"unreachable", "no-baseline"})
"""No comparison was made. Forces nothing -- but blocks a close, because not knowing is not agreement."""

CLEAR: frozenset[str] = frozenset({"match", "ahead-of-tag"})
"""The published copy is what this repo published for its version. The only verdicts that permit a close."""

STATUSES: frozenset[str] = HOLDS | INCONCLUSIVE | CLEAR

# `context:` block, then a `version:` key under it. Read textually rather than
# with a YAML parser for the reason `check_conda_recipe_pins.py` gives about the
# same file: the recipe carries `${{ }}` templating, and one key is all that is
# needed.
#
# The intervening lines are deliberately permissive. THE PUBLISHED FILE IS NOT
# OURS TO KEEP TIDY: a conda-forge migrator, a rerender or a maintainer may put
# a blank line or a column-0 comment inside the block, and an earlier spelling
# that required every intervening line to be indented then read the version as
# absent -- reporting `error`, which this script and four other artefacts define
# as a fault on OUR side. That inverts the very split the taxonomy exists for.
# So anything but a new TOP-LEVEL key may intervene: indented lines, blank
# lines, and comments at any indent.
#
# The marker line may itself carry a trailing comment, for the same reason.
# And line endings are normalised before this ever runs -- see `normalize`,
# which is why the marker class is `[ \t]` rather than `\s`: `\s` would match
# the `\r` of a CRLF file and hide the need for the normalisation everything
# else depends on.
_VERSION_RE = re.compile(
    r"^context:[ \t]*(?:#.*)?$\n(?:^(?:[ \t].*|[ \t]*|#.*)$\n)*?^[ \t]+version:[ \t]*[\"']?([^\"'\s]+)",
    re.MULTILINE,
)

# The two fields the far copy may legitimately differ on; see the module
# docstring for why each is here. Matched as a key with optional space before
# the colon, for the same reason `_VERSION_RE` tolerates reformatting: the
# published file is not ours to keep tidy, and `number : 0` would otherwise go
# unmasked and report as drift.
_EXCLUDED_KEYS = ("number", "sha256")
_EXCLUDED_RE = re.compile(rf"^(?P<indent>[ \t]*)(?P<key>{'|'.join(_EXCLUDED_KEYS)})[ \t]*:")

_TIMEOUT_SECONDS = 30

# `_gh`'s synthetic exit code for "the process never launched". 127 is the
# shell's own convention for command-not-found, and no `gh` invocation returns
# it, so it cannot collide with a real answer.
_GH_DID_NOT_RUN = 127


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
    fingerprint: str = ""
    """The published body's ``fingerprint``, or ``""`` when nothing was fetched.

    Carried on every verdict that read a body, not only on ``drift``: a row is
    cut after a maintainer reads a verdict, and the verdict a divergence first
    arrives in need not be the one they act on. Empty on ``unreachable`` and
    ``missing``, which no register row can carry, so neither can be accepted by
    accident.
    """

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #


def normalize(text: str) -> str:
    """Line endings, flattened to ``\\n``, before anything reads the text.

    The published file is written by tooling this project does not control, so
    its line endings are not a difference worth reporting. Two things break
    without this, and the second only appears once the first is fixed: the
    version parse misses a CRLF marker line and reports ``error`` -- blaming
    this repo for the far repository's line endings -- and ``mask_excluded``
    rewrites a masked line's terminator to ``\\n`` while leaving its neighbours
    ``\\r\\n``, so every line then differs and the run reports ``drift``.

    Four sibling generators in this repo (``gen_features``, ``drift_check``,
    ``gen_graph``, ``gen_graph_viz``) normalise before comparing for the same
    reason; this module did not, which is how a CRLF regression rode in on a
    fix for the adjacent case.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


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
        match = _EXCLUDED_RE.match(line)
        if match:
            out.append(f"{match.group('indent')}{match.group('key')}: <excluded>\n")
        else:
            out.append(line)
    return "".join(out)


def comparable(text: str) -> str:
    """The form two recipes are compared in: normalised, header dropped, owned fields masked."""
    return mask_excluded(body(normalize(text)))


FINGERPRINT_PREFIX = "sha256:"


def fingerprint(text: str) -> str:
    """The published body's identity, as a register row keys on it (Rule 6).

    Over ``comparable`` rather than over the raw file, and that is the whole
    point of hashing a *derived* form: it is blind to exactly the differences
    this watch already declines to report -- the header, line endings,
    ``build.number``, ``source.sha256`` -- and sensitive to every difference it
    does report. So a row survives the rerender that bumps ``build.number``
    alongside the maintainer edit it accepts, and expires on the next
    hand-edit.

    The ``sha256:`` prefix is for the reader, not the loader: the key's only
    appearance is a cell in a Markdown table, where a bare 64-hex token says
    nothing about what it is a hash of.
    """
    return FINGERPRINT_PREFIX + hashlib.sha256(comparable(text).encode("utf-8")).hexdigest()


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
    # `http.client.HTTPException` is deliberately in this list and is **not**
    # covered by `OSError`: `IncompleteRead` is raised while reading the body,
    # after the request itself succeeded, so a truncated response would
    # otherwise escape as a traceback.
    except (urllib.error.URLError, http.client.HTTPException, OSError, UnicodeDecodeError) as exc:
        raise RemoteUnreachableError(f"{url}: {exc}") from exc


def _gh(*args: str) -> subprocess.CompletedProcess:
    """Run ``gh``, treating a failure to launch it as a failed call.

    ``check=False`` suppresses a non-zero **exit**, not a failure to **exec**:
    with no ``gh`` on PATH this raises ``FileNotFoundError``, which is an
    ``OSError`` and would escape ``compare()`` -- whose contract is that it
    never raises, out of a workflow step that runs before the issue update.
    Measured: without this guard, ``compare()`` raised
    ``FileNotFoundError: [Errno 2] ... 'gh'`` from ``tag_exists``.

    A synthetic non-zero result rather than a re-raise, because every caller
    already has to handle "the call failed" and none of them can do anything
    different about the reason.
    """
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(args=["gh", *args], returncode=_GH_DID_NOT_RUN, stdout="", stderr=str(exc))


def tag_exists(tag: str, repo: str = REPO) -> bool | None:
    """Whether ``tag`` resolves in ``repo``; ``None`` if the question could not be asked.

    Asked **before** the file is fetched, and that order is the point: the
    contents endpoint answers 404 both for a tag that does not exist and for a
    file absent at a tag that does, and those are a broken watch and normal
    operation respectively.

    The third answer matters for the same reason (Rule 2: localize). ``gh``
    exits non-zero both for "no such tag" and for "the call never ran", and
    reporting the second as the first tells a maintainer the feedstock names a
    version this project never released -- sending them to the wrong repository
    entirely. ``_gh``'s synthetic 127 is what separates them.
    """
    result = _gh("api", f"repos/{repo}/git/ref/tags/{tag}")
    if result.returncode == _GH_DID_NOT_RUN:
        return None
    return result.returncode == 0


class LookupFailedError(Exception):
    """A ``gh`` call did not run at all, so its question is unanswered.

    Distinct from a call that ran and said "no": ``tag_exists`` and
    ``baseline_at`` both have a legitimate negative answer, and reporting a
    broken tool as that answer sends a maintainer to conda-forge for a fault
    that is here.
    """


def baseline_at(tag: str, repo: str = REPO, path: str = BASELINE_PATH) -> str | None:
    """The generated copy committed at ``tag``, or ``None`` if there is none.

    Raises:
        LookupFailedError: If the ``gh`` call did not run. Caught by
            ``compare``, which reports it as an ``error`` rather than as the
            ``no-baseline`` a genuine 404 means — the sibling of the split
            ``tag_exists`` makes, and for the same reason.

    Bound: a 404 and any *other* HTTP failure both read as ``None`` here, so a
    transient API error reports ``no-baseline``. That is the safe direction —
    ``no-baseline`` neither holds the issue open nor lets the run close it, so
    the week's verdict is "leave it alone" and the next run decides — but it is
    a real limit, not a claim that the file is absent.
    """
    result = _gh("api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}?ref={tag}")
    if result.returncode == _GH_DID_NOT_RUN:
        raise LookupFailedError(f"the `gh` call for {path} at {tag} did not run: {result.stderr.strip()}")
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
    """The published recipe's ``context.version``, or ``None`` if it cannot be read.

    Normalised first: a CRLF file is the same recipe, and reading it as
    versionless would report ``error`` -- a fault on this side -- for the far
    repository's line endings.
    """
    match = _VERSION_RE.search(normalize(text))
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

    # Computed once, here, and carried by every verdict below: from this point
    # on a body exists, so there is always a key a register row could name.
    digest = fingerprint(remote_text)

    version = remote_version(remote_text)
    if version is None:
        return Comparison(
            status="error",
            fingerprint=digest,
            reason="the published recipe has no `context.version`, so there is no tag to compare it against",
        )

    tag = f"v{version}"
    latest = newest_tag(repo)
    trailing = bool(latest) and latest != tag

    resolved = tag_exists(tag, repo)
    if resolved is None:
        return Comparison(
            status="error",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            fingerprint=digest,
            reason=(
                f"could not ask whether {tag} exists: the `gh` call did not run. Nothing was compared, and "
                "this says nothing about the feedstock -- look at this workflow, not at conda-forge"
            ),
        )
    if not resolved:
        return Comparison(
            status="error",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            fingerprint=digest,
            reason=(
                f"the published recipe names version {version}, which this repository has no {tag} tag for. "
                "Either the feedstock is on a version that was never released here, or this checkout "
                "cannot resolve tags"
            ),
        )

    try:
        baseline = baseline_at(tag, repo)
    except LookupFailedError as exc:
        return Comparison(
            status="error",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            fingerprint=digest,
            reason=f"{exc}. Nothing was compared, and this says nothing about the feedstock",
        )
    if baseline is None:
        return Comparison(
            status="no-baseline",
            remote_version=version,
            newest_tag=latest,
            trailing=trailing,
            fingerprint=digest,
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
            fingerprint=digest,
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
            fingerprint=digest,
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
        fingerprint=digest,
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
