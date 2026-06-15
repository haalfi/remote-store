"""Pure helpers for ``RetryPolicy``-driven backoff, shared by hand-rolled loops.

Several backends run their own retry loops because their transport has no native
retry hook: the async Graph request primitive (``graph_send``), its copy/move
monitor poller, its ``overwrite=True`` create-race write re-attempt, and the sync
HTTP backend's ``_request_with_retry``. Each had independently re-derived the same
arithmetic — the exponential envelope, jitter, the ``Retry-After`` floor, the
wall-clock budget check, and ``Retry-After`` header parsing.

This module is that arithmetic, factored out. It is deliberately **Layer 1**: no
sleeping, no ``async``, no loops, no I/O. The loops stay at their call sites and
consume these functions, so each backend keeps the control flow its transport
needs (terminal-vs-transient classification, ``return_on`` escape hatches,
typed-exception retry, body re-materialisation) while sharing the maths.

The envelope is ``min(backoff_max, backoff_base * 2**attempt)``; equal-jitter adds
a uniform ``[0, jitter]`` draw; ``Retry-After`` raises the wait to at least the
header value. ``rng`` and ``now`` are injectable so every helper is
deterministically testable.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from random import Random

# Statuses worth retrying: 5xx server errors (RET-015 / GR-033) plus 429
# throttling (GR-034). 403 / 404 / 409 / 423 / 507 are terminal — they do not
# clear on short-term retry. The sync HTTP backend additionally treats 408 as
# transient; it composes ``RETRYABLE_STATUSES | {408}`` at its own call site
# rather than widening this shared set (the Graph surface never sees a 408).
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse a ``Retry-After`` header into seconds, or ``None`` if unusable.

    Supports both forms RFC 7231 allows: delta-seconds (``"120"``) and an
    HTTP-date (``"Wed, 21 Oct 2025 07:28:00 GMT"``), the latter expressed as the
    remaining seconds until that instant (never negative). A date with no timezone
    token is assumed UTC rather than rejected. Returns ``None`` when the header is
    absent or unparseable, so the caller falls back to its computed backoff.

    Args:
        value: The raw header value, or ``None`` when absent.
        now: Reference instant for the HTTP-date delta. Defaults to the current
            UTC time; injectable for deterministic tests.
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    reference = now if now is not None else datetime.now(tz=timezone.utc)
    return max(0.0, (target - reference).total_seconds())


def backoff_envelope(attempt: int, *, base: float, cap: float) -> float:
    """Return the deterministic exponential envelope for a 0-based *attempt*.

    ``min(base * 2**attempt, cap)`` — the un-jittered backoff for the wait that
    follows the attempt numbered *attempt* (``0`` is the first attempt).
    """
    # 2.0**attempt (float base) keeps the product typed float — int**int is Any
    # in typeshed (a negative exponent would yield a float).
    return min(base * 2.0**attempt, cap)


def equal_jitter_delay(attempt: int, *, base: float, cap: float, jitter: float, rng: Random | None = None) -> float:
    """Envelope plus an additive uniform ``[0, jitter]`` draw.

    The strategy used by ``graph_send`` and the sync HTTP retry loop: the
    deterministic envelope sets the floor, and the jitter spreads retriers above
    it. *rng* defaults to the module ``random``; inject a ``random.Random`` for
    deterministic tests.
    """
    draw = (rng or random).uniform
    return backoff_envelope(attempt, base=base, cap=cap) + draw(0.0, jitter)  # noqa: S311 — jitter, not crypto


def full_jitter_delay(attempt: int, *, base: float, cap: float, rng: Random | None = None) -> float:
    """A uniform draw over the whole ``[0, envelope]`` band (full-jitter strategy).

    The strategy used by the Graph ``overwrite=True`` create-race re-attempt:
    randomising the *entire* delay desynchronises concurrent writers colliding in
    lockstep, where equal-jitter would still leave them clustered just above a
    shared floor. *rng* defaults to the module ``random``.
    """
    # Spec: GR-018 (Graph create-race write retry).
    draw = (rng or random).uniform
    return draw(0.0, backoff_envelope(attempt, base=base, cap=cap))  # noqa: S311 — jitter, not crypto


def apply_retry_after(delay: float, retry_after: float | None) -> float:
    """Raise *delay* to at least *retry_after* (the server-requested floor).

    Returns *delay* unchanged when *retry_after* is ``None`` (no header, or one
    that did not parse).
    """
    return delay if retry_after is None else max(delay, retry_after)


def budget_exhausted(*, elapsed: float, next_delay: float, timeout: float | None) -> bool:
    """Report whether the next wait would breach the wall-clock *timeout*.

    Look-ahead form: ``True`` when ``elapsed + next_delay >= timeout``. Pass
    ``next_delay=0.0`` for a plain "has the budget already run out?" check.
    ``timeout=None`` means no budget — always ``False``.
    """
    return timeout is not None and elapsed + next_delay >= timeout
