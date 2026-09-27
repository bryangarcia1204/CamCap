"""
Grid de widgets de cámaras con scroll, selección múltiple y expansión
"""
from PySide6.QtWidgets import (QWidget, QGridLayout, QScrollArea, 
                               QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                               QSizePolicy, QApplication)
from PySide6.QtCore import Qt, Signal, QRect, QEvent, SignalInstance
from PySide6.QtGui import QKeyEvent, QMouseEvent
from typing import List, Optional, Set

from core.models import CameraDevice
from ui.camera_widget import CameraWidget
from utils.logger import get_logger

logger = get_logger("CameraGrid")


class CameraGrid(QWidget):
    """Grid de widgets de cámaras con scroll y selección múltiple"""
    
    capture_requested = Signal(int)
    capture_all_requested = Signal()
    recording_toggled = Signal(int, bool)
    camera_removed = Signal(int)
    add_camera_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cameras: dict[int, CameraWidget] = {}
        self.columns = 2
        self._expanded_widget = None
        self._expanded_camera_id = None
        
        self._selected_cameras: Set[int] = set()
        self._last_selected_id = None
        
        self._setup_ui()
        
        self.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(self)
    
    def _setup_ui(self):
        """Configura la interfaz del grid"""
        from utils.config_loader import advanced_config
        spacing = advanced_config.get("grid_spacing", 12)
        margins = advanced_config.get("grid_margins", 8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Cámaras"))
        toolbar.addStretch()
        
        self.selection_info = QLabel("")
        self.selection_info.setStyleSheet("color: #4CAF50; font-size: 12px;")
        toolbar.addWidget(self.selection_info)
        
        self.capture_all_btn = QPushButton("📸 Capturar Todas")
        self.capture_all_btn.setProperty("type", "capture")
        self.capture_all_btn.clicked.connect(self.capture_all_requested.emit)
        toolbar.addWidget(self.capture_all_btn)
        
        layout.addLayout(toolbar)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(margins, margins, margins, margins)
        
        scroll_area.setWidget(self.grid_widget)
        layout.addWidget(scroll_area)
        
        self.empty_label = QLabel(
            "No hay cámaras configuradas\n"
            "Haz clic en 'Agregar Cámara' en la configuración"
        )
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #666; font-size: 14px; padding: 40px;")
        self.grid_layout.addWidget(self.empty_label, 0, 0, 1, 1)
        
        self.add_camera_btn = QPushButton("➕ Agregar Cámara")
        self.add_camera_btn.setProperty("type", "success")
        self.add_camera_btn.clicked.connect(self.add_camera_requested.emit)
        self.add_camera_btn.setVisible(False)
        self.grid_layout.addWidget(self.add_camera_btn, 1, 0, 1, 1)
    
    def clear_all_widgets(self):
        """Elimina todos los widgets SIN detener threads"""
        camera_ids = list(self.cameras.keys())
        
        for camera_id in camera_ids:
            widget = self.cameras.get(camera_id)
            if widget is None:
                continue
            
            for signal_name in [
                'capture_requested', 'recording_toggled', 'camera_removed',
                'toggle_expand_requested', 'flash_toggled', 'auto_flash_toggled',
                'expand_finished'
            ]:
                try:
                    signal:SignalInstance = getattr(widget, signal_name, None)
                    if signal is not None:
                        signal.disconnect()
                except:
                    pass
            
            try:
                widget._tm.shutdown()
                self.grid_layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()
            except:
                pass
            
            del self.cameras[camera_id]
        
        self._selected_cameras.clear()
        self._expanded_widget = None
        self._expanded_camera_id = None
        self._rearrange_grid()
        self._update_selection_info()
    
    def eventFilter(self, obj, event):
        """Filtra eventos de teclado global"""
        if event.type() == QEvent.KeyPress:
            self._handle_key_press(event)
            return True
        return super().eventFilter(obj, event)
    
    def keyPressEvent(self, event: QKeyEvent):
        self._handle_key_press(event)
        super().keyPressEvent(event)
    
    def _handle_key_press(self, event: QKeyEvent):
        """Maneja atajos de teclado"""
        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key_A and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            self.select_all()
            return
        
        if key == Qt.Key_A and modifiers == Qt.ShiftModifier:
            self.select_all()
            return
        
        if key == Qt.Key_Space:
            self.capture_selected()
            return
        
        if key == Qt.Key_Space and modifiers == Qt.AltModifier:
            self.capture_all_requested.emit()
            return
        
        if key == Qt.Key_G and modifiers == Qt.NoModifier:
            self.toggle_recording_selected()
            return
        
        if key == Qt.Key_G and modifiers == Qt.ShiftModifier:
            self.toggle_recording_all()
            return
        
        if key == Qt.Key_Escape:
            self.clear_selection()
            return
    
    def add_camera_widget(self, camera: CameraDevice) -> CameraWidget:
        """Añade widget de cámara al grid"""
        if camera.id in self.cameras:
            return self.cameras[camera.id]

        self._clear_empty_message()

        widget = CameraWidget(camera)
        widget.setVisible(True)
        widget.capture_requested.connect(self._forward_capture)
        widget.recording_toggled.connect(self._forward_recording)
        widget.camera_removed.connect(self._forward_remove)
        widget.toggle_expand_requested.connect(self._toggle_widget_expand)
        widget.expand_finished.connect(self._on_expand_finished)

        widget.mousePressEvent = lambda e: self._on_widget_click(widget, e)

        self.cameras[camera.id] = widget
        self._rearrange_grid()

        logger.debug(f"Widget añadido para {camera.name}")
        return widget
    
    def _forward_flash(self, camera_id: int, enabled: bool):
        self.flash_toggled.emit(camera_id, enabled)
    
    def _forward_auto_flash(self, camera_id: int, enabled: bool):
        self.auto_flash_toggled.emit(camera_id, enabled)
    
    def _on_widget_click(self, widget: CameraWidget, event: QMouseEvent):
        """Maneja clic para selección"""
        camera_id = widget.camera.id
        
        if event.modifiers() & Qt.ShiftModifier:
            if self._last_selected_id is not None:
                ids = list(self.cameras.keys())
                if self._last_selected_id in ids and camera_id in ids:
                    start = ids.index(self._last_selected_id)
                    end = ids.index(camera_id)
                    if start > end:
                        start, end = end, start
                    for i in range(start, end + 1):
                        self._select_camera(ids[i], True)
            else:
                self._select_camera(camera_id, True)
            self._last_selected_id = camera_id
        else:
            self.clear_selection()
            self._select_camera(camera_id, True)
            self._last_selected_id = camera_id
        
        self._update_selection_info()
    
    def _select_camera(self, camera_id: int, selected: bool):
        widget = self.cameras.get(camera_id)
        if widget:
            if selected:
                self._selected_cameras.add(camera_id)
            else:
                self._selected_cameras.discard(camera_id)
            widget.set_selected(selected)
    
    def select_all(self):
        """Selecciona todas las cámaras"""
        for camera_id in self.cameras.keys():
            self._select_camera(camera_id, True)
        self._update_selection_info()
        self._last_selected_id = None
    
    def clear_selection(self):
        """Deselecciona todas"""
        for camera_id in list(self._selected_cameras):
            self._select_camera(camera_id, False)
        self._selected_cameras.clear()
        self._update_selection_info()
        self._last_selected_id = None
    
    def get_selected_cameras(self) -> List[int]:
        return list(self._selected_cameras)
    
    def _update_selection_info(self):
        count = len(self._selected_cameras)
        if count == 0:
            self.selection_info.setText("")
        elif count == 1:
            self.selection_info.setText("1 cámara seleccionada")
        else:
            self.selection_info.setText(f"{count} cámaras seleccionadas")
    
    def capture_selected(self):
        """Captura cámaras seleccionadas"""
        for camera_id in self._selected_cameras:
            self.capture_requested.emit(camera_id)
    
    def toggle_recording_selected(self):
        """Grabar cámaras seleccionadas"""
        for camera_id in self._selected_cameras:
            widget = self.cameras.get(camera_id)
            if widget:
                widget.record_btn.click()
    
    def toggle_recording_all(self):
        """Grabar todas"""
        for widget in self.cameras.values():
            widget.record_btn.click()
    
    def _toggle_widget_expand(self, camera_id: int):
        """Expande/contrae widget"""
        widget = self.cameras.get(camera_id)
        if not widget:
            return
        
        if widget._animating:
            return
        
        if self._expanded_widget is not None and self._expanded_camera_id != camera_id:
            self._expanded_widget.toggle_expand(False)
            self._expanded_widget = None
            self._expanded_camera_id = None
        
        if self._expanded_camera_id == camera_id:
            widget.toggle_expand(False)
            self._expanded_widget = None
            self._expanded_camera_id = None
            return
        
        self._expanded_widget = widget
        self._expanded_camera_id = camera_id
        
        widget_rect = widget.geometry()
        parent_rect = self.grid_widget.geometry()
        
        expanded_rect = QRect(
            widget_rect.x(),
            widget_rect.y(),
            parent_rect.width() - 20,
            widget_rect.height() * 2
        )
        
        widget.toggle_expand(True, expanded_rect)
    
    def _on_expand_finished(self):
        """Reorganiza grid cuando termina la animación"""
        self._rearrange_grid()
        self.grid_widget.updateGeometry()
        self.updateGeometry()
    
    def remove_camera_widget(self, camera_id: int):
        """Elimina widget del grid - CON desconexión segura de señales"""
        logger.debug(f"🗑️ [grid] Eliminando widget {camera_id}")
        if camera_id not in self.cameras:
            logger.debug(f"🗑️ [grid] Widget {camera_id} no existe")
            return
        
        widget = self.cameras[camera_id]
        
        if self._expanded_camera_id == camera_id:
            self._expanded_widget = None
            self._expanded_camera_id = None
        
        self._selected_cameras.discard(camera_id)
        
        signal_names = [
            'capture_requested', 'recording_toggled', 'camera_removed',
            'toggle_expand_requested', 'flash_toggled', 'auto_flash_toggled',
            'expand_finished',
        ]
        
        for signal_name in signal_names:
            try:
                signal = getattr(widget, signal_name, None)
                if signal is not None:
                    try:
                        signal.disconnect()
                    except (RuntimeError, TypeError) as e:
                        logger.debug(f"Error al desconectar señal {signal_name}: {e}")
            except Exception as e:
                logger.debug(f"No se pudo desconectar {signal_name}: {e}")
        
        try:
            if hasattr(widget, 'cleanup'):
                logger.debug(f"🗑️ [grid] Llamando cleanup()...")
                widget.cleanup()
                logger.debug(f"🗑️ [grid] cleanup() completado")
            self.grid_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        except Exception as e:
            logger.debug(f"Error eliminando widget: {e}")
        
        del self.cameras[camera_id]
        
        self._rearrange_grid()
        self._update_selection_info()
        
        if not self.cameras:
            self._show_empty_message()
    
    def get_camera_widget(self, camera_id: int) -> Optional[CameraWidget]:
        return self.cameras.get(camera_id)
    
    def get_camera_widgets(self) -> List[CameraWidget]:
        return list(self.cameras.values())
    
    def has_cameras(self) -> bool:
        return len(self.cameras) > 0
    
    def set_columns(self, columns: int):
        self.columns = max(1, min(4, columns))
        self._rearrange_grid()
    
    def _rearrange_grid(self):
        """Reorganiza widgets en el grid"""
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        
        widgets = list(self.cameras.values())
        
        if not widgets:
            self.empty_label.setVisible(True)
            self.grid_layout.addWidget(self.empty_label, 0, 0, 1, 1)
            self.add_camera_btn.setVisible(False)
            return
        
        self.empty_label.setVisible(False)
        
        row = 0
        col = 0
        expanded_id = self._expanded_camera_id
        
        for widget in widgets:
            if widget:
                widget.setVisible(True)
                if widget.camera.id == expanded_id:
                    self.grid_layout.addWidget(widget, row, col, 1, 2)
                    col += 2
                else:
                    self.grid_layout.addWidget(widget, row, col, 1, 1)
                    col += 1
                
                if col >= self.columns:
                    col = 0
                    row += 1
        
        if col >= self.columns:
            col = 0
            row += 1
        
        self.add_camera_btn.setVisible(True)
        self.grid_layout.addWidget(self.add_camera_btn, row, col, 1, 1)
    
    def _clear_empty_message(self):
        self.empty_label.setVisible(False)
        if self.empty_label.parent() == self.grid_widget:
            self.grid_layout.removeWidget(self.empty_label)
    
    def _show_empty_message(self):
        self.empty_label.setVisible(True)
        self.grid_layout.addWidget(self.empty_label, 0, 0, 1, 1)
        self.add_camera_btn.setVisible(False)
    
    def _forward_capture(self, camera_id: int):
        self.capture_requested.emit(camera_id)
    
    def _forward_recording(self, camera_id: int, state: bool):
        self.recording_toggled.emit(camera_id, state)
    
    def _forward_remove(self, camera_id: int):
        self.camera_removed.emit(camera_id)
    
    def capture_all(self):
        for widget in self.cameras.values():
            widget.capture_btn.click()
    
    def start_all_recording(self):
        for widget in self.cameras.values():
            if not widget.is_recording:
                widget.record_btn.click()
    
    def stop_all_recording(self):
        for widget in self.cameras.values():
            if widget.is_recording:
                widget.record_btn.click()