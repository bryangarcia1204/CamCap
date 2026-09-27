"""
Implementaciones concretas de las APIs del sistema de plugins.

FASE 4: incluye capability checks.
"""
import os
import time
from typing import Optional, List, Dict, Any, Callable, Tuple
import numpy as np

from utils.logger import get_logger

logger = get_logger("PluginAPI")


def _get_current_plugin() -> str:
    """Retorna el plugin actual (contextvars)."""
    try:
        from core.plugin_api.interfaces import _current_plugin
        return _current_plugin.get()
    except Exception:
        return ""


def _check_capability(capability) -> bool:
    """
    Verifica si el plugin actual tiene la capability.
    Si no hay plugin actual → permitir (llamada desde Core).
    """
    plugin_name = _get_current_plugin()
    if not plugin_name:
        return True
    try:
        from core.extensions.capability_checker import get_capability_checker
        return get_capability_checker().check(plugin_name, capability)
    except Exception:
        return True


# ==================== SETTINGS API ====================

class SettingsAPIImpl:
    """Implementación de SettingsAPI con capability checks."""

    def __init__(self):
        self._schemas: Dict[str, Dict] = {}
        self._overrides: Dict[str, Any] = {}
        logger.debug("⚙️ [api] SettingsAPIImpl creada")

    def _get_sm(self):
        from core.settings_manager import settings_manager
        return settings_manager

    def _get_ac(self):
        from utils.config_loader import advanced_config
        return advanced_config

    def get(self, key: str, default: Any = None) -> Any:
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_READ):
            logger.warning(
                f"🚫 settings.get('{key}') denegado para "
                f"'{_get_current_plugin()}'"
            )
            return default
        if key in self._overrides:
            return self._overrides[key]
        return self._get_ac().get(key, default)

    def set(self, key: str, value: Any) -> bool:
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_WRITE):
            logger.warning(
                f"🚫 settings.set('{key}') denegado para "
                f"'{_get_current_plugin()}'"
            )
            return False
        self._overrides[key] = value
        return True

    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_READ):
            return {}
        try:
            sm = self._get_sm()
            schema = self._schemas.get(plugin_name, {})
            if not schema:
                return {}
            result = {}
            for key, spec in schema.items():
                full_key = f"plugin/{plugin_name}/{key}"
                result[key] = self._read_value_with_type(sm, full_key, spec)
            return result
        except Exception as e:
            logger.error(f"❌ Error leyendo config de '{plugin_name}': {e}")
            return {}

    def _read_value_with_type(self, sm, full_key: str, spec: Dict) -> Any:
        type_str = spec.get("type", "str").lower()
        default = spec.get("default")
        try:
            if type_str == "int":
                return sm._settings.value(full_key, default, type=int)
            elif type_str == "bool":
                return sm._settings.value(full_key, default, type=bool)
            elif type_str == "float":
                return sm._settings.value(full_key, default, type=float)
            else:
                return sm._settings.value(full_key, default, type=str)
        except Exception:
            return default

    def set_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> bool:
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_WRITE):
            return False
        try:
            sm = self._get_sm()
            for key, value in config.items():
                full_key = f"plugin/{plugin_name}/{key}"
                sm._settings.setValue(full_key, value)
            sm._settings.sync()
            return True
        except Exception as e:
            logger.error(f"❌ Error guardando config: {e}")
            return False

    def get_advanced_all(self) -> Dict[str, Any]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_READ):
            return {}
        return self._get_ac().get_all()

    def register_config_schema(self, plugin_name: str, schema: Dict[str, Any]):
        self._schemas[plugin_name] = schema

    def get_schema(self, plugin_name: str) -> Optional[Dict]:
        return self._schemas.get(plugin_name)


# ==================== CAMERAS API ====================

