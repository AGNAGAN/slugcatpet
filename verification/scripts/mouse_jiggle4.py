import time
from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT]}, name="slugcatpet-test-mouse4")
time.sleep(2.0)
for i in range(40):
    for dx, dy in ((-20, -10), (20, 10)):
        ui.write(e.EV_REL, e.REL_X, dx)
        ui.write(e.EV_REL, e.REL_Y, dy)
        ui.syn()
        time.sleep(0.1)
ui.close()
