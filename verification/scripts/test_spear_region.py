import json, os, sys
from pathlib import Path
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME']); params=json.loads((home/'app.json').read_text()); params['output']='HDMI-A-1'
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
pet=PetWindow(params=params); pet.show()
def go():
    s=pet.spawn('spear', 700, 100)
    print('scale', pet._scale, 'overlay', pet.overlay_rect().getRect(), 'items', len(list(pet._items())), 'in', s in list(pet._items()), 's', s.x,s.y,getattr(s,'rad',None),flush=True)
    r=pet._build_input_region()
    print('region rects', r.boundingRect().getRect(), 'contains', r.contains(QPoint(700,100)), 'rect_count', len(r.rects()) if hasattr(r,'rects') else '?',flush=True)
    print('item_rects', __import__('slugcatpet.platform.wayland.regions',fromlist=['item_rects']).item_rects(s,pet._scale),flush=True)
def done(): pet.shutdown(); app.quit()
QTimer.singleShot(1800, go)
QTimer.singleShot(3500, done)
app.exec()
