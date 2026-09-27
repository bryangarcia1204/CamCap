"""
ConfigWidgets builtin: ColorPicker, FilePicker.

Los ConfigWidgets se registran como factories en el
ConfigWidgetRegistry, y luego SettingsDialog los puede usar
para renderizar campos de configuración de plugins.
"""
from typing import Any, Optional

from PySide6.QtWidgets import (
    QWidget, QPushButton, QColorDialog, QFileDialog,
    QHBoxLayout, QLineEdit,
)
from PySide6.QtGui import QColor

from utils.logger import get_logger

logger = get_logger("ConfigWidgets")


class ColorPickerConfigWidget:
    """ConfigWidget para elegir un color."""

    def __init__(self, key: str, default: str = "#4da0c4"):
        self._key = key
        self._value = str(default) if default else "#4da0c4"
        self._widget: Optional[QWidget] = None
        self._preview: Optional[QPushButton] = None
        self._label: Optional[QLineEdit] = None

    def get_config_key(self) -> str:
        return self._key

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self._widget = QWidget()
            layout = QHBoxLayout(self._widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self._preview = QPushButton()
            self._preview.setFixedSize(36, 24)
            self._preview.setToolTip("Click para elegir color")
            self._update_preview()
            self._preview.clicked.connect(self._pick_color)
            layout.addWidget(self._preview)

            self._label = QLineEdit(self._value)
            self._label.setReadOnly(True)
            layout.addWidget(self._label, 1)

        return self._widget

    def _update_preview(self):
        if self._preview is not None:
            self._preview.setStyleSheet(
                f"background-color: {self._value}; "
                f"border: 1px solid rgba(0,0,0,0.3); border-radius: 4px;"
            )

    def _pick_color(self):
        initial = QColor(self._value)
        color = QColorDialog.getColor(
            initial, self._widget, "Seleccionar color"
        )
        if color.isValid():
            self._value = color.name()
            self._update_preview()
            if self._label is not None:
                self._label.setText(self._value)

    def get_value(self) -> Any:
        return self._value

    def set_value(self, value: Any):
        self._value = str(value)
        if self._widget is not None:
            self._update_preview()
            if self._label is not None:
                self._label.setText(self._value)


class FilePickerConfigWidget:
    """ConfigWidget para elegir un archivo."""

    def __init__(
        self,
        key: str,
        default: str = "",
        filter: str = "Todos los archivos (*)",
    ):
        self._key = key
        self._value = str(default) if default else ""
        self._filter = filter
        self._widget: Optional[QWidget] = None
        self._label: Optional[QLineEdit] = None

    def get_config_key(self) -> str:
        return self._key

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self._widget = QWidget()
            layout = QHBoxLayout(self._widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self._label = QLineEdit(self._value)
            self._label.setReadOnly(True)
            layout.addWidget(self._label, 1)

            btn = QPushButton("📁")
            btn.setFixedWidth(36)
            btn.clicked.connect(self._pick_file)
            layout.addWidget(btn)

        return self._widget

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self._widget, "Seleccionar archivo", self._value, self._filter
        )
        if path:
            self._value = path
            if self._label is not None:
                self._label.setText(path)

    def get_value(self) -> Any:
        return self._value

    def set_value(self, value: Any):
        self._value = str(value)
        if self._label is not None:
            self._label.setText(self._value)


def register_builtin_config_widgets():
    """Registra los ConfigWidgets builtin."""
    try:
        from core.extensions.config_widget_registry import (
            get_config_widget_registry,
        )
        registry = get_config_widget_registry()

        registry.register(
            "color",
            lambda key, default, **kw: ColorPickerConfigWidget(key, default),
            owner="builtin",
        )
        registry.register(
            "file",
            lambda key, default, **kw: FilePickerConfigWidget(
                key, default, filter=kw.get("filter", "Todos los archivos (*)")
            ),
            owner="builtin",
        )
        logger.info("📦 2 ConfigWidget builtin registrados (color, file)")
    except Exception as e:
        logger.error(f"❌ Error registrando ConfigWidgets: {e}", exc_info=True)