"""
Servicios que el Core ofrece a las extensiones.

Los plugins usan `context.services` para acceder a funcionalidad
del Core (cámaras, files, settings) SIN acoplarse a implementaciones.
"""
from typing import Optional, List, Any, Dict
from ui.main_window import MainWindow
import threading

from utils.logger import get_logger

logger = get_logger("CoreServices")


class CoreServices:
    """
    Fachada de servicios del Core.

    Expone funcionalidad de alto nivel a los plugins.
    """

    def __init__(self):
        self._camera_manager = None
        self._file_manager = None
        self._settings_manager = None
        self._main_window = None
        self._extension_registry = None
        self._lock = threading.RLock()

        logger.debug("🎯 CoreServices creada")

    # ==================== INYECCIÓN ====================

    def set_camera_manager(self, manager):
        with self._lock:
            self._camera_manager = manager

    def set_file_manager(self, fm):
        with self._lock:
            self._file_manager = fm

    def set_settings_manager(self, sm):
        with self._lock:
            self._settings_manager = sm

    def set_main_window(self, mw:MainWindow):
        with self._lock:
            self._main_window = mw

    def set_extension_registry(self, registry):
        with self._lock:
            self._extension_registry = registry

    # ==================== CÁMARAS ====================

    def find_all_cameras(self) -> List[Any]:
        """
        Busca cámaras usando TODOS los CameraDetector registrados.

        Returns:
            Lista combinada de todas las cámaras detectadas.
        """
        from .interfaces import CameraDetector

        all_cameras = []
        if self._extension_registry is None:
            return all_cameras

        detectors = self._extension_registry.get(CameraDetector)
        for detector in detectors:
            try:
                cameras = detector.detect()
                if cameras:
                    all_cameras.extend(cameras)
                    logger.debug(
                        f"📷 {detector.get_name()}: {len(cameras)} cámaras"
                    )
            except Exception as e:
                logger.error(f"❌ Detector {detector.get_name()} falló: {e}")

        return all_cameras

    def get_stream_url(self, camera) -> Optional[str]:
        """
        Obtiene la URL del stream usando TODOS los CameraProvider.

        Returns:
            URL del stream o None.
        """
        from .interfaces import CameraProvider

        if self._extension_registry is None:
            return None

        providers = self._extension_registry.get(CameraProvider)
        for provider in providers:
            try:
                if provider.can_handle(camera):
                    url = provider.get_stream_url(camera)
                    if url:
                        logger.debug(f"📷 {provider.get_protocol().value} → {url}")
                        return url
            except Exception as e:
                logger.error(f"❌ Provider falló: {e}")

        return None

    def get_camera(self, camera_id: int):
        """Obtiene una cámara por ID."""
        if self._camera_manager is None:
            return None
        return self._camera_manager.get_camera(camera_id)

    def get_all_cameras(self) -> List[Any]:
        """Retorna todas las cámaras registradas."""
        if self._camera_manager is None:
            return []
        return list(self._camera_manager.cameras.values())

    def get_active_cameras(self) -> List[Any]:
        """Retorna cámaras conectadas."""
        if self._camera_manager is None:
            return []
        return self._camera_manager.get_active_cameras()

    # ==================== SETTINGS ====================

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Lee un setting global."""
        try:
            from utils.config_loader import advanced_config
            return advanced_config.get(key, default)
        except Exception:
            return default

    def set_setting(self, key: str, value: Any) -> bool:
        """Establece un setting global."""
        try:
            from utils.config_loader import advanced_config
            return advanced_config.set(key, value)
        except Exception:
            return False

    # ==================== FILES ====================

    def get_capture_directory(self) -> str:
        """Retorna el directorio de captura por defecto."""
        try:
            from settings_manager import settings_manager
            settings = settings_manager.get_capture_settings()
            import os
            return os.path.expanduser(settings.default_directory)
        except Exception:
            import os
            return os.path.expanduser("~/Pictures/CamCap")

    def save_image(self, frame, directory: str, filename: str,
                   format: str = "jpg", quality: int = 85):
        """Guarda una imagen."""
        import cv2
        import os
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

    # ==================== UI ====================

    def get_main_window(self):
        """Retorna la MainWindow (o None)."""
        return self._main_window

    def show_message(self, message: str, timeout_ms: int = 3000):
        """Muestra mensaje en el status bar."""
        if self._main_window is None:
            return
        try:
            if hasattr(self._main_window, 'status_label'):
                self._main_window.status_label.setText(message)
        except Exception:
            pass

    # ==================== EXTENSIONES ====================

    def get_extensions(self, interface):
        """Atajo para consultar extensiones."""
        if self._extension_registry is None:
            return []
        return self._extension_registry.get(interface)

    def register_extension(self, interface, implementation,
                           priority: int = 50, owner: str = ""):
        """Registra una extensión."""
        if self._extension_registry is None:
            logger.warning("⚠️ No hay registry para registrar extensión")
            return
        self._extension_registry.register(
            interface, implementation, priority=priority, owner=owner
        )

    # ==================== UTILIDADES ====================

    def is_debug(self) -> bool:
        """Retorna True si está en modo debug."""
        try:
            from utils.config_loader import advanced_config
            return advanced_config.get("debug_mode", False)
        except Exception:
            return False

    def get_app_version(self) -> str:
        return "2.0.0"


# ==================== SINGLETON ====================

_services: Optional[CoreServices] = None
_lock = threading.Lock()


def get_core_services() -> CoreServices:
    """Obtiene el singleton de CoreServices."""
    global _services
    with _lock:
        if _services is None:
            _services = CoreServices()
    return _services


def set_core_services(services: CoreServices):
    """Reemplaza el singleton (para tests)."""
    global _services
    with _lock:
        _services = services