import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from slugcatpet.window import PetWindow

home = Path(os.environ["SLUGCATPET_HOME"])
params = json.loads((home / "app.json").read_text(encoding="utf-8"))
params["output"] = "HDMI-A-1"
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = PetWindow(params=params)
pet.show()
cap = None


def show_capture():
    global cap
    cap = pet._show_cursor_capture()
    cap.clicked.connect(lambda: print("CAP CLICKED", flush=True))
    print("CAPTURE SHOWN", cap.isVisible(), cap.geometry().getRect(), flush=True)


QTimer.singleShot(1500, show_capture)
QTimer.singleShot(6000, app.quit)
app.exec()
print("DONE", flush=True)
