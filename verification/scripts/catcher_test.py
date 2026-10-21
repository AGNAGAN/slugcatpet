import sys
from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QRegion
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)
scr = next((s for s in QGuiApplication.screens() if s.name() == "HDMI-A-1"), QGuiApplication.primaryScreen())
rect = scr.geometry()

main = QWidget()
main.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
main.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
main.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
main.setGeometry(rect)
main.show()

def m_enter(e):
    print("MAIN enter", e.position())
main.enterEvent = m_enter

# 只在猫的区域留一个输入口；当前光标在 (700,1500)，不落在里面
main.windowHandle().setMask(QRegion(700, 1800, 100, 100))
main.windowHandle().requestUpdate()
print("main shown, cursor", QCursor.pos())

capture = None

def make_catcher():
    global capture
    capture = QWidget()
    capture.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.Tool
        | Qt.WindowType.WindowStaysOnTopHint
    )
    capture.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    capture.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    capture.setGeometry(rect)
    capture.show()
    capture.raise_()
    capture.windowHandle().setMask(QRegion(0, 0, rect.width(), rect.height()))
    capture.windowHandle().requestUpdate()

    def c_enter(e):
        print("CAPTURE enter", e.position())
    capture.enterEvent = c_enter
    print("catcher shown", capture.geometry().getRect(), capture.frameGeometry().getRect())
    QTimer.singleShot(800, warp)

def warp():
    print("before warp", QCursor.pos(), "override", QApplication.overrideCursor())
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    # Qt 认为窗口在 (0,0)，传入 overlay 本地坐标
    QCursor.setPos(QPoint(850, 1400))
    QTimer.singleShot(700, done)

def done():
    print("after warp", QCursor.pos())
    QApplication.restoreOverrideCursor()
    app.quit()

QTimer.singleShot(1000, make_catcher)
QTimer.singleShot(5000, app.quit)
app.exec()
