"""
Tests para el CapabilityChecker (FASE 4).
"""
import pytest

from core.extensions.capability_checker import (
    CapabilityChecker, get_capability_checker, set_capability_checker,
)
from core.extensions.types import Capability


@pytest.fixture
def checker():
    c = CapabilityChecker()
    set_capability_checker(c)
    yield c
    c.clear()


class TestRegistration:
    def test_register_and_check(self, checker):
        checker.register_plugin("test_plugin", ["network", "write_files"])
        assert checker.check("test_plugin", Capability.NETWORK) is True
        assert checker.check("test_plugin", Capability.WRITE_FILES) is True

    def test_deny_not_declared(self, checker):
        checker.register_plugin("test_plugin", ["network"])
        assert checker.check("test_plugin", Capability.NETWORK) is True
        assert checker.check("test_plugin", Capability.WRITE_FILES) is False

    def test_deny_unregistered_plugin(self, checker):
        assert checker.check("unknown_plugin", Capability.NETWORK) is False

    def test_unknown_capability_in_manifest(self, checker):
        checker.register_plugin("test_plugin", ["network", "unknown_cap"])
        assert checker.check("test_plugin", Capability.NETWORK) is True
        # "unknown_cap" es ignorada


class TestBuiltinBypass:
    def test_builtin_bypass(self, checker):
        # builtin y core siempre pueden todo
        assert checker.check("builtin", Capability.NETWORK) is True
        assert checker.check("core", Capability.NETWORK) is True
        assert checker.check("", Capability.NETWORK) is True


class TestStrictMode:
    def test_non_strict_allows_all(self, checker):
        checker.set_strict_mode(False)
        assert checker.check("unknown_plugin", Capability.NETWORK) is True

    def test_strict_denies(self, checker):
        checker.set_strict_mode(True)
        assert checker.check("unknown_plugin", Capability.NETWORK) is False


class TestRequireRaises:
    def test_require_raises(self, checker):
        checker.register_plugin("test_plugin", ["network"])
        with pytest.raises(PermissionError):
            checker.require("test_plugin", Capability.WRITE_FILES)

    def test_require_ok(self, checker):
        checker.register_plugin("test_plugin", ["network"])
        checker.require("test_plugin", Capability.NETWORK)  # no debe lanzar


class TestDenials:
    def test_denials_logged(self, checker):
        checker.register_plugin("test_plugin", [])
        checker.check("test_plugin", Capability.NETWORK)
        denials = checker.get_denials()
        assert len(denials) == 1
        assert denials[0]["plugin"] == "test_plugin"
        assert denials[0]["capability"] == "network"


class TestSingleton:
    def test_singleton(self):
        c1 = get_capability_checker()
        c2 = get_capability_checker()
        assert c1 is c2