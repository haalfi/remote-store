"""Tests for scripts/check_dafny_twin_parity.py (BK-328).

Three layers:

* **Unit** -- ``strip_comments`` (comment forms, char literals vs prime
  identifiers, offset preservation), ``class_body`` / ``class_members``
  (scoping, attributes, anonymous constructor), ``normalise`` and
  ``divergence_signature``.
* **Compare** -- every branch of the verdict: agreement, unpinned drift, a
  held pin, a pin whose difference changed, a reconciled pin, a stale pin, and
  a member present on one class only.
* **Seeded mutation corpus** -- the `sdd/DRIFT-RULES.md` Rule 7 miss-rate
  estimate, run against the *live* Dafny source. In-scope mutations must be
  caught; the out-of-scope ones named in the script's Bounds section must be
  missed. The second half is the point: it keeps the documented bound honest,
  so a future change that silently widens or narrows the gate's reach fails
  here rather than being discovered by a reader trusting the docstring.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
DAFNY_SOURCE = ROOT / "sdd" / "formal" / "MemoryBackend.dfy"


@pytest.fixture(scope="module")
def mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_dafny_twin_parity

    return check_dafny_twin_parity


@pytest.fixture(scope="module")
def live_source() -> str:
    return DAFNY_SOURCE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# strip_comments
# ---------------------------------------------------------------------------


class TestStripComments:
    def test_line_comment_becomes_spaces_preserving_offsets(self, mod):
        source = "var x := 1;  // drop me\nvar y := 2;\n"
        stripped = mod.strip_comments(source)
        assert len(stripped) == len(source)
        assert stripped.count("\n") == source.count("\n")
        assert "drop me" not in stripped
        assert "var y := 2;" in stripped

    def test_block_comment_nests(self, mod):
        # A non-nesting scanner would close at the inner `*/` and leave
        # `still outer */` in the source as code.
        source = "a /* outer /* inner */ still outer */ b\n"
        stripped = mod.strip_comments(source)
        assert "outer" not in stripped
        assert "inner" not in stripped
        assert len(stripped) == len(source)
        assert stripped.split() == ["a", "b"]

    def test_slashes_inside_string_literal_survive(self, mod):
        # BackendContract.dfy really does contain `ContainsSub(s, "//")`; reading
        # that as a comment would silently delete the rest of the line.
        source = 'var doubled := ContainsSub(s, "//");  // PATH-005\n'
        stripped = mod.strip_comments(source)
        assert '"//"' in stripped
        assert "PATH-005" not in stripped

    def test_slash_char_literal_survives(self, mod):
        # AncestorsTraversableCheck compares against '/' on nearly every line.
        source = "if path[i] == '/' {  // boundary\n"
        stripped = mod.strip_comments(source)
        assert "'/'" in stripped
        assert "boundary" not in stripped

    def test_prime_identifier_is_not_a_char_literal(self, mod):
        # Dafny allows `xs'` as an identifier. Treating the prime as an opening
        # quote would swallow everything to the next prime -- here, merging two
        # statements and hiding whatever lies between them.
        source = "var xs' := xs[1..];\nvar ys' := ys[..i];\nvar keep := 1;\n"
        stripped = mod.strip_comments(source)
        assert stripped == source
        assert "keep" in stripped

    def test_escaped_char_literal_consumed_whole(self, mod):
        source = "var nl := '\\n'; var q := '\\''; var after := 1;\n"
        stripped = mod.strip_comments(source)
        assert stripped == source

    def test_escaped_quote_in_string_does_not_end_it(self, mod):
        source = 'var s := "a\\"// not a comment"; var after := 1;\n'
        stripped = mod.strip_comments(source)
        assert "not a comment" in stripped
        assert "after" in stripped

    def test_all_repo_dafny_sources_keep_their_shape(self, mod):
        # Offset preservation is what lets the class slicer and member splitter
        # run on stripped text; assert it over every real source, not a fixture.
        for path in sorted((ROOT / "sdd" / "formal").glob("*.dfy")):
            original = path.read_text(encoding="utf-8")
            stripped = mod.strip_comments(original)
            assert len(stripped) == len(original), path
            assert stripped.count("\n") == original.count("\n"), path


# ---------------------------------------------------------------------------
# Class and member extraction
# ---------------------------------------------------------------------------


SAMPLE = textwrap.dedent(
    """\
    class Alpha extends Backend {

      constructor ()
        ensures name == "alpha"
      {
        name := "alpha";
      }

      method {:isolate_assertions} Copy(src: Path) returns (r: int)
        ensures r == 1
      {
        r := 1;
      }

      lemma {:induction false} Helper(p: Path)
      {
      }
    }

    class Beta extends Backend {
      method Copy(src: Path) returns (r: int)
      {
        r := 2;
      }
    }
    """
)


class TestClassMembers:
    def test_scopes_to_named_class(self, mod):
        members = mod.class_members(SAMPLE, "Beta")
        assert set(members) == {"Copy"}
        assert "r := 2;" in members["Copy"]

    def test_parses_attributes_and_anonymous_constructor(self, mod):
        members = mod.class_members(SAMPLE, "Alpha")
        assert set(members) == {"constructor", "Copy", "Helper"}
        # The member text spans signature, specification clauses and body.
        assert "ensures r == 1" in members["Copy"]
        assert "r := 1;" in members["Copy"]

    def test_missing_class_yields_empty(self, mod):
        assert mod.class_members(SAMPLE, "Gamma") == {}

    def test_unbalanced_braces_yield_empty(self, mod):
        assert mod.class_body("class Alpha extends Backend {\n  method M()\n", "Alpha") == ""

    def test_live_classes_declare_the_same_members(self, mod, live_source):
        stripped = mod.strip_comments(live_source)
        reference = mod.class_members(stripped, mod.REFERENCE_CLASS)
        twin = mod.class_members(stripped, mod.TWIN_CLASS)
        assert set(reference) == set(twin)
        assert len(reference) >= mod.MIN_MEMBERS


# ---------------------------------------------------------------------------
# normalise / divergence_signature
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_collapses_layout_only_differences(self, mod):
        a = "  method M()\n    ensures  r   ==  1\n"
        b = "method M()\n\n        ensures r == 1\n\n"
        assert mod.normalise(a) == mod.normalise(b)

    def test_keeps_lines_separate_for_localisation(self, mod):
        assert mod.normalise("a\nb\n") == ["a", "b"]


class TestDivergenceSignature:
    def test_empty_when_equal(self, mod):
        assert mod.divergence_signature(["a", "b"], ["a", "b"]) == ()

    def test_excludes_context_and_headers(self, mod):
        sig = mod.divergence_signature(["a", "b", "c"], ["a", "X", "c"])
        assert sig == ("-b", "+X")

    def test_unrelated_edit_shared_by_both_sides_leaves_signature_stable(self, mod):
        # The property that makes a pin durable: editing a line that both classes
        # share does not disturb the recorded divergence.
        before = mod.divergence_signature(["keep", "ref"], ["keep", "twin"])
        after = mod.divergence_signature(["edited", "ref"], ["edited", "twin"])
        assert before == after == ("-ref", "+twin")


# ---------------------------------------------------------------------------
# compare -- every verdict branch
# ---------------------------------------------------------------------------


@pytest.fixture
def unpinned(mod, monkeypatch):
    """Install an empty DIVERGENT register, so these cases see no live pins."""
    monkeypatch.setattr(mod, "DIVERGENT", {})
    return mod


@pytest.fixture
def pinned(mod, monkeypatch):
    """Install a one-entry DIVERGENT register pinning ``M``'s difference."""
    monkeypatch.setattr(
        mod,
        "DIVERGENT",
        {"M": mod.Divergence(reason="deliberate", changes=("-ref only", "+twin only"))},
    )
    return mod


