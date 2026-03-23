"""Tests for ext.integrity — checksum verification helpers.

Spec: sdd/specs/034-ext-integrity.md
"""

from __future__ import annotations

import hashlib

import pytest

from remote_store._errors import NotFound
from remote_store._models import ContentDigest
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.integrity import checksum, content_digest, verify, verify_hex

HELLO = b"hello world"
HELLO_SHA256 = hashlib.sha256(HELLO).hexdigest()
HELLO_MD5 = hashlib.md5(HELLO).hexdigest()  # noqa: S324
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@pytest.fixture
def store() -> Store:
    backend = MemoryBackend()
    s = Store(backend)
    s.write("hello.txt", HELLO, overwrite=True)
    s.write("empty.txt", b"", overwrite=True)
    return s


# ---------------------------------------------------------------------------
# INT-001: checksum
# ---------------------------------------------------------------------------


class TestChecksum:
    @pytest.mark.spec("INT-001")
    @pytest.mark.parametrize(
        "algorithm,file,expected_algo,expected_hex",
        [
            pytest.param("sha256", "hello.txt", "sha256", HELLO_SHA256, id="sha256_default"),
            pytest.param("md5", "hello.txt", "md5", HELLO_MD5, id="md5"),
            pytest.param("sha256", "empty.txt", "sha256", EMPTY_SHA256, id="empty_file"),
        ],
    )
    def test_checksum_algorithms(
        self, store: Store, algorithm: str, file: str, expected_algo: str, expected_hex: str
    ) -> None:
        algo, hex_digest = checksum(store, file, algorithm=algorithm)
        assert algo == expected_algo
        assert hex_digest == expected_hex

    @pytest.mark.spec("INT-001")
    def test_sha256_is_default(self, store: Store) -> None:
        algo, hex_digest = checksum(store, "hello.txt")
        assert algo == "sha256"
        assert hex_digest == HELLO_SHA256

    @pytest.mark.spec("INT-001")
    def test_returns_tuple(self, store: Store) -> None:
        result = checksum(store, "hello.txt")
        assert isinstance(result, tuple) and len(result) == 2

    @pytest.mark.spec("INT-001")
    def test_not_found(self, store: Store) -> None:
        with pytest.raises(NotFound):
            checksum(store, "nonexistent.txt")

    @pytest.mark.spec("INT-001")
    def test_unsupported_algorithm(self, store: Store) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            checksum(store, "hello.txt", algorithm="not_a_hash")


# ---------------------------------------------------------------------------
# INT-002 / INT-003: verify and verify_hex
# ---------------------------------------------------------------------------


class TestVerifyAndVerifyHex:
    @pytest.mark.spec("INT-002")
    @pytest.mark.parametrize(
        "expected,algorithm,result",
        [
            pytest.param(HELLO_SHA256, "sha256", True, id="matching"),
            pytest.param("0000", "sha256", False, id="not_matching"),
            pytest.param(HELLO_SHA256.upper(), "sha256", True, id="case_insensitive"),
            pytest.param(HELLO_MD5, "md5", True, id="custom_algorithm"),
        ],
    )
    def test_verify(self, store: Store, expected: str, algorithm: str, result: bool) -> None:
        assert verify(store, "hello.txt", expected, algorithm=algorithm) is result

    @pytest.mark.spec("INT-002")
    def test_verify_not_found(self, store: Store) -> None:
        with pytest.raises(NotFound):
            verify(store, "nonexistent.txt", "abc")

    @pytest.mark.spec("INT-002")
    def test_verify_unsupported_algorithm(self, store: Store) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            verify(store, "hello.txt", "abc", algorithm="not_a_hash")

    @pytest.mark.spec("INT-003")
    @pytest.mark.parametrize(
        "algorithm,expected_hex,result",
        [
            pytest.param("sha256", HELLO_SHA256, True, id="matching"),
            pytest.param("sha256", "0000", False, id="not_matching"),
            pytest.param("sha256", HELLO_SHA256.upper(), True, id="case_insensitive"),
            pytest.param("md5", HELLO_MD5, True, id="md5"),
        ],
    )
    def test_verify_hex(self, store: Store, algorithm: str, expected_hex: str, result: bool) -> None:
        assert verify_hex(store, "hello.txt", algorithm, expected_hex) is result

    @pytest.mark.spec("INT-003")
    def test_verify_hex_not_found(self, store: Store) -> None:
        with pytest.raises(NotFound):
            verify_hex(store, "nonexistent.txt", "sha256", "abc")


# ---------------------------------------------------------------------------
# INT-005: content_digest
# ---------------------------------------------------------------------------


class TestContentDigest:
    @pytest.mark.spec("INT-005")
    @pytest.mark.parametrize(
        "algorithm,expected_algo,expected_hex",
        [
            pytest.param("sha256", "sha256", HELLO_SHA256, id="sha256"),
            pytest.param("md5", "md5", HELLO_MD5, id="md5"),
        ],
    )
    def test_returns_content_digest(self, store: Store, algorithm: str, expected_algo: str, expected_hex: str) -> None:
        result = content_digest(store, "hello.txt", algorithm=algorithm)
        assert isinstance(result, ContentDigest)
        assert result.algorithm == expected_algo
        assert result.value == expected_hex

    @pytest.mark.spec("INT-005")
    def test_not_found(self, store: Store) -> None:
        with pytest.raises(NotFound):
            content_digest(store, "nonexistent.txt")

    @pytest.mark.spec("INT-005")
    def test_unsupported_algorithm(self, store: Store) -> None:
        with pytest.raises(ValueError, match="unsupported hash type"):
            content_digest(store, "hello.txt", algorithm="not_a_real_algo")


# ---------------------------------------------------------------------------
# INT-004: Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    @pytest.mark.spec("INT-004")
    def test_all_exports(self) -> None:
        from remote_store.ext import integrity

        assert set(integrity.__all__) == {"checksum", "content_digest", "verify", "verify_hex"}

    @pytest.mark.spec("INT-004")
    def test_top_level_import(self) -> None:
        import remote_store

        for name in ("checksum", "content_digest", "verify", "verify_hex"):
            assert hasattr(remote_store, name)
