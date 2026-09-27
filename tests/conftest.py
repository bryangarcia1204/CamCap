"""
Fixtures compartidos para todos los tests.

FIX v2:
- Fixture autouse para aislar advanced_config
- Helpers para tests con tolerancia
- Marcadores para skip condicional (GPU, cámara, etc.)
"""
import os
import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

# Asegurar que el proyecto esté en el path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ==================== APLICACIÓN QT ====================

@pytest.fixture(scope="session")
def qapp():
    """QApplication única para toda la sesión de tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ==================== AISLAMIENTO DE CONFIG ====================

@pytest.fixture(autouse=True)
def isolate_advanced_config(monkeypatch, temp_dir):
    """
    Aísla advanced_config para que los tests NO dependan de la config real del usuario.

    Sin esto, un test como `assert thread.fps == 30` puede fallar si el usuario
    tiene `target_fps=25` en su QSettings.
    """
    from utils.config_loader import AdvancedConfig, advanced_config

    # Guardar config actual (si existe)
    original_config = None
    if advanced_config._config is not None:
        original_config = advanced_config._config.copy()

    # Poner defaults conocidos
    advanced_config._config = AdvancedConfig.DEFAULTS.copy()

    yield

    # Restaurar
    if original_config is not None:
        advanced_config._config = original_config
    else:
        advanced_config._config = None


# ==================== HELPERS PARA TESTS ====================

def assert_in_range(value, min_val, max_val, name="value"):
    """Helper: verifica que un valor esté en rango"""
    assert min_val <= value <= max_val, \
        f"{name}={value} fuera de rango [{min_val}, {max_val}]"


def assert_approx(actual, expected, tolerance=0.1, name="value"):
    """Helper: verifica que un valor esté cerca del esperado"""
    assert abs(actual - expected) <= tolerance, \
        f"{name}={actual} no está cerca de {expected} (tol={tolerance})"


def has_gpu() -> bool:
    """Verifica si hay GPU disponible"""
    try:
        import pynvml
        pynvml.nvmlInit()
        return pynvml.nvmlDeviceGetCount() > 0
    except Exception:
        return False


def has_camera() -> bool:
    """Verifica si hay cámara local disponible"""
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        result = cap.isOpened()
        cap.release()
        return result
    except Exception:
        return False


# ==================== MARCADORES PERSONALIZADOS ====================

def pytest_configure(config):
    """Registra marcadores personalizados"""
    config.addinivalue_line(
        "markers",
        "requires_gpu: test que requiere GPU dedicada"
    )
    config.addinivalue_line(
        "markers",
        "requires_camera: test que requiere una cámara física"
    )
    config.addinivalue_line(
        "markers",
        "requires_audio: test que requiere dispositivo de audio"
    )
    config.addinivalue_line(
        "markers",
        "slow: test que tarda >1s"
    )


# ==================== ARCHIVOS TEMPORALES ====================

@pytest.fixture
def temp_dir():
    """Directorio temporal para tests"""
    tmp = tempfile.mkdtemp(prefix="camcap_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def temp_image_path(temp_dir):
    """Crea una imagen de prueba y devuelve su ruta"""
    import cv2
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (100, 150, 200)
    path = os.path.join(temp_dir, "test_image.jpg")
    cv2.imwrite(path, img)
    return path


@pytest.fixture
def temp_video_path(temp_dir):
    """Crea un video de prueba y devuelve su ruta"""
    import cv2
    path = os.path.join(temp_dir, "test_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 30, (320, 240))
    for i in range(30):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (i * 8, 100, 200 - i * 6)
        out.write(frame)
    out.release()
    return path


# ==================== IMÁGENES DE PRUEBA ====================

@pytest.fixture
def sample_bgr_image():
    """Imagen BGR sintética"""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_gray_image():
    """Imagen en escala de grises"""
    return np.random.randint(0, 255, (480, 640), dtype=np.uint8)


@pytest.fixture
def dark_image():
    """Imagen muy oscura"""
    return np.full((480, 640, 3), 20, dtype=np.uint8)


@pytest.fixture
def bright_image():
    """Imagen muy clara"""
    return np.full((480, 640, 3), 240, dtype=np.uint8)


@pytest.fixture
def blurry_image():
    """Imagen borrosa"""
    import cv2
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    return cv2.GaussianBlur(img, (31, 31), 10)


@pytest.fixture
def noisy_image():
    """Imagen con ruido"""
    base = np.full((480, 640, 3), 128, dtype=np.uint8)
    noise = np.random.randint(-50, 50, (480, 640, 3), dtype=np.int16)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


# ==================== CÁMARAS ====================

@pytest.fixture
def camera_ip():
    """Cámara IP de prueba"""
    from core.models import CameraDevice
    return CameraDevice(
        id=0,
        name="Test IP Camera",
        ip="192.168.1.100",
        port=4747,
        url_type="video"
    )


@pytest.fixture
def camera_local():
    """Cámara local de prueba"""
    from core.models import CameraDevice
    return CameraDevice(
        id=1,
        name="Test Local Camera",
        ip="LOCAL",
        port=0,
        url_type="local",
        is_local=True,
        camera_index=0
    )


@pytest.fixture
def camera_screen():
    """Cámara de pantalla de prueba"""
    from core.models import CameraDevice
    return CameraDevice(
        id=2,
        name="Test Screen",
        ip="SCREEN",
        port=0,
        url_type="screen",
        is_screen=True
    )


# ==================== SETTINGS LIMPIOS ====================

@pytest.fixture
def clean_settings(temp_dir, monkeypatch):
    """QSettings limpio para tests de settings_manager"""
    settings_file = os.path.join(temp_dir, "test_settings.ini")
    monkeypatch.setenv("QT_SETTINGS_PATH", temp_dir)

    from core.settings_manager import SettingsManager
    SettingsManager._instance = None

    yield

    SettingsManager._instance = None
    if os.path.exists(settings_file):
        os.remove(settings_file)


# ==================== MOCKS ====================

@pytest.fixture
def mock_psutil(monkeypatch):
    """Mock de psutil para tests de CPU"""
    mock = MagicMock()
    mock.cpu_percent.return_value = 25.0
    mock.virtual_memory.return_value = MagicMock(
        percent=60.0,
        used=8 * 1024**3,
        total=16 * 1024**3
    )
    mock.Process.return_value = MagicMock(
        cpu_percent=MagicMock(return_value=15.0)
    )
    monkeypatch.setitem(sys.modules, "psutil", mock)
    return mock


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock de requests para tests de red"""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.close = MagicMock()
    mock.get.return_value = mock_response
    mock.head.return_value = mock_response
    monkeypatch.setitem(sys.modules, "requests", mock)
    return mock


@pytest.fixture
def mock_cv2_videocapture(monkeypatch):
    """Mock de cv2.VideoCapture"""
    import cv2
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    mock_cap.get.return_value = 30.0

    original = cv2.VideoCapture
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args, **kwargs: mock_cap)
    return mock_cap