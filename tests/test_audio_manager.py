"""Tests para audio/audio_manager.py

FIX v2:
- Tests de mute (feature nueva)
- Tests de sounddevice (fix de sample rate)
- No depende de pygame
"""
import pytest
import time
import numpy as np
from unittest.mock import MagicMock, patch

from plugins.audio.audio_manager import (
    AudioManager,
    CameraAudioStream,
    LocalAudioStream,
    AudioStreamBase,
    AudioSource,
)


class TestAudioSource:
    def test_enum_values(self):
        assert AudioSource.CAMERA_IP.value == "camera_ip"
        assert AudioSource.LOCAL.value == "local"


class TestAudioStreamBase:
    def test_init_defaults(self):
        # Clase base no se instancia directamente, usamos CameraAudioStream
        stream = CameraAudioStream(ip="1.1.1.1", port=80)

        assert stream.sample_rate == 44100
        assert stream.channels == 1
        assert 0.0 <= stream.volume <= 1.0
        assert stream.is_running() is False

    def test_mute_initial_false(self):
        """Un stream nuevo NO debe estar muteado"""
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        assert stream.is_muted() is False

    def test_set_muted_true(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        stream.set_muted(True)
        assert stream.is_muted() is True

    def test_set_muted_false(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        stream.set_muted(True)
        stream.set_muted(False)
        assert stream.is_muted() is False

    def test_mute_preserves_running_state(self):
        """Mute NO debe detener la captura"""
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        stream._running = True

        stream.set_muted(True)

        assert stream.is_running() is True, "Mute detuvo la captura (BUG)"
        assert stream.is_muted() is True

    def test_set_volume_clamps_high(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        stream.set_volume(1.5)
        assert stream.volume == 1.0

    def test_set_volume_clamps_low(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        stream.set_volume(-0.5)
        assert stream.volume == 0.0

    def test_set_volume_valid(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        stream.set_volume(0.5)
        assert 0.49 <= stream.volume <= 0.51


class TestCameraAudioStream:
    def test_init_attributes(self):
        stream = CameraAudioStream(ip="192.168.1.1", port=4747)
        assert stream.ip == "192.168.1.1"
        assert stream.port == 4747
        assert stream.is_running() is False

    def test_get_level_initial_zero(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        assert stream.get_level() == 0.0

    def test_update_level_from_silent_pcm(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        silent_pcm = b'\x00\x00' * 1000
        stream._update_level_from_pcm(silent_pcm)
        assert stream.get_level() < 0.01

    def test_update_level_from_loud_pcm(self):
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        loud = np.full(1000, 20000, dtype=np.int16).tobytes()
        stream._update_level_from_pcm(loud)
        assert stream.get_level() > 0.5

    def test_update_level_medium_pcm(self):
        """PCM de amplitud media debe dar nivel intermedio"""
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        medium = np.full(1000, 4000, dtype=np.int16).tobytes()
        stream._update_level_from_pcm(medium)
        assert 0.2 < stream.get_level() < 0.8

    def test_level_callback_called(self):
        """Si hay callback, debe llamarse con el nivel"""
        stream = CameraAudioStream(ip="1.1.1.1", port=80)
        received = []
        stream.level_callback = lambda lvl: received.append(lvl)

        loud = np.full(1000, 20000, dtype=np.int16).tobytes()
        stream._update_level_from_pcm(loud)

        assert len(received) == 1
        assert received[0] > 0.5


class TestLocalAudioStream:
    def test_init(self):
        stream = LocalAudioStream()
        assert stream.is_running() is False
        assert stream.sample_rate == 44100

    def test_mute_works(self):
        """LocalAudioStream también debe soportar mute"""
        stream = LocalAudioStream()
        stream.set_muted(True)
        assert stream.is_muted() is True

    def test_update_level_from_pcm(self):
        stream = LocalAudioStream()
        loud = np.full(1000, 20000, dtype=np.int16).tobytes()
        stream._update_level_from_pcm(loud)
        assert stream.get_level() > 0.5


class TestAudioManagerSingleton:
    def test_singleton(self):
        m1 = AudioManager()
        m2 = AudioManager()
        assert m1 is m2

    def test_has_streams_dict(self):
        manager = AudioManager()
        assert hasattr(manager, "streams")
        assert isinstance(manager.streams, dict)


class TestAudioManagerQueries:
    def test_get_level_no_stream(self):
        manager = AudioManager()
        assert manager.get_level(999) == 0.0

    def test_is_camera_audio_active_no_stream(self):
        manager = AudioManager()
        assert manager.is_camera_audio_active(999) is False

    def test_is_local_audio_active_no_stream(self):
        manager = AudioManager()
        # Puede haber estado previo, no es 100% determinista
        result = manager.is_local_audio_active()
        assert isinstance(result, bool)

    def test_is_muted_no_stream(self):
        manager = AudioManager()
        assert manager.is_muted(999) is False


class TestAudioManagerStop:
    def test_stop_nonexistent_camera(self):
        manager = AudioManager()
        # No debe fallar
        manager.stop_camera_audio(999)

    def test_stop_local_no_stream(self):
        manager = AudioManager()
        # No debe fallar
        manager.stop_local_audio()

    def test_stop_all_no_streams(self):
        manager = AudioManager()
        manager.stop_all()
        assert len(manager.streams) == 0


class TestAudioManagerMute:
    def test_set_muted_no_stream(self):
        """Sin stream, set_muted no debe fallar"""
        manager = AudioManager()
        manager.set_muted(999, True)

    def test_toggle_mute_no_stream(self):
        manager = AudioManager()
        assert manager.toggle_mute(999) is False

    def test_set_volume_no_stream(self):
        manager = AudioManager()
        manager.set_volume(999, 0.5)  # No debe fallar


class TestAudioManagerWithRealStream:
    """Tests que usan streams reales (sin tocar hardware)"""

    def test_start_camera_audio_invalid_ip(self):
        """IP inválida debe fallar sin crashear"""
        manager = AudioManager()
        manager.stop_camera_audio(123)

        # IP inválida → start() debe fallar, pero no crashear
        result = manager.start_camera_audio(
            camera_id=123,
            ip="999.999.999.999",
            port=99999,
            volume=0.5
        )
        # Puede ser True o False, lo importante: no crashea
        assert isinstance(result, bool)

        # Cleanup
        manager.stop_camera_audio(123)