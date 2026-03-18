"""Tests for ext.integrity — checksum verification helpers.

Spec: sdd/specs/034-ext-integrity.md
"""

from __future__ import annotations

import hashlib

import pytest

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store._models import ContentDigest
from remote_store.ext.integrity import checksum, content_digest, verify, verify_hex


@pytest.fixture
def store() -> Store:
    backend = MemoryBackend()
    s = Store(backend)
    s.write("hello.txt", b"hello world", overwrite=True)
    s.write("empty.txt", b"", overwrite=True)
    return s


# ---------------------------------------------------------------------------
# INT-001: checksum
# ---------------------------------------------------------------------------


class TestChecksum:
    @pytest.mark.spec("INT-001")
    def test_sha256_default(self, store: Store) -> None:
        algorithm, hex_digest = checksum(store, "hello.txt")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert algorithm == "sha256"
        assert hex_digest == expected

    @pytest.mark.spec("INT-001")
    def test_md5(self, store: Store) -> None:
        algorithm, hex_digest = checksum(store, "hello.txt", algorithm="md5")
        expected = hashlib.md5(b"hello world").hexdigest()  # noqa: S324
        assert algorithm == "md5"
        assert hex_digest == expected

    @pytest.mark.spec("INT-001")
    def test_empty_file(self, store: Store) -> None:
        _, hex_digest = checksum(store, "empty.txt")
        expected = hashlib.sha256(b"").hexdigest()
        assert hex_digest == expected

    @pytest.mark.spec("INT-001")
    def test_not_found(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            checksum(store, "nonexistent.txt")

    @pytest.mark.spec("INT-001")
    def test_returns_tuple(self, store: Store) -> None:
        result = checksum(store, "hello.txt")
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.spec("INT-001")
    def test_unsupported_algorithm(self, store: Store) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            checksum(store, "hello.txt", algorithm="not_a_hash")


# ---------------------------------------------------------------------------
# INT-002: verify
# ---------------------------------------------------------------------------


class TestVerify:
    @pytest.mark.spec("INT-002")
    def test_matching(self, store: Store) -> None:
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert verify(store, "hello.txt", expected) is True

    @pytest.mark.spec("INT-002")
    def test_not_matching(self, store: Store) -> None:
        assert verify(store, "hello.txt", "0000") is False

    @pytest.mark.spec("INT-002")
    def test_case_insensitive(self, store: Store) -> None:
        expected = hashlib.sha256(b"hello world").hexdigest().upper()
        assert verify(store, "hello.txt", expected) is True

    @pytest.mark.spec("INT-002")
    def test_custom_algorithm(self, store: Store) -> None:
        expected = hashlib.md5(b"hello world").hexdigest()  # noqa: S324
        assert verify(store, "hello.txt", expected, algorithm="md5") is True

    @pytest.mark.spec("INT-002")
    def test_not_found(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            verify(store, "nonexistent.txt", "abc")

    @pytest.mark.spec("INT-002")
    def test_unsupported_algorithm(self, store: Store) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            verify(store, "hello.txt", "abc", algorithm="not_a_hash")


# ---------------------------------------------------------------------------
# INT-003: verify_hex
# ---------------------------------------------------------------------------


class TestVerifyHex:
    @pytest.mark.spec("INT-003")
    def test_matching(self, store: Store) -> None:
        expected_hex = hashlib.sha256(b"hello world").hexdigest()
        assert verify_hex(store, "hello.txt", "sha256", expected_hex) is True

    @pytest.mark.spec("INT-003")
    def test_not_matching(self, store: Store) -> None:
        assert verify_hex(store, "hello.txt", "sha256", "0000") is False

    @pytest.mark.spec("INT-003")
    def test_case_insensitive(self, store: Store) -> None:
        expected_hex = hashlib.sha256(b"hello world").hexdigest().upper()
        assert verify_hex(store, "hello.txt", "sha256", expected_hex) is True

    @pytest.mark.spec("INT-003")
    def test_uses_given_algorithm(self, store: Store) -> None:
        expected_hex = hashlib.md5(b"hello world").hexdigest()  # noqa: S324
        assert verify_hex(store, "hello.txt", "md5", expected_hex) is True

    @pytest.mark.spec("INT-003")
    def test_not_found(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            verify_hex(store, "nonexistent.txt", "sha256", "abc")


# ---------------------------------------------------------------------------
# INT-004: Module exports
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# INT-005: content_digest
# ---------------------------------------------------------------------------


class TestContentDigest:
    @pytest.mark.spec("INT-005")
    def test_returns_content_digest(self, store: Store) -> None:
        result = content_digest(store, "hello.txt")
        assert isinstance(result, ContentDigest)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result.algorithm == "sha256"
        assert result.value == expected

    @pytest.mark.spec("INT-005")
    def test_md5(self, store: Store) -> None:
        result = content_digest(store, "hello.txt", algorithm="md5")
        expected = hashlib.md5(b"hello world").hexdigest()  # noqa: S324
        assert result.algorithm == "md5"
        assert result.value == expected


class TestModuleExports:
    @pytest.mark.spec("INT-004")
    def test_all_exports(self) -> None:
        from remote_store.ext import integrity

        assert set(integrity.__all__) == {"checksum", "content_digest", "verify", "verify_hex"}

    @pytest.mark.spec("INT-004")
    def test_top_level_import(self) -> None:
        import remote_store

        assert hasattr(remote_store, "checksum")
        assert hasattr(remote_store, "content_digest")
        assert hasattr(remote_store, "verify")
        assert hasattr(remote_store, "verify_hex")
