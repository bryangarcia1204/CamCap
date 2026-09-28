"""
Overlay de carga para operaciones pesadas.
Usa TimerManager para los timers de animación.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QFrame, QProgressBar, QPushButton,
                               QGraphicsDropShadowEffect, QApplication)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation
from PySide6.QtGui import QColor, QPainter

from utils.timer_manager import timer_manager


class LoadingOverlay(QWidget):
    """Overlay semi-transparente con indicador de carga"""

    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        from utils.config_loader import advanced_config
        fade_duration = advanced_config.get("loading_fade_duration", 200)

        self._is_indeterminate = False
        self._owner = f"loading_overlay_{id(self)}"

        self._setup_ui()

        self._dots_count = 0
        self._spinner_index = 0
        self._spinner_frames = ["⏳", "⌛"]

        # Animación de aparición (QPropertyAnimation, gestionada por Qt)
        self.setWindowOpacity(0)
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(fade_duration)
        self.fade_in.setStartValue(0)
        self.fade_in.setEndValue(1)

        self.hide()

    def _setup_ui(self):
        """Configura la interfaz del overlay"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setAlignment(Qt.AlignCenter)

        self.card = QFrame()
        self.card.setFixedSize(360, 200)
        self.card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(13, 20, 69, 0.95),
                    stop:0.5 rgba(26, 35, 126, 0.95),
                    stop:1 rgba(42, 10, 74, 0.95));
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 20px;
            }
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(15)

        self.spinner_label = QLabel("⏳")
        self.spinner_label.setAlignment(Qt.AlignCenter)
        self.spinner_label.setStyleSheet("font-size: 48px; background: transparent;")
        card_layout.addWidget(self.spinner_label)

        self.status_label = QLabel("Cargando...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "font-size: 15px; color: white; font-weight: 600; background: transparent;"
        )
        card_layout.addWidget(self.status_label)

        self.detail_label = QLabel("")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.6); background: transparent;"
        )
        card_layout.addWidget(self.detail_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.1);
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:0.5 #6a1b9a, stop:1 #4da0c4);
                border-radius: 2px;
            }
        """)
        self.progress_bar.setVisible(False)
        card_layout.addWidget(self.progress_bar)

        outer_layout.addWidget(self.card, alignment=Qt.AlignCenter)

    def _rotate_spinner(self):
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self.spinner_label.setText(self._spinner_frames[self._spinner_index])

    def _animate_dots(self):
        self._dots_count = (self._dots_count + 1) % 4
        dots = "." * self._dots_count
        base_text = getattr(self, '_base_status', 'Cargando')
        self.status_label.setText(f"{base_text}{dots}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def show_overlay(self, text: str = "Cargando...",
                    detail: str = "",
                    indeterminate: bool = True):
        """Muestra el overlay"""
        from utils.config_loader import advanced_config
        dots_interval = advanced_config.get("loading_dots_interval", 400)
        spinner_interval = advanced_config.get("loading_spinner_interval", 500)

        if self.parent():
            self.setGeometry(self.parent().rect())

        self._base_status = text
        self.status_label.setText(text)
        self.detail_label.setText(detail)
        self._is_indeterminate = indeterminate

        if indeterminate:
            self.spinner_label.setVisible(True)
            self.progress_bar.setVisible(False)

            # Timers gestionados
            timer_manager.create(
                f"{self._owner}.dots",
                dots_interval,
                self._animate_dots,
                start=True
            )
            timer_manager.create(
                f"{self._owner}.spinner",
                spinner_interval,
                self._rotate_spinner,
                start=True
            )
        else:
            self.spinner_label.setVisible(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)

            timer_manager.stop(f"{self._owner}.dots")
            timer_manager.stop(f"{self._owner}.spinner")

        self.show()
        self.raise_()
        self.fade_in.start()

        QApplication.processEvents()

    def update_progress(self, value: int, text: str = None):
        """Actualiza el progreso"""
        if not self._is_indeterminate:
            self.progress_bar.setValue(min(100, max(0, value)))

        if text:
            self.status_label.setText(text)
            self._base_status = text

        QApplication.processEvents()

    def hide_overlay(self):
        """Oculta el overlay con animación"""
        timer_manager.stop(f"{self._owner}.dots")
        timer_manager.stop(f"{self._owner}.spinner")

        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(200)
        self.fade_out.setStartValue(1)
        self.fade_out.setEndValue(0)
        self.fade_out.finished.connect(self._on_hide_finished)
        self.fade_out.start()

    def _on_hide_finished(self):
        self.hide()
        self.setWindowOpacity(1)

    def cleanup(self):
        """Limpia los timers gestionados"""
        timer_manager.stop(f"{self._owner}.dots")
        timer_manager.stop(f"{self._owner}.spinner")