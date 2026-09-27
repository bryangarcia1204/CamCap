"""
Widget de monitoreo de sistema: CPU, GPU, RAM
Diseñado para ir en la toolbar.
Usa TimerManager y Signal (thread-safe).
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from utils.system_monitor import system_monitor
from utils.timer_manager import timer_manager


class MiniBarWidget(QWidget):
    """Barra mini de progreso con etiqueta"""

    def __init__(self, label: str, color: str = "#4da0c4",
                 show_text: bool = True, parent=None):
        super().__init__(parent)
        self.label = label
        self.color = QColor(color)
        self.show_text = show_text
        self._value = 0.0

        self.setMinimumWidth(70)
        self.setMaximumWidth(120)
        self.setFixedHeight(28)

    def set_value(self, value: float):
        value = max(0.0, min(100.0, value))
        if abs(value - self._value) > 0.5:
            self._value = value
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        bg = QColor(0, 0, 0, 60)
        painter.fillRect(0, 0, w, h, bg)

        bar_h = 4
        bar_y = h - bar_h - 2
        bar_w = w - 4

        painter.fillRect(2, bar_y, bar_w, bar_h, QColor(255, 255, 255, 30))

        fill_w = int(bar_w * (self._value / 100.0))

        if self._value < 60:
            fill_color = QColor(76, 175, 80)
        elif self._value < 85:
            fill_color = QColor(255, 152, 0)
        else:
            fill_color = QColor(244, 67, 54)

        painter.fillRect(2, bar_y, fill_w, bar_h, fill_color)

        if self.show_text:
            painter.setPen(QColor(255, 255, 255, 220))
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)

            text = f"{self.label} {int(self._value)}%"
            painter.drawText(0, 0, w, bar_y, Qt.AlignCenter, text)

        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRect(0, 0, w - 1, h - 1)


class SystemMonitorWidget(QWidget):
    """Widget con 3 mini-barras: CPU, GPU, RAM"""

    # Señal interna thread-safe para pasar métricas al hilo GUI
    _metrics_received = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tm = timer_manager
        self._owner = "system_monitor_widget"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self.cpu_widget = MiniBarWidget("CPU", "#4da0c4")
        layout.addWidget(self.cpu_widget)

        self.gpu_widget = MiniBarWidget("GPU", "#8e24aa")
        layout.addWidget(self.gpu_widget)

        self.ram_widget = MiniBarWidget("RAM", "#2e7d32")
        layout.addWidget(self.ram_widget)

        self.setToolTip("Monitoreo de sistema\nCPU, GPU, RAM")

        if not system_monitor.has_gpu():
            self.gpu_widget.setVisible(False)
            self.setToolTip("Monitoreo de sistema\nCPU, RAM\n(GPU no detectada)")

        # Conectar señal interna al slot de aplicación (hilo GUI)
        self._metrics_received.connect(self._apply_metrics)

        # Timer gestionado por TimerManager
        self._tm.create_group(self._owner, [
            ("update", 100, self._update, False),
        ])

        # Registrar callback del monitor
        system_monitor.register_callback(self._on_metrics)

    def _on_metrics(self, metrics: dict):
        """Callback desde SystemMonitor (otro hilo) - emite señal thread-safe"""
        try:
            self._metrics_received.emit(metrics)
        except RuntimeError:
            # Widget ya destruido
            pass

    def _apply_metrics(self, metrics: dict):
        """Aplica métricas al widget (siempre en hilo GUI)"""
        self.cpu_widget.set_value(metrics.get("cpu_percent", 0))
        self.ram_widget.set_value(metrics.get("ram_percent", 0))
        self.gpu_widget.set_value(metrics.get("gpu_percent", 0))

        cpu = metrics.get("cpu_percent", 0)
        ram_pct = metrics.get("ram_percent", 0)
        ram_used = metrics.get("ram_used_gb", 0)
        ram_total = metrics.get("ram_total_gb", 0)

        gpu = metrics.get("gpu_percent", 0)
        gpu_mem = metrics.get("gpu_mem_percent", 0)
        gpu_temp = metrics.get("gpu_temp", 0)
        gpu_name = metrics.get("gpu_name", "")

        tooltip = f"<b>CPU:</b> {cpu:.1f}%<br>"
        tooltip += f"<b>RAM:</b> {ram_pct:.1f}% ({ram_used:.1f}/{ram_total:.1f} GB)<br>"

        if metrics.get("gpu_available"):
            tooltip += f"<b>GPU:</b> {gpu:.1f}%<br>"
            tooltip += f"<b>VRAM:</b> {gpu_mem:.1f}%<br>"
            if gpu_temp > 0:
                tooltip += f"<b>Temp:</b> {gpu_temp}°C<br>"
            if gpu_name:
                tooltip += f"<i>{gpu_name}</i>"

        self.setToolTip(tooltip)

    def _update(self):
        """Actualización forzada por timer"""
        metrics = system_monitor.get_metrics()
        self._apply_metrics(metrics)

    def cleanup(self):
        """Limpia recursos"""
        self._tm.stop_group(self._owner)
        try:
            system_monitor.unregister_callback(self._on_metrics)
        except Exception:
            pass