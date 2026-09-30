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

block_cipher = None

# ============================================================
# RUTAS
# ============================================================
PROJECT_DIR = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821

# ============================================================
# HIDDEN IMPORTS
# ============================================================
hiddenimports = [
    # === Core ===
    "core",

    # === Utils ===
    "utils",

    # === GUI ===
    "ui",

    # === PySide6 (solo lo que usas) ===
    "PySide6",

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
    "IPython",
    "jupyter",
    "notebook",
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
    datas=[
        ('resources', 'resources'),
        ('core', 'core'),
        ('ui', 'ui'),
        ('utils', 'utils'),
    ],
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
    runtime_hooks=['pyi_rth_setup_paths.py'],
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