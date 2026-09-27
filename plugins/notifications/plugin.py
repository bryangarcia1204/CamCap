"""
Plugin: Notificaciones.

Registra el singleton NotificationManager y su ConfigTab.
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
            from plugins.notifications.notification_manager import notification_manager
            self._notification_manager = notification_manager
            logger.info("🔌 NotificationsPlugin: singleton cargado")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando NotificationManager: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        try:
            # 1. Provider
            from core.extensions.interfaces import NotificationsProvider
            self.register_extension(
                NotificationsProvider,
                self,
                priority=50,
            )

            # 2. ConfigTab
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from plugins.notifications.config_tab import NotificationsConfigTab

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

            logger.info("✅ NotificationsPlugin activado (provider + ConfigTab)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
                self._tab_provider = None
                logger.debug("🗑️ ConfigTab de notifications desregistrada")
            except Exception as e:
                logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        logger.info("⏸️ NotificationsPlugin desactivado")

    def on_unload(self):
        self._notification_manager = None
        self._tab_provider = None
        logger.info("🔌 NotificationsPlugin descargado")

    # ==================== API PÚBLICA ====================

    def get_manager(self):
        return self._notification_manager

    def notify_motion(self, camera_name: str, image_path=None):
        if self._notification_manager:
            self._notification_manager.notify_motion(camera_name, image_path)

    def notify_face_unknown(self, camera_name: str, image_path=None):
        if self._notification_manager:
            self._notification_manager.notify_face_unknown(camera_name, image_path)

    def notify_face_known(self, camera_name: str, person_name: str):
        if self._notification_manager:
            self._notification_manager.notify_face_known(camera_name, person_name)

    def notify_custom(self, title: str, message: str):
        if self._notification_manager:
            self._notification_manager.notify_custom(title, message)