"""
Markdown viewer con renderizado nivel GitHub.

Usa QWebEngineView + marked.js + highlight.js para renderizar
markdown con resaltado de sintaxis, tablas, y estilos de GitHub.

Requiere:
  - PySide6-QtWebEngine (pip install PySide6-QtWebEngine)
"""
from .markdown_viewer import MarkdownViewer

__all__ = ["MarkdownViewer"]