"""
DEPRECATED: módulo audio migrado a plugins/audio/.

Este shim mantiene compatibilidad con imports legacy.
"""
import warnings

warnings.warn(
    "El módulo 'audio' está deprecado. "
    "Usa 'plugins.audio' en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

from plugins.audio import (
    AudioManager,
    AudioSource,
    AudioStreamBase,
    CameraAudioStream,
    LocalAudioStream,
    audio_manager,
)

__all__ = [
    "AudioManager",
    "AudioSource",
    "AudioStreamBase",
    "CameraAudioStream",
    "LocalAudioStream",
    "audio_manager",
]