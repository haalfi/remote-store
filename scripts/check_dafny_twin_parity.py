#!/usr/bin/env python3
"""Verify body parity between the Dafny reference backend and its minimal twin (BK-328).

``sdd/formal/MemoryBackend.dfy`` declares two classes that refine the same
``Backend`` trait.  ``MemoryBackend`` is the reference model; ``MemoryBackendMinimal``
is a satisfiability witness for the ``BasicSource`` / ``CapabilityNotSupported``
branches, and it duplicates every member of the reference because **Dafny has no
class-to-class inheritance**.

What the verifier does and does not cover, measured rather than assumed.  Each
class proves its own contract independently, so a one-sided edit is caught by
``dafny_verify.sh`` only when it changes what that class can prove.  Drift that
stays inside what the contract underdetermines verifies clean: changing the
value the twin's ``GetFolderInfo`` returns for the field no postcondition pins
leaves ``dafny verify`` at *478 verified, 0 errors* while changing the twin's
behaviour for every folder.  So does any change to proof structure.  That band -- provable
either way, behaviourally different -- is what this gate covers, and it was
caught only in review before the gate existed.  The complementary band
(postconditions the trait or the class actually constrains) is Dafny's, and it
holds it well; both mutation classes are in the corpus, so the division of
labour stays measured as the model evolves.

Authority: ``MemoryBackend`` is canonical.  ``sdd/formal/README.md`` states the
reference class is the oracle and that changes to it "must be manually mirrored"
in the minimal twin, so a reported difference is fixed by porting the reference
member onto the twin, never the reverse.

Why a pairwise check and not one driver: one normative description driving both
classes is the better shape (`sdd/DRIFT-RULES.md` Rule 1) and is unavailable
here.  The duplication is forced by the language, and the two classes are
genuinely two renderings of one contract, which is the exemption that rule
carves out.  Note the twin is a *copy*, not an independently derived second
description, so it carries no independent evidential weight (Rule 8): parity is
the only relation worth asserting between them.

Every member that both classes declare is compared after normalisation
(comments stripped, whitespace collapsed).  Member *order* is not compared; the
twin groups its lemmas differently.  Members that legitimately differ are not
skipped -- their difference is **pinned**: ``DIVERGENT`` records the exact set
of changed lines the twin is allowed to have, so the unchanged remainder of a
divergent member stays under the gate.  Two members are pinned today (the
constructor's name and capability set, and ``Write``'s ``CapWriteResultNative``
branch), and pinning rather than skipping keeps 108 of ``Write``'s 110
normalised lines compared, where an allowlist would drop all 110.

Fails on:

  * a member whose normalised bodies differ with no pin (drift -- the bug this
    gate exists to catch), reported as a unified diff of the normalised lines so
    the differing clause is named rather than just the member,
  * a pinned member whose difference is no longer the pinned one (drift layered
    on top of an intended divergence), reported as pinned-versus-actual,
  * a ``DIVERGENT`` entry whose member no longer differs, or is no longer
    declared on both classes (stale -- renamed, removed, or reconciled),
  * a member declared on only one class (the twin gained or lost a member).

Bounds -- what this gate does not catch (`sdd/DRIFT-RULES.md` Rule 7):

  * **Semantics of a pinned difference.** A pin fixes *which lines* may differ,
    not that differing that way is correct.  Re-pinning is a deliberate edit
    with a reason, but the reason is prose: only Dafny verification and review
    judge whether the new divergence is sound.
  * **Line-for-line pins are order-sensitive.** A pinned difference reordered
    without changing its content re-fires the gate.  That is a false positive by
    intent -- cheap to clear by re-pinning, and the alternative (order-free
    comparison) would let a moved clause pass as unchanged.
  * **Comment drift.** Comments are stripped before comparison, so an
    explanatory note that goes stale on one side passes.  Deliberate: the twin's
    comments legitimately differ (they cross-reference the reference class).
  * **Cross-member consistency.** Each member is compared to its namesake;
    nothing checks that the twin's members compose into the same state machine.
  * **The trait itself.** Drift between ``BackendContract.dfy`` and either class
    is out of scope -- Dafny verification covers that, since a class that fails
    to refine its trait does not verify.

The seeded-mutation corpus in ``tests/scripts/test_check_dafny_twin_parity.py``
exercises those bounds both ways: it asserts the in-scope mutation classes are
caught and asserts the out-of-scope ones are missed, so the bounds above stay
executable rather than aspirational.

Parsing is a scoped scan over the Dafny source -- no Dafny toolchain needed, so
this runs in ``hatch run lint`` on every change rather than only in the
path-gated formal-verification job.

Run with:
  hatch run check-dafny-twin-parity
  python scripts/check_dafny_twin_parity.py
  python scripts/check_dafny_twin_parity.py --print-pins   # paste-ready re-pin
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REFERENCE_CLASS = "MemoryBackend"
TWIN_CLASS = "MemoryBackendMinimal"

# A parse yielding fewer members than this means the source shape moved out from
# under the scanner; fail loudly rather than report a vacuous "parity".  The two
# classes carry 19 members each at the time of writing, so this is a floor with
# room for deliberate shrinkage, not a pin.
MIN_MEMBERS = 12


# ---------------------------------------------------------------------------
# Divergence register
#
# The membership of the comparison is *derived* from the source (both class
# bodies are parsed); this register holds only the decisions.  Each entry needs
# a reason -- an unexplained entry is indistinguishable from a silenced failure
# -- and the exact changed lines it licenses, so the rest of the member stays
# compared.  Regenerate the ``changes`` tuples with ``--print-pins``; write the
# ``reason`` by hand.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Divergence:
    """A licensed difference between the reference member and its twin.

    ``changes`` is the signature returned by ``divergence_signature``: the
    added and removed normalised lines, in order, with context excluded.  A
    difference the twin grows beyond these lines fails the gate.
    """

    reason: str
    changes: tuple[str, ...]


DIVERGENT: dict[str, Divergence] = {
    "constructor": Divergence(
        reason=(
            "The twin exists to witness the narrower capability set: it declares "
            "neither CapWriteResultNative nor CapUserMetadata, and carries its own "
            "name so error values are attributable. This difference is the reason "
            "the class exists -- reconciling it would delete the witness."
        ),
        changes=(
            '-ensures name == "memory"',
            '+ensures name == "memory-minimal"',
            "-CapAtomicWrite, CapAtomicMove, CapMetadata, CapSeekableRead,",
            "-CapWriteResultNative, CapUserMetadata}",
            "+CapAtomicWrite, CapAtomicMove, CapMetadata, CapSeekableRead}",
            '-name := "memory";',
            '+name := "memory-minimal";',
            "-CapAtomicWrite, CapAtomicMove, CapMetadata, CapSeekableRead,",
            "-CapWriteResultNative, CapUserMetadata};",
            "+CapAtomicWrite, CapAtomicMove, CapMetadata, CapSeekableRead};",
        ),
    ),
    "Write": Divergence(
        reason=(
            "Follows from the constructor divergence. Without CapWriteResultNative "
            "the native-timestamp binding is unreachable, so the twin drops the "
            "binding and passes None where the reference passes it -- which is what "
            "makes the WR-010 BasicSource branch live code here and dead code in the "
            "reference class."
        ),
        changes=(
            "-var ts: Option<int> :=",
            "-if CapWriteResultNative in capabilities",
            "-then Some(0)",
            "-else None;",
            "-ts,",
            "+None,",
            "-ts,",
            "+None,",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Lexer-ish helpers (pure over source text)
# ---------------------------------------------------------------------------


_CHAR_LITERAL_RE = re.compile(r"'(?:\\(?:u[0-9a-fA-F]{4}|.)|[^'\\])'")


def _char_literal_len(text: str, i: int) -> int:
    """Return the length of the Dafny character literal at *i*, or 0.

    Dafny allows an apostrophe inside an identifier (``xs'``, ``EnsureParents'``),
    which a naive quote scanner reads as an opening quote -- it then consumes
    everything up to the *next* prime, merging unrelated code into one token.
    ``BackendContract.dfy`` contains exactly that shape, so the distinction is
    load-bearing even though the file this gate parses today happens to be free
    of it.  A char literal is a quote, one character (or one escape), a quote;
    anything else at *i* is a prime.
    """
    match = _CHAR_LITERAL_RE.match(text, i)
    return len(match.group(0)) if match else 0


def strip_comments(text: str) -> str:
    """Blank out Dafny comments, preserving every line break and offset.

    Comments become spaces rather than being deleted so that offsets into the
    returned text still index the original source: the class slicer and the
    member splitter both run on the stripped text, and their spans stay usable
    for reporting.  String (``"..."``) and character (``'/'``) literals are
    tracked so a ``//`` inside one is not mistaken for a comment start --
    ``AncestorsTraversableCheck`` compares against ``'/'`` on nearly every line.
    Nested ``/* */`` is handled by depth, as Dafny allows nesting.
    """
    out: list[str] = []
    i, n = 0, len(text)
    block_depth = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if block_depth:
            if ch == "/" and nxt == "*":
                block_depth += 1
                out.append("  ")
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            out.append("  ")
            i += 2
            continue
        if ch == "'" and _char_literal_len(text, i) == 0:
            # A prime-suffixed identifier (``var xs' := …``), not a literal.
            # Treating it as a quote would swallow everything up to the next
            # apostrophe, silently merging unrelated code.
            out.append(ch)
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_CLASS_RE = re.compile(r"^class\s+(?P<name>\w+)\b[^{]*\{", re.MULTILINE)

# A class member: two-space indented declaration, optional Dafny attributes
# between the keyword and the name (``method {:isolate_assertions} Copy``).
# ``constructor`` is anonymous here, so it keys on the keyword itself.
_MEMBER_RE = re.compile(
    r"^  (?:ghost\s+|static\s+|twostate\s+)*"
    r"(?P<kind>method|function|predicate|lemma|constructor)\b"
    r"(?P<attrs>(?:\s*\{:[^}]*\})*)"
    r"\s*(?P<name>\w*)",
    re.MULTILINE,
)


def class_body(stripped: str, classname: str) -> str:
    """Return the brace-delimited body of *classname* from comment-stripped text.

    Empty string when the class is absent or its braces never balance; both
    surface through the ``MIN_MEMBERS`` guard rather than passing as parity.
    """
    for match in _CLASS_RE.finditer(stripped):
        if match.group("name") != classname:
            continue
        start = match.end() - 1
        depth = 0
        for i in range(start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    return stripped[start + 1 : i]
        return ""
    return ""


def class_members(stripped: str, classname: str) -> dict[str, str]:
    """Return ``{member_name: source_text}`` for the direct members of *classname*.

    Each member runs from its declaration keyword to the start of the next
    declaration (or the end of the class), so the returned text covers the
    signature, the specification clauses and the body together -- a dropped
    ``ensures`` is drift just as much as a changed statement is.
    """
    body = class_body(stripped, classname)
    matches = list(_MEMBER_RE.finditer(body))
    out: dict[str, str] = {}
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        name = match.group("name") or match.group("kind")
        out[name] = body[match.start() : end]
    return out


def normalise(member_text: str) -> list[str]:
    """Reduce a member to comparable lines: no comments, no layout.

    Comments are already gone (the caller works on stripped text).  Each line is
    trimmed and its internal whitespace runs collapsed, and empty lines are
    dropped, so reindentation and rewrapping are not drift.  Lines are kept
    rather than joined into one blob so the failure report can localise to a
    clause (`sdd/DRIFT-RULES.md` Rule 2).
    """
    lines = []
    for raw in member_text.splitlines():
        line = " ".join(raw.split())
        if line:
            lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Compare (pure)
# ---------------------------------------------------------------------------


def divergence_signature(ref_lines: list[str], twin_lines: list[str]) -> tuple[str, ...]:
    """Return the changed lines between reference and twin, context excluded.

    ``n=0`` drops context lines, so the signature records only what actually
    differs: an unrelated edit *inside* a pinned member does not invalidate the
    pin, while any new divergence adds a line to the signature and does.  Hunk
    and file headers are excluded for the same reason -- they encode positions,
    which move for reasons that are not drift.
    """
    return tuple(
        line
        for line in difflib.unified_diff(ref_lines, twin_lines, lineterm="", n=0)
        if line[:1] in {"+", "-"} and not line.startswith(("---", "+++"))
    )


def _render_diff(member: str, ref_lines: list[str], twin_lines: list[str]) -> str:
    """Return an indented unified diff naming the differing clause (Rule 2)."""
    return "\n".join(
        f"      {line}"
        for line in difflib.unified_diff(
            ref_lines,
            twin_lines,
            fromfile=f"{REFERENCE_CLASS}.{member}",
            tofile=f"{TWIN_CLASS}.{member}",
            lineterm="",
            n=1,
        )
    )


def compare(reference: dict[str, str], twin: dict[str, str]) -> list[str]:
    """Return parity errors.  Empty list means parity holds."""
    errors: list[str] = []
    shared = set(reference) & set(twin)

    for member in sorted(set(reference) - set(twin)):
        errors.append(
            f"`{member}` is declared on {REFERENCE_CLASS} but missing from {TWIN_CLASS} "
            f"-- the twin must mirror every member of the reference class"
        )
    for member in sorted(set(twin) - set(reference)):
        errors.append(
            f"`{member}` is declared on {TWIN_CLASS} but missing from {REFERENCE_CLASS} "
            f"-- the twin may not carry members the reference class lacks"
        )

    for member in sorted(shared):
        ref_lines = normalise(reference[member])
        twin_lines = normalise(twin[member])
        actual = divergence_signature(ref_lines, twin_lines)
        pin = DIVERGENT.get(member)

        if pin is None:
            if actual:
                errors.append(
                    f"`{member}` body drift -- {REFERENCE_CLASS} and {TWIN_CLASS} differ. "
                    f"Port the {REFERENCE_CLASS} member onto {TWIN_CLASS} (the reference "
                    f"class is canonical), or pin the divergence with a reason in "
                    f"DIVERGENT in scripts/check_dafny_twin_parity.py "
                    f"(`--print-pins` emits the entry):\n"
                    f"{_render_diff(member, ref_lines, twin_lines)}"
                )
            continue

        if not actual:
            errors.append(
                f"DIVERGENT pins `{member}` but the two classes now agree -- the "
                f"divergence was reconciled; drop the entry"
            )
            continue

        if actual != pin.changes:
            errors.append(
                f"`{member}` divergence changed -- the difference between "
                f"{REFERENCE_CLASS} and {TWIN_CLASS} is no longer the pinned one, so "
                f"drift may have been layered on top of the intended divergence. "
                f"Pinned reason: {pin.reason}\n"
                f"      pinned: {list(pin.changes)}\n"
                f"      actual: {list(actual)}\n"
                f"{_render_diff(member, ref_lines, twin_lines)}"
            )

    for member in sorted(set(DIVERGENT) - shared):
        errors.append(
            f"DIVERGENT pins `{member}` but it is not declared on both classes (renamed or removed) -- drop the entry"
        )

    return errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dafny twin body-parity gate (BK-328).")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "sdd" / "formal" / "MemoryBackend.dfy",
        help="path to the Dafny source declaring both classes",
    )
    parser.add_argument(
        "--print-pins",
        action="store_true",
        help="print paste-ready DIVERGENT `changes` tuples for every differing member",
    )
    args = parser.parse_args(argv)

    stripped = strip_comments(args.source.read_text(encoding="utf-8"))
    reference = class_members(stripped, REFERENCE_CLASS)
    twin = class_members(stripped, TWIN_CLASS)

    for label, members in ((REFERENCE_CLASS, reference), (TWIN_CLASS, twin)):
        if len(members) < MIN_MEMBERS:
            print(
                f"FAIL: parsed only {len(members)} member(s) of {label} from {args.source} "
                f"(expected at least {MIN_MEMBERS}) -- the source shape moved out from "
                f"under scripts/check_dafny_twin_parity.py",
                file=sys.stderr,
            )
            return 1

    if args.print_pins:
        # Emits membership only. The `reason` is the author's judgement and is
        # deliberately not generated -- a pin without one is a silenced failure.
        for member in sorted(set(reference) & set(twin)):
            changes = divergence_signature(normalise(reference[member]), normalise(twin[member]))
            if not changes:
                continue
            print(f'    "{member}": Divergence(')
            print('        reason="TODO: why this difference is correct",')
            print("        changes=(")
            for line in changes:
                print(f"            {line!r},")
            print("        ),")
            print("    ),")
        return 0

    errors = compare(reference, twin)
    if errors:
        print(f"Dafny twin parity verification failed ({args.source}):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            f"\n{TWIN_CLASS} duplicates {REFERENCE_CLASS} because Dafny has no "
            f"class-to-class inheritance, and each class verifies independently, so "
            f"a one-sided edit leaves dafny_verify.sh green. Mirror the change, or "
            f"record a deliberate divergence in DIVERGENT with its reason.",
            file=sys.stderr,
        )
        return 1

    compared = len(set(reference) & set(twin)) - len(DIVERGENT)
    print(f"Dafny twin parity verified ({compared} member(s) in lockstep, {len(DIVERGENT)} declared divergence(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
