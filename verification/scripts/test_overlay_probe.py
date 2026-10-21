import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params)
pet._backend.attach_overlay=lambda w: True
pet.show()
def dump(tag):
    h=pet.windowHandle(); print('APP',tag,'screen',h.screen().name() if h else None,'overlay',pet.overlay_rect().getRect(),'frame',pet.frameGeometry().getRect(),flush=True)
QTimer.singleShot(1500, lambda: dump('T1'))
QTimer.singleShot(4000, lambda: dump('T4'))
QTimer.singleShot(4500, lambda: (pet.shutdown(), app.quit()))
app.exec()
