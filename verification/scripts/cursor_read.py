import json, os, sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from slugcatpet.window import PetWindow
home=Path(os.environ['SLUGCATPET_HOME'])
params=json.loads((home/'app.json').read_text())
params['output']='HDMI-A-1'
app=QApplication(sys.argv)
pet=PetWindow(params=params); pet.show()
def show():
    print('cursor', pet.desktop_backend.cursor_global(), 'overlay', pet.overlay_rect().getRect())
    app.quit()
QTimer.singleShot(2000, show)
app.exec()
