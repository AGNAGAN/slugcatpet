import time
from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_RIGHT, e.BTN_RIGHT]}, name="slugcatpet-test-right")
time.sleep(3.0)
for i in range(6):
    ui.write(e.EV_REL, e.REL_X, 4)
    ui.syn()
    time.sleep(0.08)
    ui.write(e.EV_REL, e.REL_X, -4)
    ui.syn()
    time.sleep(0.08)
ui.write(e.EV_KEY, e.BTN_RIGHT, 1)
ui.syn()
time.sleep(0.12)
ui.write(e.EV_KEY, e.BTN_RIGHT, 0)
ui.syn()
time.sleep(1.0)
ui.close()
