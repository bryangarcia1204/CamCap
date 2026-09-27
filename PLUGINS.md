# 🔌 Guía de Desarrollo de Plugins

Guía completa para crear plugins para ProCamera.

---

## 📋 Índice

1. [Filosofía](#-filosofía)
2. [Estructura de un Plugin](#-estructura-de-un-plugin)
3. [Ciclo de Vida](#-ciclo-de-vida)
4. [Puntos de Extensión](#-puntos-de-extensión)
5. [Event Bus](#-event-bus)
6. [APIs disponibles](#-apis-disponibles)
7. [Capabilities y Sandbox](#-capabilities-y-sandbox)
8. [Ejemplos completos](#-ejemplos-completos)
9. [Empaquetado y distribución](#-empaquetado-y-distribución)

---

## 🎯 Filosofía

ProCamera sigue el principio de **inversión de dependencias**:

- **El Core no conoce los plugins**. Es totalmente autosuficiente.
- **Los plugins conocen el Core** y se enganchan a sus puntos de extensión.
- **Comunicación por eventos**: el Core emite eventos del dominio, los plugins reaccionan.
- **Sin acoplamiento**: un plugin roto no afecta a los demás ni al Core.

Esto significa que:

- ✅ Puedes añadir/eliminar plugins sin tocar el Core.
- ✅ Tu plugin puede fallar sin tumbar la app.
- ✅ El Core no sabe que tu plugin existe.

---

## 📁 Estructura de un Plugin

Un plugin es una carpeta o ZIP con esta estructura mínima:

```
mi_plugin/
├── __init__.py          # Opcional (marca el directorio como paquete)
├── plugin.py            # OBLIGATORIO: clase principal
├── manifest.json        # Recomendado: metadatos
├── widgets.py           # Opcional: widgets UI
├── config_tab.py        # Opcional: pestaña de configuración
└── ...                  # Otros módulos
```

### manifest.json

```json
{
  "name": "mi_plugin",
  "version": "1.0.0",
  "description": "Descripción breve de qué hace",
  "author": "Tu Nombre",
  "dependencies": ["otro_plugin"],
  "capabilities": ["camera_access", "network"],
  "enabled_by_default": true,
  "auto_load": true,
  "requires_debug": false
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Nombre único (sin espacios) |
| `version` | string | Versión semver |
| `description` | string | Texto corto |
| `author` | string | Autor |
| `dependencies` | list | Nombres de plugins requeridos |
| `capabilities` | list | Permisos (ver [Capabilities](#-capabilities-y-sandbox)) |
| `enabled_by_default` | bool | Cargar al arrancar (default: `true`) |
| `auto_load` | bool | Descubrir al arrancar (default: `true`) |
| `requires_debug` | bool | Solo cargar en modo debug (default: `false`) |

---

## 🔄 Ciclo de Vida

Tu plugin hereda de `BasePlugin` y sobrescribe los hooks que necesites:

```python
from core.plugin_api import BasePlugin

class MiPlugin(BasePlugin):
    NAME = "mi_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "Mi plugin de ejemplo"
    AUTHOR = "Tu Nombre"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def on_load(self) -> bool:
        """Se llama al cargar. Registra recursos, importa clases."""
        self.logger.info("Cargando...")
        return True

    def on_enable(self) -> bool:
        """Se llama al activar. Registra extensiones, se suscribe a eventos."""
        self.logger.info("Activando...")
        return True

    def on_disable(self):
        """Se llama al desactivar. Desuscríbete, limpia UI, pausa features."""
        self.logger.info("Desactivando...")

    def on_unload(self):
        """Se llama al descargar. Libera TODOS los recursos."""
        self.logger.info("Descargando...")

    def on_settings_changed(self, changed_keys: list):
        """Opcional. Se llama cuando cambia la config."""
        pass
```

| Método | Cuándo | Qué hacer |
|--------|--------|-----------|
| `on_load()` | Al cargar | Importar clases, validar dependencias |
| `on_enable()` | Al activar | Registrar extensiones, suscribirse a eventos |
| `on_disable()` | Al desactivar | Desuscribirse, ocultar UI, pausar |
| `on_unload()` | Al descargar | Liberar recursos, cerrar archivos |
| `on_settings_changed()` | Cambio config | Recargar config si aplica |

**Regla de oro**: si registras algo en `on_enable()`, desregístralo en `on_disable()`. Si lo creas en `on_load()`, destrúyelo en `on_unload()`.

---

## 🧩 Puntos de Extensión

Los plugins se enganchan al Core registrando implementaciones de **Protocols** (`core/extensions/interfaces.py`).

### `register_extension(interface, implementation, priority=50)`

Registra una implementación de una interfaz. Se desregistra automáticamente al descargar.

```python
from core.extensions.interfaces import FrameAnalyzer

self.register_extension(FrameAnalyzer, self, priority=100)
```

### Interfaces disponibles

#### 🎥 Cámaras

| Interfaz | Descripción |
|----------|-------------|
| `CameraProvider` | Provee URLs de stream (cualquier protocolo) |
| `CameraDetector` | Descubre cámaras disponibles |
| `CameraLifecycleListener` | Escucha eventos de ciclo de vida |

#### 🖼️ Frames

| Interfaz | Descripción |
|----------|-------------|
| `FramePreProcessor` | Transforma el frame antes de mostrarlo |
| `FramePostProcessor` | Analiza el frame después |
| `FrameAnalyzer` | Analiza frames (detección, tracking, etc.) |

#### 🖥️ UI

| Interfaz | Descripción |
|----------|-------------|
| `UIExtension` | Inyecta widgets en un (target, slot) |
| `ToolbarProvider` | Widgets para la toolbar |
| `MenuProvider` | Items de menú |
| `ConfigTab` | Pestaña completa de configuración |
| `ConfigSection` | Sección en una pestaña existente |
| `ConfigWidget` | Tipo de widget de config |
| `VideoOverlay` | Overlay sobre el video |
| `StatusWidget` | Widget para la status bar |
| `DialogProvider` | Diálogos personalizados |

#### ⌨️ Comportamiento

| Interfaz | Descripción |
|----------|-------------|
| `KeyboardInterceptor` | Intercepta teclas |
| `MouseInterceptor` | Intercepta clics |
| `AppLifecycleHook` | Hook de inicio/fin de app |
| `StartupHook` | Se ejecuta al arrancar |
| `ShutdownHook` | Se ejecuta al cerrar |

#### 🎨 Temas y datos

| Interfaz | Descripción |
|----------|-------------|
| `ThemeProvider` | Tema (stylesheet + paleta) |
| `IconProvider` | Iconos |
| `FileHandler` | Maneja formatos de archivo |
| `StorageProvider` | Almacenamiento externo |
| `ImportProvider` / `ExportProvider` | Import/export |

#### 🔌 Meta-plugins

| Interfaz | Descripción |
|----------|-------------|
| `PluginWrapper` | Envuelve a otros plugins |
| `PluginLifecycleHook` | Hook en ciclo de vida de plugins |
| `PluginValidator` | Valida plugins antes de cargar |

#### 🛠️ Utilidades

| Interfaz | Descripción |
|----------|-------------|
| `NotificationProvider` | Envío de notificaciones (cualquier canal) |
| `TaskScheduler` | Programa tareas periódicas |

### Ejemplo: `FrameAnalyzer`

```python
from core.extensions.interfaces import FrameAnalyzer

class MiAnalyzer:
    def analyze(self, camera_id: int, frame) -> dict:
        # Analiza el frame y devuelve un resultado
        return {"kind": "custom", "data": ...}

    def should_run(self, camera_id: int) -> bool:
        # ¿Analizar este frame?
        return True

    def get_frame_skip(self) -> int:
        return 3   # analizar 1 de cada 3 frames

# Registrar en on_enable
self.register_extension(FrameAnalyzer, MiAnalyzer(), priority=100)
```

### Ejemplo: `UIExtension`

```python
from core.extensions.interfaces import UIExtension
from PySide6.QtWidgets import QPushButton

class MiUIExtension:
    def get_id(self): return "mi_plugin.camera_widget.header"
    def get_target(self): return "camera_widget"
    def get_slot(self): return "header"
    def get_priority(self): return 120

    def get_widgets(self, context: dict):
        camera = context["camera"]
        camera_widget = context["widget"]
        btn = QPushButton("✨")
        btn.clicked.connect(lambda: self._do_something(camera))
        return [btn]

    def _do_something(self, camera):
        pass

self.register_extension(UIExtension, MiUIExtension(), priority=120)
```

### Slots disponibles por target

| Target | Slots |
|--------|-------|
| `camera_widget` | `header`, `footer` |
| `image_preview` | `info_bar` |
| `video_preview` | `info_bar` |
| `main_toolbar` | `left`, `right` |

---

## 📡 Event Bus

El Core emite **eventos del dominio** a los que tu plugin puede suscribirse.

### Suscribirse

```python
if self.context.event_bus is not None:
    from core.events import MOTION_DETECTED
    self.context.event_bus.subscribe(
        MOTION_DETECTED,
        self._on_motion,
        owner=self.NAME,
    )

def _on_motion(self, camera_id, camera_name=None, rects=None, **kwargs):
    self.logger.info(f"Movimiento en {camera_name}")
```

### Desuscribirse

```python
def on_disable(self):
    if self.context.event_bus is not None:
        from core.events import MOTION_DETECTED
        self.context.event_bus.unsubscribe(MOTION_DETECTED, self._on_motion)
```

**Usa siempre `**kwargs`** en tus handlers: el Core puede añadir campos nuevos en el futuro sin romper tu plugin.

### Eventos disponibles

#### Ciclo de vida de cámaras

| Evento | kwargs |
|--------|--------|
| `CAMERA_ADDED` | `camera` |
| `CAMERA_REMOVED` | `camera_id` |
| `CAMERA_CONNECTED` | `camera` |
| `CAMERA_DISCONNECTED` | `camera` |
| `CAMERA_ERROR` | `camera`, `error` |

#### Frames

| Evento | kwargs |
|--------|--------|
| `FRAME_READY` | `camera_id`, `frame`, `timestamp` |
| `FRAME_ANALYZED` | `camera_id`, `result` |

#### Detecciones

| Evento | kwargs |
|--------|--------|
| `MOTION_DETECTED` | `camera_id`, `camera_name`, `rects`, `intensity?` |
| `FACE_DETECTED` | `camera_id`, `camera_name`, `locations`, `names` |
| `OBJECT_DETECTED` | `camera_id`, `objects` |
| `TEXT_RECOGNIZED` | `camera_id`, `text` |

#### Capturas

| Evento | kwargs |
|--------|--------|
| `IMAGE_CAPTURED` | `camera_id`, `camera_name`, `frame` |
| `IMAGE_SAVED` | `path`, `frame`, `size_bytes`, `format` |

#### Grabación

| Evento | kwargs |
|--------|--------|
| `RECORDING_STARTED` | `camera_id`, `camera_name`, `path`, `fps`, `width`, `height` |
| `RECORDING_STOPPED` | `camera_id`, `camera_name`, `path` |
| `VIDEO_SAVED` | `path`, `size_bytes`, `frames`, `fps` |

#### Configuración

| Evento | kwargs |
|--------|--------|
| `SETTINGS_CHANGED` | `modules` (dict con módulos afectados) |
| `PLUGIN_ENABLED` | `plugin_name` |
| `PLUGIN_DISABLED` | `plugin_name` |

#### App

| Evento | kwargs |
|--------|--------|
| `APP_STARTING` | — |
| `APP_STARTED` | — |
| `APP_CLOSING` | — |
| `APP_CLOSED` | — |

### Emitir eventos propios

```python
if self.context.event_bus is not None:
    self.context.event_bus.emit(
        "mi_evento_custom",
        mi_dato="valor",
        otro_dato=42,
    )
```

Otros plugins pueden suscribirse a `"mi_evento_custom"` con el mismo `EventBus`.

---

## 🛠️ APIs disponibles

Tu plugin accede a `self.context` con estas APIs:

| API | Descripción |
|-----|-------------|
| `context.settings` | Leer/escribir configuración global y del plugin |
| `context.cameras` | Acceso a cámaras (listar, obtener, threads) |
| `context.frames` | Registro de pre/post processors, obtener último frame |
| `context.ui` | Añadir botones, menús, tabs, docks |
| `context.files` | Guardar/leer archivos, directorio de capturas |
| `context.notifications` | Enviar notificaciones |
| `context.timers` | Crear timers gestionados |
| `context.hooks` | HookRegistry (plugin ↔ plugin) |
| `context.event_bus` | EventBus (Core ↔ plugins) |
| `context.extensions` | ExtensionRegistry |
| `context.services` | CoreServices (fachada de alto nivel) |
| `self.logger` | Logger con namespace del plugin |

### Ejemplos

**Configuración:**

```python
# Leer config del plugin
config = self.context.settings.get_plugin_config(self.NAME)

# Guardar config del plugin
self.context.settings.set_plugin_config(self.NAME, {"key": "value"})

# Registrar schema para tipado
self.context.settings.register_config_schema(self.NAME, {
    "key": {"type": "str", "default": "value"},
})
```

**Cámaras:**

```python
cameras = self.context.cameras.get_all_cameras()
active = self.context.cameras.get_active_cameras()
camera = self.context.cameras.get_camera(camera_id=0)
thread = self.context.cameras.get_thread(camera_id=0)
```

**Timers:**

```python
self.context.timers.create(
    name=f"{self.NAME}.tick",
    interval_ms=1000,
    callback=self._tick,
    single_shot=False,
)
self.context.timers.stop(f"{self.NAME}.tick")
```

**Hooks (plugin ↔ plugin):**

```python
# Suscribirse a un hook
self.register_hook("mi_hook", self._on_mi_hook)

# Emitir un hook
self.emit_hook("mi_hook", value=42)
```

---

## 🔒 Capabilities y Sandbox

Las **capabilities** son permisos que tu plugin declara en `manifest.json`. El Core las verifica antes de permitir operaciones sensibles.

### Capabilities disponibles

| Capability | Permite |
|-----------|---------|
| `read_files` | Leer archivos del sistema |
| `write_files` | Escribir archivos |
| `file_delete` | Borrar archivos |
| `network` | Conexiones de red (HTTP, sockets) |
| `telegram` | Enviar mensajes por Telegram |
| `camera_access` | Acceso a frames y metadata de cámaras |
| `camera_control` | Controlar hardware de cámara (flash, PTZ) |
| `audio_access` | Acceso a audio |
| `system_info` | Info del sistema (CPU, RAM, GPU) |
| `process_execution` | Ejecutar subprocess |
| `settings_read` | Leer configuración |
| `settings_write` | Escribir configuración |
| `ui_modify` | Modificar la UI (añadir botones, tabs) |
| `notifications` | Enviar notificaciones |

### Modo estricto

En **modo estricto** (producción), si tu plugin intenta una operación sin la capability declarada, se bloquea con `PermissionError`.

En **modo dev** (debug), todo está permitido para facilitar el desarrollo.

### Módulos prohibidos (siempre bloqueados)

```python
FORBIDDEN_MODULES = {
    "ctypes", "cffi", "mmap", "fcntl", "winreg",
    "pty", "pwd", "spwd", "grp", "crypt",
}
```

### Módulos protegidos (requieren capability)

| Módulo | Capability |
|--------|-----------|
| `socket`, `ssl`, `http`, `urllib`, `requests` | `network` |
| `subprocess`, `multiprocessing` | `process_execution` |
| `sqlite3`, `pickle`, `marshal` | `write_files` / `read_files` |

### Verificar capabilities en runtime

```python
from core.extensions.types import Capability

if self.has_capability(Capability.NETWORK):
    import requests
    ...

# O lanzar excepción si no la tiene
self.require_capability(Capability.WRITE_FILES)
```

---

## 📚 Ejemplos completos

### Ejemplo 1: Plugin mínimo (solo eventos)

```python
# plugins/mi_plugin/__init__.py
# (vacío)

# plugins/mi_plugin/plugin.py
from core.plugin_api import BasePlugin
from core.events import MOTION_DETECTED, APP_CLOSING


class MiPlugin(BasePlugin):
    NAME = "mi_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "Registra movimientos en un archivo"

    def on_enable(self) -> bool:
        if self.context.event_bus is not None:
            self.context.event_bus.subscribe(
                MOTION_DETECTED, self._on_motion, owner=self.NAME
            )
            self.context.event_bus.subscribe(
                APP_CLOSING, self._on_app_closing, owner=self.NAME
            )
        return True

    def on_disable(self):
        if self.context.event_bus is not None:
            self.context.event_bus.unsubscribe(MOTION_DETECTED, self._on_motion)
            self.context.event_bus.unsubscribe(APP_CLOSING, self._on_app_closing)

    def _on_motion(self, camera_id, camera_name=None, **kwargs):
        self.logger.info(f"Movimiento: {camera_name}")

    def _on_app_closing(self, **kwargs):
        self.logger.info("Cerrando...")
```

### Ejemplo 2: FrameAnalyzer

```python
# plugins/mi_detector/plugin.py
from core.plugin_api import BasePlugin
from core.extensions.interfaces import FrameAnalyzer


class MiDetector:
    def analyze(self, camera_id, frame):
        # Aquí va tu detección (OpenCV, MediaPipe, etc.)
        return {"kind": "custom", "camera_id": camera_id, "data": ...}

    def should_run(self, camera_id):
        return True

    def get_frame_skip(self):
        return 5

    def cleanup(self, camera_id=None):
        pass


class MiDetectorPlugin(BasePlugin):
    NAME = "mi_detector"
    VERSION = "1.0.0"

    def on_enable(self) -> bool:
        self._analyzer = MiDetector()
        self.register_extension(FrameAnalyzer, self._analyzer, priority=120)
        return True

    def on_disable(self):
        if self._analyzer:
            self._analyzer.cleanup()
```

### Ejemplo 3: UIExtension + ConfigTab

```python
# plugins/mi_plugin/plugin.py
from core.plugin_api import BasePlugin
from core.extensions.interfaces import UIExtension, ConfigTab
from core.extensions.config_tab_provider import PluginConfigTabProvider


class MiUI:
    def get_id(self): return "mi_plugin.header"
    def get_target(self): return "camera_widget"
    def get_slot(self): return "header"
    def get_priority(self): return 120

    def get_widgets(self, context):
        from PySide6.QtWidgets import QPushButton
        camera = context["camera"]
        btn = QPushButton("🎯")
        btn.setToolTip(f"Mi botón en {camera.name}")
        return [btn]


class MiConfigTab:
    def __init__(self, plugin_name, context):
        self.plugin_name = plugin_name
        self.context = context
        self._widget = None

    def get_id(self): return "plugin_mi_plugin"
    def get_title(self): return "Mi Plugin"
    def get_icon(self): return "🎯"

    def get_widget(self):
        if self._widget is None:
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
            w = QWidget()
            l = QVBoxLayout(w)
            l.addWidget(QLabel("Configuración de mi plugin"))
            l.addStretch()
            self._widget = w
        return self._widget

    def on_save(self): return True
    def on_load(self): pass


class MiPlugin(BasePlugin):
    NAME = "mi_plugin"

    def on_enable(self) -> bool:
        self.register_extension(UIExtension, MiUI(), priority=120)

        provider = PluginConfigTabProvider(
            plugin_name=self.NAME,
            plugin_context=self.context,
            tab_class=MiConfigTab,
            tab_id="plugin_mi_plugin",
            title="Mi Plugin",
            icon="🎯",
        )
        self.register_extension(ConfigTab, provider, priority=180)
        return True
```

### Ejemplo 4: Grabación de audio en paralelo

Ver `plugins/audio/` para un ejemplo completo de:

- Suscribirse a `RECORDING_STARTED` / `RECORDING_STOPPED`
- Escribir WAV en paralelo mientras el Core graba video
- Mezclar al final con ffmpeg (si está disponible) o PyAV

---

## 📦 Empaquetado y distribución

### Crear un ZIP de plugin

```bash
# Desde la raíz del proyecto
cd plugins/
zip -r mi_plugin.zip mi_plugin/
```

El ZIP debe contener:

```
mi_plugin.zip
└── mi_plugin/           # (opcional: si no hay carpeta, se aplana)
    ├── plugin.py
    ├── manifest.json
    └── ...
```

### Instalar en ProCamera

**Vía GUI:**

1. `Configuración → 🔌 Plugins → 📦 Instalar ZIP`
2. Selecciona el `.zip`
3. Se extrae a `plugins_installed/<nombre>_<hash>/`

**Vía CLI:**

```python
from core.plugin_api import get_plugin_manager
pm = get_plugin_manager()
success, msg, name = pm.install_from_zip("mi_plugin.zip")
```

### Reglas de validación

Antes de instalar, el `PackageValidator` verifica:

- ✅ El ZIP contiene `plugin.py`
- ✅ `manifest.json` tiene `version`
- ✅ No hay path traversal (`../`)
- ✅ Extensiones permitidas (`.py`, `.json`, `.onnx`, etc.)
- ✅ Sin imports prohibidos (`ctypes`, `mmap`, etc.)
- ✅ Las capabilities declaradas cubren los imports sensibles

### Tamaño máximo

| Recurso | Límite |
|---------|--------|
| ZIP | 10 MB |
| Descomprimido | 50 MB |
| Archivos | 500 |

---

## 🐛 Debugging

### Activar logs del plugin

```python
def on_enable(self):
    self.logger.debug("Mi plugin activado")
    self.logger.info("Info útil")
    self.logger.warning("Algo raro")
    self.logger.error("Error", exc_info=True)
```

Los logs aparecen en:

- Archivos en `logs/` (`procamera_*.log`)
- Consola de debug (plugin `debug_console`, si está activo)

### Ver eventos del bus

En la consola de debug verás:

```
🔗 [bus] 'motion_detected' ← mi_plugin
🔗 [bus] 'motion_detected' con 2 suscriptores
```

### Ver extensiones registradas

En la consola de debug:

```
📦 [registry] FrameAnalyzer ← 'mi_plugin' (prio=100)
```

---

## 🚫 Reglas a evitar

### ❌ No importes del Core a plugins

```python
# MAL: esto acopla el Core a tu plugin
from core.engine import camera_engine
camera_engine.MI_PLUGIN_ACTIVO = True
```

```python
# BIEN: el Core no sabe que existes
self.context.event_bus.subscribe(MOTION_DETECTED, self._on_motion)
```

### ❌ No uses `try/except ImportError` para evitar crashes

```python
# MAL: si tu plugin no está, no debe afectar al Core
try:
    from mi_plugin import algo
except ImportError:
    pass
```

### ❌ No modifiques `context.event_bus` directamente

Usa siempre `subscribe` / `unsubscribe`. No accedas a `_subs` internos.

### ❌ No bloquees el event loop

Si tu handler hace trabajo pesado (OCR, HTTP, ML), usa un hilo:

```python
import threading

def _on_image_saved(self, path, frame=None, **kwargs):
    threading.Thread(target=self._do_ocr, args=(path, frame), daemon=True).start()
```

---

## 📞 Soporte

- 📖 Lee el código fuente de los plugins incluidos en `plugins/` como referencia
- 🐛 Reporta bugs en [Issues](../../issues)
- 💬 Discusiones en [Discussions](../../discussions)

---

<div align="center">
  <strong>¡Feliz desarrollo de plugins!</strong> 🔌
</div>