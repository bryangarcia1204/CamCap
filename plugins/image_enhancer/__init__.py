"""
Plugin de mejora de imagen.

Incluye:
- ImageEnhancer (core)
- ImageEnhanceDialog (UI)
"""
from .image_enhancer import ImageEnhancer
from .plugin import ImageEnhancerPlugin

__all__ = [
    "ImageEnhancer",
    "ImageEnhancerPlugin",
]