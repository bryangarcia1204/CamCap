"""
Plugin de consola de debug.

Funcionalidad:
- Muestra los logs en tiempo real
- Solo se activa en modo debug
- Se toggle con Ctrl+Alt+C x3
- Se acopla como dock widget en la parte inferior
- Registra su ConfigTab en SettingsDialog
"""
from PySide6.QtWidgets import QDockWidget, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
import time

from core.plugin_api import BasePlugin
from .console import DebugConsole


class DebugConsolePlugin(BasePlugin):
    """Plugin de consola de debug."""

    NAME = "debug_console"
    VERSION = "1.0.0"
    DESCRIPTION = "Consola de logs en tiempo real"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = True   # ← Solo se activa en modo debug

    # Estado del atajo Ctrl+Alt+C x3
    CTRL_ALT_C_TIMEOUT_MS = 1000
    CTRL_ALT_C_TARGET = 3

    def __init__(self, context):
        super().__init__(context)

        # UI
        self._console: DebugConsole = None
        self._dock: QDockWidget = None
        self._shortcut: QShortcut = None
        self._tab_provider = None

        # Estado del atajo
        self._cac_count = 0
        self._cac_last_time = 0
        self._console_visible = False

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        """Crea la consola y la registra como dock widget."""
        self.logger.info("🔌 Cargando DebugConsolePlugin...")

        if not self.context.is_debug:
            self.logger.warning("⚠️ DebugConsolePlugin requiere modo debug")
            return False

        try:
            self._console = DebugConsole()
        except Exception as e:
            self.logger.error(f"❌ Error creando consola: {e}", exc_info=True)
            return False

        try:
            if self.context.ui:
                self._dock = self.context.ui.add_dock_widget(
                    title="🖥️ Consola de Debug",
                    widget=self._console,
                    area="bottom",
                )
                if self._dock:
                    self._dock.setVisible(False)
                    self.logger.debug("🖥️ Dock widget creado (oculto)")
                else:
                    self.logger.warning("⚠️ No se pudo crear dock widget")
        except Exception as e:
            self.logger.error(f"❌ Error creando dock: {e}", exc_info=True)
            return False

        self._register_shortcut()

        self.logger.info("✅ DebugConsolePlugin cargado")
        return True

    def on_enable(self) -> bool:
        """Registra el ConfigTab (no tiene provider)."""
        try:
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from .config_tab import DebugConsoleConfigTab

            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=DebugConsoleConfigTab,
                tab_id="plugin_debug_console",
                title="Debug Console",
                icon="🐛",
            )
            self.register_extension(
                ConfigTab,
                self._tab_provider,
                priority=200,
            )

            self.logger.info("✅ DebugConsolePlugin activado (ConfigTab)")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        """Desregistra ConfigTab y oculta la consola."""
        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
                self._tab_provider = None
                self.logger.debug("🗑️ ConfigTab de debug_console desregistrada")
            except Exception as e:
                self.logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        if self._dock:
            self._dock.setVisible(False)
        self._console_visible = False

        self.logger.info("⏸️ DebugConsolePlugin desactivado")

    def on_unload(self):
        """Limpia los recursos."""
        self.logger.info("🔌 Descargando DebugConsolePlugin...")

        if self._shortcut:
            try:
                self._shortcut.setEnabled(False)
                self._shortcut.deleteLater()
            except Exception:
                pass
            self._shortcut = None

        if self._dock:
            try:
                self._dock.setParent(None)
                self._dock.deleteLater()
            except Exception:
                pass
            self._dock = None

        if self._console:
            try:
                self._console.setParent(None)
                self._console.deleteLater()
            except Exception:
                pass
            self._console = None

        self._tab_provider = None

        self.logger.info("✅ DebugConsolePlugin descargado")

    # ==================== SHORTCUT ====================

    def _register_shortcut(self):
        """Registra el shortcut Ctrl+Alt+C."""
        try:
            main_window = None
            if self.context.ui and hasattr(self.context.ui, '_main_window'):
                main_window = self.context.ui._main_window

            if main_window is None:
                self.logger.warning("⚠️ No hay MainWindow para el shortcut")
                return

            self._shortcut = QShortcut(
                QKeySequence("Ctrl+Alt+C"), main_window
            )
            self._shortcut.setContext(Qt.ApplicationShortcut)
            self._shortcut.activated.connect(self._on_shortcut_activated)

            self.logger.debug("⌨️ Shortcut Ctrl+Alt+C registrado")

        except Exception as e:
            self.logger.error(f"❌ Error registrando shortcut: {e}", exc_info=True)

    def _on_shortcut_activated(self):
        """Detecta Ctrl+Alt+C pulsado 3 veces seguidas."""
        now = time.time() * 1000

        if now - self._cac_last_time > self.CTRL_ALT_C_TIMEOUT_MS:
            self._cac_count = 1
            self.logger.debug("⌨️ Ctrl+Alt+C (1/3)")
        else:
            self._cac_count += 1
            self.logger.debug(f"⌨️ Ctrl+Alt+C ({self._cac_count}/3)")

        self._cac_last_time = now

        if self._cac_count >= self.CTRL_ALT_C_TARGET:
            self._cac_count = 0
            self._toggle_console()

    # ==================== TOGGLE ====================

    def _toggle_console(self):
        """Muestra/oculta la consola."""
        if self._dock is None:
            self.logger.warning("⚠️ No hay dock para toggle")
            return

        self._console_visible = not self._console_visible
        self._dock.setVisible(self._console_visible)

        if self._console_visible:
            self._dock.raise_()
            self.logger.info("🖥️ Consola de debug MOSTRADA")
            if self.context.ui:
                self.context.ui.show_status_message(
                    "🖥️ Consola de debug activada"
                )
        else:
            self.logger.info("🖥️ Consola de debug OCULTADA")
            if self.context.ui:
                self.context.ui.show_status_message(
                    "🖥️ Consola de debug desactivada"
                )

    # ==================== API PÚBLICA ====================

    def show_console(self):
        if self._dock and not self._console_visible:
            self._toggle_console()

    def hide_console(self):
        if self._dock and self._console_visible:
            self._toggle_console()

    def is_console_visible(self) -> bool:
        return self._console_visible

    def clear_console(self):
        if self._console:
            self._console.clear()