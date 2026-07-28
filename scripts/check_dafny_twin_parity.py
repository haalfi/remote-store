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
branch).  Concretely for ``Write``: the reference member normalises to 114 lines
and the twin to 110, the pin licenses 6 removals and 2 additions, and the other
108 of the twin's 110 lines stay compared -- where an allowlist would drop all
110.

Membership is derived, not listed.  Every two-space-indented declaration in a
class body is claimed as a member, and a declaration whose keyword the scanner
does not know is a **failure**, not a skip -- `sdd/DRIFT-RULES.md` Rule 3 warns
against exactly the parallel list a keyword allow-list would be, and a silently
unmembered declaration is how a field added to one class only would pass.
Anything before the first declaration is compared as ``(class preamble)`` rather
than discarded, for the same reason.

Fails on:

  * a member whose normalised bodies differ with no pin (drift -- the bug this
    gate exists to catch), reported as a unified diff of the normalised lines so
    the differing clause is named rather than just the member,
  * a pinned member whose difference is no longer the pinned one (drift layered
    on top of an intended divergence), reported as pinned-versus-actual,
  * a ``DIVERGENT`` entry whose member no longer differs, or is no longer
    declared on both classes (stale -- renamed, removed, or reconciled),
  * a member declared on only one class (the twin gained or lost a member).

Bounds -- what this gate does not catch (`sdd/DRIFT-RULES.md` Rule 7).  Each is
tagged with how it is held, because "the corpus covers the bounds" was an
overclaim in the first version of this docstring and the distinction is the whole
point of stating a bound:

  * **Comment drift.** [corpus] Comments are stripped before comparison, so an
    explanatory note that goes stale on one side passes.  Deliberate: the twin's
    comments legitimately differ (they cross-reference the reference class).
  * **Line-for-line pins are order-sensitive.** [corpus, as a fires-by-intent
    test] A pinned difference reordered without changing its content re-fires the
    gate.  A false positive by intent -- cheap to clear by re-pinning, and the
    alternative (order-free comparison) would let a moved clause pass as
    unchanged.  Held by a test so a later "improvement" cannot quietly drop it.
  * **Semantics of a pinned difference.** [argued, not testable] A pin fixes
    *which lines* may differ, not that differing that way is correct.  Re-pinning
    is a deliberate edit with a reason, but the reason is prose: only Dafny
    verification and review judge whether the new divergence is sound.
  * **Cross-member consistency.** [argued, not testable] Each member is compared
    to its namesake; nothing checks that the twin's members compose into the same
    state machine.
  * **The trait itself.** [structural] Drift between ``BackendContract.dfy`` and
    either class is out of scope -- the gate reads one file, and Dafny
    verification covers the trait, since a class that fails to refine it does not
    verify.  Not corpus-held because a mutation to a file the gate never opens
    could only ever produce a tautological pass.

So two of the five are executable, and the corpus does not stand in for the other
three.  Separately from the bounds, the corpus asserts every in-scope mutation
class *is* caught, and that half is the positive control the zero-failure result
depends on.

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


def blank_literals(stripped: str) -> str:
    """Blank the *contents* of string and character literals, preserving offsets.

    ``strip_comments`` deliberately keeps literal contents — the ``constructor``
    pin turns on ``"memory"`` versus ``"memory-minimal"``, so the comparison text
    must retain them.  Structural scanning must not: ``class_body`` counts braces,
    and a ``"{"`` or ``'}'`` inside a literal would desync the class slicer
    silently.  This returns a same-length twin of *stripped* with literal bodies
    replaced by spaces, so spans found here index the literal-preserving text
    exactly.  Same hazard class as the prime-identifier one, handled the same way
    rather than left as a bound.
    """
    out = list(stripped)
    i, n = 0, len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == "'":
            length = _char_literal_len(stripped, i)
            if length:
                for j in range(i + 1, i + length - 1):
                    out[j] = " "
                i += length
                continue
            i += 1
            continue
        if ch == '"':
            i += 1
            while i < n and stripped[i] != '"':
                if stripped[i] == "\\" and i + 1 < n:
                    out[i] = out[i + 1] = " "
                    i += 2
                    continue
                if stripped[i] != "\n":
                    out[i] = " "
                i += 1
            i += 1
            continue
        i += 1
    return "".join(out)


_CLASS_RE = re.compile(r"^class\s+(?P<name>\w+)\b[^{]*\{", re.MULTILINE)

# Modifiers that may precede a declaration keyword, and the keywords themselves.
# Kept as an explicit vocabulary so an unrecognised one FAILS rather than being
# silently dropped or absorbed into the preceding member: a keyword allow-list is
# the parallel list `sdd/DRIFT-RULES.md` Rule 3 warns about, so the enumeration is
# derived from the source (every two-space declaration line is claimed) and this
# set only decides whether the gate understands what it found.
_MODIFIERS = frozenset({"ghost", "static", "twostate", "opaque", "least", "greatest", "abstract"})
_DECL_KEYWORDS = frozenset(
    {
        "method",
        "function",
        "predicate",
        "lemma",
        "constructor",
        "const",
        "var",
        "iterator",
        "copredicate",
        "colemma",
        "inductive",
    }
)

