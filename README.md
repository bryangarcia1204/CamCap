# 📷 ProCamera - Estación de Control para Cámaras IP

<div align="center">

![ProCamera Banner](https://img.shields.io/badge/ProCamera-v2.0-blueviolet?style=for-the-badge&logo=python)
![License](https://img.shields.io/github/license/bryangarcia1204/CamCap?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.0+-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.5+-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)

**Sistema profesional de videovigilancia con arquitectura de plugins extensible**

[Características](#-características) • [Instalación](#-instalación) • [Uso](#-uso) • [Plugins](#-sistema-de-plugins) • [Contribuir](#-contribuir) • [Licencia](#-licencia)

</div>

---

## 📸 Vista Previa

<div align="center">
  <img src="screenshots/main_window.png" alt="Ventana Principal" width="800"/>
  <br>
  <em>Interfaz principal con efecto Glassmorphism y múltiples cámaras</em>
</div>

---

## ✨ Características

### 🎯 Funcionalidades Principales

- **📹 Múltiples Cámaras IP**: Conecta y gestiona varios teléfonos Android como cámaras de seguridad
- **📸 Captura Instantánea**: Toma fotos con un solo clic (individual o masiva)
- **🎬 Grabación de Video**: Graba video en tiempo real con soporte para múltiples formatos
- **📁 Explorador de Archivos**: Navegador estilo VSCode para gestionar capturas
- **🖼️ Visor de Imágenes**: Previsualización con zoom y navegación
- **⚙️ Configuración Completa**: Personaliza formatos, calidad, directorios y más
- **🔌 Sistema de Plugins**: Arquitectura extensible vía eventos y registry

### 🎨 UI/UX Premium

- **Glassmorphism Effect**: Diseño moderno con transparencias y blur
- **Paleta Azul-Morada**: Colores profesionales con alto contraste
- **Botones Ovalados**: Interfaz intuitiva y responsive
- **Modo Oscuro**: Por defecto, reduce la fatiga visual

### 🔒 Seguridad y Control

- **⚠️ Detección de Movimiento**: Plugin oficial con MOG2/KNN/frame_diff
- **👤 Reconocimiento Facial**: Plugin oficial con SFace/YuNet/dlib/MediaPipe
- **📄 Escaneo de Documentos**: Plugin oficial con Tesseract OCR
- **📨 Notificaciones**: Plugin oficial para Windows y Telegram
- **🎵 Audio**: Plugin oficial con soporte de mute y grabación paralela
- **🎨 Mejora de Imágenes**: Plugin oficial con análisis de calidad y presets

---

## 🏗️ Arquitectura

ProCamera está construido con una **arquitectura de plugins extensible** donde:

- **El Core es totalmente autosuficiente**: funciona sin ningún plugin instalado.
- **El Core NO conoce plugins específicos**: solo expone puntos de extensión genéricos.
- **Los plugins se enganchan vía `EventBus` y `ExtensionRegistry`**: sin acoplamiento.
- **Sin dependencias circulares**: el Core no importa de `plugins/`.

```
Core (autosuficiente)
├── EventBus (genérico)
├── ExtensionRegistry (genérico)
└── Puntos de extensión genéricos:
    ├── CameraProvider / CameraDetector / CameraLifecycleListener
    ├── FramePreProcessor / FramePostProcessor / FrameAnalyzer
    ├── UIExtension / ToolbarProvider / MenuProvider
    ├── ConfigTab / ConfigSection / ConfigWidget
    ├── VideoOverlay / StatusWidget / DialogProvider
    ├── KeyboardInterceptor / MouseInterceptor
    ├── AppLifecycleHook / StartupHook / ShutdownHook
    ├── ThemeProvider / IconProvider
    ├── FileHandler / StorageProvider / ImportProvider / ExportProvider
    ├── PluginWrapper / PluginLifecycleHook / PluginValidator
    ├── NotificationProvider
    └── TaskScheduler

Plugins (opt-in)
├── motion_detector   → FrameAnalyzer
├── face_recognizer   → FrameAnalyzer
├── document_scanner  → FrameAnalyzer + escucha IMAGE_SAVED
├── audio             → UIExtension + escucha RECORDING_*
├── notifications     → ConfigTab + escucha MOTION_DETECTED, FACE_DETECTED
├── image_enhancer    → UIExtension
├── camera_controls   → UIExtension (flash)
└── debug_console     → ConfigTab (solo modo debug)
```

Ver **[PLUGINS.md](PLUGINS.md)** para la guía completa de desarrollo de plugins.

---

## 🚀 Instalación

### Requisitos Previos

- Python 3.10 o superior
- pip (gestor de paquetes de Python)
- Git (opcional, para clonar el repositorio)

### Instalación desde Código Fuente

```bash
# Clonar el repositorio
git clone https://github.com/bryangarcia1204/CamCap.git
cd CamCap

# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate      # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar la aplicación
python main.py
```

### Instalación con Ejecutable (Windows)

1. Descarga el archivo `ProCamera.exe` desde [Releases](../../releases)
2. Ejecuta el archivo (no requiere instalación adicional)
3. Los plugins se cargan automáticamente desde la carpeta `plugins/`

---

## 📱 Configuración de Cámaras

### Paso 1: Instalar IP Webcam en tu teléfono

1. Descarga **IP Webcam** desde Google Play Store
2. Abre la app y toca **"Iniciar Servidor"**
3. Anota la IP y el puerto que aparecen en pantalla

### Paso 2: Configurar en ProCamera

1. Abre ProCamera en tu PC
2. Ve a **Configuración → 📷 Cámaras**
3. Haz clic en **"➕ IP"** e ingresa:

| Campo | Descripción |
|-------|-------------|
| Nombre | Identificador de la cámara |
| IP | La IP mostrada en tu teléfono |
| Puerto | `8080` (por defecto) |
| Tipo de URL | `video` o `shot` |

4. Guarda y verás el stream de video en tiempo real

---

## 🎮 Uso

### Controles Principales

| Acción | Descripción |
|--------|-------------|
| 📸 Capturar | Toma una foto de la cámara seleccionada |
| 📸 Capturar Todas | Toma fotos de todas las cámaras activas |
| 🎬 Grabar | Inicia grabación de video |
| 🎬 Grabar Todas | Graba video de todas las cámaras |
| ⚙️ Configurar | Abre el panel de configuración |
| 🔄 Auto | Captura automática periódica |
| 🎤 Mic PC | Activa/desactiva el micrófono del PC (plugin audio) |
| 🔊 Audio cámara | Activa el audio de una cámara IP (plugin audio) |
| 🔇 Mute | Silencia sin detener la captura (plugin audio) |
| 🔦 Flash | Controla el flash de la cámara IP (plugin camera_controls) |
| ⚡ Auto-flash | Flash automático al detectar movimiento |

### Atajos de Teclado

| Tecla | Acción |
|-------|--------|
| `Ctrl+N` | Nuevo proyecto |
| `Ctrl+Q` | Salir |
| `Ctrl+Shift+A` | Agregar cámara |
| `Ctrl+Shift+C` | Capturar todas |
| `Ctrl+,` | Abrir configuración |
| `F5` | Refrescar vista |

---

## 🔌 Sistema de Plugins

ProCamera incluye un **sistema de plugins completo** con:

- **Carga dinámica** desde carpetas o ZIPs
- **Activación/desactivación en caliente** sin reiniciar
- **Sandbox de seguridad** con capabilities
- **Aislamiento de fallos**: un plugin roto no tumba la app
- **Instalación desde ZIP** vía GUI o CLI

### Plugins Incluidos

| Plugin | Descripción | Capabilities |
|--------|-------------|--------------|
| 🎵 `audio` | Audio de cámaras IP + micrófono PC | `audio_access` |
| 🔦 `camera_controls` | Control de flash de cámara IP | `camera_control` |
| 🐛 `debug_console` | Consola de logs (solo modo debug) | `ui_modify` |
| 📄 `document_scanner` | OCR con Tesseract | `camera_access` |
| 👤 `face_recognizer` | Reconocimiento facial (SFace/dlib/MediaPipe) | `camera_access` |
| 🎨 `image_enhancer` | Mejora de imágenes con presets | — |
| 🚶 `motion_detector` | Detección de movimiento (MOG2/KNN/frame_diff) | `camera_access` |
| 🔔 `notifications` | Windows + Telegram | `network`, `notifications`, `telegram` |

### Gestión de Plugins

**Vía GUI:** `Configuración → 🔌 Plugins → Abrir Administrador`

**Vía manifest:** Edita `plugins/manifest.json`:

```json
{
  "plugins": {
    "motion_detector": {
      "enabled_by_default": true,
      "auto_load": true,
      "capabilities": ["camera_access"]
    }
  }
}
```

### Instalar desde ZIP

1. Empaqueta tu plugin como `.zip` (con `plugin.py` + `manifest.json`)
2. `Configuración → 🔌 Plugins → 📦 Instalar ZIP`
3. El ZIP se extrae a `plugins_installed/` y se carga automáticamente

### Crear tu propio plugin

Ver **[PLUGINS.md](PLUGINS.md)** para la guía completa. Ejemplo mínimo:

```python
# plugins/mi_plugin/plugin.py
from core.plugin_api import BasePlugin
from core.events import MOTION_DETECTED


class MiPlugin(BasePlugin):
    NAME = "mi_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "Plugin de ejemplo"

    def on_enable(self) -> bool:
        # Suscribirse a eventos del Core
        if self.context.event_bus is not None:
            self.context.event_bus.subscribe(
                MOTION_DETECTED,
                self._on_motion,
                owner=self.NAME,
            )
        return True

    def on_disable(self):
        if self.context.event_bus is not None:
            self.context.event_bus.unsubscribe(MOTION_DETECTED, self._on_motion)

    def _on_motion(self, camera_id, camera_name=None, **kwargs):
        self.logger.info(f"Movimiento en {camera_name} (camera_id={camera_id})")
```

---

## 🏗️ Estructura del Proyecto

```
CamCap/
├── main.py                      # Punto de entrada
├── core/                        # Núcleo (autosuficiente, no importa de plugins/)
│   ├── event_bus.py             # EventBus genérico
│   ├── events.py                # Nombres de eventos del dominio
│   ├── extension_registry.py    # Registry de extensiones
│   ├── extensions/              # Sistema de puntos de extensión
│   │   ├── interfaces.py        # Protocols genéricos
│   │   ├── types.py             # Enums y dataclasses
│   │   ├── capability_checker.py
│   │   ├── sandbox.py
│   │   └── services.py
│   ├── plugin_api/              # API de plugins
│   │   ├── base_plugin.py
│   │   ├── plugin_manager.py
│   │   ├── hooks.py
│   │   └── interfaces.py
│   ├── engine/                  # Motores de captura
│   │   ├── camera_engine.py
│   │   ├── local_camera_engine.py
│   │   ├── screen_camera_engine.py
│   │   └── builtin_providers.py
│   ├── file_manager.py
│   ├── settings_manager.py
│   └── models.py
├── plugins/                     # Plugins (opt-in)
│   ├── manifest.json
│   ├── audio/
│   ├── camera_controls/
│   ├── debug_console/
│   ├── document_scanner/
│   ├── face_recognizer/
│   ├── image_enhancer/
│   ├── motion_detector/
│   ├── notifications/
│   ├── package_loader.py
│   └── package_validator.py
├── plugins_installed/           # Plugins instalados desde ZIP
├── ui/                          # Interfaz gráfica
│   ├── main_window.py
│   ├── camera_widget.py
│   ├── camera_grid.py
│   ├── file_explorer.py
│   ├── image_preview.py
│   ├── settings_dialog.py
│   ├── settings_dialog_base.py
│   └── ...
├── utils/                       # Utilidades
├── resources/                   # Recursos (QSS, iconos)
├── tests/                       # Tests
├── requirements.txt
├── PLUGINS.md                   # Guía de desarrollo de plugins
├── LICENSE
└── README.md
```

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Sigue estos pasos:

1. Fork el repositorio
2. Crea una rama para tu feature:

   ```bash
   git checkout -b feature/NuevaFuncionalidad
   ```

3. Realiza tus cambios y haz commit:

   ```bash
   git commit -m "Añadida: Nueva funcionalidad X"
   ```

4. Sube los cambios:

   ```bash
   git push origin feature/NuevaFuncionalidad
   ```

5. Abre un Pull Request en GitHub

### Guía de Estilo

- **Python**: Sigue PEP 8
- **Commits**: Mensajes descriptivos en español o inglés
- **Documentación**: Actualiza el README si es necesario
- **Plugins**: Sigue la guía en `PLUGINS.md`

### Reportar Issues

1. Ve a la pestaña [Issues](../../issues)
2. Haz clic en **"New Issue"**
3. Describe el problema o sugerencia con el mayor detalle posible
4. Adjunta logs o capturas de pantalla si es relevante

---

## 📊 Roadmap

### ✅ Completado

- [x] Conexión con cámaras IP (IP Webcam)
- [x] Captura de fotos (individual y masiva)
- [x] Grabación de video con audio
- [x] Explorador de archivos
- [x] Visor de imágenes y videos
- [x] Configuración de formatos y calidad
- [x] Sistema de plugins extensible
- [x] Event bus y registry genéricos
- [x] Detección de movimiento (plugin)
- [x] Reconocimiento facial (plugin)
- [x] Notificaciones Windows + Telegram (plugin)
- [x] Escaneo de documentos con OCR (plugin)
- [x] Audio IP + micrófono PC (plugin)
- [x] Mejora de imágenes (plugin)
- [x] Control de flash (plugin)

### 🚧 En Desarrollo

- [ ] Exportación de datos de detección a Blender/MakeHuman
- [ ] Dashboard analítico
- [ ] Almacenamiento en la nube
- [ ] Múltiples perfiles de usuario

### 📅 Planificado

- [ ] API REST para control remoto
- [ ] Integración con sistemas domóticos
- [ ] Detección de objetos con YOLO
- [ ] Streaming RTSP

---

## 📄 Licencia

Este proyecto está licenciado bajo la **MIT License** - ver el archivo [LICENSE](LICENSE) para más detalles.

---

## 👥 Autores

- **Brayan García** - Desarrollo inicial - [@bryangarcia1204](https://github.com/bryangarcia1204)

---

## 🙏 Agradecimientos

- **PySide6** - Framework Qt para Python
- **OpenCV** - Visión por computadora
- **IP Webcam** - App para Android
- **FFmpeg** - Procesamiento de video/audio
- **Tesseract** - OCR
- **MediaPipe** - Detección de poses (futuro)

---

<div align="center">
  <sub>Hecho con ❤️ por la comunidad ProCamera</sub>
</div>