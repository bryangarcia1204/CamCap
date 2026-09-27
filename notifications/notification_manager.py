"""
DEPRECATED: movido a plugins/notifications/.
"""
import warnings
warnings.warn(
    "notifications.notification_manager está deprecado. "
    "Usa plugins.notifications.notification_manager en su lugar.",
    DeprecationWarning, stacklevel=2,
)
from plugins.notifications.notification_manager import (
    NotificationManager,
    notification_manager,
)
__all__ = ["NotificationManager", "notification_manager"]