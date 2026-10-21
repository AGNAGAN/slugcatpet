from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication([])
scr = next((s for s in QGuiApplication.screens() if s.name() == "HDMI-A-1"), QGuiApplication.primaryScreen())
w = QWidget()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
w.setScreen(scr)
w.setStyleSheet("background: #202030;")
w.setGeometry(scr.geometry())
w.showFullScreen()
w.raise_()
w.activateWindow()

def move():
    print("before", QCursor.pos())
    QCursor.setPos(QPoint(700, 1930))
    print("after", QCursor.pos())

def done():
    print("done", QCursor.pos())
    app.quit()

QTimer.singleShot(900, move)
QTimer.singleShot(1800, done)
app.exec()
