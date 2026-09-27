"""Tests para core/plugin_api/api_impl.py"""
import pytest
import numpy as np
from core.plugin_api.api_impl import (
    SettingsAPIImpl,
    CamerasAPIImpl,
    FramesAPIImpl,
    FilesAPIImpl,
    LoggerAPIImpl,
    TimersAPIImpl,
)


class TestSettingsAPI:
    def test_create(self):
        api = SettingsAPIImpl()
        assert api is not None

    def test_get_returns_default(self):
        api = SettingsAPIImpl()
        value = api.get("nonexistent_key", "default_value")
        assert value == "default_value"

    def test_register_schema(self):
        api = SettingsAPIImpl()
        schema = {
            "threshold": {"type": "int", "default": 50},
            "enabled": {"type": "bool", "default": True},
        }
        api.register_config_schema("test_plugin", schema)
        assert api._schemas["test_plugin"] == schema


class TestCamerasAPI:
    def test_create(self):
        api = CamerasAPIImpl()
        assert api is not None

    def test_get_all_no_manager(self):
        api = CamerasAPIImpl()
        assert api.get_all_cameras() == []

    def test_register_frame_processor(self):
        api = CamerasAPIImpl()
        called = []

        def processor(camera_id, frame):
            called.append(camera_id)
            return frame

        api.register_frame_processor(processor)
        api.process_frame(0, np.zeros((10, 10, 3), dtype=np.uint8))

        assert called == [0]

    def test_frame_processor_priority(self):
        api = CamerasAPIImpl()
        order = []

        api.register_frame_processor(
            lambda cid, f: order.append("low") or f,
            priority=100
        )
        api.register_frame_processor(
            lambda cid, f: order.append("high") or f,
            priority=10
        )

        api.process_frame(0, np.zeros((10, 10, 3), dtype=np.uint8))
        assert order == ["high", "low"]

    def test_frame_processor_error_isolated(self):
        api = CamerasAPIImpl()

        def bad_processor(camera_id, frame):
            raise ValueError("Test")

        def good_processor(camera_id, frame):
            return frame

        api.register_frame_processor(bad_processor)
        api.register_frame_processor(good_processor)

        # No debe crashear
        result = api.process_frame(0, np.zeros((10, 10, 3), dtype=np.uint8))
        assert result is not None


class TestFramesAPI:
    def test_create(self):
        api = FramesAPIImpl()
        assert api is not None

    def test_pre_processor_chain(self):
        api = FramesAPIImpl()

        api.register_pre_processor(lambda cid, f: f + 10)
        api.register_pre_processor(lambda cid, f: f * 2)

        frame = np.array([[1]], dtype=np.uint8)
        result = api.apply_pre_processors(0, frame)

        assert result[0][0] == (1 + 10) * 2


class TestFilesAPI:
    def test_create(self):
        api = FilesAPIImpl()
        assert api is not None

    def test_save_and_read_text(self, temp_dir):
        api = FilesAPIImpl()
        path = f"{temp_dir}/test.txt"

        assert api.save_text("Hello World", path)
        assert api.read_text(path) == "Hello World"


class TestLoggerAPI:
    def test_create(self):
        api = LoggerAPIImpl("test_plugin")
        assert api is not None

    def test_methods_dont_crash(self):
        api = LoggerAPIImpl("test")
        api.debug("test")
        api.info("test")
        api.warning("test")
        api.error("test")


class TestTimersAPI:
    def test_create(self):
        api = TimersAPIImpl()
        assert api is not None