"""Widgets de flash inyectables en CameraWidget."""
from PySide6.QtWidgets import QPushButton

from utils.logger import get_logger

logger = get_logger("Plugin.CameraControls")


def create_flash_widgets(camera_id: int, camera, camera_widget):
    """Crea botones flash y auto-flash para una cámara IP."""
    # Solo cámaras IP (no screen, no local)
    if camera.is_screen or camera.is_local:
        return []

    # === Botón flash ===
    flash_btn = QPushButton("🔦")
    flash_btn.setFixedSize(28, 28)
    flash_btn.setToolTip("Activar/Desactivar flash")
    flash_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px;
            padding: 0px;
        }
        QPushButton:hover {
            background: rgba(255,193,7,0.15);
            border-color: rgba(255,193,7,0.4);
        }
        QPushButton[type="flash-on"] {
            background: rgba(255, 193, 7, 0.3);
            border-color: #FFC107;
        }
    """)

    # === Botón auto-flash ===
    auto_flash_btn = QPushButton("⚡")
    auto_flash_btn.setFixedSize(28, 28)
    auto_flash_btn.setToolTip("Flash automático")
    auto_flash_btn.setCheckable(True)
    auto_flash_btn.setChecked(getattr(camera, "auto_flash", False))
    auto_flash_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px;
            padding: 0px;
        }
        QPushButton:hover {
            background: rgba(255,152,0,0.15);
            border-color: rgba(255,152,0,0.4);
        }
        QPushButton:checked {
            background: rgba(255, 87, 34, 0.3);
            border-color: #FF5722;
            color: #FF5722;
        }
    """)

    # === Estado ===
    state = {
        "flash_active": False,
        "auto_flash": getattr(camera, "auto_flash", False),
    }

    def _toggle_flash():
        state["flash_active"] = not state["flash_active"]
        if state["flash_active"]:
            flash_btn.setProperty("type", "flash-on")
            flash_btn.setToolTip("Flash encendido")
        else:
            flash_btn.setProperty("type", "")
            flash_btn.setToolTip("Flash apagado")
        flash_btn.style().unpolish(flash_btn)
        flash_btn.style().polish(flash_btn)

        camera_widget.flash_toggled.emit(camera_id, state["flash_active"])

    def _toggle_auto_flash(checked: bool):
        state["auto_flash"] = checked
        camera.auto_flash = checked
        camera_widget.auto_flash_toggled.emit(camera_id, checked)

    def set_flash_state(enabled: bool):
        state["flash_active"] = enabled
        if enabled:
            flash_btn.setProperty("type", "flash-on")
        else:
            flash_btn.setProperty("type", "")
        flash_btn.style().unpolish(flash_btn)
        flash_btn.style().polish(flash_btn)

    def is_auto_flash_enabled() -> bool:
        return state["auto_flash"] and not camera.is_screen and not camera.is_local

    flash_btn.clicked.connect(_toggle_flash)
    auto_flash_btn.clicked.connect(_toggle_auto_flash)

    # Exponer estado a través del camera_widget (para MainWindow y auto-flash)
    camera_widget._plugin_flash = {
        "flash_btn": flash_btn,
        "auto_flash_btn": auto_flash_btn,
        "set_flash_state": set_flash_state,
        "is_auto_flash_enabled": is_auto_flash_enabled,
        "state": state,
    }

    return [flash_btn, auto_flash_btn]