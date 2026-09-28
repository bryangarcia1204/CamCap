"""
Punto de entrada optimizado con carga escalonada
"""
import sys
import os
import threading
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from utils.logger import get_logger, setup_exception_handler, ProCameraLogger
from utils.config_loader import advanced_config
from utils.performance import PacingController

# ✅ Logger global — se asigna en main() tras configurarlo
logger = None


class UIWatchdog:
    def __init__(self, timeout=5.0):
        self.timeout = timeout
        self.last_beat = time.time()
        self._stop = False
        self._reported = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def beat(self):
        self.last_beat = time.time()
        if self._reported:
            if logger:
                logger.info("✅ UI RECUPERADA")
            self._reported = False

    def _run(self):
        while not self._stop:
            time.sleep(1.0)
            elapsed = time.time() - self.last_beat
            if elapsed > self.timeout and not self._reported:
                if logger:
                    logger.critical(f"🚨 UI BLOQUEADA {elapsed:.1f}s")
                import faulthandler
                faulthandler.dump_traceback()
                self._reported = True


STAGE_DELAYS = {
    "startup": 100,
    "config": 80,
    "advanced": 60,
    "directories": 50,
    "engine": 120,
    "file_manager": 60,
    "ui_import": 150,
    "ui_build": 100,
    "window_show": 80,
    "final": 200,
}


def setup_application():
    app = QApplication(sys.argv)
    app.setApplicationName("ProCamera")
    app.setOrganizationName("ProCamera")
    app.setQuitOnLastWindowClosed(False)
    load_stylesheet(app)
    return app

def _get_plugins_dir() -> str:
    """
    Retorna la ruta de la carpeta 'plugins' correcta.

    Casos:
    1. Ejecutando desde código fuente → <proyecto>/plugins/
    2. Ejecutable PyInstaller (onefile) → <dir_del_exe>/plugins/
    3. Ejecutable PyInstaller (onedir) → <dir_del_exe>/plugins/
    """
    if getattr(sys, 'frozen', False):
        # Ejecutable empaquetado
        base_dir = os.path.dirname(sys.executable)
    else:
        # Código fuente
        base_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_dir, "plugins")

