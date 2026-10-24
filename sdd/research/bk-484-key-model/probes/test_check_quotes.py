"""Checks of the quote check's matching rule."""

from __future__ import annotations

import pytest
from check_quotes import found, norm

SOURCE = norm("The data model is flat. There is no hierarchy of subfolders. The limit applies to the path.")


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("The data model is flat.", True),
        ("The data model is flat. … There is no hierarchy", True),
        ("model is flat … The limit applies …", True),
        ("There is no hierarchy … The data model is flat.", False),
        ("The limit applies … no hierarchy", False),
        ("The data model is flat … The data model is flat", False),
        ("The data model is round.", False),
    ],
)
def test_found_requires_fragments_in_order(quote: str, expected: bool) -> None:
    assert found(quote, SOURCE) is expected
