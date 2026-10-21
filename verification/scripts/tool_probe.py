import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QGuiApplication
app=QApplication(sys.argv)
scr=next((s for s in QGuiApplication.screens() if s.name()=='HDMI-A-1'),None)
w=QWidget(); w.setWindowTitle('slugcatpet-tool-probe'); w.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool); w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True); w.resize(500,300)
if scr: w.setScreen(scr)
w.show()
print('SHOW', w.windowHandle().screen().name() if w.windowHandle() else None, w.geometry().getRect(),flush=True)
def dump(t):
 h=w.windowHandle(); print(t,'screen',h.screen().name() if h else None,'geo',w.geometry().getRect(),'frame',w.frameGeometry().getRect(),flush=True)
QTimer.singleShot(1000,lambda:dump('T1')); QTimer.singleShot(3000,lambda:dump('T3')); QTimer.singleShot(5000,lambda:(dump('T5'),app.quit()))
app.exec()