def load_stylesheet(app):
    """Carga el tema desde ThemeProvider o fallback a styles.qss."""
    try:
        from core.extension_registry import get_extension_registry
        from core.extensions.interfaces import ThemeProvider
        from PySide6.QtCore import QSettings

        registry = get_extension_registry()
        themes = registry.get(ThemeProvider)

        if themes:
            qs = QSettings("ProCamera", "CameraControl")
            theme_id = qs.value("ui/theme", "default", type=str)

            chosen = None
            for theme in themes:
                if theme.get_id() == theme_id:
                    chosen = theme
                    break
            if chosen is None:
                chosen = themes[0]

            qss = chosen.get_stylesheet()
            if qss:
                app.setStyleSheet(qss)
                logger.info(f"✅ Tema aplicado: {chosen.get_name()}")
                palette = chosen.get_palette()
                if palette is not None:
                    app.setPalette(palette)
                return
    except Exception as e:
        logger.debug(f"Error cargando tema desde provider: {e}")

    # Fallback: styles.qss directo
    try:
        styles_path = Path(__file__).parent / "resources" / "styles.qss"
        if styles_path.exists():
            with open(styles_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
            logger.info("✅ Estilos cargados (fallback)")
    except Exception as e:
        logger.error(f"Error cargando estilos: {e}")


def load_application_staged(app, splash):
    from ui.loaders.loading_manager import LoadingManager
    from core.settings_manager import settings_manager

    splash.update_stage("Cargando configuración básica...", 10,
                        STAGE_DELAYS["startup"])
    splash.update_stage("Cargando preferencias...", 20,
                        STAGE_DELAYS["config"])

    settings = settings_manager.get_capture_settings()

    splash.update_stage("Aplicando configuración avanzada...", 30,
                        STAGE_DELAYS["advanced"])

    advanced_config.load()

    splash.update_stage("Preparando directorios...", 40,
                        STAGE_DELAYS["directories"])

    try:
        directory = os.path.expanduser(settings.default_directory)
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        logger.warning(f"No se pudo crear directorio: {e}")

    splash.update_stage("Iniciando motor de cámaras...", 55,
                        STAGE_DELAYS["engine"])
    from core.engine.camera_engine import CameraManager  # noqa: F401

    splash.update_stage("Preparando gestor de archivos...", 65,
                        STAGE_DELAYS["file_manager"])
    from core.file_manager import FileManager  # noqa: F401

    splash.update_stage("Cargando interfaz...", 75,
                        STAGE_DELAYS["ui_import"])
    from ui.main_window import MainWindow

    splash.update_stage("Construyendo ventana principal...", 90,
                        STAGE_DELAYS["ui_build"])
    window = MainWindow()

    splash.update_stage("¡Listo!", 100, STAGE_DELAYS["final"])
    return window


def main():
    try:
        from PySide6.QtCore import QSettings
        qs = QSettings("ProCamera", "CameraControl")
        debug_mode = qs.value("advanced/debug_mode", False, type=bool)
        log_level = "DEBUG" if debug_mode else qs.value("advanced/log_level", "INFO", type=str)
        save_logs = qs.value("advanced/save_logs", True, type=bool)
    except Exception:
        log_level = "INFO"
        save_logs = True
        debug_mode = False

    ProCameraLogger().initialize(
        level=log_level,
        log_to_file=save_logs,
        log_debug_to_file=debug_mode,
        force=True,
    )
    setup_exception_handler()

    global logger
    logger = get_logger("Main")

    logger.info("=" * 60)
    logger.info("🚀 ProCamera iniciando...")
    logger.info(f"   Nivel de logs: {log_level}")
    logger.info(f"   Logs a disco: {save_logs}")
    logger.info(f"   DEBUG a disco: {debug_mode}")
    logger.info("=" * 60)

    app = setup_application()

    from core.extension_registry import get_extension_registry
    from core.extensions.services import get_core_services
    extension_registry = get_extension_registry()
    core_services = get_core_services()
    logger.info("📦 ExtensionRegistry inicializado")
    logger.info("🎯 CoreServices inicializado")

    # ✅ NUEVO: inyectar settings_manager en CoreServices
    from core.settings_manager import settings_manager
    core_services.set_settings_manager(settings_manager)
    logger.info("⚙️ SettingsManager inyectado en CoreServices")

    # ✅ NUEVO: registrar providers builtin
    try:
        from core.engine.builtin_providers import register_builtin_providers
        register_builtin_providers(extension_registry)
    except Exception as e:
        logger.error(f"❌ Error registrando providers builtin: {e}")

    # ✅ NUEVO: registrar temas builtin
    try:
        from core.themes.builtin_themes import register_builtin_themes
        register_builtin_themes(extension_registry)
    except Exception as e:
        logger.error(f"❌ Error registrando temas builtin: {e}")

    # ✅ NUEVO: registrar ConfigWidgets builtin
    try:
        from ui.widgets.config_widgets import register_builtin_config_widgets
        register_builtin_config_widgets()
    except Exception as e:
        logger.error(f"❌ Error registrando ConfigWidgets: {e}")

    # ✅ NUEVO: inicializar PluginManager
    from core.plugin_api import PluginManager, set_plugin_manager
    plugin_manager = PluginManager()
    plugin_manager.context.is_debug = debug_mode
    plugin_manager.context.extensions = extension_registry
    plugin_manager.context.services = core_services
    set_plugin_manager(plugin_manager)
    logger.info("🎛️ PluginManager creado")

    # ✅ Inyectar resolver de schemas en SettingsManager
    from core.settings_manager import settings_manager as _sm
    def _schema_resolver(plugin_name):
        pm = plugin_manager
        if pm is not None and pm.context.settings is not None:
            return pm.context.settings.get_schema(plugin_name)
        return None
    _sm.set_schema_provider(_schema_resolver)

    # ✅ NUEVO: CapabilityChecker
    from core.extensions.capability_checker import get_capability_checker
    checker = get_capability_checker()
    checker.set_strict_mode(not debug_mode)
    logger.info(f"🔒 CapabilityChecker: strict_mode={not debug_mode}")

    # ✅ NUEVO: Sandbox (solo en producción)
    try:
        from core.extensions.sandbox import activate_sandbox
        from PySide6.QtCore import QSettings
        qs = QSettings("ProCamera", "CameraControl")
        sandbox_enabled = qs.value("advanced/sandbox_enabled", True, type=bool)
        sandbox_strict = qs.value("advanced/sandbox_strict", True, type=bool)

        if sandbox_enabled:
            activate_sandbox(strict=sandbox_strict)
            logger.info(
                f"🛡️ Sandbox activado (strict={sandbox_strict})"
            )
        else:
            logger.info("🛡️ Sandbox desactivado (modo dev)")
    except Exception as e:
        logger.error(f"❌ Error activando sandbox: {e}")

    # TimerManager
    from utils.timer_manager import timer_manager
    logger.info("⏱️ TimerManager listo")

    # Splash
    from ui.loaders.loading_manager import LoadingManager
    splash = LoadingManager.init_splash()
    splash.set_progress(0, "Iniciando ProCamera...", force=True)

    PacingController.sleep_ms(150, process_events=True)

    main_window_ref = {'window': None}

    def start_loading():
        try:
            window = load_application_staged(app, splash)

            if window is None:
                raise Exception("No se pudo crear ventana")

            main_window_ref['window'] = window

            # ✅ NUEVO: Inyectar APIs
            _inject_plugin_apis(window, plugin_manager, extension_registry, core_services)

            # ✅ NUEVO: Cargar plugins
            _load_plugins(plugin_manager, window)

            splash.update_stage("Mostrando aplicación...", 100,
                                STAGE_DELAYS["window_show"])

            window.show()
            window.raise_()
            window.activateWindow()

            PacingController.sleep_ms(200, process_events=True)

            QTimer.singleShot(100, finish_splash)

        except Exception as e:
            logger.critical(f"❌ Error cargando: {e}", exc_info=True)
            LoadingManager.finish_splash()
            QTimer.singleShot(500, app.quit)

    def finish_splash():
        LoadingManager.finish_splash()
        QTimer.singleShot(400, activate_main)

    def activate_main():
        window = main_window_ref.get('window')
        if window:
            window.raise_()
            window.activateWindow()
            app.setQuitOnLastWindowClosed(True)

    PacingController.sleep_ms(200, process_events=True)
    QTimer.singleShot(100, start_loading)

    exit_code = app.exec()

    # ✅ Cleanup de plugins
    try:
        plugin_manager.unload_all()
    except Exception as e:
        logger.debug(f"Error cerrando plugins: {e}")

    try:
        timer_manager.shutdown()
    except Exception:
        pass

    logger.info(f"🏁 ProCamera cerrado (código: {exit_code})")
    sys.exit(exit_code)


def _inject_plugin_apis(main_window, plugin_manager, extension_registry, core_services):
    """Inyecta todas las APIs y servicios."""
    from core.plugin_api.api_impl import (
        SettingsAPIImpl,
        CamerasAPIImpl,
        FramesAPIImpl,
        UIAPIImpl,
        FilesAPIImpl,
        NotificationsAPIImpl,
        TimersAPIImpl,
        ServicesAPIImpl,
    )
    from core.event_bus import get_event_bus

    logger.info("🔌 Inyectando APIs...")

    settings_api = SettingsAPIImpl()
    cameras_api = CamerasAPIImpl(main_window.camera_manager)
    frames_api = FramesAPIImpl(cameras_api)
    ui_api = UIAPIImpl(main_window)
    files_api = FilesAPIImpl(main_window.file_manager)
    notifications_api = NotificationsAPIImpl()
    timers_api = TimersAPIImpl()
    services_api = ServicesAPIImpl()

    core_services.set_camera_manager(main_window.camera_manager)
    core_services.set_file_manager(main_window.file_manager)
    core_services.set_main_window(main_window)
    core_services.set_extension_registry(extension_registry)
    from core.settings_manager import settings_manager
    core_services.set_settings_manager(settings_manager)

    plugin_manager.set_context_apis(
        settings=settings_api,
        cameras=cameras_api,
        frames=frames_api,
        ui=ui_api,
        files=files_api,
        notifications=notifications_api,
        timers=timers_api,
        extensions=extension_registry,
        services=services_api,
    )

    # ✅ Inyectar EventBus en el contexto
    plugin_manager.context.event_bus = get_event_bus()

    logger.info("✅ APIs inyectadas")


def _load_plugins(plugin_manager, main_window):
    """Descubre y carga plugins."""
    import os
    from pathlib import Path

    # ✅ Ejecutar StartupHooks
    from core.extensions.interfaces import StartupHook
    from core.extension_registry import get_extension_registry

    registry = get_extension_registry()
    for hook in registry.get(StartupHook):
        try:
            hook.on_startup(main_window)
        except Exception as e:
            logger.error(f"❌ StartupHook falló: {e}")

    # ✅ Descubrir plugins usando la ruta correcta
    plugins_dir = _get_plugins_dir()
    logger.info(f"📂 Buscando plugins en: {plugins_dir}")

    if not os.path.isdir(plugins_dir):
        logger.warning(f"⚠️ Carpeta de plugins no existe: {plugins_dir}")
        logger.warning(f"⚠️ Crea la carpeta o reinstala la app")
        return

    count = plugin_manager.discover(plugins_dir)
    if count == 0:
        logger.warning("⚠️ No se descubrieron plugins")
        return

    plugin_manager.load_all(enabled_only=True)
    plugin_manager.enable_all()

    logger.info(
        f"🔌 Plugins: {len(plugin_manager.list_enabled())} activos, "
        f"{len(plugin_manager.list_failed())} fallidos"
    )


if __name__ == "__main__":
    main()