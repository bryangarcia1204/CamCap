"""
Gestor de notificaciones - Coordina Windows + Telegram
"""
from datetime import datetime
from typing import Optional, Dict
import threading
from plugins.notifications.windows_notifier import windows_notifier


class NotificationManager:
    """Gestor centralizado de notificaciones"""

    def __init__(self):
        from utils.config_loader import advanced_config
        self.min_interval_seconds = advanced_config.get("notification_min_interval", 30)
        self.windows_enabled = True
        self.telegram_enabled = False
        self.telegram_bot = None

        # Historial para evitar spam
        self.recent_notifications: Dict[str, datetime] = {}

        # Cargar Telegram si está configurado
        self._load_telegram_config()

    def _load_telegram_config(self):
        """Carga la configuración de Telegram si existe"""
        try:
            from core.settings_manager import settings_manager
            settings = settings_manager.get_notification_settings()

            if settings.get("telegram_enabled"):
                token = settings.get("telegram_token")
                chat_id = settings.get("telegram_chat_id")

                if token and chat_id:
                    from plugins.notifications.telegram_notifier import TelegramNotifier
                    self.telegram_bot = TelegramNotifier(token, chat_id)
                    self.telegram_enabled = True
                    print("✅ Telegram configurado")
        except Exception as e:
            print(f"⚠️ Telegram no disponible: {e}")

    def _should_notify(self, event_key: str) -> bool:
        """Evita notificaciones repetidas en poco tiempo"""
        now = datetime.now()
        last_time = self.recent_notifications.get(event_key)

        if last_time is None:
            self.recent_notifications[event_key] = now
            return True

        elapsed = (now - last_time).total_seconds()
        if elapsed >= self.min_interval_seconds:
            self.recent_notifications[event_key] = now
            return True

        return False

    def notify_motion(self, camera_name: str, image_path: Optional[str] = None,
                     use_telegram: bool = True):
        """Notifica detección de movimiento"""
        event_key = f"motion_{camera_name}"

        if not self._should_notify(event_key):
            return

        print(f"🚨 Movimiento: {camera_name}")

        # Notificación Windows (en hilo aparte para no bloquear)
        if self.windows_enabled:
            threading.Thread(
                target=self._send_windows_motion,
                args=(camera_name,),
                daemon=True
            ).start()

        # Notificación Telegram
        if use_telegram and self.telegram_enabled and self.telegram_bot:
            threading.Thread(
                target=self._send_telegram_motion,
                args=(camera_name, image_path),
                daemon=True
            ).start()

    def _send_windows_motion(self, camera_name: str):
        try:
            windows_notifier.notify_motion(camera_name)
        except Exception as e:
            print(f"❌ Error en notificación Windows: {e}")

    def _send_telegram_motion(self, camera_name: str, image_path: Optional[str]):
        try:
            self.telegram_bot.send_motion_alert(camera_name, image_path)
        except Exception as e:
            print(f"❌ Error en Telegram: {e}")

    def notify_face_unknown(self, camera_name: str, image_path: Optional[str] = None):
        """Notifica rostro desconocido"""
        event_key = f"unknown_face_{camera_name}"

        if not self._should_notify(event_key):
            return

        print(f"👤 Rostro desconocido: {camera_name}")

        if self.windows_enabled:
            threading.Thread(
                target=lambda: windows_notifier.notify_face_unknown(camera_name),
                daemon=True
            ).start()

        if self.telegram_enabled and self.telegram_bot:
            threading.Thread(
                target=lambda: self.telegram_bot.send_unknown_face_alert(
                    camera_name, image_path
                ),
                daemon=True
            ).start()

    def notify_face_known(self, camera_name: str, person_name: str):
        """Notifica rostro conocido (con cooldown para evitar spam)"""
        event_key = f"face_known_{camera_name}_{person_name}"

        if not self._should_notify(event_key):
            return

        if self.windows_enabled:
            threading.Thread(
                target=lambda: windows_notifier.notify_face_known(camera_name, person_name),
                daemon=True
            ).start()

    def notify_custom(self, title: str, message: str):
        """Notificación personalizada"""
        if self.windows_enabled:
            windows_notifier.notify(title, message)


# Instancia global
notification_manager = NotificationManager()