"""
Diálogo de auto-grabación con cuenta regresiva.
Usa TimerManager.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QProgressBar)
from PySide6.QtCore import Qt, Signal
from utils.logger import get_logger
from utils.timer_manager import timer_manager

logger = get_logger("AutoRecordDialog")


class AutoRecordDialog(QDialog):
    """Diálogo con cuenta regresiva para auto-grabar"""

    user_confirmed = Signal()
    user_cancelled = Signal()

    _instance_counter = 0

    def __init__(self, camera_name: str, timeout_seconds: int = 2, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.timeout_seconds = timeout_seconds
        self.elapsed_ms = 0

        AutoRecordDialog._instance_counter += 1
        self._timer_name = f"auto_record_dialog_{AutoRecordDialog._instance_counter}"

        self.setWindowTitle("🚨 Movimiento Detectado")
        self.setFixedSize(450, 220)
        self.setModal(True)
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )

        self._setup_ui()
        self._start_countdown()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:0.5 #1a237e, stop:1 #2a0a4a);
                border: 2px solid rgba(255, 80, 80, 0.5);
                border-radius: 16px;
            }
            QLabel { color: white; background: transparent; }
            QPushButton {
                border: none;
                border-radius: 50px;
                padding: 12px 24px;
                font-weight: 600;
                font-size: 13px;
                color: white;
            }
            QPushButton[type="danger"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c62828, stop:1 #e53935);
            }
            QPushButton[type="danger"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d32f2f, stop:1 #ef5350);
            }
            QPushButton[type="secondary"] {
                background: rgba(255,255,255,0.1);
                border: 1px solid rgba(255,255,255,0.2);
            }
            QPushButton[type="secondary"]:hover {
                background: rgba(255,255,255,0.2);
            }
            QProgressBar {
                background: rgba(255,255,255,0.1);
                border: none;
                border-radius: 4px;
                height: 8px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF9800, stop:1 #f44336);
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QLabel(f"🚨 Movimiento en {self.camera_name}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FF9800;")
        layout.addWidget(title)

        message = QLabel("¿Deseas grabar un video?")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 14px; color: rgba(255,255,255,0.85);")
        layout.addWidget(message)

        self.countdown_label = QLabel(f"{self.timeout_seconds}s...")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #f44336;"
        )
        layout.addWidget(self.countdown_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, self.timeout_seconds * 10)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()

        cancel_btn = QPushButton("❌ Cancelar")
        cancel_btn.setProperty("type", "secondary")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)

        record_btn = QPushButton("🎬 Grabar Ahora")
        record_btn.setProperty("type", "danger")
        record_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(record_btn)

        layout.addLayout(btn_layout)

    def _start_countdown(self):
        timer_manager.create(
            self._timer_name,
            100,
            self._tick,
            start=True
        )

    def _stop_timer(self):
        timer_manager.stop(self._timer_name)

    def _tick(self):
        self.elapsed_ms += 100
        self.progress.setValue(self.elapsed_ms // 100)

        remaining = self.timeout_seconds - (self.elapsed_ms / 1000)

        if remaining <= 0:
            self._stop_timer()
            self._on_timeout()
        else:
            self.countdown_label.setText(f"{remaining:.1f}s...")

    def _on_confirm(self):
        self._stop_timer()
        logger.info("Usuario confirmó grabar")
        self.user_confirmed.emit()
        self.accept()

    def _on_cancel(self):
        self._stop_timer()
        logger.info("Usuario canceló grabar")
        self.user_cancelled.emit()
        self.reject()

    def _on_timeout(self):
        logger.info("Timeout - grabando automáticamente")
        self.user_confirmed.emit()
        self.accept()

    def closeEvent(self, event):
        """Asegurar que el timer se detiene al cerrar"""
        self._stop_timer()
        super().closeEvent(event)