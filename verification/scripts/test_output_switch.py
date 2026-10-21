import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow

home = Path(os.environ['SLUGCATPET_HOME'])
params = json.loads((home/'app.json').read_text(encoding='utf-8'))
params['output'] = 'HDMI-A-1'
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = PetWindow(params=params)
pet.show()

def dump(tag):
    h = pet.windowHandle()
    b = pet.desktop_backend
    print(tag, 'target', pet.target_output_name(), '_screen', getattr(pet._screen,'name',lambda:None)(),
          'win_screen', h.screen().name() if h else None,
          'overlay', pet.overlay_rect().getRect(),
          'frame', pet.frameGeometry().getRect(),
          'backend_target', getattr(b,'_target_screen',None),
          'backend_rect', getattr(b,'_rect',None).getRect() if getattr(b,'_rect',None) else None,
          'backend_origin', getattr(b,'_origin',None), flush=True)

def at2(): dump('T2')
def switch1():
    dump('BEFORE1'); print('set HDMI->eDP', pet.set_output('eDP-1'), flush=True); dump('AFTER1')
def at5(): dump('T5')
def switch2():
    dump('BEFORE2'); print('set eDP->HDMI', pet.set_output('HDMI-A-1'), flush=True); dump('AFTER2')
def at8(): dump('T8')
def done():
    dump('DONE'); pet.shutdown(); app.quit()
QTimer.singleShot(2000, at2)
QTimer.singleShot(3500, switch1)
QTimer.singleShot(6000, at5)
QTimer.singleShot(7000, switch2)
QTimer.singleShot(9500, at8)
QTimer.singleShot(10500, done)
app.exec()
