import sys
from PySide6.QtCore import QTimer, Qt, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget


class Probe(QWidget):
    def enterEvent(self, ev):
        print("PROBE ENTER", ev.position(), flush=True)

    def leaveEvent(self, ev):
        print("PROBE LEAVE", flush=True)

    def mouseMoveEvent(self, ev):
        print("PROBE MOVE", ev.position(), flush=True)

    def mousePressEvent(self, ev):
        print("PROBE PRESS", ev.button(), flush=True)


app = QApplication(sys.argv)
w = Probe()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
w.setMouseTracking(True)
w.setWindowTitle("Pointer Probe")
w.setScreen(QGuiApplication.screens()[-1])
w.setGeometry(QRect(0, 900, 1707, 1099))
w.show()
print("PROBE SHOW", w.geometry().getRect(), w.screen().name(), flush=True)
QTimer.singleShot(10000, app.quit)
app.exec()
print("PROBE DONE", flush=True)
