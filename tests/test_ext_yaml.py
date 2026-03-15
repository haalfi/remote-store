"""Tests for ext.yaml — derived from sdd/specs/021-config-loaders.md (CFG-010, CFG-011, CFG-013)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from remote_store._config import RegistryConfig, Secret
from remote_store.ext.yaml import _get_yaml_loader, from_yaml


class TestFromYaml:
    """CFG-010, CFG-011: from_yaml() loads config from YAML files."""

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_basic(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "backends:\n  local:\n    type: local\n    options:\n      root: /data\n"
            "stores:\n  main:\n    backend: local\n    root_path: data\n"
        )
        rc = from_yaml(yaml_file)
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options["root"] == "/data"
        assert rc.stores["main"].backend == "local"

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            from_yaml("/nonexistent/config.yaml")

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(TypeError, match="mapping"):
            from_yaml(yaml_file)

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_invalid_yaml(self, tmp_path: Path) -> None:
        from yaml import YAMLError

        bad = tmp_path / "bad.yaml"
        bad.write_text(":\n  - [unterminated\n")
        with pytest.raises(YAMLError):
            from_yaml(bad)

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_secret_wrapping(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "creds.yaml"
        yaml_file.write_text(
            "backends:\n  s3:\n    type: s3\n    options:\n      bucket: b\n      key: AKID\n      secret: SK\n"
            "stores: {}\n"
        )
        rc = from_yaml(yaml_file)
        opts = rc.backends["s3"].options
        assert isinstance(opts["key"], Secret) and isinstance(opts["secret"], Secret)

    @pytest.mark.spec("CFG-012")
    def test_from_yaml_unknown_key_warning_stacklevel(self, tmp_path: Path) -> None:
        """Unknown keys in YAML should warn pointing at the caller, not internals."""
        import warnings

        yaml_file = tmp_path / "extra.yaml"
        yaml_file.write_text("backends: {}\nstores: {}\nbogus_key: 42\n")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from_yaml(yaml_file)  # this is the line the warning should point at

        unknown_warns = [w for w in caught if "Unknown" in str(w.message)]
        assert len(unknown_warns) == 1
        # The warning should point at THIS file (the caller), not at _config.py
        assert os.path.normcase(unknown_warns[0].filename) == os.path.normcase(__file__)

    @pytest.mark.spec("CFG-013")
    def test_from_yaml_equivalence_with_from_dict(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "eq.yaml"
        yaml_file.write_text(
            "backends:\n  local:\n    type: local\n    options:\n      root: /tmp\n"
            "stores:\n  data:\n    backend: local\n    root_path: d\n"
        )
        from_yaml_cfg = from_yaml(yaml_file)
        from_dict = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
                "stores": {"data": {"backend": "local", "root_path": "d"}},
            }
        )
        assert from_yaml_cfg.backends["local"].type == from_dict.backends["local"].type
        assert from_yaml_cfg.stores["data"].root_path == from_dict.stores["data"].root_path


class TestFromYamlFallbacks:
    """Tests for optional-dependency fallback paths in from_yaml() / _get_yaml_loader()."""

    @pytest.mark.spec("CFG-011")
    def test_ruamel_fallback_when_pyyaml_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("backends:\n  m:\n    type: memory\nstores: {}\n")
        monkeypatch.setitem(sys.modules, "yaml", None)

        try:
            from ruamel.yaml import YAML  # noqa: F401
        except ImportError:
            pytest.skip("ruamel.yaml not installed")

        loader = _get_yaml_loader()
        with open(yaml_file, encoding="utf-8") as f:
            data = loader(f)
        assert isinstance(data, dict) and data["backends"]["m"]["type"] == "memory"

    @pytest.mark.spec("CFG-011")
    def test_no_yaml_lib_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "yaml", None)
        monkeypatch.setitem(sys.modules, "ruamel", None)
        monkeypatch.setitem(sys.modules, "ruamel.yaml", None)

        with pytest.raises(ModuleNotFoundError, match="pyyaml or ruamel"):
            _get_yaml_loader()


class TestYamlExtensionContract:
    """CFG-017-equivalent: ext/yaml.py follows the extension architecture (ADR-0008)."""

    @pytest.mark.spec("CFG-010")
    def test_all_defined(self) -> None:
        from remote_store.ext import yaml as yaml_ext

        assert hasattr(yaml_ext, "__all__")
        assert "from_yaml" in yaml_ext.__all__

    @pytest.mark.spec("CFG-010")
    def test_no_top_level_reexport(self) -> None:
        """Optional-dep extensions are NOT re-exported (ADR-0013)."""
        import remote_store

        assert not hasattr(remote_store, "from_yaml")
