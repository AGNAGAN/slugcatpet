import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QCursor
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
warp_timer = None


def show_capture():
    global cap, warp_timer
    cap = pet._show_cursor_capture()
    cap.clicked.connect(lambda: print("CAP CLICKED", flush=True))
    print("CAPTURE SHOWN", cap.isVisible(), flush=True)
    warp_timer = QTimer()
    warp_timer.timeout.connect(warp)

    def start_warp():
        print("WARP START", flush=True)
        warp_timer.start(25)

    QTimer.singleShot(1000, start_warp)


def warp():
    # 写到捕获面里一个固定位置，模拟 hold 每个 tick 的重定位。
    QCursor.setPos(QPoint(569, 1256))


QTimer.singleShot(1500, show_capture)
QTimer.singleShot(7000, app.quit)
app.exec()
print("DONE", flush=True)