class TestCompare:
    def test_agreement_passes(self, unpinned):
        assert unpinned.compare({"M": "a\nb\n"}, {"M": "a\nb\n"}) == []

    def test_layout_difference_is_not_drift(self, unpinned):
        assert unpinned.compare({"M": "  a\n   b\n"}, {"M": "a\n\nb\n"}) == []

    def test_unpinned_drift_fails_and_localises(self, unpinned):
        errors = unpinned.compare({"M": "a\nkeep\n"}, {"M": "b\nkeep\n"})
        assert len(errors) == 1
        assert "body drift" in errors[0]
        # Rule 2: the report names the differing line, not just the member.
        assert "-a" in errors[0]
        assert "+b" in errors[0]

    def test_pinned_difference_passes(self, pinned):
        errors = pinned.compare({"M": "shared\nref only\n"}, {"M": "shared\ntwin only\n"})
        assert errors == []

    def test_edit_elsewhere_in_pinned_member_is_caught(self, pinned):
        # The reason to pin rather than skip: the rest of a divergent member
        # stays under the gate.
        errors = pinned.compare({"M": "shared\nref only\n"}, {"M": "CHANGED\ntwin only\n"})
        assert len(errors) == 1
        assert "divergence changed" in errors[0]
        assert "deliberate" in errors[0]  # the pinned reason is surfaced

    def test_reconciled_pin_is_reported_as_stale(self, pinned):
        errors = pinned.compare({"M": "same\n"}, {"M": "same\n"})
        assert len(errors) == 1
        assert "now agree" in errors[0]

    def test_pin_for_absent_member_is_reported_as_stale(self, pinned):
        errors = pinned.compare({"Other": "x\n"}, {"Other": "x\n"})
        assert len(errors) == 1
        assert "not declared on both classes" in errors[0]

    def test_member_missing_from_twin_fails(self, unpinned):
        errors = unpinned.compare({"M": "a\n", "Gone": "b\n"}, {"M": "a\n"})
        assert len(errors) == 1
        assert "missing from" in errors[0]
        assert "Gone" in errors[0]

    def test_member_only_on_twin_fails(self, unpinned):
        errors = unpinned.compare({"M": "a\n"}, {"M": "a\n", "Extra": "b\n"})
        assert len(errors) == 1
        assert "Extra" in errors[0]


