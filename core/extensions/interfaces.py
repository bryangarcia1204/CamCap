"""
Interfaces (Protocols) para el sistema de extensiones.

Cualquier clase puede implementar estas interfaces.
El Core las descubre vía ExtensionRegistry.

NO heredes de estas clases. Son Protocolos (structural typing).
"""
from typing import Protocol, Optional, List, Dict, Any, Callable, runtime_checkable

import numpy as np
from PySide6.QtWidgets import QWidget, QDialog
from PySide6.QtGui import QIcon, QAction

from .types import (
    CameraProtocol,
    FrameFormat,
    NotificationLevel,
    ThemeMode,
    PluginInfo,
    Capability,
)


# ============================================================
# CÁMARAS
# ============================================================

@runtime_checkable
class CameraProvider(Protocol):
    """
    Provee URLs de stream para cámaras.

    Uso: un plugin puede soportar cámaras con protocolos custom
    (por ejemplo, cámaras por cable USB, cámaras industriales, etc.)
    """

    def can_handle(self, camera) -> bool:
        """Retorna True si este provider puede manejar la cámara."""
        ...

    def get_stream_url(self, camera) -> Optional[str]:
        """Retorna la URL del stream o None si no aplica."""
        ...

    def get_protocol(self) -> CameraProtocol:
        """Retorna el protocolo que maneja este provider."""
        ...


@runtime_checkable
class CameraDetector(Protocol):
    """
    Detecta cámaras disponibles en el sistema.

    Uso: un plugin puede añadir detección de cámaras por cable,
    cámaras en red local, etc.
    """

    def get_name(self) -> str:
        """Nombre del detector (para mostrar en UI)."""
        ...

    def detect(self) -> List[Any]:
        """Retorna lista de cámaras detectadas (CameraDevice)."""
        ...


@runtime_checkable
class CameraLifecycleListener(Protocol):
    """
    Escucha eventos del ciclo de vida de cámaras.
    """

    def on_camera_added(self, camera):
        """Cámara añadida."""
        ...

    def on_camera_removed(self, camera_id: int):
        """Cámara eliminada."""
        ...

    def on_camera_connected(self, camera):
        """Cámara conectada."""
        ...

    def on_camera_disconnected(self, camera):
        """Cámara desconectada."""
        ...

    def on_camera_error(self, camera, error: str):
        """Error en cámara."""
        ...


# ============================================================
# FRAMES
# ============================================================

