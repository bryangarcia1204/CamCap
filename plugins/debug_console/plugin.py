"""
Plugin de consola de debug.

Funcionalidad:
- Muestra los logs en tiempo real en un dock widget
- Solo se carga en modo debug (REQUIRES_DEBUG = True)
- Toggle con Ctrl+Alt+C pulsado 3 veces
- Registra su ConfigTab en SettingsDialog

Arquitectura:
- on_load():   solo valida que hay debug mode
- on_enable(): crea el dock, registra shortcut, registra ConfigTab
- on_disable(): destruye el dock, desregistra shortcut y ConfigTab
- on_unload():  limpieza final
"""
import time

from PySide6.QtWidgets import QDockWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence

from core.plugin_api import BasePlugin
from .console import DebugConsole


class DebugConsolePlugin(BasePlugin):
    """Plugin de consola de debug."""

    NAME = "debug_console"
    VERSION = "1.0.0"
    DESCRIPTION = "Consola de logs en tiempo real"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = True

    # Config del atajo
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

        # Config del tab (para aplicar cambios en vivo)
        self._config = {
            "max_lines": 5000,
            "auto_scroll": True,
        }

    # ==================== CONFIG ====================

    def _load_config(self):
        """Carga la config del plugin desde settings."""
        try:
            if self.context.settings is not None:
                cfg = self.context.settings.get_plugin_config(self.NAME)
                if cfg:
                    self._config["max_lines"] = int(cfg.get("max_lines", 5000))
                    self._config["auto_scroll"] = bool(cfg.get("auto_scroll", True))
        except Exception as e:
            self.logger.debug(f"No se pudo cargar config: {e}")

    def _apply_config_to_console(self):
        """Aplica la config actual al widget DebugConsole."""
        if self._console is None:
            return
        try:
            self._console.set_max_lines(self._config["max_lines"])
            self._console.set_auto_scroll(self._config["auto_scroll"])
        except Exception as e:
            self.logger.debug(f"Error aplicando config a consola: {e}")

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        """Valida que estamos en modo debug."""
        if not self.context.is_debug:
            self.logger.warning("⚠️ DebugConsolePlugin requiere modo debug")
            return False

        # Cargar config del plugin
        self._load_config()

        self.logger.info("🔌 DebugConsolePlugin listo para activar")
        return True

    def on_enable(self) -> bool:
        """Crea la consola, el dock, el shortcut y registra el ConfigTab."""
        try:
            # 1. Crear el widget de consola
            self._console = DebugConsole()
            self._apply_config_to_console()

            # 2. Crear el dock widget
            self._create_dock()

            # 3. Registrar el shortcut
            self._register_shortcut()

            # 4. Registrar el ConfigTab
            self._register_config_tab()

            self.logger.info("✅ DebugConsolePlugin activado")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            self._cleanup_all()
            return False

    def on_disable(self):
        """Destruye el dock, desregistra shortcut y ConfigTab."""
        self._cleanup_all()
        self.logger.info("⏸️ DebugConsolePlugin desactivado")

    def on_unload(self):
        """Limpieza final."""
        self._cleanup_all()
        self.logger.info("🔌 DebugConsolePlugin descargado")

    # ==================== SETUP ====================

    def _create_dock(self):
        """Crea el dock widget usando la API moderna."""
        if self.context.ui is None:
            raise RuntimeError("UIAPI no disponible")

        self._dock = self.context.ui.add_dock_widget(
            title="🖥️ Consola de Debug",
            widget=self._console,
            area="bottom",
        )
        if self._dock is None:
            raise RuntimeError("UIAPI.add_dock_widget() devolvió None")

        self._dock.setVisible(False)
        self.logger.debug("🖥️ Dock widget creado (oculto)")

    def _register_shortcut(self):
        """Registra el shortcut Ctrl+Alt+C en la MainWindow."""
        main_window = None

        # Intento 1: API moderna
        try:
            if self.context.ui and hasattr(self.context.ui, "get_main_window"):
                main_window = self.context.ui.get_main_window()
        except Exception:
            pass

        # Intento 2: fallback legacy (por si el API no tiene get_main_window)
        if main_window is None:
            try:
                if self.context.ui and hasattr(self.context.ui, "_main_window"):
                    main_window = self.context.ui._main_window
            except Exception:
                pass

        if main_window is None:
            self.logger.warning("⚠️ No hay MainWindow para el shortcut")
            return

        try:
            self._shortcut = QShortcut(QKeySequence("Ctrl+Alt+C"), main_window)
            self._shortcut.setContext(Qt.ApplicationShortcut)
            self._shortcut.activated.connect(self._on_shortcut_activated)
            self.logger.debug("⌨️ Shortcut Ctrl+Alt+C registrado")
        except Exception as e:
            self.logger.error(f"❌ Error registrando shortcut: {e}", exc_info=True)

    def _register_config_tab(self):
        """Registra el ConfigTab del plugin."""
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
        self.logger.debug("🎨 ConfigTab registrado")

    # ==================== SHORTCUT ====================

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
            self.toggle_console()

    # ==================== TOGGLE ====================

    def toggle_console(self):
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
                try:
                    self.context.ui.show_status_message(
                        "🖥️ Consola de debug activada"
                    )
                except Exception:
                    pass
        else:
            self.logger.info("🖥️ Consola de debug OCULTADA")
            if self.context.ui:
                try:
                    self.context.ui.show_status_message(
                        "🖥️ Consola de debug desactivada"
                    )
                except Exception:
                    pass

    # ==================== CLEANUP ====================

    def _cleanup_all(self):
        """Limpia el dock, shortcut y ConfigTab. Idempotente."""
        # 1. Desregistrar el ConfigTab
        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
            except Exception as e:
                self.logger.debug(f"Error desregistrando ConfigTab: {e}")
            self._tab_provider = None

        # 2. Destruir el shortcut
        if self._shortcut is not None:
            try:
                self._shortcut.setEnabled(False)
                self._shortcut.deleteLater()
            except Exception:
                pass
            self._shortcut = None

        # 3. Destruir el dock
        if self._dock is not None:
            try:
                self._dock.setVisible(False)
                self._dock.setParent(None)
                self._dock.deleteLater()
            except Exception:
                pass
            self._dock = None

        # 4. Destruir el widget de consola
        if self._console is not None:
            try:
                self._console.setParent(None)
                self._console.deleteLater()
            except Exception:
                pass
            self._console = None

        self._console_visible = False
        self._cac_count = 0

    # ==================== API PÚBLICA ====================

    def show_console(self):
        """Muestra la consola (idempotente)."""
        if self._dock and not self._console_visible:
            self.toggle_console()

    def hide_console(self):
        """Oculta la consola (idempotente)."""
        if self._dock and self._console_visible:
            self.toggle_console()

    def is_console_visible(self) -> bool:
        return self._console_visible

    def clear_console(self):
        if self._console:
            self._console.clear()

    def apply_config(self, config: dict):
        """
        Aplica nueva config al plugin (llamado desde el ConfigTab).
        """
        self._config.update(config)
        self._apply_config_to_console()