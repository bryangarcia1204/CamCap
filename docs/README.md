# 📷 ProCamera - Estación de Control para Cámaras IP

<div align="center">

![ProCamera Banner](https://img.shields.io/badge/ProCamera-v2.0-blueviolet?style=for-the-badge&logo=python)
![License](https://img.shields.io/github/license/tuusuario/ProCamera?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.0+-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.5+-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)

**Sistema profesional de videovigilancia que convierte teléfonos Android en cámaras IP inteligentes**

[Características](#-características) • [Instalación](#-instalación) • [Uso](#-uso) • [Contribuir](#-contribuir) • [Licencia](#-licencia)

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

### 🎨 UI/UX Premium

- **Glassmorphism Effect**: Diseño moderno con transparencias y blur
- **Paleta Azul-Morada**: Colores profesionales con alto contraste
- **Botones Ovalados**: Interfaz intuitiva y responsive
- **Modo Oscuro**: Por defecto, reduce la fatiga visual

### 🔒 Seguridad y Control

- **⚠️ Detección de Movimiento**: (Próximamente) Alertas inteligentes
- **📨 Notificaciones en Tiempo Real**: (Próximamente) Integración con Telegram
- **🔐 Gestión de Usuarios**: (Próximamente) Múltiples perfiles

---

## 🚀 Instalación

### Requisitos Previos

- Python 3.10 o superior
- pip (gestor de paquetes de Python)
- Git (opcional, para clonar el repositorio)

### Instalación desde Código Fuente

```bash
# Clonar el repositorio
git clone https://github.com/tuusuario/ProCamera.git
cd ProCamera

# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar la aplicación
python main.py
```

### Instalación con Ejecutable (Windows)

    Descarga el archivo ProCamera.exe desde Releases

    Ejecuta el archivo (no requiere instalación adicional)

# 📱 Configuración de Cámaras
## Paso 1: Instalar IP Webcam en tu teléfono

1. Descarga IP Webcam desde Google Play Store

2. Abre la app y toca "Iniciar Servidor"

3. Anota la IP y el puerto que aparecen en pantalla

## Paso 2: Configurar en ProCamera

1. Abre ProCamera en tu PC

2. Ve a Configuración → Cámaras

2. Haz clic en "Agregar" e ingresa:

        Nombre: Identificador de la cámara

        IP: La IP mostrada en tu teléfono

        Puerto: 8080 (por defecto)

        Tipo de URL: video o shot

4. Guarda y verás el stream de video en tiempo real

### 🎮 Uso
## Controles Principales
|Acción | Descripción|
|📸 Capturar | Toma una foto de la cámara seleccionada|
|📸 Capturar | Todas Toma fotos de todas las cámaras activas|
|🎬 Grabar | Inicia grabación de video|
|🎬 Grabar | Todas Graba video de todas las cámaras|
|⚙️ Configurar | Abre el panel de configuración|
|🔄 Auto |	Captura automática periódica|
## Atajos de Teclado
Tecla	Acción
Ctrl+N	Nuevo proyecto
Ctrl+Q	Salir
Ctrl+Shift+A	Agregar cámara
Ctrl+Shift+C	Capturar todas
Ctrl+,	Abrir configuración
F5	Refrescar vista
🏗️ Estructura del Proyecto
```text

ProCamera/
├── main.py                 # Punto de entrada
├── camera_engine.py        # Motor de cámaras IP
├── file_manager.py         # Gestión de archivos
├── models.py               # Modelos de datos
├── settings_manager.py     # Configuración persistente
├── resources/
│   ├── styles.qss          # Hoja de estilos CSS
│   └── icon.ico            # Icono de la aplicación
├── ui/
│   ├── main_window.py      # Ventana principal
│   ├── camera_widget.py    # Widget de cámara
│   ├── camera_grid.py      # Grid de cámaras
│   ├── file_explorer.py    # Explorador de archivos
│   ├── image_preview.py    # Visor de imágenes
│   └── settings_dialog.py  # Diálogo de configuración
├── requirements.txt        # Dependencias
├── LICENSE                 # Licencia MIT
└── README.md              # Este archivo
```
🤝 Contribuir

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

## Guía de Estilo

* **Python**: Sigue PEP 8

* **Commits**: Mensajes descriptivos en español o inglés

* **Documentación**: Actualiza el README si es necesario

## Reportar Issues

Si encuentras un bug o tienes una sugerencia:

1. Ve a la pestaña Issues

2. Haz clic en **"New Issue"**

3. Describe el problema o sugerencia con el mayor detalle posible

4. Adjunta logs o capturas de pantalla si es relevante

## 📊 Roadmap
### ✅ Completado

☑
Conexión con cámaras IP (IP Webcam)

☑
Captura de fotos (individual y masiva)

☑
Grabación de video

☑
Explorador de archivos

☑
Visor de imágenes

☑
Configuración de formatos y calidad

### 🚧 En Desarrollo

□
Detección de movimiento

□
Notificaciones vía Telegram

□
Exportación de videos

□
Programación de capturas

### 📅 Planificado

□
Reconocimiento facial

□
Almacenamiento en la nube

□
Múltiples perfiles de usuario

□
Dashboard analítico

# 📄 Licencia

Este proyecto está licenciado bajo la **MIT License** - ver el archivo [LICENSE](LICENSE) para más detalles.
# 👥 Autores

- Tu Nombre - Desarrollo inicial - @tuusuario

## Colaboradores
<a href="https://github.com/tuusuario/ProCamera/graphs/contributors"> <img src="https://contrib.rocks/image?repo=tuusuario/ProCamera" /> </a>

# 🙏 Agradecimientos

* **PySide6** - Framework Qt para Python

* **OpenCV** - Visión por computadora

* **IP Webcam** - App para Android

# 📞 Contacto

**Email**: tuemail@ejemplo.com

**GitHub**: github.com/tuusuario

**Twitter**: @tuusuario

<div align="center"> <sub>Hecho con ❤️ por la comunidad ProCamera</sub> </div>
