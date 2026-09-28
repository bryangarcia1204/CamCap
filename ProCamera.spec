# -*- mode: python ; coding: utf-8 -*-
"""
Spec de PyInstaller para ProCamera.

Estrategia:
- Empaqueta: main.py, core/, ui/, utils/, resources/
- NO empaqueta: plugins/ (debe ir externa)
- NO empaqueta: plugins_installed/ (se crea en runtime)
- NO empaqueta: logs/, detected/, known_faces/ (runtime)

El usuario final debe tener:
    ProCamera.exe
    _internal/           (o archivos sueltos en onedir)
    plugins/             ← Copiada manualmente
"""
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# ============================================================
# RUTAS
# ============================================================
PROJECT_DIR = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821
RESOURCES_DIR = os.path.join(PROJECT_DIR, "resources")

# ============================================================
# DATAS (archivos no-Python que van dentro del EXE)
# ============================================================
datas = [
    # Recursos (iconos, estilos)
    (os.path.join(PROJECT_DIR, "resources"), "resources"),
]

# Recursos si existen
if os.path.exists(RESOURCES_DIR):
    # Añadir icono específico
    icon_path = os.path.join(RESOURCES_DIR, "icon.png")
    if os.path.exists(icon_path):
        datas.append((icon_path, "resources"))

# ✅ NO incluir la carpeta plugins/ (debe ir externa)

# ============================================================
# HIDDEN IMPORTS
# ============================================================
hiddenimports = [
    # === Core ===
    "core",
    "core.models",
    "core.settings_manager",
    "core.file_manager",
    "core.engine",
    "core.engine.camera_engine",
    "core.engine.screen_camera_engine",
    "core.engine.local_camera_engine",
    "core.engine.builtin_providers",

    # === Extensions ===
    "core.extension_registry",
    "core.extensions",
    "core.extensions.interfaces",
    "core.extensions.types",
    "core.extensions.services",
    "core.extensions.decorators",
    "core.extensions.capability_checker",
    "core.extensions.sandbox",
    "core.extensions.config_tab_provider",

    # === Plugins API ===
    "core.plugin_api",
    "core.plugin_api.base_plugin",
    "core.plugin_api.plugin_manager",
    "core.plugin_api.hooks",
    "core.plugin_api.interfaces",
    "core.plugin_api.api_impl",

    # === Plugins loader ===
    "core.plugins",
    "core.plugins.package_loader",
    "core.plugins.package_validator",

    # === Themes ===
    "core.themes",
    "core.themes.builtin_themes",

    # === Utils ===
    "utils.logger",
    "utils.config_loader",
    "utils.timer_manager",
    "utils.adaptive_throttle",
    "utils.av_recorder",
    "utils.performance",
    "utils.pixmap_pool",
    "utils.system_monitor",
    "utils.change_detector",

    # === UI ===
    "ui",
    "ui.camera_widget",
    "ui.camera_grid",
    "ui.file_explorer",
    "ui.image_preview",
    "ui.image_preview_dialog",
    "ui.settings_dialog",
    "ui.settings_dialog_base",
    "ui.loading_overlay",
    "ui.loading_manager",
    "ui.splash_screen",
    "ui.audio_level_widget",
    "ui.system_monitor_widget",
    "ui.video_preview",
    "ui.video_thumbnail_worker",
    "ui.auto_record_dialog",
    "ui.plugin_manager_dialog",
    "ui.plugin_card",
    "ui.plugin_info_dialog",
    "ui.plugin_install_dialog",
    "ui.widgets",
    "ui.widgets.config_widgets",

    # === PySide6 (solo lo que usas) ===
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtGui",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",

    # === Dependencias de core ===
    "cv2",
    "numpy",
    "requests",
    "urllib3",
    "certifi",
    "PIL",
    "PIL.Image",
    "psutil",
    "av",
    "sounddevice",
    "plyer",

    # === GPU (opcional, para SystemMonitor) ===
    "pynvml",
    "GPUtil",
    "pyadl",
]

# ============================================================
# EXCLUDE (dependencias pesadas que NO se usan)
# ============================================================
excludes = [
    # Tests y desarrollo
    "pytest",
    "pytest_qt",
    "unittest",
    "pydoc",

    # GUI alternativas
    "tkinter",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",

    # Módulos que PySide6 puede traer y no usamos
    # Esto es CRÍTICO para el tamaño final
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtXml",
    "PySide6.QtOpenGL",
    "PySide6.QtPrintSupport",
    "pygame",
    "kivy",
    "kivymd",

    # ✅ NO excluir plugins porque no están incluidos
]

# ============================================================
# BINARIES (DLLs específicas)
# ============================================================
binaries = []

# ============================================================
# ANALYSIS
# ============================================================
a = Analysis(
    ['main.py'],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================================
# PYZ
# ============================================================
pyd = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ============================================================
# EXE
# ============================================================
exe = EXE(
    pyd,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ProCamera',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.png' if os.path.exists('resources/icon.png') else None,
)

# ============================================================
# COLLECT (para onedir)
# ============================================================
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ProCamera',
)