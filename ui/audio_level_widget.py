"""
Widget de medidor de nivel de audio (VU meter) con gradiente.
FIX v2: Un solo timer COMPARTIDO para todas las instancias.
"""
import threading
from typing import List

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from utils.timer_manager import timer_manager
from utils.logger import get_logger

logger = get_logger("AudioLevelWidget")


class AudioLevelWidget(QWidget):
    """
    Medidor de nivel de audio estilo VU.

    ✅ FIX: Todas las instancias comparten UN SOLO QTimer a 30ms.
    Antes, cada widget creaba su propio timer, lo que saturaba el
    event loop cuando había muchas cámaras.

    Modos:
        - 'horizontal': Barra horizontal (bajo el video)
        - 'vertical': Barra vertical (al lado)
        - 'compact': Versión mini (cabecera)
    """

    # ✅ Timer compartido entre TODAS las instancias
    _shared_timer_name = "audio_level_widgets_shared"
    _instances: List["AudioLevelWidget"] = []
    _instances_lock = threading.Lock()

    def __init__(self, mode: str = "horizontal", parent=None):
        super().__init__(parent)
        self.mode = mode

        self._level = 0.0
        self._peak = 0.0
        self._peak_decay = 0.0

        self._segments = 20
        self._show_peak = True
        self._show_scale = (mode == "horizontal")

        self._smooth_factor = 0.3
        self._peak_hold_ms = 800
        self._peak_hold_timer = 0

        if mode == "vertical":
            self.setMinimumWidth(12)
            self.setMaximumWidth(20)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        elif mode == "compact":
            self.setMinimumHeight(8)
            self.setMaximumHeight(12)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setMinimumHeight(12)
            self.setMaximumHeight(20)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # ✅ Registrar instancia en el registro compartido
        with AudioLevelWidget._instances_lock:
            AudioLevelWidget._instances.append(self)

        # ✅ Crear el timer COMPARTIDO solo si no existe
        if not timer_manager.exists(self._shared_timer_name):
            timer_manager.create(
                self._shared_timer_name,
                30,
                AudioLevelWidget._tick_all,
                start=True
            )
            logger.debug(f"Timer compartido creado: {self._shared_timer_name}")

    @classmethod
    def _tick_all(cls):
        """Callback del timer compartido: actualiza todas las instancias vivas."""
        with cls._instances_lock:
            instances = list(cls._instances)

        dead = []
        for widget in instances:
            try:
                widget._decay()
            except RuntimeError:
                # El widget C++ fue destruido
                dead.append(widget)
            except Exception as e:
                logger.debug(f"Error en _tick_all: {e}")
                dead.append(widget)

        # ✅ Limpiar instancias muertas
        if dead:
            with cls._instances_lock:
                for w in dead:
                    if w in cls._instances:
                        cls._instances.remove(w)

    def set_level(self, level: float):
        """Actualiza el nivel actual (0.0 - 1.0)"""
        level = max(0.0, min(1.0, level))

        self._level = self._level * self._smooth_factor + level * (1 - self._smooth_factor)

        if level > self._peak:
            self._peak = level
            self._peak_hold_timer = self._peak_hold_ms

        self.update()

    def _decay(self):
        """Decae el nivel gradualmente cuando no hay señal"""
        needs_update = False

        if self._level > 0.001:
            self._level = max(0.0, self._level - 0.02)
            needs_update = True

        if self._peak_hold_timer > 0:
            self._peak_hold_timer -= 30
        elif self._peak > 0.001:
            self._peak = max(0.0, self._peak - 0.01)
            needs_update = True

        # ✅ Solo llamar a update() si hay cambios reales
        if needs_update:
            self.update()

    def reset(self):
        """Reinicia el medidor"""
        self._level = 0.0
        self._peak = 0.0
        self._peak_hold_timer = 0
        self.update()

    def cleanup(self):
        """
        ✅ Limpia la instancia del registro compartido.
        El timer compartido se mantiene vivo (otras instancias pueden usarlo).
        """
        with AudioLevelWidget._instances_lock:
            if self in AudioLevelWidget._instances:
                AudioLevelWidget._instances.remove(self)

        # Si ya no quedan instancias, detener el timer compartido
        with AudioLevelWidget._instances_lock:
            remaining = len(AudioLevelWidget._instances)

        if remaining == 0 and timer_manager.exists(self._shared_timer_name):
            timer_manager.stop(self._shared_timer_name)

    def _get_color_for_value(self, value: float) -> QColor:
        """Color según nivel (verde → amarillo → rojo)"""
        if value < 0.6:
            t = value / 0.6
            r = int(76 + (255 - 76) * t)
            g = int(175 + (193 - 175) * t)
            b = int(80 + (7 - 80) * t)
        elif value < 0.85:
            t = (value - 0.6) / 0.25
            r = 255
            g = int(193 - (152 - 193) * t)
            b = 7
        else:
            t = (value - 0.85) / 0.15
            r = 255
            g = int(152 * (1 - t))
            b = int(0 + 50 * t)
        return QColor(r, g, b)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        bg_color = QColor(20, 25, 60, 180)
        painter.fillRect(0, 0, w, h, bg_color)

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        if self.mode in ("horizontal", "compact"):
            self._draw_horizontal(painter, w, h)
        else:
            self._draw_vertical(painter, w, h)

    def _draw_horizontal(self, painter: QPainter, w: int, h: int):
        margin = 2
        bar_x = margin
        bar_y = margin
        bar_w = w - margin * 2
        bar_h = h - margin * 2

        if bar_w <= 0 or bar_h <= 0:
            return

        level_w = int(bar_w * self._level)

        seg_w = bar_w / self._segments
        for i in range(self._segments):
            seg_x = bar_x + i * seg_w
            seg_end = seg_x + seg_w - 1
            threshold = (i + 1) / self._segments

            if seg_end <= bar_x + level_w:
                color = self._get_color_for_value(threshold)
                painter.fillRect(
                    int(seg_x), bar_y,
                    int(seg_w - 1), bar_h,
                    color
                )

        if self._show_peak and self._peak > 0.01:
            peak_x = bar_x + int(bar_w * self._peak)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            painter.drawLine(peak_x, bar_y, peak_x, bar_y + bar_h)

        if self._show_scale and self.mode == "horizontal":
            painter.setPen(QColor(255, 255, 255, 180))
            painter.setFont(self.font())
            text = f"{int(self._level * 100)}%"
            painter.drawText(w - 40, 0, 38, h, Qt.AlignRight | Qt.AlignVCenter, text)

    def _draw_vertical(self, painter: QPainter, w: int, h: int):
        margin = 2
        bar_x = margin
        bar_y = margin
        bar_w = w - margin * 2
        bar_h = h - margin * 2

        if bar_w <= 0 or bar_h <= 0:
            return

        level_h = int(bar_h * self._level)

        seg_h = bar_h / self._segments
        for i in range(self._segments):
            seg_y = bar_y + bar_h - (i + 1) * seg_h
            threshold = (i + 1) / self._segments

            if seg_h * (i + 1) <= level_h:
                color = self._get_color_for_value(threshold)
                painter.fillRect(
                    bar_x, int(seg_y),
                    bar_w, int(seg_h - 1),
                    color
                )

        if self._show_peak and self._peak > 0.01:
            peak_y = bar_y + bar_h - int(bar_h * self._peak)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            painter.drawLine(bar_x, peak_y, bar_x + bar_w, peak_y)