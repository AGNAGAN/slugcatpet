import json, os, sys, traceback
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow

home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); b=pet.desktop_backend
orig_load=b._load_script
def load():
    print('LOAD_SCRIPT target=',getattr(b,'_target_screen',None),'rect=',getattr(b,'_rect',None).getRect() if getattr(b,'_rect',None) else None, flush=True)
    traceback.print_stack(limit=5, file=sys.stdout)
    return orig_load()
b._load_script=load
orig_conf=b.configure_overlay
def conf(name, rect):
    print('CONFIGURE name=',name,'rect=',rect.getRect(),'cur_target=',getattr(b,'_target_screen',None),'cur_rect=',getattr(b,'_rect',None).getRect() if getattr(b,'_rect',None) else None, flush=True)
    return orig_conf(name,rect)
b.configure_overlay=conf
pet.show()
def sw():
    print('SET_OUTPUT start',flush=True); pet.set_output('eDP-1'); print('SET_OUTPUT done',flush=True)
def dump(tag):
    print('DUMP',tag,'tscreen',pet.target_output_name(),'win',pet.windowHandle().screen().name() if pet.windowHandle() else None,'overlay',pet.overlay_rect().getRect(),'b',getattr(b,'_target_screen',None), getattr(b,'_rect',None).getRect() if getattr(b,'_rect',None) else None, flush=True)
QTimer.singleShot(2000, lambda: dump('T2'))
QTimer.singleShot(3000, sw)
QTimer.singleShot(6000, lambda: dump('T6'))
QTimer.singleShot(6500, lambda: (pet.shutdown(), app.quit()))
app.exec()
