import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication

app = QApplication(sys.argv)
w = QWidget()
w.setWindowTitle("slugcatpet-probe4")
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
w.resize(400, 300)
w.show()
def report():
    print("app geometry", w.geometry(), "frame", w.frameGeometry(), "screen", w.screen().name(), "dpr", w.devicePixelRatioF(), flush=True)
QTimer.singleShot(1000, report)
QTimer.singleShot(5000, report)
QTimer.singleShot(7000, app.quit)
sys.exit(app.exec())
