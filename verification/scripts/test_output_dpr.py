import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); pet.show()
def dump(tag):
 h=pet.windowHandle(); print(tag,'screen',h.screen().name() if h else None,'dpr',pet.devicePixelRatioF(),'overlay',pet.overlay_rect().getRect(),flush=True)
def sw1(): pet.set_output('eDP-1')
def sw2(): pet.set_output('HDMI-A-1')
QTimer.singleShot(1800, lambda: dump('HDMI0'))
QTimer.singleShot(2500, sw1)
QTimer.singleShot(5000, lambda: dump('EDP1'))
QTimer.singleShot(5500, sw2)
QTimer.singleShot(8000, lambda: dump('HDMI1'))
QTimer.singleShot(8500, lambda: (pet.shutdown(), app.quit()))
app.exec()
