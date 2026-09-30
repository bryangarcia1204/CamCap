"""
ProCamera UI.

Interfaz gráfica del sistema. Los widgets se importan explícitamente
desde sus módulos (`from ui.camera_widget import CameraWidget`) para
evitar ciclos de importación entre diálogos, ventanas y grids.

Submódulos principales:
  - ui.main_window             Ventana principal
  - ui.camera_widget           Widget de una cámara
  - ui.camera_grid             Grid de cámaras
  - ui.file_explorer           Explorador de archivos
  - ui.image_preview           Visor de imágenes
  - ui.image_preview_dialog    Diálogo de preview + guardado
  - ui.settings_dialog         Diálogo de configuración
  - ui.settings_dialog_base    Base para ConfigTabs de plugins
  - ui.audio_level_widget      VU meter reutilizable
  - ui.system_monitor_widget   Monitor de sistema (CPU/GPU/RAM)
  - ui.plugin_manager_dialog   Administrador de plugins
  - ui.plugin_card            Card de un plugin
  - ui.plugin_info_dialog      Info detallada de un plugin
  - ui.plugin_install_dialog   Instalación desde ZIP
  - ui.markdown_viewer         Viewer markdown nivel GitHub
  - ui.loading_manager         Splash + overlay
  - ui.splash_screen           Pantalla de carga
  - ui.loading_overlay         Overlay de carga
"""

__all__ = []