# ---------------------------------------------------------------------------
# Seeded mutation corpus -- DRIFT-RULES.md Rule 7
# ---------------------------------------------------------------------------


def _mutate_twin(source: str, old: str, new: str) -> str:
    """Apply ``old -> new`` inside the twin class only.

    Anchored to the twin so a mutation cannot accidentally edit both classes in
    step (which would be invisible to a parity gate by construction, and would
    make the corpus prove nothing).  Uniqueness is asserted so a mutation whose
    anchor has drifted out of the source fails loudly instead of silently
    becoming a no-op that "passes".
    """
    start = source.index(f"class {TWIN}")
    region = source[start:]
    occurrences = region.count(old)
    assert occurrences == 1, f"anchor {old!r} appears {occurrences}x in the twin class (expected 1)"
    return source[:start] + region.replace(old, new)


TWIN = "MemoryBackendMinimal"

# Mutation classes the gate claims to catch.
#
# The first two were run through `dafny verify` while writing this corpus and
# both verified clean -- they are the measured instances of drift that the
# formal layer cannot see, and they define the gate's reason to exist. The rest
# are contract-bearing shapes (a dropped or added postcondition, a changed loop
# bound, a flipped connective, a renamed member, drift layered on an intended
# divergence); Dafny rejects several of those on its own, and the gate catching
# them too is defence in depth plus a far more localised message.
IN_SCOPE: tuple[tuple[str, str, str], ...] = (
    (
        # Verified silent: `dafny verify` reports 478 verified, 0 errors on this
        # mutation. The contract pins FolderInfo's .path, .file_count and
        # .total_size but not its second field, so the twin can return a
        # different folder name for every folder and stay provable. This is the
        # case that justifies the gate, not a synthetic one.
        "underdetermined-return-value",
        "        r := Ok(FolderInfo(path, path, file_count, total_size));\n",
        "        r := Ok(FolderInfo(path, Root, file_count, total_size));\n",
    ),
    (
        # Also verified silent (478 verified, 0 errors): proof structure is
        # invisible to the verifier by construction.
        "proof-hint-drift",
        "    var is_file := path in fs && fs[path].FileEntry?;\n",
        "    var is_file := path in fs && fs[path].FileEntry?;\n    assert true;\n",
    ),
    (
        "dropped-postcondition",
        "    ensures IsFile(old(fs), path) ==> r.Ok?\n",
        "",
    ),
    (
        "changed-loop-bound",
        "while i < |path| - 1",
        "while i <= |path| - 1",
    ),
    (
        "flipped-connective",
        "r := Ok(is_file && ancestors_ok);",
        "r := Ok(is_file || ancestors_ok);",
    ),
    (
        "added-postcondition",
        "  method Exists(path: Path) returns (r: Result<bool>)\n",
        "  method Exists(path: Path) returns (r: Result<bool>)\n    ensures true\n",
    ),
    (
        "renamed-member",
        "  method GetFolderInfo(",
        "  method GetFolderInfoRenamed(",
    ),
    (
        "drift-inside-pinned-member",
        "r.value.path == path && r.value.size == |content|",
        "r.value.path == path && r.value.size == |path|",
    ),
)

