import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); pet.show()
def dump(tag):
 h=pet.windowHandle(); b=pet.desktop_backend; print('APP',tag,'screen',h.screen().name() if h else None,'overlay',pet.overlay_rect().getRect(),'frame',pet.frameGeometry().getRect(),'b_target',getattr(b,'_target_screen',None),'b_rect',getattr(b,'_rect',None).getRect() if getattr(b,'_rect',None) else None,flush=True)
QTimer.singleShot(1800, lambda: dump('T1'))
QTimer.singleShot(2800, lambda: (print('SWITCH',flush=True), pet.set_output('eDP-1'), dump('AFTER')))
QTimer.singleShot(6000, lambda: dump('T6'))
QTimer.singleShot(9000, lambda: (dump('T9'), pet.shutdown(), app.quit()))
app.exec()
