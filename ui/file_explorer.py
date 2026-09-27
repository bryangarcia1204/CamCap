"""
Explorador de archivos estilo VSCode con acciones completas
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QTreeView, QLabel, QLineEdit, QPushButton,
                               QComboBox, QFileDialog, QListWidget, QListWidgetItem,
                               QSplitter, QMenu, QMessageBox, QInputDialog,
                               QDialog, QFormLayout)
from PySide6.QtCore import Qt, QDir, Signal, QSize, QThreadPool
from PySide6.QtWidgets import QFileSystemModel
from PySide6.QtGui import QAction, QIcon, QPixmap, QImage

from ui.video_thumbnail_worker import video_thumbnail_manager

from core.file_manager import FileManager
from core.models import CaptureSettings
from utils.logger import get_logger

logger = get_logger("FileExplorer")


class FileDetailsDialog(QDialog):
    """Diálogo de detalles de archivo"""
    
    def __init__(self, file_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalles del Archivo")
        self.setMinimumWidth(450)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:1 #2a0a4a);
            }
            QLabel { color: #ffffff; font-size: 13px; }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 24px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #6a1b9a);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        
        title = QLabel("📄 Detalles")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        layout.addWidget(title)
        
        form = QFormLayout()
        form.setSpacing(8)
        
        form.addRow("Nombre:", QLabel(file_info.get("filename", "—")))
        
        path_label = QLabel(file_info.get("path", "—"))
        path_label.setWordWrap(True)
        path_label.setStyleSheet("color: #aaa; font-size: 11px;")
        form.addRow("Ruta:", path_label)
        
        tipo = file_info.get("type", "—")
        tipo_txt = "🖼️ Imagen" if tipo == "image" else (
            "🎬 Video" if tipo == "video" else "📄 Archivo"
        )
        form.addRow("Tipo:", QLabel(tipo_txt))
        
        form.addRow("Tamaño:", QLabel(self._format_size(file_info.get("size", 0))))
        
        if "width" in file_info:
            form.addRow("Dimensiones:", QLabel(
                f"{file_info['width']} x {file_info['height']} px"
            ))
        
        if "duration" in file_info:
            d = file_info["duration"]
            mins, secs = divmod(d, 60)
            form.addRow("Duración:", QLabel(f"{mins:02d}:{secs:02d}"))
        
        if "fps" in file_info:
            form.addRow("FPS:", QLabel(f"{file_info['fps']:.1f}"))
        
        if "frames" in file_info:
            form.addRow("Frames:", QLabel(str(file_info["frames"])))
        
        if "format" in file_info:
            form.addRow("Formato:", QLabel(file_info["format"]))
        
        if "created" in file_info:
            form.addRow("Creado:", QLabel(
                file_info["created"].strftime("%Y-%m-%d %H:%M:%S")
            ))
        
        try:
            mtime = os.path.getmtime(file_info.get("path", ""))
            form.addRow("Modificado:", QLabel(
                datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            ))
        except:
            pass
        
        layout.addLayout(form)
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
    
    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"


class FileExplorer(QWidget):
    """Explorador con acciones completas"""
    
    file_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_directory = os.path.expanduser("~/Pictures")
        self._setup_ui()
        self._setup_model()
        self._setup_context_menu()
        self._refresh_files()
        logger.debug("FileExplorer inicializado")
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Navegación
        nav = QHBoxLayout()
        nav.setSpacing(4)
        
        self.dir_combo = QComboBox()
        self.dir_combo.setEditable(True)
        self.dir_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                color: white;
            }
            QComboBox::drop-down { border: none; }
        """)
        self.dir_combo.addItem(self.current_directory)
        self.dir_combo.lineEdit().returnPressed.connect(self._navigate_to_dir)
        nav.addWidget(self.dir_combo)
        
        browse_btn = QPushButton("📁")
        browse_btn.setFixedWidth(30)
        browse_btn.clicked.connect(self._browse_directory)
        nav.addWidget(browse_btn)
        
        layout.addLayout(nav)
        
        # Filtros
        filt = QHBoxLayout()
        filt.setSpacing(4)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "Todos los archivos", "Imágenes", "Videos",
            "Últimas 24h", "Última semana"
        ])
        self.filter_combo.currentTextChanged.connect(self._refresh_files)
        filt.addWidget(QLabel("Filtro:"))
        filt.addWidget(self.filter_combo)
        filt.addStretch()
        
        layout.addLayout(filt)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setIndentation(16)
        self.tree_view.setStyleSheet("""
            QTreeView {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
            QTreeView::item { padding: 4px 8px; border-radius: 4px; }
            QTreeView::item:selected { background-color: #2d7d9a; }
            QTreeView::item:hover { background-color: #3d3d3d; }
        """)
        splitter.addWidget(self.tree_view)
        
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(80, 60))
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px;
                color: white;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
                min-height: 64px;
            }
            QListWidget::item:selected {
                background-color: #2d7d9a;
                border: 1px solid #4da0c4;
            }
            QListWidget::item:hover {
                background-color: #3d3d3d;
            }
        """)
        self.list_widget.itemDoubleClicked.connect(self._on_file_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        splitter.addWidget(self.list_widget)
        
        splitter.setSizes([200, 400])
        layout.addWidget(splitter)
        
        # Estado
        status = QHBoxLayout()
        self.status_label = QLabel("Listo")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        status.addWidget(self.status_label)
        status.addStretch()
        self.file_count_label = QLabel("0 archivos")
        self.file_count_label.setStyleSheet("color: #888; font-size: 11px;")
        status.addWidget(self.file_count_label)
        layout.addLayout(status)
    
    def _setup_model(self):
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(self.current_directory)
        self.fs_model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        
        self.tree_view.setModel(self.fs_model)
        self.tree_view.setRootIndex(self.fs_model.index(self.current_directory))
        
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)
        
        self.tree_view.clicked.connect(self._on_tree_clicked)
    
    def _setup_context_menu(self):
        self.context_menu = QMenu(self)
        self.context_menu.setStyleSheet("""
            QMenu {
                background: #2d2d2d;
                color: white;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item { padding: 8px 24px; border-radius: 6px; }
            QMenu::item:selected { background: #4a148c; }
            QMenu::separator { height: 1px; background: #404040; margin: 4px 8px; }
        """)
        
        self.action_open = QAction("📂 Abrir", self)
        self.action_open.triggered.connect(self._action_open)
        
        self.action_details = QAction("ℹ️ Ver detalles", self)
        self.action_details.triggered.connect(self._action_details)
        
        self.action_rename = QAction("✏️ Renombrar", self)
        self.action_rename.triggered.connect(self._action_rename)
        
        self.action_copy = QAction("📋 Copiar a...", self)
        self.action_copy.triggered.connect(self._action_copy)
        
        self.action_move = QAction("📦 Mover a...", self)
        self.action_move.triggered.connect(self._action_move)
        
        self.action_delete = QAction("🗑️ Eliminar", self)
        self.action_delete.triggered.connect(self._action_delete)
        
        self.context_menu.addAction(self.action_open)
        self.context_menu.addAction(self.action_details)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.action_rename)
        self.context_menu.addAction(self.action_copy)
        self.context_menu.addAction(self.action_move)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.action_delete)
    
    def _show_context_menu(self, position):
        item = self.list_widget.itemAt(position)
        if item is None:
            return
        
        file_path = item.data(Qt.UserRole)
        is_file = os.path.isfile(file_path)
        self.action_details.setEnabled(is_file)
        
        self.context_menu.exec(self.list_widget.mapToGlobal(position))
    
    def _get_selected_file(self) -> str:
        item = self.list_widget.currentItem()
        if item:
            return str(Path(item.data(Qt.UserRole)))
        return None
    
    def _action_open(self):
        file_path = self._get_selected_file()
        if file_path:
            self.file_selected.emit(file_path)
    
    def _action_details(self):
        file_path = self._get_selected_file()
        if not file_path or not os.path.isfile(file_path):
            return
        
        try:
            fm = FileManager(CaptureSettings())
            info = fm.get_capture_info(file_path)
            
            if not info:
                QMessageBox.warning(self, "Error", "No se obtuvo información")
                return
            
            dialog = FileDetailsDialog(info, self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Error en detalles: {e}")
            QMessageBox.critical(self, "Error", f"Error: {e}")
    
    def _action_rename(self):
        file_path = self._get_selected_file()
        if not file_path:
            return
        
        old_name = os.path.basename(file_path)
        new_name, ok = QInputDialog.getText(
            self, "Renombrar", "Nuevo nombre:", QLineEdit.Normal, old_name
        )
        
        if ok and new_name and new_name != old_name:
            try:
                new_path = os.path.join(os.path.dirname(file_path), new_name)
                if os.path.exists(new_path):
                    QMessageBox.warning(self, "Error", "Ya existe")
                    return
                
                os.rename(file_path, new_path)
                self._refresh_files()
                self.status_label.setText(f"✅ Renombrado")
            except Exception as e:
                logger.error(f"Error renombrando: {e}")
                QMessageBox.critical(self, "Error", f"Error: {e}")
    
    def _action_copy(self):
        file_path = self._get_selected_file()
        if not file_path:
            return
        
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Carpeta destino", self.current_directory
        )
        if not dest_dir:
            return
        
        try:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(dest_dir, filename)
            
            if os.path.exists(dest_path):
                reply = QMessageBox.question(
                    self, "Confirmar",
                    f"Ya existe '{filename}'. ¿Sobrescribir?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            
            shutil.copy2(file_path, dest_path)
            self.status_label.setText(f"✅ Copiado: {filename}")
        except Exception as e:
            logger.error(f"Error copiando: {e}")
            QMessageBox.critical(self, "Error", f"Error: {e}")
    
    def _action_move(self):
        file_path = self._get_selected_file()
        if not file_path:
            return
        
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Carpeta destino", self.current_directory
        )
        if not dest_dir:
            return
        
        try:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(dest_dir, filename)
            
            if os.path.exists(dest_path):
                reply = QMessageBox.question(
                    self, "Confirmar",
                    f"Ya existe '{filename}'. ¿Sobrescribir?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
                os.remove(dest_path)
            
            shutil.move(file_path, dest_path)
            self._refresh_files()
            self.status_label.setText(f"✅ Movido: {filename}")
        except Exception as e:
            logger.error(f"Error moviendo: {e}")
            QMessageBox.critical(self, "Error", f"Error: {e}")
    
    def _action_delete(self):
        file_path = self._get_selected_file()
        if not file_path:
            return

        filename = os.path.basename(file_path)
        reply = QMessageBox.question(
            self, "Eliminar",
            f"¿Eliminar '{filename}'?\n\nNo se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            try:
                import send2trash
                send2trash.send2trash(file_path)
                self.status_label.setText(f"🗑️ Papelera: {filename}")
            except ImportError:
                os.remove(file_path)
                self.status_label.setText(f"🗑️ Eliminado: {filename}")
            
            self._refresh_files()
        except Exception as e:
            logger.error(f"Error eliminando: {e}")
            QMessageBox.critical(self, "Error", f"Error: {e}")
    
    def _on_tree_clicked(self, index):
        if self.fs_model.isDir(index):
            self._navigate_to(self.fs_model.filePath(index))
    
    def _navigate_to(self, path: str):
        if os.path.isdir(path):
            self.current_directory = path
            self.dir_combo.setEditText(path)
            self._refresh_files()
    
    def _navigate_to_dir(self):
        path = self.dir_combo.currentText().strip()
        if os.path.isdir(path):
            self.current_directory = path
            self._refresh_files()
        else:
            self.dir_combo.setEditText(self.current_directory)
    
    def _browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Seleccionar Directorio", self.current_directory
        )
        if dir_path:
            self._navigate_to(dir_path)
    
    def _refresh_files(self):
        self.list_widget.clear()

        try:
            files = os.listdir(self.current_directory)
            filter_type = self.filter_combo.currentText()

            for file in sorted(files):
                file_path = os.path.join(self.current_directory, file)
                if os.path.isfile(file_path):
                    if not self._passes_filter(file_path, filter_type):
                        continue

                    ext = os.path.splitext(file)[1].lower()

                    # Icono por defecto
                    icon = None
                    if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']:
                        display = f"🖼️ {file}"
                    elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.mpg', '.mpeg']:
                        display = f"🎬 {file}"
                    else:
                        display = f"📄 {file}"

                    # Añadir tamaño
                    try:
                        size = os.path.getsize(file_path)
                        display = f"{display}  ({self._format_size(size)})"
                    except Exception:
                        pass

                    item = QListWidgetItem(display)
                    item.setData(Qt.UserRole, file_path)

                    # Placeholder mientras se genera la miniatura
                    item.setIcon(self._get_placeholder_icon(ext))

                    self.list_widget.addItem(item)

                    # Generar miniatura para imágenes y videos
                    if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']:
                        self._load_image_thumbnail(item, file_path)
                    elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.mpg', '.mpeg']:
                        self._load_video_thumbnail(item, file_path)

            self.file_count_label.setText(f"{self.list_widget.count()} archivos")
            self.status_label.setText(f"📁 {self.current_directory}")
        except Exception as e:
            logger.error(f"Error refrescando: {e}")
            self.status_label.setText(f"Error: {e}")

    def _get_placeholder_icon(self, ext: str) -> QIcon:
        """Devuelve un icono placeholder según el tipo"""
        # Icono vacío (se reemplazará con la miniatura)
        pixmap = QPixmap(80, 60)
        pixmap.fill(Qt.transparent)
        return QIcon(pixmap)

    def _load_image_thumbnail(self, item: QListWidgetItem, image_path: str):
        """Carga la miniatura de una imagen"""
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    80, 60,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                item.setIcon(QIcon(scaled))
        except Exception as e:
            logger.debug(f"Error cargando thumbnail de imagen: {e}")

    def _load_video_thumbnail(self, item: QListWidgetItem, video_path: str):
        """Carga la miniatura de un video (asíncrono)"""
        def on_thumbnail_ready(path: str, image):
            # Buscar el item correspondiente (puede haber cambiado)
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                if it.data(Qt.UserRole) == path:
                    if image is not None and not image.isNull():
                        pixmap = QPixmap.fromImage(image)
                        # Añadir un pequeño overlay para indicar que es video
                        scaled = pixmap.scaled(
                            80, 60,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        it.setIcon(QIcon(scaled))
                    break

        video_thumbnail_manager.get_thumbnail_async(
            video_path,
            on_thumbnail_ready,
            size=160
        )
    
    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def _passes_filter(self, file_path: str, filter_type: str) -> bool:
        if filter_type == "Todos los archivos":
            return True
        
        ext = os.path.splitext(file_path)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
        video_exts = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.mpg']
        
        if filter_type == "Imágenes":
            return ext in image_exts
        elif filter_type == "Videos":
            return ext in video_exts
        
        try:
            mtime = os.path.getmtime(file_path)
            dt = datetime.fromtimestamp(mtime)
            now = datetime.now()
            
            if filter_type == "Últimas 24h":
                return (now - dt).days < 1
            elif filter_type == "Última semana":
                return (now - dt).days < 7
        except:
            pass
        
        return True
    
    def _on_file_double_clicked(self, item: QListWidgetItem):
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.file_selected.emit(file_path)
    
    def refresh(self):
        self._refresh_files()