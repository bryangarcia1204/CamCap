markdown

# 🎵 Audio Plugin

Captura y reproducción de audio para cámaras IP y micrófono del PC.

## Features

- **Audio IP**: desde endpoints `/audio.wav` o `/audio.pcm`
- **Micrófono local**: usa el micrófono del PC
- **Mute independiente**: silencia sin detener la captura
- **VU meter**: visualización en tiempo real

## Uso

1. En cada cámara, haz clic en el botón 🔊 del header
2. El audio se reproducirá y aparecerá un VU meter
3. Usa 🔇 para silenciar

## Código de ejemplo

```python
from plugins.audio.audio_manager import audio_manager

audio_manager.start_camera_audio(
    camera_id=0,
    ip="192.168.1.100",
    port=8080,
    volume=0.7,
)
```

# Tabla de configuración
| Parámetro	| Tipo	| Default | Descripción |
|-----------|-------|---------|-------------|
| sample_rate | int	| 44100	| Sample rate en Hz|
| channels	| int	| 1	| 1=mono, 2=stereo |
| volume	| float	| 0.7	| Volumen inicial |
| mute	| bool	| False	| Estado de mute |

# Dependencias

* `sounddevice`

* `numpy`

* Opcional: `ffmpeg`

| **Nota**: si usas mute, la captura sigue activa.