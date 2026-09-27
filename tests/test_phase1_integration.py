"""
Test de integración de Fase 1.

Verifica que:
- El PluginManager se puede instanciar
- Las APIs se pueden inyectar
- Un plugin puede cargarse y usar las APIs
"""
import pytest
import os
import sys
from pathlib import Path


@pytest.mark.gui
class TestPhase1Integration:
    """Test de integración completo."""

    def test_plugin_manager_with_apis(self, qapp):
        """Verifica que se pueden inyectar APIs."""
        from core.plugin_api import PluginManager
        from core.plugin_api.api_impl import (
            SettingsAPIImpl,
            CamerasAPIImpl,
            FramesAPIImpl,
            UIAPIImpl,
            FilesAPIImpl,
            NotificationsAPIImpl,
            TimersAPIImpl,
        )

        pm = PluginManager()

        # Crear APIs
        settings = SettingsAPIImpl()
        cameras = CamerasAPIImpl()
        frames = FramesAPIImpl(cameras)
        ui = UIAPIImpl()
        files = FilesAPIImpl()
        notif = NotificationsAPIImpl()
        timers = TimersAPIImpl()

        # Inyectar
        pm.set_context_apis(
            settings=settings,
            cameras=cameras,
            frames=frames,
            ui=ui,
            files=files,
            notifications=notif,
            timers=timers,
        )

        # Verificar
        assert pm.context.settings is settings
        assert pm.context.cameras is cameras
        assert pm.context.frames is frames
        assert pm.context.ui is ui
        assert pm.context.files is files

    def test_plugin_manager_singleton(self):
        """Verifica que get/set_plugin_manager funciona."""
        from core.plugin_api import (
            PluginManager,
            get_plugin_manager,
            set_plugin_manager,
        )

        pm = PluginManager()
        set_plugin_manager(pm)

        assert get_plugin_manager() is pm

    def test_frame_processor_chain(self):
        """Verifica que los processors de frames se ejecutan en orden."""
        from core.plugin_api.api_impl import FramesAPIImpl

        api = FramesAPIImpl()
        calls = []

        api.register_pre_processor(
            lambda cid, f: calls.append("first") or (f + 1),
            priority=10,
        )
        api.register_pre_processor(
            lambda cid, f: calls.append("second") or (f * 2),
            priority=20,
        )

        import numpy as np
        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        assert calls == ["first", "second"]
        assert result[0][0] == (1 + 1) * 2

    def test_settings_schema(self):
        """Verifica que se puede registrar un schema."""
        from core.plugin_api.api_impl import SettingsAPIImpl

        api = SettingsAPIImpl()
        schema = {"key1": {"type": "int", "default": 10}}
        api.register_config_schema("test_plugin", schema)

        assert api.get_schema("test_plugin") == schema


@pytest.mark.gui
class TestExamplePlugin:
    """Test del plugin de ejemplo."""

    def test_load_example_plugin(self, qapp):
        """Carga el plugin de ejemplo desde el directorio real."""
        from core.plugin_api import PluginManager
        from core.plugin_api.api_impl import (
            SettingsAPIImpl,
            UIAPIImpl,
            FramesAPIImpl,
        )

        project_root = Path(__file__).parent.parent
        plugins_dir = project_root / "plugins"

        if not (plugins_dir / "example_plugin").exists():
            pytest.skip("example_plugin no existe")

        pm = PluginManager()

        # Inyectar APIs mínimas
        settings = SettingsAPIImpl()
        frames = FramesAPIImpl()
        ui = UIAPIImpl()
        pm.set_context_apis(settings=settings, frames=frames, ui=ui)

        # Descubrir y cargar
        count = pm.discover(str(plugins_dir))
        assert count > 0

        result = pm.load("example_plugin")
        assert result is True
        assert pm.is_loaded("example_plugin")

        # Verificar que se registró el schema
        schema = settings.get_schema("example_plugin")
        assert schema is not None
        assert "enabled" in schema

        # Cleanup
        pm.unload_all()