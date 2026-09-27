"""Tests para core/plugin_api/plugin_manager.py"""
import pytest
import os
import shutil
import tempfile
from pathlib import Path

from core.plugin_api.plugin_manager import (
    PluginManager,
    PluginNotFoundError,
    PluginDependencyError,
    get_plugin_manager,
    set_plugin_manager,
)
from core.plugin_api.interfaces import PluginContext


# ==================== INIT ====================

class TestPluginManagerInit:
    def test_init(self):
        pm = PluginManager()
        assert pm.list_discovered() == []
        assert pm.list_loaded() == []
        assert pm.list_enabled() == []
        assert pm.list_failed() == []

    def test_context_created(self):
        pm = PluginManager()
        assert pm.context is not None
        assert pm.context.hooks is not None

    def test_stats_initial(self):
        pm = PluginManager()
        stats = pm.get_stats()
        assert stats["total_discovered"] == 0
        assert stats["currently_loaded"] == 0
        assert stats["currently_enabled"] == 0


# ==================== DESCUBRIMIENTO ====================

class TestPluginDiscovery:
    def test_discover_empty(self, temp_dir):
        pm = PluginManager()
        count = pm.discover(temp_dir)
        assert count == 0

    def test_discover_nonexistent(self):
        pm = PluginManager()
        count = pm.discover("/ruta/que/no/existe")
        assert count == 0

    def test_discover_plugin_folder(self, temp_dir):
        # Crear un plugin de prueba
        plugin_dir = os.path.join(temp_dir, "test_plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        pm = PluginManager()
        count = pm.discover(temp_dir)
        assert count == 1
        assert "test_plugin" in pm.list_discovered()

    def test_discover_ignores_underscore_folders(self, temp_dir):
        plugin_dir = os.path.join(temp_dir, "_hidden_plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        pm = PluginManager()
        count = pm.discover(temp_dir)
        assert count == 0

    def test_discover_multiple_plugins(self, temp_dir):
        for name in ("plugin_a", "plugin_b", "plugin_c"):
            plugin_dir = os.path.join(temp_dir, name)
            os.makedirs(plugin_dir)
            with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
                f.write("")

        pm = PluginManager()
        count = pm.discover(temp_dir)
        assert count == 3
        assert set(pm.list_discovered()) == {"plugin_a", "plugin_b", "plugin_c"}

    def test_discover_metadata_populated(self, temp_dir):
        plugin_dir = os.path.join(temp_dir, "meta_test")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        pm = PluginManager()
        pm.discover(temp_dir)

        metadata = pm.get_metadata("meta_test")
        assert metadata is not None
        assert metadata.name == "meta_test"
        assert metadata.path == os.path.abspath(plugin_dir)
        assert metadata.module_name == "meta_test"


# ==================== CARGA ====================

class TestPluginLoading:
    def test_load_nonexistent_raises(self):
        pm = PluginManager()
        with pytest.raises(PluginNotFoundError):
            pm.load("no_existe")

    def test_load_simple_plugin(self, temp_dir):
        """
        Test de carga de plugin usando path absoluto.

        Con el fix de `_import_plugin_module`, el plugin puede vivir
        en cualquier directorio (no requiere sys.path ni `plugins/`).
        """
        # Crear plugin en temp_dir
        plugin_dir = os.path.join(temp_dir, "simple_plugin")
        os.makedirs(plugin_dir)

        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
            f.write("""
from core.plugin_api import BasePlugin

class SimplePlugin(BasePlugin):
    NAME = "simple_plugin"
    VERSION = "1.0.0"

    def on_load(self):
        return True
""")

        pm = PluginManager()
        pm.discover(temp_dir)

        # ✅ El manager usa path absoluto — no necesita sys.path
        result = pm.load("simple_plugin")
        assert result is True, "El plugin debería cargar correctamente"
        assert pm.is_loaded("simple_plugin")

        # Cleanup
        pm.unload_all()

    def test_load_simple_plugin_realistic(self):
        """
        Test de carga REALISTA usando el directorio real de plugins/.

        Crea un plugin temporal en plugins/, lo carga, y lo elimina.
        """
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"
        plugin_name = "test_simple_plugin_temp"
        plugin_dir = plugins_dir / plugin_name

        try:
            # ✅ Crear plugin temporal
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "__init__.py").write_text("")
            (plugin_dir / "plugin.py").write_text("""
from core.plugin_api import BasePlugin

class TestSimplePlugin(BasePlugin):
    NAME = "test_simple_plugin_temp"
    VERSION = "1.0.0"

    def on_load(self):
        return True
""")

            pm = PluginManager()
            pm.discover(str(plugins_dir))

            assert plugin_name in pm.list_discovered()

            result = pm.load(plugin_name)
            assert result is True
            assert pm.is_loaded(plugin_name)

            # Verificar que se puede activar
            result = pm.enable(plugin_name)
            assert result is True
            assert pm.is_enabled(plugin_name)

            pm.unload_all()
        finally:
            # ✅ Cleanup: eliminar el plugin temporal
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir, ignore_errors=True)

    def test_load_plugin_with_hooks(self, temp_dir):
        """Verifica que un plugin puede registrar hooks."""
        plugin_dir = os.path.join(temp_dir, "hook_plugin")
        os.makedirs(plugin_dir)

        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
            f.write("""
from core.plugin_api import BasePlugin

class HookPlugin(BasePlugin):
    NAME = "hook_plugin"
    VERSION = "1.0.0"

    def __init__(self, context):
        super().__init__(context)
        self.hook_called = False

    def on_load(self):
        self.register_hook("test_hook", self._on_test_hook)
        return True

    def _on_test_hook(self, **kwargs):
        self.hook_called = True
""")

        pm = PluginManager()
        pm.discover(temp_dir)
        assert pm.load("hook_plugin")

        # Emitir el hook
        pm.context.hooks.emit("test_hook")

        # Verificar que se llamó
        plugin = pm.get("hook_plugin")
        assert plugin.hook_called is True

        pm.unload_all()

    def test_load_plugin_that_raises(self, temp_dir):
        """Un plugin que lanza excepción no debe romper el manager."""
        plugin_dir = os.path.join(temp_dir, "exception_plugin")
        os.makedirs(plugin_dir)

        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
            f.write("""
from core.plugin_api import BasePlugin

class ExceptionPlugin(BasePlugin):
    NAME = "exception_plugin"
    VERSION = "1.0.0"

    def on_load(self):
        raise ValueError("Test exception")
""")

        pm = PluginManager()
        pm.discover(temp_dir)
        result = pm.load("exception_plugin")

        assert result is False
        assert "exception_plugin" in pm.list_failed()