@runtime_checkable
class FramePreProcessor(Protocol):
    """
    Procesa un frame ANTES de mostrarlo.

    Puede modificar el frame. Se ejecuta en orden de prioridad.
    """

    def process(self, camera_id: int, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Procesa el frame.

        Returns:
            Frame modificado, o None para no modificar.
        """
        ...

    def get_priority(self) -> int:
        """Prioridad (menor = primero)."""
        ...


@runtime_checkable
class FramePostProcessor(Protocol):
    """
    Procesa un frame DESPUÉS de mostrarlo.

    NO puede modificar el frame visualmente, pero puede analizarlo.
    """

    def process(self, camera_id: int, frame: np.ndarray):
        """Procesa el frame (no retorna nada)."""
        ...

    def get_priority(self) -> int:
        ...


@runtime_checkable
class FrameAnalyzer(Protocol):
    """
    Analiza frames para detecciones (movimiento, caras, etc.).

    Se ejecuta en background thread.
    """

    def analyze(self, camera_id: int, frame: np.ndarray) -> Dict[str, Any]:
        """
        Analiza el frame.

        Returns:
            Dict con resultados (ej. {"motion": True, "rects": [...]})
        """
        ...

    def should_run(self, camera_id: int) -> bool:
        """Retorna True si debe analizar este frame."""
        ...

    def get_frame_skip(self) -> int:
        """Cuántos frames saltar entre análisis."""
        ...


# ============================================================
# UI
# ============================================================

@runtime_checkable
class ToolbarProvider(Protocol):
    """Provee widgets para la toolbar principal."""

    def get_widgets(self) -> List[QWidget]:
        """Retorna widgets a añadir."""
        ...


@runtime_checkable
class MenuProvider(Protocol):
    """Provee menús."""

    def get_menu_name(self) -> str:
        """Nombre del menú."""
        ...

    def get_actions(self) -> List[QAction]:
        """Acciones del menú."""
        ...


@runtime_checkable
class ConfigTab(Protocol):
    """Una pestaña completa de configuración."""

    def get_id(self) -> str:
        """ID único de la pestaña."""
        ...

    def get_title(self) -> str:
        """Título a mostrar."""
        ...

    def get_icon(self) -> str:
        """Emoji/icono (opcional)."""
        ...

    def get_widget(self) -> QWidget:
        """Widget de la pestaña."""
        ...

    def on_save(self) -> bool:
        """Guardar cambios. Retorna True si OK."""
        ...

    def on_load(self):
        """Cargar valores iniciales."""
        ...


@runtime_checkable
class ConfigSection(Protocol):
    """
    Sección de configuración que se añade a una tab existente.

    Uso: un plugin puede añadir campos a la tab "Captura" sin
    reemplazarla.
    """

    def get_target_tab_id(self) -> str:
        """ID de la tab donde añadirse (ej. "capture", "cameras")."""
        ...

    def get_title(self) -> str:
        """Título de la sección."""
        ...

    def get_widget(self) -> QWidget:
        """Widget de la sección."""
        ...

    def on_save(self) -> bool:
        """Guardar cambios."""
        ...

    def get_priority(self) -> int:
        """Orden dentro de la tab."""
        ...


@runtime_checkable
class ConfigWidget(Protocol):
    """
    Widget de configuración personalizado (slider, color picker, etc.)

    Uso: un plugin puede registrar tipos de config nuevos.
    """

    def get_config_key(self) -> str:
        """Key en la config."""
        ...

    def get_widget(self) -> QWidget:
        """Widget."""
        ...

    def get_value(self) -> Any:
        """Valor actual."""
        ...

    def set_value(self, value: Any):
        """Establecer valor."""
        ...


@runtime_checkable
class VideoOverlay(Protocol):
    """
    Overlay sobre el video de una cámara.

    Uso: mostrar información adicional sobre el video
    (FPS, detecciones, marcas, etc.)
    """

    def should_show(self, camera_id: int) -> bool:
        """Retorna True si debe mostrarse para esta cámara."""
        ...

    def get_overlay_widget(self, camera_id: int) -> Optional[QWidget]:
        """Widget a superponer, o None."""
        ...

    def get_priority(self) -> int:
        """Orden (mayor = más arriba)."""
        ...


@runtime_checkable
class StatusWidget(Protocol):
    """Widget para la status bar."""

    def get_widget(self) -> QWidget:
        """Widget a añadir a la status bar."""
        ...


@runtime_checkable
class DialogProvider(Protocol):
    """Provee diálogos personalizados."""

    def get_dialog_id(self) -> str:
        """ID único del diálogo."""
        ...

    def get_dialog(self, parent=None) -> Optional[QDialog]:
        """Retorna instancia del diálogo."""
        ...


# ============================================================
# COMPORTAMIENTO
# ============================================================

@runtime_checkable
class KeyboardInterceptor(Protocol):
    """Intercepta teclas a nivel global."""

    def intercept(self, key: int, modifiers: int) -> bool:
        """
        Intercepta una tecla.

        Returns:
            True si la consumió (no se propaga).
        """
        ...


@runtime_checkable
class MouseInterceptor(Protocol):
    """Intercepta eventos de ratón."""

    def intercept_click(self, widget, x: int, y: int, button: int) -> bool:
        """Retorna True si consumió el evento."""
        ...


@runtime_checkable
class AppLifecycleHook(Protocol):
    """Hook en el ciclo de vida de la app."""

    def on_app_start(self, app):
        """App iniciada."""
        ...

    def on_app_close(self):
        """App cerrándose."""
        ...


@runtime_checkable
class StartupHook(Protocol):
    """Se ejecuta al arrancar la app (después de MainWindow)."""

    def on_startup(self, main_window):
        """Se llama al arrancar."""
        ...

    def get_priority(self) -> int:
        """Orden de ejecución."""
        ...


@runtime_checkable
class ShutdownHook(Protocol):
    """Se ejecuta al cerrar la app."""

    def on_shutdown(self):
        """Se llama al cerrar."""
        ...

    def get_priority(self) -> int:
        """Orden (mayor = primero, LIFO)."""
        ...


# ============================================================
# TEMAS
# ============================================================

@runtime_checkable
class ThemeProvider(Protocol):
    """Provee un tema (stylesheet + paleta)."""

    def get_id(self) -> str:
        """ID único del tema."""
        ...

    def get_name(self) -> str:
        """Nombre a mostrar."""
        ...

    def get_mode(self) -> ThemeMode:
        """Modo (light/dark/auto)."""
        ...

    def get_stylesheet(self) -> str:
        """QSS a aplicar."""
        ...

    def get_palette(self) -> Optional[Any]:
        """QPalette a aplicar (opcional)."""
        ...


@runtime_checkable
class IconProvider(Protocol):
    """Provee iconos."""

    def get_icon(self, name: str) -> Optional[QIcon]:
        """Retorna icono por nombre."""
        ...

    def list_icons(self) -> List[str]:
        """Lista iconos disponibles."""
        ...


# ============================================================
# DATOS
# ============================================================

@runtime_checkable
class FileHandler(Protocol):
    """Maneja archivos con extensiones específicas."""

    def get_extensions(self) -> List[str]:
        """Extensiones soportadas (ej. [".myext"])."""
        ...

    def open(self, path: str) -> Any:
        """Abre un archivo."""
        ...

    def save(self, path: str, data: Any) -> bool:
        """Guarda un archivo."""
        ...

    def preview_widget(self, path: str) -> Optional[QWidget]:
        """Widget de preview (opcional)."""
        ...


@runtime_checkable
class StorageProvider(Protocol):
    """Provee almacenamiento adicional (cloud, base de datos, etc.)."""

    def get_id(self) -> str:
        """ID único."""
        ...

    def list_files(self, prefix: str = "") -> List[str]:
        """Lista archivos."""
        ...

    def download(self, remote_path: str, local_path: str) -> bool:
        """Descarga un archivo."""
        ...

    def upload(self, local_path: str, remote_path: str) -> bool:
        """Sube un archivo."""
        ...


@runtime_checkable
class ImportProvider(Protocol):
    """Importa datos de fuentes externas."""

    def get_name(self) -> str:
        """Nombre del provider."""
        ...

    def can_import(self, source: str) -> bool:
        """Retorna True si puede importar de esta fuente."""
        ...

    def import_data(self, source: str) -> Any:
        """Importa datos."""
        ...


@runtime_checkable
class ExportProvider(Protocol):
    """Exporta datos a formatos externos."""

    def get_name(self) -> str:
        """Nombre del provider."""
        ...

    def get_extension(self) -> str:
        """Extensión del formato (ej. ".pdf")."""
        ...

    def export_data(self, data: Any, path: str) -> bool:
        """Exporta datos."""
        ...


# ============================================================
# PLUGINS
# ============================================================

@runtime_checkable
class PluginWrapper(Protocol):
    """
    Envuelve a otros plugins para modificar su comportamiento.

    Uso: añadir logging, métricas, validaciones, etc.
    """

    def wraps_plugin(self, plugin_name: str) -> bool:
        """Retorna True si envuelve a este plugin."""
        ...

    def before_call(self, plugin_name: str, method: str, args: tuple, kwargs: dict):
        """Se ejecuta antes de llamar a un método del plugin."""
        ...

    def after_call(self, plugin_name: str, method: str, result: Any) -> Any:
        """Se ejecuta después. Puede modificar el resultado."""
        ...

    def on_error(self, plugin_name: str, method: str, error: Exception):
        """Se ejecuta si el método lanza excepción."""
        ...


@runtime_checkable
class PluginLifecycleHook(Protocol):
    """Hook en el ciclo de vida de plugins."""

    def on_plugin_loaded(self, plugin_name: str):
        """Plugin cargado."""
        ...

    def on_plugin_enabled(self, plugin_name: str):
        """Plugin activado."""
        ...

    def on_plugin_disabled(self, plugin_name: str):
        """Plugin desactivado."""
        ...

    def on_plugin_unloaded(self, plugin_name: str):
        """Plugin descargado."""
        ...


@runtime_checkable
class PluginValidator(Protocol):
    """
    Valida plugins antes de cargarlos.

    Uso: un plugin puede validar otros plugins (seguridad, compatibilidad).
    """

    def validate(self, plugin_path: str, metadata: Dict[str, Any]) -> bool:
        """Retorna True si el plugin es válido."""
        ...

    def get_rejection_reason(self) -> str:
        """Razón de rechazo (si validate retornó False)."""
        ...


# ============================================================
# UTILIDADES
# ============================================================

@runtime_checkable
class Logger(Protocol):
    """Logger personalizado."""

    def debug(self, msg: str): ...
    def info(self, msg: str): ...
    def warning(self, msg: str): ...
    def error(self, msg: str, exc_info: bool = False): ...


@runtime_checkable
class NotificationProvider(Protocol):
    """Provee notificaciones."""

    def get_id(self) -> str:
        """ID único."""
        ...

    def notify(self, title: str, message: str, level: NotificationLevel,
               image_path: Optional[str] = None) -> bool:
        """Envía notificación."""
        ...

    def is_available(self) -> bool:
        """Retorna True si está disponible."""
        ...


@runtime_checkable
class TaskScheduler(Protocol):
    """Programa tareas en background."""

    def schedule(self, name: str, interval_ms: int, callback: Callable):
        """Programa una tarea periódica."""
        ...

    def cancel(self, name: str):
        """Cancela una tarea."""
        ...

# ============================================================
# PROVIDERS DE CLASES (migración de módulos a plugins)
# ============================================================

@runtime_checkable
class MotionDetectorProvider(Protocol):
    """Provee la clase MotionDetector desde un plugin."""
    def create_detector(self, sensitivity=None, min_area=None, cooldown_seconds=None) -> Any: ...
    def get_class(self): ...


@runtime_checkable
class FaceRecognizerProvider(Protocol):
    """Provee la clase FaceRecognizer desde un plugin."""
    def create_recognizer(self, known_faces_dir="known_faces", tolerance=None, model=None) -> Any: ...
    def get_class(self): ...


@runtime_checkable
class ImageEnhancerProvider(Protocol):
    """Provee la clase ImageEnhancer desde un plugin."""
    def get_class(self): ...
    def get_dialog_class(self): ...


@runtime_checkable
class DocumentScannerProvider(Protocol):
    """Provee la clase ScanManager desde un plugin."""
    def create_scanner(self, tesseract_path=None) -> Any: ...
    def get_class(self): ...


@runtime_checkable
class AudioManagerProvider(Protocol):
    """Provee el singleton AudioManager desde un plugin."""
    def get_manager(self): ...
    def stop_all(self): ...


@runtime_checkable
class NotificationsProvider(Protocol):
    """Provee el singleton NotificationManager desde un plugin."""
    def get_manager(self): ...
    def notify_motion(self, camera_name: str, image_path=None): ...
    def notify_face_unknown(self, camera_name: str, image_path=None): ...
    def notify_face_known(self, camera_name: str, person_name: str): ...
    def notify_custom(self, title: str, message: str): ...

# ============================================================
# EXTENSIONES DE WIDGETS/DÍALOGOS (agregar UI a componentes Core)
# ============================================================

@runtime_checkable
class CameraWidgetExtension(Protocol):
    """
    Extiende el CameraWidget de una cámara específica.

    Uso: un plugin puede añadir botones, indicadores o controles
    al header de cada cámara SIN modificar el Core.

    Ejemplo:
        - Plugin audio: añade botón 🔊, mute 🔇, VU meter
        - Plugin motion: añade botón flash 🔦, auto-flash ⚡
        - Plugin recording: añade botón de marcadores
    """

    def get_widgets(self, camera_id: int, camera_widget) -> List[QWidget]:
        """
        Retorna widgets a añadir al CameraWidget.

        Args:
            camera_id: ID de la cámara
            camera_widget: instancia del CameraWidget (para conectar señales)

        Returns:
            Lista de widgets (se añaden al header, en orden de prioridad)
        """
        ...

    def get_priority(self) -> int:
        """Prioridad (menor = más a la izquierda)."""
        ...


@runtime_checkable
class DialogExtension(Protocol):
    """
    Extiende un diálogo Core específico (ImagePreview, etc.).

    Uso: un plugin puede añadir botones o secciones a un diálogo
    existente sin modificarlo.

    Ejemplo:
        - Plugin image_enhancer: añade botón "✨ Mejorar Imagen"
          al ImagePreviewDialog
    """

    def get_target_dialog(self) -> str:
        """
        Retorna el ID del diálogo a extender.

        IDs disponibles:
        - "image_preview": ImagePreviewDialog
        - "video_preview": VideoPreview (futuro)
        - "settings": SettingsDialog (futuro)
        """
        ...

    def get_widgets(self, dialog, **kwargs) -> List[QWidget]:
        """
        Retorna widgets a añadir al diálogo.

        Args:
            dialog: instancia del diálogo
            **kwargs: contexto adicional (ej. image=image, camera=camera)

        Returns:
            Lista de widgets a añadir.
        """
        ...

    def get_priority(self) -> int:
        ...


@runtime_checkable
class ToolbarContribution(Protocol):
    """
    Añade botones a la toolbar principal de MainWindow.

    Uso: un plugin puede añadir un botón global (ej. "🎤 Mic PC").

    Ejemplo:
        - Plugin audio: añade botón "🎤 Mic PC"
    """

    def get_buttons(self, main_window) -> List[QWidget]:
        """
        Retorna botones a añadir a la toolbar.

        Args:
            main_window: instancia de MainWindow

        Returns:
            Lista de widgets.
        """
        ...

    def get_priority(self) -> int:
        ...