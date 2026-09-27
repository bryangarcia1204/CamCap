"""
Plugin de notificaciones.

Incluye:
- WindowsNotifier (notificaciones nativas Windows)
- TelegramNotifier (notificaciones por Telegram)
- NotificationManager (orquestador + cooldown)
"""
from .windows_notifier import WindowsNotifier, windows_notifier
from .telegram_notifier import TelegramNotifier
from .notification_manager import NotificationManager, notification_manager
from .plugin import NotificationsPlugin

__all__ = [
    "WindowsNotifier",
    "windows_notifier",
    "TelegramNotifier",
    "NotificationManager",
    "notification_manager",
    "NotificationsPlugin",
]