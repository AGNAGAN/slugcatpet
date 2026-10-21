from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication([])
start = QCursor.pos()
scr = next((s for s in QGuiApplication.screens() if s.name() == "HDMI-A-1"), QGuiApplication.primaryScreen())
print("START cursor", start, "screen", scr.name(), scr.geometry().getRect(), "focus", QGuiApplication.focusWindow())
w = QWidget()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
w.setScreen(scr)
w.setStyleSheet("background: #202030;")
w.setGeometry(scr.geometry())
w.showFullScreen()
w.raise_()
w.activateWindow()

def step(label, target):
    print(label, "before", QCursor.pos(), "focus", QGuiApplication.focusWindow())
    QCursor.setPos(target)
    print(label, "after-call", QCursor.pos())

def s1():
    step("S1", scr.geometry().center())

def s2():
    step("S2", scr.geometry().topLeft() + QPoint(200, 200))

def s3():
    step("S3", scr.geometry().topLeft() + QPoint(400, 400))
    QTimer.singleShot(500, app.quit)

QTimer.singleShot(1000, s1)
QTimer.singleShot(1800, s2)
QTimer.singleShot(2600, s3)
app.exec()
print("END cursor", QCursor.pos())
