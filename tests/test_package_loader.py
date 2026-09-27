"""
Tests para PluginPackageLoader (FASE 5.2).
"""
import os
import json
import zipfile
import tempfile
import shutil
import pytest

from plugins.package_loader import (
    PluginPackageLoader, PackageInfo, PackageInvalidError,
)
from plugins.package_validator import (
    PackageValidator, ValidationResult,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def temp_plugins_dir():
    """Directorio temporal para plugins."""
    d = tempfile.mkdtemp(prefix="test_plugins_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_installed_dir():
    """Directorio temporal para instalados."""
    d = tempfile.mkdtemp(prefix="test_installed_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_zip(zip_path: str, files: dict):
    """Helper: crea un ZIP con archivos."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if isinstance(content, dict):
                content = json.dumps(content)
            zf.writestr(name, content)


# ============================================================
# TEST: SCAN
# ============================================================

class TestScan:
    def test_scan_empty(self, temp_plugins_dir, temp_installed_dir):
        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        assert loader.scan() == []

    def test_scan_one_zip(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "my_plugin.zip")
        _make_zip(zip_path, {
            "plugin.py": "print('hi')",
            "manifest.json": {"version": "1.0.0", "description": "Test"},
        })

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages = loader.scan()

        assert len(packages) == 1
        assert packages[0].name == "my_plugin"
        assert packages[0].version == "1.0.0"

    def test_scan_ignores_non_zip(self, temp_plugins_dir, temp_installed_dir):
        # Archivo no ZIP
        with open(os.path.join(temp_plugins_dir, "readme.txt"), "w") as f:
            f.write("hello")

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        assert loader.scan() == []


# ============================================================
# TEST: VALIDACIÓN
# ============================================================

class TestValidation:
    def test_zip_without_plugin_py(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "bad_plugin.zip")
        _make_zip(zip_path, {"manifest.json": {"version": "1.0.0"}})

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages = loader.scan()
        assert packages == []

    def test_zip_path_traversal(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "evil.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("plugin.py", "pass")
            zf.writestr("../../etc/passwd", "evil")

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages = loader.scan()
        assert packages == []

    def test_zip_bad_extension(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "bad_ext.zip")
        _make_zip(zip_path, {
            "plugin.py": "pass",
            "malware.exe": "binary",
        })

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages = loader.scan()
        assert packages == []


# ============================================================
# TEST: INSTALACIÓN
# ============================================================

class TestInstall:
    def test_install_one(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "pkg1.zip")
        _make_zip(zip_path, {
            "plugin.py": "# test plugin",
            "manifest.json": {"version": "1.0.0"},
        })

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages = loader.scan()
        assert len(packages) == 1

        count = loader.install_all(packages)
        assert count == 1
        assert packages[0].extracted is True
        assert os.path.isdir(packages[0].install_path)
        assert os.path.isfile(
            os.path.join(packages[0].install_path, "plugin.py")
        )

    def test_reinstall_same_zip_skips(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "pkg_skip.zip")
        _make_zip(zip_path, {
            "plugin.py": "# test",
            "manifest.json": {"version": "1.0.0"},
        })

        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages1 = loader.scan()
        loader.install_all(packages1)

        # Segunda vez
        loader2 = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages2 = loader2.scan()
        assert packages2[0].already_installed is True

    def test_hash_change_reinstalls(self, temp_plugins_dir, temp_installed_dir):
        zip_path = os.path.join(temp_plugins_dir, "pkg_hash.zip")

        # v1
        _make_zip(zip_path, {
            "plugin.py": "# v1",
            "manifest.json": {"version": "1.0.0"},
        })
        loader = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages1 = loader.scan()
        loader.install_all(packages1)
        sha1 = packages1[0].sha256

        # v2 (contenido distinto)
        _make_zip(zip_path, {
            "plugin.py": "# v2 different",
            "manifest.json": {"version": "1.0.1"},
        })
        loader2 = PluginPackageLoader(temp_plugins_dir, temp_installed_dir)
        packages2 = loader2.scan()
        sha2 = packages2[0].sha256

        assert sha1 != sha2
        assert packages2[0].already_installed is False


# ============================================================
# TEST: VALIDATOR
# ============================================================

class TestValidator:
    def test_valid_zip(self, temp_plugins_dir):
        zip_path = os.path.join(temp_plugins_dir, "valid.zip")
        _make_zip(zip_path, {
            "plugin.py": "from core.plugin_api import BasePlugin",
            "manifest.json": {"version": "1.0.0"},
        })

        v = PackageValidator()
        result = v.validate_zip(zip_path)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_version(self, temp_plugins_dir):
        zip_path = os.path.join(temp_plugins_dir, "no_version.zip")
        _make_zip(zip_path, {
            "plugin.py": "pass",
            "manifest.json": {"description": "No version"},
        })

        v = PackageValidator()
        result = v.validate_zip(zip_path)
        assert result.valid is False
        assert any("version" in e for e in result.errors)

    def test_forbidden_import(self, temp_plugins_dir):
        zip_path = os.path.join(temp_plugins_dir, "forbidden.zip")
        _make_zip(zip_path, {
            "plugin.py": "import ctypes\npass",
            "manifest.json": {"version": "1.0.0"},
        })

        v = PackageValidator()
        result = v.validate_zip(zip_path)
        assert result.valid is False
        assert any("ctypes" in e for e in result.errors)

    def test_capability_missing(self, temp_plugins_dir):
        zip_path = os.path.join(temp_plugins_dir, "no_cap.zip")
        _make_zip(zip_path, {
            "plugin.py": "import requests\npass",
            "manifest.json": {
                "version": "1.0.0",
                "capabilities": [],
            },
        })

        v = PackageValidator()
        result = v.validate_zip(zip_path)
        assert result.valid is False
        assert any("network" in e for e in result.errors)

    def test_capability_present(self, temp_plugins_dir):
        zip_path = os.path.join(temp_plugins_dir, "with_cap.zip")
        _make_zip(zip_path, {
            "plugin.py": "import requests\npass",
            "manifest.json": {
                "version": "1.0.0",
                "capabilities": ["network"],
            },
        })

        v = PackageValidator()
        result = v.validate_zip(zip_path)
        assert result.valid is True