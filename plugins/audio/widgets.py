"""Widgets de audio inyectables via UIExtension."""
from PySide6.QtWidgets import QPushButton, QMessageBox

from utils.logger import get_logger

logger = get_logger("Plugin.AudioWidgets")


def create_audio_widgets(camera_id: int, camera, camera_widget):
    """Crea los widgets de audio para una cámara."""
    from .audio_manager import audio_manager
    from ui.audio.audio_level_widget import AudioLevelWidget

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

    # === VU meter compacto (header) ===
    audio_level_widget = AudioLevelWidget(mode="compact")
    audio_level_widget.setFixedWidth(60)
    audio_level_widget.setFixedHeight(10)
    audio_level_widget.setVisible(False)

    state = {"timer_running": False}

    def _toggle_audio(checked: bool):
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
        audio_manager.set_muted(camera.id, checked)
        if checked:
            mute_btn.setText("🔇")
            mute_btn.setToolTip("Activar sonido (captura sigue activa)")
        else:
            mute_btn.setText("🔊")
            mute_btn.setToolTip("Silenciar audio")

    def _update_audio_level():
        level = audio_manager.get_level(camera.id)
        audio_level_widget.set_level(level)

    def _start_timer():
        from utils.timer_manager import timer_manager
        from utils.config_loader import advanced_config
        name = f"plugin_audio.{camera.id}.level"
        interval = advanced_config.get("audio_meter_interval", 50)
        timer_manager.create(name, interval, _update_audio_level, start=True)
        state["timer_running"] = True

    def _stop_timer():
        from utils.timer_manager import timer_manager
        name = f"plugin_audio.{camera.id}.level"
        timer_manager.stop(name)
        state["timer_running"] = False

    audio_btn.clicked.connect(_toggle_audio)
    mute_btn.clicked.connect(_toggle_mute)

    camera_widget._plugin_audio = {
        "audio_btn": audio_btn,
        "mute_btn": mute_btn,
        "audio_level_widget": audio_level_widget,
        "toggle_audio": _toggle_audio,
        "stop_timer": _stop_timer,
    }

    return [audio_btn, mute_btn, audio_level_widget]


def create_vu_meter_big(camera_id: int, camera, camera_widget):
    """VU meter grande para el slot 'footer'."""
    from .audio_manager import audio_manager
    from ui.audio.audio_level_widget import AudioLevelWidget

    vu = AudioLevelWidget(mode="horizontal")
    vu.setMinimumHeight(14)
    vu.setMaximumHeight(20)
    vu.setVisible(False)

    # Timer para actualizar el VU grande
    def _update_big():
        level = audio_manager.get_level(camera.id)
        vu.set_level(level)

    def _on_audio_toggled():
        active = audio_manager.is_camera_audio_active(camera.id)
        vu.setVisible(active)
        if active:
            from utils.timer_manager import timer_manager
            from utils.config_loader import advanced_config
            name = f"plugin_audio.{camera.id}.vu_big"
            interval = advanced_config.get("audio_meter_interval", 50)
            timer_manager.create(name, interval, _update_big, start=True)
        else:
            from utils.timer_manager import timer_manager
            timer_manager.stop(f"plugin_audio.{camera.id}.vu_big")

    camera_widget._plugin_audio_big = {
        "vu": vu,
        "on_toggle": _on_audio_toggled,
    }
    return [vu]


def create_local_audio_button(main_window):
    """Botón '🎤 Mic PC' para la toolbar."""
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
                    "Verifica que pyaudio esté instalado:\n  pip install pyaudio",
                )
        else:
            audio_manager.stop_local_audio()
            btn.setText("🎤 Mic PC")
            main_window.status_label.setText("🎤 Micrófono del PC desactivado")

    btn.clicked.connect(_toggle_local_audio)
    return btn


class AudioUIExtension:
    """UIExtension que inyecta widgets de audio."""

    def __init__(self, target: str, slot: str, priority: int = 110):
        self._target = target
        self._slot = slot
        self._priority = priority

    def get_id(self) -> str:
        return f"audio.{self._target}.{self._slot}"

    def get_target(self) -> str:
        return self._target

    def get_slot(self) -> str:
        return self._slot

    def get_priority(self) -> int:
        return self._priority

    def get_widgets(self, context: dict):
        if self._target == "camera_widget":
            camera = context.get("camera")
            camera_widget = context.get("widget")
            camera_id = context.get("camera_id")
            if camera is None or camera_widget is None:
                return []
            # Solo cámaras IP soportan audio (screen/local no)
            if camera.is_screen or camera.is_local:
                return []
            if self._slot == "header":
                return create_audio_widgets(camera_id, camera, camera_widget)
            elif self._slot == "footer":
                return create_vu_meter_big(camera_id, camera, camera_widget)
            return []
        elif self._target == "main_toolbar":
            main_window = context.get("main_window")
            if main_window is None:
                return []
            return [create_local_audio_button(main_window)]
        return []