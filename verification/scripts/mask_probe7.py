import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QRegion

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
w.resize(300, 300)
w.show()
def outside():
    w.windowHandle().setMask(QRegion(300, 300, 1, 1))
    print("outside", flush=True)
def inside():
    w.windowHandle().setMask(QRegion(50, 50, 100, 100))
    print("inside", flush=True)
QTimer.singleShot(400, outside)
QTimer.singleShot(800, inside)
QTimer.singleShot(1200, app.quit)
sys.exit(app.exec())
