"""
DEPRECATED: Este módulo ha sido movido a `plugins/motion_detector/`.

Este shim se mantiene para compatibilidad total con:
- Imports legacy (`from detection.motion_detector import MotionDetector`)
- Tests existentes
- Código de producción que aún no se ha migrado

Será eliminado en una versión futura.
"""
import warnings

warnings.warn(
    "detection.motion_detector está deprecado. "
    "Usa plugins.motion_detector.motion_detector en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-exportar todo desde el nuevo módulo (plugin)
from plugins.motion_detector.motion_detector import MotionDetector

__all__ = ["MotionDetector"]