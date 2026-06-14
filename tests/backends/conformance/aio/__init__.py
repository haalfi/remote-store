"""Async cross-backend conformance — concurrency lane (BK-289).

Sibling of ``tests/backends/conformance/test_concurrency.py`` for the async
axis. Shares the parent ``conformance/conftest.py`` (the ``async_backend``
indirect fixture and the registry-driven parametrize hook apply to this
subtree), and references only the abstract ``AsyncBackend`` surface per
TEST-010.
"""
