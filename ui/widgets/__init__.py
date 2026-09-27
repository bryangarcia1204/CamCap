"""Widgets reutilizables de UI."""
from .config_widgets import (
    ColorPickerConfigWidget,
    FilePickerConfigWidget,
    register_builtin_config_widgets,
)

__all__ = [
    "ColorPickerConfigWidget",
    "FilePickerConfigWidget",
    "register_builtin_config_widgets",
]