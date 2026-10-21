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
def partial():
    w.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
    w.windowHandle().setMask(QRegion(50,50,100,100))
    print("partial", flush=True)
def transparent():
    w.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
    w.windowHandle().setMask(QRegion())
    print("transparent", flush=True)
def partial2():
    w.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
    w.windowHandle().setMask(QRegion(60,60,80,80))
    print("partial2", flush=True)
QTimer.singleShot(400, partial)
QTimer.singleShot(800, transparent)
QTimer.singleShot(1200, partial2)
QTimer.singleShot(1600, app.quit)
sys.exit(app.exec())
