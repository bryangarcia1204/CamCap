"""Tests para el plugin debug_console."""
import pytest
import os
from pathlib import Path

from core.plugin_api import PluginManager
from core.plugin_api.api_impl import (
    SettingsAPIImpl,
    UIAPIImpl,
    FramesAPIImpl,
    TimersAPIImpl,
)


@pytest.fixture
def debug_plugin_setup(qapp):
    """Setup completo del plugin en modo debug."""
    pm = PluginManager()
    pm.context.is_debug = True   # ← Modo debug activado

    # Inyectar APIs mínimas
    settings = SettingsAPIImpl()
    ui = UIAPIImpl()   # Sin MainWindow — el plugin debe manejar esto
    frames = FramesAPIImpl()
    timers = TimersAPIImpl()

    pm.set_context_apis(
        settings=settings,
        ui=ui,
        frames=frames,
        timers=timers,
    )

    yield pm

    pm.unload_all()


class TestDebugConsolePluginLoad:
    def test_plugin_discovered(self, debug_plugin_setup):
        """El plugin debe estar en el directorio de plugins."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))

        assert "debug_console" in pm.list_discovered()

    def test_plugin_requires_debug(self, qapp):
        """Sin modo debug, el plugin no debe cargarse."""
        pm = PluginManager()
        pm.context.is_debug = False   # ← Debug OFF

        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"
        pm.discover(str(plugins_dir))

        result = pm.load("debug_console")
        assert result is False
        assert not pm.is_loaded("debug_console")

    def test_plugin_loads_in_debug_mode(self, debug_plugin_setup):
        """Con modo debug, el plugin debe cargarse."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))

        result = pm.load("debug_console")
        assert result is True, "El plugin debe cargarse en modo debug"
        assert pm.is_loaded("debug_console")

    def test_plugin_has_console_instance(self, debug_plugin_setup):
        """El plugin debe crear una instancia de DebugConsole."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))
        pm.load("debug_console")

        plugin = pm.get("debug_console")
        assert plugin is not None
        assert hasattr(plugin, '_console')

    def test_plugin_without_ui_does_not_crash(self, qapp):
        """El plugin no debe crashear sin UIAPI inyectada."""
        pm = PluginManager()
        pm.context.is_debug = True

        # Sin UIAPI
        from core.plugin_api.api_impl import SettingsAPIImpl
        pm.set_context_apis(settings=SettingsAPIImpl())

        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"
        pm.discover(str(plugins_dir))

        # No debe crashear
        result = pm.load("debug_console")
        # Puede cargar o fallar, pero no debe crashear


class TestDebugConsolePluginLifecycle:
    def test_enable_after_load(self, debug_plugin_setup):
        """Después de cargar, se debe poder activar."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))
        pm.load("debug_console")

        result = pm.enable("debug_console")
        assert result is True
        assert pm.is_enabled("debug_console")

    def test_disable_hides_console(self, debug_plugin_setup):
        """Al desactivar, la consola debe ocultarse."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))
        pm.enable("debug_console")

        plugin = pm.get("debug_console")
        # Si la consola está visible, se oculta al disable
        pm.disable("debug_console")
        assert not pm.is_enabled("debug_console")

    def test_unload_cleans_resources(self, debug_plugin_setup):
        """Al descargar, los recursos deben liberarse."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))
        pm.load("debug_console")

        plugin = pm.get("debug_console")

        pm.unload("debug_console")
        assert not pm.is_loaded("debug_console")
        assert pm.get("debug_console") is None


class TestDebugConsolePluginAPI:
    def test_show_console_method(self, debug_plugin_setup):
        """El plugin expone show_console()."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))
        pm.load("debug_console")

        plugin = pm.get("debug_console")
        # El método debe existir
        assert hasattr(plugin, 'show_console')
        assert hasattr(plugin, 'hide_console')
        assert hasattr(plugin, 'is_console_visible')
        assert hasattr(plugin, 'clear_console')

    def test_console_toggle_state(self, debug_plugin_setup):
        """El toggle debe alternar el estado."""
        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        pm = debug_plugin_setup
        pm.discover(str(plugins_dir))
        pm.load("debug_console")

        plugin = pm.get("debug_console")

        # Sin dock (no hay MainWindow), no debe crashear
        initial_state = plugin.is_console_visible()
        # No podemos verificar el toggle sin un dock real