"""
ProCamera Utilities.

Utilidades transversales. Cada submódulo se importa explícitamente
desde donde se necesita.

Submódulos principales:
  - utils.logger               Logger centralizado con rotación por nivel
  - utils.config_loader        AdvancedConfig (defaults + reload)
  - utils.timer_manager        Gestor centralizado de QTimers
  - utils.performance          PacingController, CPUMonitor, FrameScheduler
  - utils.pixmap_pool          Pool de QPixmap reutilizables
  - utils.system_monitor       Monitor de CPU/GPU/RAM (singleton)
  - utils.adaptive_throttle    Throttle adaptativo por CPU/GPU
  - utils.av_recorder          Grabador de video con audio (OpenCV + PyAV)
  - utils.change_detector      Detector de cambios de configuración
"""

__all__ = []