"""
DEPRECATED: movido a plugins/notifications/.
"""
import warnings
warnings.warn(
    "notifications.telegram_notifier está deprecado. "
    "Usa plugins.notifications.telegram_notifier en su lugar.",
    DeprecationWarning, stacklevel=2,
)
from plugins.notifications.telegram_notifier import TelegramNotifier
__all__ = ["TelegramNotifier"]