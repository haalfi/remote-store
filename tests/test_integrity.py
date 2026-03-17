"""Tests for ext.integrity — checksum verification helpers.

Spec: sdd/specs/034-ext-integrity.md
"""

from __future__ import annotations

import hashlib

import pytest

from remote_store._models import ContentDigest
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.integrity import checksum, verify, verify_digest


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
        result = checksum(store, "hello.txt")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result.algorithm == "sha256"
        assert result.value == expected

    @pytest.mark.spec("INT-001")
    def test_md5(self, store: Store) -> None:
        result = checksum(store, "hello.txt", algorithm="md5")
        expected = hashlib.md5(b"hello world").hexdigest()  # noqa: S324
        assert result.algorithm == "md5"
        assert result.value == expected

    @pytest.mark.spec("INT-001")
    def test_empty_file(self, store: Store) -> None:
        result = checksum(store, "empty.txt")
        expected = hashlib.sha256(b"").hexdigest()
        assert result.value == expected

    @pytest.mark.spec("INT-001")
    def test_not_found(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            checksum(store, "nonexistent.txt")

    @pytest.mark.spec("INT-001")
    def test_returns_content_digest(self, store: Store) -> None:
        result = checksum(store, "hello.txt")
        assert isinstance(result, ContentDigest)


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


# ---------------------------------------------------------------------------
# INT-003: verify_digest
# ---------------------------------------------------------------------------


class TestVerifyDigest:
    @pytest.mark.spec("INT-003")
    def test_matching(self, store: Store) -> None:
        expected_hex = hashlib.sha256(b"hello world").hexdigest()
        digest = ContentDigest("sha256", expected_hex)
        assert verify_digest(store, "hello.txt", digest) is True

    @pytest.mark.spec("INT-003")
    def test_not_matching(self, store: Store) -> None:
        digest = ContentDigest("sha256", "0000")
        assert verify_digest(store, "hello.txt", digest) is False

    @pytest.mark.spec("INT-003")
    def test_uses_digest_algorithm(self, store: Store) -> None:
        expected_hex = hashlib.md5(b"hello world").hexdigest()  # noqa: S324
        digest = ContentDigest("md5", expected_hex)
        assert verify_digest(store, "hello.txt", digest) is True


# ---------------------------------------------------------------------------
# INT-004: Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    @pytest.mark.spec("INT-004")
    def test_all_exports(self) -> None:
        from remote_store.ext import integrity

        assert set(integrity.__all__) == {"checksum", "verify", "verify_digest"}

    @pytest.mark.spec("INT-004")
    def test_top_level_import(self) -> None:
        import remote_store

        assert hasattr(remote_store, "checksum")
        assert hasattr(remote_store, "verify")
        assert hasattr(remote_store, "verify_digest")
