import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); pet.show()
def dump(tag):
 h=pet.windowHandle(); print('APP',tag,'screen',h.screen().name() if h else None,'overlay',pet.overlay_rect().getRect(),'frame',pet.frameGeometry().getRect(),'backend',getattr(pet.desktop_backend,'_target_screen',None),getattr(pet.desktop_backend,'_rect',None).getRect() if getattr(pet.desktop_backend,'_rect',None) else None,flush=True)
QTimer.singleShot(1800, lambda: dump('T1'))
QTimer.singleShot(3000, lambda: dump('T3'))
QTimer.singleShot(5000, lambda: dump('T5'))
QTimer.singleShot(6500, lambda: (dump('T6'), pet.shutdown(), app.quit()))
app.exec()
