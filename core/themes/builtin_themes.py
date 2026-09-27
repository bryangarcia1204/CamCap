"""
Temas builtin de ProCamera.

Un tema es un ThemeProvider que el Core carga al arrancar.
Si un plugin quiere añadir un tema, solo tiene que registrar
otro ThemeProvider.
"""
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QPalette, QColor

from core.extensions.interfaces import ThemeProvider
from core.extensions.types import ThemeMode
from utils.logger import get_logger

logger = get_logger("BuiltinThemes")


def _find_styles_path() -> Optional[Path]:
    """Localiza resources/styles.qss desde cualquier profundidad."""
    here = Path(__file__).resolve()
    # core/themes/builtin_themes.py → ../../resources/styles.qss
    for candidate in [
        here.parent.parent.parent / "resources" / "styles.qss",
        here.parent.parent / "resources" / "styles.qss",
    ]:
        if candidate.exists():
            return candidate
    return None


class DefaultThemeProvider:
    """Tema por defecto (lee resources/styles.qss)."""

    def get_id(self) -> str:
        return "default"

    def get_name(self) -> str:
        return "Predeterminado"

    def get_mode(self) -> ThemeMode:
        return ThemeMode.DARK

    def get_stylesheet(self) -> str:
        path = _find_styles_path()
        if path is None:
            logger.warning("⚠️ [theme] styles.qss no encontrado")
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"❌ [theme] Error leyendo styles.qss: {e}")
            return ""

    def get_palette(self) -> Optional[QPalette]:
        return None


class LightThemeProvider:
    """Tema claro builtin (mínimo, por si no hay styles_light.qss)."""

    def get_id(self) -> str:
        return "light"

    def get_name(self) -> str:
        return "Claro"

    def get_mode(self) -> ThemeMode:
        return ThemeMode.LIGHT

    def get_stylesheet(self) -> str:
        # Si existe resources/styles_light.qss, usarlo
        here = Path(__file__).resolve()
        for candidate in [
            here.parent.parent.parent / "resources" / "styles_light.qss",
        ]:
            if candidate.exists():
                try:
                    return candidate.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fallback: QSS básico
        return """
            QWidget { background-color: #f5f5f5; color: #1a1a1a; }
            QPushButton { background-color: #e0e0e0; color: #1a1a1a;
                          border: 1px solid #bdbdbd; border-radius: 4px;
                          padding: 6px 12px; }
            QPushButton:hover { background-color: #eeeeee; }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #ffffff; color: #1a1a1a;
                border: 1px solid #bdbdbd; border-radius: 4px; padding: 4px;
            }
            QLabel { color: #1a1a1a; background: transparent; }
            QGroupBox { border: 1px solid #bdbdbd; border-radius: 6px;
                        margin-top: 10px; padding-top: 14px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px;
                               padding: 0 6px; }
        """

    def get_palette(self) -> Optional[QPalette]:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#f5f5f5"))
        palette.setColor(QPalette.WindowText, QColor("#1a1a1a"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.Text, QColor("#1a1a1a"))
        return palette


def register_builtin_themes(registry) -> int:
    """Registra los temas builtin."""
    if registry is None:
        logger.error("❌ No hay registry para registrar temas")
        return 0

    registry.register(
        ThemeProvider, DefaultThemeProvider(),
        priority=50, owner="builtin",
    )
    registry.register(
        ThemeProvider, LightThemeProvider(),
        priority=100, owner="builtin",
    )

    logger.info("🎨 2 ThemeProvider builtin registrados (default, light)")
    return 2