"""Tests para widgets de UI

FIX v2: mocks de diálogos + verificación de propiedades
"""
import pytest
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt

from core.models import CameraDevice, CameraStatus


@pytest.mark.gui
class TestCameraWidget:
    def test_create_widget(self, qapp, camera_ip):
        from ui.camera_widget import CameraWidget
        widget = CameraWidget(camera_ip)

        assert widget.camera is camera_ip
        assert widget.is_recording is False
        assert widget.is_paused is False
        assert widget._display_timer_running is False
        assert widget._empty_cycles == 0
        widget.cleanup()

    def test_widget_has_pixmap_pool(self, qapp, camera_ip):
        from ui.camera_widget import CameraWidget
        widget = CameraWidget(camera_ip)
        assert widget._pixmap_pool is not None
        widget.cleanup()

    def test_set_status(self, qapp, camera_ip):
        from ui.camera_widget import CameraWidget
        widget = CameraWidget(camera_ip)

        widget.set_status(CameraStatus.CONNECTED)
        assert "Conectado" in widget.status_label.text()

        widget.set_status(CameraStatus.ERROR)
        assert "Error" in widget.status_label.text()

        widget.cleanup()

    def test_toggle_recording_no_dialog(self, qapp, camera_ip, monkeypatch):
        """Toggle recording sin que aparezca diálogo (mock QMessageBox)"""
        # Mockear QMessageBox.question para que NO bloquee
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *args, **kwargs: QMessageBox.No)
        )

        from ui.camera_widget import CameraWidget
        widget = CameraWidget(camera_ip)

        captured = []
        widget.recording_toggled.connect(
            lambda cid, state: captured.append(state)
        )

        widget._toggle_recording()
        assert widget.is_recording is True
        assert captured == [True]

        widget._toggle_recording()
        assert widget.is_recording is False
        assert captured == [True, False]

        widget.cleanup()

    def test_pause_stops_display_timer(self, qapp, camera_ip):
        """Verifica que pausar detiene el timer Y que el timer estaba corriendo"""
        from ui.camera_widget import CameraWidget
        widget = CameraWidget(camera_ip)

        # Simular un frame para arrancar el timer
        qimage = QImage(320, 240, QImage.Format_RGB888)
        qimage.fill(0xFF0000)
        widget.update_frame(qimage)

        # Ahora el timer debe estar corriendo
        assert widget._display_timer_running is True

        # Pausar
        widget._toggle_pause()
        assert widget.is_paused is True
        assert widget._display_timer_running is False

        # Reanudar
        widget._toggle_pause()
        assert widget.is_paused is False

        widget.cleanup()

    def test_cleanup_no_crash(self, qapp, camera_ip):
        from ui.camera_widget import CameraWidget
        widget = CameraWidget(camera_ip)
        widget.cleanup()
        # No debe lanzar excepciones


@pytest.mark.gui
class TestAudioLevelWidget:
    def test_create_horizontal(self, qapp):
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget(mode="horizontal")
        assert widget.mode == "horizontal"

    def test_create_compact(self, qapp):
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget(mode="compact")
        assert widget.mode == "compact"

    def test_set_level_starts_at_zero(self, qapp):
        """Un widget nuevo debe tener level=0"""
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget()
        assert widget._level == 0.0

    def test_set_level_rises(self, qapp):
        """Tras varias llamadas, el nivel debe subir"""
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget()

        initial = widget._level
        for _ in range(10):
            widget.set_level(0.8)

        assert widget._level > initial
        assert 0.0 < widget._level <= 1.0

    def test_set_level_converges_to_target(self, qapp):
        """Tras suficientes llamadas, debe converger al target"""
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget()

        for _ in range(50):
            widget.set_level(0.5)

        # Con suavizado, debe estar cerca de 0.5
        assert 0.4 <= widget._level <= 0.6

    def test_reset(self, qapp):
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget()

        for _ in range(10):
            widget.set_level(0.8)

        widget.reset()
        assert widget._level == 0.0
        assert widget._peak == 0.0

    def test_cleanup_no_crash(self, qapp):
        from ui.audio_level_widget import AudioLevelWidget
        widget = AudioLevelWidget()
        widget.cleanup()