class CamerasAPIImpl:
    def __init__(self, camera_manager=None):
        self._camera_manager = camera_manager
        self._frame_processors: List[Tuple[int, Callable]] = []
        logger.debug("📷 [api] CamerasAPIImpl creada")

    def _get_registry(self):
        try:
            from core.extension_registry import get_extension_registry
            return get_extension_registry()
        except Exception:
            return None

    def set_camera_manager(self, manager):
        self._camera_manager = manager

    def get_all_cameras(self) -> List[Any]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return []
        if self._camera_manager is None:
            return []
        return list(self._camera_manager.cameras.values())

    def get_active_cameras(self) -> List[Any]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return []
        if self._camera_manager is None:
            return []
        return self._camera_manager.get_active_cameras()

    def get_camera(self, camera_id: int) -> Optional[Any]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return None
        if self._camera_manager is None:
            return None
        return self._camera_manager.get_camera(camera_id)

    def get_thread(self, camera_id: int) -> Optional[Any]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return None
        if self._camera_manager is None:
            return None
        return self._camera_manager.get_thread(camera_id)

    def register_frame_processor(self, callback: Callable, priority: int = 50):
        registry = self._get_registry()
        if registry is None:
            self._frame_processors.append((priority, callback))
            self._frame_processors.sort(key=lambda x: x[0])
            return

        from core.extensions.interfaces import FramePreProcessor

        class ProcessorAdapter:
            def __init__(self, cb, prio):
                self._cb = cb
                self._prio = prio
            def process(self, camera_id, frame):
                return self._cb(camera_id, frame)
            def get_priority(self):
                return self._prio

        adapter = ProcessorAdapter(callback, priority)
        registry.register(FramePreProcessor, adapter, priority=priority, owner="api.cameras")

    def unregister_frame_processor(self, callback: Callable):
        self._frame_processors = [
            (p, cb) for p, cb in self._frame_processors if cb is not callback
        ]

    def process_frame(self, camera_id: int, frame: np.ndarray) -> np.ndarray:
        current = frame
        registry = self._get_registry()
        if registry is not None:
            try:
                from core.extensions.interfaces import FramePreProcessor
                processors = registry.get(FramePreProcessor)
                processors = sorted(
                    processors,
                    key=lambda p: p.get_priority() if hasattr(p, 'get_priority') else 50,
                )
                for processor in processors:
                    try:
                        result = processor.process(camera_id, current)
                        if result is not None:
                            current = result
                    except Exception as e:
                        logger.error(f"❌ Frame processor: {e}", exc_info=True)
            except Exception:
                pass
        for _, callback in self._frame_processors:
            try:
                result = callback(camera_id, current)
                if result is not None:
                    current = result
            except Exception as e:
                logger.error(f"❌ Local processor: {e}", exc_info=True)
        return current


# ==================== FRAMES API ====================

class FramesAPIImpl:
    def __init__(self, cameras_api: 'CamerasAPIImpl' = None):
        self._cameras_api = cameras_api
        self._pre_processors: List[Tuple[int, Callable]] = []
        self._post_processors: List[Tuple[int, Callable]] = []
        logger.debug("🖼️ [api] FramesAPIImpl creada")

    def _get_registry(self):
        try:
            from core.extension_registry import get_extension_registry
            return get_extension_registry()
        except Exception:
            return None

    def register_pre_processor(self, callback: Callable, priority: int = 50):
        registry = self._get_registry()
        if registry is None:
            self._pre_processors.append((priority, callback))
            self._pre_processors.sort(key=lambda x: x[0])
            return
        from core.extensions.interfaces import FramePreProcessor
        class PreProcessorAdapter:
            def __init__(self, cb, prio):
                self._cb = cb
                self._prio = prio
            def process(self, camera_id, frame):
                return self._cb(camera_id, frame)
            def get_priority(self):
                return self._prio
        adapter = PreProcessorAdapter(callback, priority)
        registry.register(FramePreProcessor, adapter, priority=priority, owner="api.frames")

    def register_post_processor(self, callback: Callable, priority: int = 50):
        registry = self._get_registry()
        if registry is None:
            self._post_processors.append((priority, callback))
            self._post_processors.sort(key=lambda x: x[0])
            return
        from core.extensions.interfaces import FramePostProcessor
        class PostProcessorAdapter:
            def __init__(self, cb, prio):
                self._cb = cb
                self._prio = prio
            def process(self, camera_id, frame):
                return self._cb(camera_id, frame)
            def get_priority(self):
                return self._prio
        adapter = PostProcessorAdapter(callback, priority)
        registry.register(FramePostProcessor, adapter, priority=priority, owner="api.frames")

    def get_last_frame(self, camera_id: int) -> Optional[np.ndarray]:
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return None
        if self._cameras_api is None:
            return None
        camera = self._cameras_api.get_camera(camera_id)
        if camera is None or camera.current_frame is None:
            return None
        return camera.current_frame.copy()

    def apply_pre_processors(self, camera_id: int, frame: np.ndarray) -> np.ndarray:
        current = frame
        registry = self._get_registry()
        if registry is not None:
            try:
                from core.extensions.interfaces import FramePreProcessor
                processors = registry.get(FramePreProcessor)
                processors = sorted(
                    processors,
                    key=lambda p: p.get_priority() if hasattr(p, 'get_priority') else 50,
                )
                for processor in processors:
                    try:
                        result = processor.process(camera_id, current)
                        if result is not None:
                            current = result
                    except Exception as e:
                        logger.error(f"❌ Pre-processor: {e}", exc_info=True)
            except Exception:
                pass
        for _, callback in self._pre_processors:
            try:
                result = callback(camera_id, current)
                if result is not None:
                    current = result
            except Exception as e:
                logger.error(f"❌ Local pre-processor: {e}", exc_info=True)
        return current

    def apply_post_processors(self, camera_id: int, frame: np.ndarray):
        registry = self._get_registry()
        if registry is not None:
            try:
                from core.extensions.interfaces import FramePostProcessor
                processors = registry.get(FramePostProcessor)
                processors = sorted(
                    processors,
                    key=lambda p: p.get_priority() if hasattr(p, 'get_priority') else 50,
                )
                for processor in processors:
                    try:
                        processor.process(camera_id, frame)
                    except Exception as e:
                        logger.error(f"❌ Post-processor: {e}", exc_info=True)
            except Exception:
                pass
        for _, callback in self._post_processors:
            try:
                callback(camera_id, frame)
            except Exception as e:
                logger.error(f"❌ Local post-processor: {e}", exc_info=True)


