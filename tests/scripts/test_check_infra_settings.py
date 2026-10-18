"""Unit tests for scripts/check_infra_settings.py gate 3b (literal ``-p N:M``)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_infra_settings.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_infra_settings", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_infra_settings", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


class TestLiteralDashP:
    """Quoting a port mapping (shellcheck SC2086) must not hide a literal one."""

    @pytest.mark.parametrize(
        "line",
        [
            "docker run -d -p 9000:9000 img",
            'docker run -d -p "9000:9000" img',
            "docker run -d -p '9000:9000' img",
        ],
    )
    def test_literal_mapping_is_flagged(self, line: str) -> None:
        assert _mod._LITERAL_DASH_P.search(line) is not None

    @pytest.mark.parametrize(
        "line",
        [
            "docker run -d -p ${MINIO_HOST_PORT}:9000 img",
            'docker run -d -p "${MINIO_HOST_PORT}:9000" img',
            'docker run -d -p "$PORT:22" img',
        ],
    )
    def test_variable_mapping_is_not_flagged(self, line: str) -> None:
        assert _mod._LITERAL_DASH_P.search(line) is None
