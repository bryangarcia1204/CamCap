# 🐛 Debug Console

Plugin de consola de logs en tiempo real para CamCap.

## Características

- 📜 **Logs en tiempo real** desde el sistema de logging de CamCap
- 🎨 **Colores por nivel**: DEBUG (gris), INFO (blanco), WARNING (amarillo), ERROR (rojo), CRITICAL (rojo intenso)
- 🔍 **Filtro por nivel** desde la toolbar
- 📌 **Auto-scroll** configurable
- 🗑️ **Botón de limpiar** consola
- 📊 **Contador de líneas** en la toolbar
- ⌨️ **Atajo `Ctrl+Alt+C × 3`** para mostrar/ocultar la consola
- 💾 **Configuración persistente** (máximo de líneas, auto-scroll)

## Requisitos

- **Solo se carga en modo debug.** Para activarlo:
  - `Configuración → Debug → Modo depuración ✅`
  - Reinicia CamCap.

## Uso

### Abrir la consola

Presiona **`Ctrl+Alt+C` tres veces seguidas** (en menos de 1 segundo entre pulsaciones).

Verás un dock widget en la parte inferior de la ventana con los logs más recientes.

### Cerrar la consola

Repite el mismo atajo (`Ctrl+Alt+C` × 3) o cierra el dock con la X.

### Filtros

En la toolbar de la consola:

- **Nivel**: muestra solo los logs de ese nivel y superiores.
  - `Todos` → DEBUG, INFO, WARNING, ERROR, CRITICAL
  - `INFO` → INFO, WARNING, ERROR, CRITICAL
  - `WARNING` → WARNING, ERROR, CRITICAL
  - `ERROR` → ERROR, CRITICAL
  - `CRITICAL` → solo CRITICAL
- **Auto-scroll**: si está activo, baja automáticamente al llegar logs nuevos.
- **🗑️ Limpiar**: vacía el contenido.

## Configuración

Disponible en `Configuración → 🐛 Debug Console`:

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `max_lines` | int | 5000 | Máximo de líneas en memoria |
| `auto_scroll` | bool | True | Bajar automáticamente al llegar logs |

## Detalles técnicos

- Los logs llegan vía `QtLogHandler` (`utils.logger`).
- El handler usa `Signal` con `Qt.QueuedConnection` para ser thread-safe.
- Al superar `max_lines`, se eliminan las líneas más antiguas.
- El atajo se registra como `QShortcut` con contexto `ApplicationShortcut`.

## Limitaciones

- La consola **no filtra logs por texto** (solo por nivel).
- Los logs se muestran en el orden en que llegan al handler.
- Si el plugin se desactiva, la consola se destruye y los logs dejan de capturarse (siguen yendo a archivos de log normalmente).

## Archivos del plugin

```
plugins/debug_console/
├── __init__.py
├── plugin.py              # Clase DebugConsolePlugin
├── console.py             # Widget DebugConsole
├── config_tab.py          # ConfigTab del plugin
├── manifest.json
└── README.md
```

## Ver también

- [`PLUGINS.md`](../../PLUGINS.md) — guía completa de desarrollo de plugins
- [`README.md`](../../README.md) — documentación general de CamCap