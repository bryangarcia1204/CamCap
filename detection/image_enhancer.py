"""
DEPRECATED: Este módulo ha sido movido a `plugins/image_enhancer/`.

Shim de compatibilidad para imports legacy y tests.
"""
import warnings

warnings.warn(
    "detection.image_enhancer está deprecado. "
    "Usa plugins.image_enhancer.image_enhancer en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

from plugins.image_enhancer.image_enhancer import ImageEnhancer

__all__ = ["ImageEnhancer"]