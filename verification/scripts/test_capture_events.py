import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from slugcatpet.window import CursorCaptureWindow, PetWindow

orig_init = CursorCaptureWindow.__init__


def init(self, *args, **kwargs):
    orig_init(self, *args, **kwargs)
    self.setMouseTracking(True)


CursorCaptureWindow.__init__ = init

orig_move = CursorCaptureWindow.mouseMoveEvent


def move(self, ev):
    print("CAP_MOVE", ev.position(), flush=True)
    orig_move(self, ev)


CursorCaptureWindow.mouseMoveEvent = move

orig_leave = CursorCaptureWindow.leaveEvent


def leave(self, ev):
    print("CAP_LEAVE", flush=True)
    orig_leave(self, ev)


CursorCaptureWindow.leaveEvent = leave

home = Path(os.environ["SLUGCATPET_HOME"])
params = json.loads((home / "app.json").read_text(encoding="utf-8"))
params["output"] = "HDMI-A-1"
params["cursor_hijack"] = True
params["cursor_shape"] = True

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = PetWindow(params=params)
pet.show()
backend = pet.desktop_backend

events = []


def on_cursor(x, y):
    events.append((x, y))
    print("CURSOR", x, y, flush=True)


backend.cursor_moved.connect(on_cursor)


def start():
    cur = backend.cursor_global()
    print("START", cur, flush=True)
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    print("created", pet.start_cursor_hold(x, y, 400) is not None, flush=True)
    QTimer.singleShot(800, move_hold)
    QTimer.singleShot(1500, escape)
    QTimer.singleShot(7500, done)


def move_hold():
    pet.move_cursor_hold(pet._WL / 3, pet._HL / 2)


def escape():
    subprocess.Popen(["/usr/bin/python3", "verification/scripts/mouse_escape_long.py"])


def done():
    print("DONE", backend.cursor_global(), "hijack", pet.cursor_hijack is not None, flush=True)
    pet.stop_cursor_hijack()
    QTimer.singleShot(500, app.quit)


QTimer.singleShot(1800, start)
QTimer.singleShot(12000, app.quit)
app.exec()
