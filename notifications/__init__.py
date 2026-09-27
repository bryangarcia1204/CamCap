"""
DEPRECATED: módulo notifications migrado a plugins/notifications/.

Este shim mantiene compatibilidad con imports legacy.
"""
import warnings

warnings.warn(
    "El módulo 'notifications' está deprecado. "
    "Usa 'plugins.notifications' en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

from plugins.notifications import (
    WindowsNotifier,
    windows_notifier,
    TelegramNotifier,
    NotificationManager,
    notification_manager,
)

__all__ = [
    "WindowsNotifier",
    "windows_notifier",
    "TelegramNotifier",
    "NotificationManager",
    "notification_manager",
]