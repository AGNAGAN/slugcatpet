import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QRegion
from slugcatpet.ui.panels.controlhud import ControlHud

LOG=open('verification/logs/live/phase1_ctrl.log','w',buffering=1)
def log(*a): print(*a,file=LOG)
class FakePet:
    variant='survivor'; name='CtrlProbe'; controlled=True
    def __init__(self):
        self.body=SimpleNamespace(energy=1,temper=0,food=1,food_q=1,karma=1,cold=0,sleepiness=0)
        self.personality='normal'; self.hidden=False
class FakeWindow:
    def __init__(self,p): self.pets=[p]
    def stop_control(self): log('STOP_CONTROL')
    def hold_controlled(self): log('HOLD')
class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('phase1-ctrl-overlay')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.resize(1440,900); self.setScreen(QGuiApplication.screens()[0])
        self.show()
    def mousePressEvent(self,e):
        log('OVERLAY_CLICK',round(e.position().x()),round(e.position().y()))
        super().mousePressEvent(e)
app=QApplication(sys.argv)
o=Overlay()
p=FakePet(); w=FakeWindow(p)
class LogCtrl(ControlHud):
    def mousePressEvent(self,e):
        log('CTRL_PRESS',round(e.position().x()),round(e.position().y()))
        super().mousePressEvent(e)
    def keyPressEvent(self,e):
        super().keyPressEvent(e)
        log('CTRL_KEY',e.key(),'HELD',sorted(self._held),'X',self.current_input().x)
ctrl=LogCtrl(w,p,parent=o,embedded=True)
o.ctrl=ctrl
ctrl.show()
edit=QLineEdit(o); edit.setGeometry(60,60,200,30); edit.show()
def full():
    r=QRegion(0,0,o.width(),o.height())
    o.windowHandle().setMask(r); o.windowHandle().requestUpdate()
    log('FULL_MASK',r.boundingRect(),'CTRL',ctrl.geometry(),'FOCUS',QApplication.focusWidget() is ctrl,'PAUSED',ctrl._paused)
QTimer.singleShot(700,full)
def report(tag):
    inp=ctrl.current_input()
    log(tag,'ACTIVE',o.isActiveWindow(),'FOCUS',QApplication.focusWidget() is ctrl,'PAUSED',ctrl._paused,'HELD',sorted(ctrl._held),'X',inp.x,'GEO',ctrl.geometry())
for t,tag in [(2500,'AFTER_CLICK_CTRL'),(4000,'DURING_D'),(5500,'AFTER_EDIT_CLICK'),(7000,'FINAL')]:
    QTimer.singleShot(t,lambda tag=tag: report(tag))
QTimer.singleShot(9000,app.quit)
sys.exit(app.exec())
