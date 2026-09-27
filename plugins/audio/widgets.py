"""
Widgets de audio inyectables en CameraWidget y toolbar.

Este módulo es la fuente de verdad para:
- Botón 🔊 de audio por cámara
- Botón 🔇 de mute
- VU meter compacto y grande
- Botón 🎤 Mic PC en toolbar
"""
from PySide6.QtWidgets import QPushButton, QWidget, QMessageBox
from PySide6.QtCore import Qt

from ui.audio_level_widget import AudioLevelWidget
from utils.logger import get_logger

logger = get_logger("Plugin.AudioWidgets")


def create_audio_widgets(camera_id: int, camera_widget):
    """
    Crea los widgets de audio para una cámara.

    Returns:
        Lista de [audio_btn, mute_btn, audio_level_widget]
    """
    from .audio_manager import audio_manager

    # === Botón de audio ===
    audio_btn = QPushButton("🔊")
    audio_btn.setFixedSize(28, 28)
    audio_btn.setToolTip("Activar/Desactivar audio")
    audio_btn.setCheckable(True)
    audio_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px;
            padding: 0px;
        }
        QPushButton:hover {
            background: rgba(76,175,80,0.15);
            border-color: rgba(76,175,80,0.4);
        }
        QPushButton:checked {
            background: rgba(76, 175, 80, 0.3);
            border-color: #4CAF50;
        }
    """)

    # === Botón mute ===
    mute_btn = QPushButton("🔊")
    mute_btn.setFixedSize(28, 28)
    mute_btn.setToolTip("Silenciar audio (la captura sigue activa)")
    mute_btn.setCheckable(True)
    mute_btn.setVisible(False)
    mute_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px;
            padding: 0px;
        }
        QPushButton:hover {
            background: rgba(244,67,54,0.15);
            border-color: rgba(244,67,54,0.4);
        }
        QPushButton:checked {
            background: rgba(244, 67, 54, 0.3);
            border-color: #f44336;
        }
    """)

    # === VU meter ===
    audio_level_widget = AudioLevelWidget(mode="compact")
    audio_level_widget.setFixedWidth(60)
    audio_level_widget.setFixedHeight(10)
    audio_level_widget.setVisible(False)

    # === Estado interno ===
    state = {
        "timer_running": False,
    }

    # === Callbacks ===
    def _toggle_audio(checked: bool):
        from .audio_manager import audio_manager
        camera = camera_widget.camera

        logger.debug(
            f"🔊 [plugin audio] {camera.name}: "
            f"{'activar' if checked else 'desactivar'}"
        )

        if checked:
            success = audio_manager.start_camera_audio(
                camera_id=camera.id,
                ip=camera.ip,
                port=camera.port,
                volume=0.7,
            )
            if success:
                audio_btn.setToolTip("🔊 Audio activado")
                audio_level_widget.setVisible(True)
                mute_btn.setVisible(True)
                mute_btn.setChecked(False)
                mute_btn.setText("🔊")
                _start_timer()
            else:
                audio_btn.setChecked(False)
                audio_btn.setToolTip("Error al activar audio")
        else:
            audio_manager.stop_camera_audio(camera.id)
            audio_btn.setToolTip("Activar/Desactivar audio")
            audio_level_widget.setVisible(False)
            audio_level_widget.reset()
            mute_btn.setVisible(False)
            mute_btn.setChecked(False)
            _stop_timer()

    def _toggle_mute(checked: bool):
        from .audio_manager import audio_manager
        camera = camera_widget.camera

        audio_manager.set_muted(camera.id, checked)
        if checked:
            mute_btn.setText("🔇")
            mute_btn.setToolTip("Activar sonido (captura sigue activa)")
        else:
            mute_btn.setText("🔊")
            mute_btn.setToolTip("Silenciar audio")

    def _update_audio_level():
        from .audio_manager import audio_manager
        level = audio_manager.get_level(camera_widget.camera.id)
        audio_level_widget.set_level(level)

    def _start_timer():
        from utils.timer_manager import timer_manager
        name = f"plugin_audio.{camera_widget.camera.id}.level"
        from utils.config_loader import advanced_config
        interval = advanced_config.get("audio_meter_interval", 50)
        timer_manager.create(name, interval, _update_audio_level, start=True)
        state["timer_running"] = True

    def _stop_timer():
        from utils.timer_manager import timer_manager
        name = f"plugin_audio.{camera_widget.camera.id}.level"
        timer_manager.stop(name)
        state["timer_running"] = False

    audio_btn.clicked.connect(_toggle_audio)
    mute_btn.clicked.connect(_toggle_mute)

    # Guardar referencias en el widget para acceso externo
    camera_widget._plugin_audio = {
        "audio_btn": audio_btn,
        "mute_btn": mute_btn,
        "audio_level_widget": audio_level_widget,
        "toggle_audio": _toggle_audio,
        "stop_timer": _stop_timer,
    }

    return [audio_btn, mute_btn, audio_level_widget]


def create_local_audio_button(main_window):
    """Crea el botón '🎤 Mic PC' para la toolbar."""
    from .audio_manager import audio_manager

    btn = QPushButton("🎤 Mic PC")
    btn.setCheckable(True)
    btn.setStyleSheet("""
        QPushButton {
            background-color: #6a1b9a;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
            font-weight: bold;
            color: white;
        }
        QPushButton:hover {
            background-color: #8e24aa;
        }
        QPushButton:checked {
            background-color: #4a148c;
        }
    """)

    def _toggle_local_audio(checked: bool):
        from utils.config_loader import advanced_config
        audio_volume = advanced_config.get("audio_volume", 0.5)

        if checked:
            success = audio_manager.start_local_audio(volume=audio_volume)
            if success:
                btn.setText("🎤 Mic ON")
                main_window.status_label.setText("🎤 Micrófono del PC activado")
            else:
                btn.setChecked(False)
                QMessageBox.warning(
                    main_window, "Error",
                    "No se pudo activar el micrófono.\n\n"
                    "Verifica que pyaudio esté instalado:\n  pip install pyaudio"
                )
        else:
            audio_manager.stop_local_audio()
            btn.setText("🎤 Mic PC")
            main_window.status_label.setText("🎤 Micrófono del PC desactivado")

    btn.clicked.connect(_toggle_local_audio)
    return btn