# Mutation classes the script's Bounds section says it does NOT catch. Asserting
# the miss keeps the documented bound executable: if a change here starts
# catching one of these, the docstring is now wrong and this test says so.
OUT_OF_SCOPE: tuple[tuple[str, str, str], ...] = (
    (
        "comment-drift",
        "  // ID-209: duplicated lemmas (Dafny lacks class-to-class inheritance).",
        "  // Stale note that no longer matches the reference class.",
    ),
    (
        "reindentation",
        "    var path_exists := path in fs;\n    var ancestors_ok := AncestorsTraversableCheck(path);",
        "      var path_exists := path in fs;\n        var ancestors_ok := AncestorsTraversableCheck(path);",
    ),
)


def _errors_for(mod, source: str) -> list[str]:
    stripped = mod.strip_comments(source)
    return mod.compare(
        mod.class_members(stripped, mod.REFERENCE_CLASS),
        mod.class_members(stripped, mod.TWIN_CLASS),
    )


class TestSeededMutations:
    def test_unmutated_live_source_passes(self, mod, live_source):
        assert _errors_for(mod, live_source) == []

    @pytest.mark.parametrize(("label", "old", "new"), IN_SCOPE, ids=[m[0] for m in IN_SCOPE])
    def test_in_scope_mutation_is_caught(self, mod, live_source, label, old, new):
        errors = _errors_for(mod, _mutate_twin(live_source, old, new))
        assert errors, f"{label}: seeded drift went undetected"

    @pytest.mark.parametrize(("label", "old", "new"), OUT_OF_SCOPE, ids=[m[0] for m in OUT_OF_SCOPE])
    def test_out_of_scope_mutation_is_missed(self, mod, live_source, label, old, new):
        errors = _errors_for(mod, _mutate_twin(live_source, old, new))
        assert errors == [], (
            f"{label}: the gate now catches a mutation its Bounds section says it "
            f"misses -- widen the docstring in scripts/check_dafny_twin_parity.py"
        )

    def test_pinned_member_keeps_its_unchanged_remainder_under_the_gate(self, mod, live_source):
        # `Write` is pinned, and pinning must not degrade to skipping: a change
        # to the ~110 normalised lines outside the pinned difference still fails.
        mutated = _mutate_twin(
            live_source,
            "r.value.path == path && r.value.size == |content|",
            "r.value.path == path && r.value.size == |path|",
        )
        errors = _errors_for(mod, mutated)
        assert any("Write" in error and "divergence changed" in error for error in errors), errors

    def test_erasing_a_pinned_divergence_is_reported(self, mod, live_source):
        # Making the twin identical to the reference is not silently "more
        # parity": it deletes the satisfiability witness the twin exists to be.
        mutated = _mutate_twin(live_source, 'name := "memory-minimal";', 'name := "memory";')
        errors = _errors_for(mod, mutated)
        assert any("constructor" in error for error in errors), errors


# ---------------------------------------------------------------------------
# Live register + entry point
# ---------------------------------------------------------------------------


class TestLiveRegister:
    def test_live_parity_holds(self, mod, live_source):
        assert _errors_for(mod, live_source) == []

    def test_every_pin_carries_a_reason(self, mod):
        # Rule 6: a divergence with no rationale is indistinguishable from a
        # silenced failure.
        for member, divergence in mod.DIVERGENT.items():
            assert divergence.reason.strip(), f"{member} pinned without a reason"
            assert divergence.changes, f"{member} pinned with an empty change set"

    def test_main_returns_zero(self, mod):
        assert mod.main([]) == 0

    def test_main_fails_on_a_source_it_cannot_parse(self, mod, tmp_path):
        # The empty-parse guard: a source whose shape moved must fail loudly
        # rather than report a vacuous parity over zero members.
        stub = tmp_path / "stub.dfy"
        stub.write_text("class MemoryBackend extends Backend {\n}\n", encoding="utf-8")
        assert mod.main(["--source", str(stub)]) == 1

    def test_print_pins_emits_the_live_divergences(self, mod, capsys):
        assert mod.main(["--print-pins"]) == 0
        out = capsys.readouterr().out
        for member in mod.DIVERGENT:
            assert f'"{member}": Divergence(' in out