# ==================== UI API ====================

class UIAPIImpl:
    def __init__(self, main_window=None):
        self._main_window = main_window
        self._toolbar_buttons: List[Any] = []
        self._menu_actions: List[Any] = []
        self._settings_tabs: List[Tuple[str, Any, str]] = []
        self._dock_widgets: List[Any] = []
        logger.debug("🖥️ [api] UIAPIImpl creada")

    def _get_registry(self):
        try:
            from core.extension_registry import get_extension_registry
            return get_extension_registry()
        except Exception:
            return None

    def set_main_window(self, main_window):
        self._main_window = main_window

    def add_toolbar_button(self, text, icon, callback, tooltip=""):
        from core.extensions.types import Capability
        if not _check_capability(Capability.UI_MODIFY):
            logger.warning(f"🚫 add_toolbar_button denegado para '{_get_current_plugin()}'")
            return None
        from PySide6.QtWidgets import QPushButton
        if self._main_window is None:
            return None
        button = QPushButton(f"{icon} {text}".strip() if icon else text)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        self._toolbar_buttons.append(button)
        registry = self._get_registry()
        if registry is not None:
            try:
                from core.extensions.interfaces import ToolbarProvider
                class ToolbarAdapter:
                    def __init__(self, widget):
                        self._widget = widget
                    def get_widgets(self):
                        return [self._widget]
                registry.register(ToolbarProvider, ToolbarAdapter(button), owner="api.ui")
            except Exception:
                pass
        toolbar = self._find_main_toolbar()
        if toolbar is not None:
            toolbar.addWidget(button)
        return button

    def _find_main_toolbar(self):
        from PySide6.QtWidgets import QToolBar
        if self._main_window is None:
            return None
        toolbar = getattr(self._main_window, 'main_toolbar', None)
        if toolbar is not None:
            return toolbar
        toolbar = self._main_window.findChild(QToolBar, "MainToolbar")
        if toolbar is not None:
            return toolbar
        toolbars = self._main_window.findChildren(QToolBar)
        return toolbars[0] if toolbars else None

    def add_menu_action(self, menu_name, text, callback, shortcut=None):
        from core.extensions.types import Capability
        if not _check_capability(Capability.UI_MODIFY):
            logger.warning(f"🚫 add_menu_action denegado para '{_get_current_plugin()}'")
            return None
        from PySide6.QtGui import QAction
        if self._main_window is None:
            return None
        action = QAction(text, self._main_window)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        self._menu_actions.append(action)
        registry = self._get_registry()
        if registry is not None:
            try:
                from core.extensions.interfaces import MenuProvider
                class MenuAdapter:
                    def __init__(self, name, action):
                        self._name = name
                        self._action = action
                    def get_menu_name(self):
                        return self._name
                    def get_actions(self):
                        return [self._action]
                registry.register(MenuProvider, MenuAdapter(menu_name, action), owner="api.ui")
            except Exception:
                pass
        menubar = self._main_window.menuBar()
        target_menu = None
        for act in menubar.actions():
            if act.text().replace("&", "") == menu_name:
                target_menu = act.menu()
                break
        if target_menu is None:
            target_menu = menubar.addMenu(menu_name)
        target_menu.addAction(action)
        return action

    def add_settings_tab(self, title, widget, icon=""):
        from core.extensions.types import Capability
        if not _check_capability(Capability.UI_MODIFY):
            logger.warning(f"🚫 add_settings_tab denegado para '{_get_current_plugin()}'")
            return
        self._settings_tabs.append((title, widget, icon))
        registry = self._get_registry()
        if registry is not None:
            try:
                from core.extensions.interfaces import ConfigTab
                class ConfigTabAdapter:
                    def __init__(self, t, w, i):
                        self._title = t
                        self._widget = w
                        self._icon = i
                        self._id = f"api_tab_{id(w)}"
                    def get_id(self):
                        return self._id
                    def get_title(self):
                        return self._title
                    def get_icon(self):
                        return self._icon
                    def get_widget(self):
                        return self._widget
                    def on_save(self):
                        if hasattr(self._widget, 'apply_changes'):
                            try:
                                return self._widget.apply_changes()
                            except Exception:
                                return False
                        return True
                    def on_load(self):
                        pass
                registry.register(ConfigTab, ConfigTabAdapter(title, widget, icon), owner="api.ui")
            except Exception:
                pass

    def get_settings_tabs(self) -> List[Tuple[str, Any, str]]:
        return list(self._settings_tabs)

    def add_dock_widget(self, title, widget, area="bottom"):
        from core.extensions.types import Capability
        if not _check_capability(Capability.UI_MODIFY):
            logger.warning(f"🚫 add_dock_widget denegado para '{_get_current_plugin()}'")
            return None
        from PySide6.QtWidgets import QDockWidget
        from PySide6.QtCore import Qt
        if self._main_window is None:
            return None
        dock = QDockWidget(title, self._main_window)
        dock.setWidget(widget)
        areas = {
            "top": Qt.TopDockWidgetArea,
            "bottom": Qt.BottomDockWidgetArea,
            "left": Qt.LeftDockWidgetArea,
            "right": Qt.RightDockWidgetArea,
        }
        self._main_window.addDockWidget(areas.get(area, Qt.BottomDockWidgetArea), dock)
        self._dock_widgets.append(dock)
        return dock

    def show_status_message(self, message, timeout_ms=3000):
        if self._main_window is None:
            return
        try:
            if hasattr(self._main_window, 'status_label'):
                self._main_window.status_label.setText(message)
        except Exception:
            pass

    def show_notification(self, title, message):
        from core.extensions.types import Capability
        if not _check_capability(Capability.NOTIFICATIONS):
            logger.warning(f"🚫 show_notification denegado para '{_get_current_plugin()}'")
            return
        try:
            from plugins.notifications.windows_notifier import windows_notifier
            windows_notifier.notify(title, message)
        except Exception as e:
            logger.debug(f"Error mostrando notificación: {e}")


