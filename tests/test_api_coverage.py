"""API documentation coverage checks (ID-058).

Verifies that every symbol in ``remote_store.__all__`` has:
  1. A matching `:::` directive in ``docs-src/api/**/*.md``
  2. A row in ``docs-src/api/index.md``

And every symbol in ``remote_store.backends.__all__`` has a `:::` directive.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS_API = ROOT / "docs-src" / "api"


def _collect_directives(directory: Path) -> set[str]:
    """Collect all `:::` directive targets from markdown files."""
    directives: set[str] = set()
    for md_file in directory.rglob("*.md"):
        for line in md_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("::: "):
                target = stripped[4:].strip()
                directives.add(target)
    return directives


def _collect_index_symbols(index_path: Path) -> set[str]:
    """Extract symbol names referenced in the API index table rows."""
    symbols: set[str] = set()
    text = index_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        # Table rows like: | [Store](store.md) | ... |
        # or: | [RegistryConfig](config.md#remote_store.RegistryConfig) | ... |
        if line.startswith("|") and "[" in line:
            # Extract the link text (symbol name)
            import re

            match = re.search(r"\[([A-Za-z_]\w*(?:\.\w+)*)\]", line)
            if match:
                symbols.add(match.group(1))
    return symbols


class TestApiDocsCoverage:
    """Every public symbol must appear in API docs."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.directives = _collect_directives(DOCS_API)

    @pytest.mark.spec("ID-058")
    def test_all_symbols_have_directive(self) -> None:
        """Every symbol in __all__ must have a ::: directive in docs-src/api/."""
        import remote_store

        all_symbols = set(remote_store.__all__)
        # __version__ is a string constant, not a documentable class/function
        all_symbols.discard("__version__")
        # deprecated alias
        all_symbols.discard("cached_store")

        missing = []
        for symbol in sorted(all_symbols):
            # Check for direct match: remote_store.Symbol
            fq = f"remote_store.{symbol}"
            # Also check if the symbol is covered by a module-level directive
            # (e.g., remote_store.ext.batch covers batch_delete, batch_copy, etc.)
            if fq not in self.directives and not self._covered_by_module(symbol):
                missing.append(symbol)

        assert not missing, f"Symbols in __all__ missing ::: directive in docs-src/api/: {missing}"

    def _covered_by_module(self, symbol: str) -> bool:
        """Check if a symbol is covered by a module-level ::: directive."""
        import remote_store

        obj = getattr(remote_store, symbol)
        module = getattr(obj, "__module__", "")
        # Check if the module itself has a ::: directive
        if module and f"::: {module}" in {f"::: {d}" for d in self.directives}:
            return True
        # Map symbol to its extension module
        _ext_modules = {
            "remote_store.ext.batch": "remote_store.ext.batch",
            "remote_store.ext.cache": "remote_store.ext.cache",
            "remote_store.ext.glob": "remote_store.ext.glob",
            "remote_store.ext.integrity": "remote_store.ext.integrity",
            "remote_store.ext.observe": "remote_store.ext.observe",
            "remote_store.ext.partition": "remote_store.ext.partition",
            "remote_store.ext.streams": "remote_store.ext.streams",
            "remote_store.ext.transfer": "remote_store.ext.transfer",
        }
        if module in _ext_modules:
            return _ext_modules[module] in self.directives
        return False

    @pytest.mark.spec("ID-058")
    def test_core_symbols_in_index(self) -> None:
        """Every core (non-extension) class/function should appear in api/index.md.

        Extension symbols (from remote_store.ext.*) are listed by module in the
        index, not individually, so we only check core symbols here.
        """
        import remote_store

        index_symbols = _collect_index_symbols(DOCS_API / "index.md")

        all_symbols = set(remote_store.__all__)
        all_symbols.discard("__version__")
        all_symbols.discard("cached_store")

        # Filter to core symbols only (not from ext.*)
        core_symbols = set()
        for symbol in all_symbols:
            obj = getattr(remote_store, symbol)
            module = getattr(obj, "__module__", "")
            if not module.startswith("remote_store.ext."):
                core_symbols.add(symbol)

        missing = []
        for symbol in sorted(core_symbols):
            if symbol not in index_symbols:
                missing.append(symbol)

        assert not missing, f"Core symbols in __all__ missing from docs-src/api/index.md: {missing}"

    @pytest.mark.spec("ID-058")
    def test_backends_all_have_directive(self) -> None:
        """Every symbol in backends.__all__ must have a ::: directive."""
        from remote_store import backends

        missing = []
        for symbol in backends.__all__:
            fq = f"remote_store.backends.{symbol}"
            if fq not in self.directives:
                missing.append(symbol)

        assert not missing, f"Symbols in backends.__all__ missing ::: directive: {missing}"
