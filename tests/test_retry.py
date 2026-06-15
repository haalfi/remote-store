"""Tests for the shared pure retry helpers in ``remote_store._retry``.

The helpers carry the backoff/jitter/budget arithmetic and ``Retry-After``
parsing that the per-backend retry loops (Graph ``graph_send`` / monitor /
create-race write, sync HTTP ``_request_with_retry``) consume. Behaviour mirrors
spec RET-015 and the sync HTTP ``HTTP-RETRY-001`` contract.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from remote_store._retry import (
    RETRYABLE_STATUSES,
    apply_retry_after,
    backoff_envelope,
    budget_exhausted,
    equal_jitter_delay,
    full_jitter_delay,
    parse_retry_after,
)

# ---------------------------------------------------------------------------
# RETRYABLE_STATUSES
# ---------------------------------------------------------------------------


def test_retryable_statuses_are_5xx_plus_throttle() -> None:
    # RET-015: 5xx + 429; terminal statuses (403/404/409/423/507) are absent, and
    # 408 is deliberately left to the sync HTTP backend to add at its call site.
    assert {429, 500, 502, 503, 504} == RETRYABLE_STATUSES
    assert 408 not in RETRYABLE_STATUSES
    for terminal in (403, 404, 409, 423, 507):
        assert terminal not in RETRYABLE_STATUSES


# ---------------------------------------------------------------------------
# parse_retry_after
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("120", 120.0),
        ("0", 0.0),
        (None, None),
        ("", None),
        ("not-a-date-or-number", None),
    ],
)
def test_parse_retry_after_scalar_and_garbage(value: str | None, expected: float | None) -> None:
    assert parse_retry_after(value) == expected


def test_parse_retry_after_http_date_uses_injected_now() -> None:
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    future = "Wed, 01 Jan 2025 12:02:00 GMT"  # 120 s after `now`
    assert parse_retry_after(future, now=now) == pytest.approx(120.0)


def test_parse_retry_after_past_date_clamps_to_zero() -> None:
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    past = "Sun, 15 Mar 2020 12:00:00 GMT"
    assert parse_retry_after(past, now=now) == 0.0


def test_parse_retry_after_naive_date_assumed_utc() -> None:
    # A date with no timezone token is assumed UTC rather than rejected (GR-048).
    now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert parse_retry_after("Thu, 01 Jan 2026 00:00:00", now=now) == pytest.approx(timedelta(days=365).total_seconds())


# ---------------------------------------------------------------------------
# backoff_envelope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 1.0), (1, 2.0), (2, 4.0), (3, 8.0)],
)
def test_backoff_envelope_doubles_until_cap(attempt: int, expected: float) -> None:
    assert backoff_envelope(attempt, base=1.0, cap=60.0) == expected


def test_backoff_envelope_clamps_to_cap() -> None:
    assert backoff_envelope(10, base=1.0, cap=8.0) == 8.0


@given(
    attempt=st.integers(min_value=0, max_value=40),
    base=st.floats(min_value=0.0, max_value=10.0),
    cap=st.floats(min_value=0.0, max_value=120.0),
)
def test_backoff_envelope_never_exceeds_cap(attempt: int, base: float, cap: float) -> None:
    assert backoff_envelope(attempt, base=base, cap=cap) <= cap


@given(
    a=st.integers(min_value=0, max_value=20),
    b=st.integers(min_value=0, max_value=20),
)
def test_backoff_envelope_monotonic_in_attempt(a: int, b: int) -> None:
    lo, hi = sorted((a, b))
    assert backoff_envelope(lo, base=1.0, cap=1e9) <= backoff_envelope(hi, base=1.0, cap=1e9)


# ---------------------------------------------------------------------------
# equal_jitter_delay / full_jitter_delay
# ---------------------------------------------------------------------------


def test_equal_jitter_zero_jitter_is_exactly_the_envelope() -> None:
    assert equal_jitter_delay(2, base=1.0, cap=60.0, jitter=0.0) == 4.0


@given(
    attempt=st.integers(min_value=0, max_value=20),
    base=st.floats(min_value=0.1, max_value=5.0),
    cap=st.floats(min_value=0.1, max_value=60.0),
    jitter=st.floats(min_value=0.0, max_value=5.0),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_equal_jitter_within_envelope_band(attempt: int, base: float, cap: float, jitter: float, seed: int) -> None:
    envelope = backoff_envelope(attempt, base=base, cap=cap)
    delay = equal_jitter_delay(attempt, base=base, cap=cap, jitter=jitter, rng=random.Random(seed))
    assert envelope <= delay <= envelope + jitter


@given(
    attempt=st.integers(min_value=0, max_value=20),
    base=st.floats(min_value=0.1, max_value=5.0),
    cap=st.floats(min_value=0.1, max_value=60.0),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_full_jitter_within_zero_to_envelope(attempt: int, base: float, cap: float, seed: int) -> None:
    envelope = backoff_envelope(attempt, base=base, cap=cap)
    delay = full_jitter_delay(attempt, base=base, cap=cap, rng=random.Random(seed))
    assert 0.0 <= delay <= envelope


def test_injected_rng_makes_jitter_deterministic() -> None:
    a = equal_jitter_delay(1, base=1.0, cap=60.0, jitter=2.0, rng=random.Random(42))
    b = equal_jitter_delay(1, base=1.0, cap=60.0, jitter=2.0, rng=random.Random(42))
    assert a == b


# ---------------------------------------------------------------------------
# apply_retry_after
# ---------------------------------------------------------------------------


def test_apply_retry_after_none_returns_delay_unchanged() -> None:
    assert apply_retry_after(3.0, None) == 3.0


def test_apply_retry_after_raises_to_floor() -> None:
    assert apply_retry_after(3.0, 10.0) == 10.0


def test_apply_retry_after_keeps_larger_delay() -> None:
    assert apply_retry_after(10.0, 3.0) == 10.0


# ---------------------------------------------------------------------------
# budget_exhausted
# ---------------------------------------------------------------------------


def test_budget_exhausted_none_timeout_is_never_exhausted() -> None:
    assert budget_exhausted(elapsed=1e9, next_delay=1e9, timeout=None) is False


def test_budget_exhausted_lookahead_trips_before_overrun() -> None:
    # 8 s elapsed + a 3 s sleep would breach a 10 s budget.
    assert budget_exhausted(elapsed=8.0, next_delay=3.0, timeout=10.0) is True


def test_budget_exhausted_within_budget() -> None:
    assert budget_exhausted(elapsed=8.0, next_delay=1.0, timeout=10.0) is False


def test_budget_exhausted_zero_next_delay_is_plain_elapsed_check() -> None:
    assert budget_exhausted(elapsed=10.0, next_delay=0.0, timeout=10.0) is True
    assert budget_exhausted(elapsed=9.99, next_delay=0.0, timeout=10.0) is False