# A declaration line: exactly two spaces of indent, then an identifier character.
# Specification clauses and statements are indented deeper, and a declaration
# always opens with a keyword — so a two-space line starting with punctuation is a
# continuation, not a declaration.  ``Write``'s multi-line signature closes its
# parameter list with ``  )`` at exactly this indent, which is why the guard is
# "starts with a letter" rather than "is not a brace".
_DECL_LINE_RE = re.compile(r"^  (?=[A-Za-z_])(?P<decl>.*)$", re.MULTILINE)
_ATTR_RE = re.compile(r"\{:[^}]*\}")

# Modifiers, then the declaration keyword, then the declared name if there is one
# (``constructor`` has none).  Applied after attributes are stripped.
_DECL_SHAPE_RE = re.compile(
    r"\s*(?:(?:" + "|".join(sorted(_MODIFIERS)) + r")\s+)*(?P<keyword>\w+)\s*(?P<name>[A-Za-z_]\w*)?"
)


class ParseError(Exception):
    """The Dafny source used a shape the scanner does not understand."""


def class_body(structural: str, classname: str) -> tuple[int, int]:
    """Return the ``(start, end)`` span of *classname*'s body in the text.

    Takes the **structural** text (comments stripped *and* literals blanked) so
    brace counting cannot be thrown by a brace inside a literal.  The returned
    span indexes the literal-preserving text identically, since every transform
    is length-preserving.  ``(-1, -1)`` when the class is absent or its braces
    never balance; both surface through the ``MIN_MEMBERS`` guard.
    """
    for match in _CLASS_RE.finditer(structural):
        if match.group("name") != classname:
            continue
        start = match.end() - 1
        depth = 0
        for i in range(start, len(structural)):
            if structural[i] == "{":
                depth += 1
            elif structural[i] == "}":
                depth -= 1
                if depth == 0:
                    return start + 1, i
        return -1, -1
    return -1, -1


def _member_name(decl: str, classname: str) -> str:
    """Return the member name for a declaration line, or raise ``ParseError``.

    Strips Dafny attributes (``method {:isolate_assertions} Copy``), consumes any
    modifiers, then requires a known declaration keyword.  An unknown keyword is
    an error rather than a skip: silently unmembering a declaration is exactly the
    failure mode that would let a field added to one class only pass the gate.
    """
    match = _DECL_SHAPE_RE.match(_ATTR_RE.sub(" ", decl))
    if match is None:
        raise ParseError(f"{classname}: declaration with no keyword: {decl.strip()!r}")
    keyword = match.group("keyword")
    if keyword not in _DECL_KEYWORDS:
        raise ParseError(
            f"{classname}: unrecognised declaration keyword {keyword!r} in "
            f"{decl.strip()!r}. Add it to _DECL_KEYWORDS in "
            f"scripts/check_dafny_twin_parity.py so the member is compared; "
            f"leaving it unknown would drop the declaration from the gate."
        )
    # ``constructor`` is anonymous in this model, so it keys on its keyword.
    return match.group("name") or keyword


def class_members(literal_text: str, structural: str, classname: str) -> dict[str, str]:
    """Return ``{member_name: source_text}`` for the direct members of *classname*.

    Each member runs from its declaration line to the next declaration (or the end
    of the class), so the returned text covers the signature, the specification
    clauses and the body together — a dropped ``ensures`` is drift just as much as
    a changed statement is.  Anything before the first declaration is returned
    under ``(class preamble)`` rather than discarded, so a field or stray
    construct at the top of one class cannot vanish from the comparison.
    """
    start, end = class_body(structural, classname)
    if start < 0:
        return {}
    spans: list[tuple[int, str]] = []
    for match in _DECL_LINE_RE.finditer(structural, start, end):
        spans.append((match.start(), _member_name(match.group("decl"), classname)))

    out: dict[str, str] = {}
    preamble_end = spans[0][0] if spans else end
    preamble = literal_text[start:preamble_end]
    if preamble.strip():
        out["(class preamble)"] = preamble
    for idx, (offset, name) in enumerate(spans):
        stop = spans[idx + 1][0] if idx + 1 < len(spans) else end
        out[name] = literal_text[offset:stop]
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

    literal_text = strip_comments(args.source.read_text(encoding="utf-8"))
    structural = blank_literals(literal_text)
    try:
        reference = class_members(literal_text, structural, REFERENCE_CLASS)
        twin = class_members(literal_text, structural, TWIN_CLASS)
    except ParseError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

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
