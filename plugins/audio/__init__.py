"""
Plugin de audio.

Incluye:
- AudioManager (singleton con streams de audio)
- CameraAudioStream (audio desde cámara IP)
- LocalAudioStream (micrófono del PC)
"""
from .audio_manager import (
    AudioManager,
    AudioSource,
    AudioStreamBase,
    CameraAudioStream,
    LocalAudioStream,
    audio_manager,
)
from .plugin import AudioPlugin

__all__ = [
    "AudioManager",
    "AudioSource",
    "AudioStreamBase",
    "CameraAudioStream",
    "LocalAudioStream",
    "audio_manager",
    "AudioPlugin",
]