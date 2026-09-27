"""
Pantalla de carga optimizada - Sin picos de CPU
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                               QProgressBar, QApplication)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen
from utils.logger import get_logger
from utils.performance import PacingController

logger = get_logger("SplashScreen")


class SplashScreen(QWidget):
    """Pantalla de carga con pacing inteligente"""
    
    finished = Signal()
    
    def __init__(self):
        super().__init__()
        from utils.config_loader import advanced_config
        fade_in = advanced_config.get("splash_fade_in_duration", 400)
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 400)
        
        self._progress = 0
        self._current_stage = ""
        
        self._setup_ui()
        self._center_on_screen()
        
        self.setWindowOpacity(0)
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(fade_in)
        self.fade_in.setStartValue(0)
        self.fade_in.setEndValue(1)
        self.fade_in.setEasingCurve(QEasingCurve.InOutQuad)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 40, 30, 40)
        layout.setSpacing(20)
        
        logo = QLabel("📷")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("font-size: 80px; background: transparent; color: white;")
        layout.addWidget(logo)
        
        title = QLabel("ProCamera")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 36px;
            font-weight: bold;
            color: white;
            letter-spacing: 3px;
            background: transparent;
        """)
        layout.addWidget(title)
        
        subtitle = QLabel("Estación de Control de Cámaras")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("""
            font-size: 13px;
            color: rgba(255,255,255,0.6);
            letter-spacing: 1px;
            background: transparent;
        """)
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.1);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4,
                    stop:0.5 #6a1b9a,
                    stop:1 #4da0c4);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Iniciando...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 12px;
            color: rgba(255,255,255,0.7);
            background: transparent;
        """)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        version = QLabel("v2.0.0")
        version.setAlignment(Qt.AlignRight)
        version.setStyleSheet("""
            font-size: 11px;
            color: rgba(255,255,255,0.4);
            background: transparent;
        """)
        layout.addWidget(version)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(13, 20, 69, 245))
        gradient.setColorAt(0.5, QColor(26, 35, 126, 245))
        gradient.setColorAt(1.0, QColor(42, 10, 74, 245))
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 20, 20)
        painter.fillPath(path, gradient)
        
        pen = QPen(QColor(255, 255, 255, 30))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 20, 20)
        
        glow = QLinearGradient(0, 0, 0, 100)
        glow.setColorAt(0.0, QColor(255, 255, 255, 15))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, glow)
    
    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)
    
    def show_with_animation(self):
        self.show()
        self.fade_in.start()
    
    def set_progress(self, value: int, status: str = None, force: bool = False):
        """Actualiza progreso con pacing"""
        self._progress = min(100, max(0, value))
        self.progress_bar.setValue(self._progress)
        
        if status:
            self._current_stage = status
            self.status_label.setText(status)
        
        if force:
            QApplication.processEvents()
        else:
            PacingController.sleep_ms(5, process_events=True)
    
    def update_stage(self, text: str, progress: int,
                     stage_delay_ms: int = 50):
        """Actualiza etapa con delay controlado"""
        self.set_progress(progress, text, force=True)
        
        if stage_delay_ms > 0:
            PacingController.sleep_ms(stage_delay_ms, process_events=True)
    
    def finish(self):
        """Termina con animación"""
        from utils.config_loader import advanced_config
        fade_out = advanced_config.get("splash_fade_out_duration", 300)
        
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(fade_out)
        self.fade_out.setStartValue(1)
        self.fade_out.setEndValue(0)
        self.fade_out.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade_out.finished.connect(self._on_fade_finished)
        self.fade_out.start()
    
    def _on_fade_finished(self):
        self.close()
        self.finished.emit()