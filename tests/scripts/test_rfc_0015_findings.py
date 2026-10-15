"""Unit tests for ``sdd/rfcs/rfc-0015-findings.py``: ``triage()`` and how ``_gh``/``_git`` decode.

BUG-326: ``TestSubprocessDecoding`` pins UTF-8 decoding of ``gh`` and ``git``
output on a host whose locale encoding is cp1252.

BUG-295: a reply opening "Fixed in <sha>" was ``refuted`` whenever its body said
"stays", because the body-wide refuted search ran before the must-fix one. The
fixture holds the fixer's first replies on PRs #1029 and #1032 verbatim, from
``gh api repos/haalfi/remote-store/pulls/<N>/comments`` (first reply per finding
by ``created_at``); every one of the 17 is a fix.
"""

from __future__ import annotations

import importlib.util
import json
import locale
import subprocess
import sys
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


# U+00C1 encodes to C3 81 in UTF-8; 0x81 is the byte cp1252 has no character for,
# the one PR #1130's comments carried.
_A_ACUTE = "\N{LATIN CAPITAL LETTER A WITH ACUTE}"


def _child_writing(payload: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the ``gh``/``git`` binary for a child Python that writes ``payload`` raw.

    Only the argv is replaced: the call keeps the classifier's own keyword
    arguments and goes through the real ``subprocess.run``, so the decoding under
    test is the standard library's. ``locale.getencoding`` returning cp1252 is
    what a German-locale Windows host answers; patched so the reproduction fails
    on any host that does not run in UTF-8 mode, not only on Windows.
    """
    real_run = subprocess.run
    script = f"import sys; sys.stdout.buffer.write(bytes.fromhex({payload.hex()!r}))"

    def run(argv, **kwargs):
        return real_run([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(locale, "getencoding", lambda: "cp1252")


class TestSubprocessDecoding:
    """BUG-326: ``gh`` and ``git`` output is UTF-8, whatever the host's locale."""

    def test_gh_reads_a_byte_cp1252_cannot_decode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = f"{_A_ACUTE}nderung"
        payload = json.dumps([{"body": body}], ensure_ascii=False).encode("utf-8")
        assert b"\x81" in payload
        _child_writing(payload, monkeypatch)
        assert fnd._gh("pulls/1/comments") == [{"body": body}]

    def test_git_reads_a_byte_cp1252_cannot_decode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _child_writing(f"{_A_ACUTE}nderung\n".encode(), monkeypatch)
        assert fnd._git("log", "-1", "--format=%s").stdout == f"{_A_ACUTE}nderung\n"

    def test_a_byte_that_is_not_utf8_is_replaced_not_fatal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The ``errors`` policy: strict decoding cannot fail loudly here.

        On Windows ``communicate`` decodes in a reader thread, so a strict
        decode error leaves ``.stdout`` as ``None`` and surfaces as the
        unrelated ``TypeError`` this bug was. A replacement character keeps the
        run alive and the bad byte visible in the output.
        """
        _child_writing(b"ok \xff end", monkeypatch)
        assert fnd._git("log").stdout == "ok \N{REPLACEMENT CHARACTER} end"
