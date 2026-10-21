import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QRegion, QGuiApplication
LOG = open("verification/logs/live/phase0_edp.log", "w", buffering=1)

class Target(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("phase0-edp-target")
        self.setStyleSheet("background: #205080;")
        self.resize(1200, 700)
        self.setScreen(QGuiApplication.screens()[0])
        self.show()
    def mousePressEvent(self, e):
        print(f"TARGET_CLICK {e.position().x():.0f} {e.position().y():.0f}", file=LOG)

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("phase0-edp-overlay")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(1440, 900)
        self.setScreen(QGuiApplication.screens()[0])
        self.show()
        QTimer.singleShot(600, self.apply_mask)
    def apply_mask(self):
        r = QRegion(0, 0, 200, 200)
        self.windowHandle().setMask(r)
        self.windowHandle().requestUpdate()
        self.update()
        print(f"OVERLAY_MASK {r.boundingRect()} DPR {self.devicePixelRatioF()}", file=LOG)
    def mousePressEvent(self, e):
        print(f"OVERLAY_CLICK {e.position().x():.0f} {e.position().y():.0f}", file=LOG)

app = QApplication(sys.argv)
t = Target(); o = Overlay()
QTimer.singleShot(1200, lambda: print(f"TARGET_GEO {t.geometry()} OVERLAY_GEO {o.geometry()} DPR {o.devicePixelRatioF()}", file=LOG))
QTimer.singleShot(30000, app.quit)
sys.exit(app.exec())
