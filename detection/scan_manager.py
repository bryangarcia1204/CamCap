"""
DEPRECATED: movido a plugins/document_scanner/.
"""
import warnings
warnings.warn(
    "detection.scan_manager está deprecado. "
    "Usa plugins.document_scanner.scan_manager en su lugar.",
    DeprecationWarning, stacklevel=2,
)
from plugins.document_scanner.scan_manager import ScanManager
__all__ = ["ScanManager"]