import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QGuiApplication
app=QApplication(sys.argv)
h=next((s for s in QGuiApplication.screens() if s.name()=='HDMI-A-1'),None)
e=next((s for s in QGuiApplication.screens() if s.name()=='eDP-1'),None)
w=QWidget(); w.setWindowTitle('slugcatpet-tool-probe'); w.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool); w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True); w.resize(500,300)
if h: w.setScreen(h)
w.show()
def dump(t):
 hw=w.windowHandle(); print(t,'screen',hw.screen().name() if hw else None,'dpr',w.devicePixelRatioF(),'geo',w.geometry().getRect(),flush=True)
QTimer.singleShot(1000,lambda:dump('T1'))
def rebind():
    print('REBIND', e.name() if e else None,flush=True)
    if e:
        w.setScreen(e)
        if w.windowHandle(): w.windowHandle().setScreen(e)
    QTimer.singleShot(1000,lambda:dump('R1'))
    QTimer.singleShot(3000,lambda:dump('R3'))
QTimer.singleShot(2500,rebind)
QTimer.singleShot(6500,lambda:(dump('T6'),app.quit()))
app.exec()
