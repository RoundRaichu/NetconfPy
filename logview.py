import logging, os, sys
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontDatabase
from utils import AppInfo

log = logging.getLogger('netconftool.logviewer')

class LogViewer(QWidget):
    def __init__(self, parent=None, flags=Qt.WindowType.Window) -> None:
        super().__init__(parent, flags)
        self.findw = None
        self._initUI()
        try:
            with open(os.path.join(AppInfo.logdir(), "NetconfTool.log"), 'r') as f:
                self.editor.setPlainText(f.read())
        except Exception as ex:
            log.error("load log file error: %s", str(ex))
            pass

    def _initUI(self):
        self.setWindowTitle("LogViewer")
        self.findw = None
        layout = QVBoxLayout(self)
        editor  = QPlainTextEdit(self)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        if sys.platform == 'darwin':
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        else:
            font = QFont("Consolas")
        editor.setFont(font)
        self.resize(800, 600)
        self.editor = editor

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                level=logging.DEBUG)
    app = QApplication([])

    widget = LogViewer()
    widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
    widget.show()
    app.exec()