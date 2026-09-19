"""Generate the conda-forge feedstock's copy of the recipe from ours.

``conda-forge/remote-store-feedstock``'s ``recipe/recipe.yaml`` is a copy of
``packaging/conda-forge/recipe.yaml``, in a repository this project does not
own. It used to be made by hand at each release, with the human asked to strip
internal coordinates on the way out -- and a copy taken correctly once and
never compared again is exactly how the published ``about`` block came to
advertise four backends while the library reached eight.

This script makes that copy mechanical. It performs **one** transformation:
everything above the ``context:`` key is replaced with a header written for a
conda-forge reader, and every byte below it is carried over unchanged. Nothing
is stripped, rewritten or reflowed, because nothing needs to be:
``check_no_tracker_refs.py`` holds the source recipe's body free of internal
coordinates, so what is copied is already publishable.

The committed result at ``packaging/conda-forge/feedstock/recipe.yaml`` is what
a release copies onto the feedstock. ``--check`` fails when it is stale.

Authority (DRIFT-RULES Rule 4)
==============================

``sdd/CONDA-FORGE.md`` Rule 1 declares it and is not restated here: **ours
governs**. The feedstock copy is never edited directly and never back-ported
from. This script is what makes that rule mechanical rather than remembered.

**One** value is the far copy's to own: ``build.number``, which conda-forge
increments for rebuilds and migrations this repo never sees.

``source.sha256`` is **ours**, and is excluded from the weekly comparison for a
different reason -- it is fetched from PyPI *after* the release tag is cut
(``CONTRIBUTING.md`` Phase 5), so a tag structurally carries the previous
release's digest and no comparison against a tag can judge it. Excluded from a
comparison is not the same claim as owned by the far side, and the shipped
header must not say the second: a reader told the incoming digest is not
authoritative could preserve a stale one and build the wrong tarball.

Wiring
======

``hatch run lint`` **and** ``hatch run docs-gate``, for the reason
``check_conda_recipe_pins.py`` documents at length: the pair straddles CI's two
classifiers. This script is under ``scripts/``, which matches ``CODE_PAT``,
while its input and output are under ``packaging/``, which matches ``DOCS_PAT``
and not ``CODE_PAT``. A gate in only one of them is unreachable for exactly half
the diffs that can invalidate it.

Bounds (DRIFT-RULES Rule 7)
===========================

* It compares this repo's two copies. It never reads the feedstock --
  ``scripts/drift_feedstock.py`` does that, weekly.
* The generated header is **not** derived from anything, so nothing checks that
  its claims stay true. It is a constant in this file, deliberately carrying no
  date and no commit so the output is byte-stable across commits.
* Structural validity of either file is `.github/workflows/conda-recipe.yml`'s
  to prove, with ``rattler-build --render-only``; this script does not parse
  YAML at all beyond finding one top-level key.

Exit codes
==========

* ``0`` -- written, or (under ``--check``) the committed copy is current.
* ``1`` -- the source could not be read or carries no ``context:``; the output
  could not be written; or, under ``--check``, the committed copy is stale or
  absent. Only the last of those is a finding about the pair -- the rest are
  this run failing, and each names itself on stderr.

Drift-gate::

    kind:       pair
    compares:   packaging/conda-forge/recipe.yaml below `context:` ↔
        packaging/conda-forge/feedstock/recipe.yaml, the generated copy a release puts onto
        conda-forge/remote-store-feedstock's recipe/recipe.yaml
    domain:     process
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE = _REPO_ROOT / "packaging" / "conda-forge" / "recipe.yaml"
GENERATED = _REPO_ROOT / "packaging" / "conda-forge" / "feedstock" / "recipe.yaml"

# The first top-level key of the recipe, and the boundary of the one
# transformation. Matched at the start of a line because the same word
# indented is a value inside another block.
BODY_MARKER = "context:"

# Written for a conda-forge maintainer reading the feedstock, not for a
# contributor here. No date and no commit hash: the output has to be
# byte-stable across commits or `--check` would fail on every one of them.
SHIPPED_HEADER = """\
# conda-forge recipe for remote-store
# v1 format (CEP-13 / rattler-build)
#
# GENERATED FILE.  Every change is made upstream, at
# https://github.com/haalfi/remote-store/blob/master/packaging/conda-forge/recipe.yaml
# and copied here by that repository's `scripts/gen_conda_feedstock.py`, which
# replaces this header and carries everything below `context:` byte for byte.
# Editing this copy directly puts it out of step with its source, where a gate
# derives `run_constraints` from the project's own optional dependencies and
# fails on a missing, extra or weaker entry.
#
# `build.number` is the feedstock's own, and upstream leaves it alone:
# conda-forge increments it for rebuilds and migrations. Every other value here
# is upstream's, `source.sha256` included -- it is set there once the release is
# on PyPI, and this file carries whatever it says.
#
# `python_min` is deliberately NOT set: conda-forge supplies it globally, and
# hardcoding it would pin this package to one minimum after the ecosystem
# raises its own.
"""


class MissingMarkerError(Exception):
    """The source recipe has no ``context:`` key, so the header is unbounded.

    Reported rather than guessed at. The marker is the whole definition of
    which part of the file is the generator's and which is the source's; with
    it gone, copying the file whole would ship this repo's internal header to
    conda-forge, and copying nothing would ship an empty recipe. Neither is a
    failure a reader should have to infer from a surprising diff.
    """


def render(source_text: str) -> str:
    """The feedstock copy: the shipped header, then the source from ``context:``.

    Raises:
        MissingMarkerError: If the source carries no ``context:`` key.
    """
    lines = source_text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(BODY_MARKER):
            return SHIPPED_HEADER + "".join(lines[index:])
    raise MissingMarkerError(
        f"no top-level {BODY_MARKER!r} key found, so there is no boundary between the header "
        f"this script replaces and the recipe body it copies"
    )


def _diff(expected: str, actual: str, *, path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=f"{path} (committed)",
            tofile=f"{path} (regenerated)",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the committed copy differs from a fresh render; write nothing.",
    )
    parser.add_argument("--source", type=Path, default=SOURCE, help=f"Source recipe (default: {SOURCE}).")
    parser.add_argument("--out", type=Path, default=GENERATED, help=f"Generated copy (default: {GENERATED}).")
    args = parser.parse_args(argv)

    try:
        expected = render(args.source.read_text(encoding="utf-8"))
    except MissingMarkerError as exc:
        print(f"{args.source}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"cannot read {args.source}: {exc}", file=sys.stderr)
        return 1

    if args.check:
        actual = args.out.read_text(encoding="utf-8") if args.out.is_file() else ""
        if actual == expected:
            print(f"gen_conda_feedstock: {args.out} is current.")
            return 0
        print(_diff(expected, actual, path=args.out), file=sys.stderr, end="")
        print(
            f"\n{args.out} is stale. Run:  hatch run gen-conda-feedstock",
            file=sys.stderr,
        )
        return 1

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(expected, encoding="utf-8")
    except OSError as exc:
        # Reported, not tracebacked, like the read above and like
        # `drift_feedstock.main` for the same failure: a traceback out of a
        # gate says less than the sentence the raiser can write.
        print(f"cannot write {args.out}: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.out.relative_to(_REPO_ROOT) if args.out.is_relative_to(_REPO_ROOT) else args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
