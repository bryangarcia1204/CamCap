"""
DEPRECATED: Este módulo ha sido movido a `plugins/image_enhancer/`.

Shim de compatibilidad para imports legacy.
"""
import warnings

warnings.warn(
    "ui.image_enhance_dialog está deprecado. "
    "Usa plugins.image_enhancer.enhance_dialog en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

from plugins.image_enhancer.enhance_dialog import ImageEnhanceDialog

__all__ = ["ImageEnhanceDialog"]