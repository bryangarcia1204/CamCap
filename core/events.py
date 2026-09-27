"""
Nombres de eventos del dominio del Core.

Los componentes del Core emiten estos eventos. Los plugins (o el propio
Core) se suscriben. Es infraestructura pura del Core.

Uso:
    from core.events import MOTION_DETECTED
    get_event_bus().emit(MOTION_DETECTED, camera_id=0, rects=[...])

Si necesitas un evento nuevo, añádelo aquí con nombre descriptivo.
"""

# ============================================================
# CICLO DE VIDA DE CÁMARAS
# ============================================================

CAMERA_ADDED = "camera_added"
CAMERA_REMOVED = "camera_removed"
CAMERA_CONNECTED = "camera_connected"
CAMERA_DISCONNECTED = "camera_disconnected"
CAMERA_ERROR = "camera_error"


# ============================================================
# FRAMES
# ============================================================

FRAME_READY = "frame_ready"
"""
kwargs:
    camera_id: int
    frame: np.ndarray (BGR)
    timestamp: float

Se emite por cada frame procesado (post-throttle).
Útil para: grabadores de audio, análisis externo, exporters.
"""

FRAME_ANALYZED = "frame_analyzed"
"""
kwargs:
    camera_id: int
    result: dict

Se emite después de que un FrameAnalyzer procesa un frame.
"""


# ============================================================
# DETECCIONES (genéricas, no específicas de un tipo)
# ============================================================

MOTION_DETECTED = "motion_detected"
"""
kwargs:
    camera_id: int
    rects: List[Tuple[int, int, int, int]]
    intensity: float (opcional)
"""

FACE_DETECTED = "face_detected"
"""
kwargs:
    camera_id: int
    locations: List[Tuple]
    names: List[str]
"""

OBJECT_DETECTED = "object_detected"
"""
kwargs:
    camera_id: int
    objects: List[dict]  (clase, bbox, confianza)
"""

TEXT_RECOGNIZED = "text_recognized"
"""
kwargs:
    camera_id: int
    text: str
"""


# ============================================================
# CAPTURAS
# ============================================================

IMAGE_CAPTURED = "image_captured"
"""
kwargs:
    camera_id: int
    camera_name: str
    frame: np.ndarray (BGR)

Frame capturado en memoria, ANTES de guardar.
"""

IMAGE_SAVED = "image_saved"
"""
kwargs:
    path: str
    camera_name: str
    frame: np.ndarray (BGR)
    size_bytes: int

Imagen persistida a disco. Útil para OCR, thumbnails, cloud sync.
"""


# ============================================================
# GRABACIÓN
# ============================================================

RECORDING_STARTED = "recording_started"
"""
kwargs:
    camera_id: int
    camera_name: str
    path: str      (ruta del video)
    fps: int
    width: int
    height: int

El Core empieza a grabar video. El plugin de audio se suscribe
para empezar a escribir su WAV en paralelo.
"""

RECORDING_STOPPED = "recording_stopped"
"""
kwargs:
    camera_id: int
    camera_name: str
    path: str      (ruta del video final)

El Core termina de grabar. El plugin de audio se suscribe para
cerrar su WAV y mezclar.
"""

VIDEO_SAVED = "video_saved"
"""
kwargs:
    path: str
    camera_name: str
    size_bytes: int
"""


# ============================================================
# CONFIGURACIÓN
# ============================================================

SETTINGS_CHANGED = "settings_changed"
"""
kwargs:
    modules: Dict[str, List[str]]
    report: ChangeReport

Los plugins se suscriben si quieren reaccionar a cambios en runtime.
"""

PLUGIN_ENABLED = "plugin_enabled"
PLUGIN_DISABLED = "plugin_disabled"
"""
kwargs:
    plugin_name: str
"""


# ============================================================
# APP
# ============================================================

APP_STARTING = "app_starting"
APP_STARTED = "app_started"
APP_CLOSING = "app_closing"
APP_CLOSED = "app_closed"