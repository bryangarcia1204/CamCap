"""
DEPRECATED: movido a plugins/document_scanner/.
"""
import warnings
warnings.warn(
    "detection.document_detector está deprecado. "
    "Usa plugins.document_scanner.document_detector en su lugar.",
    DeprecationWarning, stacklevel=2,
)
from plugins.document_scanner.document_detector import DocumentDetector
__all__ = ["DocumentDetector"]