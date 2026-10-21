import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QGuiApplication
app = QApplication(sys.argv)
scr = next((s for s in QGuiApplication.screens() if s.name() == 'HDMI-A-1'), QGuiApplication.primaryScreen())
w = QWidget()
w.setWindowTitle('slugcatpet-move-probe')
w.resize(500, 300)
w.setScreen(scr)
w.show()
print('SHOW screen', w.windowHandle().screen().name(), 'geo', w.geometry().getRect(), flush=True)
def dump(tag):
    h=w.windowHandle()
    print(tag, 'screen', h.screen().name() if h else None, 'geo', w.geometry().getRect(), 'frame', w.frameGeometry().getRect(), flush=True)
QTimer.singleShot(1000, lambda: dump('T1'))
QTimer.singleShot(3000, lambda: dump('T3'))
QTimer.singleShot(5000, lambda: (dump('T5'), app.quit()))
app.exec()
