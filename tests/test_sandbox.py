"""
Tests para el SandboxHook (FASE 5.1).

NOTA: Estos tests NO activan el sandbox real (no se puede desactivar).
Simplemente instancian el hook y llaman al __call__ directamente.
"""
import pytest
import os
import tempfile
import threading

from core.extensions.sandbox import SandboxHook
from core.extensions.capability_checker import (
    CapabilityChecker, set_capability_checker,
)
from core.extensions.types import Capability


@pytest.fixture
def hook():
    return SandboxHook()


@pytest.fixture
def checker():
    c = CapabilityChecker()
    set_capability_checker(c)
    yield c
    c.clear()


@pytest.fixture
def set_current_plugin():
    """Helper para setear el plugin actual (simula contextvars)."""
    from core.plugin_api.interfaces import _current_plugin
    tokens = []

    def _set(name: str):
        tokens.append(_current_plugin.set(name))

    yield _set

    # Cleanup
    for token in reversed(tokens):
        try:
            _current_plugin.reset(token)
        except Exception:
            pass


class TestNoPlugin:
    def test_no_plugin_allows_all(self, hook):
        """Sin plugin actual → permitir (llamada desde Core)."""
        # No debe lanzar
        hook("open", ("/etc/passwd", "w", 0))
        hook("os.system", ("rm -rf /",))
        hook("socket.connect", ("1.1.1.1", 80))


class TestFileAccess:
    def test_write_denied_without_capability(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        with pytest.raises(PermissionError):
            hook("open", ("/tmp/test.txt", "w", 0))

    def test_write_allowed_with_capability(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", ["write_files"])
        set_current_plugin("test")

        # No debe lanzar
        hook("open", ("/tmp/test.txt", "w", 0))

    def test_read_denied_without_capability(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        with pytest.raises(PermissionError):
            hook("open", ("/tmp/test.txt", "r", 0))

    def test_read_allowed_with_capability(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", ["read_files"])
        set_current_plugin("test")

        hook("open", ("/tmp/test.txt", "r", 0))


class TestNetwork:
    def test_connect_denied_without_capability(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        with pytest.raises(PermissionError):
            hook("socket.connect", ("1.1.1.1", 80))

    def test_connect_allowed_with_capability(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", ["network"])
        set_current_plugin("test")

        hook("socket.connect", ("1.1.1.1", 80))


class TestProcess:
    def test_os_system_denied(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        with pytest.raises(PermissionError):
            hook("os.system", ("ls",))

    def test_os_system_allowed(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", ["process_execution"])
        set_current_plugin("test")

        hook("os.system", ("ls",))


class TestForbiddenModules:
    def test_ctypes_forbidden(self, hook, checker, set_current_plugin):
        import sys
        checker.register_plugin("test", [])
        set_current_plugin("test")

        # Eliminar de sys.modules para forzar el evento
        saved = sys.modules.pop("ctypes", None)
        try:
            with pytest.raises(PermissionError):
                hook("import", ("ctypes",))
        finally:
            if saved is not None:
                sys.modules["ctypes"] = saved

    def test_mmap_forbidden(self, hook, checker, set_current_plugin):
        import sys
        checker.register_plugin("test", [])
        set_current_plugin("test")

        saved = sys.modules.pop("mmap", None)
        try:
            with pytest.raises(PermissionError):
                hook("import", ("mmap",))
        finally:
            if saved is not None:
                sys.modules["mmap"] = saved


class TestProtectedModules:
    def test_requests_requires_network(self, hook, checker, set_current_plugin):
        import sys
        checker.register_plugin("test", [])
        set_current_plugin("test")

        # ✅ Eliminar de sys.modules para forzar el evento
        saved = sys.modules.pop("requests", None)
        try:
            with pytest.raises(PermissionError):
                hook("import", ("requests",))
        finally:
            if saved is not None:
                sys.modules["requests"] = saved

    def test_requests_ok_with_network(self, hook, checker, set_current_plugin):
        import sys
        checker.register_plugin("test", ["network"])
        set_current_plugin("test")

        saved = sys.modules.pop("requests", None)
        try:
            # No debe lanzar
            hook("import", ("requests",))
        finally:
            if saved is not None:
                sys.modules["requests"] = saved


class TestExecCompile:
    def test_exec_blocked(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        with pytest.raises(PermissionError):
            hook("exec", ("print('hi')",))

    def test_compile_blocked(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        with pytest.raises(PermissionError):
            hook("compile", ("1+1", "<x>", "eval"))


class TestStats:
    def test_blocks_counted(self, hook, checker, set_current_plugin):
        checker.register_plugin("test", [])
        set_current_plugin("test")

        try:
            hook("open", ("/tmp/a", "w", 0))
        except PermissionError:
            pass
        try:
            hook("open", ("/tmp/b", "w", 0))
        except PermissionError:
            pass

        stats = hook.get_stats()
        assert any("open" in k for k in stats)