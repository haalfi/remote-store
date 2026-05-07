"""Cross-backend conformance suite (spec 048 / TEST-002 / TEST-010).

Files in this subpackage parametrise over the fixture registry
:mod:`tests.backends.fixtures` and reference only the cross-backend
``Store``/``Backend`` API surface. Backend-specific behaviour belongs
under ``tests/backends/<backend>/`` per TEST-003.
"""
