import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt, QRect
from PySide6.QtGui import QRegion, QColor, QPainter

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
w.resize(300, 300)
w.show()
wh = w.windowHandle()
print("platform", app.platformName(), "winId", hex(int(w.winId())), flush=True)
def apply():
    wh.setMask(QRegion(50, 50, 100, 100))
    print("mask applied", flush=True)
QTimer.singleShot(500, apply)
QTimer.singleShot(1500, app.quit)
sys.exit(app.exec())
