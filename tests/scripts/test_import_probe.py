"""Tests for scripts/import_probe.py (BK-372).

The probe is what gives the isolated install its teeth: it runs before the test
plugins join the environment, so a package an extra forgot to declare has
nothing to arrive from. Its **selection** rules are the part worth testing —
which module of a distribution to import — because they were wrong twice on this
branch and both times the leg stayed green:

* reading ``top_level.txt`` on Python 3.10, where a hatchling-built wheel ships
  none, so three working installs reported as failures;
* selecting a PEP-420 namespace root, whose import executes no code from any
  distribution, so a floor that could not load at all reported ``import ok``.

Both are selection bugs with no behavioural signature in the run that hits them,
which is exactly what a unit test is for and a smoke test is not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def import_probe():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import import_probe

    return import_probe


class _Dist:
    """The slice of `importlib.metadata.Distribution` the probe reads."""

    def __init__(self, files):
        self.files = [Path(f) for f in files]


class TestDottedModules:
    def test_a_package_becomes_its_dotted_name(self, import_probe):
        dist = _Dist(["azure/storage/filedatalake/__init__.py", "azure/storage/filedatalake/_client.py"])
        names = import_probe.dotted_modules(dist)
        assert "azure.storage.filedatalake" in names
        assert "azure.storage.filedatalake._client" in names

    def test_a_top_level_module_survives(self, import_probe):
        assert import_probe.dotted_modules(_Dist(["six.py"])) == {"six"}

    def test_non_python_files_are_ignored(self, import_probe):
        # A wheel carries metadata, data files and stubs. Only `.py` defines a
        # module: `types-paramiko` ships `.pyi` and nothing importable.
        dist = _Dist(["pkg/__init__.py", "pkg/py.typed", "pkg/data.json", "pkg/stub.pyi", "pkg-1.0.dist-info/RECORD"])
        assert import_probe.dotted_modules(dist) == {"pkg"}

    def test_a_non_identifier_path_is_dropped(self, import_probe):
        # A distribution may ship files under a directory that is not a legal
        # module name; importing that name is a SyntaxError, not a finding.
        # Note `good` itself appears only because the distribution ships its
        # `__init__.py`; a package directory is named by its own file, never
        # inferred from a submodule underneath it.
        dist = _Dist(["weird-pkg/mod.py", "2bad/other.py", "good/__init__.py", "good/mod.py"])
        assert import_probe.dotted_modules(dist) == {"good", "good.mod"}

    def test_a_distribution_with_no_files_yields_nothing(self, import_probe):
        # `dist.files` is None for an install whose RECORD is missing.
        dist = _Dist([])
        dist.files = None
        assert import_probe.dotted_modules(dist) == set()


class TestFirstRealModule:
    def test_a_namespace_root_is_stepped_over(self, import_probe, monkeypatch):
        # The defect this rule exists for: `import azure` succeeds while
        # executing no code from any distribution, so probing it would report
        # `import ok` for a floor whose azure-storage-file-datalake is broken.
        class _Spec:
            def __init__(self, origin):
                self.origin = origin

        specs = {
            "azure": _Spec(None),  # PEP-420 namespace portion
            "azure.identity": _Spec("/site-packages/azure/identity/__init__.py"),
        }
        monkeypatch.setattr(import_probe.importlib.util, "find_spec", lambda name: specs.get(name))
        assert import_probe.first_real_module({"azure", "azure.identity"}) == "azure.identity"

    def test_a_public_module_beats_a_private_one(self, import_probe, monkeypatch):
        # PyYAML declares `_yaml`, the optional libyaml accelerator, which an
        # sdist build without libyaml simply does not produce — and which says
        # less about the surface a user reaches than `yaml` does.
        monkeypatch.setattr(
            import_probe.importlib.util,
            "find_spec",
            lambda name: type("S", (), {"origin": f"/site-packages/{name}.py"})(),
        )
        assert import_probe.first_real_module({"_yaml", "yaml"}) == "yaml"

    def test_the_shallowest_public_module_wins(self, import_probe, monkeypatch):
        monkeypatch.setattr(
            import_probe.importlib.util,
            "find_spec",
            lambda name: type("S", (), {"origin": f"/site-packages/{name}.py"})(),
        )
        assert import_probe.first_real_module({"pkg.sub.deep", "pkg", "pkg.sub"}) == "pkg"

    def test_nothing_importable_returns_none(self, import_probe, monkeypatch):
        monkeypatch.setattr(import_probe.importlib.util, "find_spec", lambda name: None)
        assert import_probe.first_real_module({"pkg"}) is None

    def test_a_raising_find_spec_is_skipped_not_fatal(self, import_probe, monkeypatch):
        # `find_spec` raises rather than returning None for some shapes; the
        # probe's subject is the import, so a name it cannot even resolve is
        # passed over in favour of one it can.
        def _find(name):
            if name == "broken":
                raise ValueError("no parent package")
            return type("S", (), {"origin": f"/site-packages/{name}.py"})()

        monkeypatch.setattr(import_probe.importlib.util, "find_spec", _find)
        assert import_probe.first_real_module({"broken", "ok"}) == "ok"


class TestProbe:
    def test_every_tracked_extra_resolves_to_a_real_module(self, import_probe):
        # The end-to-end selection, against this environment's own installs.
        # `[dev]` brings every tracked extra in, so each one's declared
        # distributions are present here.
        from drift_check import list_extras

        extras = list_extras()
        assert extras, "list_extras() returned nothing; this test would pass vacuously"
        for extra in extras:
            # 0 means every declared distribution that ships a module imported,
            # and that at least one did. An ImportError propagates rather than
            # being counted, which is the finding the phase exists to report.
            assert import_probe.probe(extra) == 0, extra

    def test_a_run_that_probes_nothing_fails(self, import_probe, monkeypatch, capsys):
        # A probe that silently checks nothing looks identical to a clean one,
        # which is the shape the here-document bug produced: rc 0 from a script
        # that never ran.
        monkeypatch.setattr(import_probe, "_direct_requirements_for", lambda extra: {})
        assert import_probe.probe("anything") == 1
        assert "no importable module found" in capsys.readouterr().err

    def test_a_distribution_with_no_module_is_skipped_not_failed(self, import_probe, monkeypatch, capsys):
        # A stub-only or data-only distribution ships nothing to import. That is
        # not a finding — failing on it would report a working install as broken,
        # which this probe has done twice for other reasons.
        monkeypatch.setattr(import_probe, "_direct_requirements_for", lambda extra: {"stubs": "", "real": ""})
        monkeypatch.setattr(import_probe, "distribution", lambda name: _Dist([f"{name}/__init__.py"]))
        monkeypatch.setattr(import_probe, "first_real_module", lambda names: None if "stubs" in names else "real")
        monkeypatch.setattr(import_probe, "dotted_modules", lambda dist: {dist.files[0].parts[0]})
        monkeypatch.setattr(import_probe.importlib, "import_module", lambda name: None)
        assert import_probe.probe("x") == 0
        out = capsys.readouterr().out
        assert "skip (no importable module ships with stubs)" in out
        assert "import ok: real -> real" in out

    def test_a_marker_excluded_distribution_is_skipped(self, import_probe, monkeypatch, capsys):
        # `tomli; python_version < "3.11"` is declared and correctly absent on a
        # newer interpreter. The resolver was right; the probe must agree.
        def _missing(name):
            raise import_probe.PackageNotFoundError(name)

        monkeypatch.setattr(import_probe, "_direct_requirements_for", lambda extra: {"absent": ""})
        monkeypatch.setattr(import_probe, "distribution", _missing)
        assert import_probe.probe("x") == 1  # nothing probed at all
        assert "skip (not installed on this interpreter)" in capsys.readouterr().out

    def test_an_import_that_raises_propagates(self, import_probe, monkeypatch):
        # The finding the whole phase exists to produce: installed, and broken.
        monkeypatch.setattr(import_probe, "_direct_requirements_for", lambda extra: {"pkg": ""})
        monkeypatch.setattr(import_probe, "distribution", lambda name: _Dist(["pkg/__init__.py"]))
        monkeypatch.setattr(import_probe, "first_real_module", lambda names: "pkg")

        def _boom(name):
            raise ImportError("numpy.core.multiarray failed to import")

        monkeypatch.setattr(import_probe.importlib, "import_module", _boom)
        with pytest.raises(ImportError, match="multiarray"):
            import_probe.probe("x")


class TestMain:
    def test_a_missing_argument_is_a_usage_error(self, import_probe):
        assert import_probe.main([]) == 2

    def test_one_argument_reaches_the_probe(self, import_probe, monkeypatch):
        seen = []
        monkeypatch.setattr(import_probe, "probe", lambda extra: seen.append(extra) or 0)
        assert import_probe.main(["yaml"]) == 0
        assert seen == ["yaml"]
