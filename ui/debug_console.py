"""
DEPRECATED: Este módulo ha sido movido a `plugins/debug_console/`.

Este alias se mantiene para compatibilidad temporal.
Será eliminado en una versión futura.
"""
import warnings

warnings.warn(
    "ui.debug_console está deprecado. "
    "Usa plugins.debug_console.console en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-exportar todo desde el nuevo módulo
from plugins.debug_console.console import DebugConsole

__all__ = ["DebugConsole"]