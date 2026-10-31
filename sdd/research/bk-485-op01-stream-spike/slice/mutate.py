"""Prove the checks can fail: break the model one way at a time, expect FAIL."""

from __future__ import annotations

import contextlib
import io
import sys

import check_stream
import stream_model as m

ORIG = {k: getattr(m.Stream, k) for k in ("_check_readable", "_transfer", "close")}


def not_sticky(self):  # D16: Failed reads succeed again
    if self.state == m.CLOSED:
        raise ValueError("closed")


def partial_on_fail(self, n):  # D6/D16: bytes consumed before the failure
    if self.state == m.OPEN and self._env.fail:
        self.pos += 1
    return ORIG["_transfer"](self, n)


def close_raises(self):  # D36: release failure escapes close()
    hit = self._env.release_fail
    ORIG["close"](self)
    if hit:
        raise m.Unavailable("release")


def cancel_fails(self, n):  # D20: cancelled read leaves Failed, not Closed
    if self._env.take("cancel"):
        self._error, self.state = m.Unavailable("x"), m.FAILED
        raise m.Cancelled
    return ORIG["_transfer"](self, n)


MUTANTS = {
    "_check_readable": not_sticky,
    "_transfer": partial_on_fail,
    "close": close_raises,
}
MUTANTS_2 = {"_transfer": cancel_fails}

failed_to_kill = 0
for name, mutant in [*MUTANTS.items(), *[(k, v) for k, v in MUTANTS_2.items()]]:
    setattr(m.Stream, name, mutant)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc = check_stream.main()
    setattr(m.Stream, name, ORIG[name])
    print(f"{mutant.__name__:<16} {'killed' if rc else 'SURVIVED'}")
    failed_to_kill += rc == 0
sys.exit(failed_to_kill)
