"""
Widget "✨ Mejorar Imagen" para ImagePreviewDialog.
"""
from PySide6.QtWidgets import QPushButton, QDialog, QMessageBox

from utils.logger import get_logger

logger = get_logger("Plugin.ImageEnhancerWidgets")


def create_enhance_button(dialog, image=None, **kwargs):
    """
    Crea el botón "✨ Mejorar Imagen".

    Args:
        dialog: instancia de ImagePreviewDialog
        image: imagen numpy opcional (si no se pasa, se toma de dialog.image)

    Returns:
        Lista con [enhance_btn]
    """
    btn = QPushButton("✨ Mejorar Imagen")
    btn.setFixedHeight(32)
    btn.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ef6c00, stop:1 #f57c00);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 50px;
            padding: 4px 20px;
            font-weight: 600;
            font-size: 12px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #f57c00, stop:1 #fb8c00);
        }
    """)

    def _open_enhancer():
        try:
            from .enhance_dialog import ImageEnhanceDialog

            img = image if image is not None else getattr(dialog, 'image', None)
            if img is None:
                QMessageBox.warning(dialog, "Error", "No hay imagen")
                return

            enhancer_dialog = ImageEnhanceDialog(img, dialog)
            if enhancer_dialog.exec() == QDialog.Accepted:
                dialog.image, was_enhanced = enhancer_dialog.get_result()
                dialog._enhanced = was_enhanced

                # Actualizar preview
                if hasattr(dialog, '_display_image'):
                    dialog._display_image()

                # Actualizar info label
                h, w = dialog.image.shape[:2]
                if hasattr(dialog, 'info_label'):
                    dialog.info_label.setText(f"📐 {w}x{h} px  |  ✨ Mejorada")

                logger.info("Imagen mejorada desde plugin")
        except Exception as e:
            logger.error(f"Error abriendo editor: {e}", exc_info=True)
            QMessageBox.critical(dialog, "Error", f"Error: {e}")

    btn.clicked.connect(_open_enhancer)
    return [btn]