# ==================== FILES API ====================

class FilesAPIImpl:
    def __init__(self, file_manager=None):
        self._file_manager = file_manager
        logger.debug("📁 [api] FilesAPIImpl creada")

    def set_file_manager(self, fm):
        self._file_manager = fm

    def save_image(self, frame, directory, filename, format="jpg", quality=85):
        from core.extensions.types import Capability
        if not _check_capability(Capability.WRITE_FILES):
            logger.warning(f"🚫 save_image denegado para '{_get_current_plugin()}'")
            return "", 0
        import cv2
        try:
            ext = f".{format}"
            if not filename.endswith(ext):
                filename += ext
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, filename)
            params = []
            if format.lower() in ('jpg', 'jpeg'):
                params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            success = cv2.imwrite(path, frame, params)
            if not success:
                return "", 0
            return path, os.path.getsize(path)
        except Exception as e:
            logger.error(f"Error guardando imagen: {e}")
            return "", 0

    def save_text(self, text: str, path: str) -> bool:
        from core.extensions.types import Capability
        if not _check_capability(Capability.WRITE_FILES):
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except Exception as e:
            logger.error(f"Error guardando texto: {e}")
            return False

    def read_text(self, path: str) -> str:
        from core.extensions.types import Capability
        if not _check_capability(Capability.READ_FILES):
            return ""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error leyendo texto: {e}")
            return ""

    def get_capture_directory(self) -> str:
        from core.extensions.types import Capability
        if not _check_capability(Capability.READ_FILES):
            return ""
        try:
            from core.settings_manager import settings_manager
            settings = settings_manager.get_capture_settings()
            return os.path.expanduser(settings.default_directory)
        except Exception:
            return os.path.expanduser("~/Pictures/CamCap")


# ==================== NOTIFICATIONS API ====================

