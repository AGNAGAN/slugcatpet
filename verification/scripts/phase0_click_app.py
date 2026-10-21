import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit
from PySide6.QtCore import Qt, QTimer, QObject, Slot, ClassInfo
from PySide6.QtGui import QRegion, QGuiApplication, QColor
from PySide6.QtDBus import QDBusConnection

LOG = open("verification/logs/live/phase0_click.log", "w", buffering=1)

@ClassInfo({"D-Bus Interface": "org.slugcatpet.Phase0"})
class Service(QObject):
    @Slot(int, int)
    def Cursor(self, x, y):
        print(f"CURSOR {x} {y}", file=LOG)
    @Slot(str)
    def Note(self, s):
        print(f"NOTE {s}", file=LOG)
    @Slot(int)
    def Hotkey(self, id):
        print(f"HOTKEY {id}", file=LOG)

class Target(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("phase0-target")
        self.setStyleSheet("background: #205080;")
        self.resize(900, 700)
        self.show()
    def mousePressEvent(self, e):
        print(f"TARGET_CLICK {e.position().x():.0f} {e.position().y():.0f}", file=LOG)

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("phase0-overlay")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(1707, 1067)
        self.edit = QLineEdit(self)
        self.edit.setGeometry(20, 20, 240, 34)
        self.edit.setPlaceholderText("phase0 focus test")
        self.edit.textChanged.connect(lambda text: print(f"EDIT_TEXT {text!r}", file=LOG))
        self.show()
        QTimer.singleShot(500, self.apply_mask)
        QTimer.singleShot(9000, self.apply_outside)
        QTimer.singleShot(3000, self.apply_mask)
        QTimer.singleShot(5000, self.apply_mask)
    def apply_mask(self):
        r = QRegion(0, 0, 300, 300)
        self.windowHandle().setMask(r)
        self.windowHandle().requestUpdate()
        self.update()
        print(f"OVERLAY_MASK {r.boundingRect()} DPR {self.devicePixelRatioF()}", file=LOG)
    def apply_outside(self):
        r = QRegion(self.width(), self.height(), 1, 1)
        self.windowHandle().setMask(r)
        self.windowHandle().requestUpdate()
        self.update()
        print(f"OVERLAY_OUTSIDE {r.boundingRect()}", file=LOG)
    def mousePressEvent(self, e):
        print(f"OVERLAY_CLICK {e.position().x():.0f} {e.position().y():.0f}", file=LOG)
    def paintEvent(self, e):
        # transparent; optional faint red border to see overlay during test
        from PySide6.QtGui import QPainter, QPen
        p = QPainter(self)
        p.setPen(QPen(QColor(255, 0, 0, 120), 2))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.end()

app = QApplication(sys.argv)
QGuiApplication.setDesktopFileName("org.slugcatpet.Phase0")
bus = QDBusConnection.sessionBus()
print("DBUS", bus.isConnected(), file=LOG)
print("SERVICE", bus.registerService("org.slugcatpet.Phase0"), file=LOG)
svc = Service()
print("OBJECT", bus.registerObject("/Phase0", svc, QDBusConnection.RegisterOption.ExportAllSlots), file=LOG)
t = Target()
o = Overlay()
QTimer.singleShot(1000, lambda: print(f"TARGET_GEO {t.geometry()} OVERLAY_GEO {o.geometry()} SCREEN {QGuiApplication.primaryScreen().geometry()} DPR {o.devicePixelRatioF()}", file=LOG))
QTimer.singleShot(1200, lambda: print("SCREENS " + " | ".join(f"{s.name()} {s.geometry()} dpr={s.devicePixelRatio()}" for s in QGuiApplication.screens()), file=LOG))
QTimer.singleShot(60000, app.quit)
sys.exit(app.exec())
