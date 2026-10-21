import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); pet.show()
def dump(tag):
 h=pet.windowHandle(); b=pet.desktop_backend
 print('APP',tag,'screen',h.screen().name() if h else None,'dpr',pet.devicePixelRatioF(),'overlay',pet.overlay_rect().getRect(),'b',getattr(b,'_target_screen',None),getattr(b,'_rect',None).getRect() if getattr(b,'_rect',None) else None,flush=True)
def switch():
 dump('BEFORE'); pet.set_output('eDP-1'); dump('AFTER')
def rebind():
    dump('PRE_REBIND')
    h=pet.windowHandle(); scr=pet.target_screen()
    print('REBIND_TO', scr.name() if scr else None, flush=True)
    if scr and h:
        h.setScreen(scr)
        pet.setScreen(scr)
    QTimer.singleShot(500, lambda: dump('REBIND_500'))
    QTimer.singleShot(2000, lambda: dump('REBIND_2S'))
QTimer.singleShot(1800, lambda: dump('T1'))
QTimer.singleShot(2800, switch)
QTimer.singleShot(6000, rebind)
QTimer.singleShot(10000, lambda: (dump('T10'), pet.shutdown(), app.quit()))
app.exec()
