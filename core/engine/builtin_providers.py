"""
Providers builtin (IP, Screen, Local) para el ExtensionRegistry.

Estos providers viven en el Core y NO dependen de plugins.
El Core los registra al arrancar, para que el sistema de extensiones
tenga funcionalidad básica desde el primer momento.
"""
from typing import Optional

from core.models import CameraDevice
from core.extensions.interfaces import CameraProvider
from core.extensions.types import CameraProtocol
from utils.logger import get_logger

logger = get_logger("BuiltinProviders")


class IPCameraProvider:
    """
    Provider para cámaras IP (HTTP MJPEG).
    
    La detección real de URL vive aquí, así los plugins pueden
    sobrescribirla sin tocar el Core.
    """

    def can_handle(self, camera: CameraDevice) -> bool:
        return not camera.is_screen and not camera.is_local

    def get_stream_url(self, camera: CameraDevice) -> Optional[str]:
        """Retorna la primera URL que funcione, o None."""
        import cv2
        from utils.config_loader import advanced_config

        base = f"http://{camera.ip}:{camera.port}"
        candidates = [
            f"{base}/video",
            f"{base}/videofeed",
            f"{base}/mjpg/video.mjpg",
            f"{base}/cam.mjpg",
            f"{base}/stream.mjpg",
        ]

        buffer_size = advanced_config.get("buffer_size", 1)

        for url in candidates:
            try:
                cap = cv2.VideoCapture(url)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
                    ret, _ = cap.read()
                    cap.release()
                    if ret:
                        logger.debug(f"📷 [ip] URL válida: {url}")
                        return url
                else:
                    cap.release()
            except Exception as e:
                logger.debug(f"📷 [ip] {url} falló: {e}")
                continue

        logger.warning(f"⚠️ [ip] Ninguna URL funcionó para {camera.ip}:{camera.port}")
        return None

    def get_protocol(self) -> CameraProtocol:
        return CameraProtocol.HTTP_MJPEG


class ScreenCameraProvider:
    """Provider para captura de pantalla."""

    def can_handle(self, camera: CameraDevice) -> bool:
        return camera.is_screen

    def get_stream_url(self, camera: CameraDevice) -> Optional[str]:
        return "screen://"

    def get_protocol(self) -> CameraProtocol:
        return CameraProtocol.SCREEN


class LocalCameraProvider:
    """Provider para cámaras locales (USB / webcam)."""

    def can_handle(self, camera: CameraDevice) -> bool:
        return camera.is_local

    def get_stream_url(self, camera: CameraDevice) -> Optional[str]:
        return f"local://{camera.camera_index}"

    def get_protocol(self) -> CameraProtocol:
        return CameraProtocol.USB


def register_builtin_providers(registry) -> int:
    """
    Registra los 3 providers builtin en el ExtensionRegistry.

    Returns:
        Número de providers registrados.
    """
    if registry is None:
        logger.error("❌ No hay registry para registrar providers builtin")
        return 0

    registry.register(
        CameraProvider, IPCameraProvider(),
        priority=50, owner="builtin",
    )
    registry.register(
        CameraProvider, ScreenCameraProvider(),
        priority=50, owner="builtin",
    )
    registry.register(
        CameraProvider, LocalCameraProvider(),
        priority=50, owner="builtin",
    )

    logger.info("📦 3 CameraProvider builtin registrados (IP, Screen, Local)")
    return 3