class NotificationsAPIImpl:
    def notify(self, title, message, image_path=None) -> bool:
        from core.extensions.types import Capability
        if not _check_capability(Capability.NOTIFICATIONS):
            logger.warning(f"🚫 notify denegado para '{_get_current_plugin()}'")
            return False
        try:
            from plugins.notifications.windows_notifier import windows_notifier
            return windows_notifier.notify(title, message)
        except Exception as e:
            logger.debug(f"Error notificando: {e}")
            return False

    def notify_telegram(self, message, image_path=None) -> bool:
        from core.extensions.types import Capability
        if not _check_capability(Capability.TELEGRAM):
            logger.warning(f"🚫 notify_telegram denegado para '{_get_current_plugin()}'")
            return False
        try:
            from plugins.notifications.notification_manager import notification_manager
            if not getattr(notification_manager, 'telegram_enabled', False):
                return False
            bot = getattr(notification_manager, 'telegram_bot', None)
            if bot is None:
                return False
            if image_path:
                return bot.send_photo(image_path, message)
            else:
                return bot.send_message(message)
        except Exception as e:
            logger.debug(f"Error Telegram: {e}")
            return False


# ==================== LOGGER API ====================

class LoggerAPIImpl:
    def __init__(self, plugin_name: str):
        self._logger = get_logger(f"Plugin.{plugin_name}")

    def debug(self, msg): self._logger.debug(msg)
    def info(self, msg): self._logger.info(msg)
    def warning(self, msg): self._logger.warning(msg)
    def error(self, msg, exc_info=False):
        self._logger.error(msg, exc_info=exc_info)


# ==================== TIMERS API ====================

class TimersAPIImpl:
    def __init__(self):
        self._timers: Dict[str, Any] = {}
        logger.debug("⏱️ [api] TimersAPIImpl creada")

    def create(self, name, interval_ms, callback, single_shot=False):
        try:
            from utils.timer_manager import timer_manager
            timer_manager.create(name, interval_ms, callback, single_shot=single_shot)
            self._timers[name] = True
            return True
        except Exception as e:
            logger.error(f"Error creando timer '{name}': {e}")
            return False

    def stop(self, name):
        try:
            from utils.timer_manager import timer_manager
            timer_manager.stop(name)
            self._timers.pop(name, None)
        except Exception as e:
            logger.error(f"Error deteniendo timer '{name}': {e}")

    def destroy(self, name):
        try:
            from utils.timer_manager import timer_manager
            timer_manager.destroy(name)
            self._timers.pop(name, None)
        except Exception as e:
            logger.error(f"Error destruyendo timer '{name}': {e}")


# ==================== SERVICES API ====================

class ServicesAPIImpl:
    def __init__(self):
        from core.extensions.services import get_core_services
        self._services = get_core_services()
        logger.debug("🎯 [api] ServicesAPIImpl creada")

    def find_all_cameras(self):
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return []
        return self._services.find_all_cameras()

    def get_stream_url(self, camera):
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return None
        return self._services.get_stream_url(camera)

    def get_camera(self, camera_id):
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return None
        return self._services.get_camera(camera_id)

    def get_all_cameras(self):
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return []
        return self._services.get_all_cameras()

    def get_active_cameras(self):
        from core.extensions.types import Capability
        if not _check_capability(Capability.CAMERA_ACCESS):
            return []
        return self._services.get_active_cameras()

    def get_setting(self, key, default=None):
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_READ):
            return default
        return self._services.get_setting(key, default)

    def set_setting(self, key, value):
        from core.extensions.types import Capability
        if not _check_capability(Capability.SETTINGS_WRITE):
            return False
        return self._services.set_setting(key, value)

    def get_capture_directory(self):
        from core.extensions.types import Capability
        if not _check_capability(Capability.READ_FILES):
            return ""
        return self._services.get_capture_directory()

    def save_image(self, frame, directory, filename, format="jpg", quality=85):
        from core.extensions.types import Capability
        if not _check_capability(Capability.WRITE_FILES):
            return "", 0
        return self._services.save_image(frame, directory, filename, format, quality)

    def show_message(self, message, timeout_ms=3000):
        self._services.show_message(message, timeout_ms)

    def get_main_window(self):
        return self._services.get_main_window()

    def get_extensions(self, interface):
        return self._services.get_extensions(interface)

    def register_extension(self, interface, implementation, priority=50, owner=""):
        self._services.register_extension(interface, implementation, priority, owner)

    def is_debug(self):
        return self._services.is_debug()

    def get_app_version(self):
        return self._services.get_app_version()