import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
LOG = open("verification/logs/live/dpr_probe.log", "w", buffering=1)
app = QApplication(sys.argv)
w = QWidget(); w.setWindowTitle("phase0-dpr"); w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True); w.resize(1440, 900); w.show()
def dump():
    print(f"WIN dpr={w.devicePixelRatioF()} geo={w.geometry()} screen={w.screen().name() if w.screen() else None}", file=LOG)
    for s in QGuiApplication.screens():
        print(f"SCREEN {s.name()} geo={s.geometry()} dpr={s.devicePixelRatio()}", file=LOG)
QTimer.singleShot(800, dump)
QTimer.singleShot(4000, app.quit)
sys.exit(app.exec())
