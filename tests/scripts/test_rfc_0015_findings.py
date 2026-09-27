"""Unit tests for ``sdd/rfcs/rfc-0015-findings.py``'s ``triage()``.

BUG-295: a reply opening "Fixed in <sha>" was ``refuted`` whenever its body said
"stays", because the body-wide refuted search ran before the must-fix one. The
fixture holds the fixer's first replies on PRs #1029 and #1032 verbatim, from
``gh api repos/haalfi/remote-store/pulls/<N>/comments`` (first reply per finding
by ``created_at``); every one of the 17 is a fix.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLASSIFIER = _REPO_ROOT / "sdd" / "rfcs" / "rfc-0015-findings.py"
_FIXTURE = Path(__file__).parent / "fixtures" / "rfc_0015_first_replies.json"

_spec = importlib.util.spec_from_file_location("rfc_0015_findings", _CLASSIFIER)
assert _spec is not None
assert _spec.loader is not None
fnd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fnd)

_DATA = json.loads(_FIXTURE.read_text(encoding="utf-8"))
FIX_REPLIES: list[dict] = _DATA["fix_replies"]


class TestTriageFixReplies:
    def test_the_fixture_is_the_bugs_evidence(self) -> None:
        """Without the six "stays" replies the parametrized test below could not fail."""
        assert len(FIX_REPLIES) == 17
        assert {r["pr"] for r in FIX_REPLIES} == {1029, 1032}
        assert sum("stays" in r["body"] for r in FIX_REPLIES) == 6

    @pytest.mark.parametrize("reply", FIX_REPLIES, ids=[f"{r['pr']}-{r['reply']}" for r in FIX_REPLIES])
    def test_a_fix_reply_is_must_fix(self, reply: dict) -> None:
        assert reply["body"].startswith("Fixed in ")
        assert fnd.triage(reply["body"]) == "must-fix"

    def test_stays_is_not_a_refute_signal(self) -> None:
        """#1022's reply opens "Confirmed", not "Fixed in", so only dropping "stays" classifies it."""
        body = _DATA["stays_only"]["body"]
        assert body.startswith("Confirmed and fixed in ")
        assert "stays" in body
        assert fnd.triage(body) == "must-fix"


class TestTriageStillRefutes:
    """The fix must not turn a refutation into a must-fix."""

    @pytest.mark.parametrize(
        "body",
        [
            "Refuted: the text stays, because the claim holds.",
            "Not a defect. The paragraph stays as written.",
            "Declined. Fixed in a later PR would widen this one.",
            "The sentence is correct as written; I refute the reading.",
        ],
    )
    def test_refuted(self, body: str) -> None:
        assert fnd.triage(body) == "refuted"

    def test_opening_verdicts_keep_their_precedence(self) -> None:
        assert fnd.triage("Must-fix. Fixed in abc1234; the rest stays refuted.") == "must-fix"
        assert fnd.triage("Filed as BK-1. Fixed in nothing yet.") == "filed"
        assert fnd.triage("**Fixed in** abc1234, the declined half filed as BK-1.") == "must-fix"
        assert fnd.triage(None) == "unknown"
        assert fnd.triage("Thanks.") == "unknown"
