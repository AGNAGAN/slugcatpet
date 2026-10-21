import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from slugcatpet.window import PetWindow

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
last = {"pos": None}


def on_cursor(x, y):
    last["pos"] = (x, y)
    events.append((round(time.monotonic(), 3), x, y))
    if y < 900:
        print("ESCAPE_EVENT", x, y, flush=True)


backend.cursor_moved.connect(on_cursor)


def info(tag):
    print(
        tag,
        "cursor", backend.cursor_global(),
        "last", last["pos"],
        "hijack", pet.cursor_hijack is not None,
        "capture", bool(pet._cursor_capture_window and pet._cursor_capture_window.isVisible()),
        flush=True,
    )


def park_in_hdmi():
    info("PARK")
    subprocess.Popen(
        ["/usr/bin/python3", "verification/scripts/mouse_to_hdmi.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def start():
    info("START")
    cur = backend.cursor_global()
    if cur is None:
        print("NO CURSOR", flush=True)
        app.quit()
        return
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    print("start hold logical", x, y, "global", cur, "area", pet._area.getRect(), flush=True)
    hj = pet.start_cursor_hold(x, y, 400)
    print("created", hj is not None, "mock", getattr(hj, "mock", None), flush=True)
    QTimer.singleShot(900, move_hold)
    QTimer.singleShot(1200, escape)
    QTimer.singleShot(3400, after_escape)


def move_hold():
    info("HOLD")
    pet.move_cursor_hold(pet._WL / 3, pet._HL / 2)
    QTimer.singleShot(300, lambda: info("HOLD_MOVED"))


def escape():
    info("ESCAPE_START")
    subprocess.Popen(
        ["/usr/bin/python3", "verification/scripts/mouse_escape_jump.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def after_escape():
    info("AFTER_ESCAPE")
    print("target overlay", pet.overlay_rect().getRect(), flush=True)
    print("event count", len(events), "min y", min((e[2] for e in events), default=None), flush=True)
    print("events tail", events[-25:], flush=True)
    pet.stop_cursor_hijack()
    QTimer.singleShot(600, done)


def done():
    info("STOP")
    app.quit()


QTimer.singleShot(2800, start)
QTimer.singleShot(9500, app.quit)
app.exec()
print("DONE", flush=True)
