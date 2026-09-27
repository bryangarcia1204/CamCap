"""
Interfaces (Protocols) para el sistema de extensiones.

Puntos de extensión GENÉRICOS del Core. NO mencionan ningún servicio
específico (motion, face, audio, etc.). Cualquier plugin puede
implementarlas.

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
    """Provee URLs de stream para cámaras (cualquier protocolo)."""

    def can_handle(self, camera) -> bool: ...
    def get_stream_url(self, camera) -> Optional[str]: ...
    def get_protocol(self) -> CameraProtocol: ...


@runtime_checkable
class CameraDetector(Protocol):
    """Detecta cámaras disponibles en el sistema (cualquier método)."""

    def get_name(self) -> str: ...
    def detect(self) -> List[Any]: ...


@runtime_checkable
class CameraLifecycleListener(Protocol):
    """Escucha eventos del ciclo de vida de cámaras."""

    def on_camera_added(self, camera): ...
    def on_camera_removed(self, camera_id: int): ...
    def on_camera_connected(self, camera): ...
    def on_camera_disconnected(self, camera): ...
    def on_camera_error(self, camera, error: str): ...


# ============================================================
# FRAMES
# ============================================================

@runtime_checkable
class FramePreProcessor(Protocol):
    """Transforma un frame ANTES de mostrarlo."""

    def process(self, camera_id: int, frame: np.ndarray) -> Optional[np.ndarray]: ...
    def get_priority(self) -> int: ...


@runtime_checkable
class FramePostProcessor(Protocol):
    """Analiza un frame DESPUÉS de mostrarlo."""

    def process(self, camera_id: int, frame: np.ndarray): ...
    def get_priority(self) -> int: ...


@runtime_checkable
class FrameAnalyzer(Protocol):
    """Analiza frames (movimiento, caras, lo que sea)."""

    def analyze(self, camera_id: int, frame: np.ndarray) -> Dict[str, Any]: ...
    def should_run(self, camera_id: int) -> bool: ...
    def get_frame_skip(self) -> int: ...


# ============================================================
# UI
# ============================================================

@runtime_checkable
class ToolbarProvider(Protocol):
    """Provee widgets para la toolbar principal."""

    def get_widgets(self) -> List[QWidget]: ...


@runtime_checkable
class MenuProvider(Protocol):
    """Provee menús."""

    def get_menu_name(self) -> str: ...
    def get_actions(self) -> List[QAction]: ...


@runtime_checkable
class ConfigTab(Protocol):
    """Una pestaña completa de configuración."""

    def get_id(self) -> str: ...
    def get_title(self) -> str: ...
    def get_icon(self) -> str: ...
    def get_widget(self) -> QWidget: ...
    def on_save(self) -> bool: ...
    def on_load(self): ...


@runtime_checkable
class ConfigSection(Protocol):
    """Sección de configuración que se añade a una tab existente."""

    def get_target_tab_id(self) -> str: ...
    def get_title(self) -> str: ...
    def get_widget(self) -> QWidget: ...
    def on_save(self) -> bool: ...
    def get_priority(self) -> int: ...


@runtime_checkable
class ConfigWidget(Protocol):
    """Widget de configuración personalizado (slider, color picker, etc.)"""

    def get_config_key(self) -> str: ...
    def get_widget(self) -> QWidget: ...
    def get_value(self) -> Any: ...
    def set_value(self, value: Any): ...


@runtime_checkable
class VideoOverlay(Protocol):
    """Overlay sobre el video de una cámara."""

    def should_show(self, camera_id: int) -> bool: ...
    def get_overlay_widget(self, camera_id: int) -> Optional[QWidget]: ...
    def get_priority(self) -> int: ...


@runtime_checkable
class StatusWidget(Protocol):
    """Widget para la status bar."""

    def get_widget(self) -> QWidget: ...


@runtime_checkable
class DialogProvider(Protocol):
    """Provee diálogos personalizados."""

    def get_dialog_id(self) -> str: ...
    def get_dialog(self, parent=None) -> Optional[QDialog]: ...


# ============================================================
# UI EXTENSION GENÉRICA (inyección en slots)
# ============================================================

@runtime_checkable
class UIExtension(Protocol):
    """
    Inyecta widgets en un punto de extensión (target, slot) declarado
    por el Core. Es la interfaz MÁS genérica para UI.
    """

    def get_id(self) -> str: ...
    def get_target(self) -> str: ...
    def get_slot(self) -> str: ...
    def get_widgets(self, context: dict) -> List[QWidget]: ...
    def get_priority(self) -> int: ...


# ============================================================
# COMPORTAMIENTO
# ============================================================

@runtime_checkable
class KeyboardInterceptor(Protocol):
    """Intercepta teclas a nivel global."""

    def intercept(self, key: int, modifiers: int) -> bool: ...


@runtime_checkable
class MouseInterceptor(Protocol):
    """Intercepta eventos de ratón."""

    def intercept_click(self, widget, x: int, y: int, button: int) -> bool: ...


@runtime_checkable
class AppLifecycleHook(Protocol):
    """Hook en el ciclo de vida de la app."""

    def on_app_start(self, app): ...
    def on_app_close(self): ...


@runtime_checkable
class StartupHook(Protocol):
    """Se ejecuta al arrancar la app (después de MainWindow)."""

    def on_startup(self, main_window): ...
    def get_priority(self) -> int: ...


@runtime_checkable
class ShutdownHook(Protocol):
    """Se ejecuta al cerrar la app."""

    def on_shutdown(self): ...
    def get_priority(self) -> int: ...


# ============================================================
# TEMAS
# ============================================================

@runtime_checkable
class ThemeProvider(Protocol):
    """Provee un tema (stylesheet + paleta)."""

    def get_id(self) -> str: ...
    def get_name(self) -> str: ...
    def get_mode(self) -> ThemeMode: ...
    def get_stylesheet(self) -> str: ...
    def get_palette(self) -> Optional[Any]: ...


@runtime_checkable
class IconProvider(Protocol):
    """Provee iconos."""

    def get_icon(self, name: str) -> Optional[QIcon]: ...
    def list_icons(self) -> List[str]: ...


# ============================================================
# DATOS
# ============================================================

@runtime_checkable
class FileHandler(Protocol):
    """Maneja archivos con extensiones específicas."""

    def get_extensions(self) -> List[str]: ...
    def open(self, path: str) -> Any: ...
    def save(self, path: str, data: Any) -> bool: ...
    def preview_widget(self, path: str) -> Optional[QWidget]: ...


@runtime_checkable
class StorageProvider(Protocol):
    """Provee almacenamiento adicional (cloud, base de datos, etc.)."""

    def get_id(self) -> str: ...
    def list_files(self, prefix: str = "") -> List[str]: ...
    def download(self, remote_path: str, local_path: str) -> bool: ...
    def upload(self, local_path: str, remote_path: str) -> bool: ...


@runtime_checkable
class ImportProvider(Protocol):
    """Importa datos de fuentes externas."""

    def get_name(self) -> str: ...
    def can_import(self, source: str) -> bool: ...
    def import_data(self, source: str) -> Any: ...


@runtime_checkable
class ExportProvider(Protocol):
    """Exporta datos a formatos externos."""

    def get_name(self) -> str: ...
    def get_extension(self) -> str: ...
    def export_data(self, data: Any, path: str) -> bool: ...


# ============================================================
# PLUGINS (meta)
# ============================================================

@runtime_checkable
class PluginWrapper(Protocol):
    """Envuelve a otros plugins para modificar su comportamiento."""

    def wraps_plugin(self, plugin_name: str) -> bool: ...
    def before_call(self, plugin_name: str, method: str, args: tuple, kwargs: dict): ...
    def after_call(self, plugin_name: str, method: str, result: Any) -> Any: ...
    def on_error(self, plugin_name: str, method: str, error: Exception): ...


@runtime_checkable
class PluginLifecycleHook(Protocol):
    """Hook en el ciclo de vida de plugins."""

    def on_plugin_loaded(self, plugin_name: str): ...
    def on_plugin_enabled(self, plugin_name: str): ...
    def on_plugin_disabled(self, plugin_name: str): ...
    def on_plugin_unloaded(self, plugin_name: str): ...


@runtime_checkable
class PluginValidator(Protocol):
    """Valida plugins antes de cargarlos."""

    def validate(self, plugin_path: str, metadata: Dict[str, Any]) -> bool: ...
    def get_rejection_reason(self) -> str: ...


# ============================================================
# UTILIDADES (genéricas)
# ============================================================

@runtime_checkable
class NotificationProvider(Protocol):
    """
    Provee notificaciones (cualquier canal: Windows, Telegram, webhook…).

    Genérico: el Core no sabe de canales específicos.
    """

    def get_id(self) -> str: ...
    def notify(
        self,
        title: str,
        message: str,
        level: NotificationLevel,
        image_path: Optional[str] = None,
    ) -> bool: ...
    def is_available(self) -> bool: ...


@runtime_checkable
class TaskScheduler(Protocol):
    """Programa tareas en background."""

    def schedule(self, name: str, interval_ms: int, callback: Callable): ...
    def cancel(self, name: str): ...