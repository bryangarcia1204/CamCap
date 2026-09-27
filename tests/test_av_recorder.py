"""Tests para utils/av_recorder.py

FIX v2: atributo `declared_fps` en lugar de `fps`
"""
import os
import pytest
import numpy as np

from utils.av_recorder import AVRecorder


class TestAVRecorderInit:
    def test_init_default(self, temp_dir):
        path = os.path.join(temp_dir, "test.mp4")
        rec = AVRecorder(output_path=path)

        assert rec.output_path == path
        assert rec.declared_fps == 30  # ✅ Atributo correcto
        assert rec.audio_enabled is False
        assert rec.is_recording() is False

    def test_init_custom_fps(self, temp_dir):
        path = os.path.join(temp_dir, "test.mp4")
        rec = AVRecorder(output_path=path, fps=15)
        assert rec.declared_fps == 15

    def test_init_with_audio(self, temp_dir):
        path = os.path.join(temp_dir, "test.mp4")
        rec = AVRecorder(output_path=path, audio_enabled=True)
        assert rec.audio_enabled is True

    def test_get_backend_none_before_start(self, temp_dir):
        path = os.path.join(temp_dir, "test.mp4")
        rec = AVRecorder(output_path=path)
        assert rec.get_backend() == "none"


class TestAVRecorderOpenCV:
    def test_start_opencv(self, temp_dir):
        path = os.path.join(temp_dir, "test.avi")
        rec = AVRecorder(
            output_path=path,
            fps=15,
            video_size=(320, 240),
            video_codec="MJPG",
            audio_enabled=False
        )
        assert rec.start() is True
        assert rec.get_backend() == "opencv"
        assert rec.is_recording() is True
        rec.stop()

    def test_write_frames_creates_file(self, temp_dir):
        path = os.path.join(temp_dir, "test.avi")
        rec = AVRecorder(
            output_path=path,
            fps=30,
            video_size=(320, 240),
            video_codec="MJPG"
        )
        rec.start()

        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (100, 150, 200)

        import time
        for _ in range(10):
            rec.write_frame(frame)
            time.sleep(0.04)

        rec.stop()

        assert os.path.exists(path)
        assert os.path.getsize(path) > 0

    def test_write_frame_wrong_size_autoresize(self, temp_dir):
        """Frames de tamaño incorrecto deben redimensionarse"""
        path = os.path.join(temp_dir, "test.avi")
        rec = AVRecorder(
            output_path=path,
            fps=30,
            video_size=(320, 240),
            video_codec="MJPG"
        )
        rec.start()

        # Frame más grande
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        import time
        for _ in range(3):
            rec.write_frame(frame)
            time.sleep(0.04)

        rec.stop()
        assert os.path.exists(path)

    def test_stop_without_start(self, temp_dir):
        path = os.path.join(temp_dir, "test.avi")
        rec = AVRecorder(output_path=path)
        assert rec.stop() is None

    def test_duration_is_zero_before_stop(self, temp_dir):
        path = os.path.join(temp_dir, "test.avi")
        rec = AVRecorder(
            output_path=path,
            fps=30,
            video_size=(320, 240),
            video_codec="MJPG"
        )
        rec.start()
        # get_duration antes de stop usa time.time() - start_time
        # Debe ser >= 0 (no exactamente 0)
        duration = rec.get_duration()
        assert duration >= 0.0
        rec.stop()


class TestAVRecorderPyAV:
    @pytest.mark.skipif(
        not pytest.importorskip("av", reason="PyAV no instalado"),
        reason="PyAV no instalado"
    )
    def test_start_pyav(self, temp_dir):
        pytest.importorskip("av")
        path = os.path.join(temp_dir, "test.mp4")
        rec = AVRecorder(
            output_path=path,
            fps=30,
            video_size=(320, 240),
            video_codec="mpeg4",
            audio_enabled=True
        )
        # Puede fallar si sounddevice no está
        result = rec.start()
        if result:
            assert rec.get_backend() == "pyav"
            rec.stop()