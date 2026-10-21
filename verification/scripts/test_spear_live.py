import json, os, sys
from pathlib import Path
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); pet.show()
def spawn():
    s=pet.spawn('spear', 700, 100)
    print('SPAWN', s is not None, 'mode', getattr(s,'mode',None), 'wall', getattr(s,'wall',None), 'spears', len(pet.spears), flush=True)
    print('REGION contains', pet._build_input_region().contains(QPoint(700, 100)), flush=True)
def done():
    print('DONE spears', len(pet.spears), 'ys', [(round(s.x),round(s.y),s.mode) for s in pet.spears], flush=True)
    pet.shutdown(); app.quit()
QTimer.singleShot(1800, spawn)
QTimer.singleShot(4500, done)
QTimer.singleShot(6000, app.quit)
app.exec()
