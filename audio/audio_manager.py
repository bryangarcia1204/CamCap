"""
DEPRECATED: movido a plugins/audio/.

Shim de compatibilidad. El singleton `audio_manager` sigue siendo
el MISMO objeto, porque `plugins.audio.audio_manager` exporta el mismo.
"""
import warnings

warnings.warn(
    "audio.audio_manager está deprecado. "
    "Usa plugins.audio.audio_manager en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

from plugins.audio.audio_manager import (
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