# ==================== DESCARGA ====================

class TestPluginUnloading:
    def test_unload_simple(self, temp_dir):
        """Verifica unload de un plugin."""
        plugin_dir = os.path.join(temp_dir, "unload_test")
        os.makedirs(plugin_dir)

        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
            f.write("""
from core.plugin_api import BasePlugin

class UnloadTest(BasePlugin):
    NAME = "unload_test"
    def on_load(self):
        return True
    def on_unload(self):
        self.cleanup_called = True
""")

        pm = PluginManager()
        pm.discover(temp_dir)
        pm.load("unload_test")

        plugin = pm.get("unload_test")
        assert plugin is not None

        pm.unload("unload_test")
        assert not pm.is_loaded("unload_test")
        assert pm.get("unload_test") is None

    def test_unload_nonexistent(self):
        pm = PluginManager()
        result = pm.unload("no_existe")
        assert result is False


# ==================== ACTIVACIÓN ====================

class TestPluginActivation:
    def test_enable_simple(self, temp_dir):
        plugin_dir = os.path.join(temp_dir, "enable_test")
        os.makedirs(plugin_dir)

        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
            f.write("""
from core.plugin_api import BasePlugin

class EnableTest(BasePlugin):
    NAME = "enable_test"
    def on_load(self):
        return True
    def on_enable(self):
        return True
""")

        pm = PluginManager()
        pm.discover(temp_dir)
        result = pm.enable("enable_test")

        assert result is True
        assert pm.is_enabled("enable_test")

    def test_disable_simple(self, temp_dir):
        plugin_dir = os.path.join(temp_dir, "disable_test")
        os.makedirs(plugin_dir)

        with open(os.path.join(plugin_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
            f.write("""
from core.plugin_api import BasePlugin

class DisableTest(BasePlugin):
    NAME = "disable_test"
    def on_load(self):
        return True
    def on_enable(self):
        return True
    def on_disable(self):
        self.disable_called = True
""")

        pm = PluginManager()
        pm.discover(temp_dir)
        pm.enable("disable_test")
        result = pm.disable("disable_test")

        assert result is True
        assert not pm.is_enabled("disable_test")


# ==================== CONTEXTO ====================

class TestContextAPIs:
    def test_set_context_apis(self):
        pm = PluginManager()

        class FakeAPI:
            pass

        settings = FakeAPI()
        cameras = FakeAPI()

        pm.set_context_apis(settings=settings, cameras=cameras)

        assert pm.context.settings is settings
        assert pm.context.cameras is cameras

    def test_set_partial_apis(self):
        pm = PluginManager()

        class FakeSettings:
            pass

        settings = FakeSettings()
        pm.set_context_apis(settings=settings)

        assert pm.context.settings is settings
        assert pm.context.cameras is None

    def test_set_all_apis(self):
        pm = PluginManager()

        class FakeAPI:
            pass

        settings = FakeAPI()
        cameras = FakeAPI()
        frames = FakeAPI()
        ui = FakeAPI()
        files = FakeAPI()
        notifications = FakeAPI()
        timers = FakeAPI()

        pm.set_context_apis(
            settings=settings,
            cameras=cameras,
            frames=frames,
            ui=ui,
            files=files,
            notifications=notifications,
            timers=timers,
        )

        assert pm.context.settings is settings
        assert pm.context.cameras is cameras
        assert pm.context.frames is frames
        assert pm.context.ui is ui
        assert pm.context.files is files
        assert pm.context.notifications is notifications
        assert pm.context.timers is timers


# ==================== SINGLETON ====================

class TestPluginManagerSingleton:
    def test_get_set_plugin_manager(self):
        """Verifica el singleton global."""
        pm = PluginManager()
        set_plugin_manager(pm)

        assert get_plugin_manager() is pm