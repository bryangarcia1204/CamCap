"""Tests de integración UI + ExtensionRegistry."""
import pytest
from PySide6.QtWidgets import QWidget, QLabel, QPushButton
from PySide6.QtGui import QAction

from core.extension_registry import ExtensionRegistry, set_extension_registry
from core.extensions.interfaces import (
    ToolbarProvider,
    MenuProvider,
    ConfigTab,
    ConfigSection,
    StatusWidget,
)


@pytest.fixture
def clean_registry():
    """Registry limpio para cada test."""
    registry = ExtensionRegistry()
    set_extension_registry(registry)
    yield registry
    registry.clear()


@pytest.mark.gui
class TestToolbarProviderIntegration:

    def test_register_toolbar_provider(self, qapp, clean_registry):
        """Un ToolbarProvider debe registrarse."""
        from PySide6.QtWidgets import QPushButton

        class MyToolbarProvider:
            def get_widgets(self):
                return [QPushButton("Test")]

        provider = MyToolbarProvider()
        clean_registry.register(ToolbarProvider, provider)

        providers = clean_registry.get(ToolbarProvider)
        assert len(providers) == 1
        assert providers[0] is provider

    def test_toolbar_provider_returns_widgets(self, qapp, clean_registry):
        """get_widgets debe retornar los widgets."""
        from PySide6.QtWidgets import QPushButton

        class MyToolbarProvider:
            def get_widgets(self):
                return [QPushButton("A"), QPushButton("B")]

        clean_registry.register(ToolbarProvider, MyToolbarProvider())

        providers = clean_registry.get(ToolbarProvider)
        widgets = providers[0].get_widgets()
        assert len(widgets) == 2


@pytest.mark.gui
class TestMenuProviderIntegration:

    def test_register_menu_provider(self, qapp, clean_registry):
        """Un MenuProvider debe registrarse."""
        class MyMenuProvider:
            def get_menu_name(self):
                return "Test"
            def get_actions(self):
                return [QAction("Action1")]

        clean_registry.register(MenuProvider, MyMenuProvider())

        providers = clean_registry.get(MenuProvider)
        assert len(providers) == 1

    def test_menu_provider_actions(self, qapp, clean_registry):
        """get_actions debe retornar acciones."""
        class MyMenuProvider:
            def get_menu_name(self):
                return "Plugins"
            def get_actions(self):
                return [QAction("A"), QAction("B"), QAction("C")]

        clean_registry.register(MenuProvider, MyMenuProvider())
        providers = clean_registry.get(MenuProvider)
        actions = providers[0].get_actions()
        assert len(actions) == 3


@pytest.mark.gui
class TestConfigTabIntegration:

    def test_register_config_tab(self, qapp, clean_registry):
        """Un ConfigTab debe registrarse."""
        class MyConfigTab:
            def get_id(self): return "test_tab"
            def get_title(self): return "Test Tab"
            def get_icon(self): return "🧪"
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def on_load(self): pass

        clean_registry.register(ConfigTab, MyConfigTab())

        tabs = clean_registry.get(ConfigTab)
        assert len(tabs) == 1
        assert tabs[0].get_id() == "test_tab"

    def test_config_tab_priority(self, qapp, clean_registry):
        """Los tabs deben respetar prioridad."""
        class TabA:
            def get_id(self): return "a"
            def get_title(self): return "A"
            def get_icon(self): return ""
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def on_load(self): pass

        class TabB:
            def get_id(self): return "b"
            def get_title(self): return "B"
            def get_icon(self): return ""
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def on_load(self): pass

        clean_registry.register(ConfigTab, TabA(), priority=100)
        clean_registry.register(ConfigTab, TabB(), priority=10)

        tabs = clean_registry.get(ConfigTab)
        assert tabs[0].get_id() == "b"  # prioridad 10
        assert tabs[1].get_id() == "a"  # prioridad 100


@pytest.mark.gui
class TestConfigSectionIntegration:

    def test_register_config_section(self, qapp, clean_registry):
        """Un ConfigSection debe registrarse."""
        class MySection:
            def get_target_tab_id(self): return "capture"
            def get_title(self): return "Advanced"
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def get_priority(self): return 50

        clean_registry.register(ConfigSection, MySection())

        sections = clean_registry.get(ConfigSection)
        assert len(sections) == 1
        assert sections[0].get_target_tab_id() == "capture"

    def test_multiple_sections_same_tab(self, qapp, clean_registry):
        """Múltiples secciones para la misma tab."""
        class SectionA:
            def get_target_tab_id(self): return "capture"
            def get_title(self): return "A"
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def get_priority(self): return 50

        class SectionB:
            def get_target_tab_id(self): return "capture"
            def get_title(self): return "B"
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def get_priority(self): return 50

        clean_registry.register(ConfigSection, SectionA())
        clean_registry.register(ConfigSection, SectionB())

        sections = clean_registry.get(ConfigSection)
        assert len(sections) == 2

        # Filtrar por tab
        capture_sections = [
            s for s in sections if s.get_target_tab_id() == "capture"
        ]
        assert len(capture_sections) == 2


@pytest.mark.gui
class TestStatusWidgetIntegration:

    def test_register_status_widget(self, qapp, clean_registry):
        """Un StatusWidget debe registrarse."""
        class MyStatusWidget:
            def get_widget(self):
                return QLabel("Status")

        clean_registry.register(StatusWidget, MyStatusWidget())

        widgets = clean_registry.get(StatusWidget)
        assert len(widgets) == 1


@pytest.mark.gui
class TestUIFullIntegration:

    def test_all_ui_extensions_coexist(self, qapp, clean_registry):
        """Todas las extensiones UI deben coexistir."""
        # Toolbar
        class ToolbarP:
            def get_widgets(self):
                return [QPushButton("TB")]

        # Menu
        class MenuP:
            def get_menu_name(self): return "Plugins"
            def get_actions(self):
                return [QAction("Menu")]

        # ConfigTab
        class ConfigT:
            def get_id(self): return "t"
            def get_title(self): return "T"
            def get_icon(self): return ""
            def get_widget(self): return QWidget()
            def on_save(self): return True
            def on_load(self): pass

        # StatusWidget
        class StatusW:
            def get_widget(self): return QLabel("Status")

        clean_registry.register(ToolbarProvider, ToolbarP())
        clean_registry.register(MenuProvider, MenuP())
        clean_registry.register(ConfigTab, ConfigT())
        clean_registry.register(StatusWidget, StatusW())

        # Verificar
        assert len(clean_registry.get(ToolbarProvider)) == 1
        assert len(clean_registry.get(MenuProvider)) == 1
        assert len(clean_registry.get(ConfigTab)) == 1
        assert len(clean_registry.get(StatusWidget)) == 1