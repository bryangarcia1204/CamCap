"""
Sistema de logging centralizado para ProCamera

Optimizaciones:
  - Rotación por nivel: cada nivel crítico tiene su propio archivo
  - Rotación por tamaño: 5 MB por archivo, con backups configurables
  - DEBUG opcional: se puede desactivar el log a disco de DEBUG
  - Formato consistente entre archivos
  - Sin duplicados de handlers
"""
import os
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


class ProCameraLogger:
    """Logger singleton con rotación por nivel y tamaño"""

    _instance = None
    _logger = None
    _initialized = False

    # Tamaño de rotación: 5 MB
    MAX_BYTES = 5 * 1024 * 1024

    # Configuración de archivos por nivel
    # Formato: (nombre_archivo, nivel_minimo, backup_count, solo_este_nivel)
    # "solo_este_nivel=True" → el handler usa un filtro para capturar SOLO ese nivel
    # "solo_este_nivel=False" → el handler captura ese nivel Y SUPERIORES
    LEVEL_FILES = {
        "DEBUG":    ("procamera_debug.log",   logging.DEBUG,    2, True),
        "INFO":     ("procamera_info.log",    logging.INFO,     3, True),
        "WARNING":  ("procamera_warning.log", logging.WARNING,  3, True),
        "ERROR":    ("procamera_error.log",   logging.ERROR,    3, True),
        "CRITICAL": ("procamera_critical.log",logging.CRITICAL, 3, True),
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self,
                name: str = "ProCamera",
                level: str = "INFO",
                log_to_file: bool = True,
                log_debug_to_file: bool = False,
                log_dir: str = "logs",
                force: bool = False) -> logging.Logger:
        """
        Inicializa el logger global.

        Args:
            name: Nombre del logger raíz
            level: Nivel mínimo a capturar (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_to_file: Si True, escribe logs a archivos
            log_debug_to_file: Si True, escribe DEBUG a su propio archivo
                               (por defecto False para evitar I/O masivo)
            log_dir: Directorio donde guardar los logs
        """
        if self._initialized and not force:
            return self._logger

        level_upper = level.upper()
        numeric_level = getattr(logging, level_upper, logging.INFO)

        self._logger = logging.getLogger(name)

        # ✅ Limpiar handlers previos (importante al reconfigurar)
        if self._logger.handlers:
            for h in list(self._logger.handlers):
                try:
                    h.close()
                except Exception:
                    pass
                self._logger.removeHandler(h)

        self._logger.setLevel(numeric_level)

        # Formato detallado consistente
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-15s | %(funcName)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # ============================================================
        # 1. CONSOLA (respeta el nivel configurado)
        # ============================================================
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # ============================================================
        # 2. ARCHIVO "TODO EN UNO" (procamera.log)
        # ============================================================
        if log_to_file:
            try:
                os.makedirs(log_dir, exist_ok=True)
                all_log_path = os.path.join(log_dir, 'procamera.log')

                all_handler = RotatingFileHandler(
                    all_log_path,
                    maxBytes=self.MAX_BYTES,
                    backupCount=5,
                    encoding='utf-8'
                )
                all_handler.setLevel(numeric_level)
                all_handler.setFormatter(formatter)
                self._logger.addHandler(all_handler)
            except Exception as e:
                print(f"⚠️ No se pudo crear handler 'all': {e}")

        # ============================================================
        # 3. ARCHIVOS POR NIVEL (uno por nivel, con filtro exacto)
        # ============================================================
        if log_to_file:
            for lvl_name, (filename, lvl_num, backups, exact_only) in self.LEVEL_FILES.items():
                # Saltar DEBUG si el usuario no lo quiere a disco
                if lvl_name == "DEBUG" and not log_debug_to_file:
                    continue

                # Saltar niveles por debajo del nivel mínimo configurado
                # (ej: si level=INFO, no crear archivo DEBUG)
                if lvl_num < numeric_level:
                    continue

                try:
                    level_path = os.path.join(log_dir, filename)
                    handler = RotatingFileHandler(
                        level_path,
                        maxBytes=self.MAX_BYTES,
                        backupCount=backups,
                        encoding='utf-8'
                    )
                    handler.setFormatter(formatter)

                    if exact_only:
                        # Solo este nivel exacto (ej: warning.log no tiene ERROR)
                        handler.addFilter(self._exact_level_filter(lvl_num))
                        handler.setLevel(lvl_num)
                    else:
                        # Este nivel y superiores
                        handler.setLevel(lvl_num)

                    self._logger.addHandler(handler)
                except Exception as e:
                    print(f"⚠️ No se pudo crear handler '{lvl_name}': {e}")

        self._initialized = True

        # Log de inicialización
        created = [f for f, _, _, _ in self.LEVEL_FILES.values()]
        self._logger.debug(
            f"📝 Logger inicializado: nivel={level_upper}, "
            f"a_disco={log_to_file}, debug_a_disco={log_debug_to_file}, "
            f"archivos_por_nivel={created}"
        )

        return self._logger

    @staticmethod
    def _exact_level_filter(target_level: int):
        """Factory de filtro que solo deja pasar mensajes del nivel EXACTO."""
        class _ExactLevelFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                return record.levelno == target_level
        return _ExactLevelFilter()

    def get(self) -> logging.Logger:
        """Retorna el logger configurado"""
        if not self._initialized:
            return self.initialize()
        return self._logger


# Instancia global
_logger_instance = ProCameraLogger()


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Obtiene el logger configurado"""
    logger = _logger_instance.get()
    if name:
        return logging.getLogger(f"ProCamera.{name}")
    return logger


def setup_exception_handler():
    """Configura el manejador global de excepciones"""
    logger = get_logger()

    def exception_handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Excepción no capturada",
            exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = exception_handler


def log_function_call(func):
    """Decorador para loggear llamadas a funciones"""
    def wrapper(*args, **kwargs):
        logger = get_logger()
        logger.debug(f"→ {func.__name__}()")
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"✗ {func.__name__}() falló: {e}", exc_info=True)
            raise
    return wrapper

# ============================================================
# HANDLER PARA CONSOLA DE DEBUG
# ============================================================

from PySide6.QtCore import QObject, Signal


class LogEmitter(QObject):
    """Emisor de señales thread-safe para logs."""
    message_logged = Signal(str, int)   # (texto_formateado, levelno)


class QtLogHandler(logging.Handler):
    """Handler que emite cada log como señal Qt."""

    def __init__(self):
        super().__init__()
        self.emitter = LogEmitter()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.emitter.message_logged.emit(msg, record.levelno)
        except Exception:
            self.handleError(record)


_debug_console_handler: Optional[QtLogHandler] = None


def get_debug_console_handler() -> QtLogHandler:
    """Obtiene (o crea) el handler global para la consola de debug."""
    global _debug_console_handler

    if _debug_console_handler is None:
        _debug_console_handler = QtLogHandler()
        _debug_console_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%H:%M:%S'
        )
        _debug_console_handler.setFormatter(formatter)

        root_logger = logging.getLogger("ProCamera")
        root_logger.addHandler(_debug_console_handler)

        logging.getLogger("ProCamera.Logger").info(
            "🖥️ Handler de consola de debug registrado"
        )

    return _debug_console_handler


def remove_debug_console_handler():
    """Elimina el handler global."""
    global _debug_console_handler
    if _debug_console_handler is not None:
        root_logger = logging.getLogger("ProCamera")
        try:
            root_logger.removeHandler(_debug_console_handler)
        except Exception:
            pass
        _debug_console_handler = None