"""
DEPRECATED: movido a plugins/notifications/.
"""
import warnings
warnings.warn(
    "notifications.windows_notifier está deprecado. "
    "Usa plugins.notifications.windows_notifier en su lugar.",
    DeprecationWarning, stacklevel=2,
)
from plugins.notifications.windows_notifier import WindowsNotifier, windows_notifier
__all__ = ["WindowsNotifier", "windows_notifier"]