"""
Plugin: Notificaciones.

Se suscribe a eventos del Core:
  - MOTION_DETECTED  → notifica movimiento
  - FACE_DETECTED    → notifica cara conocida/desconocida
  - SETTINGS_CHANGED → recarga config si cambian sus claves
  - APP_CLOSING      → limpia recursos

El Core NO conoce este plugin. Solo emite eventos.
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.Notifications")


class NotificationsPlugin(BasePlugin):
    """Plugin de notificaciones."""

    NAME = "notifications"
    VERSION = "1.0.0"
    DESCRIPTION = "Notificaciones nativas Windows y por Telegram"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._notification_manager = None
        self._tab_provider = None

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        try:
            from .notification_manager import notification_manager
            self._notification_manager = notification_manager
            logger.info("🔌 NotificationsPlugin: singleton cargado")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando NotificationManager: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        try:
            # 1. ConfigTab
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from .config_tab import NotificationsConfigTab

            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=NotificationsConfigTab,
                tab_id="plugin_notifications",
                title="Notifications",
                icon="🔔",
            )
            self.register_extension(
                ConfigTab,
                self._tab_provider,
                priority=150,
            )

            # 2. Suscribirse a eventos del Core
            if self.context.event_bus is not None:
                from core.events import (
                    MOTION_DETECTED,
                    FACE_DETECTED,
                    SETTINGS_CHANGED,
                    APP_CLOSING,
                )
                bus = self.context.event_bus
                bus.subscribe(MOTION_DETECTED, self._on_motion, owner=self.NAME)
                bus.subscribe(FACE_DETECTED, self._on_face, owner=self.NAME)
                bus.subscribe(SETTINGS_CHANGED, self._on_settings, owner=self.NAME)
                bus.subscribe(APP_CLOSING, self._on_app_closing, owner=self.NAME)
                logger.debug("🔗 NotificationsPlugin suscrito a eventos")

            logger.info("✅ NotificationsPlugin activado (ConfigTab + eventos)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        # Desuscribirse del bus
        if self.context.event_bus is not None:
            from core.events import (
                MOTION_DETECTED, FACE_DETECTED,
                SETTINGS_CHANGED, APP_CLOSING,
            )
            bus = self.context.event_bus
            bus.unsubscribe(MOTION_DETECTED, self._on_motion)
            bus.unsubscribe(FACE_DETECTED, self._on_face)
            bus.unsubscribe(SETTINGS_CHANGED, self._on_settings)
            bus.unsubscribe(APP_CLOSING, self._on_app_closing)

        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
                self._tab_provider = None
            except Exception as e:
                logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        logger.info("⏸️ NotificationsPlugin desactivado")

    def on_unload(self):
        self._notification_manager = None
        self._tab_provider = None
        logger.info("🔌 NotificationsPlugin descargado")

    # ==================== HANDLERS DE EVENTOS ====================

    def _on_motion(self, camera_id, camera_name, rects=None, **kwargs):
        """Handler de MOTION_DETECTED."""
        try:
            if self._notification_manager:
                self._notification_manager.notify_motion(camera_name)
        except Exception as e:
            logger.error(f"Error en _on_motion: {e}", exc_info=True)

    def _on_face(self, camera_id, camera_name, names=None, **kwargs):
        """Handler de FACE_DETECTED."""
        if not names:
            return
        try:
            if self._notification_manager is None:
                return
            for name in names:
                if name == "Desconocido":
                    self._notification_manager.notify_face_unknown(camera_name)
                else:
                    self._notification_manager.notify_face_known(camera_name, name)
        except Exception as e:
            logger.error(f"Error en _on_face: {e}", exc_info=True)

    def _on_settings(self, modules=None, **kwargs):
        """Handler de SETTINGS_CHANGED."""
        if not modules:
            return
        if "notifications" in modules:
            try:
                from utils.config_loader import advanced_config
                advanced_config.reload()
                if self._notification_manager:
                    cfg = advanced_config.get_all()
                    self._notification_manager.min_interval_seconds = cfg.get(
                        "notification_min_interval", 30
                    )
                    self._notification_manager._load_telegram_config()
                logger.debug("🔄 Notifications recargado tras SETTINGS_CHANGED")
            except Exception as e:
                logger.error(f"Error recargando notifications: {e}", exc_info=True)

    def _on_app_closing(self, **kwargs):
        """Handler de APP_CLOSING."""
        logger.debug("🔔 Notifications recibió APP_CLOSING")

    # ==================== API PÚBLICA ====================

    def get_manager(self):
        return self